"""
Pydantic Schemas for Widget Platform.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Dict, Any


class WidgetCreate(BaseModel):
    id: Optional[str] = None
    type: str = Field("signup_form", description="Type: signup_form, contact_form, or cta_popover")
    title: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = ""
    button_text: str = Field("Submit", min_length=1, max_length=50)
    fields: List[Dict[str, Any]] = Field(
        default_factory=lambda: [
            {"name": "name", "type": "text", "required": True},
            {"name": "email", "type": "email", "required": True},
        ]
    )
    display_options: Dict[str, Any] = Field(
        default_factory=lambda: {"theme": "light", "position": "center"}
    )


class WidgetUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    button_text: Optional[str] = None
    display_options: Optional[Dict[str, Any]] = None


class WidgetOut(BaseModel):
    id: str
    tenant_id: str
    type: str
    title: str
    description: str
    button_text: str
    fields: List[Dict[str, Any]]
    display_options: Dict[str, Any]
    version: int
    embed_snippet: str
    created_at: str


class WidgetConfig(BaseModel):
    id: str
    type: str
    title: str
    description: str
    button_text: str
    fields: List[Dict[str, Any]]
    display_options: Dict[str, Any]
    submit_url: str
    version: int


class SubmissionCreate(BaseModel):
    widget_id: str
    data: Dict[str, Any] = Field(..., description="Form fields submitted by visitor")
    # Honeypot field: invisible to humans, filled by spam bots
    website_url_hp: Optional[str] = Field(None, description="Honeypot field (must remain empty)")

    @field_validator("data")
    @classmethod
    def validate_payload_limits(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not v:
            raise ValueError("Submission data cannot be empty")
        # Enforce max size limit: reject oversized payloads > 64KB
        total_len = sum(len(str(val)) for val in v.values()) + sum(len(k) for k in v.keys())
        if total_len > 64 * 1024:
            raise ValueError("Payload size exceeds 64KB limit")
        return v


class SubmissionOut(BaseModel):
    id: int
    widget_id: str
    tenant_id: str
    data: Dict[str, Any]
    visitor_ip: str
    country: Optional[str] = None
    city: Optional[str] = None
    geo_provider: Optional[str] = None
    side_effect_status: str
    created_at: str


class DashboardStats(BaseModel):
    tenant_id: str
    total_submissions: int
    submissions_by_widget: Dict[str, int]
    submissions_by_country: Dict[str, int]
    spam_blocked: int
    recent_submissions: List[SubmissionOut]
