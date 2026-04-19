"""
YLCraft — NarratoAI Pipeline / MoE 多专家剪辑 API

POST /api/v1/clip — NarratoAI Pipeline 剪辑
POST /api/v1/clip/moe — MoE 多专家协作剪辑
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("ylcraft.clip")


class NarratoRequest(BaseModel):
    video_path: str
    mode: str = "auto"  # auto / beat / vlm


class NarratoResponse(BaseModel):
    success: bool
    message: str
    result_path: str | None = None


class MoERequest(BaseModel):
    video_path: str
    experts: list[str] | None = None


class MoEResponse(BaseModel):
    success: bool
    message: str
    result_path: str | None = None


@router.post("", response_model=NarratoResponse, summary="NarratoAI Pipeline 剪辑")
async def narrato剪辑(request: NarratoRequest):
    """NarratoAI Pipeline：自动节拍踩点 + VLM 美学评分剪辑"""
    logger.warning("NarratoAI Pipeline API called but not yet implemented")
    return NarratoResponse(
        success=False,
        message="NarratoAI Pipeline 正在开发中",
        result_path=None,
    )


@router.post("/moe", response_model=MoEResponse, summary="MoE 多专家协作剪辑")
async def moe剪辑(request: MoERequest):
    """MoE 多专家协作架构的剪辑端点"""
    logger.warning("MoE clip API called but not yet implemented")
    return MoEResponse(
        success=False,
        message="MoE 多专家剪辑正在开发中",
        result_path=None,
    )
