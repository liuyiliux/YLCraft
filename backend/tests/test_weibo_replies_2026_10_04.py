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


class TestInlineRepliesAreNormalized(unittest.TestCase):
    """顶层内嵌的 `replies` **不能原样透传**。

    2026-10-04 用户实测截图后发现的：展开能显示内容，是因为前端走的是
    `parent_id` 那条路（已转好形状）。而**顶层内嵌**那份实测下来
    每个字段都是 `null` —— 原来 `"replies": c["comments"]` 直接把
    微博原始 dict 透传，而那个结构里内容在 `text`、作者在
    `user.screen_name`，**没有** `content` / `author` 字段。

    之前没人发现，是因为前端从不读这份内嵌数据
    （点击展开会重新请求）。一旦前端改用内嵌数据（少发一次请求），
    立刻就会露出空白。
    """

    def test_norm_reply_exists_and_converts(self):
        from app.services.platforms.weibo.client import _norm_reply
        out = _norm_reply(REAL_SUB_REPLY)
        self.assertIsNotNone(out)
        self.assertEqual("你居然看过", out["content"])
        self.assertEqual("钴噜球", out["author"])
        self.assertEqual(74, out["likes"])
        self.assertTrue(out["is_author_reply"])

    def test_rejects_empty_shell(self):
        """既没内容也没作者 → 不给前端（宁可不显示，别给空行）。"""
        from app.services.platforms.weibo.client import _norm_reply
        self.assertIsNone(_norm_reply({"id": 1, "text": "", "user": {}}))
        self.assertIsNone(_norm_reply("not a dict"))

    def test_both_paths_use_same_normalizer(self):
        """单一事实来源：顶层内嵌和 parent_id 必须给前端一样的数据。

        否则"直接展开"和"点开加载"会显示不同内容 —— 很难查。
        """
        from app.services.platforms.weibo import client as wc
        src = inspect.getsource(wc)
        self.assertNotIn('"replies": _raw_reps', src,
                         "顶层不能原样透传微博原始 replies（字段名对不上）")
        self.assertIn("_norm_reply(r)", src, "顶层要过 _norm_reply")
        gr = inspect.getsource(wc.WeiboClient.get_replies)
        self.assertIn("_norm_reply", gr,
                      "get_replies 必须用同一个 _norm_reply（否则两条路不一致）")

    def test_inline_replies_have_real_content(self):
        """运行时：顶层返回的 replies 必须**带内容**（不是 null）。"""
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
        self.assertEqual(1, len(top["replies"]))
        rep = top["replies"][0]
        self.assertTrue(rep["content"], "顶层内嵌的回复内容不能是空的")
        self.assertTrue(rep["author"], "顶层内嵌的回复作者不能是空的")
        # 关键：不能再是微博原始字段名
        self.assertNotIn("text", rep)
        self.assertNotIn("user", rep)


class TestCommentCountConsistency(unittest.TestCase):
    """评论总数**三处显示**必须用同一个数（2026-10-04 用户截图发现）。

    用户实测翻过页的微博：标签「共 46 条」、tab 徽标「45」、
    按钮「27 条剩余」—— **三个数互相矛盾**。

    根因：`commentTotal` 是后端**每次响应**里报的，而微博热门评论
    会**按热度重排** → 翻页过程中这个数会变。三处各算各的就对不上。
    """

    FE = (Path(__file__).resolve().parents[2]
          / "frontend" / "src" / "pages" / "crawler" / "index.tsx").read_text(
        encoding="utf-8")

    def test_single_computed_value_exists(self):
        self.assertIn("const commentCountShown", self.FE,
                      "必须有一个统一算出来的显示值")
        self.assertIn("const commentRemaining", self.FE, "剩余数也要统一算")

    def test_all_three_sites_use_it(self):
        code = self._code_only(self.FE)
        self.assertIn("badge: commentCountShown", code,
                      "tab 徽标要用统一值")
        self.assertIn("（{commentRemaining} 条剩余）", code,
                      "加载更多按钮要用统一剩余数")
        # 计数标签：从"评论列表"标题往后找（页面里有很多 <Tag color="orange">，
        # 直接 index 会命中前面批量下载那块的"微信接口限制"）。
        # ⚠️ 窗口要够大 —— 中间隔着整个排序控件（Segmented）。
        i = code.index("评论列表")
        seg = code[i: i + 3000]
        self.assertIn('style={{ marginBottom: 12 }}', seg,
                      "没找到评论计数那个 Tag（锚点失效了？）")
        self.assertIn("{commentCountShown}", seg, "计数标签要用统一值")
        self.assertNotIn("commentTotal", seg,
                         "计数标签还在用后端原值（三处数字对不上的根源）")

    def test_remaining_never_negative(self):
        self.assertIn("Math.max(0, commentCountShown - comments.length)",
                      self.FE, "剩余数不能为负（总数比已加载的还少时）")
        self.assertIn("Math.max(commentTotal || 0, comments.length)", self.FE,
                      "总数不能小于已加载条数（后端按热度重排会导致）")

    @staticmethod
    def _code_only(fe: str) -> str:
        """剥掉注释（`//` 行注释 + `/* */` 块注释）后返回可执行代码。

        ⚠️ 只剥 `//` 不够 —— 解释这个 bug 的 `{/* ... */}` 块注释里
        也写着 `commentTotal - comments.length`（"原来这里是…"），
        不剥就会匹配到自己。第三次踩"源码文本断言不可信"这个坑了。
        """
        import re as _re
        fe = _re.sub(r"/\*.*?\*/", "", fe, flags=_re.S)
        return "\n".join(ln for ln in fe.splitlines()
                         if not ln.strip().startswith("//")
                         and not ln.strip().startswith("*")
                         and "/*" not in ln)

    def test_no_direct_subtraction_left(self):
        code = self._code_only(self.FE)
        self.assertNotIn(
            "commentTotal - comments.length", code,
            "还有地方在直接相减（那正是三个数矛盾的来源）",
        )

    def test_frontend_uses_inline_replies_first(self):
        """顶层内嵌已有数据时**不该再发请求**（20 条评论省 20 次请求）。"""
        self.assertIn("const inline = Array.isArray(c.replies)", self.FE,
                      "点开时应先看列表里已有的 replies")
        i = self.FE.index("const inline = Array.isArray(c.replies)")
        seg = self.FE[i: i + 900]
        # 先用内嵌 → 早退，不进 setCommentLoading 分支
        self.assertIn("_replies: inline", seg, "内嵌数据要直接展开")
        self.assertLess(seg.index("_replies: inline"), seg.index("setCommentLoading"),
                        "先用内嵌数据、早退，之后才是请求兜底")


if __name__ == "__main__":
    unittest.main(verbosity=2)
