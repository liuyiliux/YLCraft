"""结构化世界地图服务。

地图是独立于通用 ``world_asset`` 事实卡的空间关系文档：区域、据点、路线
分别承载层级、位置与连通关系。写入用 ``revision`` 做 CAS，避免并发覆盖。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.db.models.novel_source import WorldMapDocument
from app.services.creative_project.service import dumps_json, loads_json

# 空间层（layers）由项目/世界观自定义（叫「主世界/天界/冥界」还是别的、有几层、
# 甚至完全不分层都由数据决定），不写死枚举：``layers`` 缺省或为空时视为单层地图，
# 节点 ``layer`` 为空即未分层。
DEFAULT_MAP_JSON = {"regions": [], "nodes": [], "routes": [], "layers": []}


class WorldMapService:
    """世界地图文档的读取与版本化写入。"""

    def __init__(self, session: Session):
        self.session = session

    def list_maps(
        self,
        *,
        project_id: str | None = None,
        snapshot_id: str | None = None,
        limit: int = 50,
    ) -> list[WorldMapDocument]:
        statement = select(WorldMapDocument)
        if project_id:
            statement = statement.where(WorldMapDocument.project_id == project_id)
        if snapshot_id:
            statement = statement.where(WorldMapDocument.snapshot_id == snapshot_id)
        statement = statement.order_by(WorldMapDocument.updated_at.desc()).limit(  # type: ignore[attr-defined]
            max(1, min(int(limit or 50), 200))
        )
        return list(self.session.exec(statement).all())

    def get_map(self, map_id: str) -> WorldMapDocument | None:
        return self.session.get(WorldMapDocument, map_id)

    def create_map(
        self,
        *,
        title: str,
        project_id: str | None = None,
        snapshot_id: str | None = None,
        map_json: dict[str, Any] | None = None,
    ) -> WorldMapDocument:
        document = WorldMapDocument(
            title=(title or "").strip() or "世界地图",
            project_id=project_id or None,
            snapshot_id=snapshot_id or None,
            map_json=dumps_json(map_json or DEFAULT_MAP_JSON),
            revision=1,
        )
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def update_map(
        self,
        map_id: str,
        *,
        map_json: dict[str, Any],
        expected_revision: int,
        title: str = "",
    ) -> WorldMapDocument:
        """按 revision 做 CAS 更新；版本不一致时抛错，避免覆盖他人编辑。"""
        document = self.session.get(WorldMapDocument, map_id)
        if not document:
            raise ValueError("地图文档不存在")
        if int(document.revision or 1) != int(expected_revision or 0):
            raise ValueError(
                f"地图已被修改，当前版本为 {document.revision}，请刷新后重试"
            )
        document.map_json = dumps_json(map_json or DEFAULT_MAP_JSON)
        if title and title.strip():
            document.title = title.strip()
        document.revision = int(document.revision or 1) + 1
        document.updated_at = datetime.now()
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def delete_map(self, map_id: str) -> None:
        document = self.session.get(WorldMapDocument, map_id)
        if not document:
            raise ValueError("地图文档不存在")
        self.session.delete(document)
        self.session.commit()

    def create_map_from_project_places(self, project_id: str) -> WorldMapDocument:
        """把项目的地点实体（world_entities.entity_type=place）转成地图据点初稿。

        已有地图时把未出现的地点追加进最新一张，避免重复；没有地图则新建一张。
        只写入结构化节点（名字/摘要），具体坐标由用户拖拽精修。
        """
        from app.db.models.novel_source import WorldEntity

        places = self.session.exec(
            select(WorldEntity)
            .where(
                WorldEntity.project_id == project_id,
                WorldEntity.entity_type == "place",
            )
            .order_by(WorldEntity.name)
        ).all()
        if not places:
            raise ValueError("该项目还没有地点实体，请先在世界提取中确认写入地点")

        existing = self.list_maps(project_id=project_id, limit=1)
        if existing:
            document = existing[0]
            data = loads_json(document.map_json, DEFAULT_MAP_JSON)
        else:
            document = WorldMapDocument(
                title="世界地图",
                project_id=project_id,
                map_json=dumps_json(DEFAULT_MAP_JSON),
                revision=1,
            )
            self.session.add(document)
            data = DEFAULT_MAP_JSON
        if not isinstance(data, dict):
            data = DEFAULT_MAP_JSON

        nodes = [item for item in (data.get("nodes") or []) if isinstance(item, dict)]
        # 实体为中心：优先按 entity_id 判重（地点实体改名后不会重复生成据点），
        # 历史据点没有 entity_id 时回退到名称匹配。
        existing_entity_ids = {
            str(item.get("entity_id") or "").strip()
            for item in nodes
            if str(item.get("entity_id") or "").strip()
        }
        existing_names = {str(item.get("name") or "").strip() for item in nodes}

        def _is_new_place(place: Any) -> bool:
            name = str(place.name or "").strip()
            if not name:
                return False
            if place.id in existing_entity_ids:
                return False
            return name not in existing_names

        added: list[dict[str, Any]] = []
        # 环形/径向散布：N≤1 居中，N≤3 小弧，N≥4 围圆心排开
        # （避免之前 5 个点挤在 y=15 一行的情况）。
        import math
        total = sum(1 for place in places if _is_new_place(place))
        angles: list[float] = []
        radius = 0.0  # 单点居中使用；其余分支按数量设置
        if total <= 1:
            angles = [math.pi / 2]  # 单点居中
        elif total <= 3:
            radius = 18
            step = math.pi / 2  # 在下方半圆均分
            start = math.pi / 2 - step * (total - 1) / 2
            for i in range(total):
                angles.append(start + step * i)
        else:
            radius = min(38, 18 + total * 2)
            for i in range(total):
                # 起点 12 点钟方向，均匀环布（-π/2 偏移让首点朝上）
                angles.append(-math.pi / 2 + 2 * math.pi * i / total)

        idx = 0
        for place in places:
            if not _is_new_place(place):
                continue
            name = str(place.name or "").strip()
            attributes = loads_json(place.attributes_json, {})
            angle = angles[idx]
            added.append(
                {
                    "id": f"{place.id[:8]}-{idx}",
                    # 引用地点实体而不是复制事实：正典仍在 world_entities /
                    # world_asset，地图只持有空间位置与实体指针。
                    "entity_id": place.id,
                    "name": name,
                    "kind": str(attributes.get("kind") or "地点")[:20],
                    "x": round(50 + radius * math.cos(angle), 1),
                    "y": round(50 + radius * math.sin(angle), 1),
                    "region_id": None,
                    # 未分层：空间层由用户在层管理里按世界观自定义后归入。
                    "layer": None,
                    # 摘要快照只用于离线渲染与导出，不是事实来源。
                    "description": str(place.summary or "")[:200],
                }
            )
            idx += 1
        if not added:
            raise ValueError("地点实体都已在地图上，无需重复生成")

        nodes.extend(added)
        data = dict(data)
        data["nodes"] = nodes
        document.map_json = dumps_json(data)
        document.revision = int(document.revision or 1) + 1
        document.updated_at = datetime.now()
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def resolve_nodes_with_entities(self, map_id: str) -> dict[str, Any]:
        """把地图据点与地点实体关联起来：引用不复制，实体信息按需回查。

        返回每个据点的 ``node`` / ``entity`` / ``relations``。没有 ``entity_id``
        或实体已不存在的据点 ``entity`` 为 ``None``——那是「游离标记」，
        前端应提示去关联实体，而不是把它当作正典。
        """
        from app.db.models.novel_source import WorldEntity, WorldEntityRelation

        document = self.session.get(WorldMapDocument, map_id)
        if not document:
            raise ValueError("地图文档不存在")

        data = loads_json(document.map_json, DEFAULT_MAP_JSON)
        if not isinstance(data, dict):
            data = DEFAULT_MAP_JSON
        nodes = [item for item in (data.get("nodes") or []) if isinstance(item, dict)]

        entity_ids = [
            str(item.get("entity_id") or "").strip()
            for item in nodes
            if str(item.get("entity_id") or "").strip()
        ]
        entities: dict[str, Any] = {}
        relations: dict[str, list[Any]] = {}
        if entity_ids:
            for row in self.session.exec(
                select(WorldEntity).where(col(WorldEntity.id).in_(entity_ids))
            ).all():
                entities[row.id] = row
            for rel in self.session.exec(
                select(WorldEntityRelation).where(
                    or_(
                        col(WorldEntityRelation.source_entity_id).in_(entity_ids),
                        col(WorldEntityRelation.target_entity_id).in_(entity_ids),
                    )
                )
            ).all():
                relations.setdefault(rel.source_entity_id, []).append(rel)
                if rel.target_entity_id != rel.source_entity_id:
                    relations.setdefault(rel.target_entity_id, []).append(rel)

        items: list[dict[str, Any]] = []
        orphans: list[str] = []
        for node in nodes:
            entity_id = str(node.get("entity_id") or "").strip()
            entity = entities.get(entity_id)
            if not entity:
                orphans.append(str(node.get("id") or ""))
            items.append(
                {
                    "node": node,
                    "entity_id": entity_id or None,
                    "entity": serialize_entity_ref(entity) if entity else None,
                    "relations": [
                        serialize_relation_ref(rel) for rel in relations.get(entity_id, [])
                    ],
                }
            )

        return {
            "map_id": document.id,
            "title": document.title,
            "revision": document.revision,
            "nodes": items,
            "orphan_node_ids": orphans,
        }


def build_map_export(
    document: WorldMapDocument,
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """结构化导出：据点带 ``entity_id`` / ``evidence``，供外部工具与备份使用。

    导出的是「结构化点位数据」，不是图片：空间关系 + 实体引用 + 证据锚点。
    ``confidence`` 暂无来源（实体层还没有置信度字段），恒为 ``None``（OQ-01）。
    """
    data = loads_json(document.map_json, DEFAULT_MAP_JSON)
    if not isinstance(data, dict):
        data = DEFAULT_MAP_JSON

    by_node_id: dict[str, dict[str, Any]] = {}
    for row in (resolved or {}).get("nodes") or []:
        node = row.get("node") or {}
        by_node_id[str(node.get("id") or "")] = row

    nodes: list[dict[str, Any]] = []
    for raw in [item for item in (data.get("nodes") or []) if isinstance(item, dict)]:
        row = by_node_id.get(str(raw.get("id") or "")) or {}
        entity = row.get("entity") or {}
        nodes.append(
            {
                "id": raw.get("id"),
                "name": raw.get("name"),
                "kind": raw.get("kind"),
                "x": raw.get("x"),
                "y": raw.get("y"),
                "region_id": raw.get("region_id"),
                # 空间层引用：层集合由地图数据自定义（layers），节点 layer 为空即未分层。
                "layer": raw.get("layer"),
                # 实体引用：正典不在地图里，这里只存指针。
                "entity_id": raw.get("entity_id") or entity.get("id"),
                "description": raw.get("description") or "",
                "evidence": entity.get("evidence") or [],
                "confidence": None,  # OQ-01：实体层暂无置信度字段
                "relations": row.get("relations") or [],
            }
        )

    return {
        "map": {
            "map_id": document.id,
            "title": document.title,
            "revision": document.revision,
        },
        # 空间层定义随导出带上（数据驱动，不写死枚举）。
        "layers": [
            item for item in (data.get("layers") or []) if isinstance(item, dict)
        ],
        "nodes": nodes,
        "regions": [
            item for item in (data.get("regions") or []) if isinstance(item, dict)
        ],
        "routes": [item for item in (data.get("routes") or []) if isinstance(item, dict)],
        "notes": ["confidence 待实体层补置信度字段（OQ-01），当前恒为 null"],
    }


def serialize_entity_ref(entity: Any) -> dict[str, Any]:
    """地图侧的实体引用视图。

    只暴露详情面板与导出需要的字段，不复制事实本身：正典仍在
    ``world_entities`` / ``world_asset``，地图侧按需回查。
    """
    return {
        "id": entity.id,
        "name": entity.name,
        "domain": entity.domain,
        "entity_type": entity.entity_type,
        "summary": entity.summary,
        "attributes": loads_json(entity.attributes_json, {}),
        "evidence": loads_json(entity.evidence_json, []),
        "fact_layer": entity.fact_layer,
        "is_locked": entity.is_locked,
    }


def serialize_relation_ref(relation: Any) -> dict[str, Any]:
    """地图侧的实体关系视图（类型化关系，供详情面板展示关联）。"""
    return {
        "id": relation.id,
        "source_entity_id": relation.source_entity_id,
        "target_entity_id": relation.target_entity_id,
        "relation_type": relation.relation_type,
        "note": relation.note,
        "evidence": loads_json(relation.evidence_json, []),
        "is_directed": relation.is_directed,
    }


def serialize_map(document: WorldMapDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "project_id": document.project_id,
        "snapshot_id": document.snapshot_id,
        "title": document.title,
        "map": loads_json(document.map_json, DEFAULT_MAP_JSON),
        "revision": document.revision,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


#: SVG 画布尺寸；节点坐标按 0-100 输入，等比例映射到画布。
SVG_WIDTH = 800
SVG_HEIGHT = 600


def render_map_svg(document: WorldMapDocument) -> str:
    """把结构化地图确定性地渲染为 SVG。

    本地渲染，不调用模型也不依赖外部生图供应商：据点为圆点与名称，
    路线为连线，所属区域不同的据点用不同色相区分。空地图返回空白画布。
    """
    data = loads_json(document.map_json, DEFAULT_MAP_JSON)
    if not isinstance(data, dict):
        data = DEFAULT_MAP_JSON
    nodes = [item for item in (data.get("nodes") or []) if isinstance(item, dict)]
    routes = [item for item in (data.get("routes") or []) if isinstance(item, dict)]
    regions = [item for item in (data.get("regions") or []) if isinstance(item, dict)]

    def project(value: Any, scale: float) -> float:
        try:
            return max(0.0, min(float(value), 100.0)) * scale
        except (TypeError, ValueError):
            return 0.0

    positions: dict[str, tuple[float, float]] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        positions[node_id] = (
            project(node.get("x"), SVG_WIDTH / 100),
            project(node.get("y"), SVG_HEIGHT / 100),
        )

    region_order = {str(region.get("id") or ""): index for index, region in enumerate(regions)}
    hues = ["#1677ff", "#52c41a", "#fa8c16", "#eb2f96", "#722ed1", "#13c2c2"]

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="16" y="28" font-size="16" fill="#1f2937">{_escape(str(document.title or "世界地图"))}</text>',
    ]

    for route in routes:
        start = positions.get(str(route.get("from") or ""))
        end = positions.get(str(route.get("to") or ""))
        if not start or not end:
            continue
        parts.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" '
            'stroke="#94a3b8" stroke-width="2"/>'
        )

    for node in nodes:
        node_id = str(node.get("id") or "")
        point = positions.get(node_id)
        if not point:
            continue
        color = hues[region_order.get(str(node.get("region_id") or ""), 0) % len(hues)]
        parts.append(f'<circle cx="{point[0]:.1f}" cy="{point[1]:.1f}" r="8" fill="{color}"/>')
        label = _escape(str(node.get("name") or "未命名"))
        parts.append(
            f'<text x="{point[0] + 12:.1f}" y="{point[1] + 4:.1f}" font-size="12" fill="#1f2937">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _escape(value: str) -> str:
    """SVG 文本转义，避免地图名称/据点名破坏 XML 结构。"""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _coordinate_band(x: float, y: float) -> str:
    """把 0-100 画布坐标折叠成低粒度方位短语，供提示词描述相对位置。"""
    row = (
        "地图顶部" if y < 20
        else "地图上部" if y < 42
        else "地图中部" if y <= 58
        else "地图下部" if y < 80
        else "地图底部"
    )
    col = (
        "左侧" if x < 20
        else "偏左" if x < 42
        else "正中" if x <= 58
        else "偏右" if x < 80
        else "右侧"
    )
    return f"{row}、{col}"


def _route_heading(
    start: tuple[float, float], end: tuple[float, float]
) -> str:
    """按两节点坐标给出路线走向的方位词（用于提示词）。

    x 向右增大、y 向下增大、画面顶部为北：终点相对起点在下方即更靠南。
    """
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    if abs(dx) < 12 and abs(dy) < 12:
        return "短距相接"
    if abs(dx) < 12:
        return "北向" if dy < 0 else "南向"
    if abs(dy) < 12:
        return "东向" if dx > 0 else "西向"
    if dx > 0 and dy < 0:
        return "东北"
    if dx > 0 and dy > 0:
        return "东南"
    if dx < 0 and dy < 0:
        return "西北"
    return "西南"


def build_map_visual_prompt(document: WorldMapDocument, *, style: str = "") -> str:
    """把结构化地图确定性转成生图 prompt（不调用模型）。

    生成成图只是派生的视觉资产，不是地图真相来源；结构化 ``map_json`` 才是正典。
    本函数只做「结构化数据 → 自然语言描述」的稳定转换，便于单测与可复现。
    提示词会写清坐标约定并为每个地点标注 (x,y) 与方位带，避免模型自由脑补
    相对位置导致「南北颠倒」。
    """
    data = loads_json(document.map_json, DEFAULT_MAP_JSON)
    if not isinstance(data, dict):
        data = DEFAULT_MAP_JSON

    nodes = [item for item in (data.get("nodes") or []) if isinstance(item, dict)]
    routes = [item for item in (data.get("routes") or []) if isinstance(item, dict)]
    regions = [item for item in (data.get("regions") or []) if isinstance(item, dict)]
    layer_rows = [item for item in (data.get("layers") or []) if isinstance(item, dict)]

    region_name_by_id: dict[str, str] = {}
    for region in regions:
        region_name_by_id[str(region.get("id") or "")] = str(region.get("name") or "").strip()
    layer_name_by_id: dict[str, str] = {}
    for layer in layer_rows:
        layer_name_by_id[str(layer.get("id") or "")] = str(layer.get("name") or "").strip()

    def coords(node: dict[str, Any]) -> tuple[float, float] | None:
        try:
            return float(node.get("x")), float(node.get("y"))
        except (TypeError, ValueError):
            return None

    # 统一坐标约定：x 向右增大、y 向下增大、画面顶部为北。
    parts: list[str] = [
        f"一张世界地图，标题「{str(document.title or '世界地图')}」。",
        "坐标系约定：画布坐标 (x,y) 均取 0-100，x 向右增大、y 向下增大，画面顶部为北"
        "（y 值越小越靠上/越靠北）。下方每个地点的 (x,y) 标注即其应在画面上放置的位置："
        "y≈80 的地点必须明显画在 y≈20 地点的下方，地名与图标不得脱离该相对布局，"
        "不要按名称里的「南/北/东/西」猜测位置。",
    ]

    named_nodes = [
        node for node in nodes
        if str(node.get("name") or "").strip() and coords(node) is not None
    ]
    # 按 y（上下）为主、x（左右）为次的顺序列出，方便模型理解上下层级。
    ordered = sorted(named_nodes, key=lambda node: (coords(node)[1], coords(node)[0]))

    node_lines: list[str] = []
    for node in ordered:
        px, py = coords(node) or (0.0, 0.0)
        name = str(node.get("name") or "").strip()
        line = f"「{name}」(x={px:.0f}, y={py:.0f})：位于{_coordinate_band(px, py)}"
        region_id = str(node.get("region_id") or "")
        if region_id and region_name_by_id.get(region_id):
            line += f"，属区域「{region_name_by_id[region_id]}」"
        layer_id = str(node.get("layer") or "")
        if layer_id and layer_name_by_id.get(layer_id):
            line += f"，属位面「{layer_name_by_id[layer_id]}」"
        summary = str(node.get("description") or "").strip()
        if summary:
            line += f"；{summary[:40]}"
        node_lines.append(line)
    if node_lines:
        parts.append("图上需要放置的地点（严格按标注坐标决定相对位置）：")
        parts.extend(node_lines)

    region_names = [
        str(region.get("name") or "").strip()
        for region in regions
        if str(region.get("name") or "").strip()
    ]
    if region_names:
        parts.append("区域划分：" + "、".join(region_names) + "。")

    route_descs: list[str] = []
    for route in routes:
        from_id = str(route.get("from") or "").strip()
        to_id = str(route.get("to") or "").strip()
        start_node = next(
            (n for n in named_nodes if str(n.get("id") or "") == from_id), None
        )
        end_node = next((n for n in named_nodes if str(n.get("id") or "") == to_id), None)
        start_name = str(start_node.get("name") or "") if start_node else (from_id or "起点")
        end_name = str(end_node.get("name") or "") if end_node else (to_id or "终点")
        if start_node and end_node:
            heading = _route_heading(coords(start_node), coords(end_node))
            route_descs.append(f"{start_name}→{end_name}（走向{heading}）")
        else:
            route_descs.append(f"{start_name}—{end_name}")
    if route_descs:
        parts.append("通行路线：" + "、".join(route_descs) + "，连线不得穿过无关地点。")

    # 只描述空间结构与画面可读性，不再写死画风：
    # 现实题材（乡村/都市/科幻）套「羊皮纸·中土奇幻」会严重违和，
    # 画风交给风格预设与项目视觉基准（参考图）决定。
    parts.append(
        "俯视视角的地图制图，呈现上述区域与地点的相对方位和连通关系，"
        "包含山脉、森林、河流、海岸线等自然地形，城市与据点用图例图标标注，"
        "区域用虚线或色块边界区分，右下角配比例尺与罗盘玫瑰（北在上），"
        "重要路线用虚线标出。俯视视角，画面构图完整，地名清晰可读。"
    )
    if style and str(style).strip():
        parts.append(f"风格：{str(style).strip()}。")
    else:
        parts.append("不指定画风：按项目视觉基准（参考图）自适应，无参考图时采用克制的写实地图风格。")
    return "".join(parts)
