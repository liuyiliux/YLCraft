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
