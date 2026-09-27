"""抖音搜索翻页的契约测试。

## 用户反馈（2026-09-27）

"抖音搜索显示很多，我们只有九条"

原因：原实现**只请求一次、count 固定 10**，所以永远只有 9~10 条，
而网页端能看到几十条（它自己在翻页）。

## 实测依据

抖音接口支持 offset/count 翻页：同一 keyword 下
offset=0/20/40 返回的 cursor 依次为 0/40/60，说明分页参数生效。

单页上限实测为 20（请求 count>20 也不会多给），所以翻页按 20 切。

## 为什么用 mock 测

抖音搜索有**间歇性受限**（实测约 90% 成功），
跑测试时可能正好撞上受限窗口，导致测试不稳定。
所以这里用假的 `_call` 验证翻页逻辑本身。

注意 `_call` 的真实签名是 `_call(self, path, params=None)` ——
mock 必须与之一致，否则 params 会落到 path 上（这个坑踩过一次）。
"""

from __future__ import annotations

import inspect

import pytest


def _item(item_id: str, desc: str = "x") -> dict:
    """构造一条符合抓包结构的条目。"""
    return {
        "type": 1,
        "aweme_info": {
            "aweme_id": str(item_id),
            "desc": desc,
            "create_time": 1700000000,
            "author": {"nickname": "作者", "uid": "1"},
            "statistics": {"digg_count": 1},
            "video": {"duration": 1000, "cover": {"url_list": ["http://x/c.jpg"]}},
        },
    }


def test_search_paginates():
    """search 必须支持翻页，不能只请求一次。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "max_pages" in src, "应有页数循环"
    assert "offset" in src, "应用 offset 推进"


def test_single_page_max_is_20():
    """单页上限 20（实测请求更多也不给）。"""
    from app.services.platforms.douyin.apis import SINGLE_PAGE_MAX

    assert SINGLE_PAGE_MAX == 20


def test_search_dedupes_across_pages():
    """跨页要去重——服务端翻页可能返回重复条目。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "seen" in src, "应有去重集合"


def test_search_uses_cursor_to_advance():
    """优先用响应里的 cursor 推进（比自算 offset 更贴合服务端）。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "cursor" in src


def test_retry_only_on_first_page():
    """只在第一页重试。

    翻页中途为空通常是真的到底了，再重试只是白等 12 秒。
    """
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "page_idx == 0" in src, "重试应限定在第一页"


@pytest.mark.asyncio
async def test_pagination_collects_more_than_one_page(monkeypatch):
    """行为测试：要 30 条时应发出多次请求并合并结果。"""
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode, SearchParams

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )

    calls: list[tuple[int, int]] = []

    async def fake_call(path, params=None):
        offset = int((params or {}).get("offset", 0))
        count = int((params or {}).get("count", 10))
        calls.append((offset, count))
        return {
            "status_code": 0,
            "cursor": offset + count,
            "has_more": 1,
            "data": [_item(offset + i, f"第{offset + i}条") for i in range(count)],
        }

    monkeypatch.setattr(client, "_call", fake_call)

    results = await client.search(SearchParams(keyword="x", max_results=30))

    assert len(results) == 30, f"应合并出 30 条，实得 {len(results)}"
    assert len(calls) >= 2, f"应发出多次请求，实际 {calls}"
    assert calls[0][1] == 20, f"单页应用 20，实际 {calls[0][1]}"
    ids = [r.id for r in results]
    assert len(set(ids)) == len(ids), "结果应去重"


@pytest.mark.asyncio
async def test_pagination_dedupes_repeated_items(monkeypatch):
    """服务端翻页返回重复条目时，结果要去重。"""
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode, SearchParams

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )

    async def fake_call(path, params=None):
        # 每页都返回同样的 5 条（模拟服务端不去重）
        return {
            "status_code": 0,
            "cursor": 999,
            "has_more": 1,
            "data": [_item(i, f"重复{i}") for i in range(5)],
        }

    monkeypatch.setattr(client, "_call", fake_call)

    results = await client.search(SearchParams(keyword="x", max_results=20))
    ids = [r.id for r in results]
    assert len(set(ids)) == len(ids), "重复条目应被去掉"
    assert len(results) == 5, "只有 5 个唯一 id"


@pytest.mark.asyncio
async def test_pagination_stops_at_max_results(monkeypatch):
    """达到所需条数就停，不多请求。"""
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode, SearchParams

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )
    calls = {"n": 0}

    async def fake_call(path, params=None):
        calls["n"] += 1
        n = calls["n"]
        return {
            "status_code": 0,
            "cursor": n * 20,
            "has_more": 1,
            "data": [_item(f"{n}-{i}") for i in range(20)],
        }

    monkeypatch.setattr(client, "_call", fake_call)

    results = await client.search(SearchParams(keyword="x", max_results=25))
    assert len(results) == 25
    assert calls["n"] == 2, f"25 条只需 2 页（20+5），实际请求 {calls['n']} 次"


@pytest.mark.asyncio
async def test_pagination_stops_when_server_says_no_more(monkeypatch):
    """服务端说没有更多时立即停止。"""
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode, SearchParams

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )
    calls = {"n": 0}

    async def fake_call(path, params=None):
        calls["n"] += 1
        return {
            "status_code": 0,
            "cursor": 0,
            "has_more": 0,   # 明确没有更多
            "data": [_item(i) for i in range(5)],
        }

    monkeypatch.setattr(client, "_call", fake_call)

    results = await client.search(SearchParams(keyword="x", max_results=50))
    assert len(results) == 5
    assert calls["n"] == 1, "服务端说没有了就不该继续请求"
