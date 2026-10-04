# -*- coding: utf-8 -*-
"""前端不能把「取不到」显示成「本来就没有」。

## 起因（2026-10-04）

后端修好了 YouTube 人机校验的消息（保尾，处置办法在最后一行），
但**前端又把内容切掉了**：`String(detail).slice(0, 90)`。
后端 382 字符 → 前端只显示 90 字符，里面**没有一句能照做的**：

    [youtube] 取评论被 YouTube 人机校验拦截（视频 njK0eebUsQw）。
    这不是「视频不存在」，也不是「必须登录才能看」——同一 IP 下其它视频能正常取评论（
    ↑ 断在这；「可行的办法：等待 / 更换出口 IP / …」全没了

更糟的是第二层：429 时 `comments` 是 `[]`，于是下面那个
「暂无评论」会**照常渲染** —— 面板写着"平台侧拒绝"，
下面又写"暂无评论"，等于告诉用户"这条视频没有评论"。
那正是本仓库最忌讳的**把失败伪装成"本来就没有"**
（与当年快手搜索静默返回空是同一个病）。

本组测试锁三件事：
  1. 前端摘要**保尾**（与后端 _brief 同一套规则）
  2. 429 走**独立面板**，不靠 toast（toast 3 秒就没了）
  3. 501/429 两种状态下都**不显示**"暂无评论"和"共 0 条评论"
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # 仓库根（不是 backend/）
FRONTEND = ROOT / "frontend"
CRAWLER = FRONTEND / "src" / "pages" / "crawler" / "index.tsx"
SRC = CRAWLER.read_text(encoding="utf-8")

# 真实后端返回的 detail（2026-10-04 实测，382 字符）
REAL_DETAIL = (
    "[youtube] 取评论被 YouTube 人机校验拦截（视频 njK0eebUsQw）。\n"
    "这不是「视频不存在」，也不是「必须登录才能看」——"
    "同一 IP 下其它视频能正常取评论（2026-10-04 实测 1/8）。\n"
    "YouTube 在返回的页面里把这条视频标成了 "
    "playabilityStatus=LOGIN_REQUIRED（HTTP 200，页面本身是全的），"
    "所以是**按视频**判的，客户端侧没有开关可绕。\n"
    "已试过且无效：7 种 player_client、跳过网页直连 API、"
    "读本机浏览器 cookie、**PO Token**（bgutil 2.0.1 两种模式实测，仍失败）。\n"
    "可行的办法：等待 / 更换出口 IP / 在浏览器打开该视频完成人机校验。\n\n"
    "这是**平台侧拒绝**（风控/人机验证），可尝试稍等一会儿、换 IP，"
    "或重新获取登录态。"
)


def _ts_readable_error() -> str:
    """抠出 `readableError` 的函数体（TS 源码，用正则够用）。"""
    i = SRC.index("export function readableError")
    return SRC[i: i + 900]


class TestNoHeadTruncation(unittest.TestCase):
    """**核心**：不能再出现按头硬截。"""

    def test_no_slice_from_head_on_error_detail(self):
        """`String(detail).slice(0, N)` 出现在错误分支里就是 bug。"""
        # ⚠️ 先剥掉注释 —— 解释"为什么不能用 slice(0, 90)"的注释里
        # 必然出现这个字面量（第一版就误报了自己，第三次踩同一个坑：
        # 后端那次是"注释/docstring 里有字面量"，这里同理）。
        code = "\n".join(
            ln for ln in SRC.splitlines()
            if not ln.strip().startswith("//")
        )
        offenders = re.findall(r"String\(detail\)\.slice\(\s*0\s*,", code)
        self.assertEqual(
            [], offenders,
            "错误消息被按头截断 —— 处置办法在**尾部**，会正好被切掉。"
            f"改用 readableError()。发现：{offenders}",
        )

    def test_error_branch_uses_readable_error(self):
        self.assertIn("export function readableError", SRC,
                      "缺 readableError（与后端 _brief 同规则的保尾摘要）")
        self.assertIn("readableError(detail)", SRC,
                      "错误分支要用 readableError，不能自己 slice")

    def test_helper_keeps_tail_not_head(self):
        """**行为**：保尾。断言算法本身，不只看函数名存在。"""
        body = _ts_readable_error()
        self.assertIn("slice(-limit)", body, "摘要必须取尾部（结论在尾部）")
        self.assertNotIn(
            "text.slice(0, limit)",
            body,
            "不能从头部切 —— 那会把结论切没（就是原来的 bug）",
        )
        self.assertIn("'…\\n'", body, "截断要留痕（补 …），别让半句像完整消息")


class TestBlockedStateIsVisible(unittest.TestCase):
    """429 走独立面板，不靠 toast。"""

    def test_429_has_own_state(self):
        self.assertIn("commentBlocked", SRC, "429 需要独立状态，不能复用 501 的")

    def test_429_rendered_in_panel(self):
        self.assertIn("{commentBlocked && (", SRC,
                      "429 要在面板里渲染完整原因（toast 3 秒就没了）")
        self.assertIn("{commentBlocked}", SRC,
                      "面板要显示后端给的完整消息")

    def test_429_not_labelled_unsupported(self):
        """⚠️ 措辞：501 是"没实现"，429 是"被拒绝、等一等有救"。

        混用会让用户以为永久失效 —— 那是**错误的承诺**。
        """
        i = SRC.index("{commentBlocked && (")
        panel = SRC[i: i + 1200]
        self.assertIn("平台侧拒绝", panel)
        self.assertNotIn(
            "暂不支持", panel,
            "429 不能写'暂不支持'—— 那是 501（平台没实现）的说法，"
            "会误导用户以为评论功能永久没了",
        )

    def test_429_panel_has_retry(self):
        """被拦要能重试（等一会儿/换 IP 之后）。"""
        i = SRC.index("{commentBlocked && (")
        self.assertIn("重新加载", SRC[i: i + 1400])

    def test_state_cleared_on_success_and_on_open(self):
        """两处必须清：`取到评论时` 和 `打开另一条内容时`。

        漏掉"打开新内容"那处 = 上一条的"被拦"张冠李戴到下一条
        （与 commentUnsupported 当年同一个 bug）。
        """
        self.assertGreaterEqual(
            SRC.count("setCommentBlocked('')"), 3,
            "成功/切内容/其它错误分支都要清 commentBlocked",
        )


class TestFailureNotShownAsEmpty(unittest.TestCase):
    """**最关键**：取不到 ≠ 本来就没有。"""

    def test_empty_state_hidden_when_blocked(self):
        i = SRC.index("commentBlocked || commentUnsupported ? (")
        self.assertNotEqual(-1, i, "空态分支必须同时排除 501 和 429")
        seg = SRC[i: i + 200]
        self.assertIn("<div />", seg,
                      "这两种状态下渲染空 div，不显示'暂无评论'")

    def test_count_tag_hidden_when_blocked(self):
        """'共 0 条评论' 也是编数字。"""
        self.assertRegex(
            SRC,
            r"!commentUnsupported && !commentBlocked && \(\s*"
            r"<Tag color=\"orange\"",
            "评论数量 Tag 必须在 501/429 时隐藏"
            "（'共 0 条' 是没测到的数字）",
        )

    def test_send_box_hidden_when_blocked(self):
        self.assertGreaterEqual(
            SRC.count("!commentUnsupported && !commentBlocked"), 3,
            "发评论框 / 登录态提示 / 空态都要排除 429",
        )


class TestBackendFrontendRulesMatch(unittest.TestCase):
    """前端和后端必须是**同一套**规则，否则改一边就白改。"""

    def test_same_default_limit_intent(self):
        self.assertIn("readableError", SRC)
        # 后端 _brief 的默认是 600；前端这里用 220 是因为 toast/面板
        # 空间有限 —— 但**规则**（保尾 + 补 …）必须一致
        self.assertIn("limit = 220", SRC)

    def test_backend_brief_exists(self):
        p = ROOT / "backend" / "app" / "api" / "v1" / "comments.py"
        self.assertTrue(p.exists(), f"找不到 {p}")
        self.assertIn("def _brief(", p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
