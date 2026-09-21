"""服务端无头导出：用 patchright 驱动预演台页面**走它自己的导出**，把产物取回来。

**为什么是"驱动 UI"而不是"页面暴露一个取图钩子"**：钩子方案（页面在 `?headless_export=1`
时把 `renderFrame` 挂到 window）写完就是不可靠的——实测那段 effect 在真实页面里没有运行
（`window.__previsRender` 全程 undefined，排查过程见 `tasks.md` 6.18）。而"点导出、收下载"
这条路已经被 `tools/verify_previs_export_live.py` 反复验证可用，**并且它走的就是用户点导出时
完全相同的那条实现**——只有一条导出实现，不会再出现"视口对了、导出不对"那种两条路径不一致的
问题（同一个教训在 6.15/6.16 已经吃过一次）。

**它买到的是什么**：渲染发生在**服务端的无头浏览器**里，用户的标签页不参与——关掉页面照样出片。
代价是分辨率由服务端视口决定（默认 1280×720，`PREVIS_RENDER_VIEWPORT` 覆盖）。

**前置**：前端服务可达（`PREVIS_RENDER_BASE_URL`，默认 `http://127.0.0.1:3000`）。
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from pathlib import Path

logger = logging.getLogger("ylcraft.previs.headless_render")

DEFAULT_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_VIEWPORT = (1280, 720)
#: headless Chrome 需要显式开软件 WebGL，否则画布可能渲不出来（实测通过）
CHROME_ARGS = ["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def _viewport() -> dict[str, int]:
    raw = str(os.getenv("PREVIS_RENDER_VIEWPORT") or "").lower().replace("×", "x")
    if "x" in raw:
        width, _, height = raw.partition("x")
        if width.strip().isdigit() and height.strip().isdigit():
            return {"width": int(width), "height": int(height)}
    return {"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]}


def extract_frames(archive: bytes, target_dir: Path) -> tuple[int, list[int]]:
    """把导出的 ZIP 解到 `target_dir`，重命名成 ffmpeg 要求的连续编号。

    返回 `(帧数, 真实帧号列表)`。真实帧号**优先读 ZIP 里的 `manifest.json`**
    （那是页面自己记录的"第几张图对应时间轴第几帧"，步长 >1 时两者并不相等），
    读不到才退化成"按顺序从 0 开始数"——用文件名猜帧号会得到错位的剪辑素材。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    frames: list[int] = []
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = sorted(
            name for name in bundle.namelist() if name.lower().endswith((".jpg", ".jpeg"))
        )
        for index, name in enumerate(names, start=1):
            (target_dir / f"frame_{index:04d}.jpg").write_bytes(bundle.read(name))
        if "manifest.json" in bundle.namelist():
            try:
                manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
                frames = [int(item.get("frame") or 0) for item in (manifest.get("frames") or [])]
            except Exception:  # noqa: BLE001 - manifest 不可读不该让导出失败
                logger.warning("headless export: manifest 解析失败，帧号退化为按顺序编号")
    if len(frames) != len(names):
        frames = list(range(len(names)))
    return len(names), frames


async def export_frames_headless(scene_id: str, *, timeout_ms: int = 900_000) -> tuple[bytes, int]:
    """在无头浏览器里跑一次「导出参考帧 ZIP」，返回 `(ZIP 字节, 帧数)`。

    帧范围用的是**页面上的当前设置**（进预演台时默认铺满整条时间轴、步长 1）——
    这与用户手动点导出时的默认完全一致；要改范围就在页面上改，不在这条链路里另造一套参数。
    """
    try:
        from patchright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - 依赖在 venv 里
        raise RuntimeError("patchright 不可用：服务端无头导出需要它") from exc

    base_url = str(os.getenv("PREVIS_RENDER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}/previs?scene_id={scene_id}"

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True, args=CHROME_ARGS)
        try:
            context = await browser.new_context(viewport=_viewport(), accept_downloads=True)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_selector("canvas", timeout=120_000)
            # 导出只在「活动机位」下可用（导演视角的视锥辅助线不该进画面）
            await page.get_by_role("button", name="活动机位").click()
            await page.wait_for_timeout(2000)
            # 用文本定位：`get_by_role(name="导出", exact=True)` 在这个按钮上匹配不到（实测）
            await page.locator('button:has-text("导出")').first.click()
            await page.wait_for_timeout(1000)
            async with page.expect_download(timeout=timeout_ms) as download_info:
                await page.locator('button:has-text("导出参考帧 ZIP")').first.click()
            download = await download_info.value
            path = Path(await download.path())
            archive = path.read_bytes()
        finally:
            await browser.close()

    count = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        count = len([n for n in bundle.namelist() if n.lower().endswith((".jpg", ".jpeg"))])
    logger.info("headless export done scene=%s frames=%d bytes=%d", scene_id, count, len(archive))
    return archive, count
