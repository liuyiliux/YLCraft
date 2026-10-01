"""YLCraft — **统一**评论接口（所有平台一个入口）。

## 为什么做统一入口（2026-10-01）

和体检一样的问题：评论原来只有 **B站** 有
（`/api/v1/bilibili/comments` + `BilibiliClient.get_comments_paged`），
其它平台**连实现都没有**（小红书 `get_comments` 还是 TODO）。

前端的评论 tab 也**只在 B站分支渲染** ——
所以用户在小红书/抖音的详情里点「评论」，要么看不到 tab、
要么是空白。

统一入口的意义：
  · **已实现的平台**（B站）→ 直接用
  · **未实现的平台** → 明确报 501「该平台尚未支持评论采集」，
    **不是**返回空列表（空列表会让用户以为"这条内容没评论"）

## 返回格式（各平台归一）

```json
{
  "success": true,
  "data": {
    "platform": "bili",
    "item_id": "BV1xx411c7XD",
    "total": 42,
    "comments": [
      {
        "id": "123456",
        "author": "用户名",
        "author_id": "uid",
        "avatar": "头像URL",
        "content": "评论正文",
        "likes": 10,
        "create_time": "2026-01-01T12:00:00",
        "reply_count": 3,
        "location": "IP属地",
        "replies": [...]
      }
    ],
    "has_more": true,
    "next_offset": "..."
  }
}
```

## ⚠️ 各平台「能不能做」是硬约束，要如实

  · B站    → ✅ 已实现（`/x/v2/reply`）
  · 小红书 → ⚠️ 接口是有的（`edith` 系），但需要 xsec_token + 签名，
              且风控期极易失败 —— 本次**未实现**，标 TODO
  · 抖音   → ⚠️ 需要 a_bogus 签名，本次未实现
  · 微博   → ⚠️ 需要登录 cookie，本次未实现
  · YouTube → ⚠️ yt-dlp 能取评论，但很慢（要额外请求），
              本次**未接**（有需要再说）
  · Telegram → ❌ `t.me/s` 页面**不含评论**；要 MTProto 才能取，
              且公开频道的"评论"通常是关联群组 —— 语义不同
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("ylcraft.api.comments")

router = APIRouter()

# 已实现评论采集的平台（新增平台时**必须**同步改这里 —— 与 supported_platforms() 无关，
# 因为那个表管的是"搜索"，评论是另一套能力）
COMMENTS_SUPPORTED = {"bili", "bilibili", "kuaishou", "ks", "weibo", "wb"}

# 各平台「为什么还没做」的诚实说明（未实现时返回给用户）
COMMENTS_TODO_REASON = {
    "xhs": "小红书评论接口需要 xsec_token + X-s 签名，且风控期极易失败 —— 尚未实现",
    "xiaohongshu": "小红书评论接口需要 xsec_token + X-s 签名，且风控期极易失败 —— 尚未实现",
    "douyin": "抖音评论接口需要 a_bogus 签名 —— 尚未实现",
    "dy": "抖音评论接口需要 a_bogus 签名 —— 尚未实现",
    "weibo": "微博评论接口需要登录 cookie —— 尚未实现",
    "wb": "微博评论接口需要登录 cookie —— 尚未实现",
    "kuaishou": "快手评论接口需要 hxfalcon 签名（只能浏览器抓）—— 尚未实现",
    "ks": "快手评论接口需要 hxfalcon 签名（只能浏览器抓）—— 尚未实现",
    "twitter": "X 的评论走 GraphQL，需要 transaction-id —— 尚未实现",
    "x": "X 的评论走 GraphQL，需要 transaction-id —— 尚未实现",
    "tw": "X 的评论走 GraphQL，需要 transaction-id —— 尚未实现",
    "youtube": (
        "YouTube 评论走 innertube `/youtubei/v1/next`（continuation 翻页）；\n"
        "⚠️ 2026-10-01 实测修正：我们**自己造 continuation token 拿不到**评论"
        "（HTTP 200 但响应 14KB、无评论字段）—— 那只是 yt-dlp 的**兜底路径**"
        "（`_video.py:2598-2604`），主路径是从 watch 页 `ytInitialData` 取。\n"
        "所以当初『不打算用 yt-dlp』的结论**也需修正**：yt-dlp 实测能取到评论"
        "（顶层 100 条约 4.5 秒），**不需要 API key、不需要登录**；且项目本来"
        "就已在用 yt-dlp（YouTube 搜索/详情/频道都走它）。\n"
        "⚠️ 但用 yt-dlp 取评论**必须设 `max_comments` 上限** —— 不设会无上限翻页"
        "（实测某视频报 ~1063 万条评论，跑了 10 分钟没停）。"
    ),
    "telegram": (
        "Telegram 的 `t.me/s` 预览页**不含评论**；"
        "取评论要走 MTProto，且公开频道的评论通常在关联群组 —— 语义不同"
    ),
    "fanqie": "番茄是章节式发布，没有评论",
    "wechat_mp": "公众号文章评论需要登录态且接口受限 —— 尚未实现",
}


class CommentItem(BaseModel):
    """统一评论结构。"""
    id: str = ""
    author: str = ""
    author_id: str = ""
    avatar: str = ""
    content: str = ""
    likes: int = 0
    create_time: str = ""
    reply_count: int = 0
    location: str = ""
    replies: List[Dict[str, Any]] = Field(default_factory=list)


class CommentsData(BaseModel):
    platform: str = ""
    item_id: str = ""
    total: int = 0
    comments: List[Dict[str, Any]] = Field(default_factory=list)
    has_more: bool = False
    next_offset: str = ""


class CommentsResponse(BaseModel):
    success: bool = True
    data: Optional[CommentsData] = None
    message: str = ""


def _normalize_bili_comment(raw: Dict[str, Any]) -> Dict[str, Any]:
    """把 B站评论归一成统一结构。

    ## ⚠️ 字段是**扁平的**，不是嵌套的（2026-10-01 实测踩到）

    `BilibiliClient.get_comments_paged` 已经做过一次扁平化，
    实际返回的是：

        rpid / user_name / mid / user_avatar
        message / like_count / ctime / replies_count

    我第一版按 B站**原始 API** 的嵌套结构去取
    （`user.uname` / `content.message` / `like` / `rcount`）
    —— 结果**每条评论的作者和正文都是空的**，而 `total` 是对的
    （355045），看起来像"取到了但全空"，极难定位。

    所以这里**两种形态都兼容**（扁平优先，嵌套兜底），
    将来上游再改也不会全空。
    """
    import datetime as _dt

    # --- 正文：扁平 `message` 优先，兜底嵌套 `content.message` ---
    content = raw.get("message")
    if not content:
        content = (raw.get("content") or {}).get("message") or ""

    # --- 作者：扁平 `user_name` 优先，兜底 `user.uname` / `member.uname` ---
    author = raw.get("user_name")
    if not author:
        author = (
            (raw.get("user") or {}).get("uname")
            or (raw.get("member") or {}).get("uname")
            or ""
        )

    # --- 头像 ---
    avatar = raw.get("user_avatar")
    if not avatar:
        avatar = (
            (raw.get("member") or {}).get("avatar")
            or (raw.get("user") or {}).get("avatar")
            or ""
        )

    # --- 点赞数 ---
    likes = raw.get("like_count")
    if likes is None:
        likes = raw.get("like")
    likes = int(likes or 0)

    # --- 回复数 ---
    reply_count = raw.get("replies_count")
    if reply_count is None:
        reply_count = raw.get("rcount")
    reply_count = int(reply_count or 0)

    ctime = raw.get("ctime") or 0
    try:
        create_time = _dt.datetime.fromtimestamp(int(ctime)).isoformat()
    except Exception:
        create_time = ""

    return {
        "id": str(raw.get("rpid") or ""),
        "author": author,
        "author_id": str(raw.get("mid") or (raw.get("member") or {}).get("mid") or ""),
        "avatar": avatar,
        "content": content,
        "likes": likes,
        "create_time": create_time,
        "reply_count": reply_count,
        "location": (raw.get("reply_control") or {}).get("location") or "",
        "replies": raw.get("replies") or [],
    }


def _normalize_generic_comment(raw: Dict[str, Any]) -> Dict[str, Any]:
    """归一**非 B站**平台的评论。

    各平台 `get_comments()` 按约定返回这套键（见 base.py 的 docstring）：

        id / content / author / author_id / avatar
        likes / create_time / reply_count

    这里做**防御性**归一：缺字段用默认值，时间戳统一转成 ISO 字符串
    （各平台可能给秒级 int、毫秒 int、或已经是字符串）。
    """
    import datetime as _dt

    ct = raw.get("create_time")
    create_time = ""
    if isinstance(ct, str) and ct:
        create_time = ct          # 已经是字符串（如 RFC2822/ISO）
    elif isinstance(ct, (int, float)) and ct > 0:
        ts = int(ct)
        # ⚠️ 毫秒级时间戳（> 1e12）要先转秒 —— 快手实测就是毫秒
        if ts > 10 ** 12:
            ts //= 1000
        try:
            create_time = _dt.datetime.fromtimestamp(ts).isoformat()
        except Exception:
            create_time = ""

    return {
        "id": str(raw.get("id") or ""),
        "author": raw.get("author") or "",
        "author_id": str(raw.get("author_id") or ""),
        "avatar": raw.get("avatar") or "",
        "content": raw.get("content") or "",
        "likes": int(raw.get("likes") or 0),
        "create_time": create_time,
        "reply_count": int(raw.get("reply_count") or 0),
        "location": raw.get("location") or "",
        "replies": raw.get("replies") or [],
    }


@router.get("", summary="获取评论（统一入口）", response_model=CommentsResponse)
async def get_comments(
    platform: str = Query(..., description="平台：bili/douyin/xhs/..."),
    item_id: str = Query(..., description="内容 ID（B站用 BV 号，其它平台用笔记 ID）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    sort: int = Query(0, description="排序（B站：0=最热 1=最新 2=最早）"),
    offset: str = Query("", description="游标（从响应的 next_offset 取，用于加载更多）"),
    conn_id: str = Query("", description="平台连接 ID"),
):
    """取某条内容的评论。

    ## ⚠️ 目前只有 B站能用

    其它平台会返回 **501 + 具体原因**（不是空列表）——
    "没实现"和"这条没评论"是两回事，不能混。
    """
    p = (platform or "").strip().lower()
    item = (item_id or "").strip()
    if not p or not item:
        raise HTTPException(status_code=400, detail="缺少 platform 或 item_id")

    if p not in COMMENTS_SUPPORTED:
        reason = COMMENTS_TODO_REASON.get(p, "该平台尚未实现评论采集")
        raise HTTPException(
            status_code=501,
            detail=(
                f"平台 {p!r} 暂不支持评论采集。\n原因：{reason}\n\n"
                "⚠️ 这不是「这条内容没有评论」—— 是功能还没做。"
                f"当前支持评论的平台：{', '.join(sorted(COMMENTS_SUPPORTED))}。"
            ),
        )

    try:
        from app.services.platforms import create_client
        from app.services.platforms.login_health import (
            netscape_to_header,
            resolve_connection,
        )

        # 各平台的连接平台名 + cookie 域名（⚠️ 域名必须写对 —— 实测
        # netscape_to_header 认的是这些名字，写错会返回 0 字符）
        conn_platform, cookie_domain = {
            "bili": ("BILIBILI", "bili"),
            "bilibili": ("BILIBILI", "bili"),
            "kuaishou": ("KUAISHOU", "kuaishou"),
            "ks": ("KUAISHOU", "kuaishou"),
            # ⚠️ 微博必须用**移动端**域名 `.weibo.cn`（实测：主站 weibo.com
            # 的 cookie 在 m.weibo.cn 无效，api/config 返回 login=false）
            "weibo": ("WEIBO", "weibo"),
            "wb": ("WEIBO", "weibo"),
        }[p]
        _cid, raw_cookie = resolve_connection(conn_id, conn_platform)
        cookie = netscape_to_header(raw_cookie, cookie_domain) if raw_cookie else ""

        # B站有更完整的游标分页方法（含排序/总数），优先用它；
        # 其它平台走基类 `get_comments`（各平台自己实现）
        # `wb` 是 `weibo` 的别名（两者都注册了同一个客户端类），
        # create_client 认 `weibo`
        client_name = "bili" if p in ("bili", "bilibili") else p
        if client_name == "wb":
            client_name = "weibo"
        async with create_client(client_name, mode="api", cookie=cookie) as client:
            if p in ("bili", "bilibili"):
                result = await client.get_comments_paged(
                    item, page, page_size, sort, offset
                )
                raw_comments = result.get("comments") or []
                comments = [_normalize_bili_comment(c) for c in raw_comments]
                total = int(result.get("total") or 0)
                has_more = bool(result.get("has_more"))
                next_offset = str(result.get("next_offset") or "")
                message = f"共 {total} 条评论"
            else:
                raw_comments = await client.get_comments(
                    item, max_results=page_size, page=page, cursor=offset
                )
                comments = [_normalize_generic_comment(c) for c in raw_comments]
                total = len(comments)
                # 基类签名不带总数/游标 —— 用"是否取满"推断还有没有更多
                # （不精确，但比谎报"没有更多"好；B站那种精确游标另走上面分支）
                has_more = len(raw_comments) >= page_size
                next_offset = ""
                message = f"返回 {len(comments)} 条评论"

        return CommentsResponse(
            success=True,
            data=CommentsData(
                platform=p,
                item_id=item,
                total=total,
                comments=comments,
                has_more=has_more,
                next_offset=next_offset,
            ),
            message=message,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[comments] %s/%s 失败：%s", p, item, exc)
        raise HTTPException(status_code=500, detail=f"获取评论失败: {str(exc)[:200]}")
