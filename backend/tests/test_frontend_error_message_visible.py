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


class TestDetailErrorKeepsReason(unittest.TestCase):
    """**详情**接口也要说真话 —— 截图实测发现它还在丢。

    2026-10-04 用真实浏览器验证评论面板时，截图顶部出现：

        ⚠ 详情加载失败，保留搜索结果

    而那个详情接口**同样返回 429 + 382 字符的真实原因**。
    原因在 `openDetail` 的 `catch {}`：**无参 catch 把异常整段丢掉**，
    换了一句笼统文案。

    这与评论那次（`slice(0,90)` 截断）是**同一个病的两种长法**：
    丢弃"为什么失败 + 该怎么办"。所以两处必须一起修。
    """

    def test_no_bare_catch_in_open_detail(self):
        """`catch {` 不带参数 → 拿不到 err.response，真实原因必丢。"""
        i = SRC.index("const openDetail")
        seg = SRC[i: i + 6000]
        self.assertNotIn(
            "} catch {", seg,
            "openDetail 里不能有无参 catch —— 后端返回的 429/404 原因会被丢掉",
        )
        self.assertIn(
            "} catch (err: any) {", seg,
            "openDetail 的 catch 要接住 err，读 err.response.data.detail",
        )

    def test_detail_error_uses_readable_error(self):
        i = SRC.index("const openDetail")
        seg = SRC[i: i + 6000]
        self.assertIn("setDetailError(readableError(detail)", seg,
                      "详情失败也要用 readableError（保尾），别再丢原因")

    def test_detail_429_has_own_branch(self):
        i = SRC.index("const openDetail")
        seg = SRC[i: i + 6000]
        self.assertIn("status === 429", seg,
                      "429 要单独处理（等一等/换 IP 有救，与 404 不同）")
        self.assertIn("status === 404", seg,
                      "404 要单独处理（内容没了，重试无用）")

    def test_vague_message_only_as_last_resort(self):
        """「详情加载失败」只能当**兜底**，不能在有 detail 时优先用。"""
        i = SRC.index("const openDetail")
        seg = SRC[i: i + 6000]
        # 出现是对的（兜底），但不能是唯一分支
        self.assertIn("详情加载失败，保留搜索结果", seg)
        self.assertIn("readableError(detail)", seg,
                      "有 detail 时必须优先用它")



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


class TestSubReplyRenderingComplete(unittest.TestCase):
    """展开的楼中楼**不能只显示"作者 + 内容"**。

    2026-10-04 补：微博实测数据里有 `create_time` / `like_count` /
    `is_mblog_author`，而展开区域只渲染了 `author` 和 `content`
    —— 时间、赞数、博主标记**全丢**。
    """

    def _seg(self) -> str:
        i = SRC.index("Array.isArray((c as any)._replies)")
        return SRC[i: i + 1700]

    def test_expanded_reply_shows_time(self):
        self.assertIn("formatTime(r.create_time)", self._seg(),
                      "展开的回复要显示时间（原来只显示作者+内容）")

    def test_expanded_reply_shows_likes(self):
        self.assertIn("r.likes", self._seg(), "展开的回复要显示点赞数")

    def test_author_reply_marked(self):
        """微博实测 `is_mblog_author=True`（博主本人回复）。

        不标出来用户分不清"作者在回我"和"路人在回"。
        """
        seg = self._seg()
        self.assertIn("is_author_reply", seg, "博主回复要有标记")
        self.assertIn("作者", seg, "标记文案")

    def test_no_head_truncation_in_reply_fetch(self):
        """取子回复失败时的报错 —— **第三个** `slice(0, N)` 截断点。

        与评论、详情那两处同一个病（2026-10-04 第三次发现）：
        平台错误是"解释 + 处置办法"多行式，处置办法在**尾部**，
        按字数从**头**截正好切掉。

        ⚠️ 第四次踩同一个坑：先剥掉注释行再扫。
        解释"为什么不能用 slice(0, 100)"的注释里必然含这个字面量，
        不剥就会匹配到自己。
        """
        i = SRC.index("parent_id: c.id || c.rpid")
        seg = SRC[i: i + 2400]
        code = "\n".join(ln for ln in seg.splitlines()
                         if not ln.strip().startswith("//"))
        self.assertNotIn(".slice(0, 100)", code,
                         "取回复失败的消息被按头截断了（处置办法会丢）")
        self.assertIn("readableError", code,
                      "要用 readableError（保尾），与其它两处一致")


if __name__ == "__main__":
    unittest.main(verbosity=2)
