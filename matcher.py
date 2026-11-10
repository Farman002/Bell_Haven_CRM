"""Bellhaven CRM reconciliation matcher.

Read-only: this script only reads website/CRM exports and writes review files.
It never calls the CRM API or changes CRM records.

Expected input files (relative to project root):
    data/bellhaven_facilities.csv
    data/crm_accounts.csv

Run from project root:
    python matcher.py
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WEBSITE_FILE = DATA_DIR / "bellhaven_facilities.csv"
CRM_FILE = DATA_DIR / "crm_accounts.csv"
OUTPUT_DIR = DATA_DIR

# Confirmed parent account from the CRM export.
BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"

# A high score is a review priority, not proof of legal ownership.
STRONG_MATCH_SCORE = 82.0
POSSIBLE_MATCH_SCORE = 55.0


def clean(value: Any) -> str:
    if pd.isna(value) or value is None:
        return ""
    return str(value).strip()


def normalize(value: Any) -> str:
    value = clean(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_zip(value: Any) -> str:
    value = clean(value)
    if not value:
        return ""
    # CSV exports may turn ZIPs into values such as 45840.0.
    value = re.sub(r"\.0$", "", value)
    digits = re.sub(r"\D", "", value)
    return digits[:5]


def similarity(a: Any, b: Any) -> float:
    a_norm, b_norm = normalize(a), normalize(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def token_overlap(a: Any, b: Any) -> float:
    a_tokens = set(normalize(a).split())
    b_tokens = set(normalize(b).split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def street_score(website_street: Any, crm_street: Any) -> float:
    # Blend character similarity and token overlap to tolerate abbreviations/order.
    return 0.65 * similarity(website_street, crm_street) + 0.35 * token_overlap(website_street, crm_street)


def get_candidate(website: pd.Series, crm: pd.Series) -> dict[str, Any] | None:
    city_match = normalize(website.get("city")) == normalize(crm.get("billing_city"))
    state_match = normalize(website.get("state")) == normalize(crm.get("billing_state"))

    # City and state are the minimum geographic gate; never compare unrelated towns.
    if not (city_match and state_match):
        return None

    web_zip = normalize_zip(website.get("zip"))
    crm_zip = normalize_zip(crm.get("billing_zip"))
    zip_match = bool(web_zip and crm_zip and web_zip == crm_zip)
    zip_conflict = bool(web_zip and crm_zip and web_zip != crm_zip)

    street_sim = street_score(website.get("address"), crm.get("billing_street"))
    name_sim = similarity(website.get("name"), crm.get("name"))

    # ZIP and street are primary identity evidence; name similarity is secondary.
    score = 100 * (0.35 * float(zip_match) + 0.40 * street_sim + 0.25 * name_sim)
    if zip_conflict:
        score -= 12.0
    score = round(max(0.0, min(100.0, score)), 2)

    warnings = []
    if zip_conflict:
        warnings.append(f"ZIP mismatch: website {web_zip}, CRM {crm_zip}")
    if street_sim < 0.45:
        warnings.append("Street address is a weak match")
    if name_sim < 0.55:
        warnings.append("Facility name differs materially")

    if score >= STRONG_MATCH_SCORE and street_sim >= 0.70 and (zip_match or street_sim >= 0.88):
        candidate_class = "STRONG_CANDIDATE_REQUIRES_APPROVAL"
    elif score >= POSSIBLE_MATCH_SCORE:
        candidate_class = "POSSIBLE_CANDIDATE_REVIEW"
    else:
        candidate_class = "WEAK_CANDIDATE_REVIEW"

    parent_id = clean(crm.get("parent_id"))
    parent_is_bellhaven = parent_id == BELLHAVEN_PARENT_ID
    revenue = pd.to_numeric(crm.get("lifetime_revenue", 0), errors="coerce")
    outstanding_ar = pd.to_numeric(crm.get("outstanding_ar", 0), errors="coerce")
    financials_known = pd.notna(revenue) and pd.notna(outstanding_ar)
    if financials_known and revenue > 0 and outstanding_ar > 0:
        ownership_path = "CHOW_REQUIRED_PRESERVE_OLD_ACCOUNT_CREATE_NEW_ACCOUNT"
    elif financials_known and (revenue == 0 or outstanding_ar == 0):
        ownership_path = "DIRECT_REPARENT_MAY_BE_PERMITTED_AFTER_APPROVAL"
    else:
        ownership_path = "FINANCIAL_REVIEW_REQUIRED_MISSING_OR_INVALID_VALUES"

    if candidate_class == "STRONG_CANDIDATE_REQUIRES_APPROVAL" and not parent_is_bellhaven:
        suggested_action = "OWNERSHIP_REVIEW"
    elif candidate_class == "STRONG_CANDIDATE_REQUIRES_APPROVAL":
        suggested_action = "MATCH_REVIEW_PARENT_ALREADY_BELLHAVEN"
    else:
        suggested_action = "MANUAL_REVIEW"

    return {
        "crm_account_id": clean(crm.get("account_id")),
        "crm_name": clean(crm.get("name")),
        "crm_parent_id": parent_id,
        "crm_parent_name": clean(crm.get("parent_name")),
        "crm_status": clean(crm.get("status")),
        "lifetime_revenue": crm.get("lifetime_revenue", 0),
        "outstanding_ar": crm.get("outstanding_ar", 0),
        "ownership_path_if_parent_change_is_confirmed": ownership_path,
        "crm_billing_street": clean(crm.get("billing_street")),
        "crm_billing_city": clean(crm.get("billing_city")),
        "crm_billing_state": clean(crm.get("billing_state")),
        "crm_billing_zip": crm_zip,
        "score": score,
        "city_state_match": True,
        "zip_match": zip_match,
        "zip_conflict": zip_conflict,
        "street_similarity": round(street_sim, 3),
        "name_similarity": round(name_sim, 3),
        "candidate_class": candidate_class,
        "suggested_action": suggested_action,
        "warnings": warnings,
    }


def account_pair_duplicate_reason(a: pd.Series, b: pd.Series) -> str | None:
    same_city = normalize(a.get("billing_city")) == normalize(b.get("billing_city"))
    same_state = normalize(a.get("billing_state")) == normalize(b.get("billing_state"))
    if not (same_city and same_state):
        return None

    name_sim = similarity(a.get("name"), b.get("name"))
    zip_a, zip_b = normalize_zip(a.get("billing_zip")), normalize_zip(b.get("billing_zip"))
    street_sim = street_score(a.get("billing_street"), b.get("billing_street"))
    same_zip = bool(zip_a and zip_b and zip_a == zip_b)

    if name_sim >= 0.92 and (same_zip or street_sim >= 0.82):
        return "Very similar account names with matching ZIP or street address"
    if name_sim >= 0.78 and same_zip and street_sim >= 0.78:
        return "Similar account names and highly similar location details"
    return None


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def main() -> None:
    if not WEBSITE_FILE.exists() or not CRM_FILE.exists():
        raise FileNotFoundError(
            "Input CSVs not found. Place bellhaven_facilities.csv and crm_accounts.csv "
            "inside the project's data/ folder."
        )

    website_df = pd.read_csv(WEBSITE_FILE, dtype=str).fillna("")
    crm_df = pd.read_csv(CRM_FILE, dtype=str).fillna("")

    required_web = {"name", "address", "city", "state", "zip", "source_url"}
    required_crm = {"account_id", "name", "parent_id", "parent_name", "billing_street",
                    "billing_city", "billing_state", "billing_zip", "status",
                    "lifetime_revenue", "outstanding_ar"}
    missing_web = required_web - set(website_df.columns)
    missing_crm = required_crm - set(crm_df.columns)
    if missing_web or missing_crm:
        raise ValueError(f"Missing columns. Website: {sorted(missing_web)}; CRM: {sorted(missing_crm)}")

    proposal_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    candidate_account_ids: set[str] = set()

    for _, website in website_df.iterrows():
        candidates = []
        for _, crm in crm_df.iterrows():
            candidate = get_candidate(website, crm)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda item: item["score"], reverse=True)
        top = candidates[:3]
        for rank, candidate in enumerate(top, start=1):
            candidate_account_ids.add(candidate["crm_account_id"])
            candidate_rows.append({
                "website_name": website["name"],
                "website_address": website["address"],
                "website_city": website["city"],
                "website_state": website["state"],
                "website_zip": normalize_zip(website["zip"]),
                "source_url": website["source_url"],
                "candidate_rank": rank,
                **candidate,
            })

        if not top:
            status = "NO_CRM_CANDIDATE"
            reason = "No CRM account found in the same city and state; create only after human verification."
            best = {}
        else:
            best = top[0]
            second_score = top[1]["score"] if len(top) > 1 else None
            close_competitor = second_score is not None and (best["score"] - second_score) < 8
            if close_competitor:
                status = "AMBIGUOUS_REVIEW"
                reason = "Multiple CRM candidates have similar scores; compare all candidates before deciding."
            elif best["candidate_class"] == "STRONG_CANDIDATE_REQUIRES_APPROVAL":
                status = best["suggested_action"]
                reason = "Strong location/name candidate only. Verify ownership and financial safeguards before any CRM change."
            elif best["candidate_class"] == "POSSIBLE_CANDIDATE_REVIEW":
                status = "POSSIBLE_MATCH_REVIEW"
                reason = "Potential location match, but evidence is not strong enough for an automated decision."
            else:
                status = "WEAK_MATCH_REVIEW"
                reason = "Only weak candidates found; do not create or re-parent without manual investigation."

        proposal_rows.append({
            "website_name": website["name"],
            "website_address": website["address"],
            "website_city": website["city"],
            "website_state": website["state"],
            "website_zip": normalize_zip(website["zip"]),
            "care_offerings": website.get("care_offerings", ""),
            "source_url": website["source_url"],
            "match_status": status,
            "top_candidate_account_id": best.get("crm_account_id", ""),
            "top_candidate_name": best.get("crm_name", ""),
            "top_candidate_parent_id": best.get("crm_parent_id", ""),
            "top_candidate_parent_name": best.get("crm_parent_name", ""),
            "top_candidate_score": best.get("score", ""),
            "top_candidate_revenue": best.get("lifetime_revenue", ""),
            "top_candidate_outstanding_ar": best.get("outstanding_ar", ""),
            "ownership_path_if_parent_change_is_confirmed": best.get("ownership_path_if_parent_change_is_confirmed", ""),
            "top_three_candidates_json": safe_json(top),
            "review_reason": reason,
        })

    # Only accounts under Bellhaven are considered for this review queue. Never label as obsolete.
    potential_stale = []
    duplicate_account_ids: set[str] = set()
    for i, j in combinations(range(len(crm_df)), 2):
        a, b = crm_df.iloc[i], crm_df.iloc[j]
        duplicate_reason = account_pair_duplicate_reason(a, b)
        if duplicate_reason:
            duplicate_account_ids.update([clean(a["account_id"]), clean(b["account_id"])])

    for _, crm in crm_df.iterrows():
        account_id = clean(crm.get("account_id"))
        if clean(crm.get("parent_id")) != BELLHAVEN_PARENT_ID:
            continue
        if account_id in candidate_account_ids:
            continue
        potential_stale.append({
            "account_id": account_id,
            "name": clean(crm.get("name")),
            "parent_id": clean(crm.get("parent_id")),
            "parent_name": clean(crm.get("parent_name")),
            "billing_street": clean(crm.get("billing_street")),
            "billing_city": clean(crm.get("billing_city")),
            "billing_state": clean(crm.get("billing_state")),
            "billing_zip": normalize_zip(crm.get("billing_zip")),
            "lifetime_revenue": clean(crm.get("lifetime_revenue")),
            "outstanding_ar": clean(crm.get("outstanding_ar")),
            "review_status": "POTENTIALLY_STALE_REVIEW",
            "review_reason": "Not selected as a top-three candidate for a current website facility. This is not proof the account is obsolete.",
            "duplicate_pair_review": account_id in duplicate_account_ids,
        })

    duplicate_rows = []
    for i, j in combinations(range(len(crm_df)), 2):
        a, b = crm_df.iloc[i], crm_df.iloc[j]
        reason = account_pair_duplicate_reason(a, b)
        if reason:
            duplicate_rows.append({
                "account_id_1": clean(a.get("account_id")),
                "account_name_1": clean(a.get("name")),
                "parent_id_1": clean(a.get("parent_id")),
                "status_1": clean(a.get("status")),
                "revenue_1": clean(a.get("lifetime_revenue")),
                "ar_1": clean(a.get("outstanding_ar")),
                "account_id_2": clean(b.get("account_id")),
                "account_name_2": clean(b.get("name")),
                "parent_id_2": clean(b.get("parent_id")),
                "status_2": clean(b.get("status")),
                "revenue_2": clean(b.get("lifetime_revenue")),
                "ar_2": clean(b.get("outstanding_ar")),
                "city": clean(a.get("billing_city")),
                "state": clean(a.get("billing_state")),
                "street_similarity": round(street_score(a.get("billing_street"), b.get("billing_street")), 3),
                "reason": reason,
                "decision": "HUMAN_REVIEW_REQUIRED_NO_AUTO_SURVIVOR",
            })

    proposals_df = pd.DataFrame(proposal_rows)
    candidates_df = pd.DataFrame(candidate_rows)
    stale_df = pd.DataFrame(potential_stale)
    duplicates_df = pd.DataFrame(duplicate_rows)

    outputs = {
        "matching_proposals.csv": proposals_df,
        "matching_candidates_top3.csv": candidates_df,
        "crm_potentially_stale_review.csv": stale_df,
        "crm_duplicate_candidates.csv": duplicates_df,
    }
    for filename, frame in outputs.items():
        frame.to_csv(OUTPUT_DIR / filename, index=False, encoding="utf-8-sig")

    (OUTPUT_DIR / "matching_proposals.json").write_text(
        json.dumps(proposal_rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print("\n=== BELLHAVEN MATCHING REVIEW SUMMARY ===")
    print(f"Website facilities: {len(website_df)}")
    print(f"CRM accounts: {len(crm_df)}")
    if not proposals_df.empty:
        print("\nProposal classifications:")
        print(proposals_df["match_status"].value_counts().to_string())
    print(f"\nTop-three candidate rows: {len(candidates_df)}")
    print(f"Potentially stale review rows: {len(stale_df)}")
    print(f"Duplicate candidate pairs: {len(duplicates_df)}")
    print("\nFiles written:")
    for filename in [*outputs.keys(), "matching_proposals.json"]:
        print(f" - {OUTPUT_DIR / filename}")
    print("\nIMPORTANT: Review outputs only. No CRM API writes were performed.")


if __name__ == "__main__":
    main()
