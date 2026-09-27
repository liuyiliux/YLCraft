from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend" / "app" / "main.py"
APP_DIR = ROOT / "backend" / "app"
API_DIR = ROOT / "backend" / "app" / "api" / "v1"
BILI_ROUTES = ROOT / "backend" / "app" / "services" / "platforms" / "bilibili" / "routes.py"
OUT_MD = ROOT / "docs" / "architecture" / "API_SURFACE.md"
OUT_JSON = ROOT / "docs" / "architecture" / "api_surface.json"

METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "websocket"}


@dataclass
class RouterMount:
    name: str
    file: str
    prefix: str
    tags: list[str]


@dataclass
class Endpoint:
    method: str
    path: str
    router: str
    prefix: str
    local_path: str
    tags: list[str]
    summary: str
    function: str
    file: str
    line: int
    response_model: str
    include_in_schema: bool


def literal(node: ast.AST | None, default: Any = None) -> Any:
    if node is None:
        return default
    try:
        return ast.literal_eval(node)
    except Exception:
        return default


def unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def join_paths(prefix: str, local: str) -> str:
    prefix = (prefix or "").strip()
    local = (local or "").strip()
    if not prefix:
        return local or "/"
    if not local or local == "/":
        return prefix
    return f"{prefix.rstrip('/')}/{local.lstrip('/')}"


def _find_router_file(router_name: str, imports: dict[str, str] | None = None) -> Path | None:
    """按 `include_router` 的变量名找到定义 `router` 的源文件。

    **优先用 import 语句解析**（最可靠）—— main.py 里通常有

        from app.services.platforms.xiaohongshu.routes import router as xhs_router

    直接按模块路径换算即可，不依赖名字里有没有"平台关键字"
    （`xhs_router` 指向 `xiaohongshu/` 目录，按名字猜是猜不到的）。

    回退策略（没有对应 import 时）：
      1. 常见位置精确命中
      2. 全树扫描（要求路径含模块提示词）
    """
    # 1) 用 import 映射（最准）
    if imports and router_name in imports:
        mod = imports[router_name]          # 形如 app.services...routes
        rel = Path(*mod.split("."))
        for candidate in (
            ROOT / "backend" / rel.with_suffix(".py"),
            ROOT / "backend" / rel / "__init__.py",
        ):
            if candidate.exists():
                return candidate

    stem = router_name[:-7] if router_name.endswith("_router") else router_name

    # 2) 常见位置精确命中
    for candidate in (
        BILI_ROUTES if stem == "bili" else None,
        APP_DIR / "services" / "platforms" / stem / "routes.py",
        APP_DIR / "api" / "v1" / f"{stem}.py",
        APP_DIR / "api" / "v1" / f"{stem}_routes.py",
    ):
        if candidate and candidate.exists():
            return candidate

    # 3) 全树扫描兜底
    try:
        for path in APP_DIR.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "router = APIRouter" not in text:
                continue
            if stem and stem not in str(path).replace("\\", "/"):
                continue
            return path
    except OSError:
        pass
    return None


def _collect_router_imports() -> dict[str, str]:
    """扫描 main.py 的 import，得到 `变量名 -> 模块路径` 映射。

         from app.services.platforms.xiaohongshu.routes import router as xhs_router
         → {"xhs_router": "app.services.platforms.xiaohongshu.routes"}

    也支持不带别名的 `from ... import router`（变量名就是 `router`）。
    """
    mapping: dict[str, str] = {}
    try:
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return mapping

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            if local.endswith("router") or alias.name == "router":
                mapping[local] = node.module
    return mapping


def parse_mounts() -> list[RouterMount]:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    mounts: list[RouterMount] = []
    router_imports = _collect_router_imports()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "include_router":
            continue
        if not node.args:
            continue

        router_arg = node.args[0]
        name = ""
        file_path: Path | None = None
        if isinstance(router_arg, ast.Attribute) and isinstance(router_arg.value, ast.Name):
            name = router_arg.value.id
            file_path = API_DIR / f"{name}.py"
        elif isinstance(router_arg, ast.Name):
            # 形如 `app.include_router(douyin_router, ...)` ——
            # 名字不是 `xxx.router`，得自己去源码里找它在哪个文件定义。
            #
            # 之前这里只硬编码了 `bili_router` 一个特例，于是
            # `douyin_router` / `fanqie_router` / `xhs_router` 全被
            # `file_path is None` 悄悄丢掉，**文档里少了一大块而没人发现**。
            # 现在改成通用查找：按模块名去 app 树下找
            # `router = APIRouter(...)` 所在文件。
            name = router_arg.id
            file_path = _find_router_file(name, router_imports)
        else:
            name = unparse(router_arg)

        prefix = ""
        tags: list[str] = []
        for kw in node.keywords:
            if kw.arg == "prefix":
                prefix = literal(kw.value, "") or ""
            elif kw.arg == "tags":
                value = literal(kw.value, [])
                tags = value if isinstance(value, list) else []

        if file_path and file_path.exists():
            mounts.append(
                RouterMount(
                    name=name,
                    file=str(file_path.relative_to(ROOT)).replace("\\", "/"),
                    prefix=prefix,
                    tags=[str(tag) for tag in tags],
                )
            )
        elif prefix:
            # ⚠️ **不要静默跳过**。
            #
            # 实测踩过：`from app.api.v1 import users as users_api` +
            # `app.include_router(users_api.router, ...)` 时，
            # `router_arg.value.id` 是 `users_api`，于是去找
            # `app/api/v1/users_api.py` —— 文件不存在，路由被
            # `file_path.exists()` 悄悄丢掉，**文档里完全看不到这些端点**
            # （3 个 /users/* 端点凭空消失，而生成器仍报"成功"）。
            #
            # 这类"文档少了一块但没人发现"的问题很难察觉，所以这里
            # 显式打警告：有 prefix 说明是真要挂载的路由，找不到源文件
            # 一定是解析姿势不对（起别名 / 动态 import）。
            print(
                f"WARNING: 已挂载 {prefix or '(无前缀)'} 但找不到源文件 "
                f"{file_path}（router 名 {name!r}）。"
                "这条路由不会出现在 API 文档里 —— "
                "请把 main.py 里的 include_router 改成 `xxx.router` 形式"
                "（不要起别名），或在此处补充映射。",
                file=sys.stderr,
            )

    return mounts


def parse_endpoint_decorator(decorator: ast.AST) -> tuple[str, str, str, str, bool] | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in METHODS:
        return None
    if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
        return None

    method = decorator.func.attr.upper()
    local_path = literal(decorator.args[0], "") if decorator.args else ""
    summary = ""
    response_model = ""
    include_in_schema = True

    for kw in decorator.keywords:
        if kw.arg == "summary":
            summary = literal(kw.value, "") or ""
        elif kw.arg == "response_model":
            response_model = unparse(kw.value)
        elif kw.arg == "include_in_schema":
            include_in_schema = bool(literal(kw.value, True))

    return method, local_path, summary, response_model, include_in_schema


def router_internal_prefix(file_path: Path) -> str:
    """Read a router module's own ``APIRouter(prefix=...)``.

    Without this, any router declaring its own prefix gets documented with the
    mount prefix alone — e.g. ``cookie_acquisition`` declares ``prefix="/acquire"``
    and is mounted at ``/api/v1``, so its real paths are ``/api/v1/acquire/...``,
    but generated docs claimed ``/api/v1/playwright/...``. That wrong path is how
    the docs got out of sync with the running app.
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", "") or getattr(func, "attr", "")
        if name != "APIRouter":
            continue
        for kw in node.keywords:
            if kw.arg == "prefix":
                return literal(kw.value, "") or ""
    return ""


def parse_endpoints(mount: RouterMount) -> list[Endpoint]:
    file_path = ROOT / mount.file
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        raise RuntimeError(f"Failed to parse {mount.file}: {exc}") from exc

    effective_prefix = join_paths(mount.prefix, router_internal_prefix(file_path))

    endpoints: list[Endpoint] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            parsed = parse_endpoint_decorator(decorator)
            if not parsed:
                continue
            method, local_path, summary, response_model, include_in_schema = parsed
            endpoints.append(
                Endpoint(
                    method=method,
                    path=join_paths(effective_prefix, local_path),
                    router=mount.name,
                    prefix=effective_prefix,
                    local_path=local_path,
                    tags=mount.tags,
                    summary=summary,
                    function=node.name,
                    file=mount.file,
                    line=getattr(node, "lineno", 0),
                    response_model=response_model,
                    include_in_schema=include_in_schema,
                )
            )
    return endpoints


def method_sort(method: str) -> int:
    order = ["GET", "POST", "PUT", "PATCH", "DELETE", "WEBSOCKET", "OPTIONS", "HEAD"]
    try:
        return order.index(method)
    except ValueError:
        return len(order)


def render_markdown(mounts: list[RouterMount], endpoints: list[Endpoint]) -> str:
    grouped: dict[str, list[Endpoint]] = {}
    for endpoint in endpoints:
        key = endpoint.tags[0] if endpoint.tags else endpoint.router
        grouped.setdefault(key, []).append(endpoint)

    lines: list[str] = [
        "# YLCraft API Surface",
        "",
        "> Route facts are generated from `backend/app/main.py` and FastAPI router decorators.",
        "> Update with: `python tools/generate_api_surface.py`, then manually review semantic/module impact.",
        "> Do not hand-edit generated endpoint tables unless the generator cannot represent a route.",
        "",
        "## Summary",
        "",
        f"- Router mounts: {len(mounts)}",
        f"- Endpoints: {len(endpoints)}",
        f"- Public schema endpoints: {sum(1 for item in endpoints if item.include_in_schema)}",
        f"- Hidden compatibility endpoints: {sum(1 for item in endpoints if not item.include_in_schema)}",
        "",
        "## Router Mounts",
        "",
        "| Prefix | Tags | Router | Source |",
        "| --- | --- | --- | --- |",
    ]

    for mount in sorted(mounts, key=lambda item: item.prefix):
        lines.append(
            f"| `{mount.prefix}` | {', '.join(mount.tags) or '-'} | `{mount.name}` | `{mount.file}` |"
        )

    lines.extend(["", "## Endpoints", ""])

    for group in sorted(grouped):
        items = sorted(grouped[group], key=lambda item: (item.path, method_sort(item.method), item.function))
        lines.extend(
            [
                f"### {group}",
                "",
                "| Method | Path | Summary | Handler | Source |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for endpoint in items:
            summary = endpoint.summary.replace("|", "\\|") if endpoint.summary else "-"
            hidden = " `hidden`" if not endpoint.include_in_schema else ""
            source = f"{endpoint.file}:{endpoint.line}"
            lines.append(
                f"| `{endpoint.method}`{hidden} | `{endpoint.path}` | {summary} | `{endpoint.function}` | `{source}` |"
            )
        lines.append("")

    lines.extend(
        [
            "## Update Rules",
            "",
            "- Add or remove API routes in code first.",
            "- Run `python tools/generate_api_surface.py` after route changes, or make an equivalent explicit update when the generator cannot express the change.",
            "- Commit this file and `docs/architecture/api_surface.json` together.",
            "- Review the generated diff. The script records route facts only; the AI/developer must judge semantic changes.",
            "- If route behavior changes materially, update `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`, the owning domain doc, or the relevant OpenSpec task too.",
            "- Treat Agent tools and Skills as internal APIs: update their schema/spec docs and tests when inputs, outputs, risk level, authorization, or routing behavior changes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    mounts = parse_mounts()
    endpoints = [endpoint for mount in mounts for endpoint in parse_endpoints(mount)]
    endpoints.sort(key=lambda item: (item.path, method_sort(item.method), item.function))

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(mounts, endpoints), encoding="utf-8", newline="\n")
    OUT_JSON.write_text(
        json.dumps(
            {
                "router_mounts": [asdict(mount) for mount in mounts],
                "endpoints": [asdict(endpoint) for endpoint in endpoints],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Routers: {len(mounts)}")
    print(f"Endpoints: {len(endpoints)}")


if __name__ == "__main__":
    main()
