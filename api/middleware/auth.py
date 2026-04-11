from __future__ import annotations

import hashlib
import os

from fastapi import Header, HTTPException, Request
from sqlalchemy import select

from core.database import ApiKey, AsyncSessionLocal


async def api_key_auth(x_api_key: str = Header(default="")) -> str:
    # Local/dev bypass: set DISABLE_API_KEY_AUTH=true in .env
    if os.getenv("DISABLE_API_KEY_AUTH", "").lower() in {"1", "true", "yes"}:
        return "dev-bypass"

    # Optional static key path (avoids DB dependency for local runs)
    static_api_key = os.getenv("API_KEY", "").strip()
    if static_api_key:
        if x_api_key != static_api_key:
            raise HTTPException(status_code=401, detail={"error": "invalid_api_key", "detail": "API key is invalid", "field": "X-API-Key"})
        return hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()

    if not x_api_key:
        raise HTTPException(status_code=401, detail={"error": "missing_api_key", "detail": "X-API-Key header required", "field": "X-API-Key"})

    digest = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.active == True))
        key = res.scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=401, detail={"error": "invalid_api_key", "detail": "API key is invalid", "field": "X-API-Key"})
        return digest
