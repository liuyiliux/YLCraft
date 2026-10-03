"""Telegram 频道名校验的回归测试（2026-10-03）。

## 用户反馈

界面上搜「美女」被直接拒绝：

    频道名 '美女' 看起来不合法（只允许字母/数字/下划线，4-64 位）。
    请检查输入，或直接查找视频号连接。这不是**平台侧拒绝**（触发风控或人机验证），
    不是「没搜到」。

## 为什么这个拦截是错的

### 1. 它把"未知"当成"非法"

实测（2026-10-03）：Telegram 对**不存在的频道**返回 **HTTP 200**
+ telegram.org 主页壳（~19KB，**零个 `tgme_*` 元素**）。
中文 username 与乱填的 username 返回的页面**完全同构**（都是 19854 字节）：

    t.me/s/美女              19854 字节  是频道页=False
    t.me/s/zzz_nonexist_9x8k2 9744 字节  是频道页=False
    t.me/s/durov            145600 字节  是频道页=True

**状态码和页面长度都区分不了真假**，唯一判据是 `tgme_channel_info` 在不在
（`web_preview.py` 文件头第 2 条早就实测记录了这一点）。
既然唯一判据在网络那一侧，就该**让它去问**，而不是本地正则先猜。

### 2. 它拦错了对象

Telegram 的 **username** 确实只允许 `A-Za-z0-9_`（平台规则）。
但用户在客户端里**用中文搜频道**搜的是**标题**，走另一条路径，
不经过 `t.me/s/<username>` —— 所以不受该规则约束。

也就是说"中文"在这个端点上**是搜索词，不是 username**。
我们拿不到"按标题搜频道"的能力（那是 MTProto 的活），
但也**不该用本地正则冒充平台的判断**，更不该说"你打错了"。

## 修法

删掉 ASCII 正则，只拦**明显畸形**的形态（过长 / 含空格、控制字符），
其余放行给 `channel_exists()` 判定 —— 让唯一的判据真正发挥作用。
"""
from __future__ import annotations

import pytest

from app.services.platforms.telegram.web_preview import (
    TelegramPublicError,
    normalize_channel,
)

# 真实存在的公开频道（实测 2026-10-03 均有内容）
REAL = ["durov", "xueqiu", "tgstat"]


# =============================================================================
# 不能再拦的输入
# =============================================================================

def test_chinese_name_is_not_rejected_locally():
    """中文频道名必须能过本地校验（交给网络侧判定）。"""
    assert normalize_channel("美女") == "美女"


@pytest.mark.parametrize("name", ["美女", "韩国日报", "A股", "东京", "café"])
def test_unicode_names_pass(name: str):
    """各种非 ASCII 输入都不该被本地正则拦下。"""
    assert normalize_channel(name) == name


def test_short_names_pass():
    """短名（<4 位）不该被"4-64 位"的规则拒掉。"""
    assert normalize_channel("ab") == "ab"
    assert normalize_channel("x") == "x"


def test_ascii_usernames_still_work():
    """正常 username + 各种链接形态必须照常归一（不能改坏）。"""
    assert normalize_channel("durov") == "durov"
    assert normalize_channel("@durov") == "durov"
    assert normalize_channel("https://t.me/durov") == "durov"
    assert normalize_channel("https://t.me/s/durov") == "durov"
    assert normalize_channel("t.me/durov/123") == "durov"
    assert normalize_channel("https://telegram.me/durov") == "durov"


def test_case_is_preserved():
    """大小写必须保留（实测 data-post 里有 `TGStat/468` 这种大写 T）。"""
    assert normalize_channel("TGStat") == "TGStat"


@pytest.mark.parametrize("raw", [REAL[0], REAL[1], REAL[2]])
def test_real_channels_normalize(raw: str):
    for r in REAL:
        assert normalize_channel(r) == r


# =============================================================================
# 仍该被拦的（明显畸形）
# =============================================================================

def test_empty_rejected():
    with pytest.raises(TelegramPublicError):
        normalize_channel("")


@pytest.mark.parametrize("bad", ["a b", "du rov", "名字 空格", "a\tb", "a\nb"])
def test_whitespace_rejected(bad: str):
    """含空白的输入会构造出畸形 URL，仍该拦。"""
    with pytest.raises(TelegramPublicError):
        normalize_channel(bad)


def test_too_long_rejected():
    with pytest.raises(TelegramPublicError):
        normalize_channel("A" * 100)


def test_private_invite_rejected():
    """私有邀请链接公开预览页看不了（要给出可操作提示）。"""
    with pytest.raises(TelegramPublicError) as e:
        normalize_channel("+AbCdEf")
    assert "私有" in str(e.value)


def test_joinchat_rejected():
    with pytest.raises(TelegramPublicError) as e:
        normalize_channel("https://t.me/joinchat/AAAA")
    assert "私有" in str(e.value)


# =============================================================================
# 源码层：ASCII 正则不得复活
# =============================================================================

def test_no_ascii_username_regex_in_source():
    """`^[A-Za-z0-9_]{4,64}$` 这类正则不得重新引入。

    它会把"未知"当"非法"，抢在唯一判据（`tgme_channel_info`）前面下结论。
    """
    import pathlib
    f = (pathlib.Path(__file__).resolve().parents[1]
         / "app" / "services" / "platforms" / "telegram" / "web_preview.py")
    src = f.read_text(encoding="utf-8")
    # 去掉注释后再找（注释里可以引用旧代码说明历史）
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.strip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "A-Za-z0-9_" not in code, (
        "又出现了 ASCII username 正则 —— 中文会被本地拦下，"
        "而真实判据（tgme_channel_info）在网络那一侧"
    )


def test_error_message_points_to_the_right_way():
    """含空白的报错要指明出路（复制频道链接），而不是只说"不合法"。"""
    with pytest.raises(TelegramPublicError) as e:
        normalize_channel("a b")
    msg = str(e.value)
    assert "https://t.me/" in msg, "报错要给出正确示例链接"
    assert "标题" in msg, "应区分 username 与频道标题（中文搜的是标题）"
