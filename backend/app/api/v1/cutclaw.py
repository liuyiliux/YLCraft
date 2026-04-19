"""
YLCraft — CutClaw Agent API

POST /api/v1/clip/cutclaw — CutClaw Agent 视频剪辑
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("ylcraft.cutclaw")


class CutClawRequest(BaseModel):
    video_path: str
    instruction: str | None = None
    auto_cut: bool = True


class CutClawResponse(BaseModel):
    success: bool
    message: str
    result_path: str | None = None


@router.post("", response_model=CutClawResponse, summary="CutClaw 视频剪辑")
async def cutclaw剪辑(request: CutClawRequest):
    """
    CutClaw Agent：根据自然语言指令自动剪辑视频。
    目前为占位实现。
    """
    logger.warning("CutClaw API called but not yet implemented")
    return CutClawResponse(
        success=False,
        message="CutClaw Agent 正在开发中",
        result_path=None,
    )
