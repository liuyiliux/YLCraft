"""
微信公众号服务 — 业务编排层

整合 API 客户端、二维码适配器、解析器，提供高层业务操作。
扫码登录统一走 cookies.platforms 的 QrcodeAdapter 体系。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
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

    def __init__(self):
        self._clients: dict[str, WechatMPAPIClient] = {}
        self._parser = WechatMPParser()
        # 登录会话 {session_id: {status, session_key, conn_id, created_at}}
        self._login_sessions: dict[str, dict] = {}

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

    async def _find_existing_download(self, article_url: str) -> Optional[dict]:
        """
        按 article_url 查询已存在的下载记录（用于去重）。
        返回 dict（{id, status, file_path}）或 None。
        """
        from sqlalchemy import select
        from app.db.database import get_async_session
        from app.db.models.wechat_mp import WechatMPDownload

        try:
            session_gen = get_async_session()
            session = await session_gen.__anext__()
            try:
                stmt = select(WechatMPDownload).where(
                    WechatMPDownload.article_url == article_url
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row:
                    return {
                        "id": row.id,
                        "status": row.status,
                        "file_path": row.file_path,
                    }
                return None
            finally:
                await session_gen.aclose()
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
        落库一条下载记录（upsert：按 article_url 去重）。
        返回记录 id；失败时返回 None（不影响下载主流程）。
        """
        from sqlalchemy import select
        from app.db.database import get_async_session
        from app.db.models.wechat_mp import WechatMPDownload

        try:
            session_gen = get_async_session()
            session = await session_gen.__anext__()
            try:
                stmt = select(WechatMPDownload).where(
                    WechatMPDownload.article_url == article_url
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
                    # 已存在则更新（同 URL 重新下载：刷新状态/路径/时间）
                    existing.status = status
                    existing.format = fmt
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
            finally:
                await session_gen.aclose()
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
            format: md / html / epub。

        Returns:
            { success, file_path, format, title, author, parsed, record_id?, skipped?, error? }
        """
        client = self._get_client(conn_id, cookie=cookie)

        # 0. 去重：同 URL 已成功下载过则跳过
        if skip_if_exists and article_url:
            existing = await self._find_existing_download(article_url)
            if existing and existing.get("status") == "done" and existing.get("file_path"):
                if os.path.exists(existing["file_path"]):
                    logger.info(f"[WechatMPService] 跳过已下载文章: {article_url}")
                    return {
                        "success": True,
                        "skipped": True,
                        "file_path": existing["file_path"],
                        "format": format,
                        "title": article_title,
                        "record_id": existing["id"],
                    }

        try:
            # 1. 获取文章 HTML
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

            # 2. 解析文章
            parsed = self._parser.parse(html, article_url)
            title = article_title or parsed.get("title", "未命名文章")

            # 3. 确定保存目录
            if not download_dir:
                download_dir = ensure_download_path()
            author = parsed.get("author", "unknown")
            safe_author = "".join(c for c in author if c.isalnum() or c in "._- ").strip()[:50]
            save_dir = Path(download_dir) / "wechat_mp" / (safe_author or "articles")
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

            # 5. 生成文件名
            safe_title = "".join(c for c in title if c.isalnum() or c in "._- ()（）")[:80]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if format == "md":
                file_path = str(save_dir / f"{timestamp}_{safe_title}.md")
                content = self._parser.to_markdown(parsed)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            elif format == "html":
                file_path = str(save_dir / f"{timestamp}_{safe_title}.html")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(html)
            elif format == "epub":
                from .epub_exporter import build_epub
                file_path = str(save_dir / f"{timestamp}_{safe_title}.epub")
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
            else:
                # 默认 markdown
                file_path = str(save_dir / f"{timestamp}_{safe_title}.md")
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
                cover_url=parsed.get("cover_url", ""),
                digest=parsed.get("digest", ""),
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
    ) -> dict:
        """
        批量下载文章（单篇去重 + 落库已在 download_article 内生效）

        Args:
            articles: [{ title, link, cover, digest }]
            skip_if_exists: 同 URL 已成功下载则跳过
        """
        results = []
        success_count = 0
        fail_count = 0
        skipped_count = 0

        for article in articles:
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
            results.append(result)
            if result.get("success"):
                if result.get("skipped"):
                    skipped_count += 1
                else:
                    success_count += 1
            else:
                fail_count += 1

        # 收集成功下载的文件路径
        file_paths = [r.get("file_path") for r in results if r.get("success") and r.get("file_path")]
        # 确保 download_dir 始终是字符串类型
        result_dir = results[0].get("download_dir") if results else ""
        final_download_dir = str(download_dir or result_dir or "")

        return {
            "total": len(articles),
            "downloaded": success_count,
            "skipped": skipped_count,
            "failed": fail_count,
            "success": fail_count == 0,
            "download_dir": final_download_dir,
            "file_paths": file_paths,
            "results": results,
        }

    # ── 图片 URL 改写 ────────────────────────────────────────────

    @staticmethod
    def _rewrite_urls(text: str, url_map: dict[str, str]) -> str:
        """将文本中的原图片 URL 替换为本地相对路径（HTML/Markdown 通用）。"""
        if not text or not url_map:
            return text
        for orig, rel in url_map.items():
            text = text.replace(orig, rel)
        return text

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

        if not download_dir:
            download_dir = str(ensure_download_path())
        save_dir = Path(download_dir) / "wechat_mp" / "epub"
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
