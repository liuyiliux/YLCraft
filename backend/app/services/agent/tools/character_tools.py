"""Character tools exposed to the Agent Center."""

from __future__ import annotations

from typing import Any

from app.db.database import get_async_session
from app.services.agent.registry import register_tool
from app.services.character.portrait_prompt import build_portrait_prompt, synthesize_visual_profile
from app.services.character.service import CharacterService


def _character_summary(data: dict[str, Any]) -> dict[str, Any]:
    identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
    visual_profile = identity.get("visual_profile") if isinstance(identity.get("visual_profile"), dict) else {}
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "role": data.get("role"),
        "role_label": data.get("role_label"),
        "age_range": data.get("age_range"),
        "appearance": data.get("appearance"),
        "personality": data.get("personality"),
        "costume_hint": data.get("costume_hint"),
        "visual_consistency": data.get("visual_consistency"),
        "visual_profile": visual_profile,
        "portrait_url": data.get("portrait_url"),
        "portrait_node_id": data.get("portrait_node_id"),
        "reference_asset_ids": data.get("reference_asset_ids") or [],
        "tags": data.get("tags") or [],
        "is_frozen": data.get("is_frozen"),
        "updated_at": data.get("updated_at"),
    }


@register_tool(
    name="list_characters",
    description="列出角色库角色，可按关键词、角色定位、标签、收藏状态过滤。",
    category="character",
    examples=["列出主角和反派", "找一下导演这个角色", "有哪些收藏角色"],
    input_schema_note="keyword/role/tag 可为空；is_favorite 为空表示不过滤；page_size 建议 10-30。",
    output_schema_note="返回 success、total、characters；characters 含 id/name/role/appearance/portrait_node_id/reference_asset_ids/tags。",
    risk_level="read",
    output_type="character_list",
)
async def list_characters(
    keyword: str = "",
    role: str = "",
    tag: str = "",
    is_favorite: bool | None = None,
    page: int = 1,
    page_size: int = 20,
):
    async with get_async_session() as session:
        service = CharacterService(session)
        items, total = await service.list(
            keyword=keyword or None,
            role=role or None,
            tag=tag or None,
            is_favorite=is_favorite,
            page=max(1, int(page or 1)),
            page_size=max(1, min(int(page_size or 20), 50)),
        )
        characters = [_character_summary(service.to_response(item)) for item in items]
        return {"success": True, "total": total, "characters": characters}


@register_tool(
    name="inspect_character",
    description="读取角色完整设定、视觉卡、立绘节点、参考素材和项目/世界使用情况。",
    category="character",
    examples=["查看这个角色的视觉卡", "检查导演角色有没有立绘节点", "看看角色在哪些项目里使用"],
    input_schema_note="必须提供 character_id。",
    output_schema_note="返回 character 和 world_usages；character 包含 Character Bible、identity.visual_profile、portrait_node_id、reference_asset_ids。",
    risk_level="read",
    output_type="character_detail",
)
async def inspect_character(character_id: str):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            return {"success": False, "message": "角色不存在", "character_id": character_id}
        data = service.to_response(character)
        data["world_usages"] = await service.list_world_usages(character_id)
        return {"success": True, "character": data, "world_usages": data["world_usages"]}


@register_tool(
    name="preview_character_portrait_prompt",
    description="根据角色卡和视觉卡预览立绘/九宫格/关键视觉生图提示词，不实际调用生图模型。",
    category="character",
    examples=["生成导演角色的九宫格动作提示词", "预览主角立绘提示词", "用二次元国漫风格输出提示词"],
    input_schema_note="必须提供 character_id；preset 支持 main_portrait/headshot_icon/multi_view_sheet/pose_grid_3x3/expression_grid_3x3/key_visual；visual_profile/style_override/negative_override 可选。",
    output_schema_note="返回 prompt、negative_prompt、visual_profile_snapshot、preset、prompt_template_version；不会写入数据库也不会消耗生图额度。",
    risk_level="read",
    output_type="character_portrait_prompt",
)
async def preview_character_portrait_prompt(
    character_id: str,
    preset: str = "main_portrait",
    visual_profile: dict[str, Any] | None = None,
    style_override: str = "",
    negative_override: str = "",
    language: str = "zh",
):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            return {"success": False, "message": "角色不存在", "character_id": character_id}
        bundle = build_portrait_prompt(
            character=character,
            preset=preset,
            visual_profile=visual_profile or None,
            style_override=style_override,
            negative_override=negative_override,
            language=language or "zh",
        )
        return {"success": True, "character_id": character_id, "character_name": character.name, **bundle}


@register_tool(
    name="update_character_visual_profile",
    description="更新角色视觉卡，用于把 AI 补全后的脸部、发型、服装、负面约束和一致性规则写回角色库。",
    category="character",
    examples=["把角色视觉卡补全写回去", "给导演角色写入二次元国漫风格约束"],
    input_schema_note="必须提供 character_id；visual_profile 为 identity.visual_profile 合并字段；appearance/costume_hint/visual_consistency/reference_asset_ids 可选。",
    output_schema_note="返回 character 和 visual_profile；会写入角色表，冻结角色会拒绝外观类修改。",
    risk_level="write",
    output_type="character_visual_profile_updated",
)
async def update_character_visual_profile(
    character_id: str,
    visual_profile: dict[str, Any] | None = None,
    appearance: str = "",
    costume_hint: str = "",
    visual_consistency: str = "",
    reference_asset_ids: list[str] | None = None,
):
    async with get_async_session() as session:
        service = CharacterService(session)
        character = await service.get_by_id(character_id)
        if not character:
            return {"success": False, "message": "角色不存在", "character_id": character_id}
        if character.is_frozen and (appearance or costume_hint or visual_consistency or visual_profile):
            return {"success": False, "message": "角色已冻结，不能修改外观或视觉卡", "character_id": character_id}

        current = service.to_response(character)
        identity = current.get("identity") if isinstance(current.get("identity"), dict) else {}
        merged_visual = {
            **(identity.get("visual_profile") if isinstance(identity.get("visual_profile"), dict) else {}),
            **(visual_profile or {}),
        }
        identity["visual_profile"] = merged_visual
        updated = await service.update(
            character_id,
            identity=identity,
            appearance=appearance or None,
            costume_hint=costume_hint or None,
            visual_consistency=visual_consistency or None,
            reference_asset_ids=reference_asset_ids,
        )
        if not updated:
            return {"success": False, "message": "角色更新失败", "character_id": character_id}
        data = service.to_response(updated)
        return {
            "success": True,
            "character": _character_summary(data),
            "visual_profile": synthesize_visual_profile(updated),
        }
