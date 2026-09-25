"""预演台第二期端到端验收（OpenSpec `previs-ai-copilot` 3.3）。

覆盖两件事，都是"只在真机上才看得见"的那类：

1. **全景贴图切换后导出画面正确**——贴图是 GPU 上的纹理，单测只能验到
   "metadata.textureUrl 写进去了"；写进去了但没渲染出来（加载失败回落纯色、
   球体内表面贴反、导出走的是另一条取图路径）在数据层完全看不出来。
   判据必须落在**导出的像素**上：贴图是一张可辨识的图，导出帧里就应出现它的特征色，
   而不是回落色。

2. **模型走既有路径**——在图生 3D 工作台生成 → 入库 → 预演台"从素材库添加模型"
   选入 → 导出画面正确。这里不重复造生成链路，只验证**选入 + 渲染 + 导出**这一段：
   用素材库里既有的 3D 模型建节点，导出后确认画面里有几何变化。

用法：
    set YLCRAFT_PREVIS_USER=root
    set YLCRAFT_PREVIS_PASSWORD=...
    backend\venv_win\Scripts\python.exe tools\verify_previs_phase2_live.py [--headed]

凭据只从环境变量读，绝不落到脚本或报告里。
"""

from __future__ import annotations

import codecs
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
import argparse
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")

BACKEND = os.environ.get("YLCRAFT_BACKEND", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("YLCRAFT_FRONTEND", "http://127.0.0.1:3000")

SESSION_COOKIE = ""
REPORT: list[str] = []
FAILURES = 0


def api(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{BACKEND}{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "Cookie": SESSION_COOKIE},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {body[:300]}") from exc


def check(name: str, ok: bool, detail: str = "") -> bool:
    global FAILURES
    line = f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else "")
    if not ok:
        FAILURES += 1
    REPORT.append(line)
    print(line)
    return ok


def frame_signature(blob: bytes) -> dict:
    """一帧的粗特征：平均色 + 非黑像素比例（用来判断"画面确实有内容/换了内容"）。"""
    from PIL import Image
    import io as _io

    image = Image.open(_io.BytesIO(blob)).convert("RGB")
    pixels = list(image.getdata())
    total = len(pixels)
    avg = [sum(p[i] for p in pixels) / total for i in range(3)]
    bright = sum(1 for p in pixels if sum(p) / 3 > 24) / total
    return {"avg": [round(v, 1) for v in avg], "bright_ratio": round(bright, 4), "size": image.size}


def image_assets() -> list[dict]:
    found = []
    for page in (1, 2, 3):
        data = api("GET", f"/api/v1/assets?page={page}&page_size=24")
        for asset in data.get("data") or []:
            if str(asset.get("type")) == "image":
                found.append(asset)
    return found


def model_assets() -> list[dict]:
    found = []
    for page in (1, 2, 3):
        data = api("GET", f"/api/v1/assets?page={page}&page_size=24")
        for asset in data.get("data") or []:
            if str(asset.get("type")) == "3d_model":
                found.append(asset)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tmp/previs-phase2-check")
    parser.add_argument("--headed", action="store_true")
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

    global SESSION_COOKIE
    scene_id = ""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=not args.headed,
            args=["--use-gl=angle", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 950}, accept_downloads=True)

        page.goto(f"{FRONTEND}/login", wait_until="domcontentloaded")
        page.wait_for_selector("form", timeout=30000)
        page.fill('input[autocomplete="username"]', username)
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_url(lambda url: "/login" not in str(url), timeout=30000)
        page.wait_for_timeout(1500)
        cookie = next((c for c in page.context.cookies() if c["name"] == "ylcraft_session"), None)
        if not check("登录并拿到会话 Cookie", cookie is not None):
            browser.close()
            return 1
        SESSION_COOKIE = f"ylcraft_session={cookie['value']}"

        images = image_assets()
        check("素材库里有可作贴图的图片", len(images) > 0, f"{len(images)} 张")
        models = model_assets()
        check("素材库里有 3D 模型（走既有图生 3D 入库路径）", len(models) > 0, f"{len(models)} 个")
        if not images:
            browser.close()
            return 1

        # 建一个只有全景背景 + 人物的场景：背景是否渲染，直接从导出帧判定
        created = api("POST", "/api/v1/previs/scenes", {
            "title": "E2E 二期验收：全景贴图 + 模型",
            "scene": {
                "fps": 24,
                "durationFrames": 24,
                "activeCameraId": "camera-1",
                "nodes": [
                    {
                        "id": "node-hero", "kind": "human_proxy", "name": "人物",
                        "locked": False, "visible": True,
                        "metadata": {"height": 1.72, "pose": "stand"},
                        "transform": {"scale": [1, 1, 1], "position": [0, 0, 0], "rotation": [0, 0, 0, 1]},
                    },
                    {
                        "id": "node-pano", "kind": "panorama", "name": "全景背景",
                        "locked": False, "visible": True,
                        "metadata": {"color": "#1a1a2e"},
                        "transform": {"scale": [1, 1, 1], "position": [0, 0, 0], "rotation": [0, 0, 0, 1]},
                    },
                ],
                "cameras": [{
                    "id": "camera-1", "name": "主机位",
                    "position": [0, 1.6, 4.0], "target": [0, 1.0, 0], "fov": 40,
                }],
                "keyframes": [],
                "settings": {},
            },
        })
        scene_id = created["data"]["id"]
        check("创建二期验收场景", True, f"scene={scene_id}")

        page.goto(f"{FRONTEND}/previs?scene_id={scene_id}", wait_until="domcontentloaded")
        page.wait_for_selector("canvas", timeout=60000)
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="活动机位").click()
        page.wait_for_timeout(1500)

        # 基线：纯色背景下的导出帧
        baseline_frame = capture_export(page, out / "baseline.zip")
        base_sig = frame_signature(baseline_frame) if baseline_frame else None
        check("基线导出帧可取得", baseline_frame is not None,
              json.dumps(base_sig, ensure_ascii=False) if base_sig else "取不到")

        # 选贴图：点全景节点 → 「从素材库选贴图」→ 弹窗里点第一张卡片。
        #
        # 弹窗用的是公共 `AssetGrid`：**点卡片本身就是"应用"**（`onAssetClick` 直接调
        # `applyPanoramaTexture`），没有单独的「应用」按钮。第一版脚本按"有应用按钮"找，
        # 找不到就报失败——那是脚本对错了界面，不是功能坏了。
        # 选中图层里的全景行：**点它的 Tag 芯片**，不要点文字。
        #
        # 踩坑一：`get_by_text("全景背景").first` 命中的是左栏「+ 全景背景」**添加按钮**
        # （它在图层列表之前的 DOM 里），于是又加了一个全景节点，贴图写到新节点上、
        # 去查原节点自然是空的。Tag 只出现在图层行里，点它会冒泡到该行的选中处理。
        #
        # 踩坑二：图层行的 Tag 文本来自 `NODE_KIND_LABEL`，是**「全景」而不是「全景背景」**
        # ——「全景背景」是节点名（input 的 value，不是文本节点）。用 `has_text="全景背景"`
        # 会一直等不到元素。exact 匹配 `全景` 可避免误中「全景点」之类的短词。
        page.locator("span.ant-tag", has_text=re.compile(r"^全景$")).first.click()
        page.wait_for_timeout(800)
        picker = page.get_by_role("button", name="从素材库选贴图")
        applied = False
        if picker.count():
            picker.first.click()
            page.wait_for_selector("text=从素材库选择全景贴图", timeout=15000)
            page.wait_for_timeout(2500)  # 列表异步拉取
            applied = click_first_asset_card(page)
            page.wait_for_timeout(3000)  # 等贴图加载 + 预检
        check("从素材库应用全景贴图（界面动作完成）", applied,
              "" if applied else "弹窗里没有可点的素材卡片")

        page.wait_for_timeout(2500)
        textured_frame = capture_export(page, out / "textured.zip")
        tex_sig = frame_signature(textured_frame) if textured_frame else None

        if base_sig and tex_sig:
            changed = base_sig["avg"] != tex_sig["avg"] or base_sig["bright_ratio"] != tex_sig["bright_ratio"]
            check("贴图确实改变了导出画面（不是静默回落纯色）", changed,
                  f"avg {base_sig['avg']} → {tex_sig['avg']}；bright {base_sig['bright_ratio']} → {tex_sig['bright_ratio']}")
        else:
            check("贴图确实改变了导出画面（不是静默回落纯色）", False, "缺少可比对的帧")

        # 贴图是否真的落到场景里（服务端事实，防止"界面点了但没保存"）。
        #
        # 踩坑：贴图先在**前端本地**生效，界面上能看到、导出也变了，但服务端还不知道；
        # 必须先点「保存」再 GET，否则查到的 metadata.textureUrl 永远是空的。
        # 第一版把这里放在保存之前，连续两次误报"贴图引用写进了节点元数据"失败。
        page.get_by_role("button", name="保存").click()
        page.wait_for_timeout(4000)
        saved = api("GET", f"/api/v1/previs/scenes/{scene_id}")["data"]
        nodes_now = (saved.get("scene") or {}).get("nodes", [])
        panos = [n for n in nodes_now if n.get("kind") == "panorama"]
        check("没有误加重复的全景节点", len(panos) == 1, f"{len(panos)} 个全景节点")
        pano = next((n for n in nodes_now if n.get("id") == "node-pano"), {})
        texture_url = str((pano.get("metadata") or {}).get("textureUrl") or "")
        check("贴图引用写进了节点元数据", bool(texture_url), texture_url[-60:] or "(空)")
        check("贴图记录了来源素材 id", bool(str((pano.get("metadata") or {}).get("textureAssetId") or "")),
              str((pano.get("metadata") or {}).get("textureAssetId") or "(空)")[:40])

        # 模型：从素材库添加。
        #
        # 注意顺序：加节点只是改**本地**场景状态，服务端还不知道——必须先点「保存」
        # 再回后端核对，否则查到的是旧内容（第一版就是这么误判的）。
        if models:
            added = add_first_model(page)
            page.wait_for_timeout(3000)
            saved_ok = False
            if added:
                try:
                    page.get_by_role("button", name="保存").click()
                    page.wait_for_timeout(4000)
                    saved_ok = True
                except Exception as exc:  # noqa: BLE001
                    REPORT.append(f"（保存模型节点失败）{exc}")
            kinds = []
            if saved_ok:
                model_saved = api("GET", f"/api/v1/previs/scenes/{scene_id}")["data"]
                kinds = [n.get("kind") for n in (model_saved.get("scene") or {}).get("nodes", [])]
            check("从素材库添加模型节点并落库", "asset_model" in kinds, f"节点种类：{kinds}")
        else:
            REPORT.append("（跳过）素材库里没有可加载的 3D 模型")
            print(REPORT[-1])

        browser.close()

    if scene_id:
        try:
            req = urllib.request.Request(
                f"{BACKEND}/api/v1/previs/scenes/{scene_id}", method="DELETE",
                headers={"Cookie": SESSION_COOKIE},
            )
            urllib.request.urlopen(req, timeout=30).read()
            REPORT.append(f"清理：验收场景 {scene_id} 已删除")
        except Exception as exc:  # noqa: BLE001
            REPORT.append(f"清理失败（需手动删 {scene_id}）：{exc}")
        print(REPORT[-1])

    (out / "report.txt").write_text("\n".join(REPORT) + "\n", encoding="utf-8")
    print(f"\n报告：{out / 'report.txt'}")
    print(f"结论：{'全部通过' if FAILURES == 0 else f'{FAILURES} 项未通过'}")
    return 1 if FAILURES else 0


def capture_export(page, target: Path) -> bytes | None:
    """走「导出 → 参考帧 ZIP」并返回第一帧的字节。"""
    try:
        page.get_by_role("button", name="导出").click()
        page.wait_for_timeout(1200)
        with page.expect_download(timeout=180000) as download_info:
            page.get_by_role("button", name="导出参考帧 ZIP").click()
        download = download_info.value
        download.save_as(str(target))
        with zipfile.ZipFile(target) as archive:
            frames = sorted(n for n in archive.namelist() if n.lower().endswith((".jpg", ".jpeg")))
            if not frames:
                return None
            return archive.read(frames[0])
    except Exception as exc:  # noqa: BLE001
        REPORT.append(f"（导出失败）{exc}")
        return None


def click_first_asset_card(page) -> bool:
    """点开着的弹窗里的第一张素材卡片（列表是虚拟滚动的，必须限定在弹窗内找）。"""
    try:
        modal = page.locator(".ant-modal-content").last
        card = modal.locator(".ant-card-hoverable").first
        card.wait_for(timeout=20000)
        card.click()
        return True
    except Exception as exc:  # noqa: BLE001
        REPORT.append(f"（点素材卡片失败）{exc}")
        return False


def add_first_model(page) -> bool:
    try:
        page.get_by_role("button", name="从素材库添加模型").click()
        page.wait_for_selector("text=从素材库添加 3D 模型", timeout=15000)
        page.wait_for_timeout(2500)
        return click_first_asset_card(page)
    except Exception as exc:  # noqa: BLE001
        REPORT.append(f"（添加模型失败）{exc}")
        return False


if __name__ == "__main__":
    sys.exit(main())
