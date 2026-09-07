"""Writing style profile lifecycle and bounded runtime projection."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.db.models.creative_project import (
    ProjectWritingStyleLink,
    WritingStyleProfile,
    WritingStyleProfileSourceType,
    WritingStyleProfileStatus,
)

ALLOWED_INTENSITIES = {"subtle", "balanced", "strong"}
DEFAULT_STAGE_SCOPE = ["novel_body", "novel_body_refine", "prose_draft", "prose_humanized", "prose_rewrite"]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def canonical_profile_payload(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep the runtime contract small and reject source-specific material."""
    if not isinstance(profile, dict):
        raise ValueError("profile 必须是对象")
    dimensions = profile.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        raise ValueError("profile.dimensions 必须是对象")
    normalized_dimensions: dict[str, dict[str, Any]] = {}
    for key, raw in dimensions.items():
        name = _clean(key, limit=80)
        if not name:
            continue
        if not isinstance(raw, dict):
            raw = {"value": raw}
        normalized_dimensions[name] = {
            "value": _clean(raw.get("value"), limit=1200),
            "confidence": max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0))),
            "evidence_summary": _clean(raw.get("evidence_summary"), limit=800),
            "measurement_keys": [
                _clean(item, limit=80)
                for item in (raw.get("measurement_keys") or [])
                if _clean(item, limit=80)
            ][:20],
        }
    prohibited = [
        _clean(item, limit=240)
        for item in (profile.get("prohibited_source_material") or [])
        if _clean(item, limit=240)
    ][:30]
    examples = [
        _clean(item, limit=500)
        for item in (profile.get("new_examples") or [])
        if _clean(item, limit=500)
    ][:8]
    return {
        "version": int(profile.get("version", 1) or 1),
        "dimensions": normalized_dimensions,
        "new_examples": examples,
        "anti_template_constraints": [
            _clean(item, limit=500)
            for item in (profile.get("anti_template_constraints") or [])
            if _clean(item, limit=500)
        ][:30],
        "prohibited_source_material": prohibited,
    }


def build_prompt_contract(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = canonical_profile_payload(profile)
    rules: list[str] = []
    for name, dimension in normalized["dimensions"].items():
        value = dimension.get("value")
        if value:
            rules.append(f"{name}：{value}")
    rules.extend(normalized["anti_template_constraints"])
    return {
        "instruction": "只模仿抽象表达机制，不复制来源作品的剧情、人物、世界观、专名或原句。",
        "rules": rules[:40],
        "new_examples": normalized["new_examples"],
        "prohibited_source_material": normalized["prohibited_source_material"],
    }


def profile_checksum(profile_json: dict[str, Any], prompt_contract: dict[str, Any]) -> str:
    return hashlib.sha256(_json({
        "profile": canonical_profile_payload(profile_json),
        "prompt_contract": prompt_contract,
    }).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 来源测量聚合与有界抽象分析（风格档案的"输入侧"）
#
# 设计红线：只描述"怎么写"（抽象表达机制），绝不落地"写了什么"
# （原文片段、角色名、地名、情节）。样本有界，分析完即弃，不入库。
# ---------------------------------------------------------------------------

#: 建议提取的表达机制维度。
STYLE_DIMENSIONS: tuple[str, ...] = (
    "叙事视角与距离",
    "句式长度与节奏",
    "词汇和语体",
    "对话机制与潜台词",
    "描写密度",
    "修辞偏好",
    "场景推进方式",
    "情绪温度",
    "动作与抽象解释比例",
    "段落结构",
    "章节收束方式",
)

#: 样本上限：够统计即可，不把整本小说塞进提示词。
EXTRACTION_SAMPLE_CHARS = 12000
EXTRACTION_MAX_CHUNKS = 40

_SENTENCE_SPLIT = re.compile(r"[。！？!?…]+")
_DIALOGUE_MARKS = ("“", "”", '"', "'", "「", "」")


def measure_text_sample(text: str) -> dict[str, Any]:
    """本地确定性测量：不调模型、不存原文，只产出可复核的统计特征。"""
    content = str(text or "")
    chars = len(content)
    sentences = [item for item in _SENTENCE_SPLIT.split(content) if item.strip()]
    paragraphs = [item for item in re.split(r"\n+", content) if item.strip()]
    dialogue_chars = sum(content.count(mark) for mark in _DIALOGUE_MARKS)
    punctuation = sum(content.count(p) for p in "，。！？、；：,.!?;:")
    unique_chars = len(set(content))
    return {
        "chars": chars,
        "sentence_count": len(sentences),
        "avg_sentence_chars": round(sum(len(s) for s in sentences) / len(sentences), 2) if sentences else 0.0,
        "max_sentence_chars": max((len(s) for s in sentences), default=0),
        "paragraph_count": len(paragraphs),
        "avg_paragraph_chars": round(sum(len(p) for p in paragraphs) / len(paragraphs), 2) if paragraphs else 0.0,
        "dialogue_mark_ratio": round(dialogue_chars / chars, 4) if chars else 0.0,
        "punctuation_ratio": round(punctuation / chars, 4) if chars else 0.0,
        "type_token_ratio": round(unique_chars / chars, 4) if chars else 0.0,
    }


def aggregate_sample_measurements(samples: list[str]) -> dict[str, Any]:
    """把逐块测量按字数加权合并成样本级指标。"""
    measured = [measure_text_sample(item) for item in samples if str(item or "").strip()]
    if not measured:
        return {}
    total_chars = sum(item["chars"] for item in measured) or 1

    def weighted(key: str) -> float:
        return round(sum(item[key] * item["chars"] for item in measured) / total_chars, 4)

    return {
        "sample_chars": total_chars,
        "chunk_count": len(measured),
        "sentence_count": sum(item["sentence_count"] for item in measured),
        "paragraph_count": sum(item["paragraph_count"] for item in measured),
        "avg_sentence_chars": weighted("avg_sentence_chars"),
        "avg_paragraph_chars": weighted("avg_paragraph_chars"),
        "dialogue_mark_ratio": weighted("dialogue_mark_ratio"),
        "punctuation_ratio": weighted("punctuation_ratio"),
        "type_token_ratio": weighted("type_token_ratio"),
    }


EXTRACTION_SYSTEM_PROMPT = (
    "你是文体分析助手，只从样本中提炼“抽象表达机制”，用于指导新的原创写作。\n"
    "硬性禁止：原文片段与原句、角色姓名/地名/专名、剧情与人物关系复述、"
    "世界观设定、模仿某位具体作者。\n"
    "只输出一个 JSON 对象，不要解释、不要 markdown 之外的多余文字。"
)


def build_extraction_prompt(sample: str, measurements: dict[str, Any]) -> str:
    """拼装提取提示词：样本有界，测量指标作为可复核的客观依据。"""
    dimensions = "、".join(STYLE_DIMENSIONS)
    return (
        "下面是来源样本（有界，仅用于统计与机制分析）与其客观测量指标。\n\n"
        f"测量指标：{json.dumps(measurements, ensure_ascii=False)}\n\n"
        "请输出如下结构：\n"
        '{"dimensions": {"<维度>": {"value": "机制描述", "confidence": 0.0-1.0, '
        '"evidence_summary": "支撑该判断的客观依据（不复述剧情）", "measurement_keys": ["引用的测量项"]}}, '
        '"new_examples": ["用该机制新写的一句话示例（原创，非原文）"], '
        '"anti_template_constraints": ["要避免的模板化写法"], '
        '"prohibited_source_material": ["禁止带出的来源特征"]}\n\n'
        f"建议覆盖的维度：{dimensions}\n\n"
        f"来源样本：\n{sample}"
    )


def parse_style_json(raw: str) -> dict[str, Any]:
    """解析模型返回的风格结构（允许 markdown 代码围栏）。"""
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回可解析的风格结构（缺少 JSON 对象）")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型返回的风格结构无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("模型返回的风格结构必须是对象")
    return data


class WritingStyleService:
    def __init__(self, session: Session):
        self.session = session

    def create_profile(
        self,
        *,
        name: str,
        description: str = "",
        profile: dict[str, Any] | None = None,
        owner_id: str = "default",
        source_type: str = WritingStyleProfileSourceType.USER_DEFINED.value,
        source_snapshot_id: str | None = None,
        source_sample_hash: str = "",
        provenance: dict[str, Any] | None = None,
    ) -> WritingStyleProfile:
        name = _clean(name, limit=160)
        if not name:
            raise ValueError("风格档案名称不能为空")
        if source_type not in {item.value for item in WritingStyleProfileSourceType}:
            raise ValueError("不支持的风格档案来源类型")
        normalized = canonical_profile_payload(profile or {})
        contract = build_prompt_contract(normalized)
        item = WritingStyleProfile(
            owner_id=_clean(owner_id, limit=120) or "default",
            name=name,
            description=_clean(description),
            source_type=source_type,
            source_snapshot_id=_clean(source_snapshot_id, limit=120) or None,
            source_sample_hash=_clean(source_sample_hash, limit=128),
            profile_json=_json(normalized),
            prompt_contract_json=_json(contract),
            provenance_json=_json(provenance or {}),
            checksum=profile_checksum(normalized, contract),
        )
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def get(self, profile_id: str) -> WritingStyleProfile | None:
        return self.session.get(WritingStyleProfile, profile_id)

    def list(self, *, owner_id: str = "default", status: str | None = None) -> list[WritingStyleProfile]:
        query = select(WritingStyleProfile).where(WritingStyleProfile.owner_id == owner_id)
        if status:
            query = query.where(WritingStyleProfile.status == status)
        return list(self.session.exec(query.order_by(WritingStyleProfile.updated_at.desc())).all())

    def update_draft(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        profile: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> WritingStyleProfile:
        item = self._require(profile_id)
        if item.status not in {WritingStyleProfileStatus.DRAFT.value, WritingStyleProfileStatus.REVIEWED.value}:
            raise ValueError("只有草稿或已审核档案可以编辑")
        if name is not None:
            item.name = _clean(name, limit=160)
        if description is not None:
            item.description = _clean(description)
        normalized = canonical_profile_payload(
            profile if profile is not None else json.loads(item.profile_json or "{}")
        )
        contract = build_prompt_contract(normalized)
        item.profile_json = _json(normalized)
        item.prompt_contract_json = _json(contract)
        if provenance is not None:
            item.provenance_json = _json(provenance)
        item.checksum = profile_checksum(normalized, contract)
        item.version += 1
        item.status = WritingStyleProfileStatus.DRAFT.value
        item.updated_at = datetime.now()
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def review(self, profile_id: str) -> WritingStyleProfile:
        item = self._require(profile_id)
        if item.status != WritingStyleProfileStatus.DRAFT.value:
            raise ValueError("只有草稿可以提交审核")
        self._validate_checksum(item)
        contract = json.loads(item.prompt_contract_json or "{}")
        if not contract.get("rules") and not contract.get("new_examples"):
            raise ValueError("风格档案至少需要一个表达规则或新造示例")
        item.status = WritingStyleProfileStatus.REVIEWED.value
        item.updated_at = datetime.now()
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def activate(self, profile_id: str) -> WritingStyleProfile:
        item = self._require(profile_id)
        if item.status != WritingStyleProfileStatus.REVIEWED.value:
            raise ValueError("风格档案必须先审核后激活")
        self._validate_checksum(item)
        item.status = WritingStyleProfileStatus.ACTIVE.value
        item.updated_at = datetime.now()
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def archive(self, profile_id: str) -> WritingStyleProfile:
        item = self._require(profile_id)
        if item.status == WritingStyleProfileStatus.ARCHIVED.value:
            return item
        item.status = WritingStyleProfileStatus.ARCHIVED.value
        item.updated_at = datetime.now()
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def bind(
        self,
        project_id: str,
        profile_id: str,
        *,
        intensity: str = "balanced",
        stage_scope: list[str] | None = None,
        dimension_overrides: dict[str, Any] | None = None,
        priority: int = 100,
    ) -> ProjectWritingStyleLink:
        item = self._require(profile_id)
        if item.status != WritingStyleProfileStatus.ACTIVE.value:
            raise ValueError("只有已激活的风格档案可以绑定项目")
        if intensity not in ALLOWED_INTENSITIES:
            raise ValueError("intensity 必须是 subtle、balanced 或 strong")
        existing = self.session.exec(
            select(ProjectWritingStyleLink).where(
                ProjectWritingStyleLink.project_id == project_id,
                ProjectWritingStyleLink.style_profile_id == profile_id,
            )
        ).first()
        if existing:
            link = existing
        else:
            link = ProjectWritingStyleLink(project_id=project_id, style_profile_id=profile_id)
        link.enabled = True
        link.intensity = intensity
        link.priority = priority
        link.stage_scope_json = _json(stage_scope or DEFAULT_STAGE_SCOPE)
        link.dimension_overrides_json = _json(dimension_overrides or {})
        link.updated_at = datetime.now()
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def unbind(self, project_id: str, profile_id: str) -> None:
        link = self.session.exec(
            select(ProjectWritingStyleLink).where(
                ProjectWritingStyleLink.project_id == project_id,
                ProjectWritingStyleLink.style_profile_id == profile_id,
            )
        ).first()
        if link:
            self.session.delete(link)
            self.session.commit()

    def runtime_profiles(self, project_id: str, *, stage: str = "") -> list[dict[str, Any]]:
        links = self.session.exec(
            select(ProjectWritingStyleLink)
            .where(ProjectWritingStyleLink.project_id == project_id, ProjectWritingStyleLink.enabled == True)
            .order_by(ProjectWritingStyleLink.priority.asc(), ProjectWritingStyleLink.created_at.asc())
        ).all()
        result: list[dict[str, Any]] = []
        for link in links:
            profile = self.get(link.style_profile_id)
            if not profile or profile.status != WritingStyleProfileStatus.ACTIVE.value:
                continue
            scope = json.loads(link.stage_scope_json or "[]")
            if stage and scope and stage not in scope and "*" not in scope:
                continue
            self._validate_checksum(profile)
            contract = json.loads(profile.prompt_contract_json or "{}")
            result.append({
                "id": profile.id,
                "name": profile.name,
                "version": profile.version,
                "checksum": profile.checksum,
                "intensity": link.intensity,
                "stage_scope": scope,
                "dimension_overrides": json.loads(link.dimension_overrides_json or "{}"),
                "prompt_contract": contract,
            })
        return result

    async def extract_draft_from_source(
        self,
        *,
        snapshot_id: str,
        name: str = "",
        owner_id: str = "default",
        provider: str | None = None,
        model: str | None = None,
        max_chars: int = EXTRACTION_SAMPLE_CHARS,
    ) -> WritingStyleProfile:
        """从来源快照提取风格档案草稿：测量聚合 + 有界抽象分析。

        只取有界样本做统计与机制分析，**不把来源正文存进档案**（样本分析完即弃，
        只留 hash 与测量指标做溯源）。产出的一律是 ``draft``——设计上禁止自动激活，
        必须经人工或 Agent 审核。
        """
        from app.db.models.novel_source import NovelSourceSnapshot
        from app.services.ai import get_ai_service
        from app.services.ai.service import ai_call_context
        from app.services.ai.types import LLMMessage
        from app.services.novel_source.service import NovelSourceService

        snapshot = self.session.get(NovelSourceSnapshot, snapshot_id)
        if not snapshot:
            raise ValueError("来源快照不存在")

        chunks = NovelSourceService(self.session).list_chunks(
            snapshot_id, limit=EXTRACTION_MAX_CHUNKS
        )
        samples: list[str] = []
        offsets: list[list[int]] = []
        used = 0
        for chunk in chunks:
            text = str(chunk.content or "").strip()
            if not text:
                continue
            samples.append(text)
            offsets.append([int(chunk.start_offset), int(chunk.end_offset)])
            used += len(text)
            if used >= max_chars:
                break
        if not samples:
            raise ValueError("该来源快照还没有可分析的文本块")

        measurements = aggregate_sample_measurements(samples)
        sample_text = "\n".join(samples)[:max_chars]
        sample_hash = hashlib.sha256(sample_text.encode("utf-8")).hexdigest()

        with ai_call_context(
            ref_id=snapshot_id,
            scene="writing",
            task_type="style_extract",
            label="风格档案草稿提取",
        ):
            result = await get_ai_service().chat(
                [
                    LLMMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
                    LLMMessage(
                        role="user",
                        content=build_extraction_prompt(sample_text, measurements),
                    ),
                ],
                provider=provider,
                model=model,
            )
        if not getattr(result, "success", True):
            raise ValueError(getattr(result, "error", "") or "风格提取失败")

        data = parse_style_json(getattr(result, "content", ""))
        raw_dimensions = data.get("dimensions")
        measurement_keys = sorted(measurements.keys())
        dimensions: dict[str, Any] = {}
        if isinstance(raw_dimensions, dict):
            for key, value in raw_dimensions.items():
                if isinstance(value, dict):
                    dimensions[str(key)] = {
                        "value": value.get("value"),
                        "confidence": value.get("confidence", 0.0),
                        "evidence_summary": value.get("evidence_summary", ""),
                        "measurement_keys": value.get("measurement_keys") or measurement_keys,
                    }
                else:
                    dimensions[str(key)] = {
                        "value": value,
                        "confidence": 0.0,
                        "evidence_summary": "",
                        "measurement_keys": measurement_keys,
                    }

        return self.create_profile(
            name=name or f"{str(snapshot.title or '来源')} 风格草稿",
            description="从来源快照自动提取的表达机制草稿，需审核后激活。",
            profile={
                "version": 1,
                "dimensions": dimensions,
                "new_examples": data.get("new_examples") or [],
                "anti_template_constraints": data.get("anti_template_constraints") or [],
                "prohibited_source_material": data.get("prohibited_source_material") or [],
            },
            owner_id=owner_id,
            source_type=WritingStyleProfileSourceType.EXTRACTED_FROM_SOURCE.value,
            source_snapshot_id=snapshot_id,
            source_sample_hash=sample_hash,
            provenance={
                "snapshot_id": snapshot_id,
                "snapshot_title": str(snapshot.title or ""),
                "sample_chars": len(sample_text),
                "chunk_offsets": offsets[:20],
                "measurements": measurements,
                "provider": provider or "",
                "model": model or "",
                "extracted_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    def _require(self, profile_id: str) -> WritingStyleProfile:
        item = self.get(profile_id)
        if not item:
            raise ValueError("风格档案不存在")
        return item

    @staticmethod
    def _validate_checksum(item: WritingStyleProfile) -> None:
        profile = json.loads(item.profile_json or "{}")
        contract = json.loads(item.prompt_contract_json or "{}")
        expected = profile_checksum(profile, contract)
        if item.checksum != expected:
            raise ValueError("风格档案校验和不匹配，请重新编辑并审核")


def serialize_style_profile(item: WritingStyleProfile) -> dict[str, Any]:
    return {
        "id": item.id,
        "owner_id": item.owner_id,
        "name": item.name,
        "description": item.description,
        "source_type": item.source_type,
        "source_snapshot_id": item.source_snapshot_id,
        "source_sample_hash": item.source_sample_hash,
        "status": item.status,
        "version": item.version,
        "profile": json.loads(item.profile_json or "{}"),
        "prompt_contract": json.loads(item.prompt_contract_json or "{}"),
        "provenance": json.loads(item.provenance_json or "{}"),
        "checksum": item.checksum,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def serialize_style_link(link: ProjectWritingStyleLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "style_profile_id": link.style_profile_id,
        "enabled": link.enabled,
        "priority": link.priority,
        "intensity": link.intensity,
        "stage_scope": json.loads(link.stage_scope_json or "[]"),
        "dimension_overrides": json.loads(link.dimension_overrides_json or "{}"),
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
    }
