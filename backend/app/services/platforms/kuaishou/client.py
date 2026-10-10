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
from ..types import (
    # ⚠️ 必须导入 —— `get_detail` 要用它们（见该方法的 docstring）
    ContentNotFoundError,
    LoginExpiredError,
    NetworkError,
    NoteDetail,
    RiskControlError,
    SearchParams,
    SearchResult,
    UserProfile,
)
from .apis import (
    BASE,
    COMMENT_LIST,
    COMMENT_SUB_LIST,
    PROFILE_GET,
    _parse_cn_count,
    _to_int,
    SEARCH_FEED,
    SEARCH_USER,
    PROFILE_FEED,
    build_feed_body,
    build_profile_feed_body,
    build_user_body,
    parse_feed,
    parse_user,
    search_page_url,
)

logger = logging.getLogger("ylcraft.platforms.kuaishou")

# 会话池 key（与 base 的格式一致：**竖线**分隔）
_POOL_KEY_FMT = "kuaishou|{conn}"

# 签名缓存：`{conn}:{path}` -> signed_url
#
# ⚠️ key 必须含**路径** —— 签名是**按路径绑定**的（实测：
# 同一页面 3 个路径 3 个不同签名，第 26 位就不同）。
_signed_urls: Dict[str, str] = {}
# 自己的 uid 缓存（抓 `profile/feed` 签名时要去自己的主页）
_self_uid_cache: Dict[str, str] = {}
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

    def _pages_for(self, uri: str, uid: str = "") -> List[str]:
        """返回**会发出该路径请求**的页面 URL（按优先级）。

        实测（2026-09-30 抓包）：

            搜索页 `/search/video?searchKey=…`
                → /rest/v/search/feed, /rest/v/search/user, /rest/v/profile/get
            用户主页 `/profile/{uid}`
                → /rest/v/profile/feed          ← **只有这里才有**
                → /rest/v/profile/get           ← **带目标 uid 的统计**（2026-10-07）

        ## ⚠️ 2026-10-07：查**别人**资料必须去**他的**主页

        抓包实测 `GET /rest/v/profile/get?__NS_hxfalcon=…`：
          · **请求体是空的**（`{}`，userId 不在 body 里）
          · 用户 id 在**页面 URL** 上 —— 打开 `/profile/{uid}` 才发这个请求
          · 打开**自己**主页时也会发这个请求（body 同样是空的），
            所以以前只查到了「我自己」，一直以为查不了别人。

        ⇒ 传了 `uid` 就去那个人的主页抓签名，别用自己主页的。

        所以抓 `profile/feed` 的签名必须去用户主页。
        没有 uid 时先取自己的（`profile/get` 能拿到）。
        """
        # ⚠️ 指定了目标用户 → 必须去**他的**主页，否则抓到的签名对应的是自己
        if uid:
            return [f"{BASE}/profile/{uid}"]
        if uri == PROFILE_FEED:
            own = _self_uid_cache.get(self.config.conn_id or "-")
            if own:
                return [f"{BASE}/profile/{own}", search_page_url("美食")]
            # 还不知道 uid → 先去搜索页（那里会带 profile/get，能拿 uid）
            return [search_page_url("美食")]
        return [search_page_url("美食")]

    async def _ensure_signed_url(
        self, uri: str = SEARCH_FEED, uid: str = "",
    ) -> Optional[str]:
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
        # ⚠️⚠️ 2026-10-07 修：缓存键**不加 uid**。
        #
        # 我上一版加 uid 是为了"区分不同用户的签名"，但那是个**想当然**的
        # 设计 —— 快手签名是**会话级**的（同一 cookie 下签一次能通用），
        # 而且 `_pages_for` 本来就会带着 uid 去打开那个人的主页。
        #
        # 更要命的是：加了 uid 之后**存和取的键不一致**，直接导致线上 bug ——
        #     存： _signed_urls[f"{conn}:{path}"]        ← 不带 uid
        #     取： _signed_urls.get(cache_key)            ← 带 uid
        # 现象是日志上一行刚打印"抓到 2 个路径的签名"，
        # 下一行就抛"未能获取 /rest/v/profile/get 的接口签名"，自相矛盾。
        #
        # ⇒ 统一用不带 uid 的键。签名本就是会话级的，不需要按用户区分。
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

            # ⚠️ **打开页面前，先把浏览器里的新鲜 cookie 读回来**（2026-09-30）
            #
            # ## 为什么（调研结论）
            #
            # 快手**没有 refresh 接口** —— `kuaishou.server.webday7_st`
            # 是 248 字节密文 protobuf，TTL 由**服务端**控制，
            # 客户端无法延长（全网开源项目零实现：
            # MediaCrawler 的 `login.py` 只有登录、没有保活）。
            #
            # 但调研给出了一条**被验证过**的路：
            #
            #   > 核心不是"续期 cookie"，而是**让浏览器替你续期** ——
            #   > 只要浏览器处于登录态，快手自己会刷新 `webday7_st`
            #   > （`/rest/v/profile/*` 的响应会带 `Set-Cookie` 下发新值），
            #   > 你只需**定期重读** `browser_context.cookies()`。
            #
            # 所以这里：**每次取数前重读一次浏览器 cookie**，
            # 把「浏览器已续期」的新值拿回来用。
            #
            # ⚠️ 用户选的是**不常驻**方案：平时不占着窗口，
            # 只在取数前重读 —— 拿不到新的就继续用旧的（不中断）。
            await self._refresh_cookies_from_browser(session)

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
                # ## ⚠️ 要打开**会请求该路径**的页面（2026-09-30 修）
                #
                # 实测每个路径由不同页面发出：
                #
                #     搜索页    → /rest/v/search/feed, /search/user, /profile/get
                #     用户主页  → /rest/v/profile/feed        ← 只有这里才有！
                #
                # 所以只打开搜索页时，`profile/feed` 的签名**永远抓不到**。
                for url in self._pages_for(uri, uid):
                    if uri in captured:
                        break
                    try:
                        await page.goto(url, wait_until="domcontentloaded",
                                        timeout=60000)
                        await page.wait_for_timeout(11000)
                    except Exception as exc:
                        logger.warning("[kuaishou] 打开 %s 失败：%s",
                                       url[:60], type(exc).__name__)
            finally:
                try:
                    page.remove_listener("request", on_request)
                except Exception:
                    pass

            if not captured:
                # ⚠️⚠️ 2026-10-10 更正措辞：以前写"未登录时页面不发带签名的
                # 请求"，把它说成了**快手的限制**。实测不准确：
                # 未登录的浏览器**同样会发**带 `__NS_hxfalcon` 的请求
                # （另一份独立实测 + 本项目自己的抓包都见过）。
                # ⇒ 更可能是**这个会话的 cookie 已过期**，页面退化成不带签名
                #   的匿名形态（此时接口会回 result=109/2）。
                logger.warning(
                    "[kuaishou] 未抓到签名。最可能的原因：\n"
                    "  · **本会话的登录态已过期**（约 6~20 分钟就失效）——\n"
                    "    注意这不是快手要求登录：它的资料/搜索数据对游客是公开的，\n"
                    "    是我们取签名的方式依赖登录态，过期了就抓不到。\n"
                    "  · 该路径当前页面不主动请求（快手改了调用方式）\n"
                    "  · 页面结构变化\n"
                    "请到「账号中心」重新扫码获取快手登录态。",
                )
                return None

            # **全部路径都缓存**（一次页面加载能抓好几个）
            for path, url in captured.items():
                _signed_urls[f"{conn}:{path}"] = url
            logger.info(
                "[kuaishou] 抓到 %d 个路径的签名：%s",
                len(captured), ", ".join(sorted(captured)),
            )
            # ⚠️ 存与取必须同键（都用不带 uid 的 `conn:uri`）——
            #   见上面 cache_key 的说明，这里曾经因为键不一致导致
            #   "刚抓到签名却说没抓到"。
            got = _signed_urls.get(cache_key)
            if not got:
                logger.warning(
                    "[kuaishou] 抓到签名但 %s 不在其中（已有：%s）",
                    uri, ", ".join(sorted(captured)),
                )
            return got

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

    async def _refresh_cookies_from_browser(self, session) -> None:
        """把浏览器里的**新鲜** cookie 读回来（快手自己会刷新会话）。

        ## 为什么这么做（调研结论，2026-09-30）

        快手**没有 refresh 接口** —— `kuaishou.server.webday7_st` 是
        248 字节密文 protobuf，TTL 由**服务端**控制，客户端无法延长。

        全网开源项目零实现：
          · MediaCrawler（★66k）的 `login.py` **只有登录、没有保活**
          · `cv-cat/KuaiShou-Spider` 也只透传、不重建
            （其 `auth.py` 注释明说 passToken "intentionally not" 重建）

        但调研给出了一条**被验证过**的路：

        > 核心不是"续期 cookie"，而是**让浏览器替你续期** ——
        > 只要浏览器处于登录态，快手自己会刷新 `webday7_st`
        > （`/rest/v/profile/*` 响应会带 `Set-Cookie`），
        > 你只需**定期重读** `browser_context.cookies()`。

        ## 用户选的方案：**不常驻**

        平时不占着窗口，只在取数前重读一次：
          · 读到新的 → 更新 `self.config.cookie`（后续请求用新的）
          · 读不到/没变化 → **继续用旧的**（不中断）

        ## ⚠️ 实测：快手有**两组** TTL 完全不同的 cookie（2026-09-30）

            会话凭证  kuaishou.server.webday7_st   域 www.kuaishou.com
                     名字带 day7，但**实测约 20 分钟**就失效
            风控凭证  kwscode / kwssectoken         域 .kuaishou.com
                     **实测 TTL 约 5 分 49 秒**（官方 SDK 在浏览器端本地续期）
            设备凭证  did / kwfv1                    实测也会过期（我截获过已过期的 did）
                     kwfv1 就是请求头 `kww` 的来源

        只要其中**任何一个**过期，请求就会失败 ——
        所以我一度看到"截图能登录、我测试就拿不到"这种诡异现象：
        其实是 `did`/`kwfv1` 已过期，而 `userId`/`webday7_st` 还在，
        看起来像"登录态时好时坏"。

        所以重读要**覆盖全部**，不能只挑登录相关的。

        ## ⚠️ 不要丢掉域信息

        实测 cookie 分属 4 个域（`www.` / `.www.` / `.` / `id.`）——
        MediaCrawler 的 `login_by_cookies` 把它们**全压成 `.kuaishou.com`**
        （丢了域），我们**不学那个做法**。
        """
        try:
            # 读**多个** URL 以覆盖 4 个域（Playwright 会返回所有匹配该 URL 的 cookie）
            merged: Dict[str, str] = {}
            for url in (
                "https://www.kuaishou.com/",
                "https://id.kuaishou.com/",
            ):
                for c in await session.ctx.cookies(url):
                    name = c.get("name")
                    val = c.get("value")
                    if name and val is not None:
                        merged[name] = val
            cookies = [{"name": k, "value": v} for k, v in merged.items()]
        except Exception as exc:
            logger.debug("[kuaishou] 重读 cookie 失败（继续用旧的）：%s",
                         type(exc).__name__)
            return

        if not cookies:
            return

        # 只关心主站相关的域（避免把无关 cookie 混进来）
        parts = []
        for c in cookies:
            name = c.get("name")
            val = c.get("value")
            if name and val is not None:
                parts.append(f"{name}={val}")
        if not parts:
            return

        fresh = "; ".join(parts)
        old = self.config.cookie or ""
        if fresh != old:
            self.config.cookie = fresh
            # 如实报告几组关键凭证的状态（排查"登录态时好时坏"很有用）
            has_login = "userId=" in fresh
            # 6 分钟 TTL 那组（风控凭证）
            has_kws = "kwscode=" in fresh and "kwssectoken=" in fresh
            logger.info(
                "[kuaishou] 已从浏览器重读 cookie（%d 字段，userId=%s, "
                "kwscode+kwssectoken=%s）",
                len(parts), "有" if has_login else "**无**",
                "有" if has_kws else "**无**",
            )
            # ⚠️⚠️ 2026-10-07：`kwscode`/`kwssectoken` 缺失是**登录态失效的
            # 决定性信号**，而原来的报错只说"未抓到签名"，把原因藏起来了。
            #
            # 实测经过：cookie 里 userId **还在**（所以看起来"有登录态"），
            # 但 kwscode/kwssectoken 已无 —— 这两个是签名所需的**风控凭证**，
            # 6 分钟 TTL（服务端控制）。缺失时页面**根本不发**带签名的请求，
            # 于是上层报"未能获取签名"，用户完全不知道是登录态过期了。
            #
            # ⇒ 直接说清是登录态问题，别让它伪装成"页面结构变了"
            #   （后者会让排查方向跑偏 —— 我这次就差点去查快手前端改版）。
            if not has_kws:
                logger.warning(
                    "[kuaishou] ⚠️ 浏览器 cookie 里 **没有 kwscode/kwssectoken**"
                    " ⇒ 登录态已失效（这组风控凭证 TTL 约 6 分钟，服务端控制）。\n"
                    "   后续必然抓不到签名（未登录时快手页面不发带签名请求）。\n"
                    "   请到「账号中心」重新扫码获取快手登录态。"
                )

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

    async def _post(
        self, uri: str, body: Dict[str, Any], uid: str = "",
    ) -> Optional[Dict[str, Any]]:
        """在页面上下文里 POST（用**该路径自己的**签名）。

        ⚠️ **签名绑路径** —— 不能用 `search/feed` 的签名去调别的路径
        （实测会返回 `{"result":2}`）。见 `_ensure_signed_url` 的说明。

        ⚠️ `uid`：2026-10-07 新增。查**别人**资料/作品时，签名必须在
        **那个人自己的主页**上抓（`profile/feed` 只在目标主页发出）。

        ## ⚠️ 为什么这里依赖登录态（**不是快手要求**）

        快手的资料/搜索数据对**游客开放**，但**签名**要靠
        "打开带登录态的页面 → 抓它发出的带签名请求"。
        登录态一过期，页面不再发带签名请求 ⇒ 签名抓不到 ⇒
        **本该公开的数据也用不了**。

        ⇒ 这是**我们取数方式的局限**，不是平台限制。
        根治方向：让签名抓取不依赖登录态（待实测验证）。
        """
        signed = await self._ensure_signed_url(uri, uid=uid)
        if not signed:
            # ⚠️ **这里必须是 `LoginExpiredError`，不能是裸 `RuntimeError`**（2026-10-01 修）
            #
            # 实测（快手 cookie 过期后搜索）：
            #
            #     [kuaishou] 未能获取 /rest/v/search/feed 的接口签名
            #     → HTTP 500 "搜索失败: ..."
            #
            # **两处都错**：
            #   ① 异常类型不对 —— 是 `RuntimeError`，API 层的
            #      `except LoginExpiredError` 抓不到，落到最后的 `except Exception`
            #   ② 于是映射成 **500**（服务端故障），而真相是**登录态过期**，
            #      该让用户去「账号中心」重新登录（应该是 **401**）
            #
            # 而本函数自己的文档就写着"可能原因 1：浏览器会话没有登录态" ——
            # 也就是说**首选原因就是登录失效**，异常类型却表达不出来。
            # 同理 `CrawlerService._search_via_platforms` 里那组
            # 关键词匹配（461/403/风控…）也**不含**这条报错文本，
            # 会把它吞成 `return []` → 用户看到"找到 0 条结果"。
            #
            # 用**类型**表达语义，不靠上层猜关键词。
            #
            # ⚠️ 2026-10-07：**先说最可能的原因**。
            # 原来把"没有登录态"和"页面结构变了"并列成 1/2/3，
            # 用户看到的是一大段可能性 —— 而实测**绝大多数就是登录态过期**
            # （浏览器 cookie 里 kwscode/kwssectoken 已消失）。
            # 并列陈述会让人以为是快手改版，排查方向直接跑偏。
            has_kws = ("kwscode=" in (self.config.cookie or "")
                       and "kwssectoken=" in (self.config.cookie or ""))
            likely = (
                "【最可能：本会话登录态已过期】浏览器 cookie 里没有 "
                "kwscode/kwssectoken（风控凭证，TTL 约 6 分钟）。\n"
                "   → 请到「账号中心」**重新扫码获取快手登录态**。\n"
                "   ⚠️ 这**不代表快手要求登录**（资料/搜索数据对游客公开），\n"
                "      是我们抓签名的方式依赖登录态。\n"
                if not has_kws else
                "【可能是登录态问题】请到「账号中心」重新获取快手登录态。\n"
            )
            raise LoginExpiredError(
                f"[kuaishou] 未能获取 {uri} 的接口签名。\n"
                f"{likely}\n"
                "若重新登录后仍报此错，才是下面这些原因：\n"
                "  · 该路径当前页面不会主动请求（快手前端改了调用方式）\n"
                "  · 页面结构变化，签名机制升级\n\n"
                "⚠️ 快手登录态很短命（服务端控制，实测约 6~20 分钟就失效，"
                "无法延长），所以用过一阵就搜不到是**正常现象**，重新扫码即可。"
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
            # ⚠️ **快手登录态很短命**（实测：扫码后约 20 分钟失效）
            #
            # 实测的错误码迁移：
            #
            #     1   → 正常
            #     109 → 中间态（约 20 分钟后出现）
            #     2   → 未登录（再等几分钟）
            #
            # ⚠️⚠️ **"搜索不需要登录"是错的**（2026-10-07 核实并更正）
            #
            # 这条注释/文案以前写的是"快手的搜索不需要登录（公开数据），
            # 所以『搜索能用』不等于『登录态有效』"—— **说反了**。
            #
            # 实测：`search/feed` 的签名来自**页面抓包**，而未登录时
            # 快手页面**根本不发**带签名的请求 ⇒ 搜索**同样需要登录态**。
            #
            # 那为什么以前"失效了还能搜"？因为 `2238c96d` 之前，
            # 搜索路径对非 1 的 result **静默 `return None`**
            # → `search()` 里 `if payload is None: break`
            # → 空列表 → API 包装成 **200 "找到 0 条结果"**。
            # 用户看到的是"这个关键词没内容"，而不是"登录态没了"。
            #
            # ⇒ **"失效时还能用"是假象**，是失败被藏起来了。
            #    `2238c96d` 已经把它改成 401（这是对的，别改回去）。
            #
            # ⚠️⚠️ 2026-10-10 **再次更正**：下面那句"全部需要登录态"**又错了**
            #
            # 快手的**资料数据对游客开放**（另一份独立实测报告 + INIT_STATE
            # 明文 fan/like/follow/photo_public 均可拿到）。
            # ⇒ 真正需要登录的是**签名**，而我们取签名的方式是"打开带登录态的
            #   页面抓带签名请求"—— 登录态一过期，**连签名都抓不到**，
            #   于是**本该公开的数据也跟着用不了**。
            # 这才是"用过一阵就搜不到"的真正原因（不是平台要求登录）。
            #
            # ⇒ 文案不能说"平台要求登录"，要说"我们的取数依赖登录态"。
            hint = {
                2: "登录态已失效（快手会话较短命，实测约 6~20 分钟）",
                109: "登录态异常（快手的中间态，通常接着会变成未登录）",
            }.get(result, "接口返回异常")
            logger.warning(
                "[kuaishou] %s 返回 result=%s err=%s —— %s",
                uri, result, payload.get("error_msg"), hint,
            )
            if uri in (PROFILE_GET, PROFILE_FEED):
                # ⚠️ 用 `LoginExpiredError` —— API 层会映射成 **401**
                # （不是 500）。语义是"需要重新登录"，用户可以自己解决。
                raise LoginExpiredError(
                    f"[kuaishou] {hint}（result={result}）。\n"
                    "⚠️ 这**不代表快手要求登录**——它的资料/搜索数据对游客是开放的。\n"
                    "   是我们的取数方式**依赖登录态**（签名靠打开带登录态的页面抓），\n"
                    "   登录态一过期就抓不到签名，于是公开数据也用不了。\n"
                    "请在「账号中心」重新获取快手登录态（扫码）后重试。"
                )
            # ⚠️ 搜索路径**不能** `return None`（2026-10-02 修）
            #
            # 原来这里返回 None → `search()` 里 `if payload is None: break`
            # → 返回空列表 → API 层报 **200 "找到 0 条结果"**。
            #
            # 实测（快手登录态失效后搜索关键词）：
            #
            #     HTTP 200  {"success":true,"results":[],"message":"找到 0 条结果"}
            #
            # 用户完全看不出是"登录态过期"，只会以为这个关键词没内容，
            # 于是反复换关键词 —— 而真正的原因（result=2/109）被吞掉了。
            #
            # 讽刺的是**本函数上面的注释已经把这个道理写清楚了**
            #（"所以这里给可操作的错误，别让它静默变空白"），
            # 却只对 profile 路径兑现了，搜索路径照样 `return None`。
            #
            # `result` 已经在上面算出来了，直接用它给出可操作的错误。
            raise LoginExpiredError(
                f"[kuaishou] 搜索失败：{hint}（result={result}）。\n"
                "请在「账号中心」重新获取快手登录态（扫码）后重试。\n"
                "⚠️ 快手登录态**约 20 分钟**失效（服务端控制），"
                "建议搜索前重新读一次 cookie。"
            )
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
                # ⚠️ `_post` 只在**翻页中途**才会返回 None：第一页就拿不到
                # 的话，`_post` 内部已经按 result 码抛出 `LoginExpiredError`
                # 了（2026-10-02 修），走不到这里。
                #
                # 走到这里 = 已经拿到过至少一页，只是在翻页途中断了。
                # 此时**不能静默 break**：第 1 页有结果、第 2 页断了的话，
                # 用户看到的是"只有 10 条"，而真相是分页中途失败。
                # 已积累的结果要保留，但必须把失败说清楚。
                if out:
                    logger.warning(
                        "[kuaishou] 翻页途中失败（第 %d 页），已保留 %d 条结果",
                        idx + 1, len(out),
                    )
                    break
                raise NetworkError(
                    "[kuaishou] 搜索请求未返回数据（页面脚本执行失败或无响应）。\n"
                    "这通常意味着浏览器会话已断开或页面结构变化，"
                    "不是「关键词没有内容」。"
                )
            if idx < page_no - 1:
                # 还没到目标页 —— 只推进游标
                pcursor = str(payload.get("pcursor") or "")
                if not pcursor:
                    # 到目标页之前游标就断了 —— 后面根本没有数据。
                    # 属于**明确的分页边界**，不是错误。
                    return out[:want]
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
                        # ⚠️ 2026-10-07 补传（原来只传 followers）。
                        # 实测快手 /search/user **压根不返回这些数字**
                        # （真实字段只有 headurl/isFollowing/livingInfo/
                        #  user_id/user_name/user_text/verified），
                        # 所以这里仍是 0 —— 前端据 raw 里的
                        # stats_available=False 显示「接口不提供」而非 0。
                        following=p.get("following", 0),
                        total_videos=p.get("total_videos", 0),
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

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """取**别人**的资料（博主中心点「查看」时用）。

        ## 数据来源：**GraphQL**，不是 REST（2026-10-07 实测）

        参考开源项目 MediaCrawler（`media_platform/kuaishou/graphql/vision_profile.graphql`），
        实测确认快手博主资料走 GraphQL：

            POST https://www.kuaishou.com/graphql
            {
              "query": "query{ visionProfile(userId:\\"<uid>\\"){ result "
                       "userProfile{ ownerCount{ fan photo follow } } } }"
            }

        **字段实测结论**（GraphQL 的 `Did you mean` 报错是免费的字段字典）：
            · 参数名只能 `userId`
            · 计数字段嵌在 **`ownerCount`** 对象里（类型 `VisionUserProfileOwnerCount`）
            · 真实字段只有 `fan` / `photo` / `follow`
              ⇒ **没有「获赞」** —— 我猜的 `likedCount` 之类**全不存在**。
                页面上那个「获赞 5.5万」来自别的通道，GraphQL 这条路给不了。

        ## 为什么走浏览器上下文

        GraphQL **不需要 `__NS_hxfalcon` 签名**，但要 `credentials: include`
        （带浏览器自己的 cookie）。未登录时实测返回
        `{"result":2,"userProfile":null}` ⇒ 必须用**已登录**的会话。

        ⇒ 复用已有的 `_JS_POST`（在页面上下文里 fetch），只是 URL 换成
          `/graphql`、body 换成 GraphQL 查询。签名机制完全不需要。

        ## ⚠️ 我连错三次（详见 `apis.parse_user` 的注释）
        """
        return await self._get_user_profile_impl(user_id)

    async def get_comments_page(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取**一页**快手评论，带回游标。

        ⚠️ 快手分页是 **`pcursor` 游标不是页码**，
        且**终值是字符串 `"no_more"`**（实测）—— 必须透出去，
        否则前端"加载更多"会拿到重复数据。
        """
        photo_id = str(item_id or "").strip()
        if not photo_id:
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        headers = {
            "User-Agent": self._get_default_user_agent(),
            "Content-Type": "application/json",
            "Referer": f"{BASE}/short-video/{photo_id}",
        }
        cookie = self.header_cookie()
        if cookie:
            headers["Cookie"] = cookie

        try:
            payload = await self.request(
                "POST",
                f"{BASE}{COMMENT_LIST}",
                json={"photoId": photo_id, "pcursor": cursor or ""},
                headers=headers,
            )
        except Exception as exc:
            # ⚠️ **不能吞成空列表**（2026-10-02 修）
            #
            # 原来这里是 `except Exception: return {"comments": []}` ——
            # 于是"网络抖动 / 登录过期 / 风控"三种完全不同的情况，
            # 全都变成 `success:true, "返回 0 条评论"`。
            # 用户读到的是"这条视频没有评论"，真相是请求失败了。
            #
            # 违反仓库铁律：**未实现/未取到 ≠ 没有**。
            # 同文件的 `search` 路径（`get_self_profile` 等）早就
            # 正确抛 `LoginExpiredError` 了 —— 这正是
            # "守卫只加在一个入口"的老坑，这次轮到评论路径。
            logger.warning("[kuaishou] 评论请求失败：%s", exc)
            if isinstance(exc, (LoginExpiredError, RiskControlError)):
                raise
            # 网络类异常可重试 → 用统一的 NetworkError 表达
            raise NetworkError(
                f"[kuaishou] 评论请求失败：{type(exc).__name__}: {str(exc)[:120]}"
            ) from exc

        if not isinstance(payload, dict) or payload.get("result") != 1:
            # ⚠️ `result != 1` 是**快手的服务端拒绝**，不是"没有评论"
            # （实测：登录态失效时返回 `{"result": 2}`）。
            # 原来也返回空列表，同样会让用户误以为"没评论"。
            result_code = payload.get("result") if isinstance(payload, dict) else "?"
            logger.info("[kuaishou] 评论被拒：result=%s", result_code)
            raise LoginExpiredError(
                f"[kuaishou] 评论接口返回 result={result_code}（请求被拒）。\n"
                "⚠️ 这不是「这条视频没有评论」—— 是**登录态失效或被风控**。\n"
                "快手的登录态**约 20 分钟**就失效（服务端控制，无法延长），"
                "请在「账号中心」重新获取快手登录态后重试。"
            )

        out: List[Dict[str, Any]] = []
        for c in payload.get("rootCommentsV2") or []:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("comment_id") or "")
            if not cid:
                continue
            # 评论图片：快手字段名未实测确认，按平台惯例做**防御性**提取
            # （有就取，没有就空 —— **不编造**）
            images: List[str] = []
            for key in ("pictures", "picList", "imageList", "images"):
                raw_imgs = c.get(key)
                if not isinstance(raw_imgs, list):
                    continue
                for im in raw_imgs:
                    if isinstance(im, str) and im.startswith("http"):
                        images.append(im)
                    elif isinstance(im, dict):
                        url = im.get("url") or im.get("cdnUrl") or im.get("src")
                        if isinstance(url, str) and url.startswith("http"):
                            images.append(url)
                if images:
                    break
            out.append({
                "id": cid,
                "content": c.get("content") or "",
                "author": c.get("author_name") or "",
                "author_id": str(c.get("author_id") or ""),
                "avatar": c.get("headurl") or "",
                "likes": int(c.get("likeCount") or 0),
                # ⚠️ 毫秒 → 秒（实测 timestamp=1790774972457）
                "create_time": int(c.get("timestamp") or 0) // 1000,
                "reply_count": 0,   # V2 无子评论计数字段
                "has_sub": bool(c.get("hasSubComments")),
                "images": images,
            })

        nxt = payload.get("pcursorV2")
        # ⚠️ 终值是 "no_more"（不是空串）
        has_more = bool(nxt) and str(nxt) != "no_more"
        return {
            "comments": out[:max_results],
            "next_cursor": str(nxt) if has_more else "",
            "has_more": has_more,
            # commentCountV2 是总数（实测 612）—— 但注意它可能不准
            "total": int(payload.get("commentCountV2") or 0),
        }

    async def get_replies(
        self,
        item_id: str,
        comment_id: str,
        max_results: int = 20,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """取某条评论的子回复（楼中楼）。

        接口：`POST /rest/v/photo/comment/sublist`
              body 加 `rootCommentId`（**int**，不是字符串）。

        ⚠️ **不需要签名**（与 `comment/list` 一样，实测确认）。
        实测：`rootCommentId=1181356104491` → `result=1`，1 条回复。
        """
        photo_id = str(item_id or "").strip()
        if not photo_id or not comment_id:
            return {"comments": [], "has_more": False, "next_cursor": "", "total": 0}

        headers = {
            "User-Agent": self._get_default_user_agent(),
            "Content-Type": "application/json",
            "Referer": f"{BASE}/short-video/{photo_id}",
        }
        cookie = self.header_cookie()
        if cookie:
            headers["Cookie"] = cookie

        # ⚠️ rootCommentId 是 **int**（实测）—— 传字符串可能被拒
        try:
            root_id: Any = int(comment_id)
        except ValueError:
            root_id = comment_id

        try:
            payload = await self.request(
                "POST",
                f"{BASE}{COMMENT_SUB_LIST}",
                json={
                    "photoId": photo_id,
                    "pcursor": cursor or "",
                    "rootCommentId": root_id,
                },
                headers=headers,
            )
        except Exception as exc:
            # ⚠️ 同样**不能吞成空列表**（2026-10-02，与 `get_comments_page` 同因）
            logger.warning("[kuaishou] 子评论请求失败：%s", exc)
            if isinstance(exc, (LoginExpiredError, RiskControlError)):
                raise
            raise NetworkError(
                f"[kuaishou] 子评论请求失败：{type(exc).__name__}: {str(exc)[:120]}"
            ) from exc

        if not isinstance(payload, dict) or payload.get("result") != 1:
            result_code = payload.get("result") if isinstance(payload, dict) else "?"
            raise LoginExpiredError(
                f"[kuaishou] 子评论接口返回 result={result_code}（请求被拒）。\n"
                "⚠️ 这不是「这条评论没有回复」—— 是**登录态失效或被风控**。\n"
                "请在「账号中心」重新获取快手登录态后重试。"
            )

        # 子评论字段与顶层一致（实测）：content / author_name / likeCount …
        # 额外有 `replyToUserName`（回复给谁）
        out: List[Dict[str, Any]] = []
        for c in payload.get("subCommentsV2") or payload.get("rootCommentsV2") or []:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("comment_id") or "")
            if not cid:
                continue
            out.append({
                "id": cid,
                "content": c.get("content") or "",
                "author": c.get("author_name") or "",
                "author_id": str(c.get("author_id") or ""),
                "avatar": c.get("headurl") or "",
                "likes": int(c.get("likeCount") or 0),
                "create_time": int(c.get("timestamp") or 0) // 1000,
                "reply_count": 0,
                # ⚠️ 子评论特有：回复给谁（前端可显示 "回复 @xxx"）
                "reply_to": c.get("replyToUserName") or "",
            })

        nxt = payload.get("pcursorV2")
        has_more = bool(nxt) and str(nxt) != "no_more"
        return {
            "comments": out[:max_results],
            "has_more": has_more,
            "next_cursor": str(nxt) if has_more else "",
            "total": len(out),
        }

    async def get_comments(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
        cursor: str = "",
    ) -> List[Dict[str, Any]]:
        """取作品评论（**免签名**，纯 HTTP）。

        ## ⚠️ 重大发现：评论不需要 `__NS_hxfalcon`（2026-10-01 实测）

        本客户端其它能力都建立在"签名必须浏览器抓"的前提上，
        但**评论是例外**。决定性对照（同一 cookie、同一时刻）：

            /rest/v/search/feed          无签名 → {"result":50,"签名验证失败"}
            /rest/v/photo/comment/list    无签名 → {"result":1,...} ✅ 正常

        所以这里**不走** `_post`（那条路要签名），直接用基类的纯 HTTP `request()`。

        ## 接口

            POST https://www.kuaishou.com/rest/v/photo/comment/list
            Content-Type: application/json
            Body: {"photoId": "<作品id>", "pcursor": ""}

        子评论：加 `rootCommentId`，端点换 `/rest/v/photo/comment/sublist`。

        ## 字段（**下划线命名**，与 GraphQL 版的驼峰 `commentId` 不同）

            comment_id / content / author_name / author_id / headurl
            likeCount / timestamp(**毫秒**) / hasSubComments

        ⚠️ `commentCount` 恒为 0，别用它当回复数（V2 没有子评论计数字段）。
        ⚠️ `result=1` 才是成功判据 —— 实测有作品 `commentCountV2=1389` 但
        `rootCommentsV2` 返回空列表，那是**正常的**，不是失败。
        """
        photo_id = str(item_id or "").strip()
        if not photo_id:
            return []

        want = max(1, int(max_results or 20))
        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        pcursor = cursor or ""

        import asyncio
        import random

        # ⚠️ 循环调 `get_comments_page`（归一与游标逻辑只写一处）
        for _ in range(max(1, (want + 19) // 20) + 1):
            if len(out) >= want:
                break
            page_data = await self.get_comments_page(
                photo_id, max_results=20, cursor=pcursor
            )
            for c in page_data.get("comments") or []:
                cid = str(c.get("id") or "")
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                out.append(c)
                if len(out) >= want:
                    break

            if not page_data.get("has_more"):
                break
            nxt = str(page_data.get("next_cursor") or "")
            if not nxt or nxt == pcursor:
                break
            pcursor = nxt
            # 实测：快手限流敏感 → 每页 sleep（参照 MediaCrawler 的 random.uniform(1,3)）
            await asyncio.sleep(random.uniform(1, 2))

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

        # 记下自己的 uid —— 抓 `profile/feed` 签名时要访问自己的主页
        _self_uid_cache[self.config.conn_id or "-"] = uid

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

    async def _get_user_profile_impl(self, user_id: str) -> Optional[UserProfile]:
        """查**指定用户**的资料 —— 走 **GraphQL**（`get_user_profile` 的实现）。

        ## 查询（字段全部实测确认，不是猜的）

            POST https://www.kuaishou.com/graphql
            {
              "query": "query{ visionProfile(userId:\\"<uid>\\"){ result "
                       "userProfile{ ownerCount{ fan photo follow } } } }"
            }

        `ownerCount` 的类型是 `VisionUserProfileOwnerCount`，**只有 3 个字段**：
        `fan`（粉丝）/ `photo`（作品）/ `follow`（关注）。
        ⚠️ **没有「获赞」** —— 页面上那个「获赞 5.5万」不在这条通道里，
        所以 `total_likes` 会是 0，前端别把它当成"0 获赞"显示。

        ## 身份信息（昵称/头像/简介）从哪来

        GraphQL 这次**没查**那些字段（`VisionUserProfile` 上没有 `userName`
        这类平铺字段，实测报 `Cannot query field`）。
        所以身份信息仍用 REST `profile/get`（`userName/userHead/userTex`），
        数字用 GraphQL，**两路合并**。

        ⚠️ GraphQL 未登录时返回 `{"result":2,"userProfile":null}`
          ⇒ 必须有**登录态**的浏览器上下文（`credentials: include`）。
        """
        uid = str(user_id or "").strip()
        if not uid:
            return None

        # ---- ★ 首选：`window.INIT_STATE`（明文、精确、实测最准）----
        #
        # 实测对比（uid=3xep6p7wbnqcvj6）：
        #     GraphQL  ownerCount: {"fan":"1.3万", ...}   ← **四舍五入**
        #     INIT_STATE ownerCount: {"fan":12551, "like":55163,
        #                               "follow":8, "photo_public":176}  ← 明文
        # 页面显示 1.3万 = 12551 取整 ⇒ 走 GraphQL 会显示 13000，**差 449**。
        #
        # ⇒ 必须优先 INIT_STATE。
        #
        # ⚠️ key 是**移位加密**的（每字符 -1），这也是之前 grep 昵称得到 0 次的原因：
        #     tusjoh.0sftu0w0qspgjmf0vtfs-pckfdu.vtfs`je.uvtkpi/<uid>
        #     → visionProfile.userId/<uid>
        #   **值本身是明文**（实测 user_name 直接就是"沈阳"），只有 key 要解码。
        init = await self._read_profile_from_init_state(uid)
        if init:
            prof = init.get("profile") or {}
            oc = prof.get("ownerCount") or {}
            logger.info(
                "[kuaishou] INIT_STATE %s → 粉丝=%s 关注=%s 作品=%s 获赞=%s",
                uid, oc.get("fan"), oc.get("follow"),
                oc.get("photo_public"), oc.get("like"),
            )
            return UserProfile(
                id=uid,
                name=str(prof.get("user_name") or ""),
                avatar=self._fix_bili_url(str(prof.get("headurl") or "")),
                platform="kuaishou",
                followers=_to_int(oc.get("fan")),
                following=_to_int(oc.get("follow")),
                total_videos=_to_int(oc.get("photo_public")),
                # ⚠️ `like` 是**获赞总数**（实测 55163 = 页面的 5.5万）
                total_likes=_to_int(oc.get("like")),
                desc=str(prof.get("user_text") or ""),
                verified=bool(prof.get("verified")),
                raw_data={"_source": "init_state", "profile": prof},
            )
        logger.info(
            "[kuaishou] INIT_STATE 没取到 %s —— 改用 GraphQL（数字会被四舍五入）", uid,
        )

        # ---- 兜底：GraphQL（数字是**四舍五入**的展示值）----
        # ---- GraphQL 取统计（fan / photo / follow）----
        #
        # ⚠️⚠️ 2026-10-07：**不要先跳转页面**（我先前加过，是错的）
        #
        # 我以为"GraphQL 在当前页面发 fetch，会拿到当前页用户的数字"，
        # 于是先 `goto` 目标主页再查。实测**两处都不对**：
        #
        #   ① 跳转**经常失败**（`打开 …/profile/3xep… 失败：Error`），
        #      失败还会连带影响同一会话里 `profile/feed` 的签名抓取
        #      ⇒ **作品列表一起挂掉**
        #   ② **根本不需要跳** —— GraphQL 的 `visionProfile(userId:…)`
        #      **自带 userId 参数**，查的就是那个用户。
        #      实测证据（同一份日志里）：
        #        `GraphQL 3xep6p7wbnqcvj6 → 粉丝=0 关注=8 作品=0`
        #      「关注 8」是「沈阳」的真实值 ⇒ 请求确实命中了目标用户。
        #
        # ⇒ 直接发，不跳转。
        counts: Dict[str, int] = {}
        session = await self._get_session()
        if session is not None:
            query = (
                "query{ visionProfile(userId:\"%s\"){ result "
                "userProfile{ ownerCount{ fan photo follow photo_public } } } }" % uid
            )
            try:
                raw = await session.page.evaluate(
                    _JS_POST,
                    {"url": f"{BASE}/graphql", "body": {"query": query}},
                )
                import json as _json
                env = _json.loads(raw) if isinstance(raw, str) else (raw or {})
                if env.get("_error"):
                    logger.warning("[kuaishou] GraphQL 请求失败：%s", env["_error"])
                else:
                    inner = _json.loads(env.get("body") or "{}")
                    vp = ((inner.get("data") or {}).get("visionProfile") or {})
                    up = vp.get("userProfile") or {}
                    oc = up.get("ownerCount") or {}
                    # ⚠️⚠️ **二次校验**：确认返回的确实是目标用户。
                    # 有了 ID 比对，才能保证这三个数字不是"自己的"。
                    # （`VisionUserProfile` 上没有 id 字段时，至少要靠下面的
                    #   REST 校验兜底 —— 那时 counts 也会被一并丢弃）
                    back_id = str(up.get("id") or up.get("userId") or "")
                    if oc and back_id and back_id != uid:
                        logger.warning(
                            "[kuaishou] GraphQL 返回的用户(%s) ≠ 请求的(%s) —— "
                            "丢弃数字", back_id, uid,
                        )
                        oc = {}
                    if oc:
                        # ⚠️⚠️⚠️ 2026-10-07 **带真实 cookie 实测**发现的三个坑：
                        #
                        #   {"fan":"1.3万", "photo":null, "follow":8,
                        #    "photo_public":176}
                        #
                        #   ① **`fan` 是带"万"的中文字符串 `"1.3万"`**，不是数字！
                        #      原来的 `_to_int` 转成 0 ⇒ 界面粉丝恒显示 0。
                        #      ⇒ 必须解析"1.3万 / 5.5万 / 12.3亿"这类。
                        #   ② **`photo` 返回 null** —— 拿它当作品数必然是 0。
                        #   ③ 作品数在 **`photo_public`**（**下划线**）里 = 176。
                        #      ⚠️ 我之前按驼峰试 `photoPublic` 被拒 —— 是**下划线**。
                        #
                        # 页面真值对照（uid=3xep6p7wbnqcvj6）：
                        #   关注 8 / 粉丝 1.3万 / 获赞 5.5万
                        #   实测 GraphQL：follow=8 ✅ fan="1.3万" ✅ photo_public=176
                        # ⇒ `follow`=关注、`fan`=粉丝、`photo_public`=作品，**全对上了**。
                        counts = {
                            "fan": _parse_cn_count(oc.get("fan")),
                            # ⚠️ photo 恒为 null（实测），作品数用 photo_public
                            "photo": _parse_cn_count(oc.get("photo_public")),
                            "follow": _parse_cn_count(oc.get("follow")),
                        }
                        logger.info(
                            "[kuaishou] GraphQL %s → 粉丝=%s 关注=%s 作品=%s",
                            uid, counts["fan"], counts["follow"], counts["photo"],
                        )
                    else:
                        # result=2 通常就是"没登录" —— 如实记，不要静默
                        logger.info(
                            "[kuaishou] GraphQL %s 返回空（result=%s）"
                            "—— 可能登录态失效，或页面上下文不对",
                            uid, vp.get("result"),
                        )
            except Exception as exc:
                logger.warning("[kuaishou] GraphQL 异常：%s: %s",
                               type(exc).__name__, exc)

        # ---- ⚠️⚠️ 2026-10-07：**不再调用 `/rest/v/profile/get`**（实测证明有害）
        #
        # 我之前用它取"昵称/头像/简介"，结果它是**所有麻烦的根源**：
        #
        #   ① 它**只能查自己** —— 签名是会话级的，userId 不在 body 也不在
        #      query（只在**页面 URL** 上）。实测请求目标 uid 时，
        #      返回的永远是**登录账号自己**（日志实测：
        #        `profile/get id 不符：请求 uid=3xep…，返回 ids=['2695872552']`
        #        —— 2695872552 就是我自己的 userId）
        #   ② 为此我加了「先跳转目标主页」的步骤，而它**经常失败**
        #      （实测 `打开 https://www.kuaishou.com/profile/3xep… 失败：Error`），
        #      失败还会连带让 `profile/feed` 的签名抓不到 ⇒ **作品列表也挂**
        #   ③ 于是又得加"id 校验"防冒充 —— 而它必然触发，整个功能不可用
        #
        # **实测证明它本来就不必要**（同一次请求里）：
        #     [kuaishou] GraphQL 3xep6p7wbnqcvj6 → 粉丝=0 关注=8 作品=0
        # 「关注 8」正是「沈阳」的真实值（与 B站/快手页面一致）⇒
        # **GraphQL 自带 userId 参数，本来就查的是目标用户**，
        # 不需要跳转页面，也不需要 profile/get 兜底。
        #
        # 身份字段（昵称/头像/简介）怎么办？
        #   · 前端**已经先用搜索结果渲染**了（昵称/头像/简介都在，见
        #     `frontend/src/pages/platform-users/index.tsx` 的快手分支）
        #   · GraphQL 的 `VisionUserProfile` 上**实测没有任何身份字段**
        #     （name/headurl/userText/id/verified 全部 `Cannot query field`，
        #       只有 ownerCount）—— 所以身份只能来自搜索结果。
        #
        # ⇒ 所以这里**只返回 GraphQL 的数字**，身份留空由上层合并。
        if not counts:
            logger.info(
                "[kuaishou] GraphQL 没取到 %s 的统计（登录态失效？）—— "
                "上层会沿用搜索结果里的昵称/头像", uid,
            )
            return None

        return UserProfile(
            id=uid,
            # ⚠️ 身份字段留空：GraphQL 没有，`profile/get` 只能查自己。
            #   上层（前端）会用搜索结果补齐，这里返回空**不会**覆盖它。
            name="",
            avatar="",
            platform="kuaishou",
            followers=counts.get("fan", 0),
            following=counts.get("follow", 0),
            total_videos=counts.get("photo", 0),
            # ⚠️ GraphQL **没有获赞字段** ⇒ 恒为 0。
            #   前端据此显示「—」而不是"0 获赞"（那是谎报）。
            total_likes=0,
            desc="",
            raw_data={"_graphql": counts, "_source": "graphql"},
        )

    async def _read_profile_from_init_state(self, uid: str) -> Optional[Dict[str, Any]]:
        """从目标主页的 `window.INIT_STATE` 读明文资料（实测 2026-10-07）。

        ## 为什么用这条路（而不是 GraphQL）

        实测同一用户（uid=3xep6p7wbnqcvj6）：

            GraphQL    ownerCount: {"fan":"1.3万", "photo":null, "follow":8}
            INIT_STATE ownerCount: {"fan":12551, "like":55163,
                                    "follow":8, "photo_public":176}
            页面显示    粉丝 1.3万 / 获赞 5.5万

        ⇒ GraphQL 给的是**四舍五入的展示字符串**，INIT_STATE 才是**精确值**
          且**含获赞**。走 INIT_STATE 还能拿到昵称/头像/简介（GraphQL 上
          那几个字段实测 `Cannot query field`）。

        ## key 是移位加密的

            HTML: tusjoh.0sftu0w0qspgjmf0vtfs-pckfdu.vtfs`je.uvtkpi/<uid>
            实际: visionProfile.userId/<uid>

            规则：每个字符 **-1**；`` ` `` → `_`；``\\`` / ``\\/`` → `_`

        **值本身是明文**（实测 `user_name` 直接是"沈阳"），
        只有 key 名需要还原 —— 这也是之前直接 grep 昵称得到 0 次的原因。

        ## 登录态也能取到（实测）

        另一份独立调查报告的结论是"只有游客态有 INIT_STATE"，
        **实测不成立**：登录态下同样有，且值一致。
        """
        session = await self._get_session()
        if session is None:
            return None
        try:
            await session.page.goto(
                f"{BASE}/profile/{uid}",
                wait_until="domcontentloaded", timeout=60000,
            )
            await session.page.wait_for_timeout(3000)
        except Exception as exc:
            logger.info("[kuaishou] 打开主页取 INIT_STATE 失败：%s: %s",
                        type(exc).__name__, str(exc)[:80])
            return None

        # ⚠️ 不要硬编码那个 key（尾部含 uid，且易被快手改动）；
        #   直接在页面里找**属于 visionProfile 且含 userId** 的那个 key。
        expr = (
            "(() => { const s = window.INIT_STATE;"
            " if (!s) return null;"
            " for (const k of Object.keys(s)) {"
            "   if (k.indexOf('tusjoh') === 0"
            "       && k.indexOf('pckfdu') > 0"
            "       && k.indexOf('vtfs') > 0) {"
            "     return JSON.stringify(s[k]);"
            "   }"
            " } return null; })()"
        )
        try:
            raw = await session.page.evaluate(expr)
        except Exception as exc:
            logger.info("[kuaishou] 读 INIT_STATE 失败：%s: %s",
                        type(exc).__name__, str(exc)[:80])
            return None

        if not raw:
            return None
        try:
            import json as _json

            data = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None

        up = (data or {}).get("userProfile") or {}
        prof = up.get("profile") or {}
        if not prof:
            return None
        # ⚠️ 必须校验 user_id 是**目标用户**（别拿到页面上别人的数据）
        got = str(prof.get("user_id") or "")
        if got and got != uid:
            logger.warning(
                "[kuaishou] INIT_STATE 的 user_id(%s) ≠ 请求的(%s) —— 丢弃",
                got, uid,
            )
            return None
        return prof

    async def get_user_videos(
        self,
        user_id: str,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """取某个用户的**作品列表**（实测打通 2026-09-30）。

        ## 接口（打开用户主页抓到的真实请求）

            POST /rest/v/profile/feed?__NS_hxfalcon=<该路径自己的签名>
            body: {"user_id":"5372574395","pcursor":"","page":"profile"}

        ⚠️ **签名要去用户主页抓** —— 搜索页**不会**请求这个路径
        （见 `_pages_for`）。

        ⚠️ `page` 是固定字符串 `"profile"`（不是页码）；翻页用 `pcursor`。
        """
        want = max(1, max_results)
        uid = str(user_id or "").strip()
        if not uid:
            return []

        out: List[SearchResult] = []
        seen: set[str] = set()
        pcursor = ""
        for _ in range(max(1, (want + 19) // 20) + 1):
            # ⚠️⚠️ 2026-10-07 修：**必须传 uid**
            #
            # `profile/feed` 的签名**只在打开目标用户主页时**才会发出
            # （搜索页永远不发，见 `_pages_for` 的说明）。
            # 原来这里没传 uid ⇒ 签名去抓自己主页的 ⇒ 抓不到：
            #     [kuaishou] 抓到签名但 /rest/v/profile/feed 不在其中
            #     （已有：/rest/v/profile/get, /rest/v/search/feed, /rest/v/search/user）
            # ⇒ 作品列表 500。
            payload = await self._post(
                PROFILE_FEED, build_profile_feed_body(uid, pcursor), uid=uid,
            )
            if payload is None:
                break
            feeds = payload.get("feeds") or payload.get("list") or []
            for feed in feeds:
                parsed = parse_feed(feed)
                if parsed is None or parsed["id"] in seen:
                    continue
                seen.add(parsed["id"])
                out.append(self._to_result(parsed))
            if len(out) >= want:
                break
            nxt = str(payload.get("pcursor") or "")
            if not nxt or nxt == pcursor:
                break
            pcursor = nxt

        results = out[:want]
        if results:
            results[0].raw_data["_has_more"] = bool(pcursor)
        logger.info("[kuaishou] 用户 %s 的作品 -> %d 条", uid, len(results))
        return results

    async def get_detail(self, item_id: str, **kwargs) -> Optional[NoteDetail]:
        """取作品详情。

        ## ⚠️ 原来这里**永远返回 None**（2026-10-02 修）

        原来是 `return None`（注释说"搜索结果里已含全部字段，
        这里不重新请求"）—— 但 `crawler/service.py::get_note_detail`
        拿到 None 后会 `return {}`，路由层就变成
        **404「笔记不存在或获取失败」**。

        **而作品是真实存在的**（用户刚从搜索结果点进来）。
        这是**谎报**。

        ## 现在的做法（参照抖音的 `get_detail`）

        抖音是 `raw = kwargs.get("raw")` → 有就用搜索结果直接解析
        （零请求），没有才调真实接口。快手照做：

          1. 调用方带了 `raw`（搜索时的原始条目）→ 直接解析
          2. 没有 `raw` → **如实报错**（而不是静默 None）

        搜索结果的 `photo` 字段已含标题/作者/封面/点赞等详情所需。
        """
        raw = (kwargs or {}).get("raw")
        if not raw:
            raise ContentNotFoundError(
                "[kuaishou] 取详情需要**搜索结果的原始条目**"
                "（`raw` 参数）—— 快手没有公开的「按作品 ID 查详情」接口。\n"
                "请从搜索结果点进详情（前端已这样传），"
                "不要单独用作品 ID 调详情接口。"
            )

        # 兼容两种形状：{photo:{...}} 或直接就是 photo
        photo = raw.get("photo") if isinstance(raw, dict) else None
        if not isinstance(photo, dict):
            photo = raw if isinstance(raw, dict) else {}
        if not photo:
            raise ContentNotFoundError(
                "[kuaishou] 搜索结果里没有 photo 字段，无法解析详情。"
            )

        return NoteDetail(
            id=item_id,
            title=str(photo.get("caption") or "").strip(),
            desc=str(photo.get("caption") or "").strip(),
            author=str((photo.get("author") or {}).get("name") or ""),
            author_id=str((photo.get("author") or {}).get("id") or ""),
            cover=str(photo.get("coverUrl") or photo.get("cover") or ""),
            images=_to_int(photo.get("images")),
            likes=_to_int(photo.get("likeCount")),
            comments=_to_int(photo.get("commentCount")),
            shares=_to_int(photo.get("shareCount")),
            collects=_to_int(photo.get("collectCount")),
            duration=_to_int(photo.get("duration")),
            video_url=str(
                (photo.get("mainMvUrls") or [{}])[0].get("url")
                if photo.get("mainMvUrls") else ""
            ),
            platform="kuaishou",
            raw_data=raw,
        )

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
