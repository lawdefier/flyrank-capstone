"""
Database Seeder for FlyRank Capstone Platform.
Creates initial multi-tenant test accounts, widgets, and sample submissions.
"""

from datetime import datetime, timezone
import json
from src.database import get_db, DB_FILE, init_db


def seed_database():
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cur = conn.cursor()

        # 1. Seed Tenants
        tenants = [
            ("tenant_a", "Acme Corp", "key_tenant_a_123", now),
            ("tenant_b", "Beta Industries", "key_tenant_b_456", now),
        ]
        for t in tenants:
            cur.execute(
                """
                INSERT OR IGNORE INTO tenants (id, name, api_key, created_at)
                VALUES (?, ?, ?, ?)
                """,
                t,
            )

        # 2. Seed Widgets
        widgets = [
            (
                "wid_demo_signup",
                "tenant_a",
                "signup_form",
                "Join Our Weekly Growth Newsletter",
                "Actionable backend & SEO strategies delivered every Monday morning.",
                "Subscribe Now",
                json.dumps([
                    {"name": "name", "type": "text", "label": "Full Name", "placeholder": "Jane Doe", "required": True},
                    {"name": "email", "type": "email", "label": "Email Address", "placeholder": "jane@example.com", "required": True},
                ]),
                json.dumps({
                    "theme": "dark",
                    "position": "center",
                    "accent_color": "#2563eb",
                    "border_radius": "8px"
                }),
                1,
                now,
            ),
            (
                "wid_demo_contact",
                "tenant_a",
                "contact_form",
                "Book an Architecture Consultation",
                "Speak directly with senior backend engineers on scaling systems.",
                "Schedule Call",
                json.dumps([
                    {"name": "name", "type": "text", "label": "Your Name", "placeholder": "Alex Smith", "required": True},
                    {"name": "email", "type": "email", "label": "Work Email", "placeholder": "alex@company.com", "required": True},
                    {"name": "message", "type": "textarea", "label": "Project Scope", "placeholder": "Tell us about your stack and bottlenecks...", "required": True},
                ]),
                json.dumps({
                    "theme": "light",
                    "position": "bottom-right",
                    "accent_color": "#10b981",
                    "border_radius": "10px"
                }),
                1,
                now,
            ),
            (
                "wid_beta_cta",
                "tenant_b",
                "cta_popover",
                "Beta Access VIP Invitation",
                "Get exclusive first access to Beta Industries pipeline tools.",
                "Claim VIP Pass",
                json.dumps([
                    {"name": "email", "type": "email", "label": "Invite Email", "placeholder": "vip@domain.com", "required": True},
                ]),
                json.dumps({
                    "theme": "dark",
                    "position": "center",
                    "accent_color": "#8b5cf6",
                    "border_radius": "8px"
                }),
                1,
                now,
            ),
        ]

        for w in widgets:
            cur.execute(
                """
                INSERT OR IGNORE INTO widgets (id, tenant_id, type, title, description, button_text, fields_json, display_options_json, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                w,
            )

        # 3. Seed Sample Submissions for Tenant A
        sample_submissions = [
            (
                "wid_demo_signup",
                "tenant_a",
                json.dumps({"name": "Alice Martin", "email": "alice@startup.io"}),
                "203.0.113.195",
                "United States",
                "San Jose",
                "provider_a",
                0,
                "sent",
                now,
            ),
            (
                "wid_demo_contact",
                "tenant_a",
                json.dumps({"name": "David Becker", "email": "david@fintech.de", "message": "Migrating to microservices, need audit."}),
                "198.51.100.42",
                "Germany",
                "Frankfurt",
                "provider_a",
                0,
                "sent",
                now,
            ),
            (
                "wid_demo_signup",
                "tenant_a",
                json.dumps({"name": "Bot Spammer", "email": "spam@bot.net"}),
                "192.0.2.1",
                "Unknown",
                "Unknown",
                "none",
                1,  # Honeypot tripped
                "none",
                now,
            ),
        ]

        # Insert only if submissions table empty
        cur.execute("SELECT COUNT(*) FROM submissions")
        if cur.fetchone()[0] == 0:
            for s in sample_submissions:
                cur.execute(
                    """
                    INSERT INTO submissions (widget_id, tenant_id, payload_json, visitor_ip, country, city, geo_provider, is_spam, side_effect_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    s,
                )

        conn.commit()
    print("Database successfully seeded with tenants, widgets, and sample submissions.")


if __name__ == "__main__":
    seed_database()
