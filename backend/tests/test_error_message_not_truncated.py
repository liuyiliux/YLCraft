# -*- coding: utf-8 -*-
"""错误消息给用户看之前**不能被截断掉结论**。

## 起因（2026-10-04 实测踩到）

修 YouTube 人机校验时，异常消息写得挺完整（"解释 + 已试过什么 +
可行的办法：等待 / 更换出口 IP / …"），但接口返回的是：

    HTTP 429
    …已试过且无效：7 种 player_client、…、**PO Token**（…）。
    可                                    ← 断在这里

**"可行的办法"整个被切掉了，用户只看到一个"可"。**

原因：`comments.py` 用 `str(exc)[:300]` 硬截。平台错误消息是
"解释 + 处置办法"的多行结构，**处置办法总在最后一行**，
按字数硬截正好把它切没。

## 为什么这值得单独立一组测试

这类 bug 有两个特点：
  1. **测试全绿** —— 你测的是异常本身（完整），截断发生在**出口**；
  2. **只影响用户**，不影响功能 —— 很容易长期没人发现。

所以必须测"出口"：走一遍真实 HTTP，断言**用户看得见的文本**里
该有的内容还在。
"""
import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.comments import _brief  # noqa: E402
from app.services.platforms.types import RiskControlError  # noqa: E402

BASE = "http://127.0.0.1:8000"


class TestBriefKeepsConclusion(unittest.TestCase):
    """`_brief` 的行为契约。"""

    def _long_youtube_like(self) -> str:
        return (
            "[youtube] 取评论被 YouTube 人机校验拦截（视频 njK0eebUsQw）。\n"
            "这不是「视频不存在」，也不是「必须登录才能看」——"
            "同一 IP 下其它视频能正常取评论（2026-10-04 实测 1/8）。\n"
            "YouTube 在返回的页面里把这条视频标成了 "
            "playabilityStatus=LOGIN_REQUIRED（HTTP 200，页面本身是全的），"
            "所以是**按视频**判的，客户端侧没有开关可绕。\n"
            "已试过且无效：7 种 player_client、跳过网页直连 API、"
            "读本机浏览器 cookie、**PO Token**（bgutil 2.0.1 两种模式实测，"
            "仍失败）。\n"
            "可行的办法：等待 / 更换出口 IP / 在浏览器打开该视频完成人机校验。"
        )

    def test_short_message_untouched(self):
        self.assertEqual(_brief(RiskControlError("短消息"), 300), "短消息")

    def test_conclusion_line_survives_truncation(self):
        """**核心**：处置办法那行必须活着。"""
        out = _brief(RiskControlError(self._long_youtube_like()), 300)
        self.assertIn("可行的办法", out, "处置办法被截掉了 —— 用户看不到该做什么")
        self.assertIn("更换出口 IP", out)
        self.assertIn("浏览器打开该视频", out)

    def test_marks_that_something_was_cut(self):
        """截断必须留痕，不能让半句话看起来像完整消息。"""
        out = _brief(RiskControlError(self._long_youtube_like()), 300)
        self.assertTrue(out.startswith("…"), "被截断却没有标记")

    def test_does_not_exceed_limit_much(self):
        out = _brief(RiskControlError(self._long_youtube_like()), 300)
        self.assertLessEqual(len(out), 320)

    def test_single_long_line_kept(self):
        """没有换行可切时，也要保尾（末尾通常才是关键）。"""
        msg = "A" * 200 + "关键结论在这里"
        out = _brief(RiskControlError(msg), 50)
        self.assertIn("关键结论在这里", out)
        self.assertLessEqual(len(out), 60)


class _Live:
    """真起一个后端太重，这里用 TestClient 打同一个 app。"""

    @staticmethod
    def get(path: str):
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            return c.get(path)


class TestUserVisibleMessageIsComplete(unittest.TestCase):
    """走**真实路由**，断言用户看得见的文本。"""

    def test_429_body_contains_actionable_advice(self):
        """YouTube 被人机校验拦时，响应体里必须有"怎么做"。

        ⚠️ 走**真实路由**（TestClient），不是自己拼字符串。
        第一版这个测试是"自己拼一遍 detail 再断言自己拼的东西"，
        等于什么都没测（写的时候还去 patch 一个不存在的属性）。
        截断发生在**出口**，所以必须从出口读。
        """
        long_msg = (
            "[youtube] 取评论被 YouTube 人机校验拦截（视频 njK0eebUsQw）。\n"
            "这不是「视频不存在」，也不是「必须登录才能看」——"
            "同一 IP 下其它视频能正常取评论（2026-10-04 实测 1/8）。\n"
            "YouTube 在返回的页面里把这条视频标成了 "
            "playabilityStatus=LOGIN_REQUIRED（HTTP 200），"
            "客户端侧没有开关可绕。\n"
            "已试过且无效：7 种 player_client、**PO Token**"
            "（bgutil 2.0.1 两种模式实测，仍失败）。\n"
            "可行的办法：等待 / 更换出口 IP / 在浏览器打开该视频完成人机校验。"
        )
        from app.api.v1 import comments as C

        # ⚠️ `create_client` 是**函数内部** import 的
        # （`from app.services.platforms import create_client`，见 comments.py:440），
        # 所以要 patch **源模块**，patch comments 模块属性是无效的。
        from app.services import platforms as P

        class _Boom:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get_comments_page(self, *a, **kw):
                raise RiskControlError(long_msg)

        from fastapi.testclient import TestClient
        from app.main import app

        with patch.object(P, "create_client", lambda *a, **kw: _Boom()):
            with TestClient(app) as c:
                resp = c.get(
                    "/api/v1/comments?platform=youtube&item_id=njK0eebUsQw"
                )

        self.assertIsNotNone(resp, "路由没跑起来")
        self.assertEqual(429, resp.status_code, resp.text[:300])
        detail = json.loads(resp.text)["detail"]
        # 用户看得见的文本里，处置办法必须完整
        self.assertIn("更换出口 IP", detail, f"结论被截断了：{detail!r}")
        self.assertIn("浏览器打开该视频完成人机校验", detail)
        self.assertIn("平台侧拒绝", detail)

    def test_brief_used_at_all_truncation_sites(self):
        """本文件里的截断点都要走 `_brief`，不能再有裸切片截断。

        ⚠️ 第一版这里有洞（变异测试发现的）：正则写成
        `str\\(exc\\)\\[:\\d+\\]`，只能匹配**字面量** `str(exc)[:300]`。
        于是把 `_brief(exc)` 换成 `str(exc)[:300]` 时它仍能通过 ——
        而 `_brief(exc, 200)` 那种带参数的调用匹配不上，反倒漏了。

        所以改成**结构化判定**：在 AST 里找"对 `str(exc)` 结果做切片"
        这个动作本身，不管右边写的是字面量还是变量。
        """
        import ast

        p = (Path(__file__).resolve().parents[1]
             / "app" / "api" / "v1" / "comments.py")
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)

        def is_str_exc(node) -> bool:
            """`str(exc)` / `exc.__str__()` / f-string 变体一律算。"""
            seg = ast.get_source_segment(src, node) or ""
            return seg.replace(" ", "").startswith("str(exc")

        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            val = node.value
            # 形如  str(exc)[:N]  /  str(exc)[a:b]  /  f"{str(exc)}"[:N]
            if is_str_exc(val):
                found.append(ast.get_source_segment(src, node))
            # 链式：str(exc).strip()[:N]
            if (isinstance(val, ast.Call)
                    and isinstance(val.func, ast.Attribute)
                    and is_str_exc(val.func.value)):
                found.append(ast.get_source_segment(src, node))
        self.assertEqual(
            [], found,
            "仍有裸 str(exc) 切片截断 —— 会切掉多行消息的结论行，"
            f"改用 _brief(exc, N)。发现：{found}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
