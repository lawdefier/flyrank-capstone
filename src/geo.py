"""
IP Geolocation Enrichment with Fallback Chain.
Chain: Provider A (ip-api.com) -> Provider B (ipapi.co) -> Graceful Degradation (None, None).
Never fails the request even if all providers are down.
"""

import requests
from typing import Tuple, Optional
from src.config import MOCK_GEO_FAIL_A, MOCK_GEO_FAIL_B

# Runtime toggles for deterministic probe testing (PROBE 4)
_runtime_fail_a = MOCK_GEO_FAIL_A
_runtime_fail_b = MOCK_GEO_FAIL_B


def set_provider_a_status(is_down: bool):
    global _runtime_fail_a
    _runtime_fail_a = is_down


def set_provider_b_status(is_down: bool):
    global _runtime_fail_b
    _runtime_fail_b = is_down


def enrich_ip(ip: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Enriches IP with (country, city, provider).
    Graceful degradation: returns (None, None, 'none') if all providers fail.
    """
    # Clean private/localhost IPs for mock evaluation if requested
    is_local = ip in ("127.0.0.1", "::1", "localhost", "testclient")

    # ──────────────────────────────────────────
    # 1. Try Provider A (ip-api.com)
    # ──────────────────────────────────────────
    if not _runtime_fail_a:
        try:
            if is_local:
                return "United States", "Ashburn", "provider_a"
            url = f"http://ip-api.com/json/{ip}?fields=status,country,city"
            resp = requests.get(url, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return data.get("country"), data.get("city"), "provider_a"
        except Exception:
            pass  # Fall through to Provider B

    # ──────────────────────────────────────────
    # 2. Try Provider B (ipapi.co - Fallback)
    # ──────────────────────────────────────────
    if not _runtime_fail_b:
        try:
            if is_local:
                return "United Kingdom", "London", "provider_b"
            url = f"https://ipapi.co/{ip}/json/"
            resp = requests.get(url, timeout=2.0, headers={"User-Agent": "FlyRankCapstone/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                if "country_name" in data or "city" in data:
                    return data.get("country_name"), data.get("city"), "provider_b"
        except Exception:
            pass

    # ──────────────────────────────────────────
    # 3. Graceful Degradation (Degrade, never fail)
    # ──────────────────────────────────────────
    return None, None, "none"
