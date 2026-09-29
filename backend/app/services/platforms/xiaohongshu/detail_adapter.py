"""小红书详情适配器 —— 让「内容去水印解析」页也能用上笔记详情。

## 为什么需要这层

真实的详情提取在 `platforms/xiaohongshu/note.py`（走平台连接 + Cookie +
Patchright 浏览器），而「去水印解析」页是老链路
（`services/video/parser.py`），不经过平台连接。这里做桥接。

## 实测（2026-09-27）

  · 带 `xsec_token` 的链接能正常打开笔记页
  · 图片直接读 DOM（`.swiper-slide img`），无需签名接口
  · 实测拿到：标题「168cm/180斤古早波点穿搭…」、作者「禾子盒盒」、3 张图
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.video.xhs_detail")


def extract_note_id(url: str) -> Optional[str]:
    """从各种小红书 URL 里提取笔记 ID。

    支持：
      https://www.xiaohongshu.com/explore/{id}?xsec_token=...
      https://www.xiaohongshu.com/search_result/{id}?xsec_token=...
      https://www.xiaohongshu.com/discovery/item/{id}
      https://xhslink.com/xxxxx        （短链，需先重定向）
    """
    if not url:
        return None
    m = re.search(r"/(?:explore|search_result|discovery/item)/([0-9a-fA-F]{24})", url)
    if m:
        return m.group(1)
    # 兜底：24 位 hex
    m = re.search(r"/([0-9a-f]{24})", url)
    return m.group(1) if m else None


def extract_xsec_token(url: str) -> str:
    """取链接里的 xsec_token。

    ⚠️ 这个 token 是访问凭证：实测不带 token 打开笔记页会显示
    「当前笔记暂时无法浏览」。而且它**会轮换**（URL 里与页面内的值不同），
    所以只能用当次链接里的，不能长期缓存。
    """
    if not url:
        return ""
    m = re.search(r"[?&]xsec_token=([^&]+)", url)
    return m.group(1) if m else ""


async def fetch_xhs_detail(url: str) -> Dict[str, Any]:
    """取小红书笔记详情，返回老 parser 期望的 dict。

    失败返回 {}（外层会 fallback 到 yt-dlp）。
    """
    note_id = extract_note_id(url)
    if not note_id:
        logger.warning(
            "[xhs_detail] 无法从 URL 提取笔记 ID（短链 xhslink.com 需先解析重定向）: %s",
            url[:120],
        )
        return {}

    from app.services.platforms import create_client
    from app.services.platforms.login_health import (
        netscape_to_header,
        resolve_connection,
    )

    _conn_id, raw = resolve_connection("", "XHS")
    if not raw:
        logger.warning("[xhs_detail] 没有可用的小红书连接（无法读取登录态）")
        return {}

    cookie = netscape_to_header(raw, "xiaohongshu")
    token = extract_xsec_token(url)
    # ⚠️ **走 API 模式（纯 HTTP）**，不开浏览器（2026-09-29 修正）
    #
    # 这里原本是 `mode="patchright"`，注释写"API 端点已失效"——
    # **那个判断是错的**：端点一直活着，当时只是缺 X-s/X-t 签名。
    # 加上 `xhshow` 签名后实测：
    #
    #     POST /api/sns/web/v1/feed  → 200, note_card 含
    #     title/desc/image_list(原图)/video(多清晰度)/interact_info
    #
    # 纯 HTTP 比浏览器路径**更快**、字段**更全**，也不再需要
    # "带 token 直接 goto"那套。token 从 url 里取（这是必需的，实测
    # 不带 token 会返回 HTTP 461）。
    if not token:
        logger.warning(
            "[xhs_detail] URL 缺少 xsec_token —— 详情接口必需"
            "（实测缺失返回 HTTP 461）。url=%s", url[:110],
        )
        return {}

    client = create_client("xiaohongshu", mode="api", cookie=cookie)
    if client is None:
        logger.warning("[xhs_detail] 小红书客户端未注册")
        return {}

    async with client:
        detail = await client.get_detail(note_id, xsec_token=token)

    if detail is None:
        logger.warning("[xhs_detail] 详情为空: %s", note_id)
        return {}

    logger.info(
        "[xhs_detail] %s -> %s，%d 张图",
        note_id, detail.type, len(detail.images or []),
    )
    return {
        "video_url": detail.video or "",
        "cover_url": detail.video_cover or (detail.images[0] if detail.images else ""),
        "title": detail.title or "",
        "author_name": detail.author or "",
        "author_uid": detail.author_id or "",
        "duration": detail.duration or 0,
        "like_count": detail.likes or 0,
        "comment_count": detail.comments or 0,
        "share_count": detail.shares or 0,
        "collect_count": detail.collects or 0,
        "content_type": "image" if detail.images else "video",
        "images": list(detail.images or []),
        # 走的是纯 HTTP API（不是浏览器 DOM），名字要如实反映
        "parse_method": "xiaohongshu_api",
    }
