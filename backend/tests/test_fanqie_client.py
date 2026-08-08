"""Offline contract tests for the Fanqie client.

These tests intentionally never load a stored platform connection or make a
network request. Live publishing requires a user-created ``[TEST]`` chapter.
"""

import pytest

from app.services.platforms.fanqie.utils import (
    CookieExpiredError,
    FanqieError,
    ParamError,
    RiskControlError,
    classify_fanqie_error,
    markdown_to_fanqie_html,
    normalize_cookie,
    parse_netscape_cookie,
)


@pytest.mark.asyncio
async def test_fanqie_publish_preflight_resolves_binding_without_remote_call(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.db.models.creative_project import CreativeProject, ProjectContent
    from app.db.models.platform_connection import PlatformConnection, PlatformType
    from app.services.platforms.fanqie.publish_service import FanqiePublishService

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fanqie-preflight.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(CreativeProject.__table__.create)
        await connection.run_sync(ProjectContent.__table__.create)
        await connection.run_sync(PlatformConnection.__table__.create)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        project = CreativeProject(
            id="project-preflight",
            title="Preflight project",
            project_type="novel",
            settings_json='{"fanqie":{"conn_id":"conn-1","book_id":"book-1","volume_id":"volume-1","volume_name":"Test volume"}}',
        )
        content = ProjectContent(
            id="body-preflight",
            project_id=project.id,
            content_type="novel_body",
            chapter_number=3,
            title="[TEST] chapter",
            text_content="A valid chapter body.",
        )
        fanqie_connection = PlatformConnection(
            id="conn-1",
            platform=PlatformType.FANQIE,
            name="Fanqie test connection",
        )
        session.add(project)
        session.add(content)
        session.add(fanqie_connection)
        await session.commit()

        service = FanqiePublishService(session)
        ready = await service.preview_chapter(
            project_id=project.id,
            content_id=content.id,
            item_id="test-item-3",
        )
        assert ready["ready"] is True
        assert ready["missing"] == []
        assert ready["resolved_target"]["conn_id"] == "conn-1"
        assert ready["connection"] == {"exists": True, "platform": "fanqie", "status": "unknown"}
        assert ready["chapter"]["text_length"] == len(content.text_content)

        missing_item = await service.preview_chapter(
            project_id=project.id,
            content_id=content.id,
        )
        assert missing_item["ready"] is False
        assert missing_item["missing"] == ["item_id"]

        unknown_connection = await service.preview_chapter(
            project_id=project.id,
            content_id=content.id,
            item_id="test-item-3",
            conn_id="missing-connection",
        )
        assert unknown_connection["ready"] is False
        assert unknown_connection["connection"]["exists"] is False
        assert unknown_connection["missing"] == ["conn_id referencing a configured fanqie connection"]

        with pytest.raises(ValueError, match="conn_id 必须引用已配置的番茄平台连接"):
            await service.set_binding(
                project.id,
                conn_id="missing-connection",
                book_id="book-1",
                volume_id="volume-1",
                volume_name="Test volume",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_fanqie_publish_service_rejects_unimplemented_remote_publish_action():
    from app.services.platforms.fanqie.publish_service import FanqiePublishService

    service = FanqiePublishService(None)
    with pytest.raises(ValueError, match="仅支持保存番茄草稿"):
        await service.publish_chapter(
            project_id="project",
            content_id="content",
            conn_id="conn",
            book_id="book",
            volume_id="volume",
            volume_name="",
            item_id="item",
            action="publish",
        )

    with pytest.raises(ValueError, match="缺少目标参数：item_id"):
        await service.publish_chapter(
            project_id="project",
            content_id="content",
            conn_id="conn",
            book_id="book",
            volume_id="volume",
            volume_name="",
            item_id="",
        )


def test_markdown_to_fanqie_html_escapes_and_preserves_basic_formatting():
    assert markdown_to_fanqie_html("a\n\nb") == "<p>a</p><p>b</p>"
    assert markdown_to_fanqie_html("a\nb") == "<p>a<br>b</p>"
    assert "<strong>bold</strong>" in markdown_to_fanqie_html("**bold**")
    assert "&lt;script&gt;" in markdown_to_fanqie_html("<script>x</script>")


def test_cookie_normalization_accepts_raw_and_netscape_formats():
    assert normalize_cookie(" a=1 ; b=2 ") == "a=1; b=2"
    netscape = "# Netscape HTTP Cookie File\nfanqienovel.com\tFALSE\t/\tFALSE\t0\tsessionid\tabc123\n"
    assert parse_netscape_cookie(netscape) == {"sessionid": "abc123"}
    assert normalize_cookie(netscape) == "sessionid=abc123"


def test_fanqie_error_classification_preserves_actionable_categories():
    assert isinstance(classify_fanqie_error(-100, "用户未登录"), CookieExpiredError)
    assert isinstance(classify_fanqie_error(-1, "book_id 参数缺失"), ParamError)
    assert isinstance(classify_fanqie_error(-1, "内容触发风控"), RiskControlError)
    error = classify_fanqie_error(500, "服务异常")
    assert isinstance(error, FanqieError)
    assert not isinstance(error, (CookieExpiredError, ParamError, RiskControlError))


def test_fanqie_draft_request_contract_rejects_empty_item_and_unsupported_action():
    from pydantic import ValidationError

    from app.api.v1.creative_fanqie import FanqieChapterItem, PublishToFanqieRequest

    with pytest.raises(ValidationError):
        FanqieChapterItem(content_id="content", item_id="")
    with pytest.raises(ValidationError):
        PublishToFanqieRequest(action="publish")
