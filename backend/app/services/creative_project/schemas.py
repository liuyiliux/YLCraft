"""Pydantic contracts for the creative project workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class StoryCharacterSchema(FlexibleModel):
    name: str = ""
    role: str = ""
    age_range: str = ""
    appearance: str = ""
    costume_hint: str = ""
    personality: str = ""
    background: str = ""
    goal: str = ""
    arc: str = ""
    visual_tags: list[str] = Field(default_factory=list)
    voice: str = ""
    image_prompt: str = ""
    negative_prompt: str = ""
    portrait_asset_id: str = ""
    reference_asset_ids: list[str] = Field(default_factory=list)
    character_id: str = ""


class StoryArcSchema(FlexibleModel):
    beginning: str = ""
    middle: str = ""
    climax: str = ""
    ending_direction: str = ""


class StoryLocationSchema(FlexibleModel):
    name: str = ""
    role: str = ""
    visual_description: str = ""
    mood: str = ""
    reusable_asset_note: str = ""


class StoryOutlineSchema(FlexibleModel):
    title: str = ""
    genre: list[str] = Field(default_factory=list)
    premise: str = ""
    logline: str = ""
    selling_points: list[str] = Field(default_factory=list)
    target_reader: str = ""
    audience_emotion: str = ""
    tone: str = ""
    worldview: str = ""
    narrative_rules: list[str] = Field(default_factory=list)
    main_conflict: str = ""
    themes: list[str] = Field(default_factory=list)
    characters: list[StoryCharacterSchema] = Field(default_factory=list)
    relationship_map: str = ""
    locations: list[StoryLocationSchema] = Field(default_factory=list)
    story_arc: StoryArcSchema = Field(default_factory=StoryArcSchema)
    visual_style: str = ""
    image_style_prompt: str = ""
    production_notes: list[str] = Field(default_factory=list)


class ChapterPlanItemSchema(FlexibleModel):
    chapter_number: int
    title: str = ""
    goal: str = ""
    conflict: str = ""
    key_events: list[str] = Field(default_factory=list)
    character_focus: list[str] = Field(default_factory=list)
    ending_hook: str = ""
    status: str = "planned"


class ChapterPlanSchema(FlexibleModel):
    chapter_count: int = 12
    chapters: list[ChapterPlanItemSchema] = Field(default_factory=list)


class ChapterOutlineSceneSchema(FlexibleModel):
    scene_number: int
    title: str = ""
    location: str = ""
    characters: list[str] = Field(default_factory=list)
    purpose: str = ""
    scene_role: str = ""
    objective: str = ""
    conflict: str = ""
    beats: list[str] = Field(default_factory=list)
    action: str = ""
    key_dialogue: str = ""
    emotion: str = ""
    emotional_turn: str = ""
    visual_focus: str = ""
    shot_design: str = ""
    image_prompt: str = ""


class ChapterOutlineSchema(FlexibleModel):
    chapter_number: int = 1
    title: str = ""
    summary: str = ""
    objective: str = ""
    keywords: list[str] = Field(default_factory=list)
    scenes: list[ChapterOutlineSceneSchema] = Field(default_factory=list)
    key_dialogues: list[str] = Field(default_factory=list)
    foreshadowing: list[str] = Field(default_factory=list)
    ending_hook: str = ""
    continuity_notes: list[str] = Field(default_factory=list)


class ChapterOutlineScenesSchema(FlexibleModel):
    scenes: list[ChapterOutlineSceneSchema] = Field(default_factory=list)


class NovelBodySchema(FlexibleModel):
    chapter_number: int = 1
    title: str = ""
    content: str = ""
    word_count: int = 0
    continuity_notes: list[str] = Field(default_factory=list)


class ComicPageSchema(FlexibleModel):
    page_number: int
    title: str = ""
    content: str = ""
    image_prompt: str = ""


class ComicPagesSchema(FlexibleModel):
    episode_number: int = 1
    chapter_number: int = 1
    title: str = ""
    page_count: int = 10
    visual_style: str = ""
    pages: list[ComicPageSchema] = Field(default_factory=list)


class ScriptDialogueSchema(FlexibleModel):
    character: str = ""
    line: str = ""


class ScriptSceneSchema(FlexibleModel):
    scene_number: int
    location: str = ""
    characters: list[str] = Field(default_factory=list)
    action: str = ""
    dialogue: list[ScriptDialogueSchema] = Field(default_factory=list)
    camera_hint: str = ""
    emotion: str = ""
    image_prompt: str = ""


class ShortDramaScriptSchema(FlexibleModel):
    episode_number: int = 1
    title: str = ""
    duration_target_seconds: int = 90
    hook: str = ""
    scenes: list[ScriptSceneSchema] = Field(default_factory=list)
    ending_hook: str = ""


class StoryboardPanelSchema(FlexibleModel):
    panel_number: int
    source_scene_number: int | None = None
    image_prompt: str = ""
    camera_hint: str = ""
    shot_size: str = ""
    composition: str = ""
    characters: list[str] = Field(default_factory=list)
    action: str = ""
    emotion: str = ""
    dialogue_bubbles: list[str] = Field(default_factory=list)
    sound_effect: str = ""
    negative_prompt: str = ""
    notes: str = ""


class StoryboardSchema(FlexibleModel):
    episode_number: int = 1
    title: str = ""
    visual_style: str = ""
    panels: list[StoryboardPanelSchema] = Field(default_factory=list)
