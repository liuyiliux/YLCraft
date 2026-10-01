"""Telegram 详情渲染的回归测试（2026-10-01 做 C 时加）。

覆盖两件事：
  1. **XSS 防线**：`sanitizeTelegramHtml` 的白名单必须真的挡住脚本
  2. **详情要显示播放量/时长**（原来通用详情只显示赞/收藏/评论/分享）
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _crawler() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# XSS 防线
# =============================================================================

def test_telegram_html_is_sanitized():
    """**关键回归**：Telegram 的 `raw_data.html` **不能**直接塞进
    `dangerouslySetInnerHTML`。

    那是 XSS 入口 —— 虽然来源是 Telegram，但消息可以内含
    任意标签（比如转发别人发的带 `<script>` 的内容）。
    必须过白名单清洗。
    """
    src = _crawler()
    assert "sanitizeTelegramHtml" in src, "要有 HTML 清洗函数"
    # 用法必须是"清洗后再注入"。
    # ⚠️ 文件里 `dangerouslySetInnerHTML` 可能出现多次（公众号等），
    # 要定位到 **Telegram 那处**（附近有 telegram 判断的）。
    idx = -1
    start = 0
    while True:
        j = src.find("dangerouslySetInnerHTML", start)
        if j == -1:
            break
        window = src[max(0, j - 400):j + 200]
        if "sanitizeTelegramHtml" in window:
            idx = j
            break
        start = j + 1
    assert idx != -1, (
        "Telegram 的富文本注入必须**先过 sanitizeTelegramHtml** —— "
        "直接 dangerouslySetInnerHTML 原始 HTML 是 XSS 入口"
    )


def test_sanitizer_drops_dangerous_tags():
    """清洗器要**从代码层面**挡住危险标签与事件属性。

    ⚠️ 前端 TS 函数没法在 Python 里直接跑，所以这里做
    **源码级断言**（检查白名单/黑名单确实覆盖了这些标签）。
    真正的行为验证由前端构建 + 人工在页面里确认。
    """
    src = _crawler()
    i = src.find("function sanitizeTelegramHtml")
    assert i != -1
    body = src[i:i + 2200]

    # 危险标签必须被点名清除
    for danger in ("script", "style", "iframe", "object", "embed"):
        assert danger in body, f"清洗器要挡 {danger}"
    # 白名单机制
    assert "allowed" in body, "要有标签白名单"
    # 协议校验（挡 javascript: / data:）
    assert "https?:" in body, "a 标签要校验协议（挡 javascript:）"
    # 不能有 on* 事件属性透传（白名单只留 href，天然挡住）
    assert "href" in body


def test_sanitizer_keeps_safe_tags():
    """安全标签要保留（否则 Telegram 正文的链接/换行全丢了）。"""
    src = _crawler()
    i = src.find("function sanitizeTelegramHtml")
    body = src[i:i + 2200]
    for safe in ("br", "code", "pre"):
        assert safe in body, f"应保留 {safe}"


# =============================================================================
# 播放量 / 时长要显示
# =============================================================================

def test_detail_shows_views_and_duration():
    """**回归**：通用详情要显示**播放量**和**时长**。

    原来只显示 赞/收藏/评论/分享 —— 把「播放量」「时长」漏了，
    而这两个恰恰是 YouTube/Telegram/B站 最核心的数字。

    实测症状：YouTube 详情看不出视频多长、多少人看过
    （列表里有、点进去没有）。后端**一直在传**
    （duration=16012、views=4937万），是前端没渲染。
    """
    src = _crawler()
    assert "formatDuration" in src, "要有时长格式化函数"
    # 详情里要有"播放"字样
    assert "播放" in src
    # duration 字段要参与渲染
    i = src.find("formatDuration((detailNote as any).duration)")
    assert i != -1, "详情要渲染 duration"


def test_format_duration_handles_hours():
    """**回归**：时长要处理**小时**（不能只 mm:ss）。

    YouTube 的长课程有 4 小时以上（实测 16012 秒 = 4:26:52）。
    只写 m:ss 会显示成 `26:52`，用户以为视频只有 26 分钟。
    """
    src = _crawler()
    i = src.find("function formatDuration")
    assert i != -1
    body = src[i:i + 600]
    assert "3600" in body, "要按 3600 拆分小时"
    assert "h > 0" in body or "h:" in body or "${h}" in body, "小时大于 0 时要显示小时"


# =============================================================================
# Telegram 特有字段
# =============================================================================

def test_telegram_forward_and_links_rendered():
    """Telegram 的**转发来源**和**正文外链**要渲染（其它平台没这两个）。"""
    src = _crawler()
    assert "forward_from" in src, "要显示转发来源"
    assert "raw_data?.links" in src or "raw_data.links" in src, "要列出正文外链"
