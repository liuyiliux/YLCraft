"""快手 `parse_user` 的解析测试（不需要登录态、不联网）。

## 钉住的核心事实

**搜索接口** `/search/user` 的真实返回（关键词「沈阳」实测）只有 7 个字段：

    headurl / isFollowing / livingInfo / user_id / user_name / user_text / verified

**没有任何计数** ⇒ 搜出来的条目 `followers/following/total_videos` 必然是 0。

## ⚠️⚠️ 但这**不等于**"快手页面上没有这些数字"

用户截图（**未登录**的浏览器）明明白白显示：关注 8 / 粉丝 1.3万 / 获赞 5.5万。

两次抓包（2026-10-07）定位了真正来源：**`POST /s/w/c`**，一个
**端到端加密**接口（请求体 `{"data":"1gCA…"}`、响应
`{"dataRsp":"In+Wx…","result":1}`，都是密文；加解密在快手前端 JS bundle 里）。
它不在任何普通 REST 接口中 ⇒ 现有的签名机制取不到。

⚠️ 我先后下过两个**都错**的结论，这条测试就是防它们复发的：
  ① "快手没有这些数字"      —— 用户截图推翻
  ② "要登录态才能取到"      —— 用户截图（未登录）推翻；109 的含义是
                             "这个接口没给数字"，不是"数字被锁住"

所以 `stats_available=False` 只描述**搜索接口**，
前端据此显示「—」而不是 0（0 是谎报）。
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
    """**实测事实（仍然成立）**：搜索接口 `/search/user` 返回里**没有计数**。

    ⚠️ 但这**不代表快手页面上没有这些数字**！
    2026-10-07 抓包发现：页面上的数字来自 **`POST /s/w/c`**（端到端加密），
    未登录时页面**照样显示**（用户截图：关注 8 / 粉丝 1.3万 / 获赞 5.5万）。

    ⚠️ 我曾据这条结论写过"快手不提供博主统计数字"，**那是错的**。
    这条测试的作用是提醒：**搜索结果**里没有 ≠ **平台**没有。
    """
    p = parse_user(REAL_SEARCH_USER_ITEM)
    assert p is not None
    assert p["followers"] == 0
    assert p["following"] == 0
    assert p["total_videos"] == 0


def test_declares_stats_unavailable():
    """`stats_available=False` 只描述**搜索结果**这件事。

    ⚠️ 措辞很重要：它说的是"这个搜索接口拿不到"，**不是**"平台没有"。
    数字确实存在于快手页面，只是来自加密接口 `/s/w/c`，我们读不到。
    """
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
