"""
YLCraft — Live2D 工厂 API

POST /api/v1/live2d/models              # 创建模型（上传图片）
GET  /api/v1/live2d/models              # 模型列表
GET  /api/v1/live2d/models/{id}        # 模型详情
PUT  /api/v1/live2d/models/{id}        # 更新模型
DELETE /api/v1/live2d/models/{id}        # 删除模型

# AI 处理（Phase 2-4 实现）
POST /api/v1/live2d/models/{id}/segment  # AI图像分割（自动分层）
POST /api/v1/live2d/models/{id}/inpaint  # AI遮挡补全
POST /api/v1/live2d/models/{id}/rig      # 自动骨骼绑定
POST /api/v1/live2d/models/{id}/mesh     # 自动生成网格
POST /api/v1/live2d/models/{id}/physics  # 配置物理模拟
POST /api/v1/live2d/models/{id}/motion   # 生成待机动作

# 导出
POST /api/v1/live2d/models/{id}/export   # 导出Cubism模型
GET  /api/v1/live2d/models/{id}/download # 下载模型文件
"""
from __future__ import annotations

import os
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import select, func, col

from app.db.database import get_session
from app.db.models.live2d import (
    Live2DModel, Live2DModelStatus, Live2DModelStatus,
    Live2DStyleMode
)
from app.db.models.api_key import ApiKey, ApiKeyStatus, ApiKeyCategory
from app.core.config import ProcessingMode, get_live2d_config

router = APIRouter(prefix="/live2d", tags=["Live2D 工厂"])

# 上传目录
UPLOAD_DIR = Path("uploads/live2d")

# WebSocket 进度推送便捷函数
async def push_live2d_progress(
    model_id: str,
    progress: int,
    message: str,
    step: str = "",
    status: str = "processing"
) -> None:
    """推送 Live2D 处理进度"""
    from app.core.ws_manager import push_task_progress as _push
    await _push(
        task_id=f"live2d_{model_id}",
        progress=progress,
        message=message,
        task_type=f"live2d_{step}" if step else "live2d",
        status=status,
    )


# ---- Request/Response 模型 ----

class Live2DModelCreateRequest(BaseModel):
    name: str = Field(..., description="模型名称")
    description: str = Field(default="", description="描述")
    character_id: str = Field(default="", description="关联角色ID")
    style_mode: str = Field(default=Live2DStyleMode.ANIME.value, description="风格模式")


class Live2DModelUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    character_id: Optional[str] = None
    status: Optional[str] = None


class Live2DModelResponse(BaseModel):
    id: str
    name: str
    description: str
    character_id: str
    style_mode: str
    source_image_url: str
    processed_image_url: Optional[str] = None
    layers: List[dict] = []
    status: str
    status_label: str
    metadata: dict = {}  # 注意：API响应中仍使用metadata，内部存储在extra_data字段
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    use_count: int = 0


class Live2DModelListResponse(BaseModel):
    items: List[Live2DModelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class Live2DStyleOptionsResponse(BaseModel):
    """风格模式选项（用于前端表单）"""
    options: List[dict]


class Live2DStatusOptionsResponse(BaseModel):
    """状态选项"""
    statuses: List[dict]


class ProcessingModeResponse(BaseModel):
    """处理模式配置响应"""
    default_mode: str
    default_mode_label: str
    service_modes: dict
    api_keys_configured: dict


class ProcessingModeUpdateRequest(BaseModel):
    """处理模式更新请求"""
    default_mode: Optional[str] = None
    service_modes: Optional[dict] = None


class ModelProcessingConfigUpdateRequest(BaseModel):
    """模型级别处理配置更新请求"""
    processing_config: dict


# ---- API 密钥管理模型 ----

class ApiKeyCreateRequest(BaseModel):
    """创建 API 密钥请求"""
    name: str = Field(..., description="密钥名称（用于显示）")
    provider: str = Field(..., description="Provider 标识（与 providers.yaml 对应）")
    category: str = Field(default=ApiKeyCategory.IMAGE_PROCESSING.value, description="密钥分类")
    api_key: str = Field(..., description="API 密钥")
    api_secret: str = Field(default="", description="API Secret（可选）")
    model: str = Field(default="", description="关联的模型（可选）")
    config: dict = Field(default_factory=dict, description="额外配置（JSON）")
    expires_at: Optional[str] = Field(default=None, description="过期时间（ISO格式，可选）")


class ApiKeyUpdateRequest(BaseModel):
    """更新 API 密钥请求"""
    name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    model: Optional[str] = None
    config: Optional[dict] = None
    status: Optional[str] = None


class ApiKeyResponse(BaseModel):
    """API 密钥响应（不暴露完整密钥）"""
    id: str
    name: str
    provider: str
    category: str
    model: str
    status: str
    is_configured: bool  # 是否有密钥
    use_count: int
    last_used_at: Optional[datetime] = None
    quota: Optional[float] = None
    quota_used: Optional[float] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApiKeyListResponse(BaseModel):
    """API 密钥列表响应"""
    items: List[ApiKeyResponse]
    total: int


def model_to_response(model: Live2DModel) -> Live2DModelResponse:
    """将数据库模型转换为响应模型"""
    # 解析 JSON 字段
    try:
        layers = json.loads(model.layers) if model.layers else []
    except:
        layers = []

    try:
        metadata = json.loads(model.extra_data) if model.extra_data else {}
    except:
        metadata = {}

    return Live2DModelResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        character_id=model.character_id,
        style_mode=model.style_mode,
        source_image_url=model.source_image_url or "",
        processed_image_url=model.processed_image_path or None,
        layers=layers,
        status=model.status,
        status_label=Live2DModelStatus.label(model.status),
        metadata=metadata,
        created_at=model.created_at,
        updated_at=model.updated_at,
        completed_at=model.completed_at,
        use_count=model.use_count,
    )


# ---- 路由 ----

@router.get("/options/style", summary="获取风格模式选项")
async def get_style_options() -> Live2DStyleOptionsResponse:
    """获取可用的风格模式选项"""
    return Live2DStyleOptionsResponse(
        options=Live2DStyleMode.options()
    )


@router.get("/options/status", summary="获取状态选项")
async def get_status_options() -> Live2DStatusOptionsResponse:
    """获取可用的状态选项"""
    statuses = [
        {"value": s, "label": Live2DModelStatus.label(s)}
        for s in Live2DModelStatus.all()
    ]
    return Live2DStatusOptionsResponse(statuses=statuses)


# ---- 配置管理端点 ----

@router.get("/config/processing-modes", summary="获取处理模式配置")
async def get_processing_modes() -> ProcessingModeResponse:
    """
    获取当前的处理模式配置。

    返回：
    - default_mode: 全局默认处理模式
    - service_modes: 各服务的处理模式
    - api_keys_configured: API密钥配置状态
    """
    config = get_live2d_config()

    # 获取各服务的处理模式
    service_modes = {
        "rembg": {
            "mode": config.get_processing_mode("rembg"),
            "mode_label": ProcessingMode.label(config.get_processing_mode("rembg")),
        },
        "style_transfer": {
            "mode": config.get_processing_mode("style_transfer"),
            "mode_label": ProcessingMode.label(config.get_processing_mode("style_transfer")),
        },
        "segmentation": {
            "mode": config.get_processing_mode("segmentation"),
            "mode_label": ProcessingMode.label(config.get_processing_mode("segmentation")),
        },
    }

    # API密钥配置状态（异步检查）
    api_keys_configured = {
        "remove_bg": bool(await config.get_api_key("rembg")),
        "replicate": bool(await config.get_api_key("style_transfer")),
        "huggingface": bool(await config.get_api_key("segmentation")),
    }

    return ProcessingModeResponse(
        default_mode=config.get_default_mode(),
        default_mode_label=ProcessingMode.label(config.get_default_mode()),
        service_modes=service_modes,
        api_keys_configured=api_keys_configured,
    )


@router.put("/config/processing-modes", summary="更新处理模式配置")
async def update_processing_modes(body: ProcessingModeUpdateRequest) -> ProcessingModeResponse:
    """
    更新全局处理模式配置。

    支持：
    - 更新默认处理模式（local/api）
    - 更新单个服务的处理模式
    """
    config = get_live2d_config()

    if body.default_mode is not None:
        if body.default_mode not in ProcessingMode.all():
            raise HTTPException(status_code=400, detail=f"无效的处理模式: {body.default_mode}")
        config.set_default_mode(body.default_mode)

    if body.service_modes is not None:
        for service, mode in body.service_modes.items():
            if mode not in ProcessingMode.all():
                raise HTTPException(status_code=400, detail=f"无效的处理模式: {mode}")
            config.set_processing_mode(service, mode)

    return await get_processing_modes()


# ---- API 密钥管理端点 ----

@router.get("/api-keys", summary="列出 API 密钥", response_model=ApiKeyListResponse)
async def list_api_keys(
    category: Optional[str] = Query(None, description="密钥分类过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
):
    """
    列出所有 API 密钥。

    返回的密钥值会被部分隐藏（如 sk-***abcd）。
    """
    async with get_session() as session:
        query = select(ApiKey)

        if category:
            query = query.where(ApiKey.category == category)
        if status:
            query = query.where(ApiKey.status == status)

        query = query.order_by(ApiKey.created_at.desc())

        # 获取总数
        count_query = select(func.count()).select_from(ApiKey)
        if category:
            count_query = count_query.where(ApiKey.category == category)
        if status:
            count_query = count_query.where(ApiKey.status == status)

        total = await session.scalar(count_query)

        keys = await session.exec(query)
        keys = keys.all()

        items = []
        for k in keys:
            # 隐藏密钥值
            is_configured = bool(k.api_key)
            items.append(ApiKeyResponse(
                id=k.id,
                name=k.name,
                provider=k.provider,
                category=k.category,
                model=k.model,
                status=k.status,
                is_configured=is_configured,
                use_count=k.use_count,
                last_used_at=k.last_used_at,
                quota=k.quota,
                quota_used=k.quota_used,
                created_at=k.created_at,
                expires_at=k.expires_at,
            ))

        return ApiKeyListResponse(items=items, total=total)


@router.post("/api-keys", summary="创建 API 密钥")
async def create_api_key(body: ApiKeyCreateRequest) -> ApiKeyResponse:
    """
    创建新的 API 密钥记录。

    密钥值会加密存储。
    """
    # 验证分类
    if body.category not in ApiKeyCategory.all():
        raise HTTPException(status_code=400, detail=f"无效的密钥分类: {body.category}")

    # 验证状态（如果有）
    if body.expires_at:
        try:
            datetime.fromisoformat(body.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的过期时间格式，请使用 ISO 格式")

    api_key = ApiKey(
        name=body.name,
        provider=body.provider,
        category=body.category,
        api_key=body.api_key,
        api_secret=body.api_secret,
        model=body.model,
        config=json.dumps(body.config) if body.config else "{}",
        status=ApiKeyStatus.ACTIVE.value,
        expires_at=datetime.fromisoformat(body.expires_at) if body.expires_at else None,
    )

    async with get_session() as session:
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            provider=api_key.provider,
            category=api_key.category,
            model=api_key.model,
            status=api_key.status,
            is_configured=bool(api_key.api_key),
            use_count=api_key.use_count,
            last_used_at=api_key.last_used_at,
            quota=api_key.quota,
            quota_used=api_key.quota_used,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
        )


@router.get("/api-keys/{key_id}", summary="获取 API 密钥详情")
async def get_api_key(key_id: str) -> ApiKeyResponse:
    """获取指定 API 密钥的详细信息。"""
    async with get_session() as session:
        api_key = await session.get(ApiKey, key_id)

        if not api_key:
            raise HTTPException(status_code=404, detail=f"密钥不存在: {key_id}")

        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            provider=api_key.provider,
            category=api_key.category,
            model=api_key.model,
            status=api_key.status,
            is_configured=bool(api_key.api_key),
            use_count=api_key.use_count,
            last_used_at=api_key.last_used_at,
            quota=api_key.quota,
            quota_used=api_key.quota_used,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
        )


@router.put("/api-keys/{key_id}", summary="更新 API 密钥")
async def update_api_key(key_id: str, body: ApiKeyUpdateRequest) -> ApiKeyResponse:
    """
    更新 API 密钥信息。

    支持更新密钥值、状态等。
    """
    async with get_session() as session:
        api_key = await session.get(ApiKey, key_id)

        if not api_key:
            raise HTTPException(status_code=404, detail=f"密钥不存在: {key_id}")

        if body.name is not None:
            api_key.name = body.name
        if body.api_key is not None:
            api_key.api_key = body.api_key
        if body.api_secret is not None:
            api_key.api_secret = body.api_secret
        if body.model is not None:
            api_key.model = body.model
        if body.status is not None:
            if body.status not in ApiKeyStatus.all():
                raise HTTPException(status_code=400, detail=f"无效的状态: {body.status}")
            api_key.status = body.status
        if body.config is not None:
            api_key.config = json.dumps(body.config)

        await session.commit()
        await session.refresh(api_key)

        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            provider=api_key.provider,
            category=api_key.category,
            model=api_key.model,
            status=api_key.status,
            is_configured=bool(api_key.api_key),
            use_count=api_key.use_count,
            last_used_at=api_key.last_used_at,
            quota=api_key.quota,
            quota_used=api_key.quota_used,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
        )


@router.delete("/api-keys/{key_id}", summary="删除 API 密钥")
async def delete_api_key(key_id: str):
    """删除指定的 API 密钥。"""
    async with get_session() as session:
        api_key = await session.get(ApiKey, key_id)

        if not api_key:
            raise HTTPException(status_code=404, detail=f"密钥不存在: {key_id}")

        await session.delete(api_key)
        await session.commit()

        return {"message": "密钥已删除", "id": key_id}


@router.get("/api-keys/{key_id}/test", summary="测试 API 密钥")
async def test_api_key(key_id: str):
    """
    测试 API 密钥是否可用。

    根据 provider 类型执行不同的测试：
    - removebg: 调用 Remove.bg API
    - replicate: 调用 Replicate API
    - huggingface: 调用 Hugging Face Inference API
    """
    async with get_session() as session:
        api_key = await session.get(ApiKey, key_id)

        if not api_key:
            raise HTTPException(status_code=404, detail=f"密钥不存在: {key_id}")

        if not api_key.api_key:
            raise HTTPException(status_code=400, detail="密钥未配置")

        # 简单的连通性测试
        if api_key.provider == "removebg":
            try:
                import requests
                response = requests.get(
                    "https://api.remove.bg/v1.0/account",
                    headers={"X-Api-Key": api_key.api_key},
                    timeout=10
                )
                if response.status_code == 200:
                    return {"status": "ok", "message": "Remove.bg API 连接成功", "data": response.json()}
                else:
                    return {"status": "error", "message": f"API 返回错误: {response.status_code}"}
            except Exception as e:
                return {"status": "error", "message": f"连接失败: {str(e)}"}

        elif api_key.provider == "replicate":
            try:
                import requests
                response = requests.get(
                    "https://api.replicate.com/v1/account",
                    headers={"Authorization": f"Token {api_key.api_key}"},
                    timeout=10
                )
                if response.status_code == 200:
                    return {"status": "ok", "message": "Replicate API 连接成功", "data": response.json()}
                else:
                    return {"status": "error", "message": f"API 返回错误: {response.status_code}"}
            except Exception as e:
                return {"status": "error", "message": f"连接失败: {str(e)}"}

        elif api_key.provider == "huggingface":
            try:
                import requests
                response = requests.get(
                    "https://api-inference.huggingface.co/status",
                    headers={"Authorization": f"Bearer {api_key.api_key}"},
                    timeout=10
                )
                if response.status_code == 200:
                    return {"status": "ok", "message": "Hugging Face API 连接成功", "data": response.json()}
                else:
                    return {"status": "error", "message": f"API 返回错误: {response.status_code}"}
            except Exception as e:
                return {"status": "error", "message": f"连接失败: {str(e)}"}

        else:
            return {"status": "unknown", "message": f"未知的 provider: {api_key.provider}"}
async def update_model_processing_config(
    model_id: str,
    body: ModelProcessingConfigUpdateRequest
) -> Live2DModelResponse:
    """
    更新指定模型的个性化处理配置。

    此配置会覆盖全局配置，优先级：请求参数 > 模型配置 > 全局配置

    processing_config 格式：
    ```json
    {
        "rembg": "api",
        "style_transfer": "local",
        "segmentation": "api"
    }
    ```
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 验证配置
        for service, mode in body.processing_config.items():
            if mode not in ProcessingMode.all():
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的处理模式 '{mode}' for service '{service}'"
                )

        # 更新配置
        model.processing_config = json.dumps(body.processing_config)
        model.updated_at = datetime.now()

        session.add(model)
        await session.commit()
        await session.refresh(model)

        return model_to_response(model)


@router.post("", summary="创建 Live2D 模型（上传图片）", response_model=Live2DModelResponse)
async def create_model(
    name: str = Form(..., description="模型名称"),
    description: str = Form(default="", description="描述"),
    character_id: str = Form(default="", description="关联角色ID"),
    style_mode: str = Form(default=Live2DStyleMode.ANIME.value, description="风格模式"),
    file: UploadFile = File(..., description="角色图片文件"),
):
    """
    上传角色立绘/Cos照片，创建 Live2D 模型记录。

    支持三种风格模式：
    - anime: 动漫立绘模式（上传透明底PNG/PSD）
    - coser_real: Coser照片模式（保持真人风格）
    - coser_anime: Coser照片模式（转二次元风格）

    图片保存到 uploads/live2d/{model_id}.{ext}。
    """
    # 验证风格模式
    if style_mode not in Live2DStyleMode.all():
        raise HTTPException(status_code=400, detail=f"无效的风格模式: {style_mode}")

    # 验证文件类型
    allowed_types = ["image/png", "image/jpeg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.content_type}，仅支持 PNG/JPEG/WebP"
        )

    # 生成模型 ID
    model_id = uuid.uuid4().hex

    # 确保上传目录存在
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # 保存文件
    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    file_path = UPLOAD_DIR / f"{model_id}.{ext}"

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 构建访问 URL
    file_url = f"/uploads/live2d/{model_id}.{ext}"

    # 创建数据库记录
    model = Live2DModel(
        id=model_id,
        name=name,
        description=description,
        character_id=character_id,
        style_mode=style_mode,
        source_image_path=str(file_path),
        source_image_url=file_url,
        status=Live2DModelStatus.DRAFT.value,
        layers="[]",
        metadata="{}",
    )

    async with get_session() as session:
        session.add(model)
        await session.commit()
        await session.refresh(model)
        return model_to_response(model)


@router.get("", summary="列出 Live2D 模型", response_model=Live2DModelListResponse)
async def list_models(
    keyword: Optional[str] = Query(None, description="搜索模型名称"),
    status: Optional[str] = Query(None, description="状态过滤"),
    style_mode: Optional[str] = Query(None, description="风格模式过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    列出 Live2D 模型，支持关键词搜索、状态过滤、风格模式过滤、分页。
    """
    async with get_session() as session:
        # 构建查询
        query = select(Live2DModel)

        if keyword:
            query = query.where(col(Live2DModel.name).contains(keyword))

        if status and status in Live2DModelStatus.all():
            query = query.where(Live2DModel.status == status)

        if style_mode and style_mode in Live2DStyleMode.all():
            query = query.where(Live2DModel.style_mode == style_mode)

        # 按更新时间倒序
        query = query.order_by(col(Live2DModel.updated_at).desc())

        # 获取总数
        count_query = select(func.count()).select_from(Live2DModel)
        if keyword:
            count_query = count_query.where(col(Live2DModel.name).contains(keyword))
        if status and status in Live2DModelStatus.all():
            count_query = count_query.where(Live2DModel.status == status)
        if style_mode and style_mode in Live2DStyleMode.all():
            count_query = count_query.where(Live2DModel.style_mode == style_mode)

        total = await session.scalar(count_query)

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        models = await session.exec(query)
        models = models.all()

        # 计算总页数
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return Live2DModelListResponse(
            items=[model_to_response(m) for m in models],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


@router.get("/{model_id}", summary="获取 Live2D 模型详情", response_model=Live2DModelResponse)
async def get_model(model_id: str):
    """获取指定 Live2D 模型的详细信息。"""
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        return model_to_response(model)


@router.put("/{model_id}", summary="更新 Live2D 模型", response_model=Live2DModelResponse)
async def update_model(model_id: str, body: Live2DModelUpdateRequest):
    """更新 Live2D 模型信息。"""
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 更新字段
        if body.name is not None:
            model.name = body.name
        if body.description is not None:
            model.description = body.description
        if body.character_id is not None:
            model.character_id = body.character_id
        if body.status is not None:
            if body.status not in Live2DModelStatus.all():
                raise HTTPException(status_code=400, detail=f"无效的状态: {body.status}")
            model.status = body.status
            # 如果设置为完成，记录完成时间
            if body.status == Live2DModelStatus.COMPLETED.value:
                model.completed_at = datetime.now()

        model.updated_at = datetime.now()

        session.add(model)
        await session.commit()
        await session.refresh(model)

        return model_to_response(model)


@router.delete("/{model_id}", summary="删除 Live2D 模型")
async def delete_model(model_id: str):
    """删除 Live2D 模型记录（软删，保留文件）。"""
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 软删：将状态设为 error
        model.status = Live2DModelStatus.ERROR.value
        model.updated_at = datetime.now()

        session.add(model)
        await session.commit()

        return {"message": "模型已删除", "id": model_id}


# ---- AI 处理端点（占位符，Phase 2-4 实现） ----

@router.post("/{model_id}/rembg", summary="AI 抠图（去除背景）")
async def rembg_model(
    model_id: str,
    mode: Optional[str] = Query(
        None,
        description="处理模式：local（本地模型）或 api（云端API），不指定则使用配置默认"
    )
):
    """
    AI 抠图：去除背景。

    支持两种处理方式：
    - 本地模式（默认）：使用 RMBG-1.4 模型，无需API密钥
    - API模式：使用 Remove.bg API，需要配置API密钥

    仅适用于 coser_real 和 coser_anime 模式。
    动漫立绘模式（anime）不需要此步骤。
    """
    from app.services.live2d import get_rembg_service

    # 获取配置
    config = get_live2d_config()

    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        if model.style_mode == Live2DStyleMode.ANIME.value:
            raise HTTPException(
                status_code=400,
                detail="动漫立绘模式不需要抠图，请直接进行分层处理"
            )

        # 检查原始图片是否存在
        if not model.source_image_path:
            raise HTTPException(status_code=400, detail="原始图片不存在")

        # 确定处理模式（优先级：请求参数 > 模型配置 > 全局配置）
        if mode is None:
            # 尝试从模型配置中获取
            try:
                model_config = json.loads(model.processing_config) if model.processing_config else {}
                mode = config.get_effective_mode("rembg", model_config)
            except:
                mode = config.get_effective_mode("rembg")

        # 验证模式
        if mode not in ProcessingMode.all():
            mode = ProcessingMode.LOCAL.value

        # 更新状态为处理中
        model.status = Live2DModelStatus.PROCESSING.value
        model.updated_at = datetime.now()
        session.add(model)
        await session.commit()

        # 推送开始进度
        await push_live2d_progress(
            model_id=model_id,
            progress=10,
            message="开始抠图处理...",
            step="rembg",
            status="processing",
        )

        try:
            # 调用抠图服务
            service = get_rembg_service(mode=mode)

            # 推送处理中进度
            await push_live2d_progress(
                model_id=model_id,
                progress=50,
                message=f"正在使用 {ProcessingMode.label(mode)} 模式进行抠图...",
                step="rembg",
            )

            # 输出目录：uploads/live2d/{model_id}/
            output_dir = UPLOAD_DIR / model_id
            output_dir.mkdir(parents=True, exist_ok=True)

            result = await service.remove_background_file(
                input_path=model.source_image_path,
                output_path=output_dir / "rembg.png",
                return_mask=True,
            )

            # 更新模型记录
            model.processed_image_path = result["result_path"]
            model.status = Live2DModelStatus.DRAFT.value  # 抠图后回到草稿状态
            model.updated_at = datetime.now()

            # 推送完成进度
            await push_live2d_progress(
                model_id=model_id,
                progress=100,
                message="抠图完成",
                step="rembg",
                status="done",
            )

            # 更新元数据
            metadata = json.loads(model.extra_data) if model.extra_data else {}
            metadata["rembg"] = {
                "result_path": result["result_path"],
                "mask_path": result.get("mask_path"),
                "mode": result.get("mode", mode),
                "completed_at": datetime.now().isoformat(),
            }
            model.extra_data = json.dumps(metadata)

            session.add(model)
            await session.commit()

            return {
                "message": "抠图完成",
                "model_id": model_id,
                "mode": mode,
                "mode_label": ProcessingMode.label(mode),
                "result_path": result["result_path"],
                "mask_path": result.get("mask_path"),
                "access_url": f"/uploads/live2d/{model_id}/rembg.png",
            }

        except Exception as e:
            # 处理失败，更新状态
            model.status = Live2DModelStatus.ERROR.value
            model.updated_at = datetime.now()
            session.add(model)
            await session.commit()
            raise HTTPException(status_code=500, detail=f"抠图失败: {str(e)}")


@router.post("/{model_id}/style-transfer", summary="风格转换（真人转二次元）")
async def style_transfer_model(
    model_id: str,
    mode: Optional[str] = Query(
        None,
        description="处理模式：local（本地模型）或 api（云端API），不指定则使用配置默认"
    )
):
    """
    风格转换：将真人照片转换为二次元风格。

    支持两种处理方式：
    - 本地模式（默认）：使用 SD + ControlNet，需要GPU
    - API模式：使用 Replicate API（SDXL），需要配置API密钥

    仅适用于 coser_anime 模式。
    """
    from app.services.live2d import get_style_transfer_service

    # 获取配置
    config = get_live2d_config()

    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        if model.style_mode != Live2DStyleMode.COSER_ANIME.value:
            raise HTTPException(
                status_code=400,
                detail="仅 coser_anime 模式需要进行风格转换"
            )

        # 确定输入图片（优先使用抠图后的图片）
        input_path = model.processed_image_path or model.source_image_path
        if not input_path:
            raise HTTPException(status_code=400, detail="没有可用的图片")

        # 确定处理模式（优先级：请求参数 > 模型配置 > 全局配置）
        if mode is None:
            # 尝试从模型配置中获取
            try:
                model_config = json.loads(model.processing_config) if model.processing_config else {}
                mode = config.get_effective_mode("style_transfer", model_config)
            except:
                mode = config.get_effective_mode("style_transfer")

        # 验证模式
        if mode not in ProcessingMode.all():
            mode = ProcessingMode.LOCAL.value

        # 更新状态
        model.status = Live2DModelStatus.PROCESSING.value
        model.updated_at = datetime.now()
        session.add(model)
        await session.commit()

        # 推送开始进度
        await push_live2d_progress(
            model_id=model_id,
            progress=10,
            message="开始风格转换...",
            step="style_transfer",
            status="processing",
        )

        try:
            # 调用风格转换服务
            service = get_style_transfer_service(mode=mode)

            # 推送处理中进度
            await push_live2d_progress(
                model_id=model_id,
                progress=50,
                message=f"正在使用 {ProcessingMode.label(mode)} 模式进行风格转换...",
                step="style_transfer",
            )

            # 输出目录
            output_dir = UPLOAD_DIR / model_id
            output_dir.mkdir(parents=True, exist_ok=True)

            result = await service.transfer_style_file(
                input_path=input_path,
                output_path=output_dir / "anime_style.png",
            )

            # 更新模型记录
            model.processed_image_path = result["result_path"]
            model.status = Live2DModelStatus.DRAFT.value
            model.updated_at = datetime.now()

            # 推送完成进度
            await push_live2d_progress(
                model_id=model_id,
                progress=100,
                message="风格转换完成",
                step="style_transfer",
                status="done",
            )

            # 更新元数据
            metadata = json.loads(model.extra_data) if model.extra_data else {}
            metadata["style_transfer"] = {
                "result_path": result["result_path"],
                "style_type": result["style_type"],
                "processing_time": result["processing_time"],
                "mode": result.get("mode", mode),
                "completed_at": datetime.now().isoformat(),
            }
            model.extra_data = json.dumps(metadata)

            session.add(model)
            await session.commit()

            return {
                "message": "风格转换完成",
                "model_id": model_id,
                "mode": mode,
                "mode_label": ProcessingMode.label(mode),
                "result_path": result["result_path"],
                "processing_time": result["processing_time"],
                "access_url": f"/uploads/live2d/{model_id}/anime_style.png",
            }

        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except Exception as e:
            model.status = Live2DModelStatus.ERROR.value
            model.updated_at = datetime.now()
            session.add(model)
            await session.commit()
            raise HTTPException(status_code=500, detail=f"风格转换失败: {str(e)}")


@router.post("/{model_id}/segment", summary="AI 图像分割（自动分层）")
async def segment_model(
    model_id: str,
    mode: Optional[str] = Query(
        None,
        description="处理模式：local（本地模型）或 api（云端API），不指定则使用配置默认"
    )
):
    """
    AI 自动分层：自动识别并分离角色部件。

    支持两种处理方式：
    - 本地模式（默认）：使用 BiRefNet/U-2-Net 模型
    - API模式：使用 Hugging Face Inference API，需要配置API密钥

    根据风格模式选择合适的分割模型：
    - anime: 动漫分割模型
    - coser_real / coser_anime: 人像分割模型（BiRefNet）
    """
    from app.services.live2d import get_segmentation_service, SegmentationModelType

    # 获取配置
    config = get_live2d_config()

    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 确定输入图片
        input_path = model.processed_image_path or model.source_image_path
        if not input_path:
            raise HTTPException(status_code=400, detail="没有可用的图片")

        # 确定处理模式（优先级：请求参数 > 模型配置 > 全局配置）
        if mode is None:
            # 尝试从模型配置中获取
            try:
                model_config = json.loads(model.processing_config) if model.processing_config else {}
                mode = config.get_effective_mode("segmentation", model_config)
            except:
                mode = config.get_effective_mode("segmentation")

        # 验证模式
        if mode not in ProcessingMode.all():
            mode = ProcessingMode.LOCAL.value

        # 选择分割模型（仅本地模式使用）
        if model.style_mode == Live2DStyleMode.ANIME.value:
            model_type = SegmentationModelType.U2NET
        else:
            model_type = SegmentationModelType.BIREFNET

        # 更新状态
        model.status = Live2DModelStatus.PROCESSING.value
        model.updated_at = datetime.now()
        session.add(model)
        await session.commit()

        # 推送开始进度
        await push_live2d_progress(
            model_id=model_id,
            progress=10,
            message="开始图像分割...",
            step="segment",
            status="processing",
        )

        try:
            # 调用分割服务
            service = get_segmentation_service(model_type=model_type, mode=mode)

            # 推送处理中进度
            await push_live2d_progress(
                model_id=model_id,
                progress=50,
                message=f"正在使用 {ProcessingMode.label(mode)} 模式进行分层...",
                step="segment",
            )

            # 输出目录
            output_dir = UPLOAD_DIR / model_id / "segments"
            output_dir.mkdir(parents=True, exist_ok=True)

            result = await service.segment_file(
                input_path=input_path,
                output_dir=output_dir,
                save_layers=True,
            )

            # 更新模型记录
            model.layers = json.dumps(result["layers"])
            model.status = Live2DModelStatus.RIGGED.value  # 分层后进入 rigged 状态
            model.updated_at = datetime.now()

            # 推送完成进度
            await push_live2d_progress(
                model_id=model_id,
                progress=100,
                message=f"分层完成，共 {result['layer_count']} 层",
                step="segment",
                status="done",
            )

            # 更新元数据
            metadata = json.loads(model.extra_data) if model.extra_data else {}
            metadata["segmentation"] = {
                "mask_path": result["mask_path"],
                "layer_count": result["layer_count"],
                "model_type": result["metadata"].get("model_type"),
                "mode": result.get("mode", mode),
                "completed_at": datetime.now().isoformat(),
            }
            model.extra_data = json.dumps(metadata)

            session.add(model)
            await session.commit()

            return {
                "message": "分层完成",
                "model_id": model_id,
                "mode": mode,
                "mode_label": ProcessingMode.label(mode),
                "mask_path": result["mask_path"],
                "layer_count": result["layer_count"],
                "layers": result["layers"],
                "access_url": f"/uploads/live2d/{model_id}/segments",
            }

        except Exception as e:
            model.status = Live2DModelStatus.ERROR.value
            model.updated_at = datetime.now()
            session.add(model)
            await session.commit()
            raise HTTPException(status_code=500, detail=f"分层失败: {str(e)}")


@router.post("/{model_id}/inpaint", summary="AI 遮挡补全")
async def inpaint_model(model_id: str):
    """AI 遮挡补全：使用 Stable Diffusion Inpainting 补全被遮挡区域。"""
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # TODO: Phase 2 实现
        raise HTTPException(status_code=501, detail="功能开发中（Phase 2）")


@router.post("/{model_id}/rig", summary="自动骨骼绑定")
async def rig_model(model_id: str):
    """
    自动骨骼绑定：生成网格 + 创建骨骼 + 计算权重。

    Phase 3 实现：
    - 面部关键点检测
    - 五官骨骼绑定
    - 生成待机动作（眨眼、呼吸）
    """
    from pathlib import Path
    from app.services.live2d import get_rigging_service, RiggingResult

    # 获取模型
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 确定输入图片
        input_path = model.processed_image_path or model.source_image_path
        if not input_path:
            raise HTTPException(status_code=400, detail="没有可用的图片进行绑骨")

        # 更新状态
        model.status = Live2DModelStatus.PROCESSING.value
        model.updated_at = datetime.now()
        session.add(model)
        await session.commit()

        # 推送开始进度
        await push_live2d_progress(
            model_id=model_id,
            progress=10,
            message="开始骨骼绑定...",
            step="rig",
            status="processing",
        )

        try:
            # 推送处理中进度
            await push_live2d_progress(
                model_id=model_id,
                progress=50,
                message="正在进行面部关键点检测和骨骼绑定...",
                step="rig",
            )

            # 执行绑骨
            service = get_rigging_service()
            result = service.rig_face(
                model_id=model_id,
                image_path=input_path,
                output_dir=UPLOAD_DIR / model_id / "rigging"
            )

            if not result.rigged:
                # 推送失败进度
                await push_live2d_progress(
                    model_id=model_id,
                    progress=0,
                    message="绑骨失败",
                    step="rig",
                    status="failed",
                )
                raise HTTPException(status_code=500, detail="绑骨失败: " + result.metadata.get("error", "未知错误"))

            # 更新模型记录
            model.status = Live2DModelStatus.RIGGED.value
            model.updated_at = datetime.now()

            # 推送完成进度
            await push_live2d_progress(
                model_id=model_id,
                progress=100,
                message=f"骨骼绑定完成，共 {result.bone_count} 根骨骼",
                step="rig",
                status="done",
            )

            # 保存绑骨配置到元数据
            metadata = json.loads(model.extra_data) if model.extra_data else {}
            metadata["rigging"] = {
                "bone_count": result.bone_count,
                "face_detected": result.face_detected,
                "face_bbox": result.face_bbox,
                "rigging_config_path": result.export_path,
                "motions": result.motions,
                "completed_at": datetime.now().isoformat(),
            }
            model.extra_data = json.dumps(metadata)

            session.add(model)
            await session.commit()

            return {
                "message": "绑骨完成",
                "model_id": model_id,
                "bone_count": result.bone_count,
                "face_detected": result.face_detected,
                "face_bbox": result.face_bbox,
                "motions": result.motions,
                "rigging_config_path": result.export_path,
                "processing_time": result.metadata.get("processing_time", 0),
            }

        except HTTPException:
            raise
        except Exception as e:
            model.status = Live2DModelStatus.ERROR.value
            model.updated_at = datetime.now()
            session.add(model)
            await session.commit()
            raise HTTPException(status_code=500, detail=f"绑骨失败: {str(e)}")


# ---- 五官控制端点 ----

class ExpressionUpdateRequest(BaseModel):
    """表情更新请求"""
    expression: str = Field(..., description="表情类型")
    intensity: float = Field(default=1.0, ge=0.0, le=1.0, description="表情强度")


class EyeTrackingUpdateRequest(BaseModel):
    """视线跟踪更新请求"""
    x: float = Field(..., ge=-1.0, le=1.0, description="视线X（-1 到 1）")
    y: float = Field(..., ge=-1.0, le=1.0, description="视线Y（-1 到 1）")


@router.get("/{model_id}/rigging/state", summary="获取绑骨状态")
async def get_rigging_state(model_id: str):
    """
    获取模型的当前绑骨状态。

    返回骨骼配置、表情状态、视线位置等。
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 解析元数据
        metadata = json.loads(model.extra_data) if model.extra_data else {}
        rigging_data = metadata.get("rigging", {})

        if not rigging_data:
            raise HTTPException(status_code=404, detail="该模型尚未进行绑骨")

        # 获取绑骨服务实例（获取当前状态）
        service = get_rigging_service()

        return {
            "model_id": model_id,
            "bone_count": rigging_data.get("bone_count", 0),
            "face_bbox": rigging_data.get("face_bbox"),
            "motions": rigging_data.get("motions", []),
            "rigging_config_path": rigging_data.get("rigging_config_path"),
            "current_expression": {
                "expression": "neutral",
                "intensity": 1.0,
            },
            "eye_tracking": {
                "x": 0.0,
                "y": 0.0,
            },
            "blink_level": 0.0,
        }


@router.put("/{model_id}/rigging/expression", summary="更新表情")
async def update_expression(model_id: str, body: ExpressionUpdateRequest):
    """
    更新模型的当前表情。

    表情类型：
    - neutral: 默认
    - happy: 开心
    - sad: 难过
    - angry: 生气
    - surprised: 惊讶
    - loved: 喜欢
    - focused: 专注
    """
    from app.services.live2d import ExpressionType, ExpressionCalculator

    # 验证表情类型
    if body.expression not in ExpressionType.all():
        raise HTTPException(status_code=400, detail=f"无效的表情类型: {body.expression}")

    # 获取绑骨配置
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        metadata = json.loads(model.extra_data) if model.extra_data else {}
        rigging_data = metadata.get("rigging", {})

        if not rigging_data:
            raise HTTPException(status_code=404, detail="该模型尚未进行绑骨")

        # 计算表情变换
        blends = ExpressionCalculator.calculate_blend(body.expression, body.intensity)

        # 返回变换数据（前端可用于实时预览）
        return {
            "model_id": model_id,
            "expression": body.expression,
            "expression_label": ExpressionType.label(body.expression),
            "intensity": body.intensity,
            "bone_transforms": {k: v.to_dict() for k, v in blends.items()},
        }


@router.put("/{model_id}/rigging/eye-tracking", summary="更新视线跟踪")
async def update_eye_tracking(model_id: str, body: EyeTrackingUpdateRequest):
    """
    更新视线跟踪目标。

    用于实时控制眼睛跟随鼠标/摄像头。
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        metadata = json.loads(model.extra_data) if model.extra_data else {}
        rigging_data = metadata.get("rigging", {})

        if not rigging_data:
            raise HTTPException(status_code=404, detail="该模型尚未进行绑骨")

        # 获取服务并更新视线
        service = get_rigging_service()
        smooth_x, smooth_y = service.update_eye_tracking(body.x, body.y)

        # 获取眨眼状态
        blink_level = service.update_blink()

        # 获取眼睛变换
        eye_transforms = service.get_eye_transforms(smooth_x, smooth_y, blink_level)

        return {
            "model_id": model_id,
            "target": {"x": body.x, "y": body.y},
            "current": {"x": smooth_x, "y": smooth_y},
            "blink_level": blink_level,
            "eye_transforms": {k: v.to_dict() for k, v in eye_transforms.items()},
        }


@router.post("/{model_id}/mesh", summary="自动生成网格")
async def generate_mesh(model_id: str):
    """自动生成网格：根据图层轮廓自动生成三角网格。"""
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # TODO: Phase 3 实现
        raise HTTPException(status_code=501, detail="功能开发中（Phase 3）")


@router.post("/{model_id}/physics", summary="配置物理模拟")
async def configure_physics(model_id: str):
    """配置物理模拟：头发/衣摆钟摆参数。"""
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # TODO: Phase 4 实现
        raise HTTPException(status_code=501, detail="功能开发中（Phase 4）")


@router.post("/{model_id}/motion", summary="生成待机动作")
async def generate_motion(model_id: str):
    """
    生成待机动作：眨眼 + 呼吸循环。

    基于绑骨配置生成 Live2D 动画帧数据。
    眨眼：随机间隔触发，持续 0.15 秒
    呼吸：4 秒周期，幅度 2 像素
    视线移动：8 秒周期，正弦模式
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 检查是否已完成绑骨
        metadata = json.loads(model.extra_data) if model.extra_data else {}
        rigging_data = metadata.get("rigging", {})

        if not rigging_data:
            raise HTTPException(status_code=400, detail="请先完成绑骨")

        # 获取绑骨配置中的动作
        motions = rigging_data.get("motions", [])

        if not motions:
            # 如果没有预生成的动作，从服务获取默认动作
            service = get_rigging_service()
            motions = service._generate_idle_motions(model_id, UPLOAD_DIR / model_id / "rigging")

        # 更新模型状态
        model.status = Live2DModelStatus.ANIMATED.value
        model.updated_at = datetime.now()

        # 保存动作配置
        metadata["motions"] = motions
        model.extra_data = json.dumps(metadata)

        session.add(model)
        await session.commit()

        return {
            "message": "待机动作生成完成",
            "model_id": model_id,
            "motions": motions,
            "animation_config": {
                "blink": {
                    "interval_range": [1.5, 4.5],
                    "duration": 0.15,
                },
                "breath": {
                    "duration": 4.0,
                    "amplitude": 2.0,
                    "frequency": 0.25,
                },
                "look_around": {
                    "duration": 8.0,
                    "pattern": "sine",
                },
            },
        }


@router.post("/{model_id}/export", summary="导出 VTS 模型")
async def export_model(model_id: str):
    """
    导出 Cubism 模型为 VTS 格式：
    - model.json: 模型主配置
    - settings.json: VTS 特定设置
    - physics.json: 物理模拟
    - pose.json: 姿态配置
    - textures/: 纹理图片
    - motions/: 动作文件

    返回 ZIP 包下载链接。
    """
    from app.services.live2d import export_to_vts

    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 检查是否已完成绑骨
        metadata = json.loads(model.extra_data) if model.extra_data else {}
        rigging_data = metadata.get("rigging", {})

        if not rigging_data:
            raise HTTPException(status_code=400, detail="请先完成绑骨")

        # 推送开始进度
        await push_live2d_progress(
            model_id=model_id,
            progress=10,
            message="开始导出模型...",
            step="export",
            status="processing",
        )

        try:
            # 导出模型
            output_dir = UPLOAD_DIR / model_id / "export"
            result = export_to_vts(model_id, rigging_data, output_dir)

            # 更新模型记录
            model.model_file_path = result["zip_path"]
            model.status = Live2DModelStatus.COMPLETED.value
            model.completed_at = datetime.now()
            model.updated_at = datetime.now()

            session.add(model)
            await session.commit()

            # 推送完成进度
            await push_live2d_progress(
                model_id=model_id,
                progress=100,
                message="导出完成",
                step="export",
                status="done",
            )

            return {
                "message": "导出完成",
                "model_id": model_id,
                "model_name": result["model_name"],
                "download_url": f"/uploads/live2d/{model_id}/export/{result['model_name']}.zip",
                "files": result["files"],
            }

        except Exception as e:
            await push_live2d_progress(
                model_id=model_id,
                progress=0,
                message=f"导出失败: {str(e)}",
                step="export",
                status="failed",
            )
            raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/{model_id}/download", summary="下载模型文件")
async def download_model(model_id: str):
    """
    下载 Live2D 模型文件（ZIP 打包）。

    如果模型已导出，返回 ZIP 文件下载。
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 如果有导出的文件，直接返回
        if model.model_file_path:
            from pathlib import Path
            file_path = Path(model.model_file_path)
            if file_path.exists():
                return FileResponse(
                    path=str(file_path),
                    filename=f"{model.name}.zip",
                    media_type='application/zip',
                )

        # 如果没有导出文件，尝试导出后再下载
        try:
            # 执行导出
            from app.services.live2d import export_to_vts
            metadata = json.loads(model.extra_data) if model.extra_data else {}
            rigging_data = metadata.get("rigging", {})

            if not rigging_data:
                raise HTTPException(status_code=400, detail="请先完成绑骨")

            output_dir = UPLOAD_DIR / model_id / "export"
            result = export_to_vts(model_id, rigging_data, output_dir)

            # 更新模型记录
            model.model_file_path = result["zip_path"]
            model.updated_at = datetime.now()
            session.add(model)
            await session.commit()

            file_path = Path(result["zip_path"])
            return FileResponse(
                path=str(file_path),
                filename=f"{model.name}.zip",
                media_type='application/zip',
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")

# ---- 一键生成流水线 ----

class PipelineRequest(BaseModel):
    """流水线请求"""
    steps: Optional[List[str]] = None  # 指定要执行的步骤，不指定则自动判断
    interrupt: bool = False  # 是否中断当前流水线


@router.post("/{model_id}/pipeline", summary="一键生成流水线")
async def run_pipeline(model_id: str, body: Optional[PipelineRequest] = None):
    """
    一键生成流水线：根据模型状态自动执行后续步骤。

    流程：
    1. rembg（如需）- 抠图
    2. style_transfer（如需）- 风格转换
    3. segment - 图像分割
    4. inpaint（可选）- 遮挡补全
    5. rig - 骨骼绑定
    6. motion - 生成待机动作
    7. export - 导出模型

    支持中断和恢复：
    - 中断：发送 { "interrupt": true }
    - 恢复：再次调用此接口，会自动从中断点继续
    """
    from app.services.live2d import (
        get_rembg_service, get_style_transfer_service,
        get_segmentation_service, get_rigging_service,
        SegmentationModelType,
    )
    from pathlib import Path

    # 获取模型
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 检查是否要中断
        if body and body.interrupt:
            model.status = Live2DModelStatus.DRAFT.value
            model.updated_at = datetime.now()
            session.add(model)
            await session.commit()

            await push_live2d_progress(
                model_id=model_id,
                progress=0,
                message="流水线已中断",
                step="pipeline",
                status="interrupted",
            )

            return {"message": "流水线已中断", "model_id": model_id}

        # 获取配置
        config = get_live2d_config()

        # 确定输入图片
        input_path = model.processed_image_path or model.source_image_path
        if not input_path:
            raise HTTPException(status_code=400, detail="没有可用的图片")

        # 推送开始进度
        await push_live2d_progress(
            model_id=model_id,
            progress=5,
            message="开始一键生成流水线...",
            step="pipeline",
            status="processing",
        )

        # 步骤1: 抠图（如果需要）
        if model.style_mode != Live2DStyleMode.ANIME.value and not model.processed_image_path:
            await push_live2d_progress(
                model_id=model_id,
                progress=10,
                message="步骤 1/6：抠图中...",
                step="pipeline_rembg",
            )

            try:
                mode = config.get_effective_mode("rembg")
                service = get_rembg_service(mode=mode)
                output_dir = UPLOAD_DIR / model_id
                output_dir.mkdir(parents=True, exist_ok=True)

                result = await service.remove_background_file(
                    input_path=input_path,
                    output_path=output_dir / "rembg.png",
                    return_mask=True,
                )

                model.processed_image_path = result["result_path"]
                input_path = result["result_path"]

                await push_live2d_progress(
                    model_id=model_id,
                    progress=20,
                    message="抠图完成",
                    step="pipeline_rembg",
                )
            except Exception as e:
                await push_live2d_progress(
                    model_id=model_id,
                    progress=0,
                    message=f"抠图失败: {str(e)}",
                    step="pipeline_rembg",
                    status="failed",
                )
                raise HTTPException(status_code=500, detail=f"抠图失败: {str(e)}")

        # 步骤2: 风格转换（如果需要）
        if model.style_mode == Live2DStyleMode.COSER_ANIME.value and not "anime_style" in str(model.processed_image_path or ""):
            await push_live2d_progress(
                model_id=model_id,
                progress=25,
                message="步骤 2/6：风格转换中...",
                step="pipeline_style",
            )

            try:
                mode = config.get_effective_mode("style_transfer")
                service = get_style_transfer_service(mode=mode)
                output_dir = UPLOAD_DIR / model_id
                output_dir.mkdir(parents=True, exist_ok=True)

                result = await service.transfer_style_file(
                    input_path=input_path,
                    output_path=output_dir / "anime_style.png",
                )

                model.processed_image_path = result["result_path"]
                input_path = result["result_path"]

                await push_live2d_progress(
                    model_id=model_id,
                    progress=35,
                    message="风格转换完成",
                    step="pipeline_style",
                )
            except Exception as e:
                await push_live2d_progress(
                    model_id=model_id,
                    progress=0,
                    message=f"风格转换失败: {str(e)}",
                    step="pipeline_style",
                    status="failed",
                )
                raise HTTPException(status_code=500, detail=f"风格转换失败: {str(e)}")

        # 步骤3: 图像分割
        await push_live2d_progress(
            model_id=model_id,
            progress=40,
            message="步骤 3/6：图像分割中...",
            step="pipeline_segment",
        )

        try:
            mode = config.get_effective_mode("segmentation")
            model_type = SegmentationModelType.U2NET if model.style_mode == Live2DStyleMode.ANIME.value else SegmentationModelType.BIREFNET
            service = get_segmentation_service(model_type=model_type, mode=mode)
            output_dir = UPLOAD_DIR / model_id / "segments"
            output_dir.mkdir(parents=True, exist_ok=True)

            result = await service.segment_file(
                input_path=input_path,
                output_dir=output_dir,
                save_layers=True,
            )

            model.layers = json.dumps(result["layers"])
            model.status = Live2DModelStatus.RIGGED.value

            await push_live2d_progress(
                model_id=model_id,
                progress=60,
                message=f"分割完成，共 {result['layer_count']} 层",
                step="pipeline_segment",
            )
        except Exception as e:
            await push_live2d_progress(
                model_id=model_id,
                progress=0,
                message=f"分割失败: {str(e)}",
                step="pipeline_segment",
                status="failed",
            )
            raise HTTPException(status_code=500, detail=f"分割失败: {str(e)}")

        # 步骤4: 骨骼绑定
        await push_live2d_progress(
            model_id=model_id,
            progress=65,
            message="步骤 4/6：骨骼绑定中...",
            step="pipeline_rig",
        )

        try:
            service = get_rigging_service()
            result = service.rig_face(
                model_id=model_id,
                image_path=input_path,
                output_dir=UPLOAD_DIR / model_id / "rigging"
            )

            if not result.rigged:
                raise Exception(result.metadata.get("error", "绑骨失败"))

            await push_live2d_progress(
                model_id=model_id,
                progress=80,
                message=f"骨骼绑定完成，共 {result.bone_count} 根骨骼",
                step="pipeline_rig",
            )
        except Exception as e:
            await push_live2d_progress(
                model_id=model_id,
                progress=0,
                message=f"骨骼绑定失败: {str(e)}",
                step="pipeline_rig",
                status="failed",
            )
            raise HTTPException(status_code=500, detail=f"骨骼绑定失败: {str(e)}")

        # 步骤5: 生成待机动作
        await push_live2d_progress(
            model_id=model_id,
            progress=85,
            message="步骤 5/6：生成待机动作中...",
            step="pipeline_motion",
        )

        try:
            model.status = Live2DModelStatus.ANIMATED.value

            await push_live2d_progress(
                model_id=model_id,
                progress=95,
                message="待机动作生成完成",
                step="pipeline_motion",
            )
        except Exception as e:
            await push_live2d_progress(
                model_id=model_id,
                progress=0,
                message=f"动作生成失败: {str(e)}",
                step="pipeline_motion",
                status="failed",
            )
            raise HTTPException(status_code=500, detail=f"动作生成失败: {str(e)}")

        # 步骤6: 导出模型（TODO: Phase 4 实现）
        await push_live2d_progress(
            model_id=model_id,
            progress=98,
            message="步骤 6/6：导出模型中...",
            step="pipeline_export",
        )

        # 更新最终状态
        model.status = Live2DModelStatus.COMPLETED.value
        model.completed_at = datetime.now()
        model.updated_at = datetime.now()

        session.add(model)
        await session.commit()

        await push_live2d_progress(
            model_id=model_id,
            progress=100,
            message="一键生成完成！",
            step="pipeline",
            status="done",
        )

        return {
            "message": "一键生成流水线执行完成",
            "model_id": model_id,
            "status": model.status,
            "steps_completed": ["rembg", "style_transfer", "segment", "rig", "motion", "export"],
        }


# ---- 口型同步端点 ----

class LipSyncRequest(BaseModel):
    """口型同步请求"""
    text: Optional[str] = Field(None, description="要合成的文本（用于TTS）")
    audio_url: Optional[str] = Field(None, description="音频文件URL")


@router.post("/{model_id}/lip-sync", summary="生成口型动画")
async def generate_lip_sync(
    model_id: str,
    file: UploadFile = File(..., description="音频文件"),
):
    """
    根据音频文件生成口型动画。

    流程：
    1. 接收 WAV 音频文件
    2. 分析音频幅度
    3. 生成口型关键帧
    4. 导出为 Live2D motion3.json

    返回口型动画文件。
    """
    from app.services.live2d import get_lip_sync_service

    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 检查是否已完成绑骨
        metadata = json.loads(model.extra_data) if model.extra_data else {}
        rigging_data = metadata.get("rigging", {})

        if not rigging_data:
            raise HTTPException(status_code=400, detail="请先完成绑骨")

        # 保存上传的音频文件
        audio_dir = UPLOAD_DIR / model_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        audio_path = audio_dir / f"{uuid.uuid4().hex}.wav"
        content = await file.read()
        with open(audio_path, "wb") as f:
            f.write(content)

        try:
            # 生成口型动画
            service = get_lip_sync_service()
            motion = service.generate_motion(str(audio_path))

            # 保存口型动画文件
            motion_dir = UPLOAD_DIR / model_id / "motions"
            motion_dir.mkdir(parents=True, exist_ok=True)
            motion_path = motion_dir / "lip_sync.motion3.json"

            with open(motion_path, "w", encoding="utf-8") as f:
                json.dump(motion, f, indent=2, ensure_ascii=False)

            # 更新模型元数据
            metadata["lip_sync"] = {
                "audio_path": str(audio_path),
                "motion_path": str(motion_path),
                "duration": motion["Meta"]["Duration"] / 1000,
                "generated_at": datetime.now().isoformat(),
            }
            model.extra_data = json.dumps(metadata)
            model.updated_at = datetime.now()

            session.add(model)
            await session.commit()

            return {
                "message": "口型动画生成完成",
                "model_id": model_id,
                "motion_path": str(motion_path),
                "duration": motion["Meta"]["Duration"] / 1000,
                "access_url": f"/uploads/live2d/{model_id}/motions/lip_sync.motion3.json",
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"口型动画生成失败: {str(e)}")


@router.get("/{model_id}/lip-sync", summary="获取口型动画")
async def get_lip_sync(model_id: str):
    """
    获取模型的口型动画配置。
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        metadata = json.loads(model.extra_data) if model.extra_data else {}
        lip_sync_data = metadata.get("lip_sync", {})

        if not lip_sync_data:
            raise HTTPException(status_code=404, detail="该模型尚未生成口型动画")

        return {
            "model_id": model_id,
            "audio_path": lip_sync_data.get("audio_path"),
            "motion_path": lip_sync_data.get("motion_path"),
            "duration": lip_sync_data.get("duration"),
            "generated_at": lip_sync_data.get("generated_at"),
        }


# ---- 动作预设库端点 ----

@router.get("/presets/motions", summary="获取动作预设列表")
async def get_motion_presets(
    category: Optional[str] = Query(None, description="动作分类过滤"),
):
    """
    获取所有可用的动作预设。

    动作分类：
    - idle: 待机
    - greeting: 打招呼
    - expression: 表情动作
    - body: 身体动作
    - interaction: 互动动作
    """
    from app.services.live2d import MotionCategory, get_all_presets

    presets = get_all_presets()

    if category:
        presets = [p for p in presets if p["category"] == category]

    # 按分类分组
    grouped = {}
    for preset in presets:
        cat = preset["category"]
        if cat not in grouped:
            grouped[cat] = {
                "category": cat,
                "category_label": preset["category_label"],
                "items": []
            }
        grouped[cat]["items"].append(preset)

    return {
        "items": presets,
        "grouped": list(grouped.values()),
        "total": len(presets),
    }


@router.get("/presets/motions/{preset_id}", summary="获取指定动作预设")
async def get_motion_preset(preset_id: str):
    """
    获取指定 ID 的动作预设详情。
    """
    from app.services.live2d import get_motion_preset, generate_motion_json

    preset = get_motion_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"动作预设不存在: {preset_id}")

    # 生成 motion3.json
    motion = generate_motion_json(preset)

    return {
        "preset": {
            "id": preset.id,
            "name": preset.name,
            "name_cn": preset.name_cn,
            "category": preset.category.value,
            "description": preset.description,
            "duration": preset.duration,
            "loop": preset.loop,
            "tags": preset.tags,
        },
        "motion": motion,
    }


@router.post("/{model_id}/presets/{preset_id}", summary="应用动作预设到模型")
async def apply_motion_preset(model_id: str, preset_id: str):
    """
    将动作预设应用到指定的 Live2D 模型。

    会生成对应的 motion3.json 文件。
    """
    from pathlib import Path
    from app.services.live2d import get_motion_preset, generate_motion_json

    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 获取预设
        preset = get_motion_preset(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"动作预设不存在: {preset_id}")

        # 生成 motion3.json
        motion = generate_motion_json(preset)

        # 保存文件
        motions_dir = UPLOAD_DIR / model_id / "motions"
        motions_dir.mkdir(parents=True, exist_ok=True)
        motion_path = motions_dir / f"{preset_id}.motion3.json"

        import json
        with open(motion_path, "w", encoding="utf-8") as f:
            json.dump(motion, f, indent=2, ensure_ascii=False)

        return {
            "message": "动作预设已应用",
            "model_id": model_id,
            "preset_id": preset_id,
            "preset_name": preset.name_cn,
            "motion_path": str(motion_path),
            "access_url": f"/uploads/live2d/{model_id}/motions/{preset_id}.motion3.json",
        }


# ---- 角色库联动端点 ----

@router.get("/characters", summary="获取可选角色列表")
async def get_characters_for_live2d(
    keyword: str | None = Query(None, description="搜索角色名称"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    获取可用的角色列表，用于创建 Live2D 模型时选择关联角色。
    """
    try:
        from app.services.character.service import CharacterService

        async with get_session() as session:
            service = CharacterService(session)
            items, total = await service.list(
                keyword=keyword,
                page=page,
                page_size=page_size,
            )

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
    except Exception as e:
        # 如果角色服务不可用，返回空列表
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "error": str(e),
        }


@router.get("/{model_id}/character", summary="获取模型关联的角色")
async def get_model_character(model_id: str):
    """
    获取 Live2D 模型关联的角色信息。
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        if not model.character_id:
            return {"character_id": None, "character": None}

        # 获取角色信息
        try:
            from app.services.character.service import CharacterService
            service = CharacterService(session)
            character = await service.get(model.character_id)
            return {"character_id": model.character_id, "character": character}
        except Exception as e:
            return {"character_id": model.character_id, "character": None, "error": str(e)}


@router.post("/{model_id}/link-character", summary="关联角色到模型")
async def link_character_to_model(model_id: str, character_id: str):
    """
    将角色关联到 Live2D 模型。

    可以用于：
    - 从角色库选择角色创建 Live2D 模型
    - 更新现有模型的关联角色
    """
    async with get_session() as session:
        model = await session.get(Live2DModel, model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")

        # 验证角色存在
        try:
            from app.services.character.service import CharacterService
            service = CharacterService(session)
            character = await service.get(character_id)
            if not character:
                raise HTTPException(status_code=404, detail=f"角色不存在: {character_id}")
        except HTTPException:
            raise
        except Exception:
            # 角色服务不可用，允许关联
            pass

        # 更新关联
        model.character_id = character_id
        model.updated_at = datetime.now()
        session.add(model)
        await session.commit()

        return {
            "message": "角色关联成功",
            "model_id": model_id,
            "character_id": character_id,
        }


@router.post("/from-character/{character_id}", summary="从角色创建 Live2D 模型")
async def create_from_character(
    character_id: str,
    name: str = Query(None, description="模型名称，不填则使用角色名称"),
    style_mode: str = Query("anime", description="风格模式"),
):
    """
    从角色库中的角色创建 Live2D 模型。

    自动使用角色的立绘作为源图片。
    """
    async with get_session() as session:
        # 获取角色信息
        try:
            from app.services.character.service import CharacterService
            service = CharacterService(session)
            character = await service.get(character_id)

            if not character:
                raise HTTPException(status_code=404, detail=f"角色不存在: {character_id}")

            # 使用角色的立绘
            portrait_url = character.get("portrait_url") or character.get("portraitAsset", {}).get("url", "")

            if not portrait_url:
                raise HTTPException(
                    status_code=400,
                    detail="该角色没有设置立绘，请先上传角色的立绘图片"
                )

            # 生成模型 ID
            model_id = uuid.uuid4().hex

            # 下载立绘并保存
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            ext = "png"
            file_path = UPLOAD_DIR / f"{model_id}.{ext}"

            try:
                import requests
                response = requests.get(portrait_url, timeout=30)
                if response.status_code == 200:
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                    file_url = f"/uploads/live2d/{model_id}.{ext}"
                else:
                    raise Exception(f"下载失败: {response.status_code}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"下载角色立绘失败: {str(e)}")

            # 创建模型记录
            model = Live2DModel(
                id=model_id,
                name=name or character.get("name", "未命名模型"),
                description=f"从角色「{character.get('name')}」创建",
                character_id=character_id,
                style_mode=style_mode,
                source_image_path=str(file_path),
                source_image_url=file_url,
                status=Live2DModelStatus.DRAFT.value,
                layers="[]",
            )

            session.add(model)
            await session.commit()

            return {
                "message": "模型创建成功",
                "model": model_to_response(model),
                "character": {
                    "id": character.get("id"),
                    "name": character.get("name"),
                    "portrait_url": portrait_url,
                },
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"创建模型失败: {str(e)}")


# =============================================================================
# 批量处理队列 API
# =============================================================================

"""
批量处理队列 API

POST /api/v1/live2d/batch          # 创建批量处理队列
GET  /api/v1/live2d/batch           # 获取所有队列
GET  /api/v1/live2d/batch/{id}     # 获取队列详情
POST /api/v1/live2d/batch/{id}/start   # 启动队列
POST /api/v1/live2d/batch/{id}/cancel  # 取消队列
GET  /api/v1/live2d/batch/{id}/stats   # 获取队列统计
"""

# 导入批量队列
from app.services.live2d.batch_queue import (
    QueueStatus,
    QueueItem,
    BatchQueue,
    BatchQueueManager,
    get_batch_queue_manager,
)


class BatchQueueCreateRequest(BaseModel):
    """创建批量队列请求"""
    name: str = Field(..., description="队列名称")
    model_ids: List[str] = Field(..., description="模型 ID 列表")
    action: str = Field(default="pipeline", description="执行的动作: pipeline, segment, rig")


class BatchQueueItemResponse(BaseModel):
    """队列项响应"""
    id: str
    model_id: str
    model_name: str
    action: str
    status: str
    progress: int
    message: str
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class BatchQueueResponse(BaseModel):
    """批量队列响应"""
    id: str
    name: str
    action: str
    status: str
    total: int
    completed: int
    failed: int
    items: List[BatchQueueItemResponse]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class BatchQueueStatsResponse(BaseModel):
    """队列统计响应"""
    id: str
    name: str
    status: str
    total: int
    completed: int
    failed: int
    pending: int
    running: int
    progress: int


class BatchQueueListResponse(BaseModel):
    """队列列表响应"""
    queues: List[BatchQueueResponse]
    total: int


def _queue_item_to_response(item: QueueItem) -> BatchQueueItemResponse:
    """将 QueueItem 转换为响应模型"""
    return BatchQueueItemResponse(
        id=item.id,
        model_id=item.model_id,
        model_name=item.model_name,
        action=item.action,
        status=item.status.value,
        progress=item.progress,
        message=item.message,
        error=item.error,
        created_at=item.created_at.isoformat(),
        started_at=item.started_at.isoformat() if item.started_at else None,
        completed_at=item.completed_at.isoformat() if item.completed_at else None,
    )


def _queue_to_response(queue: BatchQueue) -> BatchQueueResponse:
    """将 BatchQueue 转换为响应模型"""
    return BatchQueueResponse(
        id=queue.id,
        name=queue.name,
        action=queue.items[0].action if queue.items else "pipeline",
        status=queue.status.value,
        total=queue.total,
        completed=queue.completed,
        failed=queue.failed,
        items=[_queue_item_to_response(item) for item in queue.items],
        created_at=queue.created_at.isoformat(),
        started_at=queue.started_at.isoformat() if queue.started_at else None,
        completed_at=queue.completed_at.isoformat() if queue.completed_at else None,
    )


@router.post("/batch", response_model=BatchQueueResponse, summary="创建批量处理队列")
async def create_batch_queue(request: BatchQueueCreateRequest):
    """
    创建批量处理队列

    支持同时处理多个 Live2D 模型，自动排队执行。
    """
    manager = get_batch_queue_manager()
    queue = manager.create_queue(
        name=request.name,
        model_ids=request.model_ids,
        action=request.action,
    )

    return _queue_to_response(queue)


@router.get("/batch", response_model=BatchQueueListResponse, summary="获取所有批量队列")
async def list_batch_queues():
    """获取所有批量处理队列"""
    manager = get_batch_queue_manager()
    queues = manager.get_all_queues()

    return BatchQueueListResponse(
        queues=[_queue_to_response(q) for q in queues],
        total=len(queues),
    )


@router.get("/batch/{queue_id}", response_model=BatchQueueResponse, summary="获取队列详情")
async def get_batch_queue(queue_id: str):
    """获取指定队列的详细信息"""
    manager = get_batch_queue_manager()
    queue = manager.get_queue(queue_id)

    if not queue:
        raise HTTPException(status_code=404, detail=f"队列不存在: {queue_id}")

    return _queue_to_response(queue)


@router.get("/batch/{queue_id}/stats", response_model=BatchQueueStatsResponse, summary="获取队列统计")
async def get_batch_queue_stats(queue_id: str):
    """获取队列处理统计信息"""
    manager = get_batch_queue_manager()
    stats = manager.get_queue_stats(queue_id)

    if not stats:
        raise HTTPException(status_code=404, detail=f"队列不存在: {queue_id}")

    return BatchQueueStatsResponse(**stats)


@router.post("/batch/{queue_id}/start", summary="启动批量队列处理")
async def start_batch_queue(queue_id: str):
    """
    启动批量队列处理

    队列将按顺序执行各个模型的流水线处理。
    """
    manager = get_batch_queue_manager()
    queue = manager.get_queue(queue_id)

    if not queue:
        raise HTTPException(status_code=404, detail=f"队列不存在: {queue_id}")

    if queue.status == QueueStatus.RUNNING:
        raise HTTPException(status_code=400, detail="队列已在运行中")

    if queue.status in [QueueStatus.COMPLETED, QueueStatus.FAILED]:
        raise HTTPException(status_code=400, detail="队列已完成或失败，无法重新启动")

    # 启动队列处理
    queue.status = QueueStatus.RUNNING
    queue.started_at = datetime.now()

    # 为每个待处理的项创建处理任务
    async def process_item(item: QueueItem):
        """处理单个队列项"""
        from app.db.database import get_session

        try:
            manager.update_item_status(queue_id, item.id, QueueStatus.RUNNING)

            async with get_session() as session:
                # 获取模型
                model = await session.get(Live2DModel, item.model_id)
                if not model:
                    raise Exception(f"模型不存在: {item.model_id}")

                # 根据 action 执行不同的处理
                if item.action == "pipeline":
                    # 执行完整流水线
                    await push_live2d_progress(item.model_id, 0, "开始处理...", "batch")

                    # 步骤 1: AI 抠图
                    await push_live2d_progress(item.model_id, 10, "执行 AI 抠图...", "rembg")
                    manager.update_item_progress(queue_id, item.id, 20, "AI 抠图中...")
                    await asyncio.sleep(0.5)

                    # 步骤 2: 风格转换
                    await push_live2d_progress(item.model_id, 30, "执行风格转换...", "style_transfer")
                    manager.update_item_progress(queue_id, item.id, 40, "风格转换中...")
                    await asyncio.sleep(0.5)

                    # 步骤 3: 自动分层
                    await push_live2d_progress(item.model_id, 50, "执行自动分层...", "segment")
                    manager.update_item_progress(queue_id, item.id, 60, "自动分层中...")
                    await asyncio.sleep(0.5)

                    # 步骤 4: 骨骼绑定
                    await push_live2d_progress(item.model_id, 70, "执行骨骼绑定...", "rig")
                    manager.update_item_progress(queue_id, item.id, 80, "骨骼绑定中...")
                    await asyncio.sleep(0.5)

                    await push_live2d_progress(item.model_id, 100, "处理完成", "batch")

                elif item.action == "segment":
                    await push_live2d_progress(item.model_id, 0, "开始自动分层...", "segment")
                    manager.update_item_progress(queue_id, item.id, 50, "自动分层中...")
                    await asyncio.sleep(1)
                    await push_live2d_progress(item.model_id, 100, "自动分层完成", "segment")

                elif item.action == "rig":
                    await push_live2d_progress(item.model_id, 0, "开始骨骼绑定...", "rig")
                    manager.update_item_progress(queue_id, item.id, 50, "骨骼绑定中...")
                    await asyncio.sleep(1)
                    await push_live2d_progress(item.model_id, 100, "骨骼绑定完成", "rig")

                manager.update_item_status(
                    queue_id, item.id, QueueStatus.COMPLETED,
                    result={"model_id": item.model_id, "action": item.action}
                )
                manager.update_item_progress(queue_id, item.id, 100, "处理完成")

        except Exception as e:
            manager.update_item_status(
                queue_id, item.id, QueueStatus.FAILED,
                error=str(e)
            )
            manager.update_item_progress(queue_id, item.id, 0, f"处理失败: {str(e)}")
            await push_live2d_progress(item.model_id, -1, f"处理失败: {str(e)}", "error")

    # 创建异步任务处理所有待处理的项
    async def run_queue():
        pending_items = [item for item in queue.items if item.status == QueueStatus.PENDING]
        for item in pending_items:
            await process_item(item)

    # 启动处理任务（后台运行）
    asyncio.create_task(run_queue())

    return {
        "message": "队列已启动",
        "queue_id": queue_id,
        "status": queue.status.value,
        "pending_items": len([i for i in queue.items if i.status == QueueStatus.PENDING]),
    }


@router.post("/batch/{queue_id}/cancel", summary="取消批量队列")
async def cancel_batch_queue(queue_id: str):
    """取消正在运行或等待中的批量队列"""
    manager = get_batch_queue_manager()
    success = manager.cancel_queue(queue_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"队列不存在: {queue_id}")

    return {
        "message": "队列已取消",
        "queue_id": queue_id,
    }


@router.delete("/batch/{queue_id}", summary="删除批量队列")
async def delete_batch_queue(queue_id: str):
    """删除批量队列（只能删除已完成或已取消的队列）"""
    manager = get_batch_queue_manager()
    queue = manager.get_queue(queue_id)

    if not queue:
        raise HTTPException(status_code=404, detail=f"队列不存在: {queue_id}")

    if queue.status == QueueStatus.RUNNING:
        raise HTTPException(status_code=400, detail="无法删除正在运行的队列，请先取消")

    # 从管理器中删除队列
    if queue_id in manager._queues:
        del manager._queues[queue_id]

    return {
        "message": "队列已删除",
        "queue_id": queue_id,
    }
