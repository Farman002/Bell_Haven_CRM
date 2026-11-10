import json
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from crm_client import CRMClient, CRMError
from approvals import init_db, has_decision, save_decision, record_execution, get_decisions, get_audit
from chow_workflow import execute_chow
from reconciliation import (
    BELLHAVEN_PARENT_ID, proposal_key, parse_candidates,
    classify_parent_change, build_new_account_payload, safe_number
)

load_dotenv()
st.set_page_config(page_title="Bellhaven CRM Reconciliation", page_icon="🏥", layout="wide")
init_db()

DATA = "data"
PROPOSALS = f"{DATA}/matching_proposals.csv"
CANDIDATES = f"{DATA}/matching_candidates_top3.csv"
STALE = f"{DATA}/crm_potentially_stale_review.csv"
DUPES = f"{DATA}/crm_duplicate_candidates.csv"
ACCOUNTS = f"{DATA}/crm_accounts.csv"

st.title("Bellhaven Senior Living — CRM Reconciliation")
st.caption("Human-reviewed ownership reconciliation. No CRM changes occur without an explicit approval and execution action.")

def read_csv(path):
    return pd.read_csv(path, dtype=str).fillna("") if os.path.exists(path) else pd.DataFrame()

proposals = read_csv(PROPOSALS)
candidates = read_csv(CANDIDATES)
stale = read_csv(STALE)
dupes = read_csv(DUPES)
accounts = read_csv(ACCOUNTS)

def crm_client():
    try:
        return CRMClient(), None
    except CRMError as e:
        return None, str(e)

def show_metric(label, value):
    st.metric(label, value)

with st.sidebar:
    st.header("Review controls")
    actor = st.text_input("Reviewer name / initials", value=os.getenv("REVIEWER_NAME", "Reviewer"))
    st.warning("CRM write operations are live. Only click Execute after checking the proposed changes.")
    st.caption("The app records decisions and API responses in data/reconciliation_review.db.")

tabs = st.tabs(["Dashboard", "Facility matching", "Ownership & CHOW", "New accounts", "Duplicates", "Stale accounts", "Decision & audit log"])

with tabs[0]:
    st.subheader("Reconciliation overview")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Website facilities", len(proposals))
    c2.metric("CRM accounts (snapshot)", len(accounts))
    c3.metric("Top-three candidate rows", len(candidates))
    c4.metric("Potentially stale", len(stale))
    if not proposals.empty and "match_status" in proposals:
        st.markdown("**Proposal classifications**")
        st.bar_chart(proposals["match_status"].value_counts())
        st.dataframe(proposals[["website_name","website_city","website_state","match_status","top_candidate_name","top_candidate_parent_name","review_reason"]], use_container_width=True, hide_index=True)
    st.info("A match classification is a suggestion, not approval. Confirm current ownership evidence before any CRM write.")

with tabs[1]:
    st.subheader("Facility matching review")
    if proposals.empty:
        st.error(f"Missing {PROPOSALS}. Place the latest matcher output in the data folder.")
    else:
        names = proposals["website_name"].tolist()
        selected_name = st.selectbox("Select facility", names)
        row = proposals[proposals.website_name == selected_name].iloc[0].to_dict()
        st.markdown(f"### {selected_name}")
        a,b = st.columns(2)
        with a:
            st.markdown("**Website evidence**")
            st.write({k: row.get(k,"") for k in ["website_address","website_city","website_state","website_zip","care_offerings","source_url"]})
        with b:
            st.markdown("**Top CRM candidate**")
            st.write({k: row.get(k,"") for k in ["top_candidate_account_id","top_candidate_name","top_candidate_parent_name","top_candidate_score","top_candidate_revenue","top_candidate_outstanding_ar","match_status","review_reason"]})
        facility_candidates = candidates[candidates.website_name == selected_name] if not candidates.empty else pd.DataFrame()
        if not facility_candidates.empty:
            st.markdown("**Candidate comparison**")
            display_cols = [c for c in ["candidate_rank","crm_account_id","crm_name","crm_parent_name","crm_status","crm_billing_street","crm_billing_city","crm_billing_state","crm_billing_zip","score","zip_conflict","street_similarity","name_similarity","suggested_action","warnings"] if c in facility_candidates]
            st.dataframe(facility_candidates[display_cols], use_container_width=True, hide_index=True)
        key = proposal_key(row)
        decided = has_decision(key)
        st.caption(f"Proposal key: {key} · Existing decision: {'Yes' if decided else 'No'}")
        with st.form("match_review_form"):
            action = st.selectbox("Proposed action", ["NO_CHANGE", "DIRECT_REPARENT", "CHOW", "CREATE_NEW_ACCOUNT", "MARK_NEEDS_REVIEW"])
            rationale = st.text_area("Evidence / rationale (required)", placeholder="Record what source or evidence supports this decision.")
            approved = st.checkbox("I have independently verified the facility identity and ownership evidence.")
            submitted = st.form_submit_button("Save approval decision")
        if submitted:
            if not rationale.strip():
                st.error("Enter a rationale before saving.")
            elif not approved:
                st.error("Confirm that you verified the evidence before approving.")
            else:
                save_decision(key, selected_name, action, "APPROVED", actor, rationale, {"facility": row, "candidates": parse_candidates(row)})
                st.success("Decision saved. This does not modify the CRM.")
        if decided:
            st.warning("A decision already exists for this proposal. Review the audit log before making another decision.")

with tabs[2]:
    st.subheader("Ownership corrections and CHOW")
    if proposals.empty:
        st.info("No proposals loaded.")
    else:
        review_rows = proposals[proposals.match_status.str.contains("OWNERSHIP|PARENT|POSSIBLE|AMBIGUOUS|WEAK", case=False, na=False)]
        if review_rows.empty:
            st.info("No ownership-review rows in current proposal file.")
        for _, r in review_rows.iterrows():
            d = r.to_dict()
            name = d.get("website_name","")
            with st.expander(f"{name} — {d.get('match_status','')}"):
                st.write(f"CRM candidate: {d.get('top_candidate_name','')} · Current parent: {d.get('top_candidate_parent_name','')}")
                rev, ar = safe_number(d.get("top_candidate_revenue")), safe_number(d.get("top_candidate_outstanding_ar"))
                route = classify_parent_change(rev, ar)
                st.write(f"Lifetime revenue: {rev:,.2f} | Outstanding AR: {ar:,.2f}")
                if route == "CHOW_REQUIRED":
                    st.error("CHOW REQUIRED: preserve old account, create a new account under Bellhaven, then link old account using chow_current_account.")
                else:
                    st.info("Direct re-parenting may be permitted under the assessment SOP, subject to verification and approval.")
                st.caption(f"Account ID: {d.get('top_candidate_account_id','')}")
                k = proposal_key(d)
                with st.form(f"owner_{k}"):
                    act = st.selectbox("Approved ownership action", ["NO_CHANGE","DIRECT_REPARENT","CHOW","MARK_NEEDS_REVIEW"], key=f"oa_{k}")
                    rat = st.text_input("Approval rationale", key=f"or_{k}")
                    confirm = st.checkbox("Ownership evidence independently verified", key=f"oc_{k}")
                    save = st.form_submit_button("Save ownership decision")
                if save:
                    if not rat.strip() or not confirm:
                        st.error("Rationale and verification confirmation are required.")
                    elif route == "CHOW_REQUIRED" and act == "DIRECT_REPARENT":
                        st.error("Blocked: this record requires CHOW under the assessment SOP.")
                    elif route != "CHOW_REQUIRED" and act == "CHOW":
                        st.warning("CHOW is not mandated by the revenue/AR rule; ensure you have a documented reason.")
                        save_decision(k,name,act,"APPROVED",actor,rat,{"facility":d})
                        st.success("Decision saved; no CRM write performed.")
                    else:
                        save_decision(k,name,act,"APPROVED",actor,rat,{"facility":d})
                        st.success("Decision saved; no CRM write performed.")

with tabs[3]:
    st.subheader("New account review")
    if proposals.empty:
        st.info("No proposals loaded.")
    else:
        new_rows = proposals[proposals.match_status == "NO_CRM_CANDIDATE"]
        if new_rows.empty:
            st.info("No NO_CRM_CANDIDATE facilities.")
        for _, r in new_rows.iterrows():
            d = r.to_dict()
            with st.expander(f"{d.get('website_name')} — {d.get('website_city')}, {d.get('website_state')}"):
                st.write({k:d.get(k,"") for k in ["website_address","website_city","website_state","website_zip","care_offerings","source_url"]})
                key = proposal_key(d)
                with st.form(f"new_{key}"):
                    care = st.selectbox("Care type", ["Assisted Living","Memory Care","Skilled Nursing","Independent Living","Other"], key=f"care_{key}")
                    rationale = st.text_area("Why is a new CRM account appropriate?", key=f"newrat_{key}")
                    verified = st.checkbox("Checked CRM manually and confirmed no existing account", key=f"newver_{key}")
                    submit = st.form_submit_button("Approve new account proposal")
                if submit:
                    if not rationale.strip() or not verified:
                        st.error("Rationale and duplicate-check confirmation are required.")
                    else:
                        payload = build_new_account_payload(d, care_type=care)
                        save_decision(key,d.get("website_name"),"CREATE_NEW_ACCOUNT","APPROVED",actor,rationale, payload)
                        st.success("Approved and saved. Execute it from the approved actions section below.")

with tabs[4]:
    st.subheader("Duplicate account review")
    if dupes.empty:
        st.info("No duplicate candidates.")
    else:
        for _, r in dupes.iterrows():
            d = r.to_dict()
            with st.expander(f"{d.get('account_name_1')} — {d.get('city')}, {d.get('state')}"):
                st.write(d)
                pair_key = f"duplicate:{d.get('account_id_1')}:{d.get('account_id_2')}"
                with st.form(f"dup_{pair_key}"):
                    survivor = st.selectbox("Surviving account", [d.get("account_id_1"),d.get("account_id_2")])
                    rationale = st.text_area("Why is this the surviving record?")
                    verified = st.checkbox("I verified financial and operational records for both accounts.")
                    submit = st.form_submit_button("Approve duplicate resolution")
                if submit:
                    if not rationale.strip() or not verified:
                        st.error("Rationale and verification required.")
                    else:
                        losing = d.get("account_id_2") if survivor == d.get("account_id_1") else d.get("account_id_1")
                        save_decision(pair_key,d.get("account_name_1"),"MARK_DUPLICATE_INACTIVE","APPROVED",actor,rationale,
                                      {"survivor_id":survivor,"losing_id":losing})
                        st.success("Decision saved. No CRM write performed.")

with tabs[5]:
    st.subheader("Potentially stale account review")
    if stale.empty:
        st.info("No potentially stale accounts.")
    else:
        st.warning("Not selected as a website match does not prove an account is obsolete. No automatic deactivation is allowed.")
        for _, r in stale.iterrows():
            d = r.to_dict()
            with st.expander(f"{d.get('name')} — {d.get('billing_city')}, {d.get('billing_state')}"):
                st.write(d)
                key = f"stale:{d.get('account_id')}"
                with st.form(f"stale_{key}"):
                    decision = st.selectbox("Review outcome", ["KEEP_ACTIVE","MARK_INACTIVE","NEEDS_MORE_INVESTIGATION"])
                    rationale = st.text_area("Evidence / reason")
                    verified = st.checkbox("I checked operational, billing and ownership records.")
                    submit = st.form_submit_button("Save stale-record decision")
                if submit:
                    if not rationale.strip() or not verified:
                        st.error("Evidence and verification required.")
                    else:
                        save_decision(key,d.get("name"),decision,"APPROVED",actor,rationale,{"account":d})
                        st.success("Decision saved. No CRM write performed.")

with tabs[6]:
    st.subheader("Approved actions — explicit execution")
    decisions = get_decisions()
    approved = [d for d in decisions if d["decision"] == "APPROVED"]
    if not approved:
        st.info("No approved decisions yet.")
    else:
        st.dataframe(pd.DataFrame(approved)[["facility_name","action_type","actor","rationale","execution_status","created_at"]], use_container_width=True, hide_index=True)
        client, err = crm_client()
        if err:
            st.error(err)
        st.error("The next button performs live CRM API writes. Verify the action and target account before executing.")
        st.warning("CHOW is resumable: the replacement account ID is persisted after creation. If linking fails, retry resumes the link step instead of blindly creating another account. The POST/PATCH schema is not published by this API, so inspect the first API response and CRM browser carefully.")
        pending = [d for d in approved if d["execution_status"] in ["NOT_EXECUTED", "FAILED"] and d["action_type"] not in ["NO_CHANGE","MARK_NEEDS_REVIEW","KEEP_ACTIVE","NEEDS_MORE_INVESTIGATION"]]
        if pending and client:
            options = {f'{d["facility_name"]} | {d["action_type"]} | {d["proposal_key"][:8]}':d for d in pending}
            selected_label = st.selectbox("Select one approved action to execute", list(options))
            item = options[selected_label]
            payload = json.loads(item["proposed_payload"] or "{}")
            st.json(payload)
            phrase = st.text_input('Type EXECUTE to enable the live write')
            if st.button("Execute selected CRM action", type="primary", disabled=(phrase != "EXECUTE")):
                try:
                    action = item["action_type"]
                    before, after, api_result = {}, {}, {}
                    if action == "DIRECT_REPARENT":
                        facility = payload.get("facility", {})
                        account_id = facility.get("top_candidate_account_id")
                        if not account_id:
                            raise CRMError("Missing CRM account ID in saved proposal.")
                        current = client.get_account(account_id)
                        rev = safe_number(current.get("lifetime_revenue"))
                        ar = safe_number(current.get("outstanding_ar"))
                        if rev > 0 and ar > 0:
                            raise CRMError("Safety block: account has both revenue and AR; CHOW is required.")
                        if str(current.get("parent_id", "")) == BELLHAVEN_PARENT_ID:
                            raise CRMError("This account is already under the Bellhaven parent; no re-parenting is needed.")
                        before = current
                        api_result = client.patch_account(account_id, {"parent_id": BELLHAVEN_PARENT_ID})
                        after = client.get_account(account_id)
                    elif action == "CHOW":
                        facility = payload.get("facility", {})
                        old_id = facility.get("top_candidate_account_id")
                        if not old_id:
                            raise CRMError("Missing old CRM account ID in approved decision.")
                        result = execute_chow(client, old_id, facility)
                        before = result.get("old_account_before", {})
                        after = {
                            "old_account": result.get("old_account_after", {}),
                            "new_account": result.get("new_account", {})
                        }
                        api_result = result
                    elif action == "CREATE_NEW_ACCOUNT":
                        api_result = client.create_account(payload)
                        after = api_result
                    elif action == "MARK_DUPLICATE_INACTIVE":
                        survivor, losing = payload.get("survivor_id"), payload.get("losing_id")
                        if not survivor or not losing or survivor == losing:
                            raise CRMError("Invalid survivor/losing account selection.")
                        before = client.get_account(losing)
                        if safe_number(before.get("lifetime_revenue")) > 0 or safe_number(before.get("outstanding_ar")) > 0:
                            raise CRMError("Safety block: do not mark duplicate inactive while it has revenue or AR. Resolve financial records first.")
                        api_result = client.patch_account(losing, {"duplicate_of_account":survivor,"status":"Inactive"})
                        after = client.get_account(losing)
                    elif action == "MARK_INACTIVE":
                        account = payload.get("account", {})
                        account_id = account.get("account_id")
                        if not account_id:
                            raise CRMError("Missing stale account ID.")
                        before = client.get_account(account_id)
                        if safe_number(before.get("lifetime_revenue")) > 0 or safe_number(before.get("outstanding_ar")) > 0:
                            raise CRMError("Safety block: account has revenue or AR; investigate before deactivation.")
                        api_result = client.patch_account(account_id, {"status":"Inactive"})
                        after = client.get_account(account_id)
                    else:
                        raise CRMError(f"Unsupported action type: {action}")
                    record_execution(item["proposal_key"],before,after,api_result,"SUCCESS",actor)
                    st.success("CRM API operation completed and audit record saved. Refresh the page.")
                    st.json({"api_response":api_result,"after":after})
                except Exception as exc:
                    record_execution(item["proposal_key"],{}, {}, {"error":str(exc)},"FAILED",actor)
                    st.error(f"Execution failed: {exc}")
        else:
            st.caption("No executable approved actions are pending.")

    st.divider()
    st.markdown("**Decision history**")
    if decisions:
        st.dataframe(pd.DataFrame(decisions), use_container_width=True, hide_index=True)
    st.markdown("**Audit events**")
    audit = get_audit()
    if audit:
        st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)
