from __future__ import annotations

import ast
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend" / "app" / "main.py"
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


def parse_mounts() -> list[RouterMount]:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    mounts: list[RouterMount] = []

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
        elif isinstance(router_arg, ast.Name) and router_arg.id == "bili_router":
            name = "bilibili"
            file_path = BILI_ROUTES
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


def parse_endpoints(mount: RouterMount) -> list[Endpoint]:
    file_path = ROOT / mount.file
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        raise RuntimeError(f"Failed to parse {mount.file}: {exc}") from exc

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
                    path=join_paths(mount.prefix, local_path),
                    router=mount.name,
                    prefix=mount.prefix,
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
