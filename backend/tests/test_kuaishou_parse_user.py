"""快手 `parse_user` 的解析测试（不需要登录态、不联网）。

## 钉住的核心事实（2026-10-07 **实测**核对）

拿真实响应（关键词「沈阳」）打出来，`/search/user` 返回的**全部字段**只有：

    headurl / isFollowing / livingInfo / user_id / user_name / user_text / verified

**没有任何计数**（无 fan、无 photoCount、无…）⇒ 粉丝/关注/作品**必然是 0**。
这是**平台限制**，不是解析 bug。

所以这里主要钉住两件事：
  1. 这条事实本身（别哪天有人"修"出一堆无效候选字段名）
  2. `stats_available=False` 必须存在（前端据此显示「接口不提供」而不是 0）
"""
from __future__ import annotations

from app.services.platforms.kuaishou.apis import parse_user

# 实测抓到的真实 users[] 条目（字段一个不多、一个不少）
REAL_SEARCH_USER_ITEM = {
    "headurl": "https://p2-pro.a.yximgs.com/uhead/AB/2026/08/17/17/BMjAyNjA4MTcxNzU0MjZfMTU3ODA1.jpg",
    "isFollowing": False,
    "livingInfo": {"living": False, "livingId": None, "iconType": 0},
    "user_id": "3xep6p7wbnqcvj6",
    "user_name": "沈阳",
    "user_text": "大家好～我叫沈阳没有小～",
    "verified": False,
}


def test_real_response_has_no_counters():
    """**实测事实**：快手 `/search/user` 返回里**没有任何数字统计**。

    ⚠️ 这条测试的作用是**防止反向"修复"**：
    看到"粉丝恒为 0"很容易有人去猜一串字段名（photoCount/works/…），
    但接口根本不返回 —— 加再多候选也只是空转。
    """
    p = parse_user(REAL_SEARCH_USER_ITEM)
    assert p is not None
    assert p["followers"] == 0
    assert p["following"] == 0
    assert p["total_videos"] == 0


def test_declares_stats_unavailable():
    """必须声明"统计不可得"，前端才能显示「接口不提供」而不是 0。"""
    p = parse_user(REAL_SEARCH_USER_ITEM)
    assert p["stats_available"] is False, (
        "缺少 stats_available=False —— 前端会把 0 当成真数字显示"
    )


def test_parses_identity_fields():
    """身份字段是有的，必须正常解析。"""
    p = parse_user(REAL_SEARCH_USER_ITEM)
    assert p["id"] == "3xep6p7wbnqcvj6"
    assert p["name"] == "沈阳"
    assert p["avatar"].startswith("https://")
    assert "沈阳" in p["desc"]


def test_keeps_legacy_fields():
    """**回归**：原有字段不能被改动弄坏。"""
    p = parse_user({
        "id": "3xdefy9fk9fcadc",
        "user_name": "逸流AI",
        "headurl": "https://example.com/a.jpg",
        "user_text": "签名",
        "fan": 20,
        "verified": True,
    })
    assert p["id"] == "3xdefy9fk9fcadc"
    assert p["name"] == "逸流AI"
    assert p["avatar"] == "https://example.com/a.jpg"
    assert p["followers"] == 20          # 兼容旧字段名（若某些入口真带数字）
    assert p["desc"] == "签名"
    assert p["verified"] is True


def test_followers_fallback_names():
    """若将来某个入口带了数字，多种叫法都能取到。"""
    assert parse_user({"id": "a", "user_name": "x", "followerCount": 7})["followers"] == 7
    assert parse_user({"id": "a", "user_name": "x", "fansCount": 9})["followers"] == 9


def test_zero_value_does_not_block_fallback():
    """`0` 视作"没有这个值"，继续试下一个候选。"""
    p = parse_user({"id": "a", "user_name": "x", "fan": 0, "followerCount": 15})
    assert p["followers"] == 15


def test_missing_fields_stay_zero_not_invented():
    """取不到就返回 0 —— **绝不编造数字**。"""
    p = parse_user({"id": "a", "user_name": "x"})
    assert p["followers"] == 0
    assert p["following"] == 0
    assert p["total_videos"] == 0


def test_invalid_input_returns_none():
    assert parse_user(None) is None
    assert parse_user({}) is None          # 既没 id 也没名字
