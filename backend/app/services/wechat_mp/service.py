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
    ) -> dict:
        """
        下载单篇文章

        Returns:
            { success, file_path, format, title, error }
        """
        client = self._get_client(conn_id, cookie=cookie)

        try:
            # 1. 获取文章 HTML
            content_result = await client.get_article_content(article_url)
            if "error" in content_result:
                return {"success": False, "error": content_result["error"]}

            html = content_result.get("html", "")
            if not html:
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

            # 4. 生成文件名
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
            else:
                # 默认 markdown
                file_path = str(save_dir / f"{timestamp}_{safe_title}.md")
                content = self._parser.to_markdown(parsed)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            file_size = os.path.getsize(file_path)

            return {
                "success": True,
                "file_path": file_path,
                "file_size": file_size,
                "format": format,
                "title": title,
                "author": author,
                "parsed": parsed,
            }

        except Exception as e:
            logger.error(f"[WechatMPService] 下载文章失败: {e}")
            return {"success": False, "error": str(e)}

    # ── 批量下载 ──────────────────────────────────────────────────

    async def download_articles_batch(
        self,
        conn_id: str,
        articles: list[dict],
        cookie: str = "",
        format: str = "md",
        download_dir: str = "",
    ) -> dict:
        """
        批量下载文章

        Args:
            articles: [{ title, link, cover, digest }]
        """
        results = []
        success_count = 0
        fail_count = 0

        for article in articles:
            result = await self.download_article(
                conn_id=conn_id,
                article_url=article.get("link", ""),
                article_title=article.get("title", ""),
                cookie=cookie,
                format=format,
                download_dir=download_dir,
            )
            result["_article"] = article
            results.append(result)
            if result.get("success"):
                success_count += 1
            else:
                fail_count += 1

        return {
            "total": len(articles),
            "success": success_count,
            "fail": fail_count,
            "results": results,
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
