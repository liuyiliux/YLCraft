# -*- coding: utf-8 -*-
"""平台客户端 Cookie 头规范化测试（B站 / 小红书）。

回归目标（2026-09-13 线上问题）
--------------------------------
`PlatformConnection.cookie_content` 存的是 **Netscape 文件格式**。部分平台客户端的
`_build_headers` 曾把该原文直接赋给 `Cookie` 头，httpx 抛 `Illegal header value`
（头值不允许换行/制表符），**请求根本发不出去**——表现为"搜索搜不到东西"。

同一代码库里三种状态并存，正是"同一个凭证、多条路径、只有部分做了规范化"的典型：
- **番茄**：`normalize_cookie(self.config.cookie)` —— 一直正确
- **B站**：`headers["Cookie"] = self.config.cookie` —— 曾失败，已修
- **小红书**：同 B站写法 —— 曾失败，已修

注意：测试使用**合成 cookie**（结构与真实一致：`# Netscape HTTP Cookie File` 头 +
制表符分隔字段），**不得**放入任何真实 SESSDATA 等凭证。
"""
from __future__ import annotations

import httpx
import json  # noqa: F401  (下方 JSON 数组用例使用)
import pytest

from app.services.platforms.bilibili.client import BilibiliClient
from app.services.platforms.fanqie.client import FanqieClient
from app.services.platforms.types import ClientConfig, ClientMode
from app.services.platforms.xiaohongshu.client import XiaohongshuClient

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


def _bili(cookie: str) -> BilibiliClient:
    return BilibiliClient(ClientConfig(platform="bili", mode=ClientMode.API, cookie=cookie))


def _xhs(cookie: str) -> XiaohongshuClient:
    return XiaohongshuClient(ClientConfig(platform="xhs", mode=ClientMode.API, cookie=cookie))


def _fanqie(cookie: str) -> FanqieClient:
    return FanqieClient(ClientConfig(platform="fanqie", mode=ClientMode.API, cookie=cookie))


# ---------------------------------------------------------------------------
# 1. 两个平台的规范化行为一致
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory,platform", [(_bili, "bili"), (_xhs, "xhs")])
def test_header_cookie_normalizes_netscape(factory, platform):
    """Netscape 原文必须被转换成 `k=v; ...`，且不含换行/制表符。"""
    cookie = factory(NETSCAPE_COOKIE).header_cookie()

    assert "\n" not in cookie, "%s: Cookie 头里不得有换行" % platform
    assert "\t" not in cookie, "%s: Cookie 头里不得有制表符" % platform
    assert not cookie.startswith("#"), "%s: 不得以 Netscape 注释行开头" % platform
    assert cookie.startswith("SESSDATA=FAKE%2CSESSDATA%2CVALUE;")
    assert "DedeUserID=226082" in cookie
    assert "sid=e5u3hlbv" in cookie


@pytest.mark.parametrize("factory,platform", [(_bili, "bili"), (_xhs, "xhs")])
def test_build_headers_is_httpx_safe(factory, platform):
    """修复前这一步会抛 Illegal header value。"""
    headers = factory(NETSCAPE_COOKIE)._build_headers()

    assert headers["Cookie"].startswith("SESSDATA=")
    httpx.Headers(headers)  # 非法头值会在此失败


@pytest.mark.parametrize("factory,platform", [(_bili, "bili"), (_xhs, "xhs")])
async def test_http_client_initializes_with_netscape_cookie(factory, platform):
    """端到端复现原故障点：`_init_http_client` 曾因原始 Netscape 文本直接失败。"""
    client = factory(NETSCAPE_COOKIE)
    await client._init_http_client()
    try:
        assert client._http_client is not None
        sent = client._http_client.headers["Cookie"]
        assert "\n" not in sent and "\t" not in sent
        assert "DedeUserID=226082" in sent
    finally:
        await client._http_client.aclose()


@pytest.mark.parametrize("factory", [_bili, _xhs])
def test_header_cookie_accepts_already_raw_format(factory):
    """已经是 `k=v; ...` 的输入不得被破坏。"""
    cookie = factory(RAW_COOKIE).header_cookie()
    assert "SESSDATA=abc" in cookie
    assert "DedeUserID=226082" in cookie
    assert "\n" not in cookie


@pytest.mark.parametrize("factory", [_bili, _xhs])
def test_empty_cookie_yields_empty_string(factory):
    client = factory("")
    assert client.header_cookie() == ""
    assert "Cookie" not in client._build_headers()


# ---------------------------------------------------------------------------
# 2. B站独有：Cookie 提取（Netscape 是制表符分隔，`DedeUserID=` 匹配不到原文）
# ---------------------------------------------------------------------------


def test_bili_extract_user_id_from_netscape_cookie():
    """修复前对 Netscape 原文匹配 `DedeUserID=` 恒为 0，导致关注列表等空返回。"""
    assert _bili(NETSCAPE_COOKIE)._extract_user_id_from_cookie() == 226082


def test_bili_extract_user_id_from_raw_cookie():
    assert _bili(RAW_COOKIE)._extract_user_id_from_cookie() == 226082


def test_bili_extract_user_id_absent_returns_zero():
    assert _bili("sessionid=abc")._extract_user_id_from_cookie() == 0


# ---------------------------------------------------------------------------
# 3. 结构性保证：Cookie 规范化收在公共基类，单个平台写错也会被纠正
# ---------------------------------------------------------------------------


class _NaughtyClient(BilibiliClient):
    """故意把 Netscape 原文直接写进 Cookie 头（历史真实写法）。"""

    def _build_headers(self):  # type: ignore[override]
        return {"Cookie": self.config.cookie, "User-Agent": "x"}


async def test_base_class_corrects_illegal_cookie_from_subclass():
    """关键保证：子类即便写回原文，`_init_http_client` 也会统一覆盖为规范格式。

    这是把该逻辑收进公共层的意义——**单个平台不再可能靠自己写错而弄坏请求**。
    """
    client = _NaughtyClient(ClientConfig(platform="bili", mode=ClientMode.API, cookie=NETSCAPE_COOKIE))
    await client._init_http_client()
    try:
        sent = client._http_client.headers["Cookie"]
        assert "\n" not in sent and "\t" not in sent, "基类未纠正子类写入的非法 Cookie"
        assert sent.startswith("SESSDATA=")
        # 行为对调用方完全透明：非法头已被替换，httpx 不会再抛错
        httpx.Headers(dict(client._http_client.headers))
    finally:
        await client._http_client.aclose()


async def test_base_class_drops_cookie_when_absent():
    """无 cookie 时不得残留 Cookie 头（否则平台会认为是空凭证）。"""
    client = _NaughtyClient(ClientConfig(platform="bili", mode=ClientMode.API, cookie=""))
    await client._init_http_client()
    try:
        assert "Cookie" not in client._http_client.headers
    finally:
        await client._http_client.aclose()


# ---------------------------------------------------------------------------
# 4. 三平台共用基类实现，fanqie 的本地版本对齐到公共实现
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory,platform", [(_bili, "bili"), (_xhs, "xhs"), (_fanqie, "fanqie")])
async def test_all_platforms_share_base_cookie_normalization(factory, platform):
    """三个平台的 API 模式最终都应由基类产出同一个合法 Cookie 头。"""
    client = factory(NETSCAPE_COOKIE)
    await client._init_http_client()
    try:
        sent = client._http_client.headers["Cookie"]
        assert sent == "SESSDATA=FAKE%2CSESSDATA%2CVALUE; bili_jct=FAKEJCT0123456789; " \
                       "DedeUserID=226082; DedeUserID__ckMd5=FAKEMD5; sid=e5u3hlbv", platform
    finally:
        await client._http_client.aclose()


def test_fanqie_normalize_matches_cookie_manager_including_json():
    """fanqie.utils.normalize_cookie 已对齐到公共 CookieManager.extract_raw。

    对 Netscape / raw / 空三种输入与原实现输出一致；**JSON 数组输入**原实现会原样返回
    （导致整段 JSON 被塞进 Cookie 头），对齐后转为正确的 header 格式。
    """
    from app.services.cookies.manager import CookieManager
    from app.services.platforms.fanqie.utils import normalize_cookie as fanqie_normalize

    mgr = CookieManager()
    json_cookies = json.dumps([{"name": "sessionid", "value": "abc123"},
                               {"name": "csrf", "value": "def456"}])

    for label, val in (("netscape", "# Netscape HTTP Cookie File\n"
                                    "fanqienovel.com\tFALSE\t/\tFALSE\t0\tsessionid\tabc123\n"),
                       ("raw", " a=1 ; b=2 "),
                       ("empty", ""),
                       ("json", json_cookies)):
        assert fanqie_normalize(val) == (mgr.extract_raw(val) or ""), label

    # JSON 数组必须被真正解析，而不是原样返回
    assert fanqie_normalize(json_cookies) == "sessionid=abc123; csrf=def456"
