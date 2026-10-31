"""
Automated Test Suite for FlyRank Capstone Platform.
Verifies all 6 acceptance probes from Section 13 of the specification:
  - Probe 1: Valid submission from second origin (CORS + dashboard visibility)
  - Probe 2: Malformed / oversized payload validation (4xx JSON, never 500)
  - Probe 3: Rapid burst rate limiting (429 status code + Retry-After)
  - Probe 4: Geolocation fallback chain (Provider A -> Provider B -> degradation)
  - Probe 5: Secondary side effect failure containment (Safe failure, 201 Created)
  - Probe 6: Honeypot anti-spam defense (400 rejection, flagged in DB, no side effect)
  - Multi-tenant isolation verification.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.rate_limiter import reset_rate_limiter
from src.geo import set_provider_a_status, set_provider_b_status
from src.side_effects import set_email_side_effect_status
from src.seed import seed_database

client = TestClient(app)

TENANT_A_KEY = "key_tenant_a_123"
TENANT_B_KEY = "key_tenant_b_456"


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Reset rate limiters, provider failure flags, and ensure seeded state."""
    seed_database()
    reset_rate_limiter()
    set_provider_a_status(False)
    set_provider_b_status(False)
    set_email_side_effect_status(False)
    yield
    reset_rate_limiter()
    set_provider_a_status(False)
    set_provider_b_status(False)
    set_email_side_effect_status(False)


# ──────────────────────────────────────────────
# PROBE 1: Valid Submission from Second Origin
# ──────────────────────────────────────────────
def test_probe_1_valid_submission_cross_origin_and_dashboard():
    # 1. Check embed script static delivery & caching header
    script_resp = client.get("/static/widget.v1.js")
    assert script_resp.status_code == 200
    assert "public, max-age=31536000, immutable" in script_resp.headers.get("cache-control", "")
    assert script_resp.headers.get("access-control-allow-origin") == "*"

    # 2. Check widget config endpoint & 60s cache header
    config_resp = client.get(
        "/widgets/wid_demo_signup/config",
        headers={"Origin": "https://customer-blog.example.com"},
    )
    assert config_resp.status_code == 200
    assert "public, max-age=60" in config_resp.headers.get("cache-control", "")
    assert config_resp.headers.get("access-control-allow-origin") in ("*", "https://customer-blog.example.com")
    config = config_resp.json()
    assert config["id"] == "wid_demo_signup"
    assert config["button_text"] == "Subscribe Now"

    # 3. Submit from simulated second origin
    payload = {
        "widget_id": "wid_demo_signup",
        "data": {
            "name": "Sarah Connor",
            "email": "sarah@cyberdyne.org",
        },
    }
    submit_resp = client.post(
        "/submissions",
        json=payload,
        headers={"Origin": "https://customer-blog.example.com"},
    )
    assert submit_resp.status_code == 201
    res_data = submit_resp.json()
    assert res_data["status"] == "received"
    assert "id" in res_data
    sub_id = res_data["id"]

    # 4. Verify record appears in Tenant A's authenticated dashboard
    dash_resp = client.get("/dashboard/stats", headers={"X-API-Key": TENANT_A_KEY})
    assert dash_resp.status_code == 200
    stats = dash_resp.json()
    assert stats["total_submissions"] >= 1
    assert "wid_demo_signup" in stats["submissions_by_widget"]
    recent_ids = [s["id"] for s in stats["recent_submissions"]]
    assert sub_id in recent_ids


# ──────────────────────────────────────────────
# PROBE 2: Malformed or Oversized Payloads
# ──────────────────────────────────────────────
def test_probe_2_malformed_and_oversized_payloads():
    # 1. Empty request body
    resp_empty = client.post("/submissions", json={})
    assert resp_empty.status_code in (400, 422)
    assert resp_empty.status_code != 500

    # 2. Empty data dictionary
    resp_no_data = client.post(
        "/submissions",
        json={"widget_id": "wid_demo_signup", "data": {}},
    )
    assert resp_no_data.status_code in (400, 422)
    assert resp_no_data.status_code != 500

    # 3. Non-existent widget_id
    resp_missing_widget = client.post(
        "/submissions",
        json={"widget_id": "wid_does_not_exist", "data": {"email": "test@test.com"}},
    )
    assert resp_missing_widget.status_code == 404
    assert resp_missing_widget.status_code != 500

    # 4. Oversized payload exceeding 64KB boundary limit
    large_string = "A" * (70 * 1024)  # 70 KB
    resp_oversized = client.post(
        "/submissions",
        json={"widget_id": "wid_demo_signup", "data": {"overflow": large_string}},
    )
    assert resp_oversized.status_code in (413, 422)
    assert resp_oversized.status_code != 500


# ──────────────────────────────────────────────
# PROBE 3: Rapid Burst Rate Limiting
# ──────────────────────────────────────────────
def test_probe_3_rapid_burst_rate_limiting():
    # Rate limiter is configured to allow burst of 5 in 3 seconds
    payload = {
        "widget_id": "wid_demo_signup",
        "data": {"name": "Fast Requester", "email": "fast@domain.com"},
    }

    status_codes = []
    # Send 7 rapid requests from same client IP
    for _ in range(7):
        resp = client.post(
            "/submissions",
            json=payload,
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        status_codes.append(resp.status_code)

    # At least one request must be rejected with 429 Too Many Requests
    assert 429 in status_codes

    # Check 429 response structure & Retry-After header
    resp_blocked = client.post(
        "/submissions",
        json=payload,
        headers={"X-Forwarded-For": "198.51.100.99"},
    )
    assert resp_blocked.status_code == 429
    assert "retry-after" in resp_blocked.headers

    # Reset limiter simulates time passing -> next regular submission succeeds
    reset_rate_limiter()
    resp_ok = client.post(
        "/submissions",
        json=payload,
        headers={"X-Forwarded-For": "198.51.100.99"},
    )
    assert resp_ok.status_code == 201


# ──────────────────────────────────────────────
# PROBE 4: Geolocation Fallback Chain
# ──────────────────────────────────────────────
def test_probe_4_geo_fallback_chain():
    payload = {
        "widget_id": "wid_demo_signup",
        "data": {"name": "Geo Tester", "email": "geo@test.com"},
    }

    # Case A: Provider A is healthy
    set_provider_a_status(is_down=False)
    set_provider_b_status(is_down=False)
    resp_a = client.post("/submissions", json=payload, headers={"X-Forwarded-For": "8.8.8.8"})
    assert resp_a.status_code == 201

    # Case B: Provider A goes down -> Provider B succeeds
    set_provider_a_status(is_down=True)
    set_provider_b_status(is_down=False)
    resp_b = client.post("/submissions", json=payload, headers={"X-Forwarded-For": "8.8.8.8"})
    assert resp_b.status_code == 201

    # Case C: Both Provider A AND Provider B down -> Graceful degradation
    set_provider_a_status(is_down=True)
    set_provider_b_status(is_down=True)
    resp_degraded = client.post("/submissions", json=payload, headers={"X-Forwarded-For": "8.8.8.8"})
    assert resp_degraded.status_code == 201
    assert resp_degraded.status_code != 500

    # Verify degraded submission is stored with None / "none"
    dash = client.get("/dashboard/stats", headers={"X-API-Key": TENANT_A_KEY}).json()
    latest_sub = dash["recent_submissions"][0]
    assert latest_sub["geo_provider"] == "none"
    assert latest_sub["country"] is None


# ──────────────────────────────────────────────
# PROBE 5: Secondary Side Effect Failure Containment
# ──────────────────────────────────────────────
def test_probe_5_side_effect_failure_containment():
    # Simulate secondary email service failure (e.g. SMTP down / timeout)
    set_email_side_effect_status(should_fail=True)

    payload = {
        "widget_id": "wid_demo_signup",
        "data": {"name": "Side Effect Test", "email": "smtp_fail@domain.com"},
    }

    # Submission MUST return 201 Created and NOT 500
    resp = client.post("/submissions", json=payload)
    assert resp.status_code == 201

    # Check that submission was safely stored in database with side_effect_status="failed"
    dash = client.get("/dashboard/stats", headers={"X-API-Key": TENANT_A_KEY}).json()
    latest_sub = dash["recent_submissions"][0]
    assert latest_sub["side_effect_status"] == "failed"
    assert latest_sub["data"]["email"] == "smtp_fail@domain.com"


# ──────────────────────────────────────────────
# PROBE 6: Honeypot Anti-Spam Trap
# ──────────────────────────────────────────────
def test_probe_6_honeypot_spam_trap():
    # Spambot fills the hidden honeypot input field
    spam_payload = {
        "widget_id": "wid_demo_signup",
        "data": {"name": "Bot Spammer", "email": "bot@spam-network.ru"},
        "website_url_hp": "http://buy-crypto-now.xyz",  # Trap triggered!
    }

    resp = client.post("/submissions", json=spam_payload)
    # Rejected with 400 Bad Request
    assert resp.status_code == 400
    assert "honeypot" in resp.json()["detail"].lower()

    # Verify spam blocked counter incremented in dashboard
    dash = client.get("/dashboard/stats", headers={"X-API-Key": TENANT_A_KEY}).json()
    assert dash["spam_blocked"] >= 1


# ──────────────────────────────────────────────
# MULTI-TENANT ISOLATION
# ──────────────────────────────────────────────
def test_multi_tenant_isolation():
    # 1. Unauthenticated request to admin route rejected with 401
    resp_unauth = client.get("/widgets")
    assert resp_unauth.status_code == 401

    # 2. Tenant A lists widgets -> only sees Tenant A widgets
    resp_a = client.get("/widgets", headers={"X-API-Key": TENANT_A_KEY})
    assert resp_a.status_code == 200
    widgets_a = resp_a.json()
    tenant_a_ids = [w["id"] for w in widgets_a]
    assert "wid_demo_signup" in tenant_a_ids
    assert "wid_beta_cta" not in tenant_a_ids  # Tenant B's widget!

    # 3. Tenant A tries to fetch Tenant B's widget directly -> 404
    resp_forbidden = client.get("/widgets/wid_beta_cta", headers={"X-API-Key": TENANT_A_KEY})
    assert resp_forbidden.status_code == 404

    # 4. Tenant B lists widgets -> only sees Tenant B widgets
    resp_b = client.get("/widgets", headers={"Authorization": f"Bearer {TENANT_B_KEY}"})
    assert resp_b.status_code == 200
    widgets_b = resp_b.json()
    tenant_b_ids = [w["id"] for w in widgets_b]
    assert "wid_beta_cta" in tenant_b_ids
    assert "wid_demo_signup" not in tenant_b_ids
