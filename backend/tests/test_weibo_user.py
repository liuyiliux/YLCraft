"""微博「用户搜索 / 用户详情 / 我的数据」的契约测试。

## 实测结论（2026-09-28）

### 用户搜索（免登录可用）

    GET /api/container/getIndex
        ?containerid=100103type=3&q={关键词}&page_type=searchall&page=N
    → cards[].card_type=11 → card_group[] → user{}

**与内容搜索的解析路径完全不同**：
    内容：cards[].card_type=9  → .mblog
    用户：cards[].card_type=11 → .card_group[].user

实测一页 20 个用户。

### 用户详情

    GET /api/container/getIndex?containerid=100505{uid}
    → data.userInfo{...}

与 MediaCrawler `get_creator_info_by_id` 一致。

### 我的数据 —— **微博没有"我是谁"的接口**

试过的都不行：

    /api/config       → 只有 {login, st, user_token, ...}，**没有 uid**
    /api/profile/me   → 404
    /api/myProfile    → 404

MediaCrawler 也一样（`creator_id` 是配置项）。

### ⚠️ 一个必须记住的坑：未登录时不能从页面抓 uid

微博首页未登录时是**推荐流**，页面里的 `/profile/{uid}` 链接
**全是别的用户**。

我第一版直接抓第一个链接 → 拿到 uid=7918597670「蓟海棠」（275 万粉），
那是个**真实博主，不是登录用户**，但代码"成功地"返回了它的资料 ——
**这种"给错人"比"没数据"危险得多**。

所以现在**先查 `/api/config` 的 `login`**，未登录直接返回 None。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 参数构造
# =============================================================================

def test_user_search_params_use_type_3():
    """用户搜索的 type 是 **3**（内容是 1）——实测确认。"""
    from app.services.platforms.weibo.apis import (
        SEARCH_TYPE_USER,
        build_user_search_params,
    )

    assert SEARCH_TYPE_USER == "3"
    p = build_user_search_params("美食", page=1)
    assert p["containerid"] == "100103type=3&q=美食"
    assert p["page_type"] == "searchall"
    assert p["page"] == "1"


def test_user_detail_params_use_100505():
    """用户详情用 `100505{uid}` 容器。"""
    from app.services.platforms.weibo.apis import (
        USER_CONTAINER_PREFIX,
        build_user_detail_params,
    )

    assert USER_CONTAINER_PREFIX == "100505"
    assert build_user_detail_params("1828872085") == {
        "containerid": "1005051828872085"
    }


def test_content_search_params_unchanged():
    """内容搜索的参数没被改坏（type 映射仍正确）。"""
    from app.services.platforms.weibo.apis import build_search_params

    assert build_search_params("美食", 1, "note")["containerid"] == "100103type=1&q=美食"
    assert build_search_params("美食", 1, "video")["containerid"] == "100103type=64&q=美食"


# =============================================================================
# 计数字符串解析（微博的坑）
# =============================================================================

@pytest.mark.parametrize("raw,expected", [
    ("58.8万", 588000),
    ("1720.1万", 17201000),
    ("1.2亿", 120000000),
    (608, 608),
    ("1,234", 1234),
    ("2.9K", 2900),
    ("", 0),
    (None, 0),
    ("abc", 0),
])
def test_parse_count(raw, expected):
    """**回归**：微博的 `followers_count` 是**带单位的字符串**（如 `"58.8万"`）。

    直接 `int()` 会炸 —— 实测踩过。
    """
    from app.services.platforms.weibo.client import parse_count

    assert parse_count(raw) == expected


# =============================================================================
# user 对象解析
# =============================================================================

USER = {
    "id": 1828872085,
    "screen_name": "美食",
    "description": "我爱生活，更爱吃喝！",
    "profile_image_url": "https://tva3.sinaimg.cn/crop.0.0.179.179.180/abc.jpg",
    "avatar_hd": "https://tva3.sinaimg.cn/crop.0.0.179.179.180/hd.jpg",
    "followers_count": "58.8万",
    "follow_count": 608,
    "statuses_count": 20325,
    "verified": False,
    "verified_reason": "",
    "gender": "f",
    "profile_url": "/u/1828872085",
}


def test_parse_user_fields():
    from app.services.platforms.weibo.client import parse_user

    u = parse_user(USER)
    assert u is not None
    assert u.id == "1828872085"
    assert u.name == "美食"
    assert u.platform == "weibo"
    assert u.desc == "我爱生活，更爱吃喝！"
    # ⚠️ 字符串带单位要解析成数字
    assert u.followers == 588000
    assert u.following == 608
    assert u.total_videos == 20325
    assert u.verified is False
    # 头像优先高清
    assert u.avatar.endswith("hd.jpg")


def test_parse_user_empty_fields():
    """字段缺失不能崩（不编造）。"""
    from app.services.platforms.weibo.client import parse_user

    u = parse_user({"id": "1"})
    assert u is not None
    assert u.followers == 0
    assert u.following == 0
    assert u.verified is False


@pytest.mark.parametrize("bad", [{}, {"screen_name": "无 id"}, None, "字符串"])
def test_parse_user_tolerates_bad_input(bad):
    from app.services.platforms.weibo.client import parse_user

    assert parse_user(bad) is None


def test_iter_card_users_handles_both_shapes():
    """用户卡片有两种形状：`card_group[].user` 与顶层 `user`。"""
    from app.services.platforms.weibo.search_patchright import _iter_card_users

    grouped = {"card_type": 11, "card_group": [{"user": {"id": "1"}}, {"user": {"id": "2"}}]}
    assert [u["id"] for u in _iter_card_users(grouped)] == ["1", "2"]

    flat = {"card_type": 11, "user": {"id": "3"}}
    assert [u["id"] for u in _iter_card_users(flat)] == ["3"]

    # 内容卡片（card_type=9，有 mblog 没 user）不应产出
    assert list(_iter_card_users({"card_type": 9, "mblog": {}})) == []


# =============================================================================
# 「我的数据」必须先查登录 —— 防止给错人的资料
# =============================================================================

def test_self_profile_checks_login_first():
    """**回归（最重要的一个）**：取自己的资料前**必须先确认登录**。

    微博首页未登录时是**推荐流**，页面里的 `/profile/{uid}` 链接
    **全是别的用户**。我第一版直接抓第一个链接 → 拿到某个 275 万粉
    博主的资料，还当成"我自己"。

    **给错人的资料比没有数据危险得多**，所以必须先查 `/api/config`
    的 `login`，为 false 直接返回 None。
    """
    from app.services.platforms.weibo import search_patchright as sp

    src = inspect.getsource(sp.get_self_profile_via_patchright)
    assert "JS_CHECK_LOGIN" in src, "必须先查登录态"
    assert "login" in src, "应检查 login 字段"
    assert "return None" in src, "未登录要返回 None（不猜身份）"

    # 顺序：先查登录，再找 uid
    i_login = src.find("JS_CHECK_LOGIN")
    i_uid = src.find("JS_FIND_SELF_UID")
    assert i_login != -1 and i_uid != -1
    assert i_login < i_uid, "必须先确认登录，再去页面找 uid"


def test_self_profile_documents_the_trap():
    """要记录"未登录会抓到别人"这个坑，避免后人又直接抓 uid。"""
    from app.services.platforms.weibo import search_patchright as sp

    doc = inspect.getsource(sp.get_self_profile_via_patchright)
    assert "别人的资料" in doc or "别的用户" in doc, "应说明会抓到别人"
    assert "7918597670" in doc or "蓟海棠" in doc, "应记录实测到的错误 uid"


def test_check_login_js_exists():
    """JS 要走 `/api/config`（那个接口才带 login 字段）。"""
    from app.services.platforms.weibo import search_patchright as sp

    assert "api/config" in sp.JS_CHECK_LOGIN
    # 登录判断由 Python 侧做（读 JSON 的 login 字段），JS 只负责取数据
    assert "fetch" in sp.JS_CHECK_LOGIN


# =============================================================================
# 用户搜索/详情走浏览器（与内容搜索同样的原因）
# =============================================================================

def test_user_functions_use_browser():
    """用户搜索/详情也要走 patchright（微博依赖 Service Worker）。"""
    from app.services.platforms.weibo import search_patchright as sp

    for fn in (sp.search_users_via_patchright, sp.get_user_via_patchright):
        src = inspect.getsource(fn)
        assert "_get_session" in src, f"{fn.__name__} 应走浏览器会话"
