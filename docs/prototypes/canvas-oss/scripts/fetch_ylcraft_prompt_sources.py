#!/usr/bin/env python3
"""Dump YLCraft-backend prompt sources that the reference registry does not carry.

The unified dataset is built from three inputs. Two of them are snapshots that
live under data/prompt-sources/ (git-ignored, regenerated on demand):

  data/prompt-sources/*.json               reference registry snapshots
  data/prompt-sources/ylcraft-backend/*.json   <- written by this script
  backend/storage/image_prompt_references/sources/imi-*.json   (IMI cache)

YLCraft parses some upstream repos differently from the registry snapshot
(README_zh.md vs the English README), so those sources are complementary rather
than duplicates — without them the union is incomplete.

Usage (backend must be running on :8000):
    python scripts/fetch_ylcraft_prompt_sources.py
    python scripts/fetch_ylcraft_prompt_sources.py --base http://127.0.0.1:8000 --source youmind-gpt-image-2
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # docs/prototypes/canvas-oss
OUT_DIR = ROOT / "data" / "prompt-sources" / "ylcraft-backend"
TARGETS = ["youmind-gpt-image-2", "ylcraft-my-image-prompts"]
PAGE_SIZE = 100


def fetch_page(base: str, source_id: str, page: int) -> dict:
    url = f"{base}/api/v1/image-prompts/references?source_id={source_id}&page={page}&page_size={PAGE_SIZE}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    # Ignore shell proxy env vars: a half-configured proxy breaks localhost too.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=120) as response:
        return json.load(response)


def dump(base: str, source_id: str, out_dir: Path) -> None:
    items: list[dict] = []
    page = 1
    total = 0
    while True:
        payload = fetch_page(base, source_id, page)
        batch = payload.get("items") or []
        total = payload.get("total", len(batch))
        items.extend(batch)
        if not batch or len(items) >= total:
            break
        page += 1
    dest = out_dir / f"{source_id}.json"
    dest.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{source_id:32s} total={total:5d} fetched={len(items):5d} -> {dest.name} {dest.stat().st_size / 1024 / 1024:.2f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot YLCraft prompt sources the registry lacks.")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="YLCraft backend base URL")
    parser.add_argument("--source", default="", help="Only dump this source id")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    targets = [args.source] if args.source else TARGETS
    for source_id in targets:
        dump(args.base, source_id, args.out)


if __name__ == "__main__":
    main()
