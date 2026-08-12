"""
YLCraft — 微信公众号公众平台适配器

包含：
- WechatMPDetector：浏览器登录检测器（Patchright 用）
- WechatMPQrcodeAdapter：扫码登录适配器（httpx 纯 API 调用）

扫码登录流程：
  1. POST /cgi-bin/bizlogin?action=startlogin → 初始化会话 + 下发 uuid + Set-Cookie
  2. GET  /cgi-bin/scanloginqrcode?action=getqrcode → 拉 JPG 二维码图片
  3. GET  /cgi-bin/scanloginqrcode?action=ask&uuid=…&token=&lang=zh_CN → 轮询
     status=0 等待扫码
     status=4 已扫码/已关注（待确认）
     status=2 过期
     status=1 确认成功（redirect_url / token 等）
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import random
import re
import time
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

from app.services.cookies.base import PlatformDetector, QrcodeAdapter

logger = logging.getLogger("ylcraft.wechat_mp.adapter")

# 微信公众平台 API
MP_BASE = "https://mp.weixin.qq.com"
ENDPOINT_STARTLOGIN = f"{MP_BASE}/cgi-bin/bizlogin?action=startlogin"
ENDPOINT_LOGIN = f"{MP_BASE}/cgi-bin/bizlogin?action=login"
ENDPOINT_GETQRCODE = f"{MP_BASE}/cgi-bin/scanloginqrcode"
ENDPOINT_ASK = f"{MP_BASE}/cgi-bin/scanloginqrcode"
ENDPOINT_AUTH_ASK = f"{MP_BASE}/cgi-bin/loginauth"

# 通用请求头
_MP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": f"{MP_BASE}/cgi-bin/loginpage",
    "Origin": MP_BASE,
    "X-Requested-With": "XMLHttpRequest",
}


class WechatMPDetector(PlatformDetector):
    """
    微信公众号公众平台登录检测器

    登录成功标志（任一即可）：
    1. URL 跳转到 mp.weixin.qq.com/cgi-bin/home* 或 /cgi-bin/appmsg*
    2. 页面出现"首页"、"内容分析"、"图文素材"等登录后元素
    3. Cookie 中包含 slave_user / master_user / uin / skey 等关键字段
    """

    # 登录成功的 URL 特征
    LOGGED_IN_URL_PATTERNS = [
        r"mp\.weixin\.qq\.com/cgi-bin/home",
        r"mp\.weixin\.qq\.com/cgi-bin/appmsg",
        r"mp\.weixin\.qq\.com/cgi-bin/message",
        r"mp\.weixin\.qq\.com/cgi-bin/userindex",
        r"mp\.weixin\.qq\.com/cgi-bin/operate",
    ]

    # 登录成功的 DOM 特征
    LOGGED_IN_SELECTORS = [
        ".weui-desktop-header",
        ".weui-desktop-account",
        "a[href*='cgi-bin/home']",
        "a[href*='cgi-bin/appmsg']",
        "a[href*='cgi-bin/userindex']",
    ]

    # 登录前的 URL 特征
    LOGIN_PAGE_URL_PATTERNS = [
        r"mp\.weixin\.qq\.com/.*scanlogin",
        r"mp\.weixin\.qq\.com/.*login",
        r"^https?://mp\.weixin\.qq\.com/?$",
    ]

    async def detect(self, page) -> bool:
        """检测用户是否完成登录"""
        try:
            current_url = page.url
            logger.debug(f"[WechatMPDetector] Current URL: {current_url}")

            for pattern in self.LOGGED_IN_URL_PATTERNS:
                if re.search(pattern, current_url):
                    logger.info(f"[WechatMPDetector] Login detected by URL: {current_url}")
                    return True

            try:
                cookies = await page.context.cookies()
                cookie_names = {c["name"] for c in cookies}
                if "slave_user" in cookie_names or "master_user" in cookie_names:
                    if "uin" in cookie_names or "skey" in cookie_names:
                        logger.info(f"[WechatMPDetector] Login detected by cookies")
                        return True
            except Exception as cookie_err:
                logger.debug(f"[WechatMPDetector] Cookie check failed: {cookie_err}")

            for selector in self.LOGGED_IN_SELECTORS:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        logger.info(f"[WechatMPDetector] Login detected by DOM: {selector}")
                        return True
                except Exception:
                    pass

            return False

        except Exception as e:
            logger.warning(f"[WechatMPDetector] detect failed: {e}")
            return False

    async def extract_account_info(self, page) -> dict:
        """提取登录后的账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": "https://mp.weixin.qq.com/",
        }

        try:
            current_url = page.url
            token_match = re.search(r"[?&]token=(\d+)", current_url)
            if token_match:
                info["account_id"] = token_match.group(1)

            try:
                nick = await page.evaluate("""() => {
                    return window.nickname || window.wx?.commonData?.nickname || ''
                }""")
                if nick:
                    info["account_name"] = nick
            except Exception:
                pass

            if not info["account_name"]:
                selectors = [
                    ".weui-desktop-account .nickname",
                    ".account-name",
                    ".weui-desktop-header .nickname",
                    "[data-nickname]",
                ]
                for sel in selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            text = (await el.inner_text()).strip()
                            if text:
                                info["account_name"] = text
                                break
                    except Exception:
                        pass

            if not info["account_avatar"]:
                avatar_selectors = [
                    ".weui-desktop-account img.avatar",
                    ".account-avatar img",
                    ".weui-desktop-header img",
                ]
                for sel in avatar_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            src = await el.get_attribute("src")
                            if src and ("qpic.cn" in src or "qlogo.cn" in src):
                                info["account_avatar"] = src
                                break
                    except Exception:
                        pass

            logger.info(f"[WechatMPDetector] Extracted: {info}")
        except Exception as e:
            logger.warning(f"[WechatMPDetector] extract_account_info failed: {e}")

        return info


class WechatMPQrcodeAdapter(QrcodeAdapter):
    """
    微信公众号扫码登录适配器

    流程：
      1. POST /cgi-bin/bizlogin?action=startlogin → 初始化会话 + 下发 uuid + Set-Cookie
      2. GET  /cgi-bin/scanloginqrcode?action=getqrcode → 拉 JPG 二维码图片
      3. GET  /cgi-bin/scanloginqrcode?action=ask&uuid=… → 轮询扫码状态
         status=0 等待扫码
         status=1 已扫码/已关注（待确认）
         status=2 过期
         status>=3 确认成功

    每个扫码会话使用独立的 httpx.AsyncClient（_sessions 字典），
    确保 Set-Cookie 跨请求持久化且不会跨会话污染。
    """

    def __init__(self):
        # per-session 的 HTTP 客户端 { session_key: httpx.AsyncClient }
        self._sessions: dict[str, httpx.AsyncClient] = {}
        # 需要二次授权确认的扫码会话
        self._auth_sessions: set[str] = set()
        self._confirm_attempts: dict[str, int] = {}

    def _create_client(self) -> httpx.AsyncClient:
        """创建新的 HTTP 客户端（per-session）"""
        return httpx.AsyncClient(
            timeout=15.0,
            headers=_MP_HEADERS,
            verify=False,
            follow_redirects=False,
        )

    def _get_client(self, session_key: str) -> httpx.AsyncClient:
        """获取指定会话的 HTTP 客户端"""
        client = self._sessions.get(session_key)
        if client is None or client.is_closed:
            client = self._create_client()
            self._sessions[session_key] = client
        return client

    async def _ensure_seed_cookies(self, client: httpx.AsyncClient) -> None:
        """
        确保 httpx client 中有基础种子 cookie。

        bizlogin?action=startlogin 依赖 ua_id / wxuin / xid 等指纹 cookie，
        没有它们会返回错误。先访问登录页来获取这些 cookie。
        """
        # 如果已有 cookie 则跳过
        if client.cookies.get("ua_id", domain=".weixin.qq.com"):
            return

        try:
            logger.debug("[WechatMPQrcode] Visiting login page to seed cookies...")
            resp = await client.get(
                f"{MP_BASE}/cgi-bin/loginpage",
                follow_redirects=True,
            )
            logger.debug(
                f"[WechatMPQrcode] Login page status={resp.status_code}, "
                f"cookies={len(client.cookies)}"
            )
        except Exception as e:
            logger.warning(f"[WechatMPQrcode] Failed to seed cookies: {e}")

    async def generate_qrcode(self) -> dict:
        """
        生成微信公众号登录二维码

        Returns:
            {
                "qr_image_base64": "data:image/jpg;base64,...",
                "session_key": "<uuid>",
                "expires_in": 180,
            }
        """
        try:
            # 1. 创建 per-session 的 HTTP 客户端
            #    用临时 key 先做 seed cookie，等 startlogin 返回真实 uuid 后再替换
            temp_key = f"_temp_{int(time.time() * 1000)}"
            client = self._create_client()
            self._sessions[temp_key] = client

            # 2. 确保有种子 cookie
            await self._ensure_seed_cookies(client)

            # 3. 调用 startlogin 初始化扫码会话
            start_resp = await client.post(
                ENDPOINT_STARTLOGIN,
                data={
                    "userlang": "zh_CN",
                    "redirect_url": "",
                    "login_type": "3",
                    "sessionid": str(random.randint(10**14, 10**15 - 1)),
                    "fingerprint": hashlib.md5(os.urandom(16)).hexdigest(),
                    "token": "",
                    "lang": "zh_CN",
                    "f": "json",
                    "ajax": "1",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
            start_resp.raise_for_status()
            body = start_resp.json()

            base_resp = body.get("base_resp", {})
            ret = base_resp.get("ret", -1)
            err_msg = base_resp.get("err_msg", "")

            if ret != 0:
                # freq limited 或其他错误 → 清理临时 client
                del self._sessions[temp_key]
                await client.aclose()
                raise RuntimeError(
                    f"startlogin 失败: ret={ret}, err_msg={err_msg}, body={body}"
                )

            uuid_ = body.get("uuid", "")
            if not uuid_:
                del self._sessions[temp_key]
                await client.aclose()
                raise RuntimeError(f"startlogin 返回空 uuid: {body}")

            logger.info(f"[WechatMPQrcode] startlogin success, uuid={uuid_[:12]}...")

            # 用真实 uuid 替换临时 key
            self._sessions[uuid_] = client
            del self._sessions[temp_key]

            # 4. 拉取二维码图片
            qr_resp = await client.get(
                ENDPOINT_GETQRCODE,
                params={
                    "action": "getqrcode",
                    "random": str(int(time.time() * 1000)),
                    "login_appid": "",
                },
            )
            qr_resp.raise_for_status()

            content_type = qr_resp.headers.get("content-type", "")
            if "image" not in content_type and "octet-stream" not in content_type:
                logger.warning(
                    f"[WechatMPQrcode] getqrcode unexpected content-type: {content_type}, "
                    f"body preview: {qr_resp.text[:200]}"
                )
                raise RuntimeError(f"获取二维码图片失败，返回了非图片内容: {content_type}")

            img_b64 = base64.b64encode(qr_resp.content).decode()
            logger.info(
                f"[WechatMPQrcode] QR image fetched, size={len(qr_resp.content)} bytes"
            )

            return {
                "qr_image_base64": f"data:image/jpg;base64,{img_b64}",
                "session_key": uuid_,
                "expires_in": 180,
            }

        except Exception as e:
            logger.error(f"[WechatMPQrcode] generate_qrcode failed: {e}")
            raise

    async def check_status(self, session_key: str) -> dict:
        """
        轮询微信公众号扫码状态

        Args:
            session_key: startlogin 返回的 uuid

        Returns:
            {
                "status": "waiting" | "scanned" | "confirmed" | "expired",
                "cookies": [...],          # confirmed 时返回
                "account_info": {...},     # confirmed 时返回
            }
        """
        try:
            client = self._get_client(session_key)
            resp = await client.get(
                ENDPOINT_ASK,
                params={
                    "action": "ask",
                    "token": "",
                    "lang": "zh_CN",
                    "uuid": session_key,
                    "f": "json",
                    "ajax": "1",
                    "random": str(int(time.time() * 1000)),
                },
            )
            resp.raise_for_status()

            # 尝试解析 JSON
            try:
                data = resp.json()
            except Exception:
                logger.warning(
                    f"[WechatMPQrcode] ask response is not JSON, "
                    f"content-type={resp.headers.get('content-type')}, "
                    f"preview={resp.text[:200]}"
                )
                return {"status": "waiting"}

            # scanloginqrcode?action=ask 返回 JSON 中的 status 字段
            status = int(data.get("status", 0))
            base_resp = data.get("base_resp") or {}
            logger.debug(
                f"[WechatMPQrcode] ask status={status}, "
                f"ret={base_resp.get('ret')}, err_msg={base_resp.get('err_msg')}, "
                f"data keys={list(data.keys())}"
            )

            # status=0: 等待扫码
            if status == 0:
                return {"status": "waiting"}

            # status=4: 已扫码/已关注，待确认
            if status == 4:
                return {"status": "scanned"}

            # status=2: 二维码过期
            if status == 2:
                # 清理过期的 session client
                await self._cleanup_session(session_key)
                return {"status": "expired"}

            # status=1: 已确认登录，继续换取 redirect_url / token
            if status == 1:
                return await self._complete_confirmed_login(session_key, client, data)

            # 未知状态，当作等待
            logger.warning(f"[WechatMPQrcode] Unknown status={status}, data={data}")
            return {"status": "waiting"}

        except Exception as e:
            logger.error(f"[WechatMPQrcode] check_status failed: {e}")
            return {"status": "waiting", "error": str(e)}

    async def _complete_confirmed_login(
        self,
        session_key: str,
        client: httpx.AsyncClient,
        ask_data: dict,
    ) -> dict:
        redirect_url = ask_data.get("redirect_url") or ask_data.get("url", "")
        token = str(ask_data.get("token") or "") or self._extract_token(redirect_url)
        try:
            user_category = int(ask_data.get("user_category", 0))
        except (TypeError, ValueError):
            user_category = 0

        # user_category=1 表示非管理员扫码后进入管理员二次授权流程；
        # 需要先等待 loginauth?action=ask 返回 status=1，再执行 bizlogin?action=login。
        if user_category == 1 and not token:
            self._auth_sessions.add(session_key)
            auth_result = await self._check_login_auth(client)
            auth_status = auth_result.get("status")
            if auth_status == "confirmed":
                redirect_url = auth_result.get("redirect_url") or redirect_url
                token = auth_result.get("token", "")
            elif auth_status == "expired":
                await self._cleanup_session(session_key)
                return {"status": "expired"}
            else:
                attempts = self._confirm_attempts.get(session_key, 0) + 1
                self._confirm_attempts[session_key] = attempts
                if attempts in {1, 3, 10} or attempts % 30 == 0:
                    logger.info(
                        "[WechatMPQrcode] waiting for WeChat MP admin authorization, "
                        f"attempt={attempts}, ask_keys={list(ask_data.keys())}"
                    )
                return {"status": "scanned", "message": "已扫码，等待公众号管理员确认授权"}

        if not token:
            login_result = await self._finish_login(client)
            redirect_url = login_result.get("redirect_url") or redirect_url
            token = login_result.get("token", "")

        if not token:
            auth_result = await self._check_login_auth(client)
            auth_status = auth_result.get("status")
            if auth_status == "confirmed":
                redirect_url = auth_result.get("redirect_url") or redirect_url
                token = auth_result.get("token", "")
                if not token:
                    login_result = await self._finish_login(client)
                    redirect_url = login_result.get("redirect_url") or redirect_url
                    token = login_result.get("token", "")
            elif auth_status == "expired":
                await self._cleanup_session(session_key)
                return {"status": "expired"}

        if not token:
            self._auth_sessions.add(session_key)
            attempts = self._confirm_attempts.get(session_key, 0) + 1
            self._confirm_attempts[session_key] = attempts
            log_msg = (
                "[WechatMPQrcode] login confirmed but token not ready yet, "
                f"attempt={attempts}, ask_status={ask_data.get('status')}, "
                f"ask_keys={list(ask_data.keys())}"
            )
            if attempts in {1, 3, 10} or attempts % 30 == 0:
                logger.info(log_msg)
            else:
                logger.debug(log_msg)
            return {"status": "scanned", "message": "已确认，正在完成微信公众号授权"}

        cookies_array = self._dump_cookies(client)
        account_info = await self._fetch_account_info(client, token)

        logger.info(
            f"[WechatMPQrcode] Login confirmed! "
            f"token_present={bool(token)}, "
            f"cookies={len(cookies_array)}, "
            f"account={account_info.get('account_name', 'N/A')}"
        )

        await self._cleanup_session(session_key)

        return {
            "status": "confirmed",
            "cookies": cookies_array,
            "account_info": account_info,
        }

    async def _finish_login(self, client: httpx.AsyncClient) -> dict:
        try:
            resp = await client.post(
                ENDPOINT_LOGIN,
                data={
                    "userlang": "zh_CN",
                    "redirect_url": "",
                    "login_type": "3",
                    "token": "",
                    "lang": "zh_CN",
                    "f": "json",
                    "ajax": "1",
                    "random": str(int(time.time() * 1000)),
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": f"{MP_BASE}/cgi-bin/loginpage",
                },
            )
            resp.raise_for_status()
            data = {}
            try:
                data = resp.json()
            except Exception:
                logger.warning(
                    f"[WechatMPQrcode] finish_login response is not JSON, "
                    f"content-type={resp.headers.get('content-type')}, "
                    f"preview={resp.text[:200]}"
                )

            redirect_url = (
                data.get("redirect_url")
                or data.get("url")
                or resp.headers.get("location", "")
            )
            if redirect_url.startswith("/"):
                redirect_url = f"{MP_BASE}{redirect_url}"

            token = str(data.get("token") or "") or self._extract_token(redirect_url)
            if redirect_url:
                try:
                    landing_resp = await client.get(
                        redirect_url,
                        headers={"Referer": f"{MP_BASE}/cgi-bin/loginpage"},
                        follow_redirects=True,
                    )
                    token = token or self._extract_token(str(landing_resp.url))
                except Exception:
                    pass

            base_resp = data.get("base_resp") or {}
            logger.info(
                f"[WechatMPQrcode] finish_login token={'yes' if token else 'no'}, "
                f"ret={base_resp.get('ret')}, err_msg={base_resp.get('err_msg')}, "
                f"keys={list(data.keys())}, redirect={'yes' if redirect_url else 'no'}"
            )
            return {"redirect_url": redirect_url, "token": token}
        except Exception as e:
            logger.warning(f"[WechatMPQrcode] finish_login failed: {e}")
            return {"redirect_url": "", "token": ""}

    async def _check_login_auth(self, client: httpx.AsyncClient) -> dict:
        try:
            resp = await client.get(
                ENDPOINT_AUTH_ASK,
                params={
                    "action": "ask",
                    "token": "",
                    "lang": "zh_CN",
                    "f": "json",
                    "ajax": "1",
                    "random": str(int(time.time() * 1000)),
                },
                headers={"Referer": f"{MP_BASE}/cgi-bin/loginpage"},
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                logger.warning(
                    f"[WechatMPQrcode] loginauth ask response is not JSON, "
                    f"content-type={resp.headers.get('content-type')}, "
                    f"preview={resp.text[:200]}"
                )
                return {"status": "scanned"}

            redirect_url = data.get("redirect_url") or data.get("url", "")
            if redirect_url.startswith("/"):
                redirect_url = f"{MP_BASE}{redirect_url}"
            token = str(data.get("token") or "") or self._extract_token(redirect_url)
            raw_status = data.get("status")
            try:
                status = int(raw_status)
            except (TypeError, ValueError):
                status = -1
            base_resp = data.get("base_resp") or {}

            logger.info(
                f"[WechatMPQrcode] loginauth ask status={status}, "
                f"ret={base_resp.get('ret')}, err_msg={base_resp.get('err_msg')}, "
                f"token={'yes' if token else 'no'}, keys={list(data.keys())}"
            )

            if token or redirect_url or status == 1:
                return {
                    "status": "confirmed",
                    "redirect_url": redirect_url,
                    "token": token,
                }
            if status == 2:
                return {"status": "expired"}
            return {"status": "scanned"}
        except Exception as e:
            logger.debug(f"[WechatMPQrcode] loginauth ask failed: {e}")
            return {"status": "scanned"}

    def _dump_cookies(self, client: httpx.AsyncClient) -> list[dict]:
        """从 httpx cookie jar 提取 cookie 列表"""
        out = []
        for c in client.cookies.jar:
            out.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain or ".weixin.qq.com",
                "path": c.path or "/",
                "expires": c.expires or -1,
                "secure": c.secure,
                "httpOnly": False,
            })
        return out

    @staticmethod
    def _extract_token(url: str) -> str:
        """从 redirect_url 提取 token 参数"""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            return params.get("token", [""])[0]
        except Exception:
            return ""

    async def _fetch_account_info(
        self, client: httpx.AsyncClient, token: str
    ) -> dict:
        """
        确认登录后拉取账号信息

        访问 /cgi-bin/home 提取 nickname / head_img
        """
        info = {
            "account_id": token,
            "account_name": "",
            "account_avatar": "",
            "account_url": "https://mp.weixin.qq.com/",
        }

        if not token:
            return info

        try:
            resp = await client.get(
                f"{MP_BASE}/cgi-bin/home",
                params={
                    "t": "home/index",
                    "token": token,
                    "lang": "zh_CN",
                },
                headers={
                    "Referer": f"{MP_BASE}/",
                },
            )

            text = resp.text

            # 提取 nickname
            nick_match = re.search(r'nickname\s*=\s*["\']([^"\']+)["\']', text)
            if nick_match:
                info["account_name"] = nick_match.group(1)

            # 提取 head_img
            avatar_match = re.search(r'head_img\s*=\s*["\']([^"\']+)["\']', text)
            if avatar_match:
                info["account_avatar"] = avatar_match.group(1)

            logger.info(
                f"[WechatMPQrcode] Account info: "
                f"name={info['account_name']}, "
                f"avatar={'yes' if info['account_avatar'] else 'no'}"
            )

        except Exception as e:
            logger.warning(f"[WechatMPQrcode] _fetch_account_info failed: {e}")

        return info

    async def _cleanup_session(self, session_key: str) -> None:
        """清理指定会话的 HTTP 客户端"""
        self._auth_sessions.discard(session_key)
        self._confirm_attempts.pop(session_key, None)
        client = self._sessions.pop(session_key, None)
        if client and not client.is_closed:
            try:
                await client.aclose()
            except Exception:
                pass

    async def close(self):
        """关闭所有 HTTP 客户端"""
        keys = list(self._sessions.keys())
        for key in keys:
            await self._cleanup_session(key)
