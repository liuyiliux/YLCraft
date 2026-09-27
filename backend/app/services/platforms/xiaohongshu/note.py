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

# 已失效端点，仅作历史记录（见模块 docstring）
DEAD_V1_ENDPOINT = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"


async def get_detail_via_api(
    client,
    item_id: str,
) -> Optional[NoteDetail]:
    """API 模式：显式报错，不静默返回 None。

    原实现会真的去请求已失效的 `edith…/v1/feed`，失败后 `return None`，
    调用方只看到"没拿到详情"，完全不知道是端点废弃。
    """
    raise RuntimeError(
        "[xhs] API 模式已停用：edith.xiaohongshu.com/api/sns/web/v1/feed "
        "已失效（实测 code:300011，缺 X-s/X-t 签名被风控拒）。"
        "请改用 patchright 模式获取详情。"
    )


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
        if token:
            url += f"?xsec_token={token}&xsec_source="

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

            # 滚动触发懒加载（实测部分图在滚动后才出现）
            for _ in range(3):
                await session.page.evaluate("() => window.scrollBy(0, 600)")
                await session.page.wait_for_timeout(1200)

            raw = await session.page.evaluate(JS_PARSE_NOTE)
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
        // 页面内的 token 会比 URL 里那个新（实测会轮换）
        tokenInPage: (document.documentElement.innerHTML
            .match(/xsec_token=([A-Za-z0-9_\-]+)/) || [])[1] || '',
    });
}
"""


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
        raw_data=data,
    )


def parse_note_detail(data: Dict[str, Any]) -> NoteDetail:
    """解析 API 模式的笔记详情（**保留给历史调用方**）。

    ⚠️ API 模式已失效（见模块 docstring），这个函数现在只被测试引用。
    新代码请用 `parse_note_dom`。

    注意原来取的是 `url_default`（**缩略图**）——已改为优先取原图字段
    （`url_default` → `url` → `info_list` 里的最大尺寸）。
    """
    note_card = data.get("note_card", {})
    note_id = note_card.get("note_id", "")
    title = note_card.get("display_title", "")
    desc = note_card.get("desc", "")

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
        video_url = video_info.get("url", "")

    return NoteDetail(
        id=note_id,
        title=title,
        desc=desc,
        author=author,
        author_id=author_id,
        platform="xiaohongshu",
        type="video" if video_url else ("note" if type_str == "normal" else type_str),
        images=images,
        video=video_url,
        video_cover=cover,
        likes=likes,
        comments=comments,
        shares=shares,
        collects=collects,
        raw_data=data,
    )


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


def parse_count(s: str) -> int:
    """'2.3万' -> 23000；'1128' -> 1128。"""
    s = (s or "").strip()
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100000000)
        return int(s)
    except (ValueError, TypeError):
        return 0
