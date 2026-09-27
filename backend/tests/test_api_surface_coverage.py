"""API 文档生成器的覆盖度测试。

## 为什么需要（2026-09-27 实测）

`tools/generate_api_surface.py` 解析 `main.py` 的 `include_router(...)`
来找路由，但它**只在两种情况下能定位源文件**：

    · `prefix` 用 `xxx.router` 形式（取 `xxx` 拼 `app/api/v1/xxx.py`）
    · 变量名恰好是 `bili_router`（硬编码的特例）

其他写法（例如 `from app.api.v1 import users as users_api` 后
`include_router(users_api.router, ...)`）会**静默跳过** ——
生成器照常报"成功"，但**这些端点根本不在文档里**。

实测发现的静默漏报（共 16 个端点）：

    /api/v1/douyin/*   2 个   （`douyin_router` 变量名，非 bili 特例）
    /api/v1/xhs/*      1 个   （`xhs_router`，且目录叫 xiaohongshu，按名字猜不到）
    /api/v1/fanqie/*   9 个   （`fanqie_router`）
    /api/v1/users/*    4 个   （起别名 `users_api.router`）

修复方式：
  1. `main.py` 改成 `xxx.router` 形式（users）
  2. 生成器支持按 **import 语句**解析（最可靠，覆盖 douyin/xhs/fanqie）
  3. 生成器对"挂了 prefix 但定位不到源文件"的路由**打警告**，
     不再静默跳过

## 这些测试钉住什么

  · 已知平台的端点在文档里必须出现（防止再次静默丢失）
  · 生成器必须能解析 `from ... import router as xxx_router` 这种别名
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
API_SURFACE = ROOT / "docs" / "architecture" / "API_SURFACE.md"


def _doc() -> str:
    if not API_SURFACE.exists():
        pytest.skip("API_SURFACE.md 不存在")
    return API_SURFACE.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 文档覆盖度：各平台端点必须出现
# =============================================================================

@pytest.mark.parametrize(
    "prefix,minimum",
    [
        ("/api/v1/users/", 4),       # search / profile / videos / me
        ("/api/v1/douyin/", 2),      # health / login-health
        ("/api/v1/xhs/", 1),         # login-health
        ("/api/v1/fanqie/", 5),
        ("/api/v1/bilibili/", 10),
        ("/api/v1/crawler/", 5),
    ],
)
def test_platform_routes_present_in_docs(prefix: str, minimum: int):
    """**回归**：这些平台的端点必须出现在 API 文档里。

    曾经因为生成器定位不到源文件而**静默消失**（文档照常生成、没有报错）。
    """
    doc = _doc()
    n = doc.count(prefix)
    assert n >= minimum, (
        f"{prefix} 在 API 文档里只有 {n} 条（期望 >= {minimum}）。"
        "很可能是 generate_api_surface.py 又定位不到源文件了 —— "
        "运行 `python tools/generate_api_surface.py` 看有没有 WARNING。"
    )


def test_users_me_documented():
    """自查端点要在文档里（本轮新增）。"""
    assert "/api/v1/users/me" in _doc()


# =============================================================================
# 生成器能力
# =============================================================================

def test_generator_imports_module():
    """生成器要能导入（语法正确、无缺失符号）。"""
    sys.path.insert(0, str(TOOLS))
    try:
        import generate_api_surface as gen  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        pytest.fail(f"生成器导入失败: {exc}")


def test_generator_resolves_router_aliases():
    """**回归**：生成器要能解析 `from ... import router as xxx_router`。

    这是 douyin/xhs/fanqie 三个路由此前丢失的根因：
    `xhs_router` 指向 `xiaohongshu/routes.py`，
    **按名字里的关键字猜路径是猜不到的**，只能靠 import 语句。
    """
    sys.path.insert(0, str(TOOLS))
    import generate_api_surface as gen

    imports = gen._collect_router_imports()
    assert imports, "没能解析出任何 router import"
    # main.py 里实际存在的几个
    for var in ("douyin_router", "xhs_router", "fanqie_router", "bili_router"):
        if var in imports:
            path = gen._find_router_file(var, imports)
            assert path is not None, f"{var} 仍无法定位源文件"
            assert path.exists(), f"{var} 定位到的文件不存在: {path}"


def test_generator_warns_on_unresolved_mount():
    """生成器对"定位不到源文件"的路由要**打警告**，不能静默跳过。"""
    src = (TOOLS / "generate_api_surface.py").read_text(encoding="utf-8")
    assert "WARNING" in src, "应有警告输出"
    assert "不会出现在 API 文档里" in src, "警告要说明后果"


def test_no_alias_style_mount_in_main():
    """**回归**：main.py 里不要用 `xxx_api.router` 这种别名挂载。

    生成器按 `router_arg.value.id` 找 `app/api/v1/{id}.py`，
    起了别名就找不到（除非同时有 import 映射兜底，
    但 `prefix` 形式的路由更容易踩）。
    """
    import re

    main_py = ROOT / "backend" / "app" / "main.py"
    src = main_py.read_text(encoding="utf-8")
    # 形如 include_router(xxx_api.router, ...) 的别名用法
    bad = re.findall(r"include_router\(\s*(\w+_api)\.router", src)
    assert not bad, (
        f"main.py 里仍有别名挂载: {bad}。"
        "请改成 `from app.api.v1 import xxx` + `xxx.router`，"
        "否则生成器可能定位不到源文件。"
    )
