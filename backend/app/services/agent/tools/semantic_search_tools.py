"""Agent tools for semantic asset search and embedding inspection."""

from __future__ import annotations

from typing import Any

from app.db.database import get_async_session
from app.services.agent.registry import register_tool
from app.services.embedding.service import EmbeddingService


def _compact_results(results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in results[:limit]:
        compacted.append(
            {
                "asset_id": item.get("asset_id") or item.get("id") or "",
                "title": item.get("title") or item.get("name") or "",
                "asset_type": item.get("asset_type") or item.get("type") or "",
                "similarity": item.get("similarity"),
                "score": item.get("score") or item.get("combined_score"),
                "thumbnail_url": item.get("thumbnail_url") or "",
                "file_path": item.get("file_path") or "",
                "metadata": item.get("metadata") or {},
            }
        )
    return compacted


async def _embedding_service():
    async with get_async_session() as session:
        from sqlalchemy import String, cast, select
        from app.db.models.ai_connector import AIConnector

        result = await session.execute(
            select(AIConnector)
            .where(cast(AIConnector.provider_type, String) == "embedding")
            .where(AIConnector.is_active == True)
            .order_by(AIConnector.priority)
            .limit(1)
        )
        connector = result.scalar_one_or_none()
        yield EmbeddingService(session, provider_name=connector.name if connector else None)


@register_tool(
    name="semantic_search_assets",
    description="Search Asset Hub with semantic text/vector plus optional text/tag filters.",
    category="semantic_search",
    examples=["找和赛博导演立绘相似的参考素材", "语义搜索冷色调城市背景", "查找适合第二章分镜的素材"],
    input_schema_note="query is required. top_k max 50. vector_weight/text_weight tune hybrid ranking. tag_filters and asset_type are optional.",
    output_schema_note="Returns success, query, total, results. Results include asset_id/title/type/similarity/score/thumbnail/file_path/metadata summary.",
    risk_level="costly",
    output_type="semantic_search_results",
    cost_hint="May call an embedding model to encode the query, depending on configured embedding provider.",
)
async def semantic_search_assets(
    query: str,
    top_k: int = 10,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    min_similarity: float = 0.0,
    asset_type: str = "",
    tag_filters: list[str] | None = None,
) -> dict[str, Any]:
    if not (query or "").strip():
        raise ValueError("query cannot be empty")
    safe_top_k = max(1, min(int(top_k or 10), 50))
    async for service in _embedding_service():
        results = await service.hybrid_search(
            query_text=query.strip(),
            top_k=safe_top_k,
            vector_weight=max(0.0, min(float(vector_weight or 0.7), 1.0)),
            text_weight=max(0.0, min(float(text_weight or 0.3), 1.0)),
            min_similarity=max(0.0, min(float(min_similarity or 0.0), 1.0)),
            tag_filters=tag_filters or None,
            asset_type_filter=asset_type or None,
        )
        return {
            "success": True,
            "query": query.strip(),
            "total": len(results),
            "results": _compact_results(results, safe_top_k),
        }
    return {"success": False, "query": query, "total": 0, "results": [], "error": "embedding service unavailable"}


@register_tool(
    name="find_similar_assets",
    description="Find assets similar to an existing Asset Hub node based on stored embeddings.",
    category="semantic_search",
    examples=["找这张角色立绘的相似图", "给这个背景图找同风格参考", "查找相似素材用于一致性参考"],
    input_schema_note="asset_id is required. The asset must already have embeddings. top_k max 50.",
    output_schema_note="Returns success, query_asset_id, total, results with asset_id/title/type/similarity/thumbnail/file_path/metadata.",
    risk_level="read",
    output_type="semantic_similar_assets",
)
async def find_similar_assets(asset_id: str, top_k: int = 10) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    safe_top_k = max(1, min(int(top_k or 10), 50))
    async for service in _embedding_service():
        info = await service.get_embedding_info(asset_id.strip())
        if not info.get("embeddings"):
            return {"success": False, "query_asset_id": asset_id.strip(), "error": "asset has no embeddings", "results": []}

        from sqlalchemy import select
        from app.db.models.asset_hub import AssetEmbedding

        result = await service.session.execute(
            select(AssetEmbedding).where(AssetEmbedding.asset_node_id == asset_id.strip()).limit(1)
        )
        embedding_record = result.scalar_one_or_none()
        if not embedding_record:
            return {"success": False, "query_asset_id": asset_id.strip(), "error": "embedding record not found", "results": []}
        results = await service.search_by_embedding(
            query_vector=embedding_record.embedding,
            top_k=safe_top_k + 1,
            min_similarity=0.0,
            asset_type_filter=None,
        )
        filtered = [item for item in results if item.get("asset_id") != asset_id.strip()][:safe_top_k]
        return {
            "success": True,
            "query_asset_id": asset_id.strip(),
            "total": len(filtered),
            "results": _compact_results(filtered, safe_top_k),
        }
    return {"success": False, "query_asset_id": asset_id, "total": 0, "results": [], "error": "embedding service unavailable"}


@register_tool(
    name="get_asset_embedding_info",
    description="Inspect embedding records for one Asset Hub node without returning raw vectors.",
    category="semantic_search",
    examples=["看看这个素材有没有向量", "检查这张图能不能做相似搜索", "读取素材 embedding 信息"],
    input_schema_note="asset_id is required. Raw vector values are omitted from output.",
    output_schema_note="Returns success, asset_id, embedding_count, embeddings metadata such as model/type/dimension/created_at.",
    risk_level="read",
    output_type="semantic_embedding_info",
)
async def get_asset_embedding_info(asset_id: str) -> dict[str, Any]:
    if not (asset_id or "").strip():
        raise ValueError("asset_id cannot be empty")
    async for service in _embedding_service():
        info = await service.get_embedding_info(asset_id.strip())
        embeddings = []
        for item in info.get("embeddings") or []:
            embeddings.append(
                {
                    "id": item.get("id"),
                    "model": item.get("model"),
                    "embedding_type": item.get("embedding_type"),
                    "dimension": item.get("dimension"),
                    "created_at": item.get("created_at"),
                }
            )
        return {
            "success": bool(embeddings),
            "asset_id": asset_id.strip(),
            "embedding_count": len(embeddings),
            "embeddings": embeddings,
        }
    return {"success": False, "asset_id": asset_id, "embedding_count": 0, "embeddings": []}
