"""
YLCraft — 平台连接器服务（统一凭证架构）

管理各平台的凭证（Cookie / API Key / OAuth Token / Password）
唯一凭证存储：PlatformConnection 表

Cookie 存储规范：
- cookie_content: Netscape 格式（唯一存储位置）
- credentials.raw: 原始格式备份
- credentials.source: 来源标记 manual/playwright/qrcode
"""

from __future__ import annotations

import logging
import time
import httpx
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
    AcquisitionMethod,
)
from app.services.cookies.manager import CookieManager, get_cookie_manager
from app.services.platform_connection.bilibili import (
    extract_account_info_from_cookie as bilibili_extract_account,
)
from app.services.platform_connection.fanqie import (
    extract_account_info_from_cookie as fanqie_extract_account,
)

logger = logging.getLogger("ylcraft.platform_connection")


class PlatformConnectionService:
    """平台连接器服务"""

    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self._own_session = False  # 标记是否由内部创建，需要自行关闭

    def _ensure_session(self):
        """确保 session 可用，如果未传入则自动创建"""
        if self.session is None:
            from app.db.database import get_session
            self.session = next(get_session())
            self._own_session = True

    def _close_own_session(self):
        """关闭内部创建的 session"""
        if self._own_session and self.session is not None:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None
            self._own_session = False

    # =========================================================================
    # 基础 CRUD
    # =========================================================================

    def list_all(self) -> list[PlatformConnection]:
        self._ensure_session()
        """列出所有平台连接"""
        stmt = select(PlatformConnection).order_by(PlatformConnection.created_at.desc())
        return self.session.exec(stmt).all()

    def list_by_platform(self, platform: PlatformType) -> list[PlatformConnection]:
        """列出指定平台的所有连接"""
        self._ensure_session()
        stmt = (
            select(PlatformConnection)
            .where(PlatformConnection.platform == platform)
            .order_by(PlatformConnection.created_at.desc())
        )
        return self.session.exec(stmt).all()

    def get(self, conn_id: str) -> Optional[PlatformConnection]:
        """获取单个连接"""
        self._ensure_session()
        return self.session.get(PlatformConnection, conn_id)

    def get_active(self, platform: PlatformType | str) -> Optional[PlatformConnection]:
        """获取指定平台的活跃连接"""
        self._ensure_session()
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

    def get_default_connection(self, platform: str) -> Optional[PlatformConnection]:
        """获取指定平台的默认连接（优先活跃，否则最近创建）"""
        self._ensure_session()
        conn = self.get_active(platform)
        if conn:
            return conn
        # 降级：取最近创建的
        if isinstance(platform, str):
            try:
                platform = PlatformType(platform)
            except ValueError:
                return None
        stmt = (
            select(PlatformConnection)
            .where(PlatformConnection.platform == platform)
            .order_by(PlatformConnection.created_at.desc())
            .limit(1)
        )
        return self.session.exec(stmt).first()

    def create(self, data: PlatformConnectionCreate) -> PlatformConnection:
        """创建新连接"""
        import uuid

        # 如果没有指定 domains，设置默认值
        domains = data.domains
        if not domains:
            try:
                from app.services.cookies.base import get_platform_domains
                platform_str = self._get_platform_str(data.platform)
                default_domains = get_platform_domains(platform_str)
                if default_domains:
                    domains = default_domains
                    logger.info(f"[PlatformConnection] 使用默认 domains: {domains}")
            except Exception as e:
                logger.warning(f"[PlatformConnection] 获取默认 domains 失败: {e}")

        # 如果没有指定 test_url，设置默认值
        test_url = data.test_url
        if not test_url:
            try:
                from app.services.cookies.base import get_platform_test_url
                platform_str = self._get_platform_str(data.platform)
                default_test_url = get_platform_test_url(platform_str)
                if default_test_url:
                    test_url = default_test_url
                    logger.info(f"[PlatformConnection] 使用默认 test_url: {test_url}")
            except Exception as e:
                logger.warning(f"[PlatformConnection] 获取默认 test_url 失败: {e}")

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
            domains=domains,
            test_url=test_url,
        )

        # 处理 Cookie 存储
        self._apply_cookie_to_connection(conn, data.cookie_content, data.credentials)
        # 处理 credentials
        if data.credentials:
            conn.set_credentials(data.credentials)

        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        logger.info(f"[PlatformConnection] Created: {conn.id} for {conn.platform}, domains={domains}")
        return conn

    def update(self, conn_id: str, data: PlatformConnectionUpdate) -> Optional[PlatformConnection]:
        """更新连接"""
        conn = self.get(conn_id)
        if not conn:
            return None

        if data.name is not None:
            conn.name = data.name
        if data.auth_type is not None:
            conn.auth_type = data.auth_type
        if data.description is not None:
            conn.description = data.description
        if data.status is not None:
            conn.status = data.status
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
        if data.domains is not None:
            conn.domains = data.domains
        if data.test_url is not None:
            conn.test_url = data.test_url

        # 处理 Cookie 更新
        if data.cookie_content is not None or data.credentials is not None:
            self._apply_cookie_to_connection(conn, data.cookie_content, data.credentials)
        if data.credentials is not None:
            conn.set_credentials(data.credentials)

        conn.update_timestamp()
        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        if (data.cookie_content is not None or data.credentials is not None) and conn.cookie_content:
            self._sync_cookie_file(conn, conn.cookie_content)
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

    # =========================================================================
    # Cookie 统一管理（核心）
    # =========================================================================

    def get_raw_cookie(self, conn_id: str) -> Optional[str]:
        """
        获取原始格式 Cookie（用于 HTTP Header）

        Returns:
            原始格式 "key=value; key2=value2" 或 None
        """
        conn = self.get(conn_id)
        if not conn:
            return None

        return self._get_raw_cookie_from_connection(conn)

    def get_netscape_cookie(self, conn_id: str) -> Optional[str]:
        """
        获取 Netscape 格式 Cookie（用于 CookieManager）

        Returns:
            Netscape 格式字符串或 None
        """
        conn = self.get(conn_id)
        if not conn:
            return None
        return conn.cookie_content

    def get_cookie_any_format(self, conn_id: str) -> Optional[str]:
        """
        获取任意格式 Cookie（自动适配）

        按优先级返回：
        1. cookie_content (Netscape 格式)
        2. credentials.raw
        3. credentials.content

        Returns:
            可用的 Cookie 字符串或 None
        """
        conn = self.get(conn_id)
        if not conn:
            return None

        # 优先返回 cookie_content
        if conn.cookie_content:
            return conn.cookie_content

        # 降级：尝试从 credentials 获取
        creds = conn.get_credentials()
        raw = creds.get("raw", "")
        if raw:
            return raw

        content = creds.get("content", "")
        if content:
            return content

        return None

    def save_cookie(self, conn_id: str, cookie_str: str, source: str = "manual") -> bool:
        """
        统一保存 Cookie（自动识别格式并转换为 Netscape）

        Args:
            conn_id: 连接 ID
            cookie_str: 任意格式的 cookie 字符串
            source: 来源标记

        Returns:
            是否保存成功
        """
        conn = self.get(conn_id)
        if not conn:
            return False

        mgr = get_cookie_manager()

        # 解析为 Netscape 格式
        platform_str = self._get_platform_str(conn.platform)
        netscape_content = mgr.normalize_cookie(platform_str, cookie_str)
        if not netscape_content:
            logger.warning(f"[PlatformConnectionService] Cookie parse failed for {conn_id}")
            return False

        # 提取原始格式备份
        raw_cookie = mgr.extract_raw(netscape_content)

        # 存储到 cookie_content（唯一存储位置）
        conn.cookie_content = netscape_content

        # 同步更新 credentials
        creds = conn.get_credentials()
        creds["raw"] = raw_cookie
        creds["source"] = source
        conn.set_credentials(creds)

        conn.update_timestamp()
        self.session.add(conn)
        self.session.commit()

        # 同步写入 Cookie 文件
        self._sync_cookie_file(conn, netscape_content)

        logger.info(f"[PlatformConnectionService] Cookie saved for {conn_id}, count={mgr.validate(netscape_content)['count']}")
        return True

    def _get_raw_cookie_from_connection(self, conn: PlatformConnection) -> Optional[str]:
        """从连接对象获取原始 Cookie"""
        # 优先从 cookie_content 提取
        if conn.cookie_content:
            mgr = get_cookie_manager()
            raw = mgr.extract_raw(conn.cookie_content)
            if raw:
                return raw

        # 降级：从 credentials 获取
        creds = conn.get_credentials()
        raw = creds.get("raw", "")
        if raw:
            return raw

        content = creds.get("content", "")
        if content:
            return content

        return None

    def _apply_cookie_to_connection(
        self,
        conn: PlatformConnection,
        cookie_content: Optional[str],
        credentials: Optional[dict],
    ):
        """将 Cookie 数据应用到连接对象（不查询数据库）"""
        if cookie_content:
            # 直接存储 Netscape 格式
            mgr = get_cookie_manager()
            platform_str = self._get_platform_str(conn.platform)
            conn.cookie_content = mgr.normalize_cookie(platform_str, cookie_content)
        elif credentials:
            # 从 credentials 解析并转换为 Netscape 格式
            raw = credentials.get("raw", "")
            content = credentials.get("content", "")
            cookie_str = raw or content
            if cookie_str:
                mgr = get_cookie_manager()
                platform_str = self._get_platform_str(conn.platform)
                conn.cookie_content = mgr.normalize_cookie(platform_str, cookie_str)

    def _sync_cookie_file(self, conn: PlatformConnection, cookie_content: str):
        """同步写入 Cookie 文件"""
        try:
            from pathlib import Path

            backend_dir = Path(__file__).resolve().parent.parent.parent.parent
            cookie_dir = backend_dir / "data" / "cookies"
            cookie_dir.mkdir(parents=True, exist_ok=True)

            platform = self._get_platform_str(conn.platform)
            cookie_path = cookie_dir / f"{platform}.txt"

            # 清洗内容
            mgr = get_cookie_manager()
            clean_content = mgr.clean_cookie_content(cookie_content)

            cookie_path.write_text(clean_content, encoding="utf-8")
            cookie_path.chmod(0o600)
            logger.info(f"[PlatformConnectionService] Cookie file synced: {cookie_path.name}")
        except Exception as e:
            logger.warning(f"[PlatformConnectionService] Cookie file sync failed (non-critical): {e}")

    @staticmethod
    def _get_platform_str(platform: PlatformType | str) -> str:
        """获取平台字符串"""
        if hasattr(platform, "value"):
            return platform.value
        return str(platform)

    # =========================================================================
    # 连接测试
    # =========================================================================

    async def test_connection(self, conn_id: str) -> dict:
        """
        测试连接有效性
        返回 {"success": bool, "message": str}
        """
        conn = self.get(conn_id)
        if not conn:
            return {"success": False, "message": "连接不存在"}

        try:
            if conn.auth_type == AuthType.COOKIE:
                result = await self._test_cookie(conn)
            elif conn.auth_type == AuthType.API_KEY:
                result = self._test_api_key(conn)
            else:
                result = {"success": False, "message": f"不支持的认证类型: {conn.auth_type}"}

            # 更新状态
            conn.status = ConnectionStatus.ACTIVE if result["success"] else ConnectionStatus.FAILED
            conn.last_tested = datetime.now(timezone.utc)
            conn.error_message = result.get("message", "") if not result["success"] else None
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

    async def _test_cookie(self, conn: PlatformConnection) -> dict:
        """测试 Cookie 有效性"""
        platform = self._get_platform_str(conn.platform)
        mgr = get_cookie_manager()

        # 优先用 cookie_content
        cookie_str = conn.cookie_content or self._get_raw_cookie_from_connection(conn)
        if not cookie_str:
            return {"success": False, "message": "Cookie 内容为空"}

        # 验证格式
        result = mgr.validate(cookie_str)
        if result["valid"]:
            # 如果是B站，尝试提取账号信息
            if platform == "bilibili" and bilibili_extract_account:
                info = bilibili_extract_account(cookie_str)
                if info.get("account_id"):
                    conn.account_id = info["account_id"]
                    conn.account_name = info["account_name"]
                    conn.account_avatar = info["account_avatar"]
                    conn.account_url = info["account_url"]
                    self.session.add(conn)
                    self.session.commit()
                    return {"success": True, "message": f"Cookie有效，已提取账号: {info['account_name']}"}

            # 如果是番茄小说，尝试提取作家标识（只读探活 get_my_books）
            if platform == "fanqie" and fanqie_extract_account:
                info = fanqie_extract_account(cookie_str)
                if info.get("account_id"):
                    conn.account_id = info["account_id"]
                    conn.account_name = info["account_name"]
                    conn.account_avatar = info["account_avatar"]
                    conn.account_url = info["account_url"]
                    self.session.add(conn)
                    self.session.commit()
                    return {"success": True, "message": f"Cookie有效，已识别作家标识: {info['account_id']}"}

            # 如果是微信公众号，进行实际会话测试
            if platform == "wechat_mp":
                token = conn.get_credentials().get("token", "")
                if not token:
                    return {"success": False, "message": "缺少 token，请重新登录"}
                return await self._test_wechat_mp_session(conn, cookie_str, token)
            
            return {"success": True, "message": result["message"]}

        # 尝试自动转换
        netscape = mgr.normalize_cookie(platform, cookie_str)
        if netscape:
            result = mgr.validate(netscape)
            if result["valid"]:
                # 如果是B站，尝试提取账号信息
                if platform == "bilibili" and bilibili_extract_account:
                    info = bilibili_extract_account(cookie_str)
                    if info.get("account_id"):
                        conn.account_id = info["account_id"]
                        conn.account_name = info["account_name"]
                        conn.account_avatar = info["account_avatar"]
                        conn.account_url = info["account_url"]
                        self.session.add(conn)
                        self.session.commit()
                        return {"success": True, "message": f"自动转换后有效，已提取账号: {info['account_name']}"}

                # 如果是番茄小说，尝试提取作家标识
                if platform == "fanqie" and fanqie_extract_account:
                    info = fanqie_extract_account(cookie_str)
                    if info.get("account_id"):
                        conn.account_id = info["account_id"]
                        conn.account_name = info["account_name"]
                        conn.account_avatar = info["account_avatar"]
                        conn.account_url = info["account_url"]
                        self.session.add(conn)
                        self.session.commit()
                        return {"success": True, "message": f"自动转换后有效，已识别作家标识: {info['account_id']}"}

                return {"success": True, "message": f"自动转换后有效: {result['message']}"}

        return {"success": False, "message": result["message"]}

    def _test_api_key(self, conn: PlatformConnection) -> dict:
        """测试 API Key 有效性"""
        creds = conn.get_credentials()
        api_key = creds.get("api_key", "")
        if not api_key:
            return {"success": False, "message": "API Key 为空"}

        return {"success": True, "message": "API Key 格式正确（未进行实际连接测试）"}

    async def _test_wechat_mp_session(self, conn: PlatformConnection, cookie: str, token: str) -> dict:
        """测试微信公众号会话有效性"""
        try:
            from app.services.wechat_mp import get_wechat_mp_service
            from app.services.cookies.manager import get_cookie_manager
            
            # 使用公共组件将 Netscape 格式的 Cookie 转换为 HTTP Cookie 字符串格式
            if cookie.startswith("# Netscape HTTP Cookie File"):
                cookie = get_cookie_manager().extract_raw(cookie)
            
            service = get_wechat_mp_service()
            # 执行一个简单的搜索来测试会话是否有效
            result = await service.search_accounts(
                conn_id=conn.id,
                keyword="test",
                cookie=cookie,
                token=token,
                page=1,
                page_size=1,
            )
            
            # 检查是否有会话失效错误
            if result.get("error"):
                error_code = result.get("error_code")
                if error_code == 200003:
                    return {"success": False, "message": "会话已失效，请重新登录微信公众平台"}
                return {"success": False, "message": result["error"]}
            
            # 会话有效
            return {"success": True, "message": "会话有效"}
            
        except Exception as e:
            logger.error(f"[PlatformConnectionService] 测试微信公众号会话失败: {e}")
            return {"success": False, "message": f"测试失败: {str(e)}"}

    # =========================================================================
    # 统计
    # =========================================================================

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
