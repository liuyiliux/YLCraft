"""YLCraft — Telegram 数据模型。

## 为什么单独一个模块

其它平台的返回结构（SearchResult / NoteDetail）是"内容 → 图片/视频"，
而 Telegram 是**消息流**：一条消息可能同时有文本 + 多图 + 视频，
还可能带转发/回复/浏览量。硬塞进 SearchResult 会丢字段，
所以这里定义 Telegram 自己的结构，再由 client 转成通用形状。

## 两种数据源（对应前端两个 tab）

| tab | 数据源 | 是否需登录 |
|-----|--------|-----------|
| 频道消息 | `t.me/s/<channel>` 公开预览页 | 否 |
| 全网搜索 | MTProto `messages.SearchGlobal` | 是 |
| 我的频道 | MTProto `messages.GetDialogs` | 是 |

A 方案（免登录）解析 HTML，B 方案（登录）走 telethon。
两个数据源**共用这里的模型**，前端不用区分。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TelegramChannel:
    """频道元信息（来自 t.me/s 页头或 MTProto）。"""

    id: str = ""            # 频道 username（如 durov）或数字 id
    username: str = ""      # 不带 @ 的 username
    title: str = ""         # 频道显示名
    description: str = ""   # 简介（t.me/s 页头有）
    avatar: str = ""
    subscribers: int = 0
    # 来源标记：web_preview（A 方案）/ mtproto（B 方案）
    source: str = "web_preview"
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TelegramMessage:
    """一条频道消息。

    ⚠️ 一条消息可能**同时**有文本和多张图/一个视频 ——
    不要把 type 当成互斥的类型（这与小红书的"图文 or 视频"不同）。
    """

    id: str = ""                 # 消息 id（数字，字符串化）
    channel: str = ""            # 所属频道 username
    channel_title: str = ""
    text: str = ""               # 正文（已去掉 HTML 标签）
    html: str = ""               # 原始 HTML（前端富文本渲染用）
    date: str = ""               # ISO 时间
    views: int = 0
    images: List[str] = field(default_factory=list)   # 图片直链
    video: str = ""              # 视频直链（可能为空 —— 多半要 yt-dlp 下）
    video_cover: str = ""
    duration: int = 0
    # 转发来源（转发的消息才有）
    forward_from: str = ""
    # 链接预览 / 附加链接
    links: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_media(self) -> bool:
        return bool(self.images or self.video)

    @property
    def content_type(self) -> str:
        """给通用 SearchResult.type 用。

        一条消息同时有图和视频时算 video（视频更需要"播放"语义）。
        """
        if self.video:
            return "video"
        if self.images:
            return "image"
        return "text"

    def page_url(self) -> str:
        """该消息的网页地址（前端"看原文"用）。"""
        return f"https://t.me/{self.channel}/{self.id}" if self.channel else ""


@dataclass
class TelegramDialogsPage:
    """「我的频道」一页数据。"""

    channels: List[TelegramChannel] = field(default_factory=list)
    total: int = 0
