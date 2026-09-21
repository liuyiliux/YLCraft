"""预演动作资产的读写与种子灌入。

与 `app/api/v1/previs.py` 的场景 CRUD 一致，这里用**同步** Session（`SessionLocal`）：
动作资产的读取路径是全同步的，没有外部调用，没必要为它引入 async。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.models.previs import PrevisMotionAsset
from app.services.previs.motion import recommended_speed_mps
from app.services.previs.motion_seed import assert_channels_known, seed_motion_specs

#: 内置动作的来源与许可。程序化生成的动作没有第三方素材，但**也要如实记录**——
#: 清单里每条动作都会显示来源与许可，"没写"与"没来源"必须能区分开。
ORIGIN_GENERATED = "YLCraft 程序化生成"
LICENSE_GENERATED = "项目自有（程序化生成，无第三方素材）"


def motion_to_dict(asset: PrevisMotionAsset, *, include_payload: bool = False) -> dict[str, Any]:
    """把动作资产转成接口结构。

    `license_status` 由**是否有许可记录**推导，不单独存字段：空许可标成 `unverified`
    （未记录许可），而不是假装已获授权；反过来也不会因为"没有外部来源"就拒绝入库。
    """
    payload = asset.payload_json if isinstance(asset.payload_json, dict) else {}
    channels = payload.get("channels") if isinstance(payload.get("channels"), dict) else {}
    data: dict[str, Any] = {
        "id": asset.id,
        "slug": asset.slug,
        "name": asset.name,
        "carrier": asset.carrier,
        "skeleton": asset.skeleton,
        "category": asset.category,
        "tags": list(asset.tags_json or []),
        "fps": asset.fps,
        "frame_count": asset.frame_count,
        "duration_seconds": asset.duration_seconds,
        "loopable": asset.loopable,
        "channels": sorted(channels.keys()),
        "recommended_speed_mps": recommended_speed_mps(payload, asset.duration_seconds),
        "origin": asset.origin,
        "license": asset.license,
        "license_url": asset.license_url,
        "license_status": "recorded" if asset.license else "unverified",
        "file_path": asset.file_path,
    }
    if include_payload:
        data["payload"] = payload
    return data


def list_motions(
    session: Session,
    *,
    carrier: Optional[str] = None,
    skeleton: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    active_only: bool = True,
) -> list[PrevisMotionAsset]:
    """按载体 / 兼容规格 / 分类 / 标签筛选动作。

    标签在 Python 侧过滤而不是走 JSONB 查询：动作条目是**个位数到几十条**的小表，
    为了标签去写 JSONB 的包含查询只会让 SQLite 测试与 Postgres 生产出现两套行为，
    而这里根本不需要索引。
    """
    query = select(PrevisMotionAsset)
    if active_only:
        query = query.where(PrevisMotionAsset.is_active == True)  # noqa: E712
    if carrier:
        query = query.where(PrevisMotionAsset.carrier == carrier)
    if skeleton:
        query = query.where(PrevisMotionAsset.skeleton == skeleton)
    if category:
        query = query.where(PrevisMotionAsset.category == category)
    rows = list(session.exec(query.order_by(PrevisMotionAsset.carrier, PrevisMotionAsset.slug)).all())
    if tag:
        wanted = str(tag).strip()
        rows = [row for row in rows if wanted in (row.tags_json or [])]
    return rows


def motion_carriers(session: Session) -> dict[str, str]:
    """`slug → carrier` 映射，供场景操作校验"动作引用是否存在、能否驱动这个对象"。

    为什么给场景校验用：`validate_operations` 是**纯函数**（不碰数据库，因此可完整单测），
    它需要的事实必须由调用方喂进来；工具层顺手查一次这里，就能把"动作不存在 / 载体不匹配"
    变成可读的拒绝原因，而不是让一个拼错的动作标识静静落库（前端下拉里没有它，表现为"选了没反应"）。

    只取**启用中**的动作：已停用的动作不该被新引用（历史场景里的旧引用由前端回落处理）。
    """
    rows = session.exec(
        select(PrevisMotionAsset.slug, PrevisMotionAsset.carrier).where(
            PrevisMotionAsset.is_active == True  # noqa: E712
        )
    ).all()
    return {str(slug): str(carrier or "") for slug, carrier in rows}


def get_motion(session: Session, identifier: str) -> Optional[PrevisMotionAsset]:
    """按 id 或 slug 取一条动作——slug 更稳定，允许外部（含 AI）用 slug 引用。"""
    if not identifier:
        return None
    row = session.get(PrevisMotionAsset, identifier)
    if row is not None:
        return row
    return session.exec(select(PrevisMotionAsset).where(PrevisMotionAsset.slug == identifier)).first()


def seed_default_motions(session: Session) -> dict[str, int]:
    """幂等灌入内置动作：按 `slug` 认，已存在则更新，不存在则创建。

    id 由 slug 派生（`motion-<slug>`）而不是随机：场景里存的是动作引用，重灌种子时
    引用不能失效；固定 id 同时让"重建库后引用仍然有效"成为可能。
    """
    created = 0
    updated = 0
    now = datetime.utcnow()
    for spec in seed_motion_specs():
        assert_channels_known(spec)
        existing = session.exec(
            select(PrevisMotionAsset).where(PrevisMotionAsset.slug == spec["slug"])
        ).first()
        target = existing or PrevisMotionAsset(id=f"motion-{spec['slug']}", slug=spec["slug"])
        target.name = spec["name"]
        target.carrier = spec["carrier"]
        target.skeleton = spec["skeleton"]
        target.category = spec["category"]
        target.tags_json = list(spec["tags"])
        target.fps = spec["fps"]
        target.frame_count = spec["frame_count"]
        target.duration_seconds = spec["duration_seconds"]
        target.loopable = spec["loopable"]
        target.payload_json = spec["payload"]
        target.origin = ORIGIN_GENERATED
        target.license = LICENSE_GENERATED
        target.license_url = None
        target.is_active = True
        target.updated_at = now
        if existing is None:
            target.created_at = now
            session.add(target)
            created += 1
        else:
            updated += 1
    session.commit()
    return {"created": created, "updated": updated}
