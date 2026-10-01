"""
YLCraft — Telegram 平台

两条能力线：
  · A 方案（免登录）：`web_preview.py` + `parser.py` —— 公开频道消息、
    **频道内关键词搜索**（`?q=`）
  · B 方案（需登录）：`mtproto.py` + `mtproto_data.py` —— 跨频道全局搜索、
    我加入的频道、私有频道

统一入口是 `client.py::TelegramClient`（按 search_type 分派）。
"""
from __future__ import annotations

from ..base import BasePlatformClient
from .client import TelegramClient

__all__ = ["TelegramClient"]
