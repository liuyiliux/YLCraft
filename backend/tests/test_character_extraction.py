import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.character.service import CharacterService
from app.services.creative_project.service import CHARACTER_SOURCE_MAX_CHARS, CreativeProjectService
from app.db.models.character import Character, CharacterStoryLink
from app.db.models.novel import NovelChapter


def test_character_rosters_merge_exact_aliases_and_keep_verbatim_evidence():
    service = CreativeProjectService.__new__(CreativeProjectService)
    merged, candidates = service._merge_character_rosters([
        {"name": "陆行远", "aliases": ["陆先生"], "note": "戴眼镜", "quotes": ["别说话。"]},
        {"name": "陆先生", "aliases": ["行远"], "note": "握住伞柄", "quotes": ["别说话。", "跟我走。"]},
        {"name": "陆", "aliases": [], "note": "站在门口", "quotes": []},
    ])

    assert len(merged) == 2
    assert merged[0]["name"] == "陆行远"
    assert merged[0]["aliases"] == ["陆先生", "行远"]
    assert merged[0]["quotes"] == ["别说话。", "跟我走。"]
    assert candidates == [{"left": "陆行远", "right": "陆", "reason": "名字包含关系，需人工确认是否同一人"}]


def test_extracted_card_drops_quotes_not_found_in_source_and_maps_bible_sections():
    service = CreativeProjectService.__new__(CreativeProjectService)
    card = service._normalize_extracted_character_card(
        {
            "name": "林默",
            "speech": {"tone": "短句"},
            "speech_profile": {"voice_prompt": "low male voice"},
            "behavior_profile": {"boundary": "不伤害无辜者"},
            "arc_profile": {"start_state": "逃避"},
            "evidence": ["不存在的句子"],
        },
        {
            "name": "林默",
            "aliases": ["林记者"],
            "note": "总在记录细节",
            "quotes": ["他把录音笔收回口袋。"],
        },
        "雨夜里，他把录音笔收回口袋。",
    )

    assert card["aliases"] == ["林记者"]
    assert card["evidence"] == ["他把录音笔收回口袋。"]
    assert card["speech"] == {"tone": "短句", "voice_prompt": "low male voice"}
    assert card["behavior"] == {"boundary": "不伤害无辜者"}
    assert card["arc"] == {"start_state": "逃避"}
    assert card["extraction_notes"] == "总在记录细节"


def test_novel_character_source_reads_selected_chapters_in_order(tmp_path):
    service = CreativeProjectService.__new__(CreativeProjectService)
    first_path = tmp_path / "chapter-1.txt"
    second_path = tmp_path / "chapter-2.txt"
    first_path.write_text("第一章 林默在门口留下录音笔。", encoding="utf-8")
    second_path.write_text("第二章 林岚在码头等他。", encoding="utf-8")
    chapters = [
        NovelChapter(asset_id="asset-1", chapter_index=2, chapter_title="第二章", content_path=str(second_path)),
        NovelChapter(asset_id="asset-1", chapter_index=1, chapter_title="第一章", content_path=str(first_path)),
    ]
    service._select_novel_chapters = lambda **kwargs: sorted(chapters, key=lambda item: item.chapter_index)

    source = service._read_project_novel_chapters({
        "asset_id": "asset-1",
        "chapter_ids": ["chapter-1", "chapter-2"],
        "chapter_indices": [1, 2],
    })

    assert source.index("第一章") < source.index("第二章")
    assert "林默" in source
    assert "林岚" in source


def test_novel_character_source_caps_heading_and_body_total(tmp_path):
    service = CreativeProjectService.__new__(CreativeProjectService)
    path = tmp_path / "large-chapter.txt"
    path.write_text("林默" + ("正文" * CHARACTER_SOURCE_MAX_CHARS), encoding="utf-8")
    chapter = NovelChapter(
        asset_id="asset-1",
        chapter_index=1,
        chapter_title="第一章",
        content_path=str(path),
    )
    service._select_novel_chapters = lambda **kwargs: [chapter]

    source = service._read_project_novel_chapters({
        "asset_id": "asset-1",
        "chapter_ids": [chapter.id],
    })

    assert "林默" in source
    assert len(source) <= CHARACTER_SOURCE_MAX_CHARS


def test_novel_character_source_falls_back_to_saved_sample_when_chapters_unavailable():
    service = CreativeProjectService.__new__(CreativeProjectService)
    service.session = type("Session", (), {"get": lambda self, model, key: None})()
    service._select_novel_chapters = lambda **kwargs: []
    project = type("Project", (), {
        "metadata_json": '{"source_sample":"节选中的林默"}',
        "source_ref_json": '{"asset_id":"asset-1","chapter_ids":["missing"]}',
        "outline_json": "{}",
    })()

    assert service._project_character_source_text(project) == "节选中的林默"


@pytest.mark.asyncio
async def test_confirmed_cards_are_applied_without_a_second_model_pass():
    service = CreativeProjectService.__new__(CreativeProjectService)
    project = type("Project", (), {
        "id": "project-1",
        "title": "测试项目",
        "source_type": "imported_novel",
        "metadata_json": "{}",
        "source_ref_json": "{}",
        "outline_json": "{}",
    })()
    service._require_project = lambda project_id: project
    service._project_character_source_text = lambda current: "林默收起录音笔。"
    service._split_character_source = lambda text, max_chars, max_chunks: [text]
    applied = []
    service._apply_extracted_character_cards = lambda current, cards: applied.extend(cards) or []

    async def unexpected_model_call(*args, **kwargs):
        raise AssertionError("confirmed preview cards must not trigger another model call")

    service._generate_json = unexpected_model_call
    cards = [{
        "name": "林默",
        "aliases": ["林记者"],
        "evidence": ["林默收起录音笔。", "模型编造的句子"],
        "extraction_notes": "习惯记录细节",
        "identity": {"logline": "记者"},
    }]

    result = await service.extract_character_cards("project-1", apply=True, cards=cards)

    assert result["applied"] is True
    assert len(applied) == 1
    assert applied[0]["evidence"] == ["林默收起录音笔。"]


def test_apply_extracted_cards_keeps_unmatched_existing_outline_characters():
    service = CreativeProjectService.__new__(CreativeProjectService)
    project = type("Project", (), {
        "id": "project-1",
        "outline_json": '{"characters":[{"name":"旧角色","role":"supporting"}]}',
        "updated_at": None,
    })()
    service.session = type("Session", (), {"add": lambda self, item: None})()
    service.sync_outline_characters = lambda project_id: []

    service._apply_extracted_character_cards(project, [{"name": "新角色", "role": "protagonist"}])

    names = [item["name"] for item in __import__("json").loads(project.outline_json)["characters"]]
    assert names == ["新角色", "旧角色"]


@pytest.mark.asyncio
async def test_character_list_applies_all_filters_and_returns_filtered_total():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Character.metadata.create_all(
                sync_connection, tables=[Character.__table__, CharacterStoryLink.__table__]
            )
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Character(id="c1", name="林默", role="protagonist", workflow_source="extract", source_types='["ai_generated"]', tags='["记者"]', is_favorite=True),
            Character(id="c2", name="林岚", role="supporting", workflow_source="character_first", source_types='["local_material"]', tags='["记者"]', is_favorite=False),
            Character(id="c3", name="周岚", role="supporting", workflow_source="extract", source_types='["ai_generated"]', tags='["反派"]', is_favorite=False),
        ])
        await session.commit()
        service = CharacterService(session)

        items, total = await service.list(
            workflow_source="extract",
            source_type="ai_generated",
            tag="记者",
            is_favorite=False,
            page=1,
            page_size=20,
        )

        assert [item.id for item in items] == []
        assert total == 0

        items, total = await service.list(tag="记者", page=1, page_size=20)
        assert [item.id for item in items] == ["c1", "c2"]
        assert total == 2
    await engine.dispose()
