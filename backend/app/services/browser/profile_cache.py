"""
YLCraft — 采集浏览器 profile 的磁盘占用与清缓存

## 为什么需要这个模块（2026-10-03 实测）

`backend/data/browser_profiles/<平台>/` 是**持久化 profile**，
每次跑采集都复用同一份磁盘目录，只增不减。实测 9 个平台合计 **1.2 GB**，
而其中**约 98% 是可丢弃的加速副本**，不是登录态：

    xhs        Cache 377.5MB  Code Cache 26.9MB
    douyin     Cache 240.9MB  Code Cache 89.2MB
    kuaishou   Cache 131.0MB
    …

不清理的话它会一直涨，而且**没有任何东西会回收它**（临时 profile 退出即删，
持久 profile 不会）。

## 缓存里到底存了什么（实测 xhs 377.5MB / 4521 个文件）

按 Chromium Simple Cache 的文件头 magic 统计：

    RIFF(WEBP)          4097 个   241.7 MB   ← 封面图/图片
    JPEG(ffd8ffe0)       373 个     8.3 MB   ← 图片
    gzip(1f8b)            43 个     4.5 MB   ← JS bundle（解压后是 webpack chunk）
    SimpleCache-block      4 个   122.5 MB   ← 超大对象段（单个 data_3 就 108MB）
    PNG                     1 个     0.0 MB

所以**用户问的"是不是方便同一张图重复加载"——是的**：
`f_xxxxxx` 每个 URL 一个文件，再次请求同一 URL 时浏览器不发网络请求
直接读本地（同一张封面在列表里出现多次、翻页再看同一批图都靠它）。
但它是 **LRU 有界**的，涨到上限会淘汰最久未用的，所以 377MB 是
"历史上抓过很多大图"，不是"一张图存了 377MB"。

## ⚠️ 为什么只删这些、不多删一点

**`Service Worker` 目录不在清理列表里** —— `crawler/service.py` 明确记录：
微博采集**必须**有 Service Worker 上下文（由它代理请求并注入 httpx
复现不了的上下文，实测直连一律 `ok=-100`）。删掉它等于让微博采集直接失效。

同理 `Network`（Cookies/HSTS）、`Local Storage`、`IndexedDB`、`Sessions`
都是登录态本体，碰了就得重新扫码。

判定标准：**缓存是"加速用的副本"，这些是"身份本身"**。

## ⚠️ 删除前必须关掉占用者

profile 被浏览器打开时，Windows 会锁住 `Cookies`（实测
`PermissionError`）与 `Cache`（部分文件删不掉）。
所以：删不掉的**如实报告**为 skipped，不静默吞掉，也不假装成功。
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .persistent_profile import profiles_root

logger = logging.getLogger("ylcraft.browser.profile_cache")


# ============================================================================
# 目录分类
# ============================================================================

#: 可安全删除的纯缓存目录（相对 profile 根）。
#:
#: 全部是"加速副本"：删掉只影响下次访问速度，不影响登录态与功能。
#: **刻意不含** `Service Worker`（微博采集依赖）、`Network`（Cookies）、
#: `Local Storage` / `IndexedDB` / `Sessions`（登录态本体）。
CACHE_DIRS: tuple[str, ...] = (
    "Default/Cache",
    "Default/Code Cache",
    "Default/GPUCache",
    "Default/DawnGraphiteCache",
    "Default/DawnWebGPUCache",
    "GrShaderCache",
    "ShaderCache",
    "GraphiteDawnCache",
    "component_crx_cache",
    "CertificateRevocation",
    "Default/component_crx_cache",
)

#: 每个目录的人话说明（给前端 tooltip 用）。
CACHE_DIR_LABELS: Dict[str, str] = {
    "Cache": "HTTP 响应缓存（封面图 / JS / CSS）",
    "Code Cache": "V8 编译后的 JS 字节码",
    "GPUCache": "GPU 缓存",
    "DawnGraphiteCache": "图形缓存",
    "DawnWebGPUCache": "图形缓存",
    "GrShaderCache": "着色器缓存",
    "ShaderCache": "着色器缓存",
    "GraphiteDawnCache": "着色器缓存",
    "component_crx_cache": "扩展包缓存",
    "CertificateRevocation": "证书吊销缓存",
}

#: 会保留的东西 —— 出现在 UI 上是为了让用户知道"我们没动它"。
PRESERVED_NOTE = "登录态（Cookies / Local Storage / IndexedDB / Sessions）与 Service Worker 不会被动"


@dataclass
class PlatformCacheInfo:
    """单个平台的缓存占用。"""

    platform: str
    cache_bytes: int = 0
    total_bytes: int = 0
    cookie_bytes: int = 0
    exists: bool = True
    by_dir: Dict[str, int] = field(default_factory=dict)

    @property
    def preservable_ratio(self) -> float:
        """可清理占比。total 为 0 时返回 0（不返回 1，避免"100% 可清"的误导）。"""
        if self.total_bytes <= 0:
            return 0.0
        return self.cache_bytes / self.total_bytes


def _dir_size(path: Path) -> int:
    """目录占用（字节）。文件被占用/权限不足时跳过该文件，不抛异常。"""
    if not path.exists():
        return 0
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    continue
    except OSError as e:
        logger.debug("[profile-cache] 统计 %s 失败: %s", path, e)
    return total


def list_platform_caches() -> List[PlatformCacheInfo]:
    """列出所有平台的缓存占用。"""
    root = profiles_root()
    out: List[PlatformCacheInfo] = []
    try:
        entries = sorted(root.iterdir())
    except OSError as e:
        logger.warning("[profile-cache] 无法读取 profile 根目录: %s", e)
        return out

    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        info = PlatformCacheInfo(platform=entry.name)
        for rel in CACHE_DIRS:
            p = entry / rel
            if not p.exists():
                continue
            size = _dir_size(p)
            if size:
                info.by_dir[Path(rel).name] = size
                info.cache_bytes += size
        cookie = entry / "Default" / "Network" / "Cookies"
        if cookie.exists():
            try:
                info.cookie_bytes = cookie.stat().st_size
            except OSError:
                pass
        info.total_bytes = _dir_size(entry)
        out.append(info)
    return out


@dataclass
class ClearResult:
    """清理结果。**逐目录如实报告**，不静默吞掉失败。"""

    platform: str
    freed_bytes: int = 0
    removed: List[str] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)
    freed_bytes_after: int = 0

    @property
    def ok(self) -> bool:
        return not self.skipped


def clear_platform_cache(platform: str) -> ClearResult:
    """清理单个平台的缓存目录。**不碰登录态。**

    ## 安全约束
    · 只删 `CACHE_DIRS` 白名单里的路径，绝不递归删 profile 根
    · 平台名先过白名单字符校验（防 `../` 穿越）
    · 删不掉（浏览器占用/权限）→ 记入 `skipped` 并**返回给调用方**，
      不能假装成功 —— 否则用户以为清完了，实际没清
    """
    # ⚠️ **校验而非过滤**（2026-10-03 修）
    #
    # 原来写成"过滤掉非法字符再拼路径"：
    #     safe = "".join(ch for ch in platform if ch.isalnum() or ch in "-_")
    # 这会让 `../windows` 变成 `windows` —— **静默改写了用户输入**，
    # 结果是删掉了别的平台 / 返回"该平台没有 profile 目录"的 200，
    # 而请求里明明写的是 `../windows`。看起来"防住了"，实际是掩盖。
    #
    # 正确做法：含任何非白名单字符就**明确拒绝**。
    if not platform or platform in (".", ".."):
        raise ValueError("平台名非法")
    if not all(ch.isalnum() or ch in "-_" for ch in platform):
        raise ValueError(
            "平台名只能包含字母、数字、连字符和下划线"
            f"（收到：{platform[:40]!r}）"
        )
    safe = platform
    root = (profiles_root() / safe).resolve()
    # 纵深防御：即使前面漏了，也确保最终路径在 root 之内
    if not str(root).startswith(str(profiles_root().resolve()) + "\\"):
        raise ValueError("平台名非法")

    result = ClearResult(platform=safe)
    if not root.exists():
        result.skipped["profile"] = "该平台没有 profile 目录"
        return result

    for rel in CACHE_DIRS:
        p = root / rel
        if not p.exists():
            continue
        before = _dir_size(p)
        try:
            shutil.rmtree(p)
        except OSError as e:
            # Windows 上 profile 被浏览器打开时会锁住
            result.skipped[Path(rel).name] = (
                "浏览器正在使用该 profile，请先关闭采集/账号相关操作后重试"
                if isinstance(e, PermissionError)
                else f"{type(e).__name__}: {e}"
            )
            logger.info("[profile-cache] %s 跳过 %s: %s", safe, rel, e)
            continue
        freed = before
        if freed:
            result.removed.append(Path(rel).name)
        result.freed_bytes += freed
        logger.info("[profile-cache] %s 清理 %s 释放 %.1fMB", safe, rel, freed / 1048576)

    result.freed_bytes_after = sum(_dir_size(root / d) for d in CACHE_DIRS)
    return result


def clear_all_caches() -> List[ClearResult]:
    """清理所有平台的缓存。逐平台返回结果。"""
    return [clear_platform_cache(i.platform) for i in list_platform_caches()]


def total_cache_bytes() -> int:
    return sum(i.cache_bytes for i in list_platform_caches())
