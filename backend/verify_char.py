"""验证角色卡注入：关键场景是「先生成大纲，之后才关联角色」——原先进不了正文。"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def req(method, path, body=None, timeout=300):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    r.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:400]}
    except Exception as e:
        return 0, {"error": "%s: %s" % (type(e).__name__, str(e)[:200])}


def payload(d):
    return d.get("data") if isinstance(d, dict) and isinstance(d.get("data"), (dict, list)) else d


def main():
    st, d = req("POST", "/api/v1/creative-projects", {"title": "E2E验证-角色注入"})
    pid = payload(d).get("id")
    print("1 create project      -> %s  %s" % (st, pid))

    st, d = req("POST", "/api/v1/creative-projects/%s/generate-outline" % pid, {})
    outline_names = [c.get("name") for c in ((payload(d) or {}).get("characters") or []) if isinstance(c, dict)]
    print("2 generate outline    -> %s  outline chars=%s" % (st, outline_names))

    # 在大纲之后才建角色并关联：这是原先角色进不了正文的场景
    st, d = req("POST", "/api/v1/characters", {
        "name": "裴惊鸿",
        "role": "protagonist",
        "appearance": "银发束冠，玄色大氅，眉心一枚朱砂印",
        "personality": "孤高寡言，护短",
        "signature_items": ["断水剑"],
        "speech": {"catchphrase": "与我无关", "tone": "冷淡讥诮"},
    })
    cid = payload(d).get("id")
    print("3 create character    -> %s  %s" % (st, cid))

    st, d = req("POST", "/api/v1/characters/%s/link-story" % cid,
                {"story_id": pid, "world_name": "E2E验证-角色注入"})
    print("4 link AFTER outline  -> %s" % st)

    st, d = req("POST", "/api/v1/creative-projects/%s/generate-chapter-plan" % pid, {})
    print("5 chapter plan        -> %s  count=%s" % (st, (payload(d) or {}).get("chapter_count")))

    st, d = req("POST", "/api/v1/creative-projects/%s/generate-chapter-outline" % pid, {"chapter_number": 1})
    co = payload(d) or {}
    print("6 chapter outline     -> %s  %s" % (st, str(co.get("title"))[:40]))
    print("       summary mentions 裴惊鸿 ? %s" % ("裴惊鸿" in str(co.get("summary") or "")))

    st, d = req("POST", "/api/v1/creative-projects/%s/generate-novel-body" % pid, {"chapter_number": 1})
    body = payload(d) or {}
    text = str(body.get("content") or "")
    print("7 novel body          -> %s  words=%d" % (st, len(text)))
    print("       mentions 裴惊鸿 ? %s" % ("YES" if "裴惊鸿" in text else "NO"))
    print("       mentions 断水剑 ? %s" % ("YES" if "断水剑" in text else "NO"))
    print("       mentions 朱砂印 ? %s" % ("YES" if "朱砂印" in text else "NO"))
    print("       head: %s" % text[:160].replace("\n", " "))
    print("")
    print("8 cleanup")
    if cid:
        st, _ = req("DELETE", "/api/v1/characters/%s" % cid)
        print("   delete character -> %s" % st)
    if pid:
        st, _ = req("DELETE", "/api/v1/creative-projects/%s" % pid)
        print("   delete project   -> %s" % st)


if __name__ == "__main__":
    main()
