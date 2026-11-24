#!/usr/bin/env python3
"""Build a light prompt sample for OUR prototype page (features/prompts.html).

The canvas-oss dataset is 74 MB across 11 files — fine for a Vite app that lazy
loads per source, too heavy to drop into a single vanilla prototype page. The
prototype only needs enough cards to show the information structure, so this
takes the first N prompts of every source, keeps the fields the page renders,
and records the real per-source totals so the hero can show honest numbers.

    python scripts/make_prompt_sample.py            # 150 per source
    python scripts/make_prompt_sample.py --per 80

Output: docs/prototypes/features/data/prompts.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # docs/prototypes/canvas-oss
PUBLIC = ROOT / "web" / "public" / "prompt-data"
OUT = ROOT.parent / "features" / "data" / "prompts.json"

PROMPT_LIMIT = 1500


def short_prompt(text: str) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= PROMPT_LIMIT:
        return text, False
    return text[:PROMPT_LIMIT], True


def build(per_source: int) -> None:
    manifest = json.loads((PUBLIC / "manifest.json").read_text(encoding="utf-8"))
    sources: list[dict] = []
    items: list[dict] = []

    for source in manifest["sources"]:
        rows = json.loads((PUBLIC / f"{source['id']}.json").read_text(encoding="utf-8"))
        usable = [row for row in rows if (row.get("title") or "").strip() and (row.get("prompt") or "").strip()]
        picked = usable[:per_source]
        sources.append(
            {
                "id": source["id"],
                "name": source["name"],
                "total": source["count"],
                "dataset": source["dataset"],
                "modelGroup": source.get("modelGroup", ""),
                "sampled": len(picked),
            }
        )
        for index, row in enumerate(picked):
            prompt, truncated = short_prompt(row.get("prompt"))
            items.append(
                {
                    "id": f"{source['id']}-{index + 1:04d}",
                    "sourceId": source["id"],
                    "sourceName": source["name"],
                    "dataset": source["dataset"],
                    "modelGroup": row.get("modelGroup") or source.get("modelGroup", ""),
                    "title": (row.get("title") or "").strip(),
                    "prompt": prompt,
                    "truncated": truncated,
                    "tags": (row.get("tags") or [])[:6],
                    "coverUrl": row.get("coverUrl") or "",
                    "imageCount": len(row.get("referenceImages") or []),
                    "sourceUrl": row.get("sourceUrl") or "",
                }
            )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": f"原型示例数据：每源取前 {per_source} 条；total 字段是真实条数（13,309）。由 canvas-oss/scripts/make_prompt_sample.py 生成。",
        "perSource": per_source,
        "totalReal": sum(s["total"] for s in sources),
        "totalSampled": len(items),
        "sources": sources,
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(sources)} sources / {len(items)} sampled (real {payload['totalReal']}) -> {OUT} {OUT.stat().st_size / 1024 / 1024:.2f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the prototype prompt sample dataset.")
    parser.add_argument("--per", type=int, default=150, help="cards per source")
    args = parser.parse_args()
    build(max(10, args.per))


if __name__ == "__main__":
    main()
