# -*- coding: utf-8 -*-
"""微博搜索能取多少（2026-10-04 实测三次，数据有矛盾，如实记录）。

## 实测过程

**A. `page=2` 拿不到东西**（今天多次）
    page=1/max=10 → 10 条      page=2/max=10 → **0 条**
    page=3/max=10 → 0 条

**B. 给多少由 `max_results` 决定，不是 `page`**
    page=1/max=20 → 营口 14 / 沈阳 10
    page=1/max=100 → 同样（平台有上限）

**C. `since_id` 游标自己翻 → 不稳定，实测反而变少**
    营口   5 / 10 / 15 / **14**   ← 调到 30 条反而少 1 条
    沈阳   5 / 10 / **9** / **9** ← 调到 20 条反而少 1 条
    美食   5 / 10 / 10 / 10       （唯一正常的）

**D. 只取第 1 页但内部按 want 循环游标 → 同样出现 C 的回退**

⇒ 只能可靠地取第 1 页。想要更多，上层用**更大的 `max_results` 重搜**
（前端「加载更多」那条路，与抖音同款）。

## ⚠️ 与 `meta.py` 的 `weibo → PAGED` 矛盾

那条记录基于 2026-10-03 的实测（p2 有 17~20 条），今天测不出来。
**原因未定**（登录态？微博侧变更？时段？）。

本组测试的立场：**不假装能翻**。宁可少给，不给一个"点了没反应"的翻页按钮。
"""
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.platforms.weibo import search_patchright as sp  # noqa: E402
from app.services.platforms.weibo.apis import build_search_params  # noqa: E402

SRC = inspect.getsource(sp.search_via_patchright)


def _code() -> str:
    """剥掉 docstring + 注释，只留可执行代码。

    ⚠️ 不剥会匹配到我自己写的说明文字（"原来这里用 page+i…"）。
    同一个坑今天第 6 次了，固定处理。
    """
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(SRC))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)):
        fn.body = fn.body[1:]
    return ast.unparse(fn)


class TestOnlyFirstPageIsReliable(unittest.TestCase):
    """微博搜索只能可靠取第 1 页（实测三次的结论）。"""

    def test_pages_to_try_is_one(self):
        code = _code()
        self.assertIn("pages_to_try = 1", code,
                      "只取第 1 页 —— 实测 page=2 拿不到东西，"
                      "游标翻页又会回退（调到 30 条反而变少）")

    def test_page_param_always_one(self):
        code = _code()
        # 不能是 page + i（那会让第 2 页去请求 page=2 → 恒空）
        self.assertNotIn("page=page + i", code,
                         "翻页不要再用 page+i（实测 page=2 恒返回 0 条）")
        self.assertIn("page=1", code, "请求页码固定 1")


class TestResultsNeverDecrease(unittest.TestCase):
    """调大"每页条数"**结果不许变少** —— 那是用户一眼能看出的 bug。"""

    def test_rollback_guard_present(self):
        code = _code()
        self.assertIn("_best", code,
                      "要记住每轮已有的条数（用于'不许变少'判断）")
        self.assertIn("out = out[:_best]", code,
                      "某轮没带来新条目时**回滚**，不能带着更少的结果返回")

    def test_guard_triggers_when_no_new_items(self):
        code = _code()
        i = code.index("if len(out) <= _best:")
        self.assertIn("break", code[i: i + 260],
                      "发现没新条目要停止翻页（继续翻只会更糟）")


class TestBuildParamsSinceId(unittest.TestCase):
    """`build_search_params` 要支持 `since_id`（虽然当前只取 1 页，
    但参数留着 —— 万一微博恢复页码翻页，不用再改函数签名）。"""

    def test_accepts_since_id(self):
        a = build_search_params("营口", page=1)
        self.assertNotIn("since_id", a, "没传就不该出现这个键")

        b = build_search_params("营口", page=1, since_id="5350422397062979")
        self.assertEqual("5350422397062979", b["since_id"])

    def test_empty_since_id_omitted(self):
        for bad in (None, "", "0", 0):
            p = build_search_params("x", page=1, since_id=bad)
            self.assertNotIn("since_id", p, f"since_id={bad!r} 时不该下发")

    def test_containerid_unchanged(self):
        """⚠️ 关键词是**拼在 containerid 里**的，不是独立 q 参数
        —— 改这个函数时最容易写错（已写错过一次）。"""
        p = build_search_params("沈阳", page=2)
        self.assertIn("q=沈阳", p["containerid"])


class TestDocstringRecordsContradiction(unittest.TestCase):
    """矛盾的数据必须**留在文档里**，不能挑一个信。"""

    def test_contradiction_is_written_down(self):
        doc = inspect.getdoc(sp.search_via_patchright)
        self.assertIn("0 条", doc,
                      "要写明 page=2 实测返回 0 条")
        self.assertIn("矛盾", doc,
                      "要写明与 meta.py 的 PAGED 记录矛盾（原因未定）")

    def test_cursor_instability_recorded_in_code(self):
        """游标翻页"反而变少"这条记在**代码注释**里（docstring 没重复）。

        它是"为什么 `pages_to_try = 1`"的直接依据 ——
        将来有人想改回翻页，必须先看到这条。
        """
        # ⚠️ 用 `SRC`（含注释）而不是剥干净的代码 —— 这条**就是要**留痕的
        self.assertIn("变少", SRC,
                      "要写明游标翻页会出现'调大反而变少'")
        self.assertIn("重叠", SRC,
                      "要写明原因（游标页与第1页重叠）")


class TestNoFakePagedClaim(unittest.TestCase):
    """不得宣称能翻页 —— 宁可少给。"""

    def test_does_not_claim_paged(self):
        code = _code()
        # pages_to_try 恒为 1 时，任何"翻到第 N 页"的逻辑都是死的
        self.assertNotIn("min(2, max_pages)", code)
        self.assertNotIn("for i in range(pages_to_try)", code.split("for i in")[0][-200:],
                         "循环次数已被固定成 1，不该再有翻页意图的残留")


class TestLoginStateMustBeCheckedFirst(unittest.TestCase):
    """⚠️ **测"能不能翻页"之前必须先确认登录态**（我踩了两次）。

    ## 两次都栽在哪

    **① 手工脚本没加载 `.env`**
        `database.py:26` 的 `os.getenv("DATABASE_URL", "...localhost:5432...")`
        兜底生效 → 注入 cookie 失败 → **访客态**
        → 测出 `page=2 → ok=-100` → 我当成"平台没数据"

    **② 判据看错字段位置**
        `/api/config` 的 `login`/`uid` 在 **`data`** 里，不在顶层：

            {"data":{"login":true,"uid":"7628413874", ...}, "ok":1}
                                ↑ 在这里

        我看顶层 `cfg.get("login")` → None → 误判"未登录"

    ## 两种状态长得完全不一样

    |            | `page=2` 返回                                  |
    | ---------- | ---------------------------------------------- |
    | 访客态     | `ok=-100` + passport 登录页 URL                  |
    | 登录态     | `ok=1` + 0 条（**正常受理**，只是没内容）          |

    混在一起必然误判。
    """

    def test_check_login_snippet_reads_data_field(self):
        """登录检测必须读 `data.login`，不是顶层。"""
        snip = sp.JS_CHECK_LOGIN
        self.assertIn("api/config", snip,
                      "要用 /api/config 这个登录检测端点")

    def test_docs_record_the_two_hazards(self):
        """这两个坑必须留在文档里，否则下一个人再踩。"""
        for src, name in ((SRC, "search_patchright"),
                          (_META_SRC, "meta")):
            with self.subTest(file=name):
                self.assertIn(
                    "api/config", src,
                    "要写明登录检测用 /api/config")
                self.assertIn(
                    "data", src,
                    "要写明字段在 data 里（我因此误判过）")
                self.assertIn(
                    "访客", src,
                    "要写明访客态和登录态返回不同（ok=-100 vs ok=1）")
                self.assertIn(
                    ".env", src,
                    "要写明手工测要先加载 .env（否则是访客态）")

    def test_measured_login_state_recorded(self):
        """把实测到的登录态记下来（下次可对照）。"""
        self.assertIn("7628413874", SRC,
                      "记下实测的 uid（确认那次测的是登录态）")
        self.assertIn("login=true", SRC.replace(" ", ""),
                      "记下实测 login=true")


def _meta_src() -> str:
    p = (Path(__file__).resolve().parents[1]
         / "app" / "services" / "platforms" / "meta.py")
    return p.read_text(encoding="utf-8")


_META_SRC = _meta_src()


if __name__ == "__main__":
    unittest.main(verbosity=2)
