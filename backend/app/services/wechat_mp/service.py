"""
微信公众号服务 — 业务编排层

整合 API 客户端、二维码适配器、解析器，提供高层业务操作。
扫码登录统一走 cookies.platforms 的 QrcodeAdapter 体系。
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Optional

from .api_client import WechatMPAPIClient
from .parser import WechatMPParser
from app.core.config import ensure_download_path
from app.services.cookies.platforms import get_qrcode_adapter

logger = logging.getLogger("ylcraft.wechat_mp.service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WechatMPService:
    """
    微信公众号业务服务

    功能：
        - 扫码登录流程管理（通过 QrcodeAdapter）
        - 搜索公众号
        - 拉取文章列表
        - 下载单篇文章
        - 批量下载文章
        - 导入素材库
    """

    # parsed 结果缓存配置（parse 端点 → download 复用，避免二次抓取）
    _PARSED_CACHE_TTL = 300  # 5 分钟
    _PARSED_CACHE_MAX = 50

    def __init__(self):
        self._clients: dict[str, WechatMPAPIClient] = {}
        self._parser = WechatMPParser()
        # 登录会话 {session_id: {status, session_key, conn_id, created_at}}
        self._login_sessions: dict[str, dict] = {}
        # parsed 缓存 {article_url: (timestamp, parsed_copy, html)}
        self._parsed_cache: dict[str, tuple[float, dict, str]] = {}

    # ── 客户端管理 ──────────────────────────────────────────────

    def _get_client(self, conn_id: str, cookie: str = "", token: str = "") -> WechatMPAPIClient:
        """获取或创建 API 客户端"""
        if conn_id not in self._clients:
            self._clients[conn_id] = WechatMPAPIClient(cookie_str=cookie, token=token)
        else:
            client = self._clients[conn_id]
            if cookie:
                client.cookie = cookie
            if token:
                client.token = token
        return self._clients[conn_id]

    # ── 下载记录落库（wechat_mp_downloads）─────────────────────

    async def _find_existing_download(self, article_url: str, fmt: str = "") -> Optional[dict]:
        """
        按 article_url 查询已存在的下载记录（用于去重）。
        fmt 传入时只复用同格式文件，避免用户选择 HTML 时命中旧 MD。
        返回 dict（{id, status, file_path}）或 None。
        """
        from sqlalchemy import select
        from app.db.database import get_async_session
        from app.db.models.wechat_mp import WechatMPDownload

        try:
            async with get_async_session() as session:
                conditions = [
                    WechatMPDownload.article_url == article_url
                ]
                if fmt:
                    conditions.append(WechatMPDownload.format == fmt)
                stmt = select(WechatMPDownload).where(*conditions)
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row:
                    return {
                        "id": row.id,
                        "status": row.status,
                        "file_path": row.file_path,
                        "format": row.format,
                        "title": row.article_title,
                        "author": row.account_name,
                        "publish_time": row.publish_time.strftime("%Y-%m-%d %H:%M:%S") if row.publish_time else "",
                    }
                return None
        except Exception as e:
            logger.warning(f"[WechatMPService] 查询去重记录失败（忽略，继续下载）: {e}")
            return None

    async def _record_download(
        self,
        *,
        conn_id: str,
        article_url: str,
        article_title: str,
        author: str,
        file_path: str,
        file_size: int,
        fmt: str,
        status: str,
        cover_url: str = "",
        digest: str = "",
        publish_time: Optional[datetime] = None,
        error_message: str = "",
        account_name: str = "",
        account_fake_id: str = "",
    ) -> Optional[str]:
        """
        落库一条下载记录（upsert：按 article_url + format 去重）。
        返回记录 id；失败时返回 None（不影响下载主流程）。
        """
        from sqlalchemy import select
        from app.db.database import get_async_session
        from app.db.models.wechat_mp import WechatMPDownload

        try:
            # 处理 publish_time：支持字符串格式转换
            if isinstance(publish_time, str):
                try:
                    publish_time = datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        publish_time = datetime.strptime(publish_time, "%Y-%m-%d")
                    except ValueError:
                        publish_time = None

            async with get_async_session() as session:
                stmt = select(WechatMPDownload).where(
                    WechatMPDownload.article_url == article_url,
                    WechatMPDownload.format == fmt,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                now = _utcnow()

                if existing is None:
                    record = WechatMPDownload(
                        id=str(uuid.uuid4()),
                        conn_id=conn_id,
                        account_name=account_name or author,
                        account_fake_id=account_fake_id,
                        article_title=article_title,
                        article_url=article_url,
                        cover_url=cover_url,
                        digest=digest,
                        publish_time=publish_time,
                        status=status,
                        format=fmt,
                        file_path=file_path,
                        file_size=file_size,
                        error_message=error_message,
                        updated_at=now,
                    )
                    session.add(record)
                else:
                    # 已存在则更新（同 URL + 同格式重新下载：刷新状态/路径/时间）
                    existing.status = status
                    existing.file_path = file_path
                    existing.file_size = file_size
                    existing.error_message = error_message
                    if article_title:
                        existing.article_title = article_title
                    if account_name:
                        existing.account_name = account_name
                    if cover_url:
                        existing.cover_url = cover_url
                    if digest:
                        existing.digest = digest
                    if publish_time:
                        existing.publish_time = publish_time
                    existing.updated_at = now

                await session.commit()
                return existing.id if existing else record.id  # type: ignore[union-attr]
        except Exception as e:
            logger.warning(f"[WechatMPService] 落库下载记录失败（忽略）: {e}")
            return None

    # ── 登录流程（通过 QrcodeAdapter）──────────────────────────

    async def start_qrcode_login(self, conn_id: str) -> dict:
        """
        启动扫码登录

        使用 WechatMPQrcodeAdapter 生成二维码。

        Returns:
            { session_id, qr_url, qr_uuid }
            qr_url 是 data:image/jpg;base64,... 格式的 data URI
        """
        adapter = get_qrcode_adapter("wechat_mp")
        if not adapter:
            raise RuntimeError("微信公众号二维码适配器不可用")

        result = await adapter.generate_qrcode()

        session_id = str(uuid.uuid4())
        self._login_sessions[session_id] = {
            "status": "waiting",
            "session_key": result.get("session_key", ""),
            "conn_id": conn_id,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }

        return {
            "session_id": session_id,
            "qr_url": result.get("qr_image_base64", ""),
            "qr_uuid": result.get("session_key", ""),
        }

    async def check_login_status(self, session_id: str) -> dict:
        """
        轮询扫码登录状态

        Returns:
            { status, cookie, token, nickname, head_img, message }
        """
        session = self._login_sessions.get(session_id)
        if not session:
            return {"status": "error", "message": "会话不存在或已过期"}

        adapter = get_qrcode_adapter("wechat_mp")
        if not adapter:
            return {"status": "error", "message": "二维码适配器不可用"}

        session_key = session.get("session_key", "")
        if not session_key:
            return {"status": "error", "message": "会话缺少 session_key"}

        result = await adapter.check_status(session_key)

        status = result.get("status", "waiting")
        session["status"] = status

        if status == "confirmed":
            cookies_array = result.get("cookies", [])
            account_info = result.get("account_info", {})

            # 拼接 cookie 字符串
            cookie_str = "; ".join(
                f"{c['name']}={c['value']}" for c in cookies_array
            )

            # 从 account_info 或 redirect_url 提取 token
            token = account_info.get("account_id", "")
            self._persist_login_result(
                conn_id=session.get("conn_id", ""),
                cookie_str=cookie_str,
                token=token,
                account_info=account_info,
            )

            return {
                "status": "confirmed",
                "cookie": cookie_str,
                "token": token,
                "nickname": account_info.get("account_name", ""),
                "head_img": account_info.get("account_avatar", ""),
            }

        return {"status": status}

    # ── 搜索公众号 ──────────────────────────────────────────────

    def _persist_login_result(
        self,
        conn_id: str,
        cookie_str: str,
        token: str,
        account_info: dict,
    ) -> None:
        if not conn_id or not cookie_str:
            return

        try:
            from app.db.database import SessionLocal
            from app.db.models.platform_connection import (
                AcquisitionMethod,
                ConnectionStatus,
                PlatformConnectionUpdate,
            )
            from app.services.platform_connection.service import PlatformConnectionService

            db = SessionLocal()
            try:
                service = PlatformConnectionService(db)
                conn = service.get(conn_id)
                if not conn:
                    logger.warning(f"[WechatMPService] connection not found: {conn_id}")
                    return

                creds = conn.get_credentials()
                creds.update({
                    "raw": cookie_str,
                    "source": "qrcode",
                })
                if token:
                    creds["token"] = token

                service.update(
                    conn_id,
                    PlatformConnectionUpdate(
                        credentials=creds,
                        status=ConnectionStatus.ACTIVE,
                        acquisition_method=AcquisitionMethod.QRCODE,
                        account_id=token or account_info.get("account_id") or conn.account_id,
                        account_name=account_info.get("account_name") or conn.account_name or conn.name,
                        account_avatar=account_info.get("account_avatar") or conn.account_avatar,
                        account_url=account_info.get("account_url") or conn.account_url or "https://mp.weixin.qq.com/",
                    ),
                )
                logger.info(f"[WechatMPService] login result saved: {conn_id}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[WechatMPService] save login result failed: {e}")

    async def search_accounts(
        self,
        conn_id: str,
        keyword: str,
        cookie: str = "",
        token: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """搜索公众号"""
        client = self._get_client(conn_id, cookie=cookie, token=token)
        return await client.search_accounts(keyword, page, page_size)

    async def search_global_articles(
        self,
        conn_id: str,
        keyword: str,
        cookie: str = "",
        token: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        """按关键词搜索全网公众号文章，并缓存返回正文供下载复用。"""
        client = self._get_client(conn_id, cookie=cookie, token=token)
        result = await client.search_global_articles(
            keyword=keyword,
            begin=(max(page, 1) - 1) * min(page_size, 10),
            count=min(page_size, 10),
        )

        if not result.get("error"):
            for article in result.get("list", []) or []:
                link = article.get("link", "")
                content_html = article.get("content", "")
                if not link or not content_html:
                    continue
                parsed, html = self._build_global_article_cache(article)
                self.cache_parsed(link, parsed, html)

        return result

    def _build_global_article_cache(self, article: dict) -> tuple[dict, str]:
        """将版权检测接口返回的正文片段包装成标准微信文章解析结果。"""
        title = article.get("title", "") or "未命名文章"
        author = article.get("nickname") or article.get("author") or "公众号"
        link = article.get("link", "")
        content_html = article.get("content", "") or ""
        cover = article.get("cover", "") or ""
        digest = article.get("digest", "") or ""

        cover_attr = escape(cover, quote=True).replace("&amp;", "&")

        html = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<meta property=\"og:title\" content=\"{escape(title, quote=True)}\">"
            f"<meta name=\"author\" content=\"{escape(author, quote=True)}\">"
            f"<meta property=\"og:image\" content=\"{cover_attr}\">"
            f"<title>{escape(title)}</title>"
            "</head><body>"
            f"<h1 id=\"activity-name\">{escape(title)}</h1>"
            f"<div id=\"js_name\">{escape(author)}</div>"
            f"<div id=\"js_content\">{content_html}</div>"
            "</body></html>"
        )
        parsed = self._parser.parse(html, link)
        parsed.update({
            "title": parsed.get("title") or title,
            "author": parsed.get("author") or author,
            "content_html": parsed.get("content_html") or content_html,
            "content_text": parsed.get("content_text") or digest,
            "cover": parsed.get("cover") or cover,
            "source_url": parsed.get("source_url") or article.get("source_url", ""),
            "article_url": link,
            "error": parsed.get("error", ""),
        })
        if cover and cover not in parsed.get("images", []):
            parsed["images"] = [*parsed.get("images", []), cover]
        return parsed, html

    # ── 文章列表 ────────────────────────────────────────────────

    async def get_articles(
        self,
        conn_id: str,
        fake_id: str,
        cookie: str = "",
        token: str = "",
        begin: int = 0,
        count: int = 5,
    ) -> dict:
        """拉取文章列表"""
        client = self._get_client(conn_id, cookie=cookie, token=token)
        return await client.get_articles(fake_id, begin, count)

    # ── parsed 结果缓存（parse 端点 → download 复用）──────────────

    def cache_parsed(self, article_url: str, parsed: dict, html: str = "") -> None:
        """
        缓存已解析结果，供随后的 download_article 复用（跳过二次抓取+解析）。
        仅存内存，进程重启即失效；带 TTL 与容量上限，避免泄漏。
        """
        if not article_url or not parsed:
            return
        # 超容量时淘汰最旧条目
        if len(self._parsed_cache) >= self._PARSED_CACHE_MAX:
            try:
                oldest = min(self._parsed_cache.items(), key=lambda kv: kv[1][0])[0]
                self._parsed_cache.pop(oldest, None)
            except ValueError:
                pass
        self._parsed_cache[article_url] = (time.time(), dict(parsed), html)

    def get_cached_parsed(self, article_url: str) -> Optional[tuple[dict, str]]:
        """
        取出未过期的缓存 (parsed_copy, html)；过期或不存在返回 None。
        返回 parsed 的浅拷贝，调用方可安全修改。
        """
        if not article_url:
            return None
        entry = self._parsed_cache.get(article_url)
        if not entry:
            return None
        ts, parsed, html = entry
        if (time.time() - ts) >= self._PARSED_CACHE_TTL:
            self._parsed_cache.pop(article_url, None)
            return None
        return dict(parsed), html

    # ── 下载单篇文章 ─────────────────────────────────────────────

    async def download_article(
        self,
        conn_id: str,
        article_url: str,
        article_title: str = "",
        cookie: str = "",
        format: str = "md",
        download_dir: str = "",
        skip_if_exists: bool = True,
        localize_images: bool = True,
    ) -> dict:
        """
        下载单篇文章

        Args:
            skip_if_exists: 若同 article_url 已有成功下载记录，则跳过（去重）。
            localize_images: 是否将远程图片下载到本地并改写引用（默认开启）。
            format: md / html / epub / pdf。

        Returns:
            { success, file_path, format, title, author, parsed, record_id?, skipped?, error? }
        """
        client = self._get_client(conn_id, cookie=cookie)

        # 0. 去重：同 URL 已成功下载过则跳过
        if skip_if_exists and article_url:
            existing = await self._find_existing_download(article_url, format)
            if existing and existing.get("status") == "done" and existing.get("file_path"):
                if os.path.exists(existing["file_path"]):
                    logger.info(f"[WechatMPService] 跳过已下载文章: {article_url}")
                    # 读取已下载文件内容，供前端生成 EPUB 使用
                    content_html = ""
                    file_path = existing["file_path"]
                    existing_format = existing.get("format") or Path(file_path).suffix.lower().lstrip(".") or format
                    read_success = True
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        # 如果是 markdown 文件，转换为 HTML
                        if file_path.endswith(".md"):
                            from markdown import markdown
                            content_html = markdown(content)
                        elif file_path.endswith(".html"):
                            content_html = content
                    except Exception as e:
                        logger.warning(f"[WechatMPService] 读取已下载文件失败: {e}")
                        read_success = False
                    # 构造 parsed 数据
                    parsed = {
                        "title": existing.get("title", article_title),
                        "author": existing.get("author", ""),
                        "publish_time": existing.get("publish_time", ""),
                        "content_html": content_html,
                        "article_url": article_url,
                    }
                    return {
                        "success": read_success,
                        "skipped": True,
                        "file_path": file_path,
                        "format": existing_format,
                        "title": existing.get("title") or article_title,
                        "author": existing.get("author", ""),
                        "record_id": existing["id"],
                        "parsed": parsed,
                        "error": None if read_success else f"读取已下载文件失败",
                    }

        try:
            # 1. 获取并解析文章 HTML（优先复用 parse 端点的缓存，避免二次抓取）
            cached = self.get_cached_parsed(article_url)
            if cached:
                parsed, html = cached
                logger.info(f"[WechatMPService] 命中 parsed 缓存，跳过抓取: {article_url}")
            else:
                content_result = await client.get_article_content(article_url)
                if "error" in content_result:
                    # 落库失败记录
                    await self._record_download(
                        conn_id=conn_id, article_url=article_url, article_title=article_title,
                        author="", file_path="", file_size=0, fmt=format, status="failed",
                        error_message=str(content_result["error"]),
                    )
                    return {"success": False, "error": content_result["error"]}

                html = content_result.get("html", "")
                if not html:
                    await self._record_download(
                        conn_id=conn_id, article_url=article_url, article_title=article_title,
                        author="", file_path="", file_size=0, fmt=format, status="failed",
                        error_message="获取文章内容为空",
                    )
                    return {"success": False, "error": "获取文章内容为空"}

                # 2. 解析文章并缓存（供同进程后续 download/batch 复用）
                parsed = self._parser.parse(html, article_url)
                self.cache_parsed(article_url, parsed, html)

                # 检查解析是否成功
                if parsed.get("error") or not parsed.get("content_html"):
                    logger.warning(f"[WechatMPService] 文章解析失败或内容为空: {article_url}")
                    await self._record_download(
                        conn_id=conn_id, article_url=article_url, article_title=article_title,
                        author="", file_path="", file_size=0, fmt=format, status="failed",
                        error_message=parsed.get("error") or "解析失败，内容为空",
                    )
                    return {"success": False, "error": parsed.get("error") or "解析失败，内容为空", "parsed": parsed}

            title = article_title or parsed.get("title", "未命名文章")

            # 3. 确定保存目录：<download>/wechat_mp/<author>/<YYYY-MM>/
            if not download_dir:
                download_dir = ensure_download_path()
            author = parsed.get("author", "unknown")
            safe_author = "".join(c for c in author if c.isalnum() or c in "._- ").strip()[:50]
            yyyy_mm = self._publish_month(parsed.get("publish_time", ""))
            save_dir = Path(download_dir) / "wechat_mp" / (safe_author or "articles") / yyyy_mm
            save_dir.mkdir(parents=True, exist_ok=True)

            # 4. 图片本地化（默认开启）：下载远程图片到 images/，改写正文/全文中的 URL
            url_map: dict[str, str] = {}
            cover_local_path = ""
            if localize_images:
                try:
                    from .image_localizer import ImageLocalizer
                    localizer = ImageLocalizer(str(save_dir))
                    images_to_localize = list(parsed.get("images", []))
                    cover = parsed.get("cover", "")
                    if cover and cover not in images_to_localize:
                        images_to_localize.append(cover)
                    url_map = await localizer.localize(images_to_localize)
                    if cover and cover in url_map:
                        cover_local_path = str(save_dir / url_map[cover])
                except Exception as e:
                    logger.warning(f"[WechatMPService] 图片本地化失败（降级为远程链接）: {e}")
                    url_map = {}

            # 改写正文 HTML 与全文 HTML 中的图片 URL
            if url_map:
                parsed["content_html"] = self._rewrite_urls(parsed.get("content_html", ""), url_map)
                parsed["images"] = [url_map.get(u, u) for u in parsed.get("images", [])]
                html = self._rewrite_urls(html, url_map)

            # 5. 生成文件名（文件名去下载时间戳，同名自动追加序号防覆盖）
            safe_title = "".join(c for c in title if c.isalnum() or c in "._- ()（）")[:80]
            ext = {"md": "md", "html": "html", "epub": "epub", "pdf": "pdf"}.get(format, "md")
            file_path = self._unique_file_path(save_dir, safe_title or "未命名", ext)

            if format == "md":
                content = self._parser.to_markdown(parsed)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            elif format == "html":
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(html)
            elif format == "epub":
                from .epub_exporter import build_epub
                build_epub(
                    book_title=title,
                    articles=[{
                        "title": title,
                        "author": author,
                        "publish_time": parsed.get("publish_time", ""),
                        "content_html": parsed.get("content_html", ""),
                        "source_url": article_url,
                    }],
                    out_path=file_path,
                    cover_image_path=cover_local_path,
                    images_base_dir=str(save_dir),
                )
            elif format == "pdf":
                from .pdf_exporter import render_pdf
                await render_pdf(
                    html=html,
                    out_path=file_path,
                    title=title,
                    base_dir=str(save_dir),
                )
            else:
                # 默认 markdown
                content = self._parser.to_markdown(parsed)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            file_size = os.path.getsize(file_path)

            # 5. 落库（status=done）
            record_id = await self._record_download(
                conn_id=conn_id,
                article_url=article_url,
                article_title=title,
                author=author,
                file_path=file_path,
                file_size=file_size,
                fmt=format,
                status="done",
                cover_url=parsed.get("cover", ""),
                digest=(parsed.get("content_text") or "")[:200],
                publish_time=parsed.get("publish_time"),
                account_name=author,
            )

            return {
                "success": True,
                "file_path": file_path,
                "file_size": file_size,
                "format": format,
                "title": title,
                "author": author,
                "download_dir": str(save_dir),
                "parsed": parsed,
                "record_id": record_id,
            }

        except Exception as e:
            logger.error(f"[WechatMPService] 下载文章失败: {e}")
            # 落库失败记录
            await self._record_download(
                conn_id=conn_id, article_url=article_url, article_title=article_title,
                author="", file_path="", file_size=0, fmt=format, status="failed",
                error_message=str(e),
            )
            return {"success": False, "error": str(e)}

    # ── 批量下载 ──────────────────────────────────────────────────

    async def download_articles_batch(
        self,
        conn_id: str,
        articles: list[dict],
        cookie: str = "",
        format: str = "md",
        download_dir: str = "",
        skip_if_exists: bool = True,
        concurrency: int = 3,
    ) -> dict:
        """
        批量下载文章（并发 + WebSocket 实时进度推送）

        单篇去重 + 落库已在 download_article 内生效。
        并发安全：api_client 每次请求新建 httpx.AsyncClient、DB session 每次新建、
        parser 无状态、ImageLocalizer 每篇独立实例。

        Args:
            articles: [{ title, link, cover, digest }]
            skip_if_exists: 同 URL 已成功下载则跳过
            concurrency: 并发下载数（1~8，默认 3）

        Returns:
            {..., task_id} — task_id 可供前端 WebSocket 订阅实时进度
        """
        import asyncio
        from app.core.ws_manager import push_task_progress

        total = len(articles)
        task_id = str(uuid.uuid4())

        # 并发度钳制在 1~8
        max_concurrency = max(1, min(int(concurrency) if concurrency else 3, 8))
        sem = asyncio.Semaphore(max_concurrency)
        counter_lock = asyncio.Lock()
        results: list[dict | None] = [None] * total
        done_count = 0

        async def _push(progress: int, message: str, status: str) -> None:
            """推送 WebSocket 进度，失败不影响主流程"""
            try:
                await push_task_progress(
                    task_id=task_id,
                    progress=progress,
                    message=message,
                    task_type="wechat_mp_batch",
                    status=status,
                )
            except Exception as e:
                logger.debug(f"[WechatMPService] WS 进度推送失败（忽略）: {e}")

        async def _download_one(idx: int, article: dict) -> None:
            nonlocal done_count
            async with sem:
                result = await self.download_article(
                    conn_id=conn_id,
                    article_url=article.get("link", ""),
                    article_title=article.get("title", ""),
                    cookie=cookie,
                    format=format,
                    download_dir=download_dir,
                    skip_if_exists=skip_if_exists,
                )
                result["_article"] = article
                results[idx] = result

            # 单篇完成，更新计数并推送进度（计数加锁避免竞态）
            async with counter_lock:
                done_count += 1
                cur = done_count
            progress = int(cur / total * 100) if total else 100
            if result.get("skipped"):
                item_status = "skipped"
            elif result.get("success"):
                item_status = "done"
            else:
                item_status = "failed"
            title = article.get("title", "") or article.get("link", "")
            await _push(progress, f"[{cur}/{total}] {item_status}: {title}", "running")

        # 开始事件
        await _push(0, f"批量下载开始，共 {total} 篇（并发 {max_concurrency}）", "running")

        # 并发执行，gather 保持输入顺序
        if articles:
            await asyncio.gather(*[_download_one(i, a) for i, a in enumerate(articles)])

        # 统计
        success_count = sum(1 for r in results if r and r.get("success"))
        skipped_count = sum(1 for r in results if r and r.get("skipped"))
        fail_count = sum(1 for r in results if not (r and r.get("success")))

        # 收集成功下载的文件路径
        file_paths = [
            r.get("file_path") for r in results
            if r and r.get("success") and r.get("file_path")
        ]
        # 推导 download_dir：优先用传入值，否则从首个成功路径的 wechat_mp 父目录推导
        final_download_dir = str(download_dir or "")
        if not final_download_dir and file_paths:
            first_path = Path(file_paths[0])
            # 向上找 wechat_mp 目录：.../wechat_mp/作者/年月/文件 → .../wechat_mp
            for parent in first_path.parents:
                if parent.name == "wechat_mp":
                    final_download_dir = str(parent)
                    break
            else:
                # 兜底：取文件所在目录
                final_download_dir = str(first_path.parent)

        # 提取轻量级文章数据，供前端生成 EPUB 使用（避免传整个 results 导致响应过大）
        article_data: list[dict] = []
        for r in results:
            if not r:
                continue
            p = r.get("parsed", {}) or {}
            article = r.get("_article", {}) or {}
            item = {
                "success": r.get("success", False),
                "skipped": r.get("skipped", False),
                "file_path": r.get("file_path", ""),
                "format": r.get("format", format),
                "article_key": article.get("aid") or article.get("link") or "",
                "title": r.get("title", "") or p.get("title", ""),
                "author": r.get("author", "") or p.get("author", ""),
                "publish_time": p.get("publish_time", ""),
                "content_html": p.get("content_html", ""),
                "source_url": p.get("article_url", "") or p.get("source_url", ""),
            }
            article_data.append(item)
            # 调试日志
            logger.info(f"[WechatMPService] article_data item: success={item['success']}, has_content={len(item['content_html']) > 0}, title={item['title'][:30]}...")

        logger.info(f"[WechatMPService] 生成 article_data: 共 {len(article_data)} 条，成功且有内容: {sum(1 for item in article_data if item['success'] and item['content_html'])} 条")

        # 完成事件
        final_status = "done" if fail_count == 0 else "failed"
        await _push(
            100,
            f"完成: 成功 {success_count} 跳过 {skipped_count} 失败 {fail_count}",
            final_status,
        )

        return {
            "total": total,
            "downloaded": success_count,
            "skipped": skipped_count,
            "failed": fail_count,
            "success": fail_count == 0,
            "download_dir": final_download_dir,
            "file_paths": file_paths,
            "article_data": article_data,
            "results": [r for r in results if r is not None],
            "task_id": task_id,
        }

    # ── 图片 URL 改写 ────────────────────────────────────────────

    @staticmethod
    def _rewrite_urls(text: str, url_map: dict[str, str]) -> str:
        """将文本中的原图片 URL 替换为本地相对路径（HTML/Markdown 通用）。"""
        if not text or not url_map:
            return text

        import re

        for orig, rel in url_map.items():
            try:
                text = text.replace(orig, rel)
            except Exception:
                pass

            try:
                text = text.replace(orig.replace("&", "&amp;"), rel)
            except Exception:
                pass

            try:
                text = text.replace('data-src="' + orig + '"', 'src="' + rel + '"')
            except Exception:
                pass

            try:
                text = text.replace('data-src="' + orig.replace("&", "&amp;") + '"', 'src="' + rel + '"')
            except Exception:
                pass

            try:
                orig_no_query = orig.split("?")[0]
                pattern = r'data-src=["\']' + re.escape(orig_no_query) + r'[^\s"\']*["\']'
                text = re.sub(pattern, 'src="' + rel + '"', text)
            except Exception:
                pass

            try:
                orig_escaped = orig_no_query.replace("&", "&amp;")
                pattern = r'data-src=["\']' + re.escape(orig_escaped) + r'[^\s"\']*["\']'
                text = re.sub(pattern, 'src="' + rel + '"', text)
            except Exception:
                pass

        try:
            text = WechatMPService._promote_localized_image_sources(text, set(url_map.values()))
        except Exception:
            pass

        return text

    @staticmethod
    def _promote_localized_image_sources(text: str, local_refs: set[str]) -> str:
        """微信 HTML 常把真实图放在 data-src，src 是占位图；本地化后要把 src 同步成本地文件。"""
        if "<" not in text or not local_refs:
            return text

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "html.parser")
        changed = False
        for img in soup.find_all("img"):
            candidates = [
                str(img.get("data-src") or ""),
                str(img.get("data-original") or ""),
                str(img.get("data-backsrc") or ""),
            ]
            local = next((value for value in candidates if value in local_refs), "")
            if not local:
                continue
            img["src"] = local
            img["data-src"] = local
            if img.get("data-original"):
                img["data-original"] = local
            if img.get("data-backsrc"):
                img["data-backsrc"] = local
            changed = True

        return str(soup) if changed else text

    @staticmethod
    def _publish_month(publish_time: str) -> str:
        """
        从 publish_time（'YYYY-MM-DD HH:MM:SS'）提取 'YYYY-MM' 作为目录名。
        无效或缺失时回退到当前年月。
        """
        pt = (publish_time or "").strip()
        if len(pt) >= 7 and pt[4] == "-" and pt[:7].replace("-", "").isdigit():
            return pt[:7]
        return datetime.now().strftime("%Y-%m")

    @staticmethod
    def _unique_file_path(directory: Path, stem: str, ext: str) -> str:
        """
        生成不重名的文件路径：<stem>.<ext>，已存在则追加 _2、_3 ...。
        用于批量下载同名文章防覆盖。
        """
        p = directory / f"{stem}.{ext}"
        if not p.exists():
            return str(p)
        n = 2
        while n < 1000:
            p = directory / f"{stem}_{n}.{ext}"
            if not p.exists():
                return str(p)
            n += 1
        # 兜底
        return str(directory / f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")

    # ── 批量合并导出 EPUB ────────────────────────────────────────

    async def export_batch_to_epub(
        self,
        conn_id: str,
        articles: list[dict],
        book_title: str,
        download_dir: str = "",
        images_base_dir: str = "",
    ) -> dict:
        """
        将多篇已下载文章合并导出为单个 EPUB。

        Args:
            articles: [{ title, author, publish_time, content_html, source_url }]
                      content_html 应为已本地化图片的 HTML（图片引用 images/xxx）。
            images_base_dir: 图片所在根目录（含 images/ 子目录）；默认用保存目录。

        Returns:
            { success, file_path, file_size, format, record_id, error? }
        """
        from .epub_exporter import build_epub

        base_dir = Path(download_dir) if download_dir else ensure_download_path()
        save_dir = base_dir / "epub" if base_dir.name == "wechat_mp" else base_dir / "wechat_mp" / "epub"
        save_dir.mkdir(parents=True, exist_ok=True)

        safe_title = "".join(c for c in book_title if c.isalnum() or c in "._- ")[:80] or "epub"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = str(save_dir / f"{timestamp}_{safe_title}.epub")

        try:
            build_epub(
                book_title=book_title,
                articles=articles,
                out_path=file_path,
                images_base_dir=images_base_dir or str(save_dir),
            )
            file_size = os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"[WechatMPService] EPUB 导出失败: {e}")
            await self._record_download(
                conn_id=conn_id, article_url=f"epub:{book_title}", article_title=book_title,
                author=book_title, file_path="", file_size=0, fmt="epub", status="failed",
                error_message=str(e),
            )
            return {"success": False, "error": str(e)}

        record_id = await self._record_download(
            conn_id=conn_id, article_url=f"epub:{book_title}", article_title=book_title,
            author=book_title, file_path=file_path, file_size=file_size, fmt="epub",
            status="done",
        )
        return {
            "success": True,
            "file_path": file_path,
            "file_size": file_size,
            "format": "epub",
            "record_id": record_id,
        }

    # ── 验证登录 ──────────────────────────────────────────────────

    async def verify_login(self, conn_id: str, cookie: str = "", token: str = "") -> dict:
        """验证登录态"""
        client = self._get_client(conn_id, cookie=cookie, token=token)
        return await client.verify_login()

    # ── 清理 ──────────────────────────────────────────────────────

    def cleanup_session(self, session_id: str):
        """清理登录会话"""
        self._login_sessions.pop(session_id, None)

    def cleanup_expired_sessions(self, max_age_seconds: int = 600):
        """清理过期会话"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired = []
        for sid, session in self._login_sessions.items():
            age = (now - session["created_at"]).total_seconds()
            if age > max_age_seconds:
                expired.append(sid)
        for sid in expired:
            self._login_sessions.pop(sid, None)


# ── 全局单例 ──────────────────────────────────────────────────

_wechat_mp_service: Optional[WechatMPService] = None


def get_wechat_mp_service() -> WechatMPService:
    """获取 WechatMPService 全局单例"""
    global _wechat_mp_service
    if _wechat_mp_service is None:
        _wechat_mp_service = WechatMPService()
    return _wechat_mp_service
