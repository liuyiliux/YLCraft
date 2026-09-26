"""
YLCraft — 抖音平台模块

搜索端点由 browser-skill 接管用户已登录 Chrome 抓包确认（2026-09-26）：
  GET /aweme/v1/web/general/search/single/   → status_code=0
"""
from .client import DouyinClient, parse_search_item

__all__ = ["DouyinClient", "parse_search_item"]
