# Bellhaven CRM Ownership Reconciliation System

An automated CRM reconciliation application that identifies ownership discrepancies between Bellhaven Senior Living's website facilities and CRM records, supports human-reviewed corrections, and maintains an auditable history of approved changes.

## Project Overview

The Bellhaven CRM Ownership Reconciliation System helps identify and resolve inconsistencies between publicly listed facility information and CRM account ownership.

The application combines website scraping, data matching, ownership analysis, human approval, and controlled CRM API integration.

It is designed to make reconciliation repeatable, transparent, and safe through approval-based execution and audit logging.

## Key Features

- **Website Scraping:** Extracts facility information from the Bellhaven website.
- **CRM Data Extraction:** Retrieves account records from the CRM API.
- **Intelligent Matching:** Compares facility names, addresses, locations, and account ownership.
- **Ownership Reconciliation:** Identifies accounts that may require ownership corrections.
- **Human-in-the-Loop Approval:** Requires an explicit approval before executing CRM changes.
- **CHOW Workflow:** Handles Change of Ownership cases while preserving historical account information.
- **Duplicate Management:** Supports duplicate identification and survivor-account linking.
- **Audit Logging:** Records decisions and CRM execution results.
- **Resumable Execution:** Supports recovery from interrupted CHOW workflows.
- **Scheduled Processing:** Supports daily website scraping and matching.

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Dashboard | Streamlit |
| Data Processing | Pandas |
| Web Scraping | Requests, BeautifulSoup |
| API Integration | REST API, Requests |
| Local Database | SQLite |
| Configuration | Python dotenv |
| Scheduling | GitHub Actions |

## Project Architecture

```text
BellHaven_CRM/
│
├── app.py
├── scraper.py
├── matcher.py
├── fetch_accounts.py
├── crm_client.py
├── approvals.py
├── reconciliation.py
├── chow_workflow.py
│
├── data/
│   └── bellhaven_facilities.csv
│
├── .github/
│   └── workflows/
│       └── daily.yml
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Application Workflow

1. Scrape facility information from the Bellhaven website.
2. Retrieve existing CRM accounts.
3. Normalize and compare facility and CRM information.
4. Generate matching and ownership review proposals.
5. Display proposed actions in the Streamlit dashboard.
6. Review and approve or reject proposed changes.
7. Execute approved CRM operations through the API.
8. Verify API results and record execution details in the audit log.

## Reconciliation Logic

The application categorizes records into review groups, including:

- Already under the Bellhaven parent account.
- Possible matches.
- Ambiguous matches.
- Weak matches.
- Ownership review.
- No CRM candidate.
- Potential duplicate accounts.
- Potentially stale accounts.

Matching classifications are recommendations for review and are not treated as automatic proof of ownership.

## Change of Ownership (CHOW) Handling

The application follows a specific CHOW preservation rule:

When an existing account has both lifetime revenue greater than zero and outstanding accounts receivable greater than zero:

1. Preserve the existing account's original parent ownership.
2. Create a new account under the Bellhaven parent account.
3. Link the old account to the new account using `chow_current_account`.
4. Verify the new account and ownership link.
5. Preserve the old account's financial and historical information.

When either lifetime revenue or outstanding AR is zero, direct re-parenting may be permitted after ownership verification.

## Duplicate Account Handling

When a duplicate is confirmed:

- Identify the surviving CRM account.
- Set `duplicate_of_account` on the losing account to the survivor's ID.
- Mark the losing account as `Inactive`.
- Preserve the audit history.

The application does not use account merge or deletion operations.

## Human Approval and Audit Trail

CRM modifications are not performed simply because a matching proposal exists.

The application requires an explicit human decision before live execution.

The audit history records:

- Proposal identification.
- Facility name.
- Action type.
- Approval or rejection decision.
- Actor and rationale.
- CRM execution status.
- Before-and-after account information.

This provides traceability for reconciliation decisions and CRM modifications.

## Installation

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd BellHaven_CRM
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root using `.env.example` as a template.

Configure:

```env
CRM_BASE_URL=YOUR_CRM_API_BASE_URL
CRM_API_TOKEN=YOUR_CRM_API_TOKEN
```

Never commit the actual `.env` file or API credentials to GitHub.

## Running the Application

### Step 1: Scrape website facilities

```bash
python scraper.py
```

### Step 2: Fetch CRM accounts

```bash
python fetch_accounts.py
```

### Step 3: Generate matching proposals

```bash
python matcher.py
```

### Step 4: Launch the dashboard

```bash
python -m streamlit run app.py
```

Open the local Streamlit URL displayed in the terminal.

## Scheduled Execution

The project includes a GitHub Actions workflow for daily automated processing.

The scheduled workflow runs website scraping and matching to refresh reconciliation data.

Live CRM modifications remain subject to the application's human approval process.

## Security and Data Protection

- CRM credentials are stored in environment variables.
- API tokens must not be committed to source control.
- CRM modifications require explicit approval.
- Local approval and audit records are maintained using SQLite.
- Private CRM exports and sensitive local data should be excluded from the public repository.

## Future Improvements

- Enhanced address and geographic matching.
- More comprehensive reconciliation reporting.
- Improved matching confidence and explainability.
- Additional CRM data validation.
- Automated reconciliation performance reports.

## Author

**Farman Naim**

Python Developer | Data Analytics | Automation

GitHub: https://github.com/Farman002

LinkedIn: https://www.linkedin.com/in/farman-naim/

---

*This project was developed as a CRM ownership reconciliation and data-quality assessment, with an emphasis on safe API operations, human oversight, historical data preservation, and auditability.*
