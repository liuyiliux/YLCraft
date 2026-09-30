"""快手接口常量（**全部来自实测抓包**，2026-09-30）。

## 来源：用已登录的持久化 profile 打开搜索页，拦截真实请求

    POST /rest/v/search/feed?__NS_hxfalcon=<签名>
    Headers: content-type: application/json
             kww: <与 cookie 里的 kwfv1 完全相同>
             referer: https://www.kuaishou.com/search/video?searchKey=<编码关键词>
    Body:   {"keyword": "...", "page": "search", "webPageArea": "", "pcursor": ""}
    → {"result":1, "webPageArea":"searchxxnull", "pcursor":"1",
       "feeds":[{type, tags, photo:{id,caption,duration,coverUrl,
                                    viewCount,likeCount,photoUrls,...}, author}]}

## ⚠️ 签名 `__NS_hxfalcon` 是**必需**的（实测）

    无签名 / 只带 kww  → {"result":50,"error_msg":"**签名验证失败**"}

**纯 HTTP 拿不到签名** —— 快手的签名库是混淆 JS
（`kws-10-0.0.1-obfuscated.*.js`），**`window` 上也没有可调用的函数**
（和小红书的 `_webmsxyw` 一样被打包进闭包了）。

## ✅ 但实测发现一条**可行路径**：签名**可以复用**

    ① 在浏览器里打开一次搜索页 → 页面自己发请求 → 拦截到带签名的 URL
    ② 在**同一页面上下文**里复用那个 URL + 换关键词 → **成功**

    实测：
        旅行: {"result":1,"n":19}
        宠物: {"result":1,"n":19}
        健身: {"result":1,"n":20}
        翻页: pcursor="" → "1" → "2"   各 19~20 条

**签名与关键词无关**（是会话级的），所以抓一次能用很久。

## 翻页

用 `pcursor` 游标（不是页码）：第 1 页传空串，响应给 `"1"`，下一页传它。
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

BASE = "https://www.kuaishou.com"
SEARCH_FEED = "/rest/v/search/feed"
SEARCH_USER = "/rest/v/search/user"
NEW_RECO = "/new-reco"
SEARCH_PAGE = "/search/video"

# 每个 feed 的 `type` 值（实测：1 = 视频）
FEED_TYPE_VIDEO = 1


def search_page_url(keyword: str) -> str:
    """搜索结果页 URL —— 签名就从这个页面的请求里抓。"""
    return f"{BASE}{SEARCH_PAGE}?searchKey={quote(keyword)}"


def build_feed_body(keyword: str, pcursor: str = "") -> Dict[str, Any]:
    """构造 `/rest/v/search/feed` 的请求体（**实测字段**）。

        {"keyword":"美食","page":"search","webPageArea":"","pcursor":""}
    """
    return {
        "keyword": keyword,
        "page": "search",
        "webPageArea": "",
        "pcursor": pcursor or "",
    }


def build_user_body(keyword: str, pcursor: str = "") -> Dict[str, Any]:
    """构造 `/rest/v/search/user` 的请求体（搜用户，实测）。

        {"keyword":"美食","pcursor":"","searchSessionId":""}
    """
    return {
        "keyword": keyword,
        "pcursor": pcursor or "",
        "searchSessionId": "",
    }


def pick_video_url(photo: Dict[str, Any]) -> str:
    """从 `photo` 里挑视频直链。

    实测优先级（`photoUrls` 是**原画**，`photoH265Urls` 是 H265）：

        photoUrls[0].url        → mp4（原画）
        photoH265Urls[0].url    → mp4（H265，兼容性差些）

    取不到就返回空 —— **不编造**。
    """
    for key in ("photoUrls", "photoH265Urls", "manifest"):
        v = photo.get(key)
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, dict):
                u = first.get("url")
                if isinstance(u, str) and u.startswith("http"):
                    return u
            elif isinstance(first, str) and first.startswith("http"):
                return first
        elif isinstance(v, dict):
            u = v.get("url")
            if isinstance(u, str) and u.startswith("http"):
                return u
    return ""


def pick_cover_url(photo: Dict[str, Any]) -> str:
    """封面地址（实测 `coverUrl` 存在）。"""
    for key in ("coverUrl", "animatedCoverUrl"):
        u = photo.get(key)
        if isinstance(u, str) and u.startswith("http"):
            return u
    return ""


def _to_int(v: Any) -> int:
    """快手很多数值是**字符串**（和抖音一样），统一转 int。"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v.strip()))
        except (ValueError, TypeError):
            return 0
    return 0


def parse_feed(feed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把一条 `feed` 转成我们内部用的 dict（**字段全部实测**）。

    实测结构：

        {"type": 1, "tags": [{"name": "蜜汁排骨"}],
         "author": {"id": ..., "name": ...},
         "photo": {"id": "3xbfmxwduhwpm79",
                   "caption": "在广东珠海斗门镇…",
                   "duration": 286566,          # **毫秒**
                   "coverUrl": "https://p5.a.yximgs.com/…jpg",
                   "viewCount": 7485492, "likeCount": 134024,
                   "photoUrls": [{"url": "https://….mp4"}]}}

    取不到的留空/0 —— **不编造**。
    """
    if not isinstance(feed, dict):
        return None
    photo = feed.get("photo")
    if not isinstance(photo, dict):
        return None
    pid = str(photo.get("id") or "")
    if not pid:
        return None

    author = feed.get("author") if isinstance(feed.get("author"), dict) else {}
    tags = [
        str(t.get("name"))
        for t in (feed.get("tags") or [])
        if isinstance(t, dict) and t.get("name")
    ]
    caption = str(photo.get("caption") or "")
    duration_ms = _to_int(photo.get("duration"))

    return {
        "id": pid,
        "title": caption,
        "desc": caption,
        "author": str(author.get("name") or ""),
        "author_id": str(author.get("id") or ""),
        "cover": pick_cover_url(photo),
        "video_url": pick_video_url(photo),
        "duration": duration_ms // 1000 if duration_ms else 0,
        "views": _to_int(photo.get("viewCount")),
        "likes": _to_int(photo.get("likeCount")),
        "collects": _to_int(photo.get("collectCount")),
        "comments": _to_int(photo.get("commentCount")),
        "tags": tags,
        "type": "video" if feed.get("type") == FEED_TYPE_VIDEO else "note",
        "url": f"{BASE}/short-video/{pid}",
        # 原始条目留着（详情/调试用）
        "raw": feed,
    }


def parse_user(user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把一条 `users[]` 转成内部结构（实测字段）。

        {"user_name": "快手美食", "headurl": "https://…jpg",
         "user_id"/"id": …, "fan"/"followerCount": …}
    """
    if not isinstance(user, dict):
        return None
    uid = str(user.get("id") or user.get("user_id") or "")
    name = str(user.get("user_name") or user.get("name") or "")
    if not uid and not name:
        return None
    return {
        "id": uid,
        "name": name,
        "avatar": str(user.get("headurl") or user.get("headUrl") or ""),
        "followers": _to_int(
            user.get("fan") or user.get("followerCount") or user.get("fansCount")
        ),
        "desc": str(user.get("user_text") or user.get("description") or ""),
        "verified": bool(user.get("verified")),
        "raw": user,
    }
