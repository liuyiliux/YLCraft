"""
YLCraft — 微信公众号 API

POST /api/v1/wechat-mp/login/qrcode          — 生成登录二维码
GET  /api/v1/wechat-mp/login/status/{sid}    — 轮询登录状态
GET  /api/v1/wechat-mp/search-accounts        — 搜索公众号
GET  /api/v1/wechat-mp/articles               — 拉取文章列表
POST /api/v1/wechat-mp/download-single        — 下载单篇文章
POST /api/v1/wechat-mp/download-batch         — 批量下载文章
POST /api/v1/wechat-mp/import-assets          — 导入素材库
"""

from __future__ import annotations

import json
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.database import get_async_session
from app.db.models.platform_connection import PlatformConnection, PlatformConnectionResponse
from app.db.models.wechat_mp import WechatMPDownload, WechatMPDownloadCreate, WechatMPDownloadResponse
from app.services.wechat_mp import get_wechat_mp_service

router = APIRouter()
logger = logging.getLogger("ylcraft.wechat_mp")


# ── 请求/响应模型 ──────────────────────────────────────────────

class QRCodeLoginResponse(BaseModel):
    session_id: str
    qr_url: str
    qr_uuid: str


class LoginStatusResponse(BaseModel):
    status: str  # waiting / scanned / confirmed / expired / error
    cookie: str = ""
    token: str = ""
    nickname: str = ""
    head_img: str = ""
    message: str = ""


class SearchAccountsRequest(BaseModel):
    keyword: str
    conn_id: str
    page: int = 1
    page_size: int = 20


class AccountInfo(BaseModel):
    fake_id: str
    nickname: str
    alias: str = ""
    round_head_img: str = ""
    service_type: int = 0
    signature: str = ""


class SearchAccountsResponse(BaseModel):
    total: int
    list: list[AccountInfo]


class ArticleInfo(BaseModel):
    aid: str = ""
    appmsgid: int = 0
    title: str
    link: str
    cover: str = ""
    digest: str = ""
    create_time: int = 0
    update_time: int = 0
    item_idx: int = 0
    content_url: str = ""
    source_url: str = ""
    is_pay_subscribe: int = 0


class ArticleListResponse(BaseModel):
    total_count: int
    list: list[ArticleInfo]
    error: str = ""
    error_code: int = 0


class DownloadSingleRequest(BaseModel):
    conn_id: str
    article_url: str
    article_title: str = ""
    format: str = "md"  # md / html / epub / pdf
    download_dir: str = ""


class DownloadSingleResponse(BaseModel):
    success: bool
    file_path: str = ""
    file_size: int = 0
    format: str = "md"
    title: str = ""
    author: str = ""
    download_dir: str = ""  # 下载目录（用于生成 EPUB）
    error: str = ""
    skipped: bool = False  # 命中去重跳过
    record_id: str = ""    # 下载记录 id


class DownloadBatchRequest(BaseModel):
    conn_id: str
    articles: list[ArticleInfo]
    format: str = "md"
    download_dir: str = ""
    concurrency: int = 3  # 并发下载数（1~8）


class DownloadBatchResponse(BaseModel):
    total: int
    downloaded: int
    failed: int
    success: bool = True
    download_dir: str = ""
    file_paths: list[str] = []
    article_data: list[dict] = []   # 轻量级解析结果，供 EPUB 导出使用
    error: str = ""
    skipped: int = 0  # 命中去重跳过的数量
    task_id: str = ""  # WebSocket 进度订阅用


class ImportAssetsRequest(BaseModel):
    conn_id: str
    file_paths: list[str]
    account_name: str = ""


class EpubArticle(BaseModel):
    title: str = ""
    author: str = ""
    publish_time: str = ""
    content_html: str = ""
    source_url: str = ""
    file_path: str = ""


class ExportEpubRequest(BaseModel):
    conn_id: str
    book_title: str
    articles: list[EpubArticle]
    download_dir: str = ""
    images_base_dir: str = ""


class ExportEpubResponse(BaseModel):
    success: bool
    file_path: str = ""
    file_size: int = 0
    format: str = "epub"
    record_id: str = ""
    error: str = ""


# ── 登录 ──────────────────────────────────────────────────────

@router.post("/login/qrcode", response_model=QRCodeLoginResponse, summary="生成登录二维码")
async def start_qrcode_login(conn_id: str = Query(..., description="平台连接 ID")):
    """生成微信公众平台登录二维码"""
    service = get_wechat_mp_service()
    result = await service.start_qrcode_login(conn_id)
    return QRCodeLoginResponse(**result)


@router.get("/login/status/{session_id}", response_model=LoginStatusResponse, summary="轮询登录状态")
async def check_login_status(session_id: str):
    """轮询扫码登录状态"""
    service = get_wechat_mp_service()
    result = await service.check_login_status(session_id)
    return LoginStatusResponse(**result)


# ── 搜索公众号 ──────────────────────────────────────────────────

@router.get("/search-accounts", response_model=SearchAccountsResponse, summary="搜索公众号")
async def search_accounts(
    conn_id: str = Query(..., description="平台连接 ID"),
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """
    搜索微信公众号

    需要 conn_id 对应的连接已登录（有有效 Cookie）。
    """
    service = get_wechat_mp_service()

    # 从数据库获取连接的 Cookie
    cookie, token = await _get_conn_credentials(conn_id)

    result = await service.search_accounts(
        conn_id=conn_id,
        keyword=keyword,
        cookie=cookie,
        token=token,
        page=page,
        page_size=page_size,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return SearchAccountsResponse(
        total=result.get("total", 0),
        list=[AccountInfo(**a) for a in result.get("list", [])],
    )


# ── 拉取文章列表 ────────────────────────────────────────────────

@router.get("/articles", response_model=ArticleListResponse, summary="拉取文章列表")
async def get_articles(
    conn_id: str = Query(..., description="平台连接 ID"),
    fake_id: str = Query(..., description="公众号 FakeID"),
    begin: int = Query(0, ge=0, description="起始位置"),
    count: int = Query(5, ge=1, le=5, description="每页数量（最大5）"),
):
    """拉取公众号历史文章列表"""
    service = get_wechat_mp_service()
    cookie, token = await _get_conn_credentials(conn_id)

    result = await service.get_articles(
        conn_id=conn_id,
        fake_id=fake_id,
        cookie=cookie,
        token=token,
        begin=begin,
        count=count,
    )

    return ArticleListResponse(
        total_count=result.get("total_count", 0),
        list=[ArticleInfo(**a) for a in result.get("list", [])],
        error=result.get("error", ""),
        error_code=result.get("error_code", 0),
    )


# ── 下载文章 ──────────────────────────────────────────────────

@router.post("/download-single", response_model=DownloadSingleResponse, summary="下载单篇文章")
async def download_single_article(req: DownloadSingleRequest):
    """下载单篇微信公众号文章（返回 Markdown/HTML 文件）"""
    service = get_wechat_mp_service()
    cookie, _ = await _get_conn_credentials(req.conn_id)

    result = await service.download_article(
        conn_id=req.conn_id,
        article_url=req.article_url,
        article_title=req.article_title,
        cookie=cookie,
        format=req.format,
        download_dir=req.download_dir,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "下载失败"))

    return DownloadSingleResponse(**result)


@router.post("/download-batch", response_model=DownloadBatchResponse, summary="批量下载文章")
async def download_batch_articles(req: DownloadBatchRequest):
    """批量下载微信公众号文章"""
    service = get_wechat_mp_service()
    cookie, _ = await _get_conn_credentials(req.conn_id)

    articles = [a.model_dump() if hasattr(a, "model_dump") else a for a in req.articles]
    result = await service.download_articles_batch(
        conn_id=req.conn_id,
        articles=articles,
        cookie=cookie,
        format=req.format,
        download_dir=req.download_dir,
        concurrency=req.concurrency,
    )

    return DownloadBatchResponse(**result)


# ── 导出 EPUB ──────────────────────────────────────────────────

@router.post("/export-epub", response_model=ExportEpubResponse, summary="多篇已下载文章合并导出 EPUB")
async def export_epub(req: ExportEpubRequest):
    """
    将多篇已下载文章合并导出为单个 EPUB 电子书。

    articles 中的 content_html 应为已本地化图片的 HTML（图片引用 images/xxx），
    可由前端在下载后回传；images_base_dir 指向图片所在根目录。
    """
    service = get_wechat_mp_service()
    articles = [a.model_dump() for a in req.articles]
    try:
        result = await service.export_batch_to_epub(
            conn_id=req.conn_id,
            articles=articles,
            book_title=req.book_title,
            download_dir=req.download_dir,
            images_base_dir=req.images_base_dir,
        )
        return ExportEpubResponse(**result)
    except Exception as e:
        logger.error(f"[wechat-mp/export-epub] 导出失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 导入素材库 ──────────────────────────────────────────────────

@router.post("/import-assets", summary="将已下载文章导入素材库")
async def import_articles_to_assets(req: ImportAssetsRequest):
    """将已下载的公众号文章导入素材库"""
    from app.services.asset.service import AssetService
    from app.db.models.asset import Asset
    from app.services.asset.document_metadata import (
        extract_document_asset_metadata,
        resolve_document_cover_source,
    )

    imported = []
    failed = []

    async with get_async_session() as session:
        asset_service = AssetService(session)

        for file_path in req.file_paths:
            try:
                path = Path(file_path).expanduser()
                if not path.exists() or not path.is_file():
                    failed.append({"file_path": file_path, "error": "文件不存在"})
                    continue
                resolved_path = path.resolve()

                record = (await session.execute(
                    select(WechatMPDownload)
                    .where(WechatMPDownload.file_path == str(resolved_path))
                    .order_by(WechatMPDownload.updated_at.desc())
                    .limit(1)
                )).scalars().first()

                file_meta = extract_document_asset_metadata(resolved_path)
                title = (
                    (record.article_title if record else "")
                    or file_meta.get("title", "")
                    or _title_from_article_file(resolved_path)
                )
                author = (
                    (record.account_name if record else "")
                    or file_meta.get("author", "")
                    or req.account_name
                    or ""
                )
                cover_url = (
                    resolve_document_cover_source(resolved_path, file_meta.get("cover_ref", ""))
                    or (record.cover_url if record else "")
                    or ""
                )
                article_url = (
                    (record.article_url if record else "")
                    or file_meta.get("source_url", "")
                    or ""
                )
                source_url = article_url or f"ylcraft://local-document/{resolved_path.as_posix()}"
                file_size = resolved_path.stat().st_size
                fmt = (record.format if record else "") or resolved_path.suffix.lower().lstrip(".")
                publish_time = record.publish_time.isoformat() if record and record.publish_time else ""
                metadata = {
                    "description": (record.digest if record else "") or "",
                    "reader_root_path": str(resolved_path.parent),
                    "local_file_path": str(resolved_path),
                    "article_url": article_url,
                    "download_record_id": record.id if record else "",
                    "format": fmt,
                    "digest": (record.digest if record else "") or "",
                    "publish_time": publish_time,
                    "cover_url": cover_url,
                    "cover_ref": file_meta.get("cover_ref", ""),
                }
                tags_json = json.dumps(["wechat_mp", "article"], ensure_ascii=False)

                existing_by_path = (await session.execute(
                    select(Asset)
                    .where(Asset.file_path == str(resolved_path))
                    .where(Asset.status != "DELETED")
                    .limit(1)
                )).scalars().first()
                existing_by_url = await asset_service.get_by_url(source_url)
                asset = existing_by_url or existing_by_path

                if asset:
                    asset.title = title
                    asset.type = "ARTICLE"
                    asset.platform = "wechat_mp"
                    asset.source_type = "download"
                    asset.source_url = source_url
                    asset.file_path = str(resolved_path)
                    asset.file_size = file_size
                    asset.mime_type = _guess_article_mime_type(resolved_path)
                    asset.status = "READY"
                    asset.author = author
                    if cover_url:
                        asset.cover_url = cover_url
                    asset.metadata_json = json.dumps(metadata, ensure_ascii=False)
                    if not asset.tags or asset.tags == "[]":
                        asset.tags = tags_json
                    asset.updated_at = datetime.now()
                    await session.flush()
                    await session.refresh(asset)
                    imported.append({"file_path": str(resolved_path), "asset_id": asset.id, "updated": True})
                else:
                    asset = await asset_service.create(
                        title=title,
                        type="ARTICLE",
                        platform="wechat_mp",
                        source_type="download",
                        source_url=source_url,
                        file_path=str(resolved_path),
                        file_size=file_size,
                        mime_type=_guess_article_mime_type(resolved_path),
                        status="READY",
                        author=author,
                        cover_url=cover_url,
                        metadata_json=json.dumps(metadata, ensure_ascii=False),
                        tags=tags_json,
                    )
                    imported.append({"file_path": str(resolved_path), "asset_id": asset.id, "updated": False})

                if record:
                    record.asset_id = asset.id
            except Exception as e:
                logger.error(f"[wechat-mp/import] 导入失败 {file_path}: {e}")
                failed.append({"file_path": file_path, "error": str(e)})

        # async with 退出时自动 commit（见 get_async_session）

    return {
        "total": len(req.file_paths),
        "imported": len(imported),
        "failed": len(failed),
        "imported_items": imported,
        "failed_items": failed,
    }


# ── 辅助函数 ──────────────────────────────────────────────────

def _title_from_article_file(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_", 2)
    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 8:
        return parts[2] or stem
    return stem


def _guess_article_mime_type(path: Path) -> str:
    guessed = mimetypes.guess_type(str(path))[0]
    if guessed:
        return guessed
    suffix = path.suffix.lower()
    if suffix in {".htm", ".html"}:
        return "text/html"
    if suffix in {".md", ".markdown"}:
        return "text/markdown"
    if suffix == ".epub":
        return "application/epub+zip"
    if suffix in {".txt", ".text"}:
        return "text/plain"
    return "application/octet-stream"


async def _get_conn_credentials(conn_id: str) -> tuple[str, str]:
    """
    从数据库获取连接的 Cookie 和 Token

    Returns:
        (cookie_str, token_str)
    """
    from sqlalchemy import text

    try:
        async with get_async_session() as session:
            if conn_id:
                result = await session.execute(
                    text("SELECT credentials, cookie_content FROM platform_connections WHERE id = :id"),
                    {"id": conn_id},
                )
            else:
                result = await session.execute(
                    text(
                        "SELECT credentials, cookie_content FROM platform_connections "
                        "WHERE platform = 'wechat_mp' AND status = 'active' "
                        "ORDER BY updated_at DESC LIMIT 1"
                    )
                )
            row = result.fetchone()
            if row:
                credentials = {}
                try:
                    credentials = json.loads(row[0] or "{}")
                except (json.JSONDecodeError, TypeError):
                    pass
                token = credentials.get("token", "")
                # 优先从 credentials 获取，其次从 cookie_content 获取（Netscape格式需要转换）
                cookie = credentials.get("raw") or credentials.get("content") or ""
                if not cookie and row[1]:
                    # 尝试从 cookie_content（Netscape格式）提取原始 Cookie
                    try:
                        from app.services.cookies.manager import get_cookie_manager
                        mgr = get_cookie_manager()
                        cookie = mgr.extract_raw(row[1]) or ""
                    except Exception as e:
                        logger.warning(f"[_get_conn_credentials] 解析 cookie_content 失败: {e}")
                return cookie, token
    except Exception as e:
        logger.warning(f"[wechat-mp] 获取凭证失败: {e}")

    return "", ""
