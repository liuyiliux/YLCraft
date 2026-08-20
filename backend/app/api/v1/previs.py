"""3D director previs scene API.

Previs scenes are explicitly linked to one project storyboard panel. Unlike the
free-form canvas (last-write-wins), scene saves use compare-and-swap on
`revision` so a stale editor or Agent cannot silently overwrite a camera or
object transform that another session just changed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.previs import PrevisSceneDocument

router = APIRouter()


class PrevisSceneCreateRequest(BaseModel):
    # 三者齐全 = 绑定项目分镜面板的场景；三者全空 = 独立场景（先摆思路，无需项目）
    project_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    storyboard_content_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    panel_number: Optional[int] = Field(default=None, ge=1)
    title: str = Field(default="3D 预演", max_length=160)
    scene: dict[str, Any] = Field(default_factory=dict)


class PrevisSceneSaveRequest(BaseModel):
    expected_revision: int = Field(..., ge=1)
    title: str = Field(default="3D 预演", max_length=160)
    scene: dict[str, Any] = Field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _scene_id(value: Any = None) -> str:
    raw = str(value or "").strip()
    return raw or str(uuid4())


def _normalize_scene(scene: Any) -> dict[str, Any]:
    if not isinstance(scene, dict):
        raise HTTPException(status_code=422, detail="scene must be an object")
    normalized = dict(scene)
    normalized.setdefault("fps", 24)
    normalized.setdefault("durationFrames", 0)
    normalized.setdefault("activeCameraId", "")
    normalized.setdefault("nodes", [])
    normalized.setdefault("cameras", [])
    normalized.setdefault("keyframes", [])
    normalized.setdefault("settings", {})
    return normalized


def _row_to_scene(row: PrevisSceneDocument) -> dict[str, Any]:
    scene = dict(row.scene_json or {})
    return {
        "id": str(row.id),
        "project_id": row.project_id or "",
        "storyboard_content_id": row.storyboard_content_id or "",
        "panel_number": row.panel_number,
        "title": row.title,
        "revision": row.revision,
        "scene": scene,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/scenes", summary="List previs scenes")
def list_previs_scenes(
    project_id: Annotated[Optional[str], Query(description="Filter by project ID")] = None,
    storyboard_content_id: Annotated[Optional[str], Query(description="Filter by storyboard content ID")] = None,
    panel_number: Annotated[Optional[int], Query(description="Filter by panel number")] = None,
):
    with SessionLocal() as session:
        query = select(PrevisSceneDocument).order_by(PrevisSceneDocument.updated_at.desc())
        if project_id:
            query = query.where(PrevisSceneDocument.project_id == project_id)
        if storyboard_content_id:
            query = query.where(PrevisSceneDocument.storyboard_content_id == storyboard_content_id)
        if panel_number is not None:
            query = query.where(PrevisSceneDocument.panel_number == panel_number)
        rows = session.exec(query).all()
        return {"success": True, "data": [_row_to_scene(row) for row in rows], "total": len(rows)}


@router.post("/scenes", summary="Create previs scene")
def create_previs_scene(req: PrevisSceneCreateRequest):
    scene = _normalize_scene(req.scene)
    now = _utc_now()
    row = PrevisSceneDocument(
        id=_scene_id(),
        project_id=req.project_id,
        storyboard_content_id=req.storyboard_content_id,
        panel_number=req.panel_number,
        title=req.title,
        scene_json=scene,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    with SessionLocal() as session:
        # 只有完整绑定项目分镜的场景才做去重；独立场景（三者全空）直接创建。
        if req.project_id and req.storyboard_content_id and req.panel_number:
            existing = session.exec(
                select(PrevisSceneDocument).where(
                    PrevisSceneDocument.project_id == req.project_id,
                    PrevisSceneDocument.storyboard_content_id == req.storyboard_content_id,
                    PrevisSceneDocument.panel_number == req.panel_number,
                )
            ).first()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Previs scene already exists for this storyboard panel: {existing.id}",
                )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"success": True, "data": _row_to_scene(row)}


@router.get("/scenes/{scene_id}", summary="Get previs scene")
def get_previs_scene(scene_id: str):
    with SessionLocal() as session:
        row = session.get(PrevisSceneDocument, scene_id)
        if not row:
            raise HTTPException(status_code=404, detail="Previs scene not found")
        return {"success": True, "data": _row_to_scene(row)}


@router.put("/scenes/{scene_id}", summary="Save previs scene with revision check")
def save_previs_scene(scene_id: str, req: PrevisSceneSaveRequest):
    scene = _normalize_scene(req.scene)
    now = _utc_now()
    with SessionLocal() as session:
        row = session.get(PrevisSceneDocument, scene_id)
        if not row:
            raise HTTPException(status_code=404, detail="Previs scene not found")
        if row.revision != req.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Previs scene was modified by another session",
                    "current_revision": row.revision,
                    "expected_revision": req.expected_revision,
                },
            )
        try:
            session.exec(
                update(PrevisSceneDocument)
                .where(PrevisSceneDocument.id == scene_id)
                .values(
                    title=req.title,
                    scene_json=scene,
                    revision=row.revision + 1,
                    updated_at=now,
                )
            )
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Previs scene save failed") from exc

        session.refresh(row)
        return {"success": True, "data": _row_to_scene(row)}


@router.delete("/scenes/{scene_id}", summary="Delete previs scene")
def delete_previs_scene(scene_id: str):
    with SessionLocal() as session:
        row = session.get(PrevisSceneDocument, scene_id)
        if not row:
            raise HTTPException(status_code=404, detail="Previs scene not found")
        session.delete(row)
        session.commit()
        return {"success": True, "deleted_id": scene_id}
