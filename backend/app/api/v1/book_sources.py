"""
书源管理 API
支持导入/导出/管理阅读App格式的书源
"""

import re
import json
from typing import List, Optional, Dict, Any, Literal
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db.database import SessionLocal
from app.db.models.book_source import BookSource
from app.db.models.book_source_cookie import BookSourceCookie
from app.schemas.book_source import (
    BookSourceCookieCreate,
    BookSourceCookieRead,
    BookSourceCookieUpdate,
)
from app.services.novel.book_source_manager import BookSourceManager
from app.services.novel.cookie_manager import BookSourceCookieManager, count_cookies
from app.services.novel.rule_converter import convert_legado_to_ylcraft, convert_ylcraft_to_legado
from app.services.novel.test_manager import BookSourceTestManager


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


class BookSourceRulesUpdate(BaseModel):
    search_url: Optional[str] = None
    rule_search: Optional[Dict[str, Any]] = None
    rule_book_info: Optional[Dict[str, Any]] = None
    rule_toc: Optional[Dict[str, Any]] = None
    rule_content: Optional[Dict[str, Any]] = None
    rule_explore: Optional[Dict[str, Any]] = None
    ylcraft_rule: Optional[Dict[str, Any]] = None
    save_format: Literal["legado", "ylcraft"] = "legado"


class BookSourceRuleConvertRequest(BaseModel):
    direction: Literal["legado_to_ylcraft", "ylcraft_to_legado"]
    source: Dict[str, Any]


class BookSourceHeadersUpdate(BaseModel):
    headers: Dict[str, Any]


class BookSourceTestRequest(BaseModel):
    url: Optional[str] = None
    keyword: Optional[str] = None
    page: int = 1
    rule_type: Optional[Literal["search", "toc", "content"]] = None
    show_raw: bool = True
    rule_format: Literal["legado", "ylcraft"] = "legado"
    fetch_mode: Literal["http", "browser"] = "http"
    headers: Optional[Dict[str, Any]] = None
    rules: Optional[BookSourceRulesUpdate] = None


class BookSourceBrowserSessionSnapshotRequest(BaseModel):
    show_raw: bool = True


def get_db():
    """获取数据库会话（依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize_cookie(cookie: BookSourceCookie) -> Dict[str, Any]:
    return BookSourceCookieRead(
        id=cookie.id,
        book_source_id=cookie.book_source_id,
        domain=cookie.domain,
        description=cookie.description,
        is_active=cookie.is_active,
        expires_at=cookie.expires_at,
        cookie_count=count_cookies(cookie.cookie_content),
        created_at=cookie.created_at,
        updated_at=cookie.updated_at,
    ).model_dump()


def _ensure_source_exists(source_id: str, db: Session) -> None:
    manager = BookSourceManager(db)
    if not manager.get_source(source_id):
        raise HTTPException(status_code=404, detail="book source does not exist")


@router.get("", include_in_schema=False)
@router.get("/")
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


@router.get("/{source_id}/rules")
async def get_book_source_rules(
    source_id: str,
    db: Session = Depends(get_db),
):
    manager = BookSourceManager(db)
    rules = manager.get_source_rules(source_id)
    if not rules:
        raise HTTPException(status_code=404, detail="book source does not exist")
    return {"success": True, "data": rules}


@router.put("/{source_id}/rules")
async def update_book_source_rules(
    source_id: str,
    payload: BookSourceRulesUpdate,
    db: Session = Depends(get_db),
):
    manager = BookSourceManager(db)
    try:
        rules = manager.update_source_rules(source_id, payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rules:
        raise HTTPException(status_code=404, detail="book source does not exist")
    return {"success": True, "data": rules}


@router.post("/rules/convert")
async def convert_book_source_rules(payload: BookSourceRuleConvertRequest):
    try:
        if payload.direction == "legado_to_ylcraft":
            data = convert_legado_to_ylcraft(payload.source)
        else:
            data = convert_ylcraft_to_legado(payload.source)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": data}


@router.put("/{source_id}/headers")
async def update_book_source_headers(
    source_id: str,
    payload: BookSourceHeadersUpdate,
    db: Session = Depends(get_db),
):
    manager = BookSourceManager(db)
    try:
        result = manager.update_source_headers(source_id, payload.headers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="book source does not exist")
    return {"success": True, "data": result}


@router.get("/{source_id}/cookies")
async def list_book_source_cookies(
    source_id: str,
    db: Session = Depends(get_db),
):
    _ensure_source_exists(source_id, db)
    manager = BookSourceCookieManager(db)
    cookies = manager.get_cookies_by_source(source_id)
    return {"success": True, "data": [_serialize_cookie(cookie) for cookie in cookies]}


@router.post("/{source_id}/cookies")
async def create_book_source_cookie(
    source_id: str,
    payload: BookSourceCookieCreate,
    db: Session = Depends(get_db),
):
    _ensure_source_exists(source_id, db)
    manager = BookSourceCookieManager(db)
    try:
        data = payload.model_dump()
        data["book_source_id"] = source_id
        cookie = manager.create_cookie(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": _serialize_cookie(cookie)}


@router.put("/{source_id}/cookies/{cookie_id}")
async def update_book_source_cookie(
    source_id: str,
    cookie_id: str,
    payload: BookSourceCookieUpdate,
    db: Session = Depends(get_db),
):
    _ensure_source_exists(source_id, db)
    manager = BookSourceCookieManager(db)
    if not manager.get_cookie(cookie_id, source_id):
        raise HTTPException(status_code=404, detail="book source cookie does not exist")
    cookie = manager.update_cookie(cookie_id, payload.model_dump(exclude_unset=True))
    return {"success": True, "data": _serialize_cookie(cookie)}


@router.delete("/{source_id}/cookies/{cookie_id}")
async def delete_book_source_cookie(
    source_id: str,
    cookie_id: str,
    db: Session = Depends(get_db),
):
    _ensure_source_exists(source_id, db)
    manager = BookSourceCookieManager(db)
    if not manager.get_cookie(cookie_id, source_id):
        raise HTTPException(status_code=404, detail="book source cookie does not exist")
    return {"success": manager.delete_cookie(cookie_id)}


@router.get("/{source_id}/test")
async def test_book_source(
    source_id: str,
    url: Optional[str] = Query(None, description="Target URL to fetch and parse"),
    rule_type: Optional[str] = Query(None, description="search, toc, or content"),
    keyword: Optional[str] = Query(None, description="Search keyword used to build URL from source searchUrl"),
    page: int = Query(1, description="Search page used with keyword templates"),
    show_raw: bool = Query(True, description="Return raw HTML preview"),
    rule_format: str = Query("legado", description="Rule parser format: legado or ylcraft"),
    db: Session = Depends(get_db),
):
    manager = BookSourceTestManager(db)
    try:
        return await manager.test_url(
            source_id=source_id,
            url=url,
            rule_type=rule_type,
            keyword=keyword,
            page=page,
            show_raw=show_raw,
            rule_format=rule_format,
        )
    except ValueError as e:
        status_code = 404 if "does not exist" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{source_id}/test")
async def test_book_source_with_rules(
    source_id: str,
    payload: BookSourceTestRequest,
    db: Session = Depends(get_db),
):
    manager = BookSourceTestManager(db)
    rule_override = payload.rules.model_dump(exclude_none=True) if payload.rules else None
    try:
        return await manager.test_url(
            source_id=source_id,
            url=payload.url,
            rule_type=payload.rule_type,
            keyword=payload.keyword,
            page=payload.page,
            show_raw=payload.show_raw,
            rule_format=payload.rule_format,
            rule_override=rule_override,
            request_headers=payload.headers,
            fetch_mode=payload.fetch_mode,
        )
    except ValueError as e:
        status_code = 404 if "does not exist" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{source_id}/browser-session/start")
async def start_book_source_browser_session(
    source_id: str,
    payload: BookSourceTestRequest,
    db: Session = Depends(get_db),
):
    manager = BookSourceTestManager(db)
    rule_override = payload.rules.model_dump(exclude_none=True) if payload.rules else None
    try:
        return await manager.start_visible_browser_session(
            source_id=source_id,
            url=payload.url,
            rule_type=payload.rule_type,
            keyword=payload.keyword,
            page=payload.page,
            rule_format=payload.rule_format,
            rule_override=rule_override,
            request_headers=payload.headers,
        )
    except ValueError as e:
        status_code = 404 if "does not exist" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/browser-sessions/{session_id}/snapshot")
async def snapshot_book_source_browser_session(
    session_id: str,
    payload: BookSourceBrowserSessionSnapshotRequest,
    db: Session = Depends(get_db),
):
    manager = BookSourceTestManager(db)
    try:
        return await manager.snapshot_visible_browser_session(
            session_id=session_id,
            show_raw=payload.show_raw,
        )
    except ValueError as e:
        status_code = 404 if "does not exist" in str(e) else 400
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/browser-sessions/{session_id}")
async def close_book_source_browser_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    manager = BookSourceTestManager(db)
    try:
        return await manager.close_visible_browser_session(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_book_sources(
    format: str = Query("legado", description="Export format: legado or ylcraft"),
    db: Session = Depends(get_db)
):
    """
    导出所有启用的书源为JSON（阅读App格式）
    """
    manager = BookSourceManager(db)
    try:
        json_str = manager.export_sources(output_format=format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    from fastapi.responses import Response
    filename = f"book_sources_{format}.json"
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
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

            # 获取当前正在处理的书源信息
            current_source = next((s for s in sources_to_search if s.bookSourceName == source_name), None)
            
            # 只做显示用的简单去重，不影响 all_results（合并阶段会做真正的合并）
            new_items = []
            display_seen: Set[Tuple[str, str]] = set()  # 仅用于控制单书源内不推送重复
            for book in results:
                item = {
                    "title": book.get("name", ""),
                    "author": book.get("author", ""),
                    "url": book.get("url") or book.get("bookUrl", ""),
                    "cover": book.get("cover") or book.get("coverUrl", ""),
                    "source_site": source_name,
                    "source_id": book.get("sourceId", "") or (current_source.source_id if current_source else ""),
                }
                # all_results 保留所有结果，后面合并阶段会做真正的合并
                all_results.append(item)
                
                # 显示去重：避免同一书源有相同书籍时重复推送
                display_key = (item["title"].strip().lower(), item["author"].strip().lower())
                if display_key not in display_seen and item["title"]:
                    display_seen.add(display_key)
                    
                    # 跨书源检查：这本书前面的书源已经推送过了吗？（避免相同书名不同源时重复推送给用户）
                    global_key = display_key
                    if global_key not in seen:
                        seen.add(global_key)
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

        # 搜索完成前，合并所有书源信息
        merged_results: List[Dict[str, Any]] = []
        merged_seen: Dict[str, Dict[str, Any]] = {}  # key -> item
        
        def get_match_key(title: str) -> str:
            """生成用于匹配的key，只保留中文字符、英文字母和数字"""
            key = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title)
            return key.lower()
        
        for item in all_results:
            title = item.get("title", "")
            source_site = item.get("source_site", "")
            source_id = item.get("source_id", "")
            match_key = get_match_key(title)
            
            if not match_key:
                continue
                
            if match_key not in merged_seen:
                new_item = item.copy()
                new_item["sources"] = [{
                    "id": source_id,
                    "name": source_site,
                    "url": "",
                    "book_url": item.get("url", ""),
                }]
                merged_seen[match_key] = new_item
                merged_results.append(new_item)
            else:
                existing = merged_seen[match_key]
                existing_source_ids = {s.get("id") for s in existing.get("sources", [])}
                if source_id and source_id not in existing_source_ids:
                    existing["sources"].append({
                        "id": source_id,
                        "name": source_site,
                        "url": "",
                        "book_url": item.get("url", ""),
                    })
        
        # 搜索完成事件，返回合并后的结果
        yield f"data: {json.dumps({'type': 'finish', 'total': len(merged_results), 'data': merged_results}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
