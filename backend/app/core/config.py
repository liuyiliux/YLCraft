"""
YLCraft — 系统配置中心
所有设置持久化到 backend/data/settings.json
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).parent.parent  # backend/app/
_DATA_DIR = _BACKEND_DIR / "data"
_SETTINGS_FILE = _DATA_DIR / "settings.json"

# ---------------------------------------------------------------------------
# 默认配置（首次运行使用）
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS: dict[str, Any] = {
    # 下载
    "download_path": str(Path.home() / "YLCraft-Downloads"),
    # 素材库存储
    "media_storage_path": str(Path.home() / "YLCraft-Media"),
    # FFmpeg 路径（null=自动检测）
    "ffmpeg_path": None,
    # 存储类型：local / s3 / oss
    "storage_type": "local",
    # S3 配置（预留）
    "s3": {
        "bucket": "",
        "region": "us-east-1",
        "access_key": "",
        "secret_key": "",
    },
    # OSS 配置（预留）
    "oss": {
        "bucket": "",
        "region": "cn-hangzhou",
        "access_key": "",
        "secret_key": "",
        "endpoint": "",
    },
}

# ---------------------------------------------------------------------------
# 内部读写
# ---------------------------------------------------------------------------

def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_raw() -> dict[str, Any]:
    _ensure_data_dir()
    if not _SETTINGS_FILE.exists():
        _save_raw(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()
    try:
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # 文件损坏时 backup + 使用默认
        backup = _SETTINGS_FILE.with_suffix(".bak")
        if _SETTINGS_FILE.exists():
            shutil.copy(_SETTINGS_FILE, backup)
        _save_raw(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()


def _save_raw(data: dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 公开 API（全局单例，每次修改重新读写文件）
# ---------------------------------------------------------------------------

_settings_cache: dict[str, Any] | None = None


def get_settings() -> dict[str, Any]:
    """返回完整配置字典"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = _load_raw()
    return _settings_cache


def get(key: str, default: Any = None) -> Any:
    """读取单个配置项，支持点号路径如 's3.bucket'"""
    keys = key.split(".")
    val = get_settings()
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
        if val is None:
            return default
    return val


def put(key: str, value: Any) -> dict[str, Any]:
    """写入单个配置项，支持点号路径，创建中间字典"""
    global _settings_cache
    keys = key.split(".")
    data = _load_raw()
    d = data
    for k in keys[:-1]:
        if k not in d:
            d[k] = {}
        d = d[k]
    d[keys[-1]] = value
    _save_raw(data)
    _settings_cache = data
    return data


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    """批量更新配置"""
    global _settings_cache
    data = _load_raw()
    data.update(patch)
    _save_raw(data)
    _settings_cache = data
    return data


def ensure_download_path() -> Path:
    """确保下载目录存在，返回 Path 对象"""
    p = Path(get("download_path", DEFAULT_SETTINGS["download_path"]))
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_ffmpeg_path() -> str | None:
    """
    获取 FFmpeg 可执行文件路径。
    优先级：用户配置 > 系统 PATH 检测 > None
    """
    # 1. 用户配置优先
    configured = get("ffmpeg_path")
    if configured:
        p = Path(configured)
        if p.exists() and p.is_file():
            return str(p.resolve())
        # 也接受只配置目录的情况
        exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        p_exe = p / exe_name
        if p_exe.exists():
            return str(p_exe.resolve())

    # 2. 从系统 PATH 查找
    ffmpeg_cmd = shutil.which("ffmpeg")
    if ffmpeg_cmd:
        return ffmpeg_cmd

    return None
