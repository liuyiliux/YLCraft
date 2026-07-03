"""Pydantic contracts for the creative project workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    signature_items: list[str] = Field(default_factory=list)
    expressions: list[str] = Field(default_factory=list)
    poses: list[str] = Field(default_factory=list)
    visual_consistency: str = ""
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
    time_of_day: str = ""
    weather: str = ""
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
    props: list[str] = Field(default_factory=list)
    spatial_axis: str = ""
    character_positions: str = ""
    movement_path: str = ""
    shot_design: str = ""
    image_prompt: str = ""

    @field_validator(
        "title",
        "location",
        "time_of_day",
        "weather",
        "purpose",
        "scene_role",
        "objective",
        "conflict",
        "action",
        "key_dialogue",
        "emotion",
        "emotional_turn",
        "visual_focus",
        "spatial_axis",
        "character_positions",
        "movement_path",
        "shot_design",
        "image_prompt",
        mode="before",
    )
    @classmethod
    def coerce_text_field(cls, value):
        if value is None:
            return ""
        if isinstance(value, list):
            return " / ".join(str(item).strip() for item in value if str(item).strip())
        if isinstance(value, dict):
            return "；".join(
                f"{key}: {item}"
                for key, item in value.items()
                if str(item).strip()
            )
        return str(value)

    @field_validator("characters", "beats", "props", mode="before")
    @classmethod
    def coerce_list_field(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [str(value)]


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
    source_panel_numbers: list[int] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    portrait_node_ids: list[str] = Field(default_factory=list)
    portrait_version_ids: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)


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
    reference_asset_ids: list[str] = Field(default_factory=list)
    reference_notes: list[str] = Field(default_factory=list)


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
    panel_goal: str = ""
    location: str = ""
    image_prompt: str = ""
    camera_hint: str = ""
    camera_angle: str = ""
    camera_motion: str = ""
    shot_size: str = ""
    composition: str = ""
    blocking: str = ""
    characters: list[str] = Field(default_factory=list)
    action: str = ""
    emotion: str = ""
    props: list[str] = Field(default_factory=list)
    dialogue_bubbles: list[str] = Field(default_factory=list)
    sound_effect: str = ""
    negative_prompt: str = ""
    character_ids: list[str] = Field(default_factory=list)
    portrait_node_ids: list[str] = Field(default_factory=list)
    portrait_version_ids: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    reference_notes: list[str] = Field(default_factory=list)
    notes: str = ""


class StoryboardSchema(FlexibleModel):
    episode_number: int = 1
    title: str = ""
    visual_style: str = ""
    panels: list[StoryboardPanelSchema] = Field(default_factory=list)


class ReferenceAssetMatchItemSchema(FlexibleModel):
    target_number: int
    reference_asset_ids: list[str] = Field(default_factory=list)
    reference_notes: list[str] = Field(default_factory=list)
    reason: str = ""


class ReferenceAssetMatchSchema(FlexibleModel):
    items: list[ReferenceAssetMatchItemSchema] = Field(default_factory=list)
