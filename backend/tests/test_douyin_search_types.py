"""抖音搜索个性化（四类页签）的契约测试。

2026-09-26 由 URL 抓包确认（点击抖音搜索页页签后 URL 变化）：
    /search/小说?type=general   综合
    /search/小说?type=video     视频
    /search/小说?type=user      用户
    /search/小说?type=live      直播

这些是**实测抓到的真实值**，不是猜的——与仓库硬规则一致
（不臆造 API 路径/参数）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# search_channel 映射
# =============================================================================

def test_search_channels_are_the_captured_values():
    """四个 search_channel 必须是抓包确认的值。"""
    from app.services.platforms.douyin.apis import SEARCH_CHANNELS

    assert SEARCH_CHANNELS["general"] == "aweme_general"
    assert SEARCH_CHANNELS["video"] == "aweme_video"
    assert SEARCH_CHANNELS["user"] == "aweme_user"
    assert SEARCH_CHANNELS["live"] == "aweme_live"


@pytest.mark.parametrize(
    "search_type,expected",
    [
        ("note", "aweme_general"),      # 前端「综合」传的是 note
        ("general", "aweme_general"),
        ("video", "aweme_video"),
        ("user", "aweme_user"),
        ("live", "aweme_live"),
        ("VIDEO", "aweme_video"),       # 大小写不敏感
        (" video ", "aweme_video"),     # 容错空白
    ],
)
def test_resolve_search_channel(search_type, expected):
    from app.services.platforms.douyin.apis import resolve_search_channel

    assert resolve_search_channel(search_type) == expected


@pytest.mark.parametrize("bad", [None, "", "unknown", "topic", "series"])
def test_unknown_search_type_falls_back_to_general(bad):
    """未知类型回退到「综合」，而不是抛错。

    给综合结果比给一句报错更有用；前端也已按后端能力收敛选项，
    所以这里主要是防御性行为。
    """
    from app.services.platforms.douyin.apis import resolve_search_channel

    assert resolve_search_channel(bad) == "aweme_general"


def test_build_search_params_honors_channel():
    """build_search_params 必须真的把 search_channel 放进 query。"""
    from app.services.platforms.douyin.apis import build_search_params

    p = build_search_params(keyword="美食", offset=0, count=5, search_channel="aweme_video")
    assert p["search_channel"] == "aweme_video"
    assert p["keyword"] == "美食"
    assert p["count"] == "5"


def test_build_search_params_defaults_channel():
    """不传 channel 时用默认值，不能是空串（空串会被服务端当无效参数）。"""
    from app.services.platforms.douyin.apis import build_search_params

    p = build_search_params(keyword="x")
    assert p["search_channel"], "search_channel 不能为空"
    assert p["search_channel"].startswith("aweme_")


# =============================================================================
# 客户端接线
# =============================================================================

def test_client_uses_resolve_search_channel():
    """search() 必须用 resolve_search_channel，不能再对 user/live 抛 NotImplemented。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "resolve_search_channel" in src
    assert "NotImplementedError" not in src, (
        "四类页签都已实现，不应再对 search_type 抛未实现"
    )


def test_client_documents_captured_tabs():
    """docstring 要写明四个类型来自抓包，方便后来者核对。"""
    from app.services.platforms.douyin.client import DouyinClient

    doc = DouyinClient.search.__doc__ or ""
    for word in ("综合", "视频", "用户", "直播"):
        assert word in doc, f"docstring 应说明 {word} 类型"


def test_client_passes_channel_into_params():
    """search() 必须把 channel 传给 build_search_params。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "search_channel=" in src
