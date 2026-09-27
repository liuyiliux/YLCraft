"""抖音详情适配器 —— 让「内容去水印解析」页也能用上真实详情接口。

## 为什么需要这层

真实的详情接口在 `platforms/douyin/client.py`（走平台连接 + Cookie），
而「去水印解析」页是老链路（`services/video/parser.py`），
它不经过平台连接。这里做一层桥接：

  · 从库里取最近更新的抖音连接（用户可能刚重新登录，ID 会变）
  · 用统一 client 调详情接口
  · 把结果转成老 parser 期望的 dict 形状

## 实测（2026-09-27）

端点：`https://www-hj.douyin.com/aweme/v1/web/aweme/detail/`
（**域名是 www-hj**，不是 www —— 这是它长期没被发现的原因）

图文笔记实测拿到 9 张原图，均可直接下载（291~462 KB image/webp）。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.video.douyin_detail")


def extract_aweme_id(url: str) -> Optional[str]:
    """从各种抖音 URL 里提取作品 ID。

    支持：
      https://www.douyin.com/video/7656457812507817841
      https://www.douyin.com/note/7656457812507817841
      https://www.douyin.com/jingxuan?modal_id=7656457812507817841
      https://www.iesdouyin.com/share/video/7656457812507817841/

    短链（v.douyin.com）需要先重定向，由 `_resolve_short_link` 处理。
    """
    if not url:
        return None
    m = re.search(r"modal_id=(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(?:video|note|share/video)/(\d+)", url)
    if m:
        return m.group(1)
    # 兜底：路径最后一段是纯数字
    m = re.search(r"/(\d{15,})", url)
    return m.group(1) if m else None


# 需要跟随重定向才能拿到 ID 的短链域名
SHORT_LINK_HOSTS = ("v.douyin.com", "xhslink.com", "b23.tv", "t.cn")


async def _resolve_short_link(url: str) -> str:
    """跟随重定向拿到真实 URL。

    实测（2026-09-27）：
        https://v.douyin.com/iRNBho6u/  → 302 →
        https://www.iesdouyin.com/share/video/7298145681699622182/?…
    从中即可取出作品 ID。

    不在已知短链域名上时**原样返回**（不做无谓请求）。
    失败也原样返回，让上层走"提取不到 ID"的分支给可读错误。
    """
    if not any(h in (url or "") for h in SHORT_LINK_HOSTS):
        return url

    import httpx

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=20,
            headers={"User-Agent": _DESKTOP_UA},
        ) as client:
            resp = await client.get(url)
            location = resp.headers.get("location") or ""
            if location:
                logger.info(
                    "[douyin_detail] 短链重定向: %s -> %s",
                    url[:60], location[:90],
                )
                return location
    except Exception as exc:
        logger.warning(
            "[douyin_detail] 短链重定向失败：%s: %s", type(exc).__name__, exc
        )
    return url


_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)


async def fetch_douyin_detail(url: str) -> Dict[str, Any]:
    """取抖音作品详情，返回老 parser 期望的 dict。

    失败返回 {}（外层会 fallback 到 yt-dlp）。
    """
    # 短链先重定向（实测 v.douyin.com 302 → iesdouyin.com/share/video/{id}）
    url = await _resolve_short_link(url)

    aweme_id = extract_aweme_id(url)
    if not aweme_id:
        logger.warning("[douyin_detail] 无法从 URL 提取作品 ID: %s", url[:120])
        return {}

    from app.services.platforms import create_client
    from app.services.platforms.douyin.apis import AWEME_DETAIL, DETAIL_BASE_URL
    from app.services.platforms.login_health import (
        netscape_to_header,
        resolve_connection,
    )

    # 取最近更新的抖音连接（用户重新登录后 ID 会变，resolve_connection 会兜底）
    _conn_id, raw = resolve_connection("", "DOUYIN")
    if not raw:
        logger.warning("[douyin_detail] 没有可用的抖音连接（无法读取登录态）")
        return {}

    cookie = netscape_to_header(raw, "douyin")
    client = create_client("douyin", mode="api", cookie=cookie)
    if client is None:
        logger.warning("[douyin_detail] 抖音客户端未注册")
        return {}

    async with client:
        detail = await client.get_detail(aweme_id)

    logger.info(
        "[douyin_detail] %s -> %s，%d 张图",
        aweme_id, detail.type, len(detail.images),
    )
    return {
        "video_url": detail.video or "",
        "cover_url": detail.video_cover or "",
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
        "parse_method": "douyin_web_api",
        "detail_url": f"{DETAIL_BASE_URL}{AWEME_DETAIL}",
    }
