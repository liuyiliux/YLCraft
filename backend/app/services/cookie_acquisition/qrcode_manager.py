"""
YLCraft — QrCode Cookie 获取管理器

负责生成二维码、轮询扫码状态、提取 Cookie、保存到 PlatformConnection
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

from app.services.cookie_acquisition.base import (
    AcquisitionSession,
    AcquisitionStatus,
    get_platform_domains,
    get_platform_test_url,
)
from app.services.cookie_acquisition.platforms import get_qrcode_adapter

logger = logging.getLogger("ylcraft.cookie_acquisition.qrcode")

# 默认二维码过期时间（秒）
DEFAULT_QR_TIMEOUT = 120
# 轮询间隔（秒）
DEFAULT_POLL_INTERVAL = 2


class QrcodeAcquisitionManager:
    """二维码扫码 Cookie 获取管理器"""

    def __init__(self):
        self._sessions: dict[str, AcquisitionSession] = {}

    def get_session(self, session_id: str) -> Optional[AcquisitionSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[AcquisitionSession]:
        """列出所有活跃会话"""
        return [s for s in self._sessions.values() if not s.is_terminal]

    async def generate_qrcode(
        self,
        platform: str,
        connector_name: str = "",
    ) -> str:
        """
        生成登录二维码

        Returns:
            session_id
        """
        session_id = str(uuid.uuid4())
        session = AcquisitionSession(
            session_id=session_id,
            platform=platform,
            method="qrcode",
            connector_name=connector_name,
        )
        self._sessions[session_id] = session

        try:
            # 获取平台二维码适配器
            adapter = get_qrcode_adapter(platform)
            if not adapter:
                raise RuntimeError(f"平台 {platform} 暂不支持二维码登录")

            qr_result = await adapter.generate_qrcode()

            session.qr_image_base64 = qr_result.get("qr_image_base64", "")
            session.qr_session_key = qr_result.get("session_key", "")
            session.status = AcquisitionStatus.QR_GENERATED
            session.updated_at = __import__('datetime').datetime.now()

            # 启动后台轮询任务
            asyncio.create_task(
                self._poll_qrcode_status(session_id, adapter)
            )

        except Exception as e:
            session.status = AcquisitionStatus.FAILED
            session.error_message = str(e)
            session.updated_at = __import__('datetime').datetime.now()
            logger.error(f"[QrcodeManager] generate_qrcode failed: {e}")

        return session_id

    async def _poll_qrcode_status(
        self, session_id: str, adapter
    ):
        """后台轮询扫码状态"""
        session = self._sessions[session_id]

        try:
            for _ in range(DEFAULT_QR_TIMEOUT // DEFAULT_POLL_INTERVAL):
                if session.is_terminal:
                    return

                result = await adapter.check_status(session.qr_session_key)
                status = result.get("status", "waiting")

                if status == "scanned":
                    session.status = AcquisitionStatus.QR_SCANNED
                    session.updated_at = __import__('datetime').datetime.now()

                elif status == "confirmed":
                    # 获取 Cookie
                    session.status = AcquisitionStatus.COOKIES_EXTRACTING
                    session.updated_at = __import__('datetime').datetime.now()

                    cookies = result.get("cookies", [])
                    raw = "; ".join(
                        f"{c.get('name', '')}={c.get('value', '')}" for c in cookies
                    )
                    session.cookies_raw = raw
                    session.cookies_array = cookies

                    # 生成 Netscape 格式
                    cookie_content = self._cookies_to_netscape(cookies, session.platform)
                    session.status = AcquisitionStatus.COOKIES_EXTRACTED
                    session.updated_at = __import__('datetime').datetime.now()

                    # 提取账号信息
                    account_info = result.get("account_info", {})

                    # 保存到数据库
                    session.status = AcquisitionStatus.SAVING
                    session.updated_at = __import__('datetime').datetime.now()

                    connector_id = await self._save_to_db(
                        session_id=session_id,
                        platform=session.platform,
                        cookies_raw=raw,
                        cookies_array=cookies,
                        cookie_content=cookie_content,
                        account_info=account_info,
                    )
                    session.connector_id = connector_id

                    session.status = AcquisitionStatus.SUCCESS
                    session.updated_at = __import__('datetime').datetime.now()
                    logger.info(f"[QrcodeManager] Session {session_id} success, connector_id={connector_id}")
                    return

                elif status == "expired":
                    session.status = AcquisitionStatus.EXPIRED
                    session.updated_at = __import__('datetime').datetime.now()
                    return

                await asyncio.sleep(DEFAULT_POLL_INTERVAL)

            # 超时
            session.status = AcquisitionStatus.EXPIRED
            session.error_message = "二维码已过期，请刷新重试"
            session.updated_at = __import__('datetime').datetime.now()

        except Exception as e:
            session.status = AcquisitionStatus.FAILED
            session.error_message = str(e)
            session.updated_at = __import__('datetime').datetime.now()
            logger.error(f"[QrcodeManager] _poll_qrcode_status failed: {e}")

    async def refresh_qrcode(self, session_id: str) -> bool:
        """刷新过期二维码"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        if session.method != "qrcode":
            return False

        # 重新生成二维码
        adapter = get_qrcode_adapter(session.platform)
        if not adapter:
            return False

        try:
            qr_result = await adapter.generate_qrcode()
            session.qr_image_base64 = qr_result.get("qr_image_base64", "")
            session.qr_session_key = qr_result.get("session_key", "")
            session.status = AcquisitionStatus.QR_GENERATED
            session.updated_at = __import__('datetime').datetime.now()

            # 重新启动轮询
            asyncio.create_task(
                self._poll_qrcode_status(session_id, adapter)
            )
            return True
        except Exception as e:
            session.status = AcquisitionStatus.FAILED
            session.error_message = str(e)
            logger.error(f"[QrcodeManager] refresh_qrcode failed: {e}")
            return False

    async def _save_to_db(
        self,
        session_id: str,
        platform: str,
        cookies_raw: str,
        cookies_array: list[dict],
        cookie_content: str,
        account_info: dict,
    ) -> str:
        """保存获取结果到 PlatformConnection"""
        from app.db.database import SessionLocal
        from app.db.models.platform_connection import (
            PlatformConnection,
            AuthType,
            ConnectionStatus,
            AcquisitionMethod,
        )

        session = self._sessions[session_id]
        db = SessionLocal()
        try:
            from sqlmodel import select
            stmt = (
                select(PlatformConnection)
                .where(
                    PlatformConnection.platform == platform,
                    PlatformConnection.auth_type == AuthType.COOKIE,
                )
                .order_by(PlatformConnection.last_used.desc().nulls_last())
                .limit(1)
            )
            conn = db.exec(stmt).first()

            # 组装 credentials JSON
            credentials = {
                "raw": cookies_raw,
                "cookies_array": cookies_array,
                "source": "qrcode",
                "extracted_at": __import__('datetime').datetime.now().isoformat(),
            }

            if conn:
                conn.set_credentials(credentials)
                conn.cookie_content = cookie_content
                conn.acquisition_method = AcquisitionMethod.QRCODE
                conn.status = ConnectionStatus.ACTIVE
                conn.error_message = None
                if account_info.get("account_name"):
                    conn.account_id = account_info.get("account_id")
                    conn.account_name = account_info.get("account_name")
                    conn.account_avatar = account_info.get("account_avatar")
                    conn.account_url = account_info.get("account_url")
                conn.update_timestamp()
            else:
                import uuid as _uuid
                conn = PlatformConnection(
                    id=str(_uuid.uuid4()),
                    platform=platform,
                    name=session.connector_name or f"{platform} (扫码)",
                    auth_type=AuthType.COOKIE,
                    status=ConnectionStatus.ACTIVE,
                    acquisition_method=AcquisitionMethod.QRCODE,
                    cookie_content=cookie_content,
                    domains=get_platform_domains(platform),
                    test_url=get_platform_test_url(platform),
                    account_id=account_info.get("account_id"),
                    account_name=account_info.get("account_name"),
                    account_avatar=account_info.get("account_avatar"),
                    account_url=account_info.get("account_url"),
                )
                conn.set_credentials(credentials)

            db.add(conn)
            db.commit()
            db.refresh(conn)
            logger.info(f"[QrcodeManager] Saved PlatformConnection: {conn.id}")
            return conn.id

        except Exception as e:
            db.rollback()
            logger.error(f"[QrcodeManager] _save_to_db failed: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def _cookies_to_netscape(cookies: list[dict], platform: str) -> str:
        """将 Cookie 列表转为 Netscape 格式"""
        lines = ["# Netscape HTTP Cookie File", ""]
        for c in cookies:
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


# 全局单例
_qrcode_manager: Optional[QrcodeAcquisitionManager] = None


def get_qrcode_manager() -> QrcodeAcquisitionManager:
    """获取 QrCode 管理器全局实例"""
    global _qrcode_manager
    if _qrcode_manager is None:
        _qrcode_manager = QrcodeAcquisitionManager()
    return _qrcode_manager
