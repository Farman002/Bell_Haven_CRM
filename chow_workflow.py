import json
from approvals import get_chow_workflow, save_chow_created, save_chow_linked, save_chow_error
from reconciliation import BELLHAVEN_PARENT_ID, safe_number
from crm_client import CRMError


def _unwrap(obj):
    return obj.get("data", obj) if isinstance(obj, dict) else obj


def _find_created_account(client, facility, expected_parent):
    name = str(facility.get("website_name", "")).strip().casefold()
    city = str(facility.get("website_city", "")).strip().casefold()
    zip_code = str(facility.get("website_zip", "")).strip()
    matches = []
    for acc in client.list_accounts(page_size=100):
        if (
            str(acc.get("name", "")).strip().casefold() == name
            and str(acc.get("billing_city", "")).strip().casefold() == city
            and str(acc.get("billing_zip", "")).strip() == zip_code
            and str(acc.get("parent_id", "")) == expected_parent
        ):
            matches.append(acc)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise CRMError("Multiple identical replacement accounts found. Manual review required; no further write performed.")
    return None


def execute_chow(client, old_account_id, facility, care_type=None):
    """
    Resumable CHOW:
    - POST once, persist the returned ID immediately.
    - Verify the new account before PATCH.
    - If linking fails, retry only the PATCH stage on the next run.
    """
    facility_name = str(facility.get("website_name", "Unknown facility"))
    workflow = get_chow_workflow(old_account_id)

    try:
        old_before = client.get_account(old_account_id)
        if safe_number(old_before.get("lifetime_revenue")) <= 0 or safe_number(old_before.get("outstanding_ar")) <= 0:
            raise CRMError("CHOW blocked: SOP requires BOTH revenue and outstanding AR to be greater than zero.")

        if str(old_before.get("parent_id", "")) == BELLHAVEN_PARENT_ID:
            raise CRMError("Old account is already under Bellhaven; verify the ownership proposal manually.")

        if workflow and workflow.get("status") == "COMPLETED":
            linked_id = workflow.get("new_account_id")
            current = client.get_account(old_account_id)
            if current.get("chow_current_account") == linked_id:
                return {"status": "ALREADY_COMPLETED", "new_account_id": linked_id}
            raise CRMError("Workflow marked completed but CRM link does not match. Manual reconciliation required.")

        new_id = workflow.get("new_account_id") if workflow else None

        if not new_id:
            # Detect a prior POST whose response was lost before retrying.
            existing = _find_created_account(client, facility, BELLHAVEN_PARENT_ID)
            if existing:
                new_id = existing.get("account_id")
                if not new_id:
                    raise CRMError("Existing replacement candidate has no account_id.")
                save_chow_created(old_account_id, facility_name, new_id, {"recovered_by_exact_match": existing})
            else:
                payload = {
                    "name": facility_name,
                    "parent_id": BELLHAVEN_PARENT_ID,
                    "billing_street": str(facility.get("website_address", "")).strip(),
                    "billing_city": str(facility.get("website_city", "")).strip(),
                    "billing_state": str(facility.get("website_state", "")).strip(),
                    "billing_zip": str(facility.get("website_zip", "")).strip(),
                    "care_type": care_type or old_before.get("care_type") or "Skilled Nursing",
                    "status": "Active",
                    "note": "Replacement account created through approved Bellhaven CHOW reconciliation."
                }
                created_raw = client.create_account(payload)
                created = _unwrap(created_raw)
                new_id = created.get("account_id") if isinstance(created, dict) else None

                if not new_id:
                    # A successful POST with an unfamiliar response shape must not be repeated blindly.
                    recovered = _find_created_account(client, facility, BELLHAVEN_PARENT_ID)
                    if recovered:
                        new_id = recovered.get("account_id")
                    else:
                        raise CRMError(
                            "POST returned no account_id and exact-match recovery found no unique account. "
                            "Inspect CRM before retrying; create was not repeated."
                        )

                save_chow_created(old_account_id, facility_name, new_id, created_raw)

        # Verify replacement account before linking the old one.
        new_account = client.get_account(new_id)
        expected = {
            "name": facility_name,
            "parent_id": BELLHAVEN_PARENT_ID,
            "billing_city": str(facility.get("website_city", "")).strip(),
            "billing_zip": str(facility.get("website_zip", "")).strip()
        }
        for field, expected_value in expected.items():
            if str(new_account.get(field, "")).strip().casefold() != str(expected_value).strip().casefold():
                raise CRMError(f"New account verification failed for {field}: expected {expected_value!r}, got {new_account.get(field)!r}")

        # Re-fetch old account immediately before link; preserve all fields except chow_current_account.
        old_current = client.get_account(old_account_id)
        if old_current.get("chow_current_account") not in ("", None, new_id):
            raise CRMError("Old account already points to a different chow_current_account. Manual review required.")
        if old_current.get("parent_id") != old_before.get("parent_id"):
            raise CRMError("Old account parent changed during workflow. Manual review required.")

        if old_current.get("chow_current_account") != new_id:
            link_response = client.patch_account(old_account_id, {"chow_current_account": new_id})
        else:
            link_response = {"already_linked": True}

        old_after = client.get_account(old_account_id)
        if old_after.get("chow_current_account") != new_id:
            raise CRMError("Link PATCH did not persist. Replacement account ID is saved; retry will only attempt link after verification.")

        # Verify old account financials, parent, and status were preserved.
        for field in ["parent_id", "status", "lifetime_revenue", "outstanding_ar"]:
            if old_after.get(field) != old_before.get(field):
                raise CRMError(f"Preservation check failed: old account field {field} changed.")

        save_chow_linked(old_account_id, link_response)
        return {
            "status": "COMPLETED",
            "old_account_before": old_before,
            "new_account": new_account,
            "link_response": link_response,
            "old_account_after": old_after
        }

    except Exception as exc:
        save_chow_error(old_account_id, facility_name, exc)
        raise
