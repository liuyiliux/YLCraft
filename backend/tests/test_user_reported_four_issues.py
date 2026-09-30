"""用户报的四个问题的回归测试（2026-09-29）。

## 用户反馈（原话）

    1. 我的数据少了 x
    2. 微博下面有不知道是抖音还是小红书的数据
    3. x 搜索没有更多页 这是老毛病了 不用我每个平台都和你说吧
    4. x 的详情里面获取其他平台详情里面如果是视频的 能不能在线播放

## ① 「我的数据」下拉缺 X

后端**早就支持** X（`/users/me` + `/users/videos` 实测可用），
但前端 `PLATFORMS` 里没有它 —— 用户**根本选不到**。

## ② 微博下面显示的是抖音的创作者数据

`CreatorCenterPanel` 写成了：

    const isXhs = platform === 'xiaohongshu'
    if (isXhs) { ...小红书... } else { ...抖音... }   ← else 无条件走抖音！

于是选**微博**也会拉**抖音的创作者数据** —— 界面上是"别人的数据"。
微博/X 没有创作者中心接口，应**不渲染**该面板。

## ③ X 搜索没有下一页

X 从来没设 `_has_more` —— 于是前端**永远显示"没有下一页"**，
尽管后端 `page=2/3` 都能正常翻（实测首条各不相同）。

修法：X 是 cursor 分页，**有 cursor 就说明还有更多**。
（没有 total 可给 —— 不编造。）

## ④ 详情里的视频不能在线播放

原来只有图片预览，视频得点"打开原文"跳出去。

实测 X 的视频直链**可以直接播**：

    GET https://video.twimg.com/...
    → HTTP 206, content-type=video/mp4, accept-ranges=bytes

（206 + accept-ranges 说明支持拖动进度条。）
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"{rel} 不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# ① 下拉要有 X
# =============================================================================

def test_platform_list_has_twitter():
    """**回归**：平台下拉必须有 X。

    后端早就支持，前端漏了 —— 用户"根本选不到"。
    """
    src = _read("pages/my-platform-data/index.tsx")
    assert "value: 'twitter'" in src, "下拉应有 X（twitter）"
    assert "connKeys: ['twitter'" in src, "连接匹配要含 twitter 及别名"


def test_platform_list_covers_all_supported():
    """下拉要覆盖后端支持的全部平台（微博/X 都曾漏过）。"""
    src = _read("pages/my-platform-data/index.tsx")
    for v in ("'bili'", "'douyin'", "'xiaohongshu'", "'weibo'", "'twitter'"):
        assert f"value: {v}" in src, f"下拉缺 {v}"


# =============================================================================
# ② 创作者中心不能串平台
# =============================================================================

def test_creator_panel_guards_non_douyin_xhs():
    """**回归（数据正确性）**：创作者中心只对抖音/小红书加载。

    原来 `else` 无条件走抖音 → 选微博会显示**抖音的数据**。
    """
    src = _read("pages/my-platform-data/CreatorCenterPanel.tsx")
    assert "isDouyin" in src, "应显式判断抖音（而不是用 else 兜底）"
    # 必须有"非抖音非小红书就返回"的守卫
    assert "!isXhs && !isDouyin" in src or "!isDouyin && !isXhs" in src, (
        "应在不支持的平台直接返回，不拉数据"
    )


def test_creator_panel_not_rendered_for_weibo_twitter():
    """**回归**：微博/X 不该渲染创作者中心面板。

    无脑渲染会拉到别的平台的数据（用户："微博下面有不知道是抖音
    还是小红书的数据"）。
    """
    src = _read("pages/my-platform-data/index.tsx")
    assert "CreatorCenterPanel" in src
    # 渲染处要有平台守卫
    i = src.find("<CreatorCenterPanel")
    assert i != -1
    seg = src[max(0, i - 500):i]
    assert "'douyin'" in seg and "'xiaohongshu'" in seg, (
        "渲染 CreatorCenterPanel 前要判断平台是抖音/小红书"
    )


# =============================================================================
# ③ X 搜索的 has_more
# =============================================================================

def test_x_search_sets_has_more():
    """**回归**：X 搜索要设 `_has_more`。

    原来不设 → 前端永远显示"没有下一页"（用户："x 搜索没有更多页"）。
    """
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.search_via_http)
    assert "_has_more" in src, "应回传 has_more"
    assert "cursor_next" in src, "依据是还有没有 cursor"


def test_x_does_not_fake_total():
    """X 是 cursor 分页 —— **不编造 total**。"""
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.search_via_http)
    assert "_total" not in src, "不该编造 total"


# =============================================================================
# ④ 详情里的视频播放
# =============================================================================

def test_detail_has_video_player():
    """**回归**：详情抽屉要内嵌视频播放器。"""
    src = _read("pages/crawler/index.tsx")
    assert "previewVideoUrl" in src, "应有视频地址的 memo"
    assert "<video" in src, "应渲染 video 标签"
    assert "controls" in src, "要有播放控件"


def test_video_url_reads_multiple_shapes():
    """视频地址各平台放的位置不同，要都兼容。"""
    src = _read("pages/crawler/index.tsx")
    i = src.find("previewVideoUrl = useMemo")
    assert i != -1
    seg = src[i:i + 900]
    for key in ("_video_url", "video_url"):
        assert key in seg, f"应读 {key}"
    assert "page_info" in seg, "微博的视频在 page_info.media_info"


def test_video_error_is_actionable():
    """播不了要给**可操作**提示（不静默黑屏）。"""
    src = _read("pages/crawler/index.tsx")
    i = src.find("<video")
    assert i != -1
    seg = src[i:i + 900]
    assert "onError" in seg, "要有错误处理"
    assert "打开原文" in seg, "提示用户可打开原文"
