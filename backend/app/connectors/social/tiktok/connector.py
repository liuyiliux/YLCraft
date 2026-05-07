"""
YLCraft — TikTok 连接器

功能：
- OAuth 2.0 认证（TikTok Login Kit）
- 发布视频
- 获取视频详情和指标

API 参考：
- TikTok Developer: https://developers.tiktok.com/
- Login Kit: https://developers.tiktok.com/doc/login-kit-web
- Content Posting API: https://developers.tiktok.com/doc/content-posting-api
"""

from __future__ import annotations

import asyncio
import logging
import time
import hashlib
import secrets
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

logger = logging.getLogger("ylcraft.connectors.tiktok")


@register_social_connector(
    platform_id="tiktok",
    platform_name="TikTok",
    supported_content_types=[
        ContentType.VIDEO,
        ContentType.SHORT_VIDEO,
    ],
    supported_media_formats=[
        MediaFormat.MP4,
        MediaFormat.MOV,
    ],
    auth_types=["oauth2"],
    description="TikTok - 短视频社交平台",
    # OAuth 2.0 配置
    oauth_auth_url="https://www.tiktok.com/v2/auth/authorize/",
    oauth_token_url="https://open.tiktokapis.com/v2/oauth/token/",
    oauth_scope="user.info.basic,video.upload,video.publish",
    api_base_url="https://open.tiktokapis.com/v2",
)
class TikTokConnector(ISocialMediaConnector, AuthMixin, RateLimitMixin):
    """
    TikTok 连接器

    使用 TikTok Login Kit 和 Content Posting API

    使用方式：
        connector = TikTokConnector(
            client_key="your_client_key",
            client_secret="your_client_secret"
        )
        auth_url = await connector.generate_auth_url(redirect_uri)
        # 用户授权后获取 code
        tokens = await connector.exchange_code(code, redirect_uri)
        connector.set_oauth_tokens(
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=time.time() + tokens.get("expires_in", 7200)
        )
        result = await connector.publish(content)
    """

    def __init__(
        self,
        client_key: str = "",
        client_secret: str = "",
        access_token: str = "",
        refresh_token: str = "",
        **kwargs
    ):
        """
        初始化 TikTok 连接器

        Args:
            client_key: TikTok App Client Key
            client_secret: TikTok App Client Secret
            access_token: OAuth Access Token
            refresh_token: OAuth Refresh Token
        """
        super().__init__(**kwargs)
        self._client_key = client_key
        self._client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = 0
        self._open_id = ""
        self._api_base = "https://open.tiktokapis.com/v2"

        # 设置重试配置
        self.set_retry_config(max_retries=3, retry_delay=2.0, exponential_backoff=True)
        # TikTok API 限流
        self.set_window_limit(max_requests=100, window_seconds=60)

    @property
    def platform_id(self) -> str:
        return "tiktok"

    @property
    def platform_name(self) -> str:
        return "TikTok"

    @property
    def auth_type(self) -> str:
        return "oauth2"

    # =========================================================================
    # OAuth 2.0 实现
    # =========================================================================

    async def generate_auth_url(self, redirect_uri: str, state: str = "") -> str:
        """
        生成 TikTok OAuth 授权 URL

        Args:
            redirect_uri: 回调 URI
            state: 状态参数

        Returns:
            str: 授权 URL
        """
        if not state:
            state = secrets.token_urlsafe(32)

        params = {
            "client_key": self._client_key,
            "redirect_uri": redirect_uri,
            "scope": "user.info.basic,video.upload,video.publish",
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
            "client_key": self._client_key,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            result = response.json()

            # 保存 open_id
            self._open_id = result.get("data", {}).get("open_id", "")

            return result

    async def refresh_token(self) -> dict:
        """
        刷新 access token

        Returns:
            dict: 新的 token 信息
        """
        if not self._refresh_token:
            raise ValueError("No refresh token available")

        url = self._oauth_token_url

        data = {
            "client_key": self._client_key,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            result = response.json()

            # 更新 token
            self._access_token = result.get("data", {}).get("access_token", self._access_token)
            self._refresh_token = result.get("data", {}).get("refresh_token", self._refresh_token)
            self._expires_at = time.time() + result.get("data", {}).get("expires_in", 7200)

            return result

    # =========================================================================
    # 核心功能
    # =========================================================================

    async def publish(self, content: PostContent | str, **kwargs) -> PostResult:
        """
        发布视频到 TikTok

        Args:
            content: PostContent 对象或字符串

        Returns:
            PostResult: 发布结果
        """
        try:
            if isinstance(content, str):
                content = PostContent(body=content)

            if not self._access_token:
                return PostResult(
                    success=False,
                    error_message="未认证，请先完成 OAuth 授权"
                )

            await self._ensure_valid_token()

            if not content.media or len(content.media) == 0:
                return PostResult(
                    success=False,
                    error_message="TikTok 必须上传视频"
                )

            # 上传视频
            video_media = content.media[0]
            video_id = await self._upload_video(video_media)

            if not video_id:
                return PostResult(
                    success=False,
                    error_message="视频上传失败"
                )

            # 发布视频
            post_result = await self._publish_video(
                video_id=video_id,
                title=content.title or content.body[:100],
                description=content.body,
                tags=content.topics,
            )

            if post_result.get("data", {}).get("video_id"):
                video_id_final = post_result["data"]["video_id"]
                post_url = f"https://www.tiktok.com/@user/video/{video_id_final}"

                logger.info(f"[TikTok] Published video: {video_id_final}")
                return PostResult(
                    success=True,
                    post_id=video_id_final,
                    post_url=post_url,
                    platform_data=post_result
                )

            return PostResult(
                success=False,
                error_message=post_result.get("error", {}).get("message", "发布失败")
            )

        except Exception as e:
            error_msg = self.map_error(e, "publish")
            logger.error(f"[TikTok] Publish failed: {error_msg}")
            return PostResult(success=False, error_message=error_msg)

    async def _upload_video(self, media) -> Optional[str]:
        """
        上传视频到 TikTok

        Args:
            media: MediaAttachment 对象

        Returns:
            Optional[str]: 视频上传 ID
        """
        try:
            # 初始化上传
            init_response = await self._init_upload()
            if not init_response:
                return None

            upload_id = init_response.get("data", {}).get("upload_id")
            video_size = init_response.get("data", {}).get("video_size", 0)

            # 分片上传视频
            chunk_upload_url = f"{self._api_base}/video/upload/init/"
            # 实际分片上传逻辑（简化版）
            async with httpx.AsyncClient(timeout=300.0) as client:
                with open(media.file_path, "rb") as f:
                    video_data = f.read()

                response = await client.post(
                    chunk_upload_url,
                    files={"video": video_data},
                    headers=self.get_auth_headers()
                )
                response.raise_for_status()
                result = response.json()

                return result.get("data", {}).get("video_id")

        except Exception as e:
            logger.error(f"[TikTok] Video upload failed: {e}")
            return None

    async def _init_upload(self) -> dict:
        """初始化视频上传"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._api_base}/video/init/",
                headers=self.get_auth_headers(),
                json={"upload_type": "chunk"}
            )
            response.raise_for_status()
            return response.json()

    async def _publish_video(
        self,
        video_id: str,
        title: str,
        description: str,
        tags: List[str] = None
    ) -> dict:
        """
        发布视频

        Args:
            video_id: 视频 ID
            title: 标题
            description: 描述
            tags: 话题标签

        Returns:
            dict: 发布结果
        """
        post_data = {
            "video_id": video_id,
            "title": title[:150],  # TikTok 标题限制
            "description": description[:2200],  # 描述限制
        }

        if tags:
            post_data["tags"] = tags[:10]  # 最多10个标签

        async def _do_publish():
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._api_base}/video/publish/",
                    headers=self.get_auth_headers(),
                    json=post_data
                )
                response.raise_for_status()
                return response.json()

        return await self.retry_with_backoff(_do_publish)

    async def delete_post(self, post_id: str) -> bool:
        """
        删除视频

        Args:
            post_id: 视频 ID

        Returns:
            bool: 是否删除成功
        """
        try:
            await self._ensure_valid_token()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self._api_base}/video/",
                    headers=self.get_auth_headers(),
                    params={"video_id": post_id}
                )
                response.raise_for_status()
                return True

        except Exception as e:
            logger.error(f"[TikTok] Delete failed: {e}")
            return False

    async def get_post(self, post_id: str) -> Optional[dict]:
        """
        获取视频详情

        Args:
            post_id: 视频 ID

        Returns:
            Optional[dict]: 视频详情
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._api_base}/video/",
                    headers=self.get_auth_headers(),
                    params={"video_id": post_id}
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"[TikTok] Get post failed: {e}")
            return None

    async def get_post_metrics(self, post_id: str) -> ContentMetrics:
        """
        获取视频指标

        Args:
            post_id: 视频 ID

        Returns:
            ContentMetrics: 视频指标
        """
        try:
            data = await self.get_post(post_id)
            if not data:
                return ContentMetrics()

            video_data = data.get("data", {}).get("video", {})

            return ContentMetrics(
                views=video_data.get("view_count", 0),
                likes=video_data.get("like_count", 0),
                comments=video_data.get("comment_count", 0),
                shares=video_data.get("share_count", 0),
                bookmarks=video_data.get("save_count", 0),
            )

        except Exception as e:
            logger.error(f"[TikTok] Get metrics failed: {e}")
            return ContentMetrics()

    async def get_account_info(self) -> Optional[AccountInfo]:
        """
        获取账号信息

        Returns:
            Optional[AccountInfo]: 账号信息
        """
        try:
            await self._ensure_valid_token()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._api_base}/user/info/",
                    headers=self.get_auth_headers()
                )
                response.raise_for_status()
                data = response.json()

                user = data.get("data", {})

                return AccountInfo(
                    platform="tiktok",
                    platform_account_id=user.get("open_id", ""),
                    username=user.get("username", ""),
                    display_name=user.get("display_name", ""),
                    profile_url=f"https://www.tiktok.com/@{user.get('username', '')}",
                    followers_count=user.get("follower_count", 0),
                    following_count=user.get("following_count", 0),
                    posts_count=user.get("video_count", 0),
                    verified=user.get("is_verified", False),
                )

        except Exception as e:
            logger.error(f"[TikTok] Get account info failed: {e}")
            return None

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def _ensure_valid_token(self):
        """确保 token 有效"""
        if self.is_token_expired() and self._refresh_token:
            try:
                await self.refresh_token()
                logger.info("[TikTok] Token refreshed")
            except Exception as e:
                logger.error(f"[TikTok] Token refresh failed: {e}")
                raise

    def get_auth_headers(self) -> dict:
        """获取认证头"""
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        return headers

    def is_token_expired(self) -> bool:
        """检查 token 是否过期"""
        if not self._expires_at:
            return False
        return time.time() >= (self._expires_at - 300)
