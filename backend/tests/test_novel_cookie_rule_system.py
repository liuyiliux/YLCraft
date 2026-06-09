from datetime import datetime, timedelta
import json

from sqlmodel import Session, create_engine, select

from app.db.models.book_source import BookSource
from app.db.models.book_source_cookie import BookSourceCookie
from app.services.novel.book_source_manager import BookSourceManager
from app.services.novel.cookie_manager import BookSourceCookieManager, count_cookies
from app.services.novel.migration_manager import BookSourceMigrationManager
from app.services.novel.rule_converter import (
    convert_legado_to_ylcraft,
    convert_ylcraft_to_legado,
    parse_mixed_book_source_json,
)
from app.services.novel.rule_parser import RuleParser


def make_session():
    engine = create_engine("sqlite:///:memory:")
    BookSource.__table__.create(engine)
    BookSourceCookie.__table__.create(engine)
    return Session(engine)


def create_source(session: Session, source_id: str = "source1") -> BookSource:
    source = BookSource(
        id=source_id,
        book_source_name="Test Source",
        book_source_url="https://m.example.com",
        search_url="/search?kw={{key}}",
        rule_search=json.dumps(
            {
                "bookList": ".book-item",
                "name": "h3@text",
                "bookUrl": "a@href",
            }
        ),
    )
    session.add(source)
    session.commit()
    return source


def test_cookie_manager_matches_exact_wildcard_and_default_domains():
    session = make_session()
    create_source(session)
    manager = BookSourceCookieManager(session)

    manager.create_cookie(
        {
            "book_source_id": "source1",
            "domain": "m.example.com",
            "cookie_content": "session=exact; theme=dark",
        }
    )
    manager.create_cookie(
        {
            "book_source_id": "source1",
            "domain": ".example.com",
            "cookie_content": "#HttpOnly_.example.com\tTRUE\t/\tFALSE\t1893456000\twild\t1",
        }
    )
    manager.create_cookie(
        {
            "book_source_id": "source1",
            "domain": "*",
            "cookie_content": "fallback=yes",
        }
    )

    assert manager.get_cookie_for_url("https://m.example.com/search", "source1") == "session=exact; theme=dark"
    assert manager.get_cookie_for_url("https://www.example.com/book", "source1") == "wild=1"
    assert manager.get_cookie_for_url("https://other.test/book", "source1") == "fallback=yes"


def test_cookie_manager_ignores_expired_cookie_records():
    session = make_session()
    create_source(session)
    manager = BookSourceCookieManager(session)

    manager.create_cookie(
        {
            "book_source_id": "source1",
            "domain": "m.example.com",
            "cookie_content": "expired=yes",
            "expires_at": datetime.now() - timedelta(days=1),
        }
    )
    manager.create_cookie(
        {
            "book_source_id": "source1",
            "domain": "*",
            "cookie_content": "fallback=yes",
        }
    )

    assert manager.get_cookie_for_url("https://m.example.com/search", "source1") == "fallback=yes"
    assert count_cookies("a=1; b=2") == 2


def test_rule_parser_extracts_search_items_and_content():
    html = """
    <html>
      <body>
        <div class="book-item">
          <a href="/book/1"><h3> Example Book </h3></a>
          <span class="author">Alice</span>
        </div>
        <article id="content">
          <p>Chapter text</p><div class="ad">ad text</div><script>bad()</script>
        </article>
      </body>
    </html>
    """
    rule = {
        "search": {
            "items": {
                "selector": ".book-item",
                "fields": {
                    "title": {"selector": "h3", "type": "text"},
                    "author": {"selector": ".author", "type": "text"},
                    "url": {
                        "selector": "a",
                        "type": "attr",
                        "attr": "href",
                        "prefix": "https://m.example.com",
                    },
                },
            }
        },
        "content": {
            "selector": "#content",
            "remove": [".ad"],
            "text_only": True,
            "join_with": "\n",
        },
    }

    parser = RuleParser(rule)
    search_result = parser.parse_search(html)
    assert search_result["parse_success"] is True
    assert search_result["items"][0]["title"] == "Example Book"
    assert search_result["items"][0]["url"] == "https://m.example.com/book/1"

    content_result = parser.parse_content(html)
    assert content_result["parse_success"] is True
    assert "Chapter text" in content_result["content"]
    assert "ad text" not in content_result["content"]


def test_rule_converter_maps_legado_search_toc_and_content_rules():
    converted = convert_legado_to_ylcraft(
        {
            "bookSourceName": "Example",
            "bookSourceUrl": "https://m.example.com",
            "searchUrl": "/search?kw={{key}}&page={{page}}",
            "ruleSearch": {
                "bookList": "class.book-list@tag.div",
                "name": "tag.h3@text",
                "bookUrl": "tag.a@href",
            },
            "ruleToc": {
                "chapterList": "id.list@tag.li",
                "chapterName": "tag.a@text",
                "chapterUrl": "tag.a@href",
            },
            "ruleContent": {
                "content": "id.content",
                "removeContent": "class.ad",
            },
        }
    )

    assert converted["name"] == "Example"
    assert converted["search"]["url"] == "/search?kw={{keyword}}&page={{page}}"
    assert converted["search"]["items"]["selector"] == ".book-list div"
    assert converted["search"]["items"]["fields"]["url"]["type"] == "attr"
    assert converted["search"]["items"]["fields"]["url"]["attr"] == "href"
    assert converted["toc"]["items"]["selector"] == "#list li"
    assert converted["content"]["selector"] == "#content"
    assert converted["content"]["remove"] == [".ad"]


def test_rule_converter_round_trips_ylcraft_to_legado_shape():
    ylcraft = {
        "version": "1.0",
        "name": "Y Source",
        "base_url": "https://m.example.com",
        "search": {
            "url": "/search?kw={{keyword}}",
            "items": {
                "selector": ".book-item",
                "fields": {
                    "title": {"selector": "h3", "type": "text"},
                    "url": {"selector": "a", "type": "attr", "attr": "href"},
                },
            },
        },
        "toc": {
            "items": {
                "selector": ".chapter",
                "fields": {
                    "title": {"selector": "a", "type": "text"},
                    "url": {"selector": "a", "type": "attr", "attr": "href"},
                },
            }
        },
        "content": {"selector": "#content", "remove": [".ad"]},
    }

    legado = convert_ylcraft_to_legado(ylcraft)
    assert legado["bookSourceName"] == "Y Source"
    assert legado["bookSourceUrl"] == "https://m.example.com"
    assert legado["ruleSearch"]["bookList"] == ".book-item"
    assert legado["ruleSearch"]["name"] == "h3@text"
    assert legado["ruleSearch"]["bookUrl"] == "a@href"
    assert legado["ruleToc"]["chapterList"] == ".chapter"
    assert legado["ruleContent"]["removeContent"] == ".ad"


def test_parse_mixed_book_source_json_converts_legado_and_ylcraft_inputs():
    payload = [
        {
            "bookSourceName": "Legado Source",
            "bookSourceUrl": "https://legado.example.com",
            "searchUrl": "/search?kw={{key}}",
            "ruleSearch": {
                "bookList": ".book",
                "name": "h3@text",
                "bookUrl": "a@href",
            },
        },
        {
            "version": "1.0",
            "name": "YLCraft Source",
            "base_url": "https://ylcraft.example.com",
            "search": {
                "url": "/search?kw={{keyword}}",
                "items": {
                    "selector": ".book",
                    "fields": {
                        "title": {"selector": "h3", "type": "text"},
                        "url": {"selector": "a", "type": "attr", "attr": "href"},
                    },
                },
            },
        },
    ]

    parsed = parse_mixed_book_source_json(json.dumps(payload))
    assert len(parsed) == 2
    assert parsed[0]["ruleFormat"] == "ylcraft"
    assert parsed[0]["originalFormat"] == "legado"
    assert parsed[0]["ylcraftRule"]["name"] == "Legado Source"
    assert parsed[1]["bookSourceName"] == "YLCraft Source"
    assert parsed[1]["ruleSearch"]["bookList"] == ".book"
    assert parsed[1]["originalFormat"] == "ylcraft"


def test_book_source_manager_imports_ylcraft_and_exports_both_formats():
    session = make_session()
    manager = BookSourceManager(session)
    ylcraft = {
        "version": "1.0",
        "name": "Imported YLCraft",
        "base_url": "https://imported.example.com",
        "search": {
            "url": "/search?kw={{keyword}}",
            "items": {
                "selector": ".book",
                "fields": {
                    "title": {"selector": "h3", "type": "text"},
                    "url": {"selector": "a", "type": "attr", "attr": "href"},
                },
            },
        },
    }

    result = manager.import_sources(json.dumps(ylcraft))
    assert result["success"] is True

    db_source = session.exec(select(BookSource)).one()
    assert db_source.rule_format == "ylcraft"
    assert db_source.rule_version == "1.0"
    assert json.loads(db_source.ylcraft_rule)["name"] == "Imported YLCraft"
    assert json.loads(db_source.original_source)["base_url"] == "https://imported.example.com"

    exported_legado = json.loads(manager.export_sources("legado"))
    assert exported_legado[0]["bookSourceName"] == "Imported YLCraft"
    assert exported_legado[0]["ruleSearch"]["bookList"] == ".book"

    exported_ylcraft = json.loads(manager.export_sources("ylcraft"))
    assert exported_ylcraft[0]["version"] == "1.0"
    assert exported_ylcraft[0]["name"] == "Imported YLCraft"


def test_migration_manager_backfills_ylcraft_metadata_for_existing_sources():
    session = make_session()
    create_source(session)

    result = BookSourceMigrationManager(session).migrate_existing_sources()
    assert result["success"] is True
    assert result["migrated"] == 1

    db_source = session.get(BookSource, "source1")
    assert db_source.rule_format == "ylcraft"
    assert db_source.rule_version == "1.0"
    ylcraft_rule = json.loads(db_source.ylcraft_rule)
    assert ylcraft_rule["name"] == "Test Source"
    assert json.loads(db_source.original_source)["bookSourceName"] == "Test Source"
    assert "migrated_at" in json.loads(db_source.migration_log)
