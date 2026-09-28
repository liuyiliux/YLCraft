"""YLCraft — 生成 X 的 `x-client-transaction-id` 请求头。

## 为什么需要它

这是之前把 404 误判成"queryId 失效"的真正原因 ——
**缺这个头，SearchTimeline 一律返回 404**（实测）。

    twscrape/queue_client.py:
        # if code 404 on first try then generate new
        # x-client-transaction-id and retry
    Scweet/transaction.py:
        "A request without the x-client-transaction-id header answers 404."

## 怎么生成（2026-09-28 实测跑通）

X 把生成算法放在 JS bundle 里，需要三步：

    1. 抓 `https://x.com/tesla` 页面
    2. 从 HTML 里找出 JS bundle，下载并解析出
       `(vk_bytes, anim_key)` —— 复用 twscrape `xclid.load_keys()`
    3. `XClIdGen(vk_bytes, anim_key).calc("GET", path)`

## ⚠️ 为什么不用 twscrape 自带的 `XClIdGen.create()`

它内部用**动态 UA**（`user-agent: "@chrome"`，由 fake-useragent 生成），
实测在本机直接报 `ConnectError`（疑似卡在拉取 UA 列表那一步）。

但**用固定 UA 手工抓页面是通的**（HTTP 200, 304KB），
所以这里自己走上面三步，只借用 twscrape 的 `load_keys` / `XClIdGen`
（纯计算部分，不涉及它的网络层）。

## 缓存

生成需要下载 + 解析 JS bundle（实测数秒），所以按 profile 缓存。
X 会轮换 bundle，所以遇到 404 时要**重新生成**（见 `invalidate()`）。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("ylcraft.platforms.twitter.xclid")

# 固定 UA（不用动态 UA —— 见模块 docstring）
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

# 缓存（进程内）。键是 cookie 指纹，值是 (gen, 生成时间)
_CACHE: Dict[str, tuple[Any, float]] = {}
_CACHE_TTL = 1800.0   # 30 分钟


class TransactionIdError(RuntimeError):
    """生成 transaction-id 失败。

    这是**可操作**的错误：说明抓 bundle 或解析失败，
    需要用浏览器路径兜底（或稍后重试）。
    """


def _cookie_fingerprint(auth_token: str) -> str:
    """只取 auth_token 的尾部做指纹（避免把凭证写进日志/缓存键）。"""
    return f"at:{auth_token[-8:]}" if auth_token else "anon"


def _cookie_map(header: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in (header or "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


async def _load_keys_via_http(
    source_url: str,
    cookie_header: str,
    cookies: Dict[str, str],
) -> tuple:
    """抓页面 + 解析 JS bundle，返回 `(vk_bytes, anim_key)`。"""
    from twscrape import xclid

    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        resp = await c.get(
            source_url,
            headers={"user-agent": UA, "cookie": cookie_header},
        )
    if resp.status_code != 200:
        raise TransactionIdError(
            f"抓取 {source_url} 失败（HTTP {resp.status_code}）。"
            "transaction-id 需要这个页面里的 JS bundle。"
        )

    soup = BeautifulSoup(resp.text, "html.parser")

    # 复用 twscrape 的解析（纯计算），但用我们自己的 httpx client
    client = httpx.AsyncClient(
        timeout=40, follow_redirects=True, headers={"user-agent": UA}
    )
    try:
        for name, value in cookies.items():
            client.cookies.set(name, value, domain=".x.com")
        vk_bytes, anim_key = await xclid.load_keys(soup, client)
    finally:
        await client.aclose()
    return vk_bytes, anim_key


async def get_generator(
    cookie_header: str,
    *,
    source_url: str = "https://x.com/tesla",
    force_refresh: bool = False,
):
    """取得（或新建）transaction-id 生成器。

    同一个 cookie 会复用缓存（生成一次要几秒）。
    """
    from twscrape import xclid

    cookies = _cookie_map(cookie_header)
    key = _cookie_fingerprint(cookies.get("auth_token", ""))

    now = time.time()
    if not force_refresh:
        cached = _CACHE.get(key)
        if cached and (now - cached[1]) < _CACHE_TTL:
            return cached[0]

    t0 = time.time()
    try:
        vk_bytes, anim_key = await _load_keys_via_http(source_url, cookie_header, cookies)
        gen = xclid.XClIdGen(vk_bytes, anim_key)
    except TransactionIdError:
        raise
    except Exception as exc:
        raise TransactionIdError(
            f"生成 transaction-id 失败：{type(exc).__name__}: {str(exc)[:160]}。"
            "X 会轮换 JS bundle，稍后重试或改用浏览器路径。"
        ) from exc

    logger.info("[xclid] 生成器就绪（%.1fs）", time.time() - t0)
    _CACHE[key] = (gen, now)
    return gen


async def make_transaction_id(
    cookie_header: str,
    method: str,
    path: str,
    *,
    source_url: str = "https://x.com/tesla",
    force_refresh: bool = False,
) -> str:
    """生成一次性的 `x-client-transaction-id`。

    ⚠️ 每次请求都要重新生成（X 会校验时效）。
    """
    gen = await get_generator(
        cookie_header, source_url=source_url, force_refresh=force_refresh
    )
    return gen.calc(method.upper(), path)


def invalidate(cookie_header: str) -> None:
    """清掉缓存 —— 遇到 404 时调用，下次会重新抓 bundle。"""
    cookies = _cookie_map(cookie_header)
    key = _cookie_fingerprint(cookies.get("auth_token", ""))
    _CACHE.pop(key, None)
    logger.info("[xclid] 已清除缓存（下次重新抓 bundle）")


def clear_all() -> None:
    _CACHE.clear()
