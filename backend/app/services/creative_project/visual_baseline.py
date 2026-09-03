"""项目视觉基准（visual baseline）。

视觉基准是**项目级**的一张基准图（如主角的画风参考、世界观的整体基调），
落地为 `project_asset_links` 中 `role="visual_baseline"` 的一条关联——不新增表，
也不复制素材文件，引用始终指向素材库节点。

纪律：
- 基准只作为生图的**参考图注入**（reference_asset_ids），不改写任何正典数据；
- 每个项目同时只有一张基准，重新设置即替换（避免多基准互相冲突）；
- 生图链路自动注入，调用方（页面与 Agent）无需各自记得传。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.db.models.creative_project import CreativeProject, ProjectAssetLink

logger = logging.getLogger("ylcraft.creative_project.visual_baseline")

VISUAL_BASELINE_ROLE = "visual_baseline"


def serialize_visual_baseline(link: ProjectAssetLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "asset_id": link.asset_id,
        "role": link.role,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


class VisualBaselineService:
    def __init__(self, session: Session):
        self.session = session

    def get(self, project_id: str) -> ProjectAssetLink | None:
        return self.session.exec(
            select(ProjectAssetLink)
            .where(
                ProjectAssetLink.project_id == project_id,
                ProjectAssetLink.role == VISUAL_BASELINE_ROLE,
            )
            .order_by(ProjectAssetLink.created_at.desc())
        ).first()

    def set_baseline(self, project_id: str, asset_id: str) -> ProjectAssetLink:
        """设置（或替换）项目视觉基准：一个项目只保留一张。"""
        project = self.session.get(CreativeProject, project_id)
        if not project:
            raise ValueError("创作项目不存在")
        asset_id = (asset_id or "").strip()
        if not asset_id:
            raise ValueError("缺少素材库节点 ID")

        # 替换语义：清理旧基准，保证「一个项目一张」。
        for row in self.session.exec(
            select(ProjectAssetLink).where(
                ProjectAssetLink.project_id == project_id,
                ProjectAssetLink.role == VISUAL_BASELINE_ROLE,
            )
        ).all():
            self.session.delete(row)

        link = ProjectAssetLink(
            id=uuid4().hex,
            project_id=project_id,
            asset_id=asset_id,
            role=VISUAL_BASELINE_ROLE,
            relation="references",
            created_at=datetime.now(),
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link

    def clear(self, project_id: str) -> None:
        rows = self.session.exec(
            select(ProjectAssetLink).where(
                ProjectAssetLink.project_id == project_id,
                ProjectAssetLink.role == VISUAL_BASELINE_ROLE,
            )
        ).all()
        for row in rows:
            self.session.delete(row)
        self.session.commit()


def resolve_visual_baseline_asset_ids(session: Session, project_id: str | None) -> list[str]:
    """取项目视觉基准的素材库 ID；无项目或无基准时返回空列表。

    生图链路调用它把基准自动注入参考图，找不到就静默跳过——基准是增强项，
    不应因为没设置而阻塞生图。
    """
    if not project_id:
        return []
    link = VisualBaselineService(session).get(project_id)
    return [link.asset_id] if link else []
