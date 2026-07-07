"""Backend sync and search service for image prompt reference examples."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db.models.asset_hub import AssetNode, AssetType, AssetVersion
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
    ),
    SourceDefinition(
        id="awesome-gpt4o-image-prompts",
        name="ImgEdify Awesome GPT-4o Image Prompts",
        repo_url="https://github.com/ImgEdify/Awesome-GPT4o-Image-Prompts",
        raw_base_url="https://raw.githubusercontent.com/ImgEdify/Awesome-GPT4o-Image-Prompts/main",
        raw_path="README.zh-CN.md",
        parser="markdown_sections",
        category="awesome-gpt4o-image-prompts",
        metadata={"model_hint": "gpt-4o"},
    ),
    SourceDefinition(
        id="youmind-gpt-image-2",
        name="YouMind awesome-gpt-image-2",
        repo_url="https://github.com/YouMind-OpenLab/awesome-gpt-image-2",
        raw_base_url="https://raw.githubusercontent.com/YouMind-OpenLab/awesome-gpt-image-2/main",
        raw_path="README_zh.md",
        parser="markdown_sections",
        category="youmind-gpt-image-2",
        metadata={"model_hint": "gpt-image-2"},
    ),
    SourceDefinition(
        id="youmind-nano-banana-pro",
        name="YouMind awesome-nano-banana-pro-prompts",
        repo_url="https://github.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts",
        raw_base_url="https://raw.githubusercontent.com/YouMind-OpenLab/awesome-nano-banana-pro-prompts/main",
        raw_path="README_zh.md",
        parser="markdown_sections",
        category="youmind-nano-banana-pro",
        metadata={"model_hint": "nano-banana-pro"},
    ),
    SourceDefinition(
        id="davidwu-gpt-image2-prompts",
        name="David Wu awesome-gpt-image2-prompts",
        repo_url="https://github.com/davidwuw0811-boop/awesome-gpt-image2-prompts",
        raw_base_url="https://raw.githubusercontent.com/davidwuw0811-boop/awesome-gpt-image2-prompts/main",
        raw_path="prompts.json",
        parser="json_prompts",
        category="davidwu-gpt-image2-prompts",
        metadata={"model_hint": "gpt-image-2"},
    ),
)


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


def _absolute_image(base_url: str, image: str) -> str:
    image = (image or "").strip()
    if not image:
        return ""
    if re.match(r"^https?://", image, re.I):
        return image
    return f"{base_url.rstrip('/')}/{image.lstrip('./')}"


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
                    tags=tuple(section_tags),
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
                tags=tuple(sorted(set(tags))),
                category=str(raw.get("category_cn") or raw.get("category") or category),
                source_url=str(raw.get("githubUrl") or raw.get("source_url") or repo_url),
                model_hint=str(raw.get("model") or model_hint),
                needs_reference_image=bool(raw.get("needs_ref") or raw.get("needs_reference_image")),
                language="zh" if re.search(r"[\u4e00-\u9fff]", title + prompt) else "en",
                metadata={k: v for k, v in raw.items() if k not in {"prompt", "positive_prompt"}},
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
        for definition in DEFAULT_IMAGE_PROMPT_SOURCES:
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
            return {"success": True, "source_id": source.id, "total": len(parsed), "created": created, "updated": updated}
        except Exception as exc:
            source.sync_status = "failed"
            source.error = str(exc)
            source.updated_at = _utc_now()
            self.session.add(source)
            self.session.commit()
            raise

    def refresh_source(self, source_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
        source = self.get_source(source_id)
        if not source:
            raise ValueError(f"image prompt source not found: {source_id}")
        url = f"{source.raw_base_url.rstrip('/')}/{source.raw_path.lstrip('/')}"
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return self.sync_source_payload(source, response.text)

    def refresh_sources(self, *, source_id: str | None = None) -> dict[str, Any]:
        sources = [self.get_source(source_id)] if source_id else self.list_sources()
        results: list[dict[str, Any]] = []
        for source in sources:
            if not source:
                continue
            try:
                results.append(self.refresh_source(source.id))
            except Exception as exc:
                results.append({"success": False, "source_id": source.id, "error": str(exc)})
        return {
            "success": all(item.get("success") for item in results),
            "total_sources": len(results),
            "results": results,
        }

    def search_references(
        self,
        *,
        keyword: str = "",
        tag: str = "",
        category: str = "",
        source_id: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        query = select(ImagePromptReference).order_by(ImagePromptReference.updated_at.desc())
        if source_id:
            query = query.where(ImagePromptReference.source_id == source_id)
        if category and category.lower() not in {"all", "全部"}:
            query = query.where(ImagePromptReference.category == category)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            query = query.where(
                or_(
                    ImagePromptReference.title.ilike(pattern),
                    ImagePromptReference.prompt.ilike(pattern),
                    ImagePromptReference.category.ilike(pattern),
                )
            )
        rows = list(self.session.exec(query).all())
        if tag:
            normalized_tag = tag.strip().lower()
            rows = [row for row in rows if normalized_tag in {str(item).lower() for item in (row.tags_json or [])}]
        total = len(rows)
        offset = (page - 1) * page_size
        items = rows[offset : offset + page_size]
        return {
            "success": True,
            "items": [self.reference_to_dict(row, preview=True) for row in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "categories": sorted({row.category for row in rows if row.category}),
            "tags": sorted({tag for row in rows for tag in (row.tags_json or []) if tag}),
        }

    def get_reference(self, reference_id: str) -> ImagePromptReference | None:
        return self.session.get(ImagePromptReference, reference_id)

    def save_reference_as_asset(self, reference_id: str) -> dict[str, Any]:
        from uuid import uuid4

        ref = self.get_reference(reference_id)
        if not ref:
            raise ValueError(f"image prompt reference not found: {reference_id}")
        now = _utc_now()
        node = AssetNode(
            id=str(uuid4()),
            name=ref.title,
            asset_type=AssetType.TEXT,
            thumbnail_url=ref.cover_url or None,
            metadata_json={
                "source": "image_prompt_reference_library",
                "reference_id": ref.id,
                "source_id": ref.source_id,
                "source_url": ref.source_url,
                "prompt": ref.prompt,
                "negative_prompt": ref.negative_prompt,
                "model_hint": ref.model_hint,
            },
            tags_json=list(ref.tags_json or []),
            created_at=now,
            updated_at=now,
        )
        version = AssetVersion(
            id=str(uuid4()),
            asset_node_id=node.id,
            version_number=1,
            prompt_used=ref.prompt,
            model_used=ref.model_hint or None,
            params_json={"reference_id": ref.id},
            lineage_json={"source": "image_prompt_reference", "reference_id": ref.id, "source_id": ref.source_id},
            created_at=now,
        )
        self.session.add(node)
        self.session.add(version)
        self.session.commit()
        return {"success": True, "asset_node_id": str(node.id), "asset_version_id": str(version.id), "reference_id": ref.id}

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
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        }

    @staticmethod
    def reference_to_dict(reference: ImagePromptReference, *, preview: bool = False) -> dict[str, Any]:
        prompt = reference.prompt or ""
        return {
            "id": reference.id,
            "source_id": reference.source_id,
            "external_id": reference.external_id,
            "title": reference.title,
            "prompt": prompt[:360] + "..." if preview and len(prompt) > 360 else prompt,
            "negative_prompt": reference.negative_prompt,
            "cover_url": reference.cover_url,
            "preview_markdown": reference.preview_markdown,
            "tags": list(reference.tags_json or []),
            "category": reference.category,
            "source_url": reference.source_url,
            "model_hint": reference.model_hint,
            "needs_reference_image": reference.needs_reference_image,
            "language": reference.language,
            "metadata": dict(reference.metadata_json or {}),
            "created_at": reference.created_at.isoformat() if reference.created_at else None,
            "updated_at": reference.updated_at.isoformat() if reference.updated_at else None,
        }
