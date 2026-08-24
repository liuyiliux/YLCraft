"""外部 Agent API Key 管理：生成 / 列出 / 撤销。"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.core.external_api_auth import hash_external_key
from app.db.database import get_async_session_dependency
from app.db.models.external_api_key import ExternalApiKey

router = APIRouter()

ALLOWED_SCOPES = {"read", "write", "generate"}


class ExternalApiKeyCreateRequest(BaseModel):
    name: str = Field(default="外部 Agent", max_length=80)
    scope: str = Field(default="read", max_length=16)
    rate_limit_per_min: int = Field(default=60, ge=1, le=3600)


def _row(r: ExternalApiKey) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "key_prefix": r.key_prefix,
        "scope": r.scope,
        "rate_limit_per_min": r.rate_limit_per_min,
        "active": r.active,
        "created_at": r.created_at.isoformat(),
        "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        "use_count": r.use_count,
    }


@router.get("", summary="列出外部 Agent API Key")
async def list_external_api_keys(session=Depends(get_async_session_dependency)):
    rows = (await session.exec(select(ExternalApiKey).order_by(ExternalApiKey.created_at.desc()))).all()
    return {"success": True, "data": [_row(r) for r in rows]}


@router.post("", summary="生成外部 Agent API Key")
async def create_external_api_key(body: ExternalApiKeyCreateRequest, session=Depends(get_async_session_dependency)):
    if body.scope not in ALLOWED_SCOPES:
        raise HTTPException(status_code=422, detail=f"scope 必须是 {sorted(ALLOWED_SCOPES)} 之一")
    token = "ylk_" + secrets.token_urlsafe(32)
    row = ExternalApiKey(
        name=body.name,
        key_hash=hash_external_key(token),
        key_prefix=token[:8],
        scope=body.scope,
        rate_limit_per_min=body.rate_limit_per_min,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {"success": True, "api_key": token, "data": _row(row)}


@router.delete("/{key_id}", summary="撤销外部 Agent API Key")
async def revoke_external_api_key(key_id: str, session=Depends(get_async_session_dependency)):
    row = await session.get(ExternalApiKey, key_id)
    if not row:
        raise HTTPException(status_code=404, detail="Key 不存在")
    row.active = False
    session.add(row)
    await session.commit()
    return {"success": True, "revoked": key_id}
