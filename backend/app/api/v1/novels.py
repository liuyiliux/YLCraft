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
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

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
from app.services.novel.downloader import NovelDownloader

router = APIRouter(tags=["novels"])
logger = logging.getLogger("ylcraft.api.novels")

_NOVEL_SOURCE_TYPES = {"novel", "novel_bookshelf", "novel_download"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    chapter_indices = _chapter_indices(req.chapters)

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
    db: Session = Depends(get_db),
):
    try:
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
        downloader = NovelDownloader()

        def do_download():
            result = asyncio.run(
                downloader.download_chapters(
                    book_title=req.book_title,
                    author=req.author,
                    chapters=req.chapters,
                    site=req.site,
                )
            )
            try:
                asset_id = asyncio.run(_persist_download_result(req, result))
                logger.info(
                    "[NovelDownload] persisted to Asset Hub | title=%s | asset_id=%s | chapters=%s",
                    req.book_title,
                    asset_id,
                    len(req.chapters),
                )
            except Exception:
                logger.exception("persist novel download failed")

        background_tasks.add_task(do_download)

        mode_msg = "全文" if len(req.chapters) > 5 else f"{len(req.chapters)} 个章节"
        action = "更新" if req.asset_id else "创建"
        return {
            "success": True,
            "message": f"已开始下载{mode_msg}，{action}书架记录，请稍后查看",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
