"""Agent tools for WeChat MP account/article acquisition."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.db.database import get_async_session
from app.db.models.platform_connection import PlatformConnection, PlatformType
from app.services.agent.registry import register_tool


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value


def _connection_summary(conn: PlatformConnection) -> dict[str, Any]:
    return {
        "id": conn.id,
        "name": conn.name,
        "status": str(conn.status.value if hasattr(conn.status, "value") else conn.status),
        "auth_type": str(conn.auth_type.value if hasattr(conn.auth_type, "value") else conn.auth_type),
        "account_id": conn.account_id or "",
        "account_name": conn.account_name or "",
        "has_credentials": bool(conn.credentials),
        "has_cookie_content": bool(conn.cookie_content),
        "last_used": conn.last_used.isoformat() if conn.last_used else "",
        "last_tested": conn.last_tested.isoformat() if conn.last_tested else "",
        "error_message": conn.error_message or "",
    }


@register_tool(
    name="list_wechat_mp_connections",
    description="List configured WeChat MP platform connections without exposing cookies or credentials.",
    category="wechat_mp",
    examples=["列出公众号连接", "我有哪些微信公众号 Cookie 配置", "检查公众号连接状态"],
    input_schema_note="include_inactive controls whether expired/failed connections are included. No external request is made.",
    output_schema_note="Returns success, total, connections. Credentials and cookie contents are never returned.",
    risk_level="read",
    output_type="wechat_mp_connection_list",
)
async def list_wechat_mp_connections(include_inactive: bool = True, limit: int = 50) -> dict[str, Any]:
    async with get_async_session() as session:
        result = await session.execute(
            select(PlatformConnection)
            .where(PlatformConnection.platform == PlatformType.WECHAT_MP)
            .order_by(PlatformConnection.updated_at.desc())
            .limit(max(1, min(int(limit or 50), 100)))
        )
        connections = [_connection_summary(conn) for conn in result.scalars().all()]
    if not include_inactive:
        connections = [item for item in connections if item["status"] == "active"]
    return {"success": True, "total": len(connections), "connections": connections}


@register_tool(
    name="search_wechat_mp_accounts",
    description="Search public accounts through a configured WeChat MP connection.",
    category="wechat_mp",
    examples=["用这个连接搜索小华同学ai公众号", "查找公众号 fake_id", "搜索开源先锋"],
    input_schema_note="conn_id and keyword are required. Requires a valid logged-in WeChat MP connection and visits WeChat MP endpoints.",
    output_schema_note="Returns success, total, accounts with fake_id/nickname/alias/avatar/signature summaries, or error.",
    risk_level="external",
    output_type="wechat_mp_account_search",
)
async def search_wechat_mp_accounts(conn_id: str, keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    if not (conn_id or "").strip():
        raise ValueError("conn_id cannot be empty")
    if not (keyword or "").strip():
        raise ValueError("keyword cannot be empty")
    from app.api.v1.wechat_mp import search_accounts

    try:
        response = await search_accounts(
            conn_id=conn_id.strip(),
            keyword=keyword.strip(),
            page=max(1, int(page or 1)),
            page_size=max(1, min(int(page_size or 20), 50)),
        )
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    data = _to_plain(response)
    return {"success": True, "total": data.get("total", 0), "accounts": data.get("list", [])}


@register_tool(
    name="list_wechat_mp_articles",
    description="List recent articles of a WeChat MP account by fake_id through a configured connection.",
    category="wechat_mp",
    examples=["列出这个公众号最近 5 篇文章", "用 fake_id 获取文章列表", "从第 10 条开始拉公众号文章"],
    input_schema_note="conn_id and fake_id are required. count is capped by the platform/API to 5. Visits WeChat MP endpoints.",
    output_schema_note="Returns success, total_count, articles with title/link/cover/digest/time/source fields, plus error/error_code when provided.",
    risk_level="external",
    output_type="wechat_mp_article_list",
)
async def list_wechat_mp_articles(conn_id: str, fake_id: str, begin: int = 0, count: int = 5) -> dict[str, Any]:
    if not (conn_id or "").strip():
        raise ValueError("conn_id cannot be empty")
    if not (fake_id or "").strip():
        raise ValueError("fake_id cannot be empty")
    from app.api.v1.wechat_mp import get_articles

    response = await get_articles(
        conn_id=conn_id.strip(),
        fake_id=fake_id.strip(),
        begin=max(0, int(begin or 0)),
        count=max(1, min(int(count or 5), 5)),
    )
    data = _to_plain(response)
    return {
        "success": not bool(data.get("error")),
        "total_count": data.get("total_count", 0),
        "articles": data.get("list", []),
        "error": data.get("error", ""),
        "error_code": data.get("error_code", 0),
    }


@register_tool(
    name="download_wechat_mp_article",
    description="Download a single WeChat MP article to a local Markdown/HTML/EPUB/PDF file through a configured connection.",
    category="wechat_mp",
    examples=["下载这篇公众号文章为 Markdown", "把文章下载到本地素材目录", "确认后抓取这篇公众号文章"],
    input_schema_note="conn_id and article_url are required. format can be md/html/epub/pdf. This visits WeChat and writes a local file.",
    output_schema_note="Returns success, file_path, file_size, format, title, author, download_dir, skipped, record_id, or error.",
    risk_level="external",
    output_type="wechat_mp_download_result",
    cost_hint="This may access WeChat MP, download article images/content, and write local files. Import to Asset Hub can be done after download.",
)
async def download_wechat_mp_article(
    conn_id: str,
    article_url: str,
    article_title: str = "",
    format: str = "md",
    download_dir: str = "",
) -> dict[str, Any]:
    if not (conn_id or "").strip():
        raise ValueError("conn_id cannot be empty")
    if not (article_url or "").strip():
        raise ValueError("article_url cannot be empty")
    from app.api.v1.wechat_mp import DownloadSingleRequest, download_single_article

    try:
        response = await download_single_article(
            DownloadSingleRequest(
                conn_id=conn_id.strip(),
                article_url=article_url.strip(),
                article_title=(article_title or "").strip(),
                format=(format or "md").strip(),
                download_dir=(download_dir or "").strip(),
            )
        )
    except HTTPException as exc:
        return {"success": False, "status_code": exc.status_code, "error": str(exc.detail)}
    return _to_plain(response)
