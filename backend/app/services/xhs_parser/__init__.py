"""YLCraft — 小红书图文链接解析服务

Usage:
    from app.services.xhs_parser import get_xhs_parser, XhsNote

    parser = get_xhs_parser()
    note = parser.parse("https://www.xiaohongshu.com/explore/xxxxx")
"""

from app.services.xhs_parser.service import (
    XhsNote,
    XhsParserService,
    get_xhs_parser,
)

__all__ = [
    "XhsNote",
    "XhsParserService",
    "get_xhs_parser",
]
