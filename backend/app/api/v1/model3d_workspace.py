"""Standalone configured-provider image-to-3D workspace API."""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast
from sqlmodel import select

from app.db.database import get_async_session
from app.db.models.ai_connector import AIConnector
from app.db.models.asset_hub import AssetRelation, AssetRepresentation, AssetType, AssetVersion, RelationType
from app.db.models.task import Model3DGenerationTask
from app.services.asset_hub import AssetHubFacade
from app.services.model3d.service import Model3DService
from app.services.model3d.workspace import Model3DConnectorBackend, Model3DProviderRequestError

router = APIRouter()


class Model3DGenerateRequest(BaseModel):
    prompt: str = ""
    provider: str
    model: str = ""
    source_asset_id: Optional[str] = None
    source_image: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)


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
        "task_id": task.task_id, "provider": task.provider, "model": task.model,
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
    if not row or not Path(row).is_file():
        raise ValueError("该素材没有可用的本地图片文件")
    path = Path(row)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}", "", asset_id


async def _connector(name: str) -> AIConnector:
    async with get_async_session() as session:
        row = (await session.execute(
            select(AIConnector).where(
                AIConnector.name == name,
                cast(AIConnector.provider_type, String) == "3d",
                AIConnector.is_active == True,
            ).limit(1)
        )).scalars().first()
    if row is None:
        raise ValueError("未找到启用的图生 3D 连接器")
    return row


def _selected_model(connector: AIConnector, requested_model: str) -> str:
    """Keep the connector's configured model list authoritative for API callers too."""
    available = list(dict.fromkeys(model for model in connector.get_available_models() if model))
    model = (requested_model or connector.default_model or "").strip()
    if available and model not in available:
        raise ValueError(f"模型 {model} 未在图生 3D 连接器“{connector.name}”的可用模型中声明")
    if not model:
        raise ValueError("图生 3D 连接器必须配置默认模型或可用模型")
    return model


async def _import_result(task: Model3DGenerationTask, result: dict[str, Any]) -> str | None:
    if task.asset_id or not result.get("url"):
        return task.asset_id
    connector = await _connector(task.provider)
    backend = Model3DConnectorBackend(connector)
    path = await backend.download(result["url"], task.task_id)
    thumbnail = await backend.download_preview(result.get("preview_url") or "", task.task_id)
    metadata = json.loads(task.request_json or "{}")
    details = await Model3DService(None).extract_metadata(str(path))
    async with get_async_session() as session:
        created = await AssetHubFacade(session).create_imported_file(
            file_path=str(path), title=metadata.get("title") or task.prompt or path.stem,
            asset_type=AssetType.THREE_D_MODEL, source="image_to_3d",
            source_url=result["url"], thumbnail_url=thumbnail or "",
            metadata={"prompt": task.prompt, "provider": task.provider, "model": task.model,
                      "task_id": task.task_id, "source_asset_id": metadata.get("source_asset_id"), **details},
            lineage={"source": "image_to_3d", "task_id": task.task_id,
                     "source_asset_id": metadata.get("source_asset_id")},
            tags=["ai-generated", "image-to-3d", task.provider, task.model],
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
    return {
        "name": row.name,
        "model": row.default_model,
        "available_models": row.get_available_models() or [row.default_model],
        "poll_interval": _poll_interval_seconds(response_config),
    }


@router.get("/backends", summary="Configured image-to-3D connectors")
async def list_model3d_backends():
    async with get_async_session() as session:
        rows = (await session.execute(select(AIConnector).where(
            cast(AIConnector.provider_type, String) == "3d", AIConnector.is_active == True
        ).order_by(AIConnector.priority))).scalars().all()
    return {"success": True, "backends": [_backend_entry(row) for row in rows]}


@router.post("/generate", response_model=Model3DTaskResponse, summary="Submit configured image-to-3D task")
async def generate_model3d(req: Model3DGenerateRequest):
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
        return Model3DTaskResponse(task_id=task_id, status=task.status, progress=task.progress,
            provider=task.provider, model=task.model, url=result.get("url"), asset_id=task.asset_id,
            diagnostics=result.get("diagnostics") or {}, error=task.error)
    except Model3DProviderRequestError as exc:
        return Model3DTaskResponse(success=False, task_id="", status="error", diagnostics=exc.diagnostics, error=str(exc))
    except Exception as exc:
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
        result = await Model3DConnectorBackend(await _connector(task.provider)).poll(provider_task_id)
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


@router.get("/history", summary="Durable image-to-3D workspace history")
async def model3d_history(limit: int = Query(default=30, ge=1, le=100)):
    async with get_async_session() as session:
        rows = (await session.execute(select(Model3DGenerationTask).order_by(
            Model3DGenerationTask.created_at.desc()).limit(limit))).scalars().all()
    return {"success": True, "data": [_task_dict(row) for row in rows], "total": len(rows)}
