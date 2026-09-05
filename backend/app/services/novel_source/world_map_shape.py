"""区域形状语义参数：受控词表校验、LLM 推断与落库（阶段 4）。

纪律（决策 D-1，已定稿）：**几何由前端唯一实现**。后端与 Agent 不实现形状展开——
这里只产出/校验/保存语义参数（受控词表 + seed），顶点一律由
``frontend/src/utils/regionShape.ts`` 按「成员据点 + 参数 + seed」确定性展开。
因此本模块没有也不允许出现顶点计算。

- 显式参数：逐字段校验，越界回退默认并记录（宽松，不拒绝请求）；
- 未给参数：LLM 从「区域名 + 成员据点描述 + 项目题材」推断，同样以受控词表收敛；
- 落库走既有 revision CAS（``WorldMapService.update_map``），历史快照照常追加。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlmodel import Session

from app.db.models.novel_source import WorldMapDocument
from app.services.ai.service import get_ai_service
from app.services.ai.types import LLMMessage
from app.services.creative_project.service import loads_json
from app.services.novel_source.world_map import DEFAULT_MAP_JSON

logger = logging.getLogger(__name__)

# 受控词表：与 frontend/src/utils/regionShape.ts 的常量一一对应（改动必须两侧同步）。
NATURE_IMAGERY = ["平原", "森林", "山地", "丘陵", "湿地", "荒漠", "河谷", "海岸"]
SETTLEMENT_FORMS = ["圆形寨子", "带状街区", "散点村落", "环山聚落", "方形城邑", "沿河狭长"]
STRUCTURE_FORMS = ["城墙方形", "要塞星形", "港口半岛"]
SHAPE_SCALES = ["小", "中", "大"]
MAX_SHAPE_VERTICES = 64

DEFAULT_SHAPE_PARAMS: dict[str, Any] = {
    "nature": "平原",
    "settlement": "圆形寨子",
    "structure": "",
    "scale": "中",
    "irregularity": 0.4,
}

#: LLM 推断的提示词骨架：明确词表与 JSON 输出，禁止输出几何。
_SHAPE_INFERENCE_SYSTEM = (
    "你是小说世界地图的区域形状顾问。根据区域与成员据点的描述，"
    "为区域轮廓选择语义参数（不是几何坐标）。只输出一个 JSON 对象，"
    "字段：nature（自然意象）、settlement（聚落形态）、structure（人工构筑，"
    "没有则用空字符串）、scale（面积感：小/中/大）、irregularity（0~1 的数字）。"
    "不要输出任何顶点、坐标或多边形数据。"
)


def hash_seed(text: str) -> int:
    """FNV-1a 32bit，与前端 ``hashSeed`` 同算法：区域无 seed 时的稳定默认值。"""
    hashed = 2166136261
    for ch in str(text):
        hashed ^= ord(ch)
        hashed = (hashed * 16777619) & 0xFFFFFFFF
    return hashed


def normalize_shape_params(raw: Any) -> tuple[dict[str, Any], list[str]]:
    """把外部传入的参数收敛回受控词表。

    返回 ``(params, fallback_keys)``：越界字段回退默认并把键名记入
    ``fallback_keys``（调用方记日志 / 返回给调用方），不抛错。
    """
    source = raw if isinstance(raw, dict) else {}
    fallbacks: list[str] = []

    def pick(key: str, allowed: list[str], default: str) -> str:
        value = str(source.get(key) or "").strip()
        if value in allowed:
            return value
        if value:
            fallbacks.append(key)
        return default

    params: dict[str, Any] = {
        "nature": pick("nature", NATURE_IMAGERY, DEFAULT_SHAPE_PARAMS["nature"]),
        "settlement": pick(
            "settlement", SETTLEMENT_FORMS, DEFAULT_SHAPE_PARAMS["settlement"]
        ),
        # structure 允许为空（= 无人工构筑），但给了就必须在词表内。
        "structure": pick("structure", STRUCTURE_FORMS, ""),
        "scale": pick("scale", SHAPE_SCALES, DEFAULT_SHAPE_PARAMS["scale"]),
    }
    irregularity = source.get("irregularity")
    if isinstance(irregularity, (int, float)) and not isinstance(irregularity, bool):
        params["irregularity"] = round(max(0.0, min(1.0, float(irregularity))), 4)
    else:
        if irregularity not in (None, ""):
            fallbacks.append("irregularity")
        params["irregularity"] = DEFAULT_SHAPE_PARAMS["irregularity"]
    return params, fallbacks


def _extract_json_object(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象（容忍 ```json 代码围栏与前后闲话）。"""
    cleaned = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("LLM 输出中没有 JSON 对象")
        cleaned = cleaned[start : end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("LLM 输出的 JSON 不是对象")
    return parsed


async def infer_shape_params(
    *,
    region: dict[str, Any],
    members: list[dict[str, Any]],
    project_hint: str = "",
    provider: str = "",
    model: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """LLM 从区域描述推断语义参数，随后按受控词表收敛（越界回退 + 记日志）。"""
    ai = get_ai_service()
    if not ai.is_loaded():
        raise RuntimeError("AIService 未初始化，请先配置 LLM Provider")

    member_lines = [
        f"- {str(node.get('name') or '未命名')}：{str(node.get('description') or '')[:60]}".rstrip("：")
        for node in members[:20]
    ]
    user_text = (
        f"区域名：{str(region.get('name') or '未命名区域')}\n"
        f"区域类型：{str(region.get('kind') or '')}\n"
        f"区域描述：{str(region.get('description') or '')[:200]}\n"
        + (f"项目题材：{project_hint}\n" if project_hint.strip() else "")
        + (
            "成员据点：\n" + "\n".join(member_lines)
            if member_lines
            else "成员据点：暂无（按区域描述推断）"
        )
    )
    response = await ai.chat(
        messages=[
            LLMMessage(role="system", content=_SHAPE_INFERENCE_SYSTEM),
            LLMMessage(role="user", content=user_text),
        ],
        provider=provider or None,
        model=model or None,
        temperature=0.3,
        max_tokens=400,
    )
    if getattr(response, "success", True) is False:
        raise RuntimeError(getattr(response, "error", "") or "LLM 推断失败")
    content = str(getattr(response, "content", "") or "")
    try:
        raw_params = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM 未返回有效的参数 JSON：{exc}") from exc
    params, fallbacks = normalize_shape_params(raw_params)
    for key in fallbacks:
        logger.warning(
            "区域形状参数越界回退：region=%s key=%s raw=%r",
            region.get("id"),
            key,
            raw_params.get(key),
        )
    return params, fallbacks


async def generate_region_shape_params(
    session: Session,
    map_id: str,
    region_id: str,
    *,
    params: Any = None,
    seed: int | None = None,
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    """生成区域形状语义参数（预览用，**不落库**）。

    显式给 ``params`` 时直接校验返回；未给时调 LLM 推断。
    返回 ``region_id / name / params / seed / fallbacks / source``——
    不含顶点：几何由前端按 (成员据点, params, seed) 确定性展开（决策 D-1）。
    """
    document = session.get(WorldMapDocument, map_id)
    if not document:
        raise ValueError("地图文档不存在")
    data = loads_json(document.map_json, DEFAULT_MAP_JSON)
    if not isinstance(data, dict):
        data = dict(DEFAULT_MAP_JSON)
    regions = [item for item in (data.get("regions") or []) if isinstance(item, dict)]
    region = next((item for item in regions if str(item.get("id") or "") == region_id), None)
    if not region:
        raise ValueError(f"区域不存在：{region_id}")
    members = [
        item
        for item in (data.get("nodes") or [])
        if isinstance(item, dict) and str(item.get("region_id") or "") == region_id
    ]

    if params:
        normalized, fallbacks = normalize_shape_params(params)
        source = "explicit"
    else:
        project_hint = _project_hint(session, document.project_id)
        normalized, fallbacks = await infer_shape_params(
            region=region,
            members=members,
            project_hint=project_hint,
            provider=provider,
            model=model,
        )
        source = "llm"
    for key in fallbacks:
        logger.warning(
            "区域形状参数越界回退：region=%s key=%s source=%s", region_id, key, source
        )
    return {
        "map_id": map_id,
        "region_id": region_id,
        "name": str(region.get("name") or ""),
        "params": normalized,
        "seed": int(seed) if seed else hash_seed(region_id),
        "fallbacks": fallbacks,
        "source": source,
        # 明确告诉调用方：这里没有顶点，顶点由前端展开后预览。
        "vertices": [],
        "note": "顶点由前端 regionShape.ts 按 (成员据点, params, seed) 确定性展开（决策 D-1）",
    }


def set_region_shape(
    session: Session,
    map_id: str,
    region_id: str,
    *,
    params: dict[str, Any],
    seed: int,
    operator: str = "",
    overwrite: bool = False,
) -> WorldMapDocument:
    """把语义参数写入区域 ``shape``（CAS 落库，历史快照照常追加）。

    只写 ``mode/seed/params``，不写顶点——前端按参数确定性展开显示；
    用户之后在画布保存时顶点才会随 map_json 入库。手绘（manual）区域
    默认拒绝覆盖，``overwrite=True`` 才放行（旧顶点可从版本历史找回）。
    """
    from app.services.novel_source.world_map import WorldMapService, sanitize_map_json

    document = session.get(WorldMapDocument, map_id)
    if not document:
        raise ValueError("地图文档不存在")
    data = loads_json(document.map_json, DEFAULT_MAP_JSON)
    if not isinstance(data, dict):
        data = dict(DEFAULT_MAP_JSON)
    regions = [item for item in (data.get("regions") or []) if isinstance(item, dict)]
    region = next((item for item in regions if str(item.get("id") or "") == region_id), None)
    if not region:
        raise ValueError(f"区域不存在：{region_id}")
    current_shape = region.get("shape")
    if (
        isinstance(current_shape, dict)
        and str(current_shape.get("mode") or "") == "manual"
        and not overwrite
    ):
        raise ValueError(
            "该区域形状为手绘（manual）：覆盖需显式 overwrite=true，旧顶点可从版本历史找回"
        )
    region["shape"] = {
        "mode": "auto",
        "seed": int(seed),
        "params": params,
        # 顶点留空：前端展开显示，显式保存时才由前端写入（决策 D-1）。
        "vertices": [],
    }
    return WorldMapService(session).update_map(
        map_id,
        map_json=sanitize_map_json(data),
        expected_revision=int(document.revision or 1),
        operator=operator or "agent:generate_region_shape",
    )


def _project_hint(session: Session, project_id: str | None) -> str:
    """项目题材提示（尽力而为）：拿不到就跳过，不阻塞推断。"""
    if not project_id:
        return ""
    try:
        from app.db.models.creative_project import CreativeProject

        project = session.get(CreativeProject, project_id)
        if not project:
            return ""
        return " / ".join(
            part
            for part in [str(project.title or ""), str(project.project_type or "")]
            if part
        )
    except Exception:  # noqa: BLE001 题材只是提示，缺表/缺行都不该阻塞生成
        return ""


def shape_presets() -> dict[str, Any]:
    """受控词表总览：给 LLM / Agent 选值用（与前端 regionShape.ts 对应）。"""
    return {
        "nature": NATURE_IMAGERY,
        "settlement": SETTLEMENT_FORMS,
        "structure": STRUCTURE_FORMS,
        "scale": SHAPE_SCALES,
        "irregularity": {"min": 0, "max": 1, "default": DEFAULT_SHAPE_PARAMS["irregularity"]},
        "defaults": dict(DEFAULT_SHAPE_PARAMS),
        "max_vertices": MAX_SHAPE_VERTICES,
        "note": "AI/Agent 只产语义参数与 seed；顶点由前端按参数确定性展开（决策 D-1）",
    }
