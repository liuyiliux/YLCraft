"""
YLCraft — 小说 API 路由
支持搜索、目录获取、章节下载
"""

from __future__ import annotations

import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.asset import Asset
from app.db.models.novel import NovelChapter
from app.services.novel.crawler import get_crawler
from app.services.novel.downloader import NovelDownloader
from app.services.novel.book_source_manager import BookSourceManager

router = APIRouter(tags=["novels"])


def get_db():
    """获取数据库会话（依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DownloadChaptersRequest(BaseModel):
    book_url: str
    book_title: str
    author: str
    chapters: List[Dict[str, Any]]  # [{'index': 1, 'title': '...', 'url': '...'}]
    site: str = 'biqigecn'


class SearchResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]] = []
    total: int = 0
    page: int = 1
    limit: int = 20


class CatalogResponse(BaseModel):
    success: bool = True
    data: List[Dict[str, Any]] = []
    total: int = 0


@router.get("/search")
async def search_novels(
    q: str,
    site: str = 'biqigecn',
    page: int = 1,
    limit: int = 20,
):
    """
    搜索小说
    
    Args:
        q: 搜索关键词
        site: 站点名称（biqigecn 等）
        page: 页码
        limit: 每页数量
    """
    try:
        crawler = get_crawler(site)
        results = crawler.search(q)
        
        # 分页
        start = (page - 1) * limit
        end = start + limit
        paged = results[start:end]
        
        return {
            'success': True,
            'data': paged,
            'total': len(results),
            'page': page,
            'limit': limit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalog")
async def get_catalog(
    url: str,
    site: str = '',
    db: Session = Depends(get_db)
):
    """
    获取小说目录（使用书源解析器）
    
    Args:
        url: 小说页面URL
        site: 书源ID（可选，为空时自动匹配）
    """
    try:
        manager = BookSourceManager(db)
        
        # 如果提供了 site（书源ID），直接使用该书源
        if site:
            source = manager.get_source(site)
            if not source:
                raise HTTPException(status_code=404, detail="书源不存在")
        else:
            # 尝试根据 URL 匹配书源
            source = None
            for s in manager.sources:
                if s.bookSourceUrl and url.startswith(s.bookSourceUrl.rstrip('/')):
                    source = s
                    break
            
            if not source:
                # 使用第一个启用的书源作为 fallback
                source = next((s for s in manager.sources if s.enabled_by_user), None)
        
        if not source:
            raise HTTPException(status_code=404, detail="没有可用的书源")
        
        chapters = await manager.get_chapter_list(source, url)
        
        # 标准化字段名以匹配前端期望
        normalized_chapters = []
        for idx, ch in enumerate(chapters, 1):
            normalized_chapters.append({
                'index': idx,
                'title': ch.get('title', ''),
                'url': ch.get('url', ''),
            })
        
        return {
            'success': True,
            'data': normalized_chapters,
            'total': len(normalized_chapters),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取目录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download-chapters")
async def download_chapters(
    req: DownloadChaptersRequest,
    background_tasks: BackgroundTasks,
):
    """
    下载指定章节
    
    下载完成后自动创建 Asset 和 NovelChapter 记录
    """
    try:
        downloader = NovelDownloader()
        
        # 在后台下载
        def do_download():
            import asyncio
            
            # 下载章节
            result = asyncio.run(downloader.download_chapters(
                book_title=req.book_title,
                author=req.author,
                chapters=req.chapters,
                site=req.site,
            ))
            
            # 创建 Asset 记录
            db = SessionLocal()
            try:
                asset_id = uuid.uuid4().hex
                
                # 构建 metadata
                metadata = {
                    'novel_title': req.book_title,
                    'author': req.author,
                    'source_site': req.site,
                    'chapter_count': len(req.chapters),
                    'downloaded_chapters': [ch['index'] for ch in req.chapters],
                    'content_path': result.get('file_path', ''),
                    'last_read_chapter': 0,
                    'last_read_position': 0,
                }
                
                asset = Asset(
                    id=asset_id,
                    type='novel',
                    platform=req.site,
                    title=req.book_title,
                    author=req.author,
                    source_type='novel_download',
                    status='ready',
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                    tags='[]',
                )
                
                db.add(asset)
                
                # 创建 NovelChapter 记录
                for ch in req.chapters:
                    chapter = NovelChapter(
                        asset_id=asset_id,
                        chapter_index=ch['index'],
                        chapter_title=ch['title'],
                        chapter_url=ch.get('url', ''),
                        is_downloaded=True,
                    )
                    db.add(chapter)
                
                db.commit()
                print(f"Asset 记录已创建: {asset_id}")
                
            except Exception as e:
                print(f"创建 Asset 记录失败: {e}")
                db.rollback()
            finally:
                db.close()
        
        background_tasks.add_task(do_download)
        
        return {
            'success': True,
            'message': f'已开始下载 {len(req.chapters)} 个章节，请稍后查看书架',
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def get_sources(db: Session = Depends(get_db)):
    """获取可用的书源列表（从数据库读取）"""
    manager = BookSourceManager(db)
    sources = manager.list_sources(enabled_only=True)
    data = [
        {'id': s['id'], 'name': s['book_source_name'] + ('(JS)' if s.get('is_js_source') else ''), 'enabled': s['enabled_by_user']}
        for s in sources
    ]
    return {'success': True, 'data': data}
