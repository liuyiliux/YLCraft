"""
YLCraft — 小说下载服务
支持按章节下载，保存为 TXT 文件
"""

from __future__ import annotations

import os
import asyncio
import aiofiles
from typing import Optional, Callable
from pathlib import Path

from app.services.novel.crawler import get_crawler

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"


class NovelDownloader:
    """小说下载器"""
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or str(UPLOAD_DIR / 'novels')
        os.makedirs(self.output_dir, exist_ok=True)
    
    async def download_chapters(
        self,
        book_title: str,
        author: str,
        chapters: list[dict],
        site: str = 'biqigecn',
        progress_callback: Optional[Callable] = None,
        content_fetcher: Optional[Callable] = None,
    ) -> dict:
        """
        下载指定章节

        Args:
            book_title: 书名
            author: 作者
            chapters: 章节列表 [{'index': 1, 'title': '...', 'url': '...'}]
            site: 站点名称
            progress_callback: 进度回调函数
            content_fetcher: 可选的 async 正文获取器 (url) -> str|None。
                优先于硬编码 crawler 使用——书源规则与在线阅读同一通道；
                硬编码爬虫对未适配站点（如起点）必然抓空，导致全军覆没。

        Returns:
            {'success': [...], 'failed': [...], 'file_path': '...'}
        """
        crawler = get_crawler(site)

        async def _fetch(url: str) -> Optional[str]:
            if content_fetcher is not None:
                try:
                    return await content_fetcher(url)
                except Exception:
                    return None
            return crawler.download_chapter(url)
        
        # 创建书名目录
        safe_title = self._safe_filename(book_title)
        book_dir = os.path.join(self.output_dir, safe_title)
        os.makedirs(book_dir, exist_ok=True)
        
        # 下载章节
        success = []
        failed = []
        total = len(chapters)
        
        for idx, chapter in enumerate(chapters, 1):
            try:
                content = await _fetch(chapter['url'])
                
                if content:
                    # 保存章节
                    file_path = os.path.join(book_dir, f"{chapter['index']:04d}_{self._safe_filename(chapter['title'])}.txt")
                    async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                        await f.write(f"# {chapter['title']}\n\n")
                        await f.write(content)
                        await f.write('\n')
                    
                    success.append({
                        'index': chapter['index'],
                        'title': chapter['title'],
                        'file_path': file_path,
                    })
                else:
                    failed.append(chapter)
                
                # 进度回调
                if progress_callback:
                    await progress_callback(idx, total, chapter['title'], content is not None)
                
                # 避免请求过快
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"下载章节失败: {chapter['title']} - {e}")
                failed.append(chapter)
        
        # 生成合并文件
        merged_path = os.path.join(book_dir, f"{safe_title}_全集.txt")
        await self._merge_chapters(book_dir, merged_path, book_title, author)
        
        return {
            'success': success,
            'failed': failed,
            'file_path': merged_path,
            'total_chapters': total,
            'success_count': len(success),
            'failed_count': len(failed),
        }
    
    async def _merge_chapters(self, book_dir: str, output_path: str, book_title: str, author: str):
        """合并所有章节到一个文件"""
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as outf:
            await outf.write(f"# {book_title}\n")
            await outf.write(f"作者：{author}\n\n")
            await outf.write("---\n\n")
            
            # 读取所有章节文件（按数字排序）
            files = sorted([f for f in os.listdir(book_dir) if f.endswith('.txt') and f != os.path.basename(output_path)])
            
            for fname in files:
                file_path = os.path.join(book_dir, fname)
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as inf:
                    content = await inf.read()
                    await outf.write(content)
                    await outf.write('\n\n')
    
    def _safe_filename(self, name: str) -> str:
        """生成安全的文件名"""
        import re
        # 移除非法字符
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 限制长度
        return safe[:100]


def read_local_chapter(book_title: str, chapter_index: Optional[int]) -> Optional[str]:
    """已下载全本时优先读本地章节文件，避免重复走网络。

    章节文件命名 ``NNNN_标题.txt``（NNNN 为 4 位章节序号，从 1 起），首行是 ``# 标题``。
    找不到书目录或章节文件时返回 None，由调用方回退到在线抓取。
    """
    if not book_title or not chapter_index:
        return None
    safe_title = NovelDownloader()._safe_filename(str(book_title))
    book_dir = UPLOAD_DIR / 'novels' / safe_title
    if not book_dir.is_dir():
        return None
    matches = sorted(book_dir.glob(f'{int(chapter_index):04d}_*.txt'))
    if not matches:
        return None
    try:
        text = matches[0].read_text(encoding='utf-8')
    except OSError:
        return None
    lines = text.splitlines()
    if lines and lines[0].startswith('# '):
        lines = lines[1:]
    content = '\n'.join(lines).strip()
    return content or None

