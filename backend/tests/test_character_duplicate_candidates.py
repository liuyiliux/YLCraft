import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.character import Character, CharacterStoryLink
from app.services.character.service import CharacterService


@pytest.mark.asyncio
async def test_duplicate_candidates_include_exact_name_alias_and_usage():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: (
            Character.__table__.create(sync_conn),
            CharacterStoryLink.__table__.create(sync_conn),
        ))

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        exact = Character(name="林默", role="protagonist")
        alias = Character(name="沈砚")
        session.add(exact)
        session.add(alias)
        await session.commit()
        await session.refresh(exact)
        await session.refresh(alias)
        session.add(CharacterStoryLink(
            character_id=alias.id,
            story_id="project-1",
            world_name="霓虹城",
            aliases_json='["林队"]',
        ))
        await session.commit()

        service = CharacterService(session)
        exact_candidates = await service.find_duplicate_candidates(" 林默 ")
        alias_candidates = await service.find_duplicate_candidates("林队")
        excluded = await service.find_duplicate_candidates("林默", exclude_id=exact.id)

    assert exact_candidates[0]["id"] == exact.id
    assert exact_candidates[0]["match_type"] == "exact_name"
    assert alias_candidates[0]["id"] == alias.id
    assert alias_candidates[0]["match_type"] == "alias_match"
    assert alias_candidates[0]["project_usages"][0]["world_name"] == "霓虹城"
    assert excluded == []
    await engine.dispose()
