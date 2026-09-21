"""验证**导出产物**（参考帧 ZIP）里的相机确实按运镜走。

为什么必须单独验这一条：视口与导出是**两条取图路径**——视口走 `useThree` 订阅（拿的总是最新值），
导出走 `onCreated` 里注册的闭包。实测就出现过"视口已经推近到贴脸、导出仍是老相机的固定远景"，
根因是那个闭包抓着**创建时**的 state 快照，而 drei `makeDefault` 会**替换** state 里那份 camera。
所以只验视口是不够的，必须直接验导出出来的帧。

判据与 `verify_previs_camera_live.py` 同一套（中性灰 + 亮度 80–150 的像素数，理由见那个脚本的注释），
并额外要求：**末帧的主体像素显著多于首帧**（推进 4→2.6m 理论约 2.4 倍）。

用法：
    backend\\venv_win\\Scripts\\python.exe tools\\verify_previs_export_live.py <scene_id>
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

from PIL import Image

FRONTEND = "http://127.0.0.1:3000"


def body_pixels(blob: bytes) -> int:
    """一张 JPEG 里"中性灰且落在角色亮度档"的像素数（同另一脚本的判据）。"""
    image = Image.open(io.BytesIO(blob)).convert("RGB")
    total = 0
    for red, green, blue in image.getdata():
        if max(red, green, blue) - min(red, green, blue) > 10:
            continue
        if 80 <= (red + green + blue) / 3 <= 150:
            total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_id")
    parser.add_argument("--out", default="tmp/previs-export-check")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from patchright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page.goto(f"{FRONTEND}/previs?scene_id={args.scene_id}", wait_until="domcontentloaded")
        page.wait_for_selector("canvas", timeout=30000)
        page.get_by_role("button", name="活动机位").click()
        page.wait_for_timeout(1500)

        # 导出要求活动机位（按钮在导演视角下禁用，这里已切好）。
        # 用**文本**定位而不是 `get_by_role(name=...)`——实测后者在这个按钮上匹配不到
        # （可访问名与 `exact=True` 的期望值对不上，而按钮文本就是"导出"，见按钮 dump）。
        page.locator('button:has-text("导出")').first.click()
        page.wait_for_timeout(1000)
        modal_note = ""
        try:
            modal_note = page.locator("text=/机位：按/").first.inner_text(timeout=3000)
        except Exception:  # noqa: BLE001
            pass

        with page.expect_download(timeout=300000) as download_info:
            page.locator('button:has-text("导出参考帧 ZIP")').first.click()
        download = download_info.value
        archive = out / "frames.zip"
        download.save_as(str(archive))
        browser.close()

    with zipfile.ZipFile(archive) as bundle:
        names = sorted(name for name in bundle.namelist() if name.lower().endswith((".jpg", ".jpeg")))
        if len(names) < 2:
            (out / "report.txt").write_text(f"ZIP 里只有 {len(names)} 张图，无法比较首末帧\n", encoding="utf-8")
            print(f"ZIP 里只有 {len(names)} 张图")
            return 1
        first_pixels = body_pixels(bundle.read(names[0]))
        last_pixels = body_pixels(bundle.read(names[-1]))

    ratio = last_pixels / first_pixels if first_pixels else 0.0
    lines = [
        f"场景：{args.scene_id}",
        f"导出弹窗自检：{modal_note}",
        f"ZIP 帧数：{len(names)}（首 {names[0]} / 末 {names[-1]}）",
        f"首帧主体像素：{first_pixels}",
        f"末帧主体像素：{last_pixels}",
        f"面积比：{ratio:.2f}（推进 4→2.6m 理论约 2.4，判据下限 1.3）",
        f"产物：{archive}",
    ]
    if first_pixels == 0:
        lines.append("结论：首帧取不到主体像素——画面可能是空的，判据无效")
        code = 1
    elif ratio >= 1.3:
        lines.append("结论：导出产物里的相机确实在推近（导出与视口一致）")
        code = 0
    else:
        lines.append("结论：导出产物里的主体没有变大——导出走的仍是固定机位（闭包快照问题）")
        code = 1

    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
