# Engineering Build Log & AI Usage Reflection (BUILDLOG.md)

## 1. Project Chronology & Phase Evolution

### Phase 1 — Architecture & Multi-Tenant Schema Design
- **Objective:** Establish clean boundary layers separating admin configuration, public edge delivery, and lead ingest.
- **Key Decisions:**
  - Designed the relational data model with three core entities: `tenants`, `widgets`, and `submissions`.
  - Added indexes on `tenant_id`, `widget_id`, and `created_at` to ensure all queries remain $O(\log N)$ and prevent full table scans.
  - Chose SQLite with strict typing emulation and row factories. SQLite requires zero external server setup, making it immediately testable and portable while supporting ACID transactions.
  - Modeled authentication around API keys passed via `X-API-Key` or standard `Authorization: Bearer <key>`, verified on every admin request via FastAPI dependency injection.

### Phase 2 — Ingest Pipeline Hardening & Fault Tolerance
- **Objective:** Defend the open `POST /submissions` endpoint from abuse, crashes, and downstream cascading failures.
- **Key Decisions:**
  - **Boundary Checks:** Added global middleware to reject any request exceeding 64KB with `413 Payload Too Large` before body parsing.
  - **Sliding-Window Rate Limiter:** Implemented per-IP and per-widget tracking with a 10-second burst threshold (`RATE_LIMIT_BURST = 5`) and a 60-second limit (`RATE_LIMIT_PER_MINUTE = 20`). Configured standard `Retry-After` headers.
  - **Dual-Provider Geo Fallback:** Constructed an HTTP fallback chain (`ip-api.com` $\rightarrow$ `ipapi.co` $\rightarrow$ `(None, None, "none")`). Added runtime test toggles (`set_provider_a_status`, `set_provider_b_status`) so failure scenarios could be deterministically verified without relying on actual internet outages.
  - **Safe Secondary Side Effects:** Encapsulated confirmation emails in a non-blocking safety block. Simulated SMTP server outages proved that secondary failures never fail the primary 201 response or roll back database persistence.
  - **Honeypot Trap:** Embedded a hidden input (`website_url_hp`). If populated, submissions are flagged with `is_spam = 1`, metrics are incremented, side effects are skipped, and a 400 Bad Request is returned.

### Phase 3 — Edge Delivery, Widget Loader & Second-Origin Verification
- **Objective:** Minimize latency on public web pages and verify cross-origin interoperability.
- **Key Decisions:**
  - Configured caching headers: 1 year (`max-age=31536000, immutable`) for `widget.v1.js` and 60 seconds (`max-age=60`) for `/widgets/:id/config`.
  - Created `static/widget.v1.js`, a zero-dependency vanilla JS script that dynamically extracts its own query string parameter (`?id=...`), fetches config, renders an isolated UI with custom styles, attaches the invisible honeypot trap, and submits leads via `fetch()`.
  - Built `customer_site/index.html` to simulate a real customer website on Origin B embedding the FlyRank widget.
  - Verified end-to-end functionality across all 6 Acceptance Probes with an automated test suite.

---

## 2. Engineering Trade-offs & Analysis

| Design Area | Selected Approach | Alternative Considered | Rationale |
| :--- | :--- | :--- | :--- |
| **Persistence Engine** | SQLite with B-Tree Indexes | PostgreSQL via Docker | SQLite delivers zero-overhead, sub-millisecond local queries without requiring Docker background services for evaluation. Schema and repository boundaries allow one-file swap to Postgres if needed. |
| **Rate Limiter** | In-Memory Sliding Window | Redis Token Bucket | In-memory sliding window provides sub-microsecond rate checks without external daemon dependencies. Clean interface allows swapping to Redis in distributed production setups. |
| **Geo Resolution** | 2-Provider HTTP Fallback Chain | Offline MaxMind GeoLite2 DB | Remote HTTP APIs avoid bundling 70MB binary `.mmdb` files while demonstrating resilient multi-provider fallback and graceful degradation patterns. |
| **Honeypot Defense** | CSS Hidden Input (`left: -9999px`) | Google reCAPTCHA / Cloudflare Turnstile | Captchas introduce user friction and require third-party API credentials; honeypots catch 95%+ of automated spam bots invisibly without frustrating human leads. |

---

## 3. AI Usage & Collaborative Engineering Reflection

This capstone was developed using the Antigravity pair programming workflow:
- **Scaffolding & Architecture:** Used AI to explore data models and draft initial Pydantic schemas and database queries with tenant isolation checks.
- **Probe Verification:** AI helped design the automated test harness covering the 6 acceptance probes, ensuring edge cases (like Starlette's deprecation of `HTTP_413_REQUEST_ENTITY_TOO_LARGE` in favor of `HTTP_413_CONTENT_TOO_LARGE` and CORS origin reflection rules) were resolved cleanly.
- **Review & Hardening:** Verified that every probe in Section 13 of the PDF specification was tested deterministically and with 100% pass rates.
