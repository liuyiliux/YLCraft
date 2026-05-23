"""
YLCraft — AI 模型管理 API

GET    /api/v1/models              — 模型列表
GET    /api/v1/models/:id          — 模型详情
POST   /api/v1/models/scan         — 扫描本地模型
POST   /api/v1/models/register     — 注册模型

GET    /api/v1/models/civitai/search — 搜索 CivitAI
GET    /api/v1/models/civitai/:id  — CivitAI 模型详情
POST   /api/v1/models/civitai/download — 下载 CivitAI 模型

PUT    /api/v1/models/:id/trigger-words — 更新触发词
DELETE /api/v1/models/:id          — 删除模型
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.services.model.service import ModelService
from app.services.model.download_tracker import get_download_tracker, DownloadStatus

router = APIRouter()
logger = logging.getLogger("ylcraft.models")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_model_service():
    """获取 ModelService 实例"""
    async with get_async_session() as session:
        yield ModelService(session)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class ModelResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]

class ModelListResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]]
    total: int

class RegisterModelRequest(BaseModel):
    file_path: str = Field(..., description="模型文件路径")
    name: str = Field(..., description="模型名称")
    model_type: str = Field("Checkpoint", description="模型类型")
    base_model: str = Field("", description="基础模型")
    civitai_model_id: str = Field("", description="CivitAI 模型ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")

class DownloadCivitaiRequest(BaseModel):
    model_id: str = Field(..., description="CivitAI 模型ID")
    version_id: Optional[str] = Field(None, description="模型版本ID")
    target_directory: Optional[str] = Field(None, description="保存目录")

class UpdateTriggerWordsRequest(BaseModel):
    trigger_words: str = Field(..., description="触发词（逗号分隔）")

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.get("/models", response_model=ModelListResponse)
async def list_models(
    model_type: Optional[str] = Query(None, description="模型类型过滤"),
    base_model: Optional[str] = Query(None, description="基础模型过滤"),
    limit: int = Query(50, description="返回数量"),
    service: ModelService = Depends(get_model_service),
):
    """
    模型列表

    返回本地已注册的所有 AI 模型。
    """
    models = await service.list_models(model_type, base_model, limit)

    model_list = [
        {
            "id": m.id,
            "asset_node_id": str(m.asset_node_id),
            "name": None,  # 需要查询 AssetNode
            "model_type": m.model_type,
            "base_model": m.base_model,
            "file_hash": m.file_hash,
            "file_size": m.file_size,
            "trigger_words": m.trigger_words,
        }
        for m in models
    ]

    return {
        "success": True,
        "data": model_list,
        "total": len(model_list),
    }


@router.get("/models/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    service: ModelService = Depends(get_model_service),
):
    """
    获取模型详情
    """
    model = await service.get_model(model_id)

    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    return {
        "success": True,
        "data": {
            "id": model.id,
            "asset_node_id": str(model.asset_node_id),
            "model_type": model.model_type,
            "base_model": model.base_model,
            "file_hash": model.file_hash,
            "civitai_model_id": model.civitai_model_id,
            "civitai_version_id": model.civitai_version_id,
            "trigger_words": model.trigger_words,
            "recommended_weight": model.recommended_weight,
            "training_resolution": model.training_resolution,
            "file_path": model.file_path,
            "file_size": model.file_size,
            "preview_urls": model.preview_urls,
        },
    }


@router.post("/models/scan", response_model=ModelResponse)
async def scan_local_models(
    directory: Optional[str] = Query(None, description="扫描目录（默认使用模型存储目录）"),
    service: ModelService = Depends(get_model_service),
):
    """
    扫描本地模型目录

    发现尚未注册到数据库的新模型。
    """
    discovered = await service.scan_local_models(directory)

    return {
        "success": True,
        "data": {
            "discovered_count": len(discovered),
            "models": discovered,
        },
    }


@router.post("/models/register", response_model=ModelResponse)
async def register_model(
    request: RegisterModelRequest,
    service: ModelService = Depends(get_model_service),
):
    """
    注册模型到数据库

    将本地模型文件注册为资产中枢中的模型资产。
    """
    # 计算文件哈希
    from pathlib import Path
    file_path = Path(request.file_path)

    if not file_path.exists():
        raise HTTPException(status_code=400, detail="文件不存在")

    # 提取元数据
    metadata = await service.extract_model_metadata(str(file_path))
    if request.metadata:
        metadata.update(request.metadata)

    # 注册模型
    import hashlib
    from pathlib import Path

    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        chunk = f.read(10 * 1024 * 1024)
        sha256_hash.update(chunk)
    file_hash = sha256_hash.hexdigest()

    model = await service.register_model(
        file_path=str(file_path),
        file_hash=file_hash,
        name=request.name,
        model_type=request.model_type,
        base_model=request.base_model,
        civitai_model_id=request.civitai_model_id,
        metadata=metadata,
    )

    if not model:
        raise HTTPException(status_code=500, detail="注册失败")

    return {
        "success": True,
        "data": {
            "id": model.id,
            "name": request.name,
            "file_hash": file_hash,
        },
    }


# ---------------------------------------------------------------------------
# CivitAI 集成
# ---------------------------------------------------------------------------

@router.get("/models/civitai/search", response_model=ModelResponse)
async def search_civitai(
    query: str = Query(..., description="搜索关键词"),
    model_types: Optional[str] = Query(None, description="模型类型（逗号分隔）"),
    limit: int = Query(20, description="返回数量"),
    service: ModelService = Depends(get_model_service),
):
    """
    搜索 CivitAI 模型

    返回 CivitAI 上的公开模型列表。
    """
    types_list = model_types.split(",") if model_types else None

    results = await service.search_civitai(query, types_list, limit)

    return {
        "success": True,
        "data": {
            "query": query,
            "count": len(results),
            "models": results,
        },
    }


@router.get("/models/civitai/{model_id}", response_model=ModelResponse)
async def get_civitai_model_info(
    model_id: str,
    service: ModelService = Depends(get_model_service),
):
    """
    获取 CivitAI 模型详细信息

    返回模型的版本列表、下载链接等信息。
    """
    info = await service.get_civitai_model_info(model_id)

    if not info:
        raise HTTPException(status_code=404, detail="CivitAI 模型不存在")

    return {
        "success": True,
        "data": info,
    }


@router.post("/models/civitai/download", response_model=ModelResponse)
async def download_civitai_model(
    request: DownloadCivitaiRequest,
    service: ModelService = Depends(get_model_service),
):
    """
    下载 CivitAI 模型

    下载模型文件并注册到本地数据库。
    """
    result = await service.download_civitai_model(
        model_id=request.model_id,
        version_id=request.version_id,
        target_directory=request.target_directory,
    )

    if not result:
        raise HTTPException(status_code=500, detail="下载失败")

    return {
        "success": True,
        "data": {
            "path": result["path"],
            "hash": result["hash"],
            "model_id": result["model_record"].id if result.get("model_record") else None,
        },
    }


# ---------------------------------------------------------------------------
# 模型管理
# ---------------------------------------------------------------------------

@router.put("/models/{model_id}/trigger-words", response_model=ModelResponse)
async def update_trigger_words(
    model_id: str,
    request: UpdateTriggerWordsRequest,
    service: ModelService = Depends(get_model_service),
):
    """
    更新模型的触发词
    """
    success = await service.update_trigger_words(model_id, request.trigger_words)

    if not success:
        raise HTTPException(status_code=404, detail="模型不存在")

    return {
        "success": True,
        "data": {"trigger_words": request.trigger_words},
    }


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: str,
    delete_file: bool = Query(False, description="是否同时删除文件"),
    service: ModelService = Depends(get_model_service),
):
    """
    删除模型
    """
    success = await service.delete_model(model_id, delete_file)

    if not success:
        raise HTTPException(status_code=404, detail="模型不存在")

    return {
        "success": True,
        "data": {"message": "模型已删除"},
    }


# ---------------------------------------------------------------------------
# 下载进度查询
# ---------------------------------------------------------------------------

@router.get("/downloads/{task_id}")
async def get_download_progress(task_id: str):
    """
    获取下载进度

    返回下载任务的当前进度信息。
    """
    tracker = await get_download_tracker()
    task = await tracker.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")

    return {
        "success": True,
        "data": task,
    }


@router.get("/downloads")
async def list_downloads(
    status: Optional[str] = Query(None, description="按状态过滤"),
):
    """
    列出所有下载任务

    可以按状态过滤（downloading, completed, failed 等）。
    """
    tracker = await get_download_tracker()

    download_status = None
    if status:
        try:
            download_status = DownloadStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的状态值: {status}，有效值: pending, downloading, extracting, completed, failed, cancelled"
            )

    tasks = await tracker.list_tasks(status=download_status)

    return {
        "success": True,
        "data": tasks,
        "total": len(tasks),
    }


@router.delete("/downloads/{task_id}")
async def cancel_download(task_id: str):
    """
    取消下载任务
    """
    tracker = await get_download_tracker()
    success = await tracker.cancel_task(task_id)

    return {
        "success": success,
        "data": {"message": "下载任务已取消" if success else "取消失败"},
    }


@router.post("/downloads/cleanup")
async def cleanup_downloads(max_age_hours: int = Query(24, description="清理多少小时前的已完成任务")):
    """
    清理已完成的下载任务
    """
    tracker = await get_download_tracker()
    removed = await tracker.cleanup_completed(max_age_hours=max_age_hours)

    return {
        "success": True,
        "data": {"removed": removed},
    }
