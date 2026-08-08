"""Pydantic contracts for the creative project workflow."""

from __future__ import annotations

from typing import Any

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


class NarrativeHealthIssueSchema(FlexibleModel):
    """One project-local data integrity finding for the narrative runtime."""

    code: str
    severity: str = "warning"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ProjectNarrativeHealthSchema(FlexibleModel):
    """Read-only health contract used before narrative state is rebuilt."""

    project_id: str
    status: str = "healthy"
    checked_at: str
    summary: dict[str, int] = Field(default_factory=dict)
    issues: list[NarrativeHealthIssueSchema] = Field(default_factory=list)


class NarrativeEvidenceAnchorSchema(FlexibleModel):
    paragraph_index: int | None = None
    excerpt: str = ""
    source_label: str = ""


class NarrativeEventSchema(FlexibleModel):
    event_type: str = "event"
    title: str = ""
    description: str = ""
    participants: list[str] = Field(default_factory=list)
    location: str = ""
    timeline_order: int | None = None
    evidence_anchor: NarrativeEvidenceAnchorSchema = Field(default_factory=NarrativeEvidenceAnchorSchema)


class NarrativeForeshadowingSchema(FlexibleModel):
    kind: str = "clue"
    statement: str = ""
    planted_chapter: int = 1
    expected_window: dict[str, int] = Field(default_factory=dict)
    evidence_anchor: NarrativeEvidenceAnchorSchema = Field(default_factory=NarrativeEvidenceAnchorSchema)


class NarrativeSnapshotSchema(FlexibleModel):
    summary: str = ""
    character_state: list[dict[str, Any]] = Field(default_factory=list)
    timeline_delta: list[dict[str, Any]] = Field(default_factory=list)
    location_delta: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    events: list[NarrativeEventSchema] = Field(default_factory=list)
    foreshadowing: list[NarrativeForeshadowingSchema] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


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


class WriterRoomSceneBeatSchema(FlexibleModel):
    scene_number: int = 1
    title: str = ""
    purpose: str = ""
    location: str = ""
    characters: list[str] = Field(default_factory=list)
    dramatic_question: str = ""
    character_wants: list[str] = Field(default_factory=list)
    obstacle: str = ""
    conflict_pressure: str = ""
    action_beats: list[str] = Field(default_factory=list)
    subtext: str = ""
    sensory_anchors: list[str] = Field(default_factory=list)
    turning_point: str = ""
    hook: str = ""


class WriterRoomSceneBeatsSchema(FlexibleModel):
    chapter_number: int = 1
    title: str = ""
    summary: str = ""
    scene_beats: list[WriterRoomSceneBeatSchema] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)


class WriterRoomCharacterReactionSchema(FlexibleModel):
    character: str = ""
    public_goal: str = ""
    private_goal: str = ""
    fear: str = ""
    knows: str = ""
    hides: str = ""
    likely_action: str = ""
    likely_dialogue: list[str] = Field(default_factory=list)
    subtext: str = ""
    voice_rules: list[str] = Field(default_factory=list)


class WriterRoomCharacterRehearsalSchema(FlexibleModel):
    chapter_number: int = 1
    title: str = ""
    scene_rehearsals: list[dict[str, Any]] = Field(default_factory=list)
    character_reactions: list[WriterRoomCharacterReactionSchema] = Field(default_factory=list)
    usable_conflicts: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)


class WriterRoomReviewIssueSchema(FlexibleModel):
    severity: str = "medium"
    category: str = ""
    location: str = ""
    problem: str = ""
    suggestion: str = ""
    rewrite_instruction: str = ""


class WriterRoomProseReviewSchema(FlexibleModel):
    chapter_number: int = 1
    title: str = ""
    overall_score: int = Field(default=0, ge=0, le=100)
    ai_smell_score: int = Field(default=0, ge=0, le=100)
    quality_tags: list[str] = Field(default_factory=list)
    ai_smell_checks: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    issues: list[WriterRoomReviewIssueSchema] = Field(default_factory=list)
    rewrite_plan: list[str] = Field(default_factory=list)
    approval_recommendation: str = ""
    # Editorial review may also surface continuity facts worth locking. Kept as
    # bounded dicts (not a typed sub-model) so the schema stays forward-ref safe
    # and the dict contract matches extract_continuity_candidates_v2.
    continuity_candidates: list[dict[str, Any]] = Field(default_factory=list)


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
    # image_prompt describes the still frame; video_prompt only describes the
    # motion that happens after that frame is established.
    video_prompt: str = ""
    duration_seconds: int = 5
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
    music_hint: str = ""
    generate_audio: bool = False
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


# ---------------------------------------------------------------------------
# Continuity fact workflow (creative-project-continuity-facts OpenSpec)
# ---------------------------------------------------------------------------


class ContinuityEvidenceAnchorSchema(FlexibleModel):
    chapter_number: int | None = None
    paragraph_index: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    excerpt: str = ""  # 有界证据摘要；长文本回到 source_content_id


class ContinuityCandidatePayloadSchema(FlexibleModel):
    """单条候选事实载荷（与 design.md Contract 对齐）。"""

    entity_type: str = "other"
    entity_name: str = ""
    claim: str = ""
    evidence_excerpt: str = ""
    evidence_anchor: ContinuityEvidenceAnchorSchema = Field(
        default_factory=ContinuityEvidenceAnchorSchema
    )
    severity: str = "info"
    suggested_action: str = "create_fact"
    target_fact_type: str = "world_asset"


class ContinuityExtractRequestSchema(FlexibleModel):
    content_id: str
    source_kind: str = "prose_review"
    candidates: list[ContinuityCandidatePayloadSchema] = Field(default_factory=list)


class ContinuityDecisionRequestSchema(FlexibleModel):
    note: str = ""
    merged_fact_id: str | None = None  # 仅 merge 使用


class ContinuityCandidateSchema(FlexibleModel):
    id: str
    project_id: str
    source_content_id: str | None = None
    source_generation_log_id: str | None = None
    source_kind: str = "prose_review"
    source_fingerprint: str = ""

    entity_type: str = "other"
    entity_name: str = ""
    claim: str = ""
    evidence_excerpt: str = ""
    evidence_anchor: dict[str, Any] = Field(default_factory=dict)
    severity: str = "info"
    suggested_action: str = "create_fact"
    target_fact_type: str = "world_asset"

    status: str = "pending"
    resolved_fact_id: str | None = None
    resolution_note: str = ""
    resolved_at: str | None = None

    created_at: str | None = None
    updated_at: str | None = None


class ContinuityContextSummarySchema(FlexibleModel):
    project_id: str
    locked_fact_count: int = 0
    fact_types: dict[str, int] = Field(default_factory=dict)
    source_chapters: list[int] = Field(default_factory=list)
    pending_candidate_count: int = 0
    fingerprint: str = ""


class ContinuityConflictSchema(FlexibleModel):
    entity_type: str = "other"
    entity_name: str = ""
    claim: str = ""
    contradicting_fact_id: str = ""
    contradicting_fact_excerpt: str = ""
    severity: str = "warning"
    suggested_action: str = "resolve_conflict"
    evidence_excerpt: str = ""
    evidence_anchor: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ContinuityCheckResponseSchema(FlexibleModel):
    project_id: str
    chapter_number: int | None = None
    candidate_id: str | None = None
    checked_claims: list[str] = Field(default_factory=list)
    conflicts: list[ContinuityConflictSchema] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class ContinuityRewriteResultSchema(FlexibleModel):
    content_id: str
    project_id: str
    source_content_id: str
    paragraph_index: int
    original_paragraph: str = ""
    rewritten_paragraph: str = ""
    status: str = "candidate"  # candidate | anchor_not_found
    anchor_not_found: bool = False
    candidate_content_id: str | None = None
    instruction: str = ""
