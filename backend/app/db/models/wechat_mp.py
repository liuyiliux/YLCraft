"""
微信公众号下载记录模型
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


class WechatMPDownload(SQLModel, table=True):
    """微信公众号文章下载记录"""
    __tablename__ = "wechat_mp_downloads"

    id: str = Field(primary_key=True, description="下载记录 ID")
    conn_id: str = Field(description="关联 platform_connections.id")

    # 公众号信息
    account_name: str = Field("", description="公众号名称")
    account_fake_id: str = Field("", description="公众号 FakeID")

    # 文章信息
    article_title: str = Field("", description="文章标题")
    article_url: str = Field("", description="文章链接 (mp.weixin.qq.com)")
    content_url: str = Field("", description="微信 content_url")
    cover_url: str = Field("", description="封面图 URL")
    digest: str = Field("", description="摘要")
    publish_time: Optional[datetime] = Field(None, description="发布时间")

    # 下载状态
    status: str = Field("pending", description="pending / downloading / done / failed")
    format: str = Field("md", description="导出格式: md / html / epub / pdf")
    file_path: str = Field("", description="本地文件路径")
    file_size: int = Field(0, description="文件大小（字节）")
    asset_id: str = Field("", description="关联素材库 asset.id")
    error_message: str = Field("", description="错误信息")

    # 时间戳
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="创建时间",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="更新时间",
    )


class WechatMPDownloadCreate(SQLModel):
    """创建下载记录请求"""
    conn_id: str
    account_name: str = ""
    account_fake_id: str = ""
    article_title: str = ""
    article_url: str
    content_url: str = ""
    cover_url: str = ""
    digest: str = ""
    format: str = "md"


class WechatMPDownloadResponse(SQLModel):
    """下载记录响应"""
    id: str
    conn_id: str
    account_name: str
    account_fake_id: str
    article_title: str
    article_url: str
    content_url: str
    cover_url: str
    digest: str
    publish_time: Optional[datetime] = None
    status: str
    format: str
    file_path: str
    file_size: int
    asset_id: str
    error_message: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db(cls, record: WechatMPDownload) -> "WechatMPDownloadResponse":
        return cls(
            id=record.id,
            conn_id=record.conn_id,
            account_name=record.account_name,
            account_fake_id=record.account_fake_id,
            article_title=record.article_title,
            article_url=record.article_url,
            content_url=record.content_url,
            cover_url=record.cover_url,
            digest=record.digest,
            publish_time=record.publish_time,
            status=record.status,
            format=record.format,
            file_path=record.file_path,
            file_size=record.file_size,
            asset_id=record.asset_id,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
