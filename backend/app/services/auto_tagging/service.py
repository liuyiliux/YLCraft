"""
YLCraft — AI 自动标签服务

使用 AI 模型（CLIP/BLIP 或外部 API）分析资产内容，自动打标签。
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetNode, Tag, AssetTagLink, AssetType
from app.services.tag.service import TagService
from app.services.embedding.service import EmbeddingService

logger = logging.getLogger("ylcraft.auto_tagging")


class AutoTaggingService:
    """AI 自动标签服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tag_service = TagService(session)
        self.embedding_service = EmbeddingService(session)
        self.default_confidence_threshold = 0.7

    async def auto_tag_asset(
        self,
        asset_id: str,
        confidence_threshold: Optional[float] = None,
        model: Optional[str] = None,
        use_api: bool = True,
    ) -> List[AssetTagLink]:
        """
        给单个资产自动打标签
        
        Args:
            asset_id: 资产 ID
            confidence_threshold: 置信度阈值（默认 0.7）
            model: 使用的 AI 模型
            use_api: 是否使用外部 API（否则用本地模型）
        
        Returns:
            新增的标签关联列表
        """
        threshold = confidence_threshold or self.default_confidence_threshold
        asset = await self.session.get(AssetNode, asset_id)

        if not asset:
            logger.warning(f"[AutoTagging] asset not found | id={asset_id}")
            return []

        logger.info(f"[AutoTagging] analyzing asset | id={asset_id} | type={asset.asset_type}")

        suggestions = []

        # 1. 基于资产类型的基础标签
        type_tags = self._get_type_based_tags(asset)
        suggestions.extend(type_tags)

        # 2. 基于已有标签的语义相似度（用向量搜索找相似资产）
        similar_tags = await self._get_similar_tags_from_similar_assets(asset)
        suggestions.extend(similar_tags)

        # 3. 基于 metadata_json 提取的关键词
        metadata_tags = self._extract_tags_from_metadata(asset)
        suggestions.extend(metadata_tags)

        # 4. 调用 AI 模型分析（预留接口）
        ai_tags = await self._analyze_with_ai_model(asset, model, use_api)
        suggestions.extend(ai_tags)

        # 去重和过滤
        filtered_suggestions = self._filter_and_deduplicate(suggestions, threshold)

        if not filtered_suggestions:
            logger.info(f"[AutoTagging] no tags above threshold | id={asset_id}")
            return []

        # 应用标签
        added_links = []
        for tag_suggestion in filtered_suggestions:
            tag_name = tag_suggestion["name"]
            confidence = tag_suggestion["confidence"]

            # 查找或创建标签
            tag = await self._find_or_create_tag(tag_name, tag_suggestion.get("category"))
            if not tag:
                continue

            link = await self.tag_service.tag_asset(
                asset_id=asset_id,
                tag_id=tag.id,
                confidence=confidence,
                source="ai",
            )
            added_links.append(link)
            logger.info(
                f"[AutoTagging] added tag | tag={tag.name} "
                f"| confidence={confidence:.2f} | asset_id={asset_id}"
            )

        return added_links

    async def auto_tag_batch(
        self,
        asset_ids: List[str],
        confidence_threshold: Optional[float] = None,
    ) -> Dict[str, List[AssetTagLink]]:
        """批量给多个资产自动打标签"""
        results = {}
        for asset_id in asset_ids:
            links = await self.auto_tag_asset(asset_id, confidence_threshold)
            results[asset_id] = links
        return results

    async def analyze_with_custom_prompt(
        self,
        asset_id: str,
        prompt: str,
    ) -> List[Dict[str, Any]]:
        """
        使用自定义提示词分析资产内容，返回标签建议
        
        （预留接口，需要集成真实的 AI 模型）
        """
        asset = await self.session.get(AssetNode, asset_id)
        if not asset:
            return []

        logger.info(f"[AutoTagging] custom prompt analysis | prompt={prompt[:50]}...")

        suggestions = []

        # TODO: 集成真实的 AI 模型（如 BLIP-2、GPT-4V 等）
        suggestions.append({
            "name": "待实现",
            "category": "system",
            "confidence": 0.0,
        })

        return suggestions

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _get_type_based_tags(self, asset: AssetNode) -> List[Dict[str, Any]]:
        """基于资产类型生成基础标签"""
        tags = []

        if asset.asset_type == AssetType.IMAGE:
            tags.extend([
                {"name": "图片", "category": "类型", "confidence": 1.0},
                {"name": "视觉素材", "category": "分类", "confidence": 1.0},
            ])
        elif asset.asset_type == AssetType.VIDEO:
            tags.extend([
                {"name": "视频", "category": "类型", "confidence": 1.0},
                {"name": "动态素材", "category": "分类", "confidence": 1.0},
            ])
        elif asset.asset_type == AssetType.CHARACTER:
            tags.extend([
                {"name": "角色", "category": "类型", "confidence": 1.0},
                {"name": "人物", "category": "分类", "confidence": 1.0},
            ])
        elif asset.asset_type == AssetType.MODEL:
            tags.extend([
                {"name": "模型", "category": "类型", "confidence": 1.0},
                {"name": "AI生成", "category": "来源", "confidence": 1.0},
            ])
        elif asset.asset_type == AssetType.TEXT:
            tags.extend([
                {"name": "文本", "category": "类型", "confidence": 1.0},
                {"name": "文案", "category": "分类", "confidence": 1.0},
            ])

        return tags

    async def _get_similar_tags_from_similar_assets(self, asset: AssetNode) -> List[Dict[str, Any]]:
        """基于相似资产的标签生成建议"""
        suggestions = []

        # TODO: 实现真实的向量相似度搜索找相似资产
        # 这里先返回空列表，等待向量搜索功能完全就绪
        return suggestions

    def _extract_tags_from_metadata(self, asset: AssetNode) -> List[Dict[str, Any]]:
        """从 metadata_json 中提取关键词"""
        suggestions = []
        metadata = asset.metadata_json or {}

        # 提取 prompt 中的关键词
        prompt = metadata.get("prompt", "") or metadata.get("description", "")
        if prompt and isinstance(prompt, str):
            keywords = self._extract_keywords(prompt)
            for keyword in keywords[:5]:
                suggestions.append({
                    "name": keyword,
                    "category": "内容",
                    "confidence": 0.8,
                })

        # 提取其他元信息
        if metadata.get("style"):
            suggestions.append({
                "name": metadata["style"],
                "category": "风格",
                "confidence": 0.9,
            })

        if metadata.get("model_name"):
            suggestions.append({
                "name": metadata["model_name"],
                "category": "模型",
                "confidence": 0.95,
            })

        return suggestions

    async def _analyze_with_ai_model(
        self,
        asset: AssetNode,
        model: Optional[str],
        use_api: bool,
    ) -> List[Dict[str, Any]]:
        """
        使用 AI 模型分析资产内容（预留接口）
        
        当前是占位实现，真实实现需要：
        - 对于图片：调用 BLIP-2 / CogVLM / GPT-4V
        - 对于视频：逐帧采样 + 多模态分析
        - 对于音频：Whisper 转文字 + 关键词提取
        """
        suggestions = []

        if not use_api:
            # 本地模型分析（预留）
            return suggestions

        # 外部 API 分析（预留）
        try:
            # TODO: 调用外部 AI API
            pass
        except Exception as e:
            logger.warning(f"[AutoTagging] AI model analysis failed | error={e}")

        return suggestions

    async def _find_or_create_tag(self, tag_name: str, category: Optional[str] = None) -> Optional[Tag]:
        """查找或创建标签"""
        # 查找已存在的标签
        result = await self.session.execute(
            select(Tag).where(Tag.name == tag_name)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # 创建新标签
        try:
            return await self.tag_service.create_tag(
                name=tag_name,
                category=category,
            )
        except Exception as e:
            logger.warning(f"[AutoTagging] failed to create tag | name={tag_name} | error={e}")
            return None

    def _filter_and_deduplicate(
        self,
        suggestions: List[Dict[str, Any]],
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """过滤低置信度并去重"""
        seen_names = set()
        filtered = []

        # 按置信度降序排序
        sorted_suggestions = sorted(
            suggestions,
            key=lambda x: x.get("confidence", 0),
            reverse=True,
        )

        for suggestion in sorted_suggestions:
            name = suggestion.get("name", "").strip()
            confidence = suggestion.get("confidence", 0)

            if not name or confidence < threshold:
                continue

            if name.lower() in seen_names:
                continue

            seen_names.add(name.lower())
            filtered.append(suggestion)

        return filtered

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中简单提取关键词（占位实现）"""
        # 真实实现需要分词和停用词过滤
        stopwords = {
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "to", "the", "and", "a", "an", "is", "in", "on",
        }

        words = text.split()
        keywords = []
        for word in words:
            word = word.strip(",.!?()[]:;\"'").lower()
            if word and len(word) > 1 and word not in stopwords:
                keywords.append(word)
        return keywords
