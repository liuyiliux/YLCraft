"""
书源管理 API
支持导入/导出/管理阅读App格式的书源
"""

from typing import List, Optional
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


@router.get("/search")
async def search_books(
    keyword: str,
    db: Session = Depends(get_db)
):
    """
    在所有启用的书源中搜索小说
    
    Args:
        keyword: 搜索关键词
    """
    manager = BookSourceManager(db)
    results = await manager.search_all_sources(keyword)
    
    return {"data": results, "total": len(results)}
