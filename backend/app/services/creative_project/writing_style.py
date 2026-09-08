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


# ---------------------------------------------------------------------------
# 来源材料泄漏检查（OpenSpec 任务 11）
#
# 风格档案只许描述"怎么写"，不许带出"写了什么"。这里做三层检查：
#   1) 来源专名/禁用词污染 → 违规
#   2) 与来源样本的长片段重合（复述原文）→ 违规
#   3) 新造示例与来源样本的 n-gram 重合率偏高 → 告警（供审核人判断）
# 违规不阻止落草稿（便于查看与修正），但**阻止进入审核与激活**——
# 闸门放在 review/activate，与"确认边界"一致。
# ---------------------------------------------------------------------------

MATERIAL_NGRAM = 12
SIMILARITY_NGRAM = 8
SIMILARITY_WARN_RATIO = 0.12


def _profile_texts(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """列出需要检查来源材料泄漏的（位置, 文本）。"""
    normalized = canonical_profile_payload(profile)
    texts: list[tuple[str, str]] = []
    for name, dimension in (normalized.get("dimensions") or {}).items():
        texts.append((f"dimensions.{name}.value", str(dimension.get("value") or "")))
        texts.append(
            (f"dimensions.{name}.evidence_summary", str(dimension.get("evidence_summary") or ""))
        )
    for index, example in enumerate(normalized.get("new_examples") or []):
        texts.append((f"new_examples[{index}]", str(example)))
    for index, item in enumerate(normalized.get("anti_template_constraints") or []):
        texts.append((f"anti_template_constraints[{index}]", str(item)))
    return [(location, text) for location, text in texts if text.strip()]


def _ngrams(text: str, size: int) -> set[str]:
    cleaned = re.sub(r"\s+", "", str(text or ""))
    return {cleaned[i : i + size] for i in range(0, max(0, len(cleaned) - size + 1))}


def inspect_style_material(
    profile: dict[str, Any],
    *,
    source_terms: list[str] | None = None,
    source_samples: list[str] | None = None,
) -> dict[str, Any]:
    """检查风格档案是否带出来源材料（专名、原句、过高相似）。

    Args:
        profile: 待检查的档案内容
        source_terms: 来源专名/禁用词（作品名、作者名、角色名等），出现在档案里即为违规
        source_samples: 来源样本原文，用于长片段重合与相似度判定

    Returns:
        ``{"ok": bool, "violations": [...], "warnings": [...]}``。
        ``ok=False`` 表示存在违规，不得审核或激活。
    """
    normalized = canonical_profile_payload(profile)
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    terms = [str(term).strip() for term in (source_terms or []) if str(term).strip()]
    samples = [str(sample) for sample in (source_samples or []) if str(sample).strip()]

    # 1) 来源专名/禁用词污染
    for location, text in _profile_texts(normalized):
        for term in terms:
            if term and term in text:
                violations.append({"type": "source_term", "location": location, "term": term})

    # 2) 与来源样本的长片段重合（连续 MATERIAL_NGRAM 字雷同 = 复述原文）
    long_grams: set[str] = set()
    for sample in samples:
        long_grams |= _ngrams(sample, MATERIAL_NGRAM)
    if long_grams:
        for location, text in _profile_texts(normalized):
            for gram in _ngrams(text, MATERIAL_NGRAM):
                if gram in long_grams:
                    violations.append(
                        {"type": "verbatim_overlap", "location": location, "excerpt": gram}
                    )
                    break

    # 3) 新造示例与来源样本的相似度（只告警：短句天然会有常用词组重合）
    short_grams: set[str] = set()
    for sample in samples:
        short_grams |= _ngrams(sample, SIMILARITY_NGRAM)
    if short_grams:
        for index, example in enumerate(normalized.get("new_examples") or []):
            grams = _ngrams(example, SIMILARITY_NGRAM)
            if not grams:
                continue
            ratio = len(grams & short_grams) / len(grams)
            if ratio >= SIMILARITY_WARN_RATIO:
                warnings.append(
                    {
                        "type": "example_similarity",
                        "location": f"new_examples[{index}]",
                        "ratio": round(ratio, 3),
                    }
                )

    return {"ok": not violations, "violations": violations[:20], "warnings": warnings[:20]}


# ---------------------------------------------------------------------------
# Markdown Skill 导入导出（OpenSpec 任务 10）
#
# 互操作格式：对外是人人可读可改的 Markdown，对内档案仍是唯一事实来源。
# 导入一律产出 draft 并走同一套材料检查，不因"从文件来的"就跳过闸门。
# ---------------------------------------------------------------------------

SKILL_TYPE = "writing_style_profile"
SKILL_HEADING_DIMENSIONS = "表达机制维度"
SKILL_HEADING_EXAMPLES = "新造示例"
SKILL_HEADING_CONSTRAINTS = "反模板约束"
SKILL_HEADING_PROHIBITED = "禁止带出的来源特征"


def export_style_profile_markdown(
    profile: dict[str, Any],
    *,
    name: str = "",
    description: str = "",
    meta: dict[str, Any] | None = None,
) -> str:
    """把风格档案导出为 Markdown Skill 草稿（可版本库管理、可人工编辑）。"""
    normalized = canonical_profile_payload(profile)
    frontmatter = [f"name: {_clean(name, limit=160) or '未命名风格'}", f"type: {SKILL_TYPE}"]
    for key, value in (meta or {}).items():
        cleaned = _clean(value, limit=200)
        if cleaned:
            frontmatter.append(f"{key}: {cleaned}")

    lines = ["---", *frontmatter, "---", "", f"# {_clean(name, limit=160) or '未命名风格'}", ""]
    if description:
        lines += [f"> {_clean(description)}", ""]

    lines += [f"## {SKILL_HEADING_DIMENSIONS}", ""]
    for dimension_name, dimension in (normalized.get("dimensions") or {}).items():
        lines.append(f"- **{dimension_name}**：{dimension.get('value') or ''}")
        confidence = dimension.get("confidence")
        if confidence:
            lines.append(f"  - 置信度：{confidence}")
        if dimension.get("evidence_summary"):
            lines.append(f"  - 依据：{dimension['evidence_summary']}")
        if dimension.get("measurement_keys"):
            lines.append(f"  - 引用测量：{'、'.join(dimension['measurement_keys'])}")
    lines.append("")

    for heading, key in (
        (SKILL_HEADING_EXAMPLES, "new_examples"),
        (SKILL_HEADING_CONSTRAINTS, "anti_template_constraints"),
        (SKILL_HEADING_PROHIBITED, "prohibited_source_material"),
    ):
        items = normalized.get(key) or []
        if not items:
            continue
        lines += [f"## {heading}", ""]
        lines += [f"- {item}" for item in items]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_style_profile_markdown(text: str) -> dict[str, Any]:
    """解析 Markdown Skill 草稿为 ``{name, description, profile, meta}``。

    容错优先：frontmatter、标题层级、子项缩进都允许多种写法；解析不到的部分
    留空交给人工补，不抛异常（只有完全不像风格档案时才报错）。
    """
    raw = str(text or "")
    meta: dict[str, Any] = {}
    body = raw
    if raw.lstrip().startswith("---"):
        parts = raw.lstrip().split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            body = parts[2]

    name = str(meta.get("name") or "").strip()
    description = ""
    dimensions: dict[str, Any] = {}
    examples: list[str] = []
    constraints: list[str] = []
    prohibited: list[str] = []
    section = ""

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            if not name:
                name = stripped[2:].strip()
            section = ""
            continue
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            continue
        if stripped.startswith("> "):
            description = (description + " " + stripped[2:].strip()).strip()
            continue

        item = re.sub(r"^[-*]\s*", "", stripped)
        if not item:
            continue
        if section == SKILL_HEADING_DIMENSIONS:
            # 主项："- **维度名**：描述"；子项：缩进的「- 置信度：0.8」
            if line.startswith(" ") or line.startswith("\t"):
                match = re.match(r"^(置信度|依据|引用测量)：(.+)$", item)
                if match and dimensions:
                    last = next(reversed(dimensions))
                    kind, value = match.group(1), match.group(2).strip()
                    if kind == "置信度":
                        try:
                            dimensions[last]["confidence"] = float(value)
                        except ValueError:
                            pass
                    elif kind == "依据":
                        dimensions[last]["evidence_summary"] = value
                    else:
                        dimensions[last]["measurement_keys"] = [
                            part.strip() for part in re.split(r"[、,，]", value) if part.strip()
                        ]
                continue
            match = re.match(r"^\*\*(.+?)\*\*[：:](.*)$", item)
            if not match:
                match = re.match(r"^(.+?)[：:](.*)$", item)
            if match:
                dimensions[match.group(1).strip()] = {
                    "value": match.group(2).strip(),
                    "confidence": 0.0,
                    "evidence_summary": "",
                    "measurement_keys": [],
                }
            continue
        if section == SKILL_HEADING_EXAMPLES:
            examples.append(item)
        elif section == SKILL_HEADING_CONSTRAINTS:
            constraints.append(item)
        elif section == SKILL_HEADING_PROHIBITED:
            prohibited.append(item)

    if not dimensions and not constraints:
        raise ValueError("Markdown 里没有解析到表达机制维度或反模板约束")

    version = 1
    try:
        version = int(meta.get("version") or 1)
    except ValueError:
        version = 1

    return {
        "name": name,
        "description": description,
        "profile": {
            "version": version,
            "dimensions": dimensions,
            "new_examples": examples,
            "anti_template_constraints": constraints,
            "prohibited_source_material": prohibited,
        },
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# 生成后风格偏差审阅（OpenSpec 任务 12）
#
# 只做"测量 + 提示"，绝不自动改写正文：风格是软约束，偏离多少由人决定。
# 判定用确定性测量（与提取侧同一套指标），不把审美判断伪装成精确分数。
# ---------------------------------------------------------------------------

#: 相对偏差阈值：超过 warn 提示，超过 off 视为明显偏离。
DEVIATION_WARN_RATIO = 0.35
DEVIATION_OFF_RATIO = 0.75

#: 参与偏差比对的指标（与 measure_text_sample 的输出键对应）。
DEVIATION_METRICS = (
    "avg_sentence_chars",
    "avg_paragraph_chars",
    "dialogue_mark_ratio",
    "punctuation_ratio",
    "type_token_ratio",
)


def measure_style_deviation(
    text: str,
    profile: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """比对生成正文与风格档案声明的表达机制，给出可复核的偏差报告。

    Args:
        text: 待审阅的正文
        profile: 风格档案内容（取其反模板约束与禁止项作为人工核对提醒）
        baseline: 期望指标基线（通常是提取时的来源测量），缺失时只报实测值

    Returns:
        ``{"ok": bool, "metrics": [...], "constraints": [...], "prohibited": [...]}``；
        ``ok=False`` 表示至少一项指标明显偏离（severity=off）。
    """
    normalized = canonical_profile_payload(profile)
    actual = measure_text_sample(text)
    metrics: list[dict[str, Any]] = []
    off_count = 0

    for key in DEVIATION_METRICS:
        measured = float(actual.get(key) or 0.0)
        entry: dict[str, Any] = {"metric": key, "actual": measured}
        expected_value = (baseline or {}).get(key)
        if isinstance(expected_value, (int, float)) and float(expected_value) > 0:
            expected = float(expected_value)
            ratio = abs(measured - expected) / expected
            severity = "ok"
            if ratio >= DEVIATION_OFF_RATIO:
                severity = "off"
                off_count += 1
            elif ratio >= DEVIATION_WARN_RATIO:
                severity = "warn"
            entry.update(
                {
                    "expected": round(expected, 4),
                    "deviation_ratio": round(ratio, 3),
                    "severity": severity,
                }
            )
        else:
            entry.update({"expected": None, "deviation_ratio": None, "severity": "unknown"})
        metrics.append(entry)

    return {
        "ok": off_count == 0,
        "off_count": off_count,
        "metrics": metrics,
        # 约束与禁止项不做自动判定：短文本本就无法可靠匹配，只提醒审核人逐条看。
        "constraints": normalized.get("anti_template_constraints") or [],
        "prohibited_source_material": normalized.get("prohibited_source_material") or [],
        "dimensions": sorted((normalized.get("dimensions") or {}).keys()),
    }


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
        # 编辑后重算来源材料检查：改内容可能引入专名或原句，闸门要跟着更新。
        try:
            stored_provenance = json.loads(item.provenance_json or "{}")
        except (TypeError, ValueError):
            stored_provenance = {}
        if provenance is not None:
            stored_provenance = dict(provenance)
        if isinstance(stored_provenance, dict) and (
            stored_provenance.get("source_terms") or stored_provenance.get("material_check")
        ):
            stored_provenance["material_check"] = inspect_style_material(
                normalized, source_terms=list(stored_provenance.get("source_terms") or [])
            )
            item.provenance_json = _json(stored_provenance)
        elif provenance is not None:
            item.provenance_json = _json(provenance)
        item.checksum = profile_checksum(normalized, contract)
        item.version += 1
        item.status = WritingStyleProfileStatus.DRAFT.value
        item.updated_at = datetime.now()
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def export_skill_markdown(self, profile_id: str) -> str:
        """导出档案为 Markdown Skill 草稿（互操作格式，可版本管理与人工编辑）。"""
        item = self._require(profile_id)
        return export_style_profile_markdown(
            json.loads(item.profile_json or "{}"),
            name=item.name,
            description=item.description,
            meta={
                "version": item.version,
                "source_type": item.source_type,
                "checksum": item.checksum,
            },
        )

    def import_skill_markdown(
        self,
        markdown: str,
        *,
        name: str = "",
        owner_id: str = "default",
        source_terms: list[str] | None = None,
    ) -> WritingStyleProfile:
        """从 Markdown Skill 草稿导入档案：一律产出 draft，并跑同一套材料检查。

        导入不是免检通道：解析出的内容同样要做来源专名与原文片段检查，
        结果写进 provenance，闸门仍在 review / activate。
        """
        parsed = parse_style_profile_markdown(markdown)
        terms = [str(term).strip() for term in (source_terms or []) if str(term).strip()]
        check = inspect_style_material(parsed["profile"], source_terms=terms)
        return self.create_profile(
            name=name or parsed["name"] or "导入的风格档案",
            description=parsed["description"] or "从 Markdown Skill 导入，需审核后激活。",
            profile=parsed["profile"],
            owner_id=owner_id,
            source_type=WritingStyleProfileSourceType.AGENT_DRAFT.value,
            provenance={
                "import_format": "markdown_skill",
                "source_terms": terms,
                "material_check": check,
                "imported_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    def _material_gate(self, item: WritingStyleProfile) -> None:
        """来源材料闸门：带出原文片段或来源专名的档案不得进入生效链路。"""
        provenance = json.loads(item.provenance_json or "{}")
        if not isinstance(provenance, dict):
            return
        check = provenance.get("material_check")
        if not isinstance(check, dict):
            # 手工创建的档案没有提取检查记录：用留存的来源专名现算一次。
            terms = provenance.get("source_terms")
            if not terms:
                return
            check = inspect_style_material(
                json.loads(item.profile_json or "{}"), source_terms=list(terms)
            )
        if check.get("ok") is False:
            found = check.get("violations") or []
            first = found[0] if found else {}
            where = str(first.get("location") or "")
            if first.get("type") == "source_term":
                raise ValueError(f"风格档案带出来源专名「{first.get('term')}」（{where}），请改写后再审核")
            raise ValueError(f"风格档案存在与来源原文雷同的片段（{where}），请改写后再审核")

    def review(self, profile_id: str) -> WritingStyleProfile:
        item = self._require(profile_id)
        if item.status != WritingStyleProfileStatus.DRAFT.value:
            raise ValueError("只有草稿可以提交审核")
        self._validate_checksum(item)
        self._material_gate(item)
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
        self._material_gate(item)
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

    def review_prose_deviation(
        self, project_id: str, text: str, *, stage: str = ""
    ) -> dict[str, Any]:
        """正文生成后的风格偏差审阅：只给测量与提醒，**不改写正文**。

        风格是软约束，偏离多少由人判断——这里不自动重写、不自动改档案，
        只把"实测指标 vs 档案基线"和需要人工逐条核对的约束摆出来。
        """
        links = self.session.exec(
            select(ProjectWritingStyleLink)
            .where(
                ProjectWritingStyleLink.project_id == project_id,
                ProjectWritingStyleLink.enabled == True,  # noqa: E712
            )
            .order_by(ProjectWritingStyleLink.priority.asc(), ProjectWritingStyleLink.created_at.asc())
        ).all()

        reports: list[dict[str, Any]] = []
        for link in links:
            profile = self.get(link.style_profile_id)
            if not profile or profile.status != WritingStyleProfileStatus.ACTIVE.value:
                continue
            scope = json.loads(link.stage_scope_json or "[]")
            if stage and scope and stage not in scope and "*" not in scope:
                continue
            baseline: dict[str, Any] | None = None
            provenance = json.loads(profile.provenance_json or "{}")
            if isinstance(provenance, dict):
                measurements = provenance.get("measurements")
                baseline = measurements if isinstance(measurements, dict) else None
            report = measure_style_deviation(
                text, json.loads(profile.profile_json or "{}"), baseline=baseline
            )
            reports.append(
                {
                    "profile_id": profile.id,
                    "profile_name": profile.name,
                    "intensity": link.intensity,
                    **report,
                }
            )

        if not reports:
            return {
                "success": True,
                "bound": False,
                "message": "该项目没有已激活的风格档案，跳过偏差审阅",
                "reports": [],
            }
        return {
            "success": True,
            "bound": True,
            "ok": all(item["ok"] for item in reports),
            "reports": reports,
        }

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

        profile_payload = {
            "version": 1,
            "dimensions": dimensions,
            "new_examples": data.get("new_examples") or [],
            "anti_template_constraints": data.get("anti_template_constraints") or [],
            "prohibited_source_material": data.get("prohibited_source_material") or [],
        }
        source_terms = [
            term
            for term in (str(snapshot.title or "").strip(), str(snapshot.author or "").strip())
            if term
        ]
        material_check = inspect_style_material(
            profile_payload, source_terms=source_terms, source_samples=samples
        )
        return self.create_profile(
            name=name or f"{str(snapshot.title or '来源')} 风格草稿",
            description="从来源快照自动提取的表达机制草稿，需审核后激活。",
            profile=profile_payload,
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
                # 来源专名留存：后续编辑与审核时用它复核是否带出来源材料。
                "source_terms": source_terms,
                "material_check": material_check,
            },
        )

    def list_projects_by_profile(self, profile_id: str) -> list[dict[str, Any]]:
        """反向查询：这个档案被绑到了哪些项目。

        正向接口（``runtime_profiles``）是"项目 → 风格"，管理视角还需要
        "风格 → 项目"：解绑前能看清影响范围，避免误停在用的档案。
        """
        from app.db.models.creative_project import CreativeProject

        links = self.session.exec(
            select(ProjectWritingStyleLink).where(
                ProjectWritingStyleLink.style_profile_id == profile_id
            )
        ).all()
        rows: list[dict[str, Any]] = []
        for link in links:
            project = self.session.get(CreativeProject, link.project_id)
            rows.append(
                {
                    "project_id": link.project_id,
                    "project_title": str(getattr(project, "title", "") or "") if project else "",
                    "enabled": bool(link.enabled),
                    "intensity": link.intensity,
                    "stage_scope": json.loads(link.stage_scope_json or "[]"),
                    "priority": link.priority,
                }
            )
        # 生效中的排前面，其次按优先级与项目名，便于一眼看到影响范围。
        rows.sort(key=lambda row: (not row["enabled"], -int(row["priority"] or 0), row["project_title"]))
        return rows

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
