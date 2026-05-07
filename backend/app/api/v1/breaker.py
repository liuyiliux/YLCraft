"""
YLCraft — Breaker API（增强版）

POST /api/v1/breaker/analyze      — 创建拆解任务
GET  /api/v1/breaker/tasks/{id}   — 查询任务状态
GET  /api/v1/breaker/tasks/{id}/result — 获取结果
"""

from __future__ import annotations

import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.services.breaker import (
    create_task,
    get_task,
    run_analysis,
    result_to_dict,
    AnalysisStatus,
    analyze_xhs_content,
)
from app.services.xhs_parser import get_xhs_parser, XhsNote
from app.core.contracts.types import MediaType
from app.services.llm.manager import get_manager
from typing import Optional
import re

router = APIRouter()


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="视频链接（抖音/快手/B站等）")


class TaskStatusResponse(BaseModel):
    task_id: str
    url: str
    status: str
    progress: int
    result: dict | None = None
    error: str | None = None


@router.post("/analyze", summary="创建拆解任务", response_model=TaskStatusResponse)
async def analyze(req: AnalyzeRequest, background: BackgroundTasks):
    """
    创建爆款拆解任务。

    流程：
    1. 解析视频链接
    2. 下载视频 → 提取音频 → 语音转录
    3. LLM 分析文案结构
    4. 返回结构化报告（含角色库、分镜表、仿写提示词）

    分析完成后可通过 GET /api/v1/breaker/tasks/{task_id} 查询结果。
    """
    task = await create_task(req.url)

    # 后台运行分析
    background.add_task(run_analysis, task)

    return TaskStatusResponse(
        task_id=task.task_id,
        url=task.url,
        status=task.status.value,
        progress=task.progress,
    )


@router.get("/tasks/{task_id}", summary="查询任务状态")
async def get_task_status(task_id: str):
    """查询拆解任务状态和进度"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    result_dict = None
    if task.result:
        result_dict = result_to_dict(task.result)

    return TaskStatusResponse(
        task_id=task.task_id,
        url=task.url,
        status=task.status.value,
        progress=task.progress,
        result=result_dict,
        error=task.error,
    )


@router.get("/tasks/{task_id}/result", summary="获取拆解结果")
async def get_result(task_id: str):
    """获取拆解结果（仅任务完成时返回）"""
    task = await get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status == AnalysisStatus.FAILED:
        raise HTTPException(status_code=400, detail=task.error or "Task failed")

    if task.status != AnalysisStatus.DONE:
        raise HTTPException(
            status_code=202,
            detail=f"Task not done yet. Status: {task.status.value}, Progress: {task.progress}%",
        )

    return result_to_dict(task.result)


# =============================================================================
# 小红书图文解析端点
# =============================================================================

XHS_PATTERN = re.compile(
    r"xiaohongshu\.com/(explore|discovery/item)|xhs\.cn/t"
)


class XhsPreviewRequest(BaseModel):
    url: str = Field(..., description="小红书笔记链接")
    skip_llm: bool = Field(False, description="仅解析图文，不进行 LLM 分析")


class XhsPreviewResponse(BaseModel):
    success: bool
    url: str
    platform: str = "xiaohongshu"
    parsed: Optional[dict] = None  # XhsNote dict
    analysis: Optional[dict] = None  # LLM 分析结果
    message: str = ""


@router.post("/preview", summary="预览小红书图文笔记", response_model=XhsPreviewResponse)
async def preview_xhs_note(req: XhsPreviewRequest):
    """
    预览小红书图文笔记（先解析，后分析）。

    支持链接类型：
    - 小红书图文笔记（小红花图标）→ 解析标题/正文/图片
    - 视频笔记 → 走 /analyze 异步任务

    返回 parsed（解析结果）后，前端可展示预览，用户确认后再触发完整分析。
    """
    if not XHS_PATTERN.search(req.url):
        raise HTTPException(
            status_code=400,
            detail="链接不是小红书笔记格式，请使用 /analyze 端点处理视频链接"
        )

    try:
        parser = get_xhs_parser()
        note = parser.parse(req.url)

        if not note:
            return XhsPreviewResponse(
                success=False,
                url=req.url,
                message="解析失败，请检查链接是否正确或内容是否可见"
            )

        # 构建 parsed 结果
        parsed_dict = {
            "title": note.title,
            "description": note.description,
            "images": note.images,
            "covers": note.covers,
            "author": note.author,
            "author_id": note.author_id,
            "likes": note.likes,
            "note_id": note.note_id,
            "source_url": note.source_url,
            "cover_url": note.cover_url,
        }

        # LLM 分析（可选）
        analysis_result = None
        if not req.skip_llm:
            manager = get_manager()
            llm_available = manager.is_loaded() and bool(manager.get_default(MediaType.LLM))

            if llm_available:
                analysis_result = await analyze_xhs_content(
                    title=note.title,
                    description=note.description,
                    images_count=len(note.images),
                    author=note.author,
                )
            else:
                return XhsPreviewResponse(
                    success=True,
                    url=req.url,
                    platform="xiaohongshu",
                    parsed=parsed_dict,
                    analysis=None,
                    message="LLM 未配置，已返回解析结果（跳过 LLM 分析）"
                )

        return XhsPreviewResponse(
            success=True,
            url=req.url,
            platform="xiaohongshu",
            parsed=parsed_dict,
            analysis=analysis_result,
            message="解析成功" if analysis_result else "解析成功，LLM 分析未运行"
        )

    except Exception as e:
        return XhsPreviewResponse(
            success=False,
            url=req.url,
            message=f"解析异常: {str(e)}"
        )
