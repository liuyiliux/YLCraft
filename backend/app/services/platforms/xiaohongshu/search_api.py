"""YLCraft — 小红书搜索（**纯 HTTP API**）

## 背景：又一次"端点失效"的误判（2026-09-29 修正）

`search_patchright.py` 的模块注释里写着：

    小红书搜索端点已从 `edith.../v1/search/notes` 迁移到
    `so.xiaohongshu.com/api/sns/web/v2/search/notes`（域名+版本都变了）。
    该接口需要 X-s/X-t 签名，签名函数 `window._webmsxyw` 是混淆 JS，
    Python 里重写签名不可行也不必要；用 Patchright 打开搜索页读 DOM。

**"Python 重写签名不可行"是当时的结论 —— 但现在有 `xhshow`（纯 Python
复现，搜索/详情都在用）。加上签名后实测：**

    POST https://edith.xiaohongshu.com/api/sns/web/v1/search/notes
    body = {"keyword", "page", "page_size", "search_id", "sort", "note_type"}
    → HTTP 200, success=True, data.items[20~21]

**端点根本没迁移，也一直可用。**

## 实测能力（2026-09-29）

| 能力 | 结果 |
|------|------|
| 分页 `page=1/2/3` | ✅ 三页首条各不相同 |
| 排序 `sort` | ✅ general / time_descending / popularity_descending |
| `note_type` 筛选 | ❌ **不生效**（0/1/2 返回相同结果，见下） |
| `search_id` | ⚠️ **必需**（传空串返回 0 条） |
| 速度 | ✅ **0.2~0.5 秒**（浏览器要 ~15 秒） |

## ⚠️ `note_type` 不生效（平台行为，不是我们的 bug）

实测 `note_type=0/1/2` 返回**完全相同**的结果，且所有卡片的
`note_card.type` 都是 `"normal"` —— 说明**搜索接口本身不下发
"图文/视频"这个信息**。

所以前端若要按类型筛选，只能本地过滤（但本地也判断不了，
因为 type 不可靠）—— **不要在 UI 上承诺这个筛选**。

## 返回结构

    data.items[] = {id, model_type, note_card, **xsec_token**}
    note_card = {
        display_title,      标题
        type,               恒为 "normal"（不可靠）
        user{nickname, user_id, xsec_token},
        interact_info{liked_count, collected_count, comment_count, shared_count},
        cover{width, height},
        image_list[{width, height, ...}],   ⚠️ 搜索卡片**不含图片 URL**
        corner_tag_info[{type: "publish_time", text: "02-10"}],  发布时间
    }

**关键**：`xsec_token` 就在 item 上 —— 直接喂给详情接口即可，
全链路（搜索 → 详情）纯 HTTP。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..types import SearchParams, SearchResult

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.search_api")

EDITH_BASE = "https://edith.xiaohongshu.com"
SEARCH_URI = "/api/sns/web/v1/search/notes"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

# 排序：实测三个都可用
SORT_ALIASES: Dict[str, str] = {
    "": "general",
    "default": "general",
    "general": "general",
    "综合": "general",
    "time": "time_descending",
    "latest": "time_descending",
    "time_descending": "time_descending",
    "最新": "time_descending",
    "popular": "popularity_descending",
    "hot": "popularity_descending",
    "popularity_descending": "popularity_descending",
    "最热": "popularity_descending",
}


def resolve_sort(sort_by: str) -> str:
    """把前端的排序别名映射成接口取值。"""
    return SORT_ALIASES.get((sort_by or "").strip().lower(), "general")


async def search_via_api(client, params: SearchParams) -> List[SearchResult]:
    """纯 HTTP 搜索小红书笔记。

    流程：签名 → POST → 解析 items。

    `xsec_token` 从 item 上取出来放进 `raw_data`，前端点详情时
    直接复用（详情接口必需它）。
    """
    from .signing import sign_post

    cookie = getattr(getattr(client, "config", None), "cookie", "") or ""
    if not cookie:
        raise RuntimeError(
            "[xhs] 搜索需要登录 Cookie：请先在「账号中心」保存小红书连接。"
        )

    keyword = params.keyword or ""
    if not keyword.strip():
        return []

    page = max(1, int(getattr(params, "page", 1) or 1))
    # ⚠️ **`page_size` 只能是 20**（2026-09-29 实测，非常重要）
    #
    # 小红书搜索接口对 `page_size` 做了硬校验 —— **只认 20**，
    # 其它任何值都返回 `{"has_more": false}`（**没有 items**，
    # 但 HTTP 200、`success: true`，看起来像"这个词没结果"）。
    #
    # 实测矩阵：
    #
    #     page_size= 1 / 5 / 10 / 15 / 30 / 50  →  items 为空
    #     page_size= 20                          →  22 条 ✅
    #
    # 这个坑很隐蔽：**状态码 200、success=true、msg="成功"**，
    # 完全看不出是参数问题。而前端默认"每页 10 条"正好踩中，
    # 表现为"小红书搜什么都没结果"。
    #
    # 所以这里**固定 20**，再按调用方要的条数截断。
    page_size = 20
    want = max(1, int(params.max_results or 20))
    sort = resolve_sort(getattr(params, "sort_by", "") or "")

    body: Dict[str, Any] = {
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
        "search_id": _make_search_id(),
        "sort": sort,
        # ⚠️ `note_type` 实测**不生效**（0/1/2 结果相同），
        # 这里固定传 0（全部），不要在 UI 上承诺类型筛选。
        "note_type": 0,
        # ⚠️ **必须带 `image_formats`，否则不返回图片 URL**（2026-09-29 实测）
        #
        # 不带这个参数时，`cover` / `image_list` **只有宽高、没有 URL**：
        #
        #     不带:              cover = {"height":1600, "width":1200}
        #     带 image_formats:  cover = {..., "url_default": "http://sns-webpic-qc..."}
        #
        # 后果是搜索列表**封面全空**（前端显示占位图）。
        # 加了之后实测 **20/20 条都有封面**。
        "image_formats": ["jpg", "webp", "avif"],
    }

    headers = {
        "user-agent": _UA,
        "origin": "https://www.xiaohongshu.com",
        "referer": "https://www.xiaohongshu.com/explore",
        "content-type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cookie": cookie,
    }
    # `/search/notes` 同属风控接口，带 `x-rap-param` 更稳
    headers.update(sign_post(SEARCH_URI, cookie, body, x_rap=True))

    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        resp = await c.post(f"{EDITH_BASE}{SEARCH_URI}", json=body, headers=headers)

    # ⚠️ **用统一的风控识别，而不是只看状态码**（2026-09-29）
    #
    # 实测这一条响应极具误导性：
    #
    #     HTTP 461，但 body 是 {"code":0,"success":true,"data":{}}
    #
    # **看着像"成功但没数据"** → 会被当成"没搜到"，
    # 而真相是 `Verifytype: 217`（人机验证）。
    # 另有 `code:300011`（账号异常）/ `300012`（IP 被封）等更具体的信号
    # —— 它们的**解法不同**（换账号 vs 换 IP），所以必须分开报。
    #
    # 见 `risk.py`（错误码表来源：MediaCrawler 实测归纳）。
    from .risk import detect_risk

    body_json = None
    try:
        body_json = resp.json()
    except Exception:
        body_json = None

    signal = detect_risk(
        status_code=resp.status_code,
        headers=dict(resp.headers),
        body=body_json,
    )
    if signal is not None:
        raise RuntimeError(f"[xhs] {signal.message()}")

    if resp.status_code != 200:
        raise RuntimeError(
            f"[xhs] 搜索接口返回 HTTP {resp.status_code}。"
            f"（body 前 120：{resp.text[:120]!r}）"
        )

    payload = body_json if isinstance(body_json, dict) else {}
    if not payload.get("success"):
        raise RuntimeError(
            f"[xhs] 搜索失败：code={payload.get('code')} "
            f"msg={payload.get('msg')!r}"
        )
    data = payload.get("data") or {}
    items = data.get("items") or []
    results = [r for r in (parse_item(it) for it in items) if r is not None]

    # ⚠️ 诊断：items 为 0 时把响应结构打出来。
    # 排障用 —— "请求 200 但 items=0" 时，光看状态码看不出原因。
    if not items:
        logger.warning(
            "[xhs] 搜索 200 但 items 为空。data 键=%s  payload 键=%s  "
            "body 前 200=%r",
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            list(payload.keys()),
            resp.text[:200],
        )

    # ## ⚠️ 关于「总数」：小红书**不给真实 total**（2026-09-29 修正）
    #
    # 我第一版把 `_total` 设成"本页条数"（`len(results)`）—— 那是**错的**：
    # 接口固定一页给 20 条，于是前端显示"共 20 条"，
    # 但用户翻到第 2、3 页**明明还有内容**（`has_more=True`）。
    #
    # 把"本页条数"当"总数"会误导用户以为"只有 20 条"。
    #
    # 现在如实表达：
    #   · `_has_more` —— 接口明确给的"还有下一页"
    #   · `_total`    —— **不设**（接口没给，就不编造）
    # 前端据此显示"还有更多"而不是"共 N 条"。
    if results:
        results[0].raw_data["_has_more"] = bool(data.get("has_more"))

    # ⚠️ 把"拿到几条 / 解析出几条"都打出来 —— 这两个数字不一致时
    # 说明是**解析**问题（字段结构变了），而不是"平台没给数据"。
    # 排障时这一步能省很多时间（我为此绕了很久）。
    logger.info(
        "[xhs] search(api) %r page=%d sort=%s -> 解析 %d 条"
        "（items=%d, has_more=%s, cookie=%d字符）",
        keyword, page, sort, len(results),
        len(items), data.get("has_more"), len(cookie),
    )
    if items and not results:
        # 有 items 但全被过滤掉 —— 打出首条结构，便于定位字段变化
        logger.warning(
            "[xhs] 拿到 %d 条 items 但全部解析失败！首条键=%s",
            len(items),
            list(items[0].keys()) if isinstance(items[0], dict) else type(items[0]).__name__,
        )
    # 调用方要的条数可能少于 20（接口固定给 20），这里截断
    return results[:want] if want else results


def parse_item(it: Dict[str, Any]) -> Optional[SearchResult]:
    """把搜索结果项转成统一 `SearchResult`。

    取不到的字段留空，**不编造**。
    """
    if not isinstance(it, dict):
        return None

    note_id = str(it.get("id") or "")
    card = it.get("note_card") or {}
    if not note_id or not isinstance(card, dict):
        return None
    # ⚠️ 只有 id、`note_card` 是空壳的项要跳过 ——
    # 否则会产出一条全空记录（"标题空、作者空、没有 token"），
    # 前端看起来像"搜到了一条但点开什么都没有"。
    if not card:
        return None

    user = card.get("user") or {}
    inter = card.get("interact_info") or {}

    # 发布时间在 corner_tag_info 里（`{"type":"publish_time","text":"02-10"}`）
    create_time = ""
    for tag in (card.get("corner_tag_info") or []):
        if isinstance(tag, dict) and tag.get("type") == "publish_time":
            create_time = str(tag.get("text") or "")
            break

    token = str(it.get("xsec_token") or "")

    # 封面：**只有请求里带了 `image_formats` 才会返回 URL**（2026-09-29 实测）
    #
    #     cover = {"url_default": "http://sns-webpic-qc.xhscdn.com/...",
    #              "url_pre": "...", "height": 1600, "width": 1200}
    #
    # `url_default` 实测是 http（不是 https）—— 前端会经
    # `/api/v1/proxy/image` 代理，那边会处理。
    cover_info = card.get("cover") or {}
    cover_url = ""
    if isinstance(cover_info, dict):
        cover_url = str(
            cover_info.get("url_default")
            or cover_info.get("url_pre")
            or cover_info.get("url")
            or ""
        )

    return SearchResult(
        id=note_id,
        title=str(card.get("display_title") or card.get("title") or ""),
        author=str(user.get("nickname") or user.get("nick_name") or ""),
        author_id=str(user.get("user_id") or ""),
        cover=cover_url,
        url=f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}",
        platform="xiaohongshu",
        # ⚠️ `type` 恒为 "normal"（搜索接口不下发真实类型），
        # 这里如实标 "note"，不猜。
        type="note",
        likes=_to_int(inter.get("liked_count")),
        create_time=create_time,
        raw_data={
            "xsec_token": token,
            # 作者 token（部分场景要用）
            "author_xsec_token": str(user.get("xsec_token") or ""),
            "collected_count": _to_int(inter.get("collected_count")),
            "comment_count": _to_int(inter.get("comment_count")),
            "share_count": _to_int(inter.get("shared_count")),
            "cover_size": {
                "width": cover_info.get("width") if isinstance(cover_info, dict) else None,
                "height": cover_info.get("height") if isinstance(cover_info, dict) else None,
            },
        },
    )


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _make_search_id() -> str:
    """生成 `search_id`。

    ⚠️ 实测**空串会返回 0 条**，所以必须给一个非空值。
    格式是小红书自己的（21 位左右的 base36 串），这里按同形状生成 ——
    服务端不校验内容，只要求非空且形状合理。
    """
    import random
    import string
    import time

    # 前缀用当前毫秒的 base36，后面补随机字符
    prefix = _to_base36(int(time.time() * 1000))
    tail = "".join(random.choices(string.ascii_lowercase + string.digits, k=9))
    return (prefix + tail)[:21]


def _to_base36(n: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n <= 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(alphabet[r])
    return "".join(reversed(out))
