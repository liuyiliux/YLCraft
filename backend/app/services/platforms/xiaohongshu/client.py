"""
YLCraft — 小红书平台客户端
支持 API 模式和 Patchright 模式切换
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    ClientMode,
    SearchResult,
    NoteDetail,
    SearchParams,
    SearchType,
    UserProfile,
)

logger = logging.getLogger("ylcraft.platforms.xiaohongshu")

# 导入子模块的逻辑函数
from .search import search_via_api
from .search_patchright import search_via_patchright as _search_via_patchright_impl
from .note import get_detail_via_api, get_detail_via_patchright


def search_via_patchright(client, params):
    """Patchright 搜索（页面搜索 → 读 DOM）。

    实现为独立模块 search_patchright.py；此处转发以保持 client.search()
    的既有调用面不变。需要 client._patchright_page（已登录浏览器）。
    """
    return _search_via_patchright_impl(client, params)


# =============================================================================
# 小红书客户端
# =============================================================================

@register_platform("xhs")
@register_platform("xiaohongshu")
class XiaohongshuClient(BasePlatformClient):
    """
    小红书客户端
    支持两种模式：
    1. API 模式：直接调用小红书 Web API（快速，但可能被反爬）
    2. Patchright 模式：使用浏览器自动化（慢，但能绕过反爬）
    """

    def __init__(self, config: ClientConfig):
        super().__init__(config)

    # =========================================================================
    # 实现抽象方法
    # =========================================================================

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头（API 模式用）"""
        headers = {
            "User-Agent": self.config.user_agent or self._get_default_user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.xiaohongshu.com/",
            "Origin": "https://www.xiaohongshu.com",
            "X-Requested-With": "XMLHttpRequest",
        }

        # Cookie 规范化统一由基类 header_cookie() 负责（不在此处各平台各写一遍）
        cookie = self.header_cookie()
        if cookie:
            headers["Cookie"] = cookie

        return headers

    def _get_default_user_agent(self) -> str:
        """获取默认 User-Agent"""
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def _get_platform_domain(self) -> str:
        """获取平台域名（用于设置 Cookie）"""
        return ".xiaohongshu.com"

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """
        搜索笔记
        """
        if self.config.mode == ClientMode.PATCHRIGHT:
            return await search_via_patchright(self, params)
        else:
            return await search_via_api(self, params)

    async def get_detail(self, item_id: str, **kwargs) -> Optional[NoteDetail]:
        """
        获取笔记详情。

        ## 两条路径（2026-09-29 更新）

        · **api（默认，纯 HTTP）**：`POST /api/sns/web/v1/feed` + xhshow 签名。
          **端点一直活着**，之前"已失效"的判断是错的（详见 note.py）。
          更快、字段更全（原图 / 多清晰度 / 话题 / IP 属地）。
        · patchright（浏览器）：保留作为兜底。

        kwargs 必带：
          · `xsec_token` —— 详情接口**必需**（实测缺失返回 HTTP 461），
            从搜索结果或笔记 URL 的 `?xsec_token=` 里取。
          · `url` —— 可选，没单独传 token 时从中提取。
        """
        if self.config.mode == ClientMode.PATCHRIGHT:
            return await get_detail_via_patchright(self, item_id, **kwargs)
        # ⚠️ 必须把 kwargs 传下去 —— 原来漏了，导致 `xsec_token`
        # 到不了 `get_detail_via_api`，详情报"缺少 token"（实测踩过）。
        return await get_detail_via_api(self, item_id, **kwargs)

    # =========================================================================
    # 用户（搜索 / 资料 / 作品列表）——2026-09-27 实测实现
    # =========================================================================

    async def search_users(
        self, keyword: str, max_results: int = 20
    ) -> List[UserProfile]:
        """按关键词搜用户。

        ⚠️ 是 **POST + JSON body**（不像抖音是 GET query），
        且必须带 `search_id`（由 signing.get_search_id() 生成）。
        实测「美食」→ 20 个用户。
        """
        from .user import search_users as _impl

        return await _impl(self, keyword, max_results)

    async def get_self_profile(self) -> Optional[UserProfile]:
        """查**自己**的资料（做「我的数据」用）。

        两步走：`v2/user/me` 拿基础资料（**无粉丝数**）→
        用 user_id 调 `user/otherinfo` 补统计。
        实测：昵称=逸流AI / 粉丝=195 / 关注=2 / 获赞与收藏=2930 / 作品=73。
        """
        from .user import get_self_profile as _impl

        return await _impl(self)

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """查**他人**资料（GET `user/otherinfo` + 签名）。

        实测（逸流AI）：昵称/red_id/简介/ip_location；
        粉丝数在 `interactions` 数组里（不在 basic_info）。
        """
        from .user import get_user_profile as _impl

        return await _impl(self, user_id)

    async def get_user_notes(
        self, user_id: str, max_results: int = 20
    ) -> List[SearchResult]:
        """取用户作品列表（GET `user_posted` + 签名，cursor 分页）。

        实测（逸流AI）：20 条 + has_more + cursor。

        注意：小红书叫 `get_user_notes`（历史命名），抖音叫 `get_user_videos`。
        统一路由 `/api/v1/users/videos` 调的是后者，所以下面留一个别名，
        避免"两个平台方法名不一致"导致运行时 AttributeError
        （实测踩过：路由报 `object has no attribute 'get_user_videos'`）。
        """
        from .user import get_user_videos as _impl

        return await _impl(self, user_id, max_results)

    # 与抖音对齐的别名（统一路由用这个名字）
    async def get_user_videos(
        self, user_id: str, max_results: int = 20
    ) -> List[SearchResult]:
        """`get_user_notes` 的别名（与抖音命名对齐）。"""
        return await self.get_user_notes(user_id, max_results)

    async def get_comments(self, item_id: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """获取评论（可选）"""
        # TODO: 实现获取评论
        raise NotImplementedError(f"[{self.config.platform}] get_comments not implemented")
