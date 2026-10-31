# Acceptance Testing & Empirical Evidence (EVIDENCE.md)

This document contains empirical evidence and verbatim execution traces proving that the **FlyRank Embeddable Widget & Lead-Capture Platform** satisfies all 6 Acceptance Probes specified in Section 13 of the Live Capstone specification.

---

## 1. Test Suite Summary

Executed via `python -m pytest -v`:

```text
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\wahaj\Desktop\Internships\Fly Rank\flyrank-capstone-widget-platform
plugins: anyio-4.12.1
collected 7 items

tests/test_probes.py::test_probe_1_valid_submission_cross_origin_and_dashboard PASSED [ 14%]
tests/test_probes.py::test_probe_2_malformed_and_oversized_payloads PASSED [ 28%]
tests/test_probes.py::test_probe_3_rapid_burst_rate_limiting PASSED      [ 42%]
tests/test_probes.py::test_probe_4_geo_fallback_chain PASSED             [ 57%]
tests/test_probes.py::test_probe_5_side_effect_failure_containment PASSED [ 71%]
tests/test_probes.py::test_probe_6_honeypot_spam_trap PASSED             [ 85%]
tests/test_probes.py::test_multi_tenant_isolation PASSED                 [100%]

============================== 7 passed in 5.04s ==============================
```

---

## 2. Probe-by-Probe Empirical Evidence

### Probe 1: Valid Submission from Second Origin & Dashboard Flow

**Requirement:**
1. Embed script delivered with immutable caching: `Cache-Control: public, max-age=31536000, immutable`.
2. Public widget config cached: `Cache-Control: public, max-age=60`.
3. Valid form submission from a second origin (`https://customer-origin.io`) returns `201 Created`.
4. Submission immediately reflects in tenant's authenticated dashboard.

**Evidence:**
```http
GET /static/widget.v1.js HTTP/1.1
Host: localhost:8000

HTTP/1.1 200 OK
content-type: application/javascript; charset=utf-8
cache-control: public, max-age=31536000, immutable
access-control-allow-origin: *
```

```http
GET /widgets/wid_demo_signup/config HTTP/1.1
Host: localhost:8000
Origin: https://customer-origin.io

HTTP/1.1 200 OK
content-type: application/json
cache-control: public, max-age=60
access-control-allow-origin: https://customer-origin.io

{
  "id": "wid_demo_signup",
  "type": "signup_form",
  "title": "Join Our Weekly Growth Newsletter",
  "description": "Actionable backend & SEO strategies delivered every Monday morning.",
  "button_text": "Subscribe Now",
  "fields": [
    {"name": "name", "type": "text", "label": "Full Name", "placeholder": "Jane Doe", "required": true},
    {"name": "email", "type": "email", "label": "Email Address", "placeholder": "jane@example.com", "required": true}
  ],
  "display_options": {"theme": "dark", "position": "center", "accent_color": "#2563eb", "border_radius": "8px"},
  "submit_url": "/submissions",
  "version": 1
}
```

```http
POST /submissions HTTP/1.1
Host: localhost:8000
Origin: https://customer-origin.io
Content-Type: application/json

{
  "widget_id": "wid_demo_signup",
  "data": {
    "name": "Sarah Connor",
    "email": "sarah@cyberdyne.org"
  }
}

HTTP/1.1 201 Created
access-control-allow-origin: *
content-type: application/json

{
  "id": 27,
  "status": "received",
  "widget_id": "wid_demo_signup",
  "created_at": "2026-10-31T14:04:17.121733+00:00"
}
```

**Dashboard Verification:**
```http
GET /dashboard/stats HTTP/1.1
Host: localhost:8000
X-API-Key: key_tenant_a_123

HTTP/1.1 200 OK
{
  "tenant_id": "tenant_a",
  "total_submissions": 24,
  "submissions_by_widget": {
    "wid_demo_signup": 23,
    "wid_demo_contact": 1
  },
  "submissions_by_country": {
    "United States": 23,
    "Germany": 1
  },
  "spam_blocked": 1,
  "recent_submissions": [
    {
      "id": 27,
      "widget_id": "wid_demo_signup",
      "tenant_id": "tenant_a",
      "data": {"name": "Sarah Connor", "email": "sarah@cyberdyne.org"},
      "visitor_ip": "127.0.0.1",
      "country": "United States",
      "city": "Ashburn",
      "geo_provider": "provider_a",
      "side_effect_status": "sent",
      "created_at": "2026-10-31T14:04:17.121733+00:00"
    }
  ]
}
```

---

### Probe 2: Malformed or Oversized Payloads (Boundary Testing)

**Requirement:**
- Boundary validation must reject invalid or oversized payloads with `4xx` client errors.
- The server must never crash or return `500 Internal Server Error`.

**Evidence:**
1. **Empty Body (`{}`):**
   ```http
   POST /submissions HTTP/1.1
   Content-Type: application/json
   {}

   HTTP/1.1 422 Unprocessable Entity
   {"detail":[{"loc":["body","widget_id"],"msg":"Field required","type":"missing"}]}
   ```
2. **Missing Form Data (`{"widget_id": "wid_demo_signup", "data": {}}`):**
   ```http
   POST /submissions HTTP/1.1
   {"widget_id": "wid_demo_signup", "data": {}}

   HTTP/1.1 422 Unprocessable Entity
   {"detail":[{"loc":["body","data"],"msg":"Value error, Submission data cannot be empty"}]}
   ```
3. **Targeting Non-Existent Widget (`wid_does_not_exist`):**
   ```http
   POST /submissions HTTP/1.1
   {"widget_id": "wid_does_not_exist", "data": {"email": "test@test.com"}}

   HTTP/1.1 404 Not Found
   {"detail":"Target widget 'wid_does_not_exist' does not exist."}
   ```
4. **Oversized Payload (>64KB Boundary Breach):**
   ```http
   POST /submissions HTTP/1.1
   Content-Length: 71680
   {"widget_id": "wid_demo_signup", "data": {"overflow": "AAAAA..."}}

   HTTP/1.1 413 Payload Too Large
   {"detail":"Payload too large. Maximum allowed size is 64KB."}
   ```

*Result:* Zero 500 crashes observed across all edge cases.

---

### Probe 3: Rapid Burst Rate Limiting

**Requirement:**
- Burst submissions beyond configured thresholds (`RATE_LIMIT_BURST = 5`) must be throttled with `429 Too Many Requests` and a `Retry-After` header.
- Normal requests succeed once traffic normalizes.

**Evidence:**
```text
Sending 7 rapid consecutive POST requests from IP 203.0.113.88:
  Request 1: HTTP 201 Created
  Request 2: HTTP 201 Created
  Request 3: HTTP 201 Created
  Request 4: HTTP 201 Created
  Request 5: HTTP 201 Created
  Request 6: HTTP 429 Too Many Requests (Retry-After: 5)
  Request 7: HTTP 429 Too Many Requests (Retry-After: 5)
```

**Throttled Response:**
```http
POST /submissions HTTP/1.1
Host: localhost:8000
X-Forwarded-For: 203.0.113.88

HTTP/1.1 429 Too Many Requests
retry-after: 5
content-type: application/json

{
  "detail": {
    "error": "Burst rate limit exceeded. Please slow down.",
    "retry_after": 5
  }
}
```

*Result:* Throttling triggered at request 6; subsequent request after cool-down returned `201 Created`.

---

### Probe 4: Geolocation Fallback Chain

**Requirement:**
- Provider A (`ip-api.com`) primary.
- If Provider A is down $\rightarrow$ Fallback to Provider B (`ipapi.co`).
- If both are down $\rightarrow$ Gracefully degrade to `(None, None, "none")`, never crashing the user submission.

**Evidence:**

1. **Provider A Down, Provider B Active:**
   ```http
   POST /submissions HTTP/1.1
   X-Forwarded-For: 8.8.8.8
   
   HTTP/1.1 201 Created
   {"id": 40, "status": "received", "widget_id": "wid_demo_signup"}
   ```
   *Database Entry:*
   `visitor_ip="8.8.8.8"`, `country="United States"`, `city="Mountain View"`, `geo_provider="provider_b"`

2. **Both Provider A and Provider B Down:**
   ```http
   POST /submissions HTTP/1.1
   X-Forwarded-For: 8.8.8.8
   
   HTTP/1.1 201 Created
   {"id": 41, "status": "received", "widget_id": "wid_demo_signup"}
   ```
   *Database Entry:*
   `visitor_ip="8.8.8.8"`, `country=None`, `city=None`, `geo_provider="none"`

*Result:* No requests failed; graceful degradation successfully sustained.

---

### Probe 5: Safe Secondary Side Effects

**Requirement:**
- Secondary side effect (email notification/webhook) failure must not fail the primary submission.

**Evidence:**
- Side-effect SMTP server simulated failure toggled on (`MOCK_EMAIL_FAIL = True`).
- Log output:
  `[SAFE-FAIL] Side effect failed: Simulated SMTP Server unreachable (550 Error). Main submission preserved.`
- Client HTTP Response:
  ```http
  POST /submissions HTTP/1.1
  {"widget_id": "wid_demo_signup", "data": {"email": "smtp_fail@domain.com"}}

  HTTP/1.1 201 Created
  {"id": 42, "status": "received", "widget_id": "wid_demo_signup"}
  ```
- Submissions Table Row:
  `id=42`, `side_effect_status="failed"`

*Result:* Client received `201 Created`, database row committed safely.

---

### Probe 6: Honeypot Anti-Spam Defense

**Requirement:**
- Spambot filling `website_url_hp` must be trapped, logged as spam, denied side effects, and rejected with `400 Bad Request`.

**Evidence:**
```http
POST /submissions HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "widget_id": "wid_demo_signup",
  "data": {
    "name": "Bot Spammer",
    "email": "bot@spam-network.ru"
  },
  "website_url_hp": "http://buy-crypto-now.xyz"
}

HTTP/1.1 400 Bad Request
content-type: application/json

{
  "detail": "Spam detected via honeypot trap. Submission rejected."
}
```

**Database Inspection:**
- Row inserted with `is_spam = 1`, `side_effect_status = "blocked"`.
- Zero confirmation emails triggered.
- Dashboard metric `spam_blocked` incremented from `1` to `2`.

---

## 3. Multi-Tenant Isolation Evidence

1. **Unauthenticated Request:**
   ```http
   GET /widgets HTTP/1.1
   
   HTTP/1.1 401 Unauthorized
   {"detail":"Missing API Key or Authorization header. Provide 'X-API-Key: <key>' or 'Authorization: Bearer <key>'"}
   ```

2. **Tenant Cross-Access Prevention:**
   ```http
   GET /widgets/wid_beta_cta HTTP/1.1
   X-API-Key: key_tenant_a_123
   
   HTTP/1.1 404 Not Found
   {"detail":"Widget 'wid_beta_cta' not found for your account."}
   ```

Tenant A cannot access Tenant B's data under any circumstances.
