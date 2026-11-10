import os
import requests
from dotenv import load_dotenv

load_dotenv()

class CRMError(RuntimeError):
    pass

class CRMClient:
    def __init__(self):
        self.base_url = os.getenv("CRM_BASE_URL", "").rstrip("/")
        self.token = os.getenv("CRM_API_TOKEN", "")
        self.timeout = int(os.getenv("CRM_TIMEOUT", "30"))
        if not self.base_url or not self.token:
            raise CRMError("Set CRM_BASE_URL and CRM_API_TOKEN in your .env file.")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise CRMError(f"CRM connection failed: {exc}") from exc
        if not response.ok:
            body = response.text[:1500]
            raise CRMError(f"{method} {path} failed ({response.status_code}): {body}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw_response": response.text}

    def get_me(self):
        return self._request("GET", "/me")

    def get_account(self, account_id):
        result = self._request("GET", f"/accounts/{account_id}")
        return result.get("data", result)

    def list_accounts(self, page_size=100):
        rows, page = [], 1
        while True:
            result = self._request("GET", "/accounts", params={"page": page, "page_size": page_size})
            batch = result.get("data", [])
            rows.extend(batch)
            total = result.get("total")
            if not batch or (total is not None and len(rows) >= int(total)) or len(batch) < page_size:
                break
            page += 1
        return rows

    def patch_account(self, account_id, payload):
        return self._request("PATCH", f"/accounts/{account_id}", json=payload)

    def create_account(self, payload):
        return self._request("POST", "/accounts", json=payload)
