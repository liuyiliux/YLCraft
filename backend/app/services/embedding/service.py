"""
YLCraft — Embedding 服务

实现文本和图像的向量嵌入，支持：
- 文本嵌入（sentence-transformers）
- 图像嵌入（CLIP）
- 外部 API 嵌入（Qwen、BGE-M3、OpenAI）
- 批量向量化处理
- 向量相似度搜索
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import List, Optional, Dict, Any, Union
from uuid import uuid4
import numpy as np
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

logger = logging.getLogger("ylcraft.embedding_service")


class EmbeddingService:
    """向量嵌入服务"""

    # 嵌入模型配置（本地模型）
    TEXT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
    IMAGE_MODEL = "clip-ViT-B-32"
    TEXT_DIM = 384  # MiniLM-L12-v2 输出维度
    IMAGE_DIM = 512  # CLIP ViT-B-32 输出维度

    def __init__(self, session: AsyncSession, provider_name: Optional[str] = None):
        self.session = session
        self._text_model = None
        self._image_model = None
        self._provider_name = provider_name
        self._provider_config: Optional[Dict[str, Any]] = None  # 延迟加载

    async def _load_provider_config(self) -> Optional[Dict[str, Any]]:
        """从数据库加载嵌入 provider 配置（优先）或配置文件（备用）"""
        # 如果已经加载过，直接返回
        if self._provider_config is not None:
            return self._provider_config

        # 优先从数据库加载（用户在前端配置的）
        if self._provider_name:
            try:
                from app.db.models.ai_connector import AIConnector, AIProviderType

                # 查找指定 provider
                result = await self.session.execute(
                    select(AIConnector)
                    .where(AIConnector.provider == self._provider_name)
                    .where(AIConnector.provider_type == AIProviderType.embedding)
                    .where(AIConnector.is_active == True)
                )
                conn = result.scalar_one_or_none()

                if conn:
                    self._provider_config = {
                        "provider": conn.provider,
                        "model": conn.default_model,
                        "api_base": conn.base_url,
                        "api_key": conn.api_key,
                        "dimension": conn.embedding_dimension,
                        "embedding_type": conn.embedding_type,
                        "normalize": conn.normalize_embeddings,
                    }
                    logger.info(f"[EmbeddingService] Loaded config from database for {self._provider_name}")
                    return self._provider_config

            except Exception as e:
                logger.warning(f"[EmbeddingService] Failed to load from database: {e}")

        # 备用：从配置文件加载
        return self._load_config_from_yaml()

    def _load_config_from_yaml(self) -> Dict[str, Any]:
        """从 yaml 配置文件加载（备用方案）"""
        try:
            import yaml
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "config", "providers.yaml"
            )

            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    providers = config.get("providers", {})

                    # 获取默认 provider
                    default_name = config.get("defaults", {}).get("embedding")

                    # 查找配置
                    for name, provider in providers.items():
                        if provider.get("media_type") == "embedding" and (
                            name == self._provider_name or
                            (self._provider_name is None and name == default_name)
                        ):
                            self._provider_config = provider
                            return provider

            logger.warning(f"[EmbeddingService] No embedding provider config found")
            return {}
        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to load yaml config: {e}")
            return {}

    # -------------------------------------------------------------------------
    # 模型加载（延迟加载，按需初始化）
    # -------------------------------------------------------------------------

    async def _get_text_model(self):
        """获取文本嵌入模型（延迟加载）"""
        if self._text_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._text_model = SentenceTransformer(self.TEXT_MODEL)
                logger.info(f"[EmbeddingService] Loaded text model: {self.TEXT_MODEL}")
            except ImportError:
                logger.warning("[EmbeddingService] sentence-transformers not installed")
                return None
            except Exception as e:
                logger.error(f"[EmbeddingService] Failed to load text model: {e}")
                return None
        return self._text_model

    async def _get_image_model(self):
        """获取图像嵌入模型（延迟加载）"""
        if self._image_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._image_model = SentenceTransformer(self.IMAGE_MODEL)
                logger.info(f"[EmbeddingService] Loaded image model: {self.IMAGE_MODEL}")
            except ImportError:
                logger.warning("[EmbeddingService] sentence-transformers not installed")
                return None
            except Exception as e:
                logger.error(f"[EmbeddingService] Failed to load image model: {e}")
                return None
        return self._image_model

    # -------------------------------------------------------------------------
    # 外部 API 嵌入（优先使用配置的 provider）
    # -------------------------------------------------------------------------

    async def embed_text_via_api(self, text: str) -> Optional[List[float]]:
        """通过外部 API 嵌入文本"""
        # 异步加载配置
        config = await self._load_provider_config()
        if not config:
            return await self.embed_text_local(text)

        provider = config.get("provider")
        api_base = config.get("api_base")
        api_key = config.get("api_key", "")

        # 解析环境变量
        if api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            api_key = os.getenv(env_var, "")

        if not api_base or not api_key:
            logger.warning("[EmbeddingService] API config not set, falling back to local model")
            return await self.embed_text_local(text)

        try:
            if provider == "qwen":
                return await self._call_qwen_api(text, api_base, api_key, config.get("model"))
            elif provider == "openai":
                return await self._call_openai_api(text, api_base, api_key, config.get("model"))
            elif provider == "huggingface":
                return await self._call_huggingface_api(text, api_base, api_key, config.get("model"))
            else:
                logger.warning(f"[EmbeddingService] Unknown provider: {provider}")
                return await self.embed_text_local(text)
        except Exception as e:
            logger.error(f"[EmbeddingService] API call failed: {e}, falling back to local")
            return await self.embed_text_local(text)

    async def _call_qwen_api(self, text: str, api_base: str, api_key: str, model: str = "Qwen/Qwen3-Embedding-8B") -> Optional[List[float]]:
        """调用 Qwen 嵌入 API"""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                api_base,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text,
                    "model": model or "Qwen/Qwen3-Embedding-8B",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("output", {}).get("embedding")

    async def _call_openai_api(self, text: str, api_base: str, api_key: str, model: str = "text-embedding-3-large") -> Optional[List[float]]:
        """调用 OpenAI 嵌入 API"""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text,
                    "model": model or "text-embedding-3-large",
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [{}])[0].get("embedding")

    async def _call_huggingface_api(self, text: str, api_base: str, api_key: str, model: str = "BAAI/bge-m3") -> Optional[List[float]]:
        """调用 Hugging Face Inference API"""
        # api_base 包含完整 URL，需要提取 base
        url = f"{api_base}/{model}" if "inference" not in api_base else f"{api_base}/{model}"

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"inputs": text},
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                return data[0]
            return None

    # -------------------------------------------------------------------------
    # 文本嵌入
    # -------------------------------------------------------------------------

    async def embed_text(self, text: str) -> Optional[List[float]]:
        """将单条文本转换为向量（自动选择本地或 API）"""
        # 如果配置了外部 provider，优先使用 API
        config = await self._load_provider_config()
        if config and self._provider_name:
            return await self.embed_text_via_api(text)
        return await self.embed_text_local(text)

    async def embed_text_local(self, text: str) -> Optional[List[float]]:
        """使用本地模型将单条文本转换为向量"""
        model = await self._get_text_model()
        if not model:
            return None

        try:
            embedding = model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to embed text: {e}")
            return None

    async def embed_texts(self, texts: List[str]) -> List[Optional[List[float]]]:
        """批量将文本转换为向量（自动选择本地或 API）"""
        config = await self._load_provider_config()
        if config and self._provider_name:
            # API 模式：逐个调用
            results = []
            for text in texts:
                result = await self.embed_text_via_api(text)
                results.append(result)
            return results
        return await self.embed_texts_local(texts)

    async def embed_texts_local(self, texts: List[str]) -> List[Optional[List[float]]]:
        """使用本地模型批量将文本转换为向量"""
        model = await self._get_text_model()
        if not model:
            return [None] * len(texts)

        try:
            embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to embed texts: {e}")
            return [None] * len(texts)

    # -------------------------------------------------------------------------
    # 图像嵌入
    # -------------------------------------------------------------------------

    async def embed_image(self, image_path: str) -> Optional[List[float]]:
        """将单张图片转换为向量"""
        model = await self._get_image_model()
        if not model:
            return None

        try:
            from PIL import Image
            import os

            # 处理 URL 或本地路径
            if image_path.startswith("http://") or image_path.startswith("https://"):
                import httpx
                response = httpx.get(image_path, timeout=10)
                from io import BytesIO
                image = Image.open(BytesIO(response.content)).convert("RGB")
            elif os.path.exists(image_path):
                image = Image.open(image_path).convert("RGB")
            else:
                logger.warning(f"[EmbeddingService] Image not found: {image_path}")
                return None

            embedding = model.encode(image)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to embed image: {e}")
            return None

    async def embed_images(self, image_paths: List[str]) -> List[Optional[List[float]]]:
        """批量将图片转换为向量"""
        model = await self._get_image_model()
        if not model:
            return [None] * len(image_paths)

        try:
            from PIL import Image
            import os
            from io import BytesIO
            import httpx

            images = []
            for path in image_paths:
                try:
                    if path.startswith("http://") or path.startswith("https://"):
                        response = httpx.get(path, timeout=10)
                        img = Image.open(BytesIO(response.content)).convert("RGB")
                    elif os.path.exists(path):
                        img = Image.open(path).convert("RGB")
                    else:
                        images.append(None)
                        continue
                    images.append(img)
                except Exception:
                    images.append(None)

            # 过滤掉无效图片
            valid_images = [img for img in images if img is not None]

            if not valid_images:
                return [None] * len(image_paths)

            embeddings = model.encode(valid_images, normalize_embeddings=True, show_progress_bar=True)

            result = []
            idx = 0
            for img in images:
                if img is None:
                    result.append(None)
                else:
                    result.append(embeddings[idx].tolist())
                    idx += 1

            return result
        except Exception as e:
            logger.error(f"[EmbeddingService] Failed to embed images: {e}")
            return [None] * len(image_paths)

    # -------------------------------------------------------------------------
    # 向量存储
    # -------------------------------------------------------------------------

    async def store_text_embedding(
        self,
        asset_id: str,
        text: str,
        embedding_type: str = "text",
    ) -> Optional[Dict[str, Any]]:
        """存储资产的文本嵌入向量"""
        from app.db.models.asset_hub import AssetEmbedding

        embedding = await self.embed_text(text)
        if not embedding:
            return None

        # 检查是否已存在
        result = await self.session.execute(
            select(AssetEmbedding)
            .where(AssetEmbedding.asset_node_id == asset_id)
            .where(AssetEmbedding.embedding_model == self.TEXT_MODEL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.embedding = embedding
            self.session.add(existing)
        else:
            embedding_record = AssetEmbedding(
                id=str(uuid4()),
                asset_node_id=asset_id,
                embedding=embedding,
                embedding_model=self.TEXT_MODEL,
            )
            self.session.add(embedding_record)

        # 更新资产的全文字段
        await self.session.execute(
            text("""
                UPDATE asset_nodes
                SET fulltext_vector = to_tsvector('simple', :text)
                WHERE id = :asset_id
            """),
            {"text": text, "asset_id": asset_id}
        )

        await self.session.commit()
        return {"asset_id": asset_id, "embedding_type": embedding_type, "dimension": len(embedding)}

    async def store_image_embedding(
        self,
        asset_id: str,
        image_path: str,
    ) -> Optional[Dict[str, Any]]:
        """存储资产的图像嵌入向量"""
        from app.db.models.asset_hub import AssetEmbedding

        embedding = await self.embed_image(image_path)
        if not embedding:
            return None

        # 检查是否已存在
        result = await self.session.execute(
            select(AssetEmbedding)
            .where(AssetEmbedding.asset_node_id == asset_id)
            .where(AssetEmbedding.embedding_model == self.IMAGE_MODEL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.embedding = embedding
            self.session.add(existing)
        else:
            embedding_record = AssetEmbedding(
                id=str(uuid4()),
                asset_node_id=asset_id,
                embedding=embedding,
                embedding_model=self.IMAGE_MODEL,
            )
            self.session.add(embedding_record)

        await self.session.commit()
        return {"asset_id": asset_id, "embedding_type": "image", "dimension": len(embedding)}

    # -------------------------------------------------------------------------
    # 向量搜索
    # -------------------------------------------------------------------------

    async def search_by_text(
        self,
        query_text: str,
        top_k: int = 10,
        min_similarity: float = 0.0,
        asset_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """文本相似度搜索（返回最相似的资产）"""
        embedding = await self.embed_text(query_text)
        if not embedding:
            return []

        return await self._vector_search(
            query_vector=embedding,
            top_k=top_k,
            min_similarity=min_similarity,
            asset_type_filter=asset_type_filter,
        )

    async def search_by_image(
        self,
        image_path: str,
        top_k: int = 10,
        min_similarity: float = 0.0,
        asset_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """图像相似度搜索"""
        embedding = await self.embed_image(image_path)
        if not embedding:
            return []

        return await self._vector_search(
            query_vector=embedding,
            top_k=top_k,
            min_similarity=min_similarity,
            asset_type_filter=asset_type_filter,
            embedding_model=self.IMAGE_MODEL,
        )

    async def search_by_embedding(
        self,
        query_vector: List[float],
        top_k: int = 10,
        min_similarity: float = 0.0,
        asset_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """直接使用向量进行搜索"""
        return await self._vector_search(
            query_vector=query_vector,
            top_k=top_k,
            min_similarity=min_similarity,
            asset_type_filter=asset_type_filter,
        )

    async def _vector_search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        min_similarity: float = 0.0,
        asset_type_filter: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """执行向量相似度搜索"""
        from app.db.models.asset_hub import AssetEmbedding, AssetNode

        # 构建查询
        model_filter = embedding_model or self.TEXT_MODEL

        # PostgreSQL 向量相似度搜索（余弦相似度）
        query = text("""
            SELECT
                ae.asset_node_id,
                1 - (ae.embedding <=> :query_vector::vector) AS similarity,
                an.name,
                an.asset_type,
                an.thumbnail_url,
                an.metadata_json
            FROM asset_embeddings ae
            JOIN asset_nodes an ON ae.asset_node_id = an.id
            WHERE ae.embedding_model = :model
            AND an.asset_type = COALESCE(:asset_type, an.asset_type)
            ORDER BY ae.embedding <=> :query_vector::vector
            LIMIT :top_k
        """)

        result = await self.session.execute(
            query,
            {
                "query_vector": str(query_vector),
                "model": model_filter,
                "asset_type": asset_type_filter,
                "top_k": top_k,
            }
        )

        search_results = []
        for row in result.all():
            similarity = float(row.similarity)
            if similarity >= min_similarity:
                search_results.append({
                    "asset_id": str(row.asset_node_id),
                    "similarity": similarity,
                    "name": row.name,
                    "asset_type": row.asset_type,
                    "thumbnail_url": row.thumbnail_url,
                })

        return search_results

    # -------------------------------------------------------------------------
    # 混合搜索
    # -------------------------------------------------------------------------

    async def hybrid_search(
        self,
        query_text: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        min_similarity: float = 0.0,
        tag_filters: Optional[List[str]] = None,
        asset_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合搜索：向量 + 全文 + 标签

        一次查询完成所有搜索，综合排序。
        """
        from app.db.models.asset_hub import AssetNode, AssetEmbedding, AssetTagLink, Tag

        # 获取文本向量
        embedding = await self.embed_text(query_text)
        query_vector_str = str(embedding) if embedding else None

        # 构建混合搜索 SQL
        sql = """
            WITH vector_scores AS (
                SELECT
                    ae.asset_node_id,
                    1 - (ae.embedding <=> :query_vector::vector) AS vector_score
                FROM asset_embeddings ae
                WHERE ae.embedding_model = :model
                AND :query_vector IS NOT NULL
            ),
            text_scores AS (
                SELECT
                    id AS asset_node_id,
                    COALESCE(ts_rank(fulltext_vector, plainto_tsquery('simple', :query_text)), 0) AS text_score
                FROM asset_nodes
                WHERE fulltext_vector @@ plainto_tsquery('simple', :query_text)
            ),
            tag_scores AS (
                SELECT
                    atl.asset_node_id,
                    COUNT(*) AS tag_match_count
                FROM asset_tag_links atl
                JOIN tags t ON atl.tag_id = t.id
                WHERE t.name = ANY(:tag_filters)
                GROUP BY atl.asset_node_id
            )
            SELECT
                an.id AS asset_id,
                an.name,
                an.asset_type,
                an.thumbnail_url,
                an.metadata_json,
                COALESCE(vs.vector_score, 0) AS vector_score,
                COALESCE(ts.text_score, 0) AS text_score,
                COALESCE(tag_s.tag_match_count, 0) AS tag_match_count,
                (COALESCE(vs.vector_score, 0) * :vector_weight +
                 COALESCE(ts.text_score, 0) * :text_weight) AS combined_score
            FROM asset_nodes an
            LEFT JOIN vector_scores vs ON an.id = vs.asset_node_id
            LEFT JOIN text_scores ts ON an.id = ts.asset_node_id
            LEFT JOIN tag_scores tag_s ON an.id = tag_s.asset_node_id
            WHERE an.asset_type = COALESCE(:asset_type, an.asset_type)
            AND (vs.vector_score > 0 OR ts.text_score > 0 OR tag_s.tag_match_count > 0)
            ORDER BY combined_score DESC
            LIMIT :top_k
        """

        result = await self.session.execute(
            text(sql),
            {
                "query_vector": query_vector_str,
                "query_text": query_text,
                "model": self.TEXT_MODEL,
                "vector_weight": vector_weight,
                "text_weight": text_weight,
                "tag_filters": tag_filters or [],
                "asset_type": asset_type_filter,
                "top_k": top_k,
            }
        )

        search_results = []
        for row in result.all():
            combined_score = float(row.combined_score)
            if combined_score >= min_similarity:
                search_results.append({
                    "asset_id": str(row.asset_id),
                    "name": row.name,
                    "asset_type": row.asset_type,
                    "thumbnail_url": row.thumbnail_url,
                    "vector_score": float(row.vector_score) if row.vector_score else 0,
                    "text_score": float(row.text_score) if row.text_score else 0,
                    "tag_match_count": row.tag_match_count,
                    "combined_score": combined_score,
                })

        return search_results

    # -------------------------------------------------------------------------
    # 批量处理
    # -------------------------------------------------------------------------

    async def batch_embed_and_store(
        self,
        asset_ids: List[str],
        texts: Optional[List[str]] = None,
        image_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        批量嵌入并存储

        Args:
            asset_ids: 资产 ID 列表
            texts: 对应的文本列表（可选）
            image_paths: 对应的图片路径列表（可选）

        Returns:
            处理统计信息
        """
        stats = {"total": len(asset_ids), "success": 0, "failed": 0, "errors": []}

        # 批量处理文本嵌入
        if texts:
            embeddings = await self.embed_texts(texts)
            for i, (asset_id, text, embedding) in enumerate(zip(asset_ids, texts, embeddings)):
                if embedding:
                    try:
                        await self.store_text_embedding(asset_id, text)
                        stats["success"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        stats["errors"].append({"asset_id": asset_id, "error": str(e)})
                        logger.error(f"[EmbeddingService] Failed to store embedding for {asset_id}: {e}")

        # 批量处理图像嵌入
        if image_paths:
            embeddings = await self.embed_images(image_paths)
            for asset_id, image_path, embedding in zip(asset_ids, image_paths, embeddings):
                if embedding:
                    try:
                        await self.store_image_embedding(asset_id, image_path)
                        stats["success"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        stats["errors"].append({"asset_id": asset_id, "error": str(e)})
                        logger.error(f"[EmbeddingService] Failed to store image embedding for {asset_id}: {e}")

        return stats

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    async def get_embedding_info(self, asset_id: str) -> Dict[str, Any]:
        """获取资产的所有嵌入信息"""
        from app.db.models.asset_hub import AssetEmbedding

        result = await self.session.execute(
            select(AssetEmbedding).where(AssetEmbedding.asset_node_id == asset_id)
        )
        embeddings = result.scalars().all()

        info = {
            "asset_id": asset_id,
            "embeddings": [],
        }

        for emb in embeddings:
            info["embeddings"].append({
                "id": emb.id,
                "model": emb.embedding_model,
                "dimension": len(emb.embedding) if emb.embedding else 0,
                "created_at": emb.created_at.isoformat() if emb.created_at else None,
            })

        return info

    async def delete_embedding(self, asset_id: str, model: Optional[str] = None) -> bool:
        """删除资产的嵌入向量"""
        from app.db.models.asset_hub import AssetEmbedding

        query = select(AssetEmbedding).where(AssetEmbedding.asset_node_id == asset_id)
        if model:
            query = query.where(AssetEmbedding.embedding_model == model)

        result = await self.session.execute(query)
        embeddings = result.scalars().all()

        for emb in embeddings:
            await self.session.delete(emb)

        await self.session.commit()
        return len(embeddings) > 0
