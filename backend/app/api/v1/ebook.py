"""
YLCraft — EPUB 电子书生成 API

POST /api/v1/ebook/generate        — 从文件夹生成 EPUB
GET  /api/v1/ebook/tasks/{task_id} — 查询生成任务
GET  /api/v1/ebook/tasks           — 列出所有任务
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.ebook import get_ebook_service

router = APIRouter()
logger = logging.getLogger("ylcraft.ebook")


class EbookGenerateRequest(BaseModel):
    title: str = Field(..., description="书名")
    folder_path: str = Field(..., description="包含 Markdown/HTML 文件的文件夹路径")
    author: str = Field("YLCraft", description="作者")
    cover_path: str = Field("", description="封面图路径（可选）")
    output_dir: str = Field("", description="输出目录（默认与 folder_path 同级）")


class EbookGenerateResponse(BaseModel):
    task_id: str
    status: str
    title: str
    chapter_count: int
    file_path: str = ""
    file_size: int = 0
    error: str = ""


class EbookTaskResponse(BaseModel):
    task_id: str = ""
    status: str = ""
    title: str = ""
    chapter_count: int = 0
    file_path: str = ""
    file_size: int = 0
    error: str = ""


@router.post("/generate", response_model=EbookGenerateResponse, summary="生成 EPUB 电子书")
async def generate_ebook(req: EbookGenerateRequest):
    """从 Markdown/HTML 文件夹生成 EPUB 电子书"""
    if not req.folder_path or not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail="文件夹路径不存在")

    service = get_ebook_service()
    result = await service.create_task(
        title=req.title,
        folder_path=req.folder_path,
        author=req.author,
        cover_path=req.cover_path,
        output_dir=req.output_dir,
    )

    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "生成失败"))

    return EbookGenerateResponse(**result)


@router.get("/tasks/{task_id}", response_model=EbookTaskResponse, summary="查询生成任务")
async def get_ebook_task(task_id: str):
    """查询 EPUB 生成任务状态"""
    service = get_ebook_service()
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return EbookTaskResponse(**task)


@router.get("/tasks", summary="列出所有生成任务")
async def list_ebook_tasks():
    """列出所有 EPUB 生成任务"""
    service = get_ebook_service()
    return {"tasks": service.list_tasks()}


@router.get("/download/{task_id}", summary="下载生成的 EPUB 文件")
async def download_ebook(task_id: str):
    """下载已生成的 EPUB 文件"""
    service = get_ebook_service()
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.get("status") != "done":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    file_path = task.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    title = task.get("title", "ebook")
    return FileResponse(
        path=file_path,
        filename=f"{title}.epub",
        media_type="application/epub+zip",
    )
