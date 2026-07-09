"""Download IMI prompt JSON and preview images into the local prompt cache.

Default behavior:
  1. Fetch the three IMI JSON collections into backend/storage/image_prompt_references/sources.
  2. Download referenced images into backend/storage/image_prompt_references/media.
  3. Sync normalized prompt references into the configured database.

Examples:
  python backend/scripts/sync_imi_prompt_library.py --limit 20
  python backend/scripts/sync_imi_prompt_library.py --source imi-nano-banana-pro-prompts --workers 12
  python backend/scripts/sync_imi_prompt_library.py --no-images --sync-db
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from app.db.database import SessionLocal  # noqa: E402
from app.services.image_prompt_reference.service import (  # noqa: E402
    DEFAULT_IMAGE_PROMPT_SOURCES,
    ImagePromptReferenceService,
    _cached_media_path,
    _safe_filename,
    image_prompt_storage_root,
)


IMI_SOURCE_IDS = {
    "imi-chatgpt-prompts",
    "imi-nano-banana-2-prompts",
    "imi-nano-banana-pro-prompts",
}


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


@dataclass(frozen=True)
class DownloadJob:
    source_id: str
    item_id: str
    filename: str
    url: str
    target: Path


def _source_url(source) -> str:
    return f"{source.raw_base_url.rstrip('/')}/{source.raw_path.lstrip('/')}"


def _load_sources(selected: str) -> list[Any]:
    sources = [source for source in DEFAULT_IMAGE_PROMPT_SOURCES if source.id in IMI_SOURCE_IDS]
    if selected and selected != "all":
        sources = [source for source in sources if source.id == selected]
    if not sources:
        raise SystemExit(f"No IMI prompt source matched: {selected}")
    return sources


def _fetch_json(source, client: httpx.Client, *, force: bool) -> tuple[Path, list[dict[str, Any]]]:
    source_dir = image_prompt_storage_root() / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    target = source_dir / f"{source.id}.json"
    if target.is_file() and not force:
        _log(f"[json] use cache: {source.id} -> {target}")
        payload = target.read_text(encoding="utf-8")
    else:
        _log(f"[json] fetch: {source.id} -> {_source_url(source)}")
        response = client.get(_source_url(source))
        response.raise_for_status()
        payload = response.text
        target.write_text(payload, encoding="utf-8")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"{source.id} JSON is not a list")
    return target, [item for item in data if isinstance(item, dict)]


def _jobs_for_source(source_id: str, items: list[dict[str, Any]], *, limit: int = 0) -> list[DownloadJob]:
    jobs: list[DownloadJob] = []
    selected = items[:limit] if limit and limit > 0 else items
    for index, item in enumerate(selected, start=1):
        item_id = str(item.get("id") or item.get("source_id") or index).strip()
        images = item.get("images") if isinstance(item.get("images"), list) else []
        for image_index, image in enumerate(images, start=1):
            if not isinstance(image, dict):
                continue
            url = str(image.get("url") or "").strip()
            if not url:
                continue
            filename = _safe_filename(str(image.get("filename") or Path(str(image.get("path") or "")).name or f"{item_id}-{image_index}.jpg"))
            jobs.append(
                DownloadJob(
                    source_id=source_id,
                    item_id=item_id,
                    filename=filename,
                    url=url,
                    target=_cached_media_path(source_id, item_id, filename),
                )
            )
    return jobs


def _download_one(job: DownloadJob, *, timeout: float, force: bool) -> dict[str, Any]:
    if job.target.is_file() and job.target.stat().st_size > 0 and not force:
        return {"status": "skipped", "url": job.url, "path": str(job.target)}
    job.target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(job.url)
        response.raise_for_status()
        job.target.write_bytes(response.content)
    return {"status": "downloaded", "url": job.url, "path": str(job.target), "bytes": job.target.stat().st_size}


def _download_jobs(
    jobs: list[DownloadJob],
    *,
    workers: int,
    timeout: float,
    force: bool,
    progress_every: int,
) -> dict[str, Any]:
    if not jobs:
        return {"total": 0, "downloaded": 0, "skipped": 0, "failed": 0, "errors": []}
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    errors: list[dict[str, str]] = []
    total = len(jobs)
    progress_every = max(1, progress_every)
    _log(f"[images] start: {total} files, workers={workers}, force={force}")
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_download_one, job, timeout=timeout, force=force) for job in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            try:
                result = future.result()
                status = str(result.get("status") or "failed")
                counts[status] = counts.get(status, 0) + 1
            except Exception as exc:
                counts["failed"] += 1
                errors.append({"error": str(exc)})
            if done == total or done % progress_every == 0:
                _log(
                    "[images] "
                    f"{done}/{total} "
                    f"downloaded={counts.get('downloaded', 0)} "
                    f"skipped={counts.get('skipped', 0)} "
                    f"failed={counts.get('failed', 0)}"
                )
    return {"total": len(jobs), **counts, "errors": errors[:20]}


def _sync_database(source_payloads: list[tuple[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        for source_id, payload in source_payloads:
            _log(f"[db] sync start: {source_id}")
            source = service.get_source(source_id)
            if source is None:
                results.append({"success": False, "source_id": source_id, "error": "source not found"})
                continue
            result = service.sync_source_payload(source, payload)
            _log(
                "[db] sync done: "
                f"{source_id} total={result.get('total')} "
                f"created={result.get('created')} updated={result.get('updated')}"
            )
            results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync IMI prompt JSON and images into YLCraft local cache.")
    parser.add_argument("--source", default="all", help="Source id to sync, or all.")
    parser.add_argument("--limit", type=int, default=0, help="Limit prompt items per source. Useful for smoke tests.")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent image downloads.")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds.")
    parser.add_argument("--force", action="store_true", help="Re-fetch JSON and re-download existing images.")
    parser.add_argument("--no-images", action="store_true", help="Only fetch JSON and sync database.")
    parser.add_argument("--no-sync-db", action="store_true", help="Download files but do not write database rows.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print image download progress every N files.")
    args = parser.parse_args()

    sources = _load_sources(args.source)
    _log(
        "[start] "
        f"sources={','.join(source.id for source in sources)} "
        f"limit={args.limit or 'all'} workers={args.workers} "
        f"images={'no' if args.no_images else 'yes'} db={'no' if args.no_sync_db else 'yes'}"
    )
    source_payloads: list[tuple[str, str]] = []
    summary: dict[str, Any] = {"sources": []}
    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        for source in sources:
            json_path, items = _fetch_json(source, client, force=args.force)
            payload = json_path.read_text(encoding="utf-8")
            selected_count = min(len(items), args.limit) if args.limit and args.limit > 0 else len(items)
            _log(f"[source] {source.id}: items={selected_count}/{len(items)}")
            source_payloads.append((source.id, json.dumps(items[:selected_count], ensure_ascii=False) if args.limit and args.limit > 0 else payload))
            jobs = [] if args.no_images else _jobs_for_source(source.id, items, limit=args.limit)
            download_result = _download_jobs(
                jobs,
                workers=args.workers,
                timeout=args.timeout,
                force=args.force,
                progress_every=args.progress_every,
            )
            summary["sources"].append(
                {
                    "source_id": source.id,
                    "json_path": str(json_path),
                    "items": selected_count,
                    "images": download_result,
                }
            )

    if not args.no_sync_db:
        summary["database"] = _sync_database(source_payloads)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if any(source["images"].get("failed", 0) for source in summary["sources"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
