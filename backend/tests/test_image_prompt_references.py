from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import image_prompts as image_prompts_api
from app.api.v1.images import (
    ImageGenerateRequest,
    _generation_lineage_from_payload,
    _generation_lineage_from_request,
)
from app.db.models.image_prompt_reference import ImagePromptReference, ImagePromptSource
from app.services.agent.tools import image_prompt_reference_tools
from app.services.image_prompt_reference.service import (
    ImagePromptReferenceService,
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

    search_response = prompt_client.get("/api/v1/image-prompts/references", params={"keyword": "detective"})
    assert search_response.status_code == 200
    search_data = search_response.json()
    assert search_data["total"] == 1
    reference_id = search_data["items"][0]["id"]

    detail_response = prompt_client.get(f"/api/v1/image-prompts/references/{reference_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["prompt"].startswith("A cinematic portrait")


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
