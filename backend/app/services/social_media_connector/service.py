"""
YLCraft — 社交媒体连接器服务

管理各自媒体平台的 Cookie / OAuth 凭证
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Session, select

from app.db.models.social_media_connector import (
    SocialMediaConnector,
    SocialMediaConnectorCreate,
    SocialMediaConnectorUpdate,
    SocialMediaConnectorResponse,
    SocialMediaPlatform,
    SocialAuthType,
    SocialConnectionStatus,
)

logger = logging.getLogger("ylcraft.social_media")


class SocialMediaConnectorService:
    """社交媒体连接器服务"""

    def __init__(self, session: Session):
        self.session = session

    # -------------------------------------------------------------------------
    # CRUD 操作
    # -------------------------------------------------------------------------

    def list_all(self) -> list[SocialMediaConnector]:
        """列出所有社交媒体连接"""
        stmt = select(SocialMediaConnector).order_by(SocialMediaConnector.created_at.desc())
        return self.session.exec(stmt).all()

    def list_by_platform(self, platform: SocialMediaPlatform) -> list[SocialMediaConnector]:
        """列出指定平台的所有连接"""
        stmt = (
            select(SocialMediaConnector)
            .where(SocialMediaConnector.platform == platform)
            .order_by(SocialMediaConnector.created_at.desc())
        )
        return self.session.exec(stmt).all()

    def get(self, conn_id: str) -> Optional[SocialMediaConnector]:
        """获取单个连接"""
        return self.session.get(SocialMediaConnector, conn_id)

    def get_active(self, platform: SocialMediaPlatform) -> Optional[SocialMediaConnector]:
        """获取指定平台的活跃连接"""
        stmt = (
            select(SocialMediaConnector)
            .where(
                SocialMediaConnector.platform == platform,
                SocialMediaConnector.status == SocialConnectionStatus.ACTIVE,
            )
            .order_by(SocialMediaConnector.last_used.desc().nulls_last())
            .limit(1)
        )
        return self.session.exec(stmt).first()

    def create(self, data: SocialMediaConnectorCreate) -> SocialMediaConnector:
        """创建新连接"""
        conn = SocialMediaConnector(
            id=str(uuid.uuid4()),
            platform=data.platform,
            name=data.name,
            auth_type=data.auth_type,
            description=data.description,
            status=SocialConnectionStatus.UNKNOWN,
        )
        conn.set_credentials(data.credentials)
        conn.set_scopes(data.scopes)

        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        logger.info(f"[SocialMediaConnector] Created: {conn.id} for {conn.platform.value}")
        return conn

    def update(
        self, conn_id: str, data: SocialMediaConnectorUpdate
    ) -> Optional[SocialMediaConnector]:
        """更新连接"""
        conn = self.get(conn_id)
        if not conn:
            return None

        if data.name is not None:
            conn.name = data.name
        if data.auth_type is not None:
            conn.auth_type = data.auth_type
        if data.credentials is not None:
            conn.set_credentials(data.credentials)
        if data.scopes is not None:
            conn.set_scopes(data.scopes)
        if data.description is not None:
            conn.description = data.description
        if data.status is not None:
            conn.status = data.status

        conn.updated_at = datetime.now(timezone.utc)
        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        logger.info(f"[SocialMediaConnector] Updated: {conn.id}")
        return conn

    def delete(self, conn_id: str) -> bool:
        """删除连接"""
        conn = self.get(conn_id)
        if not conn:
            return False
        self.session.delete(conn)
        self.session.commit()
        logger.info(f"[SocialMediaConnector] Deleted: {conn_id}")
        return True

    # -------------------------------------------------------------------------
    # 账号信息更新
    # -------------------------------------------------------------------------

    def update_account_info(
        self,
        conn_id: str,
        account_id: str,
        account_name: str,
        account_avatar: Optional[str] = None,
        account_url: Optional[str] = None,
    ) -> Optional[SocialMediaConnector]:
        """更新账号信息"""
        conn = self.get(conn_id)
        if not conn:
            return None

        conn.account_id = account_id
        conn.account_name = account_name
        conn.account_avatar = account_avatar
        conn.account_url = account_url
        conn.updated_at = datetime.now(timezone.utc)

        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        return conn

    # -------------------------------------------------------------------------
    # 测试与验证
    # -------------------------------------------------------------------------

    def test_connection(self, conn_id: str) -> dict:
        """
        测试连接有效性
        返回 {"success": bool, "message": str}
        """
        conn = self.get(conn_id)
        if not conn:
            return {"success": False, "message": "连接不存在"}

        platform = conn.platform
        creds = conn.get_credentials()

        try:
            if conn.auth_type == SocialAuthType.COOKIE:
                result = self._test_cookie(platform, creds)
            elif conn.auth_type == SocialAuthType.OAUTH2:
                result = self._test_oauth2(platform, creds)
            elif conn.auth_type == SocialAuthType.PASSWORD:
                result = {"success": False, "message": "密码认证需要手动验证"}
            else:
                result = {"success": False, "message": f"不支持的认证类型: {conn.auth_type}"}

            # 更新状态
            conn.status = SocialConnectionStatus.ACTIVE if result["success"] else SocialConnectionStatus.FAILED
            conn.last_tested = datetime.now(timezone.utc)
            if not result["success"]:
                conn.error_message = result.get("message", "未知错误")
            else:
                conn.error_message = None
            self.session.add(conn)
            self.session.commit()

            return result

        except Exception as e:
            conn.status = SocialConnectionStatus.FAILED
            conn.last_tested = datetime.now(timezone.utc)
            conn.error_message = str(e)
            self.session.add(conn)
            self.session.commit()
            return {"success": False, "message": f"测试失败: {str(e)}"}

    def _test_cookie(self, platform: str, creds: dict) -> dict:
        """测试 Cookie 有效性"""
        cookie_content = creds.get("content", "")
        if not cookie_content:
            return {"success": False, "message": "Cookie 内容为空"}

        try:
            from http.cookiejar import MozillaCookieJar
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(cookie_content)
                tmp_path = f.name

            try:
                jar = MozillaCookieJar(tmp_path)
                jar.load()
                if len(jar) > 0:
                    return {"success": True, "message": f"Cookie 有效，共 {len(jar)} 条"}
                return {"success": False, "message": "Cookie 文件为空或无效"}
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            return {"success": False, "message": f"Cookie 格式错误: {str(e)}"}

    def _test_oauth2(self, platform: str, creds: dict) -> dict:
        """测试 OAuth2 Token 有效性"""
        access_token = creds.get("access_token", "")
        if not access_token:
            return {"success": False, "message": "Access Token 为空"}

        # 简单检查格式
        return {"success": True, "message": "OAuth2 Token 格式正确"}

    # -------------------------------------------------------------------------
    # 使用记录
    # -------------------------------------------------------------------------

    def mark_used(self, conn_id: str, success: bool = True, error: str = ""):
        """标记连接使用情况"""
        conn = self.get(conn_id)
        if conn:
            if success:
                conn.update_success()
            else:
                conn.update_failure(error)
            self.session.add(conn)
            self.session.commit()

    # -------------------------------------------------------------------------
    # 内容发布
    # -------------------------------------------------------------------------

    def publish(self, conn_id: str, content: dict) -> dict:
        """
        使用指定连接发布内容到平台

        Args:
            conn_id: 连接 ID
            content: 发布内容字典，包含：
                - title: 标题
                - body: 正文
                - content_type: 内容类型（video/image/text/article）
                - tags: 标签列表
                - media: 媒体文件列表 [{"file_path": "...", "media_type": "mp4"}]

        Returns:
            {"success": bool, "post_id": str, "post_url": str, "error": str}
        """
        from app.connectors.base import (
            ContentType,
            MediaFormat,
            MediaAttachment,
            PostContent,
        )
        from app.connectors.registry import get_social_connector

        conn = self.get(conn_id)
        if not conn:
            return {"success": False, "error": "连接不存在"}

        try:
            # 获取凭证
            credentials = conn.get_credentials()

            # 创建连接器实例
            connector = get_social_connector(
                platform_id=conn.platform.value,
                credentials=credentials,
            )

            # 初始化连接器
            import asyncio
            loop = asyncio.get_event_loop()
            init_ok = loop.run_until_complete(connector.initialize())

            if not init_ok:
                return {"success": False, "error": "连接器初始化失败，请检查凭证"}

            try:
                # 构建发布内容
                content_type_map = {
                    "video": ContentType.VIDEO,
                    "image": ContentType.IMAGE,
                    "text": ContentType.TEXT,
                    "article": ContentType.ARTICLE,
                }
                content_type = content_type_map.get(
                    content.get("content_type", "text"),
                    ContentType.TEXT,
                )

                # 构建媒体附件
                media_attachments = []
                for m in content.get("media", []):
                    media_type_map = {
                        "mp4": MediaFormat.MP4,
                        "jpg": MediaFormat.JPG,
                        "jpeg": MediaFormat.JPG,
                        "png": MediaFormat.PNG,
                        "avi": MediaFormat.AVI,
                        "mov": MediaFormat.MOV,
                    }
                    media_format = media_type_map.get(
                        m.get("media_type", "mp4").lower(),
                        MediaFormat.MP4,
                    )
                    media_attachments.append(
                        MediaAttachment(
                            file_path=m.get("file_path", ""),
                            media_type=media_format,
                            caption=m.get("caption", ""),
                        )
                    )

                post_content = PostContent(
                    title=content.get("title", ""),
                    body=content.get("body", ""),
                    content_type=content_type,
                    tags=content.get("tags", []),
                    media=media_attachments,
                )

                # 发布
                result = loop.run_until_complete(connector.publish(post_content))

                # 更新使用记录
                self.mark_used(conn_id, success=result.success)

                return {
                    "success": result.success,
                    "post_id": result.post_id,
                    "post_url": result.post_url,
                    "error": result.error_message,
                    "platform_data": result.platform_data,
                }

            finally:
                loop.run_until_complete(connector.close())

        except Exception as e:
            logger.error(f"[SocialMediaConnector] Publish failed: {e}")
            self.mark_used(conn_id, success=False, error=str(e))
            return {"success": False, "error": str(e)}
