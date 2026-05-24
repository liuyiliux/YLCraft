"""
YLCraft — 平台连接器模型（统一凭证架构）

唯一凭证存储：所有平台的凭证统一管理
- Cookie（抖音、B站、小红书等）→ credentials (JSON) + cookie_content (Netscape)
- API Key（AI 模型、第三方服务）→ credentials (JSON)
- OAuth Token（社交媒体发布）→ credentials (JSON)
- 账号密码（FTP、云存储等）→ credentials (JSON)

核心原则：一份 Cookie，多处使用
- cookie_content (Netscape 格式) → 视频解析 CookieManager
- credentials (JSON 格式) → 社交媒体发布 ConnectorRegistry / 素材采集 Crawler
"""

from __future__ import annotations

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Text, String, DateTime, Boolean, Integer
from datetime import datetime, timezone
from typing import Optional, Any
import json
import enum


class PlatformType(str, enum.Enum):
    """平台类型"""
    # 内容平台
    XHS = "xhs"            # 小红书
    DOUYIN = "douyin"       # 抖音
    KUAISHOU = "kuaishou"   # 快手
    BILIBILI = "bilibili"   # B站
    WEIBO = "weibo"          # 微博
    ZHIHU = "zhihu"          # 知乎
    YOUTUBE = "youtube"      # YouTube
    TIKTOK = "tiktok"       # TikTok
    TWITTER = "twitter"      # Twitter/X
    TELEGRAM = "telegram"    # Telegram

    # AI 服务
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MINIMAX = "minimax"
    GOOGLE = "google"

    # 存储/发布
    WEBDAY = "webdav"
    S3 = "s3"
    FTP = "ftp"


class AuthType(str, enum.Enum):
    """认证类型"""
    COOKIE = "cookie"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    PASSWORD = "password"
    NONE = "none"


class ConnectionStatus(str, enum.Enum):
    """连接状态"""
    ACTIVE = "active"        # 有效
    EXPIRED = "expired"      # 已过期
    FAILED = "failed"        # 连接失败
    UNKNOWN = "unknown"      # 未测试


class AcquisitionMethod(str, enum.Enum):
    """凭证获取方式"""
    MANUAL = "manual"           # 手动粘贴
    PLAYWRIGHT = "playwright"  # Playwright 浏览器自动化
    QRCODE = "qrcode"          # 二维码扫码


class PlatformConnectionBase(SQLModel):
    """平台连接基础模型"""
    platform: PlatformType = Field(..., description="平台标识")
    name: str = Field(..., description="用户定义的连接名称")
    auth_type: AuthType = Field(AuthType.COOKIE, description="认证类型")
    status: ConnectionStatus = Field(ConnectionStatus.UNKNOWN, description="连接状态")

    # 凭证数据（JSON 加密存储）
    credentials: str = Field("", description="凭证数据（JSON 字符串，建议加密）")

    # 元数据
    description: Optional[str] = Field("", description="备注说明")
    last_used: Optional[datetime] = Field(None, description="最后使用时间")
    last_tested: Optional[datetime] = Field(None, description="最后测试时间")
    error_message: Optional[str] = Field("", description="错误信息")

    # ===== 凭证获取方式 =====
    acquisition_method: AcquisitionMethod = Field(
        AcquisitionMethod.MANUAL,
        description="凭证获取方式：manual/playwright/qrcode"
    )

    # ===== 账号信息 =====
    account_id: Optional[str] = Field(None, description="平台账号 ID")
    account_name: Optional[str] = Field(None, description="账号名称/昵称")
    account_avatar: Optional[str] = Field(None, description="账号头像 URL")
    account_url: Optional[str] = Field(None, description="账号主页 URL")

    # ===== Cookie 内容（Netscape 格式，视频解析用） =====
    cookie_content: Optional[str] = Field(
        None, sa_type=Text,
        description="Netscape 格式 Cookie（视频解析用）"
    )
    domains: Optional[str] = Field(
        None, max_length=1000,
        description="关联域名列表（逗号分隔，如：.douyin.com,.iesdouyin.com）"
    )
    test_url: Optional[str] = Field(
        None, max_length=500,
        description="测试链接（用于 Cookie 有效性测试）"
    )

    # ===== 统计信息 =====
    success_count: int = Field(0, description="成功次数")
    fail_count: int = Field(0, description="失败次数")


class PlatformConnection(PlatformConnectionBase, table=True):
    """平台连接数据库模型"""
    __tablename__ = "platform_connections"

    id: str = Field(primary_key=True, description="连接ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="更新时间"
    )

    def set_credentials(self, data: dict):
        """设置凭证数据（可在此处添加加密）"""
        self.credentials = json.dumps(data, ensure_ascii=False)

    def get_credentials(self) -> dict:
        """获取凭证数据（可在此处添加解密）"""
        if not self.credentials:
            return {}
        try:
            return json.loads(self.credentials)
        except Exception:
            return {}

    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def update_success(self):
        """记录成功使用"""
        self.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        self.success_count += 1
        self.update_timestamp()

    def update_failure(self, error: str = ""):
        """记录失败"""
        self.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        self.fail_count += 1
        self.error_message = error
        self.update_timestamp()


class PlatformConnectionCreate(SQLModel):
    """创建平台连接请求"""
    platform: PlatformType
    name: str
    auth_type: AuthType = AuthType.COOKIE
    credentials: dict = Field(default_factory=dict, description="凭证数据")
    description: str = ""
    # 获取方式 / 账号信息 / Cookie
    acquisition_method: AcquisitionMethod = AcquisitionMethod.MANUAL
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_avatar: Optional[str] = None
    account_url: Optional[str] = None
    cookie_content: Optional[str] = None
    domains: Optional[str] = None
    test_url: Optional[str] = None


class PlatformConnectionUpdate(SQLModel):
    """更新平台连接请求"""
    name: Optional[str] = None
    auth_type: Optional[AuthType] = None
    credentials: Optional[dict] = None
    description: Optional[str] = None
    status: Optional[ConnectionStatus] = None
    acquisition_method: Optional[AcquisitionMethod] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_avatar: Optional[str] = None
    account_url: Optional[str] = None
    cookie_content: Optional[str] = None
    domains: Optional[str] = None
    test_url: Optional[str] = None


class PlatformConnectionResponse(SQLModel):
    """平台连接响应"""
    id: str
    platform: PlatformType
    name: str
    auth_type: AuthType
    status: ConnectionStatus
    description: str
    last_used: Optional[datetime] = None
    last_tested: Optional[datetime] = None
    created_at: datetime
    has_credentials: bool = False  # 是否配置了凭证（不返回实际凭证）
    error_message: Optional[str] = None
    acquisition_method: AcquisitionMethod = AcquisitionMethod.MANUAL
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_avatar: Optional[str] = None
    account_url: Optional[str] = None
    has_cookie_content: bool = False  # 是否配置了 Netscape Cookie
    domains: Optional[str] = None
    test_url: Optional[str] = None
    success_count: int = 0
    fail_count: int = 0

    @classmethod
    def from_db(cls, conn: PlatformConnection) -> "PlatformConnectionResponse":
        return cls(
            id=conn.id,
            platform=conn.platform,
            name=conn.name,
            auth_type=conn.auth_type,
            status=conn.status,
            description=conn.description or "",
            last_used=conn.last_used,
            last_tested=conn.last_tested,
            created_at=conn.created_at,
            has_credentials=bool(conn.credentials),
            error_message=conn.error_message,
            acquisition_method=conn.acquisition_method,
            account_id=conn.account_id,
            account_name=conn.account_name,
            account_avatar=conn.account_avatar,
            account_url=conn.account_url,
            has_cookie_content=bool(conn.cookie_content),
            domains=conn.domains,
            test_url=conn.test_url,
            success_count=conn.success_count,
            fail_count=conn.fail_count,
        )
