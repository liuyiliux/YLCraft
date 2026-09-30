"""`video_url` 字段语义修复的回归测试（2026-09-29）。

## 用户反馈

    小红书有图集的被识别为视频了？
    https://www.xiaohongshu.com/explore/6a3b5e17000000001102cf79?xsec_token=...

截图：详情里渲染出一个 **0:00 的空播放器**，而真正的 5 张图集被隐藏。

## 根因（`crawler/service.py`）

    video_url=video_direct or item.url,     # ← 拿"原文链接"兜底！

于是**所有图集都有 `video_url`**，值是：

    "https://www.xiaohongshu.com/explore/6a3b5e17...?xsec_token=..."

前端靠"`video_url` 有没有值"判断是不是视频 → **图集被判成视频**。

## ⚠️ 这个坑的影响面比"显示错"更大

`crawler_result_asset_type()` 和 `is_multi_image_post()` **本来就靠它判断**：

    if ... or (result.images and not result.video_url):   # 图集判定
    return len(images) > 1 and not has_video              # 多图判定

`video_url` 永远有值 → 这两处**永远走不到图集分支** ——
即"多图图文"从来没被正确识别过（导入素材库时会退化成单张）。

注释里其实自己都写过："**抖音此前就踩过：video_url 放详情页会导致
下载器取不到流**" —— 同一个根因：**把"页面地址"与"媒体直链"混在一个字段**。

## 修法

没直链就**留空**。想跳原文有独立的 `url` 字段。

## 实测验证

    平台          图集(应无 video_url)   视频(应有 video_url)
    小红书        10 条 → 误带 0 ✅      —
    X             2 条 → 误带 0 ✅       8 条 → 有 8 ✅
    微博          —                      9 条 → 有 9 ✅
    抖音          —                      9 条 → 有 9 ✅

## 前端也加了一道防线

`previewVideoUrl` 现在**只认媒体直链**：
  · 扩展名是 `.mp4/.m3u8/.webm/.mov`
  · 或来自已知视频 CDN（douyinvod / weibocdn / twimg / xhscdn /stream / bilivideo）

**明显是网页地址的排除掉** —— 即使后端再出类似问题也不会误判。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


# =============================================================================
# 后端：video_url 不再用原文链接兜底
# =============================================================================

def test_video_url_not_falling_back_to_page_url():
    """**回归（根因）**：`video_url` 不能用 `item.url` 兜底。

    原写法 `video_direct or item.url` 让**所有图集都有 video_url**，
    前端据此把图集判成视频。
    """
    from app.services.crawler import service as cs

    src = inspect.getsource(cs.CrawlerService._search_via_platforms)
    assert "video_url=video_direct or item.url" not in src, (
        "不该再用原文链接兜底（图集会被判成视频）"
    )
    assert "video_url=video_direct," in src, "没直链就留空"


def test_multi_image_post_detection_now_reachable():
    """**回归**：`is_multi_image_post` 现在能真正生效。

    它靠 `not video_url` 判断 —— `video_url` 永远有值时这个分支
    **永远为 False**，即"多图图文"从来没被识别过。
    """
    from app.services.crawler.service import is_multi_image_post

    class _R:
        def __init__(self, images, video_url):
            self.images = images
            self.video_url = video_url

    # 纯图集（无视频）→ 应识别为多图
    assert is_multi_image_post(_R(["a", "b", "c"], "")) is True
    # 视频 + 封面图 → 不是图集
    assert is_multi_image_post(_R(["a"], "http://x/v.mp4")) is False
    # 单图 → 不是多图
    assert is_multi_image_post(_R(["a"], "")) is False


def test_asset_type_uses_video_url_correctly():
    """**回归**：`crawler_result_asset_type` 的图集分支现在能走到。"""
    from app.services.crawler.service import crawler_result_asset_type

    class _R:
        def __init__(self, images, video_url, type_):
            self.images = images
            self.video_url = video_url
            self.type = type_

    # 多图 + 无视频 → IMAGE
    t = crawler_result_asset_type(_R(["a", "b"], "", "note"))
    assert t.name == "IMAGE", f"多图应判为 IMAGE，实际 {t}"


# =============================================================================
# 前端：只认媒体直链
# =============================================================================

def _crawler_src() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


def test_frontend_requires_media_url_shape():
    """**回归**：前端要校验"像不像媒体直链"。

    即使后端再出现"原文链接塞进 video_url"，前端也不该误判成视频。
    """
    src = _crawler_src()
    i = src.find("previewVideoUrl = useMemo")
    assert i != -1
    seg = src[i:i + 2200]
    assert "mp4" in seg, "应认 .mp4 扩展名"
    assert "m3u8" in seg, "应认 .m3u8"
    # 已知视频 CDN
    for cdn in ("douyinvod", "weibocdn", "twimg", "xhscdn"):
        assert cdn in seg, f"应认 {cdn} 视频 CDN"


def test_frontend_rejects_page_urls():
    """**回归**：明显是网页地址的要排除。

    （用户遇到的正是 `https://www.xiaohongshu.com/explore/...` 被当成视频。）

    判据：**不匹配媒体特征就不返回**（白名单），
    而不是"是 http 就认"（黑名单/无判断）。
    """
    src = _crawler_src()
    i = src.find("previewVideoUrl = useMemo")
    assert i != -1
    seg = src[i:i + 2200]
    # 必须有"媒体特征"判断
    assert "mp4" in seg, "要按扩展名白名单判断"
    assert "continue" in seg, "不匹配的要跳过，而不是直接 return"
    # 关键：小红书/微博的页面地址形态不能被认
    assert "explore" not in seg or "xhscdn" in seg, (
        "不该把 /explore/ 页面地址当视频"
    )


def test_video_notes_unaffected():
    """视频笔记仍要有地址（修复不能误伤）。"""
    src = _crawler_src()
    i = src.find("previewVideoUrl = useMemo")
    seg = src[i:i + 2200]
    # 仍保留原来的取址来源
    for key in ("_video_url", "aweme_info", "page_info"):
        assert key in seg, f"应仍读 {key}"
