"""
Database Module for SQLite persistence with multi-tenant isolation and indexing.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

DB_FILE = Path(__file__).resolve().parent.parent / "platform.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create schema tables and performance indexes."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Tenants table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                api_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)

        # Widgets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS widgets (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                button_text TEXT NOT NULL,
                fields_json TEXT NOT NULL,
                display_options_json TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        """)

        # Submissions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                widget_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                visitor_ip TEXT NOT NULL,
                country TEXT,
                city TEXT,
                geo_provider TEXT,
                is_spam BOOLEAN NOT NULL DEFAULT 0,
                side_effect_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (widget_id) REFERENCES widgets(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        """)

        # Indexes for query performance & multi-tenant isolation
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_widgets_tenant ON widgets(tenant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_tenant ON submissions(tenant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_widget ON submissions(widget_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);")

        conn.commit()


# Run schema init on import
init_db()


# ──────────────────────────────────────────────
# Tenant & Auth Database Helpers
# ──────────────────────────────────────────────

def get_tenant_by_api_key(api_key: str) -> Optional[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, api_key, created_at FROM tenants WHERE api_key = ?", (api_key,))
        row = cur.fetchone()
        return dict(row) if row else None


# ──────────────────────────────────────────────
# Widget CRUD (Tenant Isolated)
# ──────────────────────────────────────────────

def create_widget(
    tenant_id: str,
    widget_id: str,
    type_: str,
    title: str,
    description: str,
    button_text: str,
    fields: list,
    display_options: dict,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO widgets (id, tenant_id, type, title, description, button_text, fields_json, display_options_json, version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (widget_id, tenant_id, type_, title, description, button_text, json.dumps(fields), json.dumps(display_options), now),
        )
        conn.commit()
    return get_widget_by_id(widget_id, tenant_id=tenant_id)


def get_widget_by_id(widget_id: str, tenant_id: Optional[str] = None) -> Optional[dict]:
    """Retrieve widget. If tenant_id provided, enforces tenant isolation."""
    with get_db() as conn:
        cur = conn.cursor()
        if tenant_id:
            cur.execute("SELECT * FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant_id))
        else:
            cur.execute("SELECT * FROM widgets WHERE id = ?", (widget_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["fields"] = json.loads(d["fields_json"])
        d["display_options"] = json.loads(d["display_options_json"])
        return d


def list_widgets_by_tenant(tenant_id: str) -> List[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM widgets WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,))
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["fields"] = json.loads(d["fields_json"])
            d["display_options"] = json.loads(d["display_options_json"])
            result.append(d)
        return result


def update_widget(widget_id: str, tenant_id: str, updates: dict) -> Optional[dict]:
    existing = get_widget_by_id(widget_id, tenant_id=tenant_id)
    if not existing:
        return None

    title = updates.get("title") or existing["title"]
    desc = updates.get("description") if updates.get("description") is not None else existing["description"]
    btn = updates.get("button_text") or existing["button_text"]
    disp = json.dumps(updates.get("display_options")) if updates.get("display_options") else existing["display_options_json"]
    new_version = existing["version"] + 1

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE widgets
            SET title = ?, description = ?, button_text = ?, display_options_json = ?, version = ?
            WHERE id = ? AND tenant_id = ?
            """,
            (title, desc, btn, disp, new_version, widget_id, tenant_id),
        )
        conn.commit()
    return get_widget_by_id(widget_id, tenant_id=tenant_id)


def delete_widget(widget_id: str, tenant_id: str) -> bool:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant_id))
        conn.commit()
        return cur.rowcount > 0


# ──────────────────────────────────────────────
# Submissions & Analytics
# ──────────────────────────────────────────────

def insert_submission(
    widget_id: str,
    tenant_id: str,
    payload: dict,
    visitor_ip: str,
    country: Optional[str],
    city: Optional[str],
    geo_provider: Optional[str],
    is_spam: bool,
    side_effect_status: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO submissions (widget_id, tenant_id, payload_json, visitor_ip, country, city, geo_provider, is_spam, side_effect_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (widget_id, tenant_id, json.dumps(payload), visitor_ip, country, city, geo_provider, 1 if is_spam else 0, side_effect_status, now),
        )
        new_id = cur.lastrowid
        conn.commit()

    return {
        "id": new_id,
        "widget_id": widget_id,
        "tenant_id": tenant_id,
        "data": payload,
        "visitor_ip": visitor_ip,
        "country": country,
        "city": city,
        "geo_provider": geo_provider,
        "side_effect_status": side_effect_status,
        "created_at": now,
    }


def get_dashboard_metrics(tenant_id: str) -> dict:
    with get_db() as conn:
        cur = conn.cursor()

        # Total valid submissions
        cur.execute("SELECT COUNT(*) FROM submissions WHERE tenant_id = ? AND is_spam = 0", (tenant_id,))
        total = cur.fetchone()[0]

        # Total spam blocked
        cur.execute("SELECT COUNT(*) FROM submissions WHERE tenant_id = ? AND is_spam = 1", (tenant_id,))
        spam_count = cur.fetchone()[0]

        # Submissions by widget
        cur.execute(
            """
            SELECT widget_id, COUNT(*) as cnt
            FROM submissions
            WHERE tenant_id = ? AND is_spam = 0
            GROUP BY widget_id
            """,
            (tenant_id,),
        )
        by_widget = {r["widget_id"]: r["cnt"] for r in cur.fetchall()}

        # Submissions by country
        cur.execute(
            """
            SELECT COALESCE(country, 'Unknown') as country, COUNT(*) as cnt
            FROM submissions
            WHERE tenant_id = ? AND is_spam = 0
            GROUP BY country
            """,
            (tenant_id,),
        )
        by_country = {r["country"]: r["cnt"] for r in cur.fetchall()}

        # Recent 20 submissions
        cur.execute(
            """
            SELECT * FROM submissions
            WHERE tenant_id = ? AND is_spam = 0
            ORDER BY id DESC LIMIT 20
            """,
            (tenant_id,),
        )
        recent = []
        for r in cur.fetchall():
            recent.append({
                "id": r["id"],
                "widget_id": r["widget_id"],
                "tenant_id": r["tenant_id"],
                "data": json.loads(r["payload_json"]),
                "visitor_ip": r["visitor_ip"],
                "country": r["country"],
                "city": r["city"],
                "geo_provider": r["geo_provider"],
                "side_effect_status": r["side_effect_status"],
                "created_at": r["created_at"],
            })

    return {
        "tenant_id": tenant_id,
        "total_submissions": total,
        "submissions_by_widget": by_widget,
        "submissions_by_country": by_country,
        "spam_blocked": spam_count,
        "recent_submissions": recent,
    }
