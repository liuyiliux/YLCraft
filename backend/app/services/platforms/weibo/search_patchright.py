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
from ..types import LoginExpiredError
from ..session_pool import PooledSession, SessionPool
from ..types import SearchParams, SearchResult, UserProfile
from .apis import build_search_params
from .client import parse_user
from .client import parse_mblog
from .search_desktop import (
    DESKTOP_MAX_PAGE,
    DESKTOP_PAGE_SIZE,
    DESKTOP_XSORT,
    DesktopLoginRequired,
    fetch_desktop_page,
    parse_desktop_card,
)
# ⚠️ 直连 HTTP 是**主路径**（0.4~1 秒），浏览器只是兜底（15 秒）。
#    见本模块 `search_via_patchright` 的 docstring —— 名字骗人，但路是对的。
from .search_http import (
    MAX_PAGE,
    PAGE_SIZE,
    WeiboLoginRequired as HttpLoginRequired,
    _resolve_cookie as _http_cookie,
    fetch_page,
    to_search_result,
)

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
                        {
                          credentials: 'include',
                          // ⚠️ **必须带这些头**（2026-09-29 实测）
                          //
                          // 微博对"需要登录"的接口（如用户微博列表的
                          // `page>=2`）会校验 referer —— 不带就被踢到
                          // `passport.weibo.com/sso/signin`（`ok=-100`）。
                          //
                          // 实测：加 referer + x-requested-with 后
                          // `page=2/3` 都能正常返回。
                          headers: {
                            'accept': 'application/json, text/plain, */*',
                            'x-requested-with': 'XMLHttpRequest',
                            'mweibo-pwa': '1',
                          },
                          referrer: args.referrer || 'https://m.weibo.cn/',
                        });
  const t = await r.text();
  if (!t || t[0] !== '{') {
    return JSON.stringify({ _error: 'not_json', http: r.status, head: t.slice(0, 120) });
  }
  return t;
}
"""


async def _get_session(conn_key: str, client=None) -> PooledSession:
    """取（或新建）一个已打开微博首页的会话。

    ## ⚠️ 优先复用 `client` 已建好的会话（2026-09-29 修，重要）

    用户反馈"为啥个人中心的微博老是打开浏览器了？"以及
    「我的数据」一直拿不到（`login=False`）。

    实测日志暴露了真正的竞争：

        12:04:50.936  [base] Cookies set to browser → 新建会话（**有 cookie**）
        12:04:50.941  [weibo] **又启动了一次持久化 profile**   ← 打架
        12:04:51.397  [weibo] 新建浏览器会话（无头，**没注入 cookie**）

    **两个上下文同时打开同一个持久化 profile**，第二个覆盖了第一个，
    于是 m 站的登录 cookie（`SSOLoginState` 等）**没生效** → `login=False`。

    根因：`base._init_patchright` 已经建好并**注入了 cookie** 的会话，
    这里却没有复用它（之前的 key 格式还不一致，两个 key 指同一 profile）。

    **修法**：调用方传 `client` 进来时，直接用它已建好的 page/context，
    不再新建第二个上下文。

    ## 无头模式（2026-09-29）

    原来用有头 → 每次新会话都**在用户桌面弹窗口**。
    实测无头同样能搜到（cards=14 vs 13），所以改成无头。
    """
    key = f"weibo|{conn_key or '-'}"

    # ① 优先复用 base 已建好的会话（它有注入过 cookie 的上下文）
    existing_page = getattr(client, "_patchright_page", None)
    if existing_page is not None:
        session = PooledSession(
            ctx=getattr(client, "_patchright_context", None),
            page=existing_page,
        )
        # 借用，不归池所有（归还时不能关掉 base 的上下文）
        session.borrowed = True
        if session.alive():
            await _warm_up(session, borrowed=True)
            session.touch()
            return session
        logger.info("[weibo] client 的会话已失效，改为新建")

    # ② 池里已有 → 复用
    session = _pool.get(key)
    if session is None:
        rt = get_patchright_runtime()
        ctx = await rt.new_context(
            headless=True,
            viewport={"width": 1440, "height": 900},
            persistent_platform="weibo",   # 登录态跨会话保留
        )
        page = await ctx.new_page()
        # ⚠️ **必须显式注入 cookie**（2026-09-29 修）
        #
        # 原来这里不注入，只靠持久化 profile —— 实测那条路的登录态是
        # **访客态**（`/api/config` 返回 `login=False`、`MLOGIN=0`、
        # `SUB` 是访客 SUB）。
        #
        # 后果：`page=2` 这类**要求登录**的接口被踢到
        # `passport.weibo.com/sso/signin`（`ok=-100`），
        # 而 `page=1` 是公开数据所以能拿到 —— 表现为
        # "用户微博列表只有第一页"。
        #
        # base 那条路（`_set_cookies_to_browser`）是显式注入的，
        # 两条路不一致才是根因。这里对齐。
        await _inject_cookies(ctx, conn_key)
        session = PooledSession(ctx=ctx, page=page)
        _pool.put(key, session)
        logger.info("[weibo] 新建浏览器会话（无头）key=%s", key)

    await _warm_up(session)
    session.touch()
    return session


async def _inject_cookies(ctx, conn_key: str) -> None:
    """把数据库里存的微博 cookie 注入浏览器上下文。

    微博的 cookie 域是 `.weibo.cn`（m 站登录态，含 `SSOLoginState`）——
    **不能只靠持久化 profile**：实测那条路的 cookie 会退化成访客态。

    失败只告警不中断（搜索/公开数据仍可用，
    只是需要登录的能力会报可操作错误）。
    """
    try:
        from ..login_health import netscape_to_header, resolve_connection

        _cid, raw = resolve_connection(conn_key or "", "WEIBO")
        if not raw:
            logger.info("[weibo] 没有可用的 cookie（公开功能仍可用）")
            return
        cookie = netscape_to_header(raw, "weibo")
        if not cookie:
            return
        pairs = [p for p in cookie.split("; ") if "=" in p]
        items = []
        for part in pairs:
            k, _, v = part.partition("=")
            # 同时种到 m 站与主站域（m 站接口要 `.weibo.cn`）
            for dom in (".weibo.cn", ".weibo.com"):
                items.append({"name": k, "value": v, "domain": dom, "path": "/"})
        if items:
            await ctx.add_cookies(items)
            logger.info(
                "[weibo] 已注入 %d 个 cookie（含 SSOLoginState=%s）",
                len(items), "SSOLoginState" in cookie,
            )
    except Exception as exc:
        logger.warning("[weibo] 注入 cookie 失败（公开功能仍可用）：%s", exc)


async def _warm_up(session: PooledSession, *, borrowed: bool = False) -> None:
    """预热：打开 m.weibo.cn 并等 Service Worker 就绪。

    **预热是必须的**（实测）：太短会让搜索仍走无 SW 的路径 → `ok=-100`。
    实测需要 ~9 秒。
    """
    if session.warmed:
        return
    try:
        await session.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        if not borrowed:
            _pool.drop(f"weibo|{getattr(session, 'conn_key', '') or '-'}")
        raise RuntimeError(
            f"[weibo] 打开 m.weibo.cn 失败：{type(exc).__name__}。"
            "通常是网络问题或被限流。"
        ) from exc
    await session.page.wait_for_timeout(9000)
    session.warmed = True


async def search_via_patchright(
    params: SearchParams,
    *,
    conn_key: str = "",
    client=None,
    page: int = 1,
    max_pages: int = 3,
) -> List[SearchResult]:
    """在微博里搜内容。

    ## ⚠️ 名字骗人：这条路**优先不走浏览器**（2026-10-06）

    函数名还叫 `_patchright`，但实际是**先直连 HTTP**：

    | 路径 | 实测耗时 | 什么时候走                       |
    | ---- | -------- | ------------------------------ |
    | **直连（httpx）** | **0.4~1 秒** | 绝大多数情况（默认） |
    | 浏览器兜底        | 15 秒       | 直连失败/被限流/改版 |

    ⚠️ 直连实测：page 1/2/3/10/50 全都有内容，页与页**零重叠**。

    ## 为什么曾经以为"必须开浏览器"——两次都是我的错

    **① 10-04**：我用的是移动版 `m.weibo.cn` 的 JSON 接口，它的 `page`
    参数翻不动（`page=2` 恒 0 条）。**那是我选错了端点**，不是平台限制。
    打开真实页面滚到底才发现：**页面自己会发 `page=2/3/4`**，能翻。

    **② 10-06**：我给 `s.weibo.com` 的**网页请求**加了接口用的头：

        'x-requested-with': 'XMLHttpRequest'      ← 就是这个

    带上它，微博直接返回"页面不存在"（`retcode=6102`），我拿这个被踢的
    结果下了结论"直连不行"，**还写进了代码注释当实测结论**，
    于是白开了几天浏览器（每次 15 秒 + 250MB 内存）。

    ⇒ **网页请求不能带 `x-requested-with`。** 去掉就好。

    ## 总页数

    页面 HTML 里写着 **「共50页」**，实测是**真的上限**（不是模板文字）：
    换词仍是 50、请求 `page=51` 会被**弹回第 1 页**。

    ⇒ 直接告诉用户"共 50 页"，不用再翻到空页才发现。

    ## 仍然要**先确认登录态**，否则结论作废

    我在这个功能上栽过两次：手工脚本**没加载 `.env`** → 访客态；
    判据看错位置 —— `/api/config` 的 `login` 在 **`data`** 里不在顶层。
    """
    want = max(1, params.max_results or 20)

    # ⚠️ `params.search_type` 是 **SearchType 枚举**（默认 NOTE），
    # 直接 str() 会得到 "SearchType.NOTE" —— 要先取 `.value`。
    raw_st = getattr(params, "search_type", "") or "note"
    st_key = str(getattr(raw_st, "value", raw_st)).strip().lower()
    xsort = DESKTOP_XSORT.get(st_key, "")
    # ⚠️⚠️ 「实时」**是有的** —— 我之前说"桌面版没有实时分类"是**错的**（2026-10-07 修正）。
    #
    # 我当时只看了 `/weibo?q=` 这个页面，上面的标签里没有实时，就下了结论。
    # 用户直接截图 `/realtime?q=沈阳&rd=realtime` 证明它**存在**，
    # 而且是**另一个页面**（不是 `/weibo` 上的参数）。
    #
    # 浏览器实测（2026-10-07，从标签 href 读出来的）：
    #     综合 /weibo?q=…&Refer=weibo_weibo
    #     热门 /weibo?q=…&xsort=hot&Refer=hotmore
    #     实时 /realtime?q=…&rd=realtime&tw=realtime     ← 这里
    #     视频 /video?q=…&xsort=hot&hasvideo=1&tw=video
    #     图片 /pic?q=…
    #
    # ⇒ 真实路径由 `search_http.DESKTOP_PATHS` 决定，这里只透传 search_type。

    # ===== ① 先试直连 =====
    # ⚠️ 用 `raised` 记录"直连是**失败**了"还是"直连**成功但没内容**"。
    #    两者对"要不要开浏览器"的含义完全不同（见下）。
    _http_raised: Optional[str] = None
    _http_login_failed: Optional[str] = None
    try:
        results = await _search_http(
            params.keyword, want=want, page=page,
            max_pages=max_pages, xsort=xsort, conn_key=conn_key,
            search_type=st_key,
        )
        if results:
            logger.info(
                "[weibo] 搜索 %r -> %d 条（直连 s.weibo.com，type=%s，has_more=%s，共%s页）",
                params.keyword, len(results), st_key,
                results[0].raw_data.get("_has_more"),
                results[0].raw_data.get("_total_pages"),
            )
            return results

        # ⚠️⚠️ **直连成功、但这一页真的没有内容** —— 不要开浏览器。
        #
        # 实测：搜一个不存在的词，直连返回 0 条（这是**正确答案**），
        # 但旧逻辑看到 0 条就以为"直连不行"，又去开浏览器白跑一趟 ——
        # 于是"搜不到"要等 18.7 秒，而真的搜到了只要 2.8 秒。
        #
        # ⚠️ 只有**异常/网络失败**才需要浏览器兜底；
        #    "平台确实没有这个内容"不该触发兜底。
        #
        # 第 1 页为空 ⇒ 关键词真没内容（实测：不存在的词第 2~N 页也是空）
        if page <= 1:
            logger.info(
                "[weibo] 搜索 %r -> 0 条（直连正常返回，平台没有这个内容）",
                params.keyword,
            )
            return []

    except HttpLoginRequired as exc:
        # ⚠️⚠️ **登录失败要试浏览器，不能直接放弃**（2026-10-07 修）
        #
        # 原来这里无条件 `raise LoginExpiredError` —— 理由是"别开浏览器白跑"。
        # 但实测：库里那份 cookie 失效、直连被 302 到 `login.sina.com.cn` 时，
        # **浏览器路径却可能还能用** —— 它读的是持久化 profile 里的登录态，
        # 与 DB 里那份 cookie 是**两套东西**（见 `persistent_profile`）。
        #
        # ⇒ 直接抛错 = 明明有备用登录态却不用，用户看到"搜不到"。
        #   正确做法：让它走下面的浏览器兜底；浏览器也失败才报错。
        logger.warning(
            "[weibo] 直连需要登录（%s）→ 试浏览器路径"
            "（它用的是 profile 里的登录态，与 DB cookie 是两套）", exc,
        )
        _http_login_failed = str(exc)
    except Exception as exc:
        _http_raised = f"{type(exc).__name__}: {exc}"
        # ⚠️⚠️ 用 **warning** 不用 info —— 兜底是**异常情况**，不是常态。
        #    我第一版用 info，结果直连因为一个 ImportError 静默失败、
        #    悄悄回退到浏览器，表现为"改了没效果、还是 15 秒"，
        #    而日志里只有一行不起眼的 info。
        logger.warning(
            "[weibo] 直连失败（%s）→ 回退到浏览器路径（慢 15 秒）。"
            "若是 ImportError/AttributeError，说明代码有错，不是网络问题。",
            _http_raised,
        )

    # ===== ② 直连不行才开浏览器（兜底，不是主路）=====
    try:
        return await _search_via_browser(
            params, conn_key=conn_key, client=client,
            page=page, max_pages=max_pages, xsort=xsort, want=want,
        )
    except LoginExpiredError:
        # 两条路都要登录 ⇒ 这次是真的要用户去补登录态了
        if _http_login_failed:
            raise LoginExpiredError(
                "[weibo] 微博搜索需要登录 —— 直连（DB cookie）与浏览器"
                "（profile 登录态）**都**被拒。\n"
                "请在「账号中心」重新保存微博登录态后重试。"
            ) from None
        raise


async def _search_http(
    keyword: str,
    *,
    want: int,
    page: int,
    max_pages: int,
    xsort: str,
    conn_key: str,
    search_type: str = "",
) -> List[SearchResult]:
    """直连 `s.weibo.com` 取结果（主路径）。

    ## ⚠️⚠️ 两种语义要分清（2026-10-07 修，用户实测发现）

    前端有两个参数，含义**完全不同**：

        page         第几页（翻页用）
        max_results  这一页要多少条

    ⚠️ 我原来把 `max_results` 当成"**总共**要凑够多少条"，
       于是 `max_results=30` 会从第 1 页开始**连翻 3 页**凑 30 条 ——
       但那样第 2 页返回的就是"第1~3页的混合"，与"第2页"对不上。

    实测（用户报的）：要 30 条却只给 23 条，而且**不含**前 10 条 ——
    因为它是从 `page` 开始往后翻、翻到的条数又不齐。

    ⇒ 正确语义：**取第 `page` 页，最多要 `max_results` 条**。
      要更多内容请**翻页**（前端已经有分页器），不要靠调大条数。
    """
    cookie = _http_cookie(conn_key)
    if not cookie:
        raise RuntimeError("没有可用的微博 cookie")

    # ⚠️ 只取**这一页**。不再往后连翻凑数 ——
    #    那是"加载更多"的语义，不是"翻页"的语义，混在一起两边都不对。
    #    一页实测给 9~10 条（不足 10 是平台行为，不是 bug）。
    pages_to_try = 1

    out: List[SearchResult] = []
    seen: set[str] = set()
    total_pages: Optional[int] = None
    pages_fetched = 0
    cards: List[Dict[str, Any]] = []

    for i in range(pages_to_try):
        pn = page + i
        try:
            cards, tp = await fetch_page(
                keyword, pn, cookie_header=cookie, xsort=xsort,
                search_type=search_type)
        except HttpLoginRequired:
            # ⚠️ 这里必须 re-raise 成**同一个类型** —— 上层
            #    `search_via_patchright` 按它决定"要不要试浏览器"。
            #
            # ⚠️⚠️ 我第一版在这里写了个不存在的类名 `WeiboHttpLoginRequired`
            #     → `NameError` → 被下面的 `except Exception` 吃掉 →
            #     直连每次都"失败"并静默回退浏览器。
            #     表现就是"改了没效果、还是慢"——和之前那个 ImportError 同一类错。
            #     ⚠️ 自定义异常**没有**兜底类，拼错就是运行时 NameError。
            raise
        except Exception as exc:
            logger.info("[weibo] 直连第 %d 页失败：%s: %s", pn, type(exc).__name__, exc)
            break

        pages_fetched = i + 1
        if tp:
            total_pages = tp          # 平台直接说了有几页，比猜准
        if not cards:
            break

        for c in cards:
            parsed = to_search_result(c)
            if parsed is None or parsed.id in seen:
                continue
            seen.add(parsed.id)
            out.append(parsed)

    if not out:
        return []

    # ⚠️ `has_more` **算出来**，不猜：
    #   · 平台说了总页数（实测「共50页」）→ 按它算，不用翻到空页
    #   · 没说                 → 用"这页是不是空的"判断
    #
    # ⚠️ 现在只取一页，所以判据是"**这一页有没有内容**"，
    #    而不是"翻了几页"。空页 = 到顶了。
    if total_pages:
        has_more = int(page) < total_pages
    else:
        has_more = bool(cards)

    out[0].raw_data["_has_more"] = bool(has_more)
    # ⭐ 总页数透给前端 —— 用户能看见"共 50 页"，不用自己翻到头
    out[0].raw_data["_total_pages"] = total_pages
    return out[:want]


async def _search_via_browser(
    params: SearchParams,
    *,
    conn_key: str,
    client,
    page: int,
    max_pages: int,
    xsort: str,
    want: int,
) -> List[SearchResult]:
    """浏览器路径（**兜底**）—— 直连被限流/改版时才走。

    ⚠️ 慢（15 秒），但能跑。直连与它读的是同一批结果，
    所以两者拿到的 mid 集合应该一致 —— 测试钉住了这一点。

    ⚠️ 与直连路径**同样的语义**：只取第 `page` 页，最多 `max_results` 条。
       **不要**连翻几页凑数（那会让"第 2 页"变成"第1~3页的混合"）。
    """
    session = await _get_session(conn_key, client=client)
    out: List[SearchResult] = []
    seen: set[str] = set()
    cards = []

    try:
        cards = await fetch_desktop_page(session, params.keyword, page, xsort=xsort)
    except DesktopLoginRequired as exc:
        raise LoginExpiredError(
            "[weibo] 微博搜索需要登录。请在「账号中心」重新保存微博登录态后重试。"
        ) from exc
    except Exception as exc:
        logger.warning("[weibo] 浏览器路径第 %d 页失败：%s", page, exc)
        return []

    for card in cards:
        parsed = parse_desktop_card(card)
        if parsed is None or parsed.id in seen:
            continue
        seen.add(parsed.id)
        out.append(parsed)

    if not out:
        return []

    # ⚠️ 只取一页，所以 `has_more` = "这一页有没有内容"
    #    （空页 = 到顶了）。不再按"翻了几页"算。
    has_more = bool(cards)
    out[0].raw_data["_has_more"] = has_more
    # 浏览器路径拿不到总页数 —— 如实给 None，不编
    out[0].raw_data["_total_pages"] = None

    logger.info(
        "[weibo] 搜索 %r -> %d 条（浏览器兜底，第 %d 页，has_more=%s）",
        params.keyword, len(out), page, has_more,
    )
    return out[:want]


async def search_users_via_patchright(
    keyword: str,
    *,
    conn_key: str = "",
    client=None,
    page: int = 1,
    max_results: int = 20,
) -> List[UserProfile]:
    """搜微博用户（**实测免登录可用**）。

        containerid=100103type=3&q={关键词}&page_type=searchall&page=N
        → cards[].card_type=11 → card_group[] → user{}

    ⚠️ 用户卡片的解析路径与内容搜索**完全不同**
    （内容走 card_type=9 → mblog）。
    """
    from .apis import build_user_search_params

    session = await _get_session(conn_key, client=client)
    qp = build_user_search_params(keyword, page=page)
    raw = await session.page.evaluate(JS_SEARCH, {"params": qp})
    data = _load_json(raw, "用户搜索")

    out: List[UserProfile] = []
    seen: set[str] = set()
    for card in ((data.get("data") or {}).get("cards") or []):
        for user in _iter_card_users(card):
            parsed = parse_user(user)
            if parsed is None or parsed.id in seen:
                continue
            seen.add(parsed.id)
            out.append(parsed)
            if len(out) >= max_results:
                break
        if len(out) >= max_results:
            break

    logger.info("[weibo] 用户搜索 %r -> %d 个", keyword, len(out))
    return out


async def get_user_posts_via_patchright(
    uid: str,
    *,
    page: int = 1,
    max_results: int = 20,
    conn_key: str = "",
    client=None,
) -> List[SearchResult]:
    """取某个用户发的微博列表（**实测打通 2026-09-29**）。

    ## 参数（**都要**，少一个就失败）

        GET /api/container/getIndex
            ?type=uid&value={uid}                  ← 必须
            &containerid=107603{uid}               ← 必须
            &page={N}

    ⚠️ 三个坑（都实测踩过）：

    1. **`containerid` 是 `107603{uid}`**（不是用户详情的 `100505{uid}`）。
       来源：MediaCrawler 硬编码。

    2. **必须带 `type=uid&value={uid}`** —— 只给 containerid + page
       会返回 HTML 错误页（2700 字节）。

    3. **必须带 `referer`**（见 `JS_SEARCH`）—— 不带会被踢到
       `passport.weibo.com/sso/signin`（`ok=-100`）。
       而且 `page>=2` **要求登录态**（`page=1` 是公开数据）。

    ## 翻页

    用 `page=N`（不是 since_id —— 实测 `cardlistInfo.since_id` 是 None）。
    实测 page=1/2/3 各返回 10 条不同内容。

    ## 前置：登录态

    ⚠️ 池会话**必须显式注入 cookie**（见 `_inject_cookies`）——
    只靠持久化 profile 会退化成访客态，`page=2` 直接 `ok=-100`。
    """
    from .apis import build_user_posts_params
    from .client import parse_mblog

    session = await _get_session(conn_key, client=client)

    want = max(1, max_results)
    # 每页固定 10 条，要够数就多翻几页
    pages_needed = max(1, (want + 9) // 10)

    out: List[SearchResult] = []
    seen: set[str] = set()

    for i in range(pages_needed):
        page_no = page + i
        params = build_user_posts_params(uid, page=page_no)
        # ⚠️ 补上 type/value —— 少这两个会返回 HTML 错误页
        params["type"] = "uid"
        params["value"] = str(uid)

        raw = await session.page.evaluate(
            JS_SEARCH,
            {"params": params, "referrer": f"https://m.weibo.cn/u/{uid}"},
        )
        data = _load_json(raw, f"用户微博列表 page={page_no}")

        if data.get("ok") != 1:
            # ok=-100 = 被踢到登录页。这里的**可操作**提示很重要：
            # 用户看到"只有一页"会以为"这人就发了这么多"。
            logger.info(
                "[weibo] 用户微博列表 page=%d 返回 ok=%s（通常需要登录态）",
                page_no, data.get("ok"),
            )
            break

        cards = (data.get("data") or {}).get("cards") or []
        mblogs = [c.get("mblog") for c in cards
                  if isinstance(c, dict) and isinstance(c.get("mblog"), dict)]
        if not mblogs:
            break
        for mb in mblogs:
            mid = str(mb.get("id") or "")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            parsed = parse_mblog(mb)
            if parsed is not None:
                out.append(parsed)

        if len(out) >= want:
            break

    logger.info("[weibo] 用户 %s 的微博 -> %d 条", uid, len(out))
    return out[:want]


async def get_user_via_patchright(
    uid: str,
    *,
    conn_key: str = "",
    client=None,
) -> Optional[UserProfile]:
    """取微博用户资料。

        GET /api/container/getIndex?containerid=100505{uid}
        → data.userInfo{...}

    与 MediaCrawler `get_creator_info_by_id` 一致（实测确认）。
    """
    from .apis import build_user_detail_params

    session = await _get_session(conn_key, client=client)
    raw = await session.page.evaluate(JS_SEARCH, {"params": build_user_detail_params(uid)})
    data = _load_json(raw, "用户详情")

    info = (data.get("data") or {}).get("userInfo")
    if isinstance(info, dict):
        return parse_user(info)

    # 有些形态把资料放在 cards[].user
    for card in ((data.get("data") or {}).get("cards") or []):
        for user in _iter_card_users(card):
            parsed = parse_user(user)
            if parsed is not None:
                return parsed
    logger.info("[weibo] 用户详情 uid=%s 未取到", uid)
    return None


async def get_self_profile_via_patchright(
    *,
    conn_key: str = "",
    client=None,
) -> Optional[UserProfile]:
    """取**自己**的资料。

    ## ⚠️ 必须先确认登录，否则会拿到"别人的资料"（实测踩过）

    微博**没有**"我是谁"的接口：

        /api/config          → 只有 {login, st, user_token, ...}，**没有 uid**
        /api/profile/me      → 404
        /api/myProfile       → 404

    MediaCrawler 也一样 —— 它的 `creator_id` 是**配置项**，不是自动发现的。

    所以只能从页面里找 uid。**但这里有个大坑**：
    未登录时首页是**推荐流**，页面里的 `/profile/{uid}` 链接全是
    **别的用户**。我第一版直接抓第一个链接，于是拿到一个大 V 的资料，
    还以为是"我自己"（实测未登录时抓到 uid=7918597670「蓟海棠」，
    275 万粉 —— 那是个真实博主，绝不是登录用户）。

    **所以现在先查 `/api/config` 的 `login`：为 false 就直接返回 None。**
    宁可不给，也不能给错人的资料 —— 后者比"没有数据"危险得多。
    """
    session = await _get_session(conn_key, client=client)

    # 1) 先确认登录（否则下面抓到的 uid 一定是别人的）
    try:
        raw = await session.page.evaluate(JS_CHECK_LOGIN)
        config = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:
        logger.warning("[weibo] 查询登录态失败：%s", exc)
        return None

    if not (config.get("data") or {}).get("login"):
        # ⚠️ **抛可操作错误，不能静默返回 None**（2026-09-30）
        #
        # 原来只 `logger.info` + `return None` —— 用户看到**空白**，
        # 不知道是"没登录"还是"接口坏了"。
        #
        # ⚠️ 而且**必须登录才继续**：未登录时页面里的 `/profile/{uid}`
        # 全是**别的用户**（实测抓到 uid=7918597670「蓟海棠」275万粉），
        # 继续下去会拿到**别人的资料** —— 那比没有数据危险得多。
        logger.info(
            "[weibo] 未登录 —— 「我的数据」需要登录后才能确定身份"
            "（未登录时页面里的 /profile/ 链接都是别的用户，不能拿来当自己）"
        )
        raise LoginExpiredError(
            "[weibo] 未登录 —— 「我的数据」必须先登录才能确定身份。\n"
            "⚠️ 微博的**搜索不需要登录**（Service Worker 上下文），"
            "所以「搜索能用」不等于「已登录」。\n"
            "请在「账号中心」重新获取微博登录态（注意要在 **m 站**登录："
            "主站的登录态在 m.weibo.cn 无效，实测 `/api/config` 返回 "
            "login=False）。"
        )

    # 2) 已登录才从页面找自己的 uid
    uid = await session.page.evaluate(JS_FIND_SELF_UID)
    if not uid:
        logger.info("[weibo] 已登录但未能从页面取到自己的 uid")
        return None
    return await get_user_via_patchright(str(uid), conn_key=conn_key)


# =============================================================================
# 辅助
# =============================================================================

def _load_json(raw: Any, label: str) -> Dict[str, Any]:
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"[weibo] {label}响应解析失败：{exc}") from exc

    if isinstance(data, dict) and data.get("_error"):
        raise RuntimeError(
            f"[weibo] {label}返回非 JSON（{data.get('_error')}，HTTP {data.get('http')}）。"
            f"响应开头：{str(data.get('head'))[:80]}。"
            "通常是 Service Worker 未就绪或登录态失效。"
        )
    ok = data.get("ok") if isinstance(data, dict) else None
    if ok == -100:
        raise RuntimeError("[weibo] 未登录（ok=-100）。请在「账号中心」保存微博登录态。")
    return data


def _iter_card_users(card: Any):
    """从一张卡片里迭代出所有 user 对象。

    实测用户卡片的形状：
        {card_type: 11, card_group: [{user: {...}}, ...]}
    也有直接把 user 放在卡片顶层的。
    """
    if not isinstance(card, dict):
        return
    group = card.get("card_group")
    if isinstance(group, list):
        for sub in group:
            if isinstance(sub, dict) and isinstance(sub.get("user"), dict):
                yield sub["user"]
    if isinstance(card.get("user"), dict):
        yield card["user"]


# 查登录态（`/api/config` 的 `login` 字段）。
#
# ⚠️ **「我的数据」必须先查这个** —— 未登录时页面里全是别人的
# /profile/ 链接，直接抓会拿到"别人的资料"（实测踩过）。
JS_CHECK_LOGIN = """
async () => {
  try {
    const r = await fetch('https://m.weibo.cn/api/config', { credentials: 'include' });
    return await r.text();
  } catch (e) {
    return JSON.stringify({ _error: String(e).slice(0, 80) });
  }
}
"""


# 从页面找自己的 uid。
#
# ⚠️ **只在已登录时才可信**（未登录时是推荐流的其他用户）。
JS_FIND_SELF_UID = """
() => {
  // 1) 页面链接里的 /u/{uid} 或 /profile/{uid}
  for (const a of document.querySelectorAll('a[href]')) {
    const h = a.getAttribute('href') || '';
    const m = h.match(/\\/(?:u|profile)\\/(\\d{6,})/);
    if (m) return m[1];
  }
  // 2) 页面全局变量里的 uid（微博 H5 有 $render_data）
  try {
    const rd = window.$render_data;
    if (rd) {
      const s = JSON.stringify(rd);
      const m = s.match(/"uid"\\s*:\\s*"?([0-9]{6,})"?/);
      if (m) return m[1];
      const m2 = s.match(/"id"\\s*:\\s*"?([0-9]{8,})"?/);
      if (m2) return m2[1];
    }
  } catch (e) {}
  // 3) 页面 HTML 里的 "uid":xxx
  try {
    const m = document.documentElement.innerHTML.match(/"uid"\\s*:\\s*"?([0-9]{8,})"?/);
    if (m) return m[1];
  } catch (e) {}
  return '';
}
"""


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
