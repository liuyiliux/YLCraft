"""
YLCraft — B站平台适配器

登录检测 + 账号信息提取 + 二维码登录
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import qrcode
import httpx

from app.services.cookies.base import PlatformDetector, QrcodeAdapter

logger = logging.getLogger("ylcraft.bilibili.qrcode")

# B站二维码登录 API
BILI_QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
BILI_QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
BILI_NAV = "https://api.bilibili.com/x/web-interface/nav"

# B站 API 通用请求头（绕过 412 校验）
BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


class BilibiliDetector(PlatformDetector):
    """B站登录检测"""

    async def detect(self, page) -> bool:
        """检测用户是否已登录B站"""
        try:
            # B站登录后右上角出现用户头像
            avatar = await page.query_selector(".header-avatar-wrap, .bili-avatar")
            if avatar:
                return True
            # 检测用户名
            user_el = await page.query_selector(".header-user-name, .user-con")
            if user_el:
                return True
        except Exception:
            pass
        return False

    async def extract_account_info(self, page) -> dict:
        """提取B站账号信息"""
        info = {
            "account_id": None,
            "account_name": None,
            "account_avatar": None,
            "account_url": None,
        }
        try:
            name_el = await page.query_selector(".header-user-name, .user-con .name")
            if name_el:
                info["account_name"] = await name_el.inner_text()
        except Exception:
            pass
        return info


class BilibiliQrcodeAdapter(QrcodeAdapter):
    """
    B站二维码登录适配器

    流程：
    1. generate_qrcode → 调用 B站接口获取二维码 URL + qrcode_key
    2. check_status(qrcode_key) → 轮询扫码状态
       - 86101: 等待扫码
       - 86090: 已扫码，等待确认
       - 0: 登录成功，返回 Cookie
       - 86038: 二维码过期
    """

    _http: Optional[httpx.AsyncClient] = None

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10.0, headers=BILI_HEADERS)
        return self._http

    async def generate_qrcode(self) -> dict:
        """
        生成 B站登录二维码

        Returns:
            {
                "qr_image_base64": "data:image/png;base64,...",
                "session_key": "<qrcode_key>",
                "expires_in": 120,
            }
        """
        try:
            client = self._get_http()
            resp = await client.get(BILI_QR_GENERATE)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"B站二维码生成失败: {data.get('message', 'unknown')}")

            qr_data = data["data"]
            url = qr_data["url"]
            qrcode_key = qr_data["qrcode_key"]

            # 生成二维码图片
            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            logger.info(f"[BilibiliQrcode] QR generated, key={qrcode_key[:8]}...")

            return {
                "qr_image_base64": f"data:image/png;base64,{img_b64}",
                "session_key": qrcode_key,
                "expires_in": 120,
            }

        except Exception as e:
            logger.error(f"[BilibiliQrcode] generate_qrcode failed: {e}")
            raise

    async def check_status(self, session_key: str) -> dict:
        """
        轮询 B站扫码状态

        Args:
            session_key: qrcode_key

        Returns:
            {
                "status": "waiting" | "scanned" | "confirmed" | "expired",
                "cookies": [...],  # confirmed 时返回
                "account_info": {...},
            }
        """
        try:
            client = self._get_http()
            resp = await client.get(BILI_QR_POLL, params={"qrcode_key": session_key})
            resp.raise_for_status()
            data = resp.json()

            code = data.get("data", {}).get("code", -1)
            message = data.get("data", {}).get("message", "")

            logger.debug(f"[BilibiliQrcode] poll code={code}, msg={message}")

            # 86101: 等待扫码
            if code == 86101:
                return {"status": "waiting"}

            # 86090: 已扫码，等待确认
            if code == 86090:
                return {"status": "scanned"}

            # 86038: 二维码过期
            if code == 86038:
                return {"status": "expired"}

            # 0: 登录成功
            if code == 0:
                # B站 poll 接口在 code=0 时返回: data.url / data.refresh_token / data.timestamp
                # Cookie 在响应头的 Set-Cookie 中，httpx client.cookies 会自动收集
                bili_data = data.get("data", {})
                url_info = bili_data.get("url", "")

                # 1. 从 httpx cookie jar 提取 Cookie（这才是真正的登录凭证）
                cookies_array = []
                if self._http:
                    for cookie in self._http.cookies.jar:
                        cookies_array.append({
                            "name": cookie.name,
                            "value": cookie.value,
                            "domain": cookie.domain or ".bilibili.com",
                            "path": cookie.path or "/",
                            "expires": cookie.expires or -1,
                            "secure": cookie.secure,
                            "httpOnly": False,
                        })

                # 2. 尝试从 URL 提取 mid
                mid_from_url = self._extract_mid_from_url(url_info)

                # 3. 调用 nav 接口获取准确的账号信息（需要 Cookie）
                account_info = {
                    "account_id": mid_from_url,
                    "account_name": "",
                    "account_avatar": "",
                    "account_url": f"https://space.bilibili.com/{mid_from_url}" if mid_from_url else "",
                }

                if cookies_array:
                    try:
                        nav_resp = await client.get(BILI_NAV)
                        nav_data = nav_resp.json()
                        if nav_data.get("code") == 0:
                            nav = nav_data.get("data", {})
                            mid = str(nav.get("mid", ""))
                            uname = nav.get("uname", "")
                            face = nav.get("face", "")
                            if mid:
                                account_info["account_id"] = mid
                                account_info["account_url"] = f"https://space.bilibili.com/{mid}"
                            if uname:
                                account_info["account_name"] = uname
                            if face:
                                account_info["account_avatar"] = face
                    except Exception as nav_err:
                        logger.warning(f"[BilibiliQrcode] nav query failed: {nav_err}")

                logger.info(f"[BilibiliQrcode] Login success: {account_info.get('account_name')} ({account_info.get('account_id')}), cookies={len(cookies_array)}")

                return {
                    "status": "confirmed",
                    "cookies": cookies_array,
                    "account_info": account_info,
                }

            # 其他未知错误
            return {
                "status": "expired",
                "error": f"code={code}, msg={message}",
            }

        except Exception as e:
            logger.error(f"[BilibiliQrcode] check_status failed: {e}")
            return {"status": "waiting", "error": str(e)}

    @staticmethod
    def _extract_mid_from_url(url: str) -> str:
        """从跳转 URL 中提取 mid"""
        import re
        match = re.search(r"mid[=:](%?\d+)", url)
        if match:
            return match.group(1).lstrip("%")
        return ""

    @staticmethod
    def _normalize_cookies(raw_cookies: list) -> list[dict]:
        """
        将 B站返回的 Cookie 列表标准化为通用格式

        B站返回格式: [{"name": "SESSDATA", "value": "xxx", "expires": ..., "domain": ...}, ...]
        标准格式: [{"name": ..., "value": ..., "domain": ..., "path": ..., "expires": ..., "secure": ...}]
        """
        result = []
        for c in raw_cookies:
            result.append({
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ".bilibili.com"),
                "path": c.get("path", "/"),
                "expires": c.get("expires", -1),
                "secure": c.get("secure", True),
                "httpOnly": c.get("httpOnly", False),
            })
        return result

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http:
            await self._http.aclose()
            self._http = None
