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

from ..types import SearchParams, SearchResult, UserProfile
from .apis import (
    GQL_URL,
    REQUIRED_COOKIES,
    SEARCH_OP,
    USER_BY_SCREEN_NAME_FIELD_TOGGLES,
    USER_BY_SCREEN_NAME_OP,
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
    retry_on_404: bool = True,
) -> Dict[str, Any]:
    """请求任意 GraphQL 操作，返回解析后的 JSON。

    404 时：清 transaction-id 缓存 → 重新生成 → 重试一次
    （twscrape `queue_client.py` 同款策略）。

    `field_toggles` 只有部分操作需要（如 UserByScreenName）。
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

    logger.info("[twitter] 搜索 %r -> %d 条（HTTP，page=%d，翻 %d 页）",
                params.keyword, len(results), page_no, pages)
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
