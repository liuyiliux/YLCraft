"""
YLCraft — Cookie 获取抽象基类与数据模型

定义：
- AcquisitionSession：内存会话模型（追踪获取过程状态）
- AcquisitionResult：获取结果
- PlatformDetector：登录检测器（Playwright 用）
- QrcodeAdapter：二维码适配器（QrCode 用）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AcquisitionStatus(str, Enum):
    """获取会话状态"""
    INITIALIZING = "initializing"                   # 初始化中
    BROWSER_LAUNCHING = "browser_launching"         # Playwright: 浏览器启动中
    PAGE_LOADING = "page_loading"                   # Playwright: 页面加载中
    WAITING_FOR_LOGIN = "waiting_for_login"         # 等待用户登录
    QR_GENERATED = "qr_generated"                   # QrCode: 二维码已生成
    QR_SCANNED = "qr_scanned"                       # QrCode: 已扫码，等待确认
    COOKIES_EXTRACTING = "cookies_extracting"       # 正在提取 Cookie
    COOKIES_EXTRACTED = "cookies_extracted"         # Cookie 已提取
    SAVING = "saving"                                # 正在保存
    SUCCESS = "success"                              # 成功
    FAILED = "failed"                                # 失败
    CANCELLED = "cancelled"                          # 已取消
    EXPIRED = "expired"                              # 二维码过期


# 状态消息映射
STATUS_MESSAGES = {
    AcquisitionStatus.INITIALIZING: "正在初始化...",
    AcquisitionStatus.BROWSER_LAUNCHING: "浏览器启动中...",
    AcquisitionStatus.PAGE_LOADING: "页面加载中...",
    AcquisitionStatus.WAITING_FOR_LOGIN: "请在浏览器中完成登录",
    AcquisitionStatus.QR_GENERATED: "二维码已生成，请扫描",
    AcquisitionStatus.QR_SCANNED: "已扫描，请在手机上确认",
    AcquisitionStatus.COOKIES_EXTRACTING: "正在提取 Cookie...",
    AcquisitionStatus.COOKIES_EXTRACTED: "Cookie 提取成功",
    AcquisitionStatus.SAVING: "正在保存...",
    AcquisitionStatus.SUCCESS: "Cookie 获取成功！",
    AcquisitionStatus.FAILED: "获取失败",
    AcquisitionStatus.CANCELLED: "已取消",
    AcquisitionStatus.EXPIRED: "二维码已过期，请刷新重试",
}


def get_status_message(status: AcquisitionStatus) -> str:
    """获取状态对应的中文消息"""
    return STATUS_MESSAGES.get(status, "未知状态")


@dataclass
class AcquisitionSession:
    """Cookie 获取会话（内存模型，不持久化到数据库）"""
    session_id: str
    platform: str                       # xhs / douyin / bilibili / ...
    method: str                         # playwright / qrcode
    status: AcquisitionStatus = AcquisitionStatus.INITIALIZING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 结果
    cookies_raw: Optional[str] = None
    cookies_array: Optional[list[dict]] = None
    connector_id: Optional[str] = None  # 关联的 PlatformConnection ID

    # Playwright 特有
    browser_context: Optional[object] = None  # BrowserContext 引用
    page_url: Optional[str] = None

    # QrCode 特有
    qr_image_base64: Optional[str] = None
    qr_session_key: Optional[str] = None      # 平台侧会话 ID

    # 错误
    error_message: Optional[str] = None

    # 连接器名称
    connector_name: str = ""

    @property
    def is_terminal(self) -> bool:
        """是否已到达终态"""
        return self.status in (
            AcquisitionStatus.SUCCESS,
            AcquisitionStatus.FAILED,
            AcquisitionStatus.CANCELLED,
            AcquisitionStatus.EXPIRED,
        )


@dataclass
class AcquisitionResult:
    """Cookie 获取结果"""
    success: bool
    cookies_raw: str = ""                  # key=value; key2=value2 格式
    cookies_array: Optional[list[dict]] = None  # Playwright/QrCode 提取的完整 Cookie 列表
    cookie_content: str = ""              # Netscape 格式（视频解析用）
    connector_id: Optional[str] = None     # 创建/更新的 PlatformConnection ID
    error_message: str = ""
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_avatar: Optional[str] = None
    account_url: Optional[str] = None


class PlatformDetector(ABC):
    """登录检测器（Playwright 用）"""

    @abstractmethod
    async def detect(self, page) -> bool:
        """检测用户是否已登录"""
        pass

    @abstractmethod
    async def extract_account_info(self, page) -> dict:
        """
        提取账号信息（登录成功后调用）
        返回: {"account_id": "", "account_name": "", "account_avatar": "", "account_url": ""}
        """
        pass


class QrcodeAdapter(ABC):
    """二维码适配器（QrCode 用）"""

    @abstractmethod
    async def generate_qrcode(self) -> dict:
        """
        生成登录二维码

        Returns:
            {
                "qr_image_base64": "data:image/png;base64,...",
                "session_key": "xxx",
                "expires_in": 120,
            }
        """
        pass

    @abstractmethod
    async def check_status(self, session_key: str) -> dict:
        """
        检查扫码状态

        Returns:
            {
                "status": "waiting|scanned|confirmed|expired",
                "cookies": [...],  # 仅 confirmed 时有值
            }
        """
        pass


# =============================================================================
# 平台配置：登录 URL、User-Agent 等
# =============================================================================

PLATFORM_LOGIN_URLS = {
    "xhs": "https://www.xiaohongshu.com",
    "douyin": "https://www.douyin.com",
    "kuaishou": "https://www.kuaishou.com",
    "bilibili": "https://www.bilibili.com",
    "weibo": "https://weibo.com",
    "zhihu": "https://www.zhihu.com",
    "youtube": "https://www.youtube.com",
    "tiktok": "https://www.tiktok.com",
    "twitter": "https://x.com",
    "telegram": "https://web.telegram.org",
    # 微信公众号公众平台后台登录页
    "wechat_mp": "https://mp.weixin.qq.com/",
}

PLATFORM_DOMAINS = {
    "xhs": ".xiaohongshu.com,xhslink.com",
    "douyin": ".douyin.com,.iesdouyin.com,v.douyin.com",
    "kuaishou": ".kuaishou.com,.gifshow.com,v.kuaishou.com",
    "bilibili": ".bilibili.com,b23.tv",
    "weibo": ".weibo.com,t.cn",
    "zhihu": ".zhihu.com",
    "youtube": ".youtube.com,youtu.be",
    "tiktok": ".tiktok.com",
    "twitter": ".twitter.com,.x.com,t.co,pbs.twimg.com,abs.twimg.com",
    "telegram": ".telegram.org,t.me",
    # 微信公众号相关域名
    "wechat_mp": ".weixin.qq.com,.qq.com,mp.weixin.qq.com",
}

PLATFORM_TEST_URLS = {
    "xhs": "https://www.xiaohongshu.com/explore/6543a0cb000000003d0170f6",
    "douyin": "https://www.douyin.com/video/7322548203919920387",
    "kuaishou": "https://www.kuaishou.com/short-video/3xpdvbqr5y5g",
    "bilibili": "https://www.bilibili.com/video/BV1xx411c7XD",
    "weibo": "https://weibo.com/7741392674/status/5028368969279244",
    "zhihu": "https://www.zhihu.com/question/264939990",
    "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "tiktok": "https://www.tiktok.com/@tiktok/video/7043492019477857454",
    "twitter": "https://x.com/Twitter/status/12345",
    "telegram": "https://t.me/telegram",
    # 微信公众号登录后默认跳到首页
    "wechat_mp": "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

PLATFORM_USER_AGENTS = {
    "xhs": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "douyin": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "kuaishou": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "bilibili": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "weibo": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "zhihu": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # 微信公众号需要与 bizlogin 端点校验一致的 Chrome 149
    "wechat_mp": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
}


def get_login_url(platform: str) -> str:
    """获取平台登录页 URL"""
    return PLATFORM_LOGIN_URLS.get(platform, "https://www.google.com")


def get_user_agent(platform: str) -> str:
    """获取平台对应的 User-Agent"""
    return PLATFORM_USER_AGENTS.get(platform, DEFAULT_USER_AGENT)


def get_platform_domains(platform: str) -> str:
    """获取平台关联域名"""
    return PLATFORM_DOMAINS.get(platform, "")


def get_platform_test_url(platform: str) -> str:
    """获取平台测试链接"""
    return PLATFORM_TEST_URLS.get(platform, "")
