"""
YLCraft — Instagram 连接器

功能：
- OAuth 2.0 认证（Instagram Graph API）
- 发布图片/视频/Stories
- 获取帖子详情和指标

API 参考：
- Instagram Developer: https://developers.facebook.com/docs/instagram-api
- Instagram Graph API: https://developers.facebook.com/docs/instagram-api/reference/ig-user
"""

from __future__ import annotations

import asyncio
import logging
import time
import base64
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

logger = logging.getLogger("ylcraft.connectors.instagram")


@register_social_connector(
    platform_id="instagram",
    platform_name="Instagram",
    supported_content_types=[
        ContentType.IMAGE,
        ContentType.VIDEO,
        ContentType.STORY,
    ],
    supported_media_formats=[
        MediaFormat.JPG,
        MediaFormat.PNG,
        MediaFormat.GIF,
        MediaFormat.MP4,
    ],
    auth_types=["oauth2"],
    description="Instagram - 图片和短视频社交平台",
    # OAuth 2.0 配置（使用 Facebook OAuth）
    oauth_auth_url="https://api.instagram.com/oauth/authorize",
    oauth_token_url="https://api.instagram.com/oauth/access_token",
    oauth_scope="instagram_basic,instagram_content_publish,instagram_manage_comments,instagram_manage_insights",
    api_base_url="https://graph.instagram.com",
)
class InstagramConnector(ISocialMediaConnector, AuthMixin, RateLimitMixin):
    """
    Instagram 连接器

    使用 Instagram Graph API (专业账户)

    使用方式：
        connector = InstagramConnector(
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
        access_token: str = "",
        **kwargs
    ):
        """
        初始化 Instagram 连接器

        Args:
            app_id: Facebook App ID
            app_secret: Facebook App Secret
            instagram_account_id: Instagram 商业账户 ID
            access_token: 长期访问令牌
        """
        super().__init__(**kwargs)
        self._app_id = app_id
        self._app_secret = app_secret
        self._instagram_account_id = instagram_account_id
        self._access_token = access_token
        self._expires_at = 0
        self._api_base = "https://graph.instagram.com"
        self._fb_api_base = "https://graph.facebook.com/v18.0"

        # 设置重试配置
        self.set_retry_config(max_retries=3, retry_delay=2.0, exponential_backoff=True)
        self.set_window_limit(max_requests=200, window_seconds=3600)

    @property
    def platform_id(self) -> str:
        return "instagram"

    @property
    def platform_name(self) -> str:
        return "Instagram"

    @property
    def auth_type(self) -> str:
        return "oauth2"

    # =========================================================================
    # OAuth 2.0 实现
    # =========================================================================

    async def generate_auth_url(self, redirect_uri: str, state: str = "") -> str:
        """
        生成 Instagram OAuth 授权 URL

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
        return f"{self._oauth_auth_url}?{query}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """
        用授权码交换 access token

        Args:
            code: 授权码
            redirect_uri: 回调 URI

        Returns:
            dict: 包含 access_token 等信息的字典
        """
        url = self._oauth_token_url

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
            result = response.json()

            # 交换短期 token 为长期 token
            if "access_token" in result:
                long_token = await self._get_long_lived_token(result["access_token"])
                return long_token

            return result

    async def _get_long_lived_token(self, short_token: str) -> dict:
        """
        将短期 token 转换为长期 token

        Args:
            short_token: 短期访问令牌

        Returns:
            dict: 包含长期 token 的字典
        """
        url = f"{self._fb_api_base}/oauth/access_token"
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

    async def refresh_token(self) -> dict:
        """
        刷新 access token

        Returns:
            dict: 新的 token 信息
        """
        if not self._access_token:
            raise ValueError("No access token available")

        # Instagram 长期 token 可自动续期
        url = f"{self._fb_api_base}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self._app_id,
            "client_secret": self._app_secret,
            "fb_exchange_token": self._access_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            result = response.json()

            self._access_token = result.get("access_token", self._access_token)
            self._expires_at = time.time() + result.get("expires_in", 5184000)

            return result

    # =========================================================================
    # 核心功能
    # =========================================================================

    async def publish(self, content: PostContent | str, **kwargs) -> PostResult:
        """
        发布内容到 Instagram

        Args:
            content: PostContent 对象或字符串
            **kwargs: platform_override="REELS" 可发布 Reels

        Returns:
            PostResult: 发布结果
        """
        try:
            if isinstance(content, str):
                content = PostContent(body=content)

            if not self._access_token or not self._instagram_account_id:
                return PostResult(
                    success=False,
                    error_message="未认证或未设置 Instagram 账户，请先完成 OAuth 授权"
                )

            await self._ensure_valid_token()

            if not content.media:
                return PostResult(
                    success=False,
                    error_message="Instagram 必须上传图片或视频"
                )

            media = content.media[0]
            platform_override = kwargs.get("platform_override", "")

            # 创建媒体容器
            container_id = await self._create_media_container(
                media=media,
                caption=content.body,
                platform_override=platform_override
            )

            if not container_id:
                return PostResult(
                    success=False,
                    error_message="创建媒体容器失败"
                )

            # 发布媒体
            media_id = await self._publish_container(container_id)

            if media_id:
                post_url = f"https://www.instagram.com/p/{media_id}/"

                logger.info(f"[Instagram] Published media: {media_id}")
                return PostResult(
                    success=True,
                    post_id=media_id,
                    post_url=post_url
                )

            return PostResult(
                success=False,
                error_message="发布失败"
            )

        except Exception as e:
            error_msg = self.map_error(e, "publish")
            logger.error(f"[Instagram] Publish failed: {error_msg}")
            return PostResult(success=False, error_message=error_msg)

    async def _create_media_container(
        self,
        media,
        caption: str = "",
        platform_override: str = ""
    ) -> Optional[str]:
        """
        创建媒体容器

        Args:
            media: MediaAttachment 对象
            caption: 描述文字
            platform_override: 平台覆盖（STORIES, REELS, IGTV）

        Returns:
            Optional[str]: 容器 ID
        """
        url = f"{self._api_base}/me/media"

        if media.media_type == MediaFormat.MP4 or platform_override == "REELS":
            # 视频发布
            container_type = "VIDEO"
        elif platform_override == "STORIES":
            container_type = "STORIES"
        else:
            container_type = "IMAGE"

        data = {
            "caption": caption[:2200],
            "media_type": container_type,
            "access_token": self._access_token,
        }

        # 上传图片/视频文件
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                with open(media.file_path, "rb") as f:
                    if container_type == "VIDEO":
                        files = {"video_url": f}
                        data["media_type"] = "VIDEO"
                    else:
                        files = {"image_url": f}

                    response = await client.post(
                        url,
                        data=data,
                        files=files if container_type != "VIDEO" else None,
                    )
                    response.raise_for_status()
                    result = response.json()

                    return result.get("id")

        except Exception as e:
            logger.error(f"[Instagram] Create container failed: {e}")
            return None

    async def _publish_container(self, container_id: str) -> Optional[str]:
        """
        发布媒体容器

        Args:
            container_id: 容器 ID

        Returns:
            Optional[str]: 媒体 ID
        """
        url = f"{self._api_base}/{self._instagram_account_id}/media_publish"

        data = {
            "creation_id": container_id,
            "access_token": self._access_token,
        }

        async def _do_publish():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, data=data)
                response.raise_for_status()
                return response.json()

        try:
            result = await self.retry_with_backoff(_do_publish)
            return result.get("id")
        except Exception as e:
            logger.error(f"[Instagram] Publish container failed: {e}")
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
            url = f"{self._api_base}/{post_id}"

            params = {"access_token": self._access_token}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(url, params=params)
                response.raise_for_status()
                return True

        except Exception as e:
            logger.error(f"[Instagram] Delete failed: {e}")
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
            url = f"{self._api_base}/{post_id}"
            params = {
                "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
                "access_token": self._access_token,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"[Instagram] Get post failed: {e}")
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
            url = f"{self._api_base}/{post_id}/insights"
            params = {
                "metric": "likes,comments,shares,saves,impressions,reach,video_views",
                "access_token": self._access_token,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                metrics = {}
                for item in data.get("data", []):
                    metrics[item["name"]] = item["values"][0]["value"]

                return ContentMetrics(
                    likes=metrics.get("likes", 0),
                    comments=metrics.get("comments", 0),
                    shares=metrics.get("shares", 0),
                    bookmarks=metrics.get("saves", 0),
                    views=metrics.get("impressions", 0) or metrics.get("video_views", 0),
                )

        except Exception as e:
            logger.error(f"[Instagram] Get metrics failed: {e}")
            return ContentMetrics()

    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取账号信息

        Returns:
            Optional[AccountInfo]: 账号信息
        """
        try:
            url = f"{self._api_base}/{self._instagram_account_id}"
            params = {
                "fields": "id,username,name,media_count,followers_count,follows_count,biography,website,profile_picture_url,ig_id",
                "access_token": self._access_token,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                return AccountInfo(
                    platform="instagram",
                    platform_account_id=data.get("id", ""),
                    username=data.get("username", ""),
                    display_name=data.get("name", data.get("username", "")),
                    profile_url=f"https://www.instagram.com/{data.get('username', '')}",
                    followers_count=data.get("followers_count", 0),
                    following_count=data.get("follows_count", 0),
                    posts_count=data.get("media_count", 0),
                    avatar_url=data.get("profile_picture_url"),
                )

        except Exception as e:
            logger.error(f"[Instagram] Get account info failed: {e}")
            return None

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def _ensure_valid_token(self):
        """确保 token 有效"""
        if self.is_token_expired() and self._refresh_token:
            try:
                await self.refresh_token()
                logger.info("[Instagram] Token refreshed")
            except Exception as e:
                logger.error(f"[Instagram] Token refresh failed: {e}")

    def get_auth_headers(self) -> dict:
        """获取认证头"""
        return {"access_token": self._access_token}

    def is_token_expired(self) -> bool:
        """检查 token 是否过期"""
        if not self._expires_at:
            return False
        return time.time() >= (self._expires_at - 3600)
