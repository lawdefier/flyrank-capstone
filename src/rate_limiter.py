"""
In-memory Token-Bucket & Sliding-Window Rate Limiter.
Enforces limits per IP and per widget.
Returns 429 Too Many Requests when limits are exceeded.
"""

import time
from typing import Dict, List
from fastapi import Request, HTTPException, status
from src.config import RATE_LIMIT_PER_MINUTE, RATE_LIMIT_BURST

# IP -> list of request timestamps
_ip_requests: Dict[str, List[float]] = {}
# Widget ID -> list of request timestamps
_widget_requests: Dict[str, List[float]] = {}


def check_rate_limit(ip: str, widget_id: str):
    """
    Checks per-IP and per-widget rate limits using a 60-second sliding window.
    Raises HTTPException(429) if limits are breached.
    """
    now = time.time()
    cutoff = now - 60.0

    # 1. Clean old entries for IP
    timestamps = [t for t in _ip_requests.get(ip, []) if t > cutoff]
    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "Rate limit exceeded. Please slow down.", "retry_after": 5},
            headers={"Retry-After": "5"},
        )

    # Check burst: no more than RATE_LIMIT_BURST in 10 seconds
    recent_burst = [t for t in timestamps if t > (now - 10.0)]
    if len(recent_burst) >= RATE_LIMIT_BURST:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "Burst rate limit exceeded. Please slow down.", "retry_after": 5},
            headers={"Retry-After": "5"},
        )

    timestamps.append(now)
    _ip_requests[ip] = timestamps

    # 2. Track per-widget limits (protect widget from being flooded)
    w_timestamps = [t for t in _widget_requests.get(widget_id, []) if t > cutoff]
    w_timestamps.append(now)
    _widget_requests[widget_id] = w_timestamps


def reset_rate_limiter():
    """Reset rate limiter state (useful for tests)."""
    global _ip_requests, _widget_requests
    _ip_requests.clear()
    _widget_requests.clear()
