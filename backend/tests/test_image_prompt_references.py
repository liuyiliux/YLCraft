from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import images as images_api
from app.api.v1 import image_prompts as image_prompts_api
from app.api.v1.images import (
    ImageGenerateRequest,
    _generation_lineage_from_payload,
    _generation_lineage_from_request,
)
from app.db.models.image_prompt_reference import ImagePromptReference, ImagePromptSource
from app.services.agent.tools import image_prompt_reference_tools
from app.services.image_prompt_reference import service as prompt_reference_service
from app.services.image_prompt_reference.service import (
    ImagePromptReferenceService,
    parse_imi_detail_prompt_references,
    parse_json_prompt_references,
    parse_markdown_prompt_references,
)


MARKDOWN_FIXTURE = """
# Prompt Library

## Portrait / Cinematic

### Neon detective

**Prompt**

```text
A cinematic portrait of a neon detective, rain, rim light.
```

![cover](images/neon.png)

### Empty block

No prompt here.
"""


JSON_FIXTURE = [
    {
        "id": 7,
        "title_cn": "赛博街角",
        "title_en": "Cyber corner",
        "category_cn": "城市",
        "prompt": "A cyberpunk street corner with reflective ground.",
        "needs_ref": True,
        "image": "covers/city.png",
        "author": "demo",
    }
]

IMI_FIXTURE = [
    {
        "id": 14904,
        "slug": "cozy-bedroom-selfie",
        "title": "Cozy bedroom selfie",
        "cover_image": "ChatGPT/14904/14904-1.jpg",
        "detail_url": "https://opennana.com/awesome-prompt-gallery/cozy-bedroom-selfie",
        "source_name": "@demo",
        "source_url": "https://x.com/demo/status/1",
        "english_prompt": "A realistic phone selfie in a cozy bedroom.",
        "chinese_prompt": "温馨卧室里的真实手机自拍。",
        "images": [
            {
                "url": "https://img.example.test/prompts/14904-1.jpg",
                "image_name": "14904-1",
                "filename": "14904-1.jpg",
                "path": "ChatGPT/14904/14904-1.jpg",
            },
            {
                "url": "https://img.example.test/prompts/14904-2.jpg",
                "image_name": "14904-2",
                "filename": "14904-2.jpg",
                "path": "ChatGPT/14904/14904-2.jpg",
            }
        ],
        "model": "ChatGPT",
        "tags": ["portrait", {"name": "selfie"}],
        "media_type": "image",
        "thumbnail": "https://img.example.test/prompts/14904-thumb.jpg",
        "view_count": 3,
    }
]


@pytest.fixture()
def prompt_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'image-prompts.db'}")
    ImagePromptSource.__table__.create(engine)
    ImagePromptReference.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(image_prompts_api, "SessionLocal", factory)
    monkeypatch.setattr(image_prompt_reference_tools, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def prompt_client(prompt_session_factory):
    app = FastAPI()
    app.include_router(image_prompts_api.router, prefix="/api/v1/image-prompts")
    return TestClient(app)


def test_markdown_and_json_prompt_parsers_normalize_reference_items():
    markdown_items = parse_markdown_prompt_references(
        MARKDOWN_FIXTURE,
        source_id="fixture-md",
        category="fixture",
        raw_base_url="https://raw.example.test/repo/main",
        repo_url="https://github.com/example/repo",
    )

    assert len(markdown_items) == 1
    assert markdown_items[0].title == "Neon detective"
    assert "neon detective" in markdown_items[0].prompt
    assert markdown_items[0].cover_url == "https://raw.example.test/repo/main/images/neon.png"
    assert markdown_items[0].tags == ("cinematic", "portrait")

    json_items = parse_json_prompt_references(
        JSON_FIXTURE,
        source_id="fixture-json",
        category="fixture-json",
        raw_base_url="https://raw.example.test/json/main",
        repo_url="https://github.com/example/json",
    )

    assert len(json_items) == 1
    assert json_items[0].external_id == "fixture-json-7"
    assert json_items[0].needs_reference_image is True
    assert "needs-reference-image" in json_items[0].tags


def test_imi_prompt_parser_prefers_cached_media(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_reference_service, "image_prompt_storage_root", lambda: tmp_path)
    cached = tmp_path / "media" / "imi-chatgpt-prompts" / "14904" / "14904-1.jpg"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"fake-image")

    items = parse_imi_detail_prompt_references(
        IMI_FIXTURE,
        source_id="imi-chatgpt-prompts",
        category="imi-chatgpt",
        raw_base_url="https://prompt.imi.ccwu.cc/ChatGPT",
        repo_url="https://prompt.imi.ccwu.cc/ChatGPT/chatgpt_detail_data.json",
        model_hint="ChatGPT",
        media_base_url="https://prompt.imi.ccwu.cc",
    )

    assert len(items) == 1
    assert items[0].external_id == "imi-chatgpt-prompts-14904"
    assert items[0].cover_url == "/api/v1/image-prompts/media/imi-chatgpt-prompts/14904/14904-1.jpg"
    assert "ChatGPT" == items[0].model_hint
    assert "portrait" in items[0].tags
    assert items[0].tags[-1] == "@demo"
    assert items[0].metadata["images"][0]["url"] == "https://img.example.test/prompts/14904-1.jpg"
    assert items[0].metadata["images"][0]["display_url"] == "/api/v1/image-prompts/media/imi-chatgpt-prompts/14904/14904-1.jpg"
    assert len(items[0].metadata["images"]) == 2


def test_image_prompt_reference_api_search_and_detail(prompt_client, prompt_session_factory):
    with prompt_session_factory() as session:
        service = ImagePromptReferenceService(session)
        source = service.get_source("awesome-gpt-image")
        assert source is not None
        result = service.sync_source_payload(source, MARKDOWN_FIXTURE)
        assert result["total"] == 1

    list_response = prompt_client.get("/api/v1/image-prompts/sources")
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 5
    assert list_response.json()["data"][0]["model_group"]

    search_response = prompt_client.get("/api/v1/image-prompts/references", params={"keyword": "detective"})
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert search_data["total"] == 1
    reference_id = search_data["items"][0]["id"]

    detail_response = prompt_client.get(f"/api/v1/image-prompts/references/{reference_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["prompt"].startswith("A cinematic portrait")

    group_response = prompt_client.get("/api/v1/image-prompts/references", params={"model_group": "ChatGPT"})
    assert group_response.status_code == 200
    assert group_response.json()["total"] == 1
    assert group_response.json()["items"][0]["model_group"] == "ChatGPT"


def test_search_references_prioritizes_items_with_cover_images(prompt_session_factory):
    with prompt_session_factory() as session:
        service = ImagePromptReferenceService(session)
        source = service.get_source("awesome-gpt-image")
        assert source is not None
        service.sync_source_payload(source, MARKDOWN_FIXTURE)

        no_cover = ImagePromptReference(
            id="manual:no-cover",
            source_id=source.id,
            external_id="manual-no-cover",
            title="No cover prompt",
            prompt="Plain text prompt without image.",
            category="fixture",
        )
        session.add(no_cover)
        session.commit()

        data = service.search_references(page=1, page_size=10)
        assert data["items"][0]["title"] == "Neon detective"
        assert data["items"][0]["cover_url"]


def test_refresh_source_does_not_fetch_remote_without_cache(prompt_session_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_reference_service, "image_prompt_storage_root", lambda: tmp_path)
    with prompt_session_factory() as session:
        service = ImagePromptReferenceService(session)
        source = service.get_source("awesome-gpt-image")
        assert source is not None
        service.sync_source_payload(source, MARKDOWN_FIXTURE)

        result = service.refresh_source(source.id, force_remote=False)

        assert result["success"] is True
        assert result["cache"] == "missing"
        assert result["skipped_remote"] is True
        assert result["total"] == 1


@pytest.mark.asyncio
async def test_agent_image_prompt_reference_tools_search_and_save(prompt_session_factory):
    with prompt_session_factory() as session:
        service = ImagePromptReferenceService(session)
        source = service.get_source("awesome-gpt-image")
        assert source is not None
        service.sync_source_payload(source, MARKDOWN_FIXTURE)

    listed = await image_prompt_reference_tools.list_image_prompt_sources()
    assert listed["success"] is True
    assert listed["total"] >= 5

    searched = await image_prompt_reference_tools.search_image_prompt_references(keyword="neon")
    assert searched["success"] is True
    assert searched["total"] == 1
    reference_id = searched["items"][0]["id"]

    detail = await image_prompt_reference_tools.get_image_prompt_reference(reference_id)
    assert detail["success"] is True
    assert detail["reference"]["title"] == "Neon detective"


def test_image_generation_lineage_includes_prompt_reference_metadata():
    req = ImageGenerateRequest(
        prompt="A cinematic portrait",
        prompt_reference_id="ref-1",
        prompt_reference_source_id="source-1",
        prompt_reference_title="Neon detective",
        prompt_reference_category="portrait",
        prompt_reference_source_url="https://example.test/prompts/ref-1",
    )

    lineage = _generation_lineage_from_request(req)
    assert lineage["prompt_reference_id"] == "ref-1"
    assert lineage["prompt_reference_source_id"] == "source-1"
    assert lineage["prompt_reference_title"] == "Neon detective"
    assert lineage["prompt_reference_category"] == "portrait"
    assert lineage["prompt_reference_source_url"] == "https://example.test/prompts/ref-1"

    payload_lineage = _generation_lineage_from_payload(
        {
            "prompt_reference_id": "ref-2",
            "prompt_reference_source_id": "source-2",
            "prompt_reference_title": "Cyber corner",
        },
        extra={"task_id": "task-1"},
    )
    assert payload_lineage["prompt_reference_id"] == "ref-2"
    assert payload_lineage["prompt_reference_source_id"] == "source-2"
    assert payload_lineage["prompt_reference_title"] == "Cyber corner"
    assert payload_lineage["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_generated_image_asset_hub_save_rolls_back_failed_transaction(monkeypatch):
    from app.db import database

    rollbacks: list[int] = []

    class FakeNestedTransaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def begin_nested(self):
            return FakeNestedTransaction()

        async def rollback(self):
            rollbacks.append(1)

    async def fail_create_asset(*args, **kwargs):
        raise SQLAlchemyError("broken transaction")

    @asynccontextmanager
    async def fake_get_async_session():
        session = FakeSession()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

    monkeypatch.setattr(database, "get_async_session", fake_get_async_session)
    monkeypatch.setattr(images_api, "_create_generated_image_asset_hub", fail_create_asset)

    node_id = await images_api._try_create_generated_image_asset_hub(
        context="test",
        image_path="generated.png",
        prompt="demo",
        provider="test-provider",
        model="test-model",
    )

    assert node_id == ""
    assert rollbacks == [1]
