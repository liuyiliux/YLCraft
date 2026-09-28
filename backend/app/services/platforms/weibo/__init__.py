"""YLCraft — 微博平台模块。

搜索端点在真实浏览器内实测确认（2026-09-27）：

    GET https://m.weibo.cn/api/container/getIndex
        ?containerid=100103type=1&q=美食&page_type=searchall&page=1
    → {"ok":1,"data":{"cards":[...],"cardlistInfo":{"total":739}}}

⚠️ 必须登录：不带 Cookie 时返回 HTTP 432 / ok=-100。
"""
from .client import (
    WeiboClient,
    WeiboLoginRequiredError,
    parse_mblog,
    parse_mblog_detail,
)

__all__ = [
    "WeiboClient",
    "WeiboLoginRequiredError",
    "parse_mblog",
    "parse_mblog_detail",
]
