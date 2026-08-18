"""
YLCraft — 系统设置 API

GET  /api/v1/settings          — 获取所有设置
PUT  /api/v1/settings          — 批量更新设置
GET  /api/v1/settings/download-path — 获取下载路径
GET  /api/v1/settings/ffmpeg-path  — 获取 FFmpeg 路径
GET  /api/v1/settings/storage-paths — 获取所有存储路径
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import ensure_download_path, get_ffmpeg_path

router = APIRouter()

# 缓存数据库设置（避免每次都查库）
_db_settings_cache: dict[str, str] = {}
_db_settings_loaded = False


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


class StoragePathsResponse(BaseModel):
    success: bool = True
    data: dict  # { key: path }


def _get_settings_path() -> Path:
    """获取 settings.json 的路径（backend/app/data/settings.json）"""
    backend_dir = Path(__file__).parent.parent.parent.parent
    return backend_dir / "app" / "data" / "settings.json"


def _load_settings_from_file() -> dict:
    """从文件加载基础设置"""
    settings_path = _get_settings_path()
    if not settings_path.exists():
        return _get_default_settings()
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_default_settings() -> dict:
    """获取默认设置"""
    return {
        "ffmpeg_path": None,
        "storage_type": "local",
        "cos": {
            "bucket": "",
            "region": "ap-beijing",
            "secret_id": "",
            "secret_key": ""
        }
    }


def _save_settings_to_file(settings: dict):
    """保存设置到文件"""
    settings_path = _get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


async def _load_settings_from_db() -> dict[str, str]:
    """从数据库加载设置"""
    global _db_settings_cache, _db_settings_loaded
    
    if _db_settings_loaded:
        return _db_settings_cache
    
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.db.models.system_setting import SystemSetting
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSetting))
            settings = result.scalars().all()
            _db_settings_cache = {s.key: s.value for s in settings}
            _db_settings_loaded = True
    except Exception as e:
        # 数据库不存在或表不存在，使用空设置
        _db_settings_cache = {}
        _db_settings_loaded = True
    
    return _db_settings_cache


async def _save_setting_to_db(key: str, value: str, description: str = ""):
    """保存设置到数据库"""
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.db.models.system_setting import SystemSetting
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SystemSetting).where(SystemSetting.key == key)
            )
            setting = result.scalar_one_or_none()
            
            if setting:
                setting.value = value
                if description:
                    setting.description = description
            else:
                setting = SystemSetting(key=key, value=value, description=description)
                session.add(setting)
            
            await session.commit()
            
            # 更新缓存
            global _db_settings_cache
            _db_settings_cache[key] = value
    except Exception as e:
        # 数据库不可用，静默失败
        pass


def _load_settings() -> dict:
    """同步版本的设置加载（仅从文件，不查库）"""
    return _load_settings_from_file()


def _get_settings() -> dict:
    """获取所有设置"""
    return {
        "data": _load_settings_from_file()
    }


async def get_setting(key: str) -> str | None:
    """获取单个设置（数据库优先）"""
    db_settings = await _load_settings_from_db()
    
    # 数据库优先
    if key in db_settings and db_settings[key]:
        return db_settings[key]
    
    # 回退到配置文件
    file_settings = _load_settings_from_file()
    return file_settings.get(key)


async def get_cos_config() -> dict:
    """读取 COS 配置（数据库 cos_* 键优先，回退到 settings.json 的 cos 段）。"""
    db_settings = await _load_settings_from_db()
    bucket = db_settings.get("cos_bucket") or ""
    region = db_settings.get("cos_region") or ""
    secret_id = db_settings.get("cos_secret_id") or ""
    secret_key = db_settings.get("cos_secret_key") or ""

    if not (bucket and secret_id and secret_key):
        file_cos = _load_settings_from_file().get("cos") or {}
        bucket = bucket or file_cos.get("bucket") or ""
        region = region or file_cos.get("region") or "ap-beijing"
        secret_id = secret_id or file_cos.get("secret_id") or ""
        secret_key = secret_key or file_cos.get("secret_key") or ""

    return {
        "bucket": bucket,
        "region": region or "ap-beijing",
        "secret_id": secret_id,
        "secret_key": secret_key,
    }


async def get_storage_path(key: str, default_subdir: str = "") -> Path:
    """
    获取存储路径（数据库优先，回退到默认）
    
    Args:
        key: 存储路径配置键 (video_download_path, image_gen_path, etc.)
        default_subdir: 默认子目录
    
    Returns:
        Path: 有效的存储路径
    """
    # 尝试从数据库/配置获取
    configured_path = await get_setting(key)
    
    if configured_path and Path(configured_path).exists():
        return Path(configured_path)
    
    # 最终回退到 storage/ 目录
    backend_dir = Path(__file__).parent.parent.parent.parent
    storage_dir = backend_dir / "storage"
    if default_subdir:
        storage_dir = storage_dir / default_subdir
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


# ============================================================================
# API 路由
# ============================================================================

@router.get("", response_model=SettingsResponse, summary="获取系统设置")
async def get_all_settings():
    """返回所有系统设置"""
    # 加载数据库设置
    db_settings = await _load_settings_from_db()
    file_settings = _load_settings_from_file()
    
    # 合并设置（数据库优先）
    merged = file_settings.copy()
    for key, value in db_settings.items():
        if value:  # 只覆盖非空值
            merged[key] = value

    # 重建嵌套 cos 对象（数据库存的是平铺 cos_* 键）
    cos_db = {
        "bucket": db_settings.get("cos_bucket") or "",
        "region": db_settings.get("cos_region") or "",
        "secret_id": db_settings.get("cos_secret_id") or "",
        "secret_key": db_settings.get("cos_secret_key") or "",
    }
    if any(cos_db.values()):
        merged["cos"] = {**merged.get("cos", {}), **cos_db}

    return SettingsResponse(success=True, data={"data": merged})


@router.put("", response_model=SettingsResponse, summary="批量更新设置")
async def update_all_settings(req: SettingsUpdateRequest):
    """批量更新设置"""
    patch = req.patch
    
    # 处理存储路径
    storage_keys = [
        "video_download_path", "image_gen_path", "video_gen_path",
        "reference_image_path", "upload_path"
    ]
    
    for key in storage_keys:
        if key in patch:
            path = patch[key]
            if isinstance(path, str):
                path = path.strip()
                if path:
                    os.makedirs(path, exist_ok=True)
            # 保存到数据库
            await _save_setting_to_db(key, path or "", f"存储路径: {key}")

    # COS 远程对象存储：入库（平铺 cos_* 键）
    if "cos" in patch and isinstance(patch["cos"], dict):
        cos = patch["cos"]
        for field, db_key in [
            ("bucket", "cos_bucket"),
            ("region", "cos_region"),
            ("secret_id", "cos_secret_id"),
            ("secret_key", "cos_secret_key"),
        ]:
            if field in cos:
                await _save_setting_to_db(db_key, str(cos.get(field) or ""), f"COS {field}")

    return SettingsResponse(success=True, data={"data": patch})


@router.get("/storage-paths", response_model=StoragePathsResponse, summary="获取所有存储路径")
async def get_all_storage_paths():
    """返回所有存储路径配置"""
    db_settings = await _load_settings_from_db()
    file_settings = _load_settings_from_file()
    
    storage_keys = [
        "video_download_path",
        "image_gen_path", 
        "video_gen_path",
        "reference_image_path",
        "upload_path",
    ]
    
    result = {}
    for key in storage_keys:
        # 数据库优先
        if key in db_settings and db_settings[key]:
            result[key] = db_settings[key]
        else:
            # 默认路径
            backend_dir = Path(__file__).parent.parent.parent.parent
            result[key] = str(backend_dir / "storage")
    
    return StoragePathsResponse(success=True, data=result)


@router.get("/download-path", response_model=DownloadPathResponse, summary="获取下载保存路径")
async def get_download_path():
    """返回当前下载保存路径"""
    path = await get_setting("video_download_path")
    
    if path and Path(path).exists():
        return DownloadPathResponse(path=path)
    
    p = ensure_download_path()
    return DownloadPathResponse(path=str(p))


@router.get("/ffmpeg-path", response_model=FFmpegPathResponse, summary="获取 FFmpeg 路径")
async def get_ffmpeg():
    """
    返回 FFmpeg 路径信息。
    effective = configured（用户配置） > detected（系统 PATH 检测） > None
    """
    configured = await get_setting("ffmpeg_path")
    if not configured:
        configured = _load_settings_from_file().get("ffmpeg_path")
    
    detected = get_ffmpeg_path()
    return FFmpegPathResponse(
        configured=configured,
        detected=str(detected) if detected else None,
        effective=configured or (str(detected) if detected else None),
    )
