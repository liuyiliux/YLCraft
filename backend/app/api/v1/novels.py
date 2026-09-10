"""
Novel API routes.

Bookshelf and downloaded novel records now use Asset Hub as the canonical
storage. Legacy asset ids are still resolved through `legacy_asset_id`
metadata so migrated data keeps working.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.task_queue import get_task_queue
from app.db.database import AsyncSessionLocal, SessionLocal
from app.db.models.asset_hub import AssetNode, AssetType
from app.db.models.novel import NovelChapter
from app.services.asset_hub import (
    AssetNodeService,
    AssetRepresentationService,
    AssetVersionService,
)
from app.services.novel.book_source_manager import BookSourceManager
from app.services.novel.crawler import get_crawler
from app.services.novel.downloader import NovelDownloader, read_local_chapter

router = APIRouter(tags=["novels"])
logger = logging.getLogger("ylcraft.api.novels")

_NOVEL_SOURCE_TYPES = {"novel", "novel_bookshelf", "novel_download"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 小说下载的运行保护
#
# 几百章的串行下载会把线程池与连接池占满、拖垮整个服务（实测后端会停止响应）。
# 这里做三件事：同一本书同时只允许一个下载任务；抓取并发可控；任务可取消。
# ---------------------------------------------------------------------------

#: book_key -> {"task_id", "stop_event", "title"}，仅登记进行中的任务。
_ACTIVE_DOWNLOADS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_DOWNLOADS_LOCK = asyncio.Lock()

#: 章节抓取并发度：太高会被站点判定为爬虫，太低则几百章要跑很久。
NOVEL_DOWNLOAD_CONCURRENCY = int(os.getenv("NOVEL_DOWNLOAD_CONCURRENCY", "3") or 3)


class DownloadChaptersRequest(BaseModel):
    book_url: str
    book_title: str
    author: str
    chapters: List[Dict[str, Any]]
    site: str = "biqigecn"
    asset_id: Optional[str] = None


class AddToBookshelfRequest(BaseModel):
    book_url: str
    book_title: str
    author: str = ""
    cover_url: str = ""
    intro: str = ""
    kind: str = ""
    toc_url: str = ""
    source_id: str = ""
    source_name: str = ""
    source_url: str = ""
    chapters: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []


def _populate_source_catalogs(catalogs: Dict[str, Any], sources_list: List[Dict[str, Any]]) -> None:
    for source in sources_list or []:
        source_id = source.get("id") or source.get("source_id") or ""
        if not source_id or source_id in catalogs:
            continue
        catalogs[source_id] = {
            "chapters": [],
            "chapter_count": 0,
            "source_name": source.get("name") or source.get("source_name") or "",
            "source_url": source.get("url") or source.get("source_url") or source.get("book_url") or "",
            "toc_url": "",
        }


def _chapter_indices(chapters: List[Dict[str, Any]]) -> List[int]:
    indices: List[int] = []
    for chapter in chapters:
        try:
            indices.append(int(chapter.get("index")))
        except Exception:
            continue
    return indices


def _normalize_book_metadata(req: AddToBookshelfRequest) -> Dict[str, Any]:
    catalogs: Dict[str, Any] = {}
    if req.source_id:
        catalogs[req.source_id] = {
            "chapters": req.chapters,
            "chapter_count": len(req.chapters),
            "source_name": req.source_name,
            "source_url": req.source_url,
            "toc_url": req.toc_url,
        }
    _populate_source_catalogs(catalogs, req.sources)
    return {
        "novel_title": req.book_title,
        "author": req.author,
        "cover_url": req.cover_url,
        "intro": req.intro[:500] if req.intro else "",
        "kind": req.kind,
        "book_url": req.book_url,
        "toc_url": req.toc_url,
        "source_id": req.source_id,
        "source_name": req.source_name,
        "source_url": req.source_url,
        "chapters": req.chapters,
        "chapter_count": len(req.chapters),
        "catalogs": catalogs,
        "downloaded_chapter_indices": [],
        "last_read_chapter": 0,
        "last_read_position": 0,
        "content_path": "",
        "status": "bookshelf",
        "source": "novel_bookshelf",
        "source_type": "novel_bookshelf",
        "last_updated": datetime.now().isoformat(),
    }


def _node_metadata(node: AssetNode | None) -> Dict[str, Any]:
    if not node:
        return {}
    return node.metadata_json if isinstance(node.metadata_json, dict) else {}


def _is_novel_node(node: AssetNode | None) -> bool:
    if not node:
        return False
    metadata = _node_metadata(node)
    source_type = str(metadata.get("source_type") or metadata.get("source") or "").lower()
    return source_type in _NOVEL_SOURCE_TYPES


async def _resolve_novel_node(session, *, asset_id: str = "", book_url: str = "") -> AssetNode | None:
    if asset_id:
        node = await session.get(AssetNode, asset_id)
        if _is_novel_node(node):
            return node

        result = await session.execute(
            text(
                """
                SELECT id
                FROM asset_nodes
                WHERE metadata_json ->> 'legacy_asset_id' = :asset_id
                LIMIT 1
                """
            ),
            {"asset_id": asset_id},
        )
        row = result.first()
        if row:
            node = await session.get(AssetNode, str(row[0]))
            if _is_novel_node(node):
                return node

    if book_url:
        result = await session.execute(
            text(
                """
                SELECT id
                FROM asset_nodes
                WHERE asset_type = 'TEXT'
                  AND (
                    metadata_json ->> 'book_url' = :book_url
                    OR metadata_json ->> 'source_url' = :book_url
                  )
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"book_url": book_url},
        )
        row = result.first()
        if row:
            node = await session.get(AssetNode, str(row[0]))
            if _is_novel_node(node):
                return node
    return None


async def _create_novel_node(
    session,
    *,
    title: str,
    author: str,
    cover_url: str,
    metadata: Dict[str, Any],
    file_path: str = "",
) -> AssetNode:
    node_service = AssetNodeService(session)
    version_service = AssetVersionService(session)
    rep_service = AssetRepresentationService(session)

    meta = dict(metadata)
    meta.setdefault("author", author)
    meta.setdefault("cover_url", cover_url)

    node = await node_service.create(
        name=title,
        asset_type=AssetType.TEXT,
        thumbnail_url=cover_url or None,
        metadata=meta,
        tags=[tag for tag in ["novel", meta.get("source_type") or "", meta.get("source_name") or meta.get("source_site") or ""] if tag],
    )
    version = await version_service.create(
        asset_node_id=str(node.id),
        prompt_used=title,
        model_used="",
        params=meta,
        lineage={
            "source": meta.get("source_type") or meta.get("source") or "novel_bookshelf",
            "book_url": meta.get("book_url") or meta.get("source_url") or "",
        },
    )

    is_local = bool(file_path and os.path.exists(file_path))
    rep_path = file_path or meta.get("book_url") or meta.get("source_url") or title
    await rep_service.create(
        asset_version_id=str(version.id),
        file_path=str(rep_path),
        mime_type="text/plain" if is_local else "application/x-ylcraft-remote-book",
        file_size=os.path.getsize(file_path) if is_local else 0,
        format=os.path.splitext(file_path)[1].lstrip(".").lower() or ("txt" if is_local else "remote-book"),
        extra={
            "book_url": meta.get("book_url") or "",
            "source_url": meta.get("source_url") or meta.get("book_url") or "",
            "content_path": file_path or "",
            "remote": not is_local,
        },
    )
    return node


def _novel_payload(node: AssetNode) -> Dict[str, Any]:
    metadata = _node_metadata(node)
    return {
        "id": str(node.id),
        "title": node.name or metadata.get("novel_title") or "",
        "author": metadata.get("author") or "",
        "cover_url": node.thumbnail_url or metadata.get("cover_url") or "",
        "status": metadata.get("status") or "bookshelf",
        "created_at": node.created_at.isoformat() if node.created_at else None,
        **metadata,
    }


async def _record_downloaded_chapters(session, asset_id: str, chapters: List[Dict[str, Any]]) -> None:
    for chapter in chapters:
        existing = await session.execute(
            text("SELECT id FROM novel_chapters WHERE asset_id=:aid AND chapter_index=:idx"),
            {"aid": asset_id, "idx": chapter["index"]},
        )
        if existing.first():
            await session.execute(
                text(
                    """
                    UPDATE novel_chapters
                    SET is_downloaded=true, chapter_title=:title, chapter_url=:url
                    WHERE asset_id=:aid AND chapter_index=:idx
                    """
                ),
                {
                    "aid": asset_id,
                    "idx": chapter["index"],
                    "title": chapter["title"],
                    "url": chapter.get("url", ""),
                },
            )
            continue

        session.add(
            NovelChapter(
                asset_id=asset_id,
                chapter_index=chapter["index"],
                chapter_title=chapter["title"],
                chapter_url=chapter.get("url", ""),
                is_downloaded=True,
            )
        )


async def _upsert_bookshelf_node(req: AddToBookshelfRequest) -> str:
    metadata = _normalize_book_metadata(req)
    async with AsyncSessionLocal() as session:
        node = await _resolve_novel_node(session, book_url=req.book_url)
        if node:
            current = _node_metadata(node)
            catalogs = current.get("catalogs", {}) if isinstance(current.get("catalogs"), dict) else {}
            catalogs.update(metadata.get("catalogs", {}))
            metadata["catalogs"] = catalogs
            metadata["downloaded_chapter_indices"] = current.get("downloaded_chapter_indices", [])
            metadata["last_read_chapter"] = current.get("last_read_chapter", 0)
            metadata["last_read_position"] = current.get("last_read_position", 0)
            metadata["content_path"] = current.get("content_path", "")
            metadata["status"] = current.get("status", metadata["status"])
            if current.get("source_type") == "novel_download":
                metadata["source"] = "novel_download"
                metadata["source_type"] = "novel_download"

            current.update(metadata)
            node.name = req.book_title
            node.thumbnail_url = req.cover_url or node.thumbnail_url
            node.metadata_json = current
            node.updated_at = datetime.utcnow()
            session.add(node)
            await session.commit()
            return str(node.id)

        node = await _create_novel_node(
            session,
            title=req.book_title,
            author=req.author,
            cover_url=req.cover_url,
            metadata=metadata,
        )
        await session.commit()
        return str(node.id)


async def _persist_download_result(req: DownloadChaptersRequest, result: Dict[str, Any]) -> str:
    file_path = str(result.get("file_path") or "")
    # 只把真正抓到的章节记为已下载：此前按 req.chapters 全量记账，熔断或部分失败
    # 时未下到的章节也被标成"已下载"，阅读器本地落空只能回退网络，看着像没下载。
    success_items = result.get("success")
    if success_items is None:
        # 兼容没有 success 明细的旧调用路径。
        chapter_indices = _chapter_indices(req.chapters)
    else:
        chapter_indices = [
            int(item.get("index"))
            for item in success_items
            if item.get("index") is not None
        ]

    async with AsyncSessionLocal() as session:
        node = await _resolve_novel_node(session, asset_id=req.asset_id or "", book_url=req.book_url)
        if node:
            metadata = _node_metadata(node)
            downloaded = set(metadata.get("downloaded_chapter_indices", []))
            downloaded.update(chapter_indices)

            chapter_count = int(metadata.get("chapter_count") or len(req.chapters) or 0)
            status = "ready" if chapter_count and len(downloaded) >= chapter_count else "partial"
            if not chapter_count and file_path:
                status = "ready"

            catalogs = metadata.get("catalogs", {}) if isinstance(metadata.get("catalogs"), dict) else {}
            if req.site and req.chapters:
                catalogs.setdefault(
                    req.site,
                    {
                        "chapters": req.chapters,
                        "chapter_count": len(req.chapters),
                        "source_name": metadata.get("source_name") or req.site,
                        "source_url": metadata.get("source_url") or "",
                        "toc_url": metadata.get("toc_url") or "",
                    },
                )

            metadata.update(
                {
                    "novel_title": metadata.get("novel_title") or req.book_title,
                    "author": metadata.get("author") or req.author,
                    "source_site": metadata.get("source_site") or req.site,
                    "book_url": metadata.get("book_url") or req.book_url,
                    "source_url": metadata.get("source_url") or req.book_url,
                    "chapters": metadata.get("chapters") or req.chapters,
                    "chapter_count": chapter_count or len(req.chapters),
                    "catalogs": catalogs,
                    "downloaded_chapters": sorted(downloaded),
                    "downloaded_chapter_indices": sorted(downloaded),
                    "content_path": file_path,
                    "last_downloaded": datetime.now().isoformat(),
                    "status": status,
                    "source": "novel_download",
                    "source_type": "novel_download",
                    "success_count": result.get("success_count", 0),
                    "failed_count": result.get("failed_count", 0),
                }
            )
            node.name = req.book_title
            node.metadata_json = metadata
            node.updated_at = datetime.utcnow()
            if metadata.get("cover_url"):
                node.thumbnail_url = metadata.get("cover_url")
            session.add(node)

            version_service = AssetVersionService(session)
            rep_service = AssetRepresentationService(session)
            version = await version_service.create(
                asset_node_id=str(node.id),
                prompt_used=req.book_title,
                model_used="",
                params=metadata,
                lineage={
                    "source": "novel_download",
                    "book_url": req.book_url,
                    "chapter_indices": chapter_indices,
                },
            )
            if file_path:
                await rep_service.create(
                    asset_version_id=str(version.id),
                    file_path=file_path,
                    mime_type="text/plain",
                    file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    format=os.path.splitext(file_path)[1].lstrip(".").lower() or "txt",
                    extra={
                        "book_url": req.book_url,
                        "content_path": file_path,
                        "downloaded_chapter_indices": sorted(downloaded),
                    },
                )
            await _record_downloaded_chapters(session, str(node.id), req.chapters)
            await session.commit()
            return str(node.id)

        metadata = {
            "novel_title": req.book_title,
            "author": req.author,
            "source_site": req.site,
            "book_url": req.book_url,
            "source_url": req.book_url,
            "chapters": req.chapters,
            "chapter_count": len(req.chapters),
            "downloaded_chapters": chapter_indices,
            "downloaded_chapter_indices": chapter_indices,
            "content_path": file_path,
            "last_read_chapter": 0,
            "last_read_position": 0,
            "last_downloaded": datetime.now().isoformat(),
            "status": "ready" if len(req.chapters) > 10 else "partial",
            "source": "novel_download",
            "source_type": "novel_download",
            "success_count": result.get("success_count", 0),
            "failed_count": result.get("failed_count", 0),
        }
        node = await _create_novel_node(
            session,
            title=req.book_title,
            author=req.author,
            cover_url="",
            metadata=metadata,
            file_path=file_path,
        )
        await _record_downloaded_chapters(session, str(node.id), req.chapters)
        await session.commit()
        return str(node.id)


@router.get("/search")
async def search_novels(
    q: str,
    site: str = "biqigecn",
    page: int = 1,
    limit: int = 20,
):
    try:
        crawler = get_crawler(site)
        results = crawler.search(q)
        start = (page - 1) * limit
        end = start + limit
        return {
            "success": True,
            "data": results[start:end],
            "total": len(results),
            "page": page,
            "limit": limit,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/catalog")
async def get_catalog(
    url: str,
    site: str = "",
    db: Session = Depends(get_db),
):
    try:
        manager = BookSourceManager(db)
        source = None
        if site:
            source = manager.get_source(site)
            if not source:
                for item in manager.sources:
                    if item.bookSourceUrl and url.startswith(item.bookSourceUrl.rstrip("/")):
                        source = item
                        break
            if not source and manager.sources:
                source = next((item for item in manager.sources if item.enabled_by_user), manager.sources[0])
        else:
            for item in manager.sources:
                if item.bookSourceUrl and url.startswith(item.bookSourceUrl.rstrip("/")):
                    source = item
                    break
            if not source:
                source = next((item for item in manager.sources if item.enabled_by_user), None)

        if not source:
            raise HTTPException(status_code=404, detail="没有可用的书源")

        chapters = await manager.get_chapter_list(source, url)
        normalized = [
            {"index": idx, "title": chapter.get("title") or chapter.get("name", ""), "url": chapter.get("url", "")}
            for idx, chapter in enumerate(chapters, 1)
        ]
        return {"success": True, "data": normalized, "total": len(normalized)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_catalog failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/add-to-bookshelf")
async def add_to_bookshelf(req: AddToBookshelfRequest):
    try:
        asset_id = await _upsert_bookshelf_node(req)
        logger.info(
            "[Bookshelf] added/upserted novel hub node | title=%s | asset_id=%s | chapters=%s",
            req.book_title,
            asset_id,
            len(req.chapters),
        )
        return {
            "success": True,
            "message": f"已将《{req.book_title}》加入书架",
            "asset_id": asset_id,
        }
    except Exception as exc:
        logger.exception("add_to_bookshelf failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/chapter-content")
async def get_chapter_content(
    chapter_url: str = Query(..., description="章节 URL"),
    source_id: str = Query("", description="书源 ID"),
    book_url: str = Query("", description="书籍 URL"),
    book_title: str = Query("", description="书名：已下载全本时优先读本地章节"),
    chapter_index: int = Query(0, description="章节序号（从 1 起）：配合 book_title 定位本地文件"),
    db: Session = Depends(get_db),
):
    try:
        # 本地优先：已下载的书直接读本地章节文件，省一次网络抓取（离线也能读）。
        local_content = read_local_chapter(book_title, chapter_index)
        if local_content:
            return {
                "success": True,
                "data": {"content": local_content, "source_name": "本地已下载"},
            }

        manager = BookSourceManager(db)
        source = None
        if source_id:
            source = manager.get_source(source_id)
        elif book_url:
            for item in manager.sources:
                if item.bookSourceUrl and book_url.startswith(item.bookSourceUrl.rstrip("/")):
                    source = item
                    break
        if not source:
            source = next((item for item in manager.sources if item.enabled_by_user), None)
        if not source:
            raise HTTPException(status_code=404, detail="没有可用的书源")

        content = await manager.get_chapter_content(source, chapter_url)
        if content is None:
            raise HTTPException(status_code=502, detail="无法获取章节内容，请检查书源规则后重试")

        return {"success": True, "data": {"content": content, "source_name": source.bookSourceName}}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_chapter_content failed")
        raise HTTPException(status_code=500, detail=f"获取章节内容失败: {exc}")


@router.get("/local-chapter")
async def get_local_chapter(
    id: str = Query(..., description="书架资产 ID"),
    chapter_index: int = Query(..., description="章节序号（从 1 起）"),
):
    """读取已下载书籍的本地章节（阅读器本地模式）。

    书已下载全本时，阅读器走这里而不是网络抓取——离线可读、不依赖书源可用性。
    """
    try:
        async with AsyncSessionLocal() as session:
            node = await _resolve_novel_node(session, asset_id=id)
            if not node:
                raise HTTPException(status_code=404, detail="书籍不存在")
            book_title = node.name or str(_node_metadata(node).get("title") or "")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    content = read_local_chapter(book_title, chapter_index)
    if not content:
        return {
            "success": False,
            "error": f"本地没有第 {chapter_index} 章的文件（可能未下载或下载失败）",
        }
    return {"success": True, "data": {"content": content, "source_name": "本地已下载"}}


@router.post("/local-sync")
async def sync_local_chapters(id: str = Query(..., description="书架资产 ID")):
    """按磁盘上真实存在的章节文件重算「已下载章节」索引。

    下载被中断、进程重启或中途取消时，索引会落后于磁盘：书架显示 0 章、
    阅读器误判"未下载"而走网络抓取。这里扫盘对齐一次，无需重新下载。
    """
    try:
        from app.services.novel.downloader import UPLOAD_DIR

        async with AsyncSessionLocal() as session:
            node = await _resolve_novel_node(session, asset_id=id)
            if not node:
                raise HTTPException(status_code=404, detail="书籍不存在")
            metadata = _node_metadata(node)
            book_title = node.name or str(metadata.get("title") or "")
            safe_title = NovelDownloader()._safe_filename(str(book_title))
            book_dir = UPLOAD_DIR / "novels" / safe_title
            disk_indices = {
                int(path.name.split("_", 1)[0])
                for path in book_dir.glob("*_*.txt")
                if path.name.split("_", 1)[0].isdigit()
            } if book_dir.is_dir() else set()
            if not disk_indices:
                return {
                    "success": False,
                    "error": f"本地没有找到《{book_title}》的章节文件，无需对齐（需要先下载）",
                }

            chapter_count = int(metadata.get("chapter_count") or len(metadata.get("chapters") or []) or 0)
            metadata["downloaded_chapters"] = sorted(disk_indices)
            metadata["downloaded_chapter_indices"] = sorted(disk_indices)
            metadata["status"] = (
                "ready" if chapter_count and len(disk_indices) >= chapter_count else "partial"
            )
            metadata["last_local_sync"] = datetime.now().isoformat()
            # metadata_json 是 JSONB 列，直接给 dict（与 _persist_download_result 一致）。
            node.metadata_json = metadata
            session.add(node)
            await session.commit()
            return {
                "success": True,
                "data": {
                    "asset_id": id,
                    "downloaded": len(disk_indices),
                    "chapter_count": chapter_count,
                    "status": metadata["status"],
                },
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("sync_local_chapters failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/bookshelf-item/{asset_id}")
async def get_bookshelf_item(asset_id: str):
    try:
        async with AsyncSessionLocal() as session:
            node = await _resolve_novel_node(session, asset_id=asset_id)
            if not node:
                raise HTTPException(status_code=404, detail="书籍不存在")
            payload = _novel_payload(node)
            logger.debug(
                "[get_bookshelf_item] asset_id=%s, chapters=%s, meta_keys=%s",
                asset_id,
                len(payload.get("chapters") or []),
                list(_node_metadata(node).keys()),
            )
            return {"success": True, "data": payload}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/download-chapters")
async def download_chapters(
    req: DownloadChaptersRequest,
    background_tasks: BackgroundTasks,
):
    try:
        # 同一本书同时只允许一个下载任务：重复点击会叠加出多个几百章的任务，
        # 把线程池与连接池吃光（实测会让整个后端停止响应）。
        book_key = str(req.asset_id or req.book_url or req.book_title or "").strip()
        async with _ACTIVE_DOWNLOADS_LOCK:
            running = _ACTIVE_DOWNLOADS.get(book_key)
        if running:
            raise HTTPException(
                status_code=409,
                detail=f"《{req.book_title}》正在下载中（任务 {running['task_id']}），请等待完成或先停止",
            )

        queue = get_task_queue()
        task = await queue.create_task(
            task_type="novel_download",
            payload={
                "book_title": req.book_title,
                "book_url": req.book_url,
                "asset_id": req.asset_id or "",
                "total": len(req.chapters),
            },
        )
        stop_event = threading.Event()
        async with _ACTIVE_DOWNLOADS_LOCK:
            _ACTIVE_DOWNLOADS[book_key] = {
                "task_id": task.task_id,
                "stop_event": stop_event,
                "title": req.book_title,
            }

        downloader = NovelDownloader()

        trace_id = task.task_id

        # 开始事件在主事件循环里 await：asyncpg 连接池绑定主 loop，后台线程另起
        # 事件循环复用它会报 "Future attached to a different loop"（事件根本写不进库）。
        try:
            from app.services.platform_log.service import record_event

            await record_event(
                scene="download",
                task_type="novel_download",
                task_id=trace_id,
                status="pending",
                message=f"小说下载开始：{req.book_title}（{len(req.chapters)} 章）",
            )
        except Exception:
            logger.debug("[NovelDownload] 开始事件写入失败（已忽略）", exc_info=True)

        progress_state: Dict[str, int] = {"done": 0, "total": len(req.chapters), "failed": 0}

        def _sync_download() -> Dict[str, Any]:
            """阻塞的抓取放进线程执行，避免拖慢主事件循环。

            这里的 asyncio.run 只服务于 downloader 的 aiofiles，不触碰 asyncpg 连接池。
            """
            downloader = NovelDownloader()

            async def _runner() -> Dict[str, Any]:
                async def fetch_via_source(url: str) -> Optional[str]:
                    """用书源规则抓正文（与在线阅读同一通道），硬编码爬虫只作兜底。"""
                    with SessionLocal() as session:
                        manager = BookSourceManager(session)
                        source = manager.get_source(req.site) if req.site else None
                        if source is None:
                            for item in manager.sources:
                                if item.bookSourceUrl and req.book_url.startswith(
                                    item.bookSourceUrl.rstrip("/")
                                ):
                                    source = item
                                    break
                        if source is None:
                            source = next(
                                (item for item in manager.sources if item.enabled_by_user), None
                            )
                        if source is None:
                            return None
                        return await manager.get_chapter_content(source, url)

                async def on_progress(done: int, total: int, title: str, ok: bool) -> None:
                    """只写共享状态：进度由主事件循环的 pump 协程读走并更新任务。"""
                    progress_state["done"] = int(done)
                    progress_state["total"] = int(total)
                    if not ok:
                        progress_state["failed"] = int(progress_state.get("failed") or 0) + 1

                return await downloader.download_chapters(
                    book_title=req.book_title,
                    author=req.author,
                    chapters=req.chapters,
                    site=req.site,
                    content_fetcher=fetch_via_source,
                    concurrency=NOVEL_DOWNLOAD_CONCURRENCY,
                    delay=0.5,
                    stop_event=stop_event,
                    progress_callback=on_progress,
                )

            return asyncio.run(_runner())

        async def run_download() -> None:
            started = time.time()
            error: str | None = None
            result: Dict[str, Any] = {}
            finished = asyncio.Event()

            async def pump_progress() -> None:
                """主事件循环里定期上报进度——抓取本身在线程，不会阻塞这里。"""
                while not finished.is_set():
                    await asyncio.sleep(1)
                    done = int(progress_state.get("done") or 0)
                    total = int(progress_state.get("total") or len(req.chapters) or 1)
                    failed_now = int(progress_state.get("failed") or 0)
                    percent = min(99, int(done / total * 100)) if total else 0
                    try:
                        await queue.update_progress(
                            task.task_id,
                            percent,
                            f"{done}/{total} 章"
                            + (f"，失败 {failed_now}" if failed_now else ""),
                        )
                    except Exception:
                        pass

            pump = asyncio.create_task(pump_progress())
            try:
                try:
                    result = await asyncio.to_thread(_sync_download)
                except Exception as exc:
                    error = str(exc)
                    logger.exception("novel download failed")
            finally:
                # 无论成败都要收尾：停掉进度协程、释放该书的下载占位。
                finished.set()
                try:
                    await asyncio.wait_for(pump, timeout=3)
                except Exception:
                    pump.cancel()
                async with _ACTIVE_DOWNLOADS_LOCK:
                    _ACTIVE_DOWNLOADS.pop(book_key, None)

            # 成败都落库：取消或中途报错时已抓到的章节不该丢，书架与阅读器
            # 能立刻用上这部分成果（此前只有"无异常"才写，一取消就全丢）。
            if result:
                try:
                    asset_id = await _persist_download_result(req, result)
                    logger.info(
                        "[NovelDownload] persisted to Asset Hub | title=%s | asset_id=%s | chapters=%s",
                        req.book_title,
                        asset_id,
                        len(req.chapters),
                    )
                except Exception as persist_exc:
                    error = f"下载完成但书架写入失败：{persist_exc}"
                    logger.exception("persist novel download failed")

            # 完成/失败事件同样在主事件循环里 await 落库：另起循环会跨 loop 报错，
            # 且"完成（N 章）"不能掩盖实际全部抓取失败的事实。
            success_count = int((result or {}).get("success_count") or 0)
            failed_count = int((result or {}).get("failed_count") or 0)
            try:
                from app.services.platform_log.service import record_event

                if error:
                    event_status, event_level = "failed", "error"
                    event_message = f"小说下载失败：{req.book_title}（{error}）"
                elif stop_event.is_set():
                    event_status, event_level = "cancelled", "info"
                    event_message = (
                        f"小说下载已取消：{req.book_title}（已完成 {success_count} 章）"
                    )
                elif success_count == 0:
                    event_status, event_level = "failed", "error"
                    # 带上首个真实错误（如 403 反爬），别让用户只看到"全部失败"。
                    first_error = str((result or {}).get("first_error") or "")
                    hint = (
                        f"，首个错误：{first_error[:150]}"
                        if first_error
                        else "，书源可能失效，请换书源重试"
                    )
                    aborted = bool((result or {}).get("aborted"))
                    event_message = (
                        f"小说下载失败：{req.book_title}"
                        f"（{failed_count} 章抓取失败{hint}"
                        f"{'；已熔断停止后续章节' if aborted else ''}）"
                    )
                else:
                    event_status, event_level = "success", "info"
                    event_message = (
                        f"小说下载完成：{req.book_title}"
                        f"（成功 {success_count} 章 / 失败 {failed_count} 章）"
                    )
                await record_event(
                    scene="download",
                    task_type="novel_download",
                    task_id=trace_id,
                    level=event_level,
                    status=event_status,
                    provider=str(req.site or ""),
                    message=event_message,
                    error=error,
                    duration_ms=int((time.time() - started) * 1000),
                    response={
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "file_path": str((result or {}).get("file_path") or ""),
                    },
                )
            except Exception:
                logger.debug("[NovelDownload] 事件日志写入失败（已忽略）", exc_info=True)

        background_tasks.add_task(run_download)

        mode_msg = "全文" if len(req.chapters) > 5 else f"{len(req.chapters)} 个章节"
        action = "更新" if req.asset_id else "创建"
        return {
            "success": True,
            "message": f"已开始下载{mode_msg}，{action}书架记录，请稍后查看",
            "task_id": task.task_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/download-tasks/{task_id}/cancel", summary="停止小说下载任务")
async def cancel_novel_download(task_id: str):
    """请求停止下载：正在抓取的章节会尽快收尾，已下载的章节保留。"""
    for key, item in list(_ACTIVE_DOWNLOADS.items()):
        if item.get("task_id") == task_id:
            item["stop_event"].set()
            try:
                await get_task_queue().append_event(
                    task_id, "cancelled", "已请求停止，等待当前章节收尾"
                )
            except Exception:
                pass
            return {
                "success": True,
                "message": "已请求停止，正在抓取的章节会尽快结束",
                "task_id": task_id,
            }
    raise HTTPException(status_code=404, detail="任务不存在或已结束")


@router.get("/sources")
async def get_sources(db: Session = Depends(get_db)):
    manager = BookSourceManager(db)
    sources = manager.list_sources(enabled_only=True)
    return {
        "success": True,
        "data": [
            {
                "id": item["id"],
                "name": item["book_source_name"] + ("(JS)" if item.get("is_js_source") else ""),
                "enabled": item["enabled_by_user"],
            }
            for item in sources
        ],
    }


@router.get("/source-catalog")
async def get_source_catalog(
    book_url: str = Query(..., description="书籍 URL"),
    source_id: str = Query(..., description="目标书源 ID"),
    book_title: str = Query("", description="书籍名称"),
    db: Session = Depends(get_db),
):
    try:
        manager = BookSourceManager(db)
        source = manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="书源不存在")

        catalog_url = ""
        chapters: List[Dict[str, Any]] = []

        if book_title:
            logger.info("[换源] source=%s, search=%s", source.bookSourceName, book_title)
            try:
                results = await manager._search_single_source(source, book_title)
                if results:
                    def normalize(value: str) -> str:
                        return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", value).lower()

                    target = normalize(book_title)
                    matched = next((item for item in results if normalize(item.get("name", "")) == target), None)
                    if matched:
                        catalog_url = matched.get("bookUrl", "") or matched.get("url", "") or matched.get("tocUrl", "")
                        if catalog_url:
                            chapters = await manager.get_chapter_list(source, catalog_url)
            except Exception:
                logger.exception("[换源] search strategy failed")

        if not chapters:
            target_base = source.bookSourceUrl.rstrip("/")
            catalog_url = target_base
            if source.ruleToc and isinstance(source.ruleToc, dict):
                toc_template = source.ruleToc.get("bookUrl", "") or source.ruleToc.get("url", "")
                if toc_template and toc_template.startswith("http"):
                    catalog_url = toc_template
                elif toc_template:
                    catalog_url = target_base + toc_template
            chapters = await manager.get_chapter_list(source, catalog_url)

        if not chapters:
            raise HTTPException(status_code=404, detail="该书源无法获取目录，可能需要手动配置目录页 URL")

        normalized = [
            {"index": idx, "title": chapter.get("title") or chapter.get("name", ""), "url": chapter.get("url", "")}
            for idx, chapter in enumerate(chapters, 1)
        ]
        return {
            "success": True,
            "data": {
                "source_id": source_id,
                "source_name": source.bookSourceName,
                "catalog_url": catalog_url,
                "chapters": normalized,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_source_catalog failed")
        raise HTTPException(status_code=500, detail=str(exc))
