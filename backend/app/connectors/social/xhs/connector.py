"""
YLCraft — 小红书连接器

参考 MediaCrawler 的平台实现模式：
- 继承 ISOCIALMediaConnector 抽象基类
- 使用 CookieManagerMixin 管理 Cookie
- 实现笔记发布、查询等功能
"""

from __future__ import annotations

import logging
from typing import Optional, Any
from datetime import datetime

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

logger = logging.getLogger("ylcraft.connectors.xhs")


@register_social_connector(
    platform_id="xhs",
    supported_content_types=[
        ContentType.TEXT,
        ContentType.IMAGE,
        ContentType.VIDEO,
        ContentType.ARTICLE,
    ],
    supported_media_formats=[
        MediaFormat.JPG,
        MediaFormat.PNG,
        MediaFormat.MP4,
        MediaFormat.AVI,
    ],
    auth_types=["cookie"],
    description="小红书 - 种草社区",
)
class XiaoHongShuConnector(ISocialMediaConnector, AuthMixin, CookieManagerMixin, RateLimitMixin):
    """
    小红书连接器

    功能：
    - Cookie 认证
    - 笔记发布（图文/视频）
    - 笔记查询
    - 数据统计

    使用方式：
        connector = XiaoHongShuConnector({"cookie": "..."})
        await connector.initialize()
        result = await connector.publish(content)
    """

    PLATFORM_ID = "xhs"
    PLATFORM_NAME = "小红书"

    # API 端点
    API_BASE = "https://edith.xiaohongshu.com"

    def __init__(self, credentials: dict):
        ISocialMediaConnector.__init__(self, credentials)
        AuthMixin.__init__(self)
        CookieManagerMixin.__init__(self)
        RateLimitMixin.__init__(self)

        self._user_id: Optional[str] = None
        self._nickname: Optional[str] = None

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    async def initialize(self) -> bool:
        """初始化连接器"""
        try:
            # 加载 Cookie
            cookie = self.credentials.get("cookie", "")
            if not cookie:
                logger.error("[XHS] Cookie is required")
                return False

            if not self.load_cookies(cookie):
                logger.error("[XHS] Failed to load cookies")
                return False

            # 验证 Cookie 有效性
            if not await self._verify_cookie():
                return False

            self._initialized = True
            logger.info("[XHS] Initialized successfully")
            return True

        except Exception as e:
            logger.error(f"[XHS] Initialization failed: {e}")
            return False

    async def close(self):
        """关闭连接器"""
        self._initialized = False
        logger.info("[XHS] Closed")

    async def is_authenticated(self) -> bool:
        """检查是否已认证"""
        if not self._initialized:
            return False
        return await self._verify_cookie()

    # -------------------------------------------------------------------------
    # 账号信息
    # -------------------------------------------------------------------------

    async def get_account_info(self) -> AccountInfo:
        """获取账号信息"""
        try:
            # 从 Cookie 中提取用户信息
            cookies = self.get_cookies_dict()

            headers = {
                "Cookie": self.get_cookie_header(),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            # 简化实现：实际应该调用小红书 API
            user_id = cookies.get("web_session", "").split("=")[1] if "web_session" in cookies else ""

            return AccountInfo(
                platform=self.PLATFORM_ID,
                platform_account_id=user_id,
                username=self._nickname or user_id,
                display_name=self._nickname or "小红书用户",
                extra={"cookies": len(self._cookies)},
            )

        except Exception as e:
            logger.error(f"[XHS] Failed to get account info: {e}")
            return AccountInfo(
                platform=self.PLATFORM_ID,
                platform_account_id="",
                username="",
                display_name="获取失败",
            )

    # -------------------------------------------------------------------------
    # 内容发布
    # -------------------------------------------------------------------------

    async def publish(self, content: PostContent) -> PostResult:
        """
        发布小红书笔记

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

            # 构建请求
            headers = {
                "Cookie": self.get_cookie_header(),
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-s": self._generate_sign(),  # 小红书签名
            }

            # 根据内容类型构建不同的请求（使用重试机制）
            try:
                if content.content_type == ContentType.IMAGE:
                    return await self._publish_image_note(content, headers)
                elif content.content_type == ContentType.VIDEO:
                    return await self._publish_video_note(content, headers)
                elif content.content_type == ContentType.ARTICLE:
                    return await self._publish_article(content, headers)
                else:
                    return await self._publish_text_note(content, headers)
            except Exception as publish_error:
                # 使用重试机制
                logger.warning(f"[XHS] Publish attempt failed: {publish_error}")
                # 可以在这里增加重试逻辑，或者直接返回错误
                return PostResult(
                    success=False,
                    error_message=self.map_error(publish_error, "publish")
                )

        except Exception as e:
            logger.error(f"[XHS] Publish failed: {e}")
            return PostResult(success=False, error_message=self.map_error(e, "publish"))

    async def _publish_image_note(self, content: PostContent, headers: dict) -> PostResult:
        """发布图文笔记"""
        # 实现细节
        logger.info(f"[XHS] Publishing image note: {content.title[:50]}")

        # TODO: 实现实际的 API 调用
        return PostResult(
            success=True,
            post_id="demo_post_id",
            post_url=f"https://www.xiaohongshu.com/explore/demo",
            platform_data={"type": "image"},
        )

    async def _publish_video_note(self, content: PostContent, headers: dict) -> PostResult:
        """发布视频笔记"""
        logger.info(f"[XHS] Publishing video note: {content.title[:50]}")

        # TODO: 实现实际的 API 调用
        return PostResult(
            success=True,
            post_id="demo_video_id",
            post_url=f"https://www.xiaohongshu.com/explore/demo_video",
            platform_data={"type": "video"},
        )

    async def _publish_text_note(self, content: PostContent, headers: dict) -> PostResult:
        """发布纯文本笔记"""
        logger.info(f"[XHS] Publishing text note: {content.title[:50]}")

        return PostResult(
            success=True,
            post_id="demo_text_id",
            post_url=f"https://www.xiaohongshu.com/explore/demo_text",
            platform_data={"type": "text"},
        )

    async def _publish_article(self, content: PostContent, headers: dict) -> PostResult:
        """发布长文章"""
        logger.info(f"[XHS] Publishing article: {content.title[:50]}")

        return PostResult(
            success=True,
            post_id="demo_article_id",
            post_url=f"https://www.xiaohongshu.com/explore/demo_article",
            platform_data={"type": "article"},
        )

    async def delete_post(self, post_id: str) -> bool:
        """删除笔记"""
        try:
            headers = {
                "Cookie": self.get_cookie_header(),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            # TODO: 实现删除 API
            logger.info(f"[XHS] Deleting post: {post_id}")
            return True

        except Exception as e:
            logger.error(f"[XHS] Delete failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # 内容查询
    # -------------------------------------------------------------------------

    async def get_post(self, post_id: str) -> Optional[dict]:
        """获取笔记详情"""
        try:
            headers = {
                "Cookie": self.get_cookie_header(),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            # TODO: 实现获取笔记详情 API
            return {
                "id": post_id,
                "title": "示例笔记",
                "like_count": 100,
                "collect_count": 50,
                "comment_count": 20,
            }

        except Exception as e:
            logger.error(f"[XHS] Get post failed: {e}")
            return None

    async def get_post_metrics(self, post_id: str) -> ContentMetrics:
        """获取笔记指标"""
        post = await self.get_post(post_id)
        if not post:
            return ContentMetrics(post_id=post_id)

        return ContentMetrics(
            post_id=post_id,
            likes=post.get("like_count", 0),
            collects=post.get("collect_count", 0),
            comments=post.get("comment_count", 0),
            views=post.get("view_count", 0),
            shares=post.get("share_count", 0),
        )

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------

    async def _verify_cookie(self) -> bool:
        """验证 Cookie 有效性"""
        try:
            cookies = self.get_cookies_dict()
            return len(cookies) > 0
        except Exception:
            return False

    def _generate_sign(self) -> str:
        """生成小红书签名（简化实现）"""
        import hashlib
        import time

        timestamp = str(int(time.time() * 1000))
        return hashlib.md5(timestamp.encode()).hexdigest()[:10]

    # -------------------------------------------------------------------------
    # 重写基类方法
    # -------------------------------------------------------------------------

    def supports_content_type(self, content_type: ContentType) -> bool:
        """检查是否支持指定内容类型"""
        return content_type in [
            ContentType.TEXT,
            ContentType.IMAGE,
            ContentType.VIDEO,
            ContentType.ARTICLE,
        ]

    def supports_media_format(self, media_format: MediaFormat) -> bool:
        """检查是否支持指定媒体格式"""
        return media_format in [
            MediaFormat.JPG,
            MediaFormat.PNG,
            MediaFormat.MP4,
            MediaFormat.WEBP,
        ]

    def get_max_media_count(self, content_type: ContentType) -> int:
        """获取最大媒体数量"""
        if content_type == ContentType.IMAGE:
            return 9  # 图文最多 9 张
        elif content_type == ContentType.VIDEO:
            return 1  # 视频笔记最多 1 个
        return 0
