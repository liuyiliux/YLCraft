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
import uuid
from datetime import datetime, timezone
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
    format: str = "md"  # md / html / epub
    download_dir: str = ""


class DownloadSingleResponse(BaseModel):
    success: bool
    file_path: str = ""
    file_size: int = 0
    format: str = "md"
    title: str = ""
    author: str = ""
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
async def import_articles_to_assets(
    req: ImportAssetsRequest,
    session=Depends(get_async_session),
):
    """将已下载的公众号文章导入素材库"""
    from app.services.asset.service import AssetService
    import os as _os

    asset_service = AssetService()
    imported = []
    failed = []

    for file_path in req.file_paths:
        try:
            if not _os.path.exists(file_path):
                failed.append({"file_path": file_path, "error": "文件不存在"})
                continue

            file_name = _os.path.basename(file_path)
            # 尝试从文件名解析标题（格式: YYYYMMDD_HHMMSS_标题.ext）
            title = file_name
            if "_" in file_name:
                parts = file_name.split("_", 2)
                if len(parts) >= 3:
                    title = parts[2].rsplit(".", 1)[0]

            asset = await asset_service.create(
                title=title,
                asset_type="ARTICLE",
                platform="wechat_mp",
                source_type="download",
                source_url="",
                file_path=file_path,
                file_size=_os.path.getsize(file_path),
                status="READY",
                author=req.account_name or "",
            )
            if asset:
                imported.append({"file_path": file_path, "asset_id": asset.id})
            else:
                failed.append({"file_path": file_path, "error": "创建素材失败"})
        except Exception as e:
            logger.error(f"[wechat-mp/import] 导入失败 {file_path}: {e}")
            failed.append({"file_path": file_path, "error": str(e)})

    return {
        "total": len(req.file_paths),
        "imported": len(imported),
        "failed": len(failed),
        "imported_items": imported,
        "failed_items": failed,
    }


# ── 辅助函数 ──────────────────────────────────────────────────

async def _get_conn_credentials(conn_id: str) -> tuple[str, str]:
    """
    从数据库获取连接的 Cookie 和 Token

    Returns:
        (cookie_str, token_str)
    """
    session_gen = get_async_session()
    session = await session_gen.__anext__() if hasattr(session_gen, "__anext__") else None

    if session is None:
        return "", ""

    try:
        from sqlalchemy import text
        result = await session.execute(
            text("SELECT credentials, cookie_content FROM platform_connections WHERE id = :id"),
            {"id": conn_id},
        )
        row = result.fetchone()
        if row:
            credentials = {}
            try:
                credentials = json.loads(row[0] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            token = credentials.get("token", "")
            cookie = credentials.get("raw") or credentials.get("content") or ""
            if not cookie and row[1]:
                cookie = row[1]
                if cookie.startswith("# Netscape HTTP Cookie File"):
                    try:
                        from app.services.cookies.manager import get_cookie_manager
                        cookie = get_cookie_manager().extract_raw(cookie)
                    except Exception:
                        pass
            return cookie, token
    except Exception as e:
        logger.warning(f"[wechat-mp] 获取凭证失败: {e}")
    finally:
        try:
            await session.close()
        except Exception:
            pass

    return "", ""
