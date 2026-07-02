from types import SimpleNamespace

from app.services.character.enrichment import (
    build_character_enrichment_prompt,
    character_response_for_enrichment,
    merge_character_enrichment,
    parse_character_enrichment_response,
)


def test_parse_character_enrichment_response_accepts_json_fence():
    data = parse_character_enrichment_response(
        """```json
{
  "appearance": "黑色短发，左眼下有痣",
  "signature_items": ["银色钢笔", "银色钢笔"],
  "identity": {"logline": "用推理拆穿短剧模板"},
  "behavior": {"never_do": "不会无理由背叛同伴"}
}
```"""
    )

    assert data["appearance"] == "黑色短发，左眼下有痣"
    assert data["signature_items"] == ["银色钢笔"]
    assert data["identity"]["logline"] == "用推理拆穿短剧模板"
    assert data["behavior"]["never_do"] == "不会无理由背叛同伴"


def test_merge_character_enrichment_fill_missing_preserves_existing_fields():
    current = {
        "appearance": "已有外貌",
        "personality": "",
        "signature_items": ["旧钢笔"],
        "expressions": [],
        "identity": {"position": "导演"},
        "motivation": {},
        "speech": {},
        "behavior": {},
        "ability": {},
        "arc": {},
        "tags": [],
    }
    proposal = {
        "appearance": "新外貌",
        "personality": "克制、审慎",
        "signature_items": ["新道具"],
        "expressions": ["冷静", "皱眉"],
        "identity": {"position": "制片人", "logline": "控制片场节奏的人"},
    }

    merged, applied = merge_character_enrichment(current, proposal, mode="fill_missing")

    assert merged["appearance"] == "已有外貌"
    assert merged["signature_items"] == ["旧钢笔"]
    assert merged["personality"] == "克制、审慎"
    assert merged["expressions"] == ["冷静", "皱眉"]
    assert merged["identity"]["position"] == "导演"
    assert merged["identity"]["logline"] == "控制片场节奏的人"
    assert set(applied) == {"personality", "expressions", "identity"}


def test_merge_character_enrichment_rewrite_replaces_existing_fields():
    current = {
        "appearance": "旧外貌",
        "identity": {"position": "旧身份"},
    }
    proposal = {
        "appearance": "新外貌",
        "identity": {"position": "新身份"},
    }

    merged, applied = merge_character_enrichment(current, proposal, mode="rewrite")

    assert merged["appearance"] == "新外貌"
    assert merged["identity"]["position"] == "新身份"
    assert set(applied) == {"appearance", "identity"}


def test_character_response_for_enrichment_reads_legacy_json_strings():
    character = SimpleNamespace(
        name="导演",
        role="antagonist",
        source_types='["ai_generated"]',
        appearance="",
        personality="",
        costume_hint="黑色西装",
        signature_items='["场记板"]',
        expressions="[]",
        poses="[]",
        visual_consistency="",
        background="",
        age_range="外表约35岁",
        identity_json='{"position":"导演"}',
        motivation_json="{}",
        speech_json="{}",
        behavior_json="{}",
        ability_json="{}",
        arc_json="{}",
        tags='["短剧"]',
    )

    data = character_response_for_enrichment(character)
    prompt = build_character_enrichment_prompt(data, context="测试上下文")

    assert data["source_types"] == ["ai_generated"]
    assert data["identity"]["position"] == "导演"
    assert "测试上下文" in prompt
    assert "只补充空字段" in prompt
