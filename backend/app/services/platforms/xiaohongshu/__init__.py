"""
YLCraft — 小红书平台模块

提供小红书平台的数据采集能力：
- XiaohongshuClient：搜索+详情（API 模式）
- parser：图文链接 HTML 解析（降级 fallback）
"""

from .client import XiaohongshuClient
from .parser import XhsNote, XhsParserService, get_xhs_parser

__all__ = [
    "XiaohongshuClient",
    "XhsNote",
    "XhsParserService",
    "get_xhs_parser",
]
