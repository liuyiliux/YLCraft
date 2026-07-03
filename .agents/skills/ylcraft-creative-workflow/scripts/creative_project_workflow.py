#!/usr/bin/env python3
"""Small CLI for driving YLCraft creative-project workflows through the API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_TIMEOUT = 600
REQUEST_TIMEOUT = DEFAULT_TIMEOUT


class ApiError(RuntimeError):
    pass


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def api_request(base_url: str, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    url = f"{normalize_base_url(base_url)}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw:
                return None
            return json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code} {exc.reason}: {detail}") from exc
    except URLError as exc:
        raise ApiError(f"Cannot reach API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ApiError(f"Response is not JSON from {url}") from exc


def unwrap(response: Any) -> Any:
    if isinstance(response, dict) and response.get("success") is False:
        raise ApiError(str(response))
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parse_chapters(value: str) -> list[int]:
    chapters: set[int] = set()
    for part in str(value or "").split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            left, right = item.split("-", 1)
            start = int(left.strip())
            end = int(right.strip())
            if start > end:
                start, end = end, start
            chapters.update(range(start, end + 1))
        else:
            chapters.add(int(item))
    return sorted(chapter for chapter in chapters if chapter > 0)


def query_string(params: dict[str, Any]) -> str:
    filtered = {key: value for key, value in params.items() if value not in (None, "", [])}
    return f"?{urlencode(filtered)}" if filtered else ""


def list_contents(base_url: str, project_id: str, content_type: str | None = None) -> list[dict[str, Any]]:
    qs = query_string({"content_type": content_type})
    return list(unwrap(api_request(base_url, "GET", f"/creative-projects/{project_id}/contents{qs}")) or [])


def find_content(
    base_url: str,
    project_id: str,
    content_type: str,
    chapter_number: int,
) -> dict[str, Any] | None:
    contents = list_contents(base_url, project_id, content_type)
    candidates = [item for item in contents if item.get("chapter_number") == chapter_number]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)[0]


def model_payload(args: argparse.Namespace, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if getattr(args, "provider", None):
        payload["provider"] = args.provider
    if getattr(args, "model", None):
        payload["model"] = args.model
    if getattr(args, "template_id", None):
        payload["template_id"] = args.template_id
    if extra:
        payload.update(extra)
    return payload


def summarize_project(base_url: str, project_id: str) -> dict[str, Any]:
    project = unwrap(api_request(base_url, "GET", f"/creative-projects/{project_id}"))
    contents = list_contents(base_url, project_id)
    assets = unwrap(api_request(base_url, "GET", f"/creative-projects/{project_id}/assets"))
    logs = unwrap(api_request(base_url, "GET", f"/creative-projects/{project_id}/generation-logs?limit=10"))

    counts: dict[str, int] = {}
    chapters_by_type: dict[str, list[int]] = {}
    for item in contents:
        content_type = item.get("content_type") or "unknown"
        counts[content_type] = counts.get(content_type, 0) + 1
        chapter = item.get("chapter_number")
        if isinstance(chapter, int):
            chapters_by_type.setdefault(content_type, []).append(chapter)
    for chapters in chapters_by_type.values():
        chapters.sort()

    return {
        "project": {
            "id": project.get("id"),
            "title": project.get("title"),
            "project_type": project.get("project_type"),
            "status": project.get("status"),
            "current_stage": project.get("current_stage"),
            "chapter_plan_count": (project.get("chapter_plan") or {}).get("chapter_count"),
        },
        "content_counts": counts,
        "chapters_by_type": chapters_by_type,
        "asset_link_count": len(assets or []),
        "recent_logs": [
            {
                "id": item.get("id"),
                "stage": item.get("stage"),
                "status": item.get("status"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "created_at": item.get("created_at"),
                "validation_error": item.get("validation_error"),
            }
            for item in (logs or [])
        ],
    }


def command_list_projects(args: argparse.Namespace) -> None:
    qs = query_string({"limit": args.limit, "offset": args.offset, "status": args.status, "project_type": args.project_type})
    projects = unwrap(api_request(args.base_url, "GET", f"/creative-projects{qs}")) or []
    if args.full:
        print_json(projects)
        return
    print_json(
        [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "project_type": item.get("project_type"),
                "status": item.get("status"),
                "current_stage": item.get("current_stage"),
                "chapter_count": (item.get("chapter_plan") or {}).get("chapter_count"),
                "updated_at": item.get("updated_at"),
            }
            for item in projects
        ]
    )


def command_create_project(args: argparse.Namespace) -> None:
    data = {
        "title": args.title,
        "idea": args.idea,
        "project_type": args.project_type,
        "source_type": args.source_type,
        "settings": {},
        "metadata": {},
    }
    print_json(unwrap(api_request(args.base_url, "POST", "/creative-projects", data)))


def command_inspect(args: argparse.Namespace) -> None:
    print_json(summarize_project(args.base_url, args.project_id))


def command_contents(args: argparse.Namespace) -> None:
    print_json(list_contents(args.base_url, args.project_id, args.content_type))


def command_logs(args: argparse.Namespace) -> None:
    qs = query_string({"stage": args.stage, "status": args.status, "limit": args.limit, "offset": args.offset})
    print_json(unwrap(api_request(args.base_url, "GET", f"/creative-projects/{args.project_id}/generation-logs{qs}")))


def command_generate_outline(args: argparse.Namespace) -> None:
    payload = model_payload(args, {"idea": args.idea})
    print_json(unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/generate-outline", payload)))


def command_sync_characters(args: argparse.Namespace) -> None:
    print_json(unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/sync-characters", {})))


def command_generate_chapter_plan(args: argparse.Namespace) -> None:
    payload = model_payload(args, {"chapter_count": args.chapter_count})
    print_json(unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/generate-chapter-plan", payload)))


def batch_simple_stage(args: argparse.Namespace, endpoint: str, field_name: str = "chapter_number") -> list[dict[str, Any]]:
    results = []
    for chapter in parse_chapters(args.chapters):
        payload = model_payload(args, {field_name: chapter})
        result = unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/{endpoint}", payload))
        results.append({"chapter_number": chapter, "result": result})
        print(f"[ok] {endpoint} chapter {chapter}", file=sys.stderr)
    return results


def command_generate_chapter_outline(args: argparse.Namespace) -> None:
    print_json(batch_simple_stage(args, "generate-chapter-outline"))


def command_generate_novel_body(args: argparse.Namespace) -> None:
    results = []
    for chapter in parse_chapters(args.chapters):
        outline = find_content(args.base_url, args.project_id, "chapter_outline", chapter)
        payload = model_payload(args, {"chapter_number": chapter})
        if outline:
            payload["content_id"] = outline["id"]
        result = unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/generate-novel-body", payload))
        results.append({"chapter_number": chapter, "source_content_id": outline.get("id") if outline else None, "result": result})
        print(f"[ok] generate-novel-body chapter {chapter}", file=sys.stderr)
    print_json(results)


def command_generate_script(args: argparse.Namespace) -> None:
    print_json(batch_simple_stage(args, "generate-script"))


def command_split_comic_pages(args: argparse.Namespace) -> None:
    results = []
    for chapter in parse_chapters(args.chapters):
        source = find_content(args.base_url, args.project_id, args.source_type, chapter)
        payload = model_payload(
            args,
            {
                "chapter_number": chapter,
                "page_count": args.page_count,
                "visual_style": args.visual_style,
            },
        )
        if source:
            payload["content_id"] = source["id"]
        result = unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/split-comic-pages", payload))
        results.append({"chapter_number": chapter, "source_content_id": source.get("id") if source else None, "result": result})
        print(f"[ok] split-comic-pages chapter {chapter}", file=sys.stderr)
    print_json(results)


def command_generate_storyboard(args: argparse.Namespace) -> None:
    results = []
    for chapter in parse_chapters(args.chapters):
        source = find_content(args.base_url, args.project_id, args.source_type, chapter)
        if not source:
            results.append({"chapter_number": chapter, "error": f"missing {args.source_type} content"})
            print(f"[skip] missing {args.source_type} for chapter {chapter}", file=sys.stderr)
            continue
        payload = model_payload(args, {"content_id": source["id"]})
        result = unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/generate-storyboard", payload))
        results.append({"chapter_number": chapter, "source_content_id": source["id"], "result": result})
        print(f"[ok] generate-storyboard chapter {chapter}", file=sys.stderr)
    print_json(results)


def command_match_references(args: argparse.Namespace) -> None:
    results = []
    for chapter in parse_chapters(args.chapters):
        source = find_content(args.base_url, args.project_id, args.source_type, chapter)
        if not source:
            results.append({"chapter_number": chapter, "error": f"missing {args.source_type} content"})
            print(f"[skip] missing {args.source_type} for chapter {chapter}", file=sys.stderr)
            continue
        payload = model_payload(args, {"content_id": source["id"]})
        result = unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/match-reference-assets", payload))
        results.append({"chapter_number": chapter, "source_content_id": source["id"], "result": result})
        print(f"[ok] match-reference-assets chapter {chapter}", file=sys.stderr)
    print_json(results)


def command_run_pipeline(args: argparse.Namespace) -> None:
    payload = model_payload(
        args,
        {
            "stages": args.stages,
            "chapters": parse_chapters(args.chapters) if args.chapters else [],
            "chapter_count": args.chapter_count,
            "page_count": args.page_count,
            "visual_style": args.visual_style,
            "skip_existing": args.skip_existing,
            "continue_on_error": args.continue_on_error,
            "match_source_type": args.match_source_type,
        },
    )
    print_json(unwrap(api_request(args.base_url, "POST", f"/creative-projects/{args.project_id}/run-pipeline", payload)))


def command_export_novel(args: argparse.Namespace) -> None:
    project = unwrap(api_request(args.base_url, "GET", f"/creative-projects/{args.project_id}"))
    bodies = list_contents(args.base_url, args.project_id, "novel_body")
    bodies = sorted(bodies, key=lambda item: (item.get("chapter_number") or 0, item.get("created_at") or ""))
    lines = [f"# {project.get('title') or '未命名作品'}", ""]
    for item in bodies:
        chapter = item.get("chapter_number") or "?"
        title = item.get("title") or f"第{chapter}章"
        text = (item.get("text_content") or "").strip()
        lines.extend([f"## 第{chapter}章 {title}", "", text, ""])
    output = "\n".join(lines).rstrip() + "\n"
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print_json({"path": str(out_path), "chapters": len(bodies), "characters": len(output)})


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="YLCraft API base URL")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds")


def add_model(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--template-id", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive YLCraft creative-project workflows through the API.")
    add_common(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    command = subparsers.add_parser("list-projects")
    command.add_argument("--limit", type=int, default=20)
    command.add_argument("--offset", type=int, default=0)
    command.add_argument("--status", default=None)
    command.add_argument("--project-type", default=None)
    command.add_argument("--full", action="store_true")
    command.set_defaults(func=command_list_projects)

    command = subparsers.add_parser("create-project")
    command.add_argument("--title", default="")
    command.add_argument("--idea", default="")
    command.add_argument("--project-type", default="short_drama")
    command.add_argument("--source-type", default="original_idea")
    command.set_defaults(func=command_create_project)

    command = subparsers.add_parser("inspect")
    command.add_argument("--project-id", required=True)
    command.set_defaults(func=command_inspect)

    command = subparsers.add_parser("contents")
    command.add_argument("--project-id", required=True)
    command.add_argument("--content-type", default=None)
    command.set_defaults(func=command_contents)

    command = subparsers.add_parser("logs")
    command.add_argument("--project-id", required=True)
    command.add_argument("--stage", default=None)
    command.add_argument("--status", default=None)
    command.add_argument("--limit", type=int, default=20)
    command.add_argument("--offset", type=int, default=0)
    command.set_defaults(func=command_logs)

    command = subparsers.add_parser("generate-outline")
    command.add_argument("--project-id", required=True)
    command.add_argument("--idea", default="")
    add_model(command)
    command.set_defaults(func=command_generate_outline)

    command = subparsers.add_parser("sync-characters")
    command.add_argument("--project-id", required=True)
    command.set_defaults(func=command_sync_characters)

    command = subparsers.add_parser("generate-chapter-plan")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapter-count", type=int, default=12)
    add_model(command)
    command.set_defaults(func=command_generate_chapter_plan)

    command = subparsers.add_parser("generate-chapter-outline")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapters", required=True)
    add_model(command)
    command.set_defaults(func=command_generate_chapter_outline)

    command = subparsers.add_parser("generate-novel-body")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapters", required=True)
    add_model(command)
    command.set_defaults(func=command_generate_novel_body)

    command = subparsers.add_parser("generate-script")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapters", required=True)
    add_model(command)
    command.set_defaults(func=command_generate_script)

    command = subparsers.add_parser("split-comic-pages")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapters", required=True)
    command.add_argument("--source-type", default="novel_body")
    command.add_argument("--page-count", type=int, default=10)
    command.add_argument("--visual-style", default=None)
    add_model(command)
    command.set_defaults(func=command_split_comic_pages)

    command = subparsers.add_parser("generate-storyboard")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapters", required=True)
    command.add_argument("--source-type", default="script")
    add_model(command)
    command.set_defaults(func=command_generate_storyboard)

    command = subparsers.add_parser("match-references")
    command.add_argument("--project-id", required=True)
    command.add_argument("--chapters", required=True)
    command.add_argument("--source-type", default="storyboard")
    add_model(command)
    command.set_defaults(func=command_match_references)

    command = subparsers.add_parser("run-pipeline")
    command.add_argument("--project-id", required=True)
    command.add_argument(
        "--stages",
        nargs="*",
        default=[],
        help="Stages such as outline chapter_plan chapter_outline novel_body script storyboard match_references comic_pages",
    )
    command.add_argument("--chapters", default="")
    command.add_argument("--chapter-count", type=int, default=None)
    command.add_argument("--page-count", type=int, default=10)
    command.add_argument("--visual-style", default=None)
    command.add_argument("--match-source-type", default="storyboard")
    command.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    command.add_argument("--continue-on-error", action="store_true")
    add_model(command)
    command.set_defaults(func=command_run_pipeline)

    command = subparsers.add_parser("export-novel")
    command.add_argument("--project-id", required=True)
    command.add_argument("--out", required=True)
    command.set_defaults(func=command_export_novel)

    return parser


def main() -> int:
    global REQUEST_TIMEOUT
    parser = build_parser()
    args = parser.parse_args()
    REQUEST_TIMEOUT = max(1, int(args.timeout))
    try:
        args.func(args)
        return 0
    except ApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
