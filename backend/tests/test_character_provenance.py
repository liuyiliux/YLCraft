from types import SimpleNamespace

import pytest

from app.db.models.character import CharacterStoryLink
from app.services.character.provenance import (
    EXTRACT_ORIGIN_IMPORTED_NOVEL,
    EXTRACT_ORIGIN_ORIGINAL_OUTLINE,
    EXTRACT_ORIGIN_UPLOADED_NOVEL,
    build_field_sources,
    extract_origin_label,
    mark_user_edited,
    merge_field_sources,
    resolve_extract_origin,
)
from app.services.character.service import CharacterService


def _project(source_type: str, source_ref: dict) -> SimpleNamespace:
    import json

    return SimpleNamespace(
        source_type=source_type,
        source_ref_json=json.dumps(source_ref, ensure_ascii=False),
    )


def test_resolve_extract_origin_distinguishes_uploaded_and_imported_novel():
    uploaded = _project("novel", {"asset_id": "asset-1", "chapter_ids": ["c1"]})
    imported = _project("novel", {"asset_id": "asset-2", "source": "novel_bookshelf", "source_name": "起点"})
    original = _project("original_idea", {})

    assert resolve_extract_origin(uploaded) == EXTRACT_ORIGIN_UPLOADED_NOVEL
    assert resolve_extract_origin(imported) == EXTRACT_ORIGIN_IMPORTED_NOVEL
    assert resolve_extract_origin(original) == EXTRACT_ORIGIN_ORIGINAL_OUTLINE


def test_extract_origin_labels_are_chinese():
    assert extract_origin_label(EXTRACT_ORIGIN_UPLOADED_NOVEL) == "上传小说提取"
    assert extract_origin_label(EXTRACT_ORIGIN_IMPORTED_NOVEL) == "外来小说导入"
    assert "原创大纲" in extract_origin_label(EXTRACT_ORIGIN_ORIGINAL_OUTLINE)


def test_original_outline_marks_ai_inferred_while_novel_extract_marks_original():
    assert build_field_sources(EXTRACT_ORIGIN_UPLOADED_NOVEL) == "original"
    assert build_field_sources(EXTRACT_ORIGIN_IMPORTED_NOVEL) == "original"
    assert build_field_sources(EXTRACT_ORIGIN_ORIGINAL_OUTLINE) == "ai_inferred"


def test_merge_field_sources_only_fills_gaps_and_maps_outline_keys():
    merged = merge_field_sources(
        {"appearance": "user_edited"},
        {
            "appearance": "黑色短发",
            "image_prompt": "银灰短发",
            "personality": "冷静执拗",
            "identity": "调查员",
            "empty_field": "",
        },
        source="original",
    )

    # 用户手动标记的字段不被同步流程覆盖
    assert merged["appearance"] == "user_edited"
    assert merged["personality"] == "original"
    assert merged["identity"] == "original"
    assert "empty_field" not in merged


def test_mark_user_edited_overrides_existing_sources():
    marked = mark_user_edited({"appearance": "original"}, ["appearance", "personality"])
    assert marked == {"appearance": "user_edited", "personality": "user_edited"}


def test_story_link_response_exposes_extract_origin():
    service = CharacterService.__new__(CharacterService)
    link = CharacterStoryLink(
        id="link-1",
        character_id="char-1",
        story_id="project-1",
        world_name="霓虹城",
        extract_origin=EXTRACT_ORIGIN_IMPORTED_NOVEL,
    )

    data = service.story_link_to_response(link, None)

    assert data["extract_origin"] == EXTRACT_ORIGIN_IMPORTED_NOVEL
    assert data["extract_origin_label"] == "外来小说导入"


@pytest.mark.asyncio
async def test_extract_origins_for_batches_and_skips_unknown():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    import app.db.models  # noqa: F401  (registry for table creation)
    from app.db.models.character import Character

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: (
                Character.__table__.create(sync_conn),
                CharacterStoryLink.__table__.create(sync_conn),
            )
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        character = Character(name="苏棠")
        session.add(character)
        await session.commit()
        await session.refresh(character)
        for origin in (
            EXTRACT_ORIGIN_IMPORTED_NOVEL,
            EXTRACT_ORIGIN_ORIGINAL_OUTLINE,
            "unknown",
        ):
            session.add(
                CharacterStoryLink(character_id=character.id, story_id=f"p-{origin}", extract_origin=origin)
            )
        await session.commit()

        service = CharacterService(session)
        origins = await service.extract_origins_for([character.id])
        data = service.to_response(character, extract_origins=origins)

    assert origins == {character.id: [EXTRACT_ORIGIN_IMPORTED_NOVEL, EXTRACT_ORIGIN_ORIGINAL_OUTLINE]}
    assert data["extract_origins"] == [EXTRACT_ORIGIN_IMPORTED_NOVEL, EXTRACT_ORIGIN_ORIGINAL_OUTLINE]


@pytest.mark.asyncio
async def test_list_characters_filters_by_extract_origin():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    import app.db.models  # noqa: F401  (registry for table creation)
    from app.db.models.character import Character

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: (
                Character.__table__.create(sync_conn),
                CharacterStoryLink.__table__.create(sync_conn),
            )
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        uploaded = Character(name="上传角色")
        imported = Character(name="导入角色")
        session.add(uploaded)
        session.add(imported)
        await session.commit()
        await session.refresh(uploaded)
        await session.refresh(imported)
        session.add(
            CharacterStoryLink(
                character_id=uploaded.id, story_id="p1", extract_origin=EXTRACT_ORIGIN_UPLOADED_NOVEL
            )
        )
        session.add(
            CharacterStoryLink(
                character_id=imported.id, story_id="p2", extract_origin=EXTRACT_ORIGIN_IMPORTED_NOVEL
            )
        )
        await session.commit()

        service = CharacterService(session)
        uploaded_items, _ = await service.list(extract_origin=EXTRACT_ORIGIN_UPLOADED_NOVEL)
        missing_items, _ = await service.list(extract_origin=EXTRACT_ORIGIN_ORIGINAL_OUTLINE)

    assert [item.name for item in uploaded_items] == ["上传角色"]
    assert missing_items == []
