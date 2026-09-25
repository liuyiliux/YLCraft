"""预演台助手的**端到端验收**（OpenSpec `previs-ai-copilot` 3.2 / 3.3）。

为什么必须真跑浏览器：这条链路的每一步都跨在"两个世界之间"——
助手出的是**回复文本里的 JSON**、幽灵预览是 **WebGL 渲染**、落库是 **HTTP**、
导出是**逐帧截图回传**。单测只能钉住纯函数（`assistantFlow` / `operations`），
钉不住"点了发送之后到底发生了什么"。项目里已经踩过"视口对了、导出不对"
（两份实现）与"相机驱动 A、渲染 B"，都是只在真机上才暴露的那一类。

**判据按"能钉死的钉死、不能钉死的如实说"**：
  - 幽灵预览 = 页面上出现「待确认草案」标签（青色确认条）；
  - 落库 = 服务端 `revision` +1 **且节点真的变了**（只 +1 但内容没变，
    是这套交互最贵的错："点了确认，存进去的却是改动前的内容"）；
  - 导出 = 拿到能解开的 ZIP 且里面 JPEG 张数 > 0；
  - 过期作废 = 后端 `preview-operations` 返回 `valid=false`，
    且界面**没有**进幽灵态（有草案标签就说明把过期方案当能落库的展示出来了）。

助手出不出 JSON 由模型决定，脚本**不伪造**它的回复：拿不到方案就如实记为
"这一轮没拿到方案（含助手原文前 200 字）"，不因此判定通过。

用法：
    set YLCRAFT_PREVIS_USER=root
    set YLCRAFT_PREVIS_PASSWORD=...
    backend\venv_win\Scripts\python.exe tools\verify_previs_copilot_live.py [--headed]

凭据只从环境变量读，**绝不落到脚本、仓库或报告里**。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
import codecs
from pathlib import Path

# Windows 控制台默认 GBK，print 任何中文/emoji 都会 UnicodeEncodeError，
# 而"脚本自己的输出崩了"会被误读成"验收失败"——先把 stdout 换成 UTF-8。
if hasattr(sys.stdout, "buffer"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")

BACKEND = os.environ.get("YLCRAFT_BACKEND", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("YLCRAFT_FRONTEND", "http://127.0.0.1:3000")

#: 验收用场景（跑完即删）。一个"桌子 + 人物 + 一个机位"的最小场景，
#: 正好对应 3.2 那句"把桌子挪到人物右侧、机位推近一点"。
SCENE_TITLE = "E2E 验收：助手改场景"

SESSION_COOKIE = ""
REPORT: list[str] = []
FAILURES = 0


def api(method: str, path: str, payload: dict | None = None) -> dict:
    """直连后端 API（带上登录后的会话 Cookie）。"""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{BACKEND}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Cookie": SESSION_COOKIE},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body[:400]}") from exc


def check(name: str, ok: bool, detail: str = "") -> bool:
    global FAILURES
    line = f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else "")
    if not ok:
        FAILURES += 1
    REPORT.append(line)
    print(line)
    return ok


def scene_payload() -> dict:
    """一个最小可验收场景：人物在原点、桌子在左侧、一个活动机位。"""
    return {
        "fps": 24,
        "durationFrames": 24,
        "activeCameraId": "camera-1",
        "nodes": [
            {
                "id": "node-hero",
                "kind": "human_proxy",
                "name": "人物",
                "locked": False,
                "visible": True,
                "metadata": {"height": 1.72, "pose": "stand"},
                "transform": {"scale": [1, 1, 1], "position": [0, 0, 0], "rotation": [0, 0, 0, 1]},
            },
            {
                "id": "node-table",
                "kind": "primitive",
                "name": "桌子",
                "locked": False,
                "visible": True,
                "metadata": {"primitive": "box", "size": [1.2, 0.75, 0.7], "color": "#8b5a2b"},
                "transform": {"scale": [1, 1, 1], "position": [-1.4, 0.375, 0], "rotation": [0, 0, 0, 1]},
            },
        ],
        "cameras": [
            {
                "id": "camera-1",
                "name": "主机位",
                "position": [0, 1.6, 4.0],
                "target": [0, 1.0, 0],
                "fov": 40,
            }
        ],
        "keyframes": [],
        "settings": {},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tmp/previs-copilot-check")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-export", action="store_true", help="跳过逐帧导出（慢）")
    args = parser.parse_args()

    username = os.environ.get("YLCRAFT_PREVIS_USER", "")
    password = os.environ.get("YLCRAFT_PREVIS_PASSWORD", "")
    if not username or not password:
        print("缺少凭据：请设置 YLCRAFT_PREVIS_USER / YLCRAFT_PREVIS_PASSWORD")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        print("patchright 不可用：请用 backend/venv_win 的 python 运行")
        return 2

    global SESSION_COOKIE, FAILURES
    scene_id = ""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=not args.headed,
            args=["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 950}, accept_downloads=True)

        # ---- 1. 登录：拿 HttpOnly 会话 Cookie ----
        page.goto(f"{FRONTEND}/login", wait_until="domcontentloaded")
        page.wait_for_selector("form", timeout=30000)
        page.fill('input[autocomplete="username"]', username)
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url(lambda url: "/login" not in str(url), timeout=30000)
        page.wait_for_timeout(1500)
        cookie = next(
            (item for item in page.context.cookies() if item["name"] == "ylcraft_session"), None
        )
        if not check("登录并拿到 HttpOnly 会话 Cookie", cookie is not None, f"落到 {page.url}"):
            browser.close()
            return 1
        SESSION_COOKIE = f"ylcraft_session={cookie['value']}"

        # ---- 2. 建一个验收用场景 ----
        created = api("POST", "/api/v1/previs/scenes", {
            "title": SCENE_TITLE, "scene": scene_payload(),
        })
        scene_id = created["data"]["id"]
        revision_before = int(created["data"]["revision"])
        check("创建验收场景", True, f"scene={scene_id} revision={revision_before}")

        # ---- 3. 打开预演台并等画布 ----
        page.goto(f"{FRONTEND}/previs?scene_id={scene_id}", wait_until="domcontentloaded")
        page.wait_for_selector("canvas", timeout=60000)
        page.wait_for_timeout(3000)
        check("预演台加载（canvas 出现）", True, page.url)

        # ---- 4. 打开助手对话栏 ----
        page.get_by_role("button", name="助手").click()
        page.wait_for_timeout(500)
        page.get_by_placeholder(re.compile("说一句")).wait_for(timeout=10000)
        check("助手对话栏可打开", True)

        # ---- 5. 说一句话，等幽灵预览 ----
        chat_calls: list[dict] = []

        def _record(response) -> None:
            if "/agent/chat" not in response.url:
                return
            try:
                chat_calls.append(response.json())
            except Exception:  # noqa: BLE001
                pass

        page.on("response", _record)
        textarea = page.get_by_placeholder(re.compile("说一句"))
        textarea.fill("把桌子挪到人物右侧、机位推近一点")
        page.keyboard.press("Enter")

        draft_shown = False
        preview_payload = {}
        try:
            page.get_by_text("待确认草案").wait_for(timeout=420000)
            draft_shown = True
        except Exception:
            draft_shown = False

        if draft_shown:
            check("助手方案 → 幽灵预览（出现「待确认草案」）", True)
            # 幽灵态下才有的确认按钮
            confirm = page.get_by_role("button", name="确认并保存")
            check("幽灵态提供「确认并保存」", confirm.count() > 0)
            # ---- 6. 确认落库 ----
            confirm.first.click()
            page.wait_for_timeout(4000)
            latest = api("GET", f"/api/v1/previs/scenes/{scene_id}")["data"]
            revision_after = int(latest["revision"])
            nodes_after = (latest.get("scene") or {}).get("nodes") or []
            changed = json.dumps(nodes_after, sort_keys=True, ensure_ascii=False) != json.dumps(
                scene_payload()["nodes"], sort_keys=True, ensure_ascii=False
            )
            check("确认后 revision +1", revision_after == revision_before + 1,
                  f"{revision_before} → {revision_after}")
            check("落库内容真的变了（不是存了旧内容）", changed,
                  f"{len(nodes_after)} 个节点")
            check("幽灵态已退出（不再显示待确认草案）",
                  page.get_by_text("待确认草案").count() == 0)
        else:
            # 助手这轮没给出方案：如实记录，不判定通过
            replies = [str(item.get("reply") or "") for item in chat_calls]
            body = "\n\n----\n\n".join(replies) or page.inner_text("body")[:2000]
            check("助手方案 → 幽灵预览（出现「待确认草案」）", False,
                  "本轮没拿到方案（模型回复未含 operations JSON）")
            REPORT.append("（助手回复摘录）" + body.replace("\n", " | ")[:600])
            (out / "assistant-reply.txt").write_text(body, encoding="utf-8")
            (out / "agent-chat.json").write_text(
                json.dumps(chat_calls, ensure_ascii=False, indent=2), encoding="utf-8")
            print("（助手原文已写入）" + str(out / "assistant-reply.txt"))

        # ---- 7. revision 过期：整批作废 ----
        # 在"别的会话"里改一次场景，让浏览器里那份过期
        if draft_shown:
            # 先让页面回到非幽灵态（已确认），再制造并发改动
            stale_revision = int(api("GET", f"/api/v1/previs/scenes/{scene_id}")["data"]["revision"])
        else:
            stale_revision = revision_before
        current = api("GET", f"/api/v1/previs/scenes/{scene_id}")["data"]
        api("PUT", f"/api/v1/previs/scenes/{scene_id}", {
            "expected_revision": int(current["revision"]),
            "title": current["title"],
            "scene": current["scene"],
        })
        bumped = int(api("GET", f"/api/v1/previs/scenes/{scene_id}")["data"]["revision"])
        check("另一会话改动场景（制造 revision 过期）", bumped > stale_revision,
              f"{stale_revision} → {bumped}")

        # 直接问后端：拿旧 revision 提请方案必须整批作废
        stale = api("POST", f"/api/v1/previs/scenes/{scene_id}/preview-operations", {
            "operations": [{
                "type": "update_transform",
                "targetId": "node-table",
                "payload": {"position": [1.4, 0.375, 0]},
            }],
            "expected_revision": stale_revision,
        })["data"]
        reasons = [str(item.get("reason") or "") for item in (stale.get("rejected") or [])]
        check("过期方案被判为无效（valid=false）", stale.get("valid") is False,
              f"accepted={stale.get('accepted_count')}")
        check("过期方案不给 proposed_scene（不让人以为能落库）",
              stale.get("proposed_scene") is None)
        check("拒绝原因能看出是版本过期",
              any(re.search(r"版本|revision|过期", item) for item in reasons),
              " / ".join(reasons[:2]) or "(无原因)")

        # 浏览器侧：让**页面手里的那份**变成过期，再提一次。
        #
        # 不能在这里 reload：reload 会把最新 revision 拉回来，页面就"不过期"了，
        # 于是助手方案合法、幽灵态正常出现——那是**正确行为**，却会被这条检查误判成失败
        # （之前就是这么误报的）。正确做法是保持页面停在确认后的 revision，
        # 由"另一个会话"从后端把它顶掉，页面下一次提交就带着旧 revision。
        page.wait_for_timeout(500)
        box = page.get_by_placeholder(re.compile("说一句"))
        box.fill("把桌子再往右挪一点")
        page.keyboard.press("Enter")
        # 等助手这一轮跑完（真调 LLM + 工具，实测几十秒起）
        page.wait_for_timeout(90000)
        notice = ""
        try:
            notice = page.locator(".ant-alert").first.inner_text(timeout=5000)
        except Exception:
            notice = ""
        still_draft = page.get_by_text("待确认草案").count() > 0
        # 助手这一轮**没给方案**是允许的（模型行为，不是缺陷）：那就没有"过期方案"可谈，
        # 如实记为跳过，而不是把"它这次没提方案"算成过期逻辑失败。
        gave_plan = bool(notice) or still_draft
        if gave_plan:
            check("过期方案不进幽灵态", not still_draft, notice[:160])
            check("页面给出了可读的过期提示",
                  bool(re.search(r"版本|revision|过期|重新载入", notice)),
                  notice[:160] or "(没有提示)")
        else:
            REPORT.append("（跳过）浏览器侧过期复验：助手这一轮没有给出方案，"
                          "过期整批作废已由后端断言覆盖")
            print(REPORT[-1])

        # ---- 8. 导出参考帧 ----
        if not args.skip_export:
            try:
                page.get_by_role("button", name="活动机位").click()
                page.wait_for_timeout(1500)
                page.get_by_role("button", name="导出").click()
                page.wait_for_timeout(1200)
                with page.expect_download(timeout=180000) as download_info:
                    page.get_by_role("button", name="导出参考帧 ZIP").click()
                download = download_info.value
                target = out / "previs-frames.zip"
                download.save_as(str(target))
                with zipfile.ZipFile(target) as archive:
                    frames = [n for n in archive.namelist() if n.lower().endswith((".jpg", ".jpeg"))]
                    size = sum(archive.getinfo(n).file_size for n in frames)
                check("导出参考帧 ZIP", len(frames) > 0, f"{len(frames)} 张 / {size // 1024} KB")
            except Exception as exc:  # noqa: BLE001
                check("导出参考帧 ZIP", False, str(exc)[:200])

        browser.close()

    # ---- 9. 清理验收场景 ----
    if scene_id:
        try:
            req = urllib.request.Request(
                f"{BACKEND}/api/v1/previs/scenes/{scene_id}",
                method="DELETE",
                headers={"Cookie": SESSION_COOKIE},
            )
            urllib.request.urlopen(req, timeout=30).read()
            REPORT.append(f"清理：验收场景 {scene_id} 已删除")
        except Exception as exc:  # noqa: BLE001
            REPORT.append(f"清理失败（需手动删场景 {scene_id}）：{exc}")
    print(REPORT[-1])

    (out / "report.txt").write_text("\n".join(REPORT) + "\n", encoding="utf-8")
    print(f"\n报告：{out / 'report.txt'}")
    print(f"结论：{'全部通过' if FAILURES == 0 else f'{FAILURES} 项未通过'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
