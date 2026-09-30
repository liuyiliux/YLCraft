"""详情面板「视频时不再重复显示封面」的回归测试（2026-09-29）。

## 用户反馈

    下面是封面吗 是不是没必要了

截图：视频播放器下面又铺了一张大图（内容一样）。

## 根因

详情抽屉里视频和封面是**两块独立渲染**：

    {previewVideoUrl && <video poster={封面} ... />}     ← 封面当 poster 了
    {previewMediaUrls.length > 0 && <Image src={封面} />}  ← 又铺一遍

## 实测确认：视频笔记的"图集"**就是封面**

X 视频笔记：

    _images = ['https://pbs.twimg.com/amplify_video_thumb/.../img/xxx.jpg']
    cover   = 同一个地址

所以视频笔记的 `previewMediaUrls` 只有 1 项，且等于 `cover` ——
**铺在播放器下面纯属重复**（图集缩略图条也没意义，只有一张）。

## 修法

有视频（`previewVideoUrl` 非空）时**跳过整个封面/图集块**。
封面仍在播放器的 `poster` 上显示，信息没丢。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _src() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


def test_cover_hidden_when_video_present():
    """**回归**：有视频时封面块不该渲染。"""
    src = _src()
    # 找到封面块的渲染条件
    i = src.find("封面/图集预览")
    assert i != -1, "应有封面块"
    seg = src[i:i + 600]
    assert "!previewVideoUrl" in seg, (
        "封面块的条件里要有 !previewVideoUrl（有视频就跳过）"
    )


def test_cover_still_used_as_poster():
    """封面仍要当播放器的 `poster`（信息不能丢）。"""
    src = _src()
    i = src.find("<video")
    assert i != -1
    seg = src[i:i + 1400]
    assert "poster=" in seg, "video 要有 poster"
    assert "proxyImageUrl" in seg, "poster 走图片代理"


def test_image_only_notes_still_show_images():
    """**不能误伤图文笔记** —— 没有视频时图集必须照常显示。

    （回归风险：把条件写成"永远不显示"就坏了。）
    """
    src = _src()
    i = src.find("封面/图集预览")
    seg = src[i:i + 600]
    # 条件是"没有视频 **且** 有图"
    assert "previewMediaUrls.length > 0" in seg, "图集仍要有图才显示"


def test_thumbnail_strip_is_inside_cover_block():
    """缩略图条在封面块内 —— 视频时一并隐藏（只有一张，没意义）。"""
    src = _src()
    i = src.find("封面/图集预览")
    assert i != -1
    # 缩略图条（previewMediaUrls.map）应在封面块之后
    j = src.find("previewMediaUrls.map", i)
    assert j != -1, "应有缩略图条"
    # 且封面块的关闭条件在它之后（说明它在块内）
    block_end = src.find("previewVideoUrl && (", i)
    assert block_end == -1 or block_end > j, "缩略图条应在封面块内"
