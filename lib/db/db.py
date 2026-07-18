"""
Connection handling and per-table query helpers for the audit webhook.

Hosted-only: this always connects to Postgres (Supabase) via SUPABASE_DB_URL.
There is no local SQLite fallback here (unlike the original seo-agent
project this was copied from) since this code only ever runs as a deployed
Vercel function, never in local dev without a real database.
"""
import os

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "").strip()
PLACEHOLDER = "%s"


def get_connection():
    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL is not set")
    return psycopg2.connect(SUPABASE_DB_URL, cursor_factory=RealDictCursor)


# --- generic helpers, used by the per-table wrappers below ---

def _insert(table, fields):
    columns = list(fields.keys())
    col_sql = ", ".join(columns)
    placeholder_sql = ", ".join([PLACEHOLDER] * len(columns))
    values = [fields[c] for c in columns]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO {table} ({col_sql}) VALUES ({placeholder_sql}) RETURNING id", values)
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        conn.close()


def _get_by_id(table, row_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table} WHERE id = {PLACEHOLDER}", (row_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_by_column(table, column, value, order_by="id"):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table} WHERE {column} = {PLACEHOLDER} ORDER BY {order_by}", (value,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _update_fields(table, row_id, fields):
    set_sql = ", ".join(f"{c} = {PLACEHOLDER}" for c in fields)
    values = list(fields.values()) + [row_id]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE {table} SET {set_sql} WHERE id = {PLACEHOLDER}", values)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# --- partners ---

def insert_partner(**fields):
    return _insert("partners", fields)


def get_partner_by_id(partner_id):
    return _get_by_id("partners", partner_id)


def update_partner_status(partner_id, status):
    return _update_fields("partners", partner_id, {"status": status})


# --- clients ---

def insert_client(**fields):
    return _insert("clients", fields)


def get_client_by_id(client_id):
    return _get_by_id("clients", client_id)


def get_clients_by_partner_id(partner_id):
    return _get_by_column("clients", "partner_id", partner_id)


def get_all_clients():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clients ORDER BY business_name")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def update_client_status(client_id, status):
    return _update_fields("clients", client_id, {"status": status})


# --- gbp_credentials ---

def insert_gbp_credentials(**fields):
    return _insert("gbp_credentials", fields)


def get_gbp_credentials_by_id(credentials_id):
    return _get_by_id("gbp_credentials", credentials_id)


def get_gbp_credentials_by_client_id(client_id):
    return _get_by_column("gbp_credentials", "client_id", client_id)


# --- tasks ---

def insert_task(**fields):
    return _insert("tasks", fields)


def get_task_by_id(task_id):
    return _get_by_id("tasks", task_id)


def get_tasks_by_client_id(client_id):
    return _get_by_column("tasks", "client_id", client_id)


def get_tasks_by_status(status):
    return _get_by_column("tasks", "status", status)


def update_task_status(task_id, status, completed_at=None):
    fields = {"status": status}
    if completed_at is not None:
        fields["completed_at"] = completed_at
    return _update_fields("tasks", task_id, fields)


# --- task_outputs ---

def insert_task_output(**fields):
    return _insert("task_outputs", fields)


def get_task_output_by_id(task_output_id):
    return _get_by_id("task_outputs", task_output_id)


def get_task_outputs_by_task_id(task_id):
    return _get_by_column("task_outputs", "task_id", task_id)


def update_task_output(task_output_id, **fields):
    return _update_fields("task_outputs", task_output_id, fields)


# --- reviews ---

def insert_review(**fields):
    return _insert("reviews", fields)


def get_review_by_id(review_id):
    return _get_by_id("reviews", review_id)


def get_reviews_by_client_id(client_id):
    return _get_by_column("reviews", "client_id", client_id)


def update_review_response_status(review_id, response_status, responded_at=None):
    fields = {"response_status": response_status}
    if responded_at is not None:
        fields["responded_at"] = responded_at
    return _update_fields("reviews", review_id, fields)


def update_review_response_draft(review_id, response_draft):
    return _update_fields("reviews", review_id, {"response_draft": response_draft})


# --- keywords ---

def add_keyword(client_id, keyword, priority=3):
    return _insert("keywords", {"client_id": client_id, "keyword": keyword, "priority": priority})


def get_active_keywords(client_id):
    keywords = _get_by_column("keywords", "client_id", client_id)
    return [k for k in keywords if k["active"]]


def deactivate_keyword(keyword_id):
    return _update_fields("keywords", keyword_id, {"active": False})


# --- citations ---

def insert_citation_check(client_id, source, found_name, found_address, found_phone, match_status):
    return _insert(
        "citations",
        {
            "client_id": client_id,
            "source": source,
            "found_name": found_name,
            "found_address": found_address,
            "found_phone": found_phone,
            "match_status": match_status,
        },
    )


def get_latest_citations(client_id):
    checks = _get_by_column("citations", "client_id", client_id)
    latest_by_source = {}
    for check in checks:
        latest_by_source[check["source"]] = check
    return list(latest_by_source.values())


# --- rankings ---

def insert_ranking(**fields):
    return _insert("rankings", fields)


def get_ranking_by_id(ranking_id):
    return _get_by_id("rankings", ranking_id)


def get_rankings_by_client_id(client_id):
    return _get_by_column("rankings", "client_id", client_id)


# --- reports ---

def insert_report(**fields):
    return _insert("reports", fields)


def get_report_by_id(report_id):
    return _get_by_id("reports", report_id)


def get_reports_by_client_id(client_id):
    return _get_by_column("reports", "client_id", client_id)


def get_reports_by_status(status):
    return _get_by_column("reports", "status", status)


def update_report(report_id, **fields):
    return _update_fields("reports", report_id, fields)


# --- prospects ---

def insert_prospect(**fields):
    return _insert("prospects", fields)


def get_prospect_by_id(prospect_id):
    return _get_by_id("prospects", prospect_id)


def update_prospect_status(prospect_id, status):
    return _update_fields("prospects", prospect_id, {"audit_status": status})


def get_prospects_by_status(status):
    return _get_by_column("prospects", "audit_status", status)


def get_pending_prospects():
    return _get_by_column("prospects", "audit_status", "pending")


# --- audits ---

def insert_audit(**fields):
    return _insert("audits", fields)


def get_audits_by_prospect_id(prospect_id):
    return _get_by_column("audits", "prospect_id", prospect_id)


# --- activity_log ---

def insert_activity_log(**fields):
    return _insert("activity_log", fields)


def get_activity_log_by_id(log_id):
    return _get_by_id("activity_log", log_id)


def get_activity_log_by_client_id(client_id):
    return _get_by_column("activity_log", "client_id", client_id)
