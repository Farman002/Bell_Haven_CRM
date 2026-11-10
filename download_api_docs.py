
import requests
import json

BASE_URL = "https://analyst-assessment-production.up.railway.app"

# Try the likely OpenAPI locations
endpoints = [
    f"{BASE_URL}/api/openapi.json",
    f"{BASE_URL}/openapi.json",
    f"{BASE_URL}/api/v1/openapi.json"
]

for url in endpoints:
    try:
        response = requests.get(url, timeout=30)

        print(f"Checking: {url}")
        print("Status:", response.status_code)

        if response.status_code == 200:
            data = response.json()

            if "paths" in data:
                with open("openapi.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)

                print("\nSUCCESS! API documentation downloaded.")
                print("Available API paths:")

                for path, methods in data["paths"].items():
                    print(path, list(methods.keys()))

                break

    except Exception as e:
        print("Error:", e)

else:
    print("\nCould not locate OpenAPI JSON.")
    print("Open the interactive documentation:")
    print(f"{BASE_URL}/api/docs")
