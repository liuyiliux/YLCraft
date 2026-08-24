from app.services.creative_project.profiles import (
    get_content_production_profile,
    normalize_project_settings,
)


def test_storybook_profile_keeps_prose_optional():
    profile = get_content_production_profile("storybook")

    assert profile["project_type"] == "manga"
    assert "comic_pages" in profile["recommended_stages"]
    assert "novel_body" in profile["optional_stages"]


def test_project_type_provides_legacy_default_profile():
    settings = normalize_project_settings({}, profile_id=None, project_type="novel")

    assert settings["production_profile"] == "novel_serial"
    assert settings["production_profile_version"] == 1
