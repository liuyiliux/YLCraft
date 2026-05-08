"""
YLCraft — 系统设置 API

GET  /api/v1/settings          — 获取所有设置
PUT  /api/v1/settings          — 批量更新设置
GET  /api/v1/settings/download-path — 获取下载路径
GET  /api/v1/settings/ffmpeg-path  — 获取 FFmpeg 路径
"""

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings, update_settings, get, ensure_download_path, get_ffmpeg_path

router = APIRouter()


class SettingsResponse(BaseModel):
    success: bool = True
    data: dict


class SettingsUpdateRequest(BaseModel):
    patch: dict


class DownloadPathResponse(BaseModel):
    success: bool = True
    path: str


class FFmpegPathResponse(BaseModel):
    success: bool = True
    configured: str | None
    detected: str | None
    effective: str | None


@router.get("", response_model=SettingsResponse, summary="获取系统设置")
async def get_all_settings():
    """返回所有系统设置"""
    data = get_settings()
    return SettingsResponse(success=True, data=data)


@router.put("", response_model=SettingsResponse, summary="批量更新系统设置")
async def update_all_settings(req: SettingsUpdateRequest):
    """批量更新设置"""
    patch = req.patch
    if "download_path" in patch:
        path = patch["download_path"].strip()
        if not path:
            raise HTTPException(status_code=400, detail="download_path 不能为空")
        os.makedirs(path, exist_ok=True)
    data = update_settings(patch)
    return SettingsResponse(success=True, data=data)


@router.get("/download-path", response_model=DownloadPathResponse, summary="获取下载保存路径")
async def get_download_path():
    """返回当前下载保存路径（自动确保目录存在）"""
    p = ensure_download_path()
    return DownloadPathResponse(path=str(p))


@router.get("/ffmpeg-path", response_model=FFmpegPathResponse, summary="获取 FFmpeg 路径")
async def get_ffmpeg():
    """
    返回 FFmpeg 路径信息。
    effective = configured（用户配置） > detected（系统 PATH 检测） > None
    """
    configured = get("ffmpeg_path")
    detected = get_ffmpeg_path()
    return FFmpegPathResponse(
        configured=configured,
        detected=str(detected) if detected else None,
        effective=configured or (str(detected) if detected else None),
    )
