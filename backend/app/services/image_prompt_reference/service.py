"""Backend sync and search service for image prompt reference examples."""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import case, cast, func, or_, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, select

from app.db.models.asset_hub import AssetNode, AssetRepresentation, AssetType, AssetVersion
from app.db.models.image_prompt_reference import ImagePromptReference, ImagePromptSource


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    name: str
    repo_url: str
    raw_base_url: str
    raw_path: str
    parser: str
    category: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedPromptReference:
    external_id: str
    title: str
    prompt: str
    negative_prompt: str = ""
    cover_url: str = ""
    preview_markdown: str = ""
    tags: tuple[str, ...] = ()
    category: str = ""
    source_url: str = ""
    model_hint: str = ""
    needs_reference_image: bool = False
    language: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


DEFAULT_IMAGE_PROMPT_SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        id="awesome-gpt-image",
        name="ZeroLu awesome-gpt-image",
        repo_url="https://github.com/ZeroLu/awesome-gpt-image",
        raw_base_url="https://raw.githubusercontent.com/ZeroLu/awesome-gpt-image/main",
        raw_path="README.zh-CN.md",
        parser="markdown_sections",
        category="awesome-gpt-image",
        metadata={"model_group": "ChatGPT"},
    ),
    SourceDefinition(
        id="awesome-gpt4o-image-prompts",
        name="ImgEdify Awesome GPT-4o Image Prompts",
        repo_url="https://github.com/ImgEdify/Awesome-GPT4o-Image-Prompts",
        raw_base_url="https://raw.githubusercontent.com/ImgEdify/Awesome-GPT4o-Image-Prompts/main",
        raw_path="README.zh-CN.md",
        parser="markdown_sections",
        category="awesome-gpt4o-image-prompts",
        metadata={"model_hint": "gpt-4o", "model_group": "ChatGPT"},
    ),
    SourceDefinition(
        id="youmind-gpt-image-2",
        name="YouMind awesome-gpt-image-2",
        repo_url="https://github.com/YouMind-OpenLab/awesome-gpt-image-2",
        raw_base_url="https://raw.githubusercontent.com/YouMind-OpenLab/awesome-gpt-image-2/main",
        raw_path="README_zh.md",
        parser="markdown_sections",
        category="youmind-gpt-image-2",
        metadata={"model_hint": "gpt-image-2", "model_group": "ChatGPT"},
    ),
    SourceDefinition(
        id="youmind-nano-banana-pro",
        name="YouMind awesome-nano-banana-pro-prompts",
        repo_url="https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts",
        raw_base_url="https://raw.githubusercontent.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts/main",
        raw_path="README_zh.md",
        parser="markdown_sections",
        category="youmind-nano-banana-pro",
        metadata={"model_hint": "nano-banana-pro", "model_group": "NanoBananaPro"},
    ),
    SourceDefinition(
        id="davidwu-gpt-image2-prompts",
        name="David Wu awesome-gpt-image2-prompts",
        repo_url="https://github.com/davidwuw0811-boop/awesome-gpt-image2-prompts",
        raw_base_url="https://raw.githubusercontent.com/davidwuw0811-boop/awesome-gpt-image2-prompts/main",
        raw_path="prompts.json",
        parser="json_prompts",
        category="davidwu-gpt-image2-prompts",
        metadata={"model_hint": "gpt-image-2", "model_group": "ChatGPT"},
    ),
    SourceDefinition(
        id="imi-chatgpt-prompts",
        name="IMI ChatGPT Prompt Gallery",
        repo_url="https://prompt.imi.ccwu.cc/ChatGPT/chatgpt_detail_data.json",
        raw_base_url="https://prompt.imi.ccwu.cc/ChatGPT",
        raw_path="chatgpt_detail_data.json",
        parser="imi_detail_json",
        category="imi-chatgpt",
        metadata={"model_hint": "ChatGPT", "model_group": "ChatGPT", "media_base_url": "https://prompt.imi.ccwu.cc"},
    ),
    SourceDefinition(
        id="imi-nano-banana-2-prompts",
        name="IMI Nano Banana 2 Prompt Gallery",
        repo_url="https://prompt.imi.ccwu.cc/Nano%20Banana%202/nano_banana_2_detail_data.json",
        raw_base_url="https://prompt.imi.ccwu.cc/Nano%20Banana%202",
        raw_path="nano_banana_2_detail_data.json",
        parser="imi_detail_json",
        category="imi-nano-banana-2",
        metadata={"model_hint": "Nano Banana 2", "model_group": "NanoBanana2", "media_base_url": "https://prompt.imi.ccwu.cc"},
    ),
    SourceDefinition(
        id="imi-nano-banana-pro-prompts",
        name="IMI Nano Banana Pro Prompt Gallery",
        repo_url="https://prompt.imi.ccwu.cc/Nano%20Banana%20Pro/nano_banana_pro_detail_data.json",
        raw_base_url="https://prompt.imi.ccwu.cc/Nano%20Banana%20Pro",
        raw_path="nano_banana_pro_detail_data.json",
        parser="imi_detail_json",
        category="imi-nano-banana-pro",
        metadata={"model_hint": "Nano Banana Pro", "model_group": "NanoBananaPro", "media_base_url": "https://prompt.imi.ccwu.cc"},
    ),
)

USER_IMAGE_PROMPT_SOURCE = SourceDefinition(
    id="ylcraft-my-image-prompts",
    name="我的生图提示词",
    repo_url="",
    raw_base_url="",
    raw_path="",
    parser="manual",
    category="我的生图提示词",
    metadata={"source_kind": "user_generated"},
)

MODEL_GROUP_SOURCE_IDS: dict[str, set[str]] = {
    "chatgpt": {
        "awesome-gpt-image",
        "awesome-gpt4o-image-prompts",
        "youmind-gpt-image-2",
        "davidwu-gpt-image2-prompts",
        "imi-chatgpt-prompts",
    },
    "nanobanana2": {"imi-nano-banana-2-prompts"},
    "nanobananapro": {"youmind-nano-banana-pro", "imi-nano-banana-pro-prompts"},
}
PROMPT_TAG_PRIORITY: tuple[str, ...] = (
    "民国",
    "韩国风",
    "手绘感",
    "高细节",
    "古典美",
    "超写实",
    "咖啡馆",
    "羽毛眼",
    "可媲包",
    "摄影感",
    "钩针",
    "体育",
    "立体",
    "蕾丝",
    "破损",
    "巨鲸",
    "少年",
    "深海",
    "电影感",
    "奇遇",
    "童绘本",
    "手抄报",
    "涂色卡",
    "线稿风",
    "寓言画",
    "冬日村庄",
    "雪中小屋",
    "柔和插画",
    "异想天开",
    "温暖光影",
    "灰尘",
    "微距",
    "引擎盖",
    "擦拭",
    "商业照",
    "奢华风",
    "高质感",
    "光影感",
    "编辑级",
    "女仆装",
    "双马尾",
    "粉长发",
    "少女感",
    "三视图",
    "设定图",
    "细节图",
    "参考图",
    "金链控",
    "俯视角",
    "红裙女",
    "暗夜感",
    "韩系美女",
    "甜蜜互动",
    "生活摄影",
    "户外",
    "旅行",
    "写实",
    "清新",
    "山野",
    "明星",
    "人像",
    "唯美",
    "3D风格",
    "皮克斯风",
    "玩具质感",
    "影视光",
    "立体人像",
    "时尚",
    "极简",
    "卫衣",
    "海报",
    "模特",
    "暖调",
    "美妆特写",
    "时尚大片",
    "完美肤质",
    "清新少女",
    "光影人像",
    "赛博风",
    "机械兽",
    "仿生学",
    "科技感",
    "光绘摄影",
    "电影质感",
    "极简奢华",
    "琥珀光影",
    "美食摄影",
    "黄金时刻",
    "温暖治愈",
    "极致纹理",
    "3D卡通",
    "盲盒风",
    "潮酷",
    "极简风",
    "创意海报",
    "涂鸦",
    "虚实结合",
    "商业广告",
    "电商",
    "促销",
    "明星脸",
    "赤脚",
)
PROMPT_TAG_PRIORITY_INDEX = {tag.lower(): index for index, tag in enumerate(PROMPT_TAG_PRIORITY)}
PROMPT_TAG_STOPWORDS = {
    "image",
    "chatgpt",
    "gpt-4o",
    "gpt-image-2",
    "nano banana 2",
    "nano banana pro",
    "nano-banana-pro",
    "nanobanana2",
    "nanobananapro",
    "awesome-gpt-image",
    "awesome-gpt4o-image-prompts",
}
PROMPT_FACET_CACHE_TTL_SECONDS = 300
_PROMPT_FACET_CACHE: dict[str, Any] = {"expires_at": 0.0, "tags": [], "categories": []}


def _clear_prompt_facet_cache() -> None:
    _PROMPT_FACET_CACHE["expires_at"] = 0.0
    _PROMPT_FACET_CACHE["tags"] = []
    _PROMPT_FACET_CACHE["categories"] = []


def _model_variants_from_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants: dict[tuple[str, str], int] = {}
    for example in examples:
        if not isinstance(example, dict):
            continue
        key = (str(example.get("provider") or ""), str(example.get("model") or ""))
        variants[key] = variants.get(key, 0) + 1
    return [
        {"provider": provider, "model": model, "count": count}
        for (provider, model), count in sorted(variants.items())
    ]


def _utc_now() -> datetime:
    return datetime.utcnow()


def _slug(value: str, fallback: str = "prompt") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return cleaned or fallback


def _stable_external_id(prefix: str, index: int, title: str, prompt: str) -> str:
    digest = hashlib.sha1(f"{title}\n{prompt}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{index:04d}-{digest}"


def _split_before_heading(markdown: str, prefix: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in (markdown or "").splitlines():
        if line.startswith(prefix) and current:
            blocks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _first_match(value: str, pattern: str, flags: int = 0) -> str:
    match = re.search(pattern, value or "", flags)
    return (match.group(1) if match else "").strip()


def _strip_markdown_links(value: str) -> str:
    return re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", value or "").strip(" #\t")


def _split_tags(value: str) -> list[str]:
    rough = re.split(r"\s*(?:/|&|,|，|、|与|and|\|)\s*", value or "")
    return sorted({tag.strip().lower() for tag in rough if tag.strip()})


def _normalize_model_group(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", (value or "").lower())
    aliases = {
        "chatgpt": "ChatGPT",
        "gpt4o": "ChatGPT",
        "gptimage": "ChatGPT",
        "gptimage2": "ChatGPT",
        "nanobanana2": "NanoBanana2",
        "nanobananapro": "NanoBananaPro",
    }
    return aliases.get(normalized, value.strip())


def _model_group_for_source_id(source_id: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", source_id.lower())
    for group, source_ids in MODEL_GROUP_SOURCE_IDS.items():
        if source_id in source_ids:
            return _normalize_model_group(group)
    return _normalize_model_group(normalized)


def _model_group_for_reference(source_id: str, model_hint: str = "", metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    return (
        _normalize_model_group(str(metadata.get("model_group") or ""))
        or _normalize_model_group(model_hint)
        or _model_group_for_source_id(source_id)
    )


def _sort_prompt_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    unique = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
    model_tags = {"chatgpt", "gpt-4o", "gpt-image-2", "nano banana 2", "nano banana pro", "nano-banana-pro"}
    return sorted(
        unique,
        key=lambda tag: (
            3 if tag.startswith("@") else 2 if tag in model_tags else 0,
            tag,
        ),
    )


def _suggestion_tags_from_rows(rows: list[ImagePromptReference]) -> list[str]:
    tags = [tag for row in rows for tag in (row.tags_json or []) if tag]
    return _rank_prompt_suggestion_tags(tags)


def _rank_prompt_suggestion_tags(tags: list[str], *, limit: int = 180) -> list[str]:
    counter = Counter(str(tag).strip().lower() for tag in tags if str(tag).strip())
    for tag in list(counter):
        if tag.startswith("@") or tag in PROMPT_TAG_STOPWORDS or len(tag) > 28:
            counter.pop(tag, None)
    return [
        tag
        for tag, _count in sorted(
            counter.items(),
            key=lambda item: (
                0 if item[0] in PROMPT_TAG_PRIORITY_INDEX else 1,
                PROMPT_TAG_PRIORITY_INDEX.get(item[0], 9999),
                -item[1],
                len(item[0]),
                item[0],
            ),
        )[:limit]
    ]


def _absolute_image(base_url: str, image: str) -> str:
    image = (image or "").strip()
    if not image:
        return ""
    if re.match(r"^https?://", image, re.I):
        return image
    return f"{base_url.rstrip('/')}/{image.lstrip('./')}"


def image_prompt_storage_root() -> Path:
    """Return the local cache root for prompt JSON and downloaded preview images."""

    return Path(__file__).resolve().parents[3] / "storage" / "image_prompt_references"


def image_prompt_media_root() -> Path:
    return image_prompt_storage_root() / "media"


def image_prompt_source_cache_path(source: ImagePromptSource) -> Path:
    ext = Path(source.raw_path or "").suffix or ".txt"
    return image_prompt_storage_root() / "sources" / f"{_slug(source.id, 'source')}{ext}"


def _safe_filename(value: str, fallback: str = "image.jpg") -> str:
    name = Path((value or "").split("?")[0]).name.strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip(".-")
    return name or fallback


def _cached_media_path(source_id: str, item_id: str, filename: str) -> Path:
    return image_prompt_media_root() / _slug(source_id, "source") / _slug(item_id, "item") / _safe_filename(filename)


def _cached_media_url(source_id: str, item_id: str, filename: str) -> str:
    parts = [
        quote(_slug(source_id, "source"), safe=""),
        quote(_slug(item_id, "item"), safe=""),
        quote(_safe_filename(filename), safe=""),
    ]
    return f"/api/v1/image-prompts/media/{'/'.join(parts)}"


def _local_or_remote_image(source_id: str, item_id: str, filename: str, remote_url: str) -> str:
    if filename and _cached_media_path(source_id, item_id, filename).is_file():
        return _cached_media_url(source_id, item_id, filename)
    return remote_url


def _extract_images(base_url: str, markdown: str) -> list[str]:
    return [
        url
        for url in (_absolute_image(base_url, match.group(1)) for match in re.finditer(r"!\[[^\]]*]\(([^)]+)\)", markdown or ""))
        if url
    ]


def _markdown_preview(images: list[str]) -> str:
    return "\n\n".join(f"![]({image})" for image in images if image)


def _extract_prompt_from_markdown_block(block: str) -> str:
    fenced = _first_match(block, r"```[\w-]*\s*\r?\n(.*?)\r?\n```", re.S)
    if fenced:
        return fenced
    inline_patterns = [
        r"(?:提示词文本|提示词|Prompt|prompt)[^`\n]*`([^`]+)`",
        r"(?:提示词文本|提示词|Prompt|prompt)[：:]\s*(.+)",
    ]
    for pattern in inline_patterns:
        found = _first_match(block, pattern, re.S)
        if found:
            return found.strip()
    return ""


def parse_markdown_prompt_references(
    markdown: str,
    *,
    source_id: str,
    category: str,
    raw_base_url: str,
    repo_url: str,
    model_hint: str = "",
) -> list[ParsedPromptReference]:
    items: list[ParsedPromptReference] = []
    sections = _split_before_heading(markdown, "## ")
    for section in sections:
        section_heading = _first_match(section, r"^##\s+(.+)$", re.M)
        section_tags = _split_tags(re.sub(r"[^\w\u4e00-\u9fff/&，、 与|-]+", " ", section_heading))
        blocks = _split_before_heading(section, "### ")
        for block in blocks:
            title = _strip_markdown_links(_first_match(block, r"^###\s+(.+)$", re.M))
            prompt = _extract_prompt_from_markdown_block(block)
            if not title or not prompt:
                continue
            images = _extract_images(raw_base_url, block)
            index = len(items) + 1
            external_id = _stable_external_id(source_id, index, title, prompt)
            items.append(
                ParsedPromptReference(
                    external_id=external_id,
                    title=title,
                    prompt=prompt,
                    cover_url=images[0] if images else "",
                    preview_markdown=_markdown_preview(images),
                    tags=tuple(_sort_prompt_tags(section_tags)),
                    category=category,
                    source_url=repo_url,
                    model_hint=model_hint,
                    language="zh" if re.search(r"[\u4e00-\u9fff]", title + prompt) else "en",
                    metadata={"parser": "markdown_sections"},
                )
            )
    return items


def parse_json_prompt_references(
    payload: str | list[dict[str, Any]],
    *,
    source_id: str,
    category: str,
    raw_base_url: str,
    repo_url: str,
    model_hint: str = "",
) -> list[ParsedPromptReference]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, list):
        raise ValueError("JSON prompt source must be a list")
    items: list[ParsedPromptReference] = []
    for index, raw in enumerate(data, start=1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title_cn") or raw.get("title_en") or raw.get("title") or "").strip()
        prompt = str(raw.get("prompt") or raw.get("positive_prompt") or "").strip()
        if not title or not prompt:
            continue
        external_raw = raw.get("id") or raw.get("external_id") or index
        external_id = f"{source_id}-{_slug(str(external_raw), str(index))}"
        image = _absolute_image(raw_base_url, str(raw.get("image") or raw.get("coverUrl") or raw.get("cover_url") or ""))
        tags = _split_tags(
            "/".join(
                str(raw.get(key) or "")
                for key in ("category_cn", "category", "author", "source")
                if raw.get(key)
            )
        )
        if raw.get("needs_ref") or raw.get("needs_reference_image"):
            tags.append("needs-reference-image")
        items.append(
            ParsedPromptReference(
                external_id=external_id,
                title=title,
                prompt=prompt,
                negative_prompt=str(raw.get("negative_prompt") or ""),
                cover_url=image,
                preview_markdown="\n\n".join(str(part) for part in (raw.get("title_en"), raw.get("note"), f"![]({image})" if image else "") if part),
                tags=tuple(_sort_prompt_tags(tags)),
                category=str(raw.get("category_cn") or raw.get("category") or category),
                source_url=str(raw.get("githubUrl") or raw.get("source_url") or repo_url),
                model_hint=str(raw.get("model") or model_hint),
                needs_reference_image=bool(raw.get("needs_ref") or raw.get("needs_reference_image")),
                language="zh" if re.search(r"[\u4e00-\u9fff]", title + prompt) else "en",
                metadata={k: v for k, v in raw.items() if k not in {"prompt", "positive_prompt"}},
            )
        )
    return items


def parse_imi_detail_prompt_references(
    payload: str | list[dict[str, Any]],
    *,
    source_id: str,
    category: str,
    raw_base_url: str,
    repo_url: str,
    model_hint: str = "",
    media_base_url: str = "",
) -> list[ParsedPromptReference]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, list):
        raise ValueError("IMI prompt source must be a list")

    items: list[ParsedPromptReference] = []
    for index, raw in enumerate(data, start=1):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or raw.get("source_id") or index).strip()
        slug = str(raw.get("slug") or "").strip()
        title = str(raw.get("title") or slug or f"Prompt {index}").strip()
        prompts = raw.get("prompts") if isinstance(raw.get("prompts"), list) else []
        prompt = str(raw.get("chinese_prompt") or raw.get("english_prompt") or "").strip()
        if not prompt:
            for prompt_item in prompts:
                if isinstance(prompt_item, dict) and str(prompt_item.get("text") or "").strip():
                    prompt = str(prompt_item.get("text") or "").strip()
                    break
        if not title or not prompt:
            continue

        images = raw.get("images") if isinstance(raw.get("images"), list) else []
        image_urls: list[str] = []
        image_meta: list[dict[str, str]] = []
        for image_index, image in enumerate(images, start=1):
            if not isinstance(image, dict):
                continue
            remote_url = str(image.get("url") or "").strip()
            path = str(image.get("path") or "").strip()
            filename = _safe_filename(str(image.get("filename") or Path(path).name or f"{item_id}-{image_index}.jpg"))
            if not remote_url and path:
                remote_url = _absolute_image(media_base_url or raw_base_url, path)
            if not remote_url:
                continue
            display_url = _local_or_remote_image(source_id, item_id, filename, remote_url)
            image_urls.append(display_url)
            image_meta.append({"url": remote_url, "filename": filename, "path": path, "display_url": display_url})

        cover_raw = str(raw.get("thumbnail") or raw.get("cover_image") or "").strip()
        cover_remote = _absolute_image(media_base_url or raw_base_url, cover_raw) if cover_raw else ""
        if image_meta:
            first = image_meta[0]
            cover_url = _local_or_remote_image(source_id, item_id, first["filename"], cover_remote or first["url"])
        else:
            cover_url = cover_remote
            if cover_url:
                image_urls.append(cover_url)

        tags: list[str] = []
        raw_tags = raw.get("tags")
        if isinstance(raw_tags, list):
            for tag in raw_tags:
                if isinstance(tag, dict):
                    value = str(tag.get("name") or tag.get("title") or tag.get("label") or "").strip()
                else:
                    value = str(tag or "").strip()
                if value:
                    tags.extend(_split_tags(value))
        tags.extend(_split_tags(str(raw.get("model") or model_hint or "")))
        if str(raw.get("media_type") or "").strip():
            tags.append(str(raw.get("media_type")).strip().lower())
        source_name = str(raw.get("source_name") or "").strip()
        if source_name:
            tags.append(source_name.lower())

        external_raw = raw.get("source_id") or item_id or slug or index
        external_id = f"{source_id}-{_slug(str(external_raw), str(index))}"
        model = str(raw.get("model") or model_hint or "").strip()
        items.append(
            ParsedPromptReference(
                external_id=external_id,
                title=title,
                prompt=prompt,
                cover_url=cover_url,
                preview_markdown=_markdown_preview(image_urls[:6]),
                tags=tuple(_sort_prompt_tags(tags)),
                category=model or category,
                source_url=str(raw.get("detail_url") or raw.get("source_url") or repo_url),
                model_hint=model,
                language="zh" if re.search(r"[\u4e00-\u9fff]", title + prompt) else "en",
                metadata={
                    "parser": "imi_detail_json",
                    "imi_id": item_id,
                    "slug": slug,
                    "source_name": source_name,
                    "source_url": raw.get("source_url") or "",
                    "detail_url": raw.get("detail_url") or "",
                    "detail_api_url": raw.get("detail_api_url") or "",
                    "media_type": raw.get("media_type") or "",
                    "view_count": raw.get("view_count") or 0,
                    "like_count": raw.get("like_count") or 0,
                    "copy_count": raw.get("copy_count") or 0,
                    "reviewed_at": raw.get("reviewed_at") or "",
                    "remote_created_at": raw.get("remote_created_at") or raw.get("created_at") or "",
                    "remote_updated_at": raw.get("remote_updated_at") or raw.get("updated_at") or "",
                    "images": image_meta,
                    "original_cover_url": cover_remote,
                    "english_prompt": raw.get("english_prompt") or "",
                    "chinese_prompt": raw.get("chinese_prompt") or "",
                },
            )
        )
    return items


class ImagePromptReferenceService:
    """Sync, search and asset-save operations for prompt references."""

    def __init__(self, session: Session):
        self.session = session

    def seed_sources(self) -> list[ImagePromptSource]:
        rows: list[ImagePromptSource] = []
        now = _utc_now()
        for definition in [*DEFAULT_IMAGE_PROMPT_SOURCES, USER_IMAGE_PROMPT_SOURCE]:
            row = self.session.get(ImagePromptSource, definition.id)
            if row is None:
                row = ImagePromptSource(id=definition.id, created_at=now)
            row.name = definition.name
            row.repo_url = definition.repo_url
            row.raw_base_url = definition.raw_base_url
            row.raw_path = definition.raw_path
            row.parser = definition.parser
            row.category = definition.category
            row.enabled = True
            row.metadata_json = dict(definition.metadata)
            row.updated_at = now
            self.session.add(row)
            rows.append(row)
        self.session.commit()
        return rows

    def list_sources(self, *, include_disabled: bool = False) -> list[ImagePromptSource]:
        self.seed_sources()
        query = select(ImagePromptSource).order_by(ImagePromptSource.name)
        if not include_disabled:
            query = query.where(ImagePromptSource.enabled == True)  # noqa: E712
        return list(self.session.exec(query).all())

    def get_source(self, source_id: str) -> ImagePromptSource | None:
        self.seed_sources()
        return self.session.get(ImagePromptSource, source_id)

    def parse_source_payload(self, source: ImagePromptSource, payload: str) -> list[ParsedPromptReference]:
        model_hint = str((source.metadata_json or {}).get("model_hint") or "")
        if source.parser == "imi_detail_json":
            return parse_imi_detail_prompt_references(
                payload,
                source_id=source.id,
                category=source.category,
                raw_base_url=source.raw_base_url,
                repo_url=source.repo_url,
                model_hint=model_hint,
                media_base_url=str((source.metadata_json or {}).get("media_base_url") or ""),
            )
        if source.parser == "json_prompts":
            return parse_json_prompt_references(
                payload,
                source_id=source.id,
                category=source.category,
                raw_base_url=source.raw_base_url,
                repo_url=source.repo_url,
                model_hint=model_hint,
            )
        return parse_markdown_prompt_references(
            payload,
            source_id=source.id,
            category=source.category,
            raw_base_url=source.raw_base_url,
            repo_url=source.repo_url,
            model_hint=model_hint,
        )

    def sync_source_payload(self, source: ImagePromptSource, payload: str) -> dict[str, Any]:
        now = _utc_now()
        source.sync_status = "syncing"
        source.error = ""
        source.updated_at = now
        self.session.add(source)
        self.session.commit()

        try:
            parsed = self.parse_source_payload(source, payload)
            created = 0
            updated = 0
            for item in parsed:
                ref_id = f"{source.id}:{item.external_id}"
                row = self.session.get(ImagePromptReference, ref_id)
                if row is None:
                    row = ImagePromptReference(
                        id=ref_id,
                        source_id=source.id,
                        external_id=item.external_id,
                        created_at=now,
                    )
                    created += 1
                else:
                    updated += 1
                row.title = item.title
                row.prompt = item.prompt
                row.negative_prompt = item.negative_prompt
                row.cover_url = item.cover_url
                row.preview_markdown = item.preview_markdown
                row.tags_json = list(item.tags)
                row.category = item.category or source.category
                row.source_url = item.source_url or source.repo_url
                row.model_hint = item.model_hint
                row.needs_reference_image = item.needs_reference_image
                row.language = item.language
                row.metadata_json = dict(item.metadata)
                row.updated_at = now
                self.session.add(row)

            source.sync_status = "success"
            source.last_synced_at = now
            source.error = ""
            source.updated_at = now
            self.session.add(source)
            self.session.commit()
            _clear_prompt_facet_cache()
            return {"success": True, "source_id": source.id, "total": len(parsed), "created": created, "updated": updated}
        except Exception as exc:
            source.sync_status = "failed"
            source.error = str(exc)
            source.updated_at = _utc_now()
            self.session.add(source)
            self.session.commit()
            raise

    def refresh_source(self, source_id: str, *, timeout: float = 30.0, force_remote: bool = False) -> dict[str, Any]:
        source = self.get_source(source_id)
        if not source:
            raise ValueError(f"image prompt source not found: {source_id}")
        if source.parser == "manual":
            total = int(
                self.session.exec(
                    select(func.count(ImagePromptReference.id)).where(ImagePromptReference.source_id == source.id)
                ).one()
                or 0
            )
            return {"success": True, "source_id": source.id, "total": total, "created": 0, "updated": 0, "cache": "database"}
        cache_path = image_prompt_source_cache_path(source)
        if cache_path.is_file() and not force_remote:
            return {
                **self.sync_source_payload(source, cache_path.read_text(encoding="utf-8")),
                "cache": "local",
                "cache_path": str(cache_path),
            }

        if not force_remote:
            total = int(
                self.session.exec(
                    select(func.count(ImagePromptReference.id)).where(ImagePromptReference.source_id == source.id)
                ).one()
                or 0
            )
            return {
                "success": True,
                "source_id": source.id,
                "total": total,
                "created": 0,
                "updated": 0,
                "cache": "missing",
                "skipped_remote": True,
                "message": "local source cache is missing; enable remote update to refresh this source",
            }

        url = f"{source.raw_base_url.rstrip('/')}/{source.raw_path.lstrip('/')}"
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(response.text, encoding="utf-8")
            return {
                **self.sync_source_payload(source, response.text),
                "cache": "remote",
                "cache_path": str(cache_path),
            }

    def refresh_sources(self, *, source_id: str | None = None, force_remote: bool = False) -> dict[str, Any]:
        sources = [self.get_source(source_id)] if source_id else self.list_sources()
        results: list[dict[str, Any]] = []
        for source in sources:
            if not source:
                continue
            try:
                results.append(self.refresh_source(source.id, force_remote=force_remote))
            except Exception as exc:
                results.append({"success": False, "source_id": source.id, "error": str(exc)})
        return {
            "success": all(item.get("success") for item in results),
            "total_sources": len(results),
            "results": results,
        }

    def create_user_reference(
        self,
        *,
        prompt: str,
        title: str = "",
        negative_prompt: str = "",
        provider: str = "",
        model: str = "",
        asset_id: str = "",
        generation_mode: str = "text_to_image",
        size: str = "",
        seed: int | None = None,
        tags: list[str] | None = None,
    ) -> tuple[ImagePromptReference, bool, bool]:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("提示词不能为空")
        self.seed_sources()
        from uuid import uuid4

        now = _utc_now()
        sample = {
            "provider": (provider or "").strip(),
            "model": (model or "").strip(),
            "asset_id": (asset_id or "").strip(),
            "generation_mode": (generation_mode or "text_to_image").strip(),
            "size": (size or "").strip(),
            "seed": seed,
            "saved_at": now.isoformat(),
        }
        existing = self.session.exec(
            select(ImagePromptReference).where(
                ImagePromptReference.source_id == USER_IMAGE_PROMPT_SOURCE.id,
                ImagePromptReference.prompt == prompt,
                ImagePromptReference.negative_prompt == (negative_prompt or "").strip(),
            )
        ).first()
        if existing:
            metadata = dict(existing.metadata_json or {})
            examples = metadata.get("generation_examples") if isinstance(metadata.get("generation_examples"), list) else []
            sample_key = sample["asset_id"] or "|".join(str(sample.get(key) or "") for key in ("provider", "model", "generation_mode", "size", "seed"))
            known_keys = {
                item.get("asset_id") or "|".join(str(item.get(key) or "") for key in ("provider", "model", "generation_mode", "size", "seed"))
                for item in examples
                if isinstance(item, dict)
            }
            if sample_key not in known_keys:
                examples.append(sample)
            metadata["generation_examples"] = examples[-50:]
            metadata["example_count"] = len(examples)
            metadata["model_variants"] = _model_variants_from_examples(examples)
            existing.metadata_json = metadata
            existing.updated_at = now
            self.session.add(existing)
            self.session.commit()
            return existing, False, sample_key not in known_keys

        external_id = uuid4().hex
        reference = ImagePromptReference(
            id=f"{USER_IMAGE_PROMPT_SOURCE.id}:{external_id}",
            source_id=USER_IMAGE_PROMPT_SOURCE.id,
            external_id=external_id,
            title=(title or prompt[:48] or "我的生图提示词").strip()[:255],
            prompt=prompt,
            negative_prompt=(negative_prompt or "").strip(),
            tags_json=_sort_prompt_tags([*(tags or []), "我的提示词"]),
            category=USER_IMAGE_PROMPT_SOURCE.category,
            model_hint=sample["model"],
            language="zh" if re.search(r"[\u4e00-\u9fff]", prompt) else "en",
            metadata_json={
                "source_name": USER_IMAGE_PROMPT_SOURCE.name,
                "source_kind": "generated_image",
                "provider": sample["provider"],
                "model": sample["model"],
                "asset_id": sample["asset_id"],
                "generation_examples": [sample],
                "example_count": 1,
                "model_variants": _model_variants_from_examples([sample]),
            },
            created_at=now,
            updated_at=now,
        )
        self.session.add(reference)
        self.session.commit()
        _clear_prompt_facet_cache()
        return reference, True, True

    def _global_facets(self) -> dict[str, list[str]]:
        now = time.monotonic()
        if now < float(_PROMPT_FACET_CACHE.get("expires_at") or 0):
            return {
                "tags": list(_PROMPT_FACET_CACHE.get("tags") or []),
                "categories": list(_PROMPT_FACET_CACHE.get("categories") or []),
            }
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""
        if dialect_name == "postgresql":
            tag_rows = self.session.exec(
                text(
                    """
                    SELECT tag_value, COUNT(*) AS usage_count
                    FROM image_prompt_references,
                         LATERAL jsonb_array_elements_text(tags_json) AS prompt_tags(tag_value)
                    WHERE tag_value <> ''
                      AND tag_value NOT LIKE '@%'
                      AND char_length(tag_value) <= 28
                    GROUP BY tag_value
                    ORDER BY usage_count DESC
                    LIMIT 900
                    """
                )
            ).all()
            weighted_tags: list[str] = []
            for row in tag_rows:
                tag = str(row[0]).strip().lower()
                count = int(row[1])
                if tag and tag not in PROMPT_TAG_STOPWORDS:
                    weighted_tags.extend([tag] * max(1, min(count, 100)))
            tags = weighted_tags
        else:
            rows = list(self.session.exec(select(ImagePromptReference.tags_json)).all())
            tags = []
            for value in rows:
                if isinstance(value, list):
                    tags.extend(str(tag) for tag in value if tag)
        categories = sorted({str(category) for category in self.session.exec(select(ImagePromptReference.category)).all() if category})
        facets = {"tags": _rank_prompt_suggestion_tags(tags), "categories": categories}
        _PROMPT_FACET_CACHE["tags"] = facets["tags"]
        _PROMPT_FACET_CACHE["categories"] = facets["categories"]
        _PROMPT_FACET_CACHE["expires_at"] = now + PROMPT_FACET_CACHE_TTL_SECONDS
        return facets

    def _suggestion_tags_for_filters(self, filters: list[Any]) -> list[str]:
        return self._global_facets()["tags"]

    def _categories_for_filters(self, filters: list[Any]) -> list[str]:
        return self._global_facets()["categories"]

    def search_references(
        self,
        *,
        keyword: str = "",
        tag: str = "",
        category: str = "",
        source_id: str = "",
        model_group: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        filters = []
        if source_id:
            filters.append(ImagePromptReference.source_id == source_id)
        elif model_group:
            normalized_group = re.sub(r"[^a-z0-9]+", "", model_group.lower())
            source_ids = MODEL_GROUP_SOURCE_IDS.get(normalized_group)
            if source_ids:
                filters.append(ImagePromptReference.source_id.in_(sorted(source_ids)))
        if category and category.lower() not in {"all", "全部"}:
            filters.append(ImagePromptReference.category == category)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    ImagePromptReference.title.ilike(pattern),
                    ImagePromptReference.prompt.ilike(pattern),
                    ImagePromptReference.category.ilike(pattern),
                )
            )
        # Facet options are independent controls. Selecting model/source/tag narrows
        # result items, but should not make the tag/category option pool jump around.
        suggestion_filters: list[Any] = []
        normalized_tag = tag.strip().lower() if tag else ""
        bind = self.session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""
        if normalized_tag and dialect_name == "postgresql":
            filters.append(ImagePromptReference.tags_json.op("@>")(cast([normalized_tag], JSONB)))
        query = select(ImagePromptReference).where(*filters)
        offset = (page - 1) * page_size
        if normalized_tag and dialect_name != "postgresql":
            rows = list(self.session.exec(query).all())
            rows = [row for row in rows if normalized_tag in {str(item).lower() for item in (row.tags_json or [])}]
            rows.sort(
                key=lambda row: (
                    0 if ((row.cover_url or "").strip() or (row.preview_markdown or "").strip()) else 1,
                    -(row.updated_at.timestamp() if row.updated_at else 0.0),
                )
            )
            total = len(rows)
            items = rows[offset : offset + page_size]
            categories = sorted({row.category for row in rows if row.category})
            tags = self._suggestion_tags_for_filters(suggestion_filters)
        else:
            total = int(self.session.exec(select(func.count(ImagePromptReference.id)).where(*filters)).one() or 0)
            image_first_order = case(
                (
                    or_(
                        ImagePromptReference.cover_url != "",
                        ImagePromptReference.preview_markdown != "",
                    ),
                    0,
                ),
                else_=1,
            )
            items = list(
                self.session.exec(
                    query.order_by(image_first_order, ImagePromptReference.updated_at.desc())
                    .offset(offset)
                    .limit(page_size)
                ).all()
            )
            categories = self._categories_for_filters(suggestion_filters)
            tags = self._suggestion_tags_for_filters(suggestion_filters)
        return {
            "success": True,
            "items": [self.reference_to_dict(row, preview=True) for row in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "categories": categories,
            "tags": tags,
        }

    def get_reference(self, reference_id: str) -> ImagePromptReference | None:
        return self.session.get(ImagePromptReference, reference_id)

    def save_reference_as_asset(self, reference_id: str) -> dict[str, Any]:
        from uuid import uuid4

        ref = self.get_reference(reference_id)
        if not ref:
            raise ValueError(f"image prompt reference not found: {reference_id}")
        cached_image = self._first_cached_image(ref)
        if not cached_image:
            raise ValueError("该 Prompt 参考没有已缓存的图片，无法加入素材库作为图生视频首帧")
        now = _utc_now()
        image_asset_id = str(uuid4())
        image_node = AssetNode(
            id=image_asset_id,
            name=f"{ref.title} - 参考图",
            asset_type=AssetType.IMAGE,
            thumbnail_url=f"/api/v1/assets/{image_asset_id}/thumbnail",
            metadata_json={
                "source": "image_prompt_reference_library",
                "reference_id": ref.id,
                "source_id": ref.source_id,
                "source_url": ref.source_url,
                "prompt": ref.prompt,
                "negative_prompt": ref.negative_prompt,
                "model_hint": ref.model_hint,
            },
            tags_json=list(ref.tags_json or []), created_at=now, updated_at=now,
        )
        image_version = AssetVersion(
            id=str(uuid4()), asset_node_id=image_asset_id, version_number=1,
            prompt_used=ref.prompt, model_used=ref.model_hint or None,
            params_json={"reference_id": ref.id},
            lineage_json={"source": "image_prompt_reference", "reference_id": ref.id, "source_id": ref.source_id},
            created_at=now,
        )
        self.session.add(image_node)
        self.session.add(image_version)
        # PostgreSQL can flush unrelated pending rows in an order that violates
        # the representation foreign key, so persist the parent version first.
        self.session.flush()
        target_dir = Path(__file__).resolve().parents[3] / "storage" / "assets" / "prompt-references"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{image_asset_id}{cached_image.suffix.lower() or '.jpg'}"
        shutil.copy2(cached_image, target)
        mime_type = mimetypes.guess_type(str(target))[0] or "image/jpeg"
        image_representation = AssetRepresentation(
            id=str(uuid4()), asset_version_id=str(image_version.id), file_path=str(target),
            mime_type=mime_type, file_size=target.stat().st_size, format=target.suffix.lstrip(".") or None,
            extra_json={"source_path": str(cached_image)},
        )
        self.session.add(image_representation)
        self.session.commit()
        return {
            "success": True, "asset_node_id": image_asset_id, "asset_version_id": str(image_version.id),
            "image_asset_id": image_asset_id, "reference_id": ref.id, "image_saved": True,
        }

    @staticmethod
    def _first_cached_image(ref: ImagePromptReference) -> Path | None:
        metadata = dict(ref.metadata_json or {})
        images = metadata.get("images") if isinstance(metadata.get("images"), list) else []
        for image in images:
            if not isinstance(image, dict):
                continue
            filename = str(image.get("filename") or "")
            candidate = _cached_media_path(ref.source_id, str(metadata.get("imi_id") or ref.external_id), filename)
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def source_to_dict(source: ImagePromptSource) -> dict[str, Any]:
        return {
            "id": source.id,
            "name": source.name,
            "repo_url": source.repo_url,
            "raw_base_url": source.raw_base_url,
            "raw_path": source.raw_path,
            "parser": source.parser,
            "category": source.category,
            "enabled": source.enabled,
            "sync_status": source.sync_status,
            "last_synced_at": source.last_synced_at.isoformat() if source.last_synced_at else None,
            "error": source.error,
            "metadata": dict(source.metadata_json or {}),
            "model_group": _model_group_for_reference(source.id, str((source.metadata_json or {}).get("model_hint") or ""), source.metadata_json or {}),
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        }

    @staticmethod
    def reference_to_dict(reference: ImagePromptReference, *, preview: bool = False) -> dict[str, Any]:
        prompt = reference.prompt or ""
        metadata = dict(reference.metadata_json or {})
        return {
            "id": reference.id,
            "source_id": reference.source_id,
            "external_id": reference.external_id,
            "title": reference.title,
            "prompt": prompt[:360] + "..." if preview and len(prompt) > 360 else prompt,
            "negative_prompt": reference.negative_prompt,
            "cover_url": reference.cover_url,
            "preview_markdown": reference.preview_markdown,
            "tags": _sort_prompt_tags(reference.tags_json or []),
            "category": reference.category,
            "source_url": reference.source_url,
            "model_hint": reference.model_hint,
            "model_group": _model_group_for_reference(reference.source_id, reference.model_hint, metadata),
            "needs_reference_image": reference.needs_reference_image,
            "language": reference.language,
            "metadata": metadata,
            "english_prompt": metadata.get("english_prompt") or "",
            "chinese_prompt": metadata.get("chinese_prompt") or "",
            "source_name": metadata.get("source_name") or "",
            "detail_url": metadata.get("detail_url") or "",
            "image_items": metadata.get("images") or [],
            "view_count": metadata.get("view_count") or 0,
            "like_count": metadata.get("like_count") or 0,
            "copy_count": metadata.get("copy_count") or 0,
            "generation_examples": metadata.get("generation_examples") or [],
            "model_variants": metadata.get("model_variants") or [],
            "remote_created_at": metadata.get("remote_created_at") or "",
            "remote_updated_at": metadata.get("remote_updated_at") or "",
            "created_at": reference.created_at.isoformat() if reference.created_at else None,
            "updated_at": reference.updated_at.isoformat() if reference.updated_at else None,
        }
