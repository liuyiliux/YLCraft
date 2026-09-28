"""「平台注册完整性」的回归测试。

## 为什么单独测这个（2026-09-28 用户实测发现）

用户在账号中心点 X 绑定账号，界面上报：

    平台 twitter 暂不支持 Patchright 获取，
    支持: xhs, douyin, kuaishou, bilibili, weibo, zhihu, wechat_mp, fanqie

**根因**：`_detector_registry` 里没有 `twitter` ——
这正是 `docs/platform/ADDING_A_PLATFORM.md` 第 7 项，而我上一轮**漏了**。

我漏掉的原因也值得记：上一轮我只跑了
`check_platform_registry.py weibo`（只校验微博），
没有跑全量校验，所以推特的问题没暴露。
而且校验器把 twitter 放在 `KNOWN_GAPS` 里"已知放行"，
进一步掩盖了它。

## 这些测试钉住什么

  · 「支持 Patchright 的平台」必须包含本项目**已实现搜索**的所有平台
  · `_detector_registry` 的每个 key 都要能真正加载出 detector 类
    （registry 写了但类不存在 = 点了才报错，更难发现）
  · `KNOWN_GAPS` 不能包含已修好的平台（否则校验器会继续放行）
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


# =============================================================================
# Patchright 支持列表
# =============================================================================

@pytest.mark.parametrize("platform", ["twitter", "weibo", "xhs", "douyin", "bilibili"])
def test_patchright_supports_implemented_platforms(platform: str):
    """**回归**：已实现的平台必须在 Patchright 支持列表里。

    `twitter` 曾缺失 → 账号中心点 X 报「暂不支持 Patchright 获取」，
    用户**没法登录**，于是搜索功能用不了。
    """
    from app.services.cookies.platforms import get_supported_patchright_platforms

    supported = get_supported_patchright_platforms()
    assert platform in supported, (
        f"{platform} 不在 Patchright 支持列表里（{supported}）。"
        "缺了它账号中心点『浏览器』会报暂不支持，用户无法登录。"
    )


@pytest.mark.parametrize("alias", ["twitter", "x", "tw"])
def test_x_aliases_resolve(alias: str):
    """X 的多个别名都要能解析（前端传 `twitter`，调用方可能传 `x`）。"""
    from app.services.cookies.platforms import get_detector

    assert get_detector(alias) is not None, f"{alias} 无法解析出 detector"


def test_every_registry_key_loads():
    """**回归**：registry 里每个 key 都要能真正加载出类。

    registry 写了名字但类不存在/导入失败 = **点了才报错**，
    比"缺 key"更难发现（`get_detector` 会吞异常返回 None）。
    """
    from app.services.cookies import platforms as pkg

    failures = []
    for key in pkg._detector_registry:
        if pkg.get_detector(key) is None:
            failures.append(key)
    assert not failures, f"这些 key 无法加载 detector：{failures}"


def test_x_detector_does_not_use_cookie():
    """**回归**：X 的登录检测**不能**依赖 cookie。

    `auth_token` 是 httpOnly，`document.cookie` 看不到 ——
    据此判断会误判成"未登录"（实测踩过这个坑）。
    判据必须是只有登录后才出现的界面元素。
    """
    import inspect

    from app.services.cookies.platforms.x import XDetector

    src = inspect.getsource(XDetector)
    assert "SideNav_NewTweet_Button" in src, "应检测发帖按钮"
    assert "SideNav_AccountSwitcher_Button" in src, "应检测账号菜单"
    # 不应读 document.cookie 之类
    assert "document.cookie" not in src
    assert "auth_token" not in src


def test_x_detector_detect_returns_false_on_empty_page():
    """空页面（什么都取不到）应判为未登录，不能误判成已登录。"""
    import asyncio

    from app.services.cookies.platforms.x import XDetector

    class FakePage:
        async def query_selector(self, sel):
            return None

    d = XDetector()
    assert asyncio.run(d.detect(FakePage())) is False


def test_x_detector_detect_true_when_compose_present():
    """有「发帖」按钮 = 已登录。"""
    import asyncio

    from app.services.cookies.platforms.x import XDetector

    class FakeEl:
        async def get_attribute(self, name):
            return "https://pbs.twimg.com/a.jpg"

        async def inner_text(self):
            return "测试账号\n@testuser"

    class FakePage:
        async def query_selector(self, sel):
            if "NewTweet" in sel:
                return FakeEl()
            return None

    d = XDetector()
    assert asyncio.run(d.detect(FakePage())) is True


# =============================================================================
# 命名：现在叫 X
# =============================================================================

def test_platform_label_is_x():
    """**平台现名是 X**（原 Twitter）。

    label 用现名；但 **value 保持 `twitter`**
    （PlatformType.TWITTER、连接表字段、既有数据都是 twitter，
    改 value 会破坏既有数据）。
    """
    from app.api.v1 import platforms as platforms_api

    entry = next(
        p for p in platforms_api.SUPPORTED_PLATFORMS if p["value"] == "twitter"
    )
    assert entry["label"] == "X", f"label 应为 X，实际 {entry['label']!r}"
    assert entry["value"] == "twitter", "value 必须保持 twitter（既有数据依赖）"


def test_frontend_labels_are_x():
    """前端各处的显示名也要是 X（不能残留 'Twitter/X'）。"""
    src_dir = BACKEND.parent / "frontend" / "src"
    if not src_dir.exists():
        pytest.skip("前端源码不在预期位置")

    offenders = []
    for path in src_dir.rglob("*.tsx"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Twitter/X" in text:
            offenders.append(str(path.relative_to(src_dir)))
    assert not offenders, f"这些文件仍用 'Twitter/X' 作显示名：{offenders}"


# =============================================================================
# 校验器本身
# =============================================================================

def test_known_gaps_excludes_fixed_platforms():
    """**回归**：修好的平台要从 `KNOWN_GAPS` 移出。

    否则 `check_platform_registry.py --allow-known` 会继续放行，
    缺口重新溜进来没人发现（twitter 修好后已移出）。
    """
    src = (BACKEND / "scripts" / "check_platform_registry.py").read_text(
        encoding="utf-8"
    )
    line = next(
        (ln for ln in src.splitlines() if ln.strip().startswith("KNOWN_GAPS")),
        "",
    )
    assert line, "未找到 KNOWN_GAPS 定义"
    assert "twitter" not in line, (
        "twitter 已修好，应从 KNOWN_GAPS 移出（否则校验器会继续放行）"
    )
