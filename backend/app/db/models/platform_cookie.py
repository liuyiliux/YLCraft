"""
YLCraft — 平台 Cookie 配置模型

存储各平台的 Cookie 配置和解析规则
"""

from __future__ import annotations

from sqlmodel import SQLModel, Field
from sqlalchemy import String, DateTime, Text, Boolean, Integer
from datetime import datetime, timezone
from typing import Optional


# 预设平台数据（用于初始化，模块级别常量，避免触发 Pydantic 字段检测）
PLATFORM_COOKIE_PRESETS = [
    {"id": "douyin", "display_name": "抖音", "domains": ".douyin.com,.iesdouyin.com,v.douyin.com", "test_url": "https://www.douyin.com/video/7322548203919920387"},
    {"id": "tiktok", "display_name": "TikTok", "domains": ".tiktok.com", "test_url": "https://www.tiktok.com/@tiktok/video/7043492019477857454"},
    {"id": "kuaishou", "display_name": "快手", "domains": ".kuaishou.com,.gifshow.com,v.kuaishou.com", "test_url": "https://www.kuaishou.com/short-video/3xpdvbqr5y5g"},
    {"id": "bilibili", "display_name": "B站", "domains": ".bilibili.com,b23.tv", "test_url": "https://www.bilibili.com/video/BV1xx411c7XD"},
    {"id": "xiaohongshu", "display_name": "小红书", "domains": ".xiaohongshu.com,xhslink.com", "test_url": "https://www.xiaohongshu.com/explore/6543a0cb000000003d0170f6"},
    {"id": "weibo", "display_name": "微博", "domains": ".weibo.com,t.cn", "test_url": "https://weibo.com/7741392674/status/5028368969279244"},
    {"id": "youtube", "display_name": "YouTube", "domains": ".youtube.com,youtu.be", "test_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    {"id": "twitter", "display_name": "Twitter/X", "domains": ".twitter.com,.x.com,t.co,pbs.twimg.com,abs.twimg.com", "test_url": "https://x.com/Twitter/status/12345"},
    {"id": "telegram", "display_name": "Telegram", "domains": ".telegram.org,t.me,web.telegram.org", "test_url": "https://t.me/telegram"},
]


class PlatformCookie(SQLModel, table=True):
    """平台 Cookie 数据库模型"""
    __tablename__ = "platform_cookies"

    id: str = Field(primary_key=True, description="平台标识（如：douyin, twitter, xhs）")
    display_name: str = Field(..., max_length=100, description="显示名称（如：抖音, Twitter, 小红书）")
    domains: Optional[str] = Field(None, max_length=1000, description="关联域名列表（逗号分隔，如：.douyin.com,.iesdouyin.com）")
    cookie_content: Optional[str] = Field(None, sa_type=Text, description="Cookie 内容（Netscape 格式）")
    test_url: Optional[str] = Field(None, max_length=500, description="测试链接（用于 Cookie 有效性测试）")
    is_active: bool = Field(True, description="是否启用")
    description: Optional[str] = Field("", max_length=500, description="备注说明")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="更新时间"
    )


class PlatformCookieCreate(SQLModel):
    """创建平台 Cookie 请求"""
    id: str
    display_name: str
    domains: Optional[str] = None
    cookie_content: Optional[str] = None
    test_url: Optional[str] = None
    description: str = ""


class PlatformCookieUpdate(SQLModel):
    """更新平台 Cookie 请求"""
    display_name: Optional[str] = None
    domains: Optional[str] = None
    cookie_content: Optional[str] = None
    test_url: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
