"""
YLCraft — Story Maker API (重写)

POST /api/v1/story/generate — 故事生成（LLM）
POST /api/v1/story/characters — 保存角色到库
POST /api/v1/story/portrait — 为角色生成肖像
GET /api/v1/story/{story_id} — 获取故事详情
GET /api/v1/story — 列出故事列表
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db.database import get_session
from app.db.models.story import (
    Story,
    StoryCharacterPortrait,
    StoryStatus,
    StoryStyle,
)
from app.services.story import StoryGenerationService, StoryGenerationRequest

logger = logging.getLogger("ylcraft.story")
router = APIRouter()


# ── Request / Response Models ──────────────────────────────────

class StoryGenerateRequest(BaseModel):
    topic: str
    style: str = "short_drama"  # short_drama | manga
    num_scenes: int = 8


class CharacterSaveRequest(BaseModel):
    story_id: str
    characters: list[dict]  # 从 LLM 输出中提取的角色列表
    save_to_library: bool = True  # 是否保存到角色库


class PortraitGenerateRequest(BaseModel):
    story_id: str
    character_name: str
    appearance: str
    costume_hint: str = ""
    style_hint: str = ""
    generate_multi_view: bool = True  # 是否生成多视图（4张）


class StoryGenerateResponse(BaseModel):
    success: bool
    message: str
    story_id: str | None = None
    data: dict | None = None


class StoryListResponse(BaseModel):
    success: bool
    stories: list[dict] = []
    total: int = 0


# ── Endpoints ─────────────────────────────────────────────────


@router.post("/generate", response_model=StoryGenerateResponse, summary="生成故事结构")
async def generate_story(
    request: StoryGenerateRequest,
    session: Session = Depends(get_session),
):
    """
    调用 LLM 生成完整的故事结构（大纲 + 角色 + 分镜）。
    返回：story_id 和生成的内容。
    """
    try:
        logger.info(f"Story generate request: topic={request.topic}, style={request.style}")

        # 调用 LLM 生成
        gen_service = StoryGenerationService()
        gen_request = StoryGenerationRequest(
            topic=request.topic,
            style=request.style,
            num_scenes=request.num_scenes,
        )
        result = await gen_service.generate(gen_request)

        # 创建 Story 记录
        story = Story(
            title=result.title,
            topic=request.topic,
            style=request.style,
            plot_outline=result.plot_outline,
            style_hint=result.style_hint,
            music_hint=result.music_hint,
            characters_json=json.dumps([c.to_dict() for c in result.characters], ensure_ascii=False),
            scenes_json=json.dumps([s.to_dict() for s in result.scenes], ensure_ascii=False),
            scene_count=len(result.scenes),
            status=StoryStatus.COMPLETED.value,
        )
        session.add(story)
        session.commit()
        session.refresh(story)

        logger.info(f"Story created: id={story.id}, title={story.title}")

        return StoryGenerateResponse(
            success=True,
            message="故事生成成功",
            story_id=story.id,
            data=result.to_dict(),
        )

    except Exception as e:
        logger.error(f"Story generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"故事生成失败: {str(e)}")


@router.post("/characters", response_model=dict, summary="保存角色到角色库")
async def save_characters(
    request: CharacterSaveRequest,
    session: Session = Depends(get_session),
):
    """
    将生成的故事角色保存到角色库（Character 表）。
    可选：同时关联到 story_id。
    """
    try:
        from app.db.models.character import Character, CharacterRole
        from app.services.character import CharacterService

        saved = []
        if request.save_to_library:
            char_service = CharacterService()

            for char_data in request.characters:
                # 构建 Character 创建数据
                char_info = {
                    "name": char_data.get("name", ""),
                    "role": char_data.get("role", "supporting"),
                    "description": char_data.get("description", ""),
                    "personality": char_data.get("personality", ""),
                    "appearance": char_data.get("appearance", ""),
                    "costume_hint": char_data.get("costume_hint", ""),
                    # tags 等需要 JSON 序列化
                    "tags": json.dumps(["story_generated"], ensure_ascii=False),
                    "source_types": json.dumps(["ai_generated"], ensure_ascii=False),
                }

                try:
                    character = char_service.create(char_info)
                    saved.append({
                        "name": character.name,
                        "id": character.id,
                        "status": "saved",
                    })
                except Exception as e:
                    logger.warning(f"Failed to save character {char_data.get('name')}: {e}")
                    saved.append({
                        "name": char_data.get("name", ""),
                        "status": "failed",
                        "error": str(e),
                    })

        return {
            "success": True,
            "message": f"已处理 {len(request.characters)} 个角色",
            "saved": saved,
        }

    except Exception as e:
        logger.error(f"Save characters failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存角色失败: {str(e)}")


@router.post("/portrait", response_model=dict, summary="生成角色肖像")
async def generate_portrait(
    request: PortraitGenerateRequest,
    session: Session = Depends(get_session),
):
    """
    为角色生成肖像（单张或多视图）。
    通过 ImageBackend（Minimax/Seedance）生成。
    """
    try:
        from app.services.backend_registry import BackendManager
        from app.db.models.story import StoryCharacterPortrait

        # 构建 prompt
        prompt = f"{request.appearance}, {request.costume_hint}"
        if request.style_hint:
            prompt += f"，风格：{request.style_hint}"

        views = []
        if request.generate_multi_view:
            views = ["正面", "四分之三侧脸", "侧脸", "背面"]
        else:
            views = ["正面"]

        portrait_urls = []
        seed = ""

        backend_manager = BackendManager()

        for view in views:
            view_prompt = f"{prompt}，视角：{view}，确保角色外观高度一致"
            try:
                result = await backend_manager.generate_image(
                    prompt=view_prompt,
                    aspect_ratio="3:4",  # 肖像比例
                )
                url = result.get("url", "")
                if url:
                    portrait_urls.append(url)
                if not seed and result.get("seed"):
                    seed = result["seed"]
            except Exception as e:
                logger.warning(f"Portrait generation failed for view {view}: {e}")

        # 保存到数据库
        portrait = StoryCharacterPortrait(
            story_id=request.story_id,
            character_name=request.character_name,
            portrait_urls=json.dumps(portrait_urls, ensure_ascii=False),
            selected_url=portrait_urls[0] if portrait_urls else "",
            prompt_used=prompt,
            seed=seed,
        )
        session.add(portrait)
        session.commit()

        return {
            "success": True,
            "message": f"生成了 {len(portrait_urls)} 张肖像",
            "portrait_urls": portrait_urls,
            "portrait_id": portrait.id,
        }

    except Exception as e:
        logger.error(f"Portrait generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"肖像生成失败: {str(e)}")


@router.get("/{story_id}", response_model=dict, summary="获取故事详情")
async def get_story(
    story_id: str,
    session: Session = Depends(get_session),
):
    """获取指定故事的完整信息（含角色、分镜）"""
    story = session.get(Story, story_id)
    if not story:
        raise HTTPException(status_code=404, detail="故事不存在")

    # 解析 JSON 字段
    characters = json.loads(story.characters_json) if story.characters_json else []
    scenes = json.loads(story.scenes_json) if story.scenes_json else []

    # 获取肖像
    portraits = session.query(StoryCharacterPortrait).filter(
        StoryCharacterPortrait.story_id == story_id
    ).all()
    portraits_dict = {}
    for p in portraits:
        portraits_dict[p.character_name] = {
            "portrait_urls": json.loads(p.portrait_urls) if p.portrait_urls else [],
            "selected_url": p.selected_url,
        }

    return {
        "success": True,
        "story": {
            "id": story.id,
            "title": story.title,
            "topic": story.topic,
            "style": story.style,
            "plot_outline": story.plot_outline,
            "style_hint": story.style_hint,
            "music_hint": story.music_hint,
            "status": story.status,
            "scene_count": story.scene_count,
            "created_at": story.created_at.isoformat() if story.created_at else None,
        },
        "characters": characters,
        "scenes": scenes,
        "portraits": portraits_dict,
    }


@router.get("", response_model=StoryListResponse, summary="列出故事列表")
async def list_stories(
    session: Session = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
):
    """列出所有故事项目"""
    from sqlmodel import select

    stmt = select(Story).order_by(Story.created_at.desc()).offset(offset).limit(limit)
    stories = session.exec(stmt).all()

    total_stmt = select(Story)
    total = len(session.exec(total_stmt).all())

    result = []
    for s in stories:
        result.append({
            "id": s.id,
            "title": s.title,
            "topic": s.topic,
            "style": s.style,
            "status": s.status,
            "scene_count": s.scene_count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    return StoryListResponse(success=True, stories=result, total=total)
