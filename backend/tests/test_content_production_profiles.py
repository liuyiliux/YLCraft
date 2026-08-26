from app.services.creative_project.profiles import (
    get_content_production_profile,
    is_content_package_profile,
    normalize_project_settings,
    validate_profile_inputs,
)
from app.services.creative_project.schemas import ContentPackagePlanSchema


def test_storybook_profile_keeps_prose_optional():
    profile = get_content_production_profile("storybook")

    assert profile["project_type"] == "manga"
    assert "comic_pages" in profile["recommended_stages"]
    assert "novel_body" in profile["optional_stages"]
    assert profile["production_family"] == "content_package"
    assert profile["package_type"] == "page_book"
    assert profile["planning_unit"] == "item"


def test_project_type_provides_legacy_default_profile():
    settings = normalize_project_settings({}, profile_id=None, project_type="novel")

    assert settings["production_profile"] == "novel_serial"
    assert settings["production_family"] == "narrative"
    assert settings["production_profile_version"] == 1


def test_profile_family_routes_lightweight_workflows():
    assert is_content_package_profile("storybook") is True
    assert is_content_package_profile("knowledge_content") is True
    assert is_content_package_profile("novel_serial") is False
    assert is_content_package_profile(None, "novel") is False


def test_source_material_can_satisfy_package_input_requirement():
    result = validate_profile_inputs("knowledge_content", source_assets=["asset-1"])
    assert result["topic"] == ""
    assert result["source_assets"] == ["asset-1"]


def test_empty_profile_input_is_rejected_before_planning():
    try:
        validate_profile_inputs("storybook")
    except ValueError as exc:
        assert "主题" in str(exc)
    else:
        raise AssertionError("expected empty package input to be rejected")


def test_knowledge_card_schema_exposes_fact_and_source_fields():
    package = ContentPackagePlanSchema.model_validate({
        "topic": "十二生肖",
        "items": [{
            "title": "鼠",
            "fact": "鼠在十二生肖中排第一。",
            "source": "中国国家博物馆",
            "source_url": "https://example.com/zodiac",
        }],
    })
    item = package.items[0]
    assert item.fact == "鼠在十二生肖中排第一。"
    assert item.source == "中国国家博物馆"
    assert item.source_url.endswith("/zodiac")
