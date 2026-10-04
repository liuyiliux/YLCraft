# -*- coding: utf-8 -*-
"""YouTube 人机校验（"Sign in to confirm you're not a bot"）处理。

锁住 2026-10-04 实测得出的结论，防止后来人重犯这几类错：

    1. 把它当成 500（服务端故障）→ 实际应是 429（平台侧拒绝）
    2. 把它当成"必须登录"        → 实测不需要登录，失败是**按视频**的
    3. 拿它当"平台不支持评论"     → 实测 dQw4w9WgXcQ 能正常取到评论
    4. 又去试 player_client 兜底  → 7 种全试过，无效；且 web_embedded/mweb
                                     会把本来能用的视频也弄坏
    5. 只在 get_comments 里处理   → 详情页/搜索页同样会撞上

⚠️ 本文件**不联网**（真实结论来自 2026-10-04 的实测脚本），
只验证"错误被正确识别 + 映射成正确状态码 + 文案说真话"。
"""
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.platforms.types import (  # noqa: E402
    ContentNotFoundError,
    NetworkError,
    PlatformError,
    RiskControlError,
)
from app.services.platforms.youtube.client import (  # noqa: E402
    BOT_CHECK_FACTS,
    _bot_check_error,
    _is_bot_check,
)

SRC = (Path(__file__).resolve().parents[1]
       / "app" / "services" / "platforms" / "youtube" / "client.py").read_text(
    encoding="utf-8")
META_SRC = (Path(__file__).resolve().parents[1]
            / "app" / "services" / "platforms" / "youtube"
            / "meta.py").read_text(encoding="utf-8")

COMMENTS_SRC = (Path(__file__).resolve().parents[1]
                / "app" / "api" / "v1" / "comments.py").read_text(encoding="utf-8")


class TestBotCheckDetection(unittest.TestCase):
    def _mk_exc(self):
        """yt-dlp 真实错误文本（含后面那一大段 cookie 教程）。"""
        return (
            "ERROR: [youtube] njK0eebUsQw: Sign in to confirm you\u2019re not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication. "
            "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies"
            "-to-yt-dlp for how to manually pass cookies."
        )

    def test_detects_real_yt_dlp_message(self):
        self.assertTrue(_is_bot_check(self._mk_exc()))

    def test_detects_ascii_apostrophe_variant(self):
        # 不同 yt-dlp 版本弯引号/直引号不一致，两种都要认
        self.assertTrue(_is_bot_check(
            "Sign in to confirm you're not a bot"))

    def test_detects_bare_fragment(self):
        # 短片段也要认（yt-dlp 未来可能改措辞）
        self.assertTrue(_is_bot_check("some wrapper: not a bot"))

    def test_does_not_fire_on_unrelated_errors(self):
        for msg in (
            "HTTP Error 429: Too Many Requests",
            "Video unavailable",
            "This video is private",
            "Sign in to confirm your age",          # 年龄限制，不是机器人校验
            "Unable to connect to proxy",           # 这是网络问题，另有分支
            "",
        ):
            with self.subTest(msg=msg):
                self.assertFalse(_is_bot_check(msg))

    def test_facts_recorded_for_later_agents(self):
        # 实测事实必须留在代码里当"别再试了"的凭据
        self.assertIn("watch_ok", BOT_CHECK_FACTS)
        self.assertEqual(BOT_CHECK_FACTS["client_variants_tried"], 7)
        self.assertIn("等待", BOT_CHECK_FACTS["remedy"])

    def test_po_token_recorded_as_tried_and_failed(self):
        """**PO Token 装过、测过、无效** —— 这条最贵，别让下一个人再装一遍。

        2026-10-04 真的装了 bgutil 2.0.1（git clone + npm ci + npx tsc，
        317 个包，起 HTTP server 确认 /ping 返回 2.0.1），两种模式都试：

            bgutil:script-node  失败视频仍 not a bot；能用的变成 no formats
            bgutil:http         失败视频仍 not a bot；能用的变成 no formats

        所以必须记下来，否则下一个人看到 "not a bot" 会理所当然地
        以为"装个 PO token 就行"，白花 10 分钟和一台 Node 环境。
        """
        self.assertIn("po_token", BOT_CHECK_FACTS)
        self.assertIn("无效", BOT_CHECK_FACTS["po_token"])
        # 实测定位到的状态码/状态也要记着
        self.assertEqual(BOT_CHECK_FACTS["http_status"], 200)
        self.assertEqual(BOT_CHECK_FACTS["playability"], "LOGIN_REQUIRED")


class TestBotCheckErrorType(unittest.TestCase):
    def test_is_risk_control_not_bare_runtimeerror(self):
        """核心断言：必须是 RiskControlError → 上层映射 429，而不是 500。"""
        err = _bot_check_error("njK0eebUsQw", "取评论")
        self.assertIsInstance(err, RiskControlError)
        # PlatformError 家族 → comments.py 的 isinstance 分支能接住
        self.assertIsInstance(err, PlatformError)
        # 不是"内容不存在"，也不是"网络问题"——处置方式完全不同
        self.assertNotIsInstance(err, ContentNotFoundError)
        self.assertNotIsInstance(err, NetworkError)
        # 风控**不该**被自动重试/降级（越试越糟）
        self.assertFalse(err.retryable)
        self.assertFalse(err.should_fallback)

    def test_message_states_real_cause_not_501_or_login_needed(self):
        msg = str(_bot_check_error("njK0eebUsQw", "取评论"))
        # 说了真话：是人机校验 + 按视频加严
        self.assertIn("人机校验", msg)
        self.assertIn("njK0eebUsQw", msg)          # 点名是哪个视频
        # 明确排除两种误读
        self.assertIn("不是\u300c视频不存在\u300d", msg)
        self.assertIn("不是\u300c必须登录才能看\u300d", msg)
        # 带上精确定位（HTTP 200 + LOGIN_REQUIRED）→ 说明不是连不上
        self.assertIn("LOGIN_REQUIRED", msg)
        # 带上"已试过无效"的清单，含 PO Token
        self.assertIn("PO Token", msg)
        # 给了可操作办法，而不是"未实现"
        self.assertIn("可行的办法", msg)
        # 不该出现的措辞
        self.assertNotIn("501", msg)
        self.assertNotIn("未实现", msg)


class TestBotCheckWiredIntoAllThreeCallSites(unittest.TestCase):
    """get_comments / get_detail / 搜索 三处都要处理。

    踩过的坑：只在评论里加判断 → 详情页照样 500，用户搜出结果点进去就炸。
    """

    def test_three_call_sites_guard(self):
        self.assertEqual(
            3, len(re.findall(r"if _is_bot_check\(msg\):", SRC)),
            "get_comments / get_detail / _extract_entries 三处都要判人机校验",
        )

    def test_unavailable_checked_before_bot_check_in_detail(self):
        """顺序有语义：同一视频可能同时报两者。

        "视频被删"（404，没救）必须排在 "被风控拦"（429，换 IP 有救）前面，
        否则会把"内容没了"错报成"等一等就好"。
        """
        detail = SRC[SRC.index("async def get_detail"):]
        detail = detail[: detail.index("async def search_users")]
        self.assertLess(
            detail.index("ContentNotFoundError"),
            detail.index("if _is_bot_check(msg):"),
            "get_detail 里 unavailable 判定必须排在 bot-check 前面",
        )

    def test_detail_also_guarded(self):
        """实测详情页与评论页是同一个失败（都走 extract_info(watch)）。"""
        detail = SRC[SRC.index("async def get_detail"):]
        self.assertIn("_is_bot_check", detail)


class TestCommentsApiMapsTo429(unittest.TestCase):
    def test_risk_control_maps_to_429(self):
        """comments.py 必须把 RiskControlError 映射成 429，不是裸 500。"""
        block = COMMENTS_SRC[COMMENTS_SRC.index("except Exception as exc:"):]
        block = block[block.index("isinstance(exc, RiskControlError)"):]
        self.assertIn("status_code=429", block[:400])

    def test_detail_message_kept_for_user(self):
        # 429 的提示语要让用户知道"等一等/换 IP"有救
        idx = COMMENTS_SRC.index("isinstance(exc, RiskControlError)")
        self.assertIn("稍等", COMMENTS_SRC[idx: idx + 400])


class TestMetaHonest(unittest.TestCase):
    def test_comments_capability_retained(self):
        """不能因为"有些视频取不到"就把 comments 能力删掉。

        实测 dQw4w9WgXcQ 能正常返回评论 → 能力存在，只是**不稳定**。
        删掉会让前端隐藏入口，用户连试的机会都没有。
        """
        meta = (Path(__file__).resolve().parents[1]
                / "app" / "services" / "platforms" / "youtube"
                / "meta.py").read_text(encoding="utf-8")
        self.assertIn('"comments"', meta)

    def test_meta_records_measured_numbers(self):
        self.assertIn("1/8", META_SRC)
        self.assertIn("4/4", META_SRC)
        # 必须写明 web_embedded/mweb 的副作用，防止有人再当后备方案
        self.assertIn("web_embedded", META_SRC)
        self.assertIn("副作用", META_SRC)
        # 必须写明详情页同样受影响
        self.assertIn("详情页", META_SRC)

    def test_meta_records_po_token_failed(self):
        """meta 也要记 PO Token 无效（meta 是下一个人第一眼看的地方）。"""
        self.assertIn("PO Token", META_SRC)
        self.assertIn("2.0.1", META_SRC)

    def test_meta_records_playability_diagnosis(self):
        """精确定位（HTTP 200 + LOGIN_REQUIRED）必须留档。

        这解释了**为什么不用再查连接/重定向/cookie** —— 页面是全的。
        """
        self.assertIn("LOGIN_REQUIRED", META_SRC)
        self.assertIn("1,298,628", META_SRC)   # 能取到的那个视频的实测大小


class TestRuntimeWiring(unittest.TestCase):
    """运行时验证：真的抛 RiskControlError 吗？（不是只匹配源码文本）"""

    def _client(self):
        from app.services.platforms.youtube.client import YoutubeClient
        from app.services.platforms.types import ClientConfig, ClientMode
        return YoutubeClient(ClientConfig(platform="youtube", mode=ClientMode.API))

    def test_get_comments_raises_risk_control(self):
        import asyncio
        import yt_dlp

        boom = ("ERROR: [youtube] njK0eebUsQw: Sign in to confirm you\u2019re "
                "not a bot. Use --cookies-from-browser or --cookies for the "
                "authentication.")

        real_extract = yt_dlp.YoutubeDL.extract_info

        def fake_extract(self, url, **kw):
            raise yt_dlp.utils.DownloadError(boom)

        c = self._client()
        with patch.object(yt_dlp.YoutubeDL, "extract_info", fake_extract):
            with self.assertRaises(RiskControlError) as cm:
                asyncio.get_event_loop().run_until_complete(
                    c.get_comments("njK0eebUsQw", max_results=5))
        self.assertIn("人机校验", str(cm.exception))
        self.assertIn("njK0eebUsQw", str(cm.exception))
        del real_extract

    def test_get_detail_raises_risk_control(self):
        import asyncio
        import yt_dlp

        boom = ("ERROR: [youtube] YQHsXMglC9A: Sign in to confirm you\u2019re not "
                "a bot. Use --cookies-from-browser or --cookies for the "
                "authentication.")

        def fake_extract(self, url, **kw):
            raise yt_dlp.utils.DownloadError(boom)

        c = self._client()
        with patch.object(yt_dlp.YoutubeDL, "extract_info", fake_extract):
            with self.assertRaises(RiskControlError) as cm:
                asyncio.get_event_loop().run_until_complete(
                    c.get_detail("YQHsXMglC9A"))
        self.assertIn("取详情", str(cm.exception))

    def test_unavailable_still_404_not_429(self):
        """反向验证：视频被删**不能**被误报成风控。"""
        import asyncio
        import yt_dlp

        def fake_extract(self, url, **kw):
            raise yt_dlp.utils.DownloadError(
                "ERROR: [youtube] BaW_jenozKc: This video is unavailable")

        c = self._client()
        with patch.object(yt_dlp.YoutubeDL, "extract_info", fake_extract):
            with self.assertRaises(ContentNotFoundError):
                asyncio.get_event_loop().run_until_complete(
                    c.get_detail("BaW_jenozKc"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
