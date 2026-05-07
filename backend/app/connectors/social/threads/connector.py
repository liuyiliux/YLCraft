"""
YLCraft — Threads 连接器

功能：
- OAuth 2.0 认证（Instagram/Threads API）
- 发布文本帖子
- 获取帖子详情和指标

API 参考：
- Threads API: https://developers.facebook.com/docs/threads-api
- Threads API Reference: https://developers.facebook.com/docs/threads-api/reference
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Any, List
from datetime import datetime, timedelta

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
from app.connectors.mixins import AuthMixin, RateLimitMixin
from app.connectors import register_social_connector

logger = logging.getLogger("ylcraft.connectors.threads")


@register_social_connector(
    platform_id="threads",
    platform_name="Threads",
    supported_content_types=[
        ContentType.TEXT,
        ContentType.IMAGE,
    ],
    supported_media_formats=[
        MediaFormat.JPG,
        MediaFormat.PNG,
        MediaFormat.GIF,
    ],
    auth_types=["oauth2"],
    description="Threads - Meta 文本社交平台",
    # OAuth 2.0 配置（使用 Instagram/Facebook OAuth）
    oauth_auth_url="https://threads.net/oauth/authorize",
    oauth_token_url="https://graph.instagram.com/oauth/access_token",
    oauth_scope="threads_basic,threads_content_publish,instagram_basic",
    api_base_url="https://graph.instagram.com",
)
class ThreadsConnector(ISocialMediaConnector, AuthMixin, RateLimitMixin):
    """
    Threads 连接器

    使用 Threads API（基于 Instagram Graph API）

    使用方式：
        connector = ThreadsConnector(
            app_id="your_app_id",
            app_secret="your_app_secret",
            instagram_account_id="your_ig_account_id"
        )
        auth_url = await connector.generate_auth_url(redirect_uri)
        tokens = await connector.exchange_code(code, redirect_uri)
        connector.set_oauth_tokens(access_token=tokens["access_token"])
        result = await connector.publish(content)
    """

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        instagram_account_id: str = "",
        threads_token: str = "",
        access_token: str = "",
        **kwargs
    ):
        """
        初始化 Threads 连接器

        Args:
            app_id: Facebook App ID
            app_secret: Facebook App Secret
            instagram_account_id: Instagram 账户 ID (用于获取 Threads 访问)
            threads_token: Threads API 专用令牌
            access_token: Instagram 访问令牌
        """
        super().__init__(**kwargs)
        self._app_id = app_id
        self._app_secret = app_secret
        self._instagram_account_id = instagram_account_id
        self._threads_token = threads_token or access_token
        self._access_token = threads_token or access_token
        self._expires_at = 0
        self._user_id = ""
        self._api_base = "https://graph.instagram.com"
        self._threads_api_base = "https://graph.threads.net/v1.0"

        # 设置重试配置
        self.set_retry_config(max_retries=3, retry_delay=2.0, exponential_backoff=True)
        self.set_window_limit(max_requests=100, window_seconds=3600)

    @property
    def platform_id(self) -> str:
        return "threads"

    @property
    def platform_name(self) -> str:
        return "Threads"

    @property
    def auth_type(self) -> str:
        return "oauth2"

    # =========================================================================
    # OAuth 2.0 实现
    # =========================================================================

    async def generate_auth_url(self, redirect_uri: str, state: str = "") -> str:
        """
        生成 Threads OAuth 授权 URL

        Args:
            redirect_uri: 回调 URI
            state: 状态参数

        Returns:
            str: 授权 URL
        """
        params = {
            "client_id": self._app_id,
            "redirect_uri": redirect_uri,
            "scope": self._oauth_scope,
            "response_type": "code",
            "state": state,
        }

        query = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.facebook.com/v18.0/dialog/oauth?{query}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """
        用授权码交换 access token

        Args:
            code: 授权码
            redirect_uri: 回调 URI

        Returns:
            dict: 包含 access_token 等信息的字典
        """
        # 首先获取 Instagram token
        url = f"{self._api_base}/oauth/access_token"

        data = {
            "client_id": self._app_id,
            "client_secret": self._app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            ig_result = response.json()

            # 转换为长期 token
            long_token = await self._get_long_lived_token(ig_result.get("access_token"))

            # 获取 Threads token
            threads_token = await self._get_threads_token(long_token.get("access_token"))

            return threads_token

    async def _get_long_lived_token(self, short_token: str) -> dict:
        """将短期 token 转换为长期 token"""
        url = f"https://graph.facebook.com/v18.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self._app_id,
            "client_secret": self._app_secret,
            "fb_exchange_token": short_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def _get_threads_token(self, ig_token: str) -> dict:
        """获取 Threads API token"""
        url = f"{self._threads_api_base}/authorize"

        data = {
            "grant_type": "ig_exchange_token",
            "client_secret": self._app_secret,
            "access_token": ig_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()

            self._threads_token = result.get("access_token", ig_token)
            self._access_token = self._threads_token
            self._user_id = result.get("user_id", "")

            return result

    async def refresh_token(self) -> dict:
        """
        刷新 access token

        Returns:
            dict: 新的 token 信息
        """
        if not self._threads_token:
            raise ValueError("No threads token available")

        url = f"{self._threads_api_base}/refresh_token"

        data = {
            "grant_type": "refresh_token",
            "access_token": self._threads_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()

            self._threads_token = result.get("access_token", self._threads_token)
            self._access_token = self._threads_token

            return result

    # =========================================================================
    # 核心功能
    # =========================================================================

    async def publish(self, content: PostContent | str, **kwargs) -> PostResult:
        """
        发布内容到 Threads

        Args:
            content: PostContent 对象或字符串

        Returns:
            PostResult: 发布结果
        """
        try:
            if isinstance(content, str):
                content = PostContent(body=content)

            if not self._access_token or not self._user_id:
                return PostResult(
                    success=False,
                    error_message="未认证，请先完成 OAuth 授权"
                )

            await self._ensure_valid_token()

            # 构建帖子文本
            text = content.body
            if content.topics:
                topics_str = " ".join([f"#{t}" if not t.startswith("#") else t for t in content.topics])
                text = f"{text}\n\n{topics_str}"

            # 处理媒体
            media_ids = []
            if content.media:
                for media in content.media:
                    media_id = await self._upload_image(media)
                    if media_id:
                        media_ids.append(media_id)

            # 创建并发布帖子
            payload = {
                "text": text[:500],  # Threads 限制 500 字符
            }

            if media_ids:
                payload["image"] = {"media_id": media_ids[0]}

            async def _do_publish():
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self._threads_api_base}/me/threads",
                        data=payload,
                        params={"access_token": self._access_token}
                    )
                    response.raise_for_status()
                    return response.json()

            result = await self.retry_with_backoff(_do_publish)

            if result.get("id"):
                post_id = result["id"]
                post_url = f"https://www.threads.net/@user/post/{post_id}"

                logger.info(f"[Threads] Published post: {post_id}")
                return PostResult(
                    success=True,
                    post_id=post_id,
                    post_url=post_url,
                    platform_data=result
                )

            return PostResult(
                success=False,
                error_message=result.get("error", {}).get("message", "发布失败")
            )

        except Exception as e:
            error_msg = self.map_error(e, "publish")
            logger.error(f"[Threads] Publish failed: {error_msg}")
            return PostResult(success=False, error_message=error_msg)

    async def _upload_image(self, media) -> Optional[str]:
        """
        上传图片

        Args:
            media: MediaAttachment 对象

        Returns:
            Optional[str]: 媒体 ID
        """
        try:
            url = f"{self._threads_api_base}/me/media"

            async with httpx.AsyncClient(timeout=120.0) as client:
                with open(media.file_path, "rb") as f:
                    files = {"image_url": (media.file_path, f, "image/jpeg")}
                    data = {"access_token": self._access_token}

                    response = await client.post(url, data=data, files=files)
                    response.raise_for_status()
                    result = response.json()

                    return result.get("id")

        except Exception as e:
            logger.error(f"[Threads] Image upload failed: {e}")
            return None

    async def delete_post(self, post_id: str) -> bool:
        """
        删除帖子

        Args:
            post_id: 帖子 ID

        Returns:
            bool: 是否删除成功
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self._threads_api_base}/{post_id}",
                    params={"access_token": self._access_token}
                )
                response.raise_for_status()
                return True

        except Exception as e:
            logger.error(f"[Threads] Delete failed: {e}")
            return False

    async def get_post(self, post_id: str) -> Optional[dict]:
        """
        获取帖子详情

        Args:
            post_id: 帖子 ID

        Returns:
            Optional[dict]: 帖子详情
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._threads_api_base}/{post_id}",
                    params={
                        "access_token": self._access_token,
                        "fields": "id,text,timestamp,like_count,replies_count,repost_count,permalink"
                    }
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"[Threads] Get post failed: {e}")
            return None

    async def get_post_metrics(self, post_id: str) -> ContentMetrics:
        """
        获取帖子指标

        Args:
            post_id: 帖子 ID

        Returns:
            ContentMetrics: 帖子指标
        """
        try:
            data = await self.get_post(post_id)
            if not data:
                return ContentMetrics()

            return ContentMetrics(
                likes=data.get("like_count", 0),
                comments=data.get("replies_count", 0),
                shares=data.get("repost_count", 0),
            )

        except Exception as e:
            logger.error(f"[Threads] Get metrics failed: {e}")
            return ContentMetrics()

    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取账号信息

        Returns:
            Optional[AccountInfo]: 账号信息
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._threads_api_base}/me",
                    params={
                        "access_token": self._access_token,
                        "fields": "id,username,name,threads_profile_picture_url,threads_biography"
                    }
                )
                response.raise_for_status()
                data = response.json()

                return AccountInfo(
                    platform="threads",
                    platform_account_id=data.get("id", ""),
                    username=data.get("username", ""),
                    display_name=data.get("name", data.get("username", "")),
                    profile_url=f"https://www.threads.net/@{data.get('username', '')}",
                    avatar_url=data.get("threads_profile_picture_url"),
                )

        except Exception as e:
            logger.error(f"[Threads] Get account info failed: {e}")
            return None

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def _ensure_valid_token(self):
        """确保 token 有效"""
        if self.is_token_expired():
            try:
                await self.refresh_token()
                logger.info("[Threads] Token refreshed")
            except Exception as e:
                logger.error(f"[Threads] Token refresh failed: {e}")

    def get_auth_headers(self) -> dict:
        """获取认证头"""
        return {"access_token": self._access_token}

    def is_token_expired(self) -> bool:
        """检查 token 是否过期"""
        if not self._expires_at:
            return False
        return time.time() >= (self._expires_at - 3600)
