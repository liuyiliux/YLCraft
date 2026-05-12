"""
YLCraft — 小说爬虫服务
支持多站点小说搜索、目录抓取、章节下载
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from typing import Optional
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NovelCrawler:
    """小说爬虫基类"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.verify_ssl = False
    
    def search(self, keyword: str) -> list[dict]:
        """搜索小说 - 子类实现"""
        raise NotImplementedError
    
    def get_catalog(self, book_url: str) -> list[dict]:
        """获取目录 - 子类实现"""
        raise NotImplementedError
    
    def download_chapter(self, chapter_url: str) -> str:
        """下载章节内容 - 子类实现"""
        raise NotImplementedError


class BiqigecnCrawler(NovelCrawler):
    """笔趣阁爬虫（biquge.cn）"""
    
    def __init__(self, timeout: int = 10):
        super().__init__(timeout)
        self.base_url = "https://www.biquge.com.cn"
    
    def search(self, keyword: str) -> list[dict]:
        """搜索小说"""
        try:
            search_url = f"{self.base_url}/search"
            params = {"q": keyword}
            resp = requests.get(search_url, params=params, headers=self.headers, timeout=self.timeout, verify=self.verify_ssl)
            resp.encoding = 'utf-8'
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            
            # 解析搜索结果（根据实际HTML结构调整）
            for item in soup.select('.result-item, .book-item'):
                title_elem = item.select_one('.book-title, .result-title')
                author_elem = item.select_one('.book-author, .result-author')
                cover_elem = item.select_one('.book-cover img, .result-cover img')
                link_elem = item.select_one('a')
                
                if title_elem and link_elem:
                    results.append({
                        'title': title_elem.text.strip(),
                        'author': author_elem.text.strip() if author_elem else '未知',
                        'url': self.base_url + link_elem.get('href', '') if link_elem.get('href', '').startswith('/') else link_elem.get('href', ''),
                        'cover': cover_elem.get('src', '') if cover_elem else '',
                        'source_site': 'biqigecn',
                    })
            
            return results
        except Exception as e:
            print(f"搜索失败: {e}")
            return []
    
    def get_catalog(self, book_url: str) -> list[dict]:
        """获取目录"""
        try:
            resp = requests.get(book_url, headers=self.headers, timeout=self.timeout, verify=self.verify_ssl)
            resp.encoding = 'utf-8'
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            chapters = []
            
            # 解析目录（根据实际HTML结构调整）
            for idx, item in enumerate(soup.select('.chapter-item, .catalog-item, dd a'), 1):
                title = item.text.strip()
                url = item.get('href', '')
                
                if url and title:
                    # 处理相对路径
                    if url.startswith('/'):
                        url = self.base_url + url
                    
                    chapters.append({
                        'index': idx,
                        'title': title,
                        'url': url,
                    })
            
            return chapters
        except Exception as e:
            print(f"获取目录失败: {e}")
            return []
    
    def download_chapter(self, chapter_url: str) -> str:
        """下载章节内容"""
        try:
            resp = requests.get(chapter_url, headers=self.headers, timeout=self.timeout, verify=self.verify_ssl)
            resp.encoding = 'utf-8'
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 查找正文内容（根据实际HTML结构调整）
            content_elem = soup.select_one('.chapter-content, .read-content, #content')
            
            if content_elem:
                # 清理广告和多余标签
                for ad in content_elem.select('.ad, .advert, script'):
                    ad.decompose()
                
                return content_elem.get_text(separator='\n', strip=True)
            
            return ''
        except Exception as e:
            print(f"下载章节失败: {e}")
            return ''


def get_crawler(site: str = 'biqigecn') -> NovelCrawler:
    """根据站点名称获取爬虫实例"""
    crawlers = {
        'biqigecn': BiqigecnCrawler,
    }
    
    crawler_class = crawlers.get(site, BiqigecnCrawler)
    return crawler_class()
