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

from app.services.breaker.service import (
    create_task,
    get_task,
    run_analysis,
    result_to_dict,
    AnalysisStatus,
)

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
