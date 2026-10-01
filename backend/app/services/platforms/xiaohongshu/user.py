"""小红书用户相关逻辑（搜索 / 资料 / 作品列表）。

## 实测打通（2026-09-27）

    POST /api/sns/web/v1/search/usersearch  → code=1000，20 个用户
    GET  /api/sns/web/v1/user/otherinfo     → code=0，昵称/red_id/简介
    GET  /api/sns/web/v1/user_posted        → code=0，20 条 + has_more

## 与抖音的实现差异（重要）

| | 抖音 | 小红书 |
|---|---|---|
| 签名 | 当前**不需要** | **必须**（X-s/X-s-common） |
| 用户搜索 | GET + query | **POST + JSON body** |
| 搜索必需参数 | keyword/count/offset | 还要 `search_id`（需生成） |
| 资料里的粉丝数 | `user.follower_count`（int） | `data.interactions[]` 里 `type="fans"` 的 count（**字符串**） |

## 粉丝数字段踩过的坑

`data.basic_info` 里**没有**粉丝数——只有 {nickname, red_id, desc,
images, imageb, gender, ip_location}。
粉丝/关注/获赞在 `data.interactions` 数组里：

    [{"type":"follows","count":"2"}, {"type":"fans","count":"195"},
     {"type":"interaction","count":"2930"}]

数量是**字符串**，且可能带 "万"/"K" 等后缀（搜索接口的 `fans` 就是
"140.9万"），所以统一走 `parse_count` 解析。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..types import SearchResult, UserProfile
from .apis_user import (
    API_HOST,
    USER_OTHERINFO,
    USER_POSTED,
    USER_SEARCH,
    USER_SEARCH_ALT,
)
from .signing import get_search_id, sign_get, sign_post

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.user")

# 用于作品列表的图片规格（实测被服务端接受）
IMAGE_SCENES = "FD_WM_WEBP"


def _headers_base(cookie: str) -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.xiaohongshu.com/",
        "Origin": "https://www.xiaohongshu.com",
        "Cookie": cookie,
    }


async def _get_json(client, uri: str, params: Dict[str, Any], cookie: str) -> Dict[str, Any]:
    """带签名的 GET。"""
    headers = _headers_base(cookie) | sign_get(uri, cookie, params)
    if client._http_client is None:
        await client._init_http_client()
    resp = await client._http_client.get(
        f"{API_HOST}{uri}", params=params, headers=headers
    )
    resp.raise_for_status()
    return resp.json()


async def _post_json(
    client, uri: str, payload: Dict[str, Any], cookie: str
) -> Dict[str, Any]:
    """带签名的 POST（小红书用户搜索必需）。"""
    headers = _headers_base(cookie) | sign_post(uri, cookie, payload)
    headers["Content-Type"] = "application/json"
    if client._http_client is None:
        await client._init_http_client()
    resp = await client._http_client.post(
        f"{API_HOST}{uri}", json=payload, headers=headers
    )
    resp.raise_for_status()
    return resp.json()


def _check_code(data: Dict[str, Any], what: str) -> None:
    """校验小红书响应码。

    小红书成功时 code 可能是 0 **或** 1000（实测：搜索返回 1000，其余返回 0），
    所以两者都算成功。失败时给可读原因——**不静默返回空**，
    否则会把"签名失效"误报成"没有数据"。

    ⚠️ **code=-100（登录已过期）必须是 `LoginExpiredError`**（2026-10-01 加，
    与 `search_api.py` 同步）。否则用户搜索路径会把它当成普通失败，
    API 层映射成 500 而不是 401，用户不知道该重新登录。
    """
    code = data.get("code")
    if code in (0, 1000):
        return
    msg = data.get("msg") or data.get("message") or ""
    if code == -100:
        from app.services.platforms.types import LoginExpiredError

        raise LoginExpiredError(
            f"[xhs] {what} 失败：登录已过期（code=-100）。"
            "请到「账号中心」重新获取小红书登录态后重试。"
        )
    if "signature" in str(msg).lower() or code == -1:
        raise RuntimeError(
            f"[xhs] {what} 签名校验失败（code={code}, msg={msg}）。"
            "请检查 Cookie 里的 a1 是否与连接一致，或重新获取 Cookie。"
        )
    raise RuntimeError(f"[xhs] {what} 失败：code={code}, msg={msg}")


async def search_users(
    client,
    keyword: str,
    max_results: int = 20,
) -> List[UserProfile]:
    """按关键词搜小红书用户（POST + 签名）。

    实测「美食」→ 20 个用户。
    """
    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    want = max(1, max_results)
    page = 1
    out: List[UserProfile] = []
    seen: set[str] = set()

    while len(out) < want:
        payload = {
            "search_user_request": {
                "keyword": keyword,
                "search_id": get_search_id(),
                "page": page,
                "page_size": min(20, want),
                "biz_type": "web_search_user",
                "request_id": f"{int(__import__('time').time())}",
            }
        }
        data = await _post_json(client, USER_SEARCH, payload, cookie)
        _check_code(data, "用户搜索")

        body = data.get("data") or {}
        users = body.get("users") or body.get("user_list") or []
        if not users:
            break

        for u in users:
            if not isinstance(u, dict):
                continue
            uid = str(u.get("id") or u.get("user_id") or "")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            out.append(parse_search_user(u))
            if len(out) >= want:
                break

        if not body.get("has_more"):
            break
        page += 1

    logger.info("[xhs] 用户搜索 %r -> %d 个用户", keyword, len(out))
    return out[:want]


async def get_user_profile(client, user_id: str) -> Optional[UserProfile]:
    """查他人资料（GET + 签名）。

    实测（逸流AI）：昵称/red_id/简介/ip_location + 粉丝数在 interactions 里。
    """
    if not user_id:
        return None
    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    params = {"target_user_id": user_id}
    data = await _get_json(client, USER_OTHERINFO, params, cookie)
    _check_code(data, "用户资料")

    body = data.get("data") or {}
    if not body:
        return None
    return parse_user_otherinfo(body, user_id)


async def get_self_profile(client) -> Optional[UserProfile]:
    """查**自己**的资料（做「我的数据」用）。

    ## 两步走（实测 2026-09-27）

    `GET /api/sns/web/v2/user/me` 只返回基础资料：

        {user_id, nickname, desc, gender, imageb, red_id, guest, xsec_token}

    **没有粉丝数/关注数/作品数** —— 所以拿到 user_id 后还要再调
    `user/otherinfo` 补全统计（那个接口有 `interactions` 数组）。

    实测：
        v2/user/me       → 昵称=逸流AI, red_id=95645311698, desc=分享ai知识
        user/otherinfo   → 粉丝=195, 关注=2, 获赞与收藏=2930, 作品=73
    """
    from .apis_user import USER_SELFINFO

    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    if not cookie:
        return None

    # 1) 先拿自己的基础资料（含 user_id）
    data = await _get_json(client, USER_SELFINFO, {}, cookie)
    _check_code(data, "查询自己")
    me = data.get("data") or {}
    if not me:
        return None

    user_id = str(me.get("user_id") or "")
    base = UserProfile(
        id=user_id,
        name=me.get("nickname") or "",
        avatar=me.get("imageb") or me.get("images") or "",
        platform="xiaohongshu",
        desc=me.get("desc") or "",
        raw_data={
            "red_id": me.get("red_id") or "",
            "xsec_token": me.get("xsec_token") or "",
            "guest": me.get("guest"),
            "me": me,
        },
    )

    # 2) 用 user_id 补统计（v2/user/me 里没有）
    if user_id:
        try:
            full = await get_user_profile(client, user_id)
            if full:
                base.followers = full.followers
                base.following = full.following
                base.total_likes = full.total_likes
                base.total_videos = full.total_videos
                # otherinfo 的简介/IP 属地更完整，覆盖 self 的
                if full.desc:
                    base.desc = full.desc
                base.raw_data["ip_location"] = (full.raw_data or {}).get("ip_location", "")
                base.raw_data["interactions"] = (full.raw_data or {}).get("interactions", [])
        except Exception as exc:
            logger.warning("[xhs] 补统计失败（保留基础资料）：%s: %s",
                           type(exc).__name__, exc)

    return base


async def get_user_videos(
    client,
    user_id: str,
    max_results: int = 20,
) -> List[SearchResult]:
    """取用户作品列表（GET + 签名，cursor 分页）。

    实测（逸流AI）：20 条 / has_more=True / cursor 可继续翻页。
    """
    if not user_id:
        return []
    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    want = max(1, max_results)
    cursor = ""          # 首页传空串（实测）
    out: List[SearchResult] = []
    seen: set[str] = set()

    while len(out) < want:
        params = {
            "num": str(min(20, want)),
            "cursor": cursor,
            "user_id": user_id,
            "image_scenes": IMAGE_SCENES,
        }
        data = await _get_json(client, USER_POSTED, params, cookie)
        _check_code(data, "作品列表")

        body = data.get("data") or {}
        notes = body.get("notes") or []
        if not notes:
            break

        for n in notes:
            if not isinstance(n, dict):
                continue
            nid = str(n.get("note_id") or n.get("id") or "")
            if not nid or nid in seen:
                continue
            seen.add(nid)
            out.append(parse_user_note(n, user_id))
            if len(out) >= want:
                break

        if not body.get("has_more"):
            break
        next_cursor = body.get("cursor") or ""
        if not next_cursor or next_cursor == cursor:
            break
        cursor = str(next_cursor)

    logger.info("[xhs] 用户 %s 作品 -> %d 条", user_id[:12], len(out))
    return out[:want]


# =============================================================================
# 解析
# =============================================================================

def parse_count(value: Any) -> int:
    """把小红书的计数转成 int。

    实测有两种形态：
      · 数字字符串："195" / "2930"
      · 带后缀："140.9万" / "2.9K"
    """
    s = str(value or "").strip()
    if not s:
        return 0
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100000000)
        low = s.lower()
        if low.endswith("k"):
            return int(float(low[:-1]) * 1000)
        if low.endswith("m"):
            return int(float(low[:-1]) * 1000000)
        # 去掉千分位逗号
        return int(float(s.replace(",", "")))
    except (ValueError, TypeError):
        return 0


def parse_search_user(u: Dict[str, Any]) -> UserProfile:
    """解析搜索结果里的用户项。

    实测字段：id, name, image, fans(字符串 "140.9万"), sub_title,
              xsec_token, vshow, red_official_verified
    """
    return UserProfile(
        id=str(u.get("id") or u.get("user_id") or ""),
        name=u.get("name") or u.get("nickname") or "",
        avatar=u.get("image") or u.get("avatar") or "",
        platform="xiaohongshu",
        followers=parse_count(u.get("fans")),
        desc=u.get("sub_title") or u.get("desc") or "",
        verified=bool(u.get("red_official_verified") or u.get("vshow")),
        raw_data={
            "xsec_token": u.get("xsec_token") or "",
            "user": u,
        },
    )


def parse_user_otherinfo(body: Dict[str, Any], user_id: str) -> UserProfile:
    """解析 otherinfo 响应。

    ⚠️ 粉丝/关注/获赞在 `interactions` 数组里（**不在 basic_info**）：

        [{"type":"follows","count":"2"}, {"type":"fans","count":"195"},
         {"type":"interaction","count":"2930"}]

    作品数在 `data.posted`。
    """
    bi = body.get("basic_info") or {}

    def _stat(kind: str) -> int:
        for item in (body.get("interactions") or []):
            if isinstance(item, dict) and item.get("type") == kind:
                return parse_count(item.get("count"))
        return 0

    return UserProfile(
        id=user_id,
        name=bi.get("nickname") or "",
        avatar=bi.get("imageb") or bi.get("images") or "",
        platform="xiaohongshu",
        followers=_stat("fans"),
        following=_stat("follows"),
        total_likes=_stat("interaction"),   # 获赞与收藏
        total_videos=int(body.get("posted") or 0),
        desc=bi.get("desc") or "",
        raw_data={
            "red_id": bi.get("red_id") or "",
            "ip_location": bi.get("ip_location") or "",
            "liked": body.get("liked"),
            "collected": body.get("collected"),
            "basic_info": bi,
            "interactions": body.get("interactions") or [],
        },
    )


def parse_user_note(n: Dict[str, Any], user_id: str) -> SearchResult:
    """解析作品列表里的一条笔记。

    实测字段：note_id, type(normal/video), display_title, cover, liked_count…
    取不到的留空，不编造。
    """
    nid = str(n.get("note_id") or n.get("id") or "")
    cover = ""
    cv = n.get("cover")
    if isinstance(cv, dict):
        cover = cv.get("url_default") or cv.get("url") or ""
    elif isinstance(cv, str):
        cover = cv

    # 互动数：user_posted 里可能是字符串
    likes = parse_count(
        (n.get("interact_info") or {}).get("liked_count")
        if isinstance(n.get("interact_info"), dict)
        else n.get("liked_count")
    )

    is_video = str(n.get("type") or "").lower() == "video"

    return SearchResult(
        id=nid,
        title=n.get("display_title") or n.get("title") or "",
        author="",
        author_id=user_id,
        cover=cover,
        url=f"https://www.xiaohongshu.com/explore/{nid}",
        platform="xiaohongshu",
        type="video" if is_video else "note",
        likes=likes,
        raw_data={"note": n},
    )
