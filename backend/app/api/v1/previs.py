"""3D director previs scene API.

Previs scenes are explicitly linked to one project storyboard panel. Unlike the
free-form canvas (last-write-wins), scene saves use compare-and-swap on
`revision` so a stale editor or Agent cannot silently overwrite a camera or
object transform that another session just changed.
"""

from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.core.ffmpeg import get_ffmpeg_service
from app.core.task_queue import TaskStatus, get_task_queue
from app.db.database import SessionLocal, get_async_session
from app.db.models.creative_project import CreativeProject, ProjectAssetLink, ProjectContent
from app.db.models.previs import PrevisSceneDocument
from app.services.asset_hub import AssetHubFacade
from app.services.previs.motion_service import list_motions, motion_to_dict

logger = logging.getLogger("ylcraft.api.previs")

router = APIRouter()

#: 截图回流的关联语义：分镜参考图（design「截图回流」的固定顺序）
CAPTURE_ROLE = "storyboard_reference"
CAPTURE_RELATION = "derived_from"
CAPTURE_SOURCE = "previs_capture"

#: 允许的截图格式。浏览器 canvas 产出 PNG / WebP。
CAPTURE_EXTENSIONS = {".png", ".webp", ".jpg", ".jpeg"}

#: 批量帧导出的来源标记与允许格式（研究报告 §6 阶段 A/B）。
#: 只收 JPEG：同一份 4 秒预演的 PNG 序列是 132MB / 6.8s，JPEG(q0.92) 只有 9.4MB / 1.6s。
#: 批量帧是**过程产物**（进剪辑软件或喂生图），不像单帧截图那样需要无损保真。
EXPORT_SOURCE = "previs_frame_export"
EXPORT_EXTENSIONS = {".jpg", ".jpeg"}

#: 单次导出帧数上限。除了防滥用，也因为它决定了一次 multipart 上传的体积：
#: 600 帧 × JPEG(q0.92, 1440×900 ≈100KB) ≈ 60MB，已是单次请求的合理上限。
EXPORT_MAX_FRAMES = 600

#: 帧序列文件名模式。ffmpeg 的 image2 demuxer 要求编号**从 start_number 起连续**，
#: 所以导出时一律按上传顺序重命名为 frame_0001 起的连续编号，
#: 「这张图对应时间轴第几帧」记在 manifest.json 里，不靠文件名猜。
EXPORT_FRAME_PATTERN = "frame_%04d.jpg"
EXPORT_FRAME_START = 1


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
    """补齐场景必备字段。

    默认值口径在 `services/previs/draft_service.normalize_scene_dict`——**初稿管线的
    `proposed_scene` 也会被前端直接拿去落库**，两处口径必须一致，所以只留一份；
    这里额外保留"不是对象就 422"这一层入参校验（那是 API 的职责）。
    """
    from app.services.previs.draft_service import normalize_scene_dict

    if not isinstance(scene, dict):
        raise HTTPException(status_code=422, detail="scene must be an object")
    return normalize_scene_dict(scene)


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


#: 道具匹配只接受这几种可加载的模型文件：素材库里同名图片/视频不少，
#: 不按扩展名把一道关，初稿会写出一个"加载失败"的模型节点。
_PROP_MODEL_EXTS = (".glb", ".gltf", ".fbx", ".obj")


async def _lookup_prop_assets(props: list[str]) -> dict[str, dict[str, Any]]:
    """道具名 → 素材库里的模型资产（**只读**，不产生任何资产）。

    复用 `search_assets` 工具而不是另写一套查询：素材检索的口径（状态过滤、关键词命中）只有一份，
    这里再写一遍迟早会和它漂移。查询失败**降级成"没找到"**而不是 500——道具匹配不到只是少摆一个道具，
    不该让整个初稿生成失败。
    """
    from app.api.v1.assets import _hub_file_url
    from app.services.agent.tools.asset_tools import search_assets

    found: dict[str, dict[str, Any]] = {}
    for prop in props:
        if not prop or prop in found:
            continue
        try:
            result = await search_assets(query=prop, limit=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("初稿道具匹配失败（prop=%s）：%s", prop, exc)
            continue
        for asset in result.get("assets") or []:
            path = str(asset.get("file_path") or "")
            if path.lower().endswith(_PROP_MODEL_EXTS):
                found[prop] = {
                    "asset_id": str(asset.get("id") or ""),
                    "name": str(asset.get("title") or prop),
                    "model_url": _hub_file_url(path),
                }
                break
    return found


@router.post("/scenes/{scene_id}/draft", summary="Build a previs draft from the bound storyboard panel (read-only)")
async def draft_previs_scene(scene_id: str):
    """按该场景绑定的分镜格生成初稿。

    **只读、不落库**：产出是一批受限操作，要不要落库由预演台的
    "幽灵预览 → 人工确认 → CAS 落库"链路决定。这个接口不写任何数据，
    也没有任何副作用——包括道具匹配（只查素材库，不产生资产）。

    真正的管线在 `services/previs/draft_service.compose_previs_draft`：接口与 Agent 工具
    `generate_previs_draft` **共用同一条路**，否则"接口生成的草案"与"AI 拿到的草案"会不一致。
    这里只负责把失败原因映射成 HTTP 状态码。
    """
    from app.services.previs.draft_service import compose_previs_draft

    result = await compose_previs_draft(scene_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=int(result.get("status") or 400),
            detail=str(result.get("error") or "生成初稿失败"),
        )
    payload = {key: value for key, value in result.items() if key != "ok"}
    return {"success": True, "read_only": True, **payload}


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


# =============================================================================
# 动作资产（姿势与动作库）：只读清单
# =============================================================================


@router.get("/motions", summary="List reusable previs motion assets")
def list_previs_motions(
    carrier: Annotated[Optional[str], Query(description="载体：params / transform / bone")] = None,
    skeleton: Annotated[Optional[str], Query(description="兼容规格（参数集版本或骨架规格）")] = None,
    category: Annotated[Optional[str], Query(description="分类：移动 / 待机 / 互动 / 姿态 / 氛围")] = None,
    tag: Annotated[Optional[str], Query(description="按语义标签过滤")] = None,
    include_payload: Annotated[bool, Query(description="是否下发逐通道关键帧（清单默认不下发）")] = False,
):
    """预演动作清单。

    **默认不下发曲线**：清单是给选择器与 AI 浏览用的，只有真正要驱动某个对象时才需要
    逐通道数据。这样响应体大小与动作条数线性相关，而不是与"条数 × 通道数 × 关键帧数"相关。

    清单同时是"先查后引"的唯一依据：调用方（含 AI）应当先在这里查到动作标识与它适用的
    载体/规格，再往场景里写引用；不接受猜动作名。
    """
    with SessionLocal() as session:
        rows = list_motions(session, carrier=carrier, skeleton=skeleton, category=category, tag=tag)
        motions = [motion_to_dict(row, include_payload=include_payload) for row in rows]
    return {"success": True, "motions": motions, "total": len(motions)}


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


# ---------------------------------------------------------------------------
# 批量参考帧导出（Phase 4 阶段 A / B）
#
# 与上面单帧截图的分工，是刻意的：
# - 单帧截图：一张、要当生图结构参考，保持 PNG 无损，**入库并关联分镜**；
# - 批量导出：几十上百帧，是**过程产物**，用 JPEG 打包交付，不入库。
# 若把 96 帧都塞进素材库，素材库会被一次导出淹没，反而找不到东西。
# ---------------------------------------------------------------------------


def _export_root() -> Path:
    """批量导出的工作目录（帧序列 + 合成产物）。

    与 `_capture_dir` 分开：截图的文件由 Asset Hub 持有，这里只是过程目录。
    """
    directory = Path(__file__).resolve().parents[3] / "storage" / "uploads" / "previs-exports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _load_scene_export_basis(scene_id: str, camera_id: str) -> dict[str, Any]:
    """读出导出所需的场景事实。

    在会话内取值而不是把 ORM 行带出去：后台任务在请求结束后才跑，
    detached 实例的属性访问并不可靠。
    """
    with SessionLocal() as session:
        row = session.get(PrevisSceneDocument, scene_id)
        if not row:
            raise HTTPException(status_code=404, detail="Previs scene not found")
        scene = dict(row.scene_json or {})
        known_cameras = {
            str(camera.get("id") or "")
            for camera in (scene.get("cameras") or [])
            if isinstance(camera, dict)
        }
        normalized_camera_id = str(camera_id or "").strip()
        if normalized_camera_id and known_cameras and normalized_camera_id not in known_cameras:
            raise HTTPException(status_code=400, detail=f"场景中不存在机位：{normalized_camera_id}")
        return {
            "scene_id": str(row.id),
            "title": str(row.title or ""),
            "revision": int(row.revision or 1),
            "project_id": str(row.project_id or ""),
            "storyboard_content_id": str(row.storyboard_content_id or ""),
            "panel_number": row.panel_number,
            "camera_id": normalized_camera_id,
            "asset_ids": _scene_asset_ids(scene),
        }


def _resolve_fps(fps: float) -> float:
    return float(fps) if fps and float(fps) > 0 else 24.0


async def _save_export_frames(
    files: list[UploadFile],
    target_dir: Path,
    *,
    fps: float,
    start_frame: int,
    step: int,
) -> list[dict[str, Any]]:
    """按上传顺序把帧落盘为连续编号，返回每帧的清单。

    为什么要重命名而不是沿用客户端文件名：ffmpeg 的 image2 demuxer 按**编号连续性**
    读序列，而 step>1 时的真实帧号天然是 0、2、4…（不连续）。所以文件名只保证顺序，
    「这张图对应时间轴第几帧」记在 manifest 里，不靠文件名猜。
    """
    if not files:
        raise HTTPException(status_code=400, detail="没有收到任何帧")
    if len(files) > EXPORT_MAX_FRAMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"单次最多导出 {EXPORT_MAX_FRAMES} 帧（收到 {len(files)} 帧）；"
                "请增大步长或缩短帧范围后重试"
            ),
        )

    safe_step = max(1, int(step or 1))
    frames_dir = target_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    manifest_frames: list[dict[str, Any]] = []
    for offset, upload in enumerate(files):
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in EXPORT_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"帧格式不受支持：{suffix or '未知'}"
                    f"（允许 {'、'.join(sorted(EXPORT_EXTENSIONS))}，批量导出统一用 JPEG）"
                ),
            )
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"第 {offset + 1} 帧内容为空")
        index = EXPORT_FRAME_START + offset
        name = EXPORT_FRAME_PATTERN % index
        (frames_dir / name).write_bytes(payload)
        frame_number = int(start_frame) + offset * safe_step
        manifest_frames.append({
            "file": f"frames/{name}",
            "index": index,
            "frame": frame_number,
            "time": round(frame_number / fps, 4),
            "bytes": len(payload),
        })
    return manifest_frames


def _build_export_manifest(
    basis: dict[str, Any],
    frames: list[dict[str, Any]],
    *,
    fps: float,
    start_frame: int,
    step: int,
) -> dict[str, Any]:
    safe_step = max(1, int(step or 1))
    span_frames = (len(frames) - 1) * safe_step + 1 if frames else 0
    return {
        "source": EXPORT_SOURCE,
        "scene_id": basis["scene_id"],
        "scene_title": basis["title"],
        # 版本由服务端从场景行派生——「这批帧出自哪一版场景」不能由客户端自称
        "scene_revision": basis["revision"],
        "project_id": basis["project_id"],
        "storyboard_content_id": basis["storyboard_content_id"],
        "panel_number": basis["panel_number"],
        "camera_id": basis["camera_id"],
        "source_asset_ids": basis["asset_ids"],
        "fps": fps,
        "start_frame": int(start_frame),
        "step": safe_step,
        "frame_count": len(frames),
        "span_frames": span_frames,
        "duration_seconds": round(span_frames / fps, 4) if fps > 0 else 0.0,
        "frames": frames,
        "exported_at": datetime.utcnow().isoformat(),
        "notes": (
            "帧号对应预演台时间轴；文件名只保证顺序（ffmpeg 序列读取要求编号连续），"
            "真实帧号见每项的 frame 字段。"
        ),
    }


@router.post("/scenes/{scene_id}/export-frames", summary="批量导出参考帧（JPEG 序列打包 ZIP）")
async def export_previs_frames(
    scene_id: str,
    files: Annotated[list[UploadFile], File()],
    fps: Annotated[float, Form()] = 24.0,
    start_frame: Annotated[int, Form()] = 0,
    step: Annotated[int, Form()] = 1,
    camera_id: Annotated[str, Form()] = "",
):
    """把浏览器离线逐帧渲染出的画面打包成 ZIP。

    只打包、不编码：这条路上没有任何编码器，产出可直接进剪辑软件当参考层，
    或作为 img2img / 图生视频的结构参考。**不写入 Asset Hub**（理由见文件内分工说明）。
    """
    import tempfile

    basis = _load_scene_export_basis(scene_id, camera_id)
    fps_value = _resolve_fps(fps)

    with tempfile.TemporaryDirectory(prefix="previs-export-") as tmp:
        target_dir = Path(tmp)
        frames = await _save_export_frames(
            files, target_dir, fps=fps_value, start_frame=start_frame, step=step
        )
        manifest = _build_export_manifest(
            basis, frames, fps=fps_value, start_frame=start_frame, step=step
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for frame in frames:
                archive.write(target_dir / frame["file"], frame["file"])
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buffer.seek(0)
    filename = f"previs-frames-{basis['scene_id'][:8]}.zip"
    logger.info(
        "previs frames exported scene=%s frames=%s fps=%s",
        scene_id,
        len(frames),
        fps_value,
    )
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # 前端要在提示里显示帧数与时长，不解析 ZIP 也能拿到
            "X-Previs-Frame-Count": str(len(frames)),
            "X-Previs-Duration-Seconds": str(manifest["duration_seconds"]),
        },
    )


async def _run_previs_video_export(
    task_id: str,
    work_dir: Path,
    output_path: Path,
    fps: float,
    manifest: dict[str, Any],
) -> None:
    """后台任务：ffmpeg 合成 → Asset Hub 入库。

    合成失败与入库失败**分开报告**：视频确实产出时任务就是成功的，
    入库失败只作为结果里的 `asset_error`，不能让用户以为白跑一趟。
    """
    queue = get_task_queue()
    frames_dir = work_dir / "frames"
    frame_count = int(manifest.get("frame_count") or 0)
    await queue.update_progress(task_id, 10, f"开始合成 {frame_count} 帧 @ {fps}fps")

    try:
        await get_ffmpeg_service().images_to_video(
            frames_dir,
            output_path,
            fps=fps,
            pattern=EXPORT_FRAME_PATTERN,
            start_number=EXPORT_FRAME_START,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("previs video compose failed task=%s", task_id)
        task = await queue.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = f"视频合成失败：{exc}"
            task.completed_at = time.time()
            await queue.update_task(task)
        return

    await queue.update_progress(task_id, 70, "视频已合成，正在入库")

    provenance: dict[str, Any] = {
        "source": EXPORT_SOURCE,
        "previs_scene_id": manifest.get("scene_id") or "",
        "scene_revision": manifest.get("scene_revision"),
        "camera_id": manifest.get("camera_id") or "",
        "fps": fps,
        "start_frame": manifest.get("start_frame"),
        "step": manifest.get("step"),
        "frame_count": frame_count,
        "duration_seconds": manifest.get("duration_seconds"),
    }
    asset_id = ""
    asset_error = ""
    try:
        async with get_async_session() as session:
            created = await AssetHubFacade(session).create_imported_file(
                file_path=str(output_path),
                title=(str(manifest.get("scene_title") or "") or "3D 预演视频")[:120],
                asset_type="video",
                source=EXPORT_SOURCE,
                metadata=provenance,
                lineage={
                    **provenance,
                    "project_id": manifest.get("project_id") or "",
                    "content_id": manifest.get("storyboard_content_id") or "",
                },
                tags=["previs", "previs-export", "previs-video"],
            )
            asset_id = str(created.node_id)
    except Exception as exc:  # noqa: BLE001
        asset_error = str(exc)
        logger.warning("previs video asset import failed task=%s: %s", task_id, exc)

    download_url = ""
    try:
        from app.services.asset_file_resolver import to_asset_download_url

        download_url = to_asset_download_url(output_path)
    except Exception:  # noqa: BLE001
        download_url = ""

    task = await queue.get_task(task_id)
    if task:
        task.status = TaskStatus.DONE
        task.progress = 100
        task.progress_message = (
            "预演视频已合成并入库" if asset_id else "预演视频已合成（入库失败）"
        )
        task.result = {
            "scene_id": manifest.get("scene_id") or "",
            "scene_revision": manifest.get("scene_revision"),
            "frame_count": frame_count,
            "fps": fps,
            "duration_seconds": manifest.get("duration_seconds"),
            "file_path": str(output_path),
            "download_url": download_url,
            "asset_id": asset_id,
            "asset_error": asset_error,
        }
        task.completed_at = time.time()
        await queue.update_task(task)

    # 帧序列是中间产物：合成成功后删掉，避免每次都留一份几十 MB 的残留。
    # 失败时不删（上面已 return），留给人排查。
    try:
        for frame_file in frames_dir.glob("*"):
            frame_file.unlink()
        frames_dir.rmdir()
    except Exception:  # noqa: BLE001
        logger.debug("previs export frame cleanup skipped: %s", frames_dir)


@router.post("/scenes/{scene_id}/export-video", summary="服务端合成预演视频（异步任务，真 24fps）")
async def export_previs_video(
    scene_id: str,
    background: BackgroundTasks,
    files: Annotated[list[UploadFile], File()],
    fps: Annotated[float, Form()] = 24.0,
    start_frame: Annotated[int, Form()] = 0,
    step: Annotated[int, Form()] = 1,
    camera_id: Annotated[str, Form()] = "",
):
    """接收浏览器离线逐帧渲染的 JPEG 序列，交给服务端 ffmpeg 按固定帧率合成。

    为什么不是浏览器实时录制：`MediaRecorder` 按**墙上时钟**打时间戳，
    视口稳定不了 24fps 就会录出时长漂移的视频（实测播放时 17% 的帧超预算，
    并行编码时 35% 超预算）。这里每一帧都来自调用方指定的帧号，
    配 `-framerate` 后输出帧率必然正确。依据见
    `docs/research/research_report_previs_export_feasibility.md` §四/§五。
    """
    basis = _load_scene_export_basis(scene_id, camera_id)
    fps_value = _resolve_fps(fps)

    export_id = uuid4().hex
    target_dir = _export_root() / export_id
    frames = await _save_export_frames(
        files, target_dir, fps=fps_value, start_frame=start_frame, step=step
    )
    manifest = _build_export_manifest(
        basis, frames, fps=fps_value, start_frame=start_frame, step=step
    )
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    queue = get_task_queue()
    task = await queue.create_task(
        task_type="previs_export_video",
        payload={
            "project_id": basis["project_id"],
            "scene_id": scene_id,
            "scene_revision": basis["revision"],
            "camera_id": basis["camera_id"],
            "fps": fps_value,
            "frame_count": len(frames),
            "export_id": export_id,
            "stage_label": "预演视频合成",
        },
    )
    output_path = target_dir / "previs-export.mp4"
    background.add_task(
        _run_previs_video_export,
        task.task_id,
        target_dir,
        output_path,
        fps_value,
        manifest,
    )
    return {
        "success": True,
        "data": {
            "task_id": task.task_id,
            "export_id": export_id,
            "scene_id": scene_id,
            "scene_revision": basis["revision"],
            "frame_count": len(frames),
            "fps": fps_value,
            "duration_seconds": manifest["duration_seconds"],
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "message": "已开始服务端合成，可在任务中心查看进度；合成完成后视频进入素材库。",
        },
    }
