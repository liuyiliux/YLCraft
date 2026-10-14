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

from ..types import LoginExpiredError, SearchParams, SearchResult, UserProfile
from .apis import (
    GQL_URL,
    LIKES_OP,
    REQUIRED_COOKIES,
    SEARCH_OP,
    USER_BY_SCREEN_NAME_FIELD_TOGGLES,
    USER_BY_SCREEN_NAME_OP,
    USER_TWEETS_OP,
    WEB_BEARER,
    build_search_variables,
    build_user_lookup_variables,
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

# page 模式的最大页码。
#
# X 没有 page 参数，page=N 只能靠 cursor **顺序翻过**前 N-1 页，
# 所以页数越大越慢（每页一次请求 + 一次 transaction-id 生成）。
# 超过这个值就报可操作错误，**而不是默默返回第 1 页**
# （那样前端会看到"翻页没反应"，实测就是这个症状）。
MAX_PAGE = 10


class TwitterAuthError(LoginExpiredError):
    """X 凭证缺失或失效（需要用户重新登录）。

    ⚠️ **继承 `LoginExpiredError`**（2026-09-30 改）——
    这样 API 层能把它映射成 **401**（而不是 500），
    前端据此提示"请重新登录 X"，而不是"加载失败"。
    """


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
    """请求一页 SearchTimeline（`_request_page_raw` 的薄封装）。"""
    return await _request_page_raw(
        cookie_header, SEARCH_OP, variables, retry_on_404=retry_on_404
    )


async def _request_page_raw(
    cookie_header: str,
    op: str,
    variables: Dict[str, Any],
    *,
    field_toggles: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    retry_on_404: bool = True,
) -> Dict[str, Any]:
    """请求任意 GraphQL 操作，返回解析后的 JSON。

    404 时：清 transaction-id 缓存 → 重新生成 → 重试一次
    （twscrape `queue_client.py` 同款策略）。

    `field_toggles` 只有部分操作需要（如 UserByScreenName）。

    ## ⚠️ `features` 参数（2026-10-01 加）

    TweetDetail（取评论）**必须**带 `features`，实测只发 `variables` 时
    拿不到数据。但 SearchTimeline **不需要** —— 所以这里做成**可选**参数
    默认不发，保持搜索现有行为不变（不破坏已实测通过的搜索）。

    出处：twscrape `api.py` TweetDetail 用 `params = {"variables": kv, "features": GQL_FEATURES}`。
    """
    ck = cookie_map(cookie_header)
    missing = [n for n in REQUIRED_COOKIES if not ck.get(n)]
    if missing:
        raise TwitterAuthError(
            f"[twitter] 缺少必要的 cookie：{', '.join(missing)}。"
            "X 搜索必须有 auth_token + ct0 —— 请在「账号中心」"
            "用浏览器方式登录一次 x.com，登录态会自动保存。"
        )

    path = f"/i/api/graphql/{op}"

    for attempt in (1, 2):
        txid = await make_transaction_id(
            cookie_header, "GET", path, force_refresh=(attempt == 2)
        )
        headers = _build_headers(cookie_header, ck["ct0"], txid)
        params: Dict[str, Any] = {
            "variables": json.dumps(variables, ensure_ascii=False)
        }
        if field_toggles:
            params["fieldToggles"] = json.dumps(field_toggles, ensure_ascii=False)
        # ⚠️ TweetDetail（评论）需要 features；SearchTimeline 不需要（默认不发）
        if features:
            params["features"] = json.dumps(features, ensure_ascii=False)

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            resp = await c.get(f"{GQL_URL}/{op}", params=params, headers=headers)

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
            f"[twitter] 接口 {op} 返回 HTTP {resp.status_code}。"
            f"（body 前 120：{resp.text[:120]!r}）"
        )

    raise RuntimeError("[twitter] 重新生成 transaction-id 后仍失败。")


async def _request_post_op(
    cookie_header: str,
    op: str,
    variables: Dict[str, Any],
    *,
    features: Optional[Dict[str, Any]] = None,
    field_toggles: Optional[Dict[str, Any]] = None,
    retry_on_404: bool = True,
) -> Dict[str, Any]:
    """**POST** 一个 GraphQL 操作（HomeLatestTimeline 用）。

    ## ⚠️ 为什么不能复用 `_request_page_raw`（2026-10-11）

    它写的是 **GET**（`?variables=...&features=...`），而
    **HomeLatestTimeline 是 POST**，且 —— 关键差别 ——
    **`queryId` 要放在 JSON body 里**（不是只放 URL）：

        POST /i/api/graphql/{qid}/HomeLatestTimeline
        body = {"variables": {...}, "features": {...},
                "fieldToggles": {...}, "queryId": "<qid>"}

    实测（2026-10-11）：照真实请求这样发 → HTTP 200，35 条推文。

    ⚠️ 404 的处理与 GET 一致：清 transaction-id 缓存 → 重新生成 → 重试一次
    （404 通常是"缺/过期 transaction-id"，不是"没有结果"）。
    """
    ck = cookie_map(cookie_header)
    missing = [n for n in REQUIRED_COOKIES if not ck.get(n)]
    if missing:
        raise TwitterAuthError(
            f"[twitter] 缺少必要的 cookie：{', '.join(missing)}。"
            "请在「账号中心」用浏览器方式登录一次 x.com。"
        )

    path = f"/i/api/graphql/{op}"
    body: Dict[str, Any] = {"variables": variables}
    if features:
        body["features"] = features
    if field_toggles:
        body["fieldToggles"] = field_toggles
    # ⚠️ queryId 也要在 body 里（实测真实请求就是这样）
    body["queryId"] = op.split("/", 1)[0]

    for attempt in (1, 2):
        txid = await make_transaction_id(
            cookie_header, "POST", path, force_refresh=(attempt == 2)
        )
        headers = _build_headers(cookie_header, ck["ct0"], txid)
        headers["content-type"] = "application/json"

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            resp = await c.post(f"{GQL_URL}/{op}", json=body, headers=headers)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in (401, 403):
            raise TwitterAuthError(
                f"[twitter] X 拒绝请求（HTTP {resp.status_code}）。"
                "登录态可能已失效 —— 请在「账号中心」重新登录一次 x.com。"
            )

        if resp.status_code == 404 and retry_on_404 and attempt == 1:
            logger.info("[twitter] POST %s 404 —— 重新生成 transaction-id 后重试", op)
            invalidate_xclid(cookie_header)
            continue

        raise RuntimeError(
            f"[twitter] 接口 {op} 返回 HTTP {resp.status_code}。"
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
        # ⚠️ 书签 / 浏览量 / 引用（2026-10-11 补）—— 与 `_parse_tweet_result`
        #    保持一致（同一份数据两处解析，字段不能一边有一边没有）。
        collects=int(legacy.get("bookmark_count") or 0),
        views=_views_of(t),
        create_time=str(legacy.get("created_at") or ""),
        raw_data={
            "_images": images,
            "_video_url": video,
            "handle": handle,
            "lang": legacy.get("lang") or "",
            "quote_count": int(legacy.get("quote_count") or 0),
            "http": t,
        },
    )


# =============================================================================
# 入口
# =============================================================================

async def get_replies_via_http(
    tweet_id: str,
    *,
    cookie_header: str,
    max_results: int = 20,
    max_pages: int = 3,
    direct_only: bool = True,
    parent_comment_id: str = "",
) -> List[Dict[str, Any]]:
    """取一条推文的评论（回复）—— 复用 TweetDetail，纯 HTTP。

    ## 接口（2026-10-01 实测 200）

        GET {GQL_URL}/{TWEET_DETAIL_OP}
            ?variables={"focalTweetId":...,"referrer":"tweet",...}
            &features={GQL_FEATURES}

    ⚠️ 必须带 `features`（实测只发 variables 拿不到数据）——
    这就是 `_request_page_raw` 加 `features` 可选参数的原因。

    ## 翻页（实测选型）

    调研实测了两种游标：
        `ShowMore`  → 只多 1 条（展开单条 thread 的更多回复），不适合主翻页
        `Bottom`    → 每页 40 条全新增 ✅ ← 用它（与 `_get_bottom_cursor` 一致）

    ⚠️ 注意：twscrape 文档说用 `ShowMoreThreads`，但**实测响应里没有**
    这个 cursorType（只有 `ShowMore`×3 + `Bottom`×1）。

    Args:
        tweet_id: 推文 ID
        cookie_header: cookie（需 auth_token + ct0）
        max_results: 最多取多少条
        max_pages: 最多翻几页（每页约 40 条，响应 176KB 很大，别翻太多）
        direct_only: 只返回**直接回复主推**的（过滤二级回复和广告）

    Returns:
        归一后的评论字典列表。
    """
    want = max(1, int(max_results or 20))
    from .apis import GQL_FEATURES, TWEET_DETAIL_OP, build_tweet_detail_variables

    collected: Dict[str, Dict] = {}
    cursor: Optional[str] = None

    for _ in range(max(1, max_pages)):
        variables = build_tweet_detail_variables(tweet_id, cursor)
        payload = await _request_page_raw(
            cookie_header, TWEET_DETAIL_OP, variables, features=GQL_FEATURES
        )
        page: Dict[str, Dict] = {}
        _collect_tweets(payload, page)
        for rid, t in page.items():
            if rid == str(tweet_id):
                continue  # 跳过焦点推文本身
            if rid not in collected:
                collected[rid] = t

        if len(collected) >= want:
            break
        cursor = _get_bottom_cursor(payload)
        if not cursor:
            break

    out: List[Dict[str, Any]] = []
    for rid, t in list(collected.items())[:want]:
        legacy = t.get("legacy") or {}
        if not isinstance(legacy, dict):
            continue
        # ⚠️ 只要"直接回复主推"的：
        #    原始 JSON 字段是 `in_reply_to_status_id_str`
        #    （不是 twscrape 模型属性 `inReplyToTweetId` —— 那个在原始
        #     JSON 里是全 None，我差点误判"没有回复"）
        parent = str(legacy.get("in_reply_to_status_id_str") or "")
        if parent_comment_id:
            # 取子回复：只要直接回复**那条评论**的
            if parent != str(parent_comment_id):
                continue
        elif direct_only and parent != str(tweet_id):
            continue
        core = (t.get("core") or {}).get("user_results") or {}
        u = (core.get("result") or {}) if isinstance(core, dict) else {}
        # ⚠️ **作者名/handle 的新旧 schema**（2026-10-11 修）
        #
        # 原来只读**旧版扁平**字段 `u.name` / `u.screen_name` ——
        # 而 X 现在给的是**新版嵌套**：
        #
        #     u.core.name         = "sara"          ← 昵称在这
        #     u.core.screen_name  = "sarahsfek"     ← handle 也在这
        #     u.name / u.screen_name = **None**     ← 旧的没了
        #
        # 症状：评论列表里**所有人都是「匿名」**（`author` 空串），
        # 而 `author_id` / `avatar` 却正常 —— 因为那两个字段本来就
        # 读的是 `rest_id` / `avatar.image_url`（新版路径）。
        #
        # 浏览器实测（修前）：19 条评论全部显示「匿名」。
        #
        # ⇒ 两套都读（与本文件 `parse_user_http` 的做法保持一致）。
        ucore = u.get("core") if isinstance(u.get("core"), dict) else {}
        ulegacy = u.get("legacy") if isinstance(u.get("legacy"), dict) else {}
        author_name = (
            ucore.get("name") or ulegacy.get("name") or u.get("name") or ""
        )
        author_handle = (
            ucore.get("screen_name") or ulegacy.get("screen_name")
            or u.get("screen_name") or ""
        )
        # 评论图片：X 在 `legacy.extended_entities.media[]`（可能也有 entities）
        images: List[str] = []
        for holder in ("extended_entities", "entities"):
            media = (legacy.get(holder) or {}).get("media") or []
            for m in media:
                if isinstance(m, dict):
                    url = m.get("media_url_https") or m.get("media_url")
                    if isinstance(url, str) and url.startswith("http"):
                        images.append(url)
            if images:
                break
        out.append({
            "id": rid,
            "content": legacy.get("full_text") or "",
            "author": str(author_name),
            "author_id": str(u.get("rest_id") or legacy.get("user_id_str") or ""),
            # ⚠️ 作者 handle 在 screen_name，昵称在 name
            # ⚠️ 别自己加 "@" —— 实测 screen_name 有时已含（会出现 "@@xxx"）
            "author_handle": str(author_handle).lstrip("@"),
            "avatar": (u.get("avatar") or {}).get("image_url") if isinstance(u.get("avatar"), dict) else (u.get("profile_image_url_https") or ""),
            "likes": int(legacy.get("favorite_count") or 0),
            # ⚠️ created_at 是 RFC2822 字符串（与微博一样），先原样返回
            "create_time": legacy.get("created_at") or "",
            "reply_count": int(legacy.get("reply_count") or 0),
            "parent": parent,
            "images": images,
            # 回复给谁（handle）—— 前端可显示 "回复 @xxx"
            "reply_to": legacy.get("in_reply_to_screen_name") or "",
        })
    return out


async def search_via_http(
    params: SearchParams,
    *,
    cookie_header: str,
    max_pages: int = 10,
) -> List[SearchResult]:
    """纯 HTTP 搜 X。

    ## 两种取数模式

    **模式 A：`max_results` 驱动**（前端不传 page / page=1 时）
      从第 1 页开始，用 cursor 一直翻到够 `max_results` 条。
      这是主用法（"我要 50 条"）。

    **模式 B：`page` 驱动**（前端传 page>=2 时）
      X 的 GraphQL 只认 cursor，**没有 page 参数**。
      所以 page=N 要**先翻过前 N-1 页**（丢掉），再返回第 N 页的结果。
      否则前端点"第 2 页"会拿到和第 1 页**完全相同**的数据
      （实测踩过：两页首条 id 一样）。

      代价：page 越大越慢（要顺序翻过去）。所以这里限制
      `page <= MAX_PAGE`，超了就报可操作错误，而不是默默返回第 1 页。
    """
    want = max(1, params.max_results or 20)
    page_no = max(1, int(getattr(params, "page", 1) or 1))

    raw_st = getattr(params, "search_type", "") or "note"
    stype = str(getattr(raw_st, "value", raw_st))
    product = resolve_product(stype)

    if page_no > MAX_PAGE:
        raise ValueError(
            f"[twitter] 最多支持翻到第 {MAX_PAGE} 页（要第 {page_no} 页）。"
            "X 没有 page 参数，只能靠 cursor 顺序翻 —— 页数太大会很慢。"
            "如需更多结果，请把 max_results 调大（一次给够）。"
        )

    merged: Dict[str, Dict] = {}
    cursor: Optional[str] = None
    pages = 0
    # page=1 时收 0 页丢弃；page=N 时收 N-1 页丢弃
    skip_remaining = page_no - 1

    # 循环上限：跳过的页 + 本页要翻的页
    total_rounds = skip_remaining + max_pages

    for i in range(total_rounds):
        variables = build_search_variables(
            keyword=params.keyword,
            count=20,
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
        cursor_next = _get_bottom_cursor(payload)

        # page=N 模式：先丢掉前 N-1 页
        if skip_remaining > 0:
            skip_remaining -= 1
            cursor = cursor_next
            if not cursor:
                # 还没翻到目标页就没游标了 → 该页不存在
                logger.info("[twitter] 翻到第 %d 页时没有更多数据", page_no)
                return []
            continue

        _collect_tweets(payload, merged)
        pages += 1

        if len(merged) >= want:
            break
        cursor = cursor_next
        if not cursor or len(merged) == before:
            break

    results: List[SearchResult] = []
    for t in merged.values():
        parsed = parse_tweet_http(t)
        if parsed is not None:
            results.append(parsed)

    # ⚠️ **要告诉前端"还有没有下一页"**（2026-09-29 修）
    #
    # X 从来不设 `_has_more` —— 于是前端**永远显示"没有下一页"**，
    # 尽管后端 page=2/3 都能正常翻（实测首条各不相同）。
    # 用户反馈"x 搜索没有更多页"，就是这里缺字段。
    #
    # 判断依据：**还有 cursor** 就说明还有更多。
    # （X 是 cursor 分页，没有 total 可给 —— 不编造 total。）
    if results:
        results[0].raw_data["_has_more"] = bool(cursor_next)

    logger.info("[twitter] 搜索 %r -> %d 条（HTTP，page=%d，翻 %d 页，has_more=%s）",
                params.keyword, len(results), page_no, pages, bool(cursor_next))
    return results[:want]


async def search_users_via_http(
    keyword: str,
    *,
    cookie_header: str,
    max_results: int = 20,
    max_pages: int = 5,
) -> List[UserProfile]:
    """搜 X 用户（**复用 SearchTimeline，只把 product 改成 "People"**）。

    来源：twscrape `api.py::search_user`
        kv = {"product": "People", **(kv or {})}
    调研确认 X **不存在**独立的 SearchUser/UserSearch operation
    （已逐行核对 twscrape 全部 OP_* + Scweet manifest），
    所以直接复用现有 queryId，零额外成本。

    用户项在 timeline 里（`__typename` 含 "User"），用 cursor 翻页。
    """
    want = max(1, max_results)
    merged: Dict[str, Dict] = {}
    cursor: Optional[str] = None

    for _ in range(max(1, max_pages)):
        variables = build_search_variables(
            keyword=keyword, count=20, product="People", cursor=cursor
        )
        payload = await _request_page(cookie_header, variables)
        _collect_users(payload, merged)
        if len(merged) >= want:
            break
        cursor = _get_bottom_cursor(payload)
        if not cursor:
            break

    out: List[UserProfile] = []
    for u in merged.values():
        parsed = parse_user_http(u)
        if parsed is not None:
            out.append(parsed)
    logger.info("[twitter] 用户搜索 %r -> %d 个（HTTP）", keyword, len(out))
    return out[:want]


async def get_user_via_http(
    screen_name: str,
    *,
    cookie_header: str,
) -> Optional[UserProfile]:
    """按 handle 取用户资料（UserByScreenName）。"""
    variables = build_user_lookup_variables(screen_name)
    payload = await _request_page_raw(
        cookie_header,
        USER_BY_SCREEN_NAME_OP,
        variables,
        field_toggles=USER_BY_SCREEN_NAME_FIELD_TOGGLES,
    )
    result = _walk(payload, lambda x: "screen_name" in x and "followers_count" in x)
    if not isinstance(result, dict):
        # 新版嵌套结构
        result = _walk(payload, lambda x: "core" in x and "relationship_counts" in x)
    if not isinstance(result, dict):
        logger.info("[twitter] 用户 %s 未取到资料", screen_name)
        return None
    return parse_user_http(result)


def _collect_users(obj: Any, out: Dict[str, Dict]) -> None:
    """收集用户对象（按 rest_id 去重）。

    X 的用户对象形状（新旧并存 —— 调研明确警告）：
        旧版扁平：`{"__typename": "User", "rest_id": ..., "legacy": {screen_name, followers_count, ...}}`
        新版嵌套：`{"core": {screen_name, name}, "relationship_counts": {...}}`

    这里对两种都收集，解析时在 `parse_user_http` 里兼容。
    """
    if isinstance(obj, dict):
        tn = str(obj.get("__typename") or "")
        rid = str(obj.get("rest_id") or "")
        legacy = obj.get("legacy")
        looks_user = (
            "User" in tn
            and rid
            and (isinstance(legacy, dict) or "core" in obj)
        )
        if looks_user:
            out[rid] = obj
        for v in obj.values():
            _collect_users(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_users(v, out)


def parse_user_http(u: Dict[str, Any]) -> Optional[UserProfile]:
    """把 X 的 user 对象转成统一 UserProfile。

    ## ⚠️ 新旧 schema 并存（调研明确警告）

    **旧版扁平**（`legacy.*`）：
        screen_name / name / description / followers_count /
        friends_count / statuses_count / profile_image_url_https /
        verified / location

    **新版嵌套**：
        core.screen_name / core.name
        relationship_counts.followers / relationship_counts.following
        tweet_counts.tweets
        profile_bio.description
        verification.verified
        avatar.image_url
        location.location
        rest_id（顶层）

    两套都要兼容 —— 只认一套会在 X 切换时静默返回空字段。
    """
    if not isinstance(u, dict):
        return None

    legacy = u.get("legacy") if isinstance(u.get("legacy"), dict) else {}
    core = u.get("core") if isinstance(u.get("core"), dict) else {}
    rel = u.get("relationship_counts") if isinstance(u.get("relationship_counts"), dict) else {}
    tweets = u.get("tweet_counts") if isinstance(u.get("tweet_counts"), dict) else {}
    bio = u.get("profile_bio") if isinstance(u.get("profile_bio"), dict) else {}
    ver = u.get("verification") if isinstance(u.get("verification"), dict) else {}
    avatar = u.get("avatar") if isinstance(u.get("avatar"), dict) else {}
    loc = u.get("location") if isinstance(u.get("location"), dict) else {}

    uid = str(u.get("rest_id") or legacy.get("id_str") or "")
    handle = str(core.get("screen_name") or legacy.get("screen_name") or "")
    # ⚠️ 只有 rest_id 而没有昵称/handle 的，不是有效用户对象
    # （实测 GraphQL 里 `{"rest_id": "..."}` 这种壳会在多处出现，
    #   把它当用户会产出全空的记录）
    if not handle:
        return None
    if not uid:
        uid = handle

    name = str(core.get("name") or legacy.get("name") or handle)
    desc = str(bio.get("description") or legacy.get("description") or "")

    followers = _to_int(rel.get("followers", legacy.get("followers_count")))
    following = _to_int(rel.get("following", legacy.get("friends_count")))
    total = _to_int(tweets.get("tweets", legacy.get("statuses_count")))
    likes = _to_int(legacy.get("favourites_count"))

    verified = bool(ver.get("verified", legacy.get("verified", False)))
    avatar_url = str(
        avatar.get("image_url") or legacy.get("profile_image_url_https") or ""
    )

    return UserProfile(
        id=uid,
        name=name,
        avatar=avatar_url,
        platform="twitter",
        desc=desc,
        followers=followers,
        following=following,
        total_likes=likes,
        total_videos=total,
        verified=verified,
        raw_data={
            "handle": handle,
            "location": str(loc.get("location") or legacy.get("location") or ""),
            "verified_type": ver.get("verified_type") or legacy.get("verified_type"),
            "profile_url": f"https://x.com/{handle}" if handle else "",
            "user": u,
        },
    )


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def fetch_home_latest(
    *,
    cookie_header: str,
    max_results: int = 20,
    cursor: str = "",
) -> Dict[str, Any]:
    """取「**正在关注**」作品流（`HomeLatestTimeline`）—— 纯 HTTP。

    ## 这是什么

    就是 X 首页那个「正在关注」页签 —— **你关注的账号发的推文**。
    用户要求："官方x平台有正在关注作品，我们也加下"。

    ## ⚠️ 与其它 timeline 的三个不同

    1. **它是 POST**（搜索/Likes/UserTweets 都是 GET），
       `queryId` 要放在 body 里 —— 所以走 `_request_post_op`。
    2. **响应路径不同**：
           data.home.home_timeline_urt.instructions[].entries[]
       （不是 `data.user.result.timeline...`）
    3. **queryId 抓不到于 JS bundle** —— 它在 bundle 里搜不到，
       改用抓真实网络请求（见 `apis.HOME_LATEST_QUERY_ID` 的说明）。

    ## 实测（2026-10-11）

        POST → HTTP 200，body ~589KB，**35 条推文**
        首条能被 `_parse_tweet_result` 正常解析（正文/作者/互动都在）

    Returns:
        {"tweets": [...], "cursor": "下一页游标或空", "has_more": bool}
    """
    if not cookie_header:
        raise TwitterAuthError("[twitter] 取「正在关注」需要登录态。")

    from .apis import HOME_LATEST_FEATURES, HOME_LATEST_OP, build_home_latest_variables

    variables = build_home_latest_variables(
        count=max(1, min(int(max_results or 20), 100)),
        cursor=cursor,
    )
    payload = await _request_post_op(
        cookie_header,
        HOME_LATEST_OP,
        variables,
        features=HOME_LATEST_FEATURES,
        field_toggles={"withPayments": False},
    )

    # ⚠️ 路径是 `data.home.home_timeline_urt`（与 user timeline 不同）
    home = ((payload.get("data") or {}).get("home") or {})
    urt = home.get("home_timeline_urt") or {}
    instructions = urt.get("instructions") or []

    tweets: List[SearchResult] = []
    next_cursor = ""
    seen: set = set()

    for ins in instructions:
        if not isinstance(ins, dict):
            continue
        for e in (ins.get("entries") or []):
            if not isinstance(e, dict):
                continue
            eid = str(e.get("entryId") or "")
            content = e.get("content") or {}

            # 游标项
            if "cursor-bottom" in eid or content.get("cursorType") == "Bottom":
                val = content.get("value")
                if isinstance(val, str) and val:
                    next_cursor = val
                continue

            if not eid.startswith("tweet-"):
                continue
            tr = ((content.get("itemContent") or {}).get("tweet_results") or {})
            tw = tr.get("result") or {}
            if tw.get("__typename") == "TweetWithVisibilityResults":
                tw = tw.get("tweet") or {}
            parsed = _parse_tweet_result(tw)
            if parsed is not None and parsed.id not in seen:
                seen.add(parsed.id)
                tweets.append(parsed)

    logger.info(
        "[twitter] 正在关注 -> %d 条（cursor=%s）",
        len(tweets), "有" if next_cursor else "无",
    )
    return {
        "tweets": tweets,
        "cursor": next_cursor,
        "has_more": bool(next_cursor),
    }


async def fetch_user_tweets(
    uid: str,
    *,
    cookie_header: str,
    max_results: int = 20,
    cursor: str = "",
) -> Dict[str, Any]:
    """取某个用户的推文列表（`UserTweets`）—— **纯 HTTP**。

    ## 参数来源

    twscrape `api.py::user_tweets_raw`：

        op = "SXVCYB8XHSS25nzIljNtZA/UserTweets"
        kv = {"userId": uid, "count": 40, "includePromotedContent": True,
              "withQuickPromoteEligibilityTweetFields": True,
              "withVoice": True, "withV2Timeline": True}

    ⚠️ 用 **`userId`（数字 id）**，不是 handle ——
    调用方要先用 `UserByScreenName` 拿 `rest_id`。

    ## 实测响应路径（2026-09-29）

        data.user.result.timeline.timeline.instructions[].entries[]
        推文项  entryId 以 `tweet-` 开头
        游标项  entryId 以 `cursor-bottom-` 开头，value 在 `content.value`

    实测（自己的账号）解析出 2 条，正文/互动数/时间都对。

    Returns:
        {"tweets": [...], "cursor": "下一页游标或空", "has_more": bool}
    """
    if not cookie_header:
        raise TwitterAuthError("[twitter] 取推文列表需要登录态。")
    if not uid:
        raise RuntimeError("[twitter] 取推文列表需要数字 userId。")

    from .apis import build_user_tweets_variables

    variables = build_user_tweets_variables(uid, count=max_results, cursor=cursor)
    payload = await _request_page_raw(
        cookie_header, USER_TWEETS_OP, variables
    )
    tweets, next_cursor = _parse_user_timeline(payload)

    logger.info(
        "[twitter] UserTweets uid=%s -> %d 条（cursor=%s）",
        uid, len(tweets), "有" if next_cursor else "无",
    )
    return {
        "tweets": tweets,
        "cursor": next_cursor,
        "has_more": bool(next_cursor),
    }


async def fetch_user_likes(
    uid: str,
    *,
    cookie_header: str,
    max_results: int = 20,
    cursor: str = "",
) -> Dict[str, Any]:
    """取某个用户**点赞过**的推文列表（`Likes`）—— **纯 HTTP**。

    ## queryId 来源（⚠️ 不是抄的，是实测抓的）

    twscrape **没有** Likes 操作（已逐行核对它的 21 个 `OP_*`），
    所以从已登录的 x.com JS bundle 里抓出来：
    `queryId:"mu4us66Q6RRNOywVQhGtRg",operationName:"Likes"`
    详见 `apis.LIKES_QUERY_ID`。

    ## 实测（2026-10-11）

        HTTP 200，单页 ~120KB，20 条/页
        响应路径与 UserTweets **完全一致**（复用 `_parse_user_timeline`）
        翻页实测：第 1 页 / 第 2 页首条 id 各不相同 ✅

    ## ⚠️ 只能看**自己**的

    X 的点赞列表是**私密**的 —— 传别人的 userId 不会报错，
    但只会返回**空的或极少**的结果（X 不再公开他人点赞）。
    所以这个接口的定位就是「我的数据」，不是「查别人赞了什么」。
    调用方（`/users/likes`）**默认只用自己的 id**。

    Returns:
        {"tweets": [...], "cursor": "下一页游标或空", "has_more": bool}
    """
    if not cookie_header:
        raise TwitterAuthError("[twitter] 取点赞列表需要登录态。")
    if not uid:
        raise RuntimeError("[twitter] 取点赞列表需要数字 userId。")

    from .apis import build_likes_variables

    variables = build_likes_variables(uid, count=max_results, cursor=cursor)
    payload = await _request_page_raw(cookie_header, LIKES_OP, variables)
    tweets, next_cursor = _parse_user_timeline(payload)

    logger.info(
        "[twitter] Likes uid=%s -> %d 条（cursor=%s）",
        uid, len(tweets), "有" if next_cursor else "无",
    )
    return {
        "tweets": tweets,
        "cursor": next_cursor,
        "has_more": bool(next_cursor),
    }


def _parse_user_timeline(payload: Dict[str, Any]) -> tuple:
    """解析「用户维度 timeline」（`UserTweets` / `Likes` 共用）。

    ## 为什么抽出来（2026-10-11）

    Likes 的响应结构与 UserTweets **逐字段相同**（实测确认）：

        data.user.result.timeline.timeline.instructions[].entries[]
        推文项  entryId 以 `tweet-` 开头
        游标项  entryId 含 `cursor-bottom-` 或 content.cursorType == "Bottom"

    原来这段逻辑内联在 `fetch_user_tweets` 里。如果 Likes 再抄一份，
    以后 X 改结构就要改两处 —— 本仓库「同一个东西两处定义、
    只改一处」的坑已经踩过多次（见 `TwitterAuthError` 的双定义）。

    Returns:
        `(tweets, next_cursor)` 二元组。
    """
    result = ((payload.get("data") or {}).get("user") or {}).get("result") or {}
    timeline = (result.get("timeline_v2") or result.get("timeline") or {})
    tl = timeline.get("timeline") or {}
    instructions = tl.get("instructions") or []

    tweets: List[SearchResult] = []
    next_cursor = ""

    for ins in instructions:
        if not isinstance(ins, dict):
            continue
        for e in (ins.get("entries") or []):
            if not isinstance(e, dict):
                continue
            eid = str(e.get("entryId") or "")
            content = e.get("content") or {}

            # 游标项
            if "cursor-bottom" in eid or content.get("cursorType") == "Bottom":
                val = content.get("value")
                if isinstance(val, str) and val:
                    next_cursor = val
                continue

            # 推文项
            if not eid.startswith("tweet-"):
                continue
            item = content.get("itemContent") or {}
            tr = item.get("tweet_results") or {}
            tw = tr.get("result") or {}
            # 转推/引用可能是 TweetWithVisibilityResults
            if tw.get("__typename") == "TweetWithVisibilityResults":
                tw = tw.get("tweet") or {}
            parsed = _parse_tweet_result(tw)
            if parsed is not None:
                tweets.append(parsed)

    return tweets, next_cursor


def _parse_tweet_result(tw: Dict[str, Any]) -> Optional[SearchResult]:
    """把 timeline 里的 tweet 对象转成 `SearchResult`。

    结构（新旧并存，两套都兼容）：

        legacy.full_text / favorite_count / retweet_count / reply_count /
               created_at / lang
        legacy.extended_entities.media[] → 图片或视频
        core.screen_name（新版把作者名放这里）
        rest_id（顶层）

    取不到的字段留空/0，**不编造**。
    """
    if not isinstance(tw, dict):
        return None
    legacy = tw.get("legacy") if isinstance(tw.get("legacy"), dict) else {}
    tid = str(tw.get("rest_id") or legacy.get("id_str") or "")
    text = str(legacy.get("full_text") or "")
    if not tid or not text:
        return None

    # 作者 handle：旧版在 legacy 的 user 子对象里，新版在 core
    handle = ""
    user = legacy.get("user") if isinstance(legacy.get("user"), dict) else {}
    core = tw.get("core") if isinstance(tw.get("core"), dict) else {}
    ucore = core.get("user_results") if isinstance(core.get("user_results"), dict) else {}
    ures = (ucore.get("result") or {}) if isinstance(ucore, dict) else {}
    ulegacy = ures.get("legacy") if isinstance(ures.get("legacy"), dict) else {}
    ucore2 = ures.get("core") if isinstance(ures.get("core"), dict) else {}
    handle = str(
        ucore2.get("screen_name") or ulegacy.get("screen_name")
        or user.get("screen_name") or ""
    )

    # 媒体
    images: List[str] = []
    video = ""
    entities = legacy.get("extended_entities") or legacy.get("entities") or {}
    for m in (entities.get("media") or []):
        if not isinstance(m, dict):
            continue
        mtype = m.get("type")
        if mtype == "photo":
            u = m.get("media_url_https") or m.get("media_url") or ""
            if u:
                images.append(str(u))
        elif mtype in ("video", "animated_gif"):
            variants = ((m.get("video_info") or {}).get("variants") or [])
            best = ""
            best_bitrate = -1
            for v in variants:
                if not isinstance(v, dict):
                    continue
                if v.get("content_type") != "video/mp4":
                    continue
                br = v.get("bitrate") or 0
                if br > best_bitrate:
                    best_bitrate = br
                    best = str(v.get("url") or "")
            if best:
                video = best
            cover = m.get("media_url_https") or ""
            if cover and not images:
                images.append(str(cover))

    return SearchResult(
        id=tid,
        title=text[:80],
        desc=text,
        # ⚠️ **昵称优先，handle 兜底**（2026-10-11 修）
        #
        # 这里原来写的是 `author=handle` —— 于是「我的点赞」「我的作品」
        # 「正在关注」三个列表显示的全是 **@用户名**（如 `BassplayerSerge`），
        # 而**查询页**显示的是**昵称**（如 `热爱分享`）。
        #
        # 用户问："作者能加中文吗 如果原来有昵称的" ——
        # **昵称一直解析出来了**（就在上面 `handle` 那个块里算的
        # `ucore2.get("screen_name")`），只是这里没用它。
        #
        # ⚠️ 实测同一条推文两个都有：
        #     name        = '热爱分享'        ← 昵称（中文/emoji 都在这）
        #     screen_name = 'xiaoma877'      ← handle
        #
        # ⇒ 昵称优先（更像"作者名"），handle 放 raw_data 备用。
        author=_display_name_of(tw) or handle,
        author_id=handle,
        cover=images[0] if images else "",
        url=f"https://x.com/{handle}/status/{tid}" if handle else f"https://x.com/i/status/{tid}",
        platform="twitter",
        type="video" if video else "note",
        likes=int(legacy.get("favorite_count") or 0),
        comments=int(legacy.get("reply_count") or 0),
        shares=int(legacy.get("retweet_count") or 0),
        # ⚠️ **收藏数 / 浏览量 / 引用数**（2026-10-11 补）
        #
        # 用户拿 X 官方截图对比："原版是我们对比我们少了哪个数"。
        # 官方一条推文显示 5 个数字，我们原来只有 3 个：
        #
        #     官方        X 字段                    原来
        #     💬 380     legacy.reply_count        ✅
        #     🔁 97      legacy.retweet_count      ✅
        #     ♡ 3027     legacy.favorite_count     ✅
        #     🔖 307     **legacy.bookmark_count**  ❌ 没取
        #     👁 1.4万   **t.views.count**          ❌ 没取（写死 0）
        #     （引用）    **legacy.quote_count**     ❌ 没取
        #
        # ⇒ 映射到通用字段：书签 → `collects`（语义一致），浏览量 → `views`。
        #   引用数放进 raw_data（通用结构里没有对应字段）。
        collects=int(legacy.get("bookmark_count") or 0),
        views=_views_of(tw),
        create_time=str(legacy.get("created_at") or ""),
        raw_data={
            "_images": images,
            "_video_url": video,
            "handle": handle,
            "lang": legacy.get("lang") or "",
            # 引用数（转推带评论）—— 通用结构没有，放 raw
            "quote_count": int(legacy.get("quote_count") or 0),
        },
    )


def _display_name_of(t: Dict[str, Any]) -> str:
    """取推文作者的**昵称**（不是 handle）。

    ## 为什么单独抽出来（2026-10-11）

    用户："作者能加中文吗 如果原来有昵称的"。

    X 的用户对象里**两个名字都有**，但位置在新旧 schema 里不同
    （与 `parse_user_http` 遇到的是同一件事）：

        新版嵌套：`core.user_results.result.core.name`
        旧版扁平：`core.user_results.result.name` / `legacy.name`

    实测同一条推文：

        name        = '热爱分享'      ← **昵称**（中文/emoji 都在这）
        screen_name = 'xiaoma877'    ← handle

    `_parse_tweet_result` 原来直接 `author=handle`，所以三个列表
    显示的全是 @用户名 —— 而**查询页**显示昵称，两边不一致。

    ⚠️ 取不到就返回空串，由调用方兜底成 handle（**不编造**）。
    """
    core = t.get("core") if isinstance(t.get("core"), dict) else {}
    ures = ((core.get("user_results") or {}).get("result") or {}
            if isinstance(core.get("user_results"), dict) else {})
    if not isinstance(ures, dict):
        return ""
    ucore = ures.get("core") if isinstance(ures.get("core"), dict) else {}
    ulegacy = ures.get("legacy") if isinstance(ures.get("legacy"), dict) else {}
    return str(
        ucore.get("name") or ulegacy.get("name") or ures.get("name") or ""
    )


def _views_of(t: Dict[str, Any]) -> int:
    """取浏览量（`views.count`）。

    ## ⚠️ 修正了旧的结论（2026-10-11）

    这里原来写着 `views=0  # 实测拿不到 → 0（不编造）` ——
    **那个结论是错的**。浏览量确实拿不到于 `legacy`，但它在**顶层**：

        t["views"] = {"count": "14478", "state": "EnabledWithCount"}

    实测：`legacy` 里没有 views（所以当初看 legacy 就以为没有），
    而顶层有，且 **count 是字符串**（要转 int）。

    state 可能是 `EnabledWithCount` / `Enabled` / 其它；只有带 count
    时才取，取不到就 0（**仍然不编造**）。
    """
    v = t.get("views")
    if not isinstance(v, dict):
        return 0
    raw = v.get("count")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


async def get_self_profile_via_http(*, cookie_header: str) -> Optional[UserProfile]:
    """**纯 HTTP** 取自己的资料 —— 两步，不需要浏览器。

    ## ⚠️ 修正了之前的结论（2026-09-29）

    之前这里写着"X 没有『我是谁』的接口，只能靠浏览器读页面"。
    **那个结论不完整** —— 浏览器不是唯一出路，有个 REST 端点就能拿：

        ① GET https://x.com/i/api/1.1/account/settings.json
           → {"screen_name": "308YYtGer5EWPqj", ...}     ← **自己的 handle**

        ② GET .../UserByScreenName?variables={"screen_name": handle}
           → 完整资料（粉丝/关注/推文/简介/头像）

    实测两步都 **HTTP 200**（用 `auth_token` + `ct0` +
    `x-client-transaction-id`，与搜索同一套凭证）。

    ## ⚠️ 响应路径与调研说的不同

    `UserByScreenName` 实测返回 **`data.user.result`**，
    而调研报告写的是 `data.user_result_by_screen_name.result` ——
    后者**取不到**。`get_user_via_http` 里两种都兼容。

    ## 关于 `twid`

    cookie 里的 `twid=u%3D{user_id}` 也含自己的 id，但用
    `UserByRestId` 查实测 **403**（Cloudflare），
    所以走 `settings.json` → `UserByScreenName` 这条已验证可用的路。
    """
    if not cookie_header:
        raise TwitterAuthError(
            "[twitter] 取自己的资料需要登录态（auth_token + ct0）。"
            "请在「账号中心」用浏览器方式登录一次 x.com。"
        )

    ck = cookie_map(cookie_header)
    missing = [n for n in REQUIRED_COOKIES if not ck.get(n)]
    if missing:
        raise TwitterAuthError(
            f"[twitter] 缺少必要的 cookie：{', '.join(missing)}。"
        )

    # ---- ① 拿自己的 handle ----
    settings_path = "/i/api/1.1/account/settings.json"
    headers = _build_headers(
        cookie_header, ck["ct0"],
        await make_transaction_id(cookie_header, "GET", settings_path),
    )
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        r = await c.get(f"https://x.com{settings_path}", headers=headers)

    if r.status_code in (401, 403):
        raise TwitterAuthError(
            f"[twitter] account/settings.json 拒绝访问（HTTP {r.status_code}）——"
            "登录态可能已失效，请在「账号中心」重新登录 x.com。"
        )
    if r.status_code != 200 or not r.text.lstrip().startswith("{"):
        logger.info(
            "[twitter] settings.json 返回非 JSON（HTTP %s），无法确定自己的 handle",
            r.status_code,
        )
        return None

    handle = str((r.json() or {}).get("screen_name") or "").strip()
    if not handle:
        logger.info("[twitter] settings.json 里没有 screen_name")
        return None
    logger.info("[twitter] 自己的 handle = %s", handle)

    # ---- ② 用 handle 取完整资料 ----
    return await get_user_via_http(handle, cookie_header=cookie_header)


async def close() -> None:
    clear_xclid_cache()
