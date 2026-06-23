"""
微信公众号 API 客户端

封装微信公众平台后台 API，包括：
- 扫码登录流程
- 搜索公众号
- 拉取文章列表
- 获取文章内容
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import uuid
from html import unescape
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

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.request(method, url, **kwargs)
                self._update_cookie_from_response(resp)
                return resp
        except httpx.TimeoutException:
            logger.error(f"[WechatMPAPI] 请求超时: {method} {url}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"[WechatMPAPI] HTTP 请求失败: {method} {url} - {e}")
            raise
        except Exception as e:
            logger.error(f"[WechatMPAPI] 请求异常: {method} {url} - {e}")
            raise

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

            ret = data.get("base_resp", {}).get("ret")
            if ret != 0:
                err_msg = data.get("base_resp", {}).get("err_msg", "未知错误")
                logger.warning(f"[WechatMPAPI] 搜索公众号失败: ret={ret}, msg={err_msg}")
                # 会话失效错误，返回明确的错误信息
                if ret == 200003:
                    return {"total": 0, "list": [], "error": "会话已失效，请重新登录微信公众平台", "error_code": ret}
                return {"total": 0, "list": [], "error": err_msg, "error_code": ret}

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

    # ── 全网文章搜索（微信后台版权检测接口）───────────────────────

    @staticmethod
    def _strip_html_fragment(html: str, limit: int = 160) -> str:
        text = re.sub(r"<[^>]+>", "", html or "")
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        return text[:limit]

    @staticmethod
    def _article_id_from_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            biz = qs.get("__biz", [""])[0]
            mid = qs.get("mid", [""])[0]
            idx = qs.get("idx", [""])[0]
            if biz and mid:
                return f"{biz}_{mid}_{idx or '1'}"
        except Exception:
            pass
        return url

    async def search_global_articles(
        self,
        keyword: str,
        begin: int = 0,
        count: int = 10,
    ) -> dict:
        """
        通过微信公众平台编辑器的版权检测接口按关键词搜索全网文章。

        该接口需要已登录的 mp.weixin.qq.com Cookie + token。它不是公开文档接口，
        但返回中包含文章 URL、标题、公众号昵称、封面和正文片段，适合复用现有下载链路。
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return {"total": 0, "list": []}

        begin = max(0, int(begin or 0))
        count = max(1, min(int(count or 10), 10))

        try:
            await self._throttle()
            url = f"{MP_BASE}/cgi-bin/operate_appmsg?sub=check_appmsg_copyright_stat"
            payload = {
                "token": self._token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": "1",
                "fingerprint": uuid.uuid4().hex,
                "random": f"{random.random():.17f}",
                "url": keyword,
                "allow_reprint": "0",
                "begin": str(begin),
                "count": str(count),
            }
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": MP_BASE,
                "Referer": (
                    f"{MP_BASE}/cgi-bin/appmsg"
                    f"?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77"
                    f"&token={self._token}&lang=zh_CN"
                ),
                "X-Requested-With": "XMLHttpRequest",
            }

            resp = await self._request("POST", url, headers=headers, data=payload)
            data = resp.json()

            base_resp = data.get("base_resp") or {}
            ret = base_resp.get("ret")
            if ret != 0:
                err_msg = base_resp.get("err_msg", "未知错误")
                logger.warning(f"[WechatMPAPI] 全网文章搜索失败: ret={ret}, msg={err_msg}")
                if ret == 200003:
                    return {
                        "total": 0,
                        "list": [],
                        "error": "会话已失效，请重新登录微信公众平台",
                        "error_code": ret,
                    }
                return {"total": 0, "list": [], "error": err_msg, "error_code": ret}

            articles = []
            for item in data.get("list", []) or []:
                link = item.get("url", "") or item.get("source_url", "")
                content = item.get("content", "") or ""
                cover = (
                    item.get("cover_url")
                    or item.get("cover_url_235_1")
                    or item.get("cover_url_16_9")
                    or item.get("cover_url_1_1")
                    or ""
                )
                digest = item.get("digest", "") or self._strip_html_fragment(content)
                articles.append({
                    "aid": self._article_id_from_url(link),
                    "title": item.get("title", ""),
                    "link": link,
                    "cover": cover,
                    "digest": digest,
                    "author": item.get("author", ""),
                    "nickname": item.get("nickname", ""),
                    "head_img_url": item.get("head_img_url", ""),
                    "profile_description": item.get("profile_description", ""),
                    "content": content,
                    "source_url": item.get("source_url", ""),
                    "is_pay_subscribe": item.get("is_pay_subscribe", 0),
                    "source_reprint_status": item.get("source_reprint_status", ""),
                    "raw": item,
                })

            return {
                "total": int(data.get("total") or len(articles)),
                "list": articles,
                "open_ad_reprint_status": data.get("open_ad_reprint_status", ""),
            }

        except Exception as e:
            logger.error(f"[WechatMPAPI] 全网文章搜索异常: {e}")
            return {"total": 0, "list": [], "error": str(e)}

    # ── 拉取文章列表 ────────────────────────────────────────────

    # 类级别缓存：cache_key -> (timestamp, result)
    # 注意：缓存按 fake_id + begin 切分（不含 count，避免 count 变化导致翻页缓存失效）
    _articles_cache: dict = {}
    _CACHE_TTL = 1800  # 30 分钟
    _last_request_time: float = 0
    _MIN_INTERVAL = 3  # 最小请求间隔 3 秒

    async def _throttle(self):
        """请求限流：确保两次请求间隔至少 _MIN_INTERVAL 秒"""
        now = time.time()
        elapsed = now - WechatMPAPIClient._last_request_time
        if elapsed < WechatMPAPIClient._MIN_INTERVAL:
            await asyncio.sleep(WechatMPAPIClient._MIN_INTERVAL - elapsed)
        WechatMPAPIClient._last_request_time = time.time()

    @classmethod
    def _cache_cleanup(cls) -> None:
        """清理过期的文章列表缓存，避免长期运行内存泄漏"""
        if not cls._articles_cache:
            return
        now = time.time()
        expired = [k for k, (ts, _) in cls._articles_cache.items() if (now - ts) >= cls._CACHE_TTL]
        for k in expired:
            cls._articles_cache.pop(k, None)
        if expired:
            logger.debug(f"[WechatMPAPI] 清理过期缓存 {len(expired)} 条")

    async def get_articles(
        self,
        fake_id: str,
        begin: int = 0,
        count: int = 5,
        max_retries: int = 3,
    ) -> dict:
        """
        拉取公众号历史文章列表（带缓存 + 限流 + 指数退避重试）

        Args:
            fake_id: 公众号 FakeID
            begin: 起始位置
            count: 每页数量（微信限制最大 5）
            max_retries: 频率限制时的最大重试次数

        Returns:
            { total_count: int, list: [{ title, link, cover, digest, create_time }] }
        """
        # 1. 检查缓存（30 分钟内不重复请求）；key 不含 count，避免翻页缓存失效
        cache_key = f"{fake_id}_{begin}"
        cached = WechatMPAPIClient._articles_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < WechatMPAPIClient._CACHE_TTL:
            logger.info(f"[WechatMPAPI] 使用缓存: {cache_key}")
            return cached[1]

        # 2. 请求限流（最小间隔 3 秒）
        await self._throttle()

        for attempt in range(max_retries + 1):
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

                ret = data.get("base_resp", {}).get("ret")
                if ret != 0:
                    err_msg = data.get("base_resp", {}).get("err_msg", "未知错误")
                    # 频率限制 ret=200013 时自动重试（指数退避 + 随机抖动）
                    if ret == 200013 and attempt < max_retries:
                        # 退避策略：30s、60s、120s... 加 0-10s 随机抖动
                        wait = (30 * (2 ** attempt)) + random.uniform(0, 10)
                        logger.warning(f"[WechatMPAPI] 触发频率限制，{wait:.1f}秒后重试 ({attempt+1}/{max_retries})")
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(f"[WechatMPAPI] 拉取文章列表失败: ret={ret}, msg={err_msg}")
                    return {
                        "total_count": 0,
                        "list": [],
                        "error": err_msg,
                        "error_code": ret,
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

                result = {"total_count": total, "list": articles}
                # 3. 成功时写入缓存（30 分钟内不重复请求）；顺带清理过期条目
                WechatMPAPIClient._cache_cleanup()
                WechatMPAPIClient._articles_cache[cache_key] = (time.time(), result)
                return result

            except Exception as e:
                logger.error(f"[WechatMPAPI] 拉取文章列表异常: {e}")
                return {"total_count": 0, "list": [], "error": str(e)}

        # 所有重试都失败
        return {"total_count": 0, "list": [], "error": "频率限制，已达最大重试次数", "error_code": 200013}

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
