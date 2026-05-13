"""
书源管理 API
支持导入/导出/管理阅读App格式的书源
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db.database import SessionLocal
from app.db.models.book_source import BookSource
from app.services.novel.book_source_manager import BookSourceManager
import json


router = APIRouter(tags=["book-sources"])


class BookSourceResponse(BaseModel):
    """书源响应模型"""
    id: str
    book_source_name: str
    book_source_url: str
    book_source_type: int = 0
    enabled: bool = True
    book_source_group: Optional[str] = None
    enabled_by_user: bool = True
    is_js_source: bool = False
    created_at: Optional[str] = None


class BookSourceImportResponse(BaseModel):
    """书源导入响应"""
    success: bool
    added: int = 0
    updated: int = 0
    total: int = 0
    error: Optional[str] = None


def get_db():
    """获取数据库会话（依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
async def list_book_sources(
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    列出所有书源
    
    Args:
        enabled_only: 是否只显示启用的书源
    """
    manager = BookSourceManager(db)
    sources = manager.list_sources(enabled_only=enabled_only)
    return {"data": sources}


@router.post("/import")
async def import_book_sources(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    导入书源JSON文件（支持阅读App格式）
    
    Args:
        file: 书源JSON文件
    """
    try:
        content = await file.read()
        json_str = content.decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件读取失败: {str(e)}")
    
    manager = BookSourceManager(db)
    result = manager.import_sources(json_str)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/import-json")
async def import_book_sources_json(
    data: dict,
    db: Session = Depends(get_db)
):
    """
    导入书源JSON字符串（支持阅读App格式）
    
    Args:
        data: {"json": "..."} 或 {"sources": [...]}
    """
    json_str = data.get("json") or json.dumps(data.get("sources", []))
    
    manager = BookSourceManager(db)
    result = manager.import_sources(json_str)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.put("/{source_id}/toggle")
async def toggle_book_source(
    source_id: str,
    enabled: bool,
    db: Session = Depends(get_db)
):
    """
    启用/禁用书源
    
    Args:
        source_id: 书源ID
        enabled: 是否启用
    """
    manager = BookSourceManager(db)
    success = manager.toggle_source(source_id, enabled)
    
    if not success:
        raise HTTPException(status_code=404, detail="书源不存在")
    
    return {"success": True, "enabled": enabled}


@router.delete("/{source_id}")
async def delete_book_source(
    source_id: str,
    db: Session = Depends(get_db)
):
    """
    删除书源
    
    Args:
        source_id: 书源ID
    """
    manager = BookSourceManager(db)
    success = manager.delete_source(source_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="书源不存在")
    
    return {"success": True}


@router.get("/export")
async def export_book_sources(
    db: Session = Depends(get_db)
):
    """
    导出所有启用的书源为JSON（阅读App格式）
    """
    manager = BookSourceManager(db)
    json_str = manager.export_sources()
    
    from fastapi.responses import Response
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=book_sources.json"}
    )


class BatchIdsRequest(BaseModel):
    """批量ID请求"""
    ids: List[str]


class BatchToggleRequest(BaseModel):
    """批量切换状态请求"""
    ids: List[str]
    enabled: bool


@router.post("/batch-delete")
async def batch_delete_book_sources(
    data: BatchIdsRequest,
    db: Session = Depends(get_db)
):
    """
    批量删除书源
    
    Args:
        data: {"ids": ["id1", "id2", ...]}
    """
    manager = BookSourceManager(db)
    result = manager.batch_delete_sources(data.ids)
    return result


@router.post("/batch-toggle")
async def batch_toggle_book_sources(
    data: BatchToggleRequest,
    db: Session = Depends(get_db)
):
    """
    批量启用/禁用书源
    
    Args:
        data: {"ids": ["id1", "id2", ...], "enabled": true/false}
    """
    manager = BookSourceManager(db)
    result = manager.batch_toggle_sources(data.ids, data.enabled)
    return result


@router.get("/search")
async def search_books(
    keyword: str,
    db: Session = Depends(get_db)
):
    """
    在所有启用的书源中搜索小说（SSE 流式返回，每个书源完成即推送）
    
    Args:
        keyword: 搜索关键词
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    import json

    manager = BookSourceManager(db)

    async def event_generator():
        # 发送初始事件（搜索开始）
        yield f"data: {json.dumps({'type': 'start', 'data': []})}\n\n"

        sources_to_search = [
            source for source in manager.sources
            if source.enabled_by_user and source.ruleSearch and manager._is_compatible_source(source)
        ]

        if not sources_to_search:
            yield f"data: {json.dumps({'type': 'finish', 'total': 0, 'data': []})}\n\n"
            return

        semaphore = asyncio.Semaphore(10)
        all_results: List[Dict[str, Any]] = []
        seen = set()
        completed_count = 0
        total_sources = len(sources_to_search)

        async def search_one(source):
            try:
                results = await manager._search_single_source(source, keyword)
                for r in results:
                    r["sourceName"] = source.bookSourceName
                    r["sourceUrl"] = source.bookSourceUrl
                    r["sourceId"] = source.source_id
                return (source.bookSourceName, results or [])
            except Exception as e:
                print(f"在书源 {source.bookSourceName} 搜索失败: {e}")
                return (source.bookSourceName, [])

        tasks = [asyncio.create_task(search_one(source)) for source in sources_to_search]

        # 使用 as_completed 实现流式推送：哪个书源先完成就先推送给前端
        for coro in asyncio.as_completed(tasks):
            source_name, results = await coro
            completed_count += 1

            # 标准化 + 去重
            new_items = []
            for book in results:
                item = {
                    "title": book.get("name", ""),
                    "author": book.get("author", ""),
                    "url": book.get("url") or book.get("bookUrl", ""),
                    "cover": book.get("cover") or book.get("coverUrl", ""),
                    "source_site": source_name,
                    "source_id": book.get("sourceId", ""),
                }
                key = (item["title"].strip().lower(), item["author"].strip().lower())
                if key not in seen and item["title"]:
                    seen.add(key)
                    all_results.append(item)
                    new_items.append(item)

            if new_items:
                payload = {
                    'type': 'results',
                    'completed': completed_count,
                    'total_sources': total_sources,
                    'current_source': source_name,
                    'new_count': len(new_items),
                    'total_so_far': len(all_results),
                    'data': new_items,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # 搜索完成事件
        yield f"data: {json.dumps({'type': 'finish', 'total': len(all_results), 'data': all_results}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
