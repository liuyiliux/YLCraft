"""
YLCraft — 角色管理 API

GET  /api/v1/characters          — 列出角色（支持过滤/搜索/分页）
POST /api/v1/characters          — 创建角色
GET  /api/v1/characters/{id}     — 获取角色详情
PUT  /api/v1/characters/{id}    — 更新角色
DELETE /api/v1/characters/{id}   — 删除角色
GET  /api/v1/characters/tags     — 获取所有自定义标签
POST /api/v1/characters/{id}/tags — 添加自定义标签
DELETE /api/v1/characters/{id}/tags/{tag} — 移除自定义标签
POST /api/v1/characters/{id}/favorite — 切换收藏状态
POST /api/v1/characters/{id}/portrait/generate — AI 生成立绘（自动入资产中枢）
POST /api/v1/characters/{id}/portrait/upgrade — 把现有立绘升级到资产中枢
"""

from __future__ import annotations

import logging
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.database import get_async_session
from app.db.models.creative_project import CreativeProject, ProjectGenerationLog, ProjectStateEntry
from app.services.character.service import CharacterService
from app.services.platform_log import service as platform_log
from app.services.creative_project.service import dumps_json, loads_json
from app.db.models.character import CharacterSourceType, CharacterRole, CharacterRelationship, Character, CharacterWorkflowSource

router = APIRouter()


def _portrait_event_payload(
    character: Character,
    req: PortraitGenerateRequest,
    prompt: str,
    negative_prompt: str,
    preset: str,
) -> dict:
    """角色立绘生图的事件请求摘要，保留角色溯源信息。"""
    return {
        "character_id": character.id,
        "character_name": character.name,
        "preset": preset,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": req.size or "",
        "n": req.n or 1,
        "reference_images_count": len(req.reference_images or []),
        "reference_images": req.reference_images or [],
    }


def _portrait_retry_payload(
    req: PortraitGenerateRequest,
    prompt: str,
    negative_prompt: str,
) -> dict:
    """失败重发所需的原始生图参数，字段与 ImageGenerationRequest 对齐。

    重发只重新出图，不会回写角色或资产中枢。
    """
    return {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": req.size or "1024x1024",
        "n": req.n or 1,
        "provider": req.provider or "",
        "model": req.model or "",
        "reference_images": list(req.reference_images or []),
    }


async def _write_project_generation_log(session, **kwargs) -> ProjectGenerationLog:
    log = ProjectGenerationLog(
        scene=kwargs.get("scene", "creative_project"),
        project_id=kwargs.get("project_id"),
        content_id=kwargs.get("content_id"),
        ref_id=kwargs.get("ref_id"),
        stage=kwargs.get("stage", ""),
        provider=kwargs.get("provider", "") or "",
        model=kwargs.get("model", "") or "",
        status=kwargs.get("status", "success"),
        prompt=kwargs.get("prompt", "") or "",
        request_json=dumps_json(kwargs.get("request_payload") or {}),
        raw_response=kwargs.get("raw_response", "") or "",
        normalized_json=dumps_json(kwargs.get("normalized") or {}),
        validation_error=kwargs.get("validation_error", "") or "",
    )
    session.add(log)
    await session.flush()
    return log


async def _write_project_generation_log_committed(**kwargs) -> None:
    """Write a generation log in its own transaction so failures are still visible."""
    try:
        async with get_async_session() as log_session:
            await _write_project_generation_log(log_session, **kwargs)
    except Exception as log_err:
        logger.warning(f"[characters] committed log write failed: {log_err}")


logger = logging.getLogger("ylcraft.characters")


# ---- Request/Response 模型 ----

class CharacterCreateRequest(BaseModel):
    name: str = Field(..., description="角色名称")
    role: str = Field(default=CharacterRole.SUPPORTING, description="角色定位")
    workflow_source: str = Field(default=CharacterWorkflowSource.CHARACTER_FIRST.value, description="流程来源：extract / character_first / asset_import")
    source_types: list[str] = Field(
        default=[],
        description=f"来源类型，可选值：{CharacterSourceType.all()}",
    )
    appearance: str = Field(default="", description="外貌描述")
    personality: str = Field(default="", description="性格特点")
    costume_hint: str = Field(default="", description="服装提示")
    signature_items: list[str] = Field(default=[], description="角色标志性物品/符号")
    expressions: list[str] = Field(default=[], description="角色常用表情")
    poses: list[str] = Field(default=[], description="角色常用姿态/动作")
    visual_consistency: str = Field(default="", description="角色视觉一致性规则")
    background: str = Field(default="", description="背景故事")
    age_range: str = Field(default="", description="年龄范围，如 20-25岁")
    identity: dict[str, Any] = Field(default={}, description="Character Bible: 基础身份档案")
    motivation: dict[str, Any] = Field(default={}, description="Character Bible: 动机心理")
    speech: dict[str, Any] = Field(default={}, description="Character Bible: 语言语态")
    behavior: dict[str, Any] = Field(default={}, description="Character Bible: 行为/OOC 边界")
    ability: dict[str, Any] = Field(default={}, description="Character Bible: 能力短板限制")
    arc: dict[str, Any] = Field(default={}, description="Character Bible: 人物弧光")
    voice: dict[str, Any] = Field(default={}, description="音色设定：provider/voiceId/音色/音高/语速/口音/情绪/参考提示")
    voice_asset_id: str = Field(default="", description="关联语音素材 AssetNode ID（参考音/样音）")
    tags: list[str] = Field(default=[], description="自定义标签")
    portrait_url: str = Field(default="", description="立绘图片 URL")
    portrait_asset_id: str = Field(default="", description="关联素材资产 ID（立绘）")
    reference_asset_ids: list[str] = Field(default=[], description="关联素材资产 ID（参考视频/图片）")
    field_sources: dict[str, str] = Field(default={}, description="字段来源标记")
    is_frozen: bool | None = Field(default=False, description="是否冻结角色外观设定")


class CharacterUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    workflow_source: str | None = None
    source_types: list[str] | None = None
    appearance: str | None = None
    personality: str | None = None
    costume_hint: str | None = None
    signature_items: list[str] | None = None
    expressions: list[str] | None = None
    poses: list[str] | None = None
    visual_consistency: str | None = None
    background: str | None = None
    age_range: str | None = None
    identity: dict[str, Any] | None = None
    motivation: dict[str, Any] | None = None
    speech: dict[str, Any] | None = None
    behavior: dict[str, Any] | None = None
    ability: dict[str, Any] | None = None
    arc: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    voice_asset_id: str | None = None
    tags: list[str] | None = None
    portrait_url: str | None = None
    portrait_asset_id: str | None = None
    reference_asset_ids: list[str] | None = None
    field_sources: dict[str, str] | None = None
    is_frozen: bool | None = Field(None, description="是否冻结角色外观设定")


class CharacterRelationshipRequest(BaseModel):
    """角色关系创建/更新请求，支持世界和时间维度。"""
    related_character_id: str
    relation_type: str = ""
    relation_note: str = ""
    source: str = ""
    is_directed: bool = False
    world_usage_id: str | None = Field(default=None, description="归属的世界使用ID，不填表示全局关系")
    timeline_phase: str = Field(default="", description="时间阶段：前期/中期/后期/回忆/未来等")
    chapter_number: int | None = Field(default=None, description="小说中关系变化的章节号")


class AddTagRequest(BaseModel):
    tag: str = Field(..., description="要添加的标签")


class CharacterLinkStoryRequest(BaseModel):
    story_id: str = Field(..., description="故事项目 ID")
    world_id: str = Field(default="", description="世界/宇宙 ID，可为空时默认项目本身")
    world_name: str = Field(default="", description="世界/宇宙名称")
    usage_role: str = Field(default="", description="该世界中的角色职责，如 主角/NPC/反派/旁白")
    local_alias: str = Field(default="", description="该世界中的别名/代号")
    local_identity: str = Field(default="", description="该世界中的身份说明")
    local_faction: str = Field(default="", description="阵营/组织/派系")
    local_status: str = Field(default="active", description="active / cameo / archived 等")
    local_costume: str = Field(default="", description="该世界中的服装覆盖")
    local_prompt_tags: list[str] = Field(default=[], description="该世界中的局部 prompt 标签")
    ooc_notes: str = Field(default="", description="该世界中的 OOC 约束")
    off_model_notes: str = Field(default="", description="该世界中的 Off-Model 视觉约束")
    bible_overrides: dict[str, Any] = Field(default={}, description="文字设定覆盖")
    visual_overrides: dict[str, Any] = Field(default={}, description="视觉设定覆盖")


class CharacterWorldUsageUpdateRequest(BaseModel):
    world_id: str | None = None
    world_name: str | None = None
    usage_role: str | None = None
    local_alias: str | None = None
    local_identity: str | None = None
    local_faction: str | None = None
    local_status: str | None = None
    local_costume: str | None = None
    local_prompt_tags: list[str] | None = None
    ooc_notes: str | None = None
    off_model_notes: str | None = None
    bible_overrides: dict[str, Any] | None = None
    visual_overrides: dict[str, Any] | None = None


# ---- 路由 ----

@router.get("", summary="列出角色")
async def list_characters(
    keyword: str | None = Query(None, description="搜索角色名称"),
    source_type: str | None = Query(None, description="来源类型过滤，如 ai_generated"),
    workflow_source: str | None = Query(None, description="流程来源过滤：extract / character_first / asset_import"),
    extract_origin: str | None = Query(None, description="提取来源过滤：uploaded_novel / imported_novel / original_outline"),
    role: str | None = Query(None, description="角色定位过滤"),
    tag: str | None = Query(None, description="自定义标签过滤"),
    is_favorite: bool | None = Query(None, description="仅收藏"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    列出角色，支持：
    - 关键词搜索（角色名）
    - 来源类型过滤（多选）
    - 角色定位过滤
    - 自定义标签过滤
    - 收藏筛选
    - 分页
    """
    async with get_async_session() as session:
        service = CharacterService(session)
        items, total = await service.list(
            keyword=keyword,
            source_type=source_type,
            workflow_source=workflow_source,
            extract_origin=extract_origin,
            role=role,
            tag=tag,
            is_favorite=is_favorite,
            page=page,
            page_size=page_size,
        )
        origins = await service.extract_origins_for([c.id for c in items])
        return {
            "success": True,
            "data": [service.to_response(c, extract_origins=origins) for c in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.post("", summary="创建角色")
async def create_character(req: CharacterCreateRequest):
    """创建新角色"""
    async with get_async_session() as session:
        service = CharacterService(session)
        duplicate_candidates = await service.find_duplicate_candidates(req.name)
        character = await service.create(
            name=req.name,
            role=req.role,
            workflow_source=req.workflow_source,
            source_types=req.source_types,
            appearance=req.appearance,
            personality=req.personality,
            costume_hint=req.costume_hint,
            signature_items=req.signature_items,
            expressions=req.expressions,
            poses=req.poses,
            visual_consistency=req.visual_consistency,
            background=req.background,
            age_range=req.age_range,
            identity=req.identity,
            motivation=req.motivation,
            speech=req.speech,
            behavior=req.behavior,
            ability=req.ability,
            arc=req.arc,
            voice=req.voice,
            voice_asset_id=req.voice_asset_id,
            tags=req.tags,
            portrait_url=req.portrait_url,
            portrait_asset_id=req.portrait_asset_id,
            reference_asset_ids=req.reference_asset_ids,
            field_sources=req.field_sources,
            is_frozen=req.is_frozen,
        )
        return {
            "success": True,
            "data": service.to_response(character),
            "duplicate_candidates": duplicate_candidates,
            "duplicate_warning": bool(duplicate_candidates),
        }


@router.get("/tags/all", summary="获取所有自定义标签")
async def get_all_character_tags():
    """获取所有角色使用的自定义标签（去重）"""
    async with get_async_session() as session:
        service = CharacterService(session)
        tags = await service.get_all_tags()
        return {"success": True, "data": tags}


@router.get("/meta/source-types", summary="获取来源类型元数据")
async def get_source_types():
    """返回所有可选的来源类型"""
    return {
        "success": True,
        "data": [
            {"value": v, "label": CharacterSourceType.label(v)}
            for v in CharacterSourceType.all()
        ],
    }


@router.get("/meta/roles", summary="获取角色定位元数据")
async def get_roles():
    """返回所有可选的角色定位"""
    return {
        "success": True,
        "data": [
            {"value": CharacterRole.PROTAGONIST, "label": "主角"},
            {"value": CharacterRole.ANTAGONIST, "label": "反派"},
            {"value": CharacterRole.SUPPORTING, "label": "配角"},
            {"value": CharacterRole.EXTRA, "label": "路人"},
        ],
    }


@router.get("/meta/workflow-sources", summary="获取角色流程来源元数据")
async def get_workflow_sources():
    labels = {
        CharacterWorkflowSource.EXTRACT.value: "小说/正文提取",
        CharacterWorkflowSource.CHARACTER_FIRST.value: "角色先行",
        CharacterWorkflowSource.ASSET_IMPORT.value: "素材库导入",
        CharacterWorkflowSource.UNKNOWN.value: "未标记",
    }
    return {"success": True, "data": [{"value": value, "label": labels[value]} for value in labels]}


@router.get("/meta/extract-origins", summary="获取角色提取来源元数据")
async def get_extract_origins():
    """小说/正文提取链路的细分来源。

    - ``uploaded_novel``：用户上传的外来小说文本，角色字段有原文依据
    - ``imported_novel``：小说书架/搜索导入的外来小说，角色字段有原文依据
    - ``original_outline``：项目原创大纲，角色字段由 LLM 生成，标记为 AI 推断
    """
    from app.services.character.provenance import EXTRACT_ORIGIN_LABELS

    order = ["uploaded_novel", "imported_novel", "original_outline", "unknown"]
    return {"success": True, "data": [{"value": value, "label": EXTRACT_ORIGIN_LABELS[value]} for value in order]}


@router.get("/duplicate-candidates", summary="查询角色重复候选")
async def get_duplicate_candidates(
    name: str = Query(..., min_length=1, description="待检查的角色名称或别名"),
    exclude_id: str | None = Query(None, description="编辑角色时排除当前角色 ID"),
    limit: int = Query(20, ge=1, le=100, description="最多返回候选数量"),
):
    """Return candidates for review; this endpoint never merges or blocks creation."""
    async with get_async_session() as session:
        service = CharacterService(session)
        candidates = await service.find_duplicate_candidates(name, exclude_id=exclude_id, limit=limit)
        return {
            "success": True,
            "name": name,
            "candidates": candidates,
            "has_candidates": bool(candidates),
            "decision": "manual_review_required" if candidates else "no_candidate",
        }


@router.post("/{character_id}/tags", summary="添加自定义标签")
async def add_character_tag(character_id: str, req: AddTagRequest):
    """为角色添加一个自定义标签"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.add_tag(character_id, req.tag)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.to_response(character)}


@router.delete("/{character_id}/tags/{tag}", summary="移除自定义标签")
async def remove_character_tag(character_id: str, tag: str):
    """移除角色的一个自定义标签"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.remove_tag(character_id, tag)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.to_response(character)}


@router.post("/{character_id}/favorite", summary="切换收藏状态")
async def toggle_favorite(character_id: str):
    """切换角色的收藏状态"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        updated = await service.update(
            character_id,
            is_favorite=not character.is_favorite,
        )
        return {"success": True, "data": service.to_response(updated)}


@router.post("/{character_id}/link-story", summary="关联到故事项目")
async def link_story(character_id: str, req: CharacterLinkStoryRequest):
    """将全局角色关联到指定项目/世界，并保存该世界中的局部使用配置。"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        link = await service.link_to_story(
            character_id,
            req.story_id,
            world_id=req.world_id,
            world_name=req.world_name,
            usage_role=req.usage_role,
            local_alias=req.local_alias,
            local_identity=req.local_identity,
            local_faction=req.local_faction,
            local_status=req.local_status,
            local_costume=req.local_costume,
            local_prompt_tags=req.local_prompt_tags,
            ooc_notes=req.ooc_notes,
            off_model_notes=req.off_model_notes,
            bible_overrides=req.bible_overrides,
            visual_overrides=req.visual_overrides,
        )
        return {"success": True, "data": service.story_link_to_response(link)}


@router.get("/{character_id}/world-usages", summary="列出角色在不同世界/项目中的使用")
async def list_character_world_usages(character_id: str):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": await service.list_world_usages(character_id)}


@router.put("/{character_id}/world-usages/{usage_id}", summary="更新角色世界使用配置")
async def update_character_world_usage(
    character_id: str,
    usage_id: str,
    req: CharacterWorldUsageUpdateRequest,
):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        link = await service.update_world_usage(usage_id, character_id=character_id, **req.model_dump())
        if not link:
            raise HTTPException(status_code=404, detail="世界使用记录不存在")
        return {"success": True, "data": service.story_link_to_response(link)}


@router.delete("/{character_id}/world-usages/{usage_id}", summary="移除角色世界使用关系")
async def delete_character_world_usage(character_id: str, usage_id: str):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        deleted = await service.delete_world_usage(usage_id, character_id=character_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="世界使用记录不存在")
        return {"success": True}


@router.get("/{character_id}/state-timeline", summary="获取角色在剧情中的状态变化轨迹")
async def get_character_state_timeline(
    character_id: str,
    project_id: str | None = Query(None, description="按项目筛选，留空返回该角色在所有项目中的轨迹"),
):
    """返回角色状态随章节演变的台账。

    数据来自 ProjectStateEntry（scope = "character:<id>"），由 narrative_runtime
    在正文写完后由 AI 提取 state_changes 自动写入。这里按章节分组并 fold 出每章
    结束时的累积状态快照，供角色详情页画「剧情演变」时间轴。
    """
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")

        scope = f"character:{character_id}"
        stmt = select(ProjectStateEntry).where(ProjectStateEntry.scope == scope)
        if project_id:
            stmt = stmt.where(ProjectStateEntry.project_id == project_id)
        stmt = stmt.order_by(ProjectStateEntry.chapter_number.asc(), ProjectStateEntry.created_at.asc())
        rows = (await session.execute(stmt)).scalars().all()

        chapters: dict[int, list[dict]] = {}
        for e in rows:
            chapters.setdefault(int(e.chapter_number or 0), []).append(
                {
                    "id": e.id,
                    "key": e.key,
                    "op": e.op,
                    "value": loads_json(e.value_json),
                    "project_id": e.project_id,
                    "chapter_number": int(e.chapter_number or 0),
                    "source_content_id": e.source_content_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
            )

        # fold：按章节顺序累积，得到每章结束时的状态快照
        snapshot: dict[str, Any] = {}
        timeline = []
        for chapter in sorted(chapters):
            for item in chapters[chapter]:
                key = item["key"]
                value = item["value"]
                if item["op"] == "set":
                    snapshot[key] = value
                elif item["op"] == "add":
                    cur = snapshot.get(key)
                    if isinstance(cur, list):
                        if value not in cur:
                            snapshot[key] = cur + [value]
                    elif cur is None:
                        snapshot[key] = [value]
                    else:
                        snapshot[key] = [cur, value]
                elif item["op"] == "remove":
                    cur = snapshot.get(key)
                    if isinstance(cur, list) and value in cur:
                        snapshot[key] = [v for v in cur if v != value]
                    else:
                        snapshot.pop(key, None)
            timeline.append(
                {
                    "chapter_number": chapter,
                    "entries": chapters[chapter],
                    "snapshot_after": json.loads(json.dumps(snapshot, ensure_ascii=False, default=str)),
                }
            )

        return {
            "success": True,
            "data": {
                "character_id": character_id,
                "scope": scope,
                "total_entries": len(rows),
                "timeline": timeline,
                "current_state": snapshot,
            },
        }


@router.get("/relationships/graph", summary="获取角色关系图谱")
async def get_character_relationship_graph(
    world_usage_id: str | None = Query(None, description="按世界筛选，留空显示全部"),
):
    """获取角色关系图谱数据，支持按世界筛选。"""
    async with get_async_session() as session:
        service = CharacterService(session)
        characters = (await session.exec(select(Character))).all()
        char_map = {c.id: c for c in characters}

        # 预加载世界使用和项目信息
        from app.db.models.character import CharacterStoryLink
        world_links = (await session.exec(select(CharacterStoryLink))).all()
        world_map = {w.id: w for w in world_links}
        project_ids = [w.story_id for w in world_links if w.story_id]
        projects_by_id: dict[str, CreativeProject] = {}
        if project_ids:
            proj_result = await session.exec(select(CreativeProject).where(CreativeProject.id.in_(list(set(project_ids)))))
            projects_by_id = {p.id: p for p in proj_result.all()}

        rel_query = select(CharacterRelationship)
        if world_usage_id is not None:
            if world_usage_id == "":
                rel_query = rel_query.where(CharacterRelationship.world_usage_id.is_(None))
            elif world_usage_id:
                rel_query = rel_query.where(
                    (CharacterRelationship.world_usage_id == world_usage_id) |
                    (CharacterRelationship.world_usage_id.is_(None))
                )
        relationships = (await session.exec(rel_query)).all()
        edges = []
        for r in relationships:
            related_char = char_map.get(r.related_character_id) or char_map.get(r.character_id)
            world = world_map.get(r.world_usage_id) if r.world_usage_id else None
            project = projects_by_id.get(world.story_id) if world and world.story_id else None
            edges.append(service.relationship_to_response(r, related_character=related_char, world_usage=world, project=project))

        return {"success": True, "data": {
            "nodes": [{"id": c.id, "name": c.name, "role": c.role, "portrait_url": c.portrait_url} for c in characters],
            "edges": edges,
        }}


@router.get("/{character_id}/relationships", summary="列出角色关系")
async def list_character_relationships(
    character_id: str,
    world_usage_id: str | None = Query(None, description="按世界筛选：空值=全部，空字符串=仅全局，具体ID=该世界+全局"),
):
    """列出指定角色的所有关系，支持按世界/项目筛选。"""
    async with get_async_session() as session:
        service = CharacterService(session)
        if not await service.get_by_id(character_id):
            raise HTTPException(status_code=404, detail="角色不存在")

        items = await service.list_relationships(character_id, world_usage_id=world_usage_id)

        # 预加载关联角色名称（关系是双向的：对方可能在 character_id 或 related_character_id）
        related_ids = set()
        world_usage_ids = set()
        for item in items:
            # 双向关系：如果 related_character_id 是当前角色，那对方就是 character_id
            other_id = item.related_character_id if item.related_character_id != character_id else item.character_id
            related_ids.add(other_id)
            if item.world_usage_id:
                world_usage_ids.add(item.world_usage_id)

        # 批量加载关联角色
        from app.db.models.character import CharacterStoryLink
        related_chars: dict[str, Character] = {}
        if related_ids:
            char_result = await session.exec(select(Character).where(Character.id.in_(list(related_ids))))
            related_chars = {c.id: c for c in char_result.all()}

        # 批量加载世界使用和项目
        world_map: dict[str, CharacterStoryLink] = {}
        projects_by_id: dict[str, CreativeProject] = {}
        if world_usage_ids:
            world_result = await session.exec(select(CharacterStoryLink).where(CharacterStoryLink.id.in_(list(world_usage_ids))))
            world_map = {w.id: w for w in world_result.all()}
            story_ids = [w.story_id for w in world_map.values() if w.story_id]
            if story_ids:
                proj_result = await session.exec(select(CreativeProject).where(CreativeProject.id.in_(list(set(story_ids)))))
                projects_by_id = {p.id: p for p in proj_result.all()}

        response_data = []
        for item in items:
            # 确定对方角色ID（处理双向关系）
            other_id = item.related_character_id if item.related_character_id != character_id else item.character_id
            related_char = related_chars.get(other_id)
            world = world_map.get(item.world_usage_id) if item.world_usage_id else None
            project = projects_by_id.get(world.story_id) if world and world.story_id else None
            # 构造响应，确保 related_character_id 始终指向对方
            resp = service.relationship_to_response(
                item,
                related_character=related_char,
                world_usage=world,
                project=project,
            )
            # 统一让 related_character_id 指向对方角色，方便前端使用
            resp["related_character_id"] = other_id
            response_data.append(resp)
        return {"success": True, "data": response_data}


@router.post("/{character_id}/relationships", summary="创建角色关系")
async def create_character_relationship(character_id: str, req: CharacterRelationshipRequest):
    async with get_async_session() as session:
        service = CharacterService(session)
        try:
            item = await service.create_relationship(character_id, **req.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"success": True, "data": service.relationship_to_response(item)}


@router.put("/{character_id}/relationships/{relationship_id}", summary="更新角色关系")
async def update_character_relationship(character_id: str, relationship_id: str, req: CharacterRelationshipRequest):
    async with get_async_session() as session:
        service = CharacterService(session)
        try:
            item = await service.update_relationship(character_id, relationship_id, **req.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not item:
            raise HTTPException(status_code=404, detail="关系不存在")
        return {"success": True, "data": service.relationship_to_response(item)}


@router.delete("/{character_id}/relationships/{relationship_id}", summary="删除角色关系")
async def delete_character_relationship(character_id: str, relationship_id: str):
    async with get_async_session() as session:
        service = CharacterService(session)
        if not await service.delete_relationship(character_id, relationship_id):
            raise HTTPException(status_code=404, detail="关系不存在")
        return {"success": True}


@router.get("/{character_id}/prompt-pack", summary="生成角色 Prompt 资产包")
async def get_character_prompt_pack(character_id: str):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.build_prompt_pack(character)}


@router.get("/{character_id}", summary="获取角色详情")
async def get_character(character_id: str):
    """获取单个角色的完整信息"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        origins = await service.extract_origins_for([character.id])
        data = service.to_response(character, extract_origins=origins)
        data["world_usages"] = await service.list_world_usages(character_id)
        return {"success": True, "data": data}


@router.put("/{character_id}", summary="更新角色")
async def update_character(character_id: str, req: CharacterUpdateRequest):
    """更新角色信息（支持部分更新）"""
    async with get_async_session() as session:
        service = CharacterService(session)
        # 检查是否已冻结
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        if character.is_frozen and any(
            v is not None for v in [
                req.appearance, req.costume_hint, req.portrait_url, req.portrait_asset_id,
                req.signature_items, req.expressions, req.poses, req.visual_consistency,
            ]
        ):
            raise HTTPException(status_code=403, detail="角色已冻结，禁止修改外观描述")

        updated = await service.update(
            character_id=character_id,
            name=req.name,
            role=req.role,
            workflow_source=req.workflow_source,
            source_types=req.source_types,
            appearance=req.appearance,
            personality=req.personality,
            costume_hint=req.costume_hint,
            signature_items=req.signature_items,
            expressions=req.expressions,
            poses=req.poses,
            visual_consistency=req.visual_consistency,
            background=req.background,
            age_range=req.age_range,
            identity=req.identity,
            motivation=req.motivation,
            speech=req.speech,
            behavior=req.behavior,
            ability=req.ability,
            arc=req.arc,
            tags=req.tags,
            portrait_url=req.portrait_url,
            portrait_asset_id=req.portrait_asset_id,
            reference_asset_ids=req.reference_asset_ids,
            field_sources=req.field_sources,
        )
        return {"success": True, "data": service.to_response(updated)}


@router.delete("/{character_id}", summary="删除角色")
async def delete_character(character_id: str):
    """删除角色"""
    async with get_async_session() as session:
        service = CharacterService(session)
        deleted = await service.delete(character_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True}


# ===========================================================================
# 立绘生成与资产中枢集成
# ===========================================================================

class PortraitGenerateRequest(BaseModel):
    prompt: str = Field(default="", description="提示词")
    provider: Optional[str] = Field(None, description="指定生图后端（image backend name）")
    model: Optional[str] = Field(None, description="动态指定模型名（控制花费）")
    size: Optional[str] = Field("1024x1024", description="图片尺寸")
    n: Optional[int] = Field(1, description="生成数量（>1 时取首张）")
    negative_prompt: Optional[str] = Field(None, description="负向提示词")
    reference_images: list[str] = Field(default_factory=list, description="参考图 URL/base64 列表")
    preset: Optional[str] = Field("main_portrait", description="立绘预设")
    visual_profile: dict[str, Any] | None = Field(default=None, description="视觉卡覆盖字段")
    style_override: str = Field(default="", description="画风覆盖")
    negative_override: str = Field(default="", description="负向约束覆盖")
    set_as_main: bool = Field(default=True, description="是否设为角色主立绘")


class PortraitPromptPreviewRequest(BaseModel):
    preset: Optional[str] = Field("main_portrait", description="立绘预设")
    prompt_override: Optional[str] = Field(default="", description="提示词覆盖（留空则按角色设定自动生成）")
    visual_profile: dict[str, Any] | None = Field(default=None, description="视觉卡覆盖字段")
    style_override: str = Field(default="", description="画风覆盖")
    negative_override: str = Field(default="", description="负向约束覆盖")
    language: str = Field(default="zh", description="提示词语言")


class PortraitGridSliceRequest(BaseModel):
    grid_type: str = Field("auto", description="auto/expression/pose/turnaround")
    rows: int = Field(3, ge=1, le=6, description="网格行数")
    cols: int = Field(3, ge=1, le=6, description="网格列数")
    overwrite_existing: bool = Field(False, description="是否重复切片并创建新子素材")


class CharacterEnrichRequest(BaseModel):
    mode: str = Field(default="fill_missing", description="fill_missing 只补空字段；rewrite 重写并统一设定")
    context: str = Field(default="", description="额外上下文，如项目大纲、小说片段、角色关系")
    apply: bool = Field(default=False, description="是否直接写回角色")
    provider: Optional[str] = Field(None, description="指定 LLM 后端")
    model: Optional[str] = Field(None, description="指定 LLM 模型")


def _safe_filename_part(value: str, fallback: str = "asset") -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", (value or "").strip())
    safe = re.sub(r"\s+", "_", safe).strip("._ ")
    return (safe or fallback)[:60]


def _decode_asset_download_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return ""
    if parsed.path.endswith("/api/v1/assets/download") or parsed.path.endswith("/assets/download"):
        path_values = parse_qs(parsed.query).get("path") or []
        return unquote(path_values[0]) if path_values else ""
    if value.startswith("/api/v1/assets/download"):
        path_values = parse_qs(urlparse(value).query).get("path") or []
        return unquote(path_values[0]) if path_values else ""
    if parsed.scheme == "file":
        return unquote(parsed.path)
    return value


def _resolve_local_representation_path(rep) -> Path | None:
    candidates = []
    extra = dict(getattr(rep, "extra_json", None) or {})
    for key in ("local_path", "file_path", "path"):
        if extra.get(key):
            candidates.append(str(extra.get(key)))
    if getattr(rep, "file_path", ""):
        candidates.append(str(rep.file_path))
    if extra.get("url"):
        candidates.append(str(extra.get("url")))

    for candidate in candidates:
        decoded = _decode_asset_download_path(candidate)
        if not decoded:
            continue
        path = Path(decoded).expanduser()
        if path.exists() and path.is_file():
            return path
    return None


def _infer_grid_type(requested: str, preset: str) -> str:
    value = (requested or "auto").strip().lower()
    if value in {"expression", "pose", "turnaround"}:
        return value
    preset_value = (preset or "").lower()
    if "multi_view" in preset_value or "turnaround" in preset_value:
        return "turnaround"
    if "pose" in preset_value or "action" in preset_value:
        return "pose"
    return "expression"


def _grid_slice_label(grid_type: str, index: int) -> str:
    expression_labels = ["中性", "微笑", "大笑", "惊讶", "愤怒", "悲伤", "害羞", "思考", "坚定"]
    pose_labels = ["正面站姿", "侧身站姿", "背面回头", "抱臂", "行走", "奔跑", "坐姿", "战斗准备", "特写动作"]
    # turnaround 为三视图模型表，按 正面/侧面/背面 顺序切分
    turnaround_labels = ["正面", "侧面", "背面", "3/4 侧面", "背侧 3/4", "俯视", "仰视", "面部特写", "全身"]
    if grid_type == "turnaround":
        labels = turnaround_labels
    else:
        labels = pose_labels if grid_type == "pose" else expression_labels
    if 0 <= index < len(labels):
        return labels[index]
    return f"{grid_type}-{index + 1}"


def _local_file_url(path_or_url: str) -> str:
    if not path_or_url:
        return ""
    if path_or_url.startswith(("/api/", "http://", "https://", "data:")):
        return path_or_url
    return f"/api/v1/assets/download?path={quote(path_or_url)}"


@router.post(
    "/{character_id}/portrait/prompt-preview",
    summary="预览角色立绘提示词",
)
async def preview_character_portrait_prompt(character_id: str, req: PortraitPromptPreviewRequest):
    from app.db.models.character import Character
    from app.services.character.portrait_prompt import build_portrait_prompt

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        try:
            data = build_portrait_prompt(
                character=character,
                preset=req.preset,
                prompt_override=req.prompt_override or None,
                visual_profile=req.visual_profile,
                style_override=req.style_override,
                negative_override=req.negative_override,
                language=req.language,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"success": True, "data": data}


@router.get(
    "/{character_id}/portrait/versions",
    summary="列出角色立绘版本",
)
async def list_character_portrait_versions(character_id: str):
    from sqlalchemy import select

    from app.db.models.asset_hub import AssetNode, AssetRepresentation, AssetVersion
    from app.db.models.character import Character

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        if not character.portrait_node_id:
            return {"success": True, "data": {"node_id": None, "versions": []}}

        node = await session.get(AssetNode, str(character.portrait_node_id))
        if not node:
            return {"success": True, "data": {"node_id": str(character.portrait_node_id), "versions": []}}

        # The character visual profile is the source of truth for the current
        # identity image. Representation flags are kept for backwards
        # compatibility, but historical rows may contain stale/multiple flags.
        try:
            identity_payload = json.loads(character.identity_json or "{}")
        except Exception:
            identity_payload = {}
        if not isinstance(identity_payload, dict):
            identity_payload = {}
        visual_profile = identity_payload.get("visual_profile")
        if not isinstance(visual_profile, dict):
            visual_profile = {}
        identity_version_id = str(visual_profile.get("identity_reference_version_id") or "")
        identity_representation_id = str(visual_profile.get("identity_reference_representation_id") or "")

        result = await session.execute(
            select(AssetVersion)
            .where(AssetVersion.asset_node_id == str(node.id))
            .order_by(AssetVersion.version_number.desc())
        )
        versions = list(result.scalars().all())
        version_ids = [str(version.id) for version in versions]
        reps_by_version: dict[str, AssetRepresentation] = {}
        if version_ids:
            rep_result = await session.execute(
                select(AssetRepresentation).where(AssetRepresentation.asset_version_id.in_(version_ids))
            )
            for rep in rep_result.scalars().all():
                version_id = str(rep.asset_version_id)
                current = reps_by_version.get(version_id)
                if current is None or (rep.file_size or 0) > (current.file_size or 0):
                    reps_by_version[version_id] = rep

        payload = []
        for version in versions:
            rep = reps_by_version.get(str(version.id))
            rep_extra = dict(rep.extra_json or {}) if rep else {}
            # Asset Hub representations may only have a local filesystem path.
            # Never expose that path to the browser as an <img> source; route it
            # through the authenticated asset download endpoint instead.
            # 远端图床 URL 会过期，本地已落盘的文件才是稳定来源。
            # 仅当本地文件真实存在时才优先本地，否则仍回退到远端地址兜底。
            candidate_file = rep.file_path if rep else ""
            if (
                candidate_file
                and not str(candidate_file).startswith(("http://", "https://", "data:"))
                and os.path.exists(str(candidate_file))
            ):
                raw_image_url = candidate_file
            else:
                raw_image_url = rep_extra.get("url") or candidate_file or ""
            image_url = raw_image_url
            if image_url and not image_url.startswith(("/api/", "http://", "https://", "data:")):
                image_url = f"/api/v1/assets/download?path={quote(image_url)}"
            params = dict(version.params_json or {})
            is_identity_version = bool(identity_version_id and identity_version_id == str(version.id))
            is_identity_representation = bool(rep and identity_representation_id and identity_representation_id == str(rep.id))
            is_legacy_main = bool(
                not identity_version_id
                and (
                    rep_extra.get("is_main")
                    or (raw_image_url and raw_image_url == character.portrait_url)
                    or (image_url and image_url == character.portrait_url)
                )
            )
            payload.append(
                {
                    "id": str(version.id),
                    "version_number": version.version_number,
                    "created_at": str(version.created_at) if version.created_at else None,
                    "model": version.model_used or params.get("model") or "",
                    "provider": params.get("provider") or "",
                    "preset": params.get("preset") or rep_extra.get("preset") or "",
                    "prompt": version.prompt_used or "",
                    "negative_prompt": params.get("negative_prompt") or "",
                    "image_url": image_url,
                    "file_path": rep.file_path if rep else "",
                    "representation_id": str(rep.id) if rep else None,
                    "width": rep.width if rep else None,
                    "height": rep.height if rep else None,
                    "is_main": is_identity_version or is_identity_representation or is_legacy_main,
                    "params": params,
                }
            )
        return {"success": True, "data": {"node_id": str(node.id), "versions": payload}}


@router.post(
    "/{character_id}/portrait/versions/{version_id}/set-main",
    summary="设置角色主立绘版本",
)
async def set_character_main_portrait_version(character_id: str, version_id: str):
    from sqlalchemy import select

    from app.db.models.asset_hub import AssetNode, AssetRepresentation, AssetVersion
    from app.db.models.character import Character

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        if not character.portrait_node_id:
            raise HTTPException(status_code=400, detail="角色尚未绑定立绘资产节点")

        version = await session.get(AssetVersion, version_id)
        if not version or str(version.asset_node_id) != str(character.portrait_node_id):
            raise HTTPException(status_code=404, detail="立绘版本不存在或不属于该角色")

        rep_result = await session.execute(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_version_id == str(version.id))
            .order_by(AssetRepresentation.file_size.desc())
        )
        selected_rep = rep_result.scalars().first()
        if not selected_rep:
            raise HTTPException(status_code=400, detail="该立绘版本没有可用图片")

        versions_result = await session.execute(
            select(AssetVersion).where(AssetVersion.asset_node_id == str(character.portrait_node_id))
        )
        all_version_ids = [str(item.id) for item in versions_result.scalars().all()]
        if all_version_ids:
            reps_result = await session.execute(
                select(AssetRepresentation).where(AssetRepresentation.asset_version_id.in_(all_version_ids))
            )
            for rep in reps_result.scalars().all():
                extra = dict(rep.extra_json or {})
                extra["is_main"] = str(rep.asset_version_id) == str(version.id)
                rep.extra_json = extra

        params = dict(version.params_json or {})
        params["set_as_main"] = True
        version.params_json = params

        selected_extra = dict(selected_rep.extra_json or {})
        # 同 versions 读取侧：本地文件存在时优先本地，远端图床地址仅作兜底。
        _candidate = selected_rep.file_path or ""
        if (
            _candidate
            and not str(_candidate).startswith(("http://", "https://", "data:"))
            and os.path.exists(str(_candidate))
        ):
            portrait_url = _local_file_url(str(_candidate))
        else:
            portrait_url = selected_extra.get("url") or _candidate
        character.portrait_url = portrait_url
        identity = {}
        try:
            identity = json.loads(character.identity_json or "{}")
        except Exception:
            identity = {}
        if not isinstance(identity, dict):
            identity = {}
        visual_profile = identity.get("visual_profile")
        if not isinstance(visual_profile, dict):
            visual_profile = {}
        reference_urls = visual_profile.get("reference_image_urls")
        if not isinstance(reference_urls, list):
            reference_urls = []
        cleaned_refs = []
        seen_refs = set()
        for url in [portrait_url, *reference_urls]:
            text = str(url or "").strip()
            if not text or text in seen_refs:
                continue
            seen_refs.add(text)
            cleaned_refs.append(text)
        visual_profile.update(
            {
                "identity_reference_url": portrait_url,
                "identity_reference_version_id": str(version.id),
                "identity_reference_representation_id": str(selected_rep.id),
                "reference_image_urls": cleaned_refs,
            }
        )
        identity["visual_profile"] = visual_profile
        character.identity_json = json.dumps(identity, ensure_ascii=False)
        character.updated_at = datetime.now()

        node = await session.get(AssetNode, str(character.portrait_node_id))
        if node:
            node.thumbnail_url = portrait_url
            node.updated_at = datetime.now()

        await session.flush()
        await session.refresh(character)

        return {
            "success": True,
            "data": {
                "version_id": str(version.id),
                "version_number": version.version_number,
                "portrait_url": character.portrait_url,
                "character": CharacterService(session).to_response(character),
            },
        }


@router.get(
    "/{character_id}/portrait/slices",
    summary="列出角色立绘九宫格切片子素材",
)
async def list_character_portrait_slices(
    character_id: str,
    grid_type: str | None = Query(None, description="expression/pose，可选"),
):
    from sqlalchemy import select

    from app.db.models.asset_hub import AssetNode, AssetRepresentation, AssetVersion
    from app.db.models.character import Character

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        if not character.portrait_node_id:
            return {"success": True, "data": {"node_id": None, "items": []}}

        portrait_node_id = str(character.portrait_node_id)
        children_result = await session.execute(
            select(AssetNode)
            .where(AssetNode.parent_id == portrait_node_id)
            .order_by(AssetNode.created_at.asc())
        )
        children = list(children_result.scalars().all())
        slice_nodes = []
        for child in children:
            metadata = dict(child.metadata_json or {})
            if metadata.get("source") != "character_portrait_grid_slice":
                continue
            if grid_type and metadata.get("grid_type") != grid_type:
                continue
            slice_nodes.append(child)

        if not slice_nodes:
            return {"success": True, "data": {"node_id": portrait_node_id, "items": []}}

        node_ids = [str(node.id) for node in slice_nodes]
        versions_result = await session.execute(
            select(AssetVersion)
            .where(AssetVersion.asset_node_id.in_(node_ids))
            .order_by(AssetVersion.created_at.desc())
        )
        versions_by_node: dict[str, AssetVersion] = {}
        for version in versions_result.scalars().all():
            versions_by_node.setdefault(str(version.asset_node_id), version)

        version_ids = [str(version.id) for version in versions_by_node.values()]
        reps_by_version: dict[str, AssetRepresentation] = {}
        if version_ids:
            reps_result = await session.execute(
                select(AssetRepresentation)
                .where(AssetRepresentation.asset_version_id.in_(version_ids))
                .order_by(AssetRepresentation.file_size.desc())
            )
            for rep in reps_result.scalars().all():
                reps_by_version.setdefault(str(rep.asset_version_id), rep)

        items = []
        for node in slice_nodes:
            metadata = dict(node.metadata_json or {})
            version = versions_by_node.get(str(node.id))
            rep = reps_by_version.get(str(version.id)) if version else None
            file_path = rep.file_path if rep else (node.thumbnail_url or "")
            items.append(
                {
                    "node_id": str(node.id),
                    "version_id": str(version.id) if version else None,
                    "representation_id": str(rep.id) if rep else None,
                    "title": node.name,
                    "label": metadata.get("label") or node.name,
                    "grid_type": metadata.get("grid_type") or "",
                    "grid_index": metadata.get("grid_index") or 0,
                    "row": metadata.get("row") or 0,
                    "col": metadata.get("col") or 0,
                    "source_version_id": metadata.get("source_version_id") or "",
                    "source_representation_id": metadata.get("source_representation_id") or "",
                    "source_preset": metadata.get("source_preset") or "",
                    "file_path": file_path,
                    "image_url": _local_file_url(file_path),
                    "width": rep.width if rep else None,
                    "height": rep.height if rep else None,
                    "created_at": str(node.created_at) if node.created_at else None,
                }
            )

        items.sort(key=lambda item: (str(item.get("source_version_id") or ""), item.get("grid_index") or 0))
        return {"success": True, "data": {"node_id": portrait_node_id, "items": items}}


@router.post(
    "/{character_id}/portrait/versions/{version_id}/slice-grid",
    summary="将九宫格立绘版本切成可复用子素材",
)
async def slice_character_portrait_grid(
    character_id: str,
    version_id: str,
    req: PortraitGridSliceRequest,
):
    from PIL import Image
    from sqlalchemy import select

    from app.db.models.asset_hub import (
        AssetNode,
        AssetRepresentation,
        AssetType,
        AssetVersion,
        RelationType,
    )
    from app.db.models.character import Character
    from app.services.asset_hub.node_service import AssetNodeService
    from app.services.asset_hub.representation_service import AssetRepresentationService
    from app.services.asset_hub.version_service import AssetVersionService

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        if not character.portrait_node_id:
            raise HTTPException(status_code=400, detail="角色尚未绑定立绘资产节点")

        portrait_node_id = str(character.portrait_node_id)
        portrait_node = await session.get(AssetNode, portrait_node_id)
        if not portrait_node:
            raise HTTPException(status_code=404, detail="角色立绘资产节点不存在")

        version = await session.get(AssetVersion, version_id)
        if not version or str(version.asset_node_id) != portrait_node_id:
            raise HTTPException(status_code=404, detail="立绘版本不存在或不属于该角色")

        rep_result = await session.execute(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_version_id == str(version.id))
            .order_by(AssetRepresentation.file_size.desc())
        )
        source_rep = rep_result.scalars().first()
        if not source_rep:
            raise HTTPException(status_code=400, detail="该立绘版本没有可切图的文件表示")

        source_path = _resolve_local_representation_path(source_rep)
        if not source_path:
            raise HTTPException(
                status_code=400,
                detail="当前立绘版本没有本地图片文件，无法九宫格切图。请使用本地保存后的生成结果或先重新生成立绘。",
            )

        params = dict(version.params_json or {})
        preset = str(params.get("preset") or dict(source_rep.extra_json or {}).get("preset") or "")
        grid_type = _infer_grid_type(req.grid_type, preset)
        expected_count = req.rows * req.cols

        if not req.overwrite_existing:
            children = await AssetNodeService(session).list_children(portrait_node_id)
            existing_items = []
            for child in children:
                metadata = dict(child.metadata_json or {})
                if (
                    metadata.get("source") == "character_portrait_grid_slice"
                    and str(metadata.get("source_version_id")) == str(version.id)
                    and metadata.get("grid_rows") == req.rows
                    and metadata.get("grid_cols") == req.cols
                ):
                    existing_items.append(
                        {
                            "node_id": str(child.id),
                            "label": metadata.get("label") or child.name,
                            "index": metadata.get("grid_index"),
                            "row": metadata.get("row"),
                            "col": metadata.get("col"),
                            "file_path": child.thumbnail_url or "",
                            "reused": True,
                        }
                    )
            if len(existing_items) >= expected_count:
                return {
                    "success": True,
                    "data": {
                        "source_version_id": str(version.id),
                        "source_representation_id": str(source_rep.id),
                        "grid_type": grid_type,
                        "rows": req.rows,
                        "cols": req.cols,
                        "items": sorted(existing_items, key=lambda item: item.get("index") or 0),
                        "reused": True,
                    },
                }

        output_root = Path(__file__).resolve().parents[2] / "storage" / "character_slices"
        output_dir = output_root / _safe_filename_part(character_id, "character") / _safe_filename_part(version_id, "version")
        output_dir.mkdir(parents=True, exist_ok=True)

        node_service = AssetNodeService(session)
        version_service = AssetVersionService(session)
        rep_service = AssetRepresentationService(session)
        created_items = []

        try:
            with Image.open(source_path) as source_image:
                image = source_image.convert("RGBA")
                width, height = image.size
                if width < req.cols or height < req.rows:
                    raise HTTPException(status_code=400, detail="图片尺寸小于网格数量，无法切图")

                for row in range(req.rows):
                    for col in range(req.cols):
                        index = row * req.cols + col
                        label = _grid_slice_label(grid_type, index)
                        left = round(col * width / req.cols)
                        upper = round(row * height / req.rows)
                        right = round((col + 1) * width / req.cols)
                        lower = round((row + 1) * height / req.rows)
                        crop = image.crop((left, upper, right, lower))
                        filename = (
                            f"{index + 1:02d}_{row + 1}x{col + 1}_"
                            f"{_safe_filename_part(character.name, 'character')}_"
                            f"{_safe_filename_part(label, 'slice')}.png"
                        )
                        crop_path = output_dir / filename
                        crop.save(crop_path, format="PNG")
                        file_size = crop_path.stat().st_size

                        metadata = {
                            "source": "character_portrait_grid_slice",
                            "character_id": str(character.id),
                            "character_name": character.name,
                            "source_portrait_node_id": portrait_node_id,
                            "source_version_id": str(version.id),
                            "source_representation_id": str(source_rep.id),
                            "source_preset": preset,
                            "grid_type": grid_type,
                            "grid_rows": req.rows,
                            "grid_cols": req.cols,
                            "grid_index": index + 1,
                            "row": row + 1,
                            "col": col + 1,
                            "label": label,
                        }
                        child_node = await node_service.create(
                            name=f"{character.name}-{label}",
                            asset_type=AssetType.IMAGE,
                            parent_id=portrait_node_id,
                            thumbnail_url=str(crop_path),
                            metadata=metadata,
                            tags=[
                                "角色立绘",
                                "九宫格切片",
                                "表情" if grid_type == "expression" else "动作",
                                character.name,
                            ],
                        )
                        child_version = await version_service.create(
                            asset_node_id=str(child_node.id),
                            prompt_used=version.prompt_used,
                            model_used=version.model_used,
                            params={
                                **params,
                                "source": "character_portrait_grid_slice",
                                "source_preset": preset,
                                "grid_type": grid_type,
                                "grid_rows": req.rows,
                                "grid_cols": req.cols,
                                "grid_index": index + 1,
                                "slice_label": label,
                            },
                            lineage={
                                "source": "character_portrait_grid_slice",
                                "character_id": str(character.id),
                                "character_name": character.name,
                                "source_portrait_node_id": portrait_node_id,
                                "source_version_id": str(version.id),
                                "source_representation_id": str(source_rep.id),
                            },
                        )
                        child_rep = await rep_service.create(
                            asset_version_id=str(child_version.id),
                            file_path=str(crop_path),
                            mime_type="image/png",
                            file_size=file_size,
                            width=crop.width,
                            height=crop.height,
                            format="png",
                            extra={
                                **metadata,
                                "local_path": str(crop_path),
                                "url": str(crop_path),
                            },
                        )
                        await version_service.link_versions(
                            source_id=portrait_node_id,
                            target_id=str(child_node.id),
                            relation_type=RelationType.DERIVED_FROM,
                            context={
                                "source": "character_portrait_grid_slice",
                                "source_version_id": str(version.id),
                                "grid_index": index + 1,
                                "label": label,
                            },
                        )
                        created_items.append(
                            {
                                "node_id": str(child_node.id),
                                "version_id": str(child_version.id),
                                "representation_id": str(child_rep.id),
                                "file_path": str(crop_path),
                                "label": label,
                                "index": index + 1,
                                "row": row + 1,
                                "col": col + 1,
                                "width": crop.width,
                                "height": crop.height,
                            }
                        )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"[portrait/slice-grid] failed: {e}")
            try:
                await _write_project_generation_log(
                    session,
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="portrait_grid_slice",
                    status="failed",
                    prompt=version.prompt_used or "",
                    request_payload={
                        "character_id": str(character.id),
                        "version_id": str(version.id),
                        "rows": req.rows,
                        "cols": req.cols,
                        "grid_type": req.grid_type,
                    },
                    raw_response=str(e),
                    validation_error=type(e).__name__,
                )
                await session.flush()
            except Exception as log_err:
                logger.warning(f"[portrait/slice-grid] log write failed: {log_err}")
            raise HTTPException(status_code=500, detail=f"九宫格切图失败: {e}")

        await _write_project_generation_log(
            session,
            scene="character_portrait",
            ref_id=character.id,
            stage="portrait_grid_slice",
            status="success",
            prompt=version.prompt_used or "",
            request_payload={
                "character_id": str(character.id),
                "character_name": character.name,
                "version_id": str(version.id),
                "representation_id": str(source_rep.id),
                "source_path": str(source_path),
                "rows": req.rows,
                "cols": req.cols,
                "grid_type": grid_type,
            },
            normalized={
                "source_version_id": str(version.id),
                "source_representation_id": str(source_rep.id),
                "grid_type": grid_type,
                "rows": req.rows,
                "cols": req.cols,
                "count": len(created_items),
                "items": created_items,
            },
        )
        await session.flush()

        return {
            "success": True,
            "data": {
                "source_version_id": str(version.id),
                "source_representation_id": str(source_rep.id),
                "grid_type": grid_type,
                "rows": req.rows,
                "cols": req.cols,
                "items": created_items,
                "reused": False,
            },
        }


@router.post(
    "/{character_id}/enrich",
    summary="AI 补全角色信息",
)
async def enrich_character(character_id: str, req: CharacterEnrichRequest):
    from app.db.models.character import Character
    from app.services.ai import get_ai_service
    from app.services.ai.types import LLMMessage
    from app.services.character.enrichment import (
        build_character_enrichment_prompt,
        character_response_for_enrichment,
        merge_character_enrichment,
        parse_character_enrichment_response,
    )

    mode = req.mode if req.mode in {"fill_missing", "rewrite"} else "fill_missing"
    try:
        manager = get_ai_service()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AIService 未初始化: {e}")
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        current = character_response_for_enrichment(character)
        prompt = build_character_enrichment_prompt(current, context=req.context, mode=mode)
        log_request_payload = {
            "character_id": str(character.id),
            "character_name": character.name,
            "mode": mode,
            "apply": req.apply,
            "provider": req.provider,
            "model": req.model,
            "context": req.context,
        }
        enrich_started = time.time()
        result = await manager.chat(
            [
                LLMMessage(role="system", content="你是严格输出 JSON 的角色设定师。"),
                LLMMessage(role="user", content=prompt),
            ],
            backend_name=req.provider,
            model=req.model,
            temperature=0.4,
        )
        if not result.success:
            await platform_log.record_event(
                scene="llm",
                task_type="llm_chat",
                level="error",
                status="failed",
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                message=f"角色 AI 补全失败：{character.name}",
                error=result.error or "",
                request=log_request_payload,
                duration_ms=int((time.time() - enrich_started) * 1000),
            )
            await _write_project_generation_log_committed(
                scene="character_portrait",
                ref_id=str(character.id),
                stage=f"character_enrich_{mode}",
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                status="failed",
                prompt=prompt,
                request_payload=log_request_payload,
                raw_response=result.content or "",
                normalized={"current": current},
                validation_error=result.error or "unknown error",
            )
            raise HTTPException(status_code=500, detail=f"AI 补全失败: {result.error or 'unknown error'}")
        try:
            proposal = parse_character_enrichment_response(result.content)
        except Exception as e:
            await platform_log.record_event(
                scene="llm",
                task_type="llm_chat",
                level="error",
                status="failed",
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                message=f"角色 AI 补全返回解析失败：{character.name}",
                error=f"parse_error: {e}",
                request=log_request_payload,
                response=result.content or "",
                duration_ms=int((time.time() - enrich_started) * 1000),
            )
            await _write_project_generation_log_committed(
                scene="character_portrait",
                ref_id=str(character.id),
                stage=f"character_enrich_{mode}",
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                status="failed",
                prompt=prompt,
                request_payload=log_request_payload,
                raw_response=result.content or "",
                normalized={"current": current},
                validation_error=f"parse_error: {e}",
            )
            raise HTTPException(status_code=500, detail=f"AI 返回解析失败: {e}")

        merged, applied_fields = merge_character_enrichment(current, proposal, mode=mode)
        updated = None
        if req.apply and applied_fields:
            service = CharacterService(session)
            update_payload = {field: merged[field] for field in applied_fields}
            updated_character = await service.update(character_id, **update_payload)
            await session.flush()
            updated = service.to_response(updated_character) if updated_character else None

        await platform_log.record_event(
            scene="llm",
            task_type="llm_chat",
            level="info",
            status="success",
            provider=result.provider or req.provider or "",
            model=result.model or req.model or "",
            message=f"角色 AI 补全成功：{character.name}（{mode}）",
            request=log_request_payload,
            duration_ms=int((time.time() - enrich_started) * 1000),
        )
        await _write_project_generation_log(
            session,
            scene="character_portrait",
            ref_id=str(character.id),
            stage=f"character_enrich_{mode}",
            provider=result.provider or req.provider or "",
            model=result.model or req.model or "",
            status="success",
            prompt=prompt,
            request_payload=log_request_payload,
            raw_response=result.content or "",
            normalized={
                "current": current,
                "proposal": proposal,
                "merged": merged,
                "applied_fields": applied_fields if req.apply else [],
            },
        )
        await session.flush()

        return {
            "success": True,
            "data": {
                "mode": mode,
                "proposal": proposal,
                "merged": merged,
                "applied_fields": applied_fields if req.apply else [],
                "character": updated,
                "provider": result.provider,
                "model": result.model,
            },
        }


@router.post(
    "/{character_id}/portrait/generate",
    summary="AI 生成角色立绘（资产中枢版）",
)
async def generate_character_portrait(character_id: str, req: PortraitGenerateRequest):
    """
    AI 生成角色立绘并自动入资产中枢（Node+Version+Representation）。

    - 若角色已有 portrait_node_id，则在该 Node 下创建新版本（保留历史）
    - 否则创建新 AssetNode (asset_type=character) + Version 1
    - 同步更新 Character.portrait_url 和 portrait_node_id

    注意：不会调用旧版 /images/generate 端点（避免双入库旧版 Asset 表）。
    """
    from app.services.ai import get_ai_service
    from app.services.ai.types import ImageGenerationRequest
    from app.services.asset_hub import AssetHubFacade
    from app.db.models.character import Character
    from app.services.character.portrait_prompt import build_portrait_prompt

    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    async with get_async_session() as session:
        # 1. 获取角色
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")

        try:
            prompt_bundle = build_portrait_prompt(
                character=character,
                preset=req.preset,
                visual_profile=req.visual_profile,
                style_override=req.style_override,
                negative_override=req.negative_override,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        prompt = (req.prompt or "").strip() or prompt_bundle["prompt"]
        negative_prompt = (req.negative_prompt or "").strip() or prompt_bundle["negative_prompt"]

        # 2. 生图
        img_req = ImageGenerationRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            size=req.size or "1024x1024",
            n=req.n or 1,
            provider=req.provider or "",
            model=req.model or "",
            reference_images=req.reference_images or [],
        )

        started = time.time()
        try:
            result = await manager.generate_image(img_req)
        except Exception as e:
            logger.exception(f"[portrait/generate] generate_image failed: {e}")
            # 写入平台事件日志：任务中心与事件日志 Tab 读的是 platform_event_logs，
            # 只写 ProjectGenerationLog 会导致角色生图在任务中心不可见。
            await platform_log.record_event(
                scene="image",
                task_type="character_portrait",
                level="error",
                status="failed",
                provider=req.provider or "",
                model=req.model or "",
                message=f"角色立绘生成失败：{character.name}",
                error=str(e),
                ref_id=character.id,
                request=_portrait_event_payload(character, req, prompt, negative_prompt, prompt_bundle["preset"]),
                duration_ms=int((time.time() - started) * 1000),
                retry_payload=_portrait_retry_payload(req, prompt, negative_prompt),
            )
            # 写入失败日志
            try:
                await _write_project_generation_log(
                    session,
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="generate_image",
                    status="failed",
                    provider=req.provider or "",
                    model=req.model or "",
                    prompt=prompt,
                    request_payload={
                        "character_id": character.id,
                        "character_name": character.name,
                        "size": req.size,
                        "n": req.n,
                        "negative_prompt": negative_prompt,
                        "reference_images_count": len(req.reference_images or []),
                        "reference_images": req.reference_images or [],
                        "provider": req.provider,
                        "model": req.model,
                        "preset": prompt_bundle["preset"],
                    },
                    raw_response=str(e),
                    validation_error=type(e).__name__,
                )
                await session.flush()
            except Exception as log_err:
                logger.warning(f"[portrait/generate] log write failed: {log_err}")
            raise HTTPException(status_code=500, detail=f"生图失败: {e}")

        if not result.success:
            await platform_log.record_event(
                scene="image",
                task_type="character_portrait",
                level="error",
                status="failed",
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                message=f"角色立绘生成失败：{character.name}",
                error=result.error or "",
                ref_id=character.id,
                request=_portrait_event_payload(character, req, prompt, negative_prompt, prompt_bundle["preset"]),
                duration_ms=int((time.time() - started) * 1000),
                retry_payload=_portrait_retry_payload(req, prompt, negative_prompt),
            )
            # 写入失败日志
            try:
                await _write_project_generation_log(
                    session,
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="generate_image",
                    status="failed",
                    provider=result.provider or req.provider or "",
                    model=result.model or req.model or "",
                    prompt=prompt,
                    request_payload={
                        "character_id": character.id,
                        "character_name": character.name,
                        "size": req.size,
                        "n": req.n,
                        "reference_images_count": len(req.reference_images or []),
                        "reference_images": req.reference_images or [],
                        "preset": prompt_bundle["preset"],
                    },
                    raw_response=result.error or "",
                    validation_error="provider_returned_failure",
                )
                await session.flush()
            except Exception as log_err:
                logger.warning(f"[portrait/generate] log write failed: {log_err}")
            raise HTTPException(
                status_code=500,
                detail=f"生图失败: {result.error or 'unknown error'}",
            )

        urls = result.urls or ([result.url] if result.url else [])
        local_paths = (
            result.all_local_paths
            or ([result.local_path] if result.local_path else [])
        )
        if not urls and not local_paths:
            raise HTTPException(status_code=500, detail="生图成功但未返回图片")

        local_path = local_paths[0] if local_paths else ""
        # 供应商返回的 URL 多为临时图床，会过期失效。只要本地已落盘就优先使用本地路径，
        # 远端地址仅作为无本地文件时的兜底（并记入 extra 留档）。
        url = _local_file_url(local_path) if local_path else (urls[0] if urls else "")

        # 3. 写入资产中枢
        try:
            asset_hub_result = await AssetHubFacade(session).create_or_update_character_portrait(
                character=character,
                portrait_url=url,
                local_path=local_path,
                prompt=prompt,
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                negative_prompt=negative_prompt,
                size=req.size or "",
                seed=result.seed,
                generation_params={
                    "n": req.n,
                    "preset": prompt_bundle["preset"],
                    "set_as_main": req.set_as_main,
                    "prompt_template_version": prompt_bundle["prompt_template_version"],
                    "visual_profile_snapshot": prompt_bundle["visual_profile_snapshot"],
                    "reference_images": req.reference_images or [],
                    "reference_images_count": len(req.reference_images or []),
                },
                lineage={
                    "character_id": character.id,
                    "character_name": character.name,
                    "portrait_preset": prompt_bundle["preset"],
                    "reference_images": req.reference_images or [],
                },
                tags=[prompt_bundle["preset"]],
            )

            # 4. 更新 Character
            if req.set_as_main:
                character.portrait_url = url
                character.portrait_node_id = asset_hub_result.node_id
                identity = {}
                try:
                    identity = json.loads(character.identity_json or "{}")
                except Exception:
                    identity = {}
                if not isinstance(identity, dict):
                    identity = {}
                visual_profile = identity.get("visual_profile")
                if not isinstance(visual_profile, dict):
                    visual_profile = {}
                reference_urls = visual_profile.get("reference_image_urls")
                if not isinstance(reference_urls, list):
                    reference_urls = []
                cleaned_refs = []
                seen_refs = set()
                for ref_url in [url, *reference_urls]:
                    text = str(ref_url or "").strip()
                    if not text or text in seen_refs:
                        continue
                    seen_refs.add(text)
                    cleaned_refs.append(text)
                visual_profile.update(
                    {
                        "identity_reference_url": url,
                        "identity_reference_version_id": asset_hub_result.version_id,
                        "identity_reference_representation_id": asset_hub_result.representation_id,
                        "reference_image_urls": cleaned_refs,
                    }
                )
                identity["visual_profile"] = visual_profile
                character.identity_json = json.dumps(identity, ensure_ascii=False)
                character.updated_at = datetime.now()
            await session.flush()
            await session.refresh(character)

            # 5. 写入平台事件日志：任务中心与事件日志 Tab 的数据源
            await platform_log.record_event(
                scene="image",
                task_type="character_portrait",
                level="info",
                status="success",
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                message=f"角色立绘生成成功：{character.name}",
                ref_id=character.id,
                request=_portrait_event_payload(character, req, prompt, negative_prompt, prompt_bundle["preset"]),
                response={"url": url, "node_id": asset_hub_result.node_id},
                duration_ms=int((time.time() - started) * 1000),
            )

            # 6. 写入成功日志
            try:
                await _write_project_generation_log(
                    session,
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="portrait_generate",
                    status="success",
                    provider=result.provider or req.provider or "",
                    model=result.model or req.model or "",
                    prompt=prompt,
                    request_payload={
                        "character_id": character.id,
                        "character_name": character.name,
                        "size": req.size,
                        "n": req.n,
                        "negative_prompt": negative_prompt,
                        "reference_images_count": len(req.reference_images or []),
                        "reference_images": req.reference_images or [],
                        "preset": prompt_bundle["preset"],
                    },
                    raw_response=str(url),
                    normalized={
                        "node_id": asset_hub_result.node_id,
                        "version_id": asset_hub_result.version_id,
                        "version_number": asset_hub_result.version_number,
                        "representation_id": asset_hub_result.representation_id,
                        "local_path": local_path,
                        "reference_images": req.reference_images or [],
                        "reference_images_count": len(req.reference_images or []),
                    },
                )
                await session.flush()
            except Exception as log_err:
                logger.warning(f"[portrait/generate] log write failed: {log_err}")

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"[portrait/generate] asset_hub sync failed: {e}")
            # 资产中枢写入失败日志（生图本身是成功的）
            try:
                await _write_project_generation_log(
                    session,
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="asset_hub_sync",
                    status="failed",
                    provider=result.provider or req.provider or "",
                    model=result.model or req.model or "",
                    prompt=prompt,
                    request_payload={"character_id": character.id, "preset": prompt_bundle["preset"]},
                    raw_response=str(e),
                    validation_error="asset_hub_sync_failed",
                )
                await session.flush()
            except Exception as log_err:
                logger.warning(f"[portrait/generate] log write failed: {log_err}")
            raise HTTPException(status_code=500, detail=f"资产中枢写入失败: {e}")

    return {
        "success": True,
        "data": {
            "url": url,
            "local_path": local_path,
            "node_id": asset_hub_result.node_id,
            "version_id": asset_hub_result.version_id,
            "version_number": asset_hub_result.version_number,
            "representation_id": asset_hub_result.representation_id,
            "character": CharacterService(session).to_response(character),
        },
    }


@router.post(
    "/{character_id}/portrait/upgrade",
    summary="将现有立绘升级到资产中枢",
)
async def upgrade_portrait_to_asset_hub(character_id: str):
    """
    把已有的 Character.portrait_url 升级为资产中枢中的资产。

    场景：之前用 /images/generate 生成了立绘但还没入中枢，现在补登记。

    - 创建 AssetNode (type=character) + Version 1 + Representation
    - 更新 Character.portrait_node_id
    - 已绑定节点时会拒绝（需要先解绑）
    """
    from app.services.asset_hub import AssetHubFacade
    from app.db.models.character import Character

    async with get_async_session() as session:
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")

        if not character.portrait_url:
            raise HTTPException(
                status_code=400,
                detail="角色尚无 portrait_url，无法升级（请先用 portrait/generate 生成）",
            )

        if character.portrait_node_id:
            raise HTTPException(
                status_code=400,
                detail=f"角色已绑定资产中枢节点 {character.portrait_node_id}，如需重建请先在数据库清空 portrait_node_id",
            )

        try:
            asset_hub_result = await AssetHubFacade(session).create_or_update_character_portrait(
                character=character,
                portrait_url=character.portrait_url,
                prompt=character.appearance or "",
                generation_params={"upgraded_from": "legacy"},
                lineage={
                    "character_id": character.id,
                    "character_name": character.name,
                    "costume_hint": character.costume_hint or "",
                },
                legacy_asset_id=character.portrait_asset_id or "",
                source="legacy_character_portrait",
                upgraded_from="legacy_portrait_url",
            )

            character.portrait_node_id = asset_hub_result.node_id
            character.updated_at = datetime.now()
            await session.flush()
            await session.refresh(character)

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"[portrait/upgrade] failed: {e}")
            raise HTTPException(status_code=500, detail=f"升级失败: {e}")

    return {
        "success": True,
        "data": {
            "node_id": asset_hub_result.node_id,
            "version_id": asset_hub_result.version_id,
            "version_number": asset_hub_result.version_number,
            "representation_id": asset_hub_result.representation_id,
            "character": {
                "id": character.id,
                "name": character.name,
                "portrait_url": character.portrait_url,
                "portrait_node_id": str(character.portrait_node_id) if character.portrait_node_id else None,
            },
        },
    }
