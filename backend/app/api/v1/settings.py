"""
YLCraft — 系统设置 API

GET  /api/v1/settings          — 获取所有设置
PUT  /api/v1/settings          — 批量更新设置
GET  /api/v1/settings/download-path — 获取下载路径
GET  /api/v1/settings/ffmpeg-path  — 获取 FFmpeg 路径
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import ensure_download_path, get_ffmpeg_path

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


def _get_settings_path() -> Path:
    """获取 settings.json 的路径"""
    backend_dir = Path(__file__).parent.parent.parent
    return backend_dir / "app" / "data" / "settings.json"


def _load_settings() -> dict:
    """从文件加载设置"""
    settings_path = _get_settings_path()
    if not settings_path.exists():
        return {
            "download_path": str(ensure_download_path()),
            "media_storage_path": str(ensure_download_path().parent / "media"),
            "ffmpeg_path": None,
            "storage_type": "local",
            "s3": {
                "bucket": "",
                "region": "us-east-1",
                "access_key": "",
                "secret_key": ""
            },
            "oss": {
                "bucket": "",
                "region": "cn-hangzhou",
                "access_key": "",
                "secret_key": "",
                "endpoint": ""
            }
        }
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_settings(settings: dict):
    """保存设置到文件"""
    settings_path = _get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def _get(key: str, default=None):
    """获取单个设置"""
    settings = _load_settings()
    return settings.get(key, default)


def _update_settings(patch: dict) -> dict:
    """批量更新设置"""
    settings = _load_settings()
    for key, value in patch.items():
        if key in ["s3", "oss"]:
            if isinstance(settings.get(key), dict):
                settings[key].update(value)
            else:
                settings[key] = value
        else:
            settings[key] = value
    _save_settings(settings)
    return settings


def _get_settings() -> dict:
    """获取所有设置"""
    return {
        "data": _load_settings()
    }


@router.get("", response_model=SettingsResponse, summary="获取系统设置")
async def get_all_settings():
    """返回所有系统设置"""
    data = _get_settings()
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
    data = _update_settings(patch)
    return SettingsResponse(success=True, data={"data": data})


@router.get("/download-path", response_model=DownloadPathResponse, summary="获取下载保存路径")
async def get_download_path():
    """返回当前下载保存路径（自动确保目录存在）"""
    custom_path = _get("download_path")
    if custom_path and Path(custom_path).exists():
        return DownloadPathResponse(path=custom_path)
    p = ensure_download_path()
    return DownloadPathResponse(path=str(p))


@router.get("/ffmpeg-path", response_model=FFmpegPathResponse, summary="获取 FFmpeg 路径")
async def get_ffmpeg():
    """
    返回 FFmpeg 路径信息。
    effective = configured（用户配置） > detected（系统 PATH 检测） > None
    """
    configured = _get("ffmpeg_path")
    detected = get_ffmpeg_path()
    return FFmpegPathResponse(
        configured=configured,
        detected=str(detected) if detected else None,
        effective=configured or (str(detected) if detected else None),
    )
