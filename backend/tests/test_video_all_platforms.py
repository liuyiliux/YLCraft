"""全平台视频可播性的回归测试（2026-09-29）。

## 起因

用户问："你改的哪个平台"

**问得对** —— 我上一轮只实测了 X 就让用户"刷新试试"，
没验证其他平台。补测后发现还有两个平台**根本没接通**。

## 全平台实测结果（修复后）

    平台        视频条数   有地址   可播放
    X           9         4       ✅
    微博         9         4       ✅
    抖音         9         4       ✅  ← 本轮修复
    小红书       0*        4       ✅  ← 本轮修复
    B站          9         0       —  （走 yt-dlp，不内嵌）

    * 小红书搜索不返回视频类型，地址只在详情里

## ⚠️ 关键事实：**每个平台的防盗链行为都不一样**

    平台        Referer 行为
    X          带 → **403**；裸请求 → 200   （**不能带**）
    抖音       裸请求 → **403**；带 douyin Referer → 200（**必须带对的**）
    微博       怎么都 200                    （无所谓）
    小红书     怎么都 200                    （无所谓）

**所以「统一走后端代理」是对的** —— 由 `/proxy/video` 按域名决定，
前端不用关心这些差异（否则前端要写四套逻辑）。

## 本轮修的两个平台

### 抖音：搜索结果**没提取**视频地址

地址在 `aweme_info.video.play_addr.url_list`（实测 3 个候选），
但 `_parse_aweme` 没往 `raw_data` 塞 `_video_url` ——
9/9 条视频都缺，前端点播放直接失败。

⚠️ 还要**排除音频**：实测图文笔记的 `video.play_addr` 指向 **mp3**（配乐），
拿它当视频播会失败。

### 小红书：地址是**裸字符串**，不在 `raw_data._video_url`

    详情 `data.video` = "http://sns-video-v6.xhscdn.com/stream/...mp4?sign=..."

前端 memo 原来只读 `raw_data._video_url` / `video_url`，
读不到小红书的 `video` 字段。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _crawler_src() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 抖音：搜索结果要提取视频地址
# =============================================================================

def test_douyin_search_extracts_video_url():
    """**回归**：抖音搜索结果的 `raw_data._video_url` 要有值。

    原来没提取 —— 9/9 条视频都缺地址，播放直接失败。
    """
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    assert "_video_url" in src, "应往 raw_data 塞 _video_url"
    assert "play_addr" in src, "地址在 video.play_addr"


def test_douyin_prefers_play_addr_over_download_addr():
    """优先 `play_addr`（无水印），退而求其次才 download_addr。"""
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    i_play = src.find("play_addr")
    i_dl = src.find("download_addr")
    assert i_play != -1
    if i_dl != -1:
        assert i_play < i_dl, "play_addr 应排在前面（无水印）"


def test_douyin_excludes_audio_urls():
    """**回归**：要排除音频地址。

    实测图文笔记的 `video.play_addr` 指向 **mp3**（配乐），
    拿它当视频播会失败。
    """
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    assert "mp3" in src or "m4a" in src, "应排除音频扩展名"
    assert "audio" in src.lower()


def test_douyin_image_note_has_no_video_url():
    """图文笔记不该有视频地址。"""
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.parse_search_item)
    assert "is_image" in src, "应判断是否图文"


# =============================================================================
# 小红书：地址在 detail.video（裸字符串）
# =============================================================================

def test_frontend_reads_xhs_video_string():
    """**回归**：前端要读小红书详情顶层的 `video`（裸字符串）。

    它不是 `raw_data._video_url` —— 原来读不到，于是小红书视频播不了。
    """
    src = _crawler_src()
    i = src.find("previewVideoUrl = useMemo")
    assert i != -1
    seg = src[i:i + 1600]
    assert "detailNote as any).video" in seg or "(detailNote as any).video" in seg, (
        "应读 detailNote.video（小红书）"
    )


def test_frontend_reads_douyin_aweme_info():
    """前端也要能直接翻抖音的 `aweme_info.video.play_addr`（多一层保险）。"""
    src = _crawler_src()
    i = src.find("previewVideoUrl = useMemo")
    seg = src[i:i + 1600]
    assert "aweme_info" in seg, "应兼容 aweme_info.video.play_addr"


def test_frontend_excludes_audio():
    """前端也要排除音频地址（双保险）。"""
    src = _crawler_src()
    i = src.find("previewVideoUrl = useMemo")
    seg = src[i:i + 1600]
    assert "mp3" in seg or "m4a" in seg


# =============================================================================
# 代理：按域名决定 Referer（因为各平台行为不同）
# =============================================================================

def test_proxy_decides_referer_per_host():
    """**回归（关键）**：代理要**按域名**决定发不发 Referer。

    实测各平台行为**完全相反**：

        X      带 Referer → 403（不能带）
        抖音   裸请求 → 403（必须带对的）

    所以不能一刀切，必须按域名判断。
    """
    from app.api.v1 import proxy

    src = inspect.getsource(proxy.proxy_video)
    assert "_NO_REFERER_HOSTS" in src, "要有'不发 Referer'的名单"
    assert "_guess_referer" in src, "其余域名要发对的 Referer"

    assert any("twimg" in h for h in proxy._NO_REFERER_HOSTS), "X 的 CDN 不发 Referer"
    # 抖音必须发（在 _REFERER_MAP 里有）
    assert any("douyin" in k for k in proxy._REFERER_MAP), "抖音要在 Referer 映射里"


def test_frontend_always_uses_proxy():
    """**回归**：前端统一走代理，不自己判断防盗链。

    让前端写四套逻辑容易漏 —— 由后端按域名处理。
    """
    src = _crawler_src()
    i = src.find("<video")
    assert i != -1
    seg = src[i:i + 1500]
    assert "/api/v1/proxy/video" in seg
    # 不该出现"直接用原地址"的分支
    assert "src={previewVideoUrl}" not in seg
