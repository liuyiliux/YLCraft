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
    """在浏览器里搜微博。

    ## ⚠️⚠️ 翻页：**只能可靠地取第 1 页**（2026-10-04 实测，**已确认登录态**）

    ### ⚠️ 先确认登录态，否则结论作废

    我在这个功能上翻过两次车，都是因为**没先验登录态**：

      ① 手工测试脚本**没加载 `.env`** → `database.py:26` 的 localhost 兜底生效
         → 注入 cookie 失败 → **访客态** → 测出"page=2 返回 ok=-100"
         → 我把"访客没权限"当成"平台没数据"
      ② 判据也看错位置：`/api/config` 的 `login`/`uid` 在 **`data`** 里，
         不在顶层 → 打出"login=None"误判成未登录

    **正确验法**（`JS_CHECK_LOGIN`，项目里已有）：

        {"data":{"login":true,"uid":"7628413874", ...}, "ok":1}
                            ↑ 在 data 里，不在顶层

    本次实测：login=**true**、uid=**7628413874**、cookie 注入 3776 字符、
    页面里的 uid 与之一致 ⇒ **真登录态**。

    ### 访客态 vs 登录态：**完全是两回事**

    |            | `page=2` 返回                                   |
    | ---------- | ----------------------------------------------- |
    | 访客态     | `ok=-100` + `passport.weibo.com/sso/signin` URL  |
    | **登录态** | **`ok=1`** + **0 条**（正常受理，只是没内容）    |

    ⚠️ 混在一起看必然误判 —— 这就是我出错的根源。

    ### 登录态下的实测（3 关键词 × page 1/2/3）

        营口   page=1: 14 条     page=2: ok=1  0 条
        沈阳   page=1:  9 条     page=2: ok=1  0 条
        美食   page=1:  9 条     page=2: ok=1  0 条

    ⇒ **微博搜索只有 1 页。** 想要更多，上层用**更大的 `max_results`
    重新搜一次**（前端「加载更多」，与抖音同款）。**不是**页码翻页。

    ### 一页给 9~14 条，不固定

    所以"每页 10 条"可能给 9 条、给 14 条 —— **不是 bug**，是平台行为。

    ### `has_more` 的含义

    **"调大每页条数能不能拿到更多"** —— 不是"有没有第 2 页"。
    判据靠**实际试**：循环是否因"取满 want"而提前结束
    （`_stopped_by_want`）。取满了 → 可能还有；少于 want → 平台到顶。

    ## ⚠️ 与 `meta.py` 的 `weibo → PAGED` **矛盾**（原因未定）

    `meta.py` 那条基于 2026-10-03 实测（p2 有 17~20 条），
    今天登录态、访客态都测不出 —— **三个结论互不相同**。

    可能原因（**未验证，不当结论写**）：微博侧变更、时段限流。
    **没查清前不改架构** —— 宁可少给，不给"点了没反应"的翻页按钮。
    想改的话先复验 `meta.py` 里那张实测表。

    ### `ok=-100` 的防御（将来若恢复翻页仍需要）

    实测（访客态）：
        page=1 → ok=1     160KB 真实数据
        page=2 → ok=-100  {"url": "passport.weibo.com/sso/signin"}

    此时必须**保留第 1 页结果、停止翻页**，不能整体抛错 ——
    否则每次搜索都会失败，连有效的第 1 页都看不到。
    """
    want = max(1, params.max_results or 20)
    # ⚠️ `SearchParams.search_type` 是 **SearchType 枚举**（默认 NOTE），
    # 直接 str() 会得到 "SearchType.NOTE" 而不是 "note"。
    # 这里取 `.value` 再交给 resolve_search_type。
    raw_st = getattr(params, "search_type", "") or "note"
    search_type = str(getattr(raw_st, "value", raw_st))

    session = await _get_session(conn_key, client=client)
    out: List[SearchResult] = []
    seen: set[str] = set()

    # ⚠️⚠️ 翻页：**只取第 1 页**（2026-10-04 实测，**已确认登录态**）
    #
    # ## 实测前提（这一步之前漏了，导致结论作废过一轮）
    #
    #     /api/config → **login=true, uid=7628413874**
    #     注入 cookie 成功（3776 字符），页面 uid 与之一致
    #     ⇒ 测的是**真登录态**，不是访客态
    #
    # ## 实测（登录态下，3 个关键词 × page 1/2/3）
    #
    #     营口   page=1: ok=1  14 条     page=2: **ok=1**  0 条
    #     沈阳   page=1: ok=1   9 条     page=2: **ok=1**  0 条
    #     美食   page=1: ok=1   9 条     page=2: **ok=1**  0 条
    #
    # ⚠️ 关键细节：`ok=1`（**不是** `ok=-100`）—— 请求被**正常受理**了，
    # 只是那一页真的没有内容。
    #
    # ⚠️ 与访客态**完全是两回事**：
    #     访客态  page=2 → ok=-100 + passport 登录页 URL
    #     登录态  page=2 → ok=1    + 0 条
    # 混在一起看，会把"访客没权限"误当成"平台没数据" ——
    # 我就这么归因错过一次（访客态测的 0 条，被我当成平台限制）。
    #
    # ## 另外两个事实
    #
    #   · 给多少由 **`max_results`** 决定，不是 `page`
    #     （page=1，max 从 10 → 20，条数 10 → 14）
    #   · `since_id` 游标自己翻 → **不稳定**，实测反而变少
    #     营口 5/10/15/**14**   沈阳 5/10/**9**/**9**（调大反而少）
    #     游标页与第 1 页有重叠 —— 不可用。
    #
    # ⇒ 微博搜索**只有 1 页**。想要更多，上层用**更大的 `max_results`
    #   重新搜一次**（前端「加载更多」那条路，与抖音同款）。
    #
    # ⚠️ `meta.py` 里 `weibo → PAGED` 与此**矛盾**
    #   （那条基于 2026-10-03 实测 p2 有 17~20 条）。
    #   今天登录态、访客态都测不出 —— **三个结论互不相同**，
    #   在查清前不改架构：宁可少给，不给"点了没反应"的翻页按钮。
    pages_to_try = 1
    _stopped_by_want = False
    pages_fetched = 0
    _since_id: Any = None
    _best = 0

    for i in range(pages_to_try):
        qp = build_search_params(
            keyword=params.keyword,
            page=1,
            since_id=_since_id,
            search_type=search_type,
        )
        try:
            raw = await session.page.evaluate(JS_SEARCH, {"params": qp})
        except Exception as exc:
            logger.warning("[weibo] 搜索页 evaluate 失败（第 %d 页）：%s", page + i, exc)
            break

        pages_fetched = i + 1

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
            # ⚠️⚠️ **已有第 1 页结果时，这里必须停而不是抛错**（2026-10-04 改）
            #
            # 实测（访客态 / 登录态失效）：
            #     page=1 → ok=1   160KB 真实数据（9~10 条）
            #     page=2 → ok=-100  {"url":"passport.weibo.com/sso/signin"}
            #
            # 原来无条件 `raise` → 上面刚改成"要试第 2 页"之后，
            # **每次搜索都会失败**，连本来有效的第 1 页都看不到。
            # 那是把"取不到更多"变成"什么都取不到"，比原来更糟。
            #
            # 正确处置：第 1 页有效就**保留它**，停止翻页，
            # 并**如实告诉用户**"翻页需要登录"（不是假装"就这些了"）。
            if out:
                logger.info(
                    "[weibo] 第 %d 页要求登录（ok=-100），已有 %d 条，停止翻页",
                    page + i, len(out),
                )
                break
            raise RuntimeError(
                "[weibo] 未登录（ok=-100）。请在「账号中心」保存微博登录态后重试。"
            )

        cards = ((data.get("data") or {}).get("cards") or []) if isinstance(data, dict) else []
        mblogs = [
            c.get("mblog") for c in cards
            if isinstance(c, dict) and c.get("card_type") == 9
            and isinstance(c.get("mblog"), dict)
        ]
        if not mblogs:
            break

        # ⚠️ **抓 since_id 游标**（2026-10-04 实测：微博搜索翻页靠它，
        # `page` 参数无效 —— page=2 恒返回 0 条）
        #
        # 优先用响应给的 `data.cardlistInfo.since_id`；
        # 拿不到就用**本页最后一条的 mid** 兜底（微博游标就是 id 序列）。
        _card_info = ((data.get("data") or {}).get("cardlistInfo") or {}) \
            if isinstance(data, dict) else {}
        _since_id = _card_info.get("since_id") or _card_info.get("sinceId")
        if not _since_id:
            _last = (mblogs[-1] or {}).get("mid") or (mblogs[-1] or {}).get("id")
            _since_id = str(_last) if _last else None

        for mb in mblogs:
            parsed = parse_mblog(mb)
            if parsed is None or parsed.id in seen:
                continue
            seen.add(parsed.id)
            out.append(parsed)
        if len(out) >= want:
            # 被 want 截断 —— 说明**后面可能还有**
            # （has_more 要靠这个标记，不能用 `len(out) >= want` 反推）
            _stopped_by_want = True
            break
        if not _since_id:
            break        # 没有游标 = 翻不动了
        # ⚠️ "结果不许变少"保护（实测游标翻页会回退，见上方注释）
        if len(out) <= _best:
            logger.info("[weibo] 游标翻页未带来新条目（%d → %d），回滚并停止",
                        _best, len(out))
            out = out[:_best]
            break
        _best = len(out)

    # ⚠️ **给前端 `_has_more`**（2026-09-29 补，2026-10-03 修）
    #
    # 原来**写死 False**，理由是 2026-09-29 的实测：
    #     page=2 返回 173 字节 HTML 错误页，cardlistInfo.since_id 为 None
    # 于是"平台没有第 2 页"被当成结论固化进了代码。
    #
    # ⚠️ **但那个结论今天（2026-10-03）实测已不成立** —— 微博搜索**能翻页**：
    #
    #     page=1  10 条  ['5344437661075159', '5344073515796857', ...]
    #     page=2  10 条  ['5349942244934068', '5349941822098505', ...]
    #     page=3  10 条
    #     page1 ∩ page2 = **0 个**   ← 真实翻页，不是重复数据
    #
    # ⚠️⚠️ **但 2026-10-04 又实测推翻了一次**（见上方 docstring）：
    #     page=2 恒返回 **0 条**，page 参数对微博搜索**无效**；
    #     真正决定给多少的是 `max_results`，且有平台上限。
    #     所以现在只取第 1 页（pages_to_try = 1）。
    #
    # ## `has_more` 现在的含义：**调大"每页条数"能不能拿到更多**
    #
    # 判据（实测得出，不是猜）：
    #     拿到的条数 == want  → 可能还有（用户调大每页条数能再要）
    #     拿到的条数 <  want  → 平台就到顶了
    #
    # 为什么不用 `len(out) >= want` 直接算 —— 那正是这个：
    # 一页给 9~10 条不固定，want=10 时第 1 页给 9 条 → `9 >= 10` False
    # → has_more=False → 前端不给"加载更多"，而调大条数其实能多拿。
    # 与其拿条数去猜，**直接试**才知道 —— 所以 `_stopped_by_want`
    # 记录的是"循环是否因取满 want 而提前结束"。
    if out:
        out[0].raw_data["_has_more"] = _stopped_by_want

    logger.info(
        "[weibo] 搜索 %r -> %d 条（patchright，翻了 %d/%d 页，has_more=%s）",
        params.keyword, len(out), pages_fetched, pages_to_try,
        out[0].raw_data.get("_has_more") if out else False,
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
