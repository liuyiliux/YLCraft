"""YLCraft — 微博搜索（Patchright 浏览器路径）。

## 为什么微博必须走浏览器（而不是 httpx）

实测（2026-09-27）全部 HTTP 直连方案都失败：

    httpx 直连搜索 API            → HTTP 432 / ok=-100
    走 visitor 两步换访客 Cookie   → 拿到 SUB/SUBP 仍 ok=-100
    补 _T_WM / MLOGIN / XSRF 等    → 仍 ok=-100
    换桌面 UA / HTTP2 / sec-fetch  → 仍 ok=-100

而在**真实浏览器**里（**未登录**状态）同一 URL 返回：

    {"ok":1, "total":870, "cards":[...9 条微博...]}

根因：`bsk debug` 捕获显示 `from_service_worker = True` ——
**微博注册了 Service Worker**（`m.weibo.cn/`，实测 active），
由它代理请求并注入 httpx 无法复现的上下文。
浏览器 `document.cookie` 里只有 `SUBP/MLOGIN/_T_WM/x-hng/XSRF-TOKEN`，
真正的 `SUB` 是 httpOnly，且 SW 内部还有自己的逻辑。

**所以微博搜索走 Patchright（持久化 profile），在页面上下文里 fetch。**
这与小红书一致（小红书也是浏览器路径），但原因不同：
  · 小红书：需要 **X-s 签名**（`window._webmsxyw`）
  · 微博：需要 **Service Worker 上下文**

## 下载不需要浏览器

实测图片/视频直链用 httpx 就能下（HTTP 200，1.88MB 原图）。
所以只有**搜索/详情**走浏览器。

## 复用

用 `SessionPool` 复用会话（与小红书同一套），
避免每次搜索都冷启动浏览器。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from ...browser.patchright_runtime import get_patchright_runtime
from ..session_pool import PooledSession, SessionPool
from ..types import SearchParams, SearchResult
from .apis import build_search_params
from .client import parse_mblog

logger = logging.getLogger("ylcraft.platforms.weibo.patchright")

# 会话池（跨请求复用浏览器，避免每次冷启动）
_pool = SessionPool(idle_seconds=900)

# 首页（含 Service Worker 注册）——必须先访问，SW 才会接管后续请求
HOME_URL = "https://m.weibo.cn/"

# 在页面上下文里执行搜索。
#
# 关键点：
#   · credentials: 'include' —— 带上同源 Cookie
#   · 用 fetch（不是 XHR）—— 与页面自身一致，走 SW
#   · 返回原始 JSON 字符串（避免 CDP 序列化大对象出问题）
JS_SEARCH = """
async (args) => {
  const p = new URLSearchParams(args.params);
  const r = await fetch('https://m.weibo.cn/api/container/getIndex?' + p,
                        { credentials: 'include' });
  const t = await r.text();
  if (!t || t[0] !== '{') {
    return JSON.stringify({ _error: 'not_json', http: r.status, head: t.slice(0, 120) });
  }
  return t;
}
"""


async def _get_session(conn_key: str) -> PooledSession:
    """取（或新建）一个已打开微博首页的会话。"""
    key = f"weibo:{conn_key or 'default'}"
    session = _pool.get(key)
    if session is None:
        rt = get_patchright_runtime()
        ctx = await rt.new_context(
            headless=False,
            viewport={"width": 1440, "height": 900},
            persistent_platform="weibo",   # 登录态跨会话保留
        )
        page = await ctx.new_page()
        session = PooledSession(ctx=ctx, page=page)
        _pool.put(key, session)
        logger.info("[weibo] 新建浏览器会话 key=%s", key)

    if not session.warmed:
        try:
            await session.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            _pool.drop(key)
            raise RuntimeError(
                f"[weibo] 打开 m.weibo.cn 失败：{type(exc).__name__}。"
                "通常是网络问题或被限流。"
            ) from exc
        # 等 Service Worker 注册完成 + 首页请求发完
        # （实测需要 ~9s；太短会让搜索仍走无 SW 的路径 → ok=-100）
        await session.page.wait_for_timeout(9000)
        session.warmed = True
    session.touch()
    return session


async def search_via_patchright(
    params: SearchParams,
    *,
    conn_key: str = "",
    page: int = 1,
    max_pages: int = 3,
) -> List[SearchResult]:
    """在浏览器里搜微博。

    ## 翻页限制（实测 2026-09-27）

    微博搜索的 `page=1` 正常（约 9 条正文），但 **`page=2` 返回
    173 字节的 HTML 错误页** —— 它的真翻页依赖 `since_id` 游标，
    不是纯 `page`。所以这里默认**只取第 1 页**（约 9-12 条），
    并在日志里说明取不满的原因，而不是假装翻页成功。

    如果 `max_results` 明显大于一页，仍会尝试第 2 页；
    拿不到就停（不报错——第 1 页的数据是有效的）。
    """
    want = max(1, params.max_results or 20)
    # ⚠️ `SearchParams.search_type` 是 **SearchType 枚举**（默认 NOTE），
    # 直接 str() 会得到 "SearchType.NOTE" 而不是 "note"。
    # 这里取 `.value` 再交给 resolve_search_type。
    raw_st = getattr(params, "search_type", "") or "note"
    search_type = str(getattr(raw_st, "value", raw_st))

    session = await _get_session(conn_key)
    out: List[SearchResult] = []
    seen: set[str] = set()

    # 一页约 9 条正文；要更多才去翻第 2 页（实测多半拿不到）
    pages_to_try = 1 if want <= 12 else min(2, max(1, max_pages))

    for i in range(pages_to_try):
        qp = build_search_params(
            keyword=params.keyword,
            page=page + i,
            search_type=search_type,
        )
        try:
            raw = await session.page.evaluate(JS_SEARCH, {"params": qp})
        except Exception as exc:
            logger.warning("[weibo] 搜索页 evaluate 失败（第 %d 页）：%s", page + i, exc)
            break

        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError) as exc:
            logger.warning("[weibo] 搜索响应解析失败：%s", exc)
            break

        # ⚠️ 翻页拿不到有效 JSON 时**不能整体报错**。
        #
        # 实测：`page=1` 返回 173KB 真实数据，`page=2` 返回 173 字节的
        # HTML 错误页（微博的搜索翻页实际依赖 `since_id` 游标，
        # 不是纯 `page`）。此时第 1 页的结果是**有效的**，
        # 直接抛错会让用户连第一页都看不到。
        #
        # 所以在**已有结果**时静默停止翻页；一页都没有才报错。
        if isinstance(data, dict) and data.get("_error"):
            if out:
                logger.info(
                    "[weibo] 第 %d 页无有效数据（%s），已有 %d 条，停止翻页",
                    page + i, data.get("_error"), len(out),
                )
                break
            raise RuntimeError(
                f"[weibo] 搜索返回非 JSON（{data.get('_error')}，HTTP {data.get('http')}）。"
                f"响应开头：{str(data.get('head'))[:80]}。"
                "通常是 Service Worker 未就绪或登录态失效 —— "
                "请到「账号中心」重新保存微博登录态。"
            )

        ok = data.get("ok") if isinstance(data, dict) else None
        if ok == -100:
            raise RuntimeError(
                "[weibo] 未登录（ok=-100）。请在「账号中心」保存微博登录态后重试。"
            )

        cards = ((data.get("data") or {}).get("cards") or []) if isinstance(data, dict) else []
        mblogs = [
            c.get("mblog") for c in cards
            if isinstance(c, dict) and c.get("card_type") == 9 and isinstance(c.get("mblog"), dict)
        ]
        if not mblogs:
            break
        for mb in mblogs:
            parsed = parse_mblog(mb)
            if parsed is None or parsed.id in seen:
                continue
            seen.add(parsed.id)
            out.append(parsed)
        if len(out) >= want:
            break

    logger.info("[weibo] 搜索 %r -> %d 条（patchright）", params.keyword, len(out))
    return out[:want]


async def search_with_runtime(
    client,
    params: SearchParams,
    *,
    conn_id: str = "",
    page: int = 1,
) -> List[SearchResult]:
    """路由统一入口（与小红书同名函数保持一致的调用形状）。"""
    return await search_via_patchright(params, conn_key=conn_id, page=page)


async def close_pool() -> None:
    """关闭会话池（进程退出/测试清理用）。"""
    await _pool.close_all()
