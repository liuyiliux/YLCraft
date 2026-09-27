"""小红书笔记详情的契约测试。

## 实测结论（2026-09-27）

### API 端点已失效

`edith.xiaohongshu.com/api/sns/web/v1/feed` 实测 `code:300011`
（缺 X-s/X-t 签名被风控拒）。原实现会真的去请求它、失败后 `return None`，
调用方只看到"没拿到详情"，不知道是端点废弃。

### 图片能从 DOM 直接读

笔记页的图由页面自己从 `sns-webpic-qc.xhscdn.com` 加载，
所以不需要签名接口，读 `.swiper-slide img` 即可。

### 选择器踩过两次坑（都要钉住）

    × `[class*=note] img`          → 3 图的笔记返回 **40 张**（混入推荐流）
    × 限定 `#noteContainer` 内取图 → 仍 **36 张**（容器含底部推荐流）
    ✓ `.swiper-slide img` + 去重   → **3 张**，与页面 "1/3" 指示器一致

swiper 会生成 duplicate slide（同图两次），**必须去重**。

### 必须带 xsec_token

不带 token 打开 `/explore/{id}` 会显示「当前笔记暂时无法浏览」。
且 token **会轮换**（URL 里 `AB128Hnm…`，页面内已是 `AB0eZ6W7…`）。

### 一个排查陷阱

探测时看到页面显示「手机号登录」，误判登录态失效。
实际是**12 个残留 Chrome 进程占着同一持久化 profile**，导致状态错乱。
"""

from __future__ import annotations

import inspect
import json

import pytest


# =============================================================================
# ID / token 提取
# =============================================================================

@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.xiaohongshu.com/explore/6a27e457000000001702e352",
            "6a27e457000000001702e352",
        ),
        (
            "https://www.xiaohongshu.com/search_result/6a27e457000000001702e352?xsec_token=AB1&xsec_source=",
            "6a27e457000000001702e352",
        ),
        (
            "https://www.xiaohongshu.com/discovery/item/6a27e457000000001702e352",
            "6a27e457000000001702e352",
        ),
    ],
)
def test_extract_note_id(url, expected):
    from app.services.platforms.xiaohongshu.detail_adapter import extract_note_id

    assert extract_note_id(url) == expected


def test_extract_note_id_short_link_returns_none():
    """短链 xhslink.com 需要先重定向，这里返回 None。"""
    from app.services.platforms.xiaohongshu.detail_adapter import extract_note_id

    assert extract_note_id("https://xhslink.com/abc") is None


def test_extract_xsec_token():
    """必须能取到 token——不带 token 打不开笔记页。"""
    from app.services.platforms.xiaohongshu.detail_adapter import extract_xsec_token

    url = (
        "https://www.xiaohongshu.com/search_result/6a27e457000000001702e352"
        "?xsec_token=AB128Hnm0tDXUwA&xsec_source="
    )
    assert extract_xsec_token(url) == "AB128Hnm0tDXUwA"
    assert extract_xsec_token("https://www.xiaohongshu.com/explore/abc") == ""


# =============================================================================
# 解析（用实测结构）
# =============================================================================

def _dom_data(**over) -> dict:
    d = {
        "title": "168cm/180斤古早波点穿搭和日落也太配了叭！",
        "desc": "在版纳的几天连续下雨，但是在离开前碰见了绝美日落！！！",
        "author": "禾子盒盒",
        "images": [
            "https://sns-webpic-qc.xhscdn.com/1/notes_pre_post/a.webp",
            "https://sns-webpic-qc.xhscdn.com/2/notes_pre_post/b.webp",
            "https://sns-webpic-qc.xhscdn.com/3/notes_pre_post/c.webp",
        ],
        "indicator": "1/3",
        "indicatorTotal": 3,
        "videos": [],
    }
    d.update(over)
    return d


def test_parse_dom_basic():
    from app.services.platforms.xiaohongshu.note import parse_note_dom

    n = parse_note_dom(_dom_data(), "6a27e457000000001702e352")
    assert n.id == "6a27e457000000001702e352"
    assert n.title.startswith("168cm/180斤")
    assert n.author == "禾子盒盒"
    assert len(n.images) == 3
    assert n.type == "note"
    assert n.platform == "xiaohongshu"
    assert n.video_cover == n.images[0]


def test_parse_dom_video_note():
    from app.services.platforms.xiaohongshu.note import parse_note_dom

    n = parse_note_dom(_dom_data(videos=["https://x/v.mp4"]), "id")
    assert n.type == "video"
    assert n.video == "https://x/v.mp4"


def test_parse_dom_warns_on_count_mismatch(caplog):
    """图片数与页面指示器不一致时要告警（便于发现选择器失效）。"""
    import logging

    from app.services.platforms.xiaohongshu.note import parse_note_dom

    with caplog.at_level(logging.WARNING):
        parse_note_dom(_dom_data(images=["https://x/1.webp"], indicatorTotal=3), "id")
    assert any("指示器" in r.message or "不一致" in r.message for r in caplog.records)


def test_parse_dom_no_warning_when_consistent(caplog):
    import logging

    from app.services.platforms.xiaohongshu.note import parse_note_dom

    with caplog.at_level(logging.WARNING):
        parse_note_dom(_dom_data(), "id")
    assert not [r for r in caplog.records if "不一致" in r.message]


# =============================================================================
# 选择器（踩过两次坑）
# =============================================================================

def test_js_selector_is_swiper_slide():
    """**回归**：必须用 `.swiper-slide img`。

    用 `[class*=note] img` 会把推荐流算进来，3 图的笔记返回 40 张。

    注意只检查**真实代码**，不检查注释——注释里专门记录了这两个
    踩过的选择器（`[class*=note] img`、`#noteContainer`），
    直接对全文断言会被注释误伤。
    """
    from app.services.platforms.xiaohongshu.note import JS_PARSE_NOTE

    # 去掉 // 注释后再断言
    code = "\n".join(
        line for line in JS_PARSE_NOTE.splitlines()
        if not line.strip().startswith("//")
    )
    assert ".swiper-slide img" in code, "应用 swiper slide 选择器"
    assert "[class*=note] img" not in code, "代码里不要用过宽的类名匹配"


def test_js_dedupes_images():
    """**回归**：必须去重——swiper 有 duplicate slide（同图两次）。"""
    from app.services.platforms.xiaohongshu.note import JS_PARSE_NOTE

    assert "seen" in JS_PARSE_NOTE, "应有去重集合"
    # 去重键忽略了 query（同一图不同参数算一张）
    assert "split('?')[0]" in JS_PARSE_NOTE


def test_js_excludes_avatar_and_static():
    from app.services.platforms.xiaohongshu.note import JS_PARSE_NOTE

    assert "avatar" in JS_PARSE_NOTE
    assert "fe-static" in JS_PARSE_NOTE


def test_js_reads_indicator():
    """要读页面上的 1/3 指示器，用于交叉校验。"""
    from app.services.platforms.xiaohongshu.note import JS_PARSE_NOTE

    assert "indicator" in JS_PARSE_NOTE
    assert r"\d+\s*\/\s*\d+" in JS_PARSE_NOTE


def test_js_detects_not_found_and_login():
    """要能识别「暂时无法浏览」与「手机号登录」两种状态。"""
    from app.services.platforms.xiaohongshu.note import JS_PARSE_NOTE

    assert "暂时无法浏览" in JS_PARSE_NOTE
    assert "手机号登录" in JS_PARSE_NOTE


# =============================================================================
# API 模式显式报错（不静默）
# =============================================================================

@pytest.mark.asyncio
async def test_api_mode_raises_instead_of_silent_none():
    """API 模式必须显式报错。

    原实现真去请求已失效端点、失败后返回 None，
    调用方只看到"没拿到详情"，不知道是端点废弃。
    """
    from app.services.platforms.xiaohongshu.note import get_detail_via_api

    with pytest.raises(RuntimeError) as exc:
        await get_detail_via_api(None, "abc")
    msg = str(exc.value)
    assert "300011" in msg or "失效" in msg
    assert "patchright" in msg.lower(), "应给出正确做法"


def test_dead_endpoint_recorded():
    """失效端点常量要留着，避免有人又捡回去用。"""
    from app.services.platforms.xiaohongshu.note import DEAD_V1_ENDPOINT

    assert "edith.xiaohongshu.com" in DEAD_V1_ENDPOINT


# =============================================================================
# 接线
# =============================================================================

def test_parser_has_xiaohongshu_branch():
    """video/parser.py 必须有小红书分支。

    原来**完全没有**——「去水印解析」页对小红书直接落到 yt-dlp 兜底，
    而 yt-dlp 对小红书图文无效，用户只能看到"未找到视频或图片数据"。

    用 AST 检查真实执行顺序（不能用源码里 `_parse_with_ytdlp(` 的位置——
    那是**函数定义**，在文件很前面，会误判）。
    """
    import ast
    import textwrap

    from app.services.video import parser as video_parser

    src = textwrap.dedent(inspect.getsource(video_parser.parse))
    tree = ast.parse(src.replace("async def ", "def "))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

    # 找出调用 fetch_xhs_detail 与 _parse_with_ytdlp 的**语句行号**
    xhs_line = None
    ytdlp_line = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "fetch_xhs_detail":
                xhs_line = node.lineno
            if node.func.id == "_parse_with_ytdlp":
                ytdlp_line = node.lineno

    assert xhs_line is not None, "parse() 里应调用 fetch_xhs_detail"
    assert ytdlp_line is not None, "应保留 yt-dlp 兜底"
    assert xhs_line < ytdlp_line, "小红书详情应在 yt-dlp 兜底之前尝试"


def test_adapter_uses_patchright_mode():
    """适配器必须用 patchright 模式（API 端点已失效）。"""
    from app.services.platforms.xiaohongshu import detail_adapter

    src = inspect.getsource(detail_adapter.fetch_xhs_detail)
    assert 'mode="patchright"' in src


def test_adapter_passes_token():
    """适配器必须把 xsec_token 传下去（不带 token 打不开笔记页）。"""
    from app.services.platforms.xiaohongshu import detail_adapter

    src = inspect.getsource(detail_adapter.fetch_xhs_detail)
    assert "xsec_token" in src
    assert "url=url" in src


def test_pick_image_url_prefers_original():
    """图片地址要挑最大的，不能只取缩略图。

    原实现取 `url_default`（缩略图），原图字段被忽略。
    """
    from app.services.platforms.xiaohongshu.note import _pick_image_url

    node = {
        "url_default": "https://x/thumb.webp",
        "url": "https://x/orig.webp",
        "info_list": [
            {"url": "https://x/small.webp", "width": 200},
            {"url": "https://x/big.webp", "width": 2000},
        ],
    }
    assert _pick_image_url(node) == "https://x/big.webp"
    # 没有 info_list 时回退
    assert _pick_image_url({"url_default": "https://x/a.webp"}) == "https://x/a.webp"
    assert _pick_image_url({}) == ""
    assert _pick_image_url("not a dict") == ""


def test_parse_count_handles_wan_and_yi():
    from app.services.platforms.xiaohongshu.note import parse_count

    assert parse_count("1128") == 1128
    assert parse_count("2.3万") == 23000
    assert parse_count("1.5亿") == 150000000
    assert parse_count("") == 0
    assert parse_count("abc") == 0
