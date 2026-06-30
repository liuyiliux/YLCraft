from types import SimpleNamespace

import pytest

from app.services.asset_hub.facade import AssetHubFacade


class _FakeNodeService:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = []
        self.updated = []

    async def get(self, node_id: str):
        return self.existing if self.existing and str(self.existing.id) == node_id else None

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id="node-1")

    async def update(self, **kwargs):
        self.updated.append(kwargs)
        return self.existing


class _FakeVersionService:
    def __init__(self):
        self.created = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id=f"version-{len(self.created)}", version_number=len(self.created))


class _FakeRepresentationService:
    def __init__(self):
        self.created = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id=f"rep-{len(self.created)}")


def _facade(node_service=None):
    facade = AssetHubFacade.__new__(AssetHubFacade)
    facade.node_service = node_service or _FakeNodeService()
    facade.version_service = _FakeVersionService()
    facade.rep_service = _FakeRepresentationService()
    return facade


@pytest.mark.asyncio
async def test_character_portrait_facade_creates_node_version_and_representation():
    facade = _facade()
    character = SimpleNamespace(id="char-1", name="测试角色", portrait_node_id=None)

    result = await facade.create_or_update_character_portrait(
        character=character,
        portrait_url="https://mmbiz.qpic.cn/image/640?wx_fmt=jpeg",
        prompt="portrait prompt",
        provider="modelscope",
        model="Qwen/Qwen-Image",
        generation_params={"n": 1},
    )

    assert result.node_id == "node-1"
    assert result.version_number == 1
    assert facade.node_service.created[0]["asset_type"].value == "character"
    assert facade.node_service.created[0]["tags"] == ["character_portrait"]
    assert facade.version_service.created[0]["params"]["provider"] == "modelscope"
    assert facade.rep_service.created[0]["mime_type"] == "image/jpeg"
    assert facade.rep_service.created[0]["format"] == "jpeg"


@pytest.mark.asyncio
async def test_character_portrait_facade_updates_existing_node():
    node_service = _FakeNodeService(existing=SimpleNamespace(id="existing-node"))
    facade = _facade(node_service)
    character = SimpleNamespace(
        id="char-1",
        name="测试角色",
        portrait_node_id="existing-node",
    )

    result = await facade.create_or_update_character_portrait(
        character=character,
        portrait_url="https://example.test/portrait.webp",
        prompt="new prompt",
    )

    assert result.node_id == "existing-node"
    assert node_service.created == []
    assert node_service.updated[0]["node_id"] == "existing-node"
    assert node_service.updated[0]["thumbnail_url"] == "https://example.test/portrait.webp"
    assert facade.rep_service.created[0]["mime_type"] == "image/webp"
