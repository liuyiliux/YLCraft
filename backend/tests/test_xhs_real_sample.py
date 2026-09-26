"""用**真实抓包样本**验证小红书搜索卡片解析（离线，不联网）。

样本来源：browser-skill 从用户已登录 Chrome 打开真实搜索页后，
用与实现**完全相同的选择器**读出的卡片数据。
文件：.local/xhs-sample-cards.json

价值：证明 parse_card 对真实字段有效（点赞是"2.3万"这种中文计数、
xsec_token 存在、id 是 24 位 hex），而不只是对我编的假数据有效。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

SAMPLE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", ".local", "xhs-sample-cards.json",
)


def _load_sample():
    if not os.path.exists(SAMPLE):
        pytest.skip("真实抓包样本不存在（.local/xhs-sample-cards.json 未生成）")
    with open(SAMPLE, encoding="utf-8-sig") as f:
        return json.load(f)


def test_real_cards_parse():
    """真实卡片必须能全部解析出来（不要丢条目）。"""
    from app.services.platforms.xiaohongshu.search_patchright import parse_card

    cards = _load_sample()
    assert cards, "样本为空"

    results = [parse_card(c) for c in cards]
    assert len(results) == len(cards)

    for r in results:
        assert r.id, "id 解析失败"
        assert r.platform == "xiaohongshu"
        assert r.type in ("note", "video")
        # URL 必须带 xsec_token，否则点进去会被拒
        assert "xsec_token=" in r.url


def test_real_cards_likes_use_chinese_count():
    """真实点赞是 '2336' / '2.3万' 这类，必须解析成 int。"""
    from app.services.platforms.xiaohongshu.search_patchright import parse_card

    results = [parse_card(c) for c in _load_sample()]
    for r in results:
        assert isinstance(r.likes, int)
        assert r.likes >= 0
    # 样本里应至少有一条非零点赞（否则说明选择器没取到）
    assert any(r.likes > 0 for r in results), "点赞全是 0，选择器可能失效"


def test_real_cards_title_and_author_present():
    """标题与作者是卡片的核心信息，不能全空。"""
    from app.services.platforms.xiaohongshu.search_patchright import parse_card

    results = [parse_card(c) for c in _load_sample()]
    assert any(r.title for r in results), "一个标题都没解析出来"
    assert any(r.author for r in results), "一个作者都没解析出来"


def test_real_cards_xsec_token_preserved():
    """xsec_token 必须落到 raw_data（详情跳转要用）。"""
    from app.services.platforms.xiaohongshu.search_patchright import parse_card

    for c in _load_sample():
        r = parse_card(c)
        assert r.raw_data.get("xsec_token") is not None


def test_real_card_ids_are_24_hex():
    """小红书 note id 是 24 位 hex，正则抓错会长短不一。"""
    import re

    for c in _load_sample():
        assert re.fullmatch(r"[a-f0-9]{24}", c["id"]), f"id 形态异常：{c['id']}"
