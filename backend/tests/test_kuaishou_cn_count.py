"""`_parse_cn_count` 的单元测试 —— 用**实测真实值**。

实测（2026-10-07，带真实 cookie，uid=3xep6p7wbnqcvj6）：
    GraphQL: {"fan":"1.3万", "photo":null,
              "follow":8, "photo_public":176}
    页面显示:  关注 8 / 粉丝 1.3万 / 获赞 5.5万

⚠️ 这个 bug 的代价：`_to_int("1.3万")` → 0 ⇒ 粉丝恒显示 0，
而我一度据此得出"快手不提供粉丝数"的**错误结论**。
"""
from __future__ import annotations

from app.services.platforms.kuaishou.apis import _parse_cn_count


def test_real_values_from_bilibili():
    """**实测真实返回值**（最重要的一条）。"""
    assert _parse_cn_count("1.3万") == 13000, "实测 fan 就是 '1.3万'，不能变 0"
    assert _parse_cn_count(8) == 8, "实测 follow 是数字 8"
    assert _parse_cn_count(176) == 176, "实测 photo_public 是数字 176"
    # ⚠️ photo 实测返回 null —— 作品数要读 photo_public，不是 photo
    assert _parse_cn_count(None) == 0


def test_chinese_units():
    assert _parse_cn_count("5.5万") == 55000
    assert _parse_cn_count("12.3亿") == 1_230_000_000
    assert _parse_cn_count("3亿") == 300_000_000
    assert _parse_cn_count("2w") == 20000
    assert _parse_cn_count("1.5W") == 15000


def test_plain_numbers_and_thousands_sep():
    assert _parse_cn_count(0) == 0
    assert _parse_cn_count(123) == 123
    assert _parse_cn_count("123") == 123
    assert _parse_cn_count("1,234") == 1234
    assert _parse_cn_count(1.9) == 1


def test_missing_and_garbage():
    assert _parse_cn_count("") == 0
    assert _parse_cn_count("   ") == 0
    assert _parse_cn_count(None) == 0
    # 不可解析时不编造数字
    assert _parse_cn_count("暂无") == 0
    assert _parse_cn_count("abc") == 0
