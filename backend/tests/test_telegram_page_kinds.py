"""Telegram「拿不到内容」四类页面的判别测试（2026-10-03）。

## 为什么加这个

用户截图报：`@kshelfs` 搜出来报

    页面里既没有频道信息也没有消息容器 —— 通常是 **Telegram 改了页面结构**
    （解析器需要更新）

**但 `@kshelfs` 真实存在**（涩涩深夜研讨会，5032 名订阅者）。
它只是 **Telegram 没开放该频道的网页端消息列表** ——
`t.me/s` 只返回一个「Download / Preview channel」页，零个
`tgme_channel_info` / `tgme_widget_message`。

把"平台没开放"报成"我们的解析器坏了"，方向完全反了。

## 实测：四类页面特征**互斥**（2026-10-03）

| 形态 | 特征标志 | 样本 | 长度 |
|---|---|---|---|
| 正常频道页 | `tgme_channel_info` + `tgme_widget_message` | `durov` | 145601B |
| **仅预览页（频道存在）** | `tgme_page_title` + `Preview channel` | **`kshelfs`** | 12313B |
| 用户名不存在 | `tgme_username` / `Contact @xxx` | `zzz_nonexist_9x8k2` | 9744B |
| telegram.org 主页壳 | 以上都没有 | `美女`（中文） | 19854B |

## 这些断言锁住
  1. 「仅预览页」必须有**独立**判据与独立文案（不能再混进"结构变化"）
  2. 四类判据互斥（否则会误判）
  3. 每类文案都要有可操作出路，不能只说"失败了"
"""
from __future__ import annotations

from pathlib import Path

import pytest

PARSER = (
    Path(__file__).resolve().parents[1]
    / "app" / "services" / "platforms" / "telegram" / "parser.py"
)


def _src() -> str:
    if not PARSER.exists():
        pytest.skip("telegram parser not found")
    return PARSER.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 判据存在且互斥
# =============================================================================

def _preview_branch() -> str:
    """抽出**代码里**的「仅预览页」分支（不是 docstring 里那张表）。

    ⚠️ 必须找 `if "tgme_page_title" in low`（判断语句），
    而不是第一个出现的 `tgme_page_title` —— 那在 docstring 的对照表里，
    取到的是表格片段，不是逻辑（第一版就因此测错了对象）。
    """
    src = _src()
    marker = 'if "tgme_page_title" in low'
    i = src.find(marker)
    assert i > 0, "代码里找不到「仅预览页」的判断分支"
    return src[i:i + 1600]


def test_preview_only_page_has_own_branch():
    """「仅预览页」必须有独立判据（tgme_page_title + preview channel）。"""
    src = _src()
    assert "tgme_page_title" in src, "缺少「仅预览页」的判据"
    assert "preview channel" in src, "缺少 'Preview channel' 特征串"


def test_four_page_markers_are_documented():
    """四类页面的判据与样本必须写进 docstring（可复现的实测记录）。"""
    src = _src()
    for marker in ("tgme_channel_info", "tgme_page_title", "tgme_username"):
        assert marker in src, f"判据 {marker} 未记录"
    for sample in ("kshelfs", "durov", "zzz_nonexist"):
        assert sample in src, (
            f"样本 {sample} 未记录 —— 平台行为会变，实测依据必须留在代码里"
        )


# =============================================================================
# 文案必须诚实
# =============================================================================

def test_preview_page_not_reported_as_structure_change():
    """「仅预览页」不能说成"页面结构变了"（那是误导：频道好好的）。"""
    seg = _preview_branch()
    # 关键：不能把"结构变化 / 解析器需更新"当作该分支的**结论**
    for ln in seg.split("return")[-1].splitlines()[:6]:
        assert "解析器需要更新" not in ln, (
            f"仅预览页的结论里出现『解析器需要更新』—— 会误导用户去改没坏的代码：{ln.strip()[:60]!r}"
        )
    assert "没有开放" in seg, "应说清『Telegram 没开放该频道的网页端消息』"


def test_preview_page_error_offers_client_path():
    """仅预览页要给出出路（去客户端看 / 登录后用「我的频道」）。"""
    seg = _preview_branch()
    assert "客户端" in seg, "应建议去客户端查看（该频道在 App/Desktop 能看）"
    assert "我的频道" in seg, "应提示登录后可用「我的频道」读取"


def test_chinese_title_hint_comes_first():
    """主页壳分支：中文提示要放在**前面**。

    用户输入中文时第一眼看到的就是首行 ——
    原来首行说"页面结构变了（解析器需要更新）"，把平台限制说成我们的 bug。
    """
    src = _src()
    # 找最后的兜底 return（主页壳分支）
    idx = src.rfind("拿不到这个地址的内容")
    assert idx > 0, "找不到主页壳分支的文案"
    seg = src[idx:idx + 900]
    assert "频道标题" in seg, "主页壳分支应先说明「可能是输入了频道标题」"
    # 首行就该提标题，而不是"页面结构变了"
    head = seg.split("\n")[0]
    assert "页面结构变了" not in head and "解析器" not in head, (
        f"首行不该先说『页面结构变了』：{head[:60]!r}"
    )


def test_username_hint_points_to_copying_link():
    """所有"搜不到"分支都要给出可操作出路（复制频道链接）。"""
    src = _src()
    assert src.count("https://t.me/") >= 2, (
        "多处分支应提示复制频道链接（形如 https://t.me/xxx）"
    )


# =============================================================================
# 判据互斥（用实测页面片段验证，不联网）
# =============================================================================

NORMAL = """<html><body>
<div class="tgme_channel_info"><div class="tgme_channel_info_header_title">
<span class="tgme_channel_info_header_username"><a href="https://t.me/durov">durov</a>
</div><div class="tgme_channel_info_counters">Pavel Durov</div></div>
<div class="tgme_channel_history js-message_history">
<div class="tgme_widget_message text_not_supported_wrap js-widget_message">hi</div>
</div></body></html>"""

PREVIEW_ONLY = """<html><head><title>Telegram: View @kshelfs</title></head><body>
<div class="tgme_page_title"><span dir="auto">涩涩深夜研讨会</span></div>
<div class="tgme_page_extra">5 032 subscribers</div>
<div class="tgme_page_description">Preview channel
If you have Telegram, you can view and join 涩涩深夜研讨会 right away.</div>
<a class="tgme_page_button" href="tg://resolve?domain=kshelfs">View in Telegram</a>
</body></html>"""

USER_MISSING = """<html><head><title>Telegram: Contact @zzz_nonexist_9x8k2</title></head>
<body><div class="tgme_username"><a href="https://t.me/zzz_nonexist_9x8k2">
@zzz_nonexist_9x8k2</a></div></body></html>"""

TG_SHELL = """<html><head><title>Telegram – a new era of messaging</title></head>
<body><div class="tgme_page_wrap"><div>Download Telegram</div></div></body></html>"""


def _classify(html: str) -> str:
    """复刻 parser 的判据（用于验证互斥性）。"""
    low = html.lower()
    if "tgme_widget_message" in low:
        return "normal"
    if "tgme_page_title" in low and ("preview channel" in low or "tgme_page_extra" in low):
        return "preview"
    if "tgme_username" in low or "contact @" in low:
        return "user"
    return "shell"


@pytest.mark.parametrize(
    "html, expected, label",
    [
        (NORMAL, "normal", "正常频道页"),
        (PREVIEW_ONLY, "preview", "仅预览页（频道存在但无网页消息）"),
        (USER_MISSING, "user", "用户名不存在"),
        (TG_SHELL, "shell", "telegram.org 主页壳（中文输入）"),
    ],
)
def test_markers_do_not_overlap(html: str, expected: str, label: str):
    """四类判据互斥 —— 不会互相误判。"""
    assert _classify(html) == expected, (
        f"{label} 被判成 {_classify(html)}，应为 {expected}"
    )
