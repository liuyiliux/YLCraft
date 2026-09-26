"""持久化浏览器 profile 的契约测试。

## 背景（2026-09-26 实测）

取 Cookie 原本走 `chromium.launch()` —— 非持久化，每次全新空 profile。
后果：**每取一次 Cookie 都要重新扫码**；窗口一关或会话超时，登录就白做。
实测中用户扫码后 cookie 里确实出现了 sessionid，但窗口被关掉，
下次启动又是未登录，于是表现为"抖音登录一直有问题"。

## 另一个必须钉住的点

持久化 profile 目录里含**登录 Cookie**（Default/Network/Cookies）。
实测发现 .gitignore 没覆盖它，`git add --dry-run` 会把 cookie 数据库
列进提交 —— 那等于把用户登录凭证推到远端。这条测试防止规则被删掉。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# =============================================================================
# 持久化开关与目录
# =============================================================================

def test_persistent_enabled_by_default():
    """默认必须开启持久化——否则"每次都要重扫"的问题照旧。"""
    from app.services.browser import persistent_profile as pp

    os.environ.pop("YLCRAFT_BROWSER_PERSISTENT", None)
    assert pp.persistent_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no"])
def test_persistent_can_be_disabled(monkeypatch, value):
    from app.services.browser import persistent_profile as pp

    monkeypatch.setenv("YLCRAFT_BROWSER_PERSISTENT", value)
    assert pp.persistent_enabled() is False


def test_profile_dir_is_per_platform():
    """各平台必须用独立 profile 目录——不能共用，否则登录态会互相串。"""
    from app.services.browser import persistent_profile as pp

    dy = pp.profile_dir_for("douyin")
    xhs = pp.profile_dir_for("xhs")
    assert dy != xhs
    assert dy.exists() and xhs.exists()


def test_profile_dir_sanitizes_platform_name():
    """平台名里的路径分隔符等必须被清掉，不能逃出 profile 根目录。"""
    from app.services.browser import persistent_profile as pp

    evil = pp.profile_dir_for("../../etc")
    root = pp.profiles_root()
    assert str(evil).startswith(str(root)), "不允许写到 profile 根目录之外"


def test_profiles_root_under_backend_data():
    from app.services.browser import persistent_profile as pp

    root = pp.profiles_root()
    assert "browser_profiles" in str(root)
    assert "data" in str(root)


# =============================================================================
# 凭据安全：profile 目录绝不能被提交
# =============================================================================

def test_gitignore_covers_browser_profiles():
    """.gitignore 必须忽略 browser_profiles（里面有登录 Cookie）。"""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "backend/data/browser_profiles/" in gitignore, (
        "缺少忽略规则：profile 里的 Default/Network/Cookies 是登录凭证，"
        "不加规则会被 git 提交到远端"
    )


def test_gitignore_rule_actually_applies():
    """规则要真的生效（不只是文本存在）。"""
    target = "backend/data/browser_profiles/douyin/Default/Network/Cookies"
    proc = subprocess.run(
        ["git", "check-ignore", "-q", target],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    # 文件可能还没生成；用 --no-index 风格判断：规则存在即通过
    if proc.returncode == 1 and not (REPO_ROOT / target).exists():
        # 文件不存在时 git check-ignore 仍会按规则判断，1 表示未忽略
        pytest.fail(f".gitignore 规则未覆盖 {target}（登录 Cookie 会被提交）")
    assert proc.returncode == 0, f"check-ignore 返回 {proc.returncode}，规则未生效"


def test_runtime_supports_persistent_platform_kwarg():
    """new_context 必须支持 persistent_platform，供采集管理器使用。"""
    import inspect

    from app.services.browser.patchright_runtime import PatchrightBrowserRuntime

    sig = inspect.signature(PatchrightBrowserRuntime.new_context)
    assert "persistent_platform" in sig.parameters


def test_manager_uses_persistent_profile():
    """采集管理器必须走持久化，否则登录态留不住。"""
    import inspect

    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm.PatchrightAcquisitionManager.start_session)
    assert "persistent_platform" in src, "start_session 应传 persistent_platform"
    assert "persistent_enabled" in src, "应可开关（默认开）"


def test_manager_documents_why_persistent():
    """留下"为什么必须持久化"的说明，避免后人改回 launch()。"""
    import inspect

    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm.PatchrightAcquisitionManager.start_session)
    assert "非持久化" in src or "全新空 profile" in src, "应记录原因"
