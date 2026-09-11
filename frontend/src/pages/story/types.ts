/**
 * 创作项目工作台的类型定义。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，类型内容与原文件逐字一致。
 */
import { ChapterPlanItem } from '../../types/api'

export type LoadingAction =
  | 'projects'
  | 'create'
  | 'rename'
  | 'outline'
  | 'outline_save'
  | 'chapter_plan'
  | 'chapter_plan_save'
  | 'chapter_outline'
  | 'chapter_outline_scenes'
  | 'novel_body'
  | 'novel_body_refine'
  | 'comic_pages'
  | 'script'
  | 'storyboard'
  | 'reference_match'
  | 'asset'
  | 'canvas_save'
  | 'sync_characters'
  | 'project_bible'
  | 'world_extract'
  | 'delete_project'
  | 'portrait_generate'
  | 'pipeline'
  | 'writer_room'
  | 'agent_advance'
  | null

export type ChapterAction =
  | 'chapter_outline'
  | 'chapter_outline_scenes'
  | 'novel_body'
  | 'novel_body_refine'
  | 'comic_pages'
  | 'script'
  | 'storyboard'
  | null

export interface ProjectContent {
  id: string
  content_type: string
  title: string
  chapter_number?: number
  episode_number?: number
  data: Record<string, any>
  text_content: string
  source_content_id?: string
  version: number
  is_locked?: boolean
  created_at?: string
  updated_at?: string
}

export interface ProjectContentSummary {
  id: string
  content_type: string
  chapter_number?: number
  episode_number?: number
  version: number
  is_locked?: boolean
  created_at?: string
  updated_at?: string
}

export interface WriterRoomReviewIssue {
  category?: string
  severity?: string
  location?: string
  problem?: string
  suggestion?: string
  rewrite_instruction?: string
}

export interface WriterRoomQualitySummary {
  overallScore: number
  aiSmellScore: number
  tags: string[]
  checks: string[]
}

export interface ProjectAssetLink {
  id: string
  project_id: string
  asset_id: string
  content_id?: string
  role: string
  relation: string
  metadata: Record<string, any>
  created_at?: string
}

export type AssetSummary = {
  id: string
  title?: string
  type?: string
  platform?: string
  thumbnail_url?: string
  cover_url?: string
  source_url?: string
  file_path?: string
  tags?: string[]
  metadata?: Record<string, any>
}

export type CharacterReferenceSummary = {
  id: string
  name?: string
  portrait_url?: string
  portrait_node_id?: string
  reference_asset_ids?: string[]
  identity?: Record<string, any>
}

export type ReferenceImageItem = {
  url: string
  source: 'project_asset' | 'character_portrait' | 'character_reference'
  label?: string
  asset_id?: string
  character_id?: string
  character_name?: string
  role?: string
}

export type ProjectGraphNodeType =
  | 'outline'
  | 'chapter'
  | 'character'
  | 'content'
  | 'scene'
  | 'prompt'
  | 'asset'

export type ProjectGraphNode = {
  id: string
  type: ProjectGraphNodeType
  label: string
  subtitle?: string
  status?: string
  x: number
  y: number
  width?: number
  height?: number
  source?: {
    tab?: string
    contentId?: string
    chapterNumber?: number
    prompt?: string
    assetId?: string
    contentType?: string
    sourceType?: string
    sourceIndex?: number | string
  }
  data?: Record<string, any>
}

export type ProjectGraphEdge = {
  id: string
  from: string
  to: string
  type: 'contains' | 'uses' | 'references' | 'derived_from'
  label?: string
}

export type ProjectGraphState = {
  nodes?: ProjectGraphNode[]
  edges?: ProjectGraphEdge[]
  viewport?: { x?: number; y?: number; zoom?: number }
  updated_at?: string
}

export type NarrativeContextPreview = {
  chapter_number: number
  text: string
  persisted: boolean
  metadata: {
    context_snapshot_id?: string
    fingerprint?: string
    overflow?: Array<{ layer: string; budget: number; actual: number; action: string }>
    excluded_sources?: Record<string, string | number>
    layers?: Array<{ id: string; label: string; characters?: number; budget?: number; status?: string }>
  }
}

export type NarrativeForeshadowing = {
  id: string
  statement: string
  kind: string
  status: string
  timing: string
  planted_chapter: number
  expected_window?: { start?: number; end?: number }
  resolution_note?: string
}

export type NarrativeGraphData = {
  nodes: Array<{
    id: string
    type: string
    label: string
    confirmed: boolean
    status?: string
    summary?: string
    source?: { content_id?: string; chapter_number?: number; snapshot_id?: string; foreshadowing_id?: string }
  }>
  edges: Array<{ id: string; type: string; source: string; target: string; confirmed: boolean }>
  include_pending: boolean
}

export type NarrativeHealth = {
  status: 'healthy' | 'attention' | 'blocked' | string
  summary: Record<string, number>
  issues: Array<{
    code: string
    severity: 'info' | 'warning' | 'error' | string
    message: string
    details?: Record<string, unknown>
  }>
}

export type NarrativeRun = {
  id: string
  mode: string
  status: string
  target_chapters: number[]
  current_cursor: number
  trace: Array<{ chapter_number?: number; status?: string; error?: string; error_type?: string; retryable?: boolean }>
  retry_count?: number
  token_usage?: number
  cost_amount?: number
  budget?: { max_cost_amount?: number | null; max_token_usage?: number | null; metering?: string }
  error_message?: string
}

export type StoryboardPanelReferencePlan = {
  referenceAssetIds: string[]
  characterIds: string[]
  portraitNodeIds: string[]
  portraitVersionIds: string[]
  projectReferenceItems: ReferenceImageItem[]
  characterReferenceItems: ReferenceImageItem[]
  portraitNodeReferenceItems: ReferenceImageItem[]
  imageCollection: ReferenceImageItem[]
  unresolvedCharacterIds: string[]
  sentCount: number
  hasEffectivePlan: boolean
}

export type StoryboardReferenceSummary = {
  promptPanels: number
  effectivePlanPanels: number
  usableReferencePanels: number
  generatedPanels: number
  totalReferenceImages: number
  uniqueReferenceImages: number
  sentReferenceImages: number
  uniqueCharacterIds: string[]
  unresolvedCharacterIds: string[]
  missingEffectivePlanPanels: number
  noUsableReferencePanels: number
}

export interface ProjectGenerationLog {
  id: string
  project_id: string
  content_id?: string
  stage: string
  provider: string
  model: string
  status: string
  prompt: string
  request: Record<string, any>
  prompt_template?: Record<string, any> | null
  raw_response: string
  normalized: Record<string, any>
  validation_error: string
  created_at?: string
}

export type TemplateOption = { label: string; value: string }

export type ImagePromptContext = {
  contentId?: string
  sourceType?: string
  sourceIndex?: number | string
  sourceTitle?: string
  chapterNumber?: number
  referenceAssetIds?: string[]
  characterIds?: string[]
  portraitNodeIds?: string[]
  portraitVersionIds?: string[]
}

export type VideoGenerationContext = ImagePromptContext & {
  durationSeconds?: number
  generateAudio?: boolean
  musicHint?: string
}

export type InlineGeneratedImage = {
  assetId?: string
  taskId?: string
  url?: string
  localPath?: string
  referenceImages?: ReferenceImageItem[]
  referenceImagesSent?: number
  referenceImagesSupported?: boolean
  prompt: string
  provider?: string
  model?: string
  createdAt: string
}

export type PendingInlineImageTask = {
  taskId: string
  projectId: string
  key: string
  context: ImagePromptContext
  prompt: string
  size: string
  provider: string
  model: string
  referenceLineage: {
    referenceAssetIds: string[]
    characterIds: string[]
    portraitNodeIds: string[]
    portraitVersionIds: string[]
  }
  referenceImageCollection: ReferenceImageItem[]
  referenceImagesSent: number
  referenceImagesSupported: boolean
}

export type PipelineStageValue =
  | 'outline'
  | 'sync_characters'
  | 'chapter_plan'
  | 'chapter_outline'
  | 'novel_body'
  | 'script'
  | 'storyboard'
  | 'match_references'
  | 'comic_pages'

export type PipelineResultItem = {
  stage?: string
  chapter_number?: number
  status?: string
  content_type?: string
  title?: string
  reason?: string
  error?: string
  count?: number
  word_count?: number
}

export type PipelineResult = {
  stages?: string[]
  chapters?: number[]
  results?: PipelineResultItem[]
  summary?: {
    generated?: number
    skipped?: number
    failed?: number
    total?: number
  }
  generated?: number
  skipped?: number
  failed?: number
  total?: number
}

export type PipelineRunStatus = 'idle' | 'running' | 'success' | 'partial' | 'failed'

export type WorkspaceResource = 'contents' | 'writerRoom' | 'assets' | 'logs' | 'graph'

export type ImageBackendOption = {
  provider: string
  provider_label: string
  name: string
  model: string
  available_models?: string[]
  supported_sizes?: string[]
  capabilities?: string[]
  support_reference_image?: boolean
  reference_image_field?: string
}

export type ProductionStageItem = {
  key: string
  tab: string
  label: string
  hint: string
  complete: number
  total: number
}

export type EditableChapterPlanItem = ChapterPlanItem & { is_locked?: boolean }

export type ProseDiffRow = {
  kind: 'added' | 'removed' | 'changed'
  approved?: string
  candidate?: string
}

