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

# 已实现评论采集的平台 —— **从平台元数据生成**（2026-10-01 收敛）
#
# ⚠️ 原来这里是**手写名单** `{"bili","bilibili","kuaishou",...}`，
# 与 `users.py` / `health_routes.py` 里的表**各写一遍** ——
# 新增平台要改 4 个文件，漏一个就静默出错（KeyError / 找不到客户端）。
#
# 现在改由**平台自己声明**（`platforms/<平台>/meta.py` 的 capabilities），
# 这里有 meta 生成。新增平台只需在自己的 meta.py 里加 `"comments"`。
from app.services.platforms.meta import (
    all_metas as _all_metas,
    get_meta as _get_meta,
    no_login_platforms as _no_login_platforms,
    resolve_name as _resolve_name,
    supports as _supports,
)
# ⚠️ 异常类型也要 import —— 漏了会让 `except LoginExpiredError` 变成
# NameError，所有错误路径都会变成 500（这坑我们踩过一次）
from app.services.platforms.types import (
    ContentNotFoundError,
    LoginExpiredError,
    NetworkError,
    RiskControlError,
)


def _comment_platforms() -> set:
    """声明了 `comments` 能力的平台（含别名）。"""
    out: set = set()
    for m in _all_metas():
        if "comments" in m.capabilities:
            out |= m.all_names
    return out


#: 错误消息给用户看的长度上限
_MSG_LIMIT = 600


def _brief(exc: Exception, limit: int = _MSG_LIMIT) -> str:
    """把平台异常压成**给用户看的**短消息，且**不切掉结论**。

    ⚠️ 为什么不能 `str(exc)[:300]`（2026-10-04 实测踩到）：

        平台错误消息是"解释 + 处置办法"的多行结构，最后一行才是
        用户真正需要的东西。硬截 300 会**正好切掉那一行**——
        实测 YouTube 人机校验断在「可行的办法：等待 / 更换出口 IP / …」
        的**第一个字**上，用户只看到一个「可」。

    规则：
        1. 超限时**保尾**（处置办法在尾部），不保头；
        2. 截断处补 `…`，明确表示"还有内容被省了"，
           不让半句话看起来像完整消息；
        3. 逐行判断，尽量**按整行取舍**，避免切出半个词。

    注意：这只改**长度**，不删信息 —— 完整内容仍可在日志里查到
    （下面的 `logger.error` 打的是未截断的 `exc`）。
    """
    text = str(exc).strip()
    if len(text) <= limit:
        return text

    # 保留尾部：处置办法总在最后
    tail = text[-limit:]
    # 尽量从行首开始（丢掉被切开的半行）
    nl = tail.find("\n")
    if nl != -1 and len(tail) - nl - 1 > 40:
        tail = tail[nl + 1:]
    return "…\n" + tail.strip()


# ⚠️ 用**函数**而不是模块级常量：元数据是懒加载的
# （`_discover()` 在首次调用时才扫目录），模块导入时还不一定有。
# 保留 `COMMENTS_SUPPORTED` 这个名字是为了兼容已有测试与调用方。
def _supported() -> set:
    return _comment_platforms()


# 兼容：模块级符号（首次访问时求值）
class _SupportedSet:
    """惰性集合 —— 让 `COMMENTS_SUPPORTED` 用起来像普通 set。"""

    def __contains__(self, item) -> bool:
        return item in _comment_platforms()

    def __iter__(self):
        return iter(_comment_platforms())

    def __len__(self) -> int:
        return len(_comment_platforms())

    def __repr__(self) -> str:
        return repr(_comment_platforms())

    def __and__(self, other):
        return _comment_platforms() & set(other)

    def __or__(self, other):
        return _comment_platforms() | set(other)

    def __le__(self, other):
        return _comment_platforms() <= set(other)

    def __ge__(self, other):
        return _comment_platforms() >= set(other)


COMMENTS_SUPPORTED = _SupportedSet()

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
        # ⚠️ 微博子回复里有 `is_mblog_author`（博主本人回复，实测 True）——
        #    这个归一化函数是**白名单式**的：没列出来的字段会**被丢掉**。
        #    所以 platform 采集到了、前端想用，却因为这里没写而消失。
        #    （教训：加字段要同时看"采集端产出"和"归一化白名单"两处。）
        "is_author_reply": bool(raw.get("is_author_reply")),
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

        # ===== 平台元数据全部从 meta 取（2026-10-01 收敛）=====
        #
        # ⚠️ 原来这里有 16 行**手写映射**（平台 → (连接名, cookie域名)）
        # 再加上 8 行**逐个 if 的别名转换**（wb→weibo, dy→douyin…）——
        # 与 `users.py` / `health_routes.py` 里的表重复，
        # 新增平台漏改一处就报错。
        #
        # 现在改为查平台自己声明的元数据（`platforms/<平台>/meta.py`）。
        meta = _get_meta(p)
        client_name = _resolve_name(p)          # 别名 → 注册名（wb→weibo）
        if meta is None:
            # 有 comments 能力却没声明 meta —— 是**开发时的遗漏**，
            # 不是用户错误。给明确提示（不是 500）。
            raise HTTPException(
                status_code=501,
                detail=(
                    f"平台 {p!r} 声明了评论能力，但缺少 `meta.py` 元数据声明。\n"
                    "请在该平台目录下补 `meta.py`（含 conn_platform / "
                    "cookie_domain / capabilities）。"
                ),
            )

        # 免登录平台不需要连接与 cookie（YouTube 实测未传 cookie 可取到）
        if meta.no_login:
            raw_cookie = ""
        else:
            _cid, raw_cookie = resolve_connection(conn_id, meta.conn_platform)
        # ⚠️ cookie_domain 必须与 meta 里声明的一致（实测认这些名字，
        #    写错会返回 0 字符 cookie）
        cookie = (
            netscape_to_header(raw_cookie, meta.cookie_domain)
            if raw_cookie else ""
        )

        async with create_client(client_name, mode="api", cookie=cookie) as client:
            if parent_id:
                # ===== 取**子回复**（楼中楼）=====
                #
                # ⚠️ 子回复不是"评论列表的下一页" —— 端点/参数/签名都可能不同
                # （抖音换端点且签名函数不同；快手加 rootCommentId；X 靠父 id 筛）。
                #
                # 平台**有没有** replies 能力由它自己声明（meta.capabilities）。
                if not _supports(p, "replies"):
                    raise HTTPException(
                        status_code=501,
                        detail=(
                            f"{meta.name} 不支持单独取子回复。\n"
                            + (
                                # B站：2026-10-04 已补 `get_replies`（走老接口
                                # `/x/v2/reply/main?root=`）。到不了这里 ——
                                # meta 已声明 `replies`，下面的分支不会命中。
                                # 保留这段只为兜住"meta 声明了但实现缺失"的情况。
                                f"{meta.name} 声明了子回复能力，但本次请求没能取到 —— "
                                "请检查该平台 client 是否实现了 get_replies。"
                                if meta.name == "bili" else
                                # 微博：平台就没开放这个数据（实测过）
                                "⚠️ 这不是「这条评论没有回复」—— "
                                "是该平台没有开放这个数据。\n"
                                "（顶层评论仍可用：去掉 parent_id 参数。）"
                            )
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
            elif _supports(p, "comments_paged"):
                # 平台自己声明了更完整的游标分页方法（含排序/总数）
                # ⚠️ B站的 `get_comments_paged` 比基类的通用路径更完整，
                # 所以走这条分支。**由能力声明决定**，不是硬编码平台名。
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
        # ⚠️ 截断要**按行**、且**保留结尾**（2026-10-04）
        #
        # 原来是无差别 `str(exc)[:300]`。问题：平台错误消息常是
        # "解释 + 处置办法"的多行结构，硬截 300 会**把最该给用户看的
        # 那行切掉**。实测 YouTube 人机校验消息就断在
        # 「可行的办法：等待 / 更换出口 IP / …」的**第一个字**上 ——
        # 用户看到的是「可」，等于什么都没说。
        #
        # 改成：优先给完整的**最后一行**（处置办法），前面只留摘要。
        if isinstance(exc, LoginExpiredError):
            raise HTTPException(
                status_code=401,
                detail=f"{_brief(exc)}\n\n请到「账号中心」重新获取该平台登录态。",
            )
        if isinstance(exc, RiskControlError):
            raise HTTPException(
                status_code=429, detail=f"{_brief(exc)}\n\n这是**平台侧拒绝**"
                                       "（风控/人机验证），可尝试稍等一会儿、换 IP，"
                                       "或重新获取登录态。",
            )
        if isinstance(exc, ContentNotFoundError):
            raise HTTPException(
                status_code=404, detail=_brief(exc, 200)
            )
        if isinstance(exc, NetworkError):
            raise HTTPException(
                status_code=503,
                detail=f"{_brief(exc, 200)}\n\n这是**网络问题**（不是平台故障），稍后重试。",
            )
        # ⚠️ 日志打**未截断**的 exc —— 用户看的是摘要，排查要靠完整信息
        logger.error("[comments] %s/%s 失败：%s", p, item, exc)
        raise HTTPException(status_code=500, detail=f"获取评论失败: {_brief(exc, 200)}")
