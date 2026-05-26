"""
YLCraft — AI 连接器 API

GET    /api/v1/ai/connectors           — 列出所有 AI 连接
GET    /api/v1/ai/connectors/supported  — 获取支持的 AI 提供商
GET    /api/v1/ai/connectors/{id}       — 获取连接详情
POST   /api/v1/ai/connectors            — 创建新连接
PUT    /api/v1/ai/connectors/{id}       — 更新连接
DELETE /api/v1/ai/connectors/{id}       — 删除连接
POST   /api/v1/ai/connectors/{id}/test  — 测试连接
GET    /api/v1/ai/connectors/{id}/usage — 获取使用统计
POST   /api/v1/ai/connectors/{id}/use   — 标记为已使用
GET    /api/v1/ai/connectors/export    — 导出所有连接为 JSON
POST   /api/v1/ai/connectors/import    — 从 JSON 导入连接
"""

from __future__ import annotations

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlmodel import Session, SQLModel

from app.db.database import get_session
from app.db.models.ai_connector import (
    AIConnectorCreate,
    AIConnectorUpdate,
    AIConnectorResponse,
    AIProvider,
    AIConnector,
    AIProviderType,
)
from app.services.ai_connector.service import AIConnectorService
from app.services.llm.manager import init_manager as llm_init_manager

logger = logging.getLogger("ylcraft.api.ai")

router = APIRouter(tags=["AI Connectors"])

# =============================================================================
# 支持的 AI 提供商列表
# =============================================================================

# 简化的 AI Provider 配置（全部使用 OpenAI 兼容 API）
SUPPORTED_AI_PROVIDERS = [
    {
        "value": "openai",
        "label": "OpenAI",
        "color": "#10a37f",
        "icon": "brain",
        "models": [],  # 用户自定义
        "default_model": "gpt-4o",
        "supports_images": True,
        "supports_streaming": True,
    },
    {
        "value": "siliconflow",
        "label": "硅基流动 (SiliconFlow)",
        "color": "#00d4aa",
        "icon": "cloud",
        "models": [],  # 用户自定义
        "default_model": "Qwen/Qwen2.5-VL-32B-Instruct",
        "supports_images": True,
        "supports_streaming": True,
        "base_url": "https://api.siliconflow.cn/v1",
    },
    {
        "value": "gemini",
        "label": "Google Gemini",
        "color": "#4285f4",
        "icon": "globe",
        "models": [],  # 用户自定义
        "default_model": "gemini-1.5-flash",
        "supports_images": True,
        "supports_streaming": True,
    },
    {
        "value": "generic",
        "label": "通用配置 (Generic)",
        "color": "#94a3b8",
        "icon": "settings",
        "models": [],  # 完全自定义
        "default_model": "",
        "supports_images": True,
        "supports_streaming": True,
    },
]


# =============================================================================
# 依赖注入
# =============================================================================

from app.db.database import AsyncSessionLocal

async def get_ai_service():
    """获取 AI 连接服务（异步 session）"""
    async with AsyncSessionLocal() as session:
        yield AIConnectorService(session)


# =============================================================================
# API 端点
# =============================================================================

@router.get("/supported", summary="获取支持的 AI 提供商")
async def get_supported_ai_providers():
    """返回所有支持的 AI 提供商和模型"""
    return {
        "success": True,
        "providers": SUPPORTED_AI_PROVIDERS,
    }


@router.get("", summary="列出所有 AI 连接")
async def list_connectors(
    provider: Optional[str] = Query(None, description="按提供商筛选"),
    provider_type: Optional[str] = Query(None, description="按类型筛选：llm/image/video/tts/stt"),
    active_only: bool = Query(False, description="仅显示活跃"),
    service: AIConnectorService = Depends(get_ai_service),
):
    """列出所有 AI 连接（不返回 API Key）"""
    if provider:
        # provider 现在是字符串，直接使用
        conns = await service.list_by_provider(provider)
    elif provider_type:
        # 按类型筛选
        conns = await service.list_by_type(provider_type)
    elif active_only:
        conns = await service.list_active()
    else:
        conns = await service.list_all()

    return {
        "success": True,
        "connectors": [AIConnectorResponse.from_db(c) for c in conns],
        "total": len(conns),
    }


# =============================================================================
# 导入 / 导出 / 重载（必须放在 /{conn_id} 之前，避免路径冲突）
# =============================================================================

@router.post("/reload", summary="重新加载所有 AI 连接器配置，立即生效，无需重启")
async def reload_connectors():
    """立即重新加载所有 AI 连接器配置，不用重启后端"""
    try:
        from app.db.database import get_session
        session = next(get_session())
        llm_init_manager(session=session)
        logger.info("[AI Connectors] 已成功重新加载所有 AI 连接器配置")
        return {
            "success": True,
            "message": "配置重新加载成功，立即生效",
        }
    except Exception as e:
        logger.error(f"[AI Connectors] 重新加载配置失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"重新加载失败: {str(e)}")


@router.get("/export", summary="导出所有 AI 连接为 JSON")
async def export_connectors(
    service: AIConnectorService = Depends(get_ai_service),
):
    """导出所有 AI 连接为 JSON（包含完整的 API Key，用于备份/迁移）
    
    返回格式：所有 JSON 字段都解析为 Python 对象（列表/字典），方便导入
    """
    try:
        conns = await service.list_all()
        result = []
        for c in conns:
            # 辅助函数：解析 JSON 字符串为 Python 对象
            def parse_json(val):
                if val is None:
                    return None
                if isinstance(val, (list, dict)):
                    return val
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            
            result.append({
                "id": c.id,
                "provider": c.provider,
                "name": c.name,
                "api_key": c.api_key,
                "provider_type": c.provider_type.value if hasattr(c.provider_type, "value") else str(c.provider_type),
                "base_url": c.base_url,
                "api_endpoint": c.api_endpoint,
                "organization_id": c.organization_id,
                "project_id": c.project_id,
                "default_model": c.default_model,
                "available_models": c.get_available_models(),  # 已经是列表
                "max_tokens": c.max_tokens,
                "temperature": c.temperature,
                "monthly_budget": c.monthly_budget,
                "daily_limit": c.daily_limit,
                "price_per_call": c.price_per_call,
                "is_active": c.is_active,
                "is_default": c.is_default,
                "priority": c.priority,
                "description": c.description,
                "request_template": c.request_template,
                "response_config": parse_json(c.response_config),  # 解析为字典
                "parameter_transforms": parse_json(c.parameter_transforms),  # 解析为字典
                "supported_sizes": parse_json(c.supported_sizes),  # 解析为列表
                "default_params": parse_json(c.default_params),  # 解析为字典
                "support_reference_image": c.support_reference_image,
                "support_multiple_reference_images": c.support_multiple_reference_images,
                "reference_image_field": c.reference_image_field,
                "reference_image_array_field": c.reference_image_array_field,
                "test_prompt": c.test_prompt,
                "api_format": getattr(c, 'api_format', 'custom'),
                "embedding_type": c.embedding_type,
                "embedding_dimension": c.embedding_dimension,
                "normalize_embeddings": c.normalize_embeddings,
            })
        return {
            "success": True,
            "connectors": result,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.exception(f"[AIConnector] 导出失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


class ImportRequest(SQLModel):
    """导入请求"""
    connectors: List[Dict[str, Any]]
    mode: str = "upsert"  # upsert: 存在则更新，不存在则创建；create_only: 仅创建


@router.post("/import", summary="从 JSON 导入 AI 连接")
async def import_connectors(
    req: ImportRequest,
    service: AIConnectorService = Depends(get_ai_service),
):
    """从 JSON 导入 AI 连接
    mode=upsert: id 已存在则更新，不存在则创建
    mode=create_only: 仅创建新连接，id 冲突则跳过
    """
    imported = 0
    updated = 0
    skipped = 0
    failed = 0  # 新增：失败计数
    errors = []
    mode = req.mode or "upsert"
    for idx, item in enumerate(req.connectors):
        try:
            raw_id = item.get("id")
            if not raw_id:
                errors.append(f"第 {idx + 1} 项缺少 id，跳过")
                skipped += 1
                continue

            pt = item.get("provider_type", "llm")
            # 检查 pt 是否是有效的 AIProviderType 值，并转换为枚举
            try:
                pt_enum = AIProviderType(pt)
            except ValueError:
                pt_enum = AIProviderType.llm  # 默认值

            # 辅助函数：预处理导入数据，统一转换为 Pydantic 期望的格式
            def preprocess_field(val, field_type="str"):
                """预处理字段值
                - field_type="str": 期望字符串（JSON 字段），将 dict/list 转为 JSON 字符串
                - field_type="list": 期望列表，将字符串解析为列表
                """
                if val is None:
                    return [] if field_type == "list" else None
                
                if field_type == "list":
                    # 期望 list
                    if isinstance(val, list):
                        return val
                    if isinstance(val, str):
                        try:
                            parsed = json.loads(val)
                            return parsed if isinstance(parsed, list) else []
                        except (json.JSONDecodeError, TypeError):
                            return []
                    return []
                else:
                    # 期望 str (JSON 字符串)
                    if isinstance(val, str):
                        return val
                    if isinstance(val, (dict, list)):
                        return json.dumps(val, ensure_ascii=False)
                    return None

            # 预处理数据，确保符合 Pydantic 验证要求
            processed_item = item.copy()
            processed_item["available_models"] = preprocess_field(
                item.get("available_models"), "list"
            )
            for field in ["response_config", "parameter_transforms", "supported_sizes", "default_params"]:
                processed_item[field] = preprocess_field(
                    item.get(field), "str"
                )

            # 使用预处理后的数据创建 Pydantic 模型
            create_data = AIConnectorCreate(
                provider=processed_item.get("provider", "generic"),
                name=processed_item.get("name", "未命名"),
                api_key=processed_item.get("api_key", ""),
                provider_type=pt_enum,
                base_url=processed_item.get("base_url"),
                api_endpoint=processed_item.get("api_endpoint"),
                organization_id=processed_item.get("organization_id"),
                project_id=processed_item.get("project_id"),
                default_model=processed_item.get("default_model", "gpt-4o"),
                available_models=processed_item.get("available_models", []),
                max_tokens=processed_item.get("max_tokens", 4096),
                temperature=processed_item.get("temperature", 0.7),
                monthly_budget=processed_item.get("monthly_budget"),
                daily_limit=processed_item.get("daily_limit"),
                price_per_call=processed_item.get("price_per_call"),
                is_active=processed_item.get("is_active", True),
                is_default=processed_item.get("is_default", False),
                priority=processed_item.get("priority", 0),
                description=processed_item.get("description", ""),
                request_template=processed_item.get("request_template"),
                response_config=processed_item.get("response_config"),
                parameter_transforms=processed_item.get("parameter_transforms"),
                supported_sizes=processed_item.get("supported_sizes"),
                default_params=processed_item.get("default_params"),
                support_reference_image=processed_item.get("support_reference_image", False),
                support_multiple_reference_images=processed_item.get("support_multiple_reference_images", False),
                reference_image_field=processed_item.get("reference_image_field", "image"),
                reference_image_array_field=processed_item.get("reference_image_array_field"),
                test_prompt=processed_item.get("test_prompt"),
                embedding_type=processed_item.get("embedding_type"),
                embedding_dimension=processed_item.get("embedding_dimension"),
                normalize_embeddings=processed_item.get("normalize_embeddings", True),
            )

            existing = await service.get(raw_id)
            if existing:
                if mode == "create_only":
                    skipped += 1  # 有意跳过（id 已存在）
                    continue
                await service.update(raw_id, AIConnectorUpdate(**create_data.model_dump()))
                updated += 1
            else:
                from app.db.database import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    # 将 Pydantic 模型转换为字典
                    data_dict = create_data.model_dump()
                    
                    # 将列表/字典字段转换为 JSON 字符串（数据库存储格式）
                    if isinstance(data_dict.get("available_models"), list):
                        data_dict["available_models"] = json.dumps(data_dict["available_models"], ensure_ascii=False)
                    
                    # 确保其他 JSON 字段是字符串
                    for json_field in ["response_config", "parameter_transforms", "supported_sizes", "default_params"]:
                        val = data_dict.get(json_field)
                        if val is not None and not isinstance(val, str):
                            data_dict[json_field] = json.dumps(val, ensure_ascii=False)
                    
                    # 将 provider_type 转换为字符串（数据库存储枚举值）
                    if hasattr(data_dict.get("provider_type"), "value"):
                        data_dict["provider_type"] = data_dict["provider_type"].value
                    
                    conn = AIConnector(id=raw_id, **data_dict)
                    session.add(conn)
                    await session.commit()
                imported += 1
        except Exception as e:
            logger.exception(f"[AIConnector] 导入第 {idx + 1} 项失败: {e}")
            errors.append(f"第 {idx + 1} 项 ({item.get('id', '未知')}) 导入失败: {str(e)}")
            failed += 1  # 改为 failed，不是 skipped

    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,  # 新增：返回失败计数
        "errors": errors,
        "message": f"导入完成: 新建 {imported} 个, 更新 {updated} 个, 跳过 {skipped} 个, 失败 {failed} 个",
    }


# =============================================================================
# 单个连接器操作 (带 {conn_id} 的路径参数，必须放在上面特定路径之后)
# =============================================================================

@router.get("/{conn_id}", summary="获取连接详情")
async def get_connector(
    conn_id: str,
    service: AIConnectorService = Depends(get_ai_service),
):
    """获取单个连接详情（不返回 API Key）"""
    conn = await service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connector": AIConnectorResponse.from_db(conn),
    }


@router.post("", summary="创建 AI 连接")
async def create_connector(
    data: AIConnectorCreate,
    service: AIConnectorService = Depends(get_ai_service),
):
    """创建新的 AI 连接"""
    try:
        conn = await service.create(data)
        return {
            "success": True,
            "connector": AIConnectorResponse.from_db(conn),
            "message": f"AI 连接 {conn.name} 创建成功",
        }
    except Exception as e:
        logger.exception(f"[AIConnector] 创建连接失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.put("/{conn_id}", summary="更新 AI 连接")
async def update_connector(
    conn_id: str,
    data: AIConnectorUpdate,
    service: AIConnectorService = Depends(get_ai_service),
):
    """更新 AI 连接"""
    conn = await service.update(conn_id, data)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "connector": AIConnectorResponse.from_db(conn),
        "message": "更新成功",
    }


@router.delete("/{conn_id}", summary="删除 AI 连接")
async def delete_connector(
    conn_id: str,
    service: AIConnectorService = Depends(get_ai_service),
):
    """删除 AI 连接"""
    ok = await service.delete(conn_id)
    if not ok:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {
        "success": True,
        "message": "删除成功",
    }


class TestRequest(SQLModel):
    body: Optional[dict] = None


@router.post("/{conn_id}/test", summary="测试连接")
async def test_connector(
    conn_id: str,
    test_request: Optional[TestRequest] = None,
    service: AIConnectorService = Depends(get_ai_service),
):
    """测试 AI 连接有效性"""
    custom_body = test_request.body if test_request else None
    result = await service.test_connection(conn_id, custom_body)
    return {
        "success": result["success"],
        "message": result["message"],
        "connector_id": conn_id,
        "debug": result.get("debug"),
    }


@router.get("/{conn_id}/usage", summary="获取使用统计")
async def get_usage_stats(
    conn_id: str,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    service: AIConnectorService = Depends(get_ai_service),
):
    """获取 AI 连接的使用统计"""
    conn = await service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    stats = await service.get_usage_stats(conn_id, days)
    return {
        "success": True,
        "connector_id": conn_id,
        "stats": stats,
    }


@router.post("/{conn_id}/use", summary="标记为已使用")
async def mark_used(
    conn_id: str,
    service: AIConnectorService = Depends(get_ai_service),
):
    """标记连接已使用"""
    conn = await service.get(conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    conn.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
    service.session.add(conn)
    await service.session.commit()

    return {
        "success": True,
        "message": "已更新使用时间",
    }


# =============================================================================
# 模型发现 API
# =============================================================================

@router.get("/discover-models", summary="发现可用模型")
async def discover_models(
    api_format: str = Query("custom", description="API 格式：openai_sdk / openai_sdk_responses / custom"),
    base_url: str = Query(..., description="API Base URL"),
    api_key: str = Query("", description="API Key"),
    models_endpoint: str = Query("/v1/models", description="模型列表端点（custom 模式有效）"),
):
    """
    根据 api_format 自动选择发现方式：

    - openai_sdk / openai_sdk_responses: 使用 openai.OpenAI(...).models.list() 获取模型列表
    - custom: 使用 httpx GET {base_url}{models_endpoint} 获取模型列表

    返回统一格式: { models: [...], error: null|string }
    """
    import httpx

    if api_format.startswith("openai_sdk"):
        try:
            import openai

            client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url or None,
                timeout=30.0,
            )
            model_list = client.models.list()

            # 过滤掉非对话模型（常见的 prefix 过滤）
            # GPT/Claude/Qwen/DeepSeek/Gemini 等常见命名模式
            filtered_models = []
            for m in model_list.data:
                model_id = m.id.lower() if hasattr(m, 'id') else str(m)
                # 跳过已知的非对话模型（embedding, moderation, tts, whisper, dall-e 等）
                skip_prefixes = (
                    'text-embedding', 'text-moderation', 'tts-', 'whisper-',
                    'dall-e', 'babbage', 'davinci', 'curie', 'ada-',
                )
                if any(model_id.startswith(p) for p in skip_prefixes):
                    continue
                # 跳过纯数字 ID（可能是 fine-tuned 或其他非标准模型）
                if model_id.isdigit():
                    continue
                filtered_models.append(m.id)

            client.close()
            return {
                "success": True,
                "models": filtered_models,
                "error": None,
            }

        except ImportError:
            return {
                "success": False,
                "models": [],
                "error": "openai 包未安装，请运行 pip install openai",
            }
        except openai.APIError as e:
            return {
                "success": False,
                "models": [],
                "error": f"API 错误: {e}",
            }
        except Exception as e:
            logger.error(f"[discover-models] SDK 方式失败: {e}")
            return {
                "success": False,
                "models": [],
                "error": str(e),
            }

    else:
        # custom 模式：HTTP GET {base_url}{models_endpoint}
        try:
            base = base_url.rstrip("/")
            endpoint = models_endpoint if models_endpoint.startswith("/") else f"/{models_endpoint}"
            url = f"{base}{endpoint}"

            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            # 兼容 OpenAI /v1/models 响应格式: { data: [{ id: "model-name" }, ...] }
            raw_models = data.get("data", []) if isinstance(data, dict) else data
            if isinstance(raw_models, list):
                models = [
                    m.get("id", str(m))
                    if isinstance(m, dict)
                    else (m.id if hasattr(m, 'id') else str(m))
                    for m in raw_models
                ]
            else:
                models = []

            return {
                "success": True,
                "models": models,
                "error": None,
            }

        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "models": [],
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.error(f"[discover-models] HTTP 方式失败: {e}")
            return {
                "success": False,
                "models": [],
                "error": str(e),
            }


# =============================================================================
# 辅助函数
# =============================================================================


def get_default_connector(session: Session) -> Optional[AIConnector]:
    """获取默认 AI 连接"""
    service = AIConnectorService(session)
    return service.get_default()


def get_connector_by_provider(session: Session, provider: str) -> Optional[AIConnector]:
    """获取指定提供商的 AI 连接"""
    service = AIConnectorService(session)
    return service.get_by_provider(provider)
