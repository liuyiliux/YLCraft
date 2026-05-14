"""
YLCraft — 平台连接器服务（统一凭证架构）

管理各平台的凭证（Cookie / API Key / OAuth Token / Password）
唯一凭证存储：PlatformConnection 表
核心原则：一份 Cookie，多处使用
"""

from __future__ import annotations

import logging
import json
import time
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
    AcquisitionMethod,
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

    def get_active(self, platform: PlatformType | str) -> Optional[PlatformConnection]:
        """获取指定平台的活跃连接"""
        # 兼容传入字符串
        if isinstance(platform, str):
            try:
                platform = PlatformType(platform)
            except ValueError:
                return None

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
            acquisition_method=data.acquisition_method,
            account_id=data.account_id,
            account_name=data.account_name,
            account_avatar=data.account_avatar,
            account_url=data.account_url,
            cookie_content=data.cookie_content,
            domains=data.domains,
            test_url=data.test_url,
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
        # 凭证获取方式 / 账号信息 / Cookie 字段更新
        if data.acquisition_method is not None:
            conn.acquisition_method = data.acquisition_method
        if data.account_id is not None:
            conn.account_id = data.account_id
        if data.account_name is not None:
            conn.account_name = data.account_name
        if data.account_avatar is not None:
            conn.account_avatar = data.account_avatar
        if data.account_url is not None:
            conn.account_url = data.account_url
        if data.cookie_content is not None:
            conn.cookie_content = data.cookie_content
        if data.domains is not None:
            conn.domains = data.domains
        if data.test_url is not None:
            conn.test_url = data.test_url

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

    def get_cookie_content(self, conn_id: str) -> Optional[str]:
        """获取 Netscape 格式 Cookie 内容"""
        conn = self.get(conn_id)
        if not conn:
            return None
        # 优先读 cookie_content（Netscape 格式），否则从 credentials 转换
        if conn.cookie_content:
            return conn.cookie_content
        return self._credentials_to_netscape(conn)

    def save_cookie_content(self, conn_id: str, cookie_content: str) -> bool:
        """保存 Netscape 格式 Cookie"""
        conn = self.get(conn_id)
        if not conn:
            return False
        conn.cookie_content = cookie_content
        # 同时更新 credentials 的 raw 字段
        creds = conn.get_credentials()
        creds["raw"] = self._netscape_to_raw(cookie_content)
        creds["source"] = "manual"
        conn.set_credentials(creds)
        conn.update_timestamp()
        self.session.add(conn)
        self.session.commit()

        # 同步写入 Cookie 文件，确保 CookieManager 立即可用
        try:
            platform = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
            self._sync_cookie_file(platform, cookie_content)
        except Exception as e:
            logger.warning(f"[PlatformConnectionService] Cookie file sync failed (non-critical): {e}")

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
                result = self._test_cookie(platform, creds, conn)
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

    def _test_cookie(self, platform: str, creds: dict, conn: PlatformConnection = None) -> dict:
        """测试 Cookie 有效性"""
        # 优先使用 cookie_content (Netscape 格式)
        cookie_content = ""
        if conn and conn.cookie_content:
            cookie_content = conn.cookie_content
        else:
            cookie_content = creds.get("content", "") or creds.get("raw", "")

        if not cookie_content:
            return {"success": False, "message": "Cookie 内容为空"}

        # 使用已有的 Cookie 管理器测试
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

    def mark_used_with_result(self, conn_id: str, success: bool, error: str = ""):
        """标记连接使用结果"""
        conn = self.get(conn_id)
        if conn:
            if success:
                conn.update_success()
            else:
                conn.update_failure(error)
            self.session.add(conn)
            self.session.commit()

    @staticmethod
    def _credentials_to_netscape(conn: PlatformConnection) -> str:
        """从 credentials JSON 转换为 Netscape 格式"""
        creds = conn.get_credentials()
        cookies_array = creds.get("cookies_array", [])
        if not cookies_array:
            raw = creds.get("raw", "")
            if raw:
                # 尝试从 raw 字符串转换
                return _raw_to_netscape(raw, conn.domains or "")
            return ""

        lines = ["# Netscape HTTP Cookie File", ""]
        for c in cookies_array:
            name = c.get("name", "")
            value = c.get("value", "")
            domain = c.get("domain", "")
            path = c.get("path", "/")
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            expires = c.get("expires", -1)
            if expires == -1:
                expires = int(time.time()) + 86400 * 365
            else:
                expires = int(expires)
            is_dot = "TRUE" if domain.startswith(".") else "FALSE"
            lines.append(f"{domain}\t{is_dot}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
        return "\n".join(lines)

    @staticmethod
    def _sync_cookie_file(platform: str, cookie_content: str):
        """同步写入 Cookie 文件（确保 CookieManager 立即可用）"""
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
        cookie_dir = backend_dir / "data" / "cookies"
        cookie_dir.mkdir(parents=True, exist_ok=True)
        cookie_path = cookie_dir / f"{platform}.txt"

        # 使用 CookieManager 的清洗逻辑
        from app.services.video.parser import get_cookie_manager
        mgr = get_cookie_manager()
        clean_content = mgr._clean_netscape_content(cookie_content)
        cookie_path.write_text(clean_content, encoding="utf-8")
        cookie_path.chmod(0o600)
        logger.info(f"[PlatformConnectionService] Cookie file synced: {cookie_path.name}")

    @staticmethod
    def _netscape_to_raw(cookie_content: str) -> str:
        """从 Netscape 格式提取 raw 字符串"""
        parts = []
        for line in cookie_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) >= 7:
                parts.append(f"{fields[5]}={fields[6]}")
        return "; ".join(parts)


def _raw_to_netscape(raw: str, domains: str) -> str:
    """将 raw Cookie 字符串转为 Netscape 格式"""
    default_domain = ".example.com"
    if domains:
        d = domains.split(",")[0].strip()
        if d:
            default_domain = d if d.startswith(".") else "." + d

    lines = ["# Netscape HTTP Cookie File", ""]
    default_expires = str(int(time.time()) + 86400 * 365)
    is_dot = "TRUE" if default_domain.startswith(".") else "FALSE"

    import re
    pair_pattern = re.compile(r'([^=;]+?)\s*=\s*("[^"]*"|[^;]*)')
    for m in pair_pattern.finditer(raw):
        name = m.group(1).strip()
        value = m.group(2).strip()
        if not name:
            continue
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        lines.append(f"{default_domain}\t{is_dot}\t/\tFALSE\t{default_expires}\t{name}\t{value}")

    return "\n".join(lines)
