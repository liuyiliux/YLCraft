"""
微信公众号 API 客户端

封装微信公众平台后台 API，包括：
- 扫码登录流程
- 搜索公众号
- 拉取文章列表
- 获取文章内容
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger("ylcraft.wechat_mp.api")

# 微信公众平台 API 基础地址
MP_BASE = "https://mp.weixin.qq.com"

# 默认请求头
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WechatMPAPIClient:
    """
    微信公众平台 API 客户端

    使用 Cookie 保持登录态，调用公众平台后台接口。
    """

    def __init__(self, cookie_str: str = "", token: str = ""):
        self._cookie_str = cookie_str
        self._token = token
        self._fake_id: str = ""

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def cookie(self) -> str:
        return self._cookie_str

    @cookie.setter
    def cookie(self, value: str):
        self._cookie_str = value

    @property
    def token(self) -> str:
        return self._token

    @token.setter
    def token(self, value: str):
        self._token = value

    @property
    def fake_id(self) -> str:
        return self._fake_id

    def _headers(self, extra: dict | None = None) -> dict:
        h = {**_DEFAULT_HEADERS}
        if self._cookie_str:
            h["Cookie"] = self._cookie_str
        if extra:
            h.update(extra)
        return h

    def _parse_cookies_from_response(self, response: httpx.Response) -> dict[str, str]:
        """从响应中提取 Set-Cookie"""
        cookies = {}
        for cookie in response.headers.get_list("set-cookie", ()):
            for part in cookie.split(";"):
                part = part.strip()
                if "=" in part and not part.lower().startswith(("path=", "domain=", "expires=", "max-age=", "secure", "httponly", "samesite")):
                    key, _, val = part.partition("=")
                    cookies[key.strip()] = val.strip()
        return cookies

    def _update_cookie_from_response(self, response: httpx.Response):
        """从响应更新 Cookie"""
        new_cookies = self._parse_cookies_from_response(response)
        if not new_cookies:
            return

        # 合并 Cookie
        existing = {}
        for item in self._cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, _, v = item.partition("=")
                existing[k.strip()] = v.strip()

        existing.update(new_cookies)
        self._cookie_str = "; ".join(f"{k}={v}" for k, v in existing.items())

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """发起 HTTP 请求"""
        kwargs.setdefault("headers", self._headers(kwargs.pop("headers", None)))
        kwargs.setdefault("timeout", 30.0)
        kwargs.setdefault("follow_redirects", True)

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.request(method, url, **kwargs)
            self._update_cookie_from_response(resp)
            return resp

    # ── 登录（已废弃 — 扫码登录请使用 WechatMPQrcodeAdapter）──────────

    async def get_login_qrcode(self) -> dict:
        """
        获取登录二维码

        .. deprecated::
            此方法使用旧版 scanloginqrcode?action=ask 端点，
            该端点在 2024 年公众号切换到 bizlogin 体系后已不可用。
            请使用 app.services.cookies.platforms.wechat_mp.WechatMPQrcodeAdapter
        """
        # 先生成 uuid
        qr_uuid = str(uuid.uuid4())

        # 微信公众平台二维码登录 URL
        qr_url = (
            f"https://mp.weixin.qq.com/cgi-bin/scanloginqrcode"
            f"?action=ask&token=&lang=zh_CN"
        )

        try:
            resp = await self._request("GET", qr_url)
            data = resp.json()
            logger.info(f"[WechatMPAPI] 获取登录二维码: {data}")
            return {
                "qr_url": data.get("qrcode_url", ""),
                "uuid": data.get("uuid", qr_uuid),
            }
        except Exception as e:
            logger.error(f"[WechatMPAPI] 获取二维码失败: {e}")
            # 返回手动构造的二维码 URL（前端用 qrcode.react 渲染）
            return {
                "qr_url": f"{MP_BASE}/cgi-bin/scanloginqrcode?action=ask&token=&lang=zh_CN",
                "uuid": qr_uuid,
            }

    async def check_login_status(self, qr_uuid: str) -> dict:
        """
        轮询登录状态

        .. deprecated::
            此方法使用旧版 scanloginqrcode?action=ask 端点 + ret 判定，
            实际 ret=1 是错误状态而非"等待扫码"。
            请使用 app.services.cookies.platforms.wechat_mp.WechatMPQrcodeAdapter.check_status

        Returns:
            { status: "waiting"|"scanned"|"confirmed"|"expired",
              cookie: str, redirect_url: str, token: str }
        """
        try:
            url = (
                f"{MP_BASE}/cgi-bin/scanloginqrcode"
                f"?action=ask&token=&lang=zh_CN&uuid={qr_uuid}"
            )
            resp = await self._request("GET", url)
            data = resp.json()

            ret = int(data.get("ret", -1))
            if ret == 0:
                # 已确认登录
                redirect_url = data.get("redirect_url", "")
                # 从 redirect_url 提取 token
                token = self._extract_token(redirect_url)
                self._token = token
                return {
                    "status": "confirmed",
                    "cookie": self._cookie_str,
                    "redirect_url": redirect_url,
                    "token": token,
                }
            elif ret == 1:
                return {"status": "waiting"}
            elif ret == 4:
                return {"status": "scanned"}
            elif ret == -2:
                return {"status": "expired"}
            else:
                logger.warning(f"[WechatMPAPI] 未知登录状态: ret={ret}, data={data}")
                return {"status": "waiting"}

        except Exception as e:
            logger.error(f"[WechatMPAPI] 检查登录状态失败: {e}")
            return {"status": "error", "message": str(e)}

    def _extract_token(self, redirect_url: str) -> str:
        """从 redirect_url 提取 token"""
        try:
            parsed = urlparse(redirect_url)
            params = parse_qs(parsed.query)
            return params.get("token", [""])[0]
        except Exception:
            return ""

    # ── 搜索公众号 ──────────────────────────────────────────────

    async def search_accounts(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        搜索公众号

        Returns:
            { total: int, list: [{ fake_id, nickname, alias, round_head_img, service_type }] }
        """
        try:
            url = (
                f"{MP_BASE}/cgi-bin/searchbiz"
                f"?action=search_biz"
                f"&begin={(page - 1) * page_size}"
                f"&count={page_size}"
                f"&query={keyword}"
                f"&token={self._token}"
                f"&lang=zh_CN"
                f"&f=json"
            )
            resp = await self._request("GET", url)
            data = resp.json()

            if data.get("base_resp", {}).get("ret") != 0:
                logger.warning(f"[WechatMPAPI] 搜索公众号失败: {data}")
                return {"total": 0, "list": []}

            total = data.get("total", 0)
            accounts = []
            for item in data.get("list", []):
                accounts.append({
                    "fake_id": item.get("fakeid", ""),
                    "nickname": item.get("nickname", ""),
                    "alias": item.get("alias", ""),
                    "round_head_img": item.get("round_head_img", ""),
                    "service_type": item.get("service_type", 0),
                    "signature": item.get("signature", ""),
                })

            return {"total": total, "list": accounts}

        except Exception as e:
            logger.error(f"[WechatMPAPI] 搜索公众号异常: {e}")
            return {"total": 0, "list": [], "error": str(e)}

    # ── 拉取文章列表 ────────────────────────────────────────────

    async def get_articles(
        self,
        fake_id: str,
        begin: int = 0,
        count: int = 5,
    ) -> dict:
        """
        拉取公众号历史文章列表

        Args:
            fake_id: 公众号 FakeID
            begin: 起始位置
            count: 每页数量（微信限制最大 5）

        Returns:
            { total_count: int, list: [{ title, link, cover, digest, create_time }] }
        """
        try:
            url = (
                f"{MP_BASE}/cgi-bin/appmsg"
                f"?action=list_ex"
                f"&begin={begin}"
                f"&count={count}"
                f"&fakeid={fake_id}"
                f"&type=9"
                f"&token={self._token}"
                f"&lang=zh_CN"
                f"&f=json"
            )
            resp = await self._request("GET", url)
            data = resp.json()

            if data.get("base_resp", {}).get("ret") != 0:
                err_msg = data.get("base_resp", {}).get("err_msg", "未知错误")
                logger.warning(f"[WechatMPAPI] 拉取文章列表失败: ret={data.get('base_resp', {}).get('ret')}, msg={err_msg}")
                return {
                    "total_count": 0,
                    "list": [],
                    "error": err_msg,
                    "error_code": data.get("base_resp", {}).get("ret"),
                }

            total = data.get("app_msg_cnt", 0)
            articles = []
            for item in data.get("app_msg_list", []):
                articles.append({
                    "aid": item.get("aid", ""),
                    "appmsgid": item.get("appmsgid", ""),
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "cover": item.get("cover", ""),
                    "digest": item.get("digest", ""),
                    "create_time": item.get("create_time", 0),
                    "update_time": item.get("update_time", 0),
                    "item_idx": item.get("item_idx", 0),
                    "content_url": item.get("content_url", ""),
                    "source_url": item.get("source_url", ""),
                    "is_pay_subscribe": item.get("is_pay_subscribe", 0),
                })

            return {"total_count": total, "list": articles}

        except Exception as e:
            logger.error(f"[WechatMPAPI] 拉取文章列表异常: {e}")
            return {"total_count": 0, "list": [], "error": str(e)}

    # ── 获取文章内容 ──────────────────────────────────────────────

    async def get_article_content(self, article_url: str) -> dict:
        """
        获取公众号文章 HTML 内容

        Returns:
            { title, content_html, author, publish_time, images[] }
        """
        try:
            resp = await self._request(
                "GET",
                article_url,
                headers=self._headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }),
            )
            html = resp.text

            if not html or len(html) < 500:
                return {"error": "获取文章内容为空或太短", "html": html}

            return {
                "html": html,
                "status_code": resp.status_code,
            }

        except Exception as e:
            logger.error(f"[WechatMPAPI] 获取文章内容异常: {e}")
            return {"error": str(e)}

    # ── 登录态验证 ──────────────────────────────────────────────

    async def verify_login(self) -> dict:
        """
        验证登录态是否有效

        Returns:
            { valid: bool, nickname: str, head_img: str }
        """
        try:
            url = (
                f"{MP_BASE}/cgi-bin/home"
                f"?t=home/index"
                f"&token={self._token}"
                f"&lang=zh_CN"
            )
            resp = await self._request("GET", url)
            text = resp.text

            # 检查是否包含用户信息
            nickname_match = re.search(r'nickname\s*=\s*["\']([^"\']+)["\']', text)
            nickname = nickname_match.group(1) if nickname_match else ""

            if nickname or "logout" in text.lower():
                return {"valid": True, "nickname": nickname}
            else:
                return {"valid": False, "error": "未登录或登录已过期"}

        except Exception as e:
            logger.error(f"[WechatMPAPI] 验证登录失败: {e}")
            return {"valid": False, "error": str(e)}
