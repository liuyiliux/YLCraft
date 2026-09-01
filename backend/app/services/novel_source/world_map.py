"""结构化世界地图服务。

地图是独立于通用 ``world_asset`` 事实卡的空间关系文档：区域、据点、路线
分别承载层级、位置与连通关系。写入用 ``revision`` 做 CAS，避免并发覆盖。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.db.models.novel_source import WorldMapDocument
from app.services.creative_project.service import dumps_json, loads_json

DEFAULT_MAP_JSON = {"regions": [], "nodes": [], "routes": []}


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
        existing_names = {str(item.get("name") or "").strip() for item in nodes}
        added: list[dict[str, Any]] = []
        cols = 5
        for index, place in enumerate(places):
            name = str(place.name or "").strip()
            if not name or name in existing_names:
                continue
            attributes = loads_json(place.attributes_json, {})
            added.append(
                {
                    "id": f"{place.id[:8]}-{index}",
                    "name": name,
                    "kind": str(attributes.get("kind") or "地点")[:20],
                    "x": 15 + (index % cols) * 18,
                    "y": 15 + (index // cols) * 18,
                    "region_id": None,
                    "description": str(place.summary or "")[:200],
                }
            )
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


def build_map_visual_prompt(document: WorldMapDocument, *, style: str = "") -> str:
    """把结构化地图确定性转成生图 prompt（不调用模型）。

    生成成图只是派生的视觉资产，不是地图真相来源；结构化 ``map_json`` 才是正典。
    本函数只做「结构化数据 → 自然语言描述」的稳定转换，便于单测与可复现。
    """
    data = loads_json(document.map_json, DEFAULT_MAP_JSON)
    if not isinstance(data, dict):
        data = DEFAULT_MAP_JSON

    nodes = [item for item in (data.get("nodes") or []) if isinstance(item, dict)]
    routes = [item for item in (data.get("routes") or []) if isinstance(item, dict)]
    regions = [item for item in (data.get("regions") or []) if isinstance(item, dict)]

    node_name_by_id: dict[str, str] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        name = str(node.get("name") or "").strip()
        if node_id and name:
            node_name_by_id[node_id] = name

    parts: list[str] = [f"一张幻想世界地图，标题「{str(document.title or '世界地图')}」。"]

    region_names = [
        str(region.get("name") or "").strip()
        for region in regions
        if str(region.get("name") or "").strip()
    ]
    if region_names:
        parts.append("包含区域：" + "、".join(region_names) + "。")

    node_names = [name for name in node_name_by_id.values()]
    if node_names:
        parts.append("重要地点：" + "、".join(node_names) + "。")

    route_descs: list[str] = []
    for route in routes:
        start = node_name_by_id.get(str(route.get("from") or "")) or str(route.get("from") or "").strip()
        end = node_name_by_id.get(str(route.get("to") or "")) or str(route.get("to") or "").strip()
        if start and end:
            route_descs.append(f"{start}—{end}")
    if route_descs:
        parts.append("通行路线：" + "、".join(route_descs) + "。")

    parts.append("俯视视角、手绘奇幻地图风格、清晰的地名标注、比例尺与罗盘、自然地形过渡。")
    if style and str(style).strip():
        parts.append(f"风格：{str(style).strip()}。")
    return "".join(parts)
