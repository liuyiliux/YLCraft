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

from typing import Any, Dict, List, Optional
from urllib.parse import quote

BASE = "https://www.kuaishou.com"
SEARCH_FEED = "/rest/v/search/feed"
SEARCH_USER = "/rest/v/search/user"
# 「我的数据」——来自调研报告的 SIG4_WHITELIST + 实测（页面自己会请求它）
PROFILE_GET = "/rest/v/profile/get"
# 用户作品列表（同属白名单，未实测）
PROFILE_FEED = "/rest/v/profile/feed"
NEW_RECO = "/new-reco"
SEARCH_PAGE = "/search/video"

# 评论（**免签名**，2026-10-01 实测发现）
#
# ⚠️ 与其它端点不同：这两个**不需要** `__NS_hxfalcon`。
# 实测对照（同一 cookie、同一时刻）：
#   /rest/v/search/feed        无签名 → {"result":50,"签名验证失败"}
#   /rest/v/photo/comment/list 无签名 → {"result":1,...} ✅
#
# 所以它们走纯 HTTP，不走浏览器签名路径。
COMMENT_LIST = "/rest/v/photo/comment/list"
COMMENT_SUB_LIST = "/rest/v/photo/comment/sublist"

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


def build_profile_feed_body(user_id: str, pcursor: str = "") -> Dict[str, Any]:
    """构造「用户作品列表」的请求体（**实测字段**，2026-09-30）。

    打开用户主页抓到的真实请求：

        POST /rest/v/profile/feed?__NS_hxfalcon=…
        body: {"user_id":"5372574395","pcursor":"","page":"profile"}

    ⚠️ `page` 是**固定字符串 `"profile"`**（不是页码）；
    翻页用 `pcursor` 游标。
    """
    return {
        "user_id": str(user_id),
        "pcursor": pcursor or "",
        "page": "profile",
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


def _parse_cn_count(v: Any) -> int:
    """解析**中文数量**（2026-10-07 实测发现）。

    ## 为什么需要（实测证据，uid=3xep6p7wbnqcvj6）

        GraphQL 返回：{"fan":"1.3万", "photo":null,
                       "follow":8, "photo_public":176}
        页面显示：     关注 8 / 粉丝 1.3万 / 获赞 5.5万

    ⚠️ **`fan` 是带"万"的中文字符串 `"1.3万"`，不是数字** ——
    `_to_int("1.3万")` 会 `float("1.3万")` 抛异常 → 返回 **0**
    ⇒ 粉丝数在界面上恒显示 0，而我一度以为是"平台不提供"。

    ⇒ 这里必须能解析：`1.3万` / `5.5万` / `12.3亿` / `1,234` 等。
    """
    if v is None:
        return 0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)

    s = str(v).strip()
    if not s:
        return 0
    try:
        # 纯数字（含千分位逗号）
        return int(float(s.replace(",", "")))
    except (ValueError, TypeError):
        pass

    mult = 1
    if s.endswith("万"):
        mult, s = 10_000, s[:-1]
    elif s.endswith("亿"):
        mult, s = 100_000_000, s[:-1]
    elif s.endswith("w") or s.endswith("W"):
        mult, s = 10_000, s[:-1]
    try:
        return int(float(s.replace(",", "")) * mult)
    except (ValueError, TypeError):
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
    """把一条 `users[]` 转成内部结构。

    ## ⚠️ 实测：快手 `/search/user` **不返回任何数字统计**（2026-10-07 抓包核实）

    真实响应（关键词「沈阳」）的**全部字段**只有 7 个：

        headurl / isFollowing / livingInfo / user_id / user_name /
        user_text / verified

    ⇒ 搜出来的博主，`followers/following/total_videos` **必然是 0**。

    ## ⚠️⚠️ **但这不代表快手页面上没有这些数字**（用户截图证明有）

    页面上明明白白显示 关注 8 / 粉丝 1.3万 / 获赞 5.5万，
    而且**未登录也能看到**（用户确认 + 截图右侧有"立即登录"）。

    ### 数字在哪：GraphQL，不是 REST（2026-10-07 实测）

    参考开源项目 MediaCrawler 的 `media_platform/kuaishou/graphql/vision_profile.graphql`，
    实测确认快手博主资料走 **GraphQL**：

        POST https://www.kuaishou.com/graphql
        {
          visionProfile(userId: "<uid>") {
            result
            userProfile {
              ownerCount { fan  photo  follow }   # ← 粉丝 / 作品 / 关注
            }
          }
        }

    **字段实测结论**（GraphQL 的 `Did you mean` 报错是免费的字段字典）：
        · 参数名只能是 `userId`（`id`/`user_id` 都不认）
        · 计数字段**嵌在 `ownerCount` 对象里**：类型 `VisionUserProfileOwnerCount`
        · 真实字段只有三个：`fan` / `photo` / `follow`
          ⇒ **没有 `likedCount`/`获赞`！我猜的 `likedCount` 等全不存在。
        · `VisionUserProfile` 上没有 `fan`/`follow`/`photoCount` 等平铺字段

    ### 为什么我这边测出来是 null

    未登录时 `visionProfile` 返回 `result: 2` 且 `userProfile: null`。
    而页面上仍显示数字 ⇒ **页面不是靠这个未登录的 GraphQL 请求**，
    它用了另一条带登录态/设备指纹的通道。
    ⇒ 要拿到数字，得用**已登录的浏览器上下文**发这个 GraphQL 请求
      （项目的 Patchright 模式正好能提供）。

    ### ⚠️ 我连错三次的记录（防复发）

      ① "快手没有按 id 查资料的接口"（2026-10-01）
         → 部分错：REST 的 `profile/get` 确实存在（userId 在**页面 URL** 上）
      ② "数字只能从加密接口 /s/w/c 取"（2026-10-07 中途）
         → 错：那是**另一路**请求，数字在 **GraphQL**
      ③ "必须有登录态才能取到"（2026-10-07）
         → **对了一半**：未登录页面也显示数字，但那是页面用了别的通道；
            我们要自己发 GraphQL，就必须用登录态上下文。

    ⇒ `stats_available=False` 的含义是**"这个搜索接口不给数字"**，
      不是"平台没有"。显示 0 是谎报，前端据此显示「—」。
    """
    if not isinstance(user, dict):
        return None
    uid = str(user.get("id") or user.get("user_id") or "")
    name = str(user.get("user_name") or user.get("name") or "")
    if not uid and not name:
        return None

    def _first_positive(*keys: str) -> int:
        """取第一个**存在且 > 0** 的候选值（0 视作"没有"而不是"真的是 0"）。"""
        for k in keys:
            v = _to_int(user.get(k))
            if v > 0:
                return v
        return 0

    return {
        "id": uid,
        "name": name,
        "avatar": str(user.get("headurl") or user.get("headUrl") or ""),
        "followers": _first_positive(
            "fan", "followerCount", "fansCount", "followCount",
        ),
        "following": _first_positive(
            "following", "followCount", "followingCount", "follow",
        ),
        "total_videos": _first_positive(
            "photoCount", "workCount", "videoCount", "publicPhotoCount",
            "noteCount", "photo_count", "works",
        ),
        # ⚠️ 2026-10-07：显式告诉前端"这个平台搜不出统计数字"，
        #    让它显示「接口不提供」而不是 0（0 是谎报）。
        "stats_available": False,
        "desc": str(user.get("user_text") or user.get("description") or ""),
        "verified": bool(user.get("verified")),
        "raw": user,
    }
