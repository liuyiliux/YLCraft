"""平台资产本地文件的解析与访问校验（服务层）。

生图、图转 3D 等链路拿到的是 `/api/v1/assets/download?path=...` 这类平台内部地址。
过去统一走 HTTP 回环（localhost:8000）下载字节，后端繁忙或 localhost 解析到 IPv6
时会 30 秒超时，参考图随后被静默丢弃，最终发出没有参考图的图生图请求。
文件本来就在本机，直接读取即可，不再绕一圈 HTTP。

安全规则与 `app/api/v1/assets.py::_asset_file_allowed_roots` 保持一致，
修改任一处时请同步另一处。
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

logger = logging.getLogger("ylcraft.asset_file_resolver")

# 平台内部的文件下载端点，只有这些端点的 path 参数才允许还原为本地路径
_DOWNLOAD_QUERY_ENDPOINTS = ("/api/v1/assets/download", "/api/v1/assets/file")

# Windows 盘符路径，如 F:\dir 或 F:/dir
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def project_root() -> Path:
    """当前部署的项目根目录（backend 的上一级）。

    相对存储路径以它为基准解析。多机器共享同一个数据库时，各机器把
    `backend/app/storage/images/x.png` 这样的相对路径还原到自己的项目目录，
    而不是生成文件那台机器的绝对路径。
    """
    return Path(__file__).resolve().parents[3]


def is_absolute_storage_path(path_value: str) -> bool:
    """判断存储路径是否为绝对路径（Windows 盘符、UNC 或 POSIX 根）。"""
    return bool(_WINDOWS_ABS_RE.match(path_value)) or path_value.startswith(("/", "\\\\"))


def resolve_storage_path(path_value: str) -> Path:
    """把存储路径解析为绝对路径。

    绝对路径沿用原值；相对路径按当前项目根解析。解析后调用方仍必须做
    白名单校验，`..` 逃逸由 `Path.resolve()` 规范化后交给白名单拦截。
    """
    expanded = os.path.expandvars(os.path.expanduser(path_value))
    if is_absolute_storage_path(expanded):
        return Path(expanded).resolve()
    return (project_root() / expanded).resolve()


def to_storage_path(path: Path | str) -> str:
    """把本机绝对路径转成可跨机器解析的相对存储路径。

    落在项目目录内的文件转成 `backend/app/storage/images/x.png` 这样的相对
    路径，由 `resolve_storage_path` 在各机器上还原到各自的本地文件；项目外的
    文件（下载目录、临时目录）保持绝对路径，避免跨机器指向不存在的路径。

    适用于服务端内部消费的字段，如 `asset_representations.file_path`。
    """
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(project_root()).as_posix()
    except ValueError:
        return str(resolved)


def to_asset_download_url(path: Path | str) -> str:
    """把本机绝对路径转成平台内部下载地址，供前端直接当图片地址使用。

    必须保留 `/api/v1/assets/download?path=...` 形态：素材库、播放器、3D 工作台、
    故事工作台等页面会把 `thumbnail_url` / `portrait_url` 直接当作 URL 渲染，
    不做二次包装。只有 path 参数从绝对路径换成相对路径以获得跨机器可解析性。
    """
    return f"/api/v1/assets/download?path={quote(to_storage_path(path), safe='')}"


def allowed_asset_roots() -> list[Path]:
    """允许读取的资产根目录。"""
    from app.core.config import ensure_download_path

    backend_dir = Path(__file__).resolve().parents[2]
    project_dir = backend_dir.parent
    roots = [
        backend_dir / "app" / "storage",
        backend_dir / "storage",
        backend_dir / "downloads",
        backend_dir / "uploads",
        project_dir / "storage",
        project_dir / "downloads",
        project_dir / "uploads",
        ensure_download_path(),
    ]
    return [root.resolve() for root in roots if root]


def is_allowed_temp_path(path: Path) -> bool:
    """临时目录下的上传/剪辑产物允许读取。"""
    temp_root = Path(tempfile.gettempdir()).resolve()
    allowed_prefixes = ("ylcraft_uploads", "narrato_out_", "moe_out_", "cutclaw_out_")
    for parent in (path, *path.parents):
        if parent.parent == temp_root and parent.name.startswith(allowed_prefixes):
            return True
    return False


def resolve_asset_file(path_value: str) -> Path | None:
    """把本地路径解析为允许访问的文件。

    Args:
        path_value: 本地文件绝对路径，或相对项目根的存储路径

    Returns:
        Path | None: 允许访问且存在的文件；越界、不存在或非法输入返回 None
    """
    if not path_value or path_value.startswith(("http://", "https://", "data:")):
        return None
    try:
        path = resolve_storage_path(path_value)
    except (OSError, ValueError) as e:
        logger.warning("[asset_file_resolver] 无法解析路径 %s: %s", path_value[:120], e)
        return None
    if not path.is_file():
        return None
    allowed = any(path == root or root in path.parents for root in allowed_asset_roots())
    if not allowed and is_allowed_temp_path(path):
        allowed = True
    if not allowed:
        logger.warning("[asset_file_resolver] 文件不在允许目录内: %s", path)
        return None
    return path


def resolve_asset_file_from_url(url: str) -> Path | None:
    """从平台内部地址还原本地文件。

    支持 `/api/v1/assets/download?path=...`、`/api/v1/assets/file?path=...`
    以及直接的本地绝对路径。公网地址、data URL 返回 None，由调用方走网络下载。

    Args:
        url: 图片地址

    Returns:
        Path | None: 可直读的本地文件；非平台地址或越界返回 None
    """
    if not url or url.startswith(("http://", "https://", "data:")):
        return None

    candidate = url
    if url.startswith(("api/", "/api/")):
        parsed = urlparse(url)
        if parsed.path.rstrip("/") not in _DOWNLOAD_QUERY_ENDPOINTS:
            return None
        raw_path = (parse_qs(parsed.query).get("path") or [""])[0]
        if not raw_path:
            return None
        candidate = raw_path

    return resolve_asset_file(candidate)
