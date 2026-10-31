"""
FlyRank Backend Track Capstone: Embeddable Widget & Lead-Capture Platform.
Production-ready FastAPI application delivering cached embed widgets, public lead capture,
multi-tenant isolated CRUD, sliding-window rate limiting, geo enrichment, and safe side effects.
"""

import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import PORT, ENVIRONMENT
from src.models import (
    WidgetCreate,
    WidgetUpdate,
    WidgetOut,
    WidgetConfig,
    SubmissionCreate,
    SubmissionOut,
    DashboardStats,
)
from src.database import (
    create_widget,
    get_widget_by_id,
    list_widgets_by_tenant,
    update_widget,
    delete_widget,
    insert_submission,
    get_dashboard_metrics,
)
from src.auth import get_current_tenant
from src.rate_limiter import check_rate_limit
from src.geo import enrich_ip
from src.side_effects import trigger_confirmation_email

app = FastAPI(
    title="FlyRank Embeddable Widget Platform",
    description="Multi-tenant embeddable widget engine, cached delivery & resilient lead capture API",
    version="1.0.0",
)

# ──────────────────────────────────────────────
# CORS Configuration (Permissive for Public Origins)
# ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files directory
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
# Global Request Size Boundary Check
# ──────────────────────────────────────────────
@app.middleware("http")
async def check_payload_size_limit(request: Request, call_next):
    # Reject oversized payloads > 64KB (Probe 2 requirement)
    MAX_PAYLOAD_BYTES = 64 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_PAYLOAD_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Payload too large. Maximum allowed size is 64KB."},
                )
        except ValueError:
            pass
    return await call_next(request)


# ──────────────────────────────────────────────
# System Liveness
# ──────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "FlyRank Lead-Capture Platform",
        "version": "1.0.0",
        "environment": ENVIRONMENT,
    }


# ──────────────────────────────────────────────
# Embed Script Delivery (Aggressively Cached)
# ──────────────────────────────────────────────
@app.get("/static/widget.v1.js", tags=["Widget Delivery"])
@app.get("/widget.js", tags=["Widget Delivery"])
def serve_widget_script():
    """
    Serves the embed script with immutable, long-lived caching headers.
    Headers: Cache-Control: public, max-age=31536000, immutable
    """
    script_path = STATIC_DIR / "widget.v1.js"
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Widget script not found.")

    response = FileResponse(
        path=script_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Access-Control-Allow-Origin": "*",
        },
    )
    return response


# ──────────────────────────────────────────────
# Public Widget Config Delivery (Short-Lived Cached)
# ──────────────────────────────────────────────
@app.get("/widgets/{widget_id}/config", tags=["Widget Delivery"])
def get_public_widget_config(widget_id: str, response: Response):
    """
    Delivers lightweight widget configuration for client rendering.
    Cached for 60 seconds (Probe 1 requirement).
    """
    widget = get_widget_by_id(widget_id)
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{widget_id}' not found.",
        )

    # Set cache header according to spec
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Access-Control-Allow-Origin"] = "*"

    return {
        "id": widget["id"],
        "type": widget["type"],
        "title": widget["title"],
        "description": widget["description"],
        "button_text": widget["button_text"],
        "fields": widget["fields"],
        "display_options": widget["display_options"],
        "submit_url": "/submissions",
        "version": widget["version"],
    }


# ──────────────────────────────────────────────
# Public Form Submissions (Hardened & Resilient)
# ──────────────────────────────────────────────
@app.post("/submissions", status_code=status.HTTP_201_CREATED, tags=["Public Submission"])
async def create_submission(payload: SubmissionCreate, request: Request, response: Response):
    """
    Public ingest endpoint for widget lead captures:
    1. Cross-Origin (CORS) allowed
    2. Per-IP & Per-Widget sliding-window rate limiting (429)
    3. Honeypot spam defense (Probe 6)
    4. Two-provider GeoIP fallback chain (Probe 4)
    5. Graceful secondary side-effect isolation (Probe 5)
    """
    response.headers["Access-Control-Allow-Origin"] = "*"

    # 1. Resolve Target Widget
    widget = get_widget_by_id(payload.widget_id)
    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target widget '{payload.widget_id}' does not exist.",
        )

    # 2. Extract Client IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    # 3. Abuse Protection: Rate Limiting (Probe 3)
    check_rate_limit(client_ip, payload.widget_id)

    # 4. Abuse Protection: Honeypot Check (Probe 6)
    if payload.website_url_hp and payload.website_url_hp.strip():
        # Spambot filled the hidden honeypot field!
        # Record spam metric in database, skip side effects, reject with 400
        insert_submission(
            widget_id=payload.widget_id,
            tenant_id=widget["tenant_id"],
            payload=payload.data,
            visitor_ip=client_ip,
            country="Unknown",
            city="Unknown",
            geo_provider="none",
            is_spam=True,
            side_effect_status="blocked",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spam detected via honeypot trap. Submission rejected.",
        )

    # 5. Geolocation Fallback Chain (Probe 4)
    country, city, geo_provider = enrich_ip(client_ip)

    # 6. Secondary Side Effects (Probe 5 - Failure must never break submission)
    try:
        side_effect_status = trigger_confirmation_email(payload.data, widget["title"])
    except Exception:
        side_effect_status = "failed"

    # 7. Persist Submission
    saved = insert_submission(
        widget_id=payload.widget_id,
        tenant_id=widget["tenant_id"],
        payload=payload.data,
        visitor_ip=client_ip,
        country=country,
        city=city,
        geo_provider=geo_provider,
        is_spam=False,
        side_effect_status=side_effect_status,
    )

    return {
        "id": saved["id"],
        "status": "received",
        "widget_id": saved["widget_id"],
        "created_at": saved["created_at"],
    }


# ──────────────────────────────────────────────
# Admin CRUD: Widget Management (Tenant Isolated)
# ──────────────────────────────────────────────
def _build_embed_snippet(widget_id: str, request: Request) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f'<script src="{base_url}/static/widget.v1.js?id={widget_id}"></script>'


@app.post("/widgets", response_model=WidgetOut, status_code=status.HTTP_201_CREATED, tags=["Admin Widgets"])
def create_new_widget(
    data: WidgetCreate,
    request: Request,
    tenant: dict = Depends(get_current_tenant),
):
    widget_id = data.id or f"wid_{uuid.uuid4().hex[:10]}"
    created = create_widget(
        tenant_id=tenant["id"],
        widget_id=widget_id,
        type_=data.type,
        title=data.title,
        description=data.description or "",
        button_text=data.button_text,
        fields=data.fields,
        display_options=data.display_options,
    )
    created["embed_snippet"] = _build_embed_snippet(widget_id, request)
    return created


@app.get("/widgets", response_model=List[WidgetOut], tags=["Admin Widgets"])
def list_widgets(
    request: Request,
    tenant: dict = Depends(get_current_tenant),
):
    widgets = list_widgets_by_tenant(tenant["id"])
    for w in widgets:
        w["embed_snippet"] = _build_embed_snippet(w["id"], request)
    return widgets


@app.get("/widgets/{widget_id}", response_model=WidgetOut, tags=["Admin Widgets"])
def get_widget(
    widget_id: str,
    request: Request,
    tenant: dict = Depends(get_current_tenant),
):
    w = get_widget_by_id(widget_id, tenant_id=tenant["id"])
    if not w:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{widget_id}' not found for your account.",
        )
    w["embed_snippet"] = _build_embed_snippet(w["id"], request)
    return w


@app.put("/widgets/{widget_id}", response_model=WidgetOut, tags=["Admin Widgets"])
def update_widget_details(
    widget_id: str,
    data: WidgetUpdate,
    request: Request,
    tenant: dict = Depends(get_current_tenant),
):
    updates = data.model_dump(exclude_unset=True)
    updated = update_widget(widget_id, tenant["id"], updates)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{widget_id}' not found or update unauthorized.",
        )
    updated["embed_snippet"] = _build_embed_snippet(widget_id, request)
    return updated


@app.delete("/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin Widgets"])
def delete_existing_widget(
    widget_id: str,
    tenant: dict = Depends(get_current_tenant),
):
    deleted = delete_widget(widget_id, tenant["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Widget '{widget_id}' not found or delete unauthorized.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────
# Admin Dashboard & Metrics (Tenant Isolated)
# ──────────────────────────────────────────────
@app.get("/dashboard/stats", response_model=DashboardStats, tags=["Admin Dashboard"])
def get_stats(tenant: dict = Depends(get_current_tenant)):
    """Tenant-scoped analytics, submission counts, spam metrics & country aggregates."""
    return get_dashboard_metrics(tenant["id"])
