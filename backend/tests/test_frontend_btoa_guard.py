"""前端 `btoa` 误用导致整页崩溃的回归测试。

## 用户反馈（2026-09-28）

打开「下载」页直接白屏，控制台：

    Uncaught InvalidCharacterError: Failed to execute 'btoa' on 'Window':
    The string to be encoded contains characters outside of the Latin1 range.
        at DownloadPage (index.tsx:938:5)

    The above error occurred in the <DownloadPage> component

## 根因

`btoa()` **只接受 Latin1 字符**（码点 ≤ 0xFF）。代码里是：

    const FALLBACK_IMG =
      'data:image/svg+xml;base64,' +
      btoa(
        '<svg ...>' +
        '<text ...>加载失败</text>' +      // ← 中文！
        '</svg>'
      )

SVG 里写了中文"加载失败" → `btoa` 抛错。

**而且这是组件函数体顶层求值**，所以不是"某张图挂了"，
而是**整个页面渲染直接失败**（React 报 "The above error occurred
in the <DownloadPage> component"，然后走 error boundary）。

## 修法

改用 `encodeURIComponent` 生成 data URI：

    'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)

原生支持 Unicode，不需要 base64，也不用 `unescape` 那类已废弃 hack。

## 这些测试钉住什么

  · 前端源码里**不得**出现 `btoa(` 的调用（注释里提到不算）
  · 预编码的 base64 占位符**解码后不得含非 ASCII** ——
    因为那种字符串一旦被重新编码（或被 `btoa` 包起来）就会炸
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _tsx_files():
    if not FRONTEND_SRC.exists():
        pytest.skip("前端源码不在预期位置")
    return list(FRONTEND_SRC.rglob("*.tsx")) + list(FRONTEND_SRC.rglob("*.ts"))


def _strip_comments(src: str) -> str:
    """去掉 // 行注释与 /* */ 块注释。

    注释里会提到 `btoa()`（说明为什么不能用），不该被当成真实调用。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("//")
    )


# =============================================================================
# btoa 调用
# =============================================================================

def test_no_btoa_calls_in_frontend():
    """**回归**：前端不得调用 `btoa(`。

    `btoa` 只接受 Latin1 —— 一旦字符串里有中文（我们的 UI 全是中文）
    就会抛 `InvalidCharacterError`。若在组件顶层求值，**整页崩**。

    需要 data URI 时用 `encodeURIComponent`（原生支持 Unicode）。
    """
    offenders = []
    for path in _tsx_files():
        code = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        if "btoa(" in code or "btoa (" in code:
            offenders.append(str(path.relative_to(FRONTEND_SRC)))
    assert not offenders, (
        f"这些文件调用了 btoa（中文会崩）：{offenders}。"
        "请改用 `data:image/svg+xml;charset=utf-8,` + encodeURIComponent(...)"
    )


def test_download_page_no_longer_uses_btoa():
    """**回归（原始 bug）**：下载页那个 FALLBACK_IMG 不能再走 btoa。"""
    path = FRONTEND_SRC / "pages" / "download" / "index.tsx"
    if not path.exists():
        pytest.skip("下载页不在预期位置")

    src = path.read_text(encoding="utf-8", errors="ignore")
    assert "btoa(" not in _strip_comments(src), "不得再调用 btoa"
    # 应改用 encodeURIComponent 方案
    assert "charset=utf-8" in src or "encodeURIComponent(" in src


# =============================================================================
# 预编码的 base64 占位符
# =============================================================================

_B64_RE = re.compile(r"base64,([A-Za-z0-9+/=]+)")


def test_preencoded_base64_svg_is_ascii():
    """**回归**：预编码的 base64 SVG 占位**解码后必须是纯 ASCII**。

    如果解码出中文，说明那个占位是"含中文字面量"的，
    将来谁把它包进 `btoa` 就会立刻炸 —— 而且这种错误只在运行时暴露。
    """
    problems = []
    for path in _tsx_files():
        src = path.read_text(encoding="utf-8", errors="ignore")
        for m in _B64_RE.finditer(src):
            blob = m.group(1)
            try:
                decoded = base64.b64decode(blob).decode("utf-8")
            except Exception:
                continue          # 不是 UTF-8 的 base64，交给别的检查
            if any(ord(c) > 127 for c in decoded):
                problems.append(
                    f"{path.relative_to(FRONTEND_SRC)}: "
                    f"{decoded[:60]!r}"
                )
    assert not problems, (
        "这些 base64 占位符解码后含非 ASCII（将来若被 btoa 包住会崩）：\n"
        + "\n".join(problems)
    )


def test_download_page_has_working_fallback():
    """下载页仍要有图片加载失败的占位（不能为了修 bug 把它删了）。"""
    path = FRONTEND_SRC / "pages" / "download" / "index.tsx"
    if not path.exists():
        pytest.skip("下载页不在预期位置")

    src = path.read_text(encoding="utf-8", errors="ignore")
    assert "FALLBACK_IMG" in src, "占位常量应保留"
    assert "data:image/svg+xml" in src, "应是 data URI 形式的占位"
