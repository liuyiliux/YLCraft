"""
YLCraft — Twitter/X 连接器

功能：
- OAuth 2.0 认证（使用 Twitter API v2）
- 发布推文（文字/图片/视频）
- 删除推文
- 获取推文详情和指标

API 参考：
- Twitter Developer: https://developer.twitter.com/
- API v2 Documentation: https://developer.twitter.com/en/docs/twitter-api
"""

from __future__ import annotations

import asyncio
import logging
import time
import base64
import hashlib
import urllib.parse
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

logger = logging.getLogger("ylcraft.connectors.twitter")


@register_social_connector(
    platform_id="twitter",
    platform_name="Twitter/X",
    supported_content_types=[
        ContentType.TEXT,
        ContentType.IMAGE,
        ContentType.VIDEO,
    ],
    supported_media_formats=[
        MediaFormat.JPG,
        MediaFormat.PNG,
        MediaFormat.GIF,
        MediaFormat.MP4,
    ],
    auth_types=["oauth2"],
    description="Twitter/X - 全球社交媒体平台",
    # OAuth 2.0 配置（Twitter API v2）
    oauth_auth_url="https://twitter.com/i/oauth2/authorize",
    oauth_token_url="https://api.twitter.com/2/oauth2/token",
    oauth_scope="tweet.read tweet.write users.read offline.access",
    api_base_url="https://api.twitter.com/2",
)
class TwitterConnector(ISocialMediaConnector, AuthMixin, RateLimitMixin):
    """
    Twitter/X 连接器

    使用 Twitter API v2，支持 OAuth 2.0 认证流程

    使用方式：
        # OAuth 认证
        connector = TwitterConnector(
            client_id="your_client_id",
            client_secret="your_client_secret"
        )
        auth_url = await connector.generate_auth_url(redirect_uri)
        # 用户访问 auth_url 授权后获取 code
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
        client_id: str = "",
        client_secret: str = "",
        access_token: str = "",
        refresh_token: str = "",
        bearer_token: str = "",
        **kwargs
    ):
        """
        初始化 Twitter 连接器

        Args:
            client_id: Twitter App Client ID
            client_secret: Twitter App Client Secret
            access_token: OAuth Access Token
            refresh_token: OAuth Refresh Token
            bearer_token: Bearer Token (用于应用级 API 调用)
        """
        super().__init__(**kwargs)
        self._client_id = client_id
        self._client_secret = client_secret
        self._bearer_token = bearer_token
        self._api_base = "https://api.twitter.com/2"

        # OAuth tokens
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = 0

        # 设置重试配置
        self.set_retry_config(max_retries=3, retry_delay=2.0, exponential_backoff=True)
        # Twitter API v2 限流：用户上下文 200请求/15分钟
        self.set_window_limit(max_requests=180, window_seconds=900)

    @property
    def platform_id(self) -> str:
        return "twitter"

    @property
    def platform_name(self) -> str:
        return "Twitter/X"

    @property
    def auth_type(self) -> str:
        return "oauth2"

    # =========================================================================
    # OAuth 2.0 实现
    # =========================================================================

    async def generate_auth_url(self, redirect_uri: str, state: str = "") -> str:
        """
        生成 Twitter OAuth 授权 URL

        Args:
            redirect_uri: 回调 URI
            state: 状态参数（用于 CSRF 保护）

        Returns:
            str: 授权 URL
        """
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)

        # 保存 code_verifier 用于后续交换 token
        self._code_verifier = code_verifier

        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": "tweet.read tweet.write users.read offline.access",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        query = "&".join([f"{k}={urllib.parse.quote(v)}" for k, v in params.items()])
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
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": getattr(self, "_code_verifier", ""),
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # 使用 client_id:client_secret 进行 Basic 认证
        credentials = f"{self._client_id}:{self._client_secret}"
        credentials_b64 = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {credentials_b64}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data, headers=headers)
            response.raise_for_status()
            return response.json()

    async def refresh_token(self) -> dict:
        """
        刷新 access token

        Args:
            refresh_token: 刷新令牌

        Returns:
            dict: 新的 token 信息
        """
        if not self._refresh_token:
            raise ValueError("No refresh token available")

        url = self._oauth_token_url

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        credentials = f"{self._client_id}:{self._client_secret}"
        credentials_b64 = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {credentials_b64}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data, headers=headers)
            response.raise_for_status()
            tokens = response.json()

            # 更新 token
            self._access_token = tokens["access_token"]
            if "refresh_token" in tokens:
                self._refresh_token = tokens["refresh_token"]
            self._expires_at = time.time() + tokens.get("expires_in", 7200)

            return tokens

    # =========================================================================
    # PKCE 辅助方法
    # =========================================================================

    def _generate_code_verifier(self, length: int = 128) -> str:
        """生成 PKCE code_verifier"""
        return base64.urlsafe_b64encode(
            hashlib.sha256(os.urandom(length)).digest()
        ).decode().rstrip("=")[:128]

    def _generate_code_challenge(self, code_verifier: str) -> str:
        """生成 PKCE code_challenge"""
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    # =========================================================================
    # 核心功能
    # =========================================================================

    async def publish(self, content: PostContent | str, **kwargs) -> PostResult:
        """
        发布推文

        Args:
            content: PostContent 对象或字符串

        Returns:
            PostResult: 发布结果
        """
        try:
            # 转换字符串为 PostContent
            if isinstance(content, str):
                content = PostContent(body=content)

            # 检查认证
            if not self._access_token:
                return PostResult(
                    success=False,
                    error_message="未认证，请先完成 OAuth 授权"
                )

            # 确保 token 有效
            await self._ensure_valid_token()

            # 构建推文文本
            text = content.body
            if content.topics:
                topics_str = " ".join([f"#{t}" if not t.startswith("#") else t for t in content.topics])
                text = f"{text}\n\n{topics_str}"
            if content.mentions:
                mentions_str = " ".join([f"@{m}" for m in content.mentions])
                text = f"{mentions_str} {text}"

            # 处理媒体
            media_ids = []
            if content.media:
                for media in content.media:
                    media_id = await self._upload_media(media)
                    if media_id:
                        media_ids.append(media_id)

            # 发布推文
            payload = {"text": text}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}

            async def _do_publish():
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self._api_base}/tweets",
                        json=payload,
                        headers=self.get_auth_headers()
                    )
                    response.raise_for_status()
                    return response.json()

            result = await self.retry_with_backoff(_do_publish)

            tweet_id = result.get("data", {}).get("id")
            post_url = f"https://twitter.com/i/status/{tweet_id}" if tweet_id else None

            logger.info(f"[Twitter] Published tweet: {tweet_id}")
            return PostResult(
                success=True,
                post_id=tweet_id,
                post_url=post_url,
                platform_data=result
            )

        except Exception as e:
            error_msg = self.map_error(e, "publish")
            logger.error(f"[Twitter] Publish failed: {error_msg}")
            return PostResult(success=False, error_message=error_msg)

    async def _upload_media(self, media) -> Optional[str]:
        """
        上传媒体文件

        Args:
            media: MediaAttachment 对象

        Returns:
            Optional[str]: 媒体 ID
        """
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # 根据媒体类型选择上传端点
                if media.media_type == MediaFormat.MP4:
                    url = f"{self._api_base}/media/upload"
                else:
                    url = f"{self._api_base}/media/upload"

                with open(media.file_path, "rb") as f:
                    files = {"media": f}
                    data = {"media_type": "tweet_video" if media.media_type == MediaFormat.MP4 else "image"}

                    response = await client.post(
                        url,
                        files=files,
                        data=data,
                        headers=self.get_auth_headers()
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result.get("media_id_string") or result.get("media_id")

        except Exception as e:
            logger.error(f"[Twitter] Media upload failed: {e}")
            return None

    async def delete_post(self, post_id: str) -> bool:
        """
        删除推文

        Args:
            post_id: 推文 ID

        Returns:
            bool: 是否删除成功
        """
        try:
            await self._ensure_valid_token()

            async def _do_delete():
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.delete(
                        f"{self._api_base}/tweets/{post_id}",
                        headers=self.get_auth_headers()
                    )
                    response.raise_for_status()
                    return response.json()

            result = await self.retry_with_backoff(_do_delete)
            logger.info(f"[Twitter] Deleted tweet: {post_id}")
            return True

        except Exception as e:
            logger.error(f"[Twitter] Delete failed: {e}")
            return False

    async def get_post(self, post_id: str) -> Optional[dict]:
        """
        获取推文详情

        Args:
            post_id: 推文 ID

        Returns:
            Optional[dict]: 推文详情
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._api_base}/tweets/{post_id}",
                    params={
                        "tweet.fields": "created_at,public_metrics,author_id,text",
                        "expansions": "author_id",
                        "user.fields": "username,name,profile_image_url"
                    },
                    headers={"Authorization": f"Bearer {self._bearer_token}"} if self._bearer_token else self.get_auth_headers()
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"[Twitter] Get post failed: {e}")
            return None

    async def get_post_metrics(self, post_id: str) -> ContentMetrics:
        """
        获取推文指标

        Args:
            post_id: 推文 ID

        Returns:
            ContentMetrics: 推文指标
        """
        try:
            data = await self.get_post(post_id)
            if not data:
                return ContentMetrics()

            tweet = data.get("data", {})
            metrics = tweet.get("public_metrics", {})

            return ContentMetrics(
                likes=metrics.get("like_count", 0),
                retweets=metrics.get("retweet_count", 0),
                replies=metrics.get("reply_count", 0),
                quotes=metrics.get("quote_count", 0),
                impressions=metrics.get("impression_count", 0),
            )

        except Exception as e:
            logger.error(f"[Twitter] Get metrics failed: {e}")
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
                    f"{self._api_base}/users/me",
                    params={"user.fields": "name,username,profile_image_url,public_metrics,verified"},
                    headers=self.get_auth_headers()
                )
                response.raise_for_status()
                data = response.json()

                user = data.get("data", {})
                metrics = user.get("public_metrics", {})

                return AccountInfo(
                    platform="twitter",
                    platform_account_id=user.get("id", ""),
                    username=user.get("username", ""),
                    display_name=user.get("name", ""),
                    profile_url=f"https://twitter.com/{user.get('username', '')}",
                    followers_count=metrics.get("followers_count", 0),
                    following_count=metrics.get("following_count", 0),
                    posts_count=metrics.get("tweet_count", 0),
                    verified=user.get("verified", False),
                )

        except Exception as e:
            logger.error(f"[Twitter] Get account info failed: {e}")
            return None

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def _ensure_valid_token(self):
        """确保 token 有效，必要时刷新"""
        if self.is_token_expired() and self._refresh_token:
            try:
                await self.refresh_token()
                logger.info("[Twitter] Token refreshed")
            except Exception as e:
                logger.error(f"[Twitter] Token refresh failed: {e}")
                raise

    def get_auth_headers(self) -> dict:
        """获取认证头"""
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}

    def is_token_expired(self) -> bool:
        """检查 token 是否过期"""
        if not self._expires_at:
            return False
        return time.time() >= (self._expires_at - 300)


# 导入 os 用于 _generate_code_verifier
import os
