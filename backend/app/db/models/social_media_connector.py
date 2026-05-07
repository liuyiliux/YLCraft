"""
YLCraft — 社交媒体连接器模型

管理各自媒体平台的 Cookie / OAuth 凭证
用于内容发布、账号管理等功能
"""

from __future__ import annotations

from sqlmodel import SQLModel, Field
from sqlalchemy import String, DateTime, Text, Boolean
from datetime import datetime, timezone
from typing import Optional
import json
import enum


class SocialMediaPlatform(str, enum.Enum):
    """自媒体/社交媒体平台"""
    XHS = "xhs"              # 小红书
    DOUYIN = "douyin"        # 抖音
    KUAISHOU = "kuaishou"    # 快手
    BILIBILI = "bilibili"    # B站
    WEIBO = "weibo"          # 微博
    ZHIHU = "zhihu"          # 知乎
    YOUTUBE = "youtube"       # YouTube
    TIKTOK = "tiktok"        # TikTok
    REDDIT = "reddit"        # Reddit
    TWITTER = "twitter"      # Twitter/X
    INSTAGRAM = "instagram"   # Instagram
    FACEBOOK = "facebook"    # Facebook


class SocialAuthType(str, enum.Enum):
    """认证类型"""
    COOKIE = "cookie"       # Cookie 认证
    OAUTH2 = "oauth2"       # OAuth2.0
    PASSWORD = "password"   # 账号密码
    QR_CODE = "qr_code"     # 二维码扫码


class SocialConnectionStatus(str, enum.Enum):
    """连接状态"""
    ACTIVE = "active"       # 有效
    EXPIRED = "expired"     # 已过期
    FAILED = "failed"       # 连接失败
    PENDING = "pending"     # 待验证（OAuth 进行中）
    UNKNOWN = "unknown"      # 未测试


class SocialMediaConnectorBase(SQLModel):
    """社交媒体连接基础模型"""
    platform: SocialMediaPlatform = Field(..., description="平台标识")
    name: str = Field(..., description="用户定义的连接名称")
    auth_type: SocialAuthType = Field(SocialAuthType.COOKIE, description="认证类型")

    # 凭证数据（JSON 加密存储）
    credentials: str = Field("", description="凭证数据（JSON 字符串）")

    # 账号信息
    account_id: Optional[str] = Field(None, description="平台账号 ID")
    account_name: Optional[str] = Field(None, description="账号名称/昵称")
    account_avatar: Optional[str] = Field(None, description="账号头像 URL")
    account_url: Optional[str] = Field(None, description="账号主页 URL")

    # 状态
    status: SocialConnectionStatus = Field(SocialConnectionStatus.UNKNOWN, description="连接状态")

    # 权限范围
    scopes: str = Field("[]", description="OAuth 权限范围 JSON")

    # 元数据
    description: Optional[str] = Field("", description="备注说明")
    last_used: Optional[datetime] = Field(None, description="最后使用时间")
    last_tested: Optional[datetime] = Field(None, description="最后测试时间")
    error_message: Optional[str] = Field(None, description="错误信息")

    # 性能指标
    success_count: int = Field(0, description="成功次数")
    fail_count: int = Field(0, description="失败次数")


class SocialMediaConnector(SocialMediaConnectorBase, table=True):
    """社交媒体连接数据库模型"""
    __tablename__ = "social_media_connectors"

    id: str = Field(primary_key=True, description="连接ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="更新时间"
    )

    def set_credentials(self, data: dict):
        """设置凭证数据（可在此处添加加密）"""
        self.credentials = json.dumps(data)

    def get_credentials(self) -> dict:
        """获取凭证数据"""
        if not self.credentials:
            return {}
        try:
            return json.loads(self.credentials)
        except Exception:
            return {}

    def get_scopes(self) -> list[str]:
        """获取权限范围"""
        if not self.scopes:
            return []
        try:
            return json.loads(self.scopes)
        except Exception:
            return []

    def set_scopes(self, scopes: list[str]):
        """设置权限范围"""
        self.scopes = json.dumps(scopes)

    def update_success(self):
        """记录成功使用"""
        self.last_used = datetime.now(timezone.utc)
        self.success_count += 1

    def update_failure(self, error: str = ""):
        """记录失败"""
        self.last_used = datetime.now(timezone.utc)
        self.fail_count += 1
        self.error_message = error


class SocialMediaConnectorCreate(SQLModel):
    """创建社交媒体连接请求"""
    platform: SocialMediaPlatform
    name: str
    auth_type: SocialAuthType = SocialAuthType.COOKIE
    credentials: dict = Field(default_factory=dict, description="凭证数据")
    scopes: list[str] = Field(default_factory=list, description="权限范围")
    description: str = ""


class SocialMediaConnectorUpdate(SQLModel):
    """更新社交媒体连接请求"""
    name: Optional[str] = None
    auth_type: Optional[SocialAuthType] = None
    credentials: Optional[dict] = None
    scopes: Optional[list[str]] = None
    description: Optional[str] = None
    status: Optional[SocialConnectionStatus] = None


class SocialMediaConnectorResponse(SQLModel):
    """社交媒体连接响应"""
    id: str
    platform: SocialMediaPlatform
    name: str
    auth_type: SocialAuthType
    status: SocialConnectionStatus
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_avatar: Optional[str] = None
    account_url: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    description: str
    last_used: Optional[datetime] = None
    last_tested: Optional[datetime] = None
    success_count: int = 0
    fail_count: int = 0
    created_at: datetime
    has_credentials: bool = False
    error_message: Optional[str] = None

    @classmethod
    def from_db(cls, conn: SocialMediaConnector) -> "SocialMediaConnectorResponse":
        return cls(
            id=conn.id,
            platform=conn.platform,
            name=conn.name,
            auth_type=conn.auth_type,
            status=conn.status,
            account_id=conn.account_id,
            account_name=conn.account_name,
            account_avatar=conn.account_avatar,
            account_url=conn.account_url,
            scopes=conn.get_scopes(),
            description=conn.description or "",
            last_used=conn.last_used,
            last_tested=conn.last_tested,
            success_count=conn.success_count,
            fail_count=conn.fail_count,
            created_at=conn.created_at,
            has_credentials=bool(conn.credentials),
            error_message=conn.error_message,
        )
