#!/usr/bin/env python3
"""Build unified prompt-library static JSON for the canvas-oss prototype.

Inputs (three datasets, merged as a union — sources are kept side by side, with
only the YouMind source merged item-by-item because the two copies of it hold
disjoint content):
  1. reference-project source snapshots : canvas-oss/data/prompt-sources/*.json
  2. YLCraft IMI cached sources         : backend/storage/image_prompt_references/sources/imi-*.json
  3. YLCraft backend-only sources       : canvas-oss/data/prompt-sources/ylcraft-backend/*.json
     (dumped from /api/v1/image-prompts/references by fetch_ylcraft_prompt_sources.py;
     sources the registry lacks, or holds a partial set of)

Both snapshot directories live under data/ which is git-ignored; regenerate them
with `--fetch` (registry) and fetch_ylcraft_prompt_sources.py (YLCraft backend).

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
YL_BACKEND_DATA = ROOT / "data" / "prompt-sources" / "ylcraft-backend"
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

# Sources that exist in YLCraft's own library but not in the reference registry
# snapshot. mode="merge" folds the extra prompts into the registry source with
# the same id (YouMind: registry carries the English README, YLCraft parses
# README_zh.md, and the two share exactly one prompt — neither alone is whole).
YL_BACKEND_SOURCES = [
    ("youmind-gpt-image-2", "YouMind GPT Image 2", "https://github.com/YouMind-OpenLab/awesome-gpt-image-2", "ChatGPT", "merge"),
    ("ylcraft-my-image-prompts", "我的生图提示词", "", "ChatGPT", "own"),
]

# Mirrors YLCraft's PROMPT_TAG_PRIORITY from
# backend/app/services/image_prompt_reference/service.py — parsed at build time
# so the prototype's filter chips rank exactly like the real YLCraft library.
YL_SERVICE_PY = ROOT.parents[2] / "backend" / "app" / "services" / "image_prompt_reference" / "service.py"
TAG_STOPWORDS = {
    "image", "chatgpt", "gpt-4o", "gpt-image-2", "nano banana 2", "nano banana pro",
    "nano-banana-pro", "nanobanana2", "nanobananapro", "awesome-gpt-image", "awesome-gpt4o-image-prompts",
    "所有提示词", "我的提示词",
}


def load_tag_priority() -> tuple[list[str], set[str]]:
    """Parse the real PROMPT_TAG_PRIORITY tuple and its index from YLCraft source."""
    import re
    text = YL_SERVICE_PY.read_text(encoding="utf-8")
    match = re.search(r"PROMPT_TAG_PRIORITY:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\n\)", text, re.S)
    priority = re.findall(r'"([^"]+)"', match.group(1)) if match else []
    return priority, {tag.lower(): i for i, tag in enumerate(priority)}


def clean_tags(raw: Any) -> list[str]:
    """Strip stray spaces (IMI tags like '人 像' / ' 人像') and drop model/source tags."""
    import re
    seen: set[str] = set()
    result: list[str] = []
    for value in raw if isinstance(raw, list) else []:
        tag = re.sub(r"\s+", " ", as_str(value)).strip()
        key = tag.lower()
        if not tag or key in TAG_STOPWORDS or key in seen or tag.startswith("@") or len(tag) > 28:
            continue
        seen.add(key)
        result.append(tag)
    return result


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
        "tags": clean_tags(item.get("tags")),
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
        "tags": clean_tags(item.get("tags")),
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


ONLINE_BASE = "https://raw.githubusercontent.com/yukkcat/image-prompts/main/dist/sources"


def prompt_key(text: str) -> str:
    """Whitespace/case-insensitive key used to dedupe merged prompt bodies."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def usable_cover(url: str) -> str:
    """Drop shields.io badges — README-derived rows point their cover at one."""
    if not url or "img.shields.io" in url:
        return ""
    return url


def backend_images(value: Any) -> list[str]:
    urls: list[str] = []
    for entry in value if isinstance(value, list) else []:
        if isinstance(entry, dict):
            url = as_str(entry.get("url") or entry.get("image_url") or entry.get("src"))
        else:
            url = as_str(entry)
        if url:
            urls.append(url)
    return urls


def normalise_backend(item: dict, sid: str, source_name: str, model_group: str) -> dict:
    """YLCraft backend rows (/api/v1/image-prompts/references) -> shared schema."""
    cn = as_str(item.get("chinese_prompt"))
    en = as_str(item.get("english_prompt"))
    prompt = as_str(item.get("prompt")) or cn or en
    refs = backend_images(item.get("image_items"))
    cover = usable_cover(as_str(item.get("cover_url"))) or (refs[0] if refs else "")
    return {
        "id": as_str(item.get("external_id")) or as_str(item.get("id")) or f"{sid}-{prompt_key(prompt)[:24]}",
        "sourceId": sid,
        "sourceName": source_name,
        "dataset": "ylcraft-library",
        "title": as_str(item.get("title")) or prompt[:48],
        "prompt": prompt,
        "description": as_str(item.get("description")),
        "tags": clean_tags(item.get("tags")),
        "coverUrl": cover,
        "referenceImages": refs,
        "sourceUrl": as_str(item.get("source_url") or item.get("detail_url")),
        "chinesePrompt": cn,
        "englishPrompt": en,
        "model": as_str(item.get("model_hint")),
        "modelGroup": as_str(item.get("model_group")) or model_group,
        "language": as_str(item.get("language")),
        "viewCount": item.get("view_count"),
        "likeCount": item.get("like_count"),
        "copyCount": item.get("copy_count"),
        "createdAt": as_str(item.get("remote_created_at") or item.get("created_at")),
        "updatedAt": as_str(item.get("remote_updated_at") or item.get("updated_at")),
        "preview": prompt[:360],
        "raw": item,
    }


def merge_items(base: list[dict], extra: list[dict]) -> tuple[list[dict], int, int]:
    """Append prompts not already present (dedupes `extra` internally too).

    Returns (merged, added, skipped_duplicates).
    """
    seen = {prompt_key(item.get("prompt", "")) for item in base}
    seen.discard("")
    merged = list(base)
    added = 0
    skipped = 0
    for item in extra:
        key = prompt_key(item.get("prompt", ""))
        if not key:
            skipped += 1
            continue
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        merged.append(item)
        added += 1
    return merged, added, skipped



def fetch_online_snapshot(sid: str, dest: Path) -> bool:
    """Refresh one OSS source's raw snapshot from upstream. Returns success."""
    import urllib.request
    url = f"{ONLINE_BASE}/{sid}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # urlopen honours HTTP_PROXY; clear it so a broken proxy cannot block us.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=90) as response:
            payload = response.read()
        json.loads(payload)  # validate before writing
        dest.write_bytes(payload)
        print(f"  [fetch] {sid}: {len(payload)} bytes from upstream")
        return True
    except Exception as error:  # noqa: BLE001 - CLI tool, report and continue
        print(f"  [fetch] {sid}: FAILED ({error}); keeping existing snapshot")
        return False


def build() -> None:
    parser = argparse.ArgumentParser(description="Build or incrementally sync the unified prompt dataset.")
    parser.add_argument("--oss-data", type=Path, default=OSS_DATA)
    parser.add_argument("--yl-data", type=Path, default=YL_DATA)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--source", default="", help="Only sync this source id (incremental; keeps other sources in manifest).")
    parser.add_argument("--fetch", action="store_true", help="Re-fetch the raw snapshot from upstream before building (OSS sources only).")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    priority, _ = load_tag_priority()
    (args.out / "tag-priority.json").write_text(
        json.dumps({"version": 1, "tags": priority, "stopwords": sorted(TAG_STOPWORDS)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not args.source:
        print(f"Tag priority: {len(priority)} tags exported from {YL_SERVICE_PY.name}")

    # Incremental mode: preserve existing manifest entries for untouched sources.
    manifest_path = args.out / "manifest.json"
    existing: list[dict] = []
    if args.source and manifest_path.exists():
        existing = [entry for entry in json.loads(manifest_path.read_text(encoding="utf-8")).get("sources", []) if entry.get("id") != args.source]

    manifest: list[dict] = list(existing)
    only = args.source

    for sid, name, homepage, group in OSS_SOURCES:
        if only and sid != only:
            continue
        src = args.oss_data / f"{sid}.json"
        if args.fetch and fetch_online_snapshot(sid, src) is False:
            # keep the existing snapshot on failure; still rebuild from it
            pass
        if not src.exists():
            print(f"[skip] missing OSS source: {src}")
            continue
        rows = json.loads(src.read_text(encoding="utf-8"))
        items = [normalise_oss(row, sid, name, group) for row in rows if isinstance(row, dict)]
        _write_source(args.out, sid, name, homepage, group, "reference-project", items, manifest)

    for sid, name, homepage, group in YL_SOURCES:
        if only and sid != only:
            continue
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

    # YLCraft-backend sources: either fold into the registry source (merge) or
    # publish as their own source (own).
    for sid, name, homepage, group, mode in YL_BACKEND_SOURCES:
        if only and sid != only:
            continue
        src = YL_BACKEND_DATA / f"{sid}.json"
        if not src.exists():
            print(f"[skip] missing YLCraft backend source: {src}")
            continue
        rows = [row for row in json.loads(src.read_text(encoding="utf-8")) if isinstance(row, dict)]
        extra = [normalise_backend(row, sid, name, group) for row in rows]
        if mode == "merge":
            base_path = args.out / f"{sid}.json"
            if not base_path.exists():
                print(f"[skip] no registry snapshot to merge into for {sid}")
                continue
            base = json.loads(base_path.read_text(encoding="utf-8"))
            merged, added, skipped = merge_items(base, extra)
            for item in merged:
                item["dataset"] = "merged"
            manifest = [entry for entry in manifest if entry.get("id") != sid]
            _write_source(args.out, sid, name, homepage, group, "merged", merged, manifest)
            print(f"    merge: registry {len(base)} + YLCraft {len(extra)} rows -> +{added} new, {skipped} duplicate skipped")
        else:
            _write_source(args.out, sid, name, homepage, group, "ylcraft-library", extra, manifest)

    if only and not any(entry.get("id") == only for entry in manifest):
        print(f"[error] source '{only}' not found in known sources")
        return

    manifest.sort(key=lambda s: (s["dataset"] != "reference-project", s["id"]))
    (manifest_path).write_text(
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
    scope = f"source={only}" if only else "all sources"
    print(f"Built {len(manifest)} sources / {total} prompts into {args.out} ({scope})")


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
