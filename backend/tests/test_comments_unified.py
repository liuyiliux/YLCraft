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
    """
    import inspect

    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_comments)
    assert "空响应体" in src or "0 字节" in src
    assert "a_bogus" in src
    # 不能把空当成"0 条评论"返回
    assert "不是「没有评论」" in src or "不是没有评论" in src or "不是「没有评论」" in src


def test_unimplemented_platforms_have_reasons():
    """每个主要平台都要有**具体原因**（不是一句"不支持"）。

    用户能看到"为什么做不到"，才知道要不要等、能不能绕。
    """
    from app.api.v1.comments import COMMENTS_TODO_REASON

    for p in ("xhs", "douyin", "dy", "weibo", "kuaishou", "ks",
              "twitter", "youtube", "telegram"):
        assert p in COMMENTS_TODO_REASON, f"{p} 缺说明"
        assert len(COMMENTS_TODO_REASON[p]) > 8, f"{p} 的说明太简短"


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
