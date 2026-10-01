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


def test_only_bili_supported_for_now():
    """当前只有 B站实现（诚实声明，不要假装支持更多）。"""
    from app.api.v1.comments import COMMENTS_SUPPORTED

    assert "bili" in COMMENTS_SUPPORTED
    # ⚠️ 如果以后实现了别的平台，改这里**同时**要改文档说明
    assert COMMENTS_SUPPORTED <= {"bili", "bilibili"}


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
