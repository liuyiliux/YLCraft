#!/usr/bin/env python3
"""Build unified prompt-library static JSON for the canvas-oss prototype.

Inputs (two datasets, merged as a union — not deduplicated across sources):
  1. reference-project source snapshots : canvas-oss/data/prompt-sources/*.json
  2. YLCraft IMI cached sources         : backend/storage/image_prompt_references/sources/imi-*.json

Output (canvas-oss/web/public/prompt-data/):
  manifest.json          source list for the UI
  <sourceId>.json        full prompt items for each source

Fields are preserved in full from both schemas; the only change is normalising
image URLs to absolute links where possible and adding a few common keys so the
shared UI can render both schemas without branching.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]  # docs/prototypes/canvas-oss
OSS_DATA = ROOT / "data" / "prompt-sources"
YL_DATA = ROOT.parents[2] / "backend" / "storage" / "image_prompt_references" / "sources"
OUT_DIR = ROOT / "web" / "public" / "prompt-data"

OSS_SOURCES = [
    ("banana-prompt-quicker", "Banana Prompt Quicker", "https://glidea.github.io/banana-prompt-quicker/", "ChatGPT"),
    ("davidwu-gpt-image2-prompts", "DavidWu GPT Image 2", "https://github.com/davidwuw0811-boop/awesome-gpt-image2-prompts", "ChatGPT"),
    ("freestylefly-gpt-image-2", "Freestylefly GPT Image 2", "https://github.com/freestylefly/awesome-gpt-image-2", "ChatGPT"),
    ("awesome-gpt-image", "Awesome GPT Image", "https://github.com/ZeroLu/awesome-gpt-image", "ChatGPT"),
    ("awesome-gpt4o-image-prompts", "Awesome GPT-4o", "https://github.com/ImgEdify/Awesome-GPT4o-Image-Prompts", "ChatGPT"),
    ("youmind-gpt-image-2", "YouMind GPT Image 2", "https://github.com/YouMind-OpenLab/awesome-gpt-image-2", "ChatGPT"),
    ("youmind-nano-banana-pro", "YouMind Nano Banana Pro", "https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts", "NanoBananaPro"),
]

YL_SOURCES = [
    ("imi-chatgpt-prompts", "IMI ChatGPT Prompt Gallery", "https://prompt.imi.ccwu.cc/ChatGPT", "ChatGPT"),
    ("imi-nano-banana-2-prompts", "IMI Nano Banana 2", "https://prompt.imi.ccwu.cc/Nano%20Banana%202", "NanoBanana2"),
    ("imi-nano-banana-pro-prompts", "IMI Nano Banana Pro", "https://prompt.imi.ccwu.cc/Nano%20Banana%20Pro", "NanoBananaPro"),
]

IMI_IMG_BASE = "https://img.opennana.com/pthumbs/prompts/assets/"


def as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def absolute_imi_image(value: Any) -> str:
    """IMI cover_image may be a full URL or a path relative to the media host."""
    text = as_str(value).strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://", "data:")):
        return text
    text = text.lstrip("/")
    if text.startswith("prompts/assets/"):
        return "https://img.opennana.com/" + text
    if re.match(r"^ChatGPT/|^Nano", text):
        # local cached path from cache_prompt_reference_media.py -> keep as-is,
        # the UI shows a placeholder when it cannot be loaded offline
        return text
    return IMI_IMG_BASE + text


def normalise_oss(item: dict, sid: str, source_name: str, model_group: str) -> dict:
    prompt = as_str(item.get("prompt"))
    description = as_str(item.get("description"))
    refs = [as_str(u) for u in (item.get("referenceImageUrls") or []) if as_str(u)]
    cover = as_str(item.get("coverUrl")) or (refs[0] if refs else "")
    return {
        "id": as_str(item.get("id")) or f"{sid}-{item.get('title', '')[:24]}",
        "sourceId": sid,
        "sourceName": source_name,
        "dataset": "reference-project",
        "title": as_str(item.get("title")),
        "prompt": prompt,
        "description": description,
        "tags": [as_str(t) for t in (item.get("tags") or []) if as_str(t)],
        "coverUrl": cover,
        "referenceImages": refs,
        "author": as_str(item.get("author")),
        "sourceUrl": as_str(item.get("sourceUrl")),
        "imageMode": as_str(item.get("imageMode")),
        "imageModel": as_str(item.get("imageModel")),
        "imageSize": as_str(item.get("imageSize")),
        "imageCount": item.get("imageCount"),
        "modelGroup": model_group,
        "createdAt": as_str(item.get("createdAt")),
        "updatedAt": as_str(item.get("updatedAt")),
        "preview": as_str(item.get("preview")) or prompt[:360],
        # keep the original row untouched for full fidelity
        "raw": item,
    }


def normalise_imi(item: dict, sid: str, source_name: str, model_group: str) -> dict:
    cn = as_str(item.get("chinese_prompt"))
    en = as_str(item.get("english_prompt"))
    prompt = cn or en
    refs = [absolute_imi_image(u) for u in (item.get("images") or []) if as_str(u)]
    cover = absolute_imi_image(item.get("cover_image") or item.get("thumbnail"))
    if not cover and refs:
        cover = refs[0]
    return {
        "id": f"{sid}:{as_str(item.get('id'))}",
        "sourceId": sid,
        "sourceName": source_name,
        "dataset": "ylcraft-imi",
        "title": as_str(item.get("title")),
        "prompt": prompt,
        "description": as_str(item.get("description")),
        "tags": [as_str(t) for t in (item.get("tags") or []) if as_str(t)],
        "coverUrl": cover,
        "referenceImages": refs,
        "sourceUrl": as_str(item.get("source_url") or item.get("detail_url")),
        "chinesePrompt": cn,
        "englishPrompt": en,
        "model": as_str(item.get("model")),
        "modelGroup": model_group,
        "viewCount": item.get("view_count"),
        "likeCount": item.get("like_count"),
        "copyCount": item.get("copy_count"),
        "createdAt": as_str(item.get("created_at") or item.get("remote_created_at")),
        "updatedAt": as_str(item.get("updated_at") or item.get("remote_updated_at")),
        "preview": prompt[:360],
        "raw": item,
    }


def build() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oss-data", type=Path, default=OSS_DATA)
    parser.add_argument("--yl-data", type=Path, default=YL_DATA)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    for sid, name, homepage, group in OSS_SOURCES:
        src = args.oss_data / f"{sid}.json"
        if not src.exists():
            print(f"[skip] missing OSS source: {src}")
            continue
        rows = json.loads(src.read_text(encoding="utf-8"))
        items = [normalise_oss(row, sid, name, group) for row in rows if isinstance(row, dict)]
        _write_source(args.out, sid, name, homepage, group, "reference-project", items, manifest)

    for sid, name, homepage, group in YL_SOURCES:
        src = args.yl_data / f"{sid}.json"
        if not src.exists():
            print(f"[skip] missing YL source: {src}")
            continue
        rows = json.loads(src.read_text(encoding="utf-8"))
        items = [normalise_imi(row, sid, name, group) for row in rows if isinstance(row, dict)]
        # IMI images may be huge; strip raw rows for the biggest source to keep
        # the static JSON reasonable while keeping the normalised fields.
        if len(items) > 3000:
            for item in items:
                item.pop("raw", None)
        _write_source(args.out, sid, name, homepage, group, "ylcraft-imi", items, manifest)

    manifest.sort(key=lambda s: (s["dataset"] != "reference-project", s["id"]))
    (args.out / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "note": "Union of reference-project prompt sources and YLCraft downloaded IMI libraries. Fields preserved from both schemas.",
                "sources": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    total = sum(s["count"] for s in manifest)
    print(f"Built {len(manifest)} sources / {total} prompts into {args.out}")


def _write_source(out: Path, sid: str, name: str, homepage: str, group: str, dataset: str, items: list[dict], manifest: list[dict]) -> None:
    filename = f"{sid}.json"
    (out / filename).write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    manifest.append(
        {
            "id": sid,
            "name": name,
            "url": f"/prompt-data/{filename}",
            "homepage": homepage,
            "modelGroup": group,
            "dataset": dataset,
            "count": len(items),
        }
    )
    print(f"  {sid:34s} {len(items):5d} prompts  {os.path.getsize(out / filename) / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    build()
