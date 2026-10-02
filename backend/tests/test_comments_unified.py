"""统一评论接口的回归测试（2026-10-01 做 B 时加）。

## 为什么做统一入口

和体检一样的问题：评论原来**只有 B站有**
（`/api/v1/bilibili/comments`），小红书的 `get_comments` 还是 TODO。
前端的评论 tab 也**只在 B站分支渲染** ——
用户在其它平台点「评论」看到的是**空白**，
会以为"这条内容没有评论"。

## ⚠️ 最关键的纪律

**"没实现" ≠ "没评论"**：

  · 未实现的平台 → 返回 **501 + 具体原因**（不是空列表）
  · 空列表会让用户以为"这条内容没人评论" —— 那是假阴性

本仓库铁律第 2 条（见 `ADDING_A_PLATFORM.md`）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 路由与结构
# =============================================================================

def test_comments_route_exists():
    """要有统一评论路由。"""
    from app.api.v1 import comments

    assert hasattr(comments, "router")
    src = inspect.getsource(comments)
    assert "COMMENTS_SUPPORTED" in src


def test_supported_platforms_match_implementation():
    """**关键**：`COMMENTS_SUPPORTED` 必须与实际实现**一致**。

    ⚠️ 这是防"登记了但没实现"的假支持 —— 如果某个平台被列进
    `COMMENTS_SUPPORTED` 却没有 `get_comments` 实现，用户点评论会
    拿到 500（而不是明确的 501「未实现」）。

    反过来，实现了却没登记 → 用户看到"暂不支持"（功能白做）。
    两边都要对上。
    """
    import inspect

    from app.api.v1.comments import COMMENTS_SUPPORTED

    # B站：走自己的 get_comments_paged（游标分页，含排序/总数）
    from app.services.platforms.bilibili.client import BilibiliClient

    assert hasattr(BilibiliClient, "get_comments_paged")
    assert "bili" in COMMENTS_SUPPORTED

    # 其余平台：都必须有**真** get_comments（不是基类的 NotImplementedError）
    checks = [
        ("kuaishou", "KuaishouClient"),
        ("ks", None),                     # 别名，只验证登记
        ("weibo", "WeiboClient"),
        ("wb", None),
        ("twitter", "TwitterClient"),
        ("x", None),
        ("youtube", "YoutubeClient"),
        ("douyin", "DouyinClient"),
        ("dy", None),
    ]
    for plat, cls_name in checks:
        assert plat in COMMENTS_SUPPORTED, f"{plat} 未登记"
        if cls_name is None:
            continue
        mod = __import__(
            f"app.services.platforms.{plat}.client", fromlist=[cls_name]
        )
        cls = getattr(mod, cls_name)
        src = inspect.getsource(cls.get_comments)
        assert "NotImplementedError" not in src, (
            f"{cls_name}.get_comments 还是 TODO（登记了却没实现）"
        )


def test_youtube_comments_has_hard_limit():
    """**关键回归**：YouTube 评论必须设**上限**。

    ⚠️ 实测：不设 `max_comments` 就是无上限，会一直翻页。
    某视频报 ~10,631,705 条评论，不设上限跑了 **10 分钟没停**，只能杀掉。

    这是最危险的一条 —— 必须有硬上限保护。
    """
    import inspect

    from app.services.platforms.youtube.client import YoutubeClient

    src = inspect.getsource(YoutubeClient.get_comments)
    assert "MAX_SAFE" in src, "要有硬上限（防跑飞）"
    assert "max_comments" in src, "要传 max_comments 给 yt-dlp"
    # 必须限制 want，不能直接用传入值
    assert "min(" in src and "MAX_SAFE" in src


def test_platforms_implement_cursor_pagination():
    """**关键回归**：各平台要能**透出游标**（否则"加载更多"拿重复数据）。

    ## 为什么这条重要（2026-10-01 优化）

    实测各平台分页大都是 **cursor 不是页码**：
        微博 `max_id` / 快手 `pcursor` / X `Bottom cursor` / YouTube continuation

    原来统一接口只传 `page` → 第二次请求**拿到和第一次相同的数据**
    （前端点"加载更多"看起来没反应，实测踩过同类问题）。

    修法：基类加 `get_comments_page()`（返回 comments + has_more +
    **next_cursor**），各平台实现它。`get_comments` 保留（向后兼容），
    内部循环调 page 版本。
    """
    import inspect

    # 基类要有默认实现（未实现的平台退化成调 get_comments）
    from app.services.platforms.base import BasePlatformClient

    assert hasattr(BasePlatformClient, "get_comments_page")
    base_src = inspect.getsource(BasePlatformClient.get_comments_page)
    assert "next_cursor" in base_src

    # 这些平台必须**自己实现**（真的透出游标）
    impls = [
        ("weibo", "WeiboClient", "max_id"),
        ("kuaishou", "KuaishouClient", "pcursor"),
        ("douyin", "DouyinClient", "cursor"),
        ("youtube", "YoutubeClient", "offset"),
    ]
    for plat, cls_name, cursor_hint in impls:
        mod = __import__(f"app.services.platforms.{plat}.client", fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        src = inspect.getsource(cls.get_comments_page)
        assert "next_cursor" in src, f"{cls_name} 没返回 next_cursor"
        assert "has_more" in src, f"{cls_name} 没返回 has_more"
        assert cursor_hint in src or "cursor" in src, (
            f"{cls_name} 没处理游标（{cursor_hint}）"
        )


def test_comments_avoid_duplicate_transport():
    """**回归**：实现 `get_comments_page` 的平台，`get_comments` 别再写一遍分页。

    否则两处分页逻辑会**漂移**（改了游标处理忘了同步另一处）。
    正确做法：`get_comments` 循环调 `get_comments_page`。
    """
    import inspect

    for plat, cls_name in (("weibo", "WeiboClient"),
                           ("kuaishou", "KuaishouClient"),
                           ("douyin", "DouyinClient")):
        mod = __import__(f"app.services.platforms.{plat}.client", fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        src = inspect.getsource(cls.get_comments)
        assert "get_comments_page" in src, (
            f"{cls_name}.get_comments 应复用 get_comments_page（避免分页逻辑写两遍）"
        )


def test_douyin_signature_audit_is_documented():
    """**关键**：抖音用了第三方混淆 JS —— 审查结论必须写在代码里。

    ⚠️ 混淆 JS 肉眼无法确认行为，所以：
      · 必须做过静态审查（网络/文件/系统/eval）
      · 审查结论必须**记录在代码里**（后人能复核，不用重新猜）
    """
    import inspect

    from app.services.platforms.douyin import sign as sign_mod

    doc = inspect.getdoc(sign_mod) or ""
    for kw in ("混淆", "XMLHttpRequest", "child_process", "eval"):
        assert kw in doc, f"sign.py 的 docstring 缺审查记录（{kw}）"


def test_douyin_empty_body_is_treated_as_signature_issue():
    """**回归**：抖音空 body 要报"签名问题"，不是"没有评论"。

    ⚠️ 实测失败模式是 HTTP 200 + **0 字节**（不是错误码）。
    空 body 会让 json() 抛异常，按现有重试逻辑会试 3 次全失败，
    **看起来像风控**。必须显式判空并说明原因。

    ⚠️ 2026-10-01 重构后：抖音的**实际请求逻辑搬到了 `get_comments_page`**
    （`get_comments` 变成循环调它，只为跨页去重）——
    所以断言要查 `get_comments_page`，不是 `get_comments`。
    """
    import inspect

    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_comments_page)
    assert "空响应体" in src or "0 字节" in src
    assert "a_bogus" in src
    # 不能把空当成"0 条评论"返回
    assert "不是「没有评论」" in src or "不是「没有评论」" in src

    # `get_comments` 仍要能跨页去重（置顶评论会重复出现）
    src2 = inspect.getsource(DouyinClient.get_comments)
    assert "seen" in src2, "get_comments 要去重（抖音置顶评论会跨页重复）"


def test_unimplemented_platforms_have_reasons():
    """每个主要平台都要有**具体原因**（不是一句"不支持"）。

    用户能看到"为什么做不到"，才知道要不要等、能不能绕。
    """
    from app.api.v1.comments import COMMENTS_TODO_REASON

    # 真·未实现的平台（小红书按用户要求排除；Telegram/番茄/公众号语义不同）
    for p in ("xhs", "xiaohongshu", "telegram", "fanqie", "wechat_mp"):
        assert p in COMMENTS_TODO_REASON, f"{p} 缺说明"
        assert len(COMMENTS_TODO_REASON[p]) > 8, f"{p} 的说明太简短"


def test_todo_reason_only_for_unimplemented():
    """**关键回归**：`COMMENTS_TODO_REASON` 里**不能有已实现的平台**。

    ## 为什么要守这条（2026-10-01 清理过一轮）

    快手/微博/X/抖音/YouTube 陆续实现后，
    它们的"尚未实现"说明**还留在 `COMMENTS_TODO_REASON` 里**。

    虽然这些平台走 `COMMENTS_SUPPORTED` 分支、永远不会读到那些文案，
    但**文案与实际矛盾** —— 一旦有人改动判断逻辑（比如把
    `if p not in COMMENTS_SUPPORTED` 改错），就会给用户显示
    "抖音评论尚未实现"这种**完全错误的**信息。

    文案与代码不一致是隐患，必须同步清理。
    """
    from app.api.v1.comments import COMMENTS_SUPPORTED, COMMENTS_TODO_REASON

    overlap = COMMENTS_SUPPORTED & set(COMMENTS_TODO_REASON)
    assert not overlap, (
        f"这些平台**已实现**却仍留在「未实现说明」里：{sorted(overlap)}\n"
        "请从 COMMENTS_TODO_REASON 中删除它们 —— 否则文案与代码矛盾。"
    )


def test_todo_reason_does_not_say_unimplemented_for_supported():
    """补充：已实现平台的说明里不该出现"尚未实现"字样。"""
    from app.api.v1.comments import COMMENTS_SUPPORTED, COMMENTS_TODO_REASON

    for p, reason in COMMENTS_TODO_REASON.items():
        if p in COMMENTS_SUPPORTED:
            assert "尚未实现" not in reason, f"{p} 已实现，说明却写「尚未实现」"


# =============================================================================
# 501：未实现 ≠ 空列表
# =============================================================================

def test_unimplemented_returns_501_not_empty():
    """**关键**：未实现要抛 501，不是返回空列表。"""
    from app.api.v1 import comments

    src = inspect.getsource(comments.get_comments)
    assert "501" in src
    assert "这不是「这条内容没有评论」" in src or "不是" in src
    # 不能走"返回空"的路径
    assert "return CommentsResponse(success=True" not in src.split("if p not in")[0]


def test_501_message_lists_supported():
    """501 的文案要列出**当前支持哪些平台**（给用户出路）。"""
    from app.api.v1 import comments

    src = inspect.getsource(comments.get_comments)
    assert "COMMENTS_SUPPORTED" in src
    assert "当前支持" in src


# =============================================================================
# B站字段归一
# =============================================================================

def test_bili_normalizer_handles_flat_fields():
    """**关键回归**：B站评论字段是**扁平的**，不是嵌套的。

    ⚠️ 实测踩到：`get_comments_paged` 已经扁平化过了：

        rpid / user_name / mid / user_avatar
        message / like_count / ctime / replies_count

    我第一版按 B站**原始 API** 的嵌套结构取
    （`user.uname` / `content.message` / `like` / `rcount`）
    → **每条评论的作者和正文都是空的**，而 `total` 是对的（355045），
    看起来像"取到了但全空"，极难定位。

    所以归一函数要**两种形态都兼容**。
    """
    from app.api.v1.comments import _normalize_bili_comment

    # 扁平形态（实际返回）
    flat = {
        "rpid": 123, "user_name": "张三", "mid": "456",
        "user_avatar": "https://a.jpg", "message": "正文",
        "like_count": 7, "ctime": 1726980430, "replies_count": 3,
    }
    r = _normalize_bili_comment(flat)
    assert r["author"] == "张三", "扁平字段没取到"
    assert r["content"] == "正文"
    assert r["likes"] == 7
    assert r["reply_count"] == 3
    assert r["avatar"] == "https://a.jpg"
    assert r["create_time"].startswith("2024-")


def test_bili_normalizer_handles_nested_fields():
    """嵌套形态（B站原始 API）也要兼容 —— 上游改了不会全空。"""
    from app.api.v1.comments import _normalize_bili_comment

    nested = {
        "rpid": 9,
        "user": {"uname": "李四"},
        "member": {"mid": 88, "avatar": "https://b.jpg"},
        "content": {"message": "嵌套正文"},
        "like": 2, "rcount": 5, "ctime": 1726980430,
    }
    r = _normalize_bili_comment(nested)
    assert r["author"] == "李四"
    assert r["content"] == "嵌套正文"
    assert r["likes"] == 2
    assert r["reply_count"] == 5
    assert r["author_id"] == "88"


def test_normalizer_survives_empty_input():
    """空/异常输入不该崩（评论是次要功能，不能拖垮详情）。"""
    from app.api.v1.comments import _normalize_bili_comment

    r = _normalize_bili_comment({})
    assert r["author"] == ""
    assert r["content"] == ""
    assert r["likes"] == 0


# =============================================================================
# 前端
# =============================================================================

def _crawler_src() -> str:
    from pathlib import Path

    p = (Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "pages" / "crawler" / "index.tsx")
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


def test_frontend_comments_tab_not_bili_only():
    """**关键回归**：评论 tab 不得只在 B站分支渲染。

    原来 `detailDrawerTab === 'comments' && platform === 'bili'` ——
    其它平台点「评论」是空白，用户以为"这条没有评论"。
    """
    src = _crawler_src()
    assert "detailDrawerTab === 'comments' && (" in src, (
        "评论 tab 不应再带 platform === 'bili' 条件"
    )
    assert "detailDrawerTab === 'comments' && detailNote.platform === 'bili'" not in src


def test_frontend_calls_unified_comments_api():
    """前端要走统一接口（不是只调 B站的）。"""
    src = _crawler_src()
    assert "getComments" in src, "要调 /api/v1/comments"


def test_frontend_shows_unsupported_reason():
    """未实现时要显示**原因**（不是"暂无评论"）。"""
    src = _crawler_src()
    assert "commentUnsupported" in src, "要显示后端给的未实现原因"
    # 501 要被单独识别
    assert "501" in src


def test_frontend_comment_fields_compatible():
    """渲染字段要兼容统一结构（author/content/likes…）与旧结构。

    统一接口返回 `author`，B站旧接口返回 `user_name` ——
    两种都要认，否则上游一改就显示空白。
    """
    src = _crawler_src()
    assert "c.author || c.user_name" in src, "作者字段要兼容"
    assert "c.content || c.message" in src, "正文字段要兼容"
    assert "c.likes ?? c.like_count" in src, "点赞字段要兼容"
    assert "c.id || c.rpid" in src, "ID 字段要兼容"
