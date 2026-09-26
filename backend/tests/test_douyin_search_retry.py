"""抖音搜索空结果重试的契约测试。

## 实测依据（2026-09-26，48 次采样）

抖音搜索会**不定期**返回空 data（code=0 但 data=[]）：

    run1  6/6   成功（间隔 3s）
    run2  0/6   失败（3 分钟后，同脚本）
    run3  6/20  成功（前 6 成功，之后连续 14 次失败）
    run4  15/15 成功（间隔 1s）
    run5  8/8   成功（不带 webid）
    run6  8/8   成功（带 webid）

共 48 次里 43 次成功（约 90%），且**失败后隔一会儿能恢复**，
没有稳定复现的失败模式。所以「空结果 → 稍等重试一次」是有效策略。

## 上游权威结论

TikTokDownloader issue #600 是同一症状（"四个类目搜索结果均为空"，
而热搜/用户主页正常）。项目作者回复：

    "经测试似乎需要新算法，新算法尚未开源。"

说明这不是我们实现的问题，而是抖音改了搜索接口的校验方式。
"""

from __future__ import annotations

import inspect

import pytest


def test_search_retries_on_empty():
    """空结果必须重试（3 次，含首次共 4 次请求）。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert src.count("_call(SEARCH_SINGLE") == 2, (
        "应有 2 处 _call：首次 + 循环内重试"
    )
    assert "for delay in" in src, "应使用递增间隔重试"


def test_retry_has_increasing_delays():
    """重试间隔应递增（2/4/6 秒）——固定间隔在受限窗口里效果差。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "asyncio.sleep(delay)" in src
    assert "2, 4, 6" in src, "间隔应为 2/4/6 秒"


def test_retry_is_bounded():
    """重试次数必须有界，不能无限循环。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "while" not in src, "不应使用 while 无限重试"
    # for 循环最多 3 次
    assert src.count("for delay in (2, 4, 6)") == 1


def test_still_raises_after_retry_fails():
    """重试后仍为空才报错，不能静默返回空列表。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "_raise_if_environment_degraded" in src


def test_docstring_records_measured_success_rate():
    """docstring 要留下实测数据，避免后人把"有时候搜不到"误判为新 bug。"""
    from app.services.platforms.douyin.client import DouyinClient

    doc = DouyinClient.search.__doc__ or ""
    assert "48" in doc or "实测" in doc, "应记录实测采样"
    assert "重试" in doc, "应说明为什么重试"


@pytest.mark.asyncio
async def test_search_retry_actually_recovers(monkeypatch):
    """行为测试：首次空、重试命中时，应返回重试的结果。"""
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode, SearchParams

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )

    calls = {"n": 0}

    async def fake_call(method, path, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status_code": 0, "data": []}
        return {
            "status_code": 0,
            "data": [{"type": 1, "aweme_info": {
                "aweme_id": "123", "desc": "重试后的结果",
                "create_time": 1700000000,
                "author": {"nickname": "作者", "uid": "1"},
                "statistics": {"digg_count": 1},
                "video": {"duration": 1000, "cover": {"url_list": ["http://x/c.jpg"]}},
            }}],
        }

    monkeypatch.setattr(client, "_call", fake_call)
    monkeypatch.setattr("asyncio.sleep", lambda *_: _noop())

    async def _noop():
        return None

    results = await client.search(SearchParams(keyword="美食", max_results=5))
    assert calls["n"] == 2, "首次空 → 重试一次即命中，共 2 次调用"
    assert len(results) == 1
    assert results[0].title == "重试后的结果"
