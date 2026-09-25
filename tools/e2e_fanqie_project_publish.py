"""任务 32 真实联调：建项目 → 生成 novel_body → 绑定番茄 → 自动建草稿 → 发布 → 核对记录。

⚠️ 这是一个**真实写入**脚本：会在真实番茄账号的《测试啊》草稿箱里新增一条草稿并写入正文。
   绝不写入《短剧世界不准我降智》（已完结书），脚本内有硬断言拦截。

关于 novel_body 的来源：`POST /{project_id}/generate-novel-body` 需要先有
故事大纲 + 章节规划 + 单话细纲，并且会真实调用大模型。联调关注的是**发布链路**
而不是模型质量，所以本脚本直接把一段固定正文写进 `project_contents`，
让链路可离线、可重复地跑通。

用法：
    python tools/e2e_fanqie_project_publish.py --port 8024
    python tools/e2e_fanqie_project_publish.py --port 8024 --cleanup   # 跑完删掉联调项目
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BOOK_ID = "7689461729293503512"      # 《测试啊》
VOLUME_ID = "7689461731638119448"    # 第一卷：默认
VOLUME_NAME = "第一卷：默认"
CONN_ID = "3eb9f3d4-22a2-49ef-a453-3dd764aaced3"
FORBIDDEN_BOOK = "7669027234765622296"   # 《短剧世界不准我降智》已完结，绝不碰

MARKER = "[YLCraft E2E]"
BODY = f"""{MARKER} 任务32 全链路联调

夜色压下来的时候，程岸才意识到自己把最后一张回程票撕了。
站台的灯管闪了两下，像谁在犹豫要不要说实话。

他数着铁轨，一、二、三——数到第七根的时候，风里裹来一声很轻的咳嗽。
不是他的。也不该在这里。

"你等的人不会来。"那声音说，"但你可以等一个别的。"

程岸没有回头。他只是把手插进口袋，摸到那张被汗水浸软的纸条，
上面写着一行早已模糊的字。

"那我等什么？"

"等你愿意承认，你来这里不是为了走。"

灯管彻底灭了。黑暗里，他听见自己说了一个字。

——好。
"""


_AUTH: dict[str, str] = {}


def call(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in _AUTH.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:400]}


def _unwrap(res: dict) -> dict:
    d = res.get("data")
    return d if isinstance(d, dict) else res


def main() -> int:
    # Windows 控制台默认 GBK，直接 print ✅ 会 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="8024")
    ap.add_argument("--base", default="")
    ap.add_argument("--cleanup", action="store_true", help="跑完删除联调项目")
    args = ap.parse_args()
    base = args.base or f"http://localhost:{args.port}"
    api = f"{base}/api/v1"

    failures: list[str] = []

    def step(n: str, ok: bool, detail: str = "") -> None:
        print(f"[{n}] {'✅' if ok else '❌'} {detail}")
        if not ok:
            failures.append(n)

    # --- 0) 服务存活
    code, _ = call("GET", f"{api}/platforms")
    step("0 服务存活", code == 200, f"GET /platforms -> {code}")
    if code != 200:
        return 1

    # --- 0b) 认证：优先用环境变量里的 Key，否则临时签发一个（跑完撤销）
    token = os.environ.get("YLCRAFT_API_KEY", "")
    temp_key_id = ""
    if not token:
        code, res = call("POST", f"{api}/external-api-keys",
                         {"name": "e2e-fanqie-task32", "scope": "write"})
        token = res.get("api_key", "")
        temp_key_id = ((res.get("data") or {}) or {}).get("id", "")
        step("0b 临时签发 API Key", bool(token), f"{code} key_prefix={token[:8]}...")
    else:
        step("0b 使用环境变量 API Key", True, f"prefix={token[:8]}...")
    if not token:
        return 1
    _AUTH["Authorization"] = f"Bearer {token}"

    # --- 1) 建项目
    code, res = call("POST", f"{api}/creative-projects", {
        "title": f"{MARKER} 联调项目",
        "idea": "任务32 全链路联调（可删）",
        "project_type": "novel",
        "source_type": "original_idea",
    })
    project_id = _unwrap(res).get("id")
    step("1 建项目", code in (200, 201) and bool(project_id),
         f"{code} project_id={project_id}")
    if not project_id:
        print("   resp:", json.dumps(res, ensure_ascii=False)[:400])
        return 1

    # --- 2) 写入 novel_body（直连 DB，绕开需要大模型的生成链路）
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    # app.main 会 load_dotenv；这里直连 DB 必须自己先加载，否则会退回 localhost 默认值
    from dotenv import load_dotenv                       # noqa: E402

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
    from app.db.database import SessionLocal            # noqa: E402
    from app.db.models.creative_project import ProjectContent  # noqa: E402

    session = SessionLocal()
    try:
        content = ProjectContent(
            project_id=project_id,
            content_type="novel_body",
            chapter_number=1,
            title=f"{MARKER} 第1章",
            text_content=BODY,
        )
        session.add(content)
        session.commit()
        session.refresh(content)
        content_id = content.id
    finally:
        session.close()
    step("2 写入 novel_body", bool(content_id),
         f"content_id={content_id} len={len(BODY)}")

    # --- 3) 绑定番茄
    code, res = call("POST", f"{api}/creative-projects/{project_id}/fanqie/binding", {
        "conn_id": CONN_ID, "book_id": BOOK_ID,
        "volume_id": VOLUME_ID, "volume_name": VOLUME_NAME,
    })
    code2, res2 = call("GET", f"{api}/creative-projects/{project_id}/fanqie/binding")
    binding = _unwrap(res2)
    step("3 绑定番茄", code in (200, 201) and binding.get("book_id") == BOOK_ID,
         f"{code} 回读 book_id={binding.get('book_id')} volume={binding.get('volume_id')}")

    assert BOOK_ID != FORBIDDEN_BOOK, "禁止写入已完结书籍"

    # --- 4) 自动建草稿（不必手动建章）
    q = urllib.parse.urlencode({"conn_id": CONN_ID, "confirm": "true"})
    code, res = call("POST", f"{api}/fanqie/book/{BOOK_ID}/drafts?{q}")
    item_id = _unwrap(res).get("item_id")
    step("4 自动建草稿", code == 200 and bool(item_id), f"{code} item_id={item_id}")
    if not item_id:
        print("   resp:", json.dumps(res, ensure_ascii=False)[:400])
        return 1

    # --- 5) 预检
    code, res = call("GET", f"{api}/creative-projects/{project_id}/fanqie/publish-preflight?"
                     + urllib.parse.urlencode({"content_id": content_id, "item_id": item_id}))
    pre = _unwrap(res)
    step("5 发布预检", code == 200 and pre.get("ready") is True,
         f"{code} ready={pre.get('ready')} missing={pre.get('missing')}")

    # --- 6) 发布到草稿（真实写入番茄）
    code, res = call("POST", f"{api}/creative-projects/{project_id}/publish-to-fanqie", {
        "action": "draft",
        "chapters": [{"content_id": content_id, "item_id": item_id,
                      "chapter_number": 1, "title": f"{MARKER} 第1章"}],
    })
    results = _unwrap(res).get("results") or []
    # 每项形如 {"content_id", "success", "record"|"error"}——record 是嵌套的，不是平铺
    entry = results[0] if results else {}
    rec = entry.get("record") or {}
    step("6 发布到草稿", code == 200 and entry.get("success") is True,
         f"{code} success={entry.get('success')} status={rec.get('status')} "
         f"remote_version={rec.get('remote_version')} "
         f"err={entry.get('error') or rec.get('error_message') or '-'}")
    record_id = rec.get("id")

    # --- 7) 核对 ProjectPublishRecord
    code, res = call("GET", f"{api}/creative-projects/{project_id}/fanqie/publish-status")
    rows = res.get("data")
    if rows is None:
        rows = res
    if isinstance(rows, dict):
        rows = rows.get("records") or []
    rows = rows or []
    target = next((r for r in rows if r.get("id") == record_id), rows[0] if rows else {})
    ok = (target.get("status") == "success"
          and str(target.get("item_id")) == str(item_id)
          and target.get("remote_version") is not None)
    step("7 核对发布记录", ok,
         f"{code} 共{len(rows)}条 id={target.get('id')} status={target.get('status')} "
         f"item_id={target.get('item_id')} ver={target.get('remote_version')} "
         f"book_id={target.get('book_id')}")

    print("\n===== 核对摘要 =====")
    print(json.dumps({
        "project_id": project_id,
        "content_id": content_id,
        "book_id": BOOK_ID,
        "volume_id": VOLUME_ID,
        "item_id": item_id,
        "record_id": record_id,
        "record_status": target.get("status"),
        "remote_version": target.get("remote_version"),
        "editor_url": (f"https://fanqienovel.com/main/writer/{BOOK_ID}"
                       f"/publish/{item_id}?enter_from=modifydraft"),
    }, ensure_ascii=False, indent=2))

    if args.cleanup:
        code, _ = call("DELETE", f"{api}/creative-projects/{project_id}")
        print(f"\n[cleanup] 删除联调项目 -> {code}")

    # 临时签发的 Key 用完即撤销，避免在库里留下无用凭证
    if temp_key_id:
        code, _ = call("DELETE", f"{api}/external-api-keys/{temp_key_id}")
        print(f"[cleanup] 撤销临时 API Key -> {code}")

    if failures:
        print(f"\n❌ 未通过：{failures}")
        return 1
    print("\n✅ 任务32 全链路联调通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
