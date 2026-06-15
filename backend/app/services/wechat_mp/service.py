"""
微信公众号服务 — 业务编排层

整合 API 客户端、解析器、素材库，提供高层业务操作。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .api_client import WechatMPAPIClient
from .parser import WechatMPParser
from app.core.config import ensure_download_path

logger = logging.getLogger("ylcraft.wechat_mp.service")


class WechatMPService:
    """
    微信公众号业务服务

    功能：
        - 扫码登录流程管理
        - 搜索公众号
        - 拉取文章列表
        - 下载单篇文章
        - 批量下载文章
        - 导入素材库
    """

    def __init__(self):
        self._clients: dict[str, WechatMPAPIClient] = {}
        self._parser = WechatMPParser()
        # 登录会话 {session_id: {status, uuid, conn_id, created_at}}
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

    # ── 登录流程 ────────────────────────────────────────────────

    async def start_qrcode_login(self, conn_id: str) -> dict:
        """
        启动扫码登录

        Returns:
            { session_id, qr_url }
        """
        client = self._get_client(conn_id)
        result = await client.get_login_qrcode()

        session_id = str(uuid.uuid4())
        self._login_sessions[session_id] = {
            "status": "waiting",
            "uuid": result.get("uuid", ""),
            "conn_id": conn_id,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }

        return {
            "session_id": session_id,
            "qr_url": result.get("qr_url", ""),
            "qr_uuid": result.get("uuid", ""),
        }

    async def check_login_status(self, session_id: str) -> dict:
        """
        轮询扫码登录状态

        Returns:
            { status, cookie, token, nickname }
        """
        session = self._login_sessions.get(session_id)
        if not session:
            return {"status": "error", "message": "会话不存在或已过期"}

        client = self._get_client(session["conn_id"])
        result = await client.check_login_status(session["qr_uuid"])

        session["status"] = result.get("status", "waiting")

        if result.get("status") == "confirmed":
            # 登录成功，获取用户信息
            verify = await client.verify_login()
            result["nickname"] = verify.get("nickname", "")
            result["head_img"] = verify.get("head_img", "")

        return result

    # ── 搜索公众号 ──────────────────────────────────────────────

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
            # 用公众号名创建子目录
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
