"""
YLCraft — LLM API

POST /api/v1/llm/chat — 通用 LLM 对话接口
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.external_api_auth import optional_external_api_key
from app.db.models.external_api_key import ExternalApiKey
from app.services.ai import get_ai_service, AIService
from app.services.ai.types import LLMMessage
from app.services.platform_log import service as platform_log

router = APIRouter()
logger = logging.getLogger("ylcraft.llm")


async def _record_llm_platform_event(req: ChatRequest, result, *, error: str | None = None) -> None:
    from app.services.ai.types import LLMGenerationResult
    if result is None:
        result = LLMGenerationResult(success=False, error=error or "")
    await platform_log.record_event(
        scene="llm",
        task_type="llm_chat",
        level="info" if result.success else "error",
        status="success" if result.success else "failed",
        provider=result.provider or req.provider or "",
        model=result.model or req.model or "",
        message="文本生成成功" if result.success else "文本生成失败",
        error=result.error if not result.success else None,
        request={
            "messages": req.messages,
            "model": req.model or "",
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "provider": req.provider or "",
        },
        response={
            "content": (getattr(result, "content", "") or "")[:500],
            "usage": getattr(result, "usage", None),
        },
        duration_ms=result.latency_ms,
        retry_payload={
            "messages": req.messages,
            "model": req.model or "",
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "provider": req.provider or "",
        },
    )


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    provider: str | None = None
    log_scene: str | None = None
    log_ref_id: str | None = None
    log_stage: str | None = None
    log_request: dict | None = None


class ChatResponse(BaseModel):
    success: bool
    content: str = ""
    usage: dict | None = None
    error: str | None = None


class BackendInfo(BaseModel):
    name: str
    provider: str = ""
    provider_label: str = ""
    model: str
    available_models: list[str] = []
    support_vision_input: bool = False


class BackendsResponse(BaseModel):
    success: bool
    backends: list[BackendInfo] = []


@router.get("/backends", response_model=BackendsResponse, summary="获取可用的 LLM 后端列表")
async def list_llm_backends():
    """
    获取所有可用的 LLM 后端及其支持的模型列表。
    从数据库 AIConnector 表读取。
    """
    from app.db.database import SessionLocal
    manager = get_ai_service()

    try:
        with SessionLocal() as db_session:
            try:
                if not manager.is_loaded():
                    from pathlib import Path
                    config_path = Path(__file__).parent.parent.parent.parent / "config" / "providers.yaml"
                    AIService.initialize(str(config_path), session=db_session)
                    logger.info("AIService reinitialized from /llm/backends endpoint")
            except Exception as e:
                logger.warning(f"Reinitializing manager failed: {e}")

            from app.db.models.ai_connector import AIConnector
            connectors = db_session.query(AIConnector).filter(
                AIConnector.is_active == True,
                AIConnector.provider_type == 'llm'
            ).all()

            backends = []
            for conn in connectors:
                try:
                    name = conn.name
                    model = conn.default_model or ''
                    provider = conn.provider or ''

                    # provider_label 映射
                    provider_labels = {
                        "openai": "OpenAI",
                        "siliconflow": "硅基流动",
                        "gemini": "Google Gemini",
                        "generic": "通用配置",
                    }
                    provider_label = provider_labels.get(provider, provider)

                    available_models = []
                    if conn.available_models:
                        try:
                            import json
                            available_models = json.loads(conn.available_models) if isinstance(conn.available_models, str) else conn.available_models
                        except Exception:
                            pass
                    if not available_models and model:
                        available_models = [model]

                    backends.append(BackendInfo(
                        name=name,
                        provider=provider,
                        provider_label=provider_label,
                        model=model,
                        available_models=available_models,
                        support_vision_input=bool(conn.support_vision_input),
                    ))
                except Exception as e:
                    logger.warning(f"Failed to get backend info for {conn.name}: {e}")
                    continue

            return BackendsResponse(success=True, backends=backends)
    except Exception as e:
        logger.error(f"Failed to list LLM backends: {e}")
        return BackendsResponse(success=False, backends=[])


@router.post("/chat", response_model=ChatResponse, summary="LLM 对话")
async def chat(req: ChatRequest, external_key: Optional[ExternalApiKey] = Depends(optional_external_api_key)):
    """
    统一的 LLM 对话接口。
    """
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    try:
        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in req.messages
        ]
        result = await manager.chat(
            messages=llm_messages,
            provider=req.provider,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

        if req.log_scene or req.log_stage or req.log_ref_id:
            try:
                from app.db.database import get_async_session
                from app.db.models.creative_project import ProjectGenerationLog
                from app.services.creative_project.service import dumps_json

                async with get_async_session() as session:
                    session.add(
                        ProjectGenerationLog(
                            scene=req.log_scene or "llm_chat",
                            ref_id=req.log_ref_id,
                            stage=req.log_stage or "chat",
                            provider=result.provider or req.provider or "",
                            model=result.model or req.model or "",
                            status="success" if result.success else "failed",
                            prompt=dumps_json(req.messages),
                            request_json=dumps_json({
                                "messages": req.messages,
                                "provider": req.provider,
                                "model": req.model,
                                "temperature": req.temperature,
                                "max_tokens": req.max_tokens,
                                **(req.log_request or {}),
                            }),
                            raw_response=result.content or "",
                            normalized_json=dumps_json({"usage": result.usage or {}}),
                            validation_error=result.error or "",
                        )
                    )
                    await session.commit()
            except Exception as log_err:
                logger.warning(f"LLM chat log write failed: {log_err}")

        await _record_llm_platform_event(req, result)
        return ChatResponse(
            success=result.success,
            content=result.content,
            usage=result.usage,
            error=result.error,
        )
    except Exception as e:
        logger.error(f"LLM chat failed: {e}")
        await _record_llm_platform_event(req, None, error=str(e))
        return ChatResponse(success=False, error=str(e))
