"""
YLCraft — 小说服务包
"""

from app.services.novel.crawler import NovelCrawler, BiqigecnCrawler, get_crawler
from app.services.novel.downloader import NovelDownloader

__all__ = ['NovelCrawler', 'BiqigecnCrawler', 'get_crawler', 'NovelDownloader']
