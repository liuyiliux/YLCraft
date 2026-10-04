# -*- coding: utf-8 -*-
"""微博楼中楼（2026-10-04 实测推翻"拿不到"）。

## 第三次栽在同一个坑上

| 平台 | 我的错误结论 | 真相 |
|---|---|---|
| 快手 | 15 条 `reply_count=0` → "取不到" | 调 `sublist` 第一条就有 |
| B站 | 信文档说"子回复随顶层返回" | `replies` 数组全空，实为未实现 |
| **微博** | 30+ 个内容没抽到 → "仍未验到" | **给一个样本就是 20/20** |

前两次的错都源于"抽样"。这次用户直接给了确定有楼中楼的链接：

    https://m.weibo.cn/detail/5336295257679240

实测（截图核对过微博 App：博主回复粉丝那条）：顶层 20 条
**全部**带 `comments`（共 32 条），`rootid` 零串号。

## 本组锁三件事

  1. `reply_count` **不能写死 0**（写死 = 前端永远不显示回复入口，
     哪怕数据就在手里 —— 比"取不到"更隐蔽）
  2. `get_replies` 要**真的实现**，不是抛 NotImplementedError
  3. `is_author_reply` 要能穿过**归一化白名单**（采集到了却在出口被丢）
"""
import ast
import inspect
import sys
import textwrap
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.comments import _normalize_generic_comment  # noqa: E402
from app.services.platforms.weibo.client import WeiboClient  # noqa: E402
from app.services.platforms.weibo.meta import PLATFORM_META  # noqa: E402


def _dedent_src(src: str) -> str:
    """getsource 出来的代码带缩进，直接 ast.parse 会 IndentationError。"""
    return textwrap.dedent(src)


SRC = (Path(__file__).resolve().parents[1]
       / "app" / "services" / "platforms" / "weibo" / "client.py").read_text(
    encoding="utf-8")
COMMENTS_SRC = (Path(__file__).resolve().parents[1]
                / "app" / "api" / "v1" / "comments.py").read_text(encoding="utf-8")

# 实测返回里的一条（从 5336295257679240 抠出来的，字段名保持原样）
REAL_SUB_REPLY = {
    "id": 5337290936160046,
    "rootid": 5337290303868548,
    "rootidstr": "5337290303868548",
    "floor_number": 0,
    "text": "你居然看过<span class=\"url-icon\"><img alt=\"[允悲]\"/></span>",
    "created_at": "Sat Aug 29 16:39:44 +0800 2026",
    "like_count": "74",
    "source": "来自 陕西",
    "is_mblog_author": True,
    "user": {"id": 123, "screen_name": "钴噜球",
             "profile_image_url": "https://tvax2.sinaimg.cn/x.jpg"},
}

REAL_PARENT = {
    "id": 5337290303868548,
    "text": "我小时候看这段，看出心理阴影了",
    "like_count": "2007",
    "created_at": "Sat Aug 29 16:37:00 +0800 2026",
    "source": "来自 北京",
    # ⚠️ 微博**自己的** reply_count 是 0（实测 20/20 全是 0）
    "reply_count": 0,
    "comments": [REAL_SUB_REPLY],
    "user": {"id": 580, "screen_name": "一半的我在春水里永生",
             "profile_image_url": "https://tvax2.sinaimg.cn/y.jpg"},
}


class TestWeiboRepliesCapability(unittest.TestCase):
    def test_meta_declares_replies(self):
        self.assertIn("replies", PLATFORM_META["capabilities"],
                      "微博能取楼中楼（实测 20/20），meta 必须声明")

    def test_get_replies_not_still_not_implemented(self):
        """**行为**上不能再抛"不支持"—— 那个结论已被实测推翻。

        ⚠️ 踩了两次坑才写对：
          ① 直接 `assertNotIn(源码)` —— 匹配到的是**docstring 里故意保留的**
             历史说明（"这里原来写着…"），那是给人看的，不是结论。
          ② 改用 `ast.unparse` 剥 docstring —— 仍会带上整个模块。
        结论：**别用字符串匹配**去断言"某句话不存在"，
        直接断言行为 —— 传入有数据的响应时**不应**抛 NotImplementedError。
        （`test_returns_real_sub_replies` 就是这条行为的断言。）
        """
        self.assertIn("/comments/hotflow",
                      inspect.getsource(WeiboClient.get_replies),
                      "应该走顶层接口拿子回复，而不是直接拒绝")
        # meta 也要声明（否则 API 层直接 501，永远走不到这里）
        self.assertIn("replies", PLATFORM_META["capabilities"])

    def test_get_replies_returns_dict_shape(self):
        sig = inspect.signature(WeiboClient.get_replies)
        for p in ("item_id", "comment_id", "max_results", "cursor"):
            self.assertIn(p, sig.parameters, f"签名缺 {p}（调用方按名字传）")


class TestReplyCountNotHardcoded(unittest.TestCase):
    """**最隐蔽的 bug**：数据抓到了，却因为一个写死的数不显示。"""

    def test_reply_count_comes_from_len_replies(self):
        src = inspect.getsource(WeiboClient.get_comments_page)
        self.assertIn("len(_reps)", src,
                      "reply_count 必须自己数（微博给的字段恒为 0）")
        self.assertNotIn('"reply_count": 0,', src,
                         "reply_count 不能写死 0 —— 那会让前端永不显示楼中楼")

    @patch("app.services.platforms.weibo.client.WeiboClient._call")
    def test_runtime_reply_count_is_two(self, call):
        with patch.object(
            WeiboClient, "_call",
            new=AsyncMock(return_value={
                "data": {"data": [REAL_PARENT], "max_id": 0},
            }),
        ):
            c = WeiboClient.__new__(WeiboClient)
            c.config = type("C", (), {"conn_id": "", "cookie": ""})()
            out = TestGetRepliesRuntime()._run(
                c.get_comments_page("5336295257679240"))
        top = out["comments"][0]
        self.assertEqual(
            len(top["replies"]), top["reply_count"],
            "reply_count 必须等于实际子回复数（微博自己给 0）",
        )
        self.assertEqual(1, len(top["replies"]))


class TestGetRepliesRuntime(unittest.TestCase):
    def _client(self):
        c = WeiboClient.__new__(WeiboClient)
        c.config = type("C", (), {"conn_id": "", "cookie": ""})()
        return c

    def _run(self, coro):
        import asyncio
        return asyncio.new_event_loop().run_until_complete(coro)

    def test_returns_real_sub_replies(self):
        """实测数据（5336295257679240 的第一条楼中楼）。"""
        # ⚠️ 用 `patch.object(..., new=AsyncMock(...))` 而不是
        # `@patch` 装饰器 + `call.return_value`：
        # 装饰器版会把 `_call` 换成 MagicMock，`await self._call(...)`
        # 拿到的是 MagicMock 而不是 dict（第一版就这么错的）。
        with patch.object(
            WeiboClient, "_call",
            new=AsyncMock(return_value={
                "data": {"data": [REAL_PARENT], "max_id": 0},
            }),
        ):
            out = self._run(self._client().get_replies(
                "5336295257679240", "5337290303868548"))

        self.assertEqual(1, len(out["comments"]))
        r = out["comments"][0]
        self.assertEqual("5337290936160046", r["id"])
        self.assertIn("你居然看过", r["content"])
        self.assertEqual(74, r["likes"])
        self.assertEqual("钴噜球", r["author"])
        # 博主本人回复（实测 is_mblog_author=True）
        self.assertTrue(r["is_author_reply"], "博主回复标记没透出")
        # ⚠️ 子回复自己没有子回复（微博只两层）→ 0 是**真的 0**
        self.assertEqual(0, r["reply_count"])
        # total 不编造：微博不给子回复总数
        self.assertEqual(1, out["total"])

    def test_html_stripped_from_text(self):
        """实测 text 带 `<span class="url-icon">` 表情标签
        —— 不清洗的话前端会露出 HTML 源码。"""
        from app.services.platforms.weibo.client import _strip_html
        self.assertNotIn("<", _strip_html(REAL_SUB_REPLY["text"]))


class TestNormalizationKeepsAuthorFlag(unittest.TestCase):
    """采集到了 ≠ 出口给你 —— 归一化是**白名单式**的。"""

    def test_is_author_reply_survives_normalization(self):
        out = _normalize_generic_comment({
            "id": "1", "content": "x", "is_author_reply": True,
        })
        self.assertTrue(out.get("is_author_reply"),
                        "博主回复标记被归一化丢掉了（白名单漏了）")

    def test_field_listed_in_source(self):
        self.assertIn('"is_author_reply"', COMMENTS_SRC,
                      "comments.py 归一化里要显式带上 is_author_reply")


class TestNotFakingWhenNotFound(unittest.TestCase):
    """找不到时**不能**返回空列表冒充"没人回复"。"""

    def _run(self, coro):
        import asyncio
        return asyncio.new_event_loop().run_until_complete(coro)

    def _client(self):
        c = WeiboClient.__new__(WeiboClient)
        c.config = type("C", (), {"conn_id": "", "cookie": ""})()
        return c

    def test_exhausted_pages_means_truly_absent(self):
        """翻到最后一页确实没有 → 这时空列表才是对的。"""
        with patch.object(
            WeiboClient, "_call",
            new=AsyncMock(return_value={
                "data": {"data": [], "max_id": 0},   # max_id=0 = 到底了
            }),
        ):
            out = self._run(self._client().get_replies(
                "5336295257679240", "123"))
        self.assertEqual([], out["comments"])

    def test_pages_exhausted_raises_with_reason(self):
        """翻页用尽仍未找到 → 必须**明说"没翻到"**，不能返回空。"""
        with patch.object(
            WeiboClient, "_call",
            new=AsyncMock(return_value={
                "data": {"data": [], "max_id": "12345"},   # 一直有下一页
            }),
        ):
            with self.assertRaises(NotImplementedError) as cm:
                self._run(self._client().get_replies(
                    "5336295257679240", "999"))
        self.assertIn("没翻到", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
