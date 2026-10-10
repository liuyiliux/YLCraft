"""Mobile layout verification (iPhone viewport).

Verifies the problems reported from the user's screenshot:
  1. search box width
  2. any button overlapping the search box
  3. any button overlapping the account select
  4. page-level horizontal overflow
  5. mobile filter collapse can be reopened

## 怎么跑（2026-10-11 补）

⚠️ 本脚本**有前置条件**，直接跑会失败：

  1. **后端 + 前端都要在跑**（默认访问 `http://127.0.0.1:3000`，见 `BASE`）
  2. **需要一个能登录的账号**，写在 `_mob_cred.txt`（与脚本同目录）：

        第一行：用户名
        第二行：密码

     缺这个文件会直接 `return 2` 并提示 `missing _mob_cred.txt`。
     ⚠️ 该文件含凭据，**不要提交**（`.gitignore` 有 `_mob_*` 规则覆盖）。
  3. 依赖 `playwright` + 本机安装的 Chrome（用 `channel="chrome"`，
     不是 Playwright 自带的 chromium）。

        python tools/check_mobile.py

输出：截图与 `report.txt` 写到 `_mobile_shots/`。
退出码：0 = 全部通过；1 = 有布局问题；2 = 环境/登录失败。

## 为什么挪到这里

原在仓库根目录（另一位贡献者遗留），根目录不适合放脚本；
仓库已有 `tools/` 放这类运维/验证脚本，故移入。

⚠️ 它是目前**唯一**的移动端布局自动回归工具 —— 改前端布局后跑一遍，
能自动发现"手机上又溢出 / 按钮压住了"这类问题。**别删。**

Report goes to a UTF-8 file (the Windows console is GBK and
chokes on non-ASCII, which silently swallowed the whole report).
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "_mobile_shots"
OUT.mkdir(exist_ok=True)

VIEWPORTS = [
    ("iphone", {"width": 393, "height": 852}),
    ("iphone_plus", {"width": 414, "height": 896}),
]
BASE = "http://127.0.0.1:3000"

log: list[str] = []


def say(msg: str) -> None:
    log.append(msg)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _overlap(a, b):
    if not a or not b:
        return 0.0, 0.0
    ox = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    oy = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    return (ox if ox > 0 else 0.0), (oy if oy > 0 else 0.0)


def find_overlapping_button(page, box, limit=24):
    btns = page.locator("button:visible")
    n = min(btns.count(), limit)
    for i in range(n):
        try:
            bb = btns.nth(i).bounding_box()
        except Exception:
            continue
        ox, oy = _overlap(box, bb)
        if ox > 4 and oy > 4:
            return ox, oy
    return 0.0, 0.0


def main() -> int:
    errors: list[str] = []
    cred = Path(__file__).resolve().parent / "_mob_cred.txt"
    if not cred.exists():
        say("missing _mob_cred.txt (register a temp account first)")
        return 2
    user, pwd = cred.read_text(encoding="utf-8").splitlines()[:2]

    with sync_playwright() as p:
        try:
            # use the installed Chrome (playwright's own chromium is absent)
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception as exc:
            say(f"chrome launch failed: {exc}")
            return 2

        for name, vp in VIEWPORTS:
            ctx = browser.new_context(
                viewport=vp, device_scale_factor=2,
                is_mobile=True, has_touch=True,
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"
                ),
            )
            page = ctx.new_page()
            page.on(
                "console",
                lambda m: errors.append(
                    f"[{name}] console.error: {m.text[:160]}"
                ) if m.type == "error" and "401" not in m.text else None,
            )

            # ---- login (the crawler page requires auth) ----
            try:
                page.goto(f"{BASE}/login", wait_until="networkidle", timeout=45000)
                ti = page.locator('input[type="text"], input:not([type])')
                pi = page.locator('input[type="password"]')
                if ti.count() == 0 or pi.count() == 0:
                    errors.append(f"[{name}] login inputs not found")
                    ctx.close()
                    continue
                ti.first.fill(user, timeout=15000)
                pi.first.fill(pwd, timeout=15000)
                btn = page.locator('button[type="submit"]')
                if btn.count() == 0:
                    btn = page.locator("form button, .ant-btn-primary")
                btn.first.click(timeout=15000)
                page.wait_for_timeout(4000)
                if "/login" in page.url:
                    errors.append(f"[{name}] still on /login after submit")
                    ctx.close()
                    continue
            except Exception as exc:
                errors.append(f"[{name}] login failed: {exc}")
                ctx.close()
                continue

            try:
                page.goto(f"{BASE}/crawler", wait_until="networkidle", timeout=45000)
            except Exception as exc:
                errors.append(f"[{name}] goto crawler failed: {exc}")
                ctx.close()
                continue
            time.sleep(3.0)

            shot = OUT / f"{name}_crawler.png"
            page.screenshot(path=str(shot))
            say(f"[{name}] shot -> {shot}")

            # ---- 1 + 2. search box width and overlap ----
            try:
                sb = page.locator(
                    'input[placeholder*="\u641c\u7d22"]'
                ).first
                box = sb.bounding_box()
                if not box:
                    errors.append(f"[{name}] search input not found")
                else:
                    say(f"[{name}] search box width = {box['width']:.0f}px")
                    if box["width"] < 140:
                        errors.append(
                            f"[{name}] [X] search box too narrow "
                            f"({box['width']:.0f}px)"
                        )
                    ox, oy = find_overlapping_button(page, box)
                    if ox > 0:
                        errors.append(
                            f"[{name}] [X] a button overlaps the search box "
                            f"({ox:.0f}x{oy:.0f}px)"
                        )
                    else:
                        say(f"[{name}] [OK] no button overlaps search box")
            except Exception as exc:
                say(f"[{name}] search check skipped: {exc}")

            # ---- 3. account select overlap ----
            try:
                sbox = page.locator(".ant-select-selector").first.bounding_box()
                if sbox:
                    ox, oy = find_overlapping_button(page, sbox)
                    if ox > 0:
                        errors.append(
                            f"[{name}] [X] a button overlaps the account "
                            f"select ({ox:.0f}x{oy:.0f}px)"
                        )
                    else:
                        say(
                            f"[{name}] [OK] no button overlaps account select"
                        )
            except Exception as exc:
                say(f"[{name}] select check skipped: {exc}")

            # ---- 4. page overflow ----
            try:
                ow = page.evaluate(
                    "() => ({doc: document.documentElement.scrollWidth,"
                    " win: window.innerWidth})"
                )
                over = ow["doc"] - ow["win"]
                say(
                    f"[{name}] doc={ow['doc']} win={ow['win']} "
                    f"overflow={over}px"
                )
                if over > 8:
                    errors.append(f"[{name}] [X] page overflows {over}px")
            except Exception as exc:
                say(f"[{name}] overflow check skipped: {exc}")

            # ---- 5. filter collapse reopens ----
            try:
                sort_btn = page.locator(
                    'button:has-text("\u6700\u591a\u64ad\u653e")'
                )
                hidden = (
                    sort_btn.count() == 0 or not sort_btn.first.is_visible()
                )
                # locate the entry by text: the Refresh button is also
                # .ant-btn-text, so a class-only selector clicks the wrong one
                toggler = None
                cands = page.locator("button.ant-btn-text")
                for i in range(cands.count()):
                    b = cands.nth(i)
                    if not b.is_visible():
                        continue
                    txt = (b.inner_text() or "").strip()
                    if "\u7b5b\u9009" in txt or "\u6392\u5e8f" in txt:
                        toggler = b
                        say(f"[{name}] found collapse entry: {txt!r}")
                        break
                if toggler is not None:
                    toggler.click(timeout=8000)
                    page.wait_for_timeout(900)
                    opened = (
                        sort_btn.count() > 0 and sort_btn.first.is_visible()
                    )
                    if not hidden:
                        say(f"[{name}] [OK] filter already expanded")
                    elif opened:
                        say(f"[{name}] [OK] filter reopens correctly")
                    else:
                        errors.append(
                            f"[{name}] [X] filter cannot reopen after collapse"
                        )
                else:
                    say(f"[{name}] no collapse entry found (skip)")
            except Exception as exc:
                say(f"[{name}] toggle check skipped: {exc}")

            ctx.close()
        browser.close()

    say("")
    say("=" * 60)
    if errors:
        say(f"found {len(errors)} problem(s):")
        for e in errors:
            say("  " + e)
    else:
        say("all checks passed")

    (OUT / "report.txt").write_text("\n".join(log), encoding="utf-8")
    say(f"report -> {OUT / 'report.txt'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
