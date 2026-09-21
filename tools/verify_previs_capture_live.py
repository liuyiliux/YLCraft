"""tasks 7.1 的收尾段：**截图回流**（截图 → 入库 → 关联到分镜）。

7.1 的前面几段已经被验证过：初稿接口（3 条操作 / 0 拒绝）、幽灵预览与逐格确认落库（7.10）。
剩下这一段要验的是"点一下截图回流会发生什么"，而且**不能只看页面上的成功提示**——
提示说成功、实际没关联上（历史上就出现过"关联成功却选不到"）才是真正的坑。

因此这里**拦截接口响应**核对三件事：
1. `asset_id` 有值（图确实入库了）；
2. `linked` 为真（确实关联到了分镜内容，而不是只存了张图）；
3. 溯源由**服务端派生**（`provenance.scene_revision` 等字段存在），而不是客户端自称。

用法：
    backend\\venv_win\\Scripts\\python.exe tools\\verify_previs_capture_live.py <已绑定分镜的场景 id>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from patchright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:3000"
REPORT = Path("tmp/previs-capture/report.txt")


def main() -> int:
    scene_id = sys.argv[1]
    lines = [f"场景：{scene_id}"]
    payload: dict = {}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(f"{FRONTEND}/previs?scene_id={scene_id}", wait_until="domcontentloaded")
                page.wait_for_selector("canvas", timeout=60_000)
                # 截图回流只在「活动机位」下可用（截的就是该机位画面）
                page.get_by_role("button", name="活动机位").click()
                page.wait_for_timeout(2500)
                with page.expect_response(lambda r: "/capture" in r.url, timeout=120_000) as info:
                    page.locator('button:has-text("截图回流")').first.click()
                response = info.value
                payload = response.json()
                lines.append(f"HTTP {response.status}")
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        lines.append(f"浏览器步骤中断：{type(exc).__name__}: {str(exc)[:200]}")

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        lines.append(f"响应体异常：{json.dumps(payload, ensure_ascii=False)[:300]}")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1

    asset_id = str(data.get("asset_id") or "")
    linked = bool(data.get("linked"))
    provenance = data.get("provenance") or {}
    lines += [
        f"asset_id={asset_id[:12]}…  linked={linked}",
        f"content_id={str(data.get('content_id') or '')[:12]}…  role={data.get('role')}",
        f"provenance.scene_revision={provenance.get('scene_revision')}  "
        f"camera_id={str(provenance.get('camera_id') or '')[:12]}",
        f"link_error={data.get('link_error') or '（无）'}",
    ]
    ok = bool(asset_id) and linked and provenance.get("scene_revision") is not None
    lines.append(
        "结论："
        + (
            "截图回流成立——图已入库、已关联到分镜，且溯源由服务端从场景派生"
            if ok
            else "不成立（见上面各字段）"
        )
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
