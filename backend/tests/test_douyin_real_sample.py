"""用**真实抓包样本**验证抖音解析器（离线，不联网）。

样本来源：browser-skill 从用户已登录 Chrome 抓取的真实响应
（已脱敏：剥掉 URL 里的签名参数，只留解析需要的字段）。
文件：.local/douyin-sample-items.json

这个测试的价值：证明解析器对**真实字段**有效，而不只是对我自己编的假数据有效。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

SAMPLE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),   # backend/tests
    "..", "..",                                   # 仓库根
    ".local", "douyin-sample-items.json",
)


def _load_sample():
    if not os.path.exists(SAMPLE):
        pytest.skip("真实抓包样本不存在（.local/douyin-sample-items.json 未生成）")
    # utf-8-sig：PowerShell 的 Out-File 会写 BOM，要能容忍
    with open(SAMPLE, encoding="utf-8-sig") as f:
        return json.load(f)


def test_real_sample_parses():
    """真实抖音响应必须能被 parse_search_item 正常解析。"""
    from app.services.platforms.douyin.client import parse_search_item

    items = _load_sample()
    assert items, "样本为空"

    parsed = [p for p in (parse_search_item(i) for i in items) if p is not None]
    assert len(parsed) == len(items), "有真实条目被丢弃，解析器太严"

    for r in parsed:
        # 每条都该有 id 和 URL
        assert r.id, "aweme_id 解析失败"
        assert r.url == f"https://www.douyin.com/video/{r.id}"
        assert r.platform == "douyin"
        assert r.type in ("note", "video")


def test_real_sample_stats_are_ints():
    """统计字段必须是 int（真实响应里可能是 str 或缺失）。"""
    from app.services.platforms.douyin.client import parse_search_item

    for item in _load_sample():
        r = parse_search_item(item)
        assert r is not None
        for field in ("likes", "comments", "shares", "collects", "views", "duration"):
            value = getattr(r, field)
            assert isinstance(value, int), f"{field} 不是 int：{type(value)}"
            assert value >= 0


def test_real_sample_duration_is_seconds():
    """抖音 duration 是毫秒，解析后必须是秒（否则时长会大 1000 倍）。"""
    from app.services.platforms.douyin.client import parse_search_item

    items = _load_sample()
    parsed = [parse_search_item(i) for i in items]
    raws = [((i.get("aweme_info") or {}).get("video") or {}).get("duration") or 0
            for i in items]

    for r, raw_ms in zip(parsed, raws):
        if raw_ms:
            assert r.duration == int(raw_ms) // 1000, "毫秒→秒换算不对"
            assert r.duration < 100000, "秒数异常大，可能没换算"


def test_real_sample_has_author_and_desc():
    """真实样本应能取到作者昵称和正文（否则卡片会显示空白）。"""
    from app.services.platforms.douyin.client import parse_search_item

    parsed = [parse_search_item(i) for i in _load_sample()]
    assert any(r.author for r in parsed), "一个作者都没解析出来"
    assert any(r.title for r in parsed), "一个标题都没解析出来"


def test_real_sample_extract_items_handles_index_object():
    """真实响应可能给数组、也可能给 {"0":...} 索引对象，两种都要能取。

    抓包实测：同一次会话里两种形态都出现过（dataIsObject 时真时假）。
    """
    from app.services.platforms.douyin.client import DouyinClient

    items = _load_sample()

    # 数组形态
    assert len(DouyinClient._extract_items({"data": items})) == len(items)
    # 索引对象形态
    indexed = {str(i): it for i, it in enumerate(items)}
    assert len(DouyinClient._extract_items({"data": indexed})) == len(items)
