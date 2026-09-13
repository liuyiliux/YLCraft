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
)

logger = logging.getLogger("ylcraft.platforms.xiaohongshu")

# 导入子模块的逻辑函数
from .search import search_via_api, search_via_patchright
from .note import get_detail_via_api, get_detail_via_patchright


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
        # 规范化后的 Cookie 头字符串（懒求值，见 _header_cookie()）
        self._header_cookie_cache: str | None = None

    # =========================================================================
    # 实现抽象方法
    # =========================================================================

    def _header_cookie(self) -> str:
        """返回**可直接放进 HTTP 头**的 Cookie 字符串（`k=v; k2=v2`）。

        背景：`PlatformConnection.cookie_content` 是 **Netscape 文件格式**（含
        `# Netscape HTTP Cookie File` 注释头、字段以制表符分隔）。直接赋给 `Cookie`
        头会被 httpx 拒绝（`Illegal header value`，头值不允许换行/制表符），**请求根本
        发不出去**——表现为搜索静默返回空。

        B 站客户端曾因同一写法导致 API 模式全量请求失败（2026-09-13 修复）；番茄客户端
        `_build_headers` 一直是 `normalize_cookie(...)` 所以没受影响。此处对齐到同一做法，
        使客户端对调用方传入的格式不再敏感（Netscape / `k=v` / JSON 皆可）。
        """
        if self._header_cookie_cache is None:
            raw = self.config.cookie or ""
            if raw:
                try:
                    from app.services.cookies.manager import CookieManager

                    raw = CookieManager().extract_raw(raw) or raw
                except Exception as exc:  # noqa: BLE001 - 规范化失败不得阻断请求
                    self._log(f"Cookie 规范化失败，回退使用原文：{exc}", "warning")
            self._header_cookie_cache = raw
        return self._header_cookie_cache

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

        cookie = self._header_cookie()
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
        获取笔记详情
        """
        if self.config.mode == ClientMode.PATCHRIGHT:
            return await get_detail_via_patchright(self, item_id)
        else:
            return await get_detail_via_api(self, item_id)

    # =========================================================================
    # 可选方法（子类可选实现）
    # =========================================================================

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """获取用户主页（可选）"""
        # TODO: 实现获取用户主页
        raise NotImplementedError(f"[{self.config.platform}] get_user_profile not implemented")

    async def get_user_notes(self, user_id: str, max_results: int = 20) -> List[SearchResult]:
        """获取用户发布的笔记（可选）"""
        # TODO: 实现获取用户笔记列表
        raise NotImplementedError(f"[{self.config.platform}] get_user_notes not implemented")

    async def get_comments(self, item_id: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """获取评论（可选）"""
        # TODO: 实现获取评论
        raise NotImplementedError(f"[{self.config.platform}] get_comments not implemented")
