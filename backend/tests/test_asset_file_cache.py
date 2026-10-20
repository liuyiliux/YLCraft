"""素材本地文件下载的缓存语义测试。

**为什么锁这条**：同一路径的**内容会被覆写** —— 动图重新合成后
`animation.gif` 原地替换（帧数、尺寸都变了），但 URL 一个字没变。
原实现无条件 `Cache-Control: public, max-age=86400`，浏览器/`<img>` 会把旧的那份
一直缓存住，用户看到「删了格、重新合成，下载到的还是旧文件」。

正确做法是 `no-cache` + **基于 mtime/size 的 ETag**：仍走协商缓存（304 很便宜），
但文件一变必然回源。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ASSETS_API = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "assets.py"


def _source() -> str:
    return ASSETS_API.read_text(encoding="utf-8")


def _download_fn_source() -> str:
    """抽出 `download_local_asset_file` 的函数体。"""
    src = _source()
    start = src.index("async def download_local_asset_file")
    # 到下一个顶层 def/装饰器为止
    rest = src[start + 10 :]
    m = re.search(r"\n(?=@router\.|def |async def |class )", rest)
    return rest[: m.start()] if m else rest


def _strip_comments(body: str) -> str:
    """去掉 `#` 注释：源码注释里会提到 `max-age=86400`（解释这条 bug 本身），
    只应检查**真正发出的响应头**。"""
    out = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # 去掉行尾注释（简单处理：不在引号内的 # 之后截断）
        if "#" in line:
            head = line.split("#", 1)[0]
            # 粗略保留：仅当 # 出现在引号外才截断
            if head.count('"') % 2 == 0 and head.count("'") % 2 == 0:
                line = head
        out.append(line)
    return "\n".join(out)


class TestLocalFileCaching:
    def test_does_not_send_long_max_age(self):
        """不能再无条件发 24 小时强缓存 —— 那正是"旧帧"被反复拿到的原因。"""
        body = _strip_comments(_download_fn_source())
        assert "max-age=86400" not in body, (
            "下载本地文件不能无条件 max-age=86400：同路径内容会被覆写"
            "（动图重新合成），会把旧文件一直缓存住"
        )

    def test_sends_no_cache_so_etag_is_revalidated(self):
        body = _strip_comments(_download_fn_source())
        assert "no-cache" in body

    def test_etag_is_derived_from_mtime_and_size(self):
        """ETag 必须跟着文件内容变，否则改了也返回 304。"""
        body = _strip_comments(_download_fn_source())
        assert "st_mtime" in body and "st_size" in body
        assert "ETag" in body

    def test_returns_304_when_etag_matches(self):
        body = _strip_comments(_download_fn_source())
        assert "if-none-match" in body
        assert "304" in body
