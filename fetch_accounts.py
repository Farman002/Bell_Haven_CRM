
import os
import json
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("CRM_BASE_URL")
TOKEN = os.getenv("CRM_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_all_accounts():

    url = f"{BASE_URL}/accounts"

    page = 1
    page_size = 50

    all_accounts = []
    total_accounts = None

    print("\nStarting CRM account extraction...\n")

    while True:

        params = {
            "page": page,
            "page_size": page_size
        }

        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        result = response.json()

        accounts = result.get("data", [])

        if total_accounts is None:
            total_accounts = result.get("total", 0)

        if not accounts:
            break

        all_accounts.extend(accounts)

        print(
            f"Page {page}: "
            f"{len(accounts)} accounts downloaded | "
            f"Total collected: {len(all_accounts)}"
        )

        if len(all_accounts) >= total_accounts:
            break

        page += 1

    # Save JSON
    json_path = os.path.join(
        OUTPUT_DIR, "crm_accounts.json"
    )

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_accounts, f, indent=4)

    # Save CSV
    csv_path = os.path.join(
        OUTPUT_DIR, "crm_accounts.csv"
    )

    df = pd.DataFrame(all_accounts)
    df.to_csv(csv_path, index=False)

    print("\n========== EXTRACTION SUMMARY ==========")
    print("Expected accounts:", total_accounts)
    print("Downloaded accounts:", len(all_accounts))
    print("JSON saved:", json_path)
    print("CSV saved:", csv_path)

    if total_accounts != len(all_accounts):
        print("WARNING: Account count does not match API total.")

    return all_accounts


if __name__ == "__main__":

    if not BASE_URL or not TOKEN:
        raise ValueError("CRM_BASE_URL or CRM_TOKEN missing in .env")

    fetch_all_accounts()
