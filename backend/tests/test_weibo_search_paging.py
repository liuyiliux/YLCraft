# -*- coding: utf-8 -*-
"""微博搜索能翻多少页（2026-10-06 实测重写）。

## 为什么这个文件被重写过三次

同一个问题我给了三个互相矛盾的答案：**页码式 → 游标式 → 单页式**。
三次都不是平台变了，是**我用的取法不对**。

## 决定性实验：让页面自己翻一次（2026-10-06，已确认登录态）

在登录浏览器（`/api/config` → `data.login=true`、`uid=7628413874`）里打开
`m.weibo.cn/p/index?containerid=100103type%3D1%26q%3D沈阳`，监听请求后滚到底：

    /api/container/getIndex?containerid=...&q=沈阳&page=2
    /api/container/getIndex?containerid=...&q=沈阳&page=3
    /api/container/getIndex?containerid=...&q=沈阳&page=4

页面上卡片数 **18 → 28 → 40 → 50** ⇒ **页面自己翻到了第 4 页。**

⇒ "微博搜索只有一页"是**我 fetch 抄不出来**，不是平台限制。

把那条请求原样抄回来仍 0 条，四个变量逐项单独测过：

| 变量 | 结果 |
| --- | --- |
| `page_type=searchall` 有无 | 都 9/0 条 |
| `x-xsrf-token` 有无（页面确实发了） | 都 9/0 条 |
| `referer` 首页 vs 搜索页 | 都 9/0 条 |
| `type` = 1 / 60 / 61 / 64 | 都 9/0 条 |

原因**未查明**，不当结论写。MediaCrawler（★76k）用的正是这条 `m.weibo.cn`，
同样只拿到 1 页 —— 它是去重标的，不是能翻页的证据。

## ⇒ 改走桌面版 `s.weibo.com`（实测）

    page=1   20 个 mid
    page=2   10 个，与 page=1 **重叠 0**
    page=3   10 个，重叠 0
    page=50  仍有 10 个，重叠 0

⇒ 一页 10 条、最多 50 页 = 500 条，页与页零重叠。

## 本组测试的立场

**锁住真实行为**（翻页真的会发生），并把两次翻车写进文档，
避免下一个人又按"只有一页"去改。
"""
import ast
import inspect
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.platforms.weibo import search_desktop as sd  # noqa: E402
from app.services.platforms.weibo import search_patchright as sp  # noqa: E402
from app.services.platforms.weibo.apis import build_search_params  # noqa: E402

SRC = inspect.getsource(sp.search_via_patchright)
DESK_SRC = inspect.getsource(sd)


def _code(obj=sp.search_via_patchright) -> str:
    """剥掉 docstring + 注释，只留可执行代码。

    ⚠️ 不剥会匹配到我自己写的说明文字（"原来这里用 page+i…"）。
    同一个坑今天第 6 次了，固定处理。
    """
    src = inspect.getsource(obj)
    tree = ast.parse(textwrap.dedent(src))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)):
        fn.body = fn.body[1:]
    return ast.unparse(fn)


class TestDesktopPagingActuallyHappens(unittest.TestCase):
    """搜索**真的要翻页** —— 这是这次改动的全部意义。"""

    def test_pages_to_try_not_hardcoded_one(self):
        code = _code()
        self.assertNotIn(
            "pages_to_try = 1", code,
            "2026-10-04 定的「只取第 1 页」已被推翻："
            "桌面版实测能翻 50 页，且页与页零重叠。"
            "再写死 1 就是退回那个错的结论。",
        )

    def test_page_advances_with_loop(self):
        """循环里必须用 `page + i`，不能恒定 page=1。"""
        code = _code()
        self.assertIn("pn = page + i", code,
                      "第 2 页起必须请求 page+1（桌面版 page 参数有效）")

    def test_uses_desktop_fetcher(self):
        code = _code()
        self.assertIn("fetch_desktop_page", code,
                      "应该走桌面版 s.weibo.com，而不是 m.weibo.cn 的 getIndex")
        self.assertNotIn("JS_SEARCH", code,
                         "移动版 JS_SEARCH 已不再用于搜索（实测翻不动）")

    def test_stops_when_want_satisfied(self):
        code = _code()
        self.assertIn("if len(out) >= want", code,
                      "取够 want 条要停（不然每次搜索都翻 50 页，慢死）")

    def test_stops_on_empty_page(self):
        """翻到空页必须停 —— 否则会白翻 40 次 goto（每次 3 秒）。"""
        code = _code()
        i = code.index("if not cards:")
        self.assertIn("break", code[i: i + 80],
                      "空页 = 平台到顶，要立刻停")

    def test_client_passes_platform_page_cap(self):
        """⚠️ 客户端必须把 `max_pages` 放宽到平台上限。

        原来是默认值 3 —— 用户选「每页 50 条」只会拿到 30 条，
        而且页面上**没有任何提示说被截断了**。
        """
        import inspect as _i

        from app.services.platforms.weibo.client import WeiboClient
        src = _i.getsource(WeiboClient.search)
        self.assertIn("max_pages=DESKTOP_MAX_PAGE", src,
                      "要传平台上限，否则大页数取不满")


class TestHasMoreIsComputed(unittest.TestCase):
    """`has_more` 要**算出来**，不能写死 False、也不能靠"取满了就猜"。"""

    def test_has_more_not_hardcoded(self):
        code = _code()
        self.assertNotIn('_has_more"] = False', code,
                         "不能写死 False（2026-09-29 那个写死让「加载更多」永远消失）")

    def test_has_more_accounts_for_platform_page_cap(self):
        code = _code()
        self.assertIn("DESKTOP_MAX_PAGE", code,
                      "翻到平台 50 页上限时不能再声称还有")

    def test_has_more_false_when_no_results(self):
        code = _code()
        self.assertIn("has_more = bool(out)", code,
                      "一条都没拿到时不能声称还有更多")


class TestLoginRequiredIsDistinct(unittest.TestCase):
    """「没登录」和「没搜到」必须分开 —— 前者要用户去补登录态。"""

    def test_login_signal_is_its_own_type(self):
        self.assertTrue(issubclass(sd.DesktopLoginRequired, Exception))
        self.assertIsNot(sd.DesktopLoginRequired, RuntimeError,
                         "单独一类好让上层精确区分（原来混成 RuntimeError）")

    def test_maps_to_login_expired_error(self):
        code = _code()
        self.assertIn("LoginExpiredError", code,
                      "被踢到登录页要抛 LoginExpiredError —— "
                      "API 层才映射成 401 而不是 500")

    def test_keeps_results_when_only_later_page_requires_login(self):
        """第 1 页拿到了、第 2 页要登录 ⇒ **保留第 1 页**。

        ⚠️ 原来无条件 raise → 把"取不到更多"变成"什么都取不到"，比原来更糟。
        """
        code = _code()
        i = code.index("except DesktopLoginRequired")
        seg = code[i: i + 400]
        self.assertIn("if out:", seg, "已有结果时应保留并停止翻页")
        self.assertIn("break", seg)


class TestSearchTypeOnDesktop(unittest.TestCase):
    """桌面版的分类参数是 `xsort`（**实测**），不是移动版的 `type`。

    ⚠️ 移动版 `type=61` 在桌面版**完全无效**：实测返回与默认 100% 重叠
    （一模一样的 20 条）。参数名照抄过来 = 标签页点了没反应。
    """

    def test_xsort_mapping_exists(self):
        self.assertEqual("hot", sd.DESKTOP_XSORT["popular"])
        self.assertEqual("", sd.DESKTOP_XSORT["all"])

    def test_realtime_has_no_desktop_equivalent(self):
        self.assertIn(sd.DESKTOP_NO_REALTIME, sd.DESKTOP_XSORT,
                      "桌面版只有综合/热门；「实时」要显式记录为回退到综合")

    def test_enum_value_is_extracted(self):
        """⚠️ `params.search_type` 是**枚举**，直接 str() 得到
        "SearchType.NOTE" —— 必须先取 `.value`。写错过一次。"""
        code = _code()
        self.assertIn("getattr(raw_st, 'value', raw_st)", code,
                      "应从枚举取 .value（getattr 的第二个参数是兜底）")

    def test_xsort_is_passed_through(self):
        code = _code()
        self.assertIn("xsort=xsort", code, "xsort 要传到桌面版抓取函数")


class TestParseDesktopCard(unittest.TestCase):
    """桌面卡片 → `SearchResult` 的字段映射。"""

    def _card(self, **over):
        base = {
            "mid": "5350802751228029",
            "text": "沈阳生咖裙里太搞笑了",
            "user": "狂腮因子_",
            "userHref": "//weibo.com/7215424647?refer_flag=1001030103_",
            "from": "43分钟前 转赞人数超过200",
            "nums": ["1", "56", "251"],
            "img": "https://tvax2.sinaimg.cn/crop.0.0.1080.1080.180/x.jpg",
            "is_video": False,
        }
        base.update(over)
        return base

    def test_basic_fields(self):
        r = sd.parse_desktop_card(self._card())
        self.assertEqual("5350802751228029", r.id)
        self.assertEqual("狂腮因子_", r.author)
        self.assertEqual("7215424647", r.author_id,
                         "作者 uid 要从 href 里抽出来")
        self.assertEqual("沈阳生咖裙里太搞笑了", r.title)
        self.assertIn("5350802751228029", r.url)

    def test_counts_order(self):
        """`.card-tool` 的 DOM 顺序实测恒为 转发 → 评论 → 点赞。"""
        r = sd.parse_desktop_card(self._card())
        self.assertEqual(1, r.shares)
        self.assertEqual(56, r.comments)
        self.assertEqual(251, r.likes)

    def test_chinese_numbers_parsed(self):
        r = sd.parse_desktop_card(self._card(nums=["1.2万", "3千", "5.5万"]))
        self.assertEqual(12000, r.shares)
        self.assertEqual(55000, r.likes)

    def test_zero_count_shows_word_not_digit(self):
        """⚠️⚠️ 计数为 0 时页面显示的是**文字**"转发"，不是数字 0。

        实测 li 文本形如 `['转发', '1', '15']`。上一版按"哪些像数字"筛，
        把第一项筛掉后错位，**三个计数全变成 0** —— 静默的假数据。
        """
        r = sd.parse_desktop_card(self._card(nums=["转发", "1", "15"]))
        self.assertEqual(0, r.shares, "文字'转发'应解析为 0，不是 15")
        self.assertEqual(1, r.comments, "位置不能错位")
        self.assertEqual(15, r.likes, "位置不能错位")

    def test_only_verified_units_are_multiplied(self):
        """⚠️ 微博实测只用 `万` / `亿` 两种单位（`['1.2万', ...]`、`'105'`）。

        没验证过的单位**不乘** —— 取到数字就给数字，不去猜。
        猜错了显示成"3"还好，猜错了显示成"3000"就是编数据。
        """
        self.assertEqual(3, sd._cn_number("3千"), "未验证的单位不换算")
        self.assertEqual(12000, sd._cn_number("1.2万"))
        self.assertEqual(100_000_000, sd._cn_number("1亿"))
        self.assertEqual(3456, sd._cn_number("3456"))
        self.assertEqual(0, sd._cn_number("转发"))
        self.assertEqual(0, sd._cn_number(""))

    def test_missing_counts_are_zero_not_guessed(self):
        """拿不到就给 0 —— **绝不编数字**。"""
        r = sd.parse_desktop_card(self._card(nums=[]))
        self.assertEqual((0, 0, 0), (r.shares, r.comments, r.likes))

    def test_create_time_left_empty_not_faked(self):
        """桌面卡片只有 "43分钟前"，**如实留空**而不是编时间戳。"""
        r = sd.parse_desktop_card(self._card())
        self.assertEqual("", r.create_time,
                         "编一个时间戳比留空更坏 —— 详情页才有精确 created_at")

    def test_card_without_mid_rejected(self):
        self.assertIsNone(sd.parse_desktop_card({"mid": "", "text": "x"}))

    def test_card_without_text_rejected(self):
        self.assertIsNone(sd.parse_desktop_card({"mid": "123456", "text": ""}))

    def test_video_flag(self):
        self.assertEqual("video", sd.parse_desktop_card(
            self._card(is_video=True)).type)
        self.assertEqual("note", sd.parse_desktop_card(self._card()).type)


class TestPlatformConstants(unittest.TestCase):
    """平台上限要写进代码，不是只在文档里。"""

    def test_max_page_is_50(self):
        """实测：第 50 页仍有内容。写错这个数字 = 白翻或早停。"""
        self.assertEqual(50, sd.DESKTOP_MAX_PAGE)

    def test_page_size_is_10(self):
        self.assertEqual(10, sd.DESKTOP_PAGE_SIZE)

    def test_url_contains_keyword_and_page(self):
        url = sd.DESKTOP_SEARCH_URL.format(keyword="沈阳", page=3)
        self.assertIn("q=沈阳", url)
        self.assertIn("page=3", url)
        self.assertTrue(url.startswith("https://s.weibo.com/weibo"))


class TestBuildParamsSinceId(unittest.TestCase):
    """`build_search_params`（移动版）—— 留着，因为**用户列表**还在用。

    ⚠️ 搜索已经不走它了，但 `apis.py` 的类型映射仍被测试覆盖。
    """

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


class TestLessonStaysWritten(unittest.TestCase):
    """翻过三次车 ⇒ 教训必须留在代码里，不能靠聊天记录（会被压缩掉）。"""

    def test_page2_empty_is_recorded(self):
        self.assertIn("0 条", SRC, "要写明 m.weibo.cn 的 page=2 实测返回 0 条")

    def test_desktop_results_recorded(self):
        self.assertIn("50", DESK_SRC,
                      "要写明桌面版实测到第 50 页（页数上限的依据）")

    def test_login_state_recorded(self):
        """把实测到的登录态记下来（下次可对照）。"""
        for src, name in ((SRC, "search_patchright"), (DESK_SRC, "search_desktop")):
            with self.subTest(file=name):
                self.assertIn("7628413874", src,
                              "记下实测的 uid（证明那次测的是登录态）")

    def test_env_hazard_recorded(self):
        """⚠️ 手工测之前必须 `load_dotenv(.env)`，否则是访客态。"""
        for src, name in ((SRC, "search_patchright"), (DESK_SRC, "search_desktop")):
            with self.subTest(file=name):
                self.assertIn(".env", src, "要写明手工测要先加载 .env")

    def test_data_field_hazard_recorded(self):
        """⚠️ `/api/config` 的 `login` 在 **`data`** 里，不在顶层。"""
        for src, name in ((SRC, "search_patchright"), (DESK_SRC, "search_desktop")):
            with self.subTest(file=name):
                self.assertIn("data", src, "要写明字段在 data 里（我因此误判过）")

    def test_visitor_vs_login_recorded(self):
        """访客态 `ok=-100` vs 登录态 `ok=1` + 0 条 —— 混在一起必然误判。"""
        for src, name in ((SRC, "search_patchright"), (DESK_SRC, "search_desktop")):
            with self.subTest(file=name):
                self.assertIn("访客", src, "要写明访客态与登录态返回不同")

    def test_page_itself_can_paginate_recorded(self):
        """⭐ 最关键的一条：页面**自己**能翻到第 4 页。"""
        self.assertIn("页面自己", DESK_SRC,
                      "要写明'页面自己能翻页'这个决定性证据 —— "
                      "没有它，下一个人会再得出'只有一页'")


class TestExtractionUsesDomNotRegex(unittest.TestCase):
    """⚠️ 抓卡片必须走 DOM，不能正则解析 HTML。"""

    def test_no_regex_on_html(self):
        """抓卡片必须走 DOM —— 正则漏卡片（属性顺序不固定）。"""
        code = _code(sd.fetch_desktop_page)
        self.assertNotIn("re.compile", code,
                         "HTML 正则解析会漏卡片（属性顺序不固定，实测漏一半）")

    def test_js_selects_mid_attribute(self):
        self.assertIn("getAttribute('mid')", sd.JS_EXTRACT_CARDS,
                      "在 DOM 上读 mid 属性")
        self.assertIn("querySelectorAll", sd.JS_EXTRACT_CARDS,
                      "用 querySelectorAll 抽卡片")

    def test_handles_both_card_layouts(self):
        """⚠️⚠️ 同一页面同时存在两种卡片结构（2026-10-06 实测）：

            旧版  div.card-wrap > .card-tool
            新版  div.card       > .card-act > ul > li

        只认一种，另一半结果会**静默变成空字段**（上一版的 author 全空）。
        """
        js = sd.JS_EXTRACT_CARDS
        self.assertIn("div.card-wrap[mid]", js, "要认旧版 card-wrap")
        self.assertIn("div.card[mid]", js, "要认新版 card")
        self.assertIn(".card-act", js, "要认新版 .card-act")
        self.assertIn(".card-tool", js, "要认旧版 .card-tool")

    def test_counts_are_positional_not_filtered(self):
        """计数必须**按 li 位置**取，不能按"哪些像数字"过滤。"""
        js = sd.JS_EXTRACT_CARDS
        self.assertIn("lis[0]", js, "按位置取转发")
        self.assertIn("lis[1]", js, "按位置取评论")
        self.assertIn("lis[2]", js, "按位置取点赞")
        self.assertNotIn("/^[\\d.万亿]+$/.test(t)", js,
                         "数字过滤会让转发为 0 的卡片整行被筛掉（错位）")

    def test_author_selector_is_a_name(self):
        """⚠️ 作者名在 `a.name`，不是 `.name a` —— 写反过，author 全空。"""
        js = sd.JS_EXTRACT_CARDS
        self.assertIn("a.name", js, "要用 a.name")

    def test_waits_for_render(self):
        code = _code(sd.fetch_desktop_page)
        self.assertIn("wait_for_selector", code,
                      "SSR 首屏可能只有壳，要等 card-wrap 出来再抽")

    def test_render_wait_timeout_is_short(self):
        """⚠️⚠️ 等渲染的超时必须**短**。

        实测：有结果时 `card-wrap` 1 秒内出现；**没结果时永远不出现**。
        原来 timeout=15000 → 搜一个不存在的词要干等 16.8 秒。
        用户看到的就是"卡住了十几秒"。现在 6 秒封顶。
        """
        code = _code(sd.fetch_desktop_page)
        i = code.index("wait_for_selector")
        seg = code[i: i + 120]
        self.assertIn("6000", seg,
                      "等渲染超时必须 ≤6 秒（否则空搜索干等十几秒）")


if __name__ == "__main__":
    unittest.main(verbosity=2)