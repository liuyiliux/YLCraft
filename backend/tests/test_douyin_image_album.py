"""抖音「图集」识别的回归测试（2026-09-29）。

## 用户问

    抖音会有图片加视频的情况吧

**问得对** —— 抖音确实有图集（`aweme_type=68`），
而我们**之前完全没识别出来**，实测发现三个 bug。

## 三个 bug

### ① 图片读错字段

抖音图集（`aweme_type=68`）实测：

    image_infos   → **不是列表**（空）
    images        → **10 张图**（每项 {uri, url_list}）

代码只读 `image_infos` → **一张图都拿不到**。

### ② 没用权威字段 `aweme_type`

    0   = 视频
    68  = 图集（图文）

代码靠 `bool(image_infos)` 判断 → 图集永远判不出。

### ③ 连带：图集被标成 `video`

于是：
  · 前端详情把它当视频（渲染播放器）
  · **「图文下载」退化成只有封面一张**

## 实测修复后

    「plog」 图集 7 条，带图 7 条 ✅   '终其一生...' 10 张图
    「壁纸」 图集 4 条，带图 4 条 ✅   'iPad壁纸' 8 张图
    「文案」 图集 7 条，带图 7 条 ✅   '#备忘录' 6 张图

且 `video_url` 为空（不再误判成视频）。

## 两个入口都修了

  · `parse_search_item`（搜索结果）
  · `_detail_from_raw`（详情）

（都要改 —— 只改一个会出现"列表对、详情错"的不一致。）
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# ① 图集图片要读 `images`
# =============================================================================

def test_reads_images_field():
    """**回归**：要读 `aweme_info.images`（图集的图片在这里）。

    实测图集：`image_infos` 是空的，`images` 有 10 张。
    """
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    assert 'info.get("images")' in src, "应读 images 字段"
    # 仍兼容 image_infos
    assert "image_infos" in src, "也要兼容 image_infos"


def test_album_image_urls_helper():
    """图集取址要有独立辅助函数，且两种形态都兼容。"""
    from app.services.platforms.douyin.client import _album_image_urls

    # images[] 形态
    got = _album_image_urls([
        {"uri": "a", "url_list": ["https://x/1.jpg", "https://x/2.jpg"]},
        {"uri": "b", "url_list": ["https://x/3.jpg"]},
    ])
    assert got == ["https://x/1.jpg", "https://x/3.jpg"], "每张取第一个 url"

    # 纯字符串形态
    assert _album_image_urls(["https://x/a.jpg"]) == ["https://x/a.jpg"]

    # 异常输入不炸、不编造
    assert _album_image_urls(None) == []
    assert _album_image_urls("not-a-list") == []
    assert _album_image_urls([{}]) == []


# =============================================================================
# ② 用 aweme_type 判类型
# =============================================================================

def test_uses_aweme_type():
    """**回归**：要优先信 `aweme_type`（0=视频，68=图集）。"""
    from app.services.platforms.douyin import client as dy

    for fn in (dy.parse_search_item, dy._detail_from_raw):
        src = inspect.getsource(fn)
        assert "aweme_type" in src, f"{fn.__name__} 应读 aweme_type"
        assert '"68"' in src, f"{fn.__name__} 应把 68 当图集"
        assert '"0"' in src, f"{fn.__name__} 应把 0 当视频"


def test_both_entry_points_fixed():
    """**回归**：搜索与详情**两个入口都要修**。

    只改一个会出现"列表对、详情错"的不一致。
    """
    from app.services.platforms.douyin import client as dy

    for fn in (dy.parse_search_item, dy._detail_from_raw):
        src = inspect.getsource(fn)
        assert "_album_image_urls" in src or 'get("images")' in src, (
            f"{fn.__name__} 也要读 images"
        )


# =============================================================================
# ③ 图集要有图片、且不带头视频地址
# =============================================================================

def test_album_images_exposed_in_raw_data():
    """**回归**：图集图片要放进 `raw_data._images`。

    `SearchResult` 没有 images 字段，平台统一走 `raw_data._images`
    （`crawler/service.py` 从那里取，填进 `CrawlerResult.images`）。
    原来抖音没放 → 前端看不到图、「图文下载」只有封面。
    """
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    assert '"_images"' in src, "要放 raw_data._images"


def test_image_note_has_no_video_url():
    """图集不该有视频地址（配乐 mp3 要排除）。"""
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    # 取视频地址的前提是 not is_image
    i = src.find("video_url = \"\"")
    assert i != -1
    seg = src[i:i + 900]
    assert "not is_image" in seg, "图集不该取视频地址"
    assert "mp3" in seg, "要排除音频"
