
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("CRM_BASE_URL")
TOKEN = os.getenv("CRM_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

url = f"{BASE_URL}/accounts"

response = requests.get(
    url,
    headers=headers,
    params={"q": "bellhaven"},
    timeout=30
)

print("Status Code:", response.status_code)
print("Response:")

try:
    print(response.json())
except ValueError:
    print(response.text)
