"""Telegram 公开频道解析器回归测试（离线，不需要网络）。

## 为什么要"离线"测试解析器

网络（VPN）随时会断，但**解析逻辑的正确性不该依赖网络**。
用构造的 HTML 覆盖各种结构，保证：
  · 选择器写对了（尤其是 `f".{SEL}"` 拼接那类坑）
  · 边界情况（空页、私有频道、无消息容器）能正确区分

真实网络抓取另有一套实测（需要 VPN），见 `docs/platform/TELEGRAM_GUIDE.md`。
"""

from __future__ import annotations

import pytest


# =============================================================================
# 计数 / 时长解析
# =============================================================================

@pytest.mark.parametrize("raw,want", [
    ("1.2K", 1200), ("3.4M", 3400000), ("123", 123), ("1,234", 1234),
    ("2.5B", 2500000000), ("abc", 0), ("", 0), ("1.2K views", 1200),
])
def test_parse_views(raw, want):
    """浏览量：Telegram 显示 '1.2K' / '3.4M'，要转成整数。

    解析不出时返回 **0**（不猜）—— 把'解析失败'伪装成数字更糟。
    """
    from app.services.platforms.telegram.parser import _parse_views

    assert _parse_views(raw) == want


@pytest.mark.parametrize("raw,want", [
    ("1:23", 83), ("1:02:03", 3723), ("0:45", 45), ("xx", 0), ("", 0),
])
def test_parse_duration(raw, want):
    from app.services.platforms.telegram.parser import _parse_duration

    assert _parse_duration(raw) == want


# =============================================================================
# ⚠️ 选择器拼接坑（真实踩到过）
# =============================================================================

def test_selectors_are_bare_class_names():
    """**回归（关键）**：`SEL_*` 常量必须是**纯 class 名**，不带标签前缀。

    ## 踩到的 bug（2026-10-01）

    原来 `SEL_MSG_TEXT = "div.tgme_widget_message_text"`，
    而使用处是 `el.select_one(f".{SEL_MSG_TEXT}")` ——
    拼出来是 **`".div.tgme_widget_message_text"`**，
    **不是合法 CSS 选择器**，`select_one` 永远返回 `None`。

    后果：**每条消息的正文都是空字符串**，而且**不报错** ——
    测试里没断言正文就没拦住（我第一版正是漏了断言）。

    判据：会被 `f".{X}"` 拼的常量，不能含 `.` 或标签名。
    """
    from app.services.platforms.telegram import parser as p

    # 这些常量在代码里是 f".{SEL_XXX}" 用的
    for name in ("SEL_CHANNEL_TITLE", "SEL_CHANNEL_DESC", "SEL_CHANNEL_COUNTER",
                 "SEL_CHANNEL_AVATAR", "SEL_MSG_TEXT", "SEL_MSG_AUTHOR",
                 "SEL_MSG_FORWARD"):
        val = getattr(p, name)
        assert "." not in val, (
            f"{name} = {val!r} 含 '.' —— 被 f'.{{}}' 拼接后会变成非法选择器，"
            "导致永远选不到元素（静默返回空）"
        )
        assert " " not in val, f"{name} 不该含空格（会被当成后代选择器）"


def test_text_extraction_keeps_content():
    """**回归**：正文要真的取到（不是空串）。

    这条就是上面那个 bug 的守门人 —— 用最小 HTML 断言正文非空。
    """
    from bs4 import BeautifulSoup

    from app.services.platforms.telegram.parser import _text_of

    soup = BeautifulSoup(
        '<div class="tgme_widget_message_text">第一条<b>消息</b></div>', "lxml")
    el = soup.select_one(".tgme_widget_message_text")
    assert _text_of(el) == "第一条消息"


def test_text_extraction_drops_emoji_css():
    """emoji 是 `background-image` 实现 —— 不能把 CSS 混进正文。

    实测 Telegram 的 emoji 形如：
        <i class="emoji" style="background-image:url('//emoji.png')"></i>
    """
    from bs4 import BeautifulSoup

    from app.services.platforms.telegram.parser import _text_of

    soup = BeautifulSoup(
        '<div class="tgme_widget_message_text">'
        'Hello <i class="emoji" style="background-image:url(\'//e.png\')"></i> world'
        '</div>', "lxml")
    txt = _text_of(soup.select_one(".tgme_widget_message_text"))
    assert "emoji.png" not in txt and "background-image" not in txt
    assert "Hello" in txt and "world" in txt


# =============================================================================
# 整页解析
# =============================================================================

CHANNEL_PAGE = """
<html><body>
<div class="tgme_channel_info">
  <div class="tgme_channel_info_header_title">Tech News</div>
  <div class="tgme_channel_info_description">最新科技资讯<br>每日更新</div>
  <div class="tgme_channel_info_counter">
    <span class="counter_value">1.2K</span><span class="counter_type">subscribers</span>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="technews/101">
    <div class="tgme_widget_message_bubble">
      <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.example.com/p1.jpg')"></a>
      <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.example.com/p2.jpg')"></a>
      <div class="tgme_widget_message_text js-message_text">第一条<b>消息</b></div>
      <span class="tgme_widget_message_views">1.5K</span>
      <time datetime="2026-01-02T03:04:05+00:00"></time>
    </div>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="technews/102">
    <div class="tgme_widget_message_bubble">
      <a class="tgme_widget_message_video_player" style="background-image:url('https://cdn.example.com/v1.jpg')">
        <video src="https://cdn.example.com/v1.mp4" poster="https://cdn.example.com/v1p.jpg"></video>
        <time class="message_video_duration">3:07</time>
      </a>
      <div class="tgme_widget_message_text js-message_text">第二条带视频</div>
      <span class="tgme_widget_message_views">800</span>
      <time datetime="2026-01-01T00:00:00+00:00"></time>
    </div>
  </div>
</div>
</body></html>
"""


def test_parse_channel_page_full():
    """整页解析：频道信息 + 多图消息 + 视频消息。"""
    from app.services.platforms.telegram.parser import parse_channel_page

    info, msgs = parse_channel_page(CHANNEL_PAGE)
    assert info.title == "Tech News"
    assert info.description.startswith("最新科技资讯")
    assert info.subscribers == 1200
    assert len(msgs) == 2

    m1, m2 = msgs
    # 多图：两个 photo_wrap → 两张图
    assert m1.id == "101" and m1.channel == "technews"
    assert len(m1.images) == 2
    assert m1.views == 1500
    assert m1.text == "第一条消息"
    assert m1.content_type == "image"

    # 视频：直链 + 封面 + 时长
    assert m2.id == "102"
    assert m2.video == "https://cdn.example.com/v1.mp4"
    assert m2.duration == 187
    assert m2.text == "第二条带视频"
    assert m2.content_type == "video"


def test_message_page_url():
    """消息要能拼出网页地址（前端"看原文"用）。"""
    from app.services.platforms.telegram.parser import parse_channel_page

    _, msgs = parse_channel_page(CHANNEL_PAGE)
    assert msgs[0].page_url() == "https://t.me/technews/101"


def test_structure_change_detection():
    """**回归**：要能区分"频道没消息"和"页面结构变了"。

    本仓库铁律：静默返回空会把"解析器失效"伪装成"频道是空的"。
    """
    from app.services.platforms.telegram.parser import detect_structure_change

    # 正常页 → 无异常
    assert detect_structure_change(CHANNEL_PAGE) is None
    # 空内容 → 报网络/代理问题
    assert detect_structure_change("") is not None
    # 有页面但没消息容器 → 报私有/不存在/改版
    r = detect_structure_change(
        '<html><body><div class="tgme_page_title">X</div></body></html>')
    assert r is not None and ("私有" in r or "改" in r)


# =============================================================================
# 频道名归一化
# =============================================================================

@pytest.mark.parametrize("raw,want", [
    ("durov", "durov"),
    ("@durov", "durov"),
    ("https://t.me/durov", "durov"),
    ("https://t.me/s/durov", "durov"),
    ("t.me/durov/123", "durov"),
    ("https://telegram.me/durov", "durov"),
])
def test_normalize_channel(raw, want):
    """用户会粘各种形态的链接 —— 都要能归一成 username。"""
    from app.services.platforms.telegram.web_preview import normalize_channel

    assert normalize_channel(raw) == want


@pytest.mark.parametrize("bad", ["+abc123", "", "https://t.me/joinchat/xxx", "a b"])
def test_normalize_channel_rejects_bad_input(bad):
    """非法输入要**可操作报错**，不静默返回空。"""
    from app.services.platforms.telegram.web_preview import (
        TelegramPublicError,
        normalize_channel,
    )

    with pytest.raises(TelegramPublicError):
        normalize_channel(bad)


def test_private_invite_link_message_is_actionable():
    """私有频道的邀请链接要明确告诉用户"需要登录"，而不是笼统失败。"""
    from app.services.platforms.telegram.web_preview import (
        TelegramPublicError,
        normalize_channel,
    )

    with pytest.raises(TelegramPublicError) as ei:
        normalize_channel("https://t.me/+AbCdEf123")
    msg = str(ei.value)
    assert "私有" in msg and "登录" in msg
