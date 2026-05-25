"""
YLCraft — LLM API

POST /api/v1/llm/chat — 通用 LLM 对话接口
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm.manager import get_manager
from app.core.contracts.types import LLMMessage

router = APIRouter()
logger = logging.getLogger("ylcraft.llm")


class ChatRequest(BaseModel):
    messages: list[dict]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    provider: str | None = None


class ChatResponse(BaseModel):
    success: bool
    content: str = ""
    usage: dict | None = None
    error: str | None = None


class BackendInfo(BaseModel):
    name: str
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
    manager = get_manager()
    
    with SessionLocal() as db_session:
        try:
            if not manager.is_loaded():
                from app.services.llm.manager import init_manager
                from pathlib import Path
                config_path = Path(__file__).parent.parent.parent.parent / "config" / "providers.yaml"
                init_manager(str(config_path), session=db_session)
                logger.info("BackendManager reinitialized from /llm/backends endpoint")
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
async def chat(req: ChatRequest):
    """
    统一的 LLM 对话接口。
    """
    manager = get_manager()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="BackendManager 未初始化")

    try:
        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in req.messages
        ]
        result = await manager.chat(
            messages=llm_messages,
            provider=req.provider,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

        return ChatResponse(
            success=result.success,
            content=result.content,
            usage=result.usage,
            error=result.error,
        )
    except Exception as e:
        logger.error(f"LLM chat failed: {e}")
        return ChatResponse(success=False, error=str(e))
