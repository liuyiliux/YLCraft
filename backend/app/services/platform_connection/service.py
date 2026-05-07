"""
YLCraft — 平台连接器服务

管理各平台的凭证（Cookie / API Key / OAuth Token / Password）
支持状态的检测、自动获取凭证等功能。
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.models.platform_connection import (
    PlatformConnection,
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionResponse,
    PlatformType,
    AuthType,
    ConnectionStatus,
)
from app.services.video.parser import get_cookie_manager

logger = logging.getLogger("ylcraft.platform_connection")


class PlatformConnectionService:
    """平台连接器服务"""

    def __init__(self, session: Session):
        self.session = session

    def list_all(self) -> list[PlatformConnection]:
        """列出所有平台连接"""
        stmt = select(PlatformConnection).order_by(PlatformConnection.created_at.desc())
        return self.session.exec(stmt).all()

    def list_by_platform(self, platform: PlatformType) -> list[PlatformConnection]:
        """列出指定平台的所有连接"""
        stmt = (
            select(PlatformConnection)
            .where(PlatformConnection.platform == platform)
            .order_by(PlatformConnection.created_at.desc())
        )
        return self.session.exec(stmt).all()

    def get(self, conn_id: str) -> Optional[PlatformConnection]:
        """获取单个连接"""
        return self.session.get(PlatformConnection, conn_id)

    def get_active(self, platform: PlatformType) -> Optional[PlatformConnection]:
        """获取指定平台的活跃连接"""
        stmt = (
            select(PlatformConnection)
            .where(
                PlatformConnection.platform == platform,
                PlatformConnection.status == ConnectionStatus.ACTIVE,
            )
            .order_by(PlatformConnection.last_used.desc().nulls_last())
            .limit(1)
        )
        return self.session.exec(stmt).first()

    def create(self, data: PlatformConnectionCreate) -> PlatformConnection:
        """创建新连接"""
        import uuid

        conn = PlatformConnection(
            id=str(uuid.uuid4()),
            platform=data.platform,
            name=data.name,
            auth_type=data.auth_type,
            description=data.description,
            status=ConnectionStatus.UNKNOWN,
        )
        conn.set_credentials(data.credentials)

        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        logger.info(f"[PlatformConnection] Created: {conn.id} for {conn.platform}")
        return conn

    def update(
        self, conn_id: str, data: PlatformConnectionUpdate
    ) -> Optional[PlatformConnection]:
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
        if data.description is not None:
            conn.description = data.description
        if data.status is not None:
            conn.status = data.status

        conn.update_timestamp()
        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        logger.info(f"[PlatformConnection] Updated: {conn.id}")
        return conn

    def delete(self, conn_id: str) -> bool:
        """删除连接"""
        conn = self.get(conn_id)
        if not conn:
            return False
        self.session.delete(conn)
        self.session.commit()
        logger.info(f"[PlatformConnection] Deleted: {conn_id}")
        return True

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

        # 根据平台测试
        try:
            if conn.auth_type == AuthType.COOKIE:
                result = self._test_cookie(platform, creds)
            elif conn.auth_type == AuthType.API_KEY:
                result = self._test_api_key(platform, creds)
            else:
                result = {"success": False, "message": f"不支持的认证类型: {conn.auth_type}"}

            # 更新状态
            conn.status = ConnectionStatus.ACTIVE if result["success"] else ConnectionStatus.FAILED
            conn.last_tested = datetime.now(timezone.utc)
            if not result["success"]:
                conn.error_message = result.get("message", "未知错误")
            else:
                conn.error_message = None
            self.session.add(conn)
            self.session.commit()

            return result

        except Exception as e:
            conn.status = ConnectionStatus.FAILED
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

        # 使用已有的 Cookie 管理器测试
        try:
            manager = get_cookie_manager()
            # 尝试解析 Cookie
            from http.cookiejar import MozillaCookieJar
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(cookie_content)
                tmp_path = f.name

            try:
                jar = MozillaCookieJar(tmp_path)
                jar.load()
                # 检查是否有有效 Cookie
                if len(jar) > 0:
                    return {"success": True, "message": f"Cookie 有效，共 {len(jar)} 条"}
                return {"success": False, "message": "Cookie 文件为空或无效"}
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            return {"success": False, "message": f"Cookie 格式错误: {str(e)}"}

    def _test_api_key(self, platform: str, creds: dict) -> dict:
        """测试 API Key 有效性"""
        api_key = creds.get("api_key", "")
        if not api_key:
            return {"success": False, "message": "API Key 为空"}

        # 简单检查格式
        if platform == PlatformType.OPENAI:
            if not api_key.startswith("sk-"):
                return {"success": False, "message": "OpenAI API Key 格式不正确"}
        elif platform == PlatformType.MINIMAX:
            if not api_key.startswith(" eyJ"):  # MiniMax key starts with eyJ
                pass  # 不强制检查

        return {"success": True, "message": "API Key 格式正确（未进行实际连接测试）"}

    def mark_used(self, conn_id: str):
        """标记连接已使用"""
        conn = self.get(conn_id)
        if conn:
            conn.last_used = datetime.now(timezone.utc)
            self.session.add(conn)
            self.session.commit()
