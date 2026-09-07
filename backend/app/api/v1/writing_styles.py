"""Writing style profile API.

Both the human UI and external agents use this reviewed lifecycle:
draft -> reviewed -> active -> project binding.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.database import get_session
from app.services.creative_project.writing_style import (
    EXTRACTION_SAMPLE_CHARS,
    WritingStyleService,
    serialize_style_link,
    serialize_style_profile,
)

router = APIRouter()


class StyleProfileCreateRequest(BaseModel):
    name: str
    description: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    owner_id: str = "default"
    source_type: str = "user_defined"
    source_snapshot_id: str | None = None
    source_sample_hash: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)


class StyleProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    profile: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None


class StyleProfileBindRequest(BaseModel):
    profile_id: str
    intensity: str = Field(default="balanced", description="subtle/balanced/strong")
    stage_scope: list[str] = Field(default_factory=list)
    dimension_overrides: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10000)


def _service(db: Session) -> WritingStyleService:
    return WritingStyleService(db)


@router.get("", summary="列出写作风格档案")
def list_style_profiles(
    owner_id: str = Query(default="default"),
    status: str | None = Query(default=None),
    db: Session = Depends(get_session),
):
    return {
        "success": True,
        "data": [serialize_style_profile(item) for item in _service(db).list(owner_id=owner_id, status=status)],
    }


@router.post("", summary="创建写作风格档案草稿")
def create_style_profile(req: StyleProfileCreateRequest, db: Session = Depends(get_session)):
    try:
        item = _service(db).create_profile(**req.model_dump())
        return {"success": True, "data": serialize_style_profile(item)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}", summary="获取项目绑定的写作风格")
def list_project_style_profiles(project_id: str, stage: str = "", db: Session = Depends(get_session)):
    try:
        return {"success": True, "data": _service(db).runtime_profiles(project_id, stage=stage)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}", summary="绑定写作风格到项目")
def bind_project_style(project_id: str, req: StyleProfileBindRequest, db: Session = Depends(get_session)):
    try:
        link = _service(db).bind(project_id, req.profile_id, **req.model_dump(exclude={"profile_id"}))
        return {"success": True, "data": serialize_style_link(link)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/projects/{project_id}/{profile_id}", summary="解绑项目写作风格")
def unbind_project_style(project_id: str, profile_id: str, db: Session = Depends(get_session)):
    _service(db).unbind(project_id, profile_id)
    return {"success": True, "data": {"project_id": project_id, "profile_id": profile_id}}


@router.get("/{profile_id}", summary="获取写作风格档案")
def get_style_profile(profile_id: str, db: Session = Depends(get_session)):
    item = _service(db).get(profile_id)
    if not item:
        raise HTTPException(status_code=404, detail="风格档案不存在")
    return {"success": True, "data": serialize_style_profile(item)}


@router.put("/{profile_id}", summary="编辑写作风格档案草稿")
def update_style_profile(profile_id: str, req: StyleProfileUpdateRequest, db: Session = Depends(get_session)):
    try:
        item = _service(db).update_draft(profile_id, **req.model_dump(exclude_unset=True))
        return {"success": True, "data": serialize_style_profile(item)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{profile_id}/review", summary="审核写作风格档案")
def review_style_profile(profile_id: str, db: Session = Depends(get_session)):
    try:
        return {"success": True, "data": serialize_style_profile(_service(db).review(profile_id))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{profile_id}/activate", summary="激活写作风格档案")
def activate_style_profile(profile_id: str, db: Session = Depends(get_session)):
    try:
        return {"success": True, "data": serialize_style_profile(_service(db).activate(profile_id))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{profile_id}/archive", summary="归档写作风格档案")
def archive_style_profile(profile_id: str, db: Session = Depends(get_session)):
    try:
        return {"success": True, "data": serialize_style_profile(_service(db).archive(profile_id))}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class StyleProfileExtractRequest(BaseModel):
    snapshot_id: str
    name: str = ""
    owner_id: str = "default"
    provider: str | None = None
    model: str | None = None
    max_chars: int = Field(default=EXTRACTION_SAMPLE_CHARS, ge=1000, le=60000)


@router.post("/extract-from-source", summary="从来源快照提取风格档案草稿（只出 draft，不自动激活）")
async def extract_style_from_source(
    req: StyleProfileExtractRequest, db: Session = Depends(get_session)
):
    """测量聚合 + 有界抽象分析：只提炼抽象表达机制，不落地来源正文。

    产出恒为 ``draft``，需人工或 Agent 审核后才可激活、再绑定项目。
    """
    try:
        item = await _service(db).extract_draft_from_source(
            snapshot_id=req.snapshot_id,
            name=req.name,
            owner_id=req.owner_id,
            provider=req.provider,
            model=req.model,
            max_chars=req.max_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # AIService 未初始化等环境问题：503 而不是 500。
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "data": serialize_style_profile(item)}
