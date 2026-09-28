"""YLCraft — 微博客户端。

## 实测结论（2026-09-27，在真实浏览器内验证）

    GET https://m.weibo.cn/api/container/getIndex
        ?containerid=100103type=1&q=美食&page_type=searchall&page=1
    → {"ok":1,"data":{"cards":[{"card_type":9,"mblog":{...}}],
                      "cardlistInfo":{"total":739}}}

## ⚠️ 必须登录（与抖音不同）

不带 Cookie 时：HTTP 432 / 重定向到 Sina Visitor System /
`{"ok":-100,"url":".../sso/signin..."}`。

**`ok == -100` 是"未登录"，不是"没搜到结果"** ——
把它报成"关键词无结果"会把人带偏，所以这里显式区分。

## 图片与视频（实测字段，不用猜后缀）

`mblog.original_pic` 直接给**原图 URL**；
视频在 `mblog.page_info`（`type=="video"`）：

    media_info.stream_url / stream_url_hd
    urls.mp4_720p_mp4 / mp4_hd_mp4 / mp4_ld_mp4
    page_pic.url（封面）/ duration（秒）

所以不需要像某些项目那样拼 `/orj360/` `/mw690/` 后缀。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    ClientMode,
    NoteDetail,
    SearchParams,
    SearchResult,
    UserProfile,
)
from .apis import (
    MOBILE_HOST,
)

logger = logging.getLogger("ylcraft.platforms.weibo")

# 移动端 UA（微博移动 API 对桌面 UA 不友好）
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class WeiboLoginRequiredError(RuntimeError):
    """微博未登录（ok=-100）。

    与"没有搜索结果"必须区分 —— 前者要用户去补登录态，
    后者才是关键词真没内容。
    """


@register_platform("weibo")
# 别名 `wb`：**前端「内容搜索」页的平台列表用的就是 `wb`**
# （`PLATFORMS` 里 `{ value: 'wb', label: '微博' }`）。
# 不注册这个别名，用户在界面上选微博会直接报
# `ValueError: Unsupported platform: wb`（实测踩过）。
@register_platform("wb")
class WeiboClient(BasePlatformClient):
    """微博客户端（搜索 / 详情 / 图文与视频解析）。

    用法：
        config = ClientConfig(platform="weibo", mode=ClientMode.API, cookie=<微博cookie>)
        async with WeiboClient(config) as client:
            results = await client.search(SearchParams(keyword="美食"))
    """

    # =========================================================================
    # 基类契约
    # =========================================================================

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.config.user_agent or MOBILE_UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{MOBILE_HOST}/",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _get_default_user_agent(self) -> str:
        return MOBILE_UA

    def _get_platform_domain(self) -> str:
        return ".weibo.cn"

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """按关键词搜微博。

        ## 必须走浏览器（实测 2026-09-27）

        httpx 直连**全部失败**（HTTP 432 / ok=-100），原因是微博注册了
        **Service Worker**（`bsk debug` 捕获显示 `from_service_worker=True`），
        由它注入 httpx 无法复现的上下文。补 Cookie/请求头/HTTP2 都无效。

        而真实浏览器里（**未登录**）同一 URL 返回 `ok=1, total=870`。

        所以这里转交 `search_patchright`，与小红书同一套 SessionPool。
        区别在原因：小红书需要**签名**，微博需要 **Service Worker 上下文**。

        ## mode 的影响

        `mode=API` 时仍会走浏览器 —— 因为 API 路径对微博不可用。
        这是"平台差异"而非配置错误，所以在日志里说明一次。
        """
        from .search_patchright import search_via_patchright

        if self.config.mode == ClientMode.API:
            logger.info(
                "[weibo] 该平台 API 直连不可用（Service Worker 依赖），"
                "自动转浏览器路径"
            )
        return await search_via_patchright(
            params,
            conn_key=self.config.conn_id or "",
            page=max(1, int(getattr(params, "page", 1) or 1)),
        )

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """取微博详情。

        三条路径：
          1. 调用方带 `raw`（搜索时的 mblog）→ 直接解析，零请求
          2. 否则按 id 打开详情页解析（HTML 里的 `$render_data`）
          3. 都拿不到 → 抛可读错误

        优先走 1：搜索结果的 mblog 已含详情所需的一切
        （正文/作者/图片/视频/统计）。
        """
        raw = (kwargs or {}).get("raw")
        if isinstance(raw, dict) and raw.get("id"):
            detail = parse_mblog_detail(raw)
            if detail is not None:
                return detail

        # 2) 打开详情页解析
        detail = await self._fetch_detail_by_page(item_id)
        if detail is not None:
            return detail

        raise RuntimeError(
            f"[weibo] 未能获取微博详情（id={item_id}）。"
            "可能原因：微博已删除、仅粉丝可见，或登录态失效。"
        )

    # =========================================================================
    # 统一请求出口
    # =========================================================================

    async def _call(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GET 微博 API 并**显式区分登录态问题**。"""
        if self._http_client is None:
            await self._init_http_client()
        url = f"{MOBILE_HOST}{path}"
        resp = await self._http_client.get(url, params=params or {})

        if resp.status_code == 432:
            raise WeiboLoginRequiredError(
                "[weibo] 请求被微博拒绝（HTTP 432）。"
                "微博要求登录态：请在「账号中心」用浏览器方式保存微博 Cookie。"
            )
        resp.raise_for_status()

        text = resp.text or ""
        if not text.strip():
            raise WeiboLoginRequiredError(
                f"[weibo] 请求 {path} 返回空响应体。"
                "微博在未登录时会这样拒绝，请检查登录态。"
            )
        if not text.lstrip().startswith("{"):
            # 被重定向到访客/登录页（HTML）
            raise WeiboLoginRequiredError(
                f"[weibo] 请求 {path} 返回的不是 JSON（可能被重定向到 "
                "Sina Visitor System）。请在「账号中心」重新保存微博登录态。"
            )

        data = resp.json()
        ok = data.get("ok")
        if ok == -100:
            raise WeiboLoginRequiredError(
                "[weibo] 微博返回 ok=-100（未登录）。"
                f"响应里的登录地址：{data.get('url', '')[:80]}。"
                "**这不是「没有搜索结果」**——请在「账号中心」保存微博 Cookie。"
            )
        return data

    # =========================================================================
    # 解析
    # =========================================================================

    @staticmethod
    def _extract_mblogs(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从响应里取出微博正文（card_type=9）。

        搜索结果的 cards 里混着 card_type=9（正文，有 mblog）
        与 11（广告/运营），只取前者。
        """
        cards = (data.get("data") or {}).get("cards") or []
        out: List[Dict[str, Any]] = []
        for card in cards:
            if not isinstance(card, dict):
                continue
            if card.get("card_type") != CARD_TYPE_MBLOG:
                continue
            mb = card.get("mblog")
            if isinstance(mb, dict) and mb.get("id"):
                out.append(mb)
        return out

    async def _fetch_detail_by_page(self, item_id: str) -> Optional[NoteDetail]:
        """按 id 打开详情页，解析 HTML 里的 `$render_data`。

        来源：MediaCrawler `get_note_info_by_id`（用正则从 HTML 提取）。

        ⚠️ 正则匹配 `var $render_data = ([...])[0]` —— 结构与站点版本
        相关，失效时这里返回 None（由调用方给可读错误），不静默返回空详情。
        """
        if self._http_client is None:
            await self._init_http_client()
        url = f"{MOBILE_HOST}/detail/{item_id}"
        resp = await self._http_client.get(url)
        if resp.status_code != 200:
            logger.warning("[weibo] 详情页返回 HTTP %s", resp.status_code)
            return None

        m = re.search(r"var \$render_data = (\[.*?\])\[0\]", resp.text or "", re.DOTALL)
        if not m:
            logger.warning("[weibo] 详情页未找到 $render_data（id=%s）", item_id)
            return None
        try:
            import json as _json

            payload = _json.loads(m.group(1))
            status = payload[0].get("status") if payload else None
        except Exception as exc:
            logger.warning("[weibo] $render_data 解析失败：%s", exc)
            return None

        if not isinstance(status, dict):
            return None
        return parse_mblog_detail(status)


# =============================================================================
# 解析函数（模块级，便于测试）
# =============================================================================

def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _first_url(value: Any) -> str:
    """微博的图片/封面字段可能是 str 或 {url: ...}。"""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("url") or ""
    return ""


def parse_mblog(mb: Dict[str, Any]) -> Optional[SearchResult]:
    """把 mblog 转成统一 SearchResult。

    实测字段（70+ 个里取需要的）：
        id / mid / bid, text, created_at, user{...},
        original_pic / bmiddle_pic / thumbnail_pic, pics[],
        attitudes_count / comments_count / reposts_count, page_info
    """
    if not isinstance(mb, dict):
        return None
    mid = str(mb.get("id") or mb.get("mid") or "")
    if not mid:
        return None

    user = mb.get("user") or {}
    text_html = mb.get("text") or ""
    text = _strip_html(text_html)

    # 封面：优先第一张图的原图，其次视频封面
    cover = _first_url(mb.get("original_pic")) or _first_url(mb.get("bmiddle_pic"))
    images = _extract_images(mb)
    if not cover and images:
        cover = images[0]
    page_info = mb.get("page_info") or {}
    if not cover and isinstance(page_info, dict):
        cover = _first_url((page_info.get("page_pic") or {}))

    is_video = isinstance(page_info, dict) and page_info.get("type") == "video"
    video_url = _extract_video_url(mb) if is_video else ""

    # ⚠️ SearchResult **没有** images / video 字段（那些在 NoteDetail 里）。
    # 所以图片列表与视频地址放进 raw_data，供上层（crawler / 详情）读取。
    # 与抖音的做法一致 —— 不为了塞字段去改公共类型。
    raw = dict(mb)
    raw["_images"] = images
    raw["_video_url"] = video_url

    return SearchResult(
        id=mid,
        title=text[:80],          # 微博没有独立标题，用正文首段
        desc=text,
        author=user.get("screen_name") or "",
        author_id=str(user.get("id") or ""),
        cover=cover,
        url=f"{MOBILE_HOST}/detail/{mid}",
        platform="weibo",
        type="video" if is_video else "note",
        likes=_to_int(mb.get("attitudes_count")),
        comments=_to_int(mb.get("comments_count")),
        shares=_to_int(mb.get("reposts_count")),
        create_time=mb.get("created_at") or "",
        raw_data=raw,
    )


def parse_mblog_detail(mb: Dict[str, Any]) -> Optional[NoteDetail]:
    """把 mblog 转成统一 NoteDetail。"""
    if not isinstance(mb, dict):
        return None
    mid = str(mb.get("id") or mb.get("mid") or "")
    if not mid:
        return None

    user = mb.get("user") or {}
    text = _strip_html(mb.get("text") or "")
    images = _extract_images(mb)
    video = _extract_video_url(mb)
    page_info = mb.get("page_info") or {}
    cover = _first_url(mb.get("original_pic")) or _first_url(mb.get("bmiddle_pic"))
    if not cover and isinstance(page_info, dict):
        cover = _first_url((page_info.get("page_pic") or {}))
    if not cover and images:
        cover = images[0]

    duration = 0
    if isinstance(page_info, dict):
        try:
            duration = int(float(page_info.get("duration") or 0))
        except (TypeError, ValueError):
            duration = 0

    return NoteDetail(
        id=mid,
        title=text[:80],
        desc=text,
        author=user.get("screen_name") or "",
        author_id=str(user.get("id") or ""),
        platform="weibo",
        type="video" if video else "note",
        images=images,
        video=video,
        video_cover=cover,
        duration=duration,
        likes=_to_int(mb.get("attitudes_count")),
        comments=_to_int(mb.get("comments_count")),
        shares=_to_int(mb.get("reposts_count")),
        create_time=mb.get("created_at") or "",
        raw_data=mb,
    )


def _extract_images(mb: Dict[str, Any]) -> List[str]:
    """取微博的图片列表（**尽量取原图**）。

    ## 实测结构（2026-09-27）

        pics[0] = {
            "url":   ".../orj360/<pid>.jpg",     # 缩略图 360px
            "size":  "orj360",
            "large": {"url": ".../mw2000/<pid>.jpg",   # 2048 宽
                      "size": "large",
                      "geo": {...}},
        }
        original_pic = ".../large/<pid>.jpg"   # 真·原图（**只有第一张**）

    ## 关键规律

    `large.url` 的路径段是 `/mw2000/`，原图是 `/large/`，
    **但文件名（pid）完全相同** —— 所以每张图都能推导出原图 URL：

        https://wx4.sinaimg.cn/mw2000/<pid>.jpg   →   .../large/<pid>.jpg

    实测验证（2026-09-27）：`large` 版 1.88MB vs `mw2000` 版 962KB，
    两张都 HTTP 200 可直连下载（**下载不需要 Cookie**）。

    所以这里**优先推导原图**，推导不出来才退到 `large.url`。
    """
    out: List[str] = []
    for pic in (mb.get("pics") or []):
        if not isinstance(pic, dict):
            continue
        large = pic.get("large") or {}
        url = _first_url(large) or pic.get("url") or ""
        if not url:
            continue
        out.append(_to_original_url(url))

    if not out:
        single = _first_url(mb.get("original_pic"))
        if single:
            out.append(single)
    return out


# 微博图床的尺寸路径段 → 原图路径段
_WEIBO_SIZE_SEGMENTS = ("/mw2000/", "/mw690/", "/bmiddle/", "/orj360/", "/orj480/",
                        "/thumbnail/", "/small/", "/square/", "/thumb150/")


def _to_original_url(url: str) -> str:
    """把微博图床 URL 转成原图 URL（把尺寸段换成 `/large/`）。

    实测：`mw2000` 与 `large` 的文件名（pid）相同，只有路径段不同。
    已经是 `/large/` 或 `/original/` 的原样返回。
    """
    if not url:
        return url
    for seg in _WEIBO_SIZE_SEGMENTS:
        if seg in url:
            return url.replace(seg, "/large/", 1)
    return url


def _extract_video_url(mb: Dict[str, Any]) -> str:
    """取视频直链（优先最高清晰度）。

    实测字段（page_info.type == "video"）：
        page_info.urls.mp4_720p_mp4 / mp4_hd_mp4 / mp4_ld_mp4
        page_info.media_info.stream_url / stream_url_hd
    """
    page_info = mb.get("page_info") or {}
    if not isinstance(page_info, dict):
        return ""

    urls = page_info.get("urls") or {}
    if isinstance(urls, dict):
        for key in ("mp4_720p_mp4", "mp4_hd_mp4", "mp4_ld_mp4"):
            v = urls.get(key)
            if isinstance(v, str) and v:
                return v

    media = page_info.get("media_info") or {}
    if isinstance(media, dict):
        for key in ("stream_url_hd", "stream_url"):
            v = media.get(key)
            if isinstance(v, str) and v:
                return v
    return ""


def _strip_html(html: str) -> str:
    """去掉微博正文里的 HTML 标签（正文是 `<a>` 包裹的富文本）。"""
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    # 常见实体
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(a, b)
    return text.strip()
