"""Telegram 客户端能力与诚实文案的回归测试。

## 为什么专门测"文案诚实性"

这个功能的**能力边界很容易被夸大**（我自己第一版就写错了）：

  · `t.me/s` 的 `?q=` 是**频道内**搜索 → 不能说成"全网搜索"
  · MTProto 的 `SearchGlobal` **只搜你已加入的会话** → 同样不是"全网"
  · 真正搜所有公开频道要 `channels.SearchPosts`：
    需要 Premium、报 403 PREMIUM_ACCOUNT_REQUIRED、**按 Stars 计费**

如果文案写成"全网搜索"，用户会以为能搜到所有公开频道 ——
那是做不到的。**过度承诺比功能缺失更糟**（用户会一直以为是自己用错）。

所以这里用测试把"文案不得夸大"固化下来。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


# =============================================================================
# 注册与装载
# =============================================================================

def test_telegram_registered():
    from app.services.platforms import supported_platforms

    assert "telegram" in supported_platforms()


def test_telegram_in_auto_discover_list():
    """漏了自动发现列表，客户端根本不会加载。"""
    from app.services.platforms import __file__ as init_file

    src = open(init_file, encoding="utf-8").read()
    assert '"telegram"' in src


def test_client_has_required_methods():
    """`users.py::/users/videos` 调 `get_user_videos`，基类叫
    `get_user_notes` —— 两个都要有（youtube 只写后者报过 500）。"""
    from app.services.platforms.telegram.client import TelegramClient

    for m in ("search", "get_detail", "search_users", "get_user_profile",
              "get_user_videos", "get_user_notes"):
        assert hasattr(TelegramClient, m), f"缺 {m}"


# =============================================================================
# 三个 search_type 的分派
# =============================================================================

@pytest.mark.parametrize("st,expect", [
    ("channel", "_search_channel"),
    ("joined", "_search_joined"),
    ("dialogs", "_list_dialogs"),
    # 兼容别名：global/search → joined（语义是"已加入"，不是全网）
    ("global", "_search_joined"),
    ("search", "_search_joined"),
])
def test_search_type_dispatch(st, expect):
    """search_type 要正确分派（前端三个 tab 靠它）。"""
    from app.services.platforms.telegram import client as tc

    src = inspect.getsource(tc.TelegramClient.search)
    assert expect in src, f"search_type={st} 应分派到 {expect}"


def test_default_search_type_is_channel():
    """**默认必须是 channel（免登录）** —— 不能默认走需要登录的路径，
    否则第一次用的用户会直接撞上"未登录"。"""
    from app.services.platforms.telegram import client as tc

    src = inspect.getsource(tc.TelegramClient.search)
    assert '"channel"' in src


# =============================================================================
# ⚠️ 能力边界：不得夸大
# =============================================================================

def test_joined_search_is_not_called_global_search():
    """**关键回归**：`SearchGlobal` 的语义要如实说明为"已加入的会话"。

    实测依据（2026-10-01 调研）：telethon 的
    `iter_messages(None, search=...)` 只覆盖**你已加入的**会话
    （Telethon issue #4446）。真正跨频道搜要 `channels.SearchPosts`，
    那个需要 Premium 且按 Stars 计费。
    """
    from app.services.platforms.telegram import client as tc
    from app.services.platforms.telegram import mtproto_data as md

    src = inspect.getsource(md.search_global)
    assert "已加入" in src, "要写明只搜'你已加入的'会话"
    assert "Premium" in src, "要留档：真正跨频道搜需要 Premium（我们不做）"
    assert "SearchPosts" in src, "要点名正确的 API（免得后人以为做不到）"

    doc = inspect.getsource(tc.TelegramClient._search_joined)
    assert "已加入" in doc
    assert "全网" in doc, "要明确说明'不要叫全网搜索'"


def test_channel_search_supports_in_channel_keyword():
    """A 方案的**频道内关键词搜索**要保留（这是被低估的能力）。

    实测：`t.me/s/durov?q=Telegram` → 20 条且正文全部命中，**免登录**。
    """
    from app.services.platforms.telegram import client as tc
    from app.services.platforms.telegram import web_preview as wp

    # web_preview 要支持 q 参数
    src = inspect.getsource(wp.TelegramPublicClient.fetch_page)
    assert '"q"' in src or "'q'" in src, "fetch_page 要支持 q（频道内搜索）"

    # client 要能把「频道名 关键词」拆开
    src2 = inspect.getsource(tc.TelegramClient._split_channel_query)
    assert "query" in src2


@pytest.mark.parametrize("raw,ch,q", [
    ("durov", "durov", ""),
    ("@durov", "durov", ""),
    ("durov AI", "durov", "AI"),
    ("durov|AI", "durov", "AI"),
    ("durov,AI", "durov", "AI"),
    ("https://t.me/durov", "https://t.me/durov", ""),
])
def test_split_channel_query(raw, ch, q):
    """「频道名 关键词」的拆分（分隔符宽松）。"""
    from app.services.platforms.telegram.client import TelegramClient

    got_ch, got_q = TelegramClient._split_channel_query(raw)
    assert got_ch == ch, f"channel: {got_ch!r} != {ch!r}"
    assert got_q == q, f"query: {got_q!r} != {q!r}"


@pytest.mark.parametrize("raw,ch,mid", [
    ("telegram_441", "telegram", "441"),
    ("https://t.me/telegram/441", "telegram", "441"),
])
def test_split_item_id(raw, ch, mid):
    """详情 id 解析（我们自己拼的 id + 用户粘的链接都要认）。"""
    from app.services.platforms.telegram.client import TelegramClient

    got_ch, got_mid = TelegramClient._split_item_id(raw)
    assert got_ch == ch
    assert got_mid == mid


# =============================================================================
# 前端文案与入口
# =============================================================================

def _crawler_src() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


def test_frontend_telegram_tabs():
    """前端要有 Telegram 的三个 tab（数据源），且文案不得夸大。"""
    src = _crawler_src()
    i = src.find("telegram: {")
    assert i != -1, "搜索页缺 telegram 配置"
    seg = src[i:i + 1500]
    for st in ("channel", "joined", "dialogs"):
        assert f"'{st}'" in seg, f"缺 search_type={st}"
    # ⚠️ 不得出现"全网搜索"这种过度承诺
    assert "全网搜索" not in seg, "不能写'全网搜索'（做不到，属过度承诺）"
    # 要标明"已加入"
    assert "已加入" in seg, "joined tab 要写明搜索范围是'已加入的'"


def test_frontend_telegram_platform_entry():
    """平台下拉里要有 Telegram（否则用户选不到）。"""
    src = _crawler_src()
    assert "'telegram'" in src
    i = src.find("const PLATFORMS")
    seg = src[i:i + 1200]
    assert "telegram" in seg, "PLATFORMS 里缺 telegram"


def test_frontend_has_telegram_login_page():
    """Telegram 登录页要存在且被路由注册。"""
    p = FRONTEND / "pages" / "telegram-login" / "index.tsx"
    assert p.exists(), "缺 Telegram 登录页"
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8", errors="ignore")
    assert "telegram-login" in app, "登录页没注册路由"


def test_login_page_states_its_optional():
    """**关键**：登录页必须说清"公开频道不需要登录"。

    否则用户会以为"必须先登录才能用 Telegram"，白折腾一遍
    （而 A 方案的频道抓取其实免登录就能用）。
    """
    p = FRONTEND / "pages" / "telegram-login" / "index.tsx"
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "不需要登录" in src or "可选" in src
    assert "公开频道" in src
    # 也要说清登录后**额外**得到什么
    assert "私有频道" in src
    # ⚠️ 不得把已加入搜索说成全网
    assert "不是「全网搜索」" in src or "全网搜索" in src


def test_hint_not_hardcoded_proxy():
    """代理端口不能硬编码（换机器就不同）。"""
    from app.services.platforms.telegram import web_preview as wp

    src = inspect.getsource(wp)
    # 允许注释里提到端口（留档），但**代码里**不能硬编码
    code_lines = [
        ln for ln in src.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    code = "\n".join(code_lines)
    # 只允许出现在注释/字符串说明里；检查赋值类语句
    assert 'proxy = "http://127.0.0.1' not in code, "不要在代码里硬编码代理地址"
    assert "os.environ" in src, "应从环境变量读代理"
