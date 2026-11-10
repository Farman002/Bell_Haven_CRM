
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_URL = os.getenv("CRM_BASE_URL", "").rstrip("/")
TOKEN = os.getenv("CRM_API_TOKEN", "")
TIMEOUT = 30

PARENT_ID = "0015QAPLGS3FVYEEEM"

if not BASE_URL or not TOKEN:
    raise ValueError("CRM configuration missing from .env")

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
})


def request(method, path, **kwargs):
    response = session.request(
        method,
        f"{BASE_URL}/{path.lstrip('/')}",
        timeout=TIMEOUT,
        **kwargs
    )

    print(f"\n{method} {path}")
    print("HTTP:", response.status_code)

    try:
        result = response.json()
    except ValueError:
        result = {"raw_response": response.text}

    print(json.dumps(result, indent=2, default=str))

    if not response.ok:
        raise RuntimeError(
            f"API request failed: HTTP {response.status_code}"
        )

    return result


def unwrap(result):
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        return result["data"]
    return result


def main():

    print("=" * 65)
    print("BELLHAVEN CRM WRITE CONTRACT TEST")
    print("Test account only. No Tiffin or Marietta changes.")
    print("=" * 65)

    # 1. Verify authentication
    request("GET", "/me")

    # Unique, recognizable test account name
    test_name = (
        "API TEST - DO NOT USE - "
        + datetime.now().strftime("%Y%m%d-%H%M%S")
    )

    print("\nTest account name:", test_name)

    # 2. Search for an existing exact test account.
    search = request(
        "GET",
        "/accounts",
        params={"q": "API TEST - DO NOT USE", "page": 1, "page_size": 100}
    )

    rows = search.get("data", []) if isinstance(search, dict) else []

    existing = next(
        (row for row in rows if row.get("name") == test_name),
        None
    )

    if existing:
        print("\nExact test account already exists.")
        print("Reusing it instead of creating another.")
        account_id = existing.get("account_id")

    else:
        print("\nProposed CREATE payload:")

        payload = {
            "name": test_name,
            "parent_id": PARENT_ID,
            "billing_street": "TEST ADDRESS - NOT A REAL FACILITY",
            "billing_city": "Test City",
            "billing_state": "OH",
            "billing_zip": "00000",
            "care_type": "Skilled Nursing",
            "status": "Inactive",
            "note": "API write contract test. Not a real facility. Do not use."
        }

        print(json.dumps(payload, indent=2))

        confirmation = input(
            "\nType CREATE TEST ACCOUNT to send the POST request: "
        )

        if confirmation != "CREATE TEST ACCOUNT":
            print("Cancelled. No account created.")
            return

        # 3. Create test account
        created = request(
            "POST",
            "/accounts",
            json=payload
        )

        created_data = unwrap(created)
        account_id = (
            created_data.get("account_id")
            if isinstance(created_data, dict)
            else None
        )

        # If POST response doesn't include ID, search again.
        # Never blindly repeat POST.
        if not account_id:
            print("\nNo account_id in POST response.")
            print("Searching CRM for the exact test account.")

            search = request(
                "GET",
                "/accounts",
                params={
                    "q": test_name,
                    "page": 1,
                    "page_size": 100
                }
            )

            rows = search.get("data", [])
            matches = [
                row for row in rows
                if row.get("name") == test_name
            ]

            if len(matches) != 1:
                print(
                    "\nCould not uniquely identify the created account."
                )
                print("Do not repeat POST. Inspect the CRM manually.")
                return

            account_id = matches[0].get("account_id")

    if not account_id:
        print("Account ID unavailable. Stopping.")
        return

    print("\nTEST ACCOUNT ID:", account_id)

    # 4. GET account and verify creation
    account = unwrap(
        request("GET", f"/accounts/{account_id}")
    )

    if account.get("parent_id") != PARENT_ID:
        raise RuntimeError("Parent verification failed.")

    if account.get("status") != "Inactive":
        raise RuntimeError("Test account is not Inactive.")

    if account.get("name") != test_name:
        raise RuntimeError("Account name verification failed.")

    print("\nCREATE VERIFICATION PASSED.")

    # 5. Test PATCH using a harmless note update
    test_note = (
        "PATCH VERIFIED - API write contract test - "
        + datetime.now().isoformat(timespec="seconds")
    )

    print("\nTesting PATCH on the test account only.")

    patch_response = request(
        "PATCH",
        f"/accounts/{account_id}",
        json={"note": test_note}
    )

    # 6. GET again to verify persistence
    updated = unwrap(
        request("GET", f"/accounts/{account_id}")
    )

    if updated.get("note") != test_note:
        raise RuntimeError(
            "PATCH response received, but note did not persist."
        )

    if updated.get("status") != "Inactive":
        raise RuntimeError("Test account status unexpectedly changed.")

    if updated.get("parent_id") != PARENT_ID:
        raise RuntimeError("Test account parent unexpectedly changed.")

    print("\n" + "=" * 65)
    print("WRITE CONTRACT TEST COMPLETED SUCCESSFULLY")
    print("=" * 65)

    print("Account ID:", account_id)
    print("Account name:", updated.get("name"))
    print("Parent ID:", updated.get("parent_id"))
    print("Status:", updated.get("status"))
    print("PATCH note:", updated.get("note"))

    print("\nPOST: VERIFIED")
    print("PATCH: VERIFIED")
    print("GET AFTER WRITE: VERIFIED")
    print("Tiffin account: NOT MODIFIED")
    print("Marietta account: NOT MODIFIED")


if __name__ == "__main__":
    main()
