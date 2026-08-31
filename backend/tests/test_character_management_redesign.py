import json
from app.db.models.character import Character, CharacterRelationship
from app.services.character.service import CharacterService

def test_character_response_includes_field_sources_and_prompt_pack():
    service = CharacterService.__new__(CharacterService)
    character = Character(id="c1", name="林夏", appearance="短发", speech_json=json.dumps({"pace": "慢"}), field_sources_json=json.dumps({"appearance": "original", "personality": "ai_inferred"}))
    data = service.to_response(character)
    assert data["field_sources"]["appearance"] == "original"
    assert data["workflow_source"] == "unknown"
    assert data["workflow_source_label"] == "未标记"
    pack = service.build_prompt_pack(character)
    assert "林夏" in pack["image_prompt"]
    assert pack["character_json"]["id"] == "c1"

def test_relationship_response_is_stable():
    service = CharacterService.__new__(CharacterService)
    relationship = CharacterRelationship(id="r1", character_id="c1", related_character_id="c2", relation_type="盟友", relation_note="共同调查", source="原文", is_directed=True)
    data = service.relationship_to_response(relationship)
    assert data == {
        "id": "r1",
        "character_id": "c1",
        "related_character_id": "c2",
        "related_character_name": "",
        "relation_type": "盟友",
        "relation_note": "共同调查",
        "source": "原文",
        "is_directed": True,
        "world_usage_id": None,
        "world_name": None,
        "timeline_phase": "",
        "chapter_number": None,
        "created_at": str(relationship.created_at),
        "updated_at": str(relationship.updated_at),
    }


def test_character_response_normalizes_legacy_object_array_fields():
    service = CharacterService.__new__(CharacterService)
    character = Character(
        id="c2",
        name="历史角色",
        tags="{}",
        reference_asset_ids="{}",
        signature_items="{}",
        expressions="not-json",
        poses=json.dumps(["站立"], ensure_ascii=False),
    )
    data = service.to_response(character)
    assert data["tags"] == []
    assert data["reference_asset_ids"] == []
    assert data["signature_items"] == []
    assert data["expressions"] == []
    assert data["poses"] == ["站立"]
