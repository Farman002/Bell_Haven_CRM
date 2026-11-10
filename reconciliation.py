import hashlib
import json
import pandas as pd

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"

def proposal_key(row):
    identity = "|".join([
        str(row.get("website_name","")).strip().lower(),
        str(row.get("website_city","")).strip().lower(),
        str(row.get("website_state","")).strip().lower(),
        str(row.get("website_zip","")).strip(),
        str(row.get("top_candidate_account_id","")).strip(),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

def parse_candidates(row):
    raw = row.get("top_three_candidates_json", "[]")
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return data if isinstance(data, list) else []
    except Exception:
        return []

def safe_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def classify_parent_change(revenue, ar):
    # Assessment SOP: CHOW only when BOTH lifetime revenue and AR are non-zero.
    if safe_number(revenue) > 0 and safe_number(ar) > 0:
        return "CHOW_REQUIRED"
    return "DIRECT_REPARENT_MAY_BE_PERMITTED"

def build_new_account_payload(facility, parent_id=BELLHAVEN_PARENT_ID, care_type=""):
    return {
        "name": str(facility.get("website_name", "")).strip(),
        "parent_id": parent_id,
        "billing_street": str(facility.get("website_address", "")).strip(),
        "billing_city": str(facility.get("website_city", "")).strip(),
        "billing_state": str(facility.get("website_state", "")).strip(),
        "billing_zip": str(facility.get("website_zip", "")).strip(),
        "care_type": care_type or "Assisted Living",
        "status": "Active",
        "lifetime_revenue": 0,
        "outstanding_ar": 0,
        "note": "Created through approved Bellhaven ownership reconciliation.",
    }
