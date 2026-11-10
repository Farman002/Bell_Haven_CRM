import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/reconciliation_review.db")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_key TEXT NOT NULL UNIQUE,
            facility_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            decision TEXT NOT NULL,
            actor TEXT NOT NULL,
            rationale TEXT,
            proposed_payload TEXT,
            before_state TEXT,
            after_state TEXT,
            api_response TEXT,
            execution_status TEXT NOT NULL DEFAULT 'NOT_EXECUTED',
            created_at TEXT NOT NULL,
            executed_at TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_key TEXT NOT NULL,
            event TEXT NOT NULL,
            details TEXT,
            actor TEXT,
            created_at TEXT NOT NULL
        )
        """)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def has_decision(proposal_key):
    with connect() as con:
        return con.execute("SELECT 1 FROM decisions WHERE proposal_key=?", (proposal_key,)).fetchone() is not None

def save_decision(proposal_key, facility_name, action_type, decision, actor, rationale, payload):
    with connect() as con:
        con.execute("""
        INSERT INTO decisions
        (proposal_key, facility_name, action_type, decision, actor, rationale, proposed_payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(proposal_key) DO UPDATE SET
          decision=excluded.decision, actor=excluded.actor, rationale=excluded.rationale,
          proposed_payload=excluded.proposed_payload, created_at=excluded.created_at
        """, (proposal_key, facility_name, action_type, decision, actor, rationale,
              json.dumps(payload, default=str), utc_now()))
        con.execute("INSERT INTO audit_log(proposal_key,event,details,actor,created_at) VALUES(?,?,?,?,?)",
                    (proposal_key, "DECISION_RECORDED", json.dumps({"decision":decision,"action":action_type}), actor, utc_now()))

def record_execution(proposal_key, before_state, after_state, api_response, status, actor):
    with connect() as con:
        con.execute("""
        UPDATE decisions SET before_state=?, after_state=?, api_response=?,
          execution_status=?, executed_at=? WHERE proposal_key=?
        """, (json.dumps(before_state, default=str), json.dumps(after_state, default=str),
              json.dumps(api_response, default=str), status, utc_now(), proposal_key))
        con.execute("INSERT INTO audit_log(proposal_key,event,details,actor,created_at) VALUES(?,?,?,?,?)",
                    (proposal_key, "CRM_WRITE_"+status, json.dumps(api_response, default=str), actor, utc_now()))

def get_decisions():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM decisions ORDER BY id DESC").fetchall()]

def get_audit():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM audit_log ORDER BY id DESC").fetchall()]


def init_chow_table():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS chow_workflows (
            old_account_id TEXT PRIMARY KEY,
            facility_name TEXT NOT NULL,
            new_account_id TEXT,
            create_response TEXT,
            link_response TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING_CREATE',
            last_error TEXT,
            updated_at TEXT NOT NULL
        )
        """)

def get_chow_workflow(old_account_id):
    init_chow_table()
    with connect() as con:
        row = con.execute(
            "SELECT * FROM chow_workflows WHERE old_account_id=?",
            (old_account_id,)
        ).fetchone()
        return dict(row) if row else None

def save_chow_created(old_account_id, facility_name, new_account_id, create_response):
    init_chow_table()
    with connect() as con:
        con.execute("""
        INSERT INTO chow_workflows
        (old_account_id, facility_name, new_account_id, create_response, status, last_error, updated_at)
        VALUES (?, ?, ?, ?, 'NEW_ACCOUNT_CREATED', NULL, ?)
        ON CONFLICT(old_account_id) DO UPDATE SET
          new_account_id=excluded.new_account_id,
          create_response=excluded.create_response,
          status='NEW_ACCOUNT_CREATED',
          last_error=NULL,
          updated_at=excluded.updated_at
        """, (old_account_id, facility_name, new_account_id,
              json.dumps(create_response, default=str), utc_now()))

def save_chow_linked(old_account_id, link_response):
    init_chow_table()
    with connect() as con:
        con.execute("""
        UPDATE chow_workflows SET link_response=?, status='COMPLETED',
        last_error=NULL, updated_at=? WHERE old_account_id=?
        """, (json.dumps(link_response, default=str), utc_now(), old_account_id))

def save_chow_error(old_account_id, facility_name, error):
    init_chow_table()
    with connect() as con:
        con.execute("""
        INSERT INTO chow_workflows
        (old_account_id, facility_name, status, last_error, updated_at)
        VALUES (?, ?, 'FAILED_REVIEW', ?, ?)
        ON CONFLICT(old_account_id) DO UPDATE SET
          status='FAILED_REVIEW', last_error=excluded.last_error,
          updated_at=excluded.updated_at
        """, (old_account_id, facility_name, str(error), utc_now()))
