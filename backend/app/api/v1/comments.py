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
COMMENTS_SUPPORTED = {
    "bili", "bilibili",
    "kuaishou", "ks",
    "weibo", "wb",
    "twitter", "x", "tw",
    "youtube",
    "douyin", "dy",
}

# 各平台「为什么还没做」的诚实说明（**仅未实现平台**）。
#
# ⚠️ **已实现的平台不要写在这里**（2026-10-01 清理过一轮）：
# 它们走 `COMMENTS_SUPPORTED` 分支，永远不会读到这里的文案 ——
# 但留着"尚未实现"的说明会造成**文案与实际矛盾**，
# 一旦有人改动判断逻辑就会暴露出错误信息。
# 测试 `test_todo_reason_only_for_unimplemented` 守住这条。
COMMENTS_TODO_REASON = {
    "xhs": (
        "小红书评论接口需要 xsec_token + X-s 签名，且风控期极易失败。\n"
        "（评论要按笔记的 xsec_token 走 edith 接口，签名链路比搜索更脆弱；"
        "且当前小红书连接正处风控期，做了也无法验证。）"
    ),
    "xiaohongshu": (
        "小红书评论接口需要 xsec_token + X-s 签名，且风控期极易失败。\n"
        "（评论要按笔记的 xsec_token 走 edith 接口，签名链路比搜索更脆弱；"
        "且当前小红书连接正处风控期，做了也无法验证。）"
    ),
    "telegram": (
        "Telegram 的 `t.me/s` 预览页**不含评论**。\n"
        "取评论要走 MTProto，且公开频道的评论通常在**关联群组**里 —— "
        "语义与其它平台不同（不是「这条消息的回复」，而是「群的讨论」）。"
    ),
    "fanqie": "番茄是章节式发布，没有「评论」这个概念。",
    "wechat_mp": (
        "公众号文章评论需要登录态，且微信只开放部分接口（精选评论/留言）。"
    ),
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
    # 评论带的图片（各平台可有可无）
    images: List[str] = Field(default_factory=list)
    # 子回复（楼中楼）—— 默认不在列表里展开，
    # 由 `/comments?parent_id=xxx` 单独取（`reply_count > 0` 表示有）
    replies: List[Dict[str, Any]] = Field(default_factory=list)
    # 这条评论是回复给谁的（子回复场景）
    reply_to: str = ""


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
        # B站评论图：在 `content.pictures[].img_src`（有就取，没有就空）
        "images": [
            (p or {}).get("img_src")
            for p in ((raw.get("content") or {}).get("pictures") or [])
            if isinstance(p, dict) and (p or {}).get("img_src")
        ],
        "reply_to": "",
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
    if isinstance(ct, (int, float)) and ct > 0:
        ts = int(ct)
        # ⚠️ 毫秒级时间戳（> 1e12）要先转秒 —— 快手实测就是毫秒
        if ts > 10 ** 12:
            ts //= 1000
        try:
            create_time = _dt.datetime.fromtimestamp(ts).isoformat()
        except Exception:
            create_time = ""
    elif isinstance(ct, str) and ct:
        # ⚠️ X / 微博给的是 **RFC2822 字符串**
        #    （如 "Mon Sep 28 02:33:36 +0000 2026"），不是时间戳
        import calendar
        import time as _time

        parsed = None
        for fmt in ("%a %b %d %H:%M:%S %z %Y", "%a %b %d %H:%M:%S %Y"):
            try:
                parsed = _time.strptime(ct, fmt)
                break
            except Exception:
                continue
        if parsed is not None:
            try:
                create_time = _dt.datetime.fromtimestamp(
                    calendar.timegm(parsed)
                ).isoformat()
            except Exception:
                create_time = ct      # 转不了就原样给，不丢信息
        else:
            create_time = ct

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
        # 评论图片（微博/抖音/X 实测都有，快手做防御性提取）
        "images": raw.get("images") or [],
        # 子回复里"回复给谁"（抖音 reply_to / 快手 replyToUserName / X in_reply_to_screen_name）
        "reply_to": raw.get("reply_to") or "",
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
    parent_id: str = Query(
        "",
        description=(
            "取**某条评论的子回复**（楼中楼）—— 传父评论 id。"
            "留空则取顶层评论。"
        ),
    ),
):
    """取某条内容的评论（或某条评论的子回复）。

    ## 两种用法

      · `?platform=x&item_id=y`           → 顶层评论
      · `?platform=x&item_id=y&parent_id=<评论id>` → 那条评论的**子回复**

    ## 支持评论的平台（2026-10-01）

        bili / kuaishou / weibo / twitter / youtube / douyin

    未实现的平台返回 **501 + 具体原因**（不是空列表）——
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
        cookie_domain = ""        # 免登录平台不需要
        conn_platform = ""        # 免登录平台不需要
        # 需要登录的平台才有连接映射；YouTube 免登录 → 保持空
        mapping = {
            "bili": ("BILIBILI", "bili"),
            "bilibili": ("BILIBILI", "bili"),
            "kuaishou": ("KUAISHOU", "kuaishou"),
            "ks": ("KUAISHOU", "kuaishou"),
            # ⚠️ 微博必须用**移动端**域名 `.weibo.cn`（实测：主站 weibo.com
            # 的 cookie 在 m.weibo.cn 无效，api/config 返回 login=false）
            "weibo": ("WEIBO", "weibo"),
            "wb": ("WEIBO", "weibo"),
            # ⚠️ X 的 cookie_domain 必须是 `x.com`（实测：netscape_to_header
            # 认这个名字，用 "twitter" 会返回 0 字符）
            "twitter": ("TWITTER", "x.com"),
            "x": ("TWITTER", "x.com"),
            "tw": ("TWITTER", "x.com"),
            "douyin": ("DOUYIN", "douyin"),
            "dy": ("DOUYIN", "douyin"),
        }.get(p)
        # 免登录平台（YouTube 取评论不需要凭证 —— 实测未传 cookie 可取到）
        if mapping is None:
            raw_cookie = ""
        else:
            conn_platform, cookie_domain = mapping
            _cid, raw_cookie = resolve_connection(conn_id, conn_platform)
        cookie = netscape_to_header(raw_cookie, cookie_domain) if raw_cookie else ""

        # B站有更完整的游标分页方法（含排序/总数），优先用它；
        # 其它平台走基类 `get_comments`（各平台自己实现）
        # `wb` 是 `weibo` 的别名（两者都注册了同一个客户端类），
        # create_client 认 `weibo`
        client_name = "bili" if p in ("bili", "bilibili") else p
        # 别名 → 真实注册名（注册时用的是 `weibo` / `twitter`）
        if client_name == "wb":
            client_name = "weibo"
        if client_name in ("x", "tw"):
            client_name = "twitter"
        if client_name == "dy":
            client_name = "douyin"
        async with create_client(client_name, mode="api", cookie=cookie) as client:
            if parent_id:
                # ===== 取**子回复**（楼中楼）=====
                #
                # ⚠️ 子回复不是"评论列表的下一页" —— 端点/参数/签名都可能不同
                # （抖音换端点且签名函数不同；快手加 rootCommentId；X 靠父 id 筛）。
                # B站没有独立的子回复接口（它的回复在 `replies` 字段里随顶层返回），
                # 所以对 B站如实说明。
                if p in ("bili", "bilibili"):
                    raise HTTPException(
                        status_code=501,
                        detail=(
                            "B站的子回复**随顶层评论一起返回**（在每条评论的 "
                            "`replies` 字段里），不需要单独取。\n"
                            "如需查看，请直接看顶层评论返回里的 `replies`。"
                        ),
                    )
                try:
                    reply_data = await client.get_replies(
                        item, parent_id,
                        max_results=page_size, cursor=offset,
                    )
                except NotImplementedError as exc:
                    # ⚠️ **保留平台自己给的说明**（2026-10-01 改）
                    #
                    # 各平台"为什么取不到子回复"的**原因不同**，且都是实测结论：
                    #   · 微博：`comments` 字段实测为空、hotFlowChild 返回 ok=0
                    #   · 这类信息比笼统的"暂不支持"有用得多
                    # 原来是硬编码一句"暂不支持"，把平台的具体说明**丢掉了**。
                    detail = str(exc).strip()
                    if not detail or "not implemented" in detail.lower():
                        detail = (
                            f"平台 {p!r} 暂不支持单独取子回复。\n"
                            "（顶层评论仍可用 —— 去掉 parent_id 参数即可。）"
                        )
                    raise HTTPException(status_code=501, detail=detail)
                raw_comments = reply_data.get("comments") or []
                comments = [_normalize_generic_comment(c) for c in raw_comments]
                total = int(reply_data.get("total") or len(comments))
                has_more = bool(reply_data.get("has_more"))
                next_offset = str(reply_data.get("next_cursor") or "")
                message = f"该评论有 {len(comments)} 条回复"
            elif p in ("bili", "bilibili"):
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
                # ⚠️ 用 `get_comments_page`（而不是 `get_comments`）——
                # 它会**带回游标**。实测各平台分页大都是 cursor 不是页码
                # （微博 max_id / 快手 pcursor / X Bottom / YouTube continuation），
                # 只用 page 翻页会**拿到重复数据**（前端点"加载更多"没反应）。
                #
                # 未实现 `get_comments_page` 的平台，基类有默认实现
                # （退化成调 get_comments，游标为空）。
                page_data = await client.get_comments_page(
                    item, max_results=page_size, page=page, cursor=offset
                )
                raw_comments = page_data.get("comments") or []
                comments = [_normalize_generic_comment(c) for c in raw_comments]
                total = int(page_data.get("total") or len(comments))
                has_more = bool(page_data.get("has_more"))
                next_offset = str(page_data.get("next_cursor") or "")
                message = (
                    f"共 {total} 条评论" if total > len(comments)
                    else f"返回 {len(comments)} 条评论"
                )

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
