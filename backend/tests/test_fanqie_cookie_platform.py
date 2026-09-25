"""番茄平台在「浏览器（Patchright）获取 Cookie」链路中的注册契约。

背景（2026-09-25 真机排查）：账号中心点「番茄小说 → 浏览器」报
「平台 fanqie 暂不支持 Patchright 获取」。根因是**三处清单各写一份、改漏了番茄**：

1. `services/cookies/platforms/__init__.py` 的 `_detector_registry`（决定白名单）
2. `services/cookies/base.py` 的 `PLATFORM_LOGIN_URLS` / `PLATFORM_DOMAINS`
3. 前端 `pages/accounts/index.tsx` 的 `PLATFORM_METAS`（决定入口按钮是否渲染）

而业务侧（`api/v1/platforms.py` 的 `SUPPORTED_PLATFORMS`）早就支持番茄。
这些测试把三处的**一致性**钉住，避免以后再漏。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_fanqie_registered_as_patchright_platform():
    """番茄必须在 Patchright 白名单里，否则「浏览器」获取直接报不支持。"""
    from app.services.cookies.platforms import get_supported_patchright_platforms

    supported = get_supported_patchright_platforms()
    assert "fanqie" in supported, f"番茄未注册到 Patchright 白名单：{supported}"


def test_fanqie_detector_loads():
    """检测器类必须能真实导入并实例化（registry 里是字符串路径，易写错）。"""
    from app.services.cookies.base import PlatformDetector
    from app.services.cookies.platforms import get_detector

    detector = get_detector("fanqie")
    assert detector is not None
    assert isinstance(detector, PlatformDetector)
    assert type(detector).__name__ == "FanqieDetector"


def test_fanqie_has_login_url_domains_and_test_url():
    """登录地址 / 关联域名 / 测试链接三者都必须配齐。

    缺 login_url 会退化成 google.com；缺 domains 会导致提取不到 Cookie。
    """
    from app.services.cookies.base import (
        get_login_url,
        get_platform_domains,
        get_platform_test_url,
    )

    login_url = get_login_url("fanqie")
    assert "fanqienovel.com" in login_url, f"登录地址不对：{login_url}"
    assert "google.com" not in login_url, "退化成默认值说明没配置"

    domains = get_platform_domains("fanqie")
    assert "fanqienovel.com" in domains, f"关联域名缺主域：{domains}"

    assert get_platform_test_url("fanqie"), "测试链接未配置"


def test_fanqie_login_url_points_to_writer_backend():
    """番茄的发布与数据都在**作家后台**，登录地址不能指向读者站首页。

    读者站首页与作家后台不是同一个登录上下文，指错了会出现
    「登录成功但拿不到作家接口权限」的隐蔽问题。
    """
    from app.services.cookies.base import get_login_url

    assert "/main/writer/" in get_login_url("fanqie")


def test_detector_does_not_extract_sensitive_identity_fields():
    """检测器不得提取手机号/实名等敏感字段。

    番茄 `account/info` 响应里含 `phone_number`、`identity_name_mask`、
    `identity_code_mask`；平台适配层只应保留展示所需的作家名/头像。
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "app/services/cookies/platforms/fanqie.py"
    ).read_text(encoding="utf-8")
    body = re.sub(r'"""[\s\S]*?"""', "", source)  # 去掉文档字符串，只查代码
    for forbidden in ("phone_number", "identity_name_mask", "identity_code_mask"):
        assert forbidden not in body, f"检测器不应读取敏感字段：{forbidden}"


def test_frontend_accounts_meta_includes_fanqie():
    """前端账号中心的平台元数据表必须包含番茄。

    后端支持但前端遗漏，表现为「账号中心看不到番茄入口」——
    这正是本次用户报的问题：入口压根没渲染出来。
    """
    frontend_file = (
        Path(__file__).resolve().parents[2]
        / "frontend/src/pages/accounts/index.tsx"
    )
    if not frontend_file.exists():  # 纯后端环境跳过
        pytest.skip("frontend sources not present")

    source = frontend_file.read_text(encoding="utf-8")
    assert "'fanqie'" in source, "前端 PLATFORM_METAS 缺番茄条目"
    assert "番茄小说" in source, "前端缺番茄中文标签"
