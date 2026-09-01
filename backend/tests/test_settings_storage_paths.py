import pytest
from fastapi import HTTPException

from app.api.v1 import settings as settings_api
from app.services import asset_file_resolver


@pytest.mark.asyncio
async def test_storage_settings_are_resolved_from_project_root(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_api, "project_root", lambda: tmp_path)
    monkeypatch.setattr(asset_file_resolver, "project_root", lambda: tmp_path)
    monkeypatch.setattr(settings_api, "_load_settings_from_file", lambda: {})
    monkeypatch.setattr(settings_api, "_save_settings_to_file", lambda settings: None)
    saved = {}

    async def save_setting(key, value, description=""):
        saved[key] = value

    monkeypatch.setattr(settings_api, "_save_setting_to_db", save_setting)

    await settings_api.update_all_settings(
        settings_api.SettingsUpdateRequest(
            patch={"image_gen_path": "backend\\storage\\images", "novel_source_path": "backend\\storage\\novels"}
        )
    )

    assert saved["image_gen_path"] == "backend/storage/images"
    assert saved["novel_source_path"] == "backend/storage/novels"
    assert (tmp_path / "backend" / "storage" / "images").is_dir()


@pytest.mark.asyncio
async def test_storage_settings_reject_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_api, "project_root", lambda: tmp_path)
    monkeypatch.setattr(asset_file_resolver, "project_root", lambda: tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await settings_api.update_all_settings(
            settings_api.SettingsUpdateRequest(
                patch={"upload_path": "C:/old-machine/uploads"}
            )
        )

    assert exc_info.value.status_code == 400
