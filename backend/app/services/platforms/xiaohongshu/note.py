"""YLCraft — 小红书笔记详情

## 实测结论（2026-09-27）

### API 模式已不可用

`edith.xiaohongshu.com/api/sns/web/v1/feed` 实测返回
`{"code":300011,"msg":"当前账号存在异常…"}`——本质是缺 `X-s`/`X-t` 签名被风控拒，
不是账号真有问题（同一 Cookie 在浏览器里一切正常）。
签名函数 `window._webmsxyw` 是混淆 JS、跨域调用实测 406。

**所以详情必须走 Patchright**（浏览器打开笔记页读渲染结果），
与搜索同一策略。

### 浏览器模式：图片能直接从 DOM 拿

打开笔记页后，图片由页面自己从 CDN 加载：
    `sns-webpic-qc.xhscdn.com/.../notes_pre_post/...`
所以**不需要任何签名接口**，读 DOM 即可。

图集容器（实测命中）：
    `.swiper-slide img` / `[class*=slider] img` / `[class*=media] img`

### ⚠️ 必须带 xsec_token

不带 token 访问 `/explore/{id}` 会显示「当前笔记暂时无法浏览」；
带 token 则正常渲染（两种路径都行：`/explore/{id}` 与 `/search_result/{id}`）。

token 来自搜索结果，且**会轮换**（实测 URL 里是 `AB128Hnm…`，
页面内已是 `AB0eZ6W7…`），所以它有时效性，不能长期缓存。

### 实测提取结果

    标题：168cm/180斤古早波点穿搭和日落也太配了叭！
    作者：禾子盒盒
    图片：3 张（去重后）

### 一个排查陷阱

探测时曾看到页面显示「手机号登录」，误判为登录态失效。
实际是**多个残留 Chrome 进程占着同一个持久化 profile**（12 个），
导致新会话打开的是旧窗口、状态错乱。清理进程后一切正常。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..types import NoteDetail

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.note")

# 调详情接口时用的 UA（与签名里的 UA 保持一致，避免风控对不上）
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

# 详情接口：**纯 HTTP**（实测 2026-09-29 打通）
FEED_URI = "/api/sns/web/v1/feed"
EDITH_BASE = "https://edith.xiaohongshu.com"

# 已失效端点，仅作历史记录（见模块 docstring）
DEAD_V1_ENDPOINT = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"


async def get_detail_via_api(
    client,
    item_id: str,
    **kwargs,
) -> Optional[NoteDetail]:
    """**纯 HTTP 取笔记详情**（不开浏览器）—— 2026-09-29 实测打通。

    ## 这个端点一直都在，之前只是缺签名

    本函数原来是"显式报错"，注释写着：

        edith.xiaohongshu.com/api/sns/web/v1/feed 已失效
        （实测 code:300011，缺 X-s/X-t 签名被风控拒）

    **端点从来没失效** —— 是当时没有签名能力。现在我们有了
    `xhshow`（搜索接口一直在用），加上签名后实测：

        POST https://edith.xiaohongshu.com/api/sns/web/v1/feed
        body = {"source_note_id": "...", "xsec_token": "..."}
        → HTTP 200, success=True, data.items[0].note_card

    返回的数据**比浏览器 DOM 路径更全**：
        title / desc / type(normal|video) / time / ip_location
        user{nickname, user_id, avatar}
        interact_info{liked_count, collected_count,
                      comment_count, share_count}
        image_list[{url_default, width, height}]   ← 全部图片+原图分辨率
        video.media.stream.{h264,h265,av1,EF4..EF7} ← 多档清晰度
        tag_list[{name}]                            ← 话题

    ## ⚠️ `xsec_token` **必需**

    实测不带 token → **HTTP 461**。token 从搜索结果里拿。

    ## 实测

        单图笔记 → 标题/描述/作者/互动/话题全有，1440x1920 原图
        多图笔记 → 图片 3 张（全拿到）
        视频笔记 → video stream EF4~EF7 四档清晰度
    """
    import json as _json

    import httpx

    from app.services.platforms.xiaohongshu.signing import sign_post

    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    if not cookie:
        raise RuntimeError(
            "[xhs] 获取笔记详情需要登录 Cookie：请先保存小红书连接。"
        )

    token = (kwargs or {}).get("xsec_token") or ""
    if not token:
        # 从调用方给的 url 里再捞一次
        from urllib.parse import parse_qs, urlparse

        u = (kwargs or {}).get("url") or ""
        if u:
            token = (parse_qs(urlparse(u).query).get("xsec_token") or [""])[0]
    if not token:
        raise RuntimeError(
            "[xhs] 缺少 xsec_token —— 详情接口必需（实测缺失会返回 HTTP 461）。"
            "请从搜索结果里带上该笔记的 xsec_token。"
        )

    uri = FEED_URI
    body = {
        "source_note_id": item_id,
        "xsec_token": token,
        "xsec_source": "pc_feed",
    }
    # ⚠️ `/feed` 属于**风控接口**，需要 `x-rap-param` 头
    # （xhshow README 明写：feed / 搜索 / 笔记发布等需要）。
    # 实测不带也能过（HTTP 200），但带上更稳 —— 风控策略会变。
    signed = sign_post(uri, cookie, body, x_rap=True)
    headers = {
        "user-agent": _UA,
        "origin": "https://www.xiaohongshu.com",
        "referer": f"https://www.xiaohongshu.com/explore/{item_id}",
        "content-type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cookie": cookie,
    }
    headers.update(signed)

    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        resp = await c.post(f"{EDITH_BASE}{uri}", json=body, headers=headers)

    if resp.status_code == 461:
        raise RuntimeError(
            "[xhs] 详情接口返回 HTTP 461 —— 通常是 `xsec_token` 无效或过期。"
            "请重新搜索该笔记以获取新的 token。"
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"[xhs] 详情接口返回 HTTP {resp.status_code}。"
            f"（body 前 120：{resp.text[:120]!r}）"
        )

    payload = _json.loads(resp.text)
    if not payload.get("success"):
        raise RuntimeError(
            f"[xhs] 详情接口返回失败：code={payload.get('code')} "
            f"msg={payload.get('msg')!r}"
        )
    items = (payload.get("data") or {}).get("items") or []
    if not items:
        logger.info("[xhs] 详情接口未返回 items（id=%s）", item_id)
        return None

    note_card = items[0].get("note_card") or {}
    if not note_card:
        return None
    return parse_note_detail({"note_card": note_card})


async def get_detail_via_patchright(
    client,
    item_id: str,
    **kwargs,
) -> Optional[NoteDetail]:
    """通过 Patchright 打开笔记页，读渲染后的数据。

    流程：预热首页 → 打开笔记页 → 等图集渲染 → 读 DOM。

    **预热是必须的**（与搜索同一个坑）：直接打开笔记页会拿不到内容。
    """
    from app.services.browser.patchright_runtime import get_patchright_runtime
    from .search_patchright import _warmup

    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    if not cookie:
        raise RuntimeError(
            "[xhs] 获取笔记详情需要登录 Cookie：请先保存小红书连接。"
        )

    # 调用方可传原链接（含 xsec_token）。没有就用 /explore/{id}。
    url = (kwargs or {}).get("url") or ""
    token = (kwargs or {}).get("xsec_token") or ""
    if not url:
        url = f"https://www.xiaohongshu.com/explore/{item_id}"
    # ⚠️ **必须保证 URL 带上 xsec_token**（2026-09-29 修正）
    #
    # 我之前判断"详情不能直接 goto、必须站内点击" —— **那个结论是错的**。
    # 实测（用户给出的链接）：
    #
    #     explore/{id}?xsec_token=xxx&xsec_source=pc_feed → ✅ 直接进详情
    #     search_result/{id}?xsec_token=xxx               → ✅ 也进详情
    #     explore/{id}（**不带 token**）                   → ❌ 跳回首页
    #
    # 即：**能不能直接访问，取决于有没有有效的 `xsec_token`**，
    # 与"站内点击"无关。我当时用的是没有 token 的 URL，把因果搞反了。
    #
    # 所以现在：URL 缺 token 就补上（调用方单独传了 token 的情况）。
    if token and "xsec_token=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}xsec_token={token}&xsec_source=pc_feed"

    conn_id = getattr(getattr(client, "config", None), "conn_id", "") or ""
    from app.services.platforms.session_pool import PooledSession, get_session_pool

    pool = get_session_pool()
    session_key = f"xhs|{conn_id or '-'}"

    async with pool.lock_for(session_key):
        session = pool.get(session_key)
        if session is None:
            runtime = get_patchright_runtime()
            ctx = await runtime.new_context(
                headless=False, viewport={"width": 1440, "height": 900},
            )
            pairs = [p for p in cookie.split("; ") if "=" in p]
            if pairs:
                await ctx.add_cookies([
                    {
                        "name": p.split("=", 1)[0],
                        "value": p.split("=", 1)[1],
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                    }
                    for p in pairs
                ])
            page = await ctx.new_page()
            session = PooledSession(ctx=ctx, page=page)
            pool.put(session_key, session)
            logger.info("[xhs] 新建浏览器会话（详情）key=%s", session_key)

        try:
            if not session.warmed:
                await _warmup(session.page)
                session.warmed = True
            session.touch()

            # ✅ **直接 goto 带 xsec_token 的链接**（2026-09-29 修正）
            #
            # ⚠️ 我之前写的是"必须站内点击，不能直接 goto"——**那是错的**。
            #
            # 我当时的实测（用**没有 token** 的 URL）：
            #     goto explore/{id}（不带 token）  → 跳回 /explore
            #     goto search_result/{id}（旧 token）→ 300017 安全限制
            # 于是误判成"小红书禁止直接访问详情"。
            #
            # 用户给出的链接（**带有效 token**）实测：
            #     explore/{id}?xsec_token=xxx&xsec_source=pc_feed → ✅ 直接进详情
            #     search_result/{id}?xsec_token=xxx               → ✅ 也进详情
            #
            # **决定性因素是有没有有效 `xsec_token`，不是"站内点击"。**
            #
            # 所以现在直接 goto —— 比"搜索→点击"快得多（省掉搜索页加载
            # 的十几秒），也不会因为"目标不在搜索结果里"而失败
            # （用户日志里就是这个：搜索"沈阳吊带"的结果里没有那条笔记）。
            try:
                await session.page.goto(
                    url, wait_until="domcontentloaded", timeout=60000
                )
            except Exception as exc:
                raise RuntimeError(
                    f"[xhs] 打开笔记页超时：{type(exc).__name__}。"
                    "通常是 Cookie 失效或平台限流。"
                ) from exc

            # 等图集/正文渲染
            try:
                await session.page.wait_for_selector(
                    ".swiper-slide img, [class*=media] img, video", timeout=15000
                )
            except Exception:
                logger.warning("[xhs] 等待图集超时，按当前 DOM 继续")
            await session.page.wait_for_timeout(2500)

            # 先确认在详情页再滚动 —— 否则滚的是首页推荐流
            on_detail = await session.page.evaluate(
                "() => !!document.querySelector('#noteContainer')"
            )
            if on_detail:
                # 滚动触发懒加载（实测部分图在滚动后才出现）
                for _ in range(3):
                    await session.page.evaluate("() => window.scrollBy(0, 600)")
                    await session.page.wait_for_timeout(1200)
            else:
                logger.warning("[xhs] 未在详情页，跳过滚动")

            raw = await session.page.evaluate(JS_PARSE_NOTE)

            # ⚠️ **必须校验真的进了详情页**（实测 2026-09-28）
            #
            # 用户反馈"详情显示了但没啥内容、多页只显示一页"。
            #
            # 原因：站内点击失败后会退回 `goto`，而 goto **会被安全策略拦**
            # —— 页面停在首页/错误页，但代码仍继续读 DOM，于是拿到**首页的
            # 空数据**，再被 parse 成一个"看起来成功"的 NoteDetail
            # （success=True、images=[]、标题是首页里的某个文本）。
            #
            # **谎报成功比直接失败更糟**：用户看到"获取成功"却没有内容，
            # 完全不知道哪里出了问题。
            #
            # 所以这里显式检查 #noteContainer：不在详情页就直接抛错。
            on_detail = await session.page.evaluate(
                "() => !!document.querySelector('#noteContainer')"
            )
            if not on_detail:
                raise RuntimeError(
                    "[xhs] 未能进入笔记详情页（可能被安全策略拦截）。"
                    "小红书详情必须『站内点击』打开；若从搜索结果进入，"
                    "请带上当时的搜索关键词（详情接口支持 keyword 参数）。"
                )
            session.touch()
        except Exception:
            await pool.close(session_key)
            raise

    import json as _json

    data = _json.loads(raw)
    if data.get("notFound"):
        raise RuntimeError(
            "[xhs] 笔记无法浏览（可能需要 xsec_token，或笔记已删除/私密）。"
            "若从搜索结果进入，请确保带上链接里的 xsec_token。"
        )
    return parse_note_dom(data, item_id)


# DOM 提取脚本（在页面上下文执行）
JS_PARSE_NOTE = r"""
() => {
    const pick = (sels) => {
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el && (el.innerText || '').trim()) return el.innerText.trim();
        }
        return '';
    };

    const bodyText = (document.body.innerText || '');

    // 图集：取 **swiper 轮播里的 slide 图** 并去重。
    //
    // 实测（2026-09-27）：
    //   · 主图在 `.swiper-slide img` 里
    //   · swiper 会生成 duplicate slide（同一张图出现两次），所以**必须去重**
    //   · 去重后数量与页面上的 "1/3" 图集指示器一致（实测 3 张 = 3 张）
    //
    // 踩过的坑：
    //   × `[class*=note] img` 太宽 → 把推荐流也算进来，3 图的笔记返回 40 张
    //   × 限定 `#noteContainer` 也不够 → 容器内含底部推荐流，仍 36 张
    const seen = new Set();
    const images = [];
    for (const img of document.querySelectorAll('.swiper-slide img, [class*=slide] img')) {
        const u = img.currentSrc || img.src || img.getAttribute('data-src') || '';
        if (!u || u.includes('avatar') || u.includes('fe-static')) continue;
        const base = u.split('?')[0];
        if (seen.has(base)) continue;
        seen.add(base);
        images.push(u);
    }

    // 页面上是否有图集指示器（用于交叉校验数量，取不到则忽略）
    const indicator = [...document.querySelectorAll('*')]
        .map(e => (e.children.length === 0 ? (e.innerText || '').trim() : ''))
        .find(t => /^\d+\s*\/\s*\d+$/.test(t)) || '';
    const indicatorTotal = indicator ? parseInt(indicator.split('/')[1], 10) : 0;

    const videos = [...document.querySelectorAll('video')]
        .map(v => v.src || v.currentSrc || '').filter(Boolean);

    // 互动数（点赞 / 收藏 / 评论）——2026-09-27 补
    //
    // 实测：`.engage-bar` 里是 **"点赞 收藏 评论" 三个数字连在一起**
    //       （例如 '1419 71 55' = 1419赞 / 71收藏 / 55评论）
    //       另外 `.like-wrapper` 单独给出点赞数（如 '1419' 或 '1.5万'）
    //
    // 注意：数字可能带"万"后缀（实测 '1.5万'），解析时要处理。
    const engage = (() => {
        const bar = document.querySelector('.engage-bar');
        if (!bar) return { likes: '', collects: '', comments: '' };
        // 只取直接的数字 span / 文本节点，排除"说点什么..."输入框等
        const nums = [];
        for (const el of bar.querySelectorAll('span, div, em')) {
            const t = (el.innerText || '').trim();
            if (!t) continue;
            if (/^[\d.,]+[万亿Kk]?$/.test(t)) nums.push(t);
        }
        // 去重后取前 3 个（赞/收藏/评论 顺序）
        const uniq = nums.filter((v, i) => nums.indexOf(v) === i);
        return {
            likes: uniq[0] || '',
            collects: uniq[1] || '',
            comments: uniq[2] || '',
        };
    })();
    const likeWrapper = (() => {
        const el = document.querySelector('.like-wrapper');
        return el ? (el.innerText || '').trim().replace(/\s+/g, '') : '';
    })();

    return JSON.stringify({
        notFound: bodyText.includes('暂时无法浏览') || bodyText.includes('当前笔记'),
        needsLogin: bodyText.includes('手机号登录') || bodyText.includes('登录后查看'),
        title: pick(['#detail-title', '[class*=note-title]', '[class*=title]']),
        desc: pick(['#detail-desc', '[class*=desc]', '[class*=content]']),
        author: pick(['.author-wrapper .username', '[class*=username]',
                      '[class*=author] [class*=name]']),
        images,
        indicator,
        indicatorTotal,
        videos,
        engage,
        likeWrapper,
        // 页面内的 token 会比 URL 里那个新（实测会轮换）
        tokenInPage: (document.documentElement.innerHTML
            .match(/xsec_token=([A-Za-z0-9_\-]+)/) || [])[1] || '',
    });
}
"""


# 在搜索页里点击目标笔记卡片（**站内跳转**）。
#
# 实测（2026-09-28）：小红书详情**必须站内点击进入** ——
# 直接 goto 详情 URL 会被安全策略拦（300017 / 跳回首页）。
#
# 做法：打开搜索页 → 找到 href 含目标 note_id 的卡片 → 点击 →
# 等详情渲染。
JS_CLICK_NOTE_CARD = """
(args) => {
  const id = args.id;
  // 搜索结果卡片
  for (const a of document.querySelectorAll('section.note-item a.cover')) {
    const href = a.getAttribute('href') || '';
    if (href.indexOf(id) >= 0) { a.click(); return true; }
  }
  // 兜底：任意带该 id 的链接
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (href.indexOf(id) >= 0) { a.click(); return true; }
  }
  return false;
}
"""


async def _open_note_by_click(page, item_id: str, fallback_url: str) -> bool:
    """通过"站内点击"打开笔记详情（返回是否成功）。

    ## ⚠️ 必须"先搜索到这条笔记，再点它"（2026-09-28 实测）

    直接 goto 详情 URL 会被安全策略拦：

        A) goto search_result/{id}?xsec_token=...  → /website-login/error
           「安全限制 访问链接异常 300017」
        B) goto explore/{id}?xsec_token=...        → 跳回 /explore
        C) goto explore/{id}                       → 跳回 /explore

    而**在搜索结果页点击卡片**能成功：

        点到 /search_result/6aa5401f...?xsec_token=ABRdMxcx...
        → 站内跳到 /explore/6aa5401f...?xsec_token=...
        → 详情容器=True，图集 3 张 ✅

    ## 三个要点（都是实测踩出来的）

    1. **必须在搜索页点**，不能在 `/explore` 首页找 ——
       首页是推荐流，几乎不可能正好有目标笔记
       （上一版栽在这里：找不到卡片 → 退回 goto → 被拦）。
    2. **点卡片自己的 href** —— 搜索结果的 href 带 `xsec_token`；
       自己拼 `/explore/{id}`（不带 token）会被弹回首页。
    3. **不能用笔记 id 当搜索词** —— 实测搜 id 返回 30 条**不相关**结果，
       里面没有目标笔记。所以用 `fallback_url` 里的原始关键词。
    """
    if not item_id:
        return False

    # 从原链接里取搜索关键词（前端传的是 search_result?keyword=xxx 这种）
    keyword = _keyword_from_url(fallback_url) or item_id

    try:
        # 先到首页拿会话上下文，再进搜索页
        await page.goto(
            "https://www.xiaohongshu.com/explore",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.wait_for_timeout(5000)

        import urllib.parse

        q = urllib.parse.quote(keyword)
        search_url = (
            f"https://www.xiaohongshu.com/search_result?keyword={q}"
            f"&source=web_explore_feed"
        )
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(10000)

        clicked = await page.evaluate(JS_CLICK_NOTE_CARD, {"id": item_id})
        if not clicked:
            logger.info(
                "[xhs] 搜索「%s」的结果里没找到笔记 %s 的卡片", keyword, item_id
            )
            return False

        # 等详情渲染（站内跳转有动画 + 网络请求）
        await page.wait_for_timeout(7000)

        # 校验真的进了详情（而不是被弹回首页）
        on_detail = await page.evaluate(
            "() => !!document.querySelector('#noteContainer')"
        )
        if not on_detail:
            logger.info("[xhs] 点击后未进入详情页（可能被弹回）")
            return False

        logger.info("[xhs] 已通过站内点击打开笔记 %s", item_id)
        return True
    except Exception as exc:
        logger.warning("[xhs] 站内点击打开笔记失败：%s", exc)
        return False


def _keyword_from_url(url: str) -> str:
    """从 `search_result?keyword=xxx` 这类 URL 里取搜索关键词。

    取不到返回空串（调用方会退化为用 id 搜，虽然多半搜不到）。
    """
    if not url:
        return ""
    try:
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        kw = (qs.get("keyword") or [""])[0]
        return kw.strip()
    except Exception:
        return ""


def parse_note_dom(data: Dict[str, Any], item_id: str) -> NoteDetail:
    """把 DOM 提取结果转成 NoteDetail。

    取不到的字段留空，**不编造**。

    会用页面上的 `1/3` 图集指示器**交叉校验**图片数量：
    两者不一致时记 warning（便于发现选择器又失效了），但不改数据——
    指示器是 UI 文案，图片列表才是实际拿到的。
    """
    images: List[str] = [u for u in (data.get("images") or []) if u]
    videos: List[str] = [u for u in (data.get("videos") or []) if u]
    title = data.get("title") or ""

    indicator_total = int(data.get("indicatorTotal") or 0)
    if indicator_total and len(images) != indicator_total:
        logger.warning(
            "[xhs] 图片数与页面指示器不一致：拿到 %d 张，指示器显示 %d 张"
            "（%s）。选择器可能又失效了，请检查 .swiper-slide img。",
            len(images), indicator_total, data.get("indicator"),
        )

    # 互动数：优先用 .engage-bar 的三个数字（赞/收藏/评论）。
    # 拿不到就退到 .like-wrapper 单独给的点赞数。
    engage = data.get("engage") or {}
    likes = parse_count(engage.get("likes"))
    if not likes:
        likes = parse_count(data.get("likeWrapper"))

    return NoteDetail(
        id=item_id,
        title=title,
        desc=data.get("desc") or title,
        author=data.get("author") or "",
        author_id="",  # DOM 里没有作者 id
        platform="xiaohongshu",
        type="video" if videos else "note",
        images=images,
        video=videos[0] if videos else "",
        video_cover=images[0] if images else "",
        likes=likes,
        comments=parse_count(engage.get("comments")),
        collects=parse_count(engage.get("collects")),
        raw_data=data,
    )


def parse_note_detail(data: Dict[str, Any]) -> NoteDetail:
    """解析 **API 模式**的笔记详情（`note_card`）。

    ## 这个函数现在是**主路径**（2026-09-29 重新启用）

    它一度被标为"已失效，只被测试引用" —— 因为当时以为
    `/api/sns/web/v1/feed` 端点废弃了。**实际是缺签名**
    （详见 `get_detail_via_api` 的说明）。加上 `xhshow` 签名后
    端点工作正常，所以这里重新成为主路径。

    注意原来取的是 `url_default`（**缩略图**）——已改为优先取原图字段
    （`url_default` → `url` → `info_list` 里的最大尺寸）。
    """
    note_card = data.get("note_card", {})
    note_id = note_card.get("note_id", "")
    # ⚠️ 实测 2026-09-29：字段是 `title`（不是 `display_title`）。
    # 老的 display_title 作为兜底保留。
    title = note_card.get("title") or note_card.get("display_title") or ""
    desc = (note_card.get("desc") or "").strip()

    user = note_card.get("user", {})
    author = user.get("nickname", "")
    author_id = str(user.get("user_id", ""))

    cover = note_card.get("cover", {}).get("url_default", "")

    interact_info = note_card.get("interact_info", {})
    likes = parse_count(interact_info.get("liked_count", "0"))
    comments = parse_count(interact_info.get("comment_count", "0"))
    shares = parse_count(interact_info.get("share_count", "0"))
    collects = parse_count(interact_info.get("collected_count", "0"))

    type_str = note_card.get("type", "normal")

    # 图片列表：优先原图字段
    images = []
    for img in note_card.get("image_list", []) or []:
        url = _pick_image_url(img)
        if url:
            images.append(url)

    video_url = ""
    video_info = note_card.get("video", {})
    if isinstance(video_info, dict) and video_info:
        video_url = _pick_video_url(video_info)

    # 发布时间（毫秒时间戳）与话题 —— API 路径能拿到，DOM 路径拿不到
    create_time = ""
    raw_time = note_card.get("time")
    if isinstance(raw_time, (int, float)) and raw_time > 0:
        try:
            from datetime import datetime, timezone

            create_time = datetime.fromtimestamp(
                raw_time / 1000, tz=timezone.utc
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            create_time = ""
    tags = [
        str(t.get("name"))
        for t in (note_card.get("tag_list") or [])
        if isinstance(t, dict) and t.get("name")
    ]

    return NoteDetail(
        id=note_id or "",
        title=title,
        desc=desc or title,
        author=author,
        author_id=author_id,
        platform="xiaohongshu",
        type="video" if video_url else ("note" if type_str == "normal" else type_str),
        images=images,
        video=video_url,
        video_cover=cover or (images[0] if images else ""),
        likes=likes,
        comments=comments,
        shares=shares,
        collects=collects,
        create_time=create_time,
        tags=tags,
        raw_data=data,
    )


def _pick_video_url(video_info: Dict[str, Any]) -> str:
    """从视频节点里挑**清晰度最好**的播放地址。

    实测 2026-09-29：视频地址在
        video.media.stream.{h264|h265|av1|EF4|EF5|EF6|EF7}[i].master_url

    `EF*` 是小红的自有编码档位（EF7 最高）。取第一个能用的即可 ——
    各档都有 master_url，播放器会自动适配。

    拿不到就返回空串（**不编造**）。
    """
    if not isinstance(video_info, dict):
        return ""

    # 老结构可能是平铺的 url
    direct = video_info.get("url")
    if isinstance(direct, str) and direct.startswith("http"):
        return direct

    media = video_info.get("media") or {}
    if not isinstance(media, dict):
        return ""
    stream = media.get("stream") or {}
    if not isinstance(stream, dict):
        return ""

    # 优先 h264/h265（通用性好），再退到 EF* 档位
    for key in ("h264", "h265", "av1", "EF7", "EF6", "EF5", "EF4"):
        arr = stream.get(key)
        if not isinstance(arr, list):
            continue
        for entry in arr:
            if not isinstance(entry, dict):
                continue
            u = entry.get("master_url") or entry.get("backup_urls")
            if isinstance(u, list):
                u = u[0] if u else ""
            if isinstance(u, str) and u.startswith("http"):
                return u
    return ""


def _pick_image_url(img: Dict[str, Any]) -> str:
    """从图片节点里挑**最大**的地址。

    小红书图片节点实测有多个字段，`url_default` 是缩略图（如 w/1080），
    `url` 常是原图。`info_list` 里则按尺寸列出多个候选。
    """
    if not isinstance(img, dict):
        return ""

    # info_list 里挑分辨率最高的
    best = ""
    best_px = -1
    for info in (img.get("info_list") or []):
        if not isinstance(info, dict):
            continue
        u = info.get("url") or ""
        if not u:
            continue
        px = 0
        for k in ("image_scene", "width", "height"):
            v = info.get(k)
            if isinstance(v, int):
                px = max(px, v)
        if px > best_px:
            best_px = px
            best = u
    if best:
        return best

    for key in ("url_default", "url", "url_pre", "trace_id"):
        u = img.get(key)
        if isinstance(u, str) and u.startswith("http"):
            return u
    return ""


# 计数解析**统一复用** `user.py` 里那份更完整的实现：
#   支持 "195" / "140.9万" / "2.9K" / "1.5亿" / 千分位逗号。
#
# ⚠️ 不要在这里再写第二份。曾经这里有个只支持"万/亿"的旧实现，
#    与 user.py 那份**行为不一致**（'2.9K' 在这边是 0，那边是 2900），
#    而 engage-bar / like-wrapper 都可能给带后缀的字符串。
from .user import parse_count  # noqa: F401  (本模块内部继续使用这个名字)
