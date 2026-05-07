"""
YLCraft — CutClaw Agent API

POST /api/v1/clip/cutclaw     — 启动 CutClaw Agent 任务
GET  /api/v1/clip/cutclaw/{id} — 查询任务状态
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.clip.cutclaw_service import (
    CutClawConfig,
    CutClawService,
    get_cutclaw_service,
)

router = APIRouter()
logger = logging.getLogger("ylcraft.cutclaw")


# =============================================================================
# 请求/响应模型
# =============================================================================

class CutClawRequest(BaseModel):
    """CutClaw Agent 请求"""
    video_path: str = Field(..., description="输入视频路径")
    instruction: str = Field(
        None,
        description="自然语言剪辑指令，如：'把最精彩的30秒剪出来'",
    )
    auto_cut: bool = Field(True, description="是否自动执行最终剪辑（默认 True）")


class CutClawResponse(BaseModel):
    success: bool
    task_id: str
    message: str


class CutClawStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    progress_message: str
    result: dict | None = None
    error: str | None = None


# =============================================================================
# API 路由
# =============================================================================

@router.post("", response_model=CutClawResponse, summary="CutClaw Agent 视频剪辑")
async def cutclaw_clip(request: CutClawRequest):
    """
    CutClaw Agent：根据自然语言指令自动剪辑视频。

    LLM Agent 工作流程：
    1. 调用 get_video_info 了解视频信息
    2. 调用 detect_scenes 检测镜头切换
    3. 调用 extract_keyframes + analyze_content 理解内容
    4. 调用 select_clips 选定片段
    5. 调用 commit 执行 FFmpeg 合成

    示例指令：
    - "把第 30 秒到 1 分钟的内容剪出来"
    - "保留所有有人出现的片段"
    - "剪出最精彩的 45 秒，适合抖音分享"
    """
    try:
        service = get_cutclaw_service()
        instruction = request.instruction or "请帮我剪辑出最精彩的片段，适合短视频分享"

        task_id = await service.start_agent_task(
            video_path=request.video_path,
            instruction=instruction,
            auto_cut=request.auto_cut,
        )

        return CutClawResponse(
            success=True,
            task_id=task_id,
            message=f"CutClaw Agent 任务已启动（task_id: {task_id}）",
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"CutClaw start failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=CutClawStatusResponse, summary="查询 CutClaw Agent 任务状态")
async def get_cutclaw_task_status(task_id: str):
    """查询 CutClaw Agent 任务状态"""
    service = get_cutclaw_service()
    status = await service.get_task_status(task_id)

    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    return CutClawStatusResponse(**status)
