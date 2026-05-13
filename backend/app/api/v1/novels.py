"""
YLCraft — 小说 API 路由
支持搜索、目录获取、加入书架、在线阅读、章节下载
"""

from __future__ import annotations

import json
import os
import uuid
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

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
    asset_id: Optional[str] = None  # 已有书架记录时传入，用于更新


class AddToBookshelfRequest(BaseModel):
    """加入书架请求（仅保存元信息，不下载内容）"""
    book_url: str
    book_title: str
    author: str = ''
    cover_url: str = ''
    intro: str = ''
    kind: str = ''  # 分类/标签
    toc_url: str = ''  # 目录页 URL
    source_id: str = ''  # 书源 ID
    source_name: str = ''  # 书源名称
    source_url: str = ''  # 书源 URL
    chapters: List[Dict[str, Any]] = []  # [{'index': 1, 'title': '...', 'url': '...'}]


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


# ==================== 搜索 & 目录 ====================

@router.get("/search")
async def search_novels(
    q: str,
    site: str = 'biqigecn',
    page: int = 1,
    limit: int = 20,
):
    """搜索小说"""
    try:
        crawler = get_crawler(site)
        results = crawler.search(q)
        
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
    db: Session = Depends(get_db),
):
    """获取小说目录（使用书源解析器）"""
    try:
        manager = BookSourceManager(db)

        source = None
        if site:
            source = manager.get_source(site)
            if not source:
                # 尝试通过 URL 前缀匹配
                for s in manager.sources:
                    if s.bookSourceUrl and url.startswith(s.bookSourceUrl.rstrip('/')):
                        source = s
                        break
            if not source and manager.sources:
                # 使用第一个启用的书源作为 fallback
                source = next((s for s in manager.sources if s.enabled_by_user), manager.sources[0])
        else:
            for s in manager.sources:
                if s.bookSourceUrl and url.startswith(s.bookSourceUrl.rstrip('/')):
                    source = s
                    break
            if not source:
                source = next((s for s in manager.sources if s.enabled_by_user), None)

        if not source:
            raise HTTPException(status_code=404, detail="没有可用的书源")

        chapters = await manager.get_chapter_list(source, url)

        normalized_chapters = []
        for idx, ch in enumerate(chapters, 1):
            normalized_chapters.append({
                'index': idx,
                'title': ch.get('title') or ch.get('name', ''),
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


# ==================== 加入书架（仅保存元信息）====================

@router.post("/add-to-bookshelf")
async def add_to_bookshelf(req: AddToBookshelfRequest, db: Session = Depends(get_db)):
    """
    加入书架：仅保存书籍元信息 + 章节目录 + 关联书源，不下载正文内容。
    
    参考 Legado 设计：
    - Book 实体存储 bookUrl/tocUrl/origin(书源)/章节列表/阅读进度
    - 阅读时通过书源规则实时从网络获取内容
    - 下载是独立的后续操作
    """
    try:
        # 检查是否已存在相同 book_url 的记录（同一本书）
        existing = db.execute(
            text("SELECT id, metadata_json FROM assets WHERE type='NOVEL' AND source_url=:burl"),
            {"burl": req.book_url}
        ).fetchone()

        if existing:
            asset_id = existing[0]
            # 更新已有记录的章节数据和书源信息
            meta = json.loads(existing[1] or '{}')
            # 多源目录：以 source_id 为 key 存储各书源的目录
            catalogs = meta.get('catalogs', {})
            catalogs[req.source_id] = {
                'chapters': req.chapters,
                'chapter_count': len(req.chapters),
                'source_name': req.source_name,
                'source_url': req.source_url,
                'toc_url': req.toc_url,
            }
            meta.update({
                # 当前阅读使用的目录（兼容旧逻辑）
                'chapters': req.chapters,
                'chapter_count': len(req.chapters),
                'source_id': req.source_id,
                'source_name': req.source_name,
                'toc_url': req.toc_url,
                'catalogs': catalogs,
                'last_updated': datetime.now().isoformat(),
            })
            db.execute(
                text("UPDATE assets SET metadata_json=:meta, updated_at=:now WHERE id=:id"),
                {"meta": json.dumps(meta, ensure_ascii=False), "now": datetime.now(), "id": asset_id}
            )
            db.commit()
            return {'success': True, 'message': '书架信息已更新', 'asset_id': asset_id}

        # 创建新 Asset 记录
        asset_id = uuid.uuid4().hex
        
        metadata = {
            'novel_title': req.book_title,
            'author': req.author,
            'cover_url': req.cover_url,
            'intro': req.intro[:500] if req.intro else '',
            'kind': req.kind,
            'book_url': req.book_url,
            'toc_url': req.toc_url,
            'source_id': req.source_id,
            'source_name': req.source_name,
            'source_url': req.source_url,
            'chapters': req.chapters,
            'chapter_count': len(req.chapters),
            # 多源目录：key 为 source_id，value 包含该书源的章节列表和 URL
            'catalogs': {
                req.source_id: {
                    'chapters': req.chapters,
                    'chapter_count': len(req.chapters),
                    'source_name': req.source_name,
                    'source_url': req.source_url,
                    'toc_url': req.toc_url,
                }
            },
            'downloaded_chapter_indices': [],
            'last_read_chapter': 0,
            'last_read_position': 0,
            'status': 'bookshelf',  # 在书架中但未下载
        }

        asset = Asset(
            id=asset_id,
            type='NOVEL',
            platform=req.source_name or 'web',
            title=req.book_title,
            author=req.author,
            cover_url=req.cover_url,
            source_type='novel_bookshelf',
            status='bookshelf',  # 自定义状态：在书架中
            source_url=req.book_url,  # 用 source_url 存 book_url 做去重
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            tags='[]',
        )

        db.add(asset)
        db.commit()
        
        print(f"[Bookshelf] 已加入书架: {req.book_title} (asset_id={asset_id}, 章节数={len(req.chapters)})")
        
        return {
            'success': True,
            'message': f'已将《{req.book_title}》加入书架',
            'asset_id': asset_id,
        }
    
    except Exception as e:
        print(f"加入书架失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 在线阅读（从网络获取章节内容）====================

@router.get("/chapter-content")
async def get_chapter_content(
    chapter_url: str = Query(..., description="章节 URL"),
    source_id: str = Query('', description="书源 ID"),
    book_url: str = Query('', description="书籍 URL（备用匹配书源）"),
    db: Session = Depends(get_db),
):
    """
    在线获取章节正文（不依赖本地文件，直接从网站抓取）
    
    用于阅读器的在线阅读模式，参考 Legado CacheBook.download() 实现
    """
    try:
        manager = BookSourceManager(db)
        
        # 确定使用哪个书源
        source = None
        if source_id:
            source = manager.get_source(source_id)
        elif book_url:
            # 根据 book_url 匹配书源
            for s in manager.sources:
                if s.bookSourceUrl and book_url.startswith(s.bookSourceUrl.rstrip('/')):
                    source = s
                    break
        
        if not source:
            # 尝试使用第一个启用的书源
            source = next((s for s in manager.sources if s.enabled_by_user), None)

        if not source:
            raise HTTPException(status_code=404, detail="没有可用的书源")

        # 通过书源规则获取章节正文
        content = await manager.get_chapter_content(source, chapter_url)
        
        if content is None:
            raise HTTPException(status_code=502, detail="无法获取章节内容，请检查书源规则或稍后重试")

        return {
            'success': True,
            'data': {
                'content': content,
                'source_name': source.bookSourceName,
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取章节内容失败: {chapter_url} - {e}")
        raise HTTPException(status_code=500, detail=f"获取章节内容失败: {str(e)}")


@router.get("/bookshelf-item/{asset_id}")
async def get_bookshelf_item(asset_id: str, db: Session = Depends(get_db)):
    """获取书架中的书籍详情（含章节列表、书源信息等）"""
    try:
        asset = db.get(Asset, asset_id)
        if not asset or asset.type.lower() != 'novel':
            raise HTTPException(status_code=404, detail="书籍不存在")

        meta = json.loads(asset.metadata_json or '{}')
        
        chapters_data = meta.get('chapters', [])
        print(f"[DEBUG get_bookshelf_item] asset_id={asset_id}, chapters_count={len(chapters_data)}, meta_keys={list(meta.keys())}")
        
        return {
            'success': True,
            'data': {
                'id': asset.id,
                'title': asset.title,
                'author': asset.author,
                'cover_url': asset.cover_url,
                'status': asset.status,
                'created_at': asset.created_at.isoformat() if asset.created_at else None,
                **meta,  # 展开所有 metadata 字段
            },
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 下载章节（全本 / 选章 / 范围）====================

@router.post("/download-chapters")
async def download_chapters(
    req: DownloadChaptersRequest,
    background_tasks: BackgroundTasks,
):
    """
    下载指定章节
    
    支持：
    - 全本下载（chapters 包含全部章节）
    - 选章下载（chapters 只包含选中的章节）
    - 更新模式（传 asset_id 则更新已有书架记录）
    """
    try:
        downloader = NovelDownloader()
        
        def do_download():
            import asyncio
            
            result = asyncio.run(downloader.download_chapters(
                book_title=req.book_title,
                author=req.author,
                chapters=req.chapters,
                site=req.site,
            ))

            db = SessionLocal()
            try:
                if req.asset_id:
                    # 更新已有记录
                    asset = db.get(Asset, req.asset_id)
                    if asset:
                        meta = json.loads(asset.metadata_json or '{}')
                        downloaded = set(meta.get('downloaded_chapter_indices', []))
                        for ch in req.chapters:
                            downloaded.add(ch['index'])
                        meta['downloaded_chapter_indices'] = sorted(list(downloaded))
                        meta['content_path'] = result.get('file_path', '')
                        meta['last_downloaded'] = datetime.now().isoformat()
                        
                        # 如果全部下载完毕，标记为 ready
                        if len(downloaded) >= meta.get('chapter_count', 99999):
                            meta['status'] = 'ready'
                            asset.status = 'ready'
                        else:
                            meta['status'] = 'partial'
                            asset.status = 'partial'

                        asset.metadata_json = json.dumps(meta, ensure_ascii=False)
                        asset.updated_at = datetime.now()
                        
                        # 更新 NovelChapter 记录
                        for ch in req.chapters:
                            existing_ch = db.execute(
                                text("SELECT id FROM novel_chapters WHERE asset_id=:aid AND chapter_index=:ci"),
                                {"aid": req.asset_id, "ci": ch['index']}
                            ).fetchone()
                            
                            if existing_ch:
                                db.execute(
                                    text("""UPDATE novel_chapters SET is_downloaded=True 
                                        WHERE asset_id=:aid AND chapter_index=:ci"""),
                                    {"aid": req.asset_id, "ci": ch['index']}
                                )
                            else:
                                chapter = NovelChapter(
                                    asset_id=req.asset_id,
                                    chapter_index=ch['index'],
                                    chapter_title=ch['title'],
                                    chapter_url=ch.get('url', ''),
                                    is_downloaded=True,
                                )
                                db.add(chapter)
                        
                        print(f"[Download] 更新书架记录: {req.asset_id}, 新增下载 {len(req.chapters)} 章")
                    
                else:
                    # 创建新 Asset 记录（兼容旧逻辑，无 bookshelf 时用）
                    asset_id = uuid.uuid4().hex
                    
                    metadata = {
                        'novel_title': req.book_title,
                        'author': req.author,
                        'source_site': req.site,
                        'chapter_count': len(req.chapters),
                        'downloaded_chapters': [ch['index'] for ch in req.chapters],
                        'content_path': result.get('file_path', ''),
                        'last_read_chapter': 0,
                        'last_read_position': 0,
                        'status': 'ready' if len(req.chapters) > 10 else 'partial',
                    }
                    
                    asset = Asset(
                        id=asset_id,
                        type='novel',
                        platform=req.site,
                        title=req.book_title,
                        author=req.author,
                        source_type='novel_download',
                        status='ready',
                        source_url=req.book_url,
                        metadata_json=json.dumps(metadata, ensure_ascii=False),
                        tags='[]',
                    )
                    
                    db.add(asset)
                    
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
                
            except Exception as e:
                print(f"创建/更新 Asset 记录失败: {e}")
                db.rollback()
            finally:
                db.close()

        background_tasks.add_task(do_download)
        
        mode_msg = "全本" if len(req.chapters) > 5 else f"{len(req.chapters)} 个章节"
        action = "更新" if req.asset_id else "创建"
        return {
            'success': True,
            'message': f'已开始下载{mode_msg}，{action}书架记录，请稍后查看',
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


@router.get("/source-catalog")
async def get_source_catalog(
    book_url: str = Query(..., description="书籍 URL（原始书源）"),
    source_id: str = Query(..., description="目标书源 ID"),
    db: Session = Depends(get_db),
):
    """
    从指定书源获取书籍目录（用于换源时动态加载目录）。
    根据目标书源的域名，构造对应书源的目录页 URL，再抓取解析。
    """
    try:
        manager = BookSourceManager(db)
        source = manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="书源不存在")

        # 构造目标书源的目录 URL：
        # 从原始 book_url 提取路径部分，拼接到目标书源的 bookSourceUrl
        original_url = book_url.rstrip('/')
        # 提取原始 URL 的路径部分（如 /book/123.html -> /book/）
        if '/' in original_url:
            path_part = original_url[original_url.rfind('/'):]
            # 判断是否是文件页（.html/.php等），如果是则取上级目录
            if '.' in path_part:
                base_path = original_url[:original_url.rfind('/')]
            else:
                base_path = original_url
        else:
            base_path = original_url

        # 尝试用目标书源域名构造目录 URL
        target_base = source.bookSourceUrl.rstrip('/')
        
        # 简化：从目标书源根目录开始尝试
        # 先用书源配置的 ruleToc 中的 URL 模板，如果没有则直接用 bookSourceUrl
        catalog_url = target_base
        if source.ruleToc and isinstance(source.ruleToc, dict):
            toc_url_template = source.ruleToc.get('bookUrl', '') or source.ruleToc.get('url', '')
            if toc_url_template and toc_url_template.startswith('http'):
                catalog_url = toc_url_template
            elif toc_url_template:
                catalog_url = target_base + toc_url_template

        print(f"[换源] 目标书源={source.bookSourceName}, 构造目录URL={catalog_url}")

        chapters = await manager.get_chapter_list(source, catalog_url)

        if not chapters:
            raise HTTPException(status_code=404, detail=f"该书源无法获取目录，可能需要手动设置目录页 URL")

        normalized = [
            {'index': idx, 'title': ch.get('title') or ch.get('name', ''), 'url': ch.get('url', '')}
            for idx, ch in enumerate(chapters, 1)
        ]

        return {
            'success': True,
            'data': {
                'source_id': source_id,
                'source_name': source.bookSourceName,
                'catalog_url': catalog_url,
                'chapters': normalized,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[换源] 获取目录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
