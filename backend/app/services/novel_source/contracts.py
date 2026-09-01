"""世界提取的域契约与模型输出 schema。

域是提取规划的单位，不是题材标签。系统不使用整体「都市/玄幻」开关，
而是让 AI 对每个模块独立给出 ``detected / not_detected / uncertain``，
用户或 Agent 再逐域决定；用户显式指定的模块标记为 ``user_requested``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

DOMAIN_CHARACTER = "character"
DOMAIN_LOCATION = "location"
DOMAIN_FACTION = "faction"
DOMAIN_HISTORICAL_EVENT = "historical_event"
DOMAIN_TIMELINE = "timeline"
DOMAIN_WORLD_RULE = "world_rule"
DOMAIN_POWER_SYSTEM = "power_system"
DOMAIN_ECONOMY = "economy"
DOMAIN_SPECIES = "species"
DOMAIN_ITEM = "item"
DOMAIN_GLOSSARY = "glossary"
DOMAIN_MAP = "map"


@dataclass(frozen=True)
class DomainSpec:
    """一个世界模块的定义。

    ``attributes`` 即该域的 payload schema 契约：声明了 ``ExtractedFactItem.attributes``
    中应承载的域特有字段。提取时模型按此清单产出结构化字段，写入
    ``world_asset`` 事实卡时原样保留在 ``data.attributes`` 中。角色域复用既有
    角色卡的 ``identity/motivation/speech/behavior`` 等设定字段，不在此重复声明。
    """

    key: str
    label: str
    basic: bool
    extractable: bool
    entity_type: str
    prompt_hint: str
    attributes: tuple[str, ...] = field(default=())


DOMAIN_SPECS: tuple[DomainSpec, ...] = (
    DomainSpec(
        key=DOMAIN_CHARACTER,
        label="角色",
        basic=True,
        extractable=True,
        entity_type="character",
        prompt_hint=(
            "只收录有名有姓或有稳定称谓、并且在原文中行动或说话的人物。"
            "地名、组织名、旁观叙述者不算角色。"
        ),
        attributes=("aliases", "role", "affiliation", "first_appearance", "traits"),
    ),
    DomainSpec(
        key=DOMAIN_LOCATION,
        label="地点",
        basic=True,
        extractable=True,
        entity_type="place",
        prompt_hint=(
            "只收录原文明确出现、并且剧情在其内部发生的地点或区域。"
            "笼统方位（如「南方」）不算地点。"
        ),
        attributes=("aliases", "kind", "region", "significance", "first_appearance"),
    ),
    DomainSpec(
        key=DOMAIN_FACTION,
        label="势力",
        basic=True,
        extractable=True,
        entity_type="faction",
        prompt_hint=(
            "只收录原文明确存在、并且影响剧情走向的组织、门派、家族、国家或阵营。"
            "只被提及名称而无任何作用的组织不算。"
        ),
        attributes=("aliases", "kind", "territory", "goal", "rivals", "members"),
    ),
    DomainSpec(
        key=DOMAIN_HISTORICAL_EVENT,
        label="历史事件",
        basic=True,
        extractable=True,
        entity_type="event",
        prompt_hint=(
            "只收录原文明确交代、发生在主线之前或之外、并且影响当前局势的事件。"
            "正在发生的剧情本身不算历史事件。"
        ),
        attributes=("time_expression", "location", "participants", "cause", "consequence", "certainty"),
    ),
    DomainSpec(
        key=DOMAIN_TIMELINE,
        label="剧情时间线",
        basic=False,
        extractable=True,
        entity_type="timeline_event",
        prompt_hint=(
            "只收录主线剧情中明确交代了时间推进或先后顺序的关键节点，"
            "例如时间跳转标记（「三年后」「次日」「当夜」）、明确纪年或重大转折。"
            "name 用简短短语概括节点，attributes 记录时间表述、先后顺序与参与者。"
            "发生在主线之前的背景事件归入「历史事件」，不在此重复。"
        ),
        attributes=("time_expression", "order", "chapter", "participants"),
    ),
    DomainSpec(
        key=DOMAIN_WORLD_RULE,
        label="世界规则",
        basic=False,
        extractable=True,
        entity_type="world_rule",
        prompt_hint=(
            "只收录原文明确交代、约束整个世界或社会运转的底层法则、禁忌、契约与通行规矩，"
            "例如不可违背的誓言代价、族群间的通行禁令、时间与因果层面的限制。"
            "具体的修炼等级、功法与科技树归入「力量/科技体系」，不在此重复收录。"
        ),
        attributes=("kind", "scope", "constraints", "consequences", "enforced_by"),
    ),
    DomainSpec(
        key=DOMAIN_POWER_SYSTEM,
        label="力量/科技体系",
        basic=False,
        extractable=True,
        entity_type="power_system",
        prompt_hint=(
            "只收录原文明确交代了运行规则的修炼等级、功法、异能、咒术或科技体系，"
            "包含等级划分、生效规则、代价与限制。"
            "只被提到名字、原文没有说明任何规则的不算。"
        ),
        attributes=("kind", "levels", "rules", "costs", "limits", "practitioners"),
    ),
    DomainSpec(
        key=DOMAIN_ECONOMY,
        label="经济/金融",
        basic=False,
        extractable=True,
        entity_type="economy",
        prompt_hint=(
            "只收录原文明确出现的货币、物价、资源、贸易路线、税收与产业组织。"
            "笼统说「很有钱」「生意好」但没有具体制度、价格或机构的不算。"
        ),
        attributes=("kind", "currency", "prices", "resources", "trade_routes", "institutions"),
    ),
    DomainSpec(
        key=DOMAIN_SPECIES,
        label="物种",
        basic=False,
        extractable=True,
        entity_type="species",
        prompt_hint=(
            "只收录原文明确出现、有别于普通人类或现实生物的种族、妖兽、灵族等族群，"
            "包含生理特征、栖息地、寿命与族群关系。"
            "泛泛提到「野兽」「怪物」而没有具体特征的不算。"
        ),
        attributes=("kind", "traits", "habitat", "lifespan", "relations", "abilities"),
    ),
    DomainSpec(
        key=DOMAIN_ITEM,
        label="物品/资源",
        basic=False,
        extractable=True,
        entity_type="item",
        prompt_hint=(
            "只收录原文明确出现、有名字且影响剧情的器物、法宝、资源或道具，"
            "包含其用途、来历与限制。泛泛的日常物件不算。"
        ),
        attributes=("kind", "origin", "use", "constraints"),
    ),
    DomainSpec(
        key=DOMAIN_GLOSSARY,
        label="术语表",
        basic=False,
        extractable=True,
        entity_type="glossary",
        prompt_hint=(
            "只收录作品特有的专有名词、称谓、制度或概念，给出简明释义。"
            "普通词汇、地名、人名、势力名分别归入对应模块，不在此重复。"
        ),
        attributes=("kind", "definition", "related_domains"),
    ),
    DomainSpec(
        key=DOMAIN_MAP,
        label="地图",
        basic=False,
        extractable=False,
        entity_type="map",
        prompt_hint=(
            "区域层级、路线、边界与据点空间关系。该模块需要结构化的空间关系编辑，"
            "当前只做存在性检测，不产生候选；地理实体的文字设定由「地点」模块承载。"
        ),
        attributes=("regions", "routes", "borders"),
    ),
)

DOMAIN_BY_KEY: dict[str, DomainSpec] = {spec.key: spec for spec in DOMAIN_SPECS}

#: 每个项目都可用的基础层。
BASIC_DOMAINS: tuple[str, ...] = tuple(spec.key for spec in DOMAIN_SPECS if spec.basic)

#: AI 需要判断存在性的模块。
DETECTABLE_DOMAINS: tuple[str, ...] = tuple(spec.key for spec in DOMAIN_SPECS)

#: 当前已实现提取通道的模块。未实现的模块可以被检测，但不会产生候选噪声。
EXTRACTABLE_DOMAINS: tuple[str, ...] = tuple(spec.key for spec in DOMAIN_SPECS if spec.extractable)

DETECTION_DETECTED = "detected"
DETECTION_NOT_DETECTED = "not_detected"
DETECTION_UNCERTAIN = "uncertain"
DETECTION_USER_REQUESTED = "user_requested"

VALID_DETECTIONS = (
    DETECTION_DETECTED,
    DETECTION_NOT_DETECTED,
    DETECTION_UNCERTAIN,
    DETECTION_USER_REQUESTED,
)

ESTIMATED_COSTS = ("low", "medium", "high")


def get_domain(key: str) -> DomainSpec | None:
    """按 key 取域定义，未定义时返回 None 而不是抛错。"""
    return DOMAIN_BY_KEY.get(str(key or "").strip())


def domain_label(key: str) -> str:
    spec = get_domain(key)
    return spec.label if spec else str(key or "")


_NAME_NOISE_PATTERN = re.compile(r"[\s\u3000\-_/·•.,，。:：;；!！?？()（）【】\[\]{}<>《》\"'“”‘’]+")


def normalize_entity_name(value: str) -> str:
    """规范化实体名，用于去重和精确检索。"""
    return _NAME_NOISE_PATTERN.sub("", str(value or "")).casefold()


class DomainDetectionItem(BaseModel):
    """单个模块的存在性判断。"""

    domain: str = ""
    status: str = DETECTION_UNCERTAIN
    reason: str = ""
    signals: list[str] = Field(default_factory=list)
    estimated_cost: str = "low"


class DomainDetectionSchema(BaseModel):
    """模块检测趟的严格 JSON 契约。"""

    domains: list[DomainDetectionItem] = Field(default_factory=list)


class ExtractedFactItem(BaseModel):
    """任意世界模块的一条提取结果。

    各域共用一个结构：``name`` 是稳定标识，``attributes`` 承载域特有字段，
    ``quotes`` 是必须逐字出自原文的证据。
    """

    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    quotes: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    uncertain: bool = False


class DomainExtractionSchema(BaseModel):
    """单域提取趟的严格 JSON 契约。"""

    items: list[ExtractedFactItem] = Field(default_factory=list)


CONTRADICTION_CONSISTENT = "consistent"
CONTRADICTION_CONFLICTING = "conflicting"
CONTRADICTION_DISTINCT = "distinct"
VALID_CONTRADICTION_VERDICTS = (
    CONTRADICTION_CONSISTENT,
    CONTRADICTION_CONFLICTING,
    CONTRADICTION_DISTINCT,
)


class ContradictionVerdictSchema(BaseModel):
    """重复组语义判断的严格 JSON 契约。

    ``consistent`` 表示同一实体且描述一致（可 merge）；``conflicting`` 表示
    同一实体但描述矛盾（需人工 resolve）；``distinct`` 表示其实是不同实体。
    """

    verdict: str = CONTRADICTION_DISTINCT
    reason: str = ""
    recommended_action: str = "keep_separate"


class EvidenceAnchor(BaseModel):
    """一条已验证的证据锚点。"""

    chunk_id: str = ""
    chunk_ordinal: int = 0
    chapter_ordinal: int | None = None
    start_offset: int = 0
    end_offset: int = 0
    quote: str = ""


def build_candidate_fingerprint(snapshot_id: str, domain: str, name: str) -> str:
    """候选去重指纹：快照 + 域 + 规范化名。"""
    import hashlib

    raw = f"{snapshot_id}|{domain}|{normalize_entity_name(name)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
