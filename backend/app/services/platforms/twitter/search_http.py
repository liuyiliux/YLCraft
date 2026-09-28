"""YLCraft — X 搜索（纯 HTTP GraphQL 路径）。

## 为什么优先 HTTP（2026-09-28 实测跑通）

原来的 DOM 路径有两个硬伤：
  · 必须开浏览器运行时（慢、占资源）
  · 受推特**虚拟列表**限制，滚一次回收一次离屏节点，
    只能"边滚边收集"（见 `search_dom.py`）

HTTP 路径没有这两个问题，而且字段更全：

| | HTTP | DOM |
|---|---|---|
| 浏览器 | 不需要 | 必须 |
| 翻页 | cursor（想拿多少拿多少） | 只能滚动 |
| 字段 | 精确时间/语言/媒体类型 | 只有可见文本 |
| 速度 | 快 | 慢 |

实测（4 页 85 条，字段完整）：
    第 1 页: +20 → 20    cursor=有
    第 2 页: +22 → 42    cursor=有
    第 3 页: +21 → 63    cursor=有
    第 4 页: +22 → 85    cursor=有

## ⚠️ 仍然需要登录

"不用浏览器"≠"不用登录"。必须有 `auth_token` + `ct0`（domain=.x.com）。
未登录/凭证失效时报**可操作错误**，不返回"0 条结果"。

## ⚠️ 缺 transaction-id 会 404

见 `xclid.py`。404 时这里会**清缓存 + 重新生成 + 重试一次**
（twscrape 同款策略），仍失败才报错。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from ..types import SearchParams, SearchResult
from .apis import (
    GQL_URL,
    REQUIRED_COOKIES,
    SEARCH_OP,
    WEB_BEARER,
    build_search_variables,
    resolve_product,
)
from .xclid import (
    TransactionIdError,
    UA,
    invalidate as invalidate_xclid,
    make_transaction_id,
)
from .xclid import clear_all as clear_xclid_cache

logger = logging.getLogger("ylcraft.platforms.twitter.http")


class TwitterAuthError(RuntimeError):
    """X 凭证缺失或失效（需要用户重新登录）。"""


def cookie_map(header: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (header or "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


def _build_headers(cookie_header: str, ct0: str, txid: str) -> Dict[str, str]:
    """构造请求头。

    来源：twscrape `account.py::make_client` +
          Scweet `account_session.py::_apply_headers`（两者一致）
    """
    return {
        "authorization": f"Bearer {WEB_BEARER}",
        "x-csrf-token": ct0,
        "cookie": cookie_header,
        "user-agent": UA,
        "x-client-transaction-id": txid,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "content-type": "application/json",
        "accept": "*/*",
        "referer": "https://x.com/",
    }


async def _request_page(
    cookie_header: str,
    variables: Dict[str, Any],
    *,
    retry_on_404: bool = True,
) -> Dict[str, Any]:
    """请求一页 SearchTimeline，返回解析后的 JSON。

    404 时：清 transaction-id 缓存 → 重新生成 → 重试一次
    （twscrape `queue_client.py` 同款策略）。
    """
    ck = cookie_map(cookie_header)
    missing = [n for n in REQUIRED_COOKIES if not ck.get(n)]
    if missing:
        raise TwitterAuthError(
            f"[twitter] 缺少必要的 cookie：{', '.join(missing)}。"
            "X 搜索必须有 auth_token + ct0 —— 请在「账号中心」"
            "用浏览器方式登录一次 x.com，登录态会自动保存。"
        )

    path = f"/i/api/graphql/{SEARCH_OP}"

    for attempt in (1, 2):
        txid = await make_transaction_id(
            cookie_header, "GET", path, force_refresh=(attempt == 2)
        )
        headers = _build_headers(cookie_header, ck["ct0"], txid)
        params = {"variables": json.dumps(variables, ensure_ascii=False)}

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            resp = await c.get(f"{GQL_URL}/{SEARCH_OP}", params=params, headers=headers)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in (401, 403):
            raise TwitterAuthError(
                f"[twitter] X 拒绝请求（HTTP {resp.status_code}）。"
                "登录态可能已失效 —— 请在「账号中心」重新登录一次 x.com。"
            )

        if resp.status_code == 404 and retry_on_404 and attempt == 1:
            # ⚠️ 这是"缺/过期 transaction-id"的典型症状，不是"没有结果"。
            # 清缓存后重新生成再试一次。
            logger.info("[twitter] 404 —— 重新生成 transaction-id 后重试")
            invalidate_xclid(cookie_header)
            continue

        raise RuntimeError(
            f"[twitter] 搜索接口返回 HTTP {resp.status_code}。"
            f"（body 前 120：{resp.text[:120]!r}）"
        )

    raise RuntimeError("[twitter] 重新生成 transaction-id 后仍失败。")


def _walk(obj: Any, pred) -> Optional[Dict]:
    """深度优先找第一个满足条件的对象。"""
    if isinstance(obj, dict):
        if pred(obj):
            return obj
        for v in obj.values():
            r = _walk(v, pred)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _walk(v, pred)
            if r is not None:
                return r
    return None


def _collect_tweets(obj: Any, out: Dict[str, Dict]) -> None:
    """收集推文对象（按 rest_id 去重）。

    实测形状：`{"__typename": "Tweet", "rest_id": "...", "legacy": {...}}`
    """
    if isinstance(obj, dict):
        if obj.get("__typename") == "Tweet" and isinstance(obj.get("legacy"), dict):
            rid = str(obj.get("rest_id") or "")
            if rid:
                out[rid] = obj
        for v in obj.values():
            _collect_tweets(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_tweets(v, out)


def _get_bottom_cursor(payload: Dict) -> Optional[str]:
    """取翻页游标。

    来源：twscrape `api.py::_get_cursor` 找 `cursorType == "Bottom"`。
    """
    cur = _walk(payload, lambda x: x.get("cursorType") == "Bottom")
    if isinstance(cur, dict):
        v = cur.get("value")
        return v if isinstance(v, str) else None
    return None


# =============================================================================
# 解析
# =============================================================================

def parse_tweet_http(t: Dict[str, Any]) -> Optional[SearchResult]:
    """把 GraphQL 的 tweet 对象转成统一 SearchResult。

    实测字段（`legacy` 里）：
        full_text / created_at / favorite_count / retweet_count /
        reply_count / lang / extended_entities.media / id_str
    作者在 `core.user_results.result.core.screen_name`（新版结构）
    或 `legacy.screen_name`（旧版）。

    ⚠️ `views`（浏览量）GraphQL **没给**（实测 None）—— 留 0，**不编造**。
    """
    if not isinstance(t, dict):
        return None
    legacy = t.get("legacy")
    if not isinstance(legacy, dict):
        return None

    tid = str(t.get("rest_id") or legacy.get("id_str") or "")
    if not tid:
        return None

    # 作者：新版在 core.user_results.result，旧版在 legacy
    user = _walk(t.get("core") or {}, lambda x: "screen_name" in x)
    if not user:
        user = _walk(t.get("legacy") or {}, lambda x: "screen_name" in x) or {}
    handle = str(user.get("screen_name") or "")
    screen = str(user.get("name") or handle)

    text = str(legacy.get("full_text") or "")
    media = ((legacy.get("extended_entities") or {}).get("media")
             or (legacy.get("entities") or {}).get("media") or [])

    images: List[str] = []
    video = ""
    for m in media:
        if not isinstance(m, dict):
            continue
        mtype = m.get("type")
        if mtype == "photo":
            u = m.get("media_url_https") or ""
            if u:
                images.append(u)
        elif mtype in ("video", "animated_gif"):
            # 视频：从 variants 里挑码率最高的 mp4
            variants = ((m.get("video_info") or {}).get("variants") or [])
            best, best_bitrate = "", -1
            for v in variants:
                if not isinstance(v, dict):
                    continue
                if v.get("content_type") != "video/mp4":
                    continue
                br = int(v.get("bitrate") or 0)
                if br > best_bitrate:
                    best, best_bitrate = str(v.get("url") or ""), br
            if best:
                video = best
            thumb = m.get("media_url_https") or ""
            if thumb:
                images.append(thumb)

    cover = images[0] if images else ""
    url = (f"https://x.com/{handle}/status/{tid}" if handle
           else f"https://x.com/i/status/{tid}")

    return SearchResult(
        id=tid,
        title=text[:80],
        desc=text,
        author=screen or handle,
        author_id=handle,
        cover=cover,
        url=url,
        platform="twitter",
        type="video" if video else "note",
        likes=int(legacy.get("favorite_count") or 0),
        comments=int(legacy.get("reply_count") or 0),
        shares=int(legacy.get("retweet_count") or 0),
        # views 实测拿不到 → 0（不编造）
        views=0,
        create_time=str(legacy.get("created_at") or ""),
        raw_data={
            "_images": images,
            "_video_url": video,
            "handle": handle,
            "lang": legacy.get("lang") or "",
            "http": t,
        },
    )


# =============================================================================
# 入口
# =============================================================================

async def search_via_http(
    params: SearchParams,
    *,
    cookie_header: str,
    max_pages: int = 10,
) -> List[SearchResult]:
    """纯 HTTP 搜 X（cursor 翻页，直到够量 / 没游标 / 到页数上限）。"""
    want = max(1, params.max_results or 20)

    raw_st = getattr(params, "search_type", "") or "note"
    stype = str(getattr(raw_st, "value", raw_st))
    product = resolve_product(stype)

    merged: Dict[str, Dict] = {}
    cursor: Optional[str] = None
    pages = 0

    for i in range(max_pages):
        variables = build_search_variables(
            keyword=params.keyword,
            count=min(20, max(20, want)) if want <= 20 else 20,
            product=product,
            cursor=cursor,
        )
        # 首页失败要抛出去（可操作错误）；
        # 后续页失败只记日志（已有结果不能丢）
        try:
            payload = await _request_page(cookie_header, variables)
        except (TwitterAuthError, TransactionIdError):
            if merged:
                logger.warning("[twitter] 第 %d 页凭证/生成器异常，返回已有结果", i + 1)
                break
            raise
        except Exception as exc:
            if merged:
                logger.warning("[twitter] 第 %d 页失败（%s），返回已有结果",
                               i + 1, type(exc).__name__)
                break
            raise

        before = len(merged)
        _collect_tweets(payload, merged)
        pages = i + 1

        if len(merged) >= want:
            break
        cursor = _get_bottom_cursor(payload)
        if not cursor or len(merged) == before:
            break

    results: List[SearchResult] = []
    for t in merged.values():
        parsed = parse_tweet_http(t)
        if parsed is not None:
            results.append(parsed)

    logger.info("[twitter] 搜索 %r -> %d 条（HTTP，%d 页）",
                params.keyword, len(results), pages)
    return results[:want]


async def close() -> None:
    clear_xclid_cache()
