"""抖音创作者中心数据的回归测试。

## 为什么做这个

普通抖音站（`www.douyin.com`）只有**公开数据**（播放/点赞，谁都看得到）。
**创作者中心**有**只有号主能看**的运营数据：

    播放量 / 主页访问量 / 作品点赞 / 作品分享 / 作品评论 / 净增粉丝
    取关粉丝 / 粉丝总数 / 搜索来源 / 音乐创作
    单作品的：完播率 / 5秒完播 / 2秒跳出 / 平均观看时长 / 粉丝观看占比 …

## 实测（2026-09-29）

抖音创作者中心**纯 HTTP + 裸 cookie 即可**，**不需要签名**
（没有 a_bogus / X-Bogus）：

    GET creator.douyin.com/aweme/janus/creator/data/overview/all/
    → data.{play,new_fans,profile,digg,...}
        每个 {current_count, last_period_incr, option_list[...]}

    GET creator.douyin.com/janus/douyin/creator/pc/work_list?...
    → items[12], metrics 有 25 个字段

实测与创作者中心页面**完全一致**：

    播放量 16（环比 +8） / 主页访问量 1（环比 +1） / 作品点赞 1（环比 +1）

## ⚠️ 一个必须记住的坑：**所有数值都是字符串**

    {"view_count": "8", "completion_rate": "0.111111",
     "avg_view_second": "32.000000", "current_count": "16"}

只认 `isinstance(v, (int, float))` 会把它们**全部过滤成 0** ——
实测表现为"作品指标看起来全是 0，其实数据都在"。

## 另一个坑：**不要自己累加 series 当合计**

`fans` 的 `option_list` 是"总数快照"（每天都记 122），
累加会得到 854 这种无意义数字。**要用接口给的 `current_count`**。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 数值解析（最隐蔽的坑）
# =============================================================================

def test_num_handles_string_numbers():
    """**回归**：接口返回的数值**全是字符串**，必须能解析。

    实测 `{"view_count": "8", "completion_rate": "0.111111"}` ——
    只认 int/float 的话会全部变成 0（表现为"指标全是 0，其实有数据"）。
    """
    from app.services.platforms.douyin.creator import _num

    assert _num("8") == 8
    assert _num(8) == 8
    assert _num("0.111111") == pytest.approx(0.111111)
    assert _num("32.000000") == 32          # 整数值的小数串 → int
    assert _num("") == 0
    assert _num(None) == 0
    assert _num("abc") == 0
    assert _num(True) == 0                  # bool 不当数字


def test_parse_work_reads_string_metrics():
    """**回归**：作品 metrics 是字符串，要正确解析成数字。"""
    from app.services.platforms.douyin.creator import parse_work

    w = parse_work({
        "id": "123",
        "description": "标题",
        "metrics": {
            "view_count": "8", "like_count": "2", "comment_count": "0",
            "share_count": "0", "favorite_count": "0",
            "subscribe_count": "0", "completion_rate": "0.111111",
            "avg_view_second": "32.000000", "bounce_rate_2s": "0.800000",
            "fan_view_proportion": "0.500000",
        },
    })
    assert w is not None
    assert w["play_count"] == 8
    assert w["like_count"] == 2
    assert w["completion_rate"] == pytest.approx(0.111111)
    assert w["avg_view_second"] == 32
    assert w["bounce_rate_2s"] == pytest.approx(0.8)
    assert w["fan_view_proportion"] == pytest.approx(0.5)


def test_parse_work_supports_old_shape():
    """旧版形态（`aweme_list` + `statistics`）也要兼容。"""
    from app.services.platforms.douyin.creator import parse_work

    w = parse_work({
        "aweme_id": "456",
        "desc": "x",
        "statistics": {"play_count": 10, "digg_count": 5},
    })
    assert w is not None
    assert w["id"] == "456"
    assert w["play_count"] == 10
    assert w["like_count"] == 5


def test_parse_work_skips_bad():
    from app.services.platforms.douyin.creator import parse_work

    assert parse_work({}) is None
    assert parse_work(None) is None


# =============================================================================
# 总览：合计不能用累加
# =============================================================================

def test_overview_uses_current_count_not_sum():
    """**回归**：合计要用接口的 `current_count`，**不能累加 series**。

    `fans` 的 `option_list` 是"总数快照"（每天都是 122），
    累加会得到 854 这种无意义数字（实测踩过）。
    """
    from app.services.platforms.douyin.creator import fetch_overview

    src = inspect.getsource(fetch_overview)
    assert "current_count" in src, "应该用 current_count 作为合计"
    assert "period_incr" in src, "应带出环比增量"


def test_metric_labels_cover_known_keys():
    """已知指标都要有中文名（前端直接显示）。"""
    from app.services.platforms.douyin.creator import METRIC_LABELS

    for k in ("play", "profile", "digg", "comment", "share",
              "new_fans", "cancel_fans", "fans"):
        assert k in METRIC_LABELS, f"{k} 缺中文名"
        assert METRIC_LABELS[k], f"{k} 的中文名不能为空"


def test_last_days_mapping():
    """时间范围映射要正确（接口用 1/2/3 表示 7/15/30 天）。"""
    from app.services.platforms.douyin.creator import LAST_DAYS

    assert LAST_DAYS[7] == 1
    assert LAST_DAYS[15] == 2
    assert LAST_DAYS[30] == 3


# =============================================================================
# 端点与鉴权
# =============================================================================

def test_endpoints_are_the_verified_ones():
    """锁定实测可用的端点。"""
    from app.services.platforms.douyin import creator

    src = inspect.getsource(creator)
    assert "/aweme/janus/creator/data/overview/all/" in src
    assert "/janus/douyin/creator/pc/work_list" in src
    assert "creator.douyin.com" in creator.BASE


def test_no_signature_needed_documented():
    """要写明"不需要签名"（避免后人又去搞 a_bogus）。"""
    from app.services.platforms.douyin import creator

    doc = inspect.getsource(creator)
    assert "不需要签名" in doc or "裸 Cookie" in doc or "裸 cookie" in doc


async def test_overview_requires_cookie():
    """缺 cookie 要报可操作错误，不静默返回空。"""
    from app.services.platforms.douyin.creator import fetch_overview

    with pytest.raises(RuntimeError) as exc:
        await fetch_overview("")
    assert "Cookie" in str(exc.value)


async def test_works_requires_cookie():
    from app.services.platforms.douyin.creator import fetch_works

    with pytest.raises(RuntimeError) as exc:
        await fetch_works("")
    assert "Cookie" in str(exc.value)


def test_headers_minimal():
    """请求头要最小化（只有 cookie/referer/ua/accept —— 实测够用）。"""
    from app.services.platforms.douyin.creator import _headers

    h = _headers("sessionid=x")
    assert h["cookie"] == "sessionid=x"
    assert "creator.douyin.com" in h["referer"]
    # 不该有签名头
    lower_keys = {k.lower() for k in h}
    assert "a_bogus" not in lower_keys
    assert "x-bogus" not in lower_keys


# =============================================================================
# 已知边界（不要承诺做不到的）
# =============================================================================

def test_documents_missing_fan_growth_api():
    """要写明「单作品粉丝增量没有 API」—— 避免后人白找。"""
    from app.services.platforms.douyin import creator

    doc = inspect.getsource(creator)
    assert "没有 API" in doc or "粉丝增量" in doc


def test_precision_trap_documented():
    """要记录 19 位 id 的 JS 精度陷阱（Python 侧解析是安全的）。"""
    from app.services.platforms.douyin import creator

    src = inspect.getsource(creator.fetch_works)
    assert "精度" in src or "19 位" in src
