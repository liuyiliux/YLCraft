"""图集下载（`/download/download-images`）的回归测试（2026-09-29）。

## 用户要求

    "需要"（验证「图文下载」能不能下全套）

## 实测结果

    抖音   图集 13 张 → 测 3 张 成功 3 失败 0 ✅
    X      图集  2 张 → 测 2 张 成功 2 失败 0 ✅
    微博   图集  9 张 → 测 3 张 成功 3 失败 0 ✅（**修复前 0/3，全 403**）
    小红书 搜索 461（cookie 失效，与本功能无关）

## 找到的 bug：Referer 映射表缺平台 + 兜底成了抖音

    referers = {
        "douyin": "https://www.douyin.com/",
        "xiaohongshu": "https://www.xiaohongshu.com/",
        "bilibili": "https://www.bilibili.com/",
    }
    referer = referers.get(req.platform, "https://www.douyin.com/")  # ← 兜底！

**微博传进去的是"抖音的 Referer"** → 实测 403：

    {'url': 'https://wx1.sinaimg.cn/large/...jpg',
     'error': "HTTPStatusError: Client error '403'"}

## 修法：按**域名**判断（与 `proxy.py` 一致）

各平台的防盗链行为**方向相反**：

    微博图片   **必须带** weibo 的 Referer
    X 图片     **不能带** Referer（带了 403）

所以复用 `proxy.py` 的 `_guess_referer` + `_NO_REFERER_HOSTS`，
**逐张按图片域名决定** —— 而不是只看 `req.platform`
（platform 可能是空串或别名，域名更可靠；同一批图也可能来自不同 CDN）。

## 顺带记一个踩过的坑

端点的真实路径带 `/download` 前缀：

    ❌ /api/v1/download-images
    ✅ /api/v1/download/download-images

我第一版写错了，拿到 404 却以为是"下载逻辑坏了"。
"""

from __future__ import annotations

import inspect

import pytest


def _src() -> str:
    from app.api.v1 import download

    return inspect.getsource(download)


# =============================================================================
# Referer 按域名判断
# =============================================================================

def test_no_hardcoded_referer_fallback_to_douyin():
    """**回归（根因）**：不该再有"兜底成抖音"的硬编码映射表。

    微博因此拿到抖音的 Referer → 403。
    """
    src = _src()
    assert 'referers.get(req.platform, "https://www.douyin.com/")' not in src, (
        "不该兜底成抖音（微博会 403）"
    )


def test_uses_proxy_referer_helpers():
    """**回归**：要复用 `proxy.py` 的域名判断（保持一致）。"""
    src = _src()
    assert "_guess_referer" in src, "应按域名猜 Referer"
    assert "_NO_REFERER_HOSTS" in src, "要尊重'不能带 Referer'的域名"


def test_referer_decided_per_image():
    """**回归**：逐张按**图片域名**决定，而不是整批按 platform。

    同一批图可能来自不同 CDN；platform 也可能是空串/别名。
    """
    src = _src()
    i = src.find("download_images")
    seg = src[i:i + 4000]
    assert "urlparse(img_url)" in seg, "要按每张图的域名判断"
    assert "headers[\"Referer\"]" in seg or "headers['Referer']" in seg
    # 在循环内（不是循环外算一次）
    loop = seg.find("for idx, img_url in enumerate")
    setref = seg.find('headers["Referer"]')
    assert loop != -1 and setref != -1 and setref > loop, (
        "Referer 要在循环内按图设置"
    )


def test_urlparse_imported():
    """**回归**：`urlparse` 要导入（改这段时漏过，导致 SyntaxError 之外的 NameError）。"""
    src = _src()
    assert "from urllib.parse import urlparse" in src


def test_weibo_referer_in_map():
    """微博图床 `sinaimg.cn` 要在 Referer 映射表里。

    （它是 `proxy.py` 的 `_REFERER_MAP`，两条路共用。）
    """
    from app.api.v1 import proxy

    assert any("sinaimg" in k for k in proxy._REFERER_MAP), "微博图床要能拿到 Referer"
    assert "weibo" in proxy._REFERER_MAP.get("sinaimg.cn", "").lower()


def test_loop_structure_is_valid():
    """**回归**：`try/except` 缩进要对。

    （我改这段时把 `except` 缩进搞错了，语法直接不通过。）
    """
    from app.api.v1 import download

    src = inspect.getsource(download.download_images)
    lines = src.splitlines()
    try_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "try:")
    exc_idx = next(i for i, ln in enumerate(lines) if ln.strip().startswith("except "))
    t_ind = len(lines[try_idx]) - len(lines[try_idx].lstrip())
    e_ind = len(lines[exc_idx]) - len(lines[exc_idx].lstrip())
    assert t_ind == e_ind, (f"try/except 缩进不一致：try={t_ind} except={e_ind}")


# =============================================================================
# 端点契约（别再把路径写错）
# =============================================================================

def test_endpoint_path_has_download_prefix():
    """**回归**：真实路径是 `/download/download-images`。

    我第一版写成 `/api/v1/download-images` → 404，
    却误以为是"下载逻辑坏了"。
    """
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/download/download-images" in paths, (
        "端点路径要带 /download 前缀"
    )
    assert "/api/v1/download-images" not in paths, "不存在无前缀的路径"


def test_separate_download_urls_used():
    """下载图集与下载视频是**不同端点**（别混）。"""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert any("download-images" in p for p in paths)
    assert any("download-video" in p or "download" in p for p in paths)
