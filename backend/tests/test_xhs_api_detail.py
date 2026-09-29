"""小红书详情「纯 HTTP API」路径的回归测试。

## 背景：一个被误判了两轮的结论

项目里长期写着：

    edith.xiaohongshu.com/api/sns/web/v1/feed 已失效
    （实测 code:300011，缺 X-s/X-t 签名被风控拒）

**端点从来没失效** —— 是当时缺签名。而那句话自己都写了
"缺 X-s/X-t 签名被风控拒"，却把它当成了"端点废弃"。

有了 `xhshow`（搜索接口一直在用）之后，加上签名实测：

    POST https://edith.xiaohongshu.com/api/sns/web/v1/feed
    body = {"source_note_id": ..., "xsec_token": ..., "xsec_source": "pc_feed"}
    → HTTP 200, success=True, data.items[0].note_card

字段比浏览器 DOM 路径**更全**：
    title / desc / type / time / ip_location
    user{nickname, user_id}
    interact_info{liked_count, collected_count, comment_count, share_count}
    image_list[{url_default, width, height}]   ← 全部原图
    video.media.stream.{h264,h265,EF4..EF7}    ← 多档清晰度
    tag_list[{name}]

## 实测对比

    纯 HTTP：3.4 秒，chrome 进程 0 个
    浏览器 ：20+ 秒，要开 chrome

    单图笔记 → 1 张；多图笔记 → 6 张；视频笔记 → 有多档 stream
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 端点必须被视为「可用」
# =============================================================================

def test_api_mode_is_real_implementation():
    """**回归**：`get_detail_via_api` 必须是真实实现，不能是"显式报错"。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_api)
    assert "sns/web/v1/feed" in src, "应请求 /feed 端点"
    assert "sign_post" in src, "必须签名（缺签名会被风控拒）"
    assert "source_note_id" in src, "请求体字段"


def test_no_dead_endpoint_constant_claims():
    """**回归**：不该再有"端点已失效"的说法。

    那句话误导了两轮排查（先误判 goto 不行、又误判端点废弃）。
    """
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod)
    assert "API 模式已停用" not in src, "不该再说 API 停用"
    assert "API 端点已失效" not in src


def test_feed_uri_constant():
    """端点常量要存在。"""
    from app.services.platforms.xiaohongshu.note import EDITH_BASE, FEED_URI

    assert FEED_URI == "/api/sns/web/v1/feed"
    assert "edith.xiaohongshu.com" in EDITH_BASE


# =============================================================================
# token：必需
# =============================================================================

async def test_missing_token_raises_actionable():
    """缺 `xsec_token` 要报可操作错误（实测缺失返回 HTTP 461）。"""
    from app.services.platforms.xiaohongshu.note import get_detail_via_api

    class _Cfg:
        cookie = "a1=x; web_session=y"

    class _Cli:
        config = _Cfg()

    with pytest.raises(RuntimeError) as exc:
        await get_detail_via_api(_Cli(), "noteid")
    assert "xsec_token" in str(exc.value)
    assert "461" in str(exc.value) or "必需" in str(exc.value)


async def test_missing_cookie_raises_actionable():
    """没有 cookie 要明确报错，不能静默返回 None。"""
    from app.services.platforms.xiaohongshu.note import get_detail_via_api

    class _Cfg:
        cookie = ""

    class _Cli:
        config = _Cfg()

    with pytest.raises(RuntimeError) as exc:
        await get_detail_via_api(_Cli(), "noteid")
    assert "Cookie" in str(exc.value)


def test_token_can_come_from_url():
    """没单独传 token 时，应能从 `url` 的 query 里提取。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_api)
    assert "parse_qs" in src or "urlparse" in src, "应从 url 提取 token"


# =============================================================================
# 签名：/feed 是风控接口
# =============================================================================

def test_sign_post_supports_x_rap():
    """`sign_post` 要支持 `x_rap`（`/feed` 是风控接口，需要 `x-rap-param`）。

    xhshow README：feed / 搜索 / 笔记发布等接口需要额外的 x-rap-param。
    实测不带也能过，但风控策略会变，带上更稳。
    """
    from app.services.platforms.xiaohongshu import signing

    sig = inspect.signature(signing.sign_post)
    assert "x_rap" in sig.parameters, "应支持 x_rap"

    src = inspect.getsource(signing.sign_post)
    assert "x_rap" in src
    # 旧版 xhshow 不支持时要能退回（不能直接崩）
    assert "TypeError" in src, "应兼容旧版 xhshow"


def test_detail_uses_x_rap():
    """详情请求应带上风控头。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_api)
    assert "x_rap=True" in src, "详情应带 x-rap-param"


# =============================================================================
# 字段解析
# =============================================================================

def test_parses_title_not_display_title():
    """**回归**：字段是 `title`，不是 `display_title`。

    旧实现只读 `display_title` → 实测拿不到标题（实测返回的是 `title`）。
    """
    from app.services.platforms.xiaohongshu.note import parse_note_detail

    d = parse_note_detail({"note_card": {
        "note_id": "n1", "title": "真标题", "type": "normal",
    }})
    assert d.title == "真标题"


def test_parses_all_images():
    """多图要全部拿到（实测 6 张的笔记拿到 6 张）。"""
    from app.services.platforms.xiaohongshu.note import parse_note_detail

    d = parse_note_detail({"note_card": {
        "note_id": "n1", "title": "t", "type": "normal",
        "image_list": [
            {"url_default": f"https://x/{i}.webp", "width": 100}
            for i in range(6)
        ],
    }})
    assert len(d.images) == 6


def test_parses_video_stream():
    """视频地址要从 `video.media.stream` 里取（实测 EF4~EF7 多档）。"""
    from app.services.platforms.xiaohongshu.note import _pick_video_url

    url = _pick_video_url({"media": {"stream": {
        "EF7": [{"master_url": "https://x/high.mp4"}],
        "EF4": [{"master_url": "https://x/low.mp4"}],
    }}})
    assert url.startswith("http")

    # h264 优先（通用性好）
    url2 = _pick_video_url({"media": {"stream": {
        "h264": [{"master_url": "https://x/h264.mp4"}],
        "EF7": [{"master_url": "https://x/high.mp4"}],
    }}})
    assert url2 == "https://x/h264.mp4"


def test_parses_interact_info():
    """互动数要正确解析（收藏字段是 `collected_count`）。"""
    from app.services.platforms.xiaohongshu.note import parse_note_detail

    d = parse_note_detail({"note_card": {
        "note_id": "n1", "title": "t", "type": "normal",
        "interact_info": {
            "liked_count": "200", "collected_count": "10",
            "comment_count": "142", "share_count": "3",
        },
    }})
    assert d.likes == 200
    assert d.collects == 10
    assert d.comments == 142
    assert d.shares == 3


def test_parses_create_time_and_tags():
    """发布日期（毫秒时间戳）与话题要解析出来。"""
    from app.services.platforms.xiaohongshu.note import parse_note_detail

    d = parse_note_detail({"note_card": {
        "note_id": "n1", "title": "t", "type": "normal",
        "time": 1765372252000,
        "tag_list": [{"name": "沈阳"}, {"name": "旅游"}, {}],
    }})
    assert d.create_time, "应解析出时间"
    assert d.tags == ["沈阳", "旅游"]


# =============================================================================
# 接线：字段名必须跟响应模型对齐
# =============================================================================

def test_detail_dict_uses_collect_count_key():
    """**回归**：传给 `crawler.models.NoteDetail` 的键名是 `collect_count`。

    原来写 `collects` —— pydantic 会**静默忽略**未知字段，
    前端拿到 `收藏=None`（实测踩过：接口明明返回了 collected_count=10）。
    """
    from app.services.crawler import service as crawler_service
    from app.services.crawler.models import NoteDetail as ResponseNoteDetail

    src = inspect.getsource(crawler_service.CrawlerService.get_note_detail)
    assert '"collect_count"' in src, "键名必须是 collect_count"
    assert '"collects":' not in src, "不该用 collects（会被静默忽略）"

    # 模型字段名也要对得上
    assert "collect_count" in ResponseNoteDetail.model_fields


def test_detail_dict_includes_raw_data():
    """`raw_data` 要带出来 —— 前端依赖它拿 `xsec_token`。"""
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService.get_note_detail)
    assert '"raw_data"' in src
