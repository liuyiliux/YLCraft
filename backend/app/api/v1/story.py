"""
YLCraft — Story Maker API

POST /api/v1/story — AI 短剧漫剧生成
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("ylcraft.story")


class StoryRequest(BaseModel):
    prompt: str
    style: str = "short_drama"  # short_drama | manga
    num_scenes: int = 8


class StoryResponse(BaseModel):
    success: bool
    message: str
    script: list[dict] | None = None
    assets: list[str] | None = None


@router.post("", response_model=StoryResponse, summary="AI 短剧漫剧生成")
async def generate_story(request: StoryRequest):
    """
    Story Maker：输入提示词，生成短剧漫剧分镜脚本和角色立绘。
    目前为占位实现。
    """
    logger.warning("Story Maker API called but not yet implemented")
    return StoryResponse(
        success=False,
        message="Story Maker 正在开发中",
        script=None,
        assets=None,
    )
