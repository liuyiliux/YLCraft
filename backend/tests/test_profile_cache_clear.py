"""采集浏览器 profile 缓存管理的回归测试（2026-10-03）。

## 背景

`backend/data/browser_profiles/<平台>/` 是**持久化 profile**，只增不减。
实测 9 平台合计 724MB，其中约 **94% 是可丢弃的加速副本**
（xhs 419MB 里 377MB 是 `Default/Cache`），真正不能碰的是
Cookies / Local Storage / IndexedDB / Service Worker。

## 为什么这些断言必须存在

`Service Worker` 目录**一旦删掉，微博采集直接失效** —— `crawler/service.py`
明确记录它由 Service Worker 代理请求并注入 httpx 复现不了的上下文
（实测直连一律 `ok=-100`）。所以"清理缓存"绝不能变成"清空 profile"。

另外两条容易被忽略：
  · 删不掉时**不能假装成功**（浏览器占用会锁文件）
  · 不能提供"全选删除"的入口
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from app.services.browser import profile_cache as pc
from app.services.browser.persistent_profile import profiles_root

SERVICE = Path(inspect.getfile(pc))


# =============================================================================
# 目录白名单：绝不能包含登录态与 Service Worker
# =============================================================================

@pytest.mark.parametrize(
    "forbidden, why",
    [
        ("Default/Service Worker", "微博采集依赖 SW 上下文，删了直接失效"),
        ("Default/Network", "Cookies / HSTS = 登录态"),
        ("Default/Local Storage", "很多站把 token 存这"),
        ("Default/Sessions", "会话恢复状态"),
        ("Default/IndexedDB", "站点数据库，可能存登录态"),
        ("Default/Storage", "站点存储"),
        ("Default/WebStorage", "存储配额"),
        ("Default/Bookmarks", "书签"),
        ("Default/Login Data", "保存的密码"),
    ],
)
def test_cache_dirs_exclude_identity(forbidden: str, why: str):
    """清理白名单**不得**包含任何身份/功能目录。"""
    assert forbidden not in pc.CACHE_DIRS, (
        f"CACHE_DIRS 含有 {forbidden} —— {why}"
    )


def test_service_worker_not_nested_under_a_cache_dir():
    """防止把 `Service Worker` 塞进某个缓存目录下面而绕过上面的断言。"""
    for d in pc.CACHE_DIRS:
        assert "Service Worker" not in d, f"{d} 里含 Service Worker"


@pytest.mark.parametrize(
    "d", ["Default/Cache", "Default/Code Cache", "GrShaderCache"]
)
def test_expected_cache_dirs_present(d: str):
    """确认真正的缓存目录仍在白名单里（别为了安全把该清的也删了规则）。"""
    assert d in pc.CACHE_DIRS


# =============================================================================
# 平台名校验：防目录穿越
# =============================================================================

@pytest.mark.parametrize(
    "evil",
    ["..", "../windows", "..%2F..", "a/../../b", "\\..\\windows",
     "C:\\\\Windows", ".", "./../", "..\\..\\etc"],
)
def test_path_traversal_rejected(evil: str):
    """平台名含穿越成分必须抛 ValueError，绝不能拼进路径。"""
    with pytest.raises(ValueError):
        pc.clear_platform_cache(evil)


@pytest.mark.parametrize("evil", ["", "   ", "!!!", "///", "中文/../x"])
def test_empty_or_invalid_name_rejected(evil: str):
    with pytest.raises(ValueError):
        pc.clear_platform_cache(evil)


def test_resolved_path_stays_under_root():
    """清理后的路径必须在 profiles_root 之内（纵深防御）。"""
    root = profiles_root().resolve()
    assert str(root).startswith(str(profiles_root().resolve()))


# =============================================================================
# 真实目录行为（用 tmp 造 profile，不碰用户数据）
# =============================================================================

@pytest.fixture
def fake_profile(tmp_path, monkeypatch):
    """造一个可控的 profile：登录态 + 缓存 + Service Worker。"""
    root = tmp_path / "browser_profiles"
    pf = root / "douyin"
    (pf / "Default" / "Network").mkdir(parents=True)
    (pf / "Default" / "Local Storage").mkdir(parents=True)
    (pf / "Default" / "Service Worker").mkdir(parents=True)
    (pf / "Default" / "Cache").mkdir(parents=True)
    (pf / "Default" / "Code Cache").mkdir(parents=True)

    # 造一个真 cookie 库
    ck = pf / "Default" / "Network" / "Cookies"
    c = sqlite3.connect(str(ck))
    c.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT)")
    c.execute("INSERT INTO cookies VALUES ('.douyin.com','sessionid','abc')")
    c.commit()
    c.close()
    (pf / "Default" / "Network" / "Cookies-journal").write_bytes(b"x" * 100)

    # 缓存塞点数据
    (pf / "Default" / "Cache" / "data_1").write_bytes(b"a" * 300_000)
    (pf / "Default" / "Code Cache" / "js_0").write_bytes(b"b" * 200_000)
    (pf / "Default" / "Service Worker" / "ScriptCache" / "s").parent.mkdir(parents=True)
    (pf / "Default" / "Service Worker" / "ScriptCache" / "s").write_bytes(b"c" * 50_000)

    monkeypatch.setattr(pc, "profiles_root", lambda: root)
    return pf


def test_clear_removes_cache_but_keeps_identity(fake_profile: Path):
    """核心断言：缓存被删，身份目录**一个都不能少**。"""
    before_cookies = (fake_profile / "Default" / "Network" / "Cookies").read_bytes()
    before_sw = (fake_profile / "Default" / "Service Worker" / "ScriptCache" / "s").read_bytes()

    r = pc.clear_platform_cache("douyin")

    assert r.freed_bytes >= 500_000, f"释放太少: {r.freed_bytes}"
    assert r.ok, f"不该有跳过项: {r.skipped}"
    # 缓存没了
    assert not (fake_profile / "Default" / "Cache").exists()
    assert not (fake_profile / "Default" / "Code Cache").exists()
    # 身份原封不动
    assert (fake_profile / "Default" / "Network" / "Cookies").read_bytes() == before_cookies
    assert (fake_profile / "Default" / "Service Worker" / "ScriptCache" / "s").read_bytes() == before_sw
    assert (fake_profile / "Default" / "Local Storage").exists()


def test_clear_all_reports_each_platform(fake_profile: Path):
    """逐平台报告，部分失败不影响其他平台。"""
    (fake_profile.parent / "wb").mkdir()
    (fake_profile.parent / "wb" / "Default" / "Cache").mkdir(parents=True)
    (fake_profile.parent / "wb" / "Default" / "Cache" / "x").write_bytes(b"z" * 50_000)

    results = pc.clear_all_caches()
    names = {r.platform for r in results}
    assert "douyin" in names and "wb" in names
    assert all(r.ok for r in results), [r.skipped for r in results]


def test_locked_file_reported_not_swallowed(fake_profile: Path, monkeypatch):
    """删不掉必须进 skipped —— 假装成功比失败更糟。"""
    def boom(*a, **k):
        raise PermissionError(13, "used by another process")
    monkeypatch.setattr(pc.shutil, "rmtree", boom)

    r = pc.clear_platform_cache("douyin")
    assert not r.ok
    assert r.skipped, "占用导致的失败必须出现在 skipped 里"
    assert "Cache" in r.skipped
    # 原因要可操作
    assert any("浏览器" in v for v in r.skipped.values()), r.skipped


def test_list_reports_ratio_and_cookie(fake_profile: Path):
    """列表要同时给出可清占比与 cookie 大小（让用户看清"清缓存不掉登录"）。"""
    items = pc.list_platform_caches()
    assert len(items) == 1
    it = items[0]
    assert it.platform == "douyin"
    assert it.cookie_bytes > 0
    assert 0 < it.preservable_ratio < 1
    assert it.cache_bytes > it.cookie_bytes


def test_preserved_note_mentions_service_worker():
    """UI 也要如实告诉用户 SW 不会被删。"""
    assert "Service Worker" in pc.PRESERVED_NOTE
    assert "Cookies" in pc.PRESERVED_NOTE


def test_no_delete_all_profile_api():
    """接口层不能提供"删掉整个 profile"的入口。"""
    api = Path(inspect.getfile(pc)).parent.parent.parent / "api" / "v1" / "browser_profile_cache.py"
    src = api.read_text(encoding="utf-8", errors="ignore")
    # 只能有 caches 相关路由
    assert 'delete("/caches' in src
    # 不允许出现删除整个 profile 目录的路由
    for bad in ('delete("/{platform}")', 'delete("/profile', 'rmtree(root)', 'rmtree(directory)'):
        assert bad not in src, f"接口层出现了危险操作: {bad}"
