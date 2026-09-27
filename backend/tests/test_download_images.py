"""图集下载端点的契约测试。

## 背景（2026-09-27）

抖音/小红书的图文笔记是**多图作品**，解析后拿到 N 个图片地址，
但原来既没有返回字段（`ParseResponse` 缺 `images`），
也没有下载入口——用户只能一张张手动右键。

本轮补齐：响应带 `images`/`content_type`，前端出图集卡片，
新增 `POST /api/v1/download/download-images` 一次性落盘。

## 实测

抖音作品 7656457812507817841（9 张图）：
    解析 → image_count=9，content_type=image
    下载前 3 张 → 383/311/292 KB，文件头 `RIFF....WEBP`（真实 WebP）
    落盘目录：backend/downloads/douyin/{标题}/
"""

from __future__ import annotations

import inspect

import pytest


def test_download_images_endpoint_exists():
    """端点必须挂载。"""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/download/download-images" in paths


def test_download_images_request_model():
    """请求模型：urls 必填，title/platform 有合理默认值。"""
    from app.api.v1.download import DownloadImagesRequest

    req = DownloadImagesRequest(urls=["https://x/a.webp"])
    assert req.urls == ["https://x/a.webp"]
    assert req.title == "图集"
    assert req.platform == ""


def test_download_images_response_model():
    """响应要区分成功与失败（部分失败不能只报成功）。"""
    from app.api.v1.download import DownloadImagesResponse

    fields = DownloadImagesResponse.model_fields
    assert "saved" in fields
    assert "failed" in fields, "必须有失败清单——单张失败不中断其余"
    assert "dir_path" in fields


def test_endpoint_imports_httpx():
    """**回归**：函数内必须 import httpx。

    踩过：忘了导入 → `NameError: name 'httpx' is not defined` → 500。
    """
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    assert "import httpx" in src, "函数内应导入 httpx"


def test_endpoint_sets_referer_for_anti_hotlink():
    """图床有防盗链，必须带 Referer，否则 403。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    assert "Referer" in src
    assert "douyin.com" in src and "xiaohongshu.com" in src


def test_endpoint_sanitizes_title_for_path():
    """标题里的非法字符要清洗，否则建目录会失败。

    实测标题形如「回到千禧年💿。#大人感变美思路 #古早穿搭」，
    含 emoji 与空格，直接做目录名有风险。
    """
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    assert "safe_title" in src, "应清洗标题"
    assert "sub(" in src, "应做字符替换"
    assert '[0:60]' in src or "[:60]" in src, "应限制长度"


def test_endpoint_continues_after_single_failure():
    """单张失败不应中断其余（网络抖动常见）。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    # 失败在循环内 catch 并记入 failed，不 raise
    assert "failed.append" in src
    assert "continue" in src, "失败后应 continue 而不是 raise"


def test_parse_response_has_image_fields():
    """解析响应必须带图集字段（否则前端拿不到图片列表）。"""
    from app.api.v1.download import ParseResponse

    r = ParseResponse(success=True, content_type="image",
                      images=["https://x/a.webp"], image_count=1)
    assert r.content_type == "image"
    assert r.images == ["https://x/a.webp"]
    assert r.image_count == 1


@pytest.mark.asyncio
async def test_download_images_rejects_empty_list():
    """空列表要明确报错，不能静默成功。"""
    from fastapi import HTTPException

    from app.api.v1.download import DownloadImagesRequest, download_images

    with pytest.raises(HTTPException) as exc:
        await download_images(DownloadImagesRequest(urls=[]))
    assert exc.value.status_code == 400


def test_frontend_has_gallery_section():
    """前端必须有图集展示区。

    踩过：`.images` 只在视频卡片里被用来**隐藏**，没有展示区，
    即使后端返回了 9 张图，界面上一张也看不到。
    """
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "pages" / "download" / "index.tsx"
    )
    if not page.exists():
        pytest.skip("前端源码不在预期位置")
    src = page.read_text(encoding="utf-8", errors="ignore")
    assert "图文图集" in src, "应有图集卡片"
    assert "handleDownloadAllImages" in src, "应有全部下载"
    assert "handleDownloadImage" in src, "应有单张下载"
    assert "proxyImage" in src, "图片应走代理（图床有防盗链）"
