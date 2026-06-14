"""
YLCraft — 小说服务包
"""
from app.services.novel.crawler import NovelCrawler, BiqigecnCrawler, get_crawler
from app.services.novel.downloader import NovelDownloader
from app.services.novel.qidian_parser import QidianVipParser, get_qidian_vip_parser
from app.services.novel.qidian_crawler import QidianCrawler

__all__ = [
    'NovelCrawler',
    'BiqigecnCrawler',
    'get_crawler',
    'NovelDownloader',
    'QidianVipParser',
    'get_qidian_vip_parser',
    'QidianCrawler',
]
