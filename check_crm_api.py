
import os
import json
import requests
from dotenv import load_dotenv

# ==========================================================
# CONFIGURATION
# ==========================================================

load_dotenv(override=True)

BASE_URL = os.getenv("CRM_BASE_URL", "").rstrip("/")
API_TOKEN = os.getenv("CRM_API_TOKEN", "")
TIMEOUT = int(os.getenv("CRM_TIMEOUT", "30"))

ACCOUNT_ID = "001U6RW32TY0WSXZZB"

if not BASE_URL:
    raise ValueError("CRM_BASE_URL is missing from .env")

if not API_TOKEN:
    raise ValueError("CRM_API_TOKEN is missing from .env")

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}


# ==========================================================
# HELPER FUNCTION
# ==========================================================

def print_json(title, data):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print(json.dumps(data, indent=4, ensure_ascii=False, default=str))


def make_get_request(url, params=None):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=TIMEOUT
        )

        print(f"HTTP Status: {response.status_code}")

        if not response.ok:
            print("API Error:")
            print(response.text[:3000])
            return None

        return response.json()

    except requests.RequestException as error:
        print(f"Request failed: {error}")
        return None

    except ValueError:
        print("API returned a non-JSON response.")
        return None


# ==========================================================
# 1. CHECK AUTHENTICATION
# ==========================================================

def check_authentication():

    print("\n1. CHECKING CRM AUTHENTICATION")

    result = make_get_request(f"{BASE_URL}/me")

    if result is None:
        print("Authentication check failed.")
        return False

    print_json("AUTHENTICATION RESPONSE", result)

    return True


# ==========================================================
# 2. FETCH COMPLETE ACCOUNT DETAILS
# ==========================================================

def fetch_account(account_id):

    print("\n2. FETCHING COMPLETE CRM ACCOUNT")

    result = make_get_request(
        f"{BASE_URL}/accounts/{account_id}"
    )

    if result is None:
        return None

    print_json("COMPLETE ACCOUNT JSON RESPONSE", result)

    # Handle common API response structures
    account = result.get("data", result)

    if not isinstance(account, dict):
        print("Unexpected account response structure.")
        return None

    print("\n" + "=" * 70)
    print("ACCOUNT FIELD-BY-FIELD INSPECTION")
    print("=" * 70)

    for field, value in account.items():
        print(f"{field}: {value}")

    return account


# ==========================================================
# 3. INSPECT OPENAPI SPECIFICATION
# ==========================================================

def inspect_openapi():

    print("\n3. INSPECTING OPENAPI SPECIFICATION")

    spec_url = (
        BASE_URL.removesuffix("/api/v1")
        + "/api/openapi.json"
    )

    spec = make_get_request(spec_url)

    if spec is None:
        print("Could not retrieve OpenAPI specification.")
        return

    print("\nOpenAPI version:", spec.get("openapi"))
    print("API title:", spec.get("info", {}).get("title"))

    paths = spec.get("paths", {})

    account_paths = [
        "/api/v1/accounts",
        "/api/v1/accounts/{account_id}"
    ]

    for path in account_paths:

        print("\n" + "-" * 70)
        print("PATH:", path)
        print("-" * 70)

        methods = paths.get(path, {})

        if not methods:
            print("Endpoint not found.")
            continue

        for method, details in methods.items():

            print("\nMETHOD:", method.upper())
            print("Summary:", details.get("summary"))

            request_body = details.get("requestBody")

            if request_body:
                print("REQUEST BODY:")
                print_json("REQUEST BODY SCHEMA", request_body)
            else:
                print("Request body: Not documented")

            responses = details.get("responses", {})

            print("DOCUMENTED RESPONSES:")

            for status, response_info in responses.items():

                print(f"\nStatus: {status}")

                content = response_info.get("content", {})

                if content:
                    print_json(
                        "RESPONSE CONTENT",
                        content
                    )
                else:
                    print(response_info.get("description", ""))


# ==========================================================
# 4. INSPECT ACCOUNT COMPONENT SCHEMAS
# ==========================================================

def inspect_account_schemas():

    print("\n4. INSPECTING ACCOUNT COMPONENT SCHEMAS")

    spec_url = (
        BASE_URL.removesuffix("/api/v1")
        + "/api/openapi.json"
    )

    spec = make_get_request(spec_url)

    if spec is None:
        return

    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    if not schemas:
        print("No component schemas are documented.")
        return

    found = False

    for schema_name, schema_data in schemas.items():

        if "account" in schema_name.lower():

            found = True

            print_json(
                f"SCHEMA: {schema_name}",
                schema_data
            )

    if not found:
        print("No account-related schemas found.")

    print("\nAvailable component schema names:")

    for name in schemas:
        print("-", name)


# ==========================================================
# 5. MAIN EXECUTION
# ==========================================================

def main():

    print("\n" + "=" * 70)
    print("BELLHAVEN CRM API INSPECTION")
    print("=" * 70)

    print("Base URL:", BASE_URL)
    print("Account ID:", ACCOUNT_ID)

    # Authentication
    authenticated = check_authentication()

    if not authenticated:
        print("\nStopping because authentication failed.")
        return

    # Existing account
    account = fetch_account(ACCOUNT_ID)

    if account:

        print("\n" + "=" * 70)
        print("IMPORTANT CHOW FIELD VERIFICATION")
        print("=" * 70)

        fields = [
            "account_id",
            "name",
            "parent_id",
            "status",
            "lifetime_revenue",
            "outstanding_ar",
            "chow_current_account",
            "duplicate_of_account"
        ]

        for field in fields:
            print(f"{field}: {account.get(field, 'FIELD NOT PRESENT')}")

    # OpenAPI endpoints
    inspect_openapi()

    # Account schemas
    inspect_account_schemas()

    print("\n" + "=" * 70)
    print("INSPECTION COMPLETED")
    print("NO CRM RECORDS WERE MODIFIED.")
    print("=" * 70)


if __name__ == "__main__":
    main()
