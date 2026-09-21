"""Standalone configured-provider image-to-3D workspace API."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, cast
from sqlmodel import select

from app.db.database import get_async_session
from app.db.models.ai_connector import AIConnector
from app.db.models.asset_hub import AssetRelation, AssetRepresentation, AssetType, AssetVersion, RelationType
from app.db.models.task import Model3DGenerationTask
from app.core.external_api_auth import optional_external_api_key
from app.db.models.external_api_key import ExternalApiKey
from app.core.blender import BlenderService
from app.core.task_queue import TaskStatus, get_task_queue
from app.services.asset_file_resolver import resolve_storage_path
from app.services.asset_hub import AssetHubFacade
from app.services.cos_storage import load_cos_service
from app.services.model3d.service import Model3DService
from app.services.model3d.workspace import Model3DConnectorBackend, Model3DProviderRequestError
from app.services.platform_log import service as platform_log

logger = logging.getLogger("ylcraft.api.model3d_workspace")

router = APIRouter()


class Model3DGenerateRequest(BaseModel):
    prompt: str = ""
    provider: str
    model: str = ""
    source_asset_id: Optional[str] = None
    source_image: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)


class Model3DRigRequest(BaseModel):
    """Auto-rigging submission: skeleton-only or skeleton + one preset motion."""

    provider: str
    source_asset_id: Optional[str] = None
    source_url: Optional[str] = None
    motion_type: Optional[int] = Field(default=None, ge=1, le=48)
    file_type: Optional[str] = None


class Model3DTaskResponse(BaseModel):
    success: bool = True
    task_id: str
    status: str
    progress: int = 0
    progress_message: str = ""
    provider: str = ""
    model: str = ""
    url: Optional[str] = None
    asset_id: Optional[str] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


def _task_dict(task: Model3DGenerationTask) -> dict[str, Any]:
    def parse(value: str) -> dict[str, Any]:
        try:
            result = json.loads(value or "{}")
            return result if isinstance(result, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {
        "task_id": task.task_id, "kind": task.kind, "provider": task.provider, "model": task.model,
        "status": task.status, "prompt": task.prompt, "request": parse(task.request_json),
        "result": parse(task.result_json), "asset_id": task.asset_id, "error": task.error,
        "progress": task.progress, "progress_message": task.progress_message,
        "created_at": task.created_at,
    }


def _result_payload(result: dict[str, Any], provider_task_id: str = "") -> dict[str, Any]:
    """Keep provider task identifiers out of the durable local primary key."""
    payload = dict(result)
    if provider_task_id:
        payload["provider_task_id"] = provider_task_id
    return payload


def _source_image_summary(raw: str) -> str:
    """参考图入参摘要：http URL 原样、base64 data URL 记类型与长度。"""
    if not raw:
        return ""
    if raw.startswith("data:"):
        prefix = raw.split(",", 1)[0] if "," in raw else "data"
        return f"{prefix}(len={len(raw)})"
    return raw


def _model3d_log_request(req) -> dict:
    """事件日志「调用详情」：含描述、来源方式与参考图摘要，不含图片二进制。"""
    return {
        "prompt": req.prompt,
        "model": req.model or "",
        "source_asset_id": req.source_asset_id or "",
        "source_image": _source_image_summary(req.source_image or ""),
        "options": req.options or {},
    }


async def _resolve_source(asset_id: str | None, source_image: str | None) -> tuple[str, str, str | None]:
    if source_image:
        if source_image.startswith("data:"):
            return source_image, "", None
        return "", source_image, None
    if not asset_id:
        return "", "", None
    async with get_async_session() as session:
        row = (await session.execute(
            select(AssetRepresentation.file_path)
            .join(AssetVersion, AssetRepresentation.asset_version_id == AssetVersion.id)
            .where(AssetVersion.asset_node_id == asset_id)
            .order_by(AssetVersion.version_number.desc())
            .limit(1)
        )).scalar_one_or_none()
    if not row:
        raise ValueError("该素材没有可用的本地图片文件")
    # 与绑骨那条路同理：库里是相对存储路径，按项目根解析，
    # 不要拿相对路径去撞服务进程的工作目录。
    path = resolve_storage_path(row)
    if not path.is_file():
        raise ValueError(f"该素材的本地图片文件不存在：{row}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}", "", asset_id


def _connector_capability(row: AIConnector) -> str:
    """Capability declared by the connector's response_config; default generation."""
    try:
        config = json.loads(row.response_config or "{}")
    except (TypeError, ValueError):
        config = {}
    return str(config.get("capability") or "generation")


async def _connector(name: str, capability: Optional[str] = "generation") -> AIConnector:
    async with get_async_session() as session:
        row = (await session.execute(
            select(AIConnector).where(
                AIConnector.name == name,
                cast(AIConnector.provider_type, String) == "3d",
                AIConnector.is_active == True,
            ).limit(1)
        )).scalars().first()
    if row is None:
        raise ValueError("未找到启用的 3D 连接器")
    if capability and _connector_capability(row) != capability:
        raise ValueError(f"连接器“{name}”不是{_CAPABILITY_LABELS.get(capability, capability)}连接器")
    return row


_CAPABILITY_LABELS = {"generation": "图生/文生 3D", "rigging": "绑骨蒙皮"}


def _selected_model(connector: AIConnector, requested_model: str) -> str:
    """Keep the connector's configured model list authoritative for API callers too."""
    available = list(dict.fromkeys(model for model in connector.get_available_models() if model))
    model = (requested_model or connector.default_model or "").strip()
    if available and model not in available:
        raise ValueError(f"模型 {model} 未在图生 3D 连接器“{connector.name}”的可用模型中声明")
    if not model:
        raise ValueError("图生 3D 连接器必须配置默认模型或可用模型")
    return model


def _rigging_flags(details: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Derive skeleton/animation flags + tags from extracted model metadata."""
    animations = details.get("animations")
    has_animations = bool(animations)
    has_bones = bool(details.get("bones"))
    flags = {"has_bones": has_bones, "has_animations": has_animations}
    tags = (["rigged"] if has_bones else []) + (["animated"] if has_animations else [])
    return flags, tags


async def _import_result(task: Model3DGenerationTask, result: dict[str, Any]) -> str | None:
    if task.asset_id or not result.get("url"):
        return task.asset_id
    connector = await _connector(task.provider, capability=None)
    backend = Model3DConnectorBackend(connector)
    path = await backend.download(result["url"], task.task_id)
    thumbnail = await backend.download_preview(result.get("preview_url") or "", task.task_id)
    metadata = json.loads(task.request_json or "{}")
    details = await Model3DService(None).extract_metadata(str(path))
    if not isinstance(details, dict) or details.get("error"):
        details = {}
    kind = task.kind or "generation"
    source_label = "rigging" if kind == "rigging" else "image_to_3d"
    rigging_flags, rigging_tags = _rigging_flags(details)
    async with get_async_session() as session:
        created = await AssetHubFacade(session).create_imported_file(
            file_path=str(path), title=metadata.get("title") or task.prompt or path.stem,
            asset_type=AssetType.THREE_D_MODEL, source=source_label,
            source_url=result["url"], thumbnail_url=thumbnail or "",
            metadata={"prompt": task.prompt, "provider": task.provider, "model": task.model,
                      "task_id": task.task_id, "source_asset_id": metadata.get("source_asset_id"),
                      "motion_type": metadata.get("motion_type"), **details, **rigging_flags},
            lineage={"source": source_label, "task_id": task.task_id,
                     "source_asset_id": metadata.get("source_asset_id")},
            tags=["ai-generated", source_label, task.provider, task.model, *rigging_tags],
        )
        asset_id = created.node_id
        source_asset_id = metadata.get("source_asset_id")
        if source_asset_id:
            session.add(AssetRelation(
                id=str(uuid4()), source_id=asset_id, target_id=source_asset_id,
                relation_type=RelationType.DERIVED_FROM,
                context_json={"task_id": task.task_id, "provider": task.provider, "model": task.model},
            ))
    return asset_id


DEFAULT_POLL_INTERVAL_SECONDS = 10


def _poll_interval_seconds(response_config: dict[str, Any] | None) -> int:
    """Read the connector's declared poll cadence; fall back to a sane default."""
    try:
        value = int((response_config or {}).get("poll_interval", DEFAULT_POLL_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL_SECONDS
    return value if value > 0 else DEFAULT_POLL_INTERVAL_SECONDS


def _backend_entry(row: AIConnector) -> dict[str, Any]:
    response_config: dict[str, Any] = {}
    try:
        response_config = json.loads(row.response_config or "{}")
    except (TypeError, ValueError):
        response_config = {}
    motion_types = response_config.get("motion_types")
    return {
        "name": row.name,
        "model": row.default_model,
        "available_models": row.get_available_models() or [row.default_model],
        "poll_interval": _poll_interval_seconds(response_config),
        "capability": str(response_config.get("capability") or "generation"),
        "motion_types": motion_types if isinstance(motion_types, list) else [],
        "no_model_selector": bool(response_config.get("no_model_selector", False)),
    }


@router.get("/backends", summary="Configured 3D connectors (generation / rigging)")
async def list_model3d_backends(capability: Optional[str] = Query(default=None)):
    async with get_async_session() as session:
        rows = (await session.execute(select(AIConnector).where(
            cast(AIConnector.provider_type, String) == "3d", AIConnector.is_active == True
        ).order_by(AIConnector.priority))).scalars().all()
    entries = [_backend_entry(row) for row in rows]
    if capability:
        entries = [entry for entry in entries if entry["capability"] == capability]
    return {"success": True, "backends": entries}


@router.post("/generate", response_model=Model3DTaskResponse, summary="Submit configured image-to-3D task")
async def generate_model3d(req: Model3DGenerateRequest, external_key: Optional[ExternalApiKey] = Depends(optional_external_api_key)):
    try:
        source_data, source_url, source_asset_id = await _resolve_source(req.source_asset_id, req.source_image)
        if not (source_data or source_url or req.prompt.strip()):
            raise ValueError("请输入文生 3D 描述，或选择参考图片")
        connector = await _connector(req.provider)
        selected_model = _selected_model(connector, req.model)
        result = await Model3DConnectorBackend(connector).submit(
            prompt=req.prompt, source_image=source_data, source_url=source_url, model=selected_model,
            options=req.options)
        provider_task_id = str(result.get("task_id") or "")
        # Provider ids can be opaque encoded payloads. The durable task ledger
        # uses its own short identifier and stores the original for polling.
        task_id = f"model3d_{uuid4().hex}"
        now = time.time()
        task = Model3DGenerationTask(task_id=task_id, provider=connector.name, model=selected_model,
            status=result["status"], prompt=req.prompt,
            request_json=json.dumps({"source_asset_id": source_asset_id, "source_url": source_url,
                                     "title": req.prompt, "options": req.options}, ensure_ascii=False),
            result_json=json.dumps(_result_payload(result, provider_task_id), ensure_ascii=False), error=result.get("error"),
            progress=result.get("progress", 0), created_at=now, updated_at=now)
        if result["status"] == "done":
            task.asset_id = await _import_result(task, result)
            task.completed_at = now
        async with get_async_session() as session:
            session.add(task)
        await platform_log.record_event(
            scene="model3d",
            task_type="model3d_generation",
            task_id=task_id,
            level="error" if result["status"] == "error" else "info",
            status="failed" if result["status"] == "error" else ("success" if result["status"] == "done" else "pending"),
            provider=connector.name,
            model=selected_model,
            message="图转 3D 生成完成" if result["status"] == "done" else "图转 3D 任务已提交",
            error=result.get("error"),
            request=_model3d_log_request(req),
            response={"status": result.get("status"), "url": result.get("url"), "asset_id": task.asset_id},
            duration_ms=result.get("latency_ms") or 0,
            project_id=None,
            retry_payload=_rig_retry_payload(req),
        )
        return Model3DTaskResponse(task_id=task_id, status=task.status, progress=task.progress,
            provider=task.provider, model=task.model, url=result.get("url"), asset_id=task.asset_id,
            diagnostics=result.get("diagnostics") or {}, error=task.error)
    except Model3DProviderRequestError as exc:
        await platform_log.record_event(
            scene="model3d", task_type="model3d_generation", level="error", status="failed",
            provider=req.provider, model=req.model, message="图转 3D 生成失败", error=str(exc),
            request=_model3d_log_request(req),
            response={"error": str(exc)},
            retry_payload=_rig_retry_payload(req),
        )
        return Model3DTaskResponse(success=False, task_id="", status="error", diagnostics=exc.diagnostics, error=str(exc))
    except Exception as exc:
        await platform_log.record_event(
            scene="model3d", task_type="model3d_generation", level="error", status="failed",
            provider=req.provider, model=req.model, message="图转 3D 生成异常", error=str(exc),
            request=_model3d_log_request(req),
            response={"error": str(exc)},
            retry_payload=_rig_retry_payload(req),
        )
        return Model3DTaskResponse(success=False, task_id="", status="error", error=str(exc))


@router.get("/tasks/{task_id}", response_model=Model3DTaskResponse, summary="Poll image-to-3D task")
async def poll_model3d_task(task_id: str):
    async with get_async_session() as session:
        task = await session.get(Model3DGenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown image-to-3D task")
    if task.status == "cancelled":
        return Model3DTaskResponse(task_id=task_id, status="cancelled", progress=task.progress or 0,
            provider=task.provider, model=task.model, asset_id=task.asset_id,
            error=task.error or "已取消")
    try:
        try:
            prior_result = json.loads(task.result_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            prior_result = {}
        provider_task_id = str(prior_result.get("provider_task_id") or task_id)
        result = await Model3DConnectorBackend(await _connector(task.provider, capability=None)).poll(provider_task_id)
        if result["status"] == "done":
            task.asset_id = await _import_result(task, result)
            task.completed_at = time.time()
        task.status, task.progress, task.error = result["status"], result.get("progress", 0), result.get("error")
        task.result_json, task.updated_at = json.dumps(_result_payload(result, provider_task_id), ensure_ascii=False), time.time()
        async with get_async_session() as session:
            persisted = await session.get(Model3DGenerationTask, task_id)
            for field in ("status", "progress", "error", "result_json", "updated_at", "completed_at", "asset_id"):
                setattr(persisted, field, getattr(task, field))
        return Model3DTaskResponse(task_id=task_id, status=task.status, progress=task.progress,
            provider=task.provider, model=task.model, url=result.get("url"), asset_id=task.asset_id,
            diagnostics=result.get("diagnostics") or {}, error=task.error)
    except Model3DProviderRequestError as exc:
        async with get_async_session() as session:
            persisted = await session.get(Model3DGenerationTask, task_id)
            if persisted:
                persisted.status = "error"
                persisted.error = str(exc)
                persisted.result_json = json.dumps({"diagnostics": exc.diagnostics}, ensure_ascii=False)
                persisted.updated_at = time.time()
                persisted.completed_at = persisted.updated_at
        return Model3DTaskResponse(success=False, task_id=task_id, status="error", provider=task.provider,
            model=task.model, diagnostics=exc.diagnostics, error=str(exc))
    except Exception as exc:
        return Model3DTaskResponse(success=False, task_id=task_id, status="error", error=str(exc), provider=task.provider, model=task.model)


@router.get("/history", summary="Durable 3D workspace history")
async def model3d_history(
    limit: int = Query(default=30, ge=1, le=100),
    kind: Optional[str] = Query(default=None),
):
    async with get_async_session() as session:
        statement = select(Model3DGenerationTask)
        if kind:
            statement = statement.where(Model3DGenerationTask.kind == kind)
        rows = (await session.execute(statement.order_by(
            Model3DGenerationTask.created_at.desc()).limit(limit))).scalars().all()
    return {"success": True, "data": [_task_dict(row) for row in rows], "total": len(rows)}


# =============================================================================
# Auto-rigging (绑骨蒙皮): skeleton-only or skeleton + preset motion
# =============================================================================

_RIG_SOURCE_EXTENSIONS = {".glb": "GLB", ".fbx": "FBX"}

#: 腾讯混元绑骨接口的源文件上限。本地先拦住：
#: 否则要提交一次、轮询一轮，才从远端得知"文件太大"。
#: （实测素材库里已有一个 75MB 的模型，点了才知道不行。）
_RIG_SOURCE_MAX_BYTES = 60 * 1024 * 1024


def _assert_rig_source_size(path: Path) -> None:
    """校验绑骨源文件的大小上限（腾讯混元的硬限制）。

    抽成纯函数是为了能单测：这条校验一旦失效，代价是"提交了、轮询了，
    最后远端才说文件太大"，白等一轮。
    """
    size = path.stat().st_size
    if size > _RIG_SOURCE_MAX_BYTES:
        limit_mb = _RIG_SOURCE_MAX_BYTES / (1024 * 1024)
        raise ValueError(
            f"该模型 {size / 1024 / 1024:.1f}MB，超过绑骨上限 {limit_mb:.0f}MB"
            "（图生 3D 默认出 50 万面高模，很容易顶到）；请先减面或转格式再绑骨"
        )


def _model3d_public_dir() -> Path:
    """Directory served at /model3d-files so providers can fetch source models."""
    directory = Path(__file__).resolve().parents[3] / "storage" / "model3d" / "public"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _resolve_rig_source(
    source_asset_id: str | None, source_url: str | None, base_url: str,
) -> tuple[str, str, str | None]:
    """Return (public_model_url, file_type, source_asset_id) for a rigging job.

    Tencent auto-rigging only accepts a publicly reachable FBX/GLB URL. When
    COS is configured the local model is uploaded and a time-limited signed
    URL is returned (matches the "URL valid for 24h" requirement); otherwise
    the file is copied into the statically served /model3d-files directory and
    exposed via BASE_URL (falling back to the request base URL).
    """
    if source_url:
        suffix = Path(source_url.split("?", 1)[0]).suffix.lower()
        return source_url, _RIG_SOURCE_EXTENSIONS.get(suffix, "GLB"), None
    if not source_asset_id:
        raise ValueError("请选择要绑骨的 3D 模型素材，或提供模型文件 URL")
    async with get_async_session() as session:
        row = (await session.execute(
            select(AssetRepresentation.file_path)
            .join(AssetVersion, AssetRepresentation.asset_version_id == AssetVersion.id)
            .where(AssetVersion.asset_node_id == source_asset_id)
            .order_by(AssetVersion.version_number.desc())
            .limit(1)
        )).scalar_one_or_none()
    if not row:
        raise ValueError("该素材没有可用的本地模型文件")
    # 库里存的是**相对**存储路径（如 `backend/storage/...`），必须按项目根解析，
    # 不能拿相对路径直接 `Path(...).is_file()`——那样解析的是服务进程的工作目录，
    # 一旦不是项目根就永远找不到文件（实测就是这么报「没有可用的本地模型文件」的）。
    path = resolve_storage_path(row)
    if not path.is_file():
        raise ValueError(f"该素材的本地模型文件不存在：{row}")
    file_type = _RIG_SOURCE_EXTENSIONS.get(path.suffix.lower())
    if not file_type:
        raise ValueError("绑骨蒙皮仅支持 GLB/FBX 模型（≤60MB，人形需 A-Pose/T-Pose）")

    # 大小上限本地先拦。注意这只覆盖"选素材"这条路：直接给 source_url 时
    # 文件不在本机，无从判断大小，只能交给远端。
    _assert_rig_source_size(path)

    # 优先：COS 已配置 → 上传本地模型，返回临时签名 URL（24h 有效）
    cos = await load_cos_service()
    if cos:
        key = f"model3d/rig/{source_asset_id}{path.suffix.lower()}"
        await cos.upload_file(key, path)
        return cos.signed_url(key, expires=86400), file_type, source_asset_id

    # 回退：/model3d-files 静态目录 + BASE_URL（仅当后端公网可达时有效）
    public_path = _model3d_public_dir() / f"{source_asset_id}{path.suffix.lower()}"
    if not public_path.is_file() or public_path.stat().st_size != path.stat().st_size:
        shutil.copyfile(path, public_path)
    public_base = (os.getenv("BASE_URL") or "").rstrip("/") or base_url.rstrip("/")
    return f"{public_base}/model3d-files/public/{public_path.name}", file_type, source_asset_id


def _rig_retry_payload(req: Model3DRigRequest) -> dict[str, Any]:
    """绑骨任务的可重放参数。

    只取 `Model3DRigRequest` 真正拥有的字段——这段代码原先照抄 `/generate`，
    引用了 `req.prompt` / `req.model` / `req.source_image` / `req.options`，
    而这四个绑骨请求里都没有。后果很隐蔽：**绑骨一出错，错误处理自己先抛
    AttributeError**，真正的失败原因被吞掉，用户只看到一个没有信息的 500，
    平台日志里也留不下任何痕迹（事件根本没记上）。
    """
    return {
        "provider": req.provider,
        "source_asset_id": req.source_asset_id,
        "source_url": req.source_url,
        "motion_type": req.motion_type,
        "file_type": req.file_type,
    }


@router.post("/rig", response_model=Model3DTaskResponse, summary="Submit auto-rigging task (skeleton-only or preset motion)")
async def rig_model3d(req: Model3DRigRequest, request: Request):
    """Submit an auto-rigging job for an existing 3D model.

    `motion_type` omitted -> skeleton-only rigging; `motion_type` 1-48 -> bind
    one Hunyuan preset motion (idle/walk/run/dance etc.).
    """
    try:
        base_url = str(request.base_url)
        source_url, file_type, source_asset_id = await _resolve_rig_source(
            req.source_asset_id, req.source_url, base_url)
        connector = await _connector(req.provider, capability="rigging")
        selected_model = (connector.default_model or "auto-rigging").strip()
        options: dict[str, Any] = {"FileType": (req.file_type or file_type).upper()}
        if req.motion_type is not None:
            options["MotionType"] = req.motion_type
        result = await Model3DConnectorBackend(connector).submit(
            prompt="", source_image="", source_url=source_url, model=selected_model, options=options)
        provider_task_id = str(result.get("task_id") or "")
        task_id = f"model3d_{uuid4().hex}"
        now = time.time()
        task = Model3DGenerationTask(task_id=task_id, kind="rigging", provider=connector.name,
            model=selected_model, status=result["status"],
            prompt=f"绑骨蒙皮（动作 {req.motion_type}）" if req.motion_type else "绑骨蒙皮（仅骨骼）",
            request_json=json.dumps({"source_asset_id": source_asset_id, "source_url": source_url,
                                     "motion_type": req.motion_type, "file_type": file_type,
                                     "options": options}, ensure_ascii=False),
            result_json=json.dumps(_result_payload(result, provider_task_id), ensure_ascii=False),
            error=result.get("error"), progress=result.get("progress", 0), created_at=now, updated_at=now)
        if result["status"] == "done":
            task.asset_id = await _import_result(task, result)
            task.completed_at = now
        async with get_async_session() as session:
            session.add(task)
        await platform_log.record_event(
            scene="model3d",
            task_type="model3d_generation",
            task_id=task_id,
            level="error" if result["status"] == "error" else "info",
            status="failed" if result["status"] == "error" else ("success" if result["status"] == "done" else "pending"),
            provider=connector.name,
            model=selected_model,
            message="绑骨完成" if result["status"] == "done" else "绑骨任务已提交",
            error=result.get("error"),
            project_id=None,
            retry_payload=_rig_retry_payload(req),
        )
        return Model3DTaskResponse(task_id=task_id, status=task.status, progress=task.progress,
            provider=task.provider, model=task.model, url=result.get("url"), asset_id=task.asset_id,
            diagnostics=result.get("diagnostics") or {}, error=task.error)
    except Model3DProviderRequestError as exc:
        await platform_log.record_event(
            scene="model3d", task_type="model3d_generation", level="error", status="failed",
            provider=req.provider, model="", message="绑骨提交失败", error=str(exc),
            retry_payload=_rig_retry_payload(req),
        )
        return Model3DTaskResponse(success=False, task_id="", status="error", diagnostics=exc.diagnostics, error=str(exc))
    except Exception as exc:
        # 先留一条本地日志：平台日志写不进去（或这段本身再出错）时，
        # 至少诊断不会变成"一个没有任何信息的 500"。
        logger.exception("[model3d] rig submit failed: provider=%s", req.provider)
        await platform_log.record_event(
            scene="model3d", task_type="model3d_generation", level="error", status="failed",
            provider=req.provider, model="", message="绑骨提交异常", error=str(exc),
            retry_payload=_rig_retry_payload(req),
        )
        return Model3DTaskResponse(success=False, task_id="", status="error", error=str(exc))


# =============================================================================
# 通用动作库（把另一个模型的动作套到目标模型上）
# =============================================================================


class Model3DRetargetRequest(BaseModel):
    """把 `source_asset_id` 的动作套到 `target_asset_id` 的骨架上。

    `clip` 为空时取来源模型的第一段动作；注意产物里会带上来源模型的**全部**
    动作（见 `retarget_bake.py` 的说明），`clip` 只是用来定位与校验。
    """

    target_asset_id: str
    source_asset_id: str
    clip: Optional[str] = None
    title: Optional[str] = None


def _model3d_retarget_dir() -> Path:
    directory = Path(__file__).resolve().parents[3] / "storage" / "model3d" / "retarget"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _resolve_asset_model_path(asset_id: str) -> Path:
    """取素材的本地模型文件（相对路径按项目根解析）。"""
    async with get_async_session() as session:
        row = (await session.execute(
            select(AssetRepresentation.file_path)
            .join(AssetVersion, AssetRepresentation.asset_version_id == AssetVersion.id)
            .where(AssetVersion.asset_node_id == asset_id)
            .order_by(AssetVersion.version_number.desc())
            .limit(1)
        )).scalar_one_or_none()
    if not row:
        raise ValueError("该素材没有可用的本地模型文件")
    path = resolve_storage_path(row)
    if not path.is_file():
        raise ValueError(f"该素材的本地模型文件不存在：{row}")
    return path


def _suggested_map(report_path: Path) -> dict:
    """从骨骼报告里取出自动推断的 Mixamo 对应关系。"""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    armatures = report.get("armatures") or []
    if not armatures:
        return {}
    return armatures[0].get("suggested_map") or {}


async def _run_retarget(
    task_id: str,
    target_path: Path,
    source_path: Path,
    target_asset_id: str,
    source_asset_id: str,
    clip: str,
    title: str,
) -> None:
    """后台执行：必要时统一骨架命名 → 烘焙动作 → 入库。"""
    queue = get_task_queue()
    try:
        await queue.update_progress(task_id, 8, "检查目标骨架命名")
        blender = BlenderService()
        if not await blender.is_available():
            raise RuntimeError("Blender 不可用，无法套用动作（请先安装 Blender 或设置 BLENDER_PATH）")

        work_dir = _model3d_retarget_dir() / uuid4().hex
        work_dir.mkdir(parents=True, exist_ok=True)

        bake_target = target_path
        upright_note = ""
        # 扶正必须排在**套动作之前**：有些模型的绑定姿势是躺着的（实测 BrainStem
        # 的 rest 高度 2.00 / 动画中 2.78，靠自带动画把自己扶起来）。不先扶正，
        # 骨骼按新动作摆位、网格却被拽回那个躺着的骨架，模型当场躺平。
        # 脚本会自己按阈值判断，正常站姿的模型不会被碰。
        await queue.update_progress(task_id, 14, "检查绑定姿势")
        try:
            upright_path = work_dir / f"{target_path.stem}_upright{target_path.suffix}"
            needed, upright_note = await blender.upright(target_path, upright_path)
            if needed and upright_path.exists():
                bake_target = upright_path
            else:
                upright_note = ""
        except Exception as exc:  # noqa: BLE001
            # 扶正是"尽力而为"的准备步骤：判断不出来不该把整个套用流程拦下
            logger.warning("[model3d] upright skipped: %s", exc)

        if not Model3DService.is_mixamo_skeleton(str(target_path)):
            await queue.update_progress(task_id, 30, "目标骨架不是 Mixamo 命名，先统一")
            report_path = work_dir / "skeleton.json"
            await blender.skeleton_report(bake_target, report_path)
            mapping = _suggested_map(report_path)
            if not mapping:
                raise RuntimeError(
                    "看不出这个模型的骨骼怎么对应到人形部位，无法自动套用；"
                    "它需要人工整理骨架后再试"
                )
            renamed = work_dir / f"{target_path.stem}_mixamo{target_path.suffix}"
            await blender.convert_format(bake_target, renamed, bone_map=mapping)
            bake_target = renamed

        await queue.update_progress(task_id, 55, "烘焙动作到目标骨架")
        output = work_dir / f"{target_path.stem}_retarget{target_path.suffix}"
        diagnostic = await blender.retarget_bake(bake_target, source_path, clip, output)

        await queue.update_progress(task_id, 78, "生成预览图")
        preview = ""
        try:
            preview = str(
                await Model3DService(None).generate_preview(
                    str(output), str(work_dir / "preview.png")
                )
                or ""
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[model3d] retarget preview failed: %s", exc)

        await queue.update_progress(task_id, 92, "写入素材库")
        details = await Model3DService(None).extract_metadata(str(output))
        if not isinstance(details, dict) or details.get("error"):
            details = {}
        rigging_flags, rigging_tags = _rigging_flags(details)

        async with get_async_session() as session:
            created = await AssetHubFacade(session).create_imported_file(
                file_path=str(output),
                title=(title or f"{target_path.stem} · 动作库")[:120],
                asset_type=AssetType.THREE_D_MODEL,
                source="retarget",
                thumbnail_url=preview,
                metadata={
                    "target_asset_id": target_asset_id,
                    "source_asset_id": source_asset_id,
                    "clip": clip,
                    **details,
                    **rigging_flags,
                },
                tags=["retarget", "3d_model", *rigging_tags],
            )
            node_id = created.node_id
            # 两条溯源：动作来自谁、骨架来自谁
            session.add(AssetRelation(
                id=str(uuid4()), source_id=node_id, target_id=source_asset_id,
                relation_type=RelationType.DERIVED_FROM,
                context_json={"task_id": task_id, "role": "motion_source", "clip": clip},
            ))
            session.add(AssetRelation(
                id=str(uuid4()), source_id=node_id, target_id=target_asset_id,
                relation_type=RelationType.DERIVED_FROM,
                context_json={"task_id": task_id, "role": "skeleton_source"},
            ))
            await session.commit()

        current = await queue.get_task(task_id)
        if current:
            current.status = TaskStatus.DONE
            current.progress = 100
            current.progress_message = "动作已套用"
            current.result = {
                "asset_id": node_id,
                "diagnostic": diagnostic,
                # 扶正过就在这里留痕：以后遇到"套上就躺着"，看这一行即可定性
                "upright": upright_note,
            }
            current.completed_at = time.time()
            await queue.update_task(current)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[model3d] retarget failed: task=%s", task_id)
        current = await queue.get_task(task_id)
        if current:
            current.status = TaskStatus.FAILED
            current.error = str(exc)
            current.completed_at = time.time()
            await queue.update_task(current)


@router.post("/retarget", summary="通用动作库：把另一个模型的动作套到目标模型上")
async def retarget_model3d(req: Model3DRetargetRequest, background: BackgroundTasks):
    """跨模型复用动作。

    动画是**按骨骼名**寻址的，所以两个模型只有骨骼命名对得上才能复用：目标骨架若
    不是 Mixamo 标准命名，后台会先用骨骼分析推断对应关系并统一命名，再烘焙。
    全程在任务中心里跑——Blender 一步就要十几秒，不能让请求干等。
    """
    try:
        target_path = await _resolve_asset_model_path(req.target_asset_id)
        source_path = await _resolve_asset_model_path(req.source_asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 来源自己没有动画的话，没东西可套——先说清楚，别让用户白等几十秒
    source_details = await Model3DService(None).extract_metadata(str(source_path))
    source_clips = list(source_details.get("animations") or [])
    if not source_clips:
        raise HTTPException(
            status_code=400,
            detail="动作来源模型自己没有动画，没什么可套用的；请换一个带动画的模型作为来源",
        )
    clip = (req.clip or "").strip() or str(source_clips[0])

    queue = get_task_queue()
    task = await queue.create_task(
        task_type="model3d_retarget",
        payload={
            "target_asset_id": req.target_asset_id,
            "source_asset_id": req.source_asset_id,
            "clip": clip,
            "stage_label": "套用动作库",
        },
    )
    background.add_task(
        _run_retarget,
        task.task_id,
        target_path,
        source_path,
        req.target_asset_id,
        req.source_asset_id,
        clip,
        req.title or "",
    )
    return {
        "success": True,
        "task_id": task.task_id,
        "status": task.status,
        "clip": clip,
        "message": "已开始套用动作，可在任务中心查看进度；完成后会作为新素材入库。",
    }
