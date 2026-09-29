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


def test_douyin_get_detail_uses_real_api():
    """详情已实现（2026-09-27 找到真实端点），不能再是 NotImplementedError。

    端点：GET https://www-hj.douyin.com/aweme/v1/web/aweme/detail/
    （域名是 www-hj，不是 www —— 这是长期没找到的原因。）
    """
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_detail)
    assert "AWEME_DETAIL" in src or "aweme/detail" in src, "应调真实详情接口"
    assert "NotImplementedError" not in src, "详情已实现，不该再抛未实现"


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


def test_xhs_api_mode_is_real_and_requires_cookie():
    """**API 模式现在是主路径**（2026-09-29 打通），仍要"明确报错不静默"。

    ## 修正了一个错误结论

    这里原本断言"API 模式必须抛错，因为端点已返回 code:300011"。

    **300011 是"缺 X-s/X-t 签名被风控拒"，不是端点废弃** ——
    这句话原测试的 docstring 里就写着，却被当成了端点死了的证据。

    装上 `xhshow` 后实测：
        POST edith.../api/sns/web/v1/search/notes
        → 200, success=True, data.items[21]

    现在 API 模式真正去搜；**没有 cookie 时抛可操作错误**
    （不静默返回空列表 —— 那条原则仍然要守）。
    """
    import asyncio

    from app.services.platforms.types import SearchParams
    from app.services.platforms.xiaohongshu.search import search_via_api

    class _Cfg:
        cookie = ""

    class _Cli:
        config = _Cfg()

    try:
        asyncio.get_event_loop().run_until_complete(
            search_via_api(_Cli(), SearchParams(keyword="小说"))
        )
    except RuntimeError as e:
        assert "Cookie" in str(e), "缺 cookie 要说明清楚"
    else:
        raise AssertionError("缺 cookie 时应抛 RuntimeError，不能静默返回空")


def test_xhs_search_endpoint_is_usable():
    """端点常量要指向**可用**的 edith v1（不是"已死"的）。"""
    from app.services.platforms.xiaohongshu import search as search_mod

    assert "edith.xiaohongshu.com" in search_mod.REAL_ENDPOINT
    assert "/api/sns/web/v1/search/notes" in search_mod.REAL_ENDPOINT
    # 不该再有"已死端点"这种命名（它误导过两轮排查）
    assert not hasattr(search_mod, "DEAD_V1_ENDPOINT"), (
        "不该保留 DEAD_V1_ENDPOINT —— 那个端点其实可用"
    )


def test_crawler_uses_api_for_xhs():
    """**回归**：crawler 分发时必须给小红书选 api（纯 HTTP）。

    原来硬编码在 BROWSER_ONLY 里（基于"端点已停用"的错误结论），
    导致每次搜索都白开浏览器（15 秒 vs 现在的 3 秒）。

    微博仍留在 BROWSER_ONLY —— 它需要 Service Worker 上下文。
    """
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    # BROWSER_ONLY 不该包含 xhs
    line = next(
        (ln for ln in src.splitlines() if "BROWSER_ONLY" in ln and "=" in ln), ""
    )
    assert line, "应能找到 BROWSER_ONLY 定义"
    assert '"xhs"' not in line and "'xhs'" not in line, (
        "小红书不该在 BROWSER_ONLY 里（纯 HTTP 可用）"
    )
    assert "weibo" in line, "微博应仍在 BROWSER_ONLY（需要 Service Worker）"


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
