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


# =============================================================================
# E 组端点契约（2026-09-25 抓包确认）
#
# 这些测试锚定的是**抓包得到的真实契约**：路径、参数名与分页基准。
# 它们全部离线运行（不加载连接、不发网络请求）。
# 证据导出在 .local/fanqie-e-group-capture.json（不入库）。
# =============================================================================


def test_e_group_endpoint_constants_match_captured_paths():
    """端点常量必须与抓包到的真实路径一致。"""
    from app.services.platforms.fanqie import apis

    assert apis.ACCOUNT_INFO == "/api/author/account/info/v0/"
    assert apis.CHAPTER_LIST == "/api/author/chapter/chapter_list/v1"
    assert apis.VOLUME_LIST == "/api/author/volume/volume_list/v1"


@pytest.mark.asyncio
async def test_get_book_chapters_uses_zero_based_page_index_and_real_params(monkeypatch):
    """章节列表必须用真实参数名，且 page_index 是 0-based（对外 page 为 1 起）。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    captured: dict = {}

    async def fake_call(self, method, path, params=None, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params or {}
        return {"code": 0, "data": {"item_list": [{"item_id": "123", "index": 1}]}}

    monkeypatch.setattr(FanqieClient, "_call", fake_call)

    config = ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="sessionid=x")
    client = FanqieClient(config)

    data = await client.get_book_chapters("book-1", volume_id="vol-1", page=1, size=15)

    assert captured["path"] == "/api/author/chapter/chapter_list/v1"
    params = captured["params"]
    # 真实参数名（抓包确认）
    assert params["book_id"] == "book-1"
    assert params["volume_id"] == "vol-1"
    assert params["page_count"] == "15"
    assert params["status"] == "0"
    # page=1（对外）必须映射成 page_index=0（番茄内部 0 起）
    assert params["page_index"] == "0"
    # 抓包中实际出现的两个反馈参数
    assert params["must_have_correction_feedback"] == "0"
    assert params["need_correction_feedback_num"] == "1"
    # item_id 是自动映射的目标
    assert data["item_list"][0]["item_id"] == "123"


@pytest.mark.asyncio
async def test_get_book_chapters_page_two_maps_to_index_one(monkeypatch):
    """对外 page=2 应映射为 page_index=1，验证 0-based 转换不是写死的。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    captured: dict = {}

    async def fake_call(self, method, path, params=None, **kwargs):
        captured["params"] = params or {}
        return {"code": 0, "data": {"item_list": []}}

    monkeypatch.setattr(FanqieClient, "_call", fake_call)
    client = FanqieClient(ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="s=x"))

    await client.get_book_chapters("book-1", page=2)

    assert captured["params"]["page_index"] == "1"


@pytest.mark.asyncio
async def test_get_book_chapters_omits_volume_id_when_blank(monkeypatch):
    """不传卷时不应带上空的 volume_id（抓包中该参数只在按卷翻页时出现）。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    captured: dict = {}

    async def fake_call(self, method, path, params=None, **kwargs):
        captured["params"] = params or {}
        return {"code": 0, "data": {}}

    monkeypatch.setattr(FanqieClient, "_call", fake_call)
    client = FanqieClient(ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="s=x"))

    await client.get_book_chapters("book-1", volume_id="")

    assert "volume_id" not in captured["params"]


@pytest.mark.asyncio
async def test_get_my_profile_hits_account_info_and_passes_through_real_fields(monkeypatch):
    """作家资料走 account/info/v0/，并原样透传抓包到的真实字段。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    captured: dict = {}

    async def fake_call(self, method, path, params=None, **kwargs):
        captured["path"] = path
        return {
            "code": 0,
            "data": {
                "author_name": "逸流AI",
                "description": "新锐创作者",
                "avatar_url": "https://example.com/a.jpg",
                "point": 200,
                "author_level_id": 100,
            },
        }

    monkeypatch.setattr(FanqieClient, "_call", fake_call)
    client = FanqieClient(ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="s=x"))

    data = await client.get_my_profile()

    assert captured["path"] == "/api/author/account/info/v0/"
    assert data["author_name"] == "逸流AI"
    assert data["point"] == 200


@pytest.mark.asyncio
async def test_get_book_volumes_hits_volume_list(monkeypatch):
    """卷列表走 volume_list/v1。"""
    from app.services.platforms.fanqie.client import FanqieClient
    from app.services.platforms.types import ClientConfig, ClientMode

    captured: dict = {}

    async def fake_call(self, method, path, params=None, **kwargs):
        captured["path"] = path
        captured["params"] = params or {}
        return {"code": 0, "data": {"volume_list": []}}

    monkeypatch.setattr(FanqieClient, "_call", fake_call)
    client = FanqieClient(ClientConfig(platform="fanqie", mode=ClientMode.API, cookie="s=x"))

    await client.get_book_volumes("book-1")

    assert captured["path"] == "/api/author/volume/volume_list/v1"
    assert captured["params"]["book_id"] == "book-1"


def test_earnings_endpoint_is_still_captured_as_unverified():
    """收益接口仍未抓包——不得凭猜测补上路径。

    本次抓包尝试猜测收益页 URL（/main/writer/income-analysis）返回 404，
    正是「不猜路径」这条规矩的实证。故 apis.py 中**不应**存在收益端点常量。
    """
    from app.services.platforms.fanqie import apis

    earning_like = [
        name
        for name in dir(apis)
        if name.isupper() and "EARNING" in name or name.isupper() and "INCOME" in name
    ]
    assert earning_like == [], f"收益端点尚未抓包，不应存在常量：{earning_like}"


def test_fanqie_routes_expose_e_group_endpoints():
    """三条已抓包端点必须真实挂载，收益保持占位。"""
    from app.services.platforms.fanqie.routes import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/my/profile" in paths
    assert "/book/{book_id}/volumes" in paths
    assert "/book/{book_id}/chapters" in paths
    assert "/earnings" in paths  # 仍是 not_captured 占位
