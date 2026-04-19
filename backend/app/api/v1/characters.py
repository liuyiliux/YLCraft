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
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any

from app.db.database import get_session
from app.services.character.service import CharacterService
from app.db.models.character import CharacterSourceType, CharacterRole

router = APIRouter()


# ---- Request/Response 模型 ----

class CharacterCreateRequest(BaseModel):
    name: str = Field(..., description="角色名称")
    role: str = Field(default=CharacterRole.SUPPORTING, description="角色定位")
    source_types: list[str] = Field(
        default=[],
        description=f"来源类型，可选值：{CharacterSourceType.all()}",
    )
    appearance: str = Field(default="", description="外貌描述")
    personality: str = Field(default="", description="性格特点")
    costume_hint: str = Field(default="", description="服装提示")
    background: str = Field(default="", description="背景故事")
    age_range: str = Field(default="", description="年龄范围，如 20-25岁")
    tags: list[str] = Field(default=[], description="自定义标签")
    portrait_url: str = Field(default="", description="立绘图片 URL")
    portrait_asset_id: str = Field(default="", description="关联素材资产 ID（立绘）")
    reference_asset_ids: list[str] = Field(default=[], description="关联素材资产 ID（参考视频/图片）")


class CharacterUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    source_types: list[str] | None = None
    appearance: str | None = None
    personality: str | None = None
    costume_hint: str | None = None
    background: str | None = None
    age_range: str | None = None
    tags: list[str] | None = None
    portrait_url: str | None = None
    portrait_asset_id: str | None = None
    reference_asset_ids: list[str] | None = None


class AddTagRequest(BaseModel):
    tag: str = Field(..., description="要添加的标签")


class CharacterLinkStoryRequest(BaseModel):
    story_id: str = Field(..., description="故事项目 ID")


# ---- 路由 ----

@router.get("", summary="列出角色")
async def list_characters(
    keyword: str | None = Query(None, description="搜索角色名称"),
    source_type: str | None = Query(None, description="来源类型过滤，如 ai_generated"),
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
    async with get_session() as session:
        service = CharacterService(session)
        items, total = await service.list(
            keyword=keyword,
            source_type=source_type,
            role=role,
            tag=tag,
            is_favorite=is_favorite,
            page=page,
            page_size=page_size,
        )
        return {
            "success": True,
            "data": [service.to_response(c) for c in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.post("", summary="创建角色")
async def create_character(req: CharacterCreateRequest):
    """创建新角色"""
    async with get_session() as session:
        service = CharacterService(session)
        character = await service.create(
            name=req.name,
            role=req.role,
            source_types=req.source_types,
            appearance=req.appearance,
            personality=req.personality,
            costume_hint=req.costume_hint,
            background=req.background,
            age_range=req.age_range,
            tags=req.tags,
            portrait_url=req.portrait_url,
            portrait_asset_id=req.portrait_asset_id,
            reference_asset_ids=req.reference_asset_ids,
        )
        return {"success": True, "data": service.to_response(character)}


@router.get("/{character_id}", summary="获取角色详情")
async def get_character(character_id: str):
    """获取单个角色的完整信息"""
    async with get_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.to_response(character)}


@router.put("/{character_id}", summary="更新角色")
async def update_character(character_id: str, req: CharacterUpdateRequest):
    """更新角色信息（支持部分更新）"""
    async with get_session() as session:
        service = CharacterService(session)
        # 检查是否已冻结
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        if character.is_frozen and any(
            v is not None for v in [
                req.appearance, req.costume_hint, req.portrait_url, req.portrait_asset_id
            ]
        ):
            raise HTTPException(status_code=403, detail="角色已冻结，禁止修改外观描述")

        updated = await service.update(
            character_id=character_id,
            name=req.name,
            role=req.role,
            source_types=req.source_types,
            appearance=req.appearance,
            personality=req.personality,
            costume_hint=req.costume_hint,
            background=req.background,
            age_range=req.age_range,
            tags=req.tags,
            portrait_url=req.portrait_url,
            portrait_asset_id=req.portrait_asset_id,
            reference_asset_ids=req.reference_asset_ids,
        )
        return {"success": True, "data": service.to_response(updated)}


@router.delete("/{character_id}", summary="删除角色")
async def delete_character(character_id: str):
    """删除角色"""
    async with get_session() as session:
        service = CharacterService(session)
        deleted = await service.delete(character_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True}


@router.get("/tags/all", summary="获取所有自定义标签")
async def get_all_character_tags():
    """获取所有角色使用的自定义标签（去重）"""
    async with get_session() as session:
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


@router.post("/{character_id}/tags", summary="添加自定义标签")
async def add_character_tag(character_id: str, req: AddTagRequest):
    """为角色添加一个自定义标签"""
    async with get_session() as session:
        service = CharacterService(session)
        character = await service.add_tag(character_id, req.tag)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.to_response(character)}


@router.delete("/{character_id}/tags/{tag}", summary="移除自定义标签")
async def remove_character_tag(character_id: str, tag: str):
    """移除角色的一个自定义标签"""
    async with get_session() as session:
        service = CharacterService(session)
        character = await service.remove_tag(character_id, tag)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.to_response(character)}


@router.post("/{character_id}/favorite", summary="切换收藏状态")
async def toggle_favorite(character_id: str):
    """切换角色的收藏状态"""
    async with get_session() as session:
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
    """将角色关联到指定的故事项目（增加引用计数）"""
    async with get_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        await service.link_to_story(character_id, req.story_id)
        return {"success": True}
