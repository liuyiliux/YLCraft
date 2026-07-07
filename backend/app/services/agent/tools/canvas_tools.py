"""Canvas and relationship-graph tools exposed to the Agent Center."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.db.database import SessionLocal
from app.db.models.canvas import CanvasDocument as CanvasDocumentModel
from app.services.agent.registry import register_tool
from app.services.creative_project.service import CreativeProjectService, loads_json


def _json_object(value: str | dict[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return dict(value)
    parsed = loads_json(value, fallback={})
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return parsed


def _project_canvas_summary(canvas: dict[str, Any]) -> dict[str, Any]:
    nodes = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
    edges = canvas.get("edges") if isinstance(canvas.get("edges"), list) else []
    return {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "updated_at": canvas.get("updated_at") or canvas.get("updatedAt") or "",
        "node_types": sorted({str(node.get("type") or "unknown") for node in nodes if isinstance(node, dict)}),
    }


def _creative_canvas_summary(document: dict[str, Any]) -> dict[str, Any]:
    nodes = document.get("nodes") if isinstance(document.get("nodes"), list) else []
    connections = document.get("connections") if isinstance(document.get("connections"), list) else []
    return {
        "nodes_count": len(nodes),
        "connections_count": len(connections),
        "updated_at": document.get("updatedAt") or document.get("updated_at") or "",
        "node_types": sorted({str(node.get("type") or "unknown") for node in nodes if isinstance(node, dict)}),
    }


def _canvas_row_to_document(row: CanvasDocumentModel) -> dict[str, Any]:
    document = dict(row.document_json or {})
    document["id"] = str(row.id)
    document["title"] = row.title
    document["description"] = row.description or document.get("description") or ""
    if row.project_id:
        document["projectId"] = str(row.project_id)
    document["updatedAt"] = row.updated_at.isoformat() if row.updated_at else document.get("updatedAt") or ""
    document["createdAt"] = row.created_at.isoformat() if row.created_at else document.get("createdAt") or ""
    return document


def _save_canvas_row(session, row: CanvasDocumentModel, document: dict[str, Any]) -> CanvasDocumentModel:
    now = datetime.utcnow()
    row.title = str(document.get("title") or row.title or "创作画布")
    row.description = str(document.get("description") or "")
    project_id = str(document.get("projectId") or "").strip() or None
    row.project_id = project_id
    document["id"] = str(row.id)
    document["title"] = row.title
    document["description"] = row.description
    if project_id:
        document["projectId"] = project_id
    else:
        document.pop("projectId", None)
    document["updatedAt"] = now.isoformat()
    row.document_json = document
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _log_canvas_operation(
    service: CreativeProjectService,
    *,
    project_id: str,
    operation: str,
    request_payload: dict[str, Any],
    canvas: dict[str, Any],
) -> None:
    service.log_generation(
        project_id=project_id,
        scene="agent_canvas",
        ref_id=operation,
        stage="canvas_operation",
        status="success",
        provider="agent",
        model="tool",
        prompt=f"Agent canvas operation: {operation}",
        request_payload=request_payload,
        normalized={
            "operation": operation,
            "summary": _project_canvas_summary(canvas),
        },
    )
    service.session.commit()


@register_tool(
    name="list_creative_canvas_documents",
    description="List persisted free-form creative canvas documents from /canvas.",
    category="canvas",
    examples=["列出创作画布文档", "查看这个项目有哪些自由画布"],
    input_schema_note="project_id is optional; limit defaults to 20 and maxes at 50.",
    output_schema_note="Returns success, total and documents with id/title/projectId/summary.",
    risk_level="read",
    output_type="creative_canvas_document_list",
    description_short="List persisted free-form creative canvas documents.",
)
async def list_creative_canvas_documents(project_id: str = "", limit: int = 20) -> dict[str, Any]:
    from sqlmodel import select

    max_limit = max(1, min(int(limit or 20), 50))
    with SessionLocal() as session:
        query = select(CanvasDocumentModel).order_by(CanvasDocumentModel.updated_at.desc()).limit(max_limit)
        if project_id:
            query = query.where(CanvasDocumentModel.project_id == project_id)
        rows = session.exec(query).all()
        documents = [_canvas_row_to_document(row) for row in rows]
        return {
            "success": True,
            "total": len(documents),
            "documents": [
                {
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "projectId": doc.get("projectId", ""),
                    "summary": _creative_canvas_summary(doc),
                }
                for doc in documents
            ],
        }


@register_tool(
    name="get_creative_canvas_document",
    description="Read one persisted free-form creative canvas document from /canvas.",
    category="canvas",
    examples=["读取这个创作画布", "查看画布节点和连线"],
    input_schema_note="document_id is required.",
    output_schema_note="Returns success, document and summary.",
    risk_level="read",
    output_type="creative_canvas_document_detail",
    description_short="Read a persisted free-form creative canvas document.",
)
async def get_creative_canvas_document(document_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            return {"success": False, "error": "canvas document not found", "document_id": document_id}
        document = _canvas_row_to_document(row)
        return {
            "success": True,
            "document": document,
            "summary": _creative_canvas_summary(document),
        }


@register_tool(
    name="apply_creative_canvas_operations",
    description="Apply add_node, update_node, delete_node, connect_nodes, disconnect_nodes and set_viewport operations to a persisted free-form creative canvas document.",
    category="canvas",
    examples=["把规划好的 Prompt 和生图节点写入自由画布", "连接素材节点到生图节点"],
    input_schema_note="document_id and operations_json are required. operations_json must be a JSON array of operation objects.",
    output_schema_note="Returns success, document_id, applied_count, skipped_count, document and summary.",
    risk_level="write",
    output_type="creative_canvas_operations_result",
    description_short="Apply operations to a persisted free-form creative canvas document.",
)
async def apply_creative_canvas_operations(document_id: str, operations_json: str) -> dict[str, Any]:
    operations = json.loads(operations_json or "[]")
    if not isinstance(operations, list):
        raise ValueError("operations_json must be a JSON array")

    applied = 0
    skipped = 0
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            return {"success": False, "error": "canvas document not found", "document_id": document_id}
        document = _canvas_row_to_document(row)
        nodes = list(document.get("nodes") if isinstance(document.get("nodes"), list) else [])
        connections = list(document.get("connections") if isinstance(document.get("connections"), list) else [])

        for op in operations:
            if not isinstance(op, dict):
                skipped += 1
                continue
            op_name = op.get("op")
            if op_name == "add_node" and isinstance(op.get("node"), dict):
                node = dict(op["node"])
                node.setdefault("id", f"agent-node-{uuid4().hex[:10]}")
                node.setdefault("position", {"x": 180, "y": 160})
                node.setdefault("width", 260)
                node.setdefault("height", 140)
                nodes.append(node)
                applied += 1
            elif op_name == "update_node" and op.get("nodeId") and isinstance(op.get("patch"), dict):
                node_id = str(op["nodeId"])
                patch = dict(op["patch"])
                next_nodes = [{**node, **patch} if str(node.get("id")) == node_id else node for node in nodes]
                applied += int(next_nodes != nodes)
                nodes = next_nodes
            elif op_name == "delete_node" and op.get("nodeId"):
                node_id = str(op["nodeId"])
                before = len(nodes)
                nodes = [node for node in nodes if str(node.get("id")) != node_id]
                connections = [
                    connection
                    for connection in connections
                    if str(connection.get("fromNodeId")) != node_id and str(connection.get("toNodeId")) != node_id
                ]
                applied += int(len(nodes) != before)
            elif op_name == "connect_nodes" and isinstance(op.get("connection"), dict):
                connection = dict(op["connection"])
                connection.setdefault("id", f"agent-conn-{uuid4().hex[:10]}")
                connections.append(connection)
                applied += 1
            elif op_name == "disconnect_nodes" and op.get("connectionId"):
                connection_id = str(op["connectionId"])
                before = len(connections)
                connections = [connection for connection in connections if str(connection.get("id")) != connection_id]
                applied += int(len(connections) != before)
            elif op_name == "set_viewport" and isinstance(op.get("viewport"), dict):
                document["viewport"] = dict(op["viewport"])
                applied += 1
            else:
                skipped += 1

        document["nodes"] = nodes
        document["connections"] = connections
        saved = _save_canvas_row(session, row, document)
        saved_document = _canvas_row_to_document(saved)
        return {
            "success": True,
            "document_id": document_id,
            "applied_count": applied,
            "skipped_count": skipped,
            "document": saved_document,
            "summary": _creative_canvas_summary(saved_document),
        }


@register_tool(
    name="get_project_canvas",
    description="Read the saved project relationship-graph canvas metadata for a creative project.",
    category="canvas",
    examples=["查看这个项目的关系图谱节点", "读取项目画布布局"],
    input_schema_note="project_id is required.",
    output_schema_note="Returns success, project_id, canvas and summary. This is the project relationship graph canvas, not the frontend-only free-form /canvas document.",
    risk_level="read",
    output_type="project_canvas_detail",
    description_short="Read a creative project's saved relationship-graph canvas.",
)
async def get_project_canvas(project_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        canvas = CreativeProjectService(session).get_canvas(project_id)
        return {
            "success": True,
            "project_id": project_id,
            "canvas": canvas,
            "summary": _project_canvas_summary(canvas),
        }


@register_tool(
    name="save_project_canvas",
    description="Replace the saved project relationship-graph canvas metadata for a creative project.",
    category="canvas",
    examples=["保存调整后的项目关系图谱布局", "把这组节点和边写回项目画布"],
    input_schema_note="project_id and canvas_json are required; canvas_json must be a JSON object with nodes/edges/viewport.",
    output_schema_note="Returns success, project_id, canvas and summary.",
    risk_level="write",
    output_type="project_canvas_result",
    description_short="Replace a creative project's saved relationship-graph canvas metadata.",
)
async def save_project_canvas(project_id: str, canvas_json: str) -> dict[str, Any]:
    canvas = _json_object(canvas_json, field_name="canvas_json")
    canvas.setdefault("nodes", [])
    canvas.setdefault("edges", [])
    canvas["updated_at"] = datetime.utcnow().isoformat()
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        saved = service.save_canvas(project_id, canvas)
        _log_canvas_operation(
            service,
            project_id=project_id,
            operation="save_project_canvas",
            request_payload={"canvas": canvas},
            canvas=saved,
        )
        return {
            "success": True,
            "project_id": project_id,
            "canvas": saved,
            "summary": _project_canvas_summary(saved),
        }


@register_tool(
    name="add_project_canvas_node",
    description="Append one node to a creative project's saved relationship-graph canvas metadata.",
    category="canvas",
    examples=["给项目关系图谱添加一个 Prompt 节点", "把角色卡节点加入项目画布"],
    input_schema_note="project_id and node_json are required; node_json must be a JSON object. id/x/y are optional.",
    output_schema_note="Returns success, project_id, node and canvas summary.",
    risk_level="write",
    output_type="project_canvas_node_result",
    description_short="Append a node to a creative project's saved relationship-graph canvas.",
)
async def add_project_canvas_node(project_id: str, node_json: str) -> dict[str, Any]:
    node = _json_object(node_json, field_name="node_json")
    node.setdefault("id", f"agent-node-{uuid4().hex[:10]}")
    node.setdefault("type", "note")
    node.setdefault("label", node.get("title") or "Agent node")
    node.setdefault("x", 120)
    node.setdefault("y", 120)
    node.setdefault("width", 220)
    node.setdefault("height", 96)
    node.setdefault("data", {})

    with SessionLocal() as session:
        service = CreativeProjectService(session)
        canvas = service.get_canvas(project_id)
        nodes = canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else []
        canvas["nodes"] = [*nodes, node]
        canvas.setdefault("edges", [])
        canvas["updated_at"] = datetime.utcnow().isoformat()
        saved = service.save_canvas(project_id, canvas)
        _log_canvas_operation(
            service,
            project_id=project_id,
            operation="add_project_canvas_node",
            request_payload={"node": node},
            canvas=saved,
        )
        return {
            "success": True,
            "project_id": project_id,
            "node": node,
            "summary": _project_canvas_summary(saved),
        }


@register_tool(
    name="connect_project_canvas_nodes",
    description="Append an edge between two nodes in a creative project's saved relationship-graph canvas metadata.",
    category="canvas",
    examples=["连接章节节点和分镜 Prompt 节点", "给素材节点建立 references 关系"],
    input_schema_note="project_id/from_node_id/to_node_id are required. relation defaults to references.",
    output_schema_note="Returns success, project_id, edge and canvas summary.",
    risk_level="write",
    output_type="project_canvas_edge_result",
    description_short="Connect two nodes in a creative project's saved relationship-graph canvas.",
)
async def connect_project_canvas_nodes(
    project_id: str,
    from_node_id: str,
    to_node_id: str,
    relation: str = "references",
    label: str = "",
) -> dict[str, Any]:
    edge = {
        "id": f"agent-edge-{uuid4().hex[:10]}",
        "from": from_node_id,
        "to": to_node_id,
        "type": relation or "references",
        "label": label or "",
    }
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        canvas = service.get_canvas(project_id)
        canvas.setdefault("nodes", [])
        edges = canvas.get("edges") if isinstance(canvas.get("edges"), list) else []
        canvas["edges"] = [*edges, edge]
        canvas["updated_at"] = datetime.utcnow().isoformat()
        saved = service.save_canvas(project_id, canvas)
        _log_canvas_operation(
            service,
            project_id=project_id,
            operation="connect_project_canvas_nodes",
            request_payload={"edge": edge},
            canvas=saved,
        )
        return {
            "success": True,
            "project_id": project_id,
            "edge": edge,
            "summary": _project_canvas_summary(saved),
        }


@register_tool(
    name="apply_project_canvas_operations",
    description="Apply basic add_node, update_node, delete_node, connect_nodes and disconnect_nodes operations to a creative project's saved relationship-graph canvas metadata.",
    category="canvas",
    examples=["批量把 Agent 规划的节点和连线写入项目关系图谱"],
    input_schema_note="project_id and operations_json are required. operations_json must be a JSON array of operation objects.",
    output_schema_note="Returns success, project_id, applied_count, skipped_count, canvas and summary.",
    risk_level="write",
    output_type="project_canvas_operations_result",
    description_short="Apply basic operations to a creative project's saved relationship-graph canvas.",
)
async def apply_project_canvas_operations(project_id: str, operations_json: str) -> dict[str, Any]:
    operations = json.loads(operations_json or "[]")
    if not isinstance(operations, list):
        raise ValueError("operations_json must be a JSON array")

    applied = 0
    skipped = 0
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        canvas = service.get_canvas(project_id)
        nodes = list(canvas.get("nodes") if isinstance(canvas.get("nodes"), list) else [])
        edges = list(canvas.get("edges") if isinstance(canvas.get("edges"), list) else [])

        for op in operations:
            if not isinstance(op, dict):
                skipped += 1
                continue
            op_name = op.get("op")
            if op_name == "add_node" and isinstance(op.get("node"), dict):
                node = dict(op["node"])
                node.setdefault("id", f"agent-node-{uuid4().hex[:10]}")
                nodes.append(node)
                applied += 1
            elif op_name == "update_node" and op.get("nodeId") and isinstance(op.get("patch"), dict):
                node_id = str(op["nodeId"])
                patch = dict(op["patch"])
                next_nodes = [{**node, **patch} if str(node.get("id")) == node_id else node for node in nodes]
                applied += int(next_nodes != nodes)
                nodes = next_nodes
            elif op_name == "delete_node" and op.get("nodeId"):
                node_id = str(op["nodeId"])
                before = len(nodes)
                nodes = [node for node in nodes if str(node.get("id")) != node_id]
                edges = [edge for edge in edges if str(edge.get("from")) != node_id and str(edge.get("to")) != node_id]
                applied += int(len(nodes) != before)
            elif op_name == "connect_nodes" and isinstance(op.get("connection"), dict):
                connection = dict(op["connection"])
                connection.setdefault("id", f"agent-edge-{uuid4().hex[:10]}")
                edges.append(connection)
                applied += 1
            elif op_name == "disconnect_nodes" and op.get("connectionId"):
                connection_id = str(op["connectionId"])
                before = len(edges)
                edges = [edge for edge in edges if str(edge.get("id")) != connection_id]
                applied += int(len(edges) != before)
            else:
                skipped += 1

        canvas["nodes"] = nodes
        canvas["edges"] = edges
        canvas["updated_at"] = datetime.utcnow().isoformat()
        saved = service.save_canvas(project_id, canvas)
        _log_canvas_operation(
            service,
            project_id=project_id,
            operation="apply_project_canvas_operations",
            request_payload={"operations": operations, "applied_count": applied, "skipped_count": skipped},
            canvas=saved,
        )
        return {
            "success": True,
            "project_id": project_id,
            "applied_count": applied,
            "skipped_count": skipped,
            "canvas": saved,
            "summary": _project_canvas_summary(saved),
        }
