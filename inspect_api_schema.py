
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

base_url = os.getenv("CRM_BASE_URL").rstrip("/")
token = os.getenv("CRM_API_TOKEN")

headers = {"Authorization": f"Bearer {token}"}

# OpenAPI specification
url = base_url.replace("/api/v1", "") + "/api/openapi.json"

response = requests.get(url, headers=headers, timeout=30)
response.raise_for_status()

spec = response.json()

print("\n========== ACCOUNT ENDPOINTS ==========")

for path, methods in spec.get("paths", {}).items():
    if "accounts" not in path:
        continue

    print("\nPATH:", path)

    for method, details in methods.items():
        print("\nMETHOD:", method.upper())
        print("Summary:", details.get("summary"))

        body = details.get("requestBody")
        if body:
            print("Request body:")
            print(json.dumps(body, indent=2))
        else:
            print("Request body: Not documented")

print("\n========== COMPONENT SCHEMAS ==========")

schemas = spec.get("components", {}).get("schemas", {})

for name, schema in schemas.items():
    if "account" in name.lower():
        print("\nSCHEMA:", name)
        print(json.dumps(schema, indent=2))

print("\n========== END OF INSPECTION ==========")
