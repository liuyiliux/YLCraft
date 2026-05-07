"""
YLCraft — 微博连接器

功能：
- Cookie 认证 + OAuth 2.0 认证（参考任务 #43 的 OAuth 支持）
- 发布微博（文字/图片/视频）
- 删除微博
- 获取微博详情和指标

API 参考：
- 微博开放平台：https://open.weibo.com/
- API 文档：https://open.weibo.com/wiki/API
"""

from __future__ import annotations

import asyncio
import logging
import time
import json
from typing import Optional, Any, List
from datetime import datetime

import httpx

from app.connectors.base import (
    ISocialMediaConnector,
    ContentType,
    MediaFormat,
    PostContent,
    PostResult,
    AccountInfo,
    ContentMetrics,
)
from app.connectors.mixins import AuthMixin, CookieManagerMixin, RateLimitMixin
from app.connectors import register_social_connector

logger = logging.getLogger("ylcraft.connectors.weibo")


@register_social_connector(
    platform_id="weibo",
    supported_content_types=[
        ContentType.TEXT,
        ContentType.IMAGE,
        ContentType.VIDEO,
    ],
    supported_media_formats=[
        MediaFormat.JPG,
        MediaFormat.PNG,
        MediaFormat.MP4,
    ],
    auth_types=["cookie", "oauth2"],
    description="微博 - 社交媒体平台",
    # OAuth 2.0 配置（参考任务 #43）
    oauth_auth_url="https://api.weibo.com/oauth2/authorize",
    oauth_token_url="https://api.weibo.com/oauth2/access_token",
    oauth_scope="",  # 微博的 scope 可根据需要设置
    oauth_redirect_uri="",  # 需要用户在开放平台配置
)
class WeiboConnector(ISocialMediaConnector, AuthMixin, CookieManagerMixin, RateLimitMixin):
    """
    微博连接器

    功能：
    - Cookie 认证（通过 base64 编码的 cookie）
    - OAuth 2.0 认证（参考任务 #43 实现）
    - 发布微博（文字/图片/视频）
    - 删除微博
    - 获取微博详情和指标

    使用方式：
        # Cookie 认证
        connector = WeiboConnector({"cookie": "..."})
        await connector.initialize()
        result = await connector.publish(content)

        # OAuth 认证（需要先获取 access_token）
        connector = WeiboConnector({
            "access_token": "xxx",
            "expires_at": 1234567890.123,
        })
        await connector.initialize()
        result = await connector.publish(content)
    """

    PLATFORM_ID = "weibo"
    PLATFORM_NAME = "微博"

    # OAuth 2.0 配置（参考 Mixpost/Postiz 实现）
    OAUTH_AUTH_URL = "https://api.weibo.com/oauth2/authorize"
    OAUTH_TOKEN_URL = "https://api.weibo.com/oauth2/access_token"
    OAUTH_SCOPE = ""
    OAUTH_REDIRECT_URI = ""

    # API 端点
    API_BASE = "https://api.weibo.com/2"
    MOBILE_API_BASE = "https://m.weibo.cn"

    # 限流配置
    RATE_LIMIT_REQUESTS = 30  # 每分钟最多请求数（微博限制）
    RATE_LIMIT_WINDOW = 60    # 时间窗口（秒）

    def __init__(self, credentials: dict):
        ISocialMediaConnector.__init__(self, credentials)
        AuthMixin.__init__(self)
        CookieManagerMixin.__init__(self)
        RateLimitMixin.__init__(self)

        self._user_id: Optional[str] = None
        self._screen_name: Optional[str] = None

        # HTTP 客户端
        self._client: Optional[httpx.AsyncClient] = None

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    async def initialize(self) -> bool:
        """初始化连接器"""
        try:
            # 创建 HTTP 客户端
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )

            # 加载凭证
            cookie = self.credentials.get("cookie", "")
            if cookie:
                self.load_cookies(cookie)

            # 检查认证状态
            if self._access_token:
                # OAuth 认证：验证 token 有效性
                if self.is_token_expired():
                    logger.info("[Weibo] Token expired, refreshing...")
                    refresh_result = await self.refresh_token()
                    if "error" in refresh_result:
                        logger.error(f"[Weibo] Token refresh failed: {refresh_result['error']}")
                        return False
            else:
                # Cookie 认证：验证登录状态
                if not await self._verify_cookie():
                    logger.error("[Weibo] Cookie verification failed")
                    return False

            # 获取用户信息
            await self._fetch_user_info()

            self._initialized = True
            logger.info(f"[Weibo] Initialized for user: {self._screen_name or self._user_id}")
            return True

        except Exception as e:
            logger.error(f"[Weibo] Initialization failed: {e}")
            return False

    async def close(self):
        """关闭连接器"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("[Weibo] Closed")

    async def is_authenticated(self) -> bool:
        """检查是否已认证"""
        if not self._initialized:
            return False

        if self._access_token:
            return not self.is_token_expired()
        else:
            return await self._verify_cookie()

    # -------------------------------------------------------------------------
    # 账号信息
    # -------------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        """获取账号信息"""
        return AccountInfo(
            platform=self.PLATFORM_ID,
            platform_account_id=self._user_id or "",
            username=self._user_id or "",
            display_name=self._screen_name or "微博用户",
            extra={
                "auth_type": "oauth" if self._access_token else "cookie",
                "cookies_count": len(self._cookies),
            },
        )

    # -------------------------------------------------------------------------
    # 内容发布
    # -------------------------------------------------------------------------

    async def publish(self, content: PostContent) -> PostResult:
        """
        发布微博

        Args:
            content: 要发布的内容

        Returns:
            发布结果
        """
        if not self._initialized:
            return PostResult(success=False, error_message="Connector not initialized")

        try:
            # 限流等待
            await self.wait_if_needed()

            # 根据内容类型调用不同的发布方法
            if content.content_type == ContentType.IMAGE and content.media:
                return await self._post_with_image(content)
            elif content.content_type == ContentType.VIDEO and content.media:
                return await self._post_with_video(content)
            else:
                return await self._post_text(content)

        except Exception as e:
            logger.error(f"[Weibo] Publish failed: {e}")
            return PostResult(success=False, error_message=self.map_error(e, "publish"))

    async def _post_text(self, content: PostContent) -> PostResult:
        """发布纯文字微博"""
        logger.info(f"[Weibo] Posting text: {content.title[:50]}")

        try:
            # 构建微博文本
            text = content.title or ""
            if content.body:
                text = f"{text}\n\n{content.body}" if text else content.body

            # 添加话题标签
            if content.topics:
                topics_str = " ".join([f"#{t}#" for t in content.topics])
                text = f"{text} {topics_str}"

            # 调用 API
            url = f"{self.API_BASE}/statuses/update.json"
            data = {"status": text[:140]}  # 微博限制 140 字

            # 添加认证信息
            headers = self._get_headers()
            if self._access_token:
                data["access_token"] = self._access_token
            else:
                headers["Cookie"] = self.get_cookie_header()

            resp = await self._client.post(url, data=data, headers=headers)

            if resp.status_code == 200:
                result = resp.json()
                if "id" in result:
                    weibo_id = result["id"]
                    return PostResult(
                        success=True,
                        post_id=str(weibo_id),
                        post_url=f"https://weibo.com/{self._user_id}/{weibo_id}",
                        platform_data=result,
                    )
                else:
                    return PostResult(
                        success=False,
                        error_message=f"Publish failed: {result.get('error', 'Unknown error')}",
                    )
            else:
                return PostResult(
                    success=False,
                    error_message=f"API request failed: {resp.status_code} - {resp.text[:200]}",
                )

        except Exception as e:
            logger.error(f"[Weibo] Post text failed: {e}")
            return PostResult(success=False, error_message=str(e))

    async def _post_with_image(self, content: PostContent) -> PostResult:
        """发布带图片的微博"""
        logger.info(f"[Weibo] Posting with image: {content.title[:50]}")

        try:
            # 微博的图片上传需要先上传图片，再发布微博
            # 这里简化为直接调用 statuses/upload.json（实际上需要多步）
            # 实际实现可能需要先上传图片到图床，或者使用微博的图片上传接口

            # 暂时返回未实现
            return PostResult(
                success=False,
                error_message="Image posting not yet implemented, needs multi-step upload",
            )

        except Exception as e:
            logger.error(f"[Weibo] Post with image failed: {e}")
            return PostResult(success=False, error_message=str(e))

    async def _post_with_video(self, content: PostContent) -> PostResult:
        """发布带视频的微博"""
        logger.info(f"[Weibo] Posting with video: {content.title[:50]}")

        try:
            # 视频发布类似图片，需要多步上传
            return PostResult(
                success=False,
                error_message="Video posting not yet implemented, needs multi-step upload",
            )

        except Exception as e:
            logger.error(f"[Weibo] Post with video failed: {e}")
            return PostResult(success=False, error_message=str(e))

    async def delete_post(self, post_id: str) -> bool:
        """删除微博"""
        try:
            url = f"{self.API_BASE}/statuses/destroy.json"
            data = {"id": post_id}

            headers = self._get_headers()
            if self._access_token:
                data["access_token"] = self._access_token
            else:
                headers["Cookie"] = self.get_cookie_header()

            resp = await self._client.post(url, data=data, headers=headers)

            if resp.status_code == 200:
                result = resp.json()
                return "id" in result

            return False

        except Exception as e:
            logger.error(f"[Weibo] Delete failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # 内容查询
    # -------------------------------------------------------------------------

    async def get_post(self, post_id: str) -> Optional[dict]:
        """获取微博详情"""
        try:
            url = f"{self.API_BASE}/statuses/show.json"
            params = {"id": post_id}

            if self._access_token:
                params["access_token"] = self._access_token

            headers = self._get_headers()
            if not self._access_token:
                headers["Cookie"] = self.get_cookie_header()

            resp = await self._client.get(url, params=params, headers=headers)

            if resp.status_code == 200:
                return resp.json()

            return None

        except Exception as e:
            logger.error(f"[Weibo] Get post failed: {e}")
            return None

    async def get_post_metrics(self, post_id: str) -> ContentMetrics:
        """获取微博指标"""
        post = await self.get_post(post_id)
        if not post:
            return ContentMetrics(post_id=post_id)

        return ContentMetrics(
            post_id=post_id,
            likes=post.get("attitudes_count", 0),
            comments=post.get("comments_count", 0),
            shares=post.get("reposts_count", 0),
            views=post.get("page_info", {}).get("play_count", 0) if "page_info" in post else 0,
        )

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------

    async def _verify_cookie(self) -> bool:
        """验证 Cookie 有效性"""
        try:
            url = f"{self.API_BASE}/account/get_uid.json"
            headers = {"Cookie": self.get_cookie_header()}

            resp = await self._client.get(url, headers=headers)

            if resp.status_code == 200:
                result = resp.json()
                return "uid" in result

            return False

        except Exception as e:
            logger.warning(f"[Weibo] Cookie verify error: {e}")
            return False

    async def _fetch_user_info(self):
        """获取用户信息"""
        try:
            # 获取 uid
            url = f"{self.API_BASE}/account/get_uid.json"
            headers = self._get_headers()

            if self._access_token:
                params = {"access_token": self._access_token}
                resp = await self._client.get(url, params=params)
            else:
                headers["Cookie"] = self.get_cookie_header()
                resp = await self._client.get(url, headers=headers)

            if resp.status_code == 200:
                result = resp.json()
                self._user_id = str(result.get("uid", ""))

                # 获取用户详情
                if self._user_id:
                    url = f"{self.API_BASE}/users/show.json"
                    params = {"uid": self._user_id}

                    if self._access_token:
                        params["access_token"] = self._access_token
                        resp = await self._client.get(url, params=params)
                    else:
                        headers["Cookie"] = self.get_cookie_header()
                        resp = await self._client.get(url, headers=headers)

                    if resp.status_code == 200:
                        user_info = resp.json()
                        self._screen_name = user_info.get("screen_name", "")

        except Exception as e:
            logger.warning(f"[Weibo] Fetch user info error: {e}")

    def _get_headers(self) -> dict:
        """获取请求头"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if self._access_token:
            headers.update(self.get_auth_headers())

        return headers

    # -------------------------------------------------------------------------
    # 重写基类方法
    # -------------------------------------------------------------------------

    def supports_content_type(self, content_type: ContentType) -> bool:
        """检查是否支持指定内容类型"""
        return content_type in [
            ContentType.TEXT,
            ContentType.IMAGE,
            ContentType.VIDEO,
        ]

    def supports_media_format(self, media_format: MediaFormat) -> bool:
        """检查是否支持指定媒体格式"""
        return media_format in [
            MediaFormat.JPG,
            MediaFormat.PNG,
            MediaFormat.MP4,
        ]

    def get_max_media_count(self, content_type: ContentType) -> int:
        """获取最大媒体数量"""
        if content_type == ContentType.IMAGE:
            return 9  # 微博最多 9 张图
        elif content_type == ContentType.VIDEO:
            return 1  # 视频最多 1 个
        return 0
