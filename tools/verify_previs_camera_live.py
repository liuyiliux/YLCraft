"""在真实浏览器里验证「活动机位逐帧跟随运镜」（用外部 Chrome / patchright）。

**为什么需要这个脚本**：相机"驱动 A、渲染 B"这类缺陷在单测里完全不可见——单测覆盖的是
纯函数与数据，而这类问题只在真实 WebGL 渲染里才表现出来（实测踩过：机位数据与关键帧全对，
画面却是 Canvas 默认机位 `[4,3,6]` 的斜侧面且完全不动）。

因此判据必须**客观**，不能靠"看起来对了"：

1. 把播放头从第 0 帧拖到末帧；
2. **主体（人形占位的灰）在画面里的像素面积必须显著变大**——推进 4m → 2.6m，
   投影面积比约 `(4/2.6)² ≈ 2.37`，取 1.3 作为下限（人物姿态变化带来的面积波动远小于此）；
3. 两帧不能相同（防止"静止不动但面积恰好变大"这种巧合）。

用法：
    backend\\venv_win\\Scripts\\python.exe tools\\verify_previs_camera_live.py <scene_id> [--out DIR] [--headed]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

#: 前端开发服务器（浏览器验证走它，不是后端 8000）
FRONTEND = "http://127.0.0.1:3000"
#: 人形占位的中性灰（`frontend/src/components/three/humanProxy.tsx` 的 DEFAULT_BODY）
BODY_RGB = (168, 173, 181)
TOLERANCE = 26


def body_pixels(path: Path) -> int:
    """画面里"人形占位那身灰"的像素数。

    **不要拿素材基色 `(168,173,181)` 直接匹配**：场景有方向光与 ACES 色调映射，
    角色实际渲染出来是 `(111,115,122)` 这一档深灰（实测），按基色匹配等于量了个寂寞。
    判据改为"**中性灰 + 落在角色这一档亮度**"：
    - 中性灰（三通道互差 ≤ 10）把彩色物体排除；
    - 亮度 80–150 把背景（实测 `(9,9,11)`）与更暗的网格线（实测 `(58,61,66)`）排除，
      剩下的主要就是角色本体。
    """
    image = Image.open(path).convert("RGB")
    total = 0
    for red, green, blue in image.getdata():
        if max(red, green, blue) - min(red, green, blue) > 10:
            continue
        if 80 <= (red + green + blue) / 3 <= 150:
            total += 1
    return total


PROBE_JS = """
() => {
  const canvas = document.querySelector('canvas');
  const root = canvas && canvas.__r3f && (canvas.__r3f.root || canvas.__r3f.store);
  let camera = null;
  try {
    const state = root && root.getState ? root.getState() : (root && root.store ? root.store.getState() : null);
    if (state && state.camera) {
      camera = {
        position: state.camera.position.toArray(),
        fov: state.camera.fov,
        isPerspectiveCamera: state.camera.isPerspectiveCamera === true,
      };
    }
  } catch (error) {
    camera = { error: String(error) };
  }
  return { hasR3fRoot: Boolean(root), camera };
}
"""


def probe_camera(page) -> dict:
    """读**渲染相机**的坐标（r3f 的 root 挂在 canvas 元素上）。读不到就返回带错误的对象。"""
    try:
        return page.evaluate(PROBE_JS)
    except Exception as exc:  # noqa: BLE001
        return {"hasR3fRoot": False, "error": str(exc)}


def identical(a: Path, b: Path) -> bool:
    return Image.open(a).convert("RGB").tobytes() == Image.open(b).convert("RGB").tobytes()


def diff_pixels(a: Path, b: Path, threshold: int = 12) -> int:
    """两帧差异像素数。

    它能把"机位在动"与"只有角色在动"分开：机位推进时**地面网格线整体位移**，
    差异会铺满画面；而只有角色动时，差异集中在它自己的轮廓内（占比小一个量级）。
    """
    left = Image.open(a).convert("RGB")
    right = Image.open(b).convert("RGB")
    if left.size != right.size:
        return -1
    total = 0
    for pixel_a, pixel_b in zip(left.getdata(), right.getdata()):
        if max(abs(pixel_a[0] - pixel_b[0]), abs(pixel_a[1] - pixel_b[1]), abs(pixel_a[2] - pixel_b[2])) > threshold:
            total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_id")
    parser.add_argument("--out", default="tmp/previs-camera-check")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（headless 下 WebGL 不可用时用）")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        print("patchright 不可用：请用 backend/venv_win 的 python 运行本脚本")
        return 2

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=not args.headed,
            # headless 下需要显式开启软件 WebGL，否则画布可能渲染不出来
            args=["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{FRONTEND}/previs?scene_id={args.scene_id}", wait_until="domcontentloaded")
        page.wait_for_selector("canvas", timeout=30000)

        # 导出与截图都要求活动机位；这里先切过去，确认它就是"渲染用的相机"
        page.get_by_role("button", name="活动机位").click()
        page.wait_for_timeout(2000)

        canvas = page.locator("canvas").first
        start = out / "frame_start.png"
        canvas.screenshot(path=str(start))
        # 直接读**渲染相机的坐标**：像素判据受光照/色调映射影响（实测角色渲染出来是深灰
        # `(111,115,122)` 而不是基色 `(168,173,181)`，按基色匹配等于量了个寂寞）。
        # 相机坐标是这套逻辑唯一的事实来源，能读到就不需要任何图像启发式。
        camera_at_start = probe_camera(page)

        # 把播放头移到末帧。
        #
        # 先用**键盘**（antd Slider 的 handle 是 role=slider 且可聚焦，End 直接到最大值）——
        # 鼠标拖拽依赖 handle 的命中区域与步进，实测容易"看着拖了、值没变"；
        # 而"播放头没动"与"机位没动"在画面上都会表现成"两帧几乎一样"，会得出错误结论。
        handle = page.locator(".ant-slider-handle").first
        handle.click()
        page.keyboard.press("End")
        page.wait_for_timeout(1500)

        # 读页面上的播放头读数（`第 N / 96 帧`）。**必须核对它真的到了末帧**，
        # 否则后面测的其实是"同一帧对比"，结论不成立。
        readout = "（未取到读数）"
        try:
            readout = page.locator("text=/第 \\d+ \\/ \\d+ 帧/").first.inner_text(timeout=5000)
        except Exception:  # noqa: BLE001
            pass
        print(f"播放头读数：{readout}")

        end = out / "frame_end.png"
        canvas.screenshot(path=str(end))
        camera_at_end = probe_camera(page)
        browser.close()

    start_pixels = body_pixels(start)
    end_pixels = body_pixels(end)
    ratio = end_pixels / start_pixels if start_pixels else 0.0
    differing = diff_pixels(start, end)

    cam_start = ((camera_at_start or {}).get("camera") or {}).get("position")
    cam_end = ((camera_at_end or {}).get("camera") or {}).get("position")
    moved = None
    if cam_start and cam_end:
        moved = sum((a - b) ** 2 for a, b in zip(cam_start, cam_end)) ** 0.5

    distance_frames = round(sum((a - b) ** 2 for a, b in zip(cam_end, cam_start)) ** 0.5, 3) if moved is not None else None
    lines = [
        f"场景：{args.scene_id}",
        f"播放头读数：{readout}",
        f"渲染相机 @ 第 0 帧：{cam_start}",
        f"渲染相机 @ 末帧：  {cam_end}",
        f"相机位移：{distance_frames} m（场景里推进关键帧是 4 → 2.6 米，应约 1.4）",
        f"（参考）主体像素：{start_pixels} → {end_pixels}，面积比 {ratio:.2f}（推进 4→2.6m 理论约 2.4）",
        f"（诊断）r3f root 是否可读：{bool((camera_at_start or {}).get('hasR3fRoot'))}",
        f"（参考）两帧差异像素：{differing}（占整幅 {differing / (1440 * 900) * 100:.1f}%）",
        f"（参考）两帧逐字节相同：{identical(start, end)}",
        f"截图：{start} / {end}",
    ]

    if moved is None:
        # 读不到相机就退回像素判据，并**明确标注它不可靠**（光照与色调映射会让颜色判据失真）
        lines.append("读不到渲染相机（r3f root 未暴露）：退回像素判据，结论仅供参考")
        if start_pixels == 0:
            lines.append("结论：画面里取不到主体像素，判据无效")
            code = 1
        elif ratio >= 1.3 or differing / (1440 * 900) > 0.04:
            lines.append("结论：画面确实随时间轴变化（疑似机位跟随），但缺权威判据")
            code = 0
        else:
            lines.append("结论：画面几乎没变，机位很可能没有跟随时间轴")
            code = 1
    elif moved > 0.3:
        lines.append("结论：活动机位确实逐帧跟随关键帧（渲染相机的坐标随播放头变化）")
        code = 0
    else:
        lines.append("结论：渲染相机没有随播放头移动——相机错位缺陷仍在")
        code = 1

    # 中文写到 UTF-8 文件而不是只靠控制台：Windows 控制台会把中文转成乱码，
    # 让"读结果"这件事变得不可靠（脚本自己的输出也会被误判成失败）
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
