from app.services.creative_project.profiles import (
    CONTENT_PRODUCTION_PROFILES,
    PACKAGE_PLAN_STAGES,
    get_content_production_profile,
    is_content_package_profile,
    normalize_project_settings,
    validate_profile_inputs,
)
from app.services.creative_project.schemas import ContentPackagePlanSchema

#: 叙事族阶段名：内容包 profile 不得使用（#17）
NARRATIVE_STAGES = {
    "outline",
    "chapter_plan",
    "chapter_outline",
    "novel_body",
    "script",
    "storyboard",
    "comic_pages",
    "story_seed",
    "review",
}


def test_storybook_profile_routes_to_package_stages_not_narrative():
    """内容包项目的导演必须拿到内容包阶段，而不是叙事阶段（#17）。

    `context_pack` 会把 `recommended_stages` 原样交给导演；若它写成
    `outline/chapter_plan/chapter_outline`，导演就会为一个绘本包提议章节大纲——
    这正是本条要修的路由错误。
    """
    profile = get_content_production_profile("storybook")

    assert profile["project_type"] == "manga"
    assert profile["production_family"] == "content_package"
    assert profile["package_type"] == "page_book"
    assert profile["planning_unit"] == "item"
    assert profile["recommended_stages"] == list(PACKAGE_PLAN_STAGES)

    used = set(profile["recommended_stages"]) | set(profile["optional_stages"])
    assert not used & NARRATIVE_STAGES, f"内容包 profile 不得使用叙事阶段：{sorted(used & NARRATIVE_STAGES)}"


def test_narrative_profiles_keep_existing_stages():
    """#17 的另一半：叙事项目的既有阶段词表不被内容包词表改写。"""
    drama = get_content_production_profile("vertical_drama")
    assert drama["production_family"] == "narrative"
    assert drama["recommended_stages"] == [
        "outline", "chapter_plan", "chapter_outline", "script", "storyboard", "video",
    ]
    assert not set(drama["recommended_stages"]) & set(PACKAGE_PLAN_STAGES)

    novel = get_content_production_profile("novel_serial")
    assert novel["production_family"] == "narrative"
    assert novel["recommended_stages"] == [
        "outline", "chapter_plan", "chapter_outline", "novel_body", "review",
    ]
    assert not set(novel["recommended_stages"]) & set(PACKAGE_PLAN_STAGES)


def test_every_package_profile_uses_only_declared_package_stages():
    """所有内容包 profile 的阶段都必须落在声明过的词表内。

    这条防的是「以后再给某个内容包 profile 顺手写上 outline」——词表是唯一事实源，
    任意阶段名会让导演拿到不存在的编排单位。
    """
    declared = set(PACKAGE_PLAN_STAGES) | {"item_review", "layout"}
    package_profiles = {
        pid: item
        for pid, item in CONTENT_PRODUCTION_PROFILES.items()
        if item["production_family"] == "content_package"
    }
    assert package_profiles, "应至少有一个内容包 profile"

    for profile_id, profile in package_profiles.items():
        assert profile["recommended_stages"], f"{profile_id} 必须有推荐阶段"
        used = set(profile["recommended_stages"]) | set(profile["optional_stages"])
        assert used <= declared, f"{profile_id} 使用了未声明的阶段：{sorted(used - declared)}"


def test_package_stage_vocabulary_matches_available_capabilities():
    """每个阶段名都必须对应一个已存在的能力，不能是构想。

    这条把「阶段词表不是凭空写的」变成可检查的：规划入口、条目编辑、批量媒体任务与
    适配器输出四类能力都已落地（对应 `#7/#8/#11/#15`）。
    """
    assert PACKAGE_PLAN_STAGES == (
        "package_plan",
        "item_text",
        "item_prompt",
        "media_batch",
        "package_outputs",
    )


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
