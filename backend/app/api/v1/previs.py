"""3D director previs scene API.

Previs scenes are explicitly linked to one project storyboard panel. Unlike the
free-form canvas (last-write-wins), scene saves use compare-and-swap on
`revision` so a stale editor or Agent cannot silently overwrite a camera or
object transform that another session just changed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.db.database import SessionLocal, get_async_session
from app.db.models.creative_project import CreativeProject, ProjectAssetLink, ProjectContent
from app.db.models.previs import PrevisSceneDocument
from app.services.asset_hub import AssetHubFacade

logger = logging.getLogger("ylcraft.api.previs")

router = APIRouter()

#: 截图回流的关联语义：分镜参考图（design「截图回流」的固定顺序）
CAPTURE_ROLE = "storyboard_reference"
CAPTURE_RELATION = "derived_from"
CAPTURE_SOURCE = "previs_capture"

#: 允许的截图格式。浏览器 canvas 产出 PNG / WebP。
CAPTURE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}


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


def _capture_dir() -> Path:
    directory = Path(__file__).resolve().parents[3] / "storage" / "uploads" / "previs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _scene_asset_ids(scene: dict[str, Any]) -> list[str]:
    """场景内节点引用的 Asset Hub 资产（去重保序），作为截图的来源素材集。"""
    collected: list[str] = []
    for node in scene.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        asset_id = str(node.get("assetId") or "").strip()
        if asset_id and asset_id not in collected:
            collected.append(asset_id)
    return collected


@router.post("/scenes/{scene_id}/capture", summary="回流当前机位截图到 Asset Hub 并关联分镜面板")
async def capture_previs_scene(
    scene_id: str,
    file: Annotated[UploadFile, File()],
    camera_id: Annotated[str, Form()] = "",
    frame: Annotated[int, Form()] = 0,
):
    """把预演台当前机位的截图入库为 Asset Hub 图片，并关联到该场景所属的分镜面板。

    顺序固定（design「截图回流」）：
    场景 + 活动机位 → 浏览器截图 → Asset Hub 图片 →
    `ProjectAssetLink(role=storyboard_reference)` → 分镜面板 → 既有生图/生视频参考。

    两条刻意的设计选择：

    1. **溯源由服务端从场景派生**（`scene_revision` 取行上的 `revision`、`source_asset_ids`
       取场景自己的节点引用），不接受客户端传入——否则「这张图出自哪一版场景」不可信。
    2. **失败语义分离，不制造半成品关联**：上传失败则既不产生资产也不产生关联，直接报错；
       上传成功但关联失败时返回 `linked=false` + `link_error` + 可重试所需的全部字段
       （`asset_id`/`content_id`/`role`/`relation`/`provenance`），调用方可用既有的
       `POST /api/v1/creative-projects/{project_id}/assets` 以同一 metadata 重试关联。
    """
    filename = file.filename or "previs-capture.png"
    suffix = Path(filename).suffix.lower()
    if suffix not in CAPTURE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"截图格式不受支持：{suffix or '未知'}（允许 {'、'.join(sorted(CAPTURE_EXTENSIONS))}）",
        )

    with SessionLocal() as session:
        row = session.get(PrevisSceneDocument, scene_id)
        if not row:
            raise HTTPException(status_code=404, detail="Previs scene not found")
        scene = dict(row.scene_json or {})
        project_id = str(row.project_id or "")
        content_id = str(row.storyboard_content_id or "")
        scene_revision = int(row.revision or 1)
        panel_number = row.panel_number
        scene_title = str(row.title or "")

    # 独立场景没有分镜面板可关联：明确拒绝，而不是建一个悬空关联
    if not project_id or not content_id:
        raise HTTPException(
            status_code=400,
            detail="该预演场景未绑定项目分镜面板，无法回流截图；请从分镜卡片进入预演台后再截图",
        )

    known_cameras = {
        str(camera.get("id") or "")
        for camera in (scene.get("cameras") or [])
        if isinstance(camera, dict)
    }
    normalized_camera_id = str(camera_id or "").strip()
    if normalized_camera_id and known_cameras and normalized_camera_id not in known_cameras:
        raise HTTPException(status_code=400, detail=f"场景中不存在机位：{normalized_camera_id}")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="截图内容为空")

    target_dir = _capture_dir() / uuid4().hex
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(filename).name
    target.write_bytes(payload)

    provenance: dict[str, Any] = {
        "source": CAPTURE_SOURCE,
        "previs_scene_id": scene_id,
        "camera_id": normalized_camera_id,
        "frame": int(frame or 0),
        "scene_revision": scene_revision,
        "source_asset_ids": _scene_asset_ids(scene),
    }
    if panel_number is not None:
        provenance["panel_number"] = int(panel_number)

    asset_id = ""
    linked = False
    link_error: Optional[str] = None
    try:
        async with get_async_session() as session:
            created = await AssetHubFacade(session).create_imported_file(
                file_path=str(target),
                title=(scene_title or "3D 预演截图")[:120],
                asset_type="image",
                source=CAPTURE_SOURCE,
                metadata=provenance,
                lineage={**provenance, "project_id": project_id, "content_id": content_id},
                tags=["previs", "previs-capture", "storyboard-reference"],
            )
            asset_id = str(created.node_id)

            project = await session.get(CreativeProject, project_id)
            if project is None:
                raise ValueError(f"项目不存在：{project_id}")
            content = await session.get(ProjectContent, content_id)
            if content is None or content.project_id != project_id:
                raise ValueError(f"分镜内容不属于该项目：{content_id}")
            session.add(
                ProjectAssetLink(
                    project_id=project_id,
                    asset_id=asset_id,
                    content_id=content_id,
                    role=CAPTURE_ROLE,
                    relation=CAPTURE_RELATION,
                    metadata_json=json.dumps(provenance, ensure_ascii=False),
                )
            )
            await session.commit()
            linked = True
    except Exception as exc:  # noqa: BLE001
        if not asset_id:
            # 上传失败：既无资产也无关联，保持干净
            logger.warning("previs capture upload failed scene=%s: %s", scene_id, exc)
            raise HTTPException(status_code=503, detail=f"截图入库失败：{exc}") from exc
        # 上传成功、关联失败：保留可诊断错误与可重试入口，不假装成功
        link_error = str(exc)
        logger.warning("previs capture link failed asset=%s scene=%s: %s", asset_id, scene_id, exc)

    return {
        "success": True,
        "data": {
            "asset_id": asset_id,
            "project_id": project_id,
            "content_id": content_id,
            "role": CAPTURE_ROLE,
            "relation": CAPTURE_RELATION,
            "provenance": provenance,
            "linked": linked,
            "link_error": link_error,
            "retry_hint": (
                ""
                if linked
                else f"图片已入库（asset_id={asset_id}），但关联分镜失败；可用 POST /api/v1/creative-projects/{project_id}/assets 以同一 metadata 重试关联。"
            ),
        },
    }
