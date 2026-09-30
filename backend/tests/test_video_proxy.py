"""视频代理的回归测试（2026-09-29）。

## 用户反馈

    视频直链无法直接播放（可能被防盗链限制），请点「打开原文」

## 根因（实测，与直觉相反）

X 的视频直链 `video.twimg.com`：

    裸请求（无 Referer）           → HTTP 200  ✅
    带 Origin/Referer（localhost） → **HTTP 403** ❌
    带 Range                       → HTTP 206  ✅

**浏览器 `<video>` 必然会带 `Referer`** ——
所以直链在浏览器里**一定失败**，不是网络问题。

## 与图片代理**相反**

    图片  需要正确的 Referer（不带就 403）
    视频  **不能**带 Referer（带了就 403）

所以视频必须走**独立的代理**，不能复用图片代理
（`_REFERER_MAP` 里 `twimg.com` → `https://twitter.com`，
拿去请求视频正好触发 403）。

## 还要透传 Range

浏览器的 `<video>` 会先发 `Range: bytes=0-` 探测，
拖动进度条也发 Range。不透传的话：
  · 不能拖动
  · 部分浏览器直接报错（拿不到 206）

实测代理效果：

    无 Range: HTTP 200  video/mp4  2.28MB  accept-ranges=bytes
    带 Range: **HTTP 206**  1001 字节  content-range=bytes 1000-2000/2279789
"""

from __future__ import annotations

import inspect

import pytest


def _src() -> str:
    from app.api.v1 import proxy

    return inspect.getsource(proxy)


# =============================================================================
# 代理存在且行为正确
# =============================================================================

def test_video_proxy_route_exists():
    """要有 `/proxy/video` 路由。"""
    from app.api.v1 import proxy

    assert hasattr(proxy, "proxy_video")
    src = _src()
    assert '"/video"' in src


def test_video_proxy_strips_referer_for_twimg():
    """**回归（关键）**：对 X 的 CDN **不能发 Referer**。

    实测：带 Referer → 403。这与图片相反（图片必须带）。
    """
    from app.api.v1 import proxy

    hosts = proxy._NO_REFERER_HOSTS
    assert any("twimg" in h for h in hosts), "twimg.com 要在名单里"

    src = inspect.getsource(proxy.proxy_video)
    assert "send_referer" in src, "要按域名决定发不发 Referer"
    assert "_NO_REFERER_HOSTS" in src


def test_video_proxy_forwards_range():
    """**回归**：要透传 `Range`（拖动进度条 / 边下边播）。"""
    src = inspect.getsource(_import_proxy().proxy_video)
    assert "range" in src.lower(), "要读 Range 头"
    assert '"Range"' in src, "要转发给源站"


def _import_proxy():
    from app.api.v1 import proxy

    return proxy


def test_video_proxy_returns_streaming():
    """要用 `StreamingResponse`（视频几 MB~几十 MB，不能全读进内存）。"""
    src = _src()
    assert "StreamingResponse" in src
    assert "aiter_bytes" in src, "应分块转发"


def test_video_proxy_passes_through_206_and_content_range():
    """**回归**：要回传 `206` 与 `Content-Range`。

    浏览器靠这两个判断"能不能拖动"。
    """
    src = inspect.getsource(_import_proxy().proxy_video)
    assert "content-range" in src.lower(), "要回传 Content-Range"
    assert "resp.status_code" in src, "状态码要透传（200/206）"
    assert "accept-ranges" in src.lower(), "要回传 Accept-Ranges"


def test_video_proxy_validates_url():
    """非法 URL 要报 400（不是 500）。"""
    src = inspect.getsource(_import_proxy().proxy_video)
    assert "400" in src
    assert "http" in src, "要校验 scheme"


def test_video_proxy_error_is_502_not_500():
    """上游失败要给 502（网关错误），不是 500。"""
    src = inspect.getsource(_import_proxy().proxy_video)
    assert "502" in src


# =============================================================================
# 前端接的是**视频**代理，不是图片代理
# =============================================================================

def test_frontend_uses_video_proxy():
    """**回归**：前端 `<video src>` 要走 `/proxy/video`。

    原来是直链 —— 浏览器一定带 Referer → 403 → 播不了。
    """
    from pathlib import Path

    p = (Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "pages" / "crawler" / "index.tsx")
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    i = src.find("<video")
    assert i != -1, "应有 video 标签"
    seg = src[i:i + 1400]
    assert "/api/v1/proxy/video" in seg, "video src 要走视频代理"
    # 不能直接用裸直链
    assert "src={previewVideoUrl}" not in seg, "不该直接用直链（会被 403）"


def test_frontend_offers_open_in_new_window():
    """播不了时要有"在新窗口打开"（走代理，可另存）。"""
    from pathlib import Path

    p = (Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "pages" / "crawler" / "index.tsx")
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "在新窗口打开视频" in src
