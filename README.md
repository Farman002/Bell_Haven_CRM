# Bellhaven CRM Reconciliation Review App

## 1. Setup (Windows / PyCharm)

Open a terminal in the project folder:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and paste the sandbox token into `CRM_API_TOKEN`.
Do not share `.env`, commit it to Git, or paste the token into screenshots.

## 2. Data inputs

The `data` directory includes the latest matcher exports:
- `matching_proposals.csv`
- `matching_candidates_top3.csv`
- `crm_potentially_stale_review.csv`
- `crm_duplicate_candidates.csv`
- `crm_accounts.csv`
- `bellhaven_facilities.csv`

When rerunning the matcher, replace these files with the latest outputs. Keep the filenames unchanged.

## 3. Run

```powershell
streamlit run app.py
```

## 4. Approval and execution model

- Review and save a decision first. Saving a decision does not write to the CRM.
- The Decision & audit log tab shows saved decisions.
- Live writes require selecting one approved action and typing `EXECUTE`.
- Each execution fetches the current account before writing.
- Direct re-parent is blocked if BOTH lifetime_revenue and outstanding_ar are non-zero.
- CHOW creates a new account under Bellhaven, then links the old account using `chow_current_account`.
- Duplicate resolution sets `duplicate_of_account` and `status=Inactive` on the losing account; it is blocked if the losing record has revenue or AR.
- Stale deactivation is blocked if revenue or AR is non-zero.
- No merge or delete endpoint is used.

## 5. Important limitation

The supplied OpenAPI document lists the account endpoints but does not publish request-body schemas for POST/PATCH. This app uses the account fields visible in the sandbox GET responses and the assessment's field names. Test a low-risk approved action in the sandbox first. If the API rejects a payload, the app records the failure in SQLite; inspect the error before changing the payload.

CHOW is a two-step API workflow (create new account, then patch old account link). If the second call fails, the newly created account may remain; inspect CRM and the audit log before retrying. Do not blindly rerun.


## CHOW execution safety update

`chow_workflow.py` implements a resumable two-stage CHOW:
1. Re-checks the old account's financial values and ownership.
2. Searches for an already-created replacement with exact facility name, city, ZIP and Bellhaven parent before attempting POST.
3. Persists the new account ID in SQLite immediately after creation (or exact-match recovery).
4. Verifies the replacement account before linking.
5. PATCHes only `chow_current_account` on the old account.
6. Re-fetches both accounts and verifies that the old account's parent, status, lifetime revenue and AR remain unchanged.
7. If linking fails after creation, a retry resumes from the stored replacement ID.

The assessment API's OpenAPI file does not publish POST/PATCH request schemas. The create payload therefore follows the field names observed in GET account records, but it remains an unverified API contract until a sandbox POST is accepted. Review the API response and CRM browser after the first approved test. Do not blindly retry after an ambiguous POST response; the workflow attempts an exact-match recovery first.

Failed executions can be retried from the Decision & audit log tab. A failed CHOW with a persisted new account ID will not repeat the create step.
