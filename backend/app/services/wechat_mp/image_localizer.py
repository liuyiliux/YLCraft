"""
微信公众号文章图片本地化

- 下载图片到 <save_dir>/images/<seq>_<hash>.<ext>
- 返回 {原URL: 相对路径} 映射，供 service 改写 MD/HTML 中的引用
- 失败的 URL 不出现在返回 dict 中（保持原 URL 不改写，不阻塞主流程）
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("ylcraft.wechat_mp.image_localizer")

# 微信图片 CDN（防盗链宽松，但带 Referer 更稳）
_REFERER = "https://mp.weixin.qq.com/"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
_CONCURRENCY = 3  # 并发下载数（遵守微信限流）
_TIMEOUT = 15.0
_MAX_RETRIES = 2

_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}


class ImageLocalizer:
    """下载微信文章图片到本地，并返回 URL → 相对路径映射。"""

    def __init__(self, save_dir: str, client: Optional[httpx.AsyncClient] = None):
        self.save_dir = Path(save_dir)
        self.images_dir = self.save_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._external_client = client  # 复用外部 client（可为 None）
        self._own_client: Optional[httpx.AsyncClient] = None
        self._sem = asyncio.Semaphore(_CONCURRENCY)

    async def localize(self, image_urls: list[str]) -> dict[str, str]:
        """
        下载所有图片。

        Returns:
            {原URL: 相对路径(相对 save_dir)}；失败的 URL 不包含在内。
        """
        url_map: dict[str, str] = {}
        if not image_urls:
            return url_map

        tasks = [self._download_one(idx, url) for idx, url in enumerate(image_urls)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, tuple) and r[0]:
                url_map[r[0]] = r[1]

        # 关闭自建的 client
        if self._own_client is not None:
            await self._own_client.aclose()
            self._own_client = None

        return url_map

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        if self._own_client is None:
            self._own_client = httpx.AsyncClient(
                headers={"Referer": _REFERER, "User-Agent": _USER_AGENT},
                timeout=_TIMEOUT,
                verify=False,
                follow_redirects=True,
            )
        return self._own_client

    async def _download_one(self, idx: int, url: str) -> tuple[str, str]:
        """下载单张图片，返回 (原URL, 相对路径)；失败返回 ("", "")。"""
        if not url or url.startswith("data:"):
            return ("", "")

        async with self._sem:
            client = await self._get_client()
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200 or not resp.content:
                        raise IOError(f"HTTP {resp.status_code}")
                    ext = self._guess_ext(resp.headers.get("content-type", ""), url)
                    name = f"{idx:03d}_{hashlib.md5(url.encode()).hexdigest()[:8]}{ext}"
                    (self.images_dir / name).write_bytes(resp.content)
                    return (url, f"images/{name}")
                except Exception as e:
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(1.0)
                        continue
                    logger.warning(f"[ImageLocalizer] 下载失败（保留原链接）: {url} -> {e}")
                    return ("", "")
        return ("", "")

    @staticmethod
    def _guess_ext(content_type: str, url: str) -> str:
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct in _EXT_BY_CONTENT_TYPE:
            return _EXT_BY_CONTENT_TYPE[ct]
        # 从 URL 后缀推断
        low = url.split("?")[0].lower()
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"):
            if low.endswith(ext):
                return ".jpg" if ext == ".jpeg" else ext
        return ".jpg"
