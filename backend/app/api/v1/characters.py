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
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.services.character.service import CharacterService
from app.db.models.character import CharacterSourceType, CharacterRole

router = APIRouter()
logger = logging.getLogger("ylcraft.characters")


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
    async with get_async_session() as session:
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
    async with get_async_session() as session:
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
    """将角色关联到指定的故事项目（增加引用计数）"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        await service.link_to_story(character_id, req.story_id)
        return {"success": True}


@router.get("/{character_id}", summary="获取角色详情")
async def get_character(character_id: str):
    """获取单个角色的完整信息"""
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"success": True, "data": service.to_response(character)}


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
    prompt: str = Field(..., description="提示词")
    provider: Optional[str] = Field(None, description="指定生图后端（image backend name）")
    model: Optional[str] = Field(None, description="动态指定模型名（控制花费）")
    size: Optional[str] = Field("1024x1024", description="图片尺寸")
    n: Optional[int] = Field(1, description="生成数量（>1 时取首张）")
    negative_prompt: Optional[str] = Field(None, description="负向提示词")


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

    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    async with get_async_session() as session:
        # 1. 获取角色
        character = await session.get(Character, character_id)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")

        # 2. 生图
        img_req = ImageGenerationRequest(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or "",
            size=req.size or "1024x1024",
            n=req.n or 1,
            provider=req.provider or "",
            model=req.model or "",
        )

        # 准备日志服务（生图前/后均写入，便于追踪失败原因）
        from app.services.creative_project.service import CreativeProjectService
        log_service = CreativeProjectService(session)

        try:
            result = await manager.generate_image(img_req)
        except Exception as e:
            logger.exception(f"[portrait/generate] generate_image failed: {e}")
            # 写入失败日志
            try:
                await log_service.log_generation(
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="generate_image",
                    status="failed",
                    provider=req.provider or "",
                    model=req.model or "",
                    prompt=req.prompt,
                    request_payload={
                        "character_id": character.id,
                        "character_name": character.name,
                        "size": req.size,
                        "n": req.n,
                        "negative_prompt": req.negative_prompt,
                        "provider": req.provider,
                        "model": req.model,
                    },
                    raw_response=str(e),
                    validation_error=type(e).__name__,
                )
                await session.flush()
            except Exception as log_err:
                logger.warning(f"[portrait/generate] log write failed: {log_err}")
            raise HTTPException(status_code=500, detail=f"生图失败: {e}")

        if not result.success:
            # 写入失败日志
            try:
                await log_service.log_generation(
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="generate_image",
                    status="failed",
                    provider=result.provider or req.provider or "",
                    model=result.model or req.model or "",
                    prompt=req.prompt,
                    request_payload={
                        "character_id": character.id,
                        "character_name": character.name,
                        "size": req.size,
                        "n": req.n,
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

        url = urls[0] if urls else ""
        local_path = local_paths[0] if local_paths else ""

        # 3. 写入资产中枢
        try:
            asset_hub_result = await AssetHubFacade(session).create_or_update_character_portrait(
                character=character,
                portrait_url=url,
                local_path=local_path,
                prompt=req.prompt,
                provider=result.provider or req.provider or "",
                model=result.model or req.model or "",
                negative_prompt=req.negative_prompt or "",
                size=req.size or "",
                seed=result.seed,
                generation_params={"n": req.n},
            )

            # 4. 更新 Character
            character.portrait_url = url
            character.portrait_node_id = asset_hub_result.node_id
            character.updated_at = datetime.now()
            await session.flush()
            await session.refresh(character)

            # 5. 写入成功日志
            try:
                await log_service.log_generation(
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="portrait_generate",
                    status="success",
                    provider=result.provider or req.provider or "",
                    model=result.model or req.model or "",
                    prompt=req.prompt,
                    request_payload={
                        "character_id": character.id,
                        "character_name": character.name,
                        "size": req.size,
                        "n": req.n,
                        "negative_prompt": req.negative_prompt,
                    },
                    raw_response=str(url),
                    normalized={
                        "node_id": asset_hub_result.node_id,
                        "version_id": asset_hub_result.version_id,
                        "version_number": asset_hub_result.version_number,
                        "representation_id": asset_hub_result.representation_id,
                        "local_path": local_path,
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
                await log_service.log_generation(
                    scene="character_portrait",
                    ref_id=character.id,
                    stage="asset_hub_sync",
                    status="failed",
                    provider=result.provider or req.provider or "",
                    model=result.model or req.model or "",
                    prompt=req.prompt,
                    request_payload={"character_id": character.id},
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
            "character": {
                "id": character.id,
                "name": character.name,
                "portrait_url": character.portrait_url,
                "portrait_node_id": str(character.portrait_node_id) if character.portrait_node_id else None,
            },
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
