"""
Tenant Authentication Layer.
Extracts API Key from X-API-Key header or Authorization: Bearer <key>.
Enforces multi-tenant isolation across all management and dashboard endpoints.
"""

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from src.database import get_tenant_by_api_key

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_tenant(
    api_key: Optional[str] = Security(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> dict:
    token = api_key or (credentials.credentials if credentials else None)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key or Authorization header. Provide 'X-API-Key: <key>' or 'Authorization: Bearer <key>'",
        )

    tenant = get_tenant_by_api_key(token)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key. Access denied.",
        )

    return tenant
