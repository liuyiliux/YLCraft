"""小红书创作服务平台数据的回归测试。

## 为什么做这个

普通小红书站只有**公开数据**。**创作服务平台**
（`creator.xiaohongshu.com`）有**只有号主能看**的运营数据：

    曝光数 / 观看数 / 封面点击率 / 视频完播率 / 平均观看时长
    净涨粉 / 取消关注 / 主页访客 / 弹幕数 …

## 实测（2026-09-29，与创作者后台页面完全一致）

    曝光数 759（环比 +96%）   观看数 157（环比 +503%）
    封面点击率 4.4%           视频完播率 3.4%
    主页访客 9（环比 -40%）   净涨粉 1
    粉丝：涨粉 1 / 掉粉 0 / 总数 195

## 登录态**与主站通用**（修正了我之前的错误判断）

我一度断定"创作者中心需要单独登录、主站 cookie 不能用" —— **那是错的**。

真相：cookie domain 是 `.xiaohongshu.com`，creator / customer 子域都能收到。
实测用主站 cookie 打开 creator 站**直接就是登录状态**
（"逸流AI 发布笔记 笔记管理 数据看板"）。

我当初测到 401 是因为**那个 web_session 已经过期**。

## ⚠️ 教训：`有 web_session` ≠ `登录有效`

过期的 `web_session` **依然存在**于 cookie 里，只查存在性会误判。
实测登录态失效时主站正文会写"**电脑设备登录超限，请重新登录**"。

## 签名

用 `xhshow` 的 **GET 签名**即可（`sign_get`）。
⚠️ uri **必须带完整 query 串** —— 签名是对整条 URI 做的摘要，
少一个参数就报 **406**（我第一版手写 XYW_ AES 签名就是这样失败的）。

## ⚠️ 字段命名不统一（调研明确警告，实测确认）

    总览接口      → `impl_count` / `cover_click_rate`（snake_case）
    作品列表接口  → `imp_count`  / `coverClickRate`（camelCase）

**不能复用同一个解析器。**

## ⚠️ 趋势数组命名也不统一

    impl_count      → impl_count_list
    view_count      → **view_list**       （不带 _count）
    like_count      → **like_list**
    home_view_count → **home_view_list**

所以配对时要"去掉 `_count` 后缀"再试一次。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 端点
# =============================================================================

def test_endpoints_are_the_verified_ones():
    """锁定实测可用的端点。"""
    from app.services.platforms.xiaohongshu import creator

    assert creator.ACCOUNT_BASE == "/api/galaxy/v2/creator/datacenter/account/base"
    assert creator.FANS_OVERALL == "/api/galaxy/creator/data/fans/overall_new"
    assert "creator.xiaohongshu.com" in creator.CREATOR_BASE


def test_uses_xhshow_get_signature():
    """**回归**：用 xhshow 的 GET 签名（不要手写 AES）。

    我第一版手写了 `XYW_`（MD5→AES-128-CBC）签名 —— 算法对但少了字段，
    结果 **406**。改用 `sign_get` 后正常。
    """
    from app.services.platforms.xiaohongshu import creator

    src = inspect.getsource(creator._sign_get)
    assert "sign_get" in src, "应复用 signing.sign_get"


def test_uri_includes_query_string():
    """**回归**：签名用的 uri **必须带完整 query**。

    签名是对整条 URI 做的摘要 —— 少一个参数就报 406（实测）。
    """
    from app.services.platforms.xiaohongshu import creator

    src = inspect.getsource(creator._request)
    assert "api_with_query" in src, "应把 query 拼进 uri"
    assert "urlencode" in src


# =============================================================================
# 指标白名单
# =============================================================================

def test_metric_labels_cover_screenshot_metrics():
    """截图上出现的指标都要在白名单里。"""
    from app.services.platforms.xiaohongshu.creator import METRIC_LABELS

    for k in ("impl_count", "view_count", "cover_click_rate",
              "video_full_view_rate", "home_view_count",
              "net_rise_fans_count", "rise_fans_count", "loss_fans_count",
              "like_count", "collect_count", "comment_count", "share_count"):
        assert k in METRIC_LABELS, f"{k} 缺中文名"
        assert METRIC_LABELS[k]


def test_overview_only_returns_whitelisted_keys():
    """**回归**：只输出白名单指标。

    接口的 `seven` 里混着 `begin_time`/`end_time`/`summary`/
    `publish_*_rate` 等非指标字段 —— 遍历全部会把它们当指标吐给前端
    （实测踩过：出现了 `end_time = 1790524800000` 这种"指标"）。
    """
    from app.services.platforms.xiaohongshu import creator

    src = inspect.getsource(creator.fetch_overview)
    assert "for key in METRIC_LABELS" in src, "应遍历白名单，不是遍历 seg"


# =============================================================================
# 趋势配对（命名不统一）
# =============================================================================

def test_pair_trend_handles_count_suffix():
    """**回归**：趋势数组命名不统一，要能处理 `view_count` → `view_list`。

    实测：
        impl_count      → impl_count_list
        view_count      → **view_list**（不带 _count）
        home_view_count → **home_view_list**
    """
    from app.services.platforms.xiaohongshu.creator import _pair_trend

    seg = {
        "impl_count_list": [{"date": 1700000000000, "count": "5"}],
        "view_list": [{"date": 1700000000000, "count": "3"}],
        "home_view_list": [{"date": 1700000000000, "count": "1"}],
    }
    assert len(_pair_trend(seg, "impl_count")) == 1
    assert len(_pair_trend(seg, "view_count")) == 1, "view_count → view_list"
    assert len(_pair_trend(seg, "home_view_count")) == 1


def test_pair_trend_returns_empty_when_absent():
    """配不到就返回空列表（不编造）。"""
    from app.services.platforms.xiaohongshu.creator import _pair_trend

    assert _pair_trend({}, "whatever") == []


# =============================================================================
# 数值解析
# =============================================================================

def test_num_handles_strings():
    """接口数值可能是字符串（同抖音）。"""
    from app.services.platforms.xiaohongshu.creator import _num

    assert _num("759") == 759
    assert _num(759) == 759
    assert _num("4.4") == pytest.approx(4.4)
    assert _num("4.4%") == pytest.approx(4.4)
    assert _num("") == 0
    assert _num(None) == 0
    assert _num(True) == 0


def test_rate_metrics_flagged():
    """比率类指标要标记（前端按百分比展示）。"""
    from app.services.platforms.xiaohongshu.creator import RATE_KEYS

    assert "cover_click_rate" in RATE_KEYS
    assert "video_full_view_rate" in RATE_KEYS
    # 计数值不是比率
    assert "view_count" not in RATE_KEYS
    assert "impl_count" not in RATE_KEYS


# =============================================================================
# 鉴权与错误信息
# =============================================================================

async def test_requires_cookie():
    """缺 cookie 要报可操作错误。"""
    from app.services.platforms.xiaohongshu.creator import fetch_overview

    with pytest.raises(RuntimeError) as exc:
        await fetch_overview("")
    assert "Cookie" in str(exc.value)


def test_401_message_mentions_stale_session():
    """401 要提示"过期的 session 依然存在，需重新扫码"。

    这是实测踩过的坑：只查 cookie 存在性会误判成"已登录"。
    """
    from app.services.platforms.xiaohongshu import creator

    src = inspect.getsource(creator._request)
    assert "401" in src
    assert "重新登录" in src or "web_session" in src


def test_406_message_mentions_query_string():
    """406 要提示"检查 uri 是否带完整 query"。"""
    from app.services.platforms.xiaohongshu import creator

    src = inspect.getsource(creator._request)
    assert "406" in src
    assert "query" in src


# =============================================================================
# 作品列表
# =============================================================================

def test_note_parser_uses_camel_case():
    """**回归**：作品列表用 camelCase（`imp_count` / `coverClickRate`）。

    调研明确警告与总览不一致 —— 不能复用总览的解析器。
    """
    from app.services.platforms.xiaohongshu.creator import parse_note

    n = parse_note({
        "id": "n1", "title": "标题", "type": 1,
        "read_count": "10", "imp_count": "100",
        "coverClickRate": "5.5", "like_count": "3",
        "fav_count": "2", "increase_fans_count": "1",
    })
    assert n is not None
    assert n["imp_count"] == 100
    assert n["cover_click_rate"] == pytest.approx(5.5)
    assert n["fav_count"] == 2
    assert n["increase_fans_count"] == 1


def test_note_parser_skips_bad():
    from app.services.platforms.xiaohongshu.creator import parse_note

    assert parse_note({}) is None
    assert parse_note(None) is None
