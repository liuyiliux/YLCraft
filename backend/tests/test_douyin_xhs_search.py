"""抖音搜索 / 小红书 Patchright 搜索 契约测试。

2026-09-26 由 browser-skill 接管用户已登录 Chrome 抓包确认：

抖音：
  GET https://www.douyin.com/aweme/v1/web/general/search/single/
  → {"status_code":0,"data":[{"type":1,"aweme_info":{...}}],"cursor":5,"has_more":1}
  实测**不需要** msToken/a_bogus 签名（与番茄不同）。

小红书（重要更正）：
  真实端点已迁移为 https://so.xiaohongshu.com/api/sns/web/v2/search/notes，
  **不是**代码里旧写的 edith.xiaohongshu.com/api/sns/web/v1/search/notes
  （旧端点实测返回 code:300011「当前账号存在异常」= 缺签名被拒）。
  该接口需要 X-s/X-t 签名，签名函数 window._webmsxyw 是混淆 JS 且跨域调用 406，
  故改用 Patchright 打开搜索页读 DOM（section.note-item，实测 30 条/页）。
"""

from __future__ import annotations

import inspect


# =============================================================================
# 抖音
# =============================================================================

def test_douyin_search_endpoint_constant():
    from app.services.platforms.douyin.apis import SEARCH_SINGLE

    assert SEARCH_SINGLE == "/aweme/v1/web/general/search/single/"


def test_douyin_client_registered_both_aliases():
    """douyin 和 dy 都要能建出客户端——前端搜索用的是 dy。"""
    from app.services.platforms import create_client

    for alias in ("douyin", "dy"):
        client = create_client(alias, mode="api", cookie="probe=1")
        assert client is not None, f"{alias} 未注册"
        assert type(client).__name__ == "DouyinClient"


def test_douyin_build_params_has_required_keys():
    """抓包确认的最小可用参数集。"""
    from app.services.platforms.douyin.apis import build_search_params

    p = build_search_params("小说", offset=0, count=10)
    for key in ("aid", "device_platform", "channel", "search_channel",
                "keyword", "offset", "count"):
        assert key in p, f"缺少必要参数 {key}"
    assert p["keyword"] == "小说"
    assert p["count"] == "10"


def test_douyin_extract_items_handles_index_object():
    """抖音的 data 实测是**按数字索引的对象**而非数组，必须能取出来。

    这个坑的代价：按数组取值会静默拿到 []，看起来像"没搜到"。
    """
    from app.services.platforms.douyin.client import DouyinClient

    data = {"data": {"0": {"aweme_info": {"aweme_id": "1"}},
                     "1": {"aweme_info": {"aweme_id": "2"}}}}
    items = DouyinClient._extract_items(data)
    assert len(items) == 2

    # 数组形式也要兼容
    assert len(DouyinClient._extract_items({"data": [{"a": 1}]})) == 1
    # 取不到时返回空而不是抛异常
    assert DouyinClient._extract_items({}) == []


def test_douyin_parse_search_item():
    """解析抓包确认的条目结构。"""
    from app.services.platforms.douyin.client import parse_search_item

    item = {
        "type": 1,
        "aweme_info": {
            "aweme_id": "7300000000000000000",
            "desc": "全文50分钟，一口气看完。#小说",
            "create_time": 1700000000,
            "author": {"nickname": "某作者", "uid": "123"},
            "statistics": {"digg_count": 100, "comment_count": 5,
                           "share_count": 2, "collect_count": 7,
                           "play_count": 999},
            "video": {"duration": 43000,
                      "cover": {"url_list": ["https://x/cover.jpeg"]}},
        },
    }
    r = parse_search_item(item)
    assert r is not None
    assert r.id == "7300000000000000000"
    assert r.author == "某作者"
    assert r.likes == 100 and r.comments == 5 and r.views == 999
    assert r.duration == 43, "抖音时长是毫秒，应换算成秒"
    assert r.cover == "https://x/cover.jpeg"
    assert r.platform == "douyin"
    assert r.url.endswith("7300000000000000000")


def test_douyin_parse_skips_entries_without_aweme_info():
    """广告/运营卡片没有 aweme_info，必须跳过而不是崩。"""
    from app.services.platforms.douyin.client import parse_search_item

    assert parse_search_item({"type": 1}) is None
    assert parse_search_item({"aweme_info": {}}) is None
    assert parse_search_item(None) is None


def test_douyin_get_detail_not_implemented_loudly():
    """未抓包确认的能力要显式报错，不能静默返回 None。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_detail)
    assert "NotImplementedError" in src


def test_douyin_routes_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/douyin/health" in paths


# =============================================================================
# 小红书
# =============================================================================

def test_xhs_old_v1_endpoint_is_documented_as_dead():
    """旧 v1/edith 端点已失效，代码里必须留下更正说明，避免有人改回去。"""
    from app.services.platforms.xiaohongshu import apis

    src = inspect.getsource(apis)
    assert "so.xiaohongshu.com" in src, "应记录真实端点"
    assert "300011" in src or "失效" in src or "已迁移" in src, "应说明旧端点已失效"


def test_xhs_search_patchright_reads_dom():
    """Patchright 搜索必须走真实搜索页并解析 section.note-item。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp)
    assert "section.note-item" in src, "应解析实测存在的卡片选择器"
    assert "search_result" in src, "应打开真实搜索页"
    assert "xsec_token" in src, "xsec_token 是跳转详情必需参数"


def test_xhs_patchright_requires_cookie_or_browser():
    """既没有浏览器上下文、也没有 Cookie 时要明确报错，不能偷偷返回空列表。

    '返回空' 会被上层理解成 '没搜到'，属于假阴性。
    """
    import asyncio

    from app.services.platforms.types import ClientConfig, ClientMode, SearchParams
    from app.services.platforms.xiaohongshu.search_patchright import (
        search_via_patchright,
    )

    class FakeClient:
        _patchright_page = None

        class config:
            cookie = ""  # 没有 Cookie

    try:
        asyncio.get_event_loop().run_until_complete(
            search_via_patchright(FakeClient(), SearchParams(keyword="x"))
        )
    except RuntimeError as e:
        msg = str(e)
        assert "Cookie" in msg or "浏览器" in msg, f"错误信息不可读：{msg}"
    else:
        raise AssertionError("缺浏览器和 Cookie 时应抛 RuntimeError")


def test_xhs_html_card_extraction():
    """从渲染后的 HTML 抽卡片：真实 href 形态必须能解析出 id 与 xsec_token。"""
    from app.services.platforms.xiaohongshu.search_patchright import (
        _parse_cards_from_html,
    )

    html = (
        '<a class="cover" href="/search_result/6a088d4c000000003502bac3'
        '?xsec_token=ABUNkf6Ebj14dve4-GR_TMcaWHMHoAIajgtYhQ8lM4Fm0=&xsec_source=">'
        '</a>'
        # 重复项要去重
        '<a href="/search_result/6a088d4c000000003502bac3?xsec_token=SAME&xsec_source="></a>'
        '<a href="/search_result/6ab22a730000000031002345?xsec_token=SECOND&xsec_source="></a>'
    )
    cards = _parse_cards_from_html(html)
    assert len(cards) == 2, "应去重"
    assert cards[0]["id"] == "6a088d4c000000003502bac3"
    assert cards[0]["xsec_token"].startswith("ABUNkf6E")
    assert cards[1]["xsec_token"] == "SECOND"


def test_xhs_parse_count():
    from app.services.platforms.xiaohongshu.search_patchright import parse_count

    assert parse_count("2.3万") == 23000
    assert parse_count("1128") == 1128
    assert parse_count("") == 0
    assert parse_count("abc") == 0
