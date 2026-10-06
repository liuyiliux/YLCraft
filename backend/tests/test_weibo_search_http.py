# -*- coding: utf-8 -*-
"""微博搜索走**纯 HTTP**（2026-10-06）。

## 这条路为什么存在

我先后两次断言"微博搜索必须开浏览器"，**两次都是我的测试方法错了**：

**① 10-04** —— 用了移动版 `m.weibo.cn` 的 JSON 接口，它的 `page` 翻不动。
那是**我选错了端点**，不是平台限制。打开真实页面滚到底才发现
**页面自己会发 `page=2/3/4`**。

**② 10-06** —— 给 `s.weibo.com` 的**网页请求**加了接口用的头：

    'x-requested-with': 'XMLHttpRequest'      ← 就是这个

加上它，微博直接返回"页面不存在"：

    → https://weibo.com/sorry?pagenotfound&retcode=6102

我拿这个被踢的结果下了结论"直连不行"，**还写进代码注释当实测结论**，
于是白开了几天浏览器（每次搜索 15 秒 + 250MB 内存）。

⇒ **网页请求不能带 `x-requested-with`。** 去掉之后一切正常。

## 去掉那个头之后（实测 2026-10-06）

    page=1   1.0 秒  22 张卡片
    page=2   0.4 秒  10 张
    page=3   0.5 秒   9 张
    page=10  0.4 秒  10 张
    page=50  0.4 秒  10 张
    页与页重叠 = **0**（真翻页）

⇒ **15 秒 → 0.4~1 秒**，且不需要开浏览器。
"""
import ast
import inspect
import re
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.platforms.weibo import search_desktop as sd  # noqa: E402
from app.services.platforms.weibo import search_http as sh  # noqa: E402
from app.services.platforms.weibo import search_patchright as sp  # noqa: E402


def _code(obj) -> str:
    """剥掉 docstring + 注释，只留可执行代码。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
    fn = tree.body[0]
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)):
        fn.body = fn.body[1:]
    return ast.unparse(fn)


class TestNoXhrHeaderOnWebRequests(unittest.TestCase):
    """⭐⭐ 锁死那个把直连搞挂的头。

    这是我误判"必须开浏览器"的**唯一原因**。加上它，微博返回
    `pagenotfound&retcode=6102`，卡片 0 个。
    """

    def test_headers_must_not_contain_x_requested_with(self):
        for name, value in sh.BASE_HEADERS.items():
            with self.subTest(header=name):
                self.assertNotEqual(
                    "XMLHttpRequest", value,
                    "⚠️ 网页请求不能带 x-requested-with —— "
                    "带上它微博返回 pagenotfound（实测 0 条结果），"
                    "我因此误判'直连不行'好几天",
                )
        self.assertNotIn("x-requested-with", {k.lower() for k in sh.BASE_HEADERS})

    def test_headers_look_like_a_normal_page_request(self):
        """网页请求该带的是这些，不是 AJAX 头。"""
        keys = {k.lower() for k in sh.BASE_HEADERS}
        self.assertIn("user-agent", keys)
        self.assertIn("accept", keys)
        self.assertIn("accept-language", keys)


class TestUrlBuilding(unittest.TestCase):
    """⚠️ 中文关键词必须编码 —— 不编码直接返回 pagenotfound。"""

    def test_keyword_is_quoted(self):
        url = sh.build_search_url("沈阳", 2)
        self.assertIn("q=%E6%B2%88%E9%98%B3", url)
        self.assertNotIn("q=沈阳", url)

    def test_page_number(self):
        self.assertIn("page=3", sh.build_search_url("x", 3))

    def test_xsort_appended_only_when_given(self):
        self.assertNotIn("xsort", sh.build_search_url("x", 1))
        self.assertIn("xsort=hot", sh.build_search_url("x", 1, "hot"))


class TestTotalPages(unittest.TestCase):
    """「共50页」实测是真的平台上限，不是模板文字。"""

    def test_reads_total_pages(self):
        self.assertEqual(50, sh.parse_total_pages("<div>共50页</div>"))
        self.assertEqual(50, sh.parse_total_pages("共 50 页"))

    def test_absent_is_none_not_guessed(self):
        """⚠️ 平台没说就返回 None —— **不猜**。编数字比不知道更坏。"""
        self.assertIsNone(sh.parse_total_pages("这里没有任何页数信息"))
        self.assertIsNone(sh.parse_total_pages(""))

    def test_absurd_value_is_clamped(self):
        """`共6102页` 那种（实测出现在错误页里）要夹到上限。"""
        self.assertEqual(sh.MAX_PAGE, sh.parse_total_pages("共6102页"))

    def test_platform_cap_is_50(self):
        """实测：page=51 会被弹回第 1 页。"""
        self.assertEqual(50, sh.MAX_PAGE)


class TestCountParsing(unittest.TestCase):
    """三个计数的解析 —— 踩过两个坑。"""

    def test_plain_numbers(self):
        self.assertEqual(1, sh._to_int("<li>1</li>"))
        self.assertEqual(69, sh._to_int("<li>69</li>"))

    def test_chinese_units(self):
        self.assertEqual(12000, sh._to_int("<li>1.2万</li>"))
        self.assertEqual(100_000_000, sh._to_int("<li>1亿</li>"))

    def test_zero_shows_as_word_not_digit(self):
        """⚠️⚠️ 转发为 0 时页面显示的是**文字"转发"**，不是 "0"。

        早期版本按"哪些像数字"过滤，把第一项筛掉后三个计数全部错位成 0。
        """
        self.assertEqual(0, sh._to_int("<li><a>转发</a></li>"))

    def test_mid_in_attributes_must_not_be_mistaken_for_count(self):
        """⭐⭐ `<a>` 属性里塞满 `mid=5350578936875316`。

        不先剥标签就找数字，会**先撞上 mid** → 点赞数显示成 535 万
        （实测踩到过）。
        """
        li = ('<li><a href="javascript:void(0);" '
              'action-data="allowForward=1&mid=5350578936875316&uid=2094249094">'
              '<span>843</span></a></li>')
        self.assertEqual(843, sh._to_int(li))

    def test_unverified_unit_not_scaled(self):
        """⚠️ 微博只用万/亿。没验证的单位**不换算** —— 猜错就是编数据。"""
        self.assertEqual(3, sh._to_int("<li>3千</li>"))


class TestCommentStripping(unittest.TestCase):
    """⭐ `.card-act` 里有一段被注释掉的 `<li>`（"收藏"）。

    不删的话它会被当成第 1 个 li → `['收藏','转发','1','2']`
    —— 位置整体错一位，三个计数全读错。
    """

    HTML = (
        '<div class="card-wrap" mid="123">'
        '<p class="txt">正文内容</p>'
        '<a class="name">某人</a>'
        '<div class="card-act"><ul>'
        '<!--  <li><a href="javascript:void(0);">收藏</a></li>-->'
        '<li>2</li><li>50</li><li>843</li>'
        '</ul></div></div>'
    )

    def test_counts_are_correct_after_comment_stripped(self):
        seg = sh.RE_CARD_START.search(self.HTML)
        self.assertIsNotNone(seg)
        body = self.HTML[seg.start():]
        repost, comment, like = sh._parse_counts(body)
        self.assertEqual((2, 50, 843), (repost, comment, like))

    def test_comment_is_removed_before_matching_li(self):
        inner = sh.RE_CARD_ACT.search(self.HTML).group(1)
        self.assertEqual(4, len(sh.RE_LI.findall(inner)),
                         "不去掉注释的话会数到 4 个 li")
        self.assertEqual(3, len(sh.RE_LI.findall(sh.RE_COMMENT.sub("", inner))),
                         "去掉注释后应该是 3 个")


class TestCardParsing(unittest.TestCase):
    """整张卡片的字段映射。"""

    def _html(self, **over):
        mid = over.get("mid", "5350800920679941")
        return (
            '<div action-type="feed_list_item" mid="%s" class="card-wrap">'
            '<div class="card"><div class="card-feed">'
            '<div class="avator"><a href="//weibo.com/6257234757?x=1">'
            '<img src="https://tvax4.sinaimg.cn/crop.0.0.700.700.180/a.jpg">'
            '</a></div>'
            '<p class="txt">%s</p>'
            '<a class="name">娱念波波</a>'
            '<div class="card-act"><ul>'
            '<!--<li>收藏</li>-->'
            '<li>%d</li><li>%d</li><li>%d</li>'
            '</ul></div></div></div>'
        ) % (mid, over.get("text", "正文内容"), over.get("repost", 2),
             over.get("comment", 50), over.get("like", 843))

    def test_basic_fields(self):
        cards = sh.parse_cards(self._html())
        self.assertEqual(1, len(cards))
        c = cards[0]
        self.assertEqual("5350800920679941", c["mid"])
        self.assertEqual("正文内容", c["text"])
        self.assertEqual("娱念波波", c["user"])
        self.assertEqual("6257234757", c["user_id"])
        self.assertIn("sinaimg", c["img"])
        self.assertFalse(c["is_video"])

    def test_counts(self):
        c = sh.parse_cards(self._html())[0]
        self.assertEqual(2, c["repost"])
        self.assertEqual(50, c["comment"])
        self.assertEqual(843, c["like"])

    def test_card_without_mid_skipped(self):
        """热搜榜/推广位没有 mid，要跳过而不是产出空卡片。"""
        html = '<div class="card-wrap"><p class="txt">没有mid</p></div>'
        self.assertEqual([], sh.parse_cards(html))

    def test_attribute_order_does_not_matter(self):
        """⚠️ 真实属性顺序是 action-type → mid → class，不能假设。"""
        html = ('<div class="card-wrap" mid="111" action-type="feed_list_item">'
                '<p class="txt">正文</p></div>')
        cards = sh.parse_cards(html)
        self.assertEqual(1, len(cards))
        self.assertEqual("111", cards[0]["mid"])

    def test_html_entities_unescaped(self):
        cards = sh.parse_cards(self._html(text="A &amp; B"))
        self.assertEqual("A & B", cards[0]["text"])

    def test_zero_width_space_removed(self):
        """微博正文末尾常带 U+200B，用户看到是空方块。"""
        cards = sh.parse_cards(self._html(text="正文"))
        self.assertEqual("正文", cards[0]["text"])


class TestHttpIsPrimaryPath(unittest.TestCase):
    """⭐ 直连是**主路径**，浏览器只是兜底。"""

    def test_search_calls_http_first(self):
        src = inspect.getsource(sp.search_via_patchright)
        i_http = src.index("_search_http(")
        i_browser = src.index("_search_via_browser(")
        self.assertLess(i_http, i_browser,
                        "必须先试直连（0.4~1 秒），浏览器只做兜底（15 秒）")

    def test_browser_only_is_empty(self):
        """微博不该再被强制走浏览器 —— 那会白起 9 个 chrome 进程。"""
        from app.services.crawler import service

        # ⚠️⚠️ 必须剥掉注释再找 —— 我在注释里写了
        # `BROWSER_ONLY = ("weibo", "wb")` 来解释历史，
        # 不剥的话会匹配到**我自己写的注释**。
        # （这个坑今天第 7 次了，见 test_weibo_search_paging._code）
        fn = service.CrawlerService._search_via_platforms
        code = _code(fn)
        m = re.search(r"BROWSER_ONLY\s*=\s*\(([^)]*)\)", code)
        self.assertIsNotNone(m, "找不到 BROWSER_ONLY 定义")
        self.assertEqual("", m.group(1).strip(),
                         "现在没有平台必须走浏览器（微博已改直连）")

    def test_login_error_is_distinct(self):
        """『要登录』要与『没搜到』分开。"""
        self.assertTrue(issubclass(sh.WeiboLoginRequired, Exception))
        code = _code(sp.search_via_patchright)
        self.assertIn("LoginExpiredError", code,
                      "被踢到登录页要抛 LoginExpiredError → 401 而不是 500")

    def test_browser_used_as_fallback_only(self):
        """直连**异常**才开浏览器；直连**正常返回 0 条**不该兜底。

        ⚠️ 实测踩到：搜一个不存在的词，直连返回 0 条（这是**正确答案**），
        旧逻辑却以为"直连不行"，又去开浏览器白跑一趟 ——
        "搜不到"要等 18.7 秒，而真的搜到只要 2.8 秒。

        ⚠️⚠️ **但"要登录"不在此列** —— 那是异常，必须走兜底
           （见 `TestLoginFailureFallsBackToBrowser`）。
        """
        code = _code(sp.search_via_patchright)
        i_http = code.index("await _search_http(")
        i_empty = code.index("if page <= 1:", i_http)
        i_browser = code.index("await _search_via_browser(")
        self.assertLess(i_empty, i_browser)
        seg = code[i_empty: i_browser]
        self.assertIn("return []", seg,
                      "直连正常但没内容时要直接返回，不要开浏览器白跑 15 秒")

    def test_fallback_is_logged_as_warning(self):
        """⚠️ 兜底必须用 warning。

        我第一版用 `logger.info`，结果直连因一个 ImportError 静默失败、
        悄悄回退到浏览器，表现为"改了没效果、还是 15 秒"，
        而日志里只有一行不起眼的 info —— 不主动查根本发现不了。
        """
        src = inspect.getsource(sp.search_via_patchright)
        self.assertIn("logger.warning", src,
                      "回退到浏览器要用 warning（异常情况不该埋在 info 里）")

    def test_import_error_would_not_silently_pass(self):
        """`to_search_result` 的 import 必须指向真实存在的模块。

        ⚠️ 我第一版写成 `from .client import parse_desktop_card`，
        那个函数在 `search_desktop` 里 → ImportError → 直连静默失败
        → 回退浏览器，表现为"改了没效果"。
        """
        code = _code(sh.to_search_result)
        self.assertIn("search_desktop", code,
                      "parse_desktop_card 在 search_desktop，不在 client")


class TestLoginRedirectIsNotMistakenForEmpty(unittest.TestCase):
    """⭐⭐⭐ 2026-10-07 用户实测：搜「营口」返回 0 条，日志却是

        GET s.weibo.com/weibo?q=营口   → 302
        GET login.sina.com.cn/sso/login.php?...  → 200
        [weibo] 搜索 '营口' -> 0 条（直连正常返回，平台没有这个内容）

    **被踢到登录页，却被报成"平台没有这个内容"** —— 假阴性。

    根因：我第一版只认 `passport.weibo.com`，而微博 302 到的是
    **`login.sina.com.cn`**，检查穿过去了 → 解析出 0 张卡片 →
    上层当成"没内容" → 返回空列表**且不回退浏览器**。

    ⇒ 判据改成"最终落点还在不在 s.weibo.com"，不枚举登录域。
    """

    def test_login_sina_is_rejected(self):
        self.assertFalse(sh._is_search_page(
            "https://login.sina.com.cn/sso/login.php?url=https%3A%2F%2Fs.weibo.com"))

    def test_passport_is_rejected(self):
        self.assertFalse(sh._is_search_page(
            "https://passport.weibo.com/visitor/visitor?a=enter"))

    def test_real_search_page_accepted(self):
        self.assertTrue(sh._is_search_page(
            "https://s.weibo.com/weibo?q=%E8%90%A5%E5%8F%A3&page=1"))

    def test_other_weibo_hosts_rejected(self):
        """⚠️ 只认 `s.weibo.com` —— `weibo.com/sorry` 之类也不是结果页。"""
        self.assertFalse(sh._is_search_page("https://weibo.com/sorry?pagenotfound"))
        self.assertFalse(sh._is_search_page("https://m.weibo.cn/"))

    def test_empty_and_garbage_rejected(self):
        for bad in ("", "not a url", "https://evil.com/s.weibo.com"):
            with self.subTest(value=bad):
                self.assertFalse(sh._is_search_page(bad))

    def test_host_of_handles_bad_input(self):
        self.assertEqual("", sh._host_of(""))
        self.assertEqual("", sh._host_of("垃圾"))
        self.assertEqual("s.weibo.com", sh._host_of("https://s.weibo.com/x"))


class TestLoginFailureFallsBackToBrowser(unittest.TestCase):
    """⭐ 直连要登录 ≠ 放弃 —— 浏览器用的是**另一套登录态**。

    持久化 profile 里的登录态与 DB 里那份 cookie 是两套东西。
    实测：DB cookie 失效时直连被 302，但浏览器 profile 可能还能用。
    直接抛错 = 明明有备用登录态却不用。
    """

    def test_http_login_failure_tries_browser(self):
        code = _code(sp.search_via_patchright)
        i_catch = code.index("except HttpLoginRequired")
        i_browser = code.index("await _search_via_browser(")
        self.assertLess(i_catch, i_browser,
                        "登录失败之后必须还能走到浏览器兜底")
        # 抛出前必须经过浏览器尝试
        seg = code[i_catch:i_browser]
        self.assertNotIn("raise LoginExpiredError", seg,
                         "登录失败不该直接抛 —— 要先试浏览器路径")

    def test_both_failing_reports_login_required(self):
        """两条路都被拒才报『要登录』，并且说清是两边都拒了。"""
        code = _code(sp.search_via_patchright)
        i_browser = code.index("await _search_via_browser(")
        seg = code[i_browser:]
        self.assertIn("LoginExpiredError", seg,
                      "浏览器也失败时要报『要登录』而不是返回空")
        self.assertIn("都", seg,
                      "要说清是直连与浏览器**都**被拒，别让用户猜")


class TestNoUndefinedNamesInHotPath(unittest.TestCase):
    """⭐⭐ 未定义的名字**必须**在测试期暴露，不能在运行时被吞掉。

    今天同一个坑踩了三次：

      ① `from .client import parse_desktop_card`（实际在 search_desktop）
         → ImportError → 被 `except Exception` 吞 → 静默回退浏览器
      ② `except WeiboHttpLoginRequired`（不存在的类名）
         → NameError → 被吞 → 直连每次"失败"
      ③ 同一个 `to_search_result` 的导入问题复发

    共同点：**自定义异常/函数名写错没有静态保护**，
    拼错就是运行时 NameError，而外层的 `except Exception` 让症状变成
    "改了没效果、还是慢"，根本不是报错 —— 最难查的一类。

    ⇒ 用 `compile` + 符号表做一次静态检查，杜绝这一类。
    """

    def test_module_compiles_without_syntax_errors(self):
        """语法必须没问题（`compile()` 只编译不入盘，避免临时文件权限问题）。"""
        for mod in (sh, sp, sd):
            with self.subTest(module=mod.__name__):
                src = Path(mod.__file__).read_text(encoding="utf-8")
                compile(src, mod.__file__, "exec")   # 抛错即失败

    def test_custom_exception_names_resolve(self):
        """⚠️ 模块里 `except X` 引用的名字必须真的能取到。

        只查**本项目自定义**的异常名（大驼峰且非内建），
        因为内建异常（ValueError/TypeError…）走内置命名空间，不在模块里。
        """
        import ast as _ast
        import builtins

        custom = {
            "WeiboLoginRequired", "DesktopLoginRequired", "LoginExpiredError",
            "WeiboLoginRequiredError",
        }
        for mod in (sh, sp):
            tree = _ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if not (isinstance(node, _ast.ExceptHandler) and node.type):
                    continue
                names = []
                if isinstance(node.type, _ast.Name):
                    names = [node.type.id]
                elif isinstance(node.type, _ast.Tuple):
                    names = [e.id for e in node.type.elts
                             if isinstance(e, _ast.Name)]
                for n in names:
                    if n not in custom:
                        continue
                    with self.subTest(module=mod.__name__, name=n):
                        self.assertTrue(
                            hasattr(mod, n),
                            f"{mod.__name__} 里 `except {n}` 用了"
                            f"不存在的名字 —— 运行时会 NameError，"
                            f"并被外层 except Exception 吞成『静默回退』",
                        )
                        self.assertTrue(
                            issubclass(getattr(mod, n), builtins.Exception),
                            f"{n} 必须是异常类",
                        )

    def test_login_error_type_is_shared(self):
        """直连与上层必须用**同一个**登录异常类型，否则接不住。"""
        self.assertIs(sh.WeiboLoginRequired, sp.HttpLoginRequired,
                      "search_patchright 的 HttpLoginRequired 必须是 "
                      "search_http.WeiboLoginRequired 本身")


class TestTotalPagesPlumbedThrough(unittest.TestCase):
    """总页数要能到前端 —— 用户不用自己翻到头。"""

    def test_raw_data_carries_total_pages(self):
        src = inspect.getsource(sp._search_http)
        self.assertIn("_total_pages", src)

    def test_browser_path_says_unknown(self):
        """浏览器路径拿不到总页数 —— 如实给 None，**不编**。"""
        src = inspect.getsource(sp._search_via_browser)
        self.assertIn('_total_pages"] = None', src)

    def test_response_model_has_field(self):
        from app.api.v1.crawler import SearchResponse
        self.assertIn("total_pages", SearchResponse.model_fields)

    def test_api_passes_it_through(self):
        from app.api.v1 import crawler
        src = inspect.getsource(crawler.search_enhanced)
        self.assertIn("total_pages=total_pages", src,
                      "要把总页数返回给前端")


if __name__ == "__main__":
    unittest.main(verbosity=2)