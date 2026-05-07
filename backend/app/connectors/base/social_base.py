"""
YLCraft — 社交媒体连接器抽象基类

参考 MediaCrawler 的分层架构设计：
- 定义所有社交媒体平台必须遵循的接口契约
- 支持 Cookie、OAuth2、QRCode 等多种认证方式
- 提供统一的发布、查询、数据采集接口

所有平台实现必须继承这些抽象基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("ylcraft.connectors.base")


# =============================================================================
# 数据模型
# =============================================================================

class ContentType(str, Enum):
    """内容类型"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    ARTICLE = "article"
    STORY = "story"
    SHORT_VIDEO = "short_video"


class MediaFormat(str, Enum):
    """媒体格式"""
    MP4 = "mp4"
    MOV = "mov"
    AVI = "avi"
    JPG = "jpg"
    PNG = "png"
    GIF = "gif"
    WEBP = "webp"


@dataclass
class MediaAttachment:
    """媒体附件"""
    file_path: str
    media_type: MediaFormat
    caption: str = ""
    duration: Optional[float] = None  # 视频时长（秒）


@dataclass
class PostContent:
    """发布内容"""
    title: str = ""
    body: str = ""
    content_type: ContentType = ContentType.TEXT
    media: list[MediaAttachment] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)  # @用户
    topics: list[str] = field(default_factory=list)   # #话题
    location: Optional[str] = None
    extra: dict = field(default_factory=dict)  # 平台特定参数


@dataclass
class PostResult:
    """发布结果"""
    success: bool
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    error_message: Optional[str] = None
    platform_data: dict = field(default_factory=dict)  # 平台返回的原始数据


@dataclass
class AccountInfo:
    """账号信息"""
    platform: str
    platform_account_id: str
    username: str
    display_name: str
    avatar_url: Optional[str] = None
    profile_url: Optional[str] = None
    followers_count: Optional[int] = None
    following_count: Optional[int] = None
    posts_count: Optional[int] = None
    verified: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class ContentMetrics:
    """内容指标"""
    post_id: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    collects: int = 0
    followers_gained: int = 0


# =============================================================================
# 抽象基类
# =============================================================================

class ISocialMediaConnector(ABC):
    """
    社交媒体连接器抽象基类

    所有社交媒体平台连接器必须实现此接口。
    设计参考 MediaCrawler 的 AbstractCrawler 模式。

    新增 OAuth 2.0 支持（参考 Mixpost/Postiz 实现）
    """

    # 平台标识（子类必须设置）
    PLATFORM_ID: str = ""
    PLATFORM_NAME: str = ""

    # OAuth 配置（子类可覆盖）
    OAUTH_SCOPE: str = ""
    OAUTH_AUTH_URL: str = ""
    OAUTH_TOKEN_URL: str = ""
    OAUTH_REDIRECT_URI: str = ""

    def __init__(self, credentials: dict):
        """
        初始化连接器

        Args:
            credentials: 凭证数据（Cookie/OAuth Token 等）
        """
        self.credentials = credentials
        self._initialized = False
        self._account_info: Optional[AccountInfo] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

        # 从凭证中提取 token 信息
        self._extract_oauth_info()

    def _extract_oauth_info(self):
        """从凭证中提取 OAuth 信息（子类可覆盖）"""
        self._access_token = self.credentials.get("access_token")
        self._refresh_token = self.credentials.get("refresh_token")
        self._token_expires_at = self.credentials.get("expires_at")

    # -------------------------------------------------------------------------
    # OAuth 2.0 认证流程（参考 Mixpost/Postiz 实现）
    # -------------------------------------------------------------------------

    def supports_oauth(self) -> bool:
        """
        检查是否支持 OAuth 认证
        子类可覆盖
        """
        return bool(self.OAUTH_AUTH_URL and self.OAUTH_TOKEN_URL)

    def generate_auth_url(self, state: str = None, extra_params: dict = None) -> str:
        """
        生成 OAuth 授权 URL
        参考 Postiz 的 generateAuthUrl 方法

        Args:
            state: 可选的状态参数（用于 CSRF 防护）
            extra_params: 额外的授权参数

        Returns:
            授权 URL，如果不支持则返回空字符串
        """
        if not self.supports_oauth():
            return ""

        import urllib.parse
        import secrets

        params = {
            "client_id": self.credentials.get("client_id", ""),
            "redirect_uri": self.credentials.get("redirect_uri", self.OAUTH_REDIRECT_URI),
            "response_type": "code",
            "scope": self.OAUTH_SCOPE,
        }

        if state:
            params["state"] = state
        else:
            params["state"] = secrets.token_urlsafe(16)

        if extra_params:
            params.update(extra_params)

        return f"{self.OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str = None) -> dict:
        """
        用授权码交换 access token
        参考 Mixpost 的 OAuth 令牌交换流程

        Args:
            code: OAuth 授权码
            redirect_uri: 回调地址（可选）

        Returns:
            包含 token 信息的字典，如：
            {
                "access_token": "...",
                "refresh_token": "...",
                "expires_in": 3600,
                "token_type": "Bearer"
            }
        """
        if not self.supports_oauth():
            return {"error": "OAuth not supported"}

        import httpx
        import time

        try:
            data = {
                "client_id": self.credentials.get("client_id", ""),
                "client_secret": self.credentials.get("client_secret", ""),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri or self.credentials.get("redirect_uri", ""),
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(self.OAUTH_TOKEN_URL, data=data)

                if resp.status_code == 200:
                    result = resp.json()
                    token_info = {
                        "access_token": result.get("access_token"),
                        "refresh_token": result.get("refresh_token"),
                        "expires_in": result.get("expires_in", 3600),
                        "token_type": result.get("token_type", "Bearer"),
                        "expires_at": time.time() + result.get("expires_in", 3600),
                    }
                    return token_info
                else:
                    return {"error": f"Token exchange failed: {resp.status_code}"}

        except Exception as e:
            return {"error": str(e)}

    async def refresh_token(self, refresh_token: str = None) -> dict:
        """
        刷新 access token
        参考 Postiz 的 refreshToken 方法

        Args:
            refresh_token: 刷新令牌（可选，默认使用存储的）

        Returns:
            新的 token 信息字典
        """
        if not self.supports_oauth():
            return {"error": "OAuth not supported"}

        import httpx
        import time

        refresh_token = refresh_token or self._refresh_token
        if not refresh_token:
            return {"error": "No refresh token available"}

        try:
            data = {
                "client_id": self.credentials.get("client_id", ""),
                "client_secret": self.credentials.get("client_secret", ""),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(self.OAUTH_TOKEN_URL, data=data)

                if resp.status_code == 200:
                    result = resp.json()
                    token_info = {
                        "access_token": result.get("access_token"),
                        "refresh_token": result.get("refresh_token", refresh_token),
                        "expires_in": result.get("expires_in", 3600),
                        "token_type": result.get("token_type", "Bearer"),
                        "expires_at": time.time() + result.get("expires_in", 3600),
                    }

                    # 更新内部状态
                    self._access_token = token_info["access_token"]
                    self._refresh_token = token_info.get("refresh_token", self._refresh_token)
                    self._token_expires_at = token_info["expires_at"]

                    return token_info
                else:
                    return {"error": f"Token refresh failed: {resp.status_code}"}

        except Exception as e:
            return {"error": str(e)}

    def is_token_expired(self) -> bool:
        """
        检查 access token 是否过期

        Returns:
            True if token is expired or not set
        """
        if not self._access_token:
            return True

        if self._token_expires_at:
            import time
            return time.time() >= self._token_expires_at

        return False

    def get_auth_headers(self) -> dict:
        """
        获取认证请求头
        参考 Postiz 的认证头生成

        Returns:
            包含认证信息的请求头字典
        """
        if self._access_token:
            return {
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
            }
        return {}

    def get_oauth_callback_url(self, request_url: str) -> dict:
        """
        解析 OAuth 回调 URL
        参考 AuthMixin.parse_oauth_callback

        Args:
            request_url: 回调 URL（包含 code、state 等参数）

        Returns:
            解析后的参数字典
        """
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(request_url)
        params = parse_qs(parsed.query)
        return {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化连接器

        如果是 OAuth 认证，此方法应该：
        1. 检查 token 是否过期
        2. 如果过期则自动刷新
        3. 验证 token 有效性

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    async def close(self):
        """关闭连接器（释放资源）"""
        pass

    @abstractmethod
    async def is_authenticated(self) -> bool:
        """检查是否已认证"""
        pass

    # -------------------------------------------------------------------------
    # 账号信息
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """获取账号信息"""
        pass

    # -------------------------------------------------------------------------
    # 内容发布
    # -------------------------------------------------------------------------

    @abstractmethod
    async def publish(self, content: PostContent) -> PostResult:
        """
        发布内容

        Args:
            content: 要发布的内容

        Returns:
            发布结果
        """
        pass

    @abstractmethod
    async def delete_post(self, post_id: str) -> bool:
        """
        删除帖子

        Args:
            post_id: 帖子 ID

        Returns:
            True if deletion successful
        """
        pass

    # -------------------------------------------------------------------------
    # 内容查询
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_post(self, post_id: str) -> Optional[dict]:
        """
        获取帖子详情

        Args:
            post_id: 帖子 ID

        Returns:
            帖子数据字典
        """
        pass

    @abstractmethod
    async def get_post_metrics(self, post_id: str) -> ContentMetrics:
        """
        获取帖子指标数据

        Args:
            post_id: 帖子 ID

        Returns:
            内容指标
        """
        pass

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------

    def get_platform_id(self) -> str:
        """获取平台标识"""
        return self.PLATFORM_ID

    def get_platform_name(self) -> str:
        """获取平台名称"""
        return self.PLATFORM_NAME

    def supports_content_type(self, content_type: ContentType) -> bool:
        """
        检查是否支持指定内容类型
        子类可覆盖此方法
        """
        return True

    def supports_media_format(self, media_format: MediaFormat) -> bool:
        """
        检查是否支持指定媒体格式
        子类可覆盖此方法
        """
        return True

    def get_max_media_count(self, content_type: ContentType) -> int:
        """
        获取指定内容类型支持的最大媒体数量
        子类可覆盖此方法
        """
        return 9  # 默认最多 9 张图

    # -------------------------------------------------------------------------
    # 错误处理（参考 Postiz 的 handleErrors 方法）
    # -------------------------------------------------------------------------

    def map_error(self, error: Exception, context: str = "") -> str:
        """
        将平台特定的错误映射为统一错误类型
        参考 Postiz 的 handleErrors 实现

        Args:
            error: 原始异常
            context: 错误上下文（如 "publish", "auth"）

        Returns:
            用户友好的错误消息
        """
        error_str = str(error).lower()

        # 认证相关错误
        if any(kw in error_str for kw in ["401", "unauthorized", "invalid token", "auth"]):
            return f"认证失败，请检查凭证是否有效 ({context})"

        # 限流相关错误
        if any(kw in error_str for kw in ["429", "rate limit", "too many requests"]):
            return f"请求过于频繁，请稍后再试 ({context})"

        # 网络相关错误
        if any(kw in error_str for kw in ["timeout", "connection", "network", "dns"]):
            return f"网络连接失败，请检查网络 ({context})"

        # 参数错误
        if any(kw in error_str for kw in ["400", "bad request", "invalid param"]):
            return f"请求参数错误 ({context}): {error}"

        # 服务器错误
        if any(kw in error_str for kw in ["500", "502", "503", "server error"]):
            return f"服务器错误，请稍后再试 ({context})"

        # 默认错误
        return f"操作失败 ({context}): {error}"


# =============================================================================
# 抽象工厂（用于运行时创建）
# =============================================================================

class ISocialMediaConnectorFactory(ABC):
    """
    社交媒体连接器工厂抽象

    定义创建连接器实例的契约。
    """

    @abstractmethod
    def create(self, credentials: dict) -> ISocialMediaConnector:
        """创建连接器实例"""
        pass

    @abstractmethod
    def get_platform_id(self) -> str:
        """获取平台标识"""
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """获取平台名称"""
        pass

    @abstractmethod
    def supports_content_types(self) -> list[ContentType]:
        """获取支持的内容类型"""
        pass

    @abstractmethod
    def supports_media_formats(self) -> list[MediaFormat]:
        """获取支持的媒体格式"""
        pass

    @abstractmethod
    def get_auth_types(self) -> list[str]:
        """获取支持的认证类型"""
        pass
