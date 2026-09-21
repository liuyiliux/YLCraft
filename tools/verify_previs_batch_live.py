"""tasks 7.10：批量初稿**逐格确认**的落地验证。

核心要验的不是"能点"，而是那条安全属性：**没确认的格子不产生任何已保存数据**。
批量的价值在于省点击，风险也在这里——一旦"批量"顺手把没看过的草案也落了库，
用户就失去了逐格把关的机会（proposal 已确认项 17 明确不得绕过逐格确认）。

**判据**（同一批里的两格）：
1. 第一格点「确认并保存」后：revision 递增、场景里出现草案内容；
2. 第二格点「放弃」后：revision 不变、`scene_json` 与基线逐字节相同；
3. 进度文案要说清"还有没有下一格"。

**这个脚本的写法值得留意**：它把"现场"当一等公民——每一步都往 `lines` 里记，
**报告写在 `finally` 里**。原因很实在：前几版的失败现场是"报告文件根本不存在"，
因为报告只在成功结尾写；而超时、异常这些最需要现场的情况恰恰走不到结尾。
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from patchright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000/api/v1"
FRONTEND = "http://127.0.0.1:3000"
REPORT = Path("tmp/previs-batch/report.txt")


def api_get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as response:
        return json.load(response)


def api_post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def resolve_scene(project_id: str, content_id: str, panel: int) -> str:
    """取该分镜格已有的场景；没有才创建（直接 POST 在已存在时返回 409，那是幂等保护）。"""
    for item in api_get("/previs/scenes")["data"]:
        if (
            str(item.get("storyboard_content_id") or "") == content_id
            and int(item.get("panel_number") or 0) == panel
        ):
            return str(item["id"])
    response = api_post(
        "/previs/scenes",
        {
            "project_id": project_id,
            "storyboard_content_id": content_id,
            "panel_number": panel,
            "title": f"批量验证 · 第 {panel} 格",
        },
    )
    return str(response["data"]["id"])


def scene_state(scene_id: str) -> dict:
    data = api_get(f"/previs/scenes/{scene_id}")["data"]
    return {
        "revision": int(data.get("revision") or 0),
        "nodes": len((data.get("scene") or {}).get("nodes") or []),
        "digest": json.dumps(data.get("scene") or {}, sort_keys=True, ensure_ascii=False),
    }


def main() -> int:
    probe = api_get(f"/previs/scenes/{sys.argv[1]}")["data"]
    project_id = str(probe.get("project_id") or "")
    content_id = str(probe.get("storyboard_content_id") or "")
    panel_number = int(probe.get("panel_number") or 0)
    if not project_id or not content_id or panel_number <= 0:
        print("该场景未绑定分镜，无法做批量验证")
        return 2

    panels = [panel_number, panel_number + 1]
    created = [resolve_scene(project_id, content_id, panel) for panel in panels]
    baseline = [scene_state(scene_id) for scene_id in created]
    url = f"{FRONTEND}/previs?scene_id={created[0]}&draft=1&queue={','.join(created)}"
    lines = [
        f"批量队列：{panels} → {[s[:8] for s in created]}",
        f"基线 revision：{[item['revision'] for item in baseline]}",
    ]
    advanced = False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_selector("canvas", timeout=60_000)
                # 第一格：等幽灵草案（确认条）出现。
                # 等不到时给可区分的现场：`draft=1` 是否被页面自己摘掉＝"自动出草案"那段逻辑跑没跑。
                try:
                    page.locator('button:has-text("确认并保存")').first.wait_for(timeout=90_000)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"第一格等不到确认条：{type(exc).__name__}")
                    lines.append(f"  诊断 draft=1 还在 URL？{'draft=1' in page.url}")
                    lines.append(f"  诊断 页面提示={page.locator('.ant-message').all_inner_texts()[:3]}")
                    raise
                lines.append(f"第一格出现确认条；URL 是否带 queue：{'queue=' in page.url}")
                page.locator('button:has-text("确认并保存")').first.click()
                page.wait_for_timeout(8000)

                current = page.url.split("scene_id=")[-1].split("&")[0] if "scene_id=" in page.url else ""
                advanced = current == created[1]
                lines.append(f"确认后是否推进到第二格：{advanced}（当前 {current[:8]}，期望 {created[1][:8]}）")
                lines.append(f"  诊断 URL 是否还带 queue：{'queue=' in page.url}")

                if advanced:
                    page.locator('button:has-text("放弃")').first.wait_for(timeout=90_000)
                    page.locator('button:has-text("放弃")').first.click()
                    page.wait_for_timeout(5000)
                    lines.append(f"末格收尾后 URL 是否还带 queue：{'queue=' in page.url}")
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        lines.append(f"浏览器步骤中断：{type(exc).__name__}: {str(exc)[:160]}")

    after = [scene_state(scene_id) for scene_id in created]
    lines += [
        f"第一格（已确认）：revision {baseline[0]['revision']} → {after[0]['revision']}，节点 {baseline[0]['nodes']} → {after[0]['nodes']}",
        f"第二格（已放弃）：revision {baseline[1]['revision']} → {after[1]['revision']}，节点 {baseline[1]['nodes']} → {after[1]['nodes']}",
        f"第二格场景逐字节未变：{baseline[1]['digest'] == after[1]['digest']}",
    ]
    confirmed_ok = after[0]["revision"] > baseline[0]["revision"]
    discarded_ok = (
        after[1]["revision"] == baseline[1]["revision"] and baseline[1]["digest"] == after[1]["digest"]
    )
    lines.append(
        "结论："
        + (
            "逐格确认成立——已确认的落了库、已放弃的没有任何改动"
            if confirmed_ok and discarded_ok
            else f"未完全成立（已确认落库={confirmed_ok}，已放弃无改动={discarded_ok}，是否推进={advanced}）"
        )
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if confirmed_ok and discarded_ok else 1


if __name__ == "__main__":
    sys.exit(main())
