# -*- coding: utf-8 -*-
"""微博搜索分页（2026-10-04 用户实测截图发现）。

## 症状

用户选「每页 10 条」搜"沈阳"→ **只显示 9 条，且底部没有翻页按钮**。

## 根因（两层，都在这一个文件里）

`search_patchright.py` 原来两处都基于"一页给 10 条"的假设：

  ① `pages_to_try = 1 if want <= 12 else ...`
     want=10 ≤ 12 → **只试第 1 页**，压根没去试第 2 页

  ② `out[0].raw_data["_has_more"] = len(out) >= want`
     微博一页给 **9~10 条不固定**，第 1 页给 9 条 → `9 >= 10` 为 False
     → `has_more=False` → **前端不给翻页**

而**第 2 页确实有内容**（用户翻页截图证实：第 2 页是"看看这阳光"等新条目）。

## 实测（改完之后，2026-10-04）

    每页 5 条  → 5 条   has_more=True    ← 取不满 → 去翻页
    每页10条  → 9 条   has_more=False
    每页20条  → 9 条   has_more=False

`每页 5 条` 那行 `has_more=True` 就是新逻辑：
不再用"条数够不够 want"猜有没有下一页，而是**记录翻页循环
是怎么退出的**（被 want 截断 vs 真的翻完了）。
"""
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.platforms.weibo import search_patchright as sp  # noqa: E402

SRC = inspect.getsource(sp.search_via_patchright)


def _code_only() -> str:
    """剥掉 docstring 与注释，只留**可执行代码**。

    ⚠️ 不剥就会匹配到我自己写的说明文字 —— 注释里正写着
    「原来：`pages_to_try = 1 if want <= 12 else ...`」来解释这次改动，
    而 `inspect.getsource` **包含注释**。
    同一个坑今天已经踩第四次（后端 docstring、TSX 块注释…），固定处理。
    """
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(SRC))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)):
        fn.body = fn.body[1:]          # 删 docstring
    return ast.unparse(fn)


class TestPagesToTryNotGatedByWant(unittest.TestCase):
    def test_small_want_still_tries_page_2(self):
        """want 小于 12 也**必须**去试第 2 页。

        原来 `1 if want <= 12` → want=10 只试 1 页 → 用户看不到翻页。
        """
        code = _code_only()
        self.assertNotIn("want <= 12", code,
                         "别再用 want<=12 决定只翻 1 页（第 2 页是有内容的）")
        # 按"一页约 9 条"反推需要几页
        self.assertIn("(want + 8) // 9", code,
                      "应按一页实际条数（约 9）反推页数")

    def test_page_size_estimate_is_9(self):
        """9 这个数是实测的（微博一页 9~10 条不固定），别随手改成 10。"""
        self.assertIn("(want + 8) // 9", _code_only(),
                      "一页按 9 条估（实测微博常给 9 条）")


class TestHasMoreUsesLoopExitReason(unittest.TestCase):
    """`has_more` 不能用"条数够不够 want"来猜。"""

    def test_stopped_by_want_flag(self):
        self.assertIn("_stopped_by_want", SRC,
                      "必须记录'是不是被 want 截断的'")

    def test_has_more_uses_flag_not_length_compare(self):
        code = _code_only()
        # ⚠️ 窗口要**只包住赋值那一句** —— 循环里那个
        # `if len(out) >= want: _stopped_by_want = True` 是**正确的**
        # （它正是"被截断"的判定），窗口太宽会把它一起捞进来。
        i = code.index("raw_data['_has_more']")
        j = code.index("\n", i)
        assign = code[i: j]
        self.assertIn("_stopped_by_want", assign,
                      "has_more 要用 _stopped_by_want，不能用 len(out) >= want")
        self.assertNotIn(">= want", assign,
                         "has_more 不能拿条数比 want（9 >= 10 那个坑）")

    def test_flag_set_only_on_want_truncation(self):
        code = _code_only()
        i = code.index("if len(out) >= want:")
        seg = code[i: i + 200]
        self.assertIn("_stopped_by_want = True", seg,
                      "只有'被 want 截断'那条退出路径要置位")


class TestPage2FailureKeepsPage1(unittest.TestCase):
    """⚠️ 这条最关键：改完"要试第 2 页"之后必须配套修这里。

    实测（访客态 / 登录态失效）：
        page=1 → ok=1   160KB 真实数据（9~10 条）
        page=2 → ok=-100  {"url":"passport.weibo.com/sso/signin"}

    原来 `ok == -100` 无条件 `raise` → 一旦开始试第 2 页，
    **每次搜索都会失败**，连本来有效的第 1 页都看不到 ——
    把"取不到更多"变成"什么都取不到"，比原来更糟。
    """

    def test_ok_minus_100_keeps_existing_results(self):
        code = _code_only()
        i = code.index("if ok == -100:")
        seg = code[i: i + 400]
        self.assertIn("if out:", seg,
                      "ok=-100 时若已有第 1 页结果，必须保留它（不能整体抛错）")
        self.assertIn("break", seg, "保留已有结果后停止翻页")

    def test_still_raises_when_nothing_at_all(self):
        """一页都没有时**仍然要报错** —— 不能静默返回空列表。"""
        code = _code_only()
        i = code.index("if ok == -100:")
        seg = code[i: i + 600]
        self.assertIn("raise RuntimeError", seg,
                      "完全没结果时必须报错（空列表会被当成'搜不到'）")


class TestDocstringNoLongerSaysOnlyOnePage(unittest.TestCase):
    def test_docstring_updated(self):
        """docstring 里那条旧结论（只取第 1 页）必须改掉。

        它是这个 bug 的**源头**：代码按它写，注释里却已有相反的实测。
        """
        doc = inspect.getdoc(sp.search_via_patchright)
        self.assertNotIn(
            "所以这里默认**只取第 1 页**", doc,
            "docstring 还在说'只取第 1 页'，而代码已经会翻页 —— "
            "留着会误导下一个人改回去",
        )
        self.assertIn("9~10", doc,
                      "docstring 要写清'一页 9~10 条不固定'（实测）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
