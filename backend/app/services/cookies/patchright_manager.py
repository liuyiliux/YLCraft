"""
YLCraft — Patchright Cookie 获取管理器

⚠️ 使用 Patchright 替代 Playwright（内置 Stealth 反检测）
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

from app.services.cookies.base import (
    AcquisitionSession,
    AcquisitionStatus,
    get_status_message,
    get_login_url,
    get_user_agent,
    get_platform_domains,
    get_platform_test_url,
)
from app.services.cookies.platforms import get_detector
from app.services.browser.patchright_runtime import (
    PATCHRIGHT_INSTALL_MESSAGE,
    get_patchright_runtime,
)

logger = logging.getLogger("ylcraft.cookies.patchright")

# 默认最大等待登录时间（秒）
DEFAULT_LOGIN_TIMEOUT = 300


class PatchrightAcquisitionManager:
    """Patchright Cookie 获取管理器（内置 Stealth 反检测）

    ⚠️ 使用 Patchright 替代 Playwright：
    - API 完全兼容，只需改 import
    - 内置 Stealth，无需手动注入 JS 脚本
    - 更强的反检测能力（修改了 Chromium 源码）
    """

    def __init__(self):
        self._sessions: dict[str, AcquisitionSession] = {}
        self._runtime = get_patchright_runtime()

    def is_available(self) -> bool:
        """检查 Patchright 是否可用"""
        return self._runtime.is_available()

    async def ensure_browser(self, headless: bool = False):
        """确保浏览器实例存在（懒加载）"""
        return await self._runtime.ensure_browser(headless=headless)

    def get_session(self, session_id: str) -> Optional[AcquisitionSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[AcquisitionSession]:
        """列出所有活跃会话"""
        return [s for s in self._sessions.values() if not s.is_terminal]

    async def start_session(
        self,
        platform: str,
        headless: bool = False,
        connector_name: str = "",
    ) -> str:
        """
        启动一个浏览器获取会话

        Returns:
            session_id
        """
        if not self.is_available():
            raise RuntimeError(PATCHRIGHT_INSTALL_MESSAGE)

        session_id = str(uuid.uuid4())
        session = AcquisitionSession(
            session_id=session_id,
            platform=platform,
            method="patchright",  # ✅ 改为 patchright
            connector_name=connector_name,
        )
        self._sessions[session_id] = session

        try:
            await self.ensure_browser(headless)
            session.status = AcquisitionStatus.BROWSER_LAUNCHING

            context = await self._runtime.new_context(
                headless=headless,
                viewport={"width": 1280, "height": 800},
                user_agent=get_user_agent(platform),
            )

            # ✅ 无需注入 Stealth！Patchright 已内置反检测

            page = await context.new_page()

            # 导航到登录页
            session.status = AcquisitionStatus.PAGE_LOADING
            login_url = get_login_url(platform)
            await self._goto_login_page(page, login_url)

            # 更新状态
            session.status = AcquisitionStatus.WAITING_FOR_LOGIN
            session.browser_context = context
            session.page_url = page.url
            session.updated_at = __import__('datetime').datetime.now()

            # 启动后台检测任务
            asyncio.create_task(
                self._detect_login(session_id, page, platform)
            )

        except Exception as e:
            session.status = AcquisitionStatus.FAILED
            session.error_message = str(e)
            session.updated_at = __import__('datetime').datetime.now()
            logger.error(
                "[PatchrightManager] start_session failed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            # 必须把失败抛出去。此前这里只写 status 就照常 return session_id，
            # 于是接口永远返回 success=true —— 浏览器根本没起来也显示"成功"，
            # 用户端只看到弹窗没反应，排查时毫无线索。
            raise

        return session_id

    async def _goto_login_page(self, page, login_url: str) -> None:
        """打开登录页。

        不要用 networkidle 等待策略：番茄作家后台等站点有**常驻轮询**
        （消息通知、状态心跳），网络永远不会空闲，等 networkidle 必然超时
        （实测 `Page.goto: Timeout 30000ms exceeded`），并因抛出异常把整个会话标记失败
        —— 而实际上登录页早就开好了、二维码都能扫。

        所以改为 `domcontentloaded`（拿到 DOM 即可，登录页不依赖懒加载数据），
        失败时只告警不中断：用户要的是"打开页面并等他登录"，导航等待策略不该
        决定这次会话成不成功。
        """
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            # 页面可能已部分可用（例如仅在等待某个一直没有响应的资源）。
            logger.warning(
                "[PatchrightManager] goto %s 未在超时内完成，继续等待登录：%s",
                login_url,
                exc,
            )

    async def _detect_login(
        self,
        session_id: str,
        page,
        platform: str,
    ):
        """后台检测用户是否完成登录"""
        session = self._sessions[session_id]
        detector = get_detector(platform)

        if not detector:
            session.status = AcquisitionStatus.FAILED
            session.error_message = f"平台 {platform} 暂不支持 Patchright 获取"
            session.updated_at = __import__('datetime').datetime.now()
            return

        try:
            # 轮询检测登录状态（最多等待 5 分钟）
            for _ in range(DEFAULT_LOGIN_TIMEOUT):
                if session.is_terminal:
                    return

                try:
                    is_logged_in = await detector.detect(page)
                except Exception:
                    # 页面可能正在跳转，忽略临时错误
                    await asyncio.sleep(1)
                    continue

                if is_logged_in:
                    # 提取 Cookie
                    session.status = AcquisitionStatus.COOKIES_EXTRACTING
                    session.updated_at = __import__('datetime').datetime.now()

                    cookies = await page.context.cookies()

                    # 组装 raw 格式
                    raw = "; ".join(
                        f"{c['name']}={c['value']}" for c in cookies
                    )
                    session.cookies_raw = raw
                    session.cookies_array = cookies

                    # 生成 Netscape 格式
                    cookie_content = self._cookies_to_netscape(cookies, platform)
                    session.status = AcquisitionStatus.COOKIES_EXTRACTED
                    session.updated_at = __import__('datetime').datetime.now()

                    # 提取账号信息
                    account_info = {}
                    try:
                        account_info = await detector.extract_account_info(page)
                    except Exception as e:
                        logger.warning(
                            "[PatchrightManager] extract_account_info failed: %s: %s",
                            type(e).__name__,
                            e,
                        )

                    # 保存到数据库
                    session.status = AcquisitionStatus.SAVING
                    session.updated_at = __import__('datetime').datetime.now()

                    connector_id = await self._save_to_db(
                        session_id=session_id,
                        platform=platform,
                        cookies_raw=raw,
                        cookies_array=cookies,
                        cookie_content=cookie_content,
                        account_info=account_info,
                    )
                    session.connector_id = connector_id

                    # 同步写入 Cookie 文件，确保 CookieManager 立即可用
                    try:
                        from pathlib import Path
                        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
                        cookie_dir = backend_dir / "data" / "cookies"
                        cookie_dir.mkdir(parents=True, exist_ok=True)
                        cookie_path = cookie_dir / f"{platform}.txt"
                        # 写入清洗后的 Netscape 内容
                        from app.services.cookies.manager import get_cookie_manager
                        mgr = get_cookie_manager()
                        clean_content = mgr._clean_netscape_content(cookie_content)
                        cookie_path.write_text(clean_content, encoding="utf-8")
                        cookie_path.chmod(0o600)
                        logger.info(f"[PatchrightManager] Cookie file synced: {cookie_path.name}")
                    except Exception as sync_err:
                        logger.warning(f"[PatchrightManager] Cookie file sync failed (non-critical): {sync_err}")

                    session.status = AcquisitionStatus.SUCCESS
                    session.updated_at = __import__('datetime').datetime.now()
                    logger.info(f"[PatchrightManager] Session {session_id} success, connector_id={connector_id}")

                    # 关闭浏览器上下文
                    try:
                        await page.context.close()
                    except Exception:
                        pass
                    return

                await asyncio.sleep(1)

            # 超时
            session.status = AcquisitionStatus.FAILED
            session.error_message = "登录等待超时（5 分钟）"
            session.updated_at = __import__('datetime').datetime.now()
            try:
                await page.context.close()
            except Exception:
                pass

        except Exception as e:
            session.status = AcquisitionStatus.FAILED
            session.error_message = str(e)
            session.updated_at = __import__('datetime').datetime.now()
            try:
                await page.context.close()
            except Exception:
                pass

    async def cancel_session(self, session_id: str) -> bool:
        """取消会话"""
        session = self._sessions.get(session_id)
        if not session or session.is_terminal:
            return False

        session.status = AcquisitionStatus.CANCELLED
        session.updated_at = __import__('datetime').datetime.now()

        # 关闭浏览器上下文
        if session.browser_context:
            try:
                await session.browser_context.close()
            except Exception:
                pass
            session.browser_context = None

        return True

    async def _save_to_db(
        self,
        session_id: str,
        platform: str,
        cookies_raw: str,
        cookies_array: list[dict],
        cookie_content: str,
        account_info: dict,
    ) -> str:
        """保存获取结果到 PlatformConnection。

        实际落库是**同步** SQLAlchemy（SessionLocal + commit），因此放到工作线程执行。

        为什么必须这样：本方法此前直接在当前协程里跑同步 DB 调用。uvicorn 只有一个
        事件循环，同步阻塞调用会把**整个服务**卡住——实测表现为端口仍在 Listen，
        但连接全部堆在 CloseWait、任何请求都超时（连 /api/v1/platforms 都不响应），
        而脱离 uvicorn 单独跑同一段代码仅需 1 秒。用 to_thread 让阻塞 I/O 不占用循环。
        """
        return await asyncio.to_thread(
            self._save_to_db_sync,
            session_id=session_id,
            platform=platform,
            cookies_raw=cookies_raw,
            cookies_array=cookies_array,
            cookie_content=cookie_content,
            account_info=account_info,
        )

    def _save_to_db_sync(
        self,
        session_id: str,
        platform: str,
        cookies_raw: str,
        cookies_array: list[dict],
        cookie_content: str,
        account_info: dict,
    ) -> str:
        """同步落库实现（只应在工作线程中调用，见 _save_to_db）。"""
        from app.db.database import SessionLocal
        from app.db.models.platform_connection import (
            PlatformConnection,
            PlatformType,
            AuthType,
            ConnectionStatus,
            AcquisitionMethod,
        )

        session = self._sessions[session_id]
        db = SessionLocal()
        try:
            # 查找同平台的活跃连接
            from sqlmodel import select
            try:
                plat_enum = PlatformType(platform)
            except ValueError:
                plat_enum = None

            if plat_enum:
                stmt = (
                    select(PlatformConnection)
                    .where(
                        PlatformConnection.platform == plat_enum,
                        PlatformConnection.auth_type == AuthType.COOKIE,
                    )
                    .order_by(PlatformConnection.last_used.desc().nulls_last())
                    .limit(1)
                )
                conn = db.exec(stmt).first()
            else:
                conn = None

            # 组装 credentials JSON
            credentials = {
                "raw": cookies_raw,
                "cookies_array": cookies_array,
                "source": "patchright",  # ✅ 改为 patchright
                "browser_version": "Chromium",
                "extracted_at": __import__('datetime').datetime.now().isoformat(),
            }

            if conn:
                # 更新现有连接
                conn.set_credentials(credentials)
                conn.cookie_content = cookie_content
                conn.acquisition_method = AcquisitionMethod.PATCHRIGHT  # ✅ 改为 PATCHRIGHT
                conn.status = ConnectionStatus.ACTIVE
                conn.error_message = None
                if account_info.get("account_name"):
                    conn.account_id = account_info.get("account_id")
                    conn.account_name = account_info.get("account_name")
                    conn.account_avatar = account_info.get("account_avatar")
                    conn.account_url = account_info.get("account_url")
                conn.update_timestamp()
            else:
                # 创建新连接
                import uuid as _uuid
                if not plat_enum:
                    raise ValueError(f"Unsupported platform: {platform}")
                conn = PlatformConnection(
                    id=str(_uuid.uuid4()),
                    platform=plat_enum,
                    name=session.connector_name or f"{platform} (Patchright)",  # ✅ 改为 Patchright
                    auth_type=AuthType.COOKIE,
                    status=ConnectionStatus.ACTIVE,
                    acquisition_method=AcquisitionMethod.PATCHRIGHT,  # ✅ 改为 PATCHRIGHT
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
            logger.info(f"[PatchrightManager] Saved PlatformConnection: {conn.id}")
            return conn.id

        except Exception as e:
            db.rollback()
            # 必须带上异常类型。此前只打 `str(e)`，日志里就剩孤零零的 `PATCHRIGHT`，
            # 看着像数据库枚举问题，真实却是 AttributeError（枚举成员不存在）——
            # 误导排查方向。已有 FORMAT 变量保证金字塔里也能自证类型。
            logger.error(
                "[PatchrightManager] _save_to_db failed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            raise
        finally:
            db.close()

    @staticmethod
    def _cookies_to_netscape(cookies: list[dict], platform: str) -> str:
        """将 Patchright cookies 列表转为 Netscape 格式"""
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

    async def close(self):
        """关闭所有资源"""
        await self._runtime.close()


# 全局单例
_patchright_manager: Optional[PatchrightAcquisitionManager] = None


def get_patchright_manager() -> PatchrightAcquisitionManager:
    """获取 Patchright 管理器全局实例"""
    global _patchright_manager
    if _patchright_manager is None:
        _patchright_manager = PatchrightAcquisitionManager()
    return _patchright_manager
