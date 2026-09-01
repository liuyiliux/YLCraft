"""小说源资产与世界提取服务。

对外暴露来源导入、文本块、模块检测、世界候选提取和确认写入能力。
"""

from app.services.novel_source.contracts import (
    BASIC_DOMAINS,
    DETECTABLE_DOMAINS,
    EXTRACTABLE_DOMAINS,
    DomainSpec,
    domain_label,
    get_domain,
    normalize_entity_name,
)
from app.services.novel_source.service import NovelSourceService
from app.services.novel_source.extraction import WorldExtractionService

__all__ = [
    "BASIC_DOMAINS",
    "DETECTABLE_DOMAINS",
    "EXTRACTABLE_DOMAINS",
    "DomainSpec",
    "NovelSourceService",
    "WorldExtractionService",
    "domain_label",
    "get_domain",
    "normalize_entity_name",
]
