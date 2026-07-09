"""Cache remote image prompt reference media into local storage.

This script works for every prompt reference already stored in the database,
including markdown/json sources that were synced before the IMI large
collections. It downloads remote cover/preview images and rewrites media URLs to
the shared local API format:

  /api/v1/image-prompts/media/{source_id}/{item_id}/{filename}

Examples:
  python backend/scripts/cache_prompt_reference_media.py --source all
  python backend/scripts/cache_prompt_reference_media.py --source awesome-gpt-image --limit 100
  python backend/scripts/cache_prompt_reference_media.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from sqlalchemy import or_
from sqlmodel import select

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from app.db.database import SessionLocal  # noqa: E402
from app.db.models.image_prompt_reference import ImagePromptReference  # noqa: E402
from app.services.image_prompt_reference.service import (  # noqa: E402
    _cached_media_path,
    _safe_filename,
    _slug,
)


IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)]+)\)")


@dataclass(frozen=True)
class MediaJob:
    reference_id: str
    source_id: str
    item_id: str
    original_url: str
    filename: str
    target: Path

    @property
    def local_url(self) -> str:
        return "/api/v1/image-prompts/media/{}/{}/{}".format(
            quote(_slug(self.source_id, "source"), safe=""),
            quote(_slug(self.item_id, "item"), safe=""),
            quote(_safe_filename(self.filename), safe=""),
        )


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _remote_image_urls(reference: ImagePromptReference) -> list[str]:
    urls: list[str] = []
    cover_url = (reference.cover_url or "").strip()
    if cover_url.startswith("http://") or cover_url.startswith("https://"):
        urls.append(cover_url)
    for match in IMAGE_RE.finditer(reference.preview_markdown or ""):
        url = match.group(1).strip()
        if url.startswith("http://") or url.startswith("https://"):
            urls.append(url)
    return list(dict.fromkeys(urls))


def _jobs_for_reference(reference: ImagePromptReference) -> list[MediaJob]:
    item_id = reference.external_id or reference.id
    jobs: list[MediaJob] = []
    for index, url in enumerate(_remote_image_urls(reference), start=1):
        filename = _safe_filename(Path(url.split("?")[0]).name or f"{item_id}-{index}.jpg")
        jobs.append(
            MediaJob(
                reference_id=reference.id,
                source_id=reference.source_id,
                item_id=item_id,
                original_url=url,
                filename=filename,
                target=_cached_media_path(reference.source_id, item_id, filename),
            )
        )
    return jobs


def _download(job: MediaJob, *, timeout: float, force: bool) -> tuple[MediaJob, str]:
    if job.target.is_file() and job.target.stat().st_size > 0 and not force:
        return job, "skipped"
    job.target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(job.original_url)
        response.raise_for_status()
        job.target.write_bytes(response.content)
    return job, "downloaded"


def _load_references(source_id: str, limit: int) -> list[ImagePromptReference]:
    with SessionLocal() as session:
        query = select(ImagePromptReference).where(
            or_(
                ImagePromptReference.cover_url.like("http%"),
                ImagePromptReference.preview_markdown.like("%http%"),
            )
        )
        if source_id and source_id != "all":
            query = query.where(ImagePromptReference.source_id == source_id)
        if limit > 0:
            query = query.limit(limit)
        rows = list(session.exec(query).all())
    return [row for row in rows if _remote_image_urls(row)]


def _rewrite_database(successful_jobs: list[MediaJob]) -> int:
    by_reference: dict[str, list[MediaJob]] = {}
    for job in successful_jobs:
        by_reference.setdefault(job.reference_id, []).append(job)

    updated = 0
    with SessionLocal() as session:
        for reference_id, jobs in by_reference.items():
            ref = session.get(ImagePromptReference, reference_id)
            if ref is None:
                continue
            replacement = {job.original_url: job.local_url for job in jobs}
            cover = ref.cover_url or ""
            preview = ref.preview_markdown or ""
            for original, local in replacement.items():
                if cover == original:
                    cover = local
                preview = preview.replace(original, local)
            metadata = dict(ref.metadata_json or {})
            metadata["cached_media"] = [
                {"original_url": job.original_url, "local_url": job.local_url, "path": str(job.target)}
                for job in jobs
            ]
            ref.cover_url = cover
            ref.preview_markdown = preview
            ref.metadata_json = metadata
            session.add(ref)
            updated += 1
        session.commit()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache prompt reference media for all sources.")
    parser.add_argument("--source", default="all", help="Source id or all.")
    parser.add_argument("--limit", type=int, default=0, help="Limit references for smoke tests.")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent image downloads.")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds.")
    parser.add_argument("--force", action="store_true", help="Re-download existing cached files.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned work without downloading or updating DB.")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N images.")
    args = parser.parse_args()

    references = _load_references(args.source, args.limit)
    jobs = [job for ref in references for job in _jobs_for_reference(ref)]
    _log(f"[start] references={len(references)} images={len(jobs)} source={args.source}")
    if args.dry_run:
        print({"references": len(references), "images": len(jobs)})
        return 0

    successful_jobs: list[MediaJob] = []
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    progress_every = max(1, args.progress_every)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_download, job, timeout=args.timeout, force=args.force) for job in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            try:
                job, status = future.result()
                counts[status] = counts.get(status, 0) + 1
                successful_jobs.append(job)
            except Exception as exc:
                counts["failed"] += 1
                _log(f"[error] {exc}")
            if done == len(jobs) or done % progress_every == 0:
                _log(f"[media] {done}/{len(jobs)} {counts}")

    updated = _rewrite_database(successful_jobs)
    print({"references": len(references), "images": len(jobs), "updated": updated, **counts})
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
