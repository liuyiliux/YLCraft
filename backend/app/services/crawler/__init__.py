"""
Crawler Service Module
"""

from app.services.crawler.service import (
    CrawlerService,
    CrawlerResult,
    CrawlerTaskResponse,
    SearchRequest,
    get_crawler_service,
    CrawlerPlatform,
)

__all__ = [
    "CrawlerService",
    "CrawlerResult",
    "CrawlerTaskResponse",
    "SearchRequest",
    "get_crawler_service",
    "CrawlerPlatform",
]
