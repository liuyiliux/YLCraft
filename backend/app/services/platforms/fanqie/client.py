"""
YLCraft — 番茄小说作家后台客户端

定位：番茄作家后台的 API 数据采集 + 发布客户端，对齐 B站 `BilibiliClient`
（`BasePlatformClient` 子类 + `@register_platform("fanqie")`）。

已验证接口（纯 cookie，无需逆向签名）：
  - save_draft / cover_article/v0/   存草稿（章节正文）
  - get_hot_list  / douyin_hot_list/v0/  热门故事（灵感）

设计要点：
  - 所有请求经 `_call()` 统一出口：校验 HTTP 200、解析 JSON、按 code 分类异常。
  - cookie 走 HTTP `Cookie` 头（字符串），支持 Netscape / 原始两种来源。
  - 不在此处建书 / 建卷 / 建章节——那些仍在番茄 Web 端完成。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..base import BasePlatformClient, register_platform
from ..types import ClientConfig, ClientMode, SearchResult, NoteDetail, UserProfile, SeriesInfo, SearchParams
from .apis import (
    BASE_URL,
    COVER_ARTICLE,
    DOUYIN_HOT_LIST,
    BOOK_LIST,
    BOOK_COMMON,
    ACCOUNT_INFO,
    CHAPTER_LIST,
    VOLUME_LIST,
    DEFAULT_AID,
    DEFAULT_APP_NAME,
    COVER_MS_TOKEN,
    COVER_A_BOGUS,
    HOT_MS_TOKEN,
    HOT_A_BOGUS,
    X_SECSDK_CSRF_TOKEN,
)
from .utils import (
    classify_fanqie_error,
    CookieExpiredError,
    FanqieError,
    markdown_to_fanqie_html,
)

logger = logging.getLogger("ylcraft.platforms.fanqie")


@register_platform("fanqie")
class FanqieClient(BasePlatformClient):
    """
    番茄小说作家后台客户端。

    用法：
        config = ClientConfig(platform="fanqie", mode=ClientMode.API, cookie=<番茄cookie>)
        async with FanqieClient(config) as client:
            await client.save_draft(book_id=..., item_id=..., title=..., content_html=...)
            hot = await client.get_hot_list()
    """

    def __init__(self, config: ClientConfig):
        super().__init__(config)
        # 作家标识 / 当前操作的 book_id（用于构造 referer，可选）
        self.writer_id: str = ""
        self._book_id: str = ""

    # =========================================================================
    # 抽象方法实现
    # =========================================================================

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "origin": "https://fanqienovel.com",
            "referer": self._make_referer(),
            "user-agent": self._get_default_user_agent(),
        }
        # Cookie 规范化统一由基类 header_cookie() 负责（不在此处各平台各写一遍）
        cookie = self.header_cookie()
        if cookie:
            headers["Cookie"] = cookie
        # x-secsdk-csrf-token 为可选反爬头；缺失时多数接口仍可访问
        if X_SECSDK_CSRF_TOKEN:
            headers["x-secsdk-csrf-token"] = X_SECSDK_CSRF_TOKEN
        return headers

    def _get_default_user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        )

    def _get_platform_domain(self) -> str:
        return ".fanqienovel.com"

    def _make_referer(self) -> str:
        """构造 Referer。带 writer_id/book_id 时更贴近真实浏览器请求。"""
        if self.writer_id and self._book_id:
            return (
                f"https://fanqienovel.com/main/writer/{self.writer_id}"
                f"/publish/{self._book_id}?enter_from=newchapter_0"
            )
        if self.writer_id:
            return f"https://fanqienovel.com/main/writer/{self.writer_id}"
        return "https://fanqienovel.com/main/writer/"

    # search / get_detail 在番茄场景下暂无通用语义，显式声明未实现
    async def search(self, params: SearchParams) -> List[SearchResult]:  # noqa: D401
        raise NotImplementedError("[fanqie] search 暂未实现（番茄为章节式发布，无通用搜索）")

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:  # noqa: D401
        raise NotImplementedError("[fanqie] get_detail 暂未实现")

    # =========================================================================
    # 统一请求出口（带错误分类）
    # =========================================================================

    async def _call(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        统一请求出口：
          1. 调基类 request（HTTP 层，含重试/JSON 解析）
          2. 校验返回结构，按 code 分类异常

        Args:
            method: "GET" / "POST"
            path:   相对路径（不含 BASE_URL）
            params: query 参数（会并入默认 aid/app_name）
            data:   form 表单体（POST 用）

        Returns:
            解析后的响应 dict（含 code / message / data）

        Raises:
            CookieExpiredError / ParamError / RiskControlError / FanqieError
        """
        url = f"{BASE_URL}{path}"
        q = {"aid": DEFAULT_AID, "app_name": DEFAULT_APP_NAME}
        if params:
            q.update(params)

        try:
            resp = await self.request(method, url, params=q, data=data)
        except httpx.HTTPStatusError as e:
            raise FanqieError(f"番茄接口 HTTP 错误：{e}") from e

        return self._check_response(resp)

    def _check_response(self, resp: Any) -> Dict[str, Any]:
        """
        校验响应并分类异常。

        响应约定：JSON dict，含 `code`（0 为成功）、`message`、`data`。
        若返回的是 HTML（登录页重定向 / cookie 失效），`resp` 会是
        {'text': ..., 'status': 200} 形态，无 code → 视为登录失效。
        """
        if not isinstance(resp, dict):
            raise FanqieError(f"番茄返回非预期结构：{type(resp)}")

        # 登录页重定向：基类在 JSON 解析失败时返回 {'text': html}
        if "text" in resp and "code" not in resp:
            raise CookieExpiredError("番茄返回登录页（cookie 失效或缺失），请重新登录并刷新 cookie")

        code = resp.get("code", -1)
        message = resp.get("message") or resp.get("msg") or ""

        if code == 0:
            return resp

        raise classify_fanqie_error(code, message)

    # =========================================================================
    # 发布：存草稿（已验证）
    # =========================================================================

    async def save_draft(
        self,
        *,
        book_id: str,
        item_id: str,
        title: str,
        content_html: str,
        volume_name: str,
        volume_id: str,
        content_type: int = 1,
    ) -> Dict[str, Any]:
        """
        存草稿（章节正文）。对应 cover_article/v0/ POST。

        注意：调用前，**章节必须在番茄 Web 端已建好**（拿到 item_id）。
        本方法只推送正文，不创建章节。

        Args:
            book_id:      书籍 ID（番茄 Web 端获取）
            item_id:      章节 ID（番茄 Web 端「新建章节」后获取）
            title:        章节标题
            content_html: 正文 HTML（用 <p> 包段落；可先用 markdown_to_fanqie_html 转换）
            volume_name:  卷名（如「第一卷：默认」）
            volume_id:    卷 ID
            content_type: 内容类型，默认 1

        Returns:
            响应 data 字典（含 latest_version 等）

        Raises:
            CookieExpiredError / ParamError / RiskControlError / FanqieError
        """
        self._book_id = str(book_id)

        payload = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "book_id": str(book_id),
            "item_id": str(item_id),
            "title": title,
            "content": content_html,
            "volume_name": volume_name,
            "volume_id": str(volume_id),
            "content_type": str(content_type),
        }
        query = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "msToken": COVER_MS_TOKEN,
            "a_bogus": COVER_A_BOGUS,
        }
        resp = await self._call("POST", COVER_ARTICLE, params=query, data=payload)
        data = resp.get("data", {}) or {}
        version = data.get("latest_version")
        logger.info(f"[fanqie] save_draft ok: book={book_id} item={item_id} title={title!r} latest_version={version}")
        return data

    async def save_draft_from_markdown(
        self,
        *,
        book_id: str,
        item_id: str,
        title: str,
        content_markdown: str,
        volume_name: str,
        volume_id: str,
        content_type: int = 1,
    ) -> Dict[str, Any]:
        """
        与 save_draft 相同，但接受 Markdown 正文（内部转换为番茄 HTML）。
        """
        content_html = markdown_to_fanqie_html(content_markdown)
        return await self.save_draft(
            book_id=book_id,
            item_id=item_id,
            title=title,
            content_html=content_html,
            volume_name=volume_name,
            volume_id=volume_id,
            content_type=content_type,
        )

    # =========================================================================
    # 灵感：热门故事（已验证）
    # =========================================================================

    async def get_hot_list(self, hot_type: int = 0) -> Dict[str, Any]:
        """
        获取热门故事 / 开书灵感列表（只读，不改任何数据）。
        对应 douyin_hot_list/v0/ GET。

        Args:
            hot_type: 类型，默认 0

        Returns:
            响应 data 字典（含若干 item 列表，title/name 为标题字段）
        """
        query = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "type": str(hot_type),
            "msToken": HOT_MS_TOKEN,
            "a_bogus": HOT_A_BOGUS,
        }
        resp = await self._call("GET", DOUYIN_HOT_LIST, params=query)
        return resp.get("data", {}) or {}

    # =========================================================================
    # 占位：我的数据（Phase 3 补齐字段解析）
    # =========================================================================

    async def get_my_books(self, page: int = 1, size: int = 20) -> Dict[str, Any]:
        """
        我的书籍列表（已验证：GET /api/author/stats/book_list/v0/，code:0）。

        番茄真实分页参数为 `page_count`（每页数量，-1 表示取全部）/
        `page_index`（0-based）；此处保持 page/size 对外友好签名，
        内部转换为真实参数。

        Returns:
            data 字典，含 `item_list[]`：每本书字段
            book_id / book_name / book_status / book_status_desc /
            word_count / chapter_count / category / cover_url(thumb_url)。
            注意：未签约/未推荐的书可能不出现在此列表（实测 item_list:[]），
            此时需用 get_book_stats 按 book_id 单本查。
        """
        query = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "page_count": str(size),
            "page_index": str(page - 1),
            "image_fmt_list": "160x214",
        }
        resp = await self._call("GET", BOOK_LIST, params=query)
        return resp.get("data", {}) or {}

    async def get_book_stats(self, book_id: str, stats_type: int = 1) -> Dict[str, Any]:
        """
        单本书统计（已验证：GET /api/author/stats/book_common_v1/v0/，code:0）。

        `stats_type` 对应作家后台「数据中心」的不同 Tab：
          1 = 基础数据（阅读/在读/追更/评分等，本方法默认）
          截图提到的「质量分析」「流量构成」可能使用其它 stats_type 值，
          待 Phase 3 抓包确认后扩展（已预留参数）。

        Returns:
            data 字典，含字段（实测示例）：
            book_name / is_publish / read_completion_rate(完读率) /
            pursue_read_rate(追更率) / reader_uv_daily(日阅读UV) /
            thumb_url_list[{main_url,backup_url}] / main_intro /
            authorize_type 等。未推荐分发时多数指标为 "0"/"---"。
        """
        query = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "book_id": str(book_id),
            "stats_type": str(stats_type),
        }
        resp = await self._call("GET", BOOK_COMMON, params=query)
        return resp.get("data", {}) or {}

    # =========================================================================
    # E 组：2026-09-25 抓包确认的真实实现
    # =========================================================================

    async def get_my_profile(self) -> Dict[str, Any]:
        """
        作家资料（真实端点：GET /api/author/account/info/v0/，2026-09-25 抓包确认）。

        ⚠️ 与早期设计的差异：本接口返回的是**作家名/简介/头像/积分/等级**，
        **不返回「总阅读」「总粉丝」**——那两个属作品级或数据中心指标。
        如需流量指标请用 `get_book_stats(book_id, stats_type=...)`。

        Returns:
            data 字典，含字段（实测）：
            author_name / description / avatar_url / point / point_detail[] /
            author_level_id / verify_status / is_auth / is_ban 等。

        ⚠️ 响应含 `phone_number` / `identity_name_mask` / `identity_code_mask`
        等个人敏感字段。本方法**原样透传**供界面展示，调用方**不得**将其落库、
        写日志或送入模型上下文（与 cookie 同级的隐私边界）。
        """
        query = {"aid": DEFAULT_AID, "app_name": DEFAULT_APP_NAME}
        resp = await self._call("GET", ACCOUNT_INFO, params=query)
        return resp.get("data", {}) or {}

    async def get_book_volumes(self, book_id: str) -> Dict[str, Any]:
        """
        卷列表（真实端点：GET /api/author/volume/volume_list/v1，2026-09-25 抓包确认）。

        章节按卷组织，发布到已有章节时需要 `volume_id`，故与 `get_book_chapters` 配套。
        """
        query = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "book_id": str(book_id),
        }
        resp = await self._call("GET", VOLUME_LIST, params=query)
        return resp.get("data", {}) or {}

    async def get_book_chapters(
        self,
        book_id: str,
        volume_id: str = "",
        page: int = 1,
        size: int = 50,
        status: int = 0,
    ) -> Dict[str, Any]:
        """
        书籍章节列表（真实端点：GET /api/author/chapter/chapter_list/v1，2026-09-25 抓包确认）。

        这是把「手动粘贴 item_id」换成**自动映射**的关键接口：返回的 `item_id`
        就是发布目标章节 ID。

        ⚠️ 分页是 **0-based**（`page_index` 从 0 开始），与对外 `page`（1 起）
        不同，内部已做转换——与 `get_my_books` 的约定保持一致。

        Args:
            book_id: 书籍 ID
            volume_id: 卷 ID；留空时番茄按书本整体返回
            page: 对外页码，1 起
            size: 每页条数（`page_count`）
            status: 章节状态过滤，0 表示不筛

        Returns:
            data 字典，含 `item_list[]`，每项字段（实测）：
            item_id（**发布目标 ID**）/ volume_id / index（1 起章序）/
            title / word_number / article_status（2=已发布）/
            can_delete / cant_modify_reason / create_time。
            外层另有 book_status / creation_status 等书籍级字段。

        注意：`index` 是章序，可据它与项目内的 `chapter_number` 对齐；
        但**发布前仍应人工确认**——映射错章节会写到错误的位置。
        """
        query: Dict[str, Any] = {
            "aid": DEFAULT_AID,
            "app_name": DEFAULT_APP_NAME,
            "book_id": str(book_id),
            "page_index": str(max(page - 1, 0)),
            "page_count": str(size),
            "status": str(status),
            "must_have_correction_feedback": "0",
            "need_correction_feedback_num": "1",
            "sort": "",
        }
        if volume_id:
            query["volume_id"] = str(volume_id)
        resp = await self._call("GET", CHAPTER_LIST, params=query)
        return resp.get("data", {}) or {}
