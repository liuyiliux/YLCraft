"""快手客户端（搜索 / 搜博主）。

## 为什么用「浏览器抓签名 + 复用」

快手的接口签名 `__NS_hxfalcon` **拿不到纯 Python 实现**：

  · 签名库是混淆 JS（`kws-10-0.0.1-obfuscated.*.js`）
  · `window` 上**没有**可调用的签名函数（被打包进闭包）
  · 无签名 → `{"result":50,"error_msg":"签名验证失败"}`
    （实测：只带 `kww` 头也不行；`kww` 只是 cookie 里 `kwfv1` 的转发）

**但实测发现签名可以复用**：

    ① 浏览器打开一次搜索页 → 页面自己发请求 → 拦截到带签名的 URL
    ② 在**同一页面上下文**里复用该 URL + 换关键词 → 成功

    实测：旅行 19 条 / 宠物 19 条 / 健身 20 条；翻页 pcursor 0→1→2 正常

**签名与关键词无关**（会话级），所以抓一次能用很久。

## 会话管理

签名 + 页面上下文都缓存在模块级（按 conn_id 分），
复用同一个浏览器会话 —— 和 `weibo/search_patchright.py` 的思路一致：
**无头**运行（不弹窗），有头只在登录流程里用。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from ..base import BasePlatformClient, register_platform
from ..session_pool import PooledSession, get_session_pool
from ..types import SearchParams, SearchResult, UserProfile
from .apis import (
    BASE,
    PROFILE_GET,
    _to_int,
    SEARCH_FEED,
    SEARCH_USER,
    build_feed_body,
    build_user_body,
    parse_feed,
    parse_user,
    search_page_url,
)

logger = logging.getLogger("ylcraft.platforms.kuaishou")

# 会话池 key（与 base 的格式一致：**竖线**分隔）
_POOL_KEY_FMT = "kuaishou|{conn}"

# 签名缓存：conn_id -> signed_url（**不含**关键词，可复用）
_signed_urls: Dict[str, str] = {}
# 每个 conn 一把锁，避免并发重复抓签名
_locks: Dict[str, asyncio.Lock] = {}


def _lock_for(conn: str) -> asyncio.Lock:
    if conn not in _locks:
        _locks[conn] = asyncio.Lock()
    return _locks[conn]


# 在页面上下文里 POST（由**页面**发起，签名已在 URL 上）
_JS_POST = """
async (args) => {
  try {
    const r = await fetch(args.url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(args.body),
    });
    const t = await r.text();
    return JSON.stringify({ status: r.status, body: t });
  } catch (e) {
    return JSON.stringify({ _error: String(e).slice(0, 120) });
  }
}
"""


@register_platform("kuaishou")
@register_platform("ks")
class KuaishouClient(BasePlatformClient):
    """快手客户端。

    ⚠️ 签名要从浏览器抓 —— 所以**必须有 Playwright 会话**，
    纯 HTTP 模式做不到（见模块 docstring）。
    """

    async def _ensure_signed_url(self, uri: str = SEARCH_FEED) -> Optional[str]:
        """拿到**指定路径**的带签名 URL（有缓存）。

        ## ⚠️ 签名是**按路径绑定**的（2026-09-30 实测）

        同一页面会发出**多个不同路径**的带签名请求，每个的签名都不同：

            /rest/v/profile/get     HUDR_…PT3TMP-sk0…
            /rest/v/search/feed     HUDR_…PTnTMP-sk0…      ← 第 26 位就不同
            /rest/v/search/user     HUDR_…PTXTMP-sk0…

        **用 A 路径的签名去调 B 路径 → `{"result":2}`**。

        我因此踩过两个坑：
          · 测试时误用 `profile/get` 的签名调 `search/feed` → 全 `result:2`
          · 客户端里用 `signed.replace(SEARCH_FEED, uri)` 换路径
            —— **路径换了签名没换** → 必然失败（`search_users` 就是坏的）

        所以现在**按页面实际发出的请求，逐路径抓并缓存**。
        """
        conn = self.config.conn_id or "-"
        cache_key = f"{conn}:{uri}"
        if _signed_urls.get(cache_key):
            return _signed_urls[cache_key]

        async with _lock_for(conn):
            # 双重检查（等锁期间别人可能已抓好）
            if _signed_urls.get(cache_key):
                return _signed_urls[cache_key]

            session = await self._get_session()
            if session is None:
                return None

            # **按路径**收集（一个页面会发好几个）
            captured: Dict[str, str] = {}

            def on_request(req):
                # ⚠️ 事件回调里**任何异常都会被 Playwright 吞掉**，
                # 表现成"抓不到签名"但看不到原因（实测踩过：
                # 少 `import re` → `NameError` 被吞 → 误判成"页面没发请求"）。
                # 所以这里自己兜住并记日志。
                try:
                    u = req.url
                    if "__NS_hxfalcon=" not in u:
                        return
                    m = re.search(r"/rest/v/[^?]+", u)
                    if m:
                        captured.setdefault(m.group(0), u)
                except Exception as exc:
                    logger.warning("[kuaishou] 解析请求 URL 失败：%s: %s",
                                   type(exc).__name__, exc)

            page = session.page
            page.on("request", on_request)
            try:
                # 打开搜索页 → 页面自己会发多个带签名的请求
                await page.goto(
                    search_page_url("美食"),
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_timeout(11000)
            except Exception as exc:
                logger.warning("[kuaishou] 打开搜索页失败：%s", type(exc).__name__)
            finally:
                try:
                    page.remove_listener("request", on_request)
                except Exception:
                    pass

            if not captured:
                logger.warning(
                    "[kuaishou] 未抓到签名。常见原因：\n"
                    "  · 浏览器会话**没有登录态**（未登录时页面不发带签名的请求）\n"
                    "  · 页面结构变了\n"
                    "请在「账号中心」确认快手登录态可用。",
                )
                return None

            # **全部路径都缓存**（一次页面加载能抓好几个）
            for path, url in captured.items():
                _signed_urls[f"{conn}:{path}"] = url
            logger.info(
                "[kuaishou] 抓到 %d 个路径的签名：%s",
                len(captured), ", ".join(sorted(captured)),
            )
            return _signed_urls.get(cache_key)

    async def _get_session(self) -> Optional[PooledSession]:
        """取（或新建）一个快手浏览器会话（**无头**）。

        与 `base._init_patchright` 用**同一个 key 格式**（竖线分隔），
        两条路共用会话 —— 这是微博那边踩过的坑（key 不一致导致
        各建各的、上下文打架）。
        """
        conn = self.config.conn_id or "-"
        key = _POOL_KEY_FMT.format(conn=conn)
        pool = get_session_pool()
        existing = pool.get(key)
        if existing is not None:
            return existing

        # 复用 base 已建好的会话（它有注入过 cookie 的上下文）
        page = getattr(self, "_patchright_page", None)
        if page is not None:
            sess = PooledSession(ctx=getattr(self, "_patchright_context", None), page=page)
            sess.borrowed = True
            if sess.alive():
                return sess

        from ...browser.patchright_runtime import get_patchright_runtime

        rt = get_patchright_runtime()
        ctx = await rt.new_context(
            headless=True,                       # 无头：不弹窗
            viewport={"width": 1440, "height": 900},
            persistent_platform="kuaishou",
        )
        # ⚠️ **必须显式注入 cookie**（2026-09-30 修）
        #
        # 原来不注入，只靠持久化 profile —— 而实测那个 profile 里
        # **没有登录态**（`userId=None`），于是：
        #
        #   · 搜索页拿不到签名（未登录时页面不发那个带签名的请求）
        #   · 表现成"抓不到签名"或 `result:2`
        #
        # **我一度误判成"快手限流"** —— 直到注入 cookie 后
        # 立刻抓到 3 个带签名的请求、`userId=5372574395` 恢复。
        #
        # 这与微博那次是**同一个坑**：`base._init_patchright`
        # 会注入 cookie，而平台自己的 `_get_session` 不注入 →
        # 两条路行为不一致。
        await self._inject_cookies(ctx)

        page2 = await ctx.new_page()
        sess = PooledSession(ctx=ctx, page=page2)
        pool.put(key, sess)
        return sess

    async def _inject_cookies(self, ctx) -> None:
        """把 `self.config.cookie` 注入浏览器上下文。

        快手需要的 cookie（实测）：
          · `userId`                      —— 登录标志
          · `kuaishou.server.webday7_st`  —— 会话令牌
          · `did` / `kpn` / `kwssectoken` —— 设备与安全

        失败只告警不中断（公开页面仍可看，但**搜索会拿不到签名**）。
        """
        cookie = self.config.cookie or ""
        if not cookie:
            logger.warning(
                "[kuaishou] 没有 cookie —— 未登录时页面不会发带签名的请求，"
                "搜索会失败。请在「账号中心」获取快手登录态。",
            )
            return

        # ⚠️ **必须按原始域注入，不能全塞到 `.kuaishou.com`**（2026-09-30 修）
        #
        # 实测存库 cookie 的域分布：
        #
        #     www.kuaishou.com    kuaishou.server.webday7_st ← **会话令牌在这！**
        #     .www.kuaishou.com   clientid / kpf / kpn
        #     .kuaishou.com       did / kwfv1 / userId / kwssectoken
        #     id.kuaishou.com     passToken / userId
        #
        # 原来一律塞到 `.kuaishou.com` —— 后果实测：
        #
        #     userId 在 ✅、webday7_st 也在（但域变了）
        #     页面 UI 依然显示"登录即可享受…立即登录"
        #     /rest/v/profile/get 依然 {"result":2}
        #
        # 即**会话令牌的域不匹配 → 页面 JS 不认这个登录态**。
        #
        # `self.config.cookie` 是 `k=v; k2=v2` 形式（已经丢了域信息），
        # 所以这里按**实测的域归属**还原 —— 同名 cookie 在不同域是
        # 不同的 cookie，不能合并。
        #
        # 判据（实测得出，按 cookie 名分组）：
        _DOMAIN_OF = {
            # 会话令牌只在 `www.kuaishou.com`（不带点）
            "kuaishou.server.webday7_st": "www.kuaishou.com",
            "kuaishou.server.webday7_ph": "www.kuaishou.com",
            "ktrace-context": "www.kuaishou.com",
            # id 域
            "passToken": "id.kuaishou.com",
        }
        _WILDCARD = (".kuaishou.com", ".www.kuaishou.com")

        items = []
        for part in cookie.split("; "):
            if "=" not in part:
                continue
            k, _, v = part.partition("=")
            if not k:
                continue
            dom = _DOMAIN_OF.get(k)
            if dom:
                items.append({"name": k, "value": v, "domain": dom, "path": "/"})
            else:
                for d in _WILDCARD:
                    items.append({"name": k, "value": v, "domain": d, "path": "/"})
        if not items:
            return
        try:
            await ctx.add_cookies(items)
            names = {i["name"] for i in items}
            logger.info(
                "[kuaishou] 已注入 %d 个 cookie（userId=%s, webday7_st=%s）",
                len(items),
                "有" if "userId" in names else "**无**",
                "有" if "kuaishou.server.webday7_st" in names else "**无**",
            )
        except Exception as exc:
            logger.warning("[kuaishou] 注入 cookie 失败：%s", type(exc).__name__)

    async def _post(self, uri: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """在页面上下文里 POST（用**该路径自己的**签名）。

        ⚠️ **签名绑路径** —— 不能用 `search/feed` 的签名去调别的路径
        （实测会返回 `{"result":2}`）。见 `_ensure_signed_url` 的说明。
        """
        signed = await self._ensure_signed_url(uri)
        if not signed:
            raise RuntimeError(
                f"[kuaishou] 未能获取 {uri} 的接口签名。\n"
                "可能原因：\n"
                "  1. 浏览器会话**没有登录态** —— 请在「账号中心」"
                "重新获取快手登录态（未登录时页面不发带签名的请求）\n"
                "  2. 该路径当前页面不会主动请求（快手前端可能改了调用方式）\n"
                "  3. 页面结构变化，签名机制升级"
            )

        session = await self._get_session()
        if session is None:
            raise RuntimeError("[kuaishou] 没有可用的浏览器会话")

        raw = await session.page.evaluate(_JS_POST, {"url": signed, "body": body})
        import json as _json

        data = _json.loads(raw) if isinstance(raw, str) else (raw or {})
        if data.get("_error"):
            logger.warning("[kuaishou] 请求失败：%s", data["_error"])
            return None
        try:
            payload = _json.loads(data.get("body") or "{}")
        except Exception:
            return None
        result = payload.get("result")
        if result != 1:
            logger.warning(
                "[kuaishou] %s 返回 result=%s err=%s",
                uri, result, payload.get("error_msg"),
            )
            return None
        return payload

    # =========================================================================
    # 搜索
    # =========================================================================

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """搜索作品。

        ⚠️ `pcursor` 翻页 —— `params.page` 换算：第 N 页要**顺序翻过去**
        （游标式，没有页码参数）。这里只翻到目标页。
        """
        want = max(1, int(params.max_results or 10))
        page_no = max(1, int(getattr(params, "page", 1) or 1))

        out: List[SearchResult] = []
        seen: set[str] = set()
        pcursor = ""

        # 每页约 20 条；翻到目标页需要跳 page_no-1 次
        for idx in range(page_no + 2):
            payload = await self._post(SEARCH_FEED, build_feed_body(params.keyword, pcursor))
            if payload is None:
                break
            if idx < page_no - 1:
                # 还没到目标页 —— 只推进游标
                pcursor = str(payload.get("pcursor") or "")
                if not pcursor:
                    return []
                continue

            feeds = payload.get("feeds") or []
            for feed in feeds:
                parsed = parse_feed(feed)
                if parsed is None or parsed["id"] in seen:
                    continue
                seen.add(parsed["id"])
                out.append(self._to_result(parsed))

            # ⚠️ **先记下游标，再决定要不要继续**（2026-09-30 修）
            #
            # 原来把读游标写在 `break` **之后** —— 于是"本页拿满 want"
            # 直接 break 时游标没记，`_has_more` 恒为 False：
            #
            #     page=1  10条  has_more=**False**   ← 其实还有更多！
            #     page=2  10条  has_more=True
            #
            # 用户看到第 1 页没有「下一页」按钮。
            next_cursor = str(payload.get("pcursor") or "")

            if len(out) >= want:
                # 拿够了 —— 但要知道"还有没有下一页"
                pcursor = next_cursor
                break
            if not next_cursor or next_cursor == pcursor:
                pcursor = ""
                break
            pcursor = next_cursor

        results = out[:want]
        # ⚠️ **给前端 `_has_more`**（有游标就说明还有更多）
        if results:
            results[0].raw_data["_has_more"] = bool(pcursor)
        logger.info("[kuaishou] 搜索 %r -> %d 条", params.keyword, len(results))
        return results

    @staticmethod
    def _to_result(p: Dict[str, Any]) -> SearchResult:
        return SearchResult(
            id=p["id"],
            title=p["title"][:80] or p["id"],
            desc=p["desc"],
            author=p["author"],
            author_id=p["author_id"],
            cover=p["cover"],
            url=p["url"],
            platform="kuaishou",
            type=p["type"],
            likes=p["likes"],
            comments=p["comments"],
            collects=p["collects"],
            views=p["views"],
            duration=p["duration"],
            raw_data={
                **p["raw"],
                # 前端详情播放/下载读这两个（与别的平台字段名统一）
                "_video_url": p["video_url"],
                "_images": [],
                "tags": p["tags"],
            },
        )

    # =========================================================================
    # 搜博主
    # =========================================================================

    async def search_users(self, keyword: str, max_results: int = 20) -> List[UserProfile]:
        """搜用户。

        ⚠️ 签名**绑路径** —— 从 `/search/feed` 换到 `/search/user` 时
        要重新构造 URL（实测签名串能换路径用，但保险起见这里重抓一次）。
        """
        want = max(1, max_results)
        out: List[UserProfile] = []
        seen: set[str] = set()
        pcursor = ""
        for _ in range(3):
            payload = await self._post(
                SEARCH_USER, build_user_body(keyword, pcursor)
            )
            if payload is None:
                break
            users = payload.get("users") or []
            for u in users:
                p = parse_user(u)
                if p is None or (p["id"] and p["id"] in seen):
                    continue
                if p["id"]:
                    seen.add(p["id"])
                out.append(
                    UserProfile(
                        id=p["id"],
                        name=p["name"],
                        avatar=p["avatar"],
                        platform="kuaishou",
                        followers=p["followers"],
                        desc=p["desc"],
                        verified=p["verified"],
                        raw_data=p["raw"],
                    )
                )
                if len(out) >= want:
                    return out
            nxt = str(payload.get("pcursor") or "")
            if not nxt or nxt == pcursor:
                break
            pcursor = nxt
        return out[:want]

    async def get_self_profile(self) -> Optional[UserProfile]:
        """查**自己**的资料（「我的数据」）。

        ## 接口（实测打通，2026-09-30）

            GET /rest/v/profile/get?__NS_hxfalcon=<该路径自己的签名>

        ## ⚠️ 响应字段是**扁平的**，不是嵌套的！

        实测返回（登录态有效时）：

            {
              "result": 1,
              "userName": "逸流AI",
              "userId": 5372574395,
              "userHead": "https://p66.a.kwimgs.com/uhead/...",
              "fans": 20,
              "follows": 2,          ← 注意是 `follows`，不是 `following`
              "like": 312,           ← 获赞
              "sex": "M",
              "mobile": "131****1644",
              "eid": "3xdefy9fk9fcadc",
              "userTex": "",
              "userDefineId": "5372574395"
            }

        **我第一版按 `data.user` 嵌套解析 → 拿到空**（字段名也对不上）。
        所以这里**直接读顶层**。

        ## 两个前提

          1. **必须有有效登录态** —— 否则 `result=2`
          2. 签名是**该路径专属**的（不能用 `search/feed` 的签名）
        """
        payload = await self._post(PROFILE_GET, {})
        if payload is None:
            return None

        # ⚠️ 字段在**顶层**（实测），不是 `data.user`
        uid = str(payload.get("userId") or payload.get("userDefineId") or "")
        name = str(payload.get("userName") or "")
        if not uid and not name:
            logger.info(
                "[kuaishou] profile/get 字段与预期不符，顶层键：%s",
                sorted(payload.keys())[:14],
            )
            return None

        return UserProfile(
            id=uid,
            name=name,
            avatar=str(payload.get("userHead") or ""),
            platform="kuaishou",
            followers=_to_int(payload.get("fans")),
            # ⚠️ 快手叫 `follows`（关注数），不是 `following`
            following=_to_int(payload.get("follows")),
            total_likes=_to_int(payload.get("like")),
            desc=str(payload.get("userTex") or ""),
            raw_data=payload,
        )

    async def get_detail(self, item_id: str):
        """详情：搜索结果里已含全部字段，这里**不重新请求**（返回 None）。"""
        return None

    # =========================================================================
    # 抽象方法（base 要求）
    # =========================================================================

    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    def _build_headers(self) -> Dict[str, str]:
        """请求头。

        ⚠️ 实测真实请求需要的头（抓包确认）：

            content-type: application/json
            kww: <cookie 里的 kwfv1>
            referer: https://www.kuaishou.com/search/video?searchKey=<编码关键词>

        但**光有这些不够** —— 真正的签名 `__NS_hxfalcon` 在 URL 上，
        纯 HTTP 拿不到（见模块 docstring）。所以这里返回的头
        主要用于**浏览器上下文里的 fetch**（cookie 由 credentials 带）。
        """
        return {
            "User-Agent": self.config.user_agent or self.UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/",
        }

    def _get_default_user_agent(self) -> str:
        return self.UA

    def _get_platform_domain(self) -> str:
        """cookie 域 —— `netscape_to_header` 要认识这个名字。

        ⚠️ 实测 `netscape_to_header(raw, "kuaishou")` 能返回内容
        （与 `"xhs"` 那种返回 0 字符的情况不同）。
        """
        return ".kuaishou.com"
