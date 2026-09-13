# -*- coding: utf-8 -*-
"""B站 Cookie 头规范化测试。

回归目标（2026-09-13 线上问题）
--------------------------------
`PlatformConnection.cookie_content` 存的是 **Netscape 文件格式**。`BilibiliClient._build_headers`
此前把该原文直接赋给 `Cookie` 头，httpx 抛 `Illegal header value`（头值不允许换行/制表符），
表现为"B站搜索搜不到东西"，而账号检测仍可用（那条路径已先经 `CookieManager.extract_raw`）。

本测试固定该行为，避免再次回归。

注意：测试使用**合成 cookie**（结构与真实一致：`# Netscape HTTP Cookie File` 头 + 制表符
分隔字段），**不得**放入任何真实 SESSDATA / bili_jct 等凭证。
"""
from __future__ import annotations

import httpx

from app.services.platforms.bilibili.client import BilibiliClient
from app.services.platforms.types import ClientConfig, ClientMode

# 合成 Netscape cookie（字段名与真实一致，值全为占位）
NETSCAPE_COOKIE = (
    "# Netscape HTTP Cookie File\n"
    "\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1796029674\tSESSDATA\tFAKE%2CSESSDATA%2CVALUE\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1796029674\tbili_jct\tFAKEJCT0123456789\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1796029674\tDedeUserID\t226082\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1796029674\tDedeUserID__ckMd5\tFAKEMD5\n"
    ".bilibili.com\tTRUE\t/\tTRUE\t1796029674\tsid\te5u3hlbv"
)

RAW_COOKIE = "SESSDATA=abc; bili_jct=def; DedeUserID=226082; sid=xyz"


def _client(cookie: str) -> BilibiliClient:
    return BilibiliClient(ClientConfig(platform="bili", mode=ClientMode.API, cookie=cookie))


# ---------------------------------------------------------------------------
# 1. 规范化本身
# ---------------------------------------------------------------------------


def test_header_cookie_normalizes_netscape_to_header_safe_string():
    """Netscape 原文必须被转换成 `k=v; k2=v2`，且不含换行/制表符。"""
    cookie = _client(NETSCAPE_COOKIE)._header_cookie()

    assert "\n" not in cookie, "Cookie 头里不得有换行"
    assert "\t" not in cookie, "Cookie 头里不得有制表符"
    assert not cookie.startswith("#"), "不得以 Netscape 注释行开头"
    assert cookie.startswith("SESSDATA=FAKE%2CSESSDATA%2CVALUE;")
    assert "bili_jct=FAKEJCT0123456789" in cookie
    assert "DedeUserID=226082" in cookie
    assert "sid=e5u3hlbv" in cookie


def test_header_cookie_accepts_already_raw_format():
    """已经是 `k=v; ...` 的输入不得被破坏。"""
    cookie = _client(RAW_COOKIE)._header_cookie()
    assert "SESSDATA=abc" in cookie
    assert "DedeUserID=226082" in cookie
    assert "\n" not in cookie


def test_header_cookie_is_cached():
    """重复取用不应重复解析（同一次请求链路会多次读取）。"""
    client = _client(NETSCAPE_COOKIE)
    first = client._header_cookie()
    assert client._header_cookie_cache == first
    assert client._header_cookie() is first


def test_empty_cookie_yields_empty_string():
    assert _client("")._header_cookie() == ""


# ---------------------------------------------------------------------------
# 2. 头本身必须被 httpx 接受（原故障点）
# ---------------------------------------------------------------------------


def test_build_headers_is_httpx_safe():
    """修复前这一步会抛 Illegal header value。"""
    headers = _client(NETSCAPE_COOKIE)._build_headers()

    assert headers["Cookie"].startswith("SESSDATA=")
    # httpx 在构造 Headers 时校验头值合法性——非法值会在此失败
    httpx.Headers(headers)


async def test_http_client_initializes_with_netscape_cookie():
    """端到端复现原故障点：`_init_http_client` 曾因原始 Netscape 文本直接失败。"""
    client = _client(NETSCAPE_COOKIE)
    await client._init_http_client()  # 修复前：httpx.LocalProtocolError / Illegal header value
    try:
        assert client._http_client is not None
        sent = client._http_client.headers["Cookie"]
        assert "\n" not in sent and "\t" not in sent
        assert "DedeUserID=226082" in sent
    finally:
        await client._http_client.aclose()


# ---------------------------------------------------------------------------
# 3. Cookie 提取（同族隐患：Netscape 是制表符分隔，`DedeUserID=` 匹配不到原文）
# ---------------------------------------------------------------------------


def test_extract_user_id_from_netscape_cookie():
    """修复前对 Netscape 原文匹配 `DedeUserID=` 恒为 0，导致关注列表等空返回。"""
    assert _client(NETSCAPE_COOKIE)._extract_user_id_from_cookie() == 226082


def test_extract_user_id_from_raw_cookie():
    assert _client(RAW_COOKIE)._extract_user_id_from_cookie() == 226082


def test_extract_user_id_absent_returns_zero():
    assert _client("sessionid=abc")._extract_user_id_from_cookie() == 0
