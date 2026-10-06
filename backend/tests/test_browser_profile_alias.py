# -*- coding: utf-8 -*-
"""别名必须共用同一份登录态（2026-10-06 用户实测踩到后修）。

## 故障现象

用户在前端搜微博（**前端传的是别名 `wb`**），日志：

    [persistent] 启动持久化 profile platform=wb  dir=...\browser_profiles\wb
    [weibo] 搜索 '沈阳' -> **0 条**（翻了 1 页）

换成正式名 `weibo` 同一个关键词：

    [persistent] 启动持久化 profile platform=weibo dir=...\browser_profiles\weibo
    [weibo] 搜索 '沈阳' -> 30 条

## 根因

`profile_dir_for(platform)` 直接拿平台名当目录名，于是

    browser_profiles/wb/      ← 空的（没登录过）
    browser_profiles/weibo/   ← 登录态在这里

**同一个平台两个目录，等于没有登录态。**

## ⚠️ 为什么这个 bug 潜伏了很久

移动版 `m.weibo.cn` **访客态也能凑出 9 条** —— 看起来"能搜"，
所以别名带来的空目录没人发现。

2026-10-06 搜索改走桌面版 `s.weibo.com`，而桌面版**必须登录**才能搜，
潜伏问题才暴露成"搜不到任何东西"。

⇒ 教训：**一个"看起来能用"的降级路径，会把真正的配置错误藏很久。**
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.browser.persistent_profile import (  # noqa: E402
    canonical_platform, profile_dir_for,
)


class TestAliasResolvesToCanonicalName(unittest.TestCase):
    """别名 → 正式名。"""

    def test_weibo_alias(self):
        self.assertEqual("weibo", canonical_platform("wb"))

    def test_other_aliases(self):
        for alias, full in (
            ("xhs", "xiaohongshu"),
            ("dy", "douyin"),
            ("ks", "kuaishou"),
            ("bili", "bilibili"),
            ("tw", "twitter"),
            ("x", "twitter"),
        ):
            with self.subTest(alias=alias):
                self.assertEqual(full, canonical_platform(alias))

    def test_canonical_name_unchanged(self):
        """正式名传进来要**原样返回** —— 归一只处理别名。"""
        for name in ("weibo", "douyin", "xiaohongshu"):
            with self.subTest(name=name):
                self.assertEqual(name, canonical_platform(name))

    def test_case_insensitive(self):
        self.assertEqual("weibo", canonical_platform("WB"))
        self.assertEqual("weibo", canonical_platform("Weibo"))

    def test_unknown_passes_through(self):
        """⚠️ 未知平台**不抛错** —— 这里只是拼个目录名。

        新增平台时不该被这里卡住。
        """
        self.assertEqual("newplatform", canonical_platform("newplatform"))
        self.assertEqual("", canonical_platform(""))

    def test_weird_input_does_not_raise(self):
        for bad in ("../etc", "a/b", "  ", "!!!", "微博"):
            with self.subTest(value=bad):
                self.assertIsInstance(canonical_platform(bad), str)


class TestProfileDirIsSharedByAliases(unittest.TestCase):
    """⭐ 这才是真正的回归点：别名与正式名**必须指向同一个目录**。"""

    def test_wb_and_weibo_same_dir(self):
        """用户实测踩到的那个 bug。"""
        self.assertEqual(
            profile_dir_for("weibo"), profile_dir_for("wb"),
            "别名 wb 必须与正式名 weibo 共用同一份登录态，"
            "否则会建出第二个空 profile，表现为'明明登录了却搜不到'",
        )

    def test_other_aliases_same_dir(self):
        for alias, full in (
            ("xhs", "xiaohongshu"),
            ("dy", "douyin"),
            ("ks", "kuaishou"),
            ("bili", "bilibili"),
            ("tw", "twitter"),
        ):
            with self.subTest(alias=alias):
                self.assertEqual(profile_dir_for(full), profile_dir_for(alias))

    def test_different_platforms_still_differ(self):
        """⚠️ 归一不能过头 —— 微博和小红书**必须**是两个目录。

        合到一起会导致两个站点共用一份 cookie，既不安全也不工作。
        """
        self.assertNotEqual(profile_dir_for("weibo"), profile_dir_for("xiaohongshu"))
        self.assertNotEqual(profile_dir_for("wb"), profile_dir_for("xhs"))

    def test_dir_name_is_canonical(self):
        self.assertEqual("weibo", profile_dir_for("wb").name)
        self.assertEqual("weibo", profile_dir_for("weibo").name)

    def test_path_traversal_still_blocked(self):
        """归一**不能削弱**原有的非法字符过滤。"""
        d = profile_dir_for("../../evil")
        self.assertNotIn("..", d.name)
        self.assertTrue(d.exists())


class TestSessionPoolKeyUsesCanonicalName(unittest.TestCase):
    """池 key 也必须用正式名。

    ⚠️ 不然 `wb|<conn>` 与 `weibo|<conn>` 是**两个不同的 key 指向同一个
    profile 目录** —— Chromium 的 profile 锁会打架，登录态表现随机
    （一会儿能用一会儿不能用，最难查的那种故障）。
    """

    def test_base_uses_canonical_name(self):
        import inspect

        from app.services.platforms import base
        src = inspect.getsource(base.BasePlatformClient._init_patchright)
        self.assertIn(
            "canonical_platform", src,
            "池 key 必须用正式名（2026-10-06 修：wb 与 weibo 曾是两个 key）",
        )
        self.assertNotIn(
            'session_key = f"{self.config.platform}|', src,
            "不能直接用 config.platform 当 key（别名会分裂成两个 key）",
        )

    def test_cookie_manager_uses_canonical_name(self):
        """采集登录态那条路也要 —— 否则登录态存在 wb 目录、搜索读 weibo 目录。"""
        import inspect

        from app.services.cookies import patchright_manager
        src = inspect.getsource(patchright_manager)
        self.assertIn("canonical_platform", src,
                      "采集登录态必须写进正式名目录")


class TestCookieDomainsCoverDesktopSite(unittest.TestCase):
    """⭐ 第二个 bug：cookie 种错域（2026-10-06，用户实测 0 条）

    日志当时打了 `[wb] Cookies set to browser` ——
    **那句话在骗人**：cookie 确实种了，但只种到 `.weibo.cn`，
    而桌面版搜索是 `s.weibo.com`，一个 cookie 都收不到。

    ⇒ "无异常"不等于"生效了"。这比第一个 bug 更隐蔽。
    """

    def _client(self, platform):
        from app.services.platforms.types import ClientConfig, ClientMode
        from app.services.platforms.weibo.client import WeiboClient
        return WeiboClient(ClientConfig(
            platform=platform, mode=ClientMode.API, cookie="SUB=x; SUBP=y",
        ))

    def test_weibo_declares_no_single_domain(self):
        """返回单个域就意味着"只种那一个" —— 必须让它回退到多域。"""
        c = self._client("weibo")
        self.assertIsNone(
            c._get_platform_domain(),
            "微博必须返回 None 走多域分支：桌面版 s.weibo.com 不在 .weibo.cn 下",
        )

    def test_domains_include_desktop_site(self):
        for plat in ("weibo", "wb"):
            with self.subTest(platform=plat):
                domains = self._client(plat)._cookie_domains()
                self.assertIn(
                    ".weibo.com", domains,
                    "⭐ 必须种到 .weibo.com —— 桌面版搜索在 s.weibo.com，"
                    "漏了它就是'cookie 都在但一个都收不到'",
                )
                self.assertIn(".weibo.cn", domains,
                              "m 站的登录态也要留着（详情/我的数据走它）")

    def test_domain_table_has_both_names_for_xiaohongshu(self):
        """⚠️ 那张表原本用别名 `xhs` 当键，归一成正式名后会查空。

        小红书自己声明了 `_get_platform_domain()` 所以暂时没暴露，
        但表本身的不一致是个雷 —— 任何走多域分支的平台都会中招。
        """
        from app.services.cookies.base import PLATFORM_DOMAINS
        from app.services.browser.persistent_profile import canonical_platform
        for name in PLATFORM_DOMAINS:
            with self.subTest(platform=name):
                self.assertTrue(
                    PLATFORM_DOMAINS.get(canonical_platform(name)),
                    f"{name} 归一后查不到域名表 → cookie 种不进去",
                )

    def test_other_platforms_still_get_domains(self):
        """⚠️ 改动共用层，必须确认**没有把别的平台弄坏**。"""
        from app.services.platforms.types import ClientConfig, ClientMode
        from app.services.platforms.xiaohongshu.client import XiaohongshuClient
        from app.services.platforms.douyin.client import DouyinClient
        from app.services.platforms.twitter.client import TwitterClient

        for cls, plat in (
            (XiaohongshuClient, "xhs"),
            (DouyinClient, "douyin"),
            (TwitterClient, "twitter"),
        ):
            with self.subTest(platform=plat):
                c = cls(ClientConfig(
                    platform=plat, mode=ClientMode.API, cookie="a=b",
                ))
                domains = c._cookie_domains()
                self.assertTrue(domains, f"{plat} 不该拿到空域名列表")


if __name__ == "__main__":
    unittest.main(verbosity=2)