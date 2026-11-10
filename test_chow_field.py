
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_URL = os.getenv("CRM_BASE_URL", "").rstrip("/")
TOKEN = os.getenv("CRM_API_TOKEN", "")

TEST_ACCOUNT_ID = "001B0CC23320397C95"
REFERENCE_ACCOUNT_ID = "001U6RW32TY0WSXZZB"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def get_account(account_id):
    r = requests.get(
        f"{BASE_URL}/accounts/{account_id}",
        headers=headers,
        timeout=30
    )
    r.raise_for_status()
    return r.json()

def patch_account(account_id, payload):
    r = requests.patch(
        f"{BASE_URL}/accounts/{account_id}",
        headers=headers,
        json=payload,
        timeout=30
    )
    print("PATCH status:", r.status_code)
    print("Response:", r.text)
    r.raise_for_status()
    return r.json()

# Confirm the test record is the intended inactive test account.
test_account = get_account(TEST_ACCOUNT_ID)

assert test_account["name"].startswith("API TEST - DO NOT USE")
assert test_account["status"] == "Inactive"
assert not test_account.get("chow_current_account")

print("Test account verified.")

confirm = input(
    "Type TEST CHOW FIELD to test and then clear the link: "
)

if confirm != "TEST CHOW FIELD":
    print("Cancelled.")
    raise SystemExit

# Test field acceptance on the test account only.
patch_account(
    TEST_ACCOUNT_ID,
    {"chow_current_account": REFERENCE_ACCOUNT_ID}
)

linked = get_account(TEST_ACCOUNT_ID)

if linked.get("chow_current_account") != REFERENCE_ACCOUNT_ID:
    raise RuntimeError("CHOW field did not persist.")

print("CHOW field PATCH verified.")

# Restore the test account's original empty link.
patch_account(
    TEST_ACCOUNT_ID,
    {"chow_current_account": ""}
)

restored = get_account(TEST_ACCOUNT_ID)

if restored.get("chow_current_account") not in ("", None):
    raise RuntimeError(
        "Could not restore test account. Manual review required."
    )

print("Test account CHOW field restored to empty.")
print("Tiffin account was not modified.")
