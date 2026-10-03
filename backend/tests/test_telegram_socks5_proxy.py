"""Telegram MTProto 必须走 SOCKS5（2026-10-03 实测）。

## 现象

用户开了 VPN（Clash 正常、系统代理正常、HTTP 代理 10090 通），
Telegram 三个 tab 全 500：

    saved / dialogs → HTTP 500
    「无法连接 Telegram（TimeoutError）。请确认 VPN/代理可用。」

**提示是误导的** —— VPN 明明开着。

## 根因：MTProto 是原始 TCP，不读 `HTTPS_PROXY`

实测（国内 + Clash 只开"系统代理"、**未开 TUN 模式**）：

    TCP 直连 149.154.167.51:443    → **超时**
    HTTP CONNECT via 10090         → 200 Connection established
    HTTPS_PROXY 对 httpx           → 生效（所以 t.me/s 那条路能用）

telethon 连 Telegram 走的是**原始 TCP**，`HTTPS_PROXY`/`HTTP_PROXY`
对它**完全无效**；它只认 `proxy=("socks5", host, port)`。

而 Clash 的 **mixed 端口**（本机 10090）同时支持 SOCKS5 与 HTTP CONNECT，
实测 SOCKS5 握手返回 `0500`（接受 no-auth）。

## 三个连带缺���

1. `_build_client()` **根本没传 proxy**
2. 即使传了也缺 `python-socks`（telethon 依赖它），
   没装会静默降级成直连：
       UserWarning: proxy argument will be ignored because python-socks is not installed
3. `requirements.txt` 里**连 telethon 都没有**（文件是 GBK 编码）

## 这些断言锁住
  1. `_build_client` 必须传 SOCKS5 代理
  2. 必须有 SOCKS5 探测（不能硬编码端口）
  3. 依赖必须写进 requirements
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MTPROTO = BACKEND / "app" / "services" / "platforms" / "telegram" / "mtproto.py"
REQS = BACKEND / "requirements.txt"


def _src() -> str:
    if not MTPROTO.exists():
        import pytest
        pytest.skip("mtproto.py not found")
    return MTPROTO.read_text(encoding="utf-8", errors="ignore")


def _reqs() -> str:
    if not REQS.exists():
        import pytest
        pytest.skip("requirements.txt not found")
    raw = REQS.read_bytes()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


# =============================================================================
# 代理：必须传，且要探测
# =============================================================================

def test_build_client_passes_socks5_proxy():
    """`_build_client` 必须给 telethon 传 `proxy=("socks5", ...)`。

    不传 = 直连 = 国内必然超时，而报错会让人以为"VPN 没开"。
    """
    src = _src()
    i = src.find("def _build_client")
    seg = src[i:i + 1800]
    assert "proxy=" in seg, (
        "_build_client 没传 proxy —— telethon 直连 Telegram，"
        "国内必然超时（实测 149.154.167.51:443 TCP 不通）"
    )
    assert "socks5" in seg, "必须用 SOCKS5（MTProto 是原始 TCP，不读 HTTPS_PROXY）"


def test_has_socks5_detection():
    """不能硬编码端口 —— 各家代理端口不同。必须有探测。"""
    src = _src()
    assert "def _detect_socks5" in src, "缺少 SOCKS5 探测（不能硬编码端口）"
    assert "_is_socks5" in src, "探测应通过 SOCKS5 握手判断，而不是猜"


def test_detection_reads_env_first():
    """应支持 `TELEGRAM_SOCKS5` 环境变量显式指定（探测不到时的逃生口）。"""
    src = _src()
    assert "TELEGRAM_SOCKS5" in src, (
        "应支持 TELEGRAM_SOCKS5 环境变量 —— "
        "自动探测失败时用户需要手动指定端口"
    )


def test_mentions_https_proxy_is_useless():
    """注释要写明「MTProto 不读 HTTPS_PROXY」，否则下一个人会重复踩。"""
    src = _src()
    assert "HTTPS_PROXY" in src, (
        "应在注释里说明 MTProto 不读 HTTPS_PROXY（这是本 bug 的根因）"
    )


# =============================================================================
# 依赖
# =============================================================================

def test_requirements_has_telethon():
    """`requirements.txt` 必须有 telethon —— 代码在用却没声明。"""
    assert "telethon" in _reqs(), (
        "requirements.txt 缺 telethon —— 新机器装完依赖会 ImportError"
    )


def test_requirements_has_python_socks():
    """必须有 python-socks，否则传了 proxy 也被静默忽略。"""
    t = _reqs()
    assert "python-socks" in t or "PySocks" in t, (
        "缺 python-socks —— telethon 会警告"
        "『proxy argument will be ignored』并回退直连（静默失败）"
    )


# =============================================================================
# 语法
# =============================================================================

def test_mtproto_syntax_valid():
    ast.parse(_src())


def test_no_hardcoded_proxy_port():
    """探测列表里出现端口是允许的，但不能只依赖某一个。"""
    src = _src()
    i = src.find("def _detect_socks5")
    seg = src[i:i + 2000]
    # 至少要试多个候选端口
    assert seg.count(",") >= 3, "候选端口太少，换个代理客户端就失效"
