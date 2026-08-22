import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Collapse,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Progress,
  Segmented,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  DeploymentUnitOutlined,
  DownOutlined,
  DownloadOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  UserOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  agentChat,
  createCreativeProject,
  createCreativeProjectFromNovel,
  deleteCreativeProject,
  extractCreativeProjectContinuity,
  getCreativeProjectContinuityContextSummary,
  getCreativeProjectNarrativeContextPreview,
  getCreativeProjectNarrativeGraph,
  getCreativeProjectNarrativeHealth,
  getCreativeProjectWritingPreflight,
  listCreativeProjectNarrativeRuns,
  controlCreativeProjectNarrativeRun,
  configureCreativeProjectNarrativeAutopilot,
  generateCharacterPortrait,
  generateCreativeProjectChapterPlan,
  generateCreativeProjectChapterOutline,
  generateCreativeProjectNovelBody,
  generateCreativeProjectOutline,
  generateCreativeProjectScript,
  generateCreativeProjectStoryboard,
  generateImage as generateImageApi,
  getAsset,
  getCharacter,
  getCreativeProjectCanvas,
  getImageTask,
  getImageBackends,
  getPlatformTemplates,
  listAssets,
  linkCreativeProjectAsset,
  listConnectors,
  listCreativeProjectContents,
  listCreativeProjectContinuityCandidates,
  listCreativeProjectForeshadowing,
  listCreativeProjectAssets,
  listCreativeProjectGenerationLogs,
  listCreativeProjects,
  getOrCreatePrevisScene,
  listTasks,
  matchCreativeProjectReferenceAssets,
  promoteCreativeProjectWriterRoomContent,
  refineCreativeProjectNovelBody,
  regenerateCreativeProjectChapterOutlineScenes,
  runCreativeProjectPipeline,
  runCreativeProjectWriterRoomStep,
  rewriteCreativeProjectParagraph,
  resolveCreativeProjectContinuityCandidate,
  decideCreativeProjectForeshadowing,
  splitCreativeProjectComicPages,
  syncCreativeProjectBible,
  syncCreativeProjectCharacters,
  saveCreativeProjectCanvas,
  saveCreativeProjectContentAsAsset,
  updateCreativeProject,
  updateCreativeProjectContent,
  type PlatformTemplate,
  type CreativeProjectContinuityCandidate,
} from '../../api'
import type {
  ChapterPlanItem,
  ChapterPlan,
  CreativeProject,
  CreativeProjectGenerateResponse,
  CreativeProjectListResponse,
  CreativeProjectResponse,
  Provider,
  StoryOutline,
  StoryOutlineCharacter,
  WritingPreflight,
  WritingMethodCandidate,
} from '../../types/api'
import { useTheme, type ThemeColors } from '../../constants/theme'
import { enqueueCanvasImport } from '../../components/canvas/bridge'
import type { CanvasNode, CanvasNodeType } from '../../components/canvas/types'
import { useTaskPolling } from '../../hooks/useTaskPolling'
import FanqiePublishPanel from './FanqiePublishPanel'
import ProjectStatePanel from './ProjectStatePanel'
import StoryWorkspaceOverview from './StoryWorkspaceOverview'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

const STORY_WORKSPACE_CONTENT_TYPES = [
  'chapter_outline',
  'novel_body',
  'comic_pages',
  'script',
  'storyboard',
  'project_bible',
  'world_asset',
]

type LoadingAction =
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
  | 'delete_project'
  | 'portrait_generate'
  | 'pipeline'
  | 'writer_room'
  | 'agent_advance'
  | null

type ChapterAction =
  | 'chapter_outline'
  | 'chapter_outline_scenes'
  | 'novel_body'
  | 'novel_body_refine'
  | 'comic_pages'
  | 'script'
  | 'storyboard'
  | null

interface ProjectContent {
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

interface ProjectContentSummary {
  id: string
  content_type: string
  chapter_number?: number
  episode_number?: number
  version: number
  is_locked?: boolean
  created_at?: string
  updated_at?: string
}

interface WriterRoomReviewIssue {
  category?: string
  severity?: string
  location?: string
  problem?: string
  suggestion?: string
  rewrite_instruction?: string
}

interface WriterRoomQualitySummary {
  overallScore: number
  aiSmellScore: number
  tags: string[]
  checks: string[]
}

interface ProjectAssetLink {
  id: string
  project_id: string
  asset_id: string
  content_id?: string
  role: string
  relation: string
  metadata: Record<string, any>
  created_at?: string
}

type AssetSummary = {
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

type CharacterReferenceSummary = {
  id: string
  name?: string
  portrait_url?: string
  portrait_node_id?: string
  reference_asset_ids?: string[]
  identity?: Record<string, any>
}

type ReferenceImageItem = {
  url: string
  source: 'project_asset' | 'character_portrait' | 'character_reference'
  label?: string
  asset_id?: string
  character_id?: string
  character_name?: string
  role?: string
}

type ProjectGraphNodeType =
  | 'outline'
  | 'chapter'
  | 'character'
  | 'content'
  | 'scene'
  | 'prompt'
  | 'asset'

type ProjectGraphNode = {
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

type ProjectGraphEdge = {
  id: string
  from: string
  to: string
  type: 'contains' | 'uses' | 'references' | 'derived_from'
  label?: string
}

type ProjectGraphState = {
  nodes?: ProjectGraphNode[]
  edges?: ProjectGraphEdge[]
  viewport?: { x?: number; y?: number; zoom?: number }
  updated_at?: string
}

type NarrativeContextPreview = {
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

type NarrativeForeshadowing = {
  id: string
  statement: string
  kind: string
  status: string
  timing: string
  planted_chapter: number
  expected_window?: { start?: number; end?: number }
  resolution_note?: string
}

type NarrativeGraphData = {
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

type NarrativeHealth = {
  status: 'healthy' | 'attention' | 'blocked' | string
  summary: Record<string, number>
  issues: Array<{
    code: string
    severity: 'info' | 'warning' | 'error' | string
    message: string
    details?: Record<string, unknown>
  }>
}

type NarrativeRun = {
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

function canvasTypeForGraphNode(node: ProjectGraphNode): CanvasNodeType {
  if (node.type === 'prompt') return 'prompt'
  if (node.type === 'asset' || node.type === 'character') return 'asset'
  if (node.type === 'content' || node.type === 'scene' || node.type === 'chapter' || node.type === 'outline') return 'content'
  return 'text'
}

function graphNodeToCanvasNode(node: ProjectGraphNode, project?: CreativeProject | null): CanvasNode {
  const source = node.source || {}
  const data = node.data || {}
  const type = canvasTypeForGraphNode(node)
  const prompt = source.prompt || data.image_prompt || data.prompt || ''
  const content = data.summary || data.content || data.text || node.subtitle || node.label
  const assetId = source.assetId || data.asset_id || data.assetId || data.portrait_node_id || ''
  const metadata: Record<string, unknown> = {
    projectId: project?.id || data.project_id || '',
    projectTitle: project?.title || '',
    contentId: source.contentId || '',
    sourceType: source.sourceType || node.type,
    sourceIndex: source.sourceIndex,
    chapterNumber: source.chapterNumber,
    graphNodeId: node.id,
    graphNodeType: node.type,
    graphNodeLabel: node.label,
    rawSource: source,
    rawData: data,
  }

  if (type === 'prompt') metadata.prompt = prompt || content
  else if (type === 'asset') metadata.assetId = assetId
  else metadata.content = prompt || content

  if (Array.isArray(data.reference_asset_ids)) metadata.referenceAssetIds = data.reference_asset_ids
  if (Array.isArray(data.character_ids)) metadata.characterIds = data.character_ids
  if (Array.isArray(data.portrait_node_ids)) metadata.portraitNodeIds = data.portrait_node_ids

  return {
    id: `node-graph-${node.id}-${Date.now()}`,
    type,
    title: node.label,
    position: { x: 180, y: 160 },
    width: type === 'prompt' ? 292 : type === 'asset' ? 248 : 276,
    height: type === 'prompt' ? 152 : 140,
    metadata,
  }
}

type StoryboardPanelReferencePlan = {
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

type StoryboardReferenceSummary = {
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

interface ProjectGenerationLog {
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

const projectTypeOptions = [
  { label: '短剧', value: 'short_drama' },
  { label: '小说', value: 'novel' },
  { label: '漫画', value: 'manga' },
  { label: '混合项目', value: 'mixed' },
]

const stageLabels: Record<string, string> = {
  outline: '大纲',
  chapter_plan: '章节',
  chapter_outline: '细纲',
  novel_body: '正文',
  comic_pages: '漫画页',
  script: '脚本',
  storyboard: '分镜',
  assets: '素材',
  scene_simulation_candidate: '多智能体候选',
}

// Kept outside StoryPage so React Strict Mode's development-only remount does
// not probe the same stale Asset Hub link twice during one page visit.
const unavailableProjectAssetIds = new Map<string, Set<string>>()
const projectAssetDetailRequests = new Map<string, Promise<AssetSummary | null>>()

function resolveProjectAssetDetail(assetId: string): Promise<AssetSummary | null> {
  const pendingOrResolved = projectAssetDetailRequests.get(assetId)
  if (pendingOrResolved) return pendingOrResolved

  const request = getAsset(assetId)
    .then((response) => response?.data || null)
    .catch(() => null)
  projectAssetDetailRequests.set(assetId, request)
  return request
}

const statusLabels: Record<string, string> = {
  draft: '草稿',
  outlining: '大纲中',
  planning: '规划中',
  scripting: '脚本中',
  storyboarding: '分镜中',
  ready: '可整理',
  archived: '归档',
  failed: '失败',
}

type TemplateOption = { label: string; value: string }

type ImagePromptContext = {
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

type VideoGenerationContext = ImagePromptContext & {
  durationSeconds?: number
  generateAudio?: boolean
  musicHint?: string
}

type InlineGeneratedImage = {
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

type PendingInlineImageTask = {
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

type PipelineStageValue =
  | 'outline'
  | 'sync_characters'
  | 'chapter_plan'
  | 'chapter_outline'
  | 'novel_body'
  | 'script'
  | 'storyboard'
  | 'match_references'
  | 'comic_pages'

type PipelineResultItem = {
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

type PipelineResult = {
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

type PipelineRunStatus = 'idle' | 'running' | 'success' | 'partial' | 'failed'

type WorkspaceResource = 'contents' | 'writerRoom' | 'assets' | 'logs' | 'graph'

const pipelineStageOptions: { label: string; value: PipelineStageValue }[] = [
  { label: '大纲', value: 'outline' },
  { label: '同步角色', value: 'sync_characters' },
  { label: '章节规划', value: 'chapter_plan' },
  { label: '细纲', value: 'chapter_outline' },
  { label: '正文', value: 'novel_body' },
  { label: '脚本', value: 'script' },
  { label: '分镜', value: 'storyboard' },
  { label: '参考卡匹配', value: 'match_references' },
  { label: '漫画拆页', value: 'comic_pages' },
]

const pipelineStageLabels = Object.fromEntries(pipelineStageOptions.map((item) => [item.value, item.label])) as Record<
  PipelineStageValue,
  string
>

const writerRoomStepOptions = [
  { label: '导演场景节拍', value: 'scene_beats' },
  { label: '角色演绎', value: 'character_rehearsal' },
  { label: '正文初稿', value: 'prose_draft' },
  { label: '人味润色', value: 'prose_humanized' },
  { label: '主编审稿', value: 'prose_review' },
  { label: '定向重写', value: 'prose_rewrite' },
]

const writerRoomStepLabelMap = Object.fromEntries(writerRoomStepOptions.map((item) => [item.value, item.label]))

const writerRoomStepDescriptions: Record<string, string> = {
  scene_beats: '拆解本章场景目标、节奏、转折和连续性。',
  character_rehearsal: '让关键角色先演一遍，暴露欲望、恐惧和可用冲突。',
  prose_draft: '把细纲和演绎结果写成可读正文初稿。',
  prose_humanized: '压低解释感，补动作、物件互动、停顿和潜台词。',
  prose_review: '主编审稿，给出 AI 味、逻辑、节奏和可执行改法。',
  prose_rewrite: '按审稿意见或选段要求生成新的候选正文。',
}

const writerRoomAgentNames: Record<string, string> = {
  scene_beats: '导演',
  character_rehearsal: '演员组',
  prose_draft: '写手',
  prose_humanized: '润色师',
  prose_review: '主编',
  prose_rewrite: '改稿师',
}

const writerRoomStepInputs: Record<string, string[]> = {
  scene_beats: ['项目大纲', '章节规划', '本章细纲', '前文上下文'],
  character_rehearsal: ['项目大纲', '本章细纲', '场景节拍'],
  prose_draft: ['本章细纲', '场景节拍', '角色演绎'],
  prose_humanized: ['正文初稿或候选正文', '用户额外要求'],
  prose_review: ['正文候选', '大纲与连续性上下文'],
  prose_rewrite: ['正文候选', '主编审稿意见', '用户选段或要求'],
}

const writerRoomStepOutputs: Record<string, string[]> = {
  scene_beats: ['场景目标', '动作节拍', '转折', '尾钩'],
  character_rehearsal: ['角色目标', '隐瞒信息', '潜台词', '可写冲突'],
  prose_draft: ['完整正文初稿'],
  prose_humanized: ['更自然的正文候选'],
  prose_review: ['质量标签', 'AI味检查', '可执行重写指令'],
  prose_rewrite: ['可提升为正式正文的候选版本'],
}

const writerRoomStepNextHints: Record<string, string> = {
  scene_beats: '生成后进入“角色演绎”，让角色按自己的欲望和隐瞒信息先演一遍。',
  character_rehearsal: '生成后进入“正文初稿”，把细纲、场景节拍和角色反应合成完整正文。',
  prose_draft: '初稿不要急着提升，优先进入“人味润色”压低解释感。',
  prose_humanized: '润色后进入“主编审稿”，检查逻辑、节奏、AI腔和角色声音。',
  prose_review: '审稿后可以按单条意见重写，也可以应用全部意见生成定向重写版。',
  prose_rewrite: '确认效果后再提升为正式正文，旧正文会作为历史版本保留。',
}

function parseChapterRange(value: string): number[] {
  const chapters = new Set<number>()
  String(value || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      if (part.includes('-')) {
        const [left, right] = part.split('-').map((item) => Number(item.trim()))
        if (!Number.isFinite(left) || !Number.isFinite(right)) return
        const start = Math.max(1, Math.min(left, right))
        const end = Math.max(left, right)
        for (let chapter = start; chapter <= end; chapter += 1) chapters.add(chapter)
        return
      }
      const chapter = Number(part)
      if (Number.isFinite(chapter) && chapter > 0) chapters.add(chapter)
    })
  return Array.from(chapters).sort((a, b) => a - b)
}

function linesToList(value: string): string[] {
  return String(value || '')
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function listToLines(value: unknown): string {
  return Array.isArray(value) ? value.filter(Boolean).join('\n') : ''
}

function isChapterLocked(item: ChapterPlanItem | Record<string, any>) {
  return Boolean((item as any).is_locked) || item.status === 'locked'
}

function normalizeChapterItem(item: ChapterPlanItem | Record<string, any>): ChapterPlanItem {
  const chapterNumber = Number(item.chapter_number || 1)
  const locked = isChapterLocked(item)
  return {
    ...item,
    chapter_number: Number.isFinite(chapterNumber) && chapterNumber > 0 ? chapterNumber : 1,
    title: String(item.title || ''),
    goal: String(item.goal || ''),
    conflict: String(item.conflict || ''),
    key_events: Array.isArray(item.key_events) ? item.key_events.filter(Boolean).map(String) : linesToList(String(item.key_events || '')),
    character_focus: Array.isArray(item.character_focus)
      ? item.character_focus.filter(Boolean).map(String)
      : linesToList(String(item.character_focus || '')),
    ending_hook: String(item.ending_hook || ''),
    status: locked ? 'locked' : String(item.status || 'draft'),
  }
}

function normalizeChapterPlan(plan: ChapterPlan | Record<string, any>): ChapterPlan {
  const chapters = Array.isArray(plan.chapters) ? plan.chapters.map(normalizeChapterItem) : []
  return {
    ...plan,
    chapter_count: chapters.length || Number(plan.chapter_count || 0),
    chapters,
  }
}

function buildCreativeProjectGraph(params: {
  project?: CreativeProject | null
  contents: ProjectContent[]
  assets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  saved?: ProjectGraphState | null
}): ProjectGraphState {
  const { project, contents, assets, assetDetails, saved } = params
  const savedNodes = new Map((saved?.nodes || []).map((node) => [node.id, node]))
  const nodes: ProjectGraphNode[] = []
  const edges: ProjectGraphEdge[] = []
  const addNode = (node: ProjectGraphNode) => {
    const savedNode = savedNodes.get(node.id)
    nodes.push({
      ...node,
      x: Number(savedNode?.x ?? node.x),
      y: Number(savedNode?.y ?? node.y),
      width: savedNode?.width || node.width || 210,
      height: savedNode?.height || node.height || 92,
    })
  }
  const addEdge = (edge: ProjectGraphEdge) => {
    if (edge.from === edge.to) return
    if (edges.some((item) => item.id === edge.id)) return
    edges.push(edge)
  }

  if (!project) return { nodes: [], edges: [] }

  const outline = project.outline || {}
  const chapters = project.chapter_plan?.chapters || []
  const outlineId = 'outline:root'
  addNode({
    id: outlineId,
    type: 'outline',
    label: outline.title || project.title || '故事大纲',
    subtitle: outline.logline || outline.premise || '项目核心设定',
    status: project.current_stage,
    x: 40,
    y: 180,
    source: { tab: 'outline' },
  })

  ;(outline.characters || []).slice(0, 12).forEach((character: StoryOutlineCharacter, index: number) => {
    const id = `character:${character.character_id || character.name || index}`
    addNode({
      id,
      type: 'character',
      label: character.name || `角色 ${index + 1}`,
      subtitle: [character.role, character.goal || character.personality].filter(Boolean).join(' / '),
      status: character.character_id ? 'linked' : 'draft',
      x: 330,
      y: 40 + index * 118,
      source: { tab: 'outline', assetId: character.portrait_asset_id },
      data: character as Record<string, any>,
    })
    addEdge({ id: `${outlineId}->${id}`, from: outlineId, to: id, type: 'contains', label: 'character' })
  })

  chapters.forEach((chapter: ChapterPlanItem, index: number) => {
    const chapterNumber = Number(chapter.chapter_number || index + 1)
    const chapterId = `chapter:${chapterNumber}`
    addNode({
      id: chapterId,
      type: 'chapter',
      label: chapter.title || `第 ${chapterNumber} 章`,
      subtitle: chapter.goal || chapter.conflict || chapter.ending_hook,
      status: isChapterLocked(chapter) ? 'locked' : chapter.status || 'draft',
      x: 650,
      y: 40 + index * 132,
      source: { tab: 'episode-workbench', chapterNumber },
      data: chapter as Record<string, any>,
    })
    addEdge({ id: `${outlineId}->${chapterId}`, from: outlineId, to: chapterId, type: 'contains', label: 'chapter' })
  })

  const contentTypeOrder: Record<string, number> = {
    chapter_outline: 0,
    novel_body: 1,
    script: 2,
    storyboard: 3,
    comic_pages: 4,
    project_bible: -1,
    world_asset: -1,
  }
  const sortedContents = [...contents].sort((left, right) => {
    const leftChapter = Number(left.chapter_number || left.episode_number || 0)
    const rightChapter = Number(right.chapter_number || right.episode_number || 0)
    if (leftChapter !== rightChapter) return leftChapter - rightChapter
    return (contentTypeOrder[left.content_type] ?? 9) - (contentTypeOrder[right.content_type] ?? 9)
  })

  sortedContents.forEach((content, index) => {
    const chapterNumber = Number(content.chapter_number || content.episode_number || 0)
    const contentId = `content:${content.id}`
    const contentLabel = stageLabels[content.content_type] || content.content_type
    const column = content.content_type === 'project_bible' || content.content_type === 'world_asset' ? 1 : 4
    addNode({
      id: contentId,
      type: 'content',
      label: content.title || contentLabel,
      subtitle: chapterNumber ? `第 ${chapterNumber} 章 / ${contentLabel} v${content.version}` : `${contentLabel} v${content.version}`,
      status: content.is_locked ? 'locked' : 'ready',
      x: column === 1 ? 330 : 950,
      y: column === 1 ? 720 + index * 112 : 50 + index * 104,
      source: { tab: content.content_type === 'novel_body' || content.content_type === 'comic_pages' ? 'script' : 'episode-workbench', contentId: content.id, chapterNumber, contentType: content.content_type },
      data: content.data,
    })
    if (chapterNumber) {
      addEdge({ id: `chapter:${chapterNumber}->${contentId}`, from: `chapter:${chapterNumber}`, to: contentId, type: 'contains', label: contentLabel })
    } else {
      addEdge({ id: `${outlineId}->${contentId}`, from: outlineId, to: contentId, type: 'contains', label: contentLabel })
    }

    const panels = Array.isArray(content.data?.panels) ? content.data.panels : []
    panels.slice(0, 24).forEach((panel: any, panelIndex: number) => {
      const panelNumber = Number(panel.panel_number || panel.page_number || panelIndex + 1)
      const sceneId = `scene:${content.id}:${panelNumber}`
      addNode({
        id: sceneId,
        type: 'scene',
        label: panel.action || panel.scene || `镜头 ${panelNumber}`,
        subtitle: panel.shot_type || panel.dialogue || panel.camera || '',
        status: panel.image_url ? 'generated' : 'draft',
        x: 1250,
        y: 60 + (index * 3 + panelIndex) * 94,
        source: { tab: 'episode-workbench', contentId: content.id, chapterNumber, sourceIndex: panelNumber, sourceType: 'storyboard_panel' },
        data: panel,
      })
      addEdge({ id: `${contentId}->${sceneId}`, from: contentId, to: sceneId, type: 'contains', label: 'scene' })
      if (panel.image_prompt) {
        const promptId = `prompt:${content.id}:${panelNumber}`
        addNode({
          id: promptId,
          type: 'prompt',
          label: `生图提示 ${panelNumber}`,
          subtitle: String(panel.image_prompt).slice(0, 90),
          status: panel.reference_asset_ids?.length ? 'with_refs' : 'ready',
          x: 1540,
          y: 60 + (index * 3 + panelIndex) * 94,
          source: { tab: 'episode-workbench', contentId: content.id, chapterNumber, prompt: panel.image_prompt, sourceIndex: panelNumber, sourceType: 'storyboard_panel' },
          data: panel,
        })
        addEdge({ id: `${sceneId}->${promptId}`, from: sceneId, to: promptId, type: 'uses', label: 'prompt' })
        ;(panel.reference_asset_ids || []).forEach((assetId: string) => {
          addEdge({ id: `asset:${assetId}->${promptId}`, from: `asset:${assetId}`, to: promptId, type: 'references', label: 'ref' })
        })
      }
    })
  })

  assets.forEach((asset, index) => {
    const detail = assetDetails[asset.asset_id]
    const metadata = asset.metadata || {}
    const assetId = `asset:${asset.asset_id}`
    addNode({
      id: assetId,
      type: 'asset',
      label: detail?.title || metadata.title || asset.asset_id.slice(0, 10),
      subtitle: [asset.role, asset.relation, detail?.type].filter(Boolean).join(' / '),
      status: asset.relation || asset.role,
      x: asset.role === 'output' ? 1840 : 40,
      y: 40 + index * 112,
      source: { tab: 'assets', assetId: asset.asset_id, contentId: asset.content_id, sourceType: metadata.source_type, sourceIndex: metadata.source_index, prompt: metadata.prompt },
      data: { ...asset.metadata, asset_id: asset.asset_id, role: asset.role, relation: asset.relation },
    })
    if (asset.content_id) {
      addEdge({ id: `content:${asset.content_id}->${assetId}`, from: `content:${asset.content_id}`, to: assetId, type: asset.relation === 'references' ? 'references' : 'derived_from', label: asset.role })
    }
    if (metadata.source_type && metadata.source_index !== undefined && asset.content_id) {
      addEdge({
        id: `prompt:${asset.content_id}:${metadata.source_index}->${assetId}`,
        from: `prompt:${asset.content_id}:${metadata.source_index}`,
        to: assetId,
        type: 'derived_from',
        label: 'generated',
      })
    }
  })

  return { nodes, edges, viewport: saved?.viewport || { x: 0, y: 0, zoom: 1 }, updated_at: saved?.updated_at }
}

function isPipelineStageValue(value?: string): value is PipelineStageValue {
  return pipelineStageOptions.some((item) => item.value === value)
}

function getPipelineFailedRows(result: PipelineResult | null): PipelineResultItem[] {
  return (result?.results || []).filter((item) => item.status === 'failed')
}

function getPipelineSummary(result: PipelineResult | null) {
  const rows = result?.results || []
  return {
    generated: result?.summary?.generated ?? result?.generated ?? rows.filter((item) => item.status === 'generated').length,
    skipped: result?.summary?.skipped ?? result?.skipped ?? rows.filter((item) => item.status === 'skipped').length,
    failed: result?.summary?.failed ?? result?.failed ?? rows.filter((item) => item.status === 'failed').length,
    total: result?.summary?.total ?? result?.total ?? rows.length,
  }
}

function imageContextKey(context: ImagePromptContext = {}) {
  return [
    context.contentId || 'project',
    context.sourceType || 'prompt',
    context.sourceIndex ?? '0',
    context.chapterNumber ?? '0',
  ].join(':')
}

function normalizeStoryboardVideoDuration(value?: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 5
  return Math.max(3, Math.min(Math.round(parsed), 6))
}

function buildStoryboardVideoFallbackPrompt(panel: Record<string, any>) {
  const action = String(panel.action || panel.panel_goal || '人物完成当前镜头动作').trim()
  const motion = String(panel.camera_motion || panel.camera_hint || '静止').trim()
  const shotSize = String(panel.shot_size || '中景').trim()
  const angle = String(panel.camera_angle || '平视').trim()
  const location = String(panel.location || '当前场景').trim()
  const emotion = String(panel.emotion || '').trim()
  return [
    `竖屏短剧${shotSize}${angle}镜头：${action}`,
    `在${location}内以${motion}完成镜头运动`,
    emotion ? `人物情绪保持${emotion}` : '',
    '动作自然连贯，保持首帧中的角色、服装、场景和光线一致，不出现字幕或新增人物',
  ].filter(Boolean).join('；')
}

function dedupeStrings(values: Array<unknown>) {
  const seen = new Set<string>()
  return values
    .map((value) => String(value || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false
      seen.add(value)
      return true
    })
}

function assetFileUrl(path?: string): string {
  if (!path) return ''
  if (/^(https?:|data:|blob:|\/api\/)/i.test(path)) return path
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}`
}

function normalizeCharacterReference(payload: any): CharacterReferenceSummary | null {
  const source = payload?.data || payload?.character || payload
  if (!source?.id) return null
  return {
    id: String(source.id),
    name: source.name || '',
    portrait_url: source.portrait_url || '',
    portrait_node_id: source.portrait_node_id || '',
    reference_asset_ids: Array.isArray(source.reference_asset_ids) ? source.reference_asset_ids : [],
    identity: source.identity && typeof source.identity === 'object' ? source.identity : {},
  }
}

function getCharacterReferenceItems(character?: CharacterReferenceSummary): ReferenceImageItem[] {
  if (!character) return []
  const identity = character.identity || {}
  const visualProfile = (
    identity.visual_profile ||
    identity.visualProfile ||
    {}
  ) as Record<string, any>
  const identityReferenceUrl = String(visualProfile.identity_reference_url || '').trim()
  const visualReferenceUrls = [
    visualProfile.reference_image_urls,
    visualProfile.reference_images,
    visualProfile.reference_urls,
    visualProfile.main_reference_url,
  ].flatMap((value) => (Array.isArray(value) ? value : value ? [value] : []))

  const items: ReferenceImageItem[] = []
  if (identityReferenceUrl) {
    items.push({
      url: assetFileUrl(identityReferenceUrl),
      source: 'character_portrait',
      label: `${character.name || '角色'}身份基准图`,
      character_id: character.id,
      character_name: character.name,
    })
  }
  if (character.portrait_url) {
    items.push({
      url: assetFileUrl(character.portrait_url),
      source: 'character_portrait',
      label: `${character.name || '角色'}主立绘`,
      character_id: character.id,
      character_name: character.name,
    })
  }
  if (character.portrait_node_id) {
    items.push({
      url: `/api/v1/assets/${character.portrait_node_id}/thumbnail?original=true`,
      source: 'character_portrait',
      label: `${character.name || '角色'}立绘节点`,
      asset_id: character.portrait_node_id,
      character_id: character.id,
      character_name: character.name,
    })
  }
  for (const assetId of character.reference_asset_ids || []) {
    items.push({
      url: `/api/v1/assets/${assetId}/thumbnail?original=true`,
      source: 'character_reference',
      label: `${character.name || '角色'}参考素材`,
      asset_id: assetId,
      character_id: character.id,
      character_name: character.name,
    })
  }
  for (const url of visualReferenceUrls) {
    items.push({
      url: assetFileUrl(String(url)),
      source: 'character_reference',
      label: `${character.name || '角色'}视觉卡参考图`,
      character_id: character.id,
      character_name: character.name,
    })
  }

  const seen = new Set<string>()
  return items.filter((item) => {
    const url = String(item.url || '').trim()
    if (!url || seen.has(url)) return false
    seen.add(url)
    item.url = url
    return true
  })
}

function dedupeReferenceImageItems(items: ReferenceImageItem[]): ReferenceImageItem[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const url = String(item.url || '').trim()
    if (!url || seen.has(url)) return false
    seen.add(url)
    item.url = url
    return true
  })
}

function collectStoryboardCharacterIds(contents: ProjectContent[]): string[] {
  return dedupeStrings(
    contents
      .filter((content) => content.content_type === 'storyboard')
      .flatMap((content) => content.data?.panels || [])
      .flatMap((panel: any) => panel?.character_ids || []),
  )
}

function selectReferenceAssetsForPrompt(projectAssets: ProjectAssetLink[], prompt: string, maxCount = 4) {
  const references = projectAssets.filter((asset) =>
    ['character', 'background', 'style', 'world', 'reference'].includes(asset.role),
  )
  if (!references.length) return []

  const promptText = String(prompt || '').toLowerCase()
  const scored = references.map((asset, index) => {
    const meta = asset.metadata || {}
    const marker = [
      meta.character_name,
      meta.name,
      meta.source_title,
      meta.label,
      asset.role,
      asset.asset_id,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    let score = 0
    if (asset.role === 'style') score += 8
    if (asset.role === 'background') score += 6
    if (asset.role === 'reference') score += 4
    if (asset.role === 'character') score += 3
    if (marker && promptText.includes(marker)) score += 20
    if (meta.character_name && promptText.includes(String(meta.character_name).toLowerCase())) score += 30
    return { asset, score, index }
  })

  return scored
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, maxCount)
    .map((item) => item.asset)
}

function dedupeProjectAssetLinks(assets: ProjectAssetLink[]) {
  const seen = new Set<string>()
  return assets.filter((asset) => {
    if (!asset.asset_id || seen.has(asset.asset_id)) return false
    seen.add(asset.asset_id)
    return true
  })
}

function projectAssetToReferenceItem(assetId: string, link?: ProjectAssetLink): ReferenceImageItem {
  return {
    url: `/api/v1/assets/${assetId}/thumbnail?original=true`,
    source: 'project_asset',
    label:
      link?.metadata?.label ||
      link?.metadata?.character_name ||
      link?.metadata?.source_title ||
      link?.role ||
      assetId,
    asset_id: assetId,
    role: link?.role,
    character_id: link?.metadata?.character_id,
    character_name: link?.metadata?.character_name,
  }
}

function portraitNodeToReferenceItem(assetId: string, character?: CharacterReferenceSummary): ReferenceImageItem {
  return {
    url: `/api/v1/assets/${assetId}/thumbnail?original=true`,
    source: 'character_portrait',
    label: `${character?.name || '角色'}立绘节点`,
    asset_id: assetId,
    character_id: character?.id,
    character_name: character?.name,
  }
}

function buildStoryboardPanelReferencePlan({
  panel,
  projectAssets,
  characterDetails,
  supportsReferenceImages,
  maxImages = 6,
}: {
  panel: any
  projectAssets: ProjectAssetLink[]
  characterDetails: Record<string, CharacterReferenceSummary>
  supportsReferenceImages: boolean
  maxImages?: number
}): StoryboardPanelReferencePlan {
  const panelReferenceAssetIds = dedupeStrings(panel?.reference_asset_ids || [])
  const panelCharacterIds = dedupeStrings(panel?.character_ids || [])
  const panelPortraitNodeIds = dedupeStrings(panel?.portrait_node_ids || [])
  const panelPortraitVersionIds = dedupeStrings(panel?.portrait_version_ids || [])
  const explicitAssetIds = new Set([...panelReferenceAssetIds, ...panelPortraitNodeIds])
  const explicitAssets = explicitAssetIds.size
    ? projectAssets.filter((asset) => explicitAssetIds.has(asset.asset_id))
    : []
  const promptAssets = selectReferenceAssetsForPrompt(
    projectAssets,
    [panel?.image_prompt, panel?.action, panel?.location].filter(Boolean).join('\n'),
    4,
  )
  const referenceAssets = dedupeProjectAssetLinks([...explicitAssets, ...promptAssets]).slice(0, 4)
  const linksByAssetId = new Map(projectAssets.map((asset) => [asset.asset_id, asset]))
  const referenceAssetIds = dedupeStrings([
    ...panelReferenceAssetIds,
    ...referenceAssets.map((asset) => asset.asset_id),
  ])
  const characterIds = dedupeStrings([
    ...panelCharacterIds,
    ...referenceAssets.map((asset) => asset.metadata?.character_id),
  ])
  const portraitNodeIds = dedupeStrings([
    ...panelPortraitNodeIds,
    ...referenceAssets
      .filter((asset) => asset.role === 'character')
      .map((asset) => asset.asset_id),
    ...referenceAssets.map((asset) => asset.metadata?.portrait_node_id),
  ])
  const portraitVersionIds = dedupeStrings([
    ...panelPortraitVersionIds,
    ...referenceAssets.map((asset) => asset.metadata?.portrait_version_id || asset.metadata?.main_portrait_version_id),
  ])
  const projectReferenceItems = referenceAssetIds.map((assetId) =>
    projectAssetToReferenceItem(assetId, linksByAssetId.get(assetId)),
  )
  const characterReferenceItems = characterIds.flatMap((characterId) =>
    getCharacterReferenceItems(characterDetails[characterId]),
  )
  const portraitNodeReferenceItems = portraitNodeIds.map((assetId) => {
    const character = characterIds
      .map((characterId) => characterDetails[characterId])
      .find((item) => item?.portrait_node_id === assetId)
    return portraitNodeToReferenceItem(assetId, character)
  })
  const imageCollection = dedupeReferenceImageItems([
    ...projectReferenceItems,
    ...characterReferenceItems,
    ...portraitNodeReferenceItems,
  ]).slice(0, maxImages)
  const unresolvedCharacterIds = characterIds.filter((id) => !characterDetails[id])
  const hasEffectivePlan = Boolean(
    referenceAssetIds.length || characterIds.length || portraitNodeIds.length || portraitVersionIds.length,
  )

  return {
    referenceAssetIds,
    characterIds,
    portraitNodeIds,
    portraitVersionIds,
    projectReferenceItems,
    characterReferenceItems,
    portraitNodeReferenceItems,
    imageCollection,
    unresolvedCharacterIds,
    sentCount: supportsReferenceImages ? imageCollection.length : 0,
    hasEffectivePlan,
  }
}

function buildStoryboardReferenceSummary(
  plans: StoryboardPanelReferencePlan[],
  generatedPanels: number,
  supportsReferenceImages: boolean,
): StoryboardReferenceSummary {
  const uniqueReferenceUrls = dedupeStrings(plans.flatMap((plan) => plan.imageCollection.map((item) => item.url)))
  const uniqueCharacterIds = dedupeStrings(plans.flatMap((plan) => plan.characterIds))
  const unresolvedCharacterIds = dedupeStrings(plans.flatMap((plan) => plan.unresolvedCharacterIds))
  const effectivePlanPanels = plans.filter((plan) => plan.hasEffectivePlan).length
  const usableReferencePanels = plans.filter((plan) => plan.imageCollection.length).length
  const totalReferenceImages = plans.reduce((total, plan) => total + plan.imageCollection.length, 0)

  return {
    promptPanels: plans.length,
    effectivePlanPanels,
    usableReferencePanels,
    generatedPanels,
    totalReferenceImages,
    uniqueReferenceImages: uniqueReferenceUrls.length,
    sentReferenceImages: supportsReferenceImages ? totalReferenceImages : 0,
    uniqueCharacterIds,
    unresolvedCharacterIds,
    missingEffectivePlanPanels: plans.length - effectivePlanPanels,
    noUsableReferencePanels: plans.length - usableReferencePanels,
  }
}

type ImageBackendOption = {
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

function getNovelDisplayTitle(asset?: AssetSummary | null): string {
  if (!asset) return ''
  const meta = asset.metadata || {}
  return String(asset.title || meta.novel_title || meta.book_title || '未命名小说')
}

function getNovelChapterOptions(asset?: AssetSummary | null) {
  const meta = asset?.metadata || {}
  const chapters = Array.isArray(meta.chapters) ? meta.chapters : []
  const downloaded = Array.isArray(meta.downloaded_chapter_indices)
    ? new Set(meta.downloaded_chapter_indices.map((item: unknown) => Number(item)))
    : null
  return chapters
    .map((chapter: any, index: number) => {
      const chapterIndex = Number(chapter?.index ?? index + 1)
      return {
        label: `第 ${chapterIndex} 章 ${chapter?.title || ''}`.trim(),
        value: chapterIndex,
        downloaded: downloaded ? downloaded.has(chapterIndex) : true,
      }
    })
    .filter((item) => Number.isFinite(item.value) && item.value > 0 && item.downloaded)
}

export default function StoryPage() {
  const { theme } = useTheme()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [projects, setProjects] = useState<CreativeProject[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [selectedProject, setSelectedProject] = useState<CreativeProject | null>(null)
  const [contents, setContents] = useState<ProjectContent[]>([])
  const [writerRoomContents, setWriterRoomContents] = useState<ProjectContent[]>([])
  const [writerRoomSummary, setWriterRoomSummary] = useState<ProjectContentSummary[]>([])
  const writerRoomRequestRef = useRef(0)
  const [projectAssets, setProjectAssets] = useState<ProjectAssetLink[]>([])
  const [assetDetails, setAssetDetails] = useState<Record<string, AssetSummary>>({})
  const [unavailableAssetIds, setUnavailableAssetIds] = useState<Record<string, true>>({})
  const [projectGraph, setProjectGraph] = useState<ProjectGraphState | null>(null)
  const [characterDetails, setCharacterDetails] = useState<Record<string, CharacterReferenceSummary>>({})
  const [generationLogs, setGenerationLogs] = useState<ProjectGenerationLog[]>([])
  const [continuityCandidates, setContinuityCandidates] = useState<CreativeProjectContinuityCandidate[]>([])
  const [continuitySummary, setContinuitySummary] = useState<Record<string, any> | null>(null)
  const [narrativeContext, setNarrativeContext] = useState<NarrativeContextPreview | null>(null)
  const [foreshadowingLedger, setForeshadowingLedger] = useState<NarrativeForeshadowing[]>([])
  const [allForeshadowingLedger, setAllForeshadowingLedger] = useState<NarrativeForeshadowing[]>([])
  const [narrativeGraphData, setNarrativeGraphData] = useState<NarrativeGraphData | null>(null)
  const [narrativeHealth, setNarrativeHealth] = useState<NarrativeHealth | null>(null)
  const [narrativeRuns, setNarrativeRuns] = useState<NarrativeRun[]>([])
  const [narrativeLoading, setNarrativeLoading] = useState(false)
  const [llmConnectors, setLlmConnectors] = useState<Provider[]>([])
  const [imageBackends, setImageBackends] = useState<ImageBackendOption[]>([])
  const [novelAssets, setNovelAssets] = useState<AssetSummary[]>([])
  const [loadingNovelAssets, setLoadingNovelAssets] = useState(false)
  const [promptTemplates, setPromptTemplates] = useState<PlatformTemplate[]>([])
  const [selectedPromptTemplates, setSelectedPromptTemplates] = useState<Record<string, string>>({})
  const [selectedLlm, setSelectedLlm] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [rehearsalMode, setRehearsalMode] = useState<'fast' | 'team'>('team')
  const [createOpen, setCreateOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [fanqieOpen, setFanqieOpen] = useState(false)
  const [renameForm] = Form.useForm()
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null)
  const [workspaceErrors, setWorkspaceErrors] = useState<Record<string, string>>({})
  const [projectListError, setProjectListError] = useState('')
  const [savingContentId, setSavingContentId] = useState<string | null>(null)
  const [loadingChapterAction, setLoadingChapterAction] = useState<{ action: ChapterAction; chapterNumber: number | null }>({
    action: null,
    chapterNumber: null,
  })
  const [chapterCount, setChapterCount] = useState(12)
  const [comicPageCount, setComicPageCount] = useState(10)
  const [comicStyle, setComicStyle] = useState('彩色影视漫画，竖屏短剧分镜感，半写实人物，高对比光影，画风统一')
  const [pipelineChapters, setPipelineChapters] = useState('1')
  const [pipelineStages, setPipelineStages] = useState<PipelineStageValue[]>([
    'chapter_outline',
    'novel_body',
    'script',
    'storyboard',
    'match_references',
  ])
  const [pipelineSkipExisting, setPipelineSkipExisting] = useState(true)
  const [pipelineContinueOnError, setPipelineContinueOnError] = useState(true)
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null)
  const [pipelineRunStatus, setPipelineRunStatus] = useState<PipelineRunStatus>('idle')
  const [pipelineOpen, setPipelineOpen] = useState(false)
  const [workspaceLoading, setWorkspaceLoading] = useState<Record<WorkspaceResource, boolean>>({
    contents: false,
    writerRoom: false,
    assets: false,
    logs: false,
    graph: false,
  })
  const [activeChapterNumber, setActiveChapterNumber] = useState(1)
  const activeChapterRestoreRef = useRef<{
    projectId: string | null
    restoredPersistedChapter: number | null
    pendingLocalChapter: number | null
  }>({ projectId: null, restoredPersistedChapter: null, pendingLocalChapter: null })
  const [projectLibraryWidth, setProjectLibraryWidth] = useState(260)
  const [projectLibraryCollapsed, setProjectLibraryCollapsed] = useState(
    () => window.localStorage.getItem('ylcraft:story-project-library-collapsed') === 'true',
  )
  const storyPageRef = useRef<HTMLDivElement>(null)
  const [cockpitCompact, setCockpitCompact] = useState(true)
  const [workspaceNarrow, setWorkspaceNarrow] = useState(false)
  const [workbenchWidths, setWorkbenchWidths] = useState({ outline: 360, prose: 520 })
  const [savingImageModel, setSavingImageModel] = useState(false)
  const [inlineImageLoadingKey, setInlineImageLoadingKey] = useState<string | null>(null)
  const [pendingInlineImageTask, setPendingInlineImageTask] = useState<PendingInlineImageTask | null>(null)
  const [batchStoryboardImageChapter, setBatchStoryboardImageChapter] = useState<number | null>(null)
  const [inlineImages, setInlineImages] = useState<Record<string, InlineGeneratedImage>>({})
  const [portraitGeneratingCharacter, setPortraitGeneratingCharacter] = useState<string | null>(null)
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState('outline')
  const [workspaceMode, setWorkspaceMode] = useState<'overview' | 'chapter'>(() =>
    window.localStorage.getItem('ylcraft:story-workspace-mode') === 'chapter' ? 'chapter' : 'overview',
  )
  const workspaceModeProjectRef = useRef<string | null>(null)
  const [overviewDetailOpen, setOverviewDetailOpen] = useState(true)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [runtimeSettingsOpen, setRuntimeSettingsOpen] = useState(false)
  const [form] = Form.useForm()
  const createSourceType = Form.useWatch('source_type', form) || 'original_idea'
  const createNovelAssetId = Form.useWatch('novel_asset_id', form)

  const outline = selectedProject?.outline || {}
  const chapterPlan = selectedProject?.chapter_plan || {}
  const chapters = chapterPlan.chapters || []
  const hasOutline = Object.keys(outline).length > 0
  const hasChapterPlan = chapters.length > 0
  const chapterOutlines = contents.filter((item) => item.content_type === 'chapter_outline')
  const novelBodies = contents.filter((item) => item.content_type === 'novel_body')
  const comicPages = contents.filter((item) => item.content_type === 'comic_pages')
  const scripts = contents.filter((item) => item.content_type === 'script')
  const storyboards = contents.filter((item) => item.content_type === 'storyboard')
  const projectBibleContents = contents.filter((item) => item.content_type === 'project_bible')
  const worldAssetContents = contents.filter((item) => item.content_type === 'world_asset')

  const activeProjectMeta = selectedProject?.metadata || {}
  const activeProjectSettings = selectedProject?.settings || {}
  const idea = String(activeProjectMeta.idea || '')
  const defaultImageModel = activeProjectMeta.default_image_model || {}
  const selectedImageBackend = imageBackends.find((item) => item.name === defaultImageModel.name)
  const defaultImageSupportsReferenceImages = Boolean(
    selectedImageBackend?.support_reference_image ||
      selectedImageBackend?.capabilities?.includes('image_to_image') ||
      defaultImageModel.support_reference_image,
  )
  const selectedNovelAsset = novelAssets.find((asset) => asset.id === createNovelAssetId)
  const selectedNovelChapterOptions = getNovelChapterOptions(selectedNovelAsset)
  const selectedCreativeSkillIds = useMemo(
    () =>
      Array.isArray(activeProjectSettings.creative_skill_ids)
        ? activeProjectSettings.creative_skill_ids.filter((item: unknown): item is string => typeof item === 'string')
        : [],
    [activeProjectSettings],
  )

  const projectGraphView = useMemo(
    () =>
      buildCreativeProjectGraph({
        project: selectedProject,
        contents,
        assets: projectAssets,
        assetDetails,
        saved: projectGraph,
      }),
    [selectedProject, contents, projectAssets, assetDetails, projectGraph],
  )

  useEffect(() => {
    window.localStorage.setItem('ylcraft:story-project-library-collapsed', String(projectLibraryCollapsed))
  }, [projectLibraryCollapsed])

  useEffect(() => {
    if (!selectedProject?.id) return
    if (workspaceModeProjectRef.current !== selectedProject.id) {
      workspaceModeProjectRef.current = selectedProject.id
      const persistedMode = window.localStorage.getItem(`ylcraft:story-workspace-mode:${selectedProject.id}`)
      setWorkspaceMode(persistedMode === 'chapter' ? 'chapter' : 'overview')
      setOverviewDetailOpen(false)
      return
    }
    window.localStorage.setItem(`ylcraft:story-workspace-mode:${selectedProject.id}`, workspaceMode)
  }, [selectedProject?.id, workspaceMode])

  useEffect(() => {
    const requestedProjectId = searchParams.get('project_id')
    if (requestedProjectId && projects.some((item) => item.id === requestedProjectId)) {
      setSelectedId(requestedProjectId)
    }
  }, [projects, searchParams])

  useEffect(() => {
    const element = storyPageRef.current
    if (!element) return

    // The global navigation consumes part of the viewport. Measure the actual
    // workbench so its three-column layout never crushes the prose workspace.
    const update = (width: number) => {
      setCockpitCompact(width < 1320)
      setWorkspaceNarrow(width < 760)
    }
    update(element.getBoundingClientRect().width)
    const observer = new ResizeObserver((entries) => {
      update(entries[0]?.contentRect.width || element.getBoundingClientRect().width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    // Target count belongs to the selected project.  Do not let a previous
    // project's target leak into this workspace, but preserve an in-progress
    // user edit until the persisted plan itself changes.
    const persistedCount = chapters.length || Number(chapterPlan.chapter_count || 0)
    setChapterCount(persistedCount > 0 ? persistedCount : 12)
  }, [selectedProject?.id, chapters.length])

  const finalizeInlineImageResult = useCallback(async (data: any, task: PendingInlineImageTask) => {
    if (!data?.success) throw new Error(data?.error || '图片生成失败')

    const urls = data.urls?.length ? data.urls : data.url ? [data.url] : []
    const localPaths = data.all_local_paths?.length
      ? data.all_local_paths
      : data.local_path
        ? [data.local_path]
        : []
    const assetIds = data.all_asset_hub_node_ids?.length
      ? data.all_asset_hub_node_ids
      : data.asset_hub_node_id
        ? [data.asset_hub_node_id]
        : data.all_asset_ids?.length
          ? data.all_asset_ids
          : data.asset_id
            ? [data.asset_id]
            : []
    const assetId = assetIds[0]
    const referenceImages = task.referenceImageCollection.map((item) => item.url)

    if (assetId) {
      try {
        await linkCreativeProjectAsset(task.projectId, {
          asset_id: assetId,
          content_id: task.context.contentId || undefined,
          role: 'output',
          relation: 'derived_from',
          metadata: {
            source_type: task.context.sourceType,
            source_index: task.context.sourceIndex,
            source_title: task.context.sourceTitle,
            chapter_number: task.context.chapterNumber,
            prompt: task.prompt,
            provider: task.provider,
            model: task.model,
            size: task.size,
            reference_asset_ids: task.referenceLineage.referenceAssetIds,
            character_ids: task.referenceLineage.characterIds,
            portrait_node_ids: task.referenceLineage.portraitNodeIds,
            portrait_version_ids: task.referenceLineage.portraitVersionIds,
            reference_images: referenceImages,
            reference_images_count: referenceImages.length,
            reference_image_collection: task.referenceImageCollection,
            reference_images_sent: task.referenceImagesSent,
            reference_images_supported: task.referenceImagesSupported,
            task_id: data.task_id || '',
            generated_at: new Date().toISOString(),
          },
        })
      } catch (error: any) {
        message.warning(error?.message || '图片已生成，但回写项目素材失败')
      }
    }

    setInlineImages((prev) => ({
      ...prev,
      [task.key]: {
        assetId,
        taskId: String(data.task_id || task.taskId || ''),
        url: urls[0] || '',
        localPath: localPaths[0] || data.local_path,
        referenceImages: task.referenceImageCollection,
        referenceImagesSent: task.referenceImagesSent,
        referenceImagesSupported: task.referenceImagesSupported,
        prompt: task.prompt,
        provider: data.provider || task.provider,
        model: data.model || task.model,
        createdAt: new Date().toISOString(),
      },
    }))
    await loadProjectAssets(task.projectId)
    message.success(assetId ? '图片已生成并关联到项目素材' : '图片已生成')
  }, [])

  useTaskPolling({
    enabled: Boolean(pendingInlineImageTask?.taskId),
    intervalMs: 5000,
    fetcher: useCallback(() => {
      if (!pendingInlineImageTask) return Promise.resolve(null as any)
      return getImageTask(pendingInlineImageTask.taskId, pendingInlineImageTask.provider)
    }, [pendingInlineImageTask]),
    isDone: useCallback((data: any) => data?.success && data?.status === 'done', []),
    isFailed: useCallback((data: any) => data?.success === false || data?.status === 'error' || data?.status === 'failed', []),
    onData: useCallback(() => undefined, []),
    onDone: useCallback(async (data: any) => {
      if (!pendingInlineImageTask) return
      try {
        await finalizeInlineImageResult(data, pendingInlineImageTask)
      } catch (error: any) {
        message.error(error?.message || '异步生图结果处理失败')
      } finally {
        setPendingInlineImageTask(null)
        setInlineImageLoadingKey(null)
      }
    }, [finalizeInlineImageResult, pendingInlineImageTask]),
    onFailed: useCallback((data: any) => {
      message.error(data?.error || '异步生图失败')
      setPendingInlineImageTask(null)
      setInlineImageLoadingKey(null)
    }, []),
    onError: useCallback(() => undefined, []),
  })

  async function waitForInlineImageTask(task: PendingInlineImageTask) {
    const maxAttempts = 120
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const data = await getImageTask(task.taskId, task.provider)
      if (data?.success && data?.status === 'done') {
        await finalizeInlineImageResult(data, task)
        return
      }
      if (data?.success === false || data?.status === 'error' || data?.status === 'failed') {
        throw new Error(data?.error || '异步生图失败')
      }
      await new Promise((resolve) => window.setTimeout(resolve, 5000))
    }
    throw new Error('异步生图等待超时，请到任务中心查看详情')
  }

  const handleInlineGenerateImage = async (
    prompt: string,
    context: ImagePromptContext = {},
    options: { awaitAsync?: boolean } = {},
  ) => {
    const trimmedPrompt = prompt.trim()
    if (!trimmedPrompt) {
      message.warning('请先填写生图提示词')
      return
    }
    if (!selectedProject) {
      message.warning('请先选择创作项目')
      return
    }
    if (!defaultImageModel.name) {
      message.warning('请先在顶部选择默认生图模型')
      return
    }

    const chapterNumber = context.chapterNumber ?? activeChapterNumber
    const normalizedContext = { ...context, chapterNumber }
    const key = imageContextKey(normalizedContext)
    const size = defaultImageModel.default_size || '1024x1024'
    setInlineImageLoadingKey(key)
    const referenceAssets = pickReferenceAssetsForContext(trimmedPrompt, normalizedContext)
    const referenceLineage = buildReferenceLineage(normalizedContext, referenceAssets)
    const loadedCharacters = await loadCharacterDetailsForIds(referenceLineage.characterIds)
    const projectReferenceItems: ReferenceImageItem[] = referenceAssets.map((asset) => ({
      url: `/api/v1/assets/${asset.asset_id}/thumbnail?original=true`,
      source: 'project_asset',
      label:
        asset.metadata?.label ||
        asset.metadata?.character_name ||
        asset.metadata?.source_title ||
        asset.role ||
        asset.asset_id,
      asset_id: asset.asset_id,
      role: asset.role,
      character_id: asset.metadata?.character_id,
      character_name: asset.metadata?.character_name,
    }))
    const characterReferenceItems = referenceLineage.characterIds.flatMap((characterId) =>
      getCharacterReferenceItems(loadedCharacters[characterId] || characterDetails[characterId]),
    )
    const portraitNodeReferenceItems = referenceLineage.portraitNodeIds.map((assetId) => {
      const character = referenceLineage.characterIds
        .map((characterId) => loadedCharacters[characterId] || characterDetails[characterId])
        .find((item) => item?.portrait_node_id === assetId)
      return portraitNodeToReferenceItem(assetId, character)
    })
    const referenceImageCollection = dedupeReferenceImageItems([
      ...projectReferenceItems,
      ...characterReferenceItems,
      ...portraitNodeReferenceItems,
    ]).slice(0, 6)
    const referenceImages = referenceImageCollection.map((item) => item.url)
    const supportsReferenceImages = defaultImageSupportsReferenceImages
    const requestReferenceImages = supportsReferenceImages ? referenceImages : []

    let startedAsyncTask = false
    try {
      const data = await generateImageApi({
        prompt: trimmedPrompt,
        provider: defaultImageModel.name,
        size,
        n: 1,
        project_id: selectedProject.id,
        content_id: normalizedContext.contentId || undefined,
        source_type: normalizedContext.sourceType || undefined,
        source_index:
          normalizedContext.sourceIndex !== undefined ? String(normalizedContext.sourceIndex) : undefined,
        source_title: normalizedContext.sourceTitle || undefined,
        chapter_number: chapterNumber !== undefined && chapterNumber !== null ? String(chapterNumber) : undefined,
        reference_asset_ids: referenceLineage.referenceAssetIds,
        character_ids: referenceLineage.characterIds,
        portrait_node_ids: referenceLineage.portraitNodeIds,
        portrait_version_ids: referenceLineage.portraitVersionIds,
        reference_image_collection: referenceImageCollection,
        reference_images: requestReferenceImages.length ? requestReferenceImages : undefined,
      })

      if (!data?.success) {
        message.error(data?.error || '图片生成失败')
        return
      }

      if (data.status === 'pending' && data.task_id) {
        const pendingTask: PendingInlineImageTask = {
          taskId: String(data.task_id),
          projectId: selectedProject.id,
          key,
          context: normalizedContext,
          prompt: trimmedPrompt,
          size,
          provider: data.provider || defaultImageModel.name,
          model: data.model || defaultImageModel.model || '',
          referenceLineage,
          referenceImageCollection,
          referenceImagesSent: requestReferenceImages.length,
          referenceImagesSupported: supportsReferenceImages,
        }
        if (options.awaitAsync) {
          await waitForInlineImageTask(pendingTask)
          return
        }
        startedAsyncTask = true
        setPendingInlineImageTask(pendingTask)
        message.info(`图片任务已提交，完成后自动回写项目：${data.task_id}`)
        return
      }

      const urls = data.urls?.length ? data.urls : data.url ? [data.url] : []
      const localPaths = data.all_local_paths?.length
        ? data.all_local_paths
        : data.local_path
          ? [data.local_path]
          : []
      const assetIds = data.all_asset_hub_node_ids?.length
        ? data.all_asset_hub_node_ids
        : data.asset_hub_node_id
          ? [data.asset_hub_node_id]
          : data.all_asset_ids?.length
            ? data.all_asset_ids
            : data.asset_id
              ? [data.asset_id]
              : []
      const assetId = assetIds[0]

      if (assetId) {
        try {
          await linkCreativeProjectAsset(selectedProject.id, {
            asset_id: assetId,
            content_id: normalizedContext.contentId || undefined,
            role: 'output',
            relation: 'derived_from',
            metadata: {
              source_type: normalizedContext.sourceType,
              source_index: normalizedContext.sourceIndex,
              source_title: normalizedContext.sourceTitle,
              chapter_number: chapterNumber,
              prompt: trimmedPrompt,
              provider: defaultImageModel.name,
              model: defaultImageModel.model || '',
              size,
              reference_asset_ids: referenceLineage.referenceAssetIds,
              character_ids: referenceLineage.characterIds,
              portrait_node_ids: referenceLineage.portraitNodeIds,
              portrait_version_ids: referenceLineage.portraitVersionIds,
              reference_images: referenceImages,
              reference_images_count: referenceImages.length,
              reference_image_collection: referenceImageCollection,
              reference_images_sent: requestReferenceImages.length,
              reference_images_supported: supportsReferenceImages,
              generated_at: new Date().toISOString(),
            },
          })
        } catch (error: any) {
          message.warning(error?.message || '图片已生成，但回写项目素材失败')
        }
      }

      setInlineImages((prev) => ({
        ...prev,
        [key]: {
          assetId,
          url: urls[0] || '',
          localPath: localPaths[0] || data.local_path,
          referenceImages: referenceImageCollection,
          referenceImagesSent: requestReferenceImages.length,
          referenceImagesSupported: supportsReferenceImages,
          prompt: trimmedPrompt,
          provider: data.provider || defaultImageModel.name,
          model: data.model || defaultImageModel.model || '',
          createdAt: new Date().toISOString(),
        },
      }))
      await loadProjectAssets(selectedProject.id)
      message.success(assetId ? '图片已生成并关联到项目素材' : '图片已生成')
      return true
    } catch (error: any) {
      message.error(error?.message || '图片生成失败')
      return false
    } finally {
      if (!startedAsyncTask) setInlineImageLoadingKey(null)
    }
  }

  async function loadCharacterDetailsForIds(ids: string[]) {
    const uniqueIds = dedupeStrings(ids)
    const missingIds = uniqueIds.filter((id) => !characterDetails[id])
    if (!missingIds.length) return characterDetails

    const resolved: Record<string, CharacterReferenceSummary> = {}
    await Promise.all(
      missingIds.map(async (id) => {
        try {
          const payload = await getCharacter(id)
          const character = normalizeCharacterReference(payload)
          if (character?.id) resolved[character.id] = character
        } catch (error) {
          console.warn('[StoryPage] load character reference failed', id, error)
        }
      }),
    )

    if (Object.keys(resolved).length) {
      setCharacterDetails((prev) => ({ ...prev, ...resolved }))
    }
    return { ...characterDetails, ...resolved }
  }

  function pickReferenceAssetsForContext(prompt: string, context: ImagePromptContext = {}, maxCount = 4) {
    const explicitIds = new Set([
      ...(context.referenceAssetIds || []),
      ...(context.portraitNodeIds || []),
    ].filter(Boolean))
    const explicitAssets = explicitIds.size
      ? projectAssets.filter((asset) => explicitIds.has(asset.asset_id))
      : []
    const pickedAssets = pickReferenceAssetsForPrompt(prompt, maxCount)
    const merged = [...explicitAssets, ...pickedAssets]
    const seen = new Set<string>()
    return merged.filter((asset) => {
      if (!asset.asset_id || seen.has(asset.asset_id)) return false
      seen.add(asset.asset_id)
      return true
    }).slice(0, maxCount)
  }

  function buildReferenceLineage(context: ImagePromptContext, referenceAssets: ProjectAssetLink[]) {
    const referenceAssetIds = dedupeStrings([
      ...(context.referenceAssetIds || []),
      ...referenceAssets.map((asset) => asset.asset_id),
    ])
    const characterIds = dedupeStrings([
      ...(context.characterIds || []),
      ...referenceAssets.map((asset) => asset.metadata?.character_id),
    ])
    const portraitNodeIds = dedupeStrings([
      ...(context.portraitNodeIds || []),
      ...referenceAssets
        .filter((asset) => asset.role === 'character')
        .map((asset) => asset.asset_id),
      ...referenceAssets.map((asset) => asset.metadata?.portrait_node_id),
    ])
    const portraitVersionIds = dedupeStrings([
      ...(context.portraitVersionIds || []),
      ...referenceAssets.map((asset) => asset.metadata?.portrait_version_id || asset.metadata?.main_portrait_version_id),
    ])
    return { referenceAssetIds, characterIds, portraitNodeIds, portraitVersionIds }
  }

  function pickReferenceAssetsForPrompt(prompt: string, maxCount = 4) {
    return selectReferenceAssetsForPrompt(projectAssets, prompt, maxCount)
  }

  useEffect(() => {
    loadProjects()
    loadLlmConnectors()
    loadImageBackends()
    loadPromptTemplates()
  }, [])

  useEffect(() => {
    const found = projects.find((item) => item.id === selectedId) || null
    setSelectedProject(found)
    const cachedUnavailableIds = found ? unavailableProjectAssetIds.get(found.id) : undefined
    setUnavailableAssetIds(Object.fromEntries([...(cachedUnavailableIds || [])].map((id) => [id, true] as const)))
    setWorkspaceErrors({})
    setWorkspaceLoading({ contents: false, writerRoom: false, assets: false, logs: false, graph: false })
    writerRoomRequestRef.current += 1
    setPipelineResult(null)
    setPipelineRunStatus('idle')
    if (found) {
      // The previous project's links must never be rendered or resolved under
      // the newly selected project while its workspace requests are in flight.
      setProjectAssets([])
      setWriterRoomContents([])
      setWriterRoomSummary([])
      loadContents(found.id)
      loadProjectAssets(found.id)
      loadGenerationLogs(found.id)
      loadContinuityFacts(found.id)
      loadProjectGraph(found.id)
      loadNarrativeRuntime(found.id, activeChapterNumber)
    } else {
      setContents([])
      setWriterRoomContents([])
      setWriterRoomSummary([])
      setProjectAssets([])
      setProjectGraph(null)
      setGenerationLogs([])
      setContinuityCandidates([])
      setContinuitySummary(null)
      setNarrativeContext(null)
      setForeshadowingLedger([])
      setAllForeshadowingLedger([])
      setNarrativeGraphData(null)
      setNarrativeHealth(null)
      setNarrativeRuns([])
    }
  }, [selectedId, projects])

  useEffect(() => {
    if (selectedProject?.id) void loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
  }, [selectedProject?.id, activeChapterNumber])

  useEffect(() => {
    if (activeWorkspaceTab !== 'writer-room' || !selectedProject?.id) return
    void loadWriterRoomContents(selectedProject.id, activeChapterNumber)
  }, [activeWorkspaceTab, selectedProject?.id, activeChapterNumber])

  useEffect(() => {
    setPendingInlineImageTask(null)
    setInlineImageLoadingKey(null)
  }, [selectedId])

  useEffect(() => {
    const projectId = selectedProject?.id
    if (!projectId) return

    let cancelled = false
    ;(async () => {
      try {
        const response = await listTasks({
          project_id: projectId,
          task_type: 'image_generation',
          active_only: true,
          include_detail: true,
        })
        if (cancelled) return
        const tasks = Array.isArray(response?.tasks) ? response.tasks : response?.data || []
        const task = tasks
          .filter((item: any) => item?.task_id && item?.payload?.project_id === projectId)
          .sort((a: any, b: any) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
        const payload = task?.payload
        if (!task || !payload) return

        const context: ImagePromptContext = {
          contentId: payload.content_id || undefined,
          sourceType: payload.source_type || undefined,
          sourceIndex: payload.source_index !== undefined && payload.source_index !== '' ? payload.source_index : undefined,
          sourceTitle: payload.source_title || undefined,
          chapterNumber:
            payload.chapter_number !== undefined && payload.chapter_number !== ''
              ? Number(payload.chapter_number)
              : undefined,
        }
        const referenceLineage = {
          referenceAssetIds: Array.isArray(payload.reference_asset_ids) ? payload.reference_asset_ids : [],
          characterIds: Array.isArray(payload.character_ids) ? payload.character_ids : [],
          portraitNodeIds: Array.isArray(payload.portrait_node_ids) ? payload.portrait_node_ids : [],
          portraitVersionIds: Array.isArray(payload.portrait_version_ids) ? payload.portrait_version_ids : [],
        }
        const referenceImageCollection = Array.isArray(payload.reference_image_collection)
          ? payload.reference_image_collection
          : []
        const key = imageContextKey(context)
        setPendingInlineImageTask({
          taskId: String(task.task_id),
          projectId,
          key,
          context,
          prompt: String(payload.prompt || ''),
          size: String(payload.size || '1024x1024'),
          provider: String(payload.provider || ''),
          model: String(payload.model || ''),
          referenceLineage,
          referenceImageCollection,
          referenceImagesSent: Array.isArray(payload.reference_images) ? payload.reference_images.length : 0,
          referenceImagesSupported: Array.isArray(payload.reference_images) && payload.reference_images.length > 0,
        })
        setInlineImageLoadingKey(key)
        message.info(`已恢复未完成的生图任务：${task.task_id}`)
      } catch {
        // Task recovery is best effort; the project workspace remains usable.
      }
    })()

    return () => {
      cancelled = true
    }
  }, [selectedProject?.id])

  useEffect(() => {
    const projectId = selectedProject?.id
    if (!projectId) return
    const ids = Array.from(new Set(projectAssets.map((asset) => asset.asset_id).filter(Boolean)))
    const knownUnavailableIds = unavailableProjectAssetIds.get(projectId) || new Set<string>()
    unavailableProjectAssetIds.set(projectId, knownUnavailableIds)
    const missingIds = ids.filter((id) => !assetDetails[id] && !knownUnavailableIds.has(id))
    if (!missingIds.length) return

    // Mark them before starting requests. This also prevents a render caused by
    // another resolved asset from issuing the same in-flight request again.
    missingIds.forEach((id) => knownUnavailableIds.add(id))
    setUnavailableAssetIds((previous) => ({
      ...previous,
      ...Object.fromEntries(missingIds.map((id) => [id, true] as const)),
    }))

    let cancelled = false
    ;(async () => {
      const entries = await Promise.all(
        missingIds.map(async (id) => {
          const asset = await resolveProjectAssetDetail(id)
          return [id, asset] as const
        }),
      )
      if (cancelled) return
      const next: Record<string, AssetSummary> = {}
      const resolvedIds: string[] = []
      entries.forEach(([id, asset]) => {
        if (asset) {
          next[id] = asset
          resolvedIds.push(id)
          knownUnavailableIds.delete(id)
        }
      })
      if (resolvedIds.length) {
        setUnavailableAssetIds((previous) => {
          const remaining = { ...previous }
          resolvedIds.forEach((id) => delete remaining[id])
          return remaining
        })
      }
      if (Object.keys(next).length) {
        setAssetDetails((prev) => ({ ...prev, ...next }))
      }
    })()

    return () => {
      cancelled = true
    }
  }, [projectAssets, assetDetails])

  useEffect(() => {
    if (!selectedProject?.id) {
      setInlineImages({})
      return
    }

    const outputLinks = projectAssets.filter((link) => {
      const metadata = link.metadata || {}
      return (
        link.role === 'output' &&
        metadata.source !== 'video_generation' &&
        metadata.source_type &&
        metadata.source_index !== undefined
      )
    })

    if (!outputLinks.length) {
      setInlineImages({})
      return
    }

    let cancelled = false
    ;(async () => {
      const entries = await Promise.all(
        outputLinks.map(async (link) => {
          const metadata = link.metadata || {}
          const context: ImagePromptContext = {
            contentId: link.content_id || undefined,
            sourceType: metadata.source_type,
            sourceIndex: metadata.source_index,
            chapterNumber:
              metadata.chapter_number !== undefined && metadata.chapter_number !== null
                ? Number(metadata.chapter_number)
                : undefined,
          }
          const key = imageContextKey(context)
          const asset = await resolveProjectAssetDetail(link.asset_id)
          return [
            key,
            {
              assetId: link.asset_id,
              url: asset?.thumbnail_url || asset?.cover_url || asset?.source_url || '',
              localPath: asset?.file_path || '',
              prompt: metadata.prompt || asset?.metadata?.prompt || '',
              provider: metadata.provider || asset?.metadata?.provider || asset?.platform || '',
              model: metadata.model || asset?.metadata?.model || '',
              referenceImages: metadata.reference_image_collection || [],
              referenceImagesSent: metadata.reference_images_sent || 0,
              referenceImagesSupported: metadata.reference_images_supported,
              createdAt: metadata.generated_at || link.created_at || '',
            } satisfies InlineGeneratedImage,
          ] as const
        }),
      )

      if (!cancelled) {
        setInlineImages(Object.fromEntries([...entries].reverse()))
      }
    })()

    return () => {
      cancelled = true
    }
  }, [selectedProject?.id, projectAssets])

  useEffect(() => {
    if (!selectedProject?.id) return
    const ids = collectStoryboardCharacterIds(contents)
    if (ids.length) {
      loadCharacterDetailsForIds(ids)
    }
  }, [selectedProject?.id, contents])

  useEffect(() => {
    if (!selectedProject?.id || !chapters.length) return
    const chapterNumbers = chapters
      .map((item: ChapterPlanItem) => Number(item.chapter_number))
      .filter((value) => Number.isInteger(value) && value > 0)
    if (!chapterNumbers.length) return

    const restoreState = activeChapterRestoreRef.current
    if (restoreState.projectId !== selectedProject.id) {
      restoreState.projectId = selectedProject.id
      restoreState.restoredPersistedChapter = null
      restoreState.pendingLocalChapter = null
    }

    const savedChapter = Number(selectedProject.metadata?.writer_room_active_chapter)
    const hasSavedChapter = chapterNumbers.includes(savedChapter)

    // A project-list refresh can arrive before the PATCH response. Keep the
    // user's local selection until the server echoes the same persisted value.
    if (restoreState.pendingLocalChapter !== null) {
      if (savedChapter === restoreState.pendingLocalChapter) {
        restoreState.restoredPersistedChapter = savedChapter
        restoreState.pendingLocalChapter = null
      } else if (chapterNumbers.includes(restoreState.pendingLocalChapter)) {
        setActiveChapterNumber(restoreState.pendingLocalChapter)
        return
      } else {
        restoreState.pendingLocalChapter = null
      }
    }

    // Project details and chapter content load independently. Apply a newly
    // hydrated saved chapter once, even when chapter data reached this effect
    // first with incomplete project metadata.
    if (hasSavedChapter && restoreState.restoredPersistedChapter !== savedChapter) {
      restoreState.restoredPersistedChapter = savedChapter
      setActiveChapterNumber(savedChapter)
      return
    }

    if (!chapterNumbers.includes(activeChapterNumber)) {
      setActiveChapterNumber(chapterNumbers[0])
    }
  }, [selectedProject?.id, selectedProject?.metadata?.writer_room_active_chapter, chapters, activeChapterNumber])

  async function handleActiveChapterChange(nextChapter: number) {
    if (!selectedProject) return
    const chapterNumber = Number(nextChapter)
    if (!chapters.some((item: ChapterPlanItem) => Number(item.chapter_number) === chapterNumber)) return

    activeChapterRestoreRef.current.pendingLocalChapter = chapterNumber
    setActiveChapterNumber(chapterNumber)
    const metadata = { ...(selectedProject.metadata || {}), writer_room_active_chapter: chapterNumber }
    try {
      const response = (await updateCreativeProject(selectedProject.id, { metadata })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
    } catch (error: any) {
      // The local selection remains usable; persistence can retry on the next chapter switch.
      message.warning(error?.message || '保存当前写作章节失败')
    }
  }

  async function handleCreativeSkillIdsChange(nextSkillIds: string[]) {
    if (!selectedProject) return
    const settings = {
      ...(selectedProject.settings || {}),
      creative_skill_ids: nextSkillIds,
    }
    try {
      const response = (await updateCreativeProject(selectedProject.id, { settings })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
        message.success('已保存写作方法包')
      }
    } catch (error: any) {
      message.error(error?.message || '保存写作方法包失败')
    }
  }

  const selectedProjectIndex = useMemo(
    () => projects.findIndex((item) => item.id === selectedId),
    [projects, selectedId],
  )

  const retryWorkspaceLoads = () => {
    if (!selectedProject) return
    void Promise.all([
      loadContents(selectedProject.id),
      loadWriterRoomContents(selectedProject.id),
      loadProjectAssets(selectedProject.id),
      loadGenerationLogs(selectedProject.id),
      loadProjectGraph(selectedProject.id),
    ])
  }

  const activeLlm = useMemo(
    () => llmConnectors.find((item) => item.name === selectedLlm) || null,
    [llmConnectors, selectedLlm],
  )

  const llmAvailable = useMemo(
    () => Boolean(llmConnectors.length && selectedLlm && selectedModel),
    [llmConnectors, selectedLlm, selectedModel],
  )

  const modelOptions = useMemo(() => {
    const models = activeLlm?.available_models?.length
      ? activeLlm.available_models
      : activeLlm?.default_model
        ? [activeLlm.default_model]
        : []
    return Array.from(new Set(models.filter(Boolean))).map((model) => ({
      label: model,
      value: model,
    }))
  }, [activeLlm])

  const imageModelOptions = useMemo(
    () =>
      imageBackends.map((backend) => ({
        label: `${backend.name}${backend.model ? ` · ${backend.model}` : ''}`,
        value: backend.name,
      })),
    [imageBackends],
  )

  const templateOptionsByStage = useMemo(() => {
    const grouped: Record<string, { label: string; value: string }[]> = {}
    promptTemplates.forEach((template) => {
      const stage = template.template_stage || 'outline'
      if (!grouped[stage]) grouped[stage] = []
      grouped[stage].push({
        label: `${template.name}${template.description ? ` · ${template.description}` : ''}`,
        value: template.id,
      })
    })
    return grouped
  }, [promptTemplates])

  const contentByChapter = useMemo(() => {
    const grouped: Record<string, Record<number, ProjectContent>> = {}
    contents.forEach((item) => {
      const chapterNumber = Number(item.chapter_number || item.episode_number || 0)
      if (!chapterNumber || !item.content_type) return
      if (!grouped[item.content_type]) grouped[item.content_type] = {}
      const current = grouped[item.content_type][chapterNumber]
      if (isProjectContentNewer(item, current)) {
        grouped[item.content_type][chapterNumber] = item
      }
    })
    return grouped
  }, [contents])

  const contentForChapter = (contentType: string, chapterNumber: number) =>
    contentByChapter[contentType]?.[chapterNumber]

  const productionStages = useMemo(() => {
    const chapterTarget = Math.max(chapters.length, 1)
    const countChapterOutput = (contentType: string) => Object.keys(contentByChapter[contentType] || {}).length
    const productionComplete = ['chapter_outline', 'novel_body', 'script', 'storyboard']
      .reduce((total, contentType) => total + countChapterOutput(contentType), 0)
    const reviewedChapters = new Set(
      writerRoomSummary
        .filter((item) => item.content_type === 'prose_review')
        .map((item) => Number(item.chapter_number || item.episode_number || 0))
        .filter(Boolean),
    ).size

    return [
      { key: 'outline', tab: 'outline', label: '故事蓝图', hint: '大纲', complete: hasOutline ? 1 : 0, total: 1 },
      {
        key: 'bible',
        tab: 'project-bible',
        label: '项目设定',
        hint: '圣经 / 世界',
        complete: projectBibleContents.length || worldAssetContents.length ? 1 : 0,
        total: 1,
      },
      { key: 'chapters', tab: 'chapters', label: '章节规划', hint: `${chapters.length} 话`, complete: chapters.length ? 1 : 0, total: 1 },
      {
        key: 'production',
        tab: 'episode-workbench',
        label: '单话制作',
        hint: '细纲 / 正文 / 脚本 / 分镜',
        complete: productionComplete,
        total: chapterTarget * 4,
      },
      {
        key: 'review',
        tab: 'writer-room',
        label: '写作审校',
        hint: '候选与连续性',
        complete: reviewedChapters,
        total: Math.max(countChapterOutput('novel_body'), 1),
      },
      {
        key: 'lineage',
        tab: 'canvas',
        label: '关系与交付',
        hint: `${projectAssets.length} 个关联素材`,
        complete: projectAssets.length ? 1 : 0,
        total: 1,
      },
    ]
  }, [
    chapters.length,
    contentByChapter,
    hasOutline,
    projectAssets.length,
    projectBibleContents.length,
    worldAssetContents.length,
    writerRoomSummary,
  ])

  const activeChapter = useMemo(
    () => chapters.find((item: ChapterPlanItem) => item.chapter_number === activeChapterNumber) || null,
    [chapters, activeChapterNumber],
  )

  const narrativeInspectorLogs = useMemo(() => {
    const chapterContentIds = new Set(
      contents
        .filter((item) => Number(item.chapter_number || item.episode_number || 0) === activeChapterNumber)
        .map((item) => item.id),
    )
    return generationLogs.filter((log) => log.content_id && chapterContentIds.has(log.content_id)).slice(0, 12)
  }, [contents, generationLogs, activeChapterNumber])

  const isChapterActionLoading = (action: ChapterAction, chapterNumber: number) =>
    loadingChapterAction.action === action && loadingChapterAction.chapterNumber === chapterNumber

  const openWorkspaceTab = (tab: string, mode?: 'overview' | 'chapter') => {
    const chapterTabs = new Set(['episode-workbench', 'writer-room', 'script'])
    const nextMode = mode || (chapterTabs.has(tab) ? 'chapter' : 'overview')
    setActiveWorkspaceTab(tab)
    setWorkspaceMode(nextMode)
    if (nextMode === 'chapter') setOverviewDetailOpen(false)
  }

  const openChapterStudio = (chapterNumber: number, tab = 'episode-workbench') => {
    handleActiveChapterChange(chapterNumber)
    openWorkspaceTab(tab, 'chapter')
  }

  function startHorizontalResize(
    event: React.MouseEvent,
    options: {
      initial: number
      min: number
      max: number
      onChange: (value: number) => void
    },
  ) {
    event.preventDefault()
    const startX = event.clientX
    const startValue = options.initial
    const handleMove = (moveEvent: MouseEvent) => {
      const next = Math.min(options.max, Math.max(options.min, startValue + moveEvent.clientX - startX))
      options.onChange(next)
    }
    const handleUp = () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
  }

  async function loadProjects(nextSelectedId?: string) {
    setLoadingAction('projects')
    try {
      const response = (await listCreativeProjects({ limit: 80 })) as CreativeProjectListResponse
      const data = response.data || []
      setProjects(data)
      setProjectListError('')
      const requestedId = nextSelectedId !== undefined
        ? nextSelectedId
        : searchParams.get('project_id') || selectedId
      const targetId = requestedId && data.some((item) => item.id === requestedId)
        ? requestedId
        : data[0]?.id || ''
      setSelectedId(targetId)
    } catch (error: any) {
      setProjectListError(error?.message || '项目列表加载失败')
      message.error(error?.message || '项目列表加载失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function loadLlmConnectors() {
    try {
      const response = await listConnectors({ provider_type: 'llm', active_only: true })
      const connectors = (response?.connectors || []) as Provider[]
      setLlmConnectors(connectors)
      const defaultConnector =
        connectors.find((item) => item.is_default) ||
        connectors.sort((a, b) => (a.priority || 0) - (b.priority || 0))[0]
      if (defaultConnector) {
        setSelectedLlm((current) => current || defaultConnector.name)
        setSelectedModel((current) => current || defaultConnector.default_model || '')
      }
    } catch (error) {
      setLlmConnectors([])
    }
  }

  async function loadImageBackends() {
    try {
      const response = await getImageBackends()
      setImageBackends((response?.backends || []) as ImageBackendOption[])
    } catch {
      setImageBackends([])
    }
  }

  async function handleDefaultImageModelChange(value?: string) {
    if (!selectedProject) return
    const backend = imageBackends.find((item) => item.name === value)
    const nextMeta = { ...activeProjectMeta }
    if (backend) {
      nextMeta.default_image_model = {
        name: backend.name,
        provider: backend.provider,
        provider_label: backend.provider_label,
        model: backend.model,
        default_size: backend.supported_sizes?.[0] || '1024x1024',
        support_reference_image: Boolean(backend.support_reference_image),
        capabilities: backend.capabilities || [],
      }
    } else {
      delete nextMeta.default_image_model
    }

    setSavingImageModel(true)
    try {
      const response = (await updateCreativeProject(selectedProject.id, { metadata: nextMeta })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
      message.success(backend ? '默认生图模型已保存' : '已清除默认生图模型')
    } catch (error: any) {
      message.error(error?.message || '保存默认生图模型失败')
    } finally {
      setSavingImageModel(false)
    }
  }

  async function loadPromptTemplates() {
    try {
      const response = await getPlatformTemplates({ template_scope: 'creative_project' })
      const templates = (response?.templates || []) as PlatformTemplate[]
      setPromptTemplates(templates)
      setSelectedPromptTemplates((current) => {
        const next = { ...current }
        ;[
          'outline',
          'chapter_plan',
          'chapter_outline',
          'novel_body',
          'comic_pages',
          'script',
          'storyboard',
          ...writerRoomStepOptions.map((item) => item.value),
        ].forEach((stage) => {
          if (!next[stage]) {
            const template = templates.find((item) => item.template_stage === stage)
            if (template) next[stage] = template.id
          }
        })
        return next
      })
    } catch {
      setPromptTemplates([])
    }
  }

  async function loadContents(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, contents: true }))
    try {
      const response = await listCreativeProjectContents(projectId, undefined, {
        contentTypes: STORY_WORKSPACE_CONTENT_TYPES,
      })
      setContents(response?.data || [])
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.contents; return next })
    } catch (error: any) {
      setContents([])
      setWorkspaceErrors((current) => ({ ...current, contents: error?.message || '项目内容加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, contents: false }))
    }
  }

  async function loadWriterRoomContents(projectId: string, chapterNumber?: number) {
    const requestId = writerRoomRequestRef.current + 1
    writerRoomRequestRef.current = requestId
    setWorkspaceLoading((current) => ({ ...current, writerRoom: true }))
    const contentTypes = writerRoomStepOptions.map((item) => item.value)
    const mergeCandidates = (incoming: ProjectContent[]) => {
      if (writerRoomRequestRef.current !== requestId) return
      setWriterRoomContents((current) => {
        const byId = new Map(current.map((item) => [item.id, item]))
        incoming.forEach((item) => byId.set(item.id, item))
        return Array.from(byId.values())
      })
    }
    try {
      // The inspected chapter is the user's immediate need. Load its small
      // version history first; project-wide latest candidates can reconcile
      // afterward without holding the workspace in an empty state.
      if (chapterNumber) {
        const historyResponse = await listCreativeProjectContents(projectId, undefined, {
          includeHistory: true,
          contentTypes,
          chapterNumber,
        })
        mergeCandidates(historyResponse?.data || [])
      }
      if (writerRoomRequestRef.current !== requestId) return
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.writerRoom; return next })

      // Project-wide stage counters power the chapter rail and overview badges.
      // They only need identity/version metadata, so fetch the summary rail
      // without text_content/data instead of shipping every chapter's prose.
      void listCreativeProjectContents(projectId, undefined, { contentTypes, summary: true })
        .then((response) => setWriterRoomSummary(response?.data || []))
        .catch((error: any) => {
          if (writerRoomRequestRef.current !== requestId) return
          // The current chapter remains usable even when the auxiliary rail
          // refresh fails. Surface the failure instead of turning it into an
          // empty "not generated" state.
          setWorkspaceErrors((current) => ({
            ...current,
            writerRoom: error?.message || '写作室章节轨刷新失败',
          }))
        })
    } catch (error: any) {
      if (writerRoomRequestRef.current !== requestId) return
      // Keep already visible candidates when this auxiliary refresh fails.
      setWorkspaceErrors((current) => ({ ...current, writerRoom: error?.message || '写作室候选加载失败' }))
    } finally {
      if (writerRoomRequestRef.current === requestId) {
        setWorkspaceLoading((current) => ({ ...current, writerRoom: false }))
      }
    }
  }

  async function loadProjectAssets(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, assets: true }))
    try {
      const response = await listCreativeProjectAssets(projectId)
      setProjectAssets(response?.data || [])
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.assets; return next })
    } catch (error: any) {
      setProjectAssets([])
      setWorkspaceErrors((current) => ({ ...current, assets: error?.message || '项目素材关联加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, assets: false }))
    }
  }

  async function loadGenerationLogs(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, logs: true }))
    try {
      const response = await listCreativeProjectGenerationLogs(projectId, { limit: 80 })
      setGenerationLogs(response?.data || [])
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.logs; return next })
    } catch (error: any) {
      setGenerationLogs([])
      setWorkspaceErrors((current) => ({ ...current, logs: error?.message || '生成日志加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, logs: false }))
    }
  }

  async function loadContinuityFacts(projectId: string) {
    try {
      const [candidates, summary] = await Promise.all([
        listCreativeProjectContinuityCandidates(projectId, { limit: 200 }),
        getCreativeProjectContinuityContextSummary(projectId),
      ])
      setContinuityCandidates(candidates?.data || [])
      setContinuitySummary(summary?.data || null)
    } catch {
      setContinuityCandidates([])
      setContinuitySummary(null)
    }
  }

  async function ensureWritingPreflight(chapterNumber: number, stage: string, contentId?: string) {
    if (!selectedProject) return false
    try {
      const response = await getCreativeProjectWritingPreflight(selectedProject.id, {
        chapterNumber,
        stage,
        contentId,
      })
      const result = response?.data
      if (result?.ready) return true
      message.warning(result?.next_action || '当前阶段还有前置条件未完成')
      return false
    } catch (error: any) {
      message.warning(error?.message || '无法检查当前写作阶段的前置条件')
      return false
    }
  }

  async function loadNarrativeRuntime(projectId: string, chapterNumber: number) {
    setNarrativeLoading(true)
    try {
      const [context, chapterLedger, fullLedger, graph, health, runs] = await Promise.allSettled([
        getCreativeProjectNarrativeContextPreview(projectId, chapterNumber),
        listCreativeProjectForeshadowing(projectId, { chapterNumber }),
        listCreativeProjectForeshadowing(projectId),
        getCreativeProjectNarrativeGraph(projectId, { chapterNumber }),
        getCreativeProjectNarrativeHealth(projectId),
        listCreativeProjectNarrativeRuns(projectId),
      ])
      setNarrativeContext(context.status === 'fulfilled' ? context.value?.data || null : null)
      setForeshadowingLedger(chapterLedger.status === 'fulfilled' ? chapterLedger.value?.data?.data || [] : [])
      setAllForeshadowingLedger(fullLedger.status === 'fulfilled' ? fullLedger.value?.data?.data || [] : [])
      setNarrativeGraphData(graph.status === 'fulfilled' ? graph.value?.data || null : null)
      setNarrativeHealth(health.status === 'fulfilled' ? health.value?.data || null : null)
      setNarrativeRuns(runs.status === 'fulfilled' ? runs.value?.data || [] : [])
    } finally {
      setNarrativeLoading(false)
    }
  }

  async function handleNarrativeRunControl(runId: string, action: 'pause' | 'resume' | 'retry' | 'cancel') {
    if (!selectedProject) return
    try {
      await controlCreativeProjectNarrativeRun(selectedProject.id, runId, action)
      await loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
    } catch (error: any) {
      message.error(error?.message || '叙事运行操作失败')
    }
  }

  async function handleNarrativeAutopilot(enabled: boolean) {
    if (!selectedProject) return
    try {
      await configureCreativeProjectNarrativeAutopilot(selectedProject.id, {
        enabled,
        chapter_numbers: [activeChapterNumber],
      })
      await loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
    } catch (error: any) {
      message.error(error?.message || '受控自动推进配置失败')
    }
  }

  async function handleForeshadowingDecision(itemId: string, action: 'accept' | 'advance' | 'resolve' | 'ignore') {
    if (!selectedProject) return
    try {
      await decideCreativeProjectForeshadowing(selectedProject.id, itemId, action, { current_chapter: activeChapterNumber })
      await loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
    } catch (error: any) {
      message.error(error?.message || '伏笔状态更新失败')
    }
  }

  async function loadProjectGraph(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, graph: true }))
    try {
      const response = await getCreativeProjectCanvas(projectId)
      setProjectGraph(response?.data || { nodes: [], edges: [] })
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.graph; return next })
    } catch (error: any) {
      setProjectGraph({ nodes: [], edges: [] })
      setWorkspaceErrors((current) => ({ ...current, graph: error?.message || '项目关系图谱加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, graph: false }))
    }
  }

  async function loadNovelAssets() {
    setLoadingNovelAssets(true)
    try {
      const response = await listAssets({ asset_type: 'novel', page_size: 100 })
      setNovelAssets(response?.data || [])
    } catch (error: any) {
      setNovelAssets([])
      message.warning(error?.message || '加载小说书架失败')
    } finally {
      setLoadingNovelAssets(false)
    }
  }

  async function handleCreate(values: any) {
    setLoadingAction('create')
    try {
      let response: CreativeProjectResponse
      if (values.source_type === 'novel') {
        const chapterIndices = [
          ...(Array.isArray(values.chapter_indices) ? values.chapter_indices : []),
          ...parseChapterRange(values.chapter_range || ''),
        ].filter((value, index, array) => Number.isFinite(value) && value > 0 && array.indexOf(value) === index)
        response = (await createCreativeProjectFromNovel({
          asset_id: values.novel_asset_id,
          chapter_indices: chapterIndices,
          title: values.title || getNovelDisplayTitle(selectedNovelAsset),
          project_type: values.project_type,
        })) as CreativeProjectResponse
      } else {
        response = (await createCreativeProject({
          title: values.title,
          idea: values.idea,
          project_type: values.project_type,
          source_type: 'original_idea',
        })) as CreativeProjectResponse
      }
      message.success('项目已创建')
      setCreateOpen(false)
      form.resetFields()
      await loadProjects(response.data.id)
    } catch (error: any) {
      message.error(error?.message || '创建失败')
    } finally {
      setLoadingAction(null)
    }
  }

  // 打开重命名弹窗，并把当前项目名预填到表单
  function openRenameModal() {
    if (!selectedProject) {
      message.warning('请先选择项目')
      return
    }
    renameForm.setFieldsValue({ title: selectedProject.title || '' })
    setRenameOpen(true)
  }

  // 提交重命名：调用 PATCH 接口更新项目名，并刷新当前项目
  async function handleRename(values: { title: string }) {
    if (!selectedProject) return
    const nextTitle = (values.title || '').trim()
    if (!nextTitle) {
      message.error('项目名不能为空')
      return
    }
    if (nextTitle === selectedProject.title) {
      setRenameOpen(false)
      return
    }
    setLoadingAction('rename')
    try {
      const response = (await updateCreativeProject(selectedProject.id, { title: nextTitle })) as CreativeProjectResponse
      setSelectedProject(response.data)
      // 同步刷新项目列表中的标题
      setProjects((prev) => prev.map((p) => (p.id === response.data.id ? response.data : p)))
      message.success('项目已重命名')
      setRenameOpen(false)
    } catch (error: any) {
      message.error(error?.message || '重命名失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleDeleteProject() {
    if (!selectedProject) return
    const deletingId = selectedProject.id
    setLoadingAction('delete_project')
    try {
      await deleteCreativeProject(deletingId)
      message.success('项目已删除，角色库和素材库资产已保留')
      setSelectedId('')
      setSelectedProject(null)
      setContents([])
      setWriterRoomContents([])
      setProjectAssets([])
      setGenerationLogs([])
      await loadProjects()
    } catch (error: any) {
      message.error(error?.message || '删除项目失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function refreshSelected(project?: CreativeProject | null) {
    if (project) {
      setProjects((prev) => prev.map((item) => (item.id === project.id ? project : item)))
      setSelectedId(project.id)
      await loadContents(project.id)
      await loadProjectAssets(project.id)
      await loadGenerationLogs(project.id)
    } else {
      await loadProjects(selectedId)
    }
  }

  async function handleLinkAsset(assetId: string, role: string, metadata?: Record<string, any>) {
    if (!selectedProject || !assetId.trim()) return
    setLoadingAction('asset')
    try {
      await linkCreativeProjectAsset(selectedProject.id, {
        asset_id: assetId.trim(),
        role,
        relation: role === 'output' ? 'derived_from' : 'references',
        metadata: metadata || {},
      })
      message.success('素材已关联到项目')
      await loadProjectAssets(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '关联素材失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleSaveContent(
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) {
    if (!selectedProject) return
    setSavingContentId(contentId)
    try {
      await updateCreativeProjectContent(selectedProject.id, contentId, patch)
      message.success('内容已保存')
      await loadContents(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '保存失败')
    } finally {
      setSavingContentId(null)
    }
  }

  async function handleUpdateStoryboardPanelReferences(
    contentId: string,
    panelNumber: number,
    referenceAssetIds: string[],
  ) {
    const source = contents.find((item) => item.id === contentId)
    if (!source) return
    const panels = Array.isArray(source.data?.panels) ? source.data.panels : []
    const nextData = {
      ...source.data,
      panels: panels.map((panel: any) => {
        if (Number(panel.panel_number) !== Number(panelNumber)) return panel
        return { ...panel, reference_asset_ids: dedupeStrings(referenceAssetIds) }
      }),
    }
    await handleSaveContent(contentId, { data: nextData })
  }

  async function handleSyncCharacters() {
    if (!selectedProject) return
    setLoadingAction('sync_characters')
    try {
      const response = (await syncCreativeProjectCharacters(selectedProject.id)) as CreativeProjectGenerateResponse
      message.success('大纲角色已同步到角色库')
      await refreshSelected(response.project || null)
      await loadProjectAssets(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '同步角色库失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleSyncProjectBible(overwrite = false) {
    if (!selectedProject) return
    setLoadingAction('project_bible')
    try {
      const response = (await syncCreativeProjectBible(selectedProject.id, { overwrite })) as { data?: ProjectContent[] }
      const count = response.data?.length || 0
      message.success(count ? `已同步 ${count} 张圣经/世界资产卡` : '圣经/世界资产已是最新，无需补齐')
      await loadContents(selectedProject.id)
      await refreshSelected(selectedProject)
    } catch (error: any) {
      message.error(error?.message || '同步项目圣经失败')
    } finally {
      setLoadingAction(null)
    }
  }

  function buildProjectCharacterPortraitPrompt(record: StoryOutlineCharacter) {
    const parts = [
      '单人角色立绘，完整角色设定图，适合作为后续漫画/短剧分镜的一致性参考图。',
      record.name ? `角色名：${record.name}` : '',
      record.role ? `角色定位：${record.role}` : '',
      record.age_range ? `年龄范围：${record.age_range}` : '',
      record.appearance ? `外貌特征：${record.appearance}` : '',
      record.costume_hint ? `服装与配饰：${record.costume_hint}` : '',
      record.signature_items?.length ? `标志物：${record.signature_items.join('、')}` : '',
      record.expressions?.length ? `常用表情：${record.expressions.join('、')}` : '',
      record.poses?.length ? `常用姿态：${record.poses.join('、')}` : '',
      record.visual_consistency ? `一致性规则：${record.visual_consistency}` : '',
      record.personality ? `性格气质：${record.personality}` : '',
      record.image_prompt ? `既有生图提示：${record.image_prompt}` : '',
      outline.image_style_prompt ? `项目统一画风：${outline.image_style_prompt}` : '',
      '要求：正面半身或全身清晰可辨，干净背景，角色特征稳定，不添加无关人物，不遮挡脸部。',
    ]
    return parts.filter(Boolean).join('\n')
  }

  async function handleGenerateCharacterPortrait(record: StoryOutlineCharacter) {
    if (!selectedProject) return
    if (!record.character_id) {
      message.warning('请先同步角色库，再生成角色立绘')
      return
    }
    if (!defaultImageModel.name) {
      message.warning('请先在顶部选择默认生图模型')
      return
    }
    const key = record.character_id || record.name || ''
    setPortraitGeneratingCharacter(key)
    setLoadingAction('portrait_generate')
    try {
      const prompt = buildProjectCharacterPortraitPrompt(record)
      const size = defaultImageModel.default_size || '1024x1024'
      const response = await generateCharacterPortrait(record.character_id, {
        prompt,
        provider: defaultImageModel.name,
        model: defaultImageModel.model || undefined,
        size,
        n: 1,
      })
      const nodeId = response?.data?.node_id
      if (nodeId) {
        await linkCreativeProjectAsset(selectedProject.id, {
          asset_id: nodeId,
          role: 'character',
          relation: 'portrait',
          metadata: {
            character_id: record.character_id,
            character_name: record.name,
            prompt,
            provider: defaultImageModel.name,
            model: defaultImageModel.model || '',
            generated_from: 'creative_project_outline_character',
            generated_at: new Date().toISOString(),
          },
        })
        const nextOutline = {
          ...outline,
          characters: (outline.characters || []).map((item: StoryOutlineCharacter) => {
            const sameCharacter = item.character_id
              ? item.character_id === record.character_id
              : item.name === record.name
            if (!sameCharacter) return item
            const refs = Array.from(new Set([...(item.reference_asset_ids || []), nodeId]))
            return { ...item, portrait_asset_id: nodeId, reference_asset_ids: refs }
          }),
        }
        const projectResponse = (await updateCreativeProject(selectedProject.id, { outline: nextOutline })) as CreativeProjectResponse
        await refreshSelected(projectResponse.data || selectedProject)
        await loadProjectAssets(selectedProject.id)
      } else {
        await refreshSelected(selectedProject)
      }
      message.success(nodeId ? '角色立绘已生成并关联到项目参考卡' : '角色立绘已生成')
    } catch (error: any) {
      message.error(error?.message || '生成角色立绘失败')
    } finally {
      setPortraitGeneratingCharacter(null)
      setLoadingAction(null)
    }
  }

  async function handleGenerateOutline() {
    if (!selectedProject) return
    setLoadingAction('outline')
    try {
      const response = (await generateCreativeProjectOutline(selectedProject.id, {
        idea,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.outline || undefined,
      })) as CreativeProjectGenerateResponse
      message.success('故事大纲已生成')
      await refreshSelected(response.project || null)
    } catch (error: any) {
      message.error(error?.message || '故事大纲生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleSaveOutline(nextOutline: StoryOutline) {
    if (!selectedProject) return
    setLoadingAction('outline_save')
    try {
      const response = (await updateCreativeProject(selectedProject.id, { outline: nextOutline })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
      message.success('故事大纲已保存')
    } catch (error: any) {
      message.error(error?.message || '保存故事大纲失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleSaveChapterPlan(nextChapterPlan: ChapterPlan) {
    if (!selectedProject) return
    setLoadingAction('chapter_plan_save')
    try {
      const response = (await updateCreativeProject(selectedProject.id, {
        chapter_plan: normalizeChapterPlan(nextChapterPlan),
      })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
      message.success('章节规划已保存')
    } catch (error: any) {
      message.error(error?.message || '保存章节规划失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleSaveProjectGraph(nextGraph: ProjectGraphState) {
    if (!selectedProject) return
    setLoadingAction('canvas_save')
    try {
      const payload = {
        ...nextGraph,
        updated_at: new Date().toISOString(),
      }
      const response = await saveCreativeProjectCanvas(selectedProject.id, payload)
      setProjectGraph(response?.data || payload)
      message.success('关系图谱布局已保存')
    } catch (error: any) {
      message.error(error?.message || '保存关系图谱布局失败')
    } finally {
      setLoadingAction(null)
    }
  }

  function handleOpenGraphNode(node: ProjectGraphNode) {
    const source = node.source || {}
    if (source.chapterNumber) {
      openChapterStudio(Number(source.chapterNumber), source.tab || 'episode-workbench')
      return
    }
    if (node.type === 'asset' && source.assetId) {
      openWorkspaceTab('assets', 'overview')
      return
    }
    if (source.tab) openWorkspaceTab(source.tab)
  }

  async function handleToggleGraphNodeLock(node: ProjectGraphNode) {
    if (node.type === 'content' && node.source?.contentId) {
      const nextLocked = node.status !== 'locked'
      await handleSaveContent(node.source.contentId, { is_locked: nextLocked })
      return
    }
    if (node.type === 'chapter' && node.source?.chapterNumber) {
      const nextChapters = chapters.map((chapter: ChapterPlanItem) => {
        if (Number(chapter.chapter_number) !== Number(node.source?.chapterNumber)) return chapter
        const nextLocked = !isChapterLocked(chapter)
        return { ...chapter, status: nextLocked ? 'locked' : 'draft' }
      })
      await handleSaveChapterPlan({ ...chapterPlan, chapter_count: nextChapters.length, chapters: nextChapters })
    }
  }

  async function handleRegenerateGraphNode(node: ProjectGraphNode) {
    const chapterNumber = Number(node.source?.chapterNumber || 0)
    const contentType = node.source?.contentType
    if (node.type === 'outline') {
      await handleGenerateOutline()
      return
    }
    if (node.type === 'chapter') {
      await handleGenerateChapterPlan({ preserveLocked: true })
      return
    }
    if (!chapterNumber) {
      message.warning('这个节点暂不支持直接再生成')
      return
    }
    if (contentType === 'chapter_outline') await handleGenerateChapterOutline(chapterNumber)
    else if (contentType === 'novel_body') await handleGenerateNovelBody(chapterNumber)
    else if (contentType === 'script') await handleGenerateScript(chapterNumber)
    else if (contentType === 'storyboard') await handleGenerateStoryboardForChapter(chapterNumber)
    else if (contentType === 'comic_pages') await handleSplitComicPages(chapterNumber)
    else message.warning('这个节点暂不支持直接再生成')
  }

  function handleSendGraphNodeToCanvas(node: ProjectGraphNode) {
    if (!selectedProject) return
    enqueueCanvasImport([
      {
        id: `graph-import-${node.id}-${Date.now()}`,
        projectId: selectedProject.id,
        sourceNodeId: node.id,
        createdAt: new Date().toISOString(),
        node: graphNodeToCanvasNode(node, selectedProject),
      },
    ])
    message.success('已发送到创作画布')
    navigate('/canvas')
  }

  async function handleGenerateChapterPlan(options: { preserveLocked?: boolean } = {}) {
    if (!selectedProject) return
    setLoadingAction('chapter_plan')
    try {
      const response = (await generateCreativeProjectChapterPlan(selectedProject.id, {
        chapter_count: chapterCount,
        append_existing: Boolean(options.preserveLocked),
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_plan || undefined,
      })) as CreativeProjectGenerateResponse
      await refreshSelected(response.project || null)
      if (options.preserveLocked) {
        const appended = Array.isArray(response.data?.appended_chapter_numbers)
          ? response.data.appended_chapter_numbers.length
          : 0
        message.success(appended ? `已保留现有规划，并续写 ${appended} 章` : '现有章节规划已保留，无需补充')
      } else {
        message.success('章节规划已生成')
      }
    } catch (error: any) {
      message.error(error?.message || '章节规划生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleRunPipeline(options: { retryFailed?: boolean } = {}) {
    if (!selectedProject) return
    const retryFailedRows = options.retryFailed ? getPipelineFailedRows(pipelineResult) : []
    const retryStages = Array.from(
      new Set(retryFailedRows.map((item) => item.stage).filter(isPipelineStageValue)),
    )
    const retryChapters = Array.from(
      new Set(
        retryFailedRows
          .map((item) => Number(item.chapter_number || 0))
          .filter((chapter) => Number.isFinite(chapter) && chapter > 0),
      ),
    ).sort((a, b) => a - b)
    const effectiveStages = options.retryFailed ? retryStages : pipelineStages
    const effectiveSkipExisting = options.retryFailed ? true : pipelineSkipExisting
    const effectiveContinueOnError = options.retryFailed ? true : pipelineContinueOnError

    if (options.retryFailed && !retryFailedRows.length) {
      message.info('本次批量生产没有失败步骤')
      return
    }
    if (!effectiveStages.length) {
      message.warning('请至少选择一个生产阶段')
      return
    }
    const parsedChapters = parseChapterRange(pipelineChapters)
    const effectiveChapters = options.retryFailed ? retryChapters : parsedChapters
    if (!effectiveChapters.length && !effectiveStages.some((stage) => ['outline', 'sync_characters', 'chapter_plan'].includes(stage))) {
      message.warning('请填写章节范围，例如 1、1-3 或 1,3,5')
      return
    }

    setLoadingAction('pipeline')
    setPipelineRunStatus('running')
    if (!options.retryFailed) {
      setPipelineResult(null)
    }
    try {
      const response = (await runCreativeProjectPipeline(selectedProject.id, {
        stages: effectiveStages,
        chapters: effectiveChapters.length ? effectiveChapters : undefined,
        chapter_count: effectiveChapters.length ? undefined : chapterCount,
        page_count: comicPageCount,
        visual_style: comicStyle || undefined,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        skip_existing: effectiveSkipExisting,
        continue_on_error: effectiveContinueOnError,
        match_source_type: 'storyboard',
      })) as CreativeProjectGenerateResponse<PipelineResult>

      const result = response.data || null
      setPipelineResult(result)
      const { generated, skipped, failed } = getPipelineSummary(result)
      setPipelineRunStatus(failed > 0 ? (generated > 0 || skipped > 0 ? 'partial' : 'failed') : 'success')
      message.success(`${options.retryFailed ? '失败步骤重试' : '批量生产'}完成：生成 ${generated}，跳过 ${skipped}，失败 ${failed}`)
      if (response.project) {
        await refreshSelected(response.project)
      } else {
        await refreshSelected(selectedProject)
      }
      await loadContents(selectedProject.id)
      await loadProjectAssets(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      setPipelineRunStatus('failed')
      message.error(error?.message || '批量生产失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleAgentAdvanceProject() {
    if (!selectedProject) return
    const parsedChapters = parseChapterRange(pipelineChapters)
    const targetChapters = parsedChapters.length ? parsedChapters : [activeChapterNumber]
    const selectedStageLabels = pipelineStages.map((stage) => pipelineStageLabels[stage] || stage)
    setLoadingAction('agent_advance')
    try {
      const response = await agentChat({
        profile_id: 'creative-director',
        message: [
          `请作为创作导演推进创作项目《${selectedProject.title}》。`,
          `优先检查并推进章节：${targetChapters.join('、')}。`,
          `当前勾选的生产阶段：${selectedStageLabels.join('、') || '未选择'}。`,
          '请先读取项目上下文，判断缺口，再在授权工具范围内调用创作项目工具；如果需要高风险或消耗型工具，请生成待确认步骤。',
          '输出时给出：已完成动作、发现的问题、下一步建议，以及涉及的项目/章节/素材对象。',
        ].join('\n'),
        context: {
          source_page: 'creative_project',
          action: 'advance_project',
          project_id: selectedProject.id,
          creative_project_id: selectedProject.id,
          project_title: selectedProject.title,
          current_stage: selectedProject.current_stage,
          active_chapter_number: activeChapterNumber,
          target_chapters: targetChapters,
          pipeline_stages: pipelineStages,
          pipeline_stage_labels: selectedStageLabels,
          chapter_count: chapterCount,
          page_count: comicPageCount,
          visual_style: comicStyle,
          provider: selectedLlm || undefined,
          model: selectedModel || undefined,
          default_image_model: defaultImageModel,
          skip_existing: pipelineSkipExisting,
          continue_on_error: pipelineContinueOnError,
        },
      })
      const runId = response?.run_id || ''
      Modal.success({
        title: '已创建智能体推进任务',
        content: runId
          ? `Run ${runId} 已创建，可以到智能体工作室查看执行轨迹、确认高风险步骤或继续委派子任务。`
          : '已发送给创作导演，可以到智能体工作室查看执行结果。',
        okText: '去智能体工作室',
        onOk: () => navigate('/agent'),
      })
    } catch (error: any) {
      message.error(error?.message || '创建智能体推进任务失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleGenerateChapterOutline(chapterNumber: number) {
    if (!selectedProject) return
    if (!(await ensureWritingPreflight(chapterNumber, 'chapter_outline'))) return
    setLoadingAction('chapter_outline')
    setLoadingChapterAction({ action: 'chapter_outline', chapterNumber })
    try {
      await generateCreativeProjectChapterOutline(selectedProject.id, {
        chapter_number: chapterNumber,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_outline || undefined,
      })
      message.success(`第 ${chapterNumber} 章细纲已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '细纲生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleRegenerateChapterOutlineScenes(chapterNumber: number) {
    if (!selectedProject) return
    const chapterOutline = contentForChapter('chapter_outline', chapterNumber)
    if (!chapterOutline) {
      message.warning('请先生成这一话的细纲')
      return
    }
    setLoadingAction('chapter_outline_scenes')
    setLoadingChapterAction({ action: 'chapter_outline_scenes', chapterNumber })
    try {
      await regenerateCreativeProjectChapterOutlineScenes(selectedProject.id, {
        content_id: chapterOutline.id,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_outline || undefined,
      })
      message.success(`第 ${chapterNumber} 话场景已重生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '场景重生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleGenerateNovelBody(chapterNumber: number) {
    if (!selectedProject) return
    if (!contentForChapter('chapter_outline', chapterNumber)) {
      message.warning('请先生成这一章的细纲')
      return
    }
    if (!(await ensureWritingPreflight(chapterNumber, 'novel_body'))) return
    setLoadingAction('novel_body')
    setLoadingChapterAction({ action: 'novel_body', chapterNumber })
    try {
      await generateCreativeProjectNovelBody(selectedProject.id, {
        chapter_number: chapterNumber,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.novel_body || undefined,
      })
      message.success(`第 ${chapterNumber} 章正文已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '正文生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleRefineNovelBody(chapterNumber: number, instruction: string) {
    if (!selectedProject) return
    const novelBody = contentForChapter('novel_body', chapterNumber)
    if (!novelBody) {
      message.warning('请先生成这一话的正文')
      return
    }
    if (!instruction.trim()) {
      message.warning('请填写正文修改要求')
      return
    }
    if (!(await ensureWritingPreflight(chapterNumber, 'novel_body_refine', novelBody.id))) return
    setLoadingAction('novel_body_refine')
    setLoadingChapterAction({ action: 'novel_body_refine', chapterNumber })
    try {
      await refineCreativeProjectNovelBody(selectedProject.id, {
        content_id: novelBody.id,
        instruction: instruction.trim(),
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.novel_body || undefined,
      })
      message.success(`第 ${chapterNumber} 话正文已按要求微调`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '正文微调失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleSplitComicPages(chapterNumber: number) {
    if (!selectedProject) return
    const storyboard = contentForChapter('storyboard', chapterNumber)
    if (!storyboard) {
      message.warning('请先生成这一章的分镜')
      return
    }
    setLoadingAction('comic_pages')
    setLoadingChapterAction({ action: 'comic_pages', chapterNumber })
    try {
      await splitCreativeProjectComicPages(selectedProject.id, {
        chapter_number: chapterNumber,
        content_id: storyboard.id,
        page_count: comicPageCount,
        visual_style: comicStyle || undefined,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.comic_pages || undefined,
      })
      message.success(`第 ${chapterNumber} 章漫画拆页已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '漫画拆页失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleGenerateStoryboardForChapter(chapterNumber: number) {
    const script = contentForChapter('script', chapterNumber)
    if (!script) {
      message.warning('请先生成这一章的脚本')
      return
    }
    await handleGenerateStoryboard(script.id)
  }

  async function handleGenerateScript(chapterNumber: number) {
    if (!selectedProject) return
    setLoadingAction('script')
    setLoadingChapterAction({ action: 'script', chapterNumber })
    try {
      await generateCreativeProjectScript(selectedProject.id, {
        chapter_number: chapterNumber,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.script || undefined,
      })
      message.success(`第 ${chapterNumber} 章脚本已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '脚本生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleGenerateStoryboard(contentId: string) {
    if (!selectedProject) return
    const source = contents.find((item) => item.id === contentId)
    const chapterNumber = source?.chapter_number || source?.episode_number || null
    setLoadingAction('storyboard')
    setLoadingChapterAction({ action: 'storyboard', chapterNumber })
    try {
      await generateCreativeProjectStoryboard(selectedProject.id, {
        content_id: contentId,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.storyboard || undefined,
      })
      message.success('分镜草稿已生成')
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '分镜生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleMatchReferenceAssets(contentId: string) {
    if (!selectedProject) return
    const source = contents.find((item) => item.id === contentId)
    const chapterNumber = source?.chapter_number || source?.episode_number || activeChapterNumber
    setLoadingAction('reference_match')
    setLoadingChapterAction({ action: null, chapterNumber })
    try {
      await matchCreativeProjectReferenceAssets(selectedProject.id, {
        content_id: contentId,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
      })
      message.success('参考卡已匹配并写回')
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '参考卡匹配失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  async function handleRunWriterRoomStep(
    step: string,
    chapterNumber: number,
    contentId?: string,
    instruction?: string,
    selectedText?: string,
  ) {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      await runCreativeProjectWriterRoomStep(selectedProject.id, step, {
        chapter_number: chapterNumber,
        content_id: contentId,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates[step] || undefined,
        instruction: instruction?.trim() || undefined,
        selected_text: selectedText?.trim() || undefined,
        rehearsal_mode: rehearsalMode,
      })
      message.success('写作室步骤已完成')
      await Promise.all([loadContents(selectedProject.id), loadWriterRoomContents(selectedProject.id, chapterNumber)])
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '写作室步骤失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleRunWriterRoomBatch(chapterNumber: number, steps?: string[], contentId?: string) {
    if (!selectedProject) return
    const runSteps = steps?.length
      ? steps
      : ['scene_beats', 'character_rehearsal', 'prose_draft', 'prose_humanized', 'prose_review']
    if (!runSteps.length) {
      message.warning('请至少选择一个写作室步骤')
      return
    }
    setLoadingAction('writer_room')
    let sourceContentId = contentId
    let succeeded = 0
    let failed = 0
    let blockedBy: string | null = null
    try {
      // Run steps one request at a time so each success lands in the panel as
      // soon as it finishes.  The writer room is a linear candidate chain: when
      // a step fails, its downstream steps would only be able to fall back to a
      // stale candidate, so we stop the run instead of continuing with old data.
      for (const step of runSteps) {
        const stepLabel = writerRoomStepLabelMap[step] || step
        try {
          const response = await runCreativeProjectWriterRoomStep(selectedProject.id, step, {
            chapter_number: chapterNumber,
            content_id: sourceContentId,
            provider: selectedLlm || undefined,
            model: selectedModel || undefined,
            template_id: selectedPromptTemplates[step] || undefined,
            rehearsal_mode: rehearsalMode,
          })
          const content = response?.data
          if (content?.id) {
            sourceContentId = content.id
            succeeded += 1
            setWriterRoomContents((current) => {
              const byId = new Map(current.map((item) => [item.id, item]))
              byId.set(content.id, content)
              return Array.from(byId.values())
            })
            message.success(`「${stepLabel}」已完成`)
          } else {
            failed += 1
            blockedBy = stepLabel
            message.error(`「${stepLabel}」未返回结果`)
            break
          }
        } catch (error: any) {
          failed += 1
          blockedBy = stepLabel
          message.error(`「${stepLabel}」失败：${error?.message || '未知错误'}`)
          break
        }
      }
      if (blockedBy) {
        message.warning(`写作室已停止：成功 ${succeeded}，失败 ${failed}；「${blockedBy}」失败后，后续阶段不再使用旧候选继续。`)
      } else if (failed) {
        message.warning(`写作室批量结束：成功 ${succeeded}，失败 ${failed}`)
      } else {
        message.success(`写作室批量完成：成功 ${succeeded}`)
      }
    } finally {
      void loadWriterRoomContents(selectedProject.id, chapterNumber)
      void loadContents(selectedProject.id)
      void loadGenerationLogs(selectedProject.id)
      setLoadingAction(null)
    }
  }

  async function handlePromoteWriterRoomContent(contentId: string) {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      await promoteCreativeProjectWriterRoomContent(selectedProject.id, contentId)
      message.success('已提升为正文最新版本')
      await Promise.all([loadContents(selectedProject.id), loadWriterRoomContents(selectedProject.id, activeChapterNumber)])
      await loadGenerationLogs(selectedProject.id)
      await refreshSelected(selectedProject)
    } catch (error: any) {
      message.error(error?.message || '提升正文失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleResolveContinuityCandidate(candidateId: string, action: 'accept' | 'ignore') {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      await resolveCreativeProjectContinuityCandidate(selectedProject.id, candidateId, action)
      message.success(action === 'accept' ? '已锁定为项目事实' : '已忽略该候选')
      await Promise.all([loadContents(selectedProject.id), loadContinuityFacts(selectedProject.id)])
    } catch (error: any) {
      message.error(error?.message || '处理连续性候选失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleRewriteParagraph(
    contentId: string,
    paragraphIndex: number,
    instruction: string,
  ) {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      const response = await rewriteCreativeProjectParagraph(selectedProject.id, contentId, {
        paragraph_index: paragraphIndex,
        instruction,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
      })
      if (response?.data?.anchor_not_found) {
        message.warning('没有找到这个段落锚点，请重新选择段落')
      } else {
        message.success('已生成段落重写候选版本')
      }
      await Promise.all([loadContents(selectedProject.id), loadGenerationLogs(selectedProject.id)])
    } catch (error: any) {
      message.error(error?.message || '段落重写失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleSaveContentAsAsset(contentId: string) {
    if (!selectedProject) return
    setLoadingAction('asset')
    try {
      const response = await saveCreativeProjectContentAsAsset(selectedProject.id, contentId)
      message.success(response?.created_node ? '已保存为文本素材' : '已新增文本素材版本')
      await loadProjectAssets(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '保存文本素材失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleExtractContinuity(contentId: string) {
    if (!selectedProject) return
    setLoadingAction('project_bible')
    try {
      const response = await extractCreativeProjectContinuity(selectedProject.id, contentId)
      const count = response?.data?.length || 0
      message.success(count ? `已提取 ${count} 条连续性候选卡` : '连续性候选卡已存在')
      await loadContents(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '提取连续性候选失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleOpenPrevis(storyboardContentId: string, panelNumber: number, title?: string) {
    if (!selectedProject) return
    try {
      const scene = await getOrCreatePrevisScene({
        projectId: selectedProject.id,
        storyboardContentId,
        panelNumber,
        title,
      })
      navigate(`/previs?scene_id=${encodeURIComponent(scene.id)}`)
    } catch (error: any) {
      message.error(error?.message || '打开 3D 预演失败')
    }
  }

  function handleOpenVideoGeneration(prompt: string, context: VideoGenerationContext = {}) {
    if (!selectedProject) return
    const params = new URLSearchParams({
      prompt: prompt.trim(),
      project_id: selectedProject.id,
      content_id: context.contentId || '',
      chapter_number: String(context.chapterNumber ?? activeChapterNumber),
      source_index: context.sourceIndex !== undefined ? String(context.sourceIndex) : '',
      source_type: context.sourceType || 'storyboard_panel',
      source_title: context.sourceTitle || '',
      aspect_ratio: '9:16',
      duration: String(normalizeStoryboardVideoDuration(context.durationSeconds)),
      generate_audio: context.generateAudio ? 'true' : 'false',
    })
    const referenceAssetIds = dedupeStrings([
      ...(context.referenceAssetIds || []),
      ...(context.portraitNodeIds || []),
    ])
    if (referenceAssetIds.length) params.set('reference_asset_ids', referenceAssetIds.join(','))
    if (context.musicHint?.trim()) params.set('music_hint', context.musicHint.trim())
    navigate(`/video-gen?${params.toString()}`)
  }

  async function handleBatchGenerateStoryboardImages(chapterNumber: number) {
    const storyboard = contentForChapter('storyboard', chapterNumber)
    if (!storyboard) {
      message.warning('请先生成这一章的分镜')
      return
    }
    if (!defaultImageModel.name) {
      message.warning('请先在顶部选择默认生图模型')
      return
    }

    const panels = (storyboard.data?.panels || []).filter((panel: any) => panel?.image_prompt)
    if (!panels.length) {
      message.warning('当前分镜没有可用的生图提示词')
      return
    }
    const pendingPanels = panels.filter((panel: any) => {
      const key = imageContextKey({
        contentId: storyboard.id,
        sourceType: 'storyboard_panel',
        sourceIndex: panel.panel_number,
        chapterNumber,
      })
      return !inlineImages[key]
    })
    if (!pendingPanels.length) {
      message.success('本话分镜图都已经生成过了')
      return
    }
    const plannedCharacterIds = dedupeStrings(
      panels.flatMap((panel: any) => [
        ...(panel.character_ids || []),
        ...selectReferenceAssetsForPrompt(
          projectAssets,
          [panel.image_prompt, panel.action, panel.location].filter(Boolean).join('\n'),
          4,
        ).map(
          (asset) => asset.metadata?.character_id,
        ),
      ]),
    )
    const loadedCharacters = await loadCharacterDetailsForIds(plannedCharacterIds)
    const referencePlans = panels.map((panel: any) =>
      buildStoryboardPanelReferencePlan({
        panel,
        projectAssets,
        characterDetails: loadedCharacters,
        supportsReferenceImages: defaultImageSupportsReferenceImages,
      }),
    )
    const referenceSummary = buildStoryboardReferenceSummary(referencePlans, 0, defaultImageSupportsReferenceImages)
    if (referenceSummary.missingEffectivePlanPanels) {
      message.warning(`有 ${referenceSummary.missingEffectivePlanPanels} 个分镜没有角色/参考卡规划，可先点“匹配参考卡”提升一致性`)
    }
    if (referenceSummary.noUsableReferencePanels) {
      message.warning(`有 ${referenceSummary.noUsableReferencePanels} 个分镜暂时没有可发送参考图，可先补角色基准图或项目参考卡`)
    }
    if (referenceSummary.unresolvedCharacterIds.length) {
      message.warning(`有 ${referenceSummary.unresolvedCharacterIds.length} 个角色资料未加载成功，本次会继续生成但参考图可能不完整`)
    }
    if (!defaultImageSupportsReferenceImages) {
      message.info('当前默认生图模型未声明支持参考图，本次会保留参考卡 lineage，但不会上传参考图图片')
    } else if (referenceSummary.sentReferenceImages) {
      message.info(`本次批量生成最多会随分镜发送 ${referenceSummary.sentReferenceImages} 张参考图`)
    }

    const confirmed = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '确认批量生图',
        content: `将使用「${defaultImageModel.name}」提交 ${pendingPanels.length} 个分镜任务，最多携带 ${referenceSummary.sentReferenceImages} 张参考图。${defaultImageSupportsReferenceImages ? '' : '当前模型不会上传参考图。'}`,
        okText: '开始生成',
        cancelText: '返回检查',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!confirmed) return

    setBatchStoryboardImageChapter(chapterNumber)
    try {
      let generated = 0
      for (const panel of panels) {
        const key = imageContextKey({
          contentId: storyboard.id,
          sourceType: 'storyboard_panel',
          sourceIndex: panel.panel_number,
          chapterNumber,
        })
        if (inlineImages[key]) continue
        const completed = await handleInlineGenerateImage(panel.image_prompt, {
          contentId: storyboard.id,
          sourceType: 'storyboard_panel',
          sourceIndex: panel.panel_number,
          sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
          chapterNumber,
          referenceAssetIds: panel.reference_asset_ids || [],
          characterIds: panel.character_ids || [],
          portraitNodeIds: panel.portrait_node_ids || [],
          portraitVersionIds: panel.portrait_version_ids || [],
        }, { awaitAsync: true })
        if (completed) generated += 1
      }
      message.success(generated ? `已批量生成 ${generated} 张分镜图` : '本话分镜图都已经生成过了')
    } finally {
      setBatchStoryboardImageChapter(null)
    }
  }

  const chapterColumns = [
    {
      title: '章',
      dataIndex: 'chapter_number',
      width: 64,
    },
    {
      title: '标题',
      dataIndex: 'title',
      width: 220,
      render: (value: string) => <Text strong>{value || '未命名'}</Text>,
    },
    {
      title: '目标 / 冲突',
      render: (_: unknown, record: ChapterPlanItem) => (
        <Space direction="vertical" size={2}>
          <Text>{record.goal || '未填写目标'}</Text>
          <Text type="secondary">{record.conflict || '未填写冲突'}</Text>
        </Space>
      ),
    },
    {
      title: '焦点角色',
      dataIndex: 'character_focus',
      width: 180,
      render: (items: string[] = []) => (
        <Space size={[4, 4]} wrap>
          {items.slice(0, 3).map((name) => (
            <Tag key={name}>{name}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '产物',
      width: 230,
      render: (_: unknown, record: ChapterPlanItem) => {
        const chapterNumber = record.chapter_number
        const items = [
          { key: 'chapter_outline', label: '细纲', value: contentForChapter('chapter_outline', chapterNumber) },
          { key: 'novel_body', label: '正文', value: contentForChapter('novel_body', chapterNumber) },
          { key: 'script', label: '脚本', value: contentForChapter('script', chapterNumber) },
          { key: 'storyboard', label: '分镜', value: contentForChapter('storyboard', chapterNumber) },
          { key: 'comic_pages', label: '漫画', value: contentForChapter('comic_pages', chapterNumber) },
        ]
        return (
          <Space size={[4, 4]} wrap>
            {items.map((item) => (
              <Tag key={item.key} color={item.value ? 'green' : 'default'}>
                {item.label}{item.value ? ` v${item.value.version}` : ''}
              </Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '动作',
      width: 280,
      render: (_: unknown, record: ChapterPlanItem) => {
        const chapterNumber = record.chapter_number
        const hasChapterOutline = Boolean(contentForChapter('chapter_outline', chapterNumber))
        const hasScript = Boolean(contentForChapter('script', chapterNumber))
        const hasStoryboard = Boolean(contentForChapter('storyboard', chapterNumber))
        return (
          <Space size={6} wrap>
            <Button
              size="small"
              icon={<BranchesOutlined />}
              loading={isChapterActionLoading('chapter_outline', chapterNumber)}
              onClick={() => handleGenerateChapterOutline(chapterNumber)}
            >
              细纲
            </Button>
            <Tooltip title={hasChapterOutline ? '' : '先生成细纲，再生成正文'}>
              <Button
                size="small"
                icon={<FileTextOutlined />}
                disabled={!hasChapterOutline}
                loading={isChapterActionLoading('novel_body', chapterNumber)}
                onClick={() => handleGenerateNovelBody(chapterNumber)}
              >
                正文
              </Button>
            </Tooltip>
            <Button
              size="small"
              icon={<FileTextOutlined />}
              loading={isChapterActionLoading('script', chapterNumber)}
              onClick={() => handleGenerateScript(chapterNumber)}
            >
              脚本
            </Button>
            <Tooltip title={hasScript ? '' : '先生成脚本，再生成分镜'}>
              <Button
                size="small"
                  icon={<PictureOutlined />}
                  disabled={!hasScript}
                  loading={isChapterActionLoading('storyboard', chapterNumber)}
                  onClick={() => handleGenerateStoryboardForChapter(chapterNumber)}
              >
                分镜
              </Button>
            </Tooltip>
            <Tooltip title={hasStoryboard ? '' : '先生成分镜，再生成漫画页'}>
              <Button
                size="small"
                icon={<PictureOutlined />}
                disabled={!hasStoryboard}
                loading={isChapterActionLoading('comic_pages', chapterNumber)}
                onClick={() => handleSplitComicPages(chapterNumber)}
              >
                漫画
              </Button>
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  const characterColumns = [
    {
      title: '角色',
      dataIndex: 'name',
      width: 120,
      render: (value: string, record: StoryOutlineCharacter) => (
        <Space>
          <UserOutlined />
          <Text strong>{value || record.role || '未命名'}</Text>
        </Space>
      ),
    },
    {
      title: '定位',
      dataIndex: 'role',
      width: 120,
    },
    {
      title: '性格 / 目标',
      render: (_: unknown, record: StoryOutlineCharacter) => (
        <Space direction="vertical" size={2}>
          <Text>{record.personality || '未填写性格'}</Text>
          <Text type="secondary">{record.goal || '未填写目标'}</Text>
        </Space>
      ),
    },
    {
      title: '外貌',
      dataIndex: 'appearance',
      ellipsis: true,
    },
    {
      title: '一致性',
      width: 220,
      render: (_: unknown, record: StoryOutlineCharacter) => {
        const visualTags = Array.isArray(record.visual_tags)
          ? record.visual_tags
          : String(record.visual_tags || '').split(/[、，,;\s]+/).filter(Boolean)
        const signatureItems = (record.signature_items?.length ? record.signature_items : visualTags).filter(Boolean)
        return (
          <Space direction="vertical" size={4}>
            <Space size={[4, 4]} wrap>
              {signatureItems.slice(0, 3).map((item) => (
              <Tag key={item} color="cyan">{item}</Tag>
              ))}
              {(record.expressions || []).slice(0, 2).map((item) => (
              <Tag key={item} color="blue">{item}</Tag>
              ))}
              {(record.poses || []).slice(0, 2).map((item) => (
              <Tag key={item} color="purple">{item}</Tag>
              ))}
            </Space>
            {record.visual_consistency ? (
              <Text type="secondary" ellipsis={{ tooltip: record.visual_consistency }}>
                {record.visual_consistency}
              </Text>
            ) : (
              <Text type="secondary">未填写一致性规则</Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '素材 / 提示词',
      width: 180,
      render: (_: unknown, record: StoryOutlineCharacter) => (
        <Space direction="vertical" size={2}>
          {record.character_id ? <Tag color="green">已入库</Tag> : <Tag>未入库</Tag>}
          {record.portrait_asset_id ? (
            <Text copyable ellipsis style={{ maxWidth: 150 }}>
              {record.portrait_asset_id}
            </Text>
          ) : (
            <Text type="secondary">未绑定立绘</Text>
          )}
          {record.image_prompt ? (
            <Text type="secondary" ellipsis={{ tooltip: record.image_prompt }}>
              有角色图提示词
            </Text>
          ) : null}
          <Button
            size="small"
            icon={<PictureOutlined />}
            disabled={!record.character_id || !defaultImageModel.name}
            loading={portraitGeneratingCharacter === (record.character_id || record.name)}
            onClick={() => handleGenerateCharacterPortrait(record)}
          >
            {record.portrait_asset_id ? '重生立绘' : '生成立绘'}
          </Button>
        </Space>
      ),
    },
  ]

  const workspaceErrorEntries = Object.entries(workspaceErrors)
  const overviewDetailLabels: Record<string, string> = {
    outline: '故事蓝图',
    'project-bible': '项目圣经与世界设定',
    chapters: '全书章节规划',
    canvas: '项目关系图谱',
    'narrative-graph': '叙事图谱',
    assets: '角色与项目素材',
    logs: '生成与任务日志',
    json: '高级 JSON 数据',
  }
  const overviewDetailLabel = overviewDetailLabels[activeWorkspaceTab] || '项目详情'

  return (
    <div ref={storyPageRef} className="story-theme-page story-production-desk" style={{ padding: '18px 24px 24px', maxWidth: 2400, width: '100%', margin: '0 auto', color: theme.textPrimary }}>
      <header
        style={{
          display: 'grid',
          gridTemplateColumns: cockpitCompact ? 'minmax(0, 1fr)' : 'minmax(220px, 1fr) minmax(0, auto)',
          alignItems: 'center',
          gap: '10px 20px',
          marginBottom: 14,
          paddingBottom: 14,
          borderBottom: `1px solid ${theme.borderLight}`,
        }}
      >
        <div style={{ minWidth: 220 }}>
          <Text strong style={{ fontSize: 16 }}>项目制作台</Text>
          <Text type="secondary" style={{ display: 'block', marginTop: 2 }}>从故事设定到可追溯的内容与素材产出</Text>
          {selectedProject ? (
            <Segmented
              size="small"
              value={workspaceMode}
              style={{ marginTop: 10 }}
              options={[
                { label: '项目总览', value: 'overview' },
                { label: '单章工作室', value: 'chapter' },
              ]}
              onChange={(value) => {
                const nextMode = value as 'overview' | 'chapter'
                setWorkspaceMode(nextMode)
                if (nextMode === 'overview') setOverviewDetailOpen(false)
                if (nextMode === 'chapter' && !['episode-workbench', 'writer-room', 'script'].includes(activeWorkspaceTab)) {
                  setActiveWorkspaceTab('episode-workbench')
                }
                if (nextMode === 'overview' && ['episode-workbench', 'writer-room', 'script'].includes(activeWorkspaceTab)) {
                  setActiveWorkspaceTab('outline')
                }
              }}
            />
          ) : null}
        </div>
        <Space wrap size={[8, 8]} style={{ justifyContent: cockpitCompact ? 'flex-start' : 'flex-end', minWidth: 0 }}>
          {runtimeSettingsOpen ? <>
            <Select
            placeholder="文本模型"
            value={selectedLlm || undefined}
            style={{ width: 190 }}
            options={llmConnectors.map((item) => ({
              label: `${item.name}${item.is_default ? '（默认）' : ''}`,
              value: item.name,
            }))}
            onChange={(value) => {
              const connector = llmConnectors.find((item) => item.name === value)
              setSelectedLlm(value)
              setSelectedModel(connector?.default_model || '')
            }}
          />
            <Select
            placeholder="模型"
            value={selectedModel || undefined}
            style={{ width: 210 }}
            options={modelOptions}
            onChange={setSelectedModel}
            disabled={!selectedLlm}
          />
            <Select
            allowClear
            showSearch
            placeholder="默认生图模型"
            value={defaultImageModel.name || undefined}
            style={{ width: 230 }}
            options={imageModelOptions}
            loading={savingImageModel}
            onChange={handleDefaultImageModelChange}
            optionFilterProp="label"
              disabled={!selectedProject}
            />
            <Button type="text" size="small" onClick={() => setRuntimeSettingsOpen(false)}>收起设置</Button>
          </> : (
            <Button icon={<EditOutlined />} onClick={() => setRuntimeSettingsOpen(true)}>
              运行设置
            </Button>
          )}
          <Tooltip title="提示词与平台模板">
            <Button icon={<FileTextOutlined />} onClick={() => navigate('/platform-templates?scope=creative_project')}>
              模板
            </Button>
          </Tooltip>
          <Tooltip title="刷新项目数据">
            <Button aria-label="刷新项目数据" icon={<ReloadOutlined />} onClick={() => loadProjects(selectedId)} />
          </Tooltip>
          {selectedProject ? (
            <Tooltip title={inspectorOpen ? '关闭上下文检查器' : '打开上下文检查器'}>
              <Button
                type={inspectorOpen ? 'default' : 'text'}
                aria-label={inspectorOpen ? '关闭上下文检查器' : '打开上下文检查器'}
                icon={<EyeOutlined />}
                onClick={() => setInspectorOpen((open) => !open)}
              />
            </Tooltip>
          ) : null}
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建项目</Button>
        </Space>
      </header>

      {workspaceErrorEntries.length > 0 ? (
        <Alert
          type="error"
          showIcon
          message="项目工作台有数据加载失败"
          description={workspaceErrorEntries.map(([key, value]) => `${key}: ${value}`).join('；')}
          action={<Button size="small" onClick={retryWorkspaceLoads}>重试</Button>}
          style={{ marginBottom: 16 }}
        />
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: workspaceNarrow
            ? 'minmax(0, 1fr)'
            : projectLibraryCollapsed
            ? cockpitCompact ? '48px 0 minmax(0, 1fr)' : '48px 0 minmax(0, 1fr) minmax(236px, 280px)'
            : cockpitCompact
              ? `${projectLibraryWidth}px 10px minmax(0, 1fr)`
              : `${projectLibraryWidth}px 10px minmax(0, 1fr) minmax(236px, 280px)`,
          gap: workspaceNarrow ? 12 : projectLibraryCollapsed ? 6 : 8,
          alignItems: 'start',
        }}
      >
        <section
          style={{
            border: `1px solid ${theme.borderLight}`,
            borderRadius: 8,
            background: theme.bgCard,
            overflow: 'hidden',
            minHeight: projectLibraryCollapsed ? 620 : undefined,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              padding: projectLibraryCollapsed ? '12px 8px' : '14px 16px',
              borderBottom: projectLibraryCollapsed ? 'none' : `1px solid ${theme.border}`,
            }}
          >
            {projectLibraryCollapsed ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                <Tooltip title="展开项目库">
                  <Button
                    type="text"
                    aria-label="展开项目库"
                    icon={<MenuUnfoldOutlined />}
                    onClick={() => setProjectLibraryCollapsed(false)}
                    style={{ color: theme.textPrimary }}
                  />
                </Tooltip>
                <Badge count={projects.length} showZero color="#1677ff">
                  <FolderOpenOutlined style={{ color: theme.textSecondary }} />
                </Badge>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%' }}>
                <Space size={8} style={{ minWidth: 0 }}>
                  <FolderOpenOutlined />
                  <Text strong>项目库</Text>
                  <Badge count={projects.length} showZero color="#1677ff" />
                </Space>
                <Tooltip title="折叠项目库">
                  <Button
                    type="text"
                    size="small"
                    aria-label="折叠项目库"
                    icon={<MenuFoldOutlined />}
                    onClick={() => setProjectLibraryCollapsed(true)}
                    style={{ color: theme.textSecondary, flex: '0 0 auto' }}
                  />
                </Tooltip>
              </div>
            )}
          </div>
          {!projectLibraryCollapsed && loadingAction === 'projects' && !projects.length ? (
            <div style={{ padding: 16 }}>
              <Skeleton active paragraph={{ rows: 8 }} />
            </div>
          ) : !projectLibraryCollapsed && projects.length ? (
            <List
              style={{ flex: '0 1 320px', minHeight: 0, overflowY: 'auto' }}
              dataSource={projects}
              rowKey="id"
              renderItem={(item, index) => (
                <List.Item
                  onClick={() => setSelectedId(item.id)}
                  style={{
                    cursor: 'pointer',
                    padding: '12px 16px',
                    background: item.id === selectedId ? theme.primaryAlpha(0.12) : theme.bgCard,
                    borderLeft: item.id === selectedId ? `3px solid ${theme.primary}` : '3px solid transparent',
                  }}
                >
                  <List.Item.Meta
                    title={
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong ellipsis style={{ maxWidth: Math.max(96, projectLibraryWidth - 110) }}>
                          {item.title || `项目 ${index + 1}`}
                        </Text>
                        <Tag color={item.status === 'ready' ? 'green' : 'blue'}>
                          {statusLabels[item.status] || item.status}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space size={6} wrap>
                        <Text type="secondary">{stageLabels[item.current_stage] || item.current_stage}</Text>
                        <Text type="secondary">#{projects.length - index}</Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          ) : !projectLibraryCollapsed && projectListError ? (
            <div style={{ padding: 16 }}>
              <Alert
                type="error"
                showIcon
                message="项目列表加载失败"
                description={projectListError}
                action={<Button size="small" onClick={() => loadProjects(selectedId)}>重试</Button>}
              />
            </div>
          ) : !projectLibraryCollapsed ? (
            <div style={{ padding: 24 }}>
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无项目" />
            </div>
          ) : null}
          {!projectLibraryCollapsed && selectedProject && workspaceMode === 'chapter' ? (
            <ChapterRail
              theme={theme}
              chapters={chapters}
              activeChapterNumber={activeChapterNumber}
              contents={contents}
              writerRoomSummary={writerRoomSummary}
              ledger={allForeshadowingLedger}
              health={narrativeHealth}
              onChapterChange={handleActiveChapterChange}
            />
          ) : null}
        </section>

        {workspaceNarrow ? null : projectLibraryCollapsed ? (
          <div />
        ) : (
          <ResizeHandle
            onMouseDown={(event) =>
              startHorizontalResize(event, {
                initial: projectLibraryWidth,
                min: 190,
                max: 360,
                onChange: setProjectLibraryWidth,
              })
            }
          />
        )}

        <main
          style={{
            minHeight: 620,
            border: `1px solid ${theme.borderLight}`,
            borderRadius: 8,
            background: theme.bgCard,
          }}
        >
          {!selectedProject ? (
            <div style={{ padding: 64 }}>
              <Empty description="选择或新建项目" />
            </div>
          ) : (
            <>
              <div className={`story-project-toolbar story-project-toolbar--${workspaceMode}`} style={{ padding: '20px 20px 16px', borderBottom: `1px solid ${theme.border}` }}>
                <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <div>
                      <Space size={10} wrap>
                        <Title level={3} style={{ margin: 0 }}>
                          {selectedProject.title}
                        </Title>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={openRenameModal}
                          loading={loadingAction === 'rename'}
                        >
                          重命名
                        </Button>
                        <Tag color="processing">{projectTypeLabel(selectedProject.project_type)}</Tag>
                        <Tag>{stageLabels[selectedProject.current_stage] || selectedProject.current_stage}</Tag>
                        <Tooltip
                          title={
                            llmAvailable
                              ? '由创作导演自动推进后续步骤'
                              : '请先在设置中配置文本模型'
                          }
                        >
                          <Button
                            type="primary"
                            icon={<RobotOutlined />}
                            onClick={handleAgentAdvanceProject}
                            loading={loadingAction === 'agent_advance'}
                            disabled={!llmAvailable}
                          >
                            智能体推进
                          </Button>
                        </Tooltip>
                        <Button
                          icon={<DownloadOutlined />}
                          href={`/api/v1/creative-projects/${selectedProject.id}/export`}
                        >
                          导出项目
                        </Button>
                      </Space>
                      {idea && (
                        <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: '8px 0 0' }}>
                          {idea}
                        </Paragraph>
                      )}
                    </div>
                    <Space direction="vertical" size={2} align="end">
                      <Text type="secondary">{selectedProjectIndex >= 0 ? `项目 ${projects.length - selectedProjectIndex}` : ''}</Text>
                      <Popconfirm
                        title="删除当前创作项目？"
                        description="只删除项目、内容版本、日志和项目关联，不删除角色库角色或素材库资产。"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true, loading: loadingAction === 'delete_project' }}
                        onConfirm={handleDeleteProject}
                      >
                        <Button type="text" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                      </Popconfirm>
                    </Space>
                  </Space>
                </Space>
              </div>

              {workspaceMode === 'overview' ? (
                <StoryWorkspaceOverview
                  theme={theme}
                  projectTitle={selectedProject.title}
                  projectType={projectTypeLabel(selectedProject.project_type)}
                  currentStage={stageLabels[selectedProject.current_stage] || selectedProject.current_stage}
                  idea={idea}
                  chapters={chapters}
                  stages={productionStages}
                  activeChapterNumber={activeChapterNumber}
                  hasOutline={hasOutline}
                  hasBible={Boolean(projectBibleContents.length || worldAssetContents.length)}
                  hasChapterPlan={hasChapterPlan}
                  assetCount={projectAssets.length}
                  unresolvedContinuityCount={continuityCandidates.filter((item) => item.status === 'pending').length}
                  onOpenSection={(tab) => {
                    const chapterTab = ['episode-workbench', 'writer-room', 'script'].includes(tab)
                    openWorkspaceTab(tab, chapterTab ? 'chapter' : 'overview')
                    setOverviewDetailOpen(!chapterTab)
                  }}
                  onOpenChapter={openChapterStudio}
                  onContinue={() => {
                    if (chapters.length) openChapterStudio(activeChapterNumber)
                    else {
                      openWorkspaceTab(hasOutline ? 'chapters' : 'outline', 'overview')
                      // 展开详情区，让大纲/章节规划编辑器可见（否则无章节时点击无视觉变化）
                      setOverviewDetailOpen(true)
                      if (!hasOutline) {
                        // 有创意则自动生成故事大纲，无创意则引导先填写
                        if (idea) void handleGenerateOutline()
                        else message.info('已打开大纲编辑器，请先填写创意（idea）后再点击「生成故事大纲」')
                      }
                    }
                  }}
                />
              ) : (
                <ProductionStageRail
                  theme={theme}
                  stages={productionStages}
                  activeTab={activeWorkspaceTab}
                  onSelect={openWorkspaceTab}
                />
              )}

              {workspaceMode === 'overview' ? <Collapse
                ghost
                size="small"
                activeKey={pipelineOpen ? ['production'] : []}
                onChange={(keys) => setPipelineOpen(keys.includes('production'))}
                style={{ margin: '0 20px' }}
                items={[
                  {
                    key: 'production',
                    label: <Text strong>批量生产设置</Text>,
                    extra: pipelineRunStatus !== 'idle' ? <Tag color={pipelineRunStatus === 'failed' ? 'red' : pipelineRunStatus === 'partial' ? 'orange' : 'blue'}>{pipelineRunStatus === 'running' ? '运行中' : pipelineRunStatus === 'partial' ? '部分完成' : pipelineRunStatus === 'failed' ? '失败' : '已完成'}</Tag> : <Text type="secondary">按依赖顺序补齐章节</Text>,
                    children: (
                      <PipelinePanel
                        theme={theme}
                        stages={pipelineStages}
                        onStagesChange={setPipelineStages}
                        chapterRange={pipelineChapters}
                        onChapterRangeChange={setPipelineChapters}
                        skipExisting={pipelineSkipExisting}
                        onSkipExistingChange={setPipelineSkipExisting}
                        continueOnError={pipelineContinueOnError}
                        onContinueOnErrorChange={setPipelineContinueOnError}
                        loading={loadingAction === 'pipeline'}
                        result={pipelineResult}
                        runStatus={pipelineRunStatus}
                        onRun={handleRunPipeline}
                        onRetryFailed={() => handleRunPipeline({ retryFailed: true })}
                      />
                    ),
                  },
                ]}
              /> : null}

              {Object.values(workspaceLoading).some(Boolean) ? (
                <Alert
                  type="info"
                  showIcon
                  message="正在加载项目工作台"
                  description="内容、素材、生成日志和关系图谱正在分别同步；已有数据仍可继续查看。"
                  style={{ margin: '16px 20px 0' }}
                />
              ) : null}

              <div className={`story-workspace-detail story-workspace-detail--${workspaceMode}`}>
                {workspaceMode === 'overview' ? (
                  <button
                    type="button"
                    className="story-workspace-detail__toggle"
                    onClick={() => setOverviewDetailOpen((open) => !open)}
                    aria-expanded={overviewDetailOpen}
                  >
                    <span>
                      <Text strong>{overviewDetailLabel}</Text>
                      <Text type="secondary">仅在需要编辑或查看完整资料时展开</Text>
                    </span>
                    <span>{overviewDetailOpen ? '收起' : '展开'}</span>
                  </button>
                ) : null}
                <div hidden={workspaceMode === 'overview' && !overviewDetailOpen}>
              <Tabs
                className={`story-workspace-tabs story-workspace-tabs--${workspaceMode}`}
                style={{ padding: workspaceMode === 'overview' ? '0 22px 22px' : '0 20px 20px' }}
                activeKey={activeWorkspaceTab}
                onChange={openWorkspaceTab}
                items={[
                  {
                    key: 'outline',
                    label: (
                      <Space>
                        <ThunderboltOutlined />
                        大纲
                      </Space>
                    ),
                    children: (
                      <OutlineTab
                        outline={outline}
                        hasOutline={hasOutline}
                        loading={loadingAction === 'outline'}
                        saving={loadingAction === 'outline_save'}
                        syncLoading={loadingAction === 'sync_characters'}
                        llmAvailable={llmAvailable}
                        templateOptions={templateOptionsByStage.outline || []}
                        selectedTemplateId={selectedPromptTemplates.outline}
                        onTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, outline: value }))
                        }
                        onGenerate={handleGenerateOutline}
                        onSave={handleSaveOutline}
                        onSyncCharacters={handleSyncCharacters}
                        characterColumns={characterColumns}
                      />
                    ),
                  },
                  {
                    key: 'project-bible',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        圣经/世界
                      </Space>
                    ),
                    children: (
                      <ProjectBibleTab
                        hasOutline={hasOutline}
                        bibleContents={projectBibleContents}
                        worldAssets={worldAssetContents}
                        loading={loadingAction === 'project_bible'}
                        savingContentId={savingContentId}
                        onSync={handleSyncProjectBible}
                        onSaveContent={handleSaveContent}
                        onSaveAsAsset={handleSaveContentAsAsset}
                      />
                    ),
                  },
                  {
                    key: 'dynamic-state',
                    label: (
                      <Space>
                        <HistoryOutlined />
                        动态状态
                      </Space>
                    ),
                    children: <ProjectStatePanel projectId={selectedProject?.id || ''} />,
                  },
                  {
                    key: 'chapters',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        章节
                      </Space>
                    ),
                    children: (
                      <ChapterTab
                        chapterPlan={chapterPlan}
                        chapters={chapters}
                        hasOutline={hasOutline}
                        hasChapterPlan={hasChapterPlan}
                        chapterColumns={chapterColumns}
                        chapterCount={chapterCount}
                        setChapterCount={setChapterCount}
                        comicPageCount={comicPageCount}
                        setComicPageCount={setComicPageCount}
                        chapterTemplateOptions={templateOptionsByStage.chapter_plan || []}
                        selectedChapterTemplateId={selectedPromptTemplates.chapter_plan}
                        onChapterTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, chapter_plan: value }))
                        }
                        scriptTemplateOptions={templateOptionsByStage.script || []}
                        selectedScriptTemplateId={selectedPromptTemplates.script}
                        onScriptTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, script: value }))
                        }
                        chapterOutlineTemplateOptions={templateOptionsByStage.chapter_outline || []}
                        selectedChapterOutlineTemplateId={selectedPromptTemplates.chapter_outline}
                        onChapterOutlineTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, chapter_outline: value }))
                        }
                        novelBodyTemplateOptions={templateOptionsByStage.novel_body || []}
                        selectedNovelBodyTemplateId={selectedPromptTemplates.novel_body}
                        onNovelBodyTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, novel_body: value }))
                        }
                        comicPagesTemplateOptions={templateOptionsByStage.comic_pages || []}
                        selectedComicPagesTemplateId={selectedPromptTemplates.comic_pages}
                        onComicPagesTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, comic_pages: value }))
                        }
                        loading={loadingAction === 'chapter_plan'}
                        saving={loadingAction === 'chapter_plan_save'}
                        onGenerate={handleGenerateChapterPlan}
                        onSave={handleSaveChapterPlan}
                      />
                    ),
                  },
                  {
                    key: 'episode-workbench',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        单话工作台
                      </Space>
                    ),
                    children: (
                      <EpisodeWorkbenchTab
                        projectId={selectedProject?.id || ''}
                        chapters={chapters}
                        activeChapterNumber={activeChapterNumber}
                        onActiveChapterChange={handleActiveChapterChange}
                        activeChapter={activeChapter}
                        contentForChapter={contentForChapter}
                        isChapterActionLoading={isChapterActionLoading}
                        comicPageCount={comicPageCount}
                        setComicPageCount={setComicPageCount}
                        comicStyle={comicStyle}
                        setComicStyle={setComicStyle}
                        columnWidths={workbenchWidths}
                        setColumnWidths={setWorkbenchWidths}
                        startHorizontalResize={startHorizontalResize}
                        projectAssets={projectAssets}
                        assetDetails={assetDetails}
                        characterDetails={characterDetails}
                        savingContentId={savingContentId}
                        linkingAsset={loadingAction === 'asset'}
                        onGenerateChapterOutline={handleGenerateChapterOutline}
                        onRegenerateChapterOutlineScenes={handleRegenerateChapterOutlineScenes}
                        onGenerateNovelBody={handleGenerateNovelBody}
                        onRefineNovelBody={handleRefineNovelBody}
                        onSaveContentAsAsset={handleSaveContentAsAsset}
                        onExtractContinuity={handleExtractContinuity}
                        continuityExtracting={loadingAction === 'project_bible'}
                        onOpenFanqiePublish={() => setFanqieOpen(true)}
                        onGenerateScript={handleGenerateScript}
                        onGenerateStoryboard={handleGenerateStoryboardForChapter}
                        onMatchReferenceAssets={handleMatchReferenceAssets}
                        referenceMatching={loadingAction === 'reference_match'}
                        onBatchGenerateStoryboardImages={handleBatchGenerateStoryboardImages}
                        onSplitComicPages={handleSplitComicPages}
                        onSaveContent={handleSaveContent}
                        onUpdateStoryboardPanelReferences={handleUpdateStoryboardPanelReferences}
                        onLinkReferenceAsset={handleLinkAsset}
                        onSendImagePrompt={handleInlineGenerateImage}
                        onOpenVideoGeneration={handleOpenVideoGeneration}
                         onOpenPrevis={handleOpenPrevis}
                        inlineImages={inlineImages}
                        inlineImageLoadingKey={inlineImageLoadingKey}
                        pendingImageTaskKey={pendingInlineImageTask?.key}
                        pendingImageTaskId={pendingInlineImageTask?.taskId}
                        batchStoryboardImageChapter={batchStoryboardImageChapter}
                        defaultImageModelName={defaultImageModel.name || ''}
                        defaultImageSupportsReferenceImages={defaultImageSupportsReferenceImages}
                        selectedCreativeSkillIds={selectedCreativeSkillIds}
                        onCreativeSkillIdsChange={handleCreativeSkillIdsChange}
                        compact={workspaceNarrow}
                      />
                    ),
                  },
                  {
                    key: 'writer-room',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        写作室
                      </Space>
                    ),
                    children: (
                      <WriterRoomTab
                        chapters={chapters}
                        activeChapterNumber={activeChapterNumber}
                        onActiveChapterChange={handleActiveChapterChange}
                        contents={writerRoomContents}
                        loadError={workspaceErrors.writerRoom}
                        loadingContents={workspaceLoading.writerRoom}
                        onRetryContents={() => selectedProject && loadWriterRoomContents(selectedProject.id, activeChapterNumber)}
                        contentForChapter={contentForChapter}
                        logs={generationLogs}
                        templateOptionsByStage={templateOptionsByStage}
                        selectedPromptTemplates={selectedPromptTemplates}
                        onTemplateChange={(stage, value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, [stage]: value }))
                        }
                        llmOptions={llmConnectors.map((item) => ({
                          label: `${item.name}${item.is_default ? '（默认）' : ''}`,
                          value: item.name,
                        }))}
                        selectedLlm={selectedLlm}
                        selectedModel={selectedModel}
                        modelOptions={modelOptions}
                        onLlmChange={(value) => {
                          const connector = llmConnectors.find((item) => item.name === value)
                          setSelectedLlm(value)
                          setSelectedModel(connector?.default_model || '')
                        }}
                        onModelChange={setSelectedModel}
                        loading={loadingAction === 'writer_room'}
                        rehearsalMode={rehearsalMode}
                        onRehearsalModeChange={setRehearsalMode}
                        onRunStep={handleRunWriterRoomStep}
                        onRunBatch={handleRunWriterRoomBatch}
                        onPromote={handlePromoteWriterRoomContent}
                        continuityCandidates={continuityCandidates}
                        continuitySummary={continuitySummary}
                        onResolveContinuityCandidate={handleResolveContinuityCandidate}
                        onRewriteParagraph={handleRewriteParagraph}
                      />
                    ),
                  },
                  {
                    key: 'script',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        正文/漫画
                      </Space>
                    ),
                    children: (
                      <ScriptTab
                        novelBodies={novelBodies}
                        comicPages={comicPages}
                        chapterPlan={chapterPlan}
                        onSendImagePrompt={handleInlineGenerateImage}
                        inlineImages={inlineImages}
                        inlineImageLoadingKey={inlineImageLoadingKey}
                        projectTitle={selectedProject?.title || ''}
                      />
                    ),
                  },
                  {
                    key: 'canvas',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        关系图谱
                      </Space>
                    ),
                    children: (
                      <ProjectGraphTab
                        graph={projectGraphView}
                        saving={loadingAction === 'canvas_save'}
                        generating={Boolean(loadingAction || loadingChapterAction.action || inlineImageLoadingKey)}
                        onSave={handleSaveProjectGraph}
                        onOpenNode={handleOpenGraphNode}
                        onToggleLock={handleToggleGraphNodeLock}
                        onRegenerate={handleRegenerateGraphNode}
                        onSendToCanvas={handleSendGraphNodeToCanvas}
                        onSendImagePrompt={(node) => {
                          const prompt = node.source?.prompt || node.data?.image_prompt || ''
                          if (!prompt) {
                            message.warning('这个节点没有可发送的生图提示词')
                            return
                          }
                          handleInlineGenerateImage(prompt, {
                            contentId: node.source?.contentId,
                            sourceType: node.source?.sourceType || 'project_graph_prompt',
                            sourceIndex: node.source?.sourceIndex,
                            sourceTitle: node.label,
                            chapterNumber: node.source?.chapterNumber,
                            referenceAssetIds: node.data?.reference_asset_ids || [],
                            characterIds: node.data?.character_ids || [],
                            portraitNodeIds: node.data?.portrait_node_ids || [],
                            portraitVersionIds: node.data?.portrait_version_ids || [],
                          })
                        }}
                      />
                    ),
                  },
                  {
                    key: 'narrative-graph',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        叙事图谱
                      </Space>
                    ),
                    children: <NarrativeGraphTab graph={narrativeGraphData} chapterNumber={activeChapterNumber} />,
                  },
                  {
                    key: 'assets',
                    label: (
                      <Space>
                        <FolderOpenOutlined />
                        素材
                      </Space>
                    ),
                    children: (
                      <AssetsTab
                        assets={projectAssets}
                        unavailableAssetIds={unavailableAssetIds}
                        loading={loadingAction === 'asset'}
                        onLinkAsset={handleLinkAsset}
                      />
                    ),
                  },
                  {
                    key: 'logs',
                    label: (
                      <Space>
                        <HistoryOutlined />
                        日志
                      </Space>
                    ),
                    children: (
                      <LogsTab
                        logs={generationLogs}
                        onRefresh={() => selectedProject && loadGenerationLogs(selectedProject.id)}
                      />
                    ),
                  },
                  {
                    key: 'json',
                    label: 'JSON',
                    children: (
                      <JsonTab
                        outline={outline}
                        chapterPlan={chapterPlan}
                        contents={contents}
                        assets={projectAssets}
                      />
                    ),
                  },
                ].filter((item) =>
                  workspaceMode === 'chapter'
                    ? ['episode-workbench', 'writer-room', 'script'].includes(item.key)
                    : ['outline', 'project-bible', 'chapters', 'canvas', 'narrative-graph', 'assets', 'logs', 'json'].includes(item.key),
                )}
              />
                </div>
              </div>
            </>
          )}
        </main>
        {inspectorOpen && !cockpitCompact && selectedProject ? (
          <aside
            aria-label="叙事检查器"
            style={{
              borderLeft: `1px solid ${theme.borderLight}`,
              background: theme.bgCard,
              minHeight: 620,
              minWidth: 0,
            }}
          >
            <NarrativeInspector
              theme={theme}
              chapterNumber={activeChapterNumber}
              context={narrativeContext}
              ledger={foreshadowingLedger}
              graph={narrativeGraphData}
              facts={[...projectBibleContents, ...worldAssetContents]}
              continuityCandidates={continuityCandidates}
              continuitySummary={continuitySummary}
              logs={narrativeInspectorLogs}
              runs={narrativeRuns}
              loading={narrativeLoading}
              onRefresh={() => selectedProject && loadNarrativeRuntime(selectedProject.id, activeChapterNumber)}
              onDecision={handleForeshadowingDecision}
              onRunControl={handleNarrativeRunControl}
              onAutopilot={handleNarrativeAutopilot}
              onOpenWriterRoom={() => openWorkspaceTab('writer-room', 'chapter')}
              onOpenFacts={() => openWorkspaceTab('project-bible', 'overview')}
            />
          </aside>
        ) : null}
      </div>

      {inspectorOpen && cockpitCompact && selectedProject ? (
        <aside
          aria-label="叙事检查器"
          style={{ marginTop: 12, border: `1px solid ${theme.borderLight}`, borderRadius: 8, background: theme.bgCard }}
        >
          <NarrativeInspector
            theme={theme}
            chapterNumber={activeChapterNumber}
            context={narrativeContext}
            ledger={foreshadowingLedger}
            graph={narrativeGraphData}
            facts={[...projectBibleContents, ...worldAssetContents]}
            continuityCandidates={continuityCandidates}
            continuitySummary={continuitySummary}
            logs={narrativeInspectorLogs}
            runs={narrativeRuns}
            loading={narrativeLoading}
            onRefresh={() => selectedProject && loadNarrativeRuntime(selectedProject.id, activeChapterNumber)}
            onDecision={handleForeshadowingDecision}
            onRunControl={handleNarrativeRunControl}
            onAutopilot={handleNarrativeAutopilot}
            onOpenWriterRoom={() => openWorkspaceTab('writer-room', 'chapter')}
            onOpenFacts={() => openWorkspaceTab('project-bible', 'overview')}
          />
        </aside>
      ) : null}

      <Modal
        title="新建创作项目"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        afterOpenChange={(open) => {
          if (open) {
            form.setFieldsValue({ source_type: 'original_idea', project_type: 'short_drama' })
            loadNovelAssets()
          }
        }}
        onOk={() => form.submit()}
        confirmLoading={loadingAction === 'create'}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ source_type: 'original_idea', project_type: 'short_drama' }}
          onFinish={handleCreate}
        >
          <Form.Item label="来源" name="source_type">
            <Select
              options={[
                { label: '原创创意', value: 'original_idea' },
                { label: '小说书架', value: 'novel' },
              ]}
              onChange={() => {
                form.setFieldsValue({ novel_asset_id: undefined, chapter_indices: [], chapter_range: '' })
              }}
            />
          </Form.Item>
          <Form.Item label="标题" name="title">
            <Input placeholder="可留空，生成大纲后会自动更新" />
          </Form.Item>
          <Form.Item label="项目类型" name="project_type">
            <Select options={projectTypeOptions} />
          </Form.Item>
          {createSourceType === 'novel' ? (
            <>
              <Form.Item
                label="小说"
                name="novel_asset_id"
                rules={[{ required: true, message: '请选择小说' }]}
              >
                <Select
                  showSearch
                  loading={loadingNovelAssets}
                  placeholder="选择已加入书架的小说"
                  optionFilterProp="label"
                  options={novelAssets.map((asset) => {
                    const meta = asset.metadata || {}
                    const downloaded = Array.isArray(meta.downloaded_chapter_indices)
                      ? meta.downloaded_chapter_indices.length
                      : 0
                    const total = meta.chapter_count || meta.chapters?.length || 0
                    return {
                      label: `${getNovelDisplayTitle(asset)}${downloaded || total ? `（已下载 ${downloaded}/${total || '?'}）` : ''}`,
                      value: asset.id,
                    }
                  })}
                  onChange={() => form.setFieldsValue({ chapter_indices: [], chapter_range: '' })}
                  dropdownRender={(menu) => (
                    <>
                      {menu}
                      {!novelAssets.length && !loadingNovelAssets ? (
                        <div style={{ padding: 8 }}>
                          <Button type="link" size="small" onClick={() => navigate('/novel-bookshelf')}>
                            去小说书架添加
                          </Button>
                        </div>
                      ) : null}
                    </>
                  )}
                />
              </Form.Item>
              <Form.Item label="已下载章节" name="chapter_indices">
                <Select
                  mode="multiple"
                  allowClear
                  placeholder={
                    selectedNovelAsset
                      ? selectedNovelChapterOptions.length
                        ? '选择要导入的已下载章节；留空则使用手填范围或全部已下载章节'
                        : '这本书暂无已下载章节，请先去书架下载'
                      : '先选择小说'
                  }
                  options={selectedNovelChapterOptions}
                  disabled={!selectedNovelAsset || !selectedNovelChapterOptions.length}
                />
              </Form.Item>
              <Form.Item label="章节范围" name="chapter_range">
                <Input placeholder="可选，例如 1-3,5；用于目录未展开或快速选择" />
              </Form.Item>
              <Text type="secondary">
                只会导入已经下载到本地的章节；如果章节未下载，请先到小说书架下载。
              </Text>
            </>
          ) : (
            <Form.Item
              label="创意"
              name="idea"
              rules={[{ required: true, message: '请输入创意' }]}
            >
              <TextArea rows={5} placeholder="例如：短剧但是不降智" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title="重命名项目"
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={() => renameForm.submit()}
        confirmLoading={loadingAction === 'rename'}
        destroyOnClose
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={renameForm}
          layout="vertical"
          onFinish={handleRename}
        >
          <Form.Item
            label="项目名称"
            name="title"
            rules={[{ required: true, message: '请输入项目名称' }, { max: 80, message: '名称最多 80 字' }]}
          >
            <Input placeholder="请输入新的项目名称" maxLength={80} allowClear />
          </Form.Item>
        </Form>
      </Modal>

      <FanqiePublishPanel
        visible={fanqieOpen}
        onClose={() => setFanqieOpen(false)}
        projectId={selectedProject?.id || ''}
        contentId={contentForChapter('novel_body', activeChapterNumber)?.id || ''}
        chapterNumber={activeChapterNumber}
        chapterTitle={contentForChapter('novel_body', activeChapterNumber)?.title}
      />
    </div>
  )
}

function PipelinePanel({
  theme,
  stages,
  onStagesChange,
  chapterRange,
  onChapterRangeChange,
  skipExisting,
  onSkipExistingChange,
  continueOnError,
  onContinueOnErrorChange,
  loading,
  result,
  runStatus,
  onRun,
  onRetryFailed,
}: {
  theme: ThemeColors
  stages: PipelineStageValue[]
  onStagesChange: (value: PipelineStageValue[]) => void
  chapterRange: string
  onChapterRangeChange: (value: string) => void
  skipExisting: boolean
  onSkipExistingChange: (value: boolean) => void
  continueOnError: boolean
  onContinueOnErrorChange: (value: boolean) => void
  loading: boolean
  result: PipelineResult | null
  runStatus: PipelineRunStatus
  onRun: () => void
  onRetryFailed: () => void
}) {
  const rows = result?.results || []
  const { generated, skipped, failed } = getPipelineSummary(result)

  const pipelineColumns = [
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 120,
      render: (value: string) => pipelineStageOptions.find((item) => item.value === value)?.label || value,
    },
    {
      title: '章节',
      dataIndex: 'chapter_number',
      width: 76,
      render: (value?: number) => (value ? `第 ${value} 章` : '全局'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => {
        const color = value === 'failed' ? 'red' : value === 'skipped' ? 'default' : 'green'
        const label = value === 'failed' ? '失败' : value === 'skipped' ? '跳过' : '完成'
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '结果',
      render: (_: unknown, record: PipelineResultItem) => (
        <Text type={record.status === 'failed' ? 'danger' : 'secondary'} ellipsis={{ tooltip: record.error || record.reason || record.title }}>
          {record.error || record.reason || record.title || record.content_type || record.count || record.word_count || '-'}
        </Text>
      ),
    },
  ]

  return (
    <section
      style={{
        margin: '8px 0 0',
        padding: 16,
        border: `1px solid ${theme.border}`,
        borderRadius: 8,
        background: theme.bgElevated,
      }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <Space align="start" style={{ justifyContent: 'space-between', width: '100%' }} wrap>
          <div>
            <Text strong>批量生产</Text>
            <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>
              按章节连续生成细纲、正文、脚本、分镜和参考卡；默认跳过已有内容，适合补齐后续章节。
            </Paragraph>
          </div>
          <Space wrap>
            {failed ? (
              <Button loading={loading} onClick={onRetryFailed}>
                只重试失败
              </Button>
            ) : null}
            <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={() => onRun()}>
              开始批量生产
            </Button>
          </Space>
        </Space>

        {runStatus === 'running' ? (
          <Alert
            type="info"
            showIcon
            message="批量生产进行中"
            description="后端会按依赖顺序执行各阶段；关闭或刷新页面不会把已完成的步骤当成空结果。"
          />
        ) : null}
        {runStatus === 'partial' ? (
          <Alert
            type="warning"
            showIcon
            message="批量生产部分完成"
            description="成功和跳过的步骤已经保留，下面只需重试失败步骤，不会重复提交已完成内容。"
          />
        ) : null}
        {runStatus === 'failed' ? (
          <Alert
            type="error"
            showIcon
            message="批量生产失败"
            description="请查看步骤结果和生成日志中的具体错误；修复配置后可以只重试失败步骤。"
          />
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 0.7fr) minmax(320px, 1.3fr)', gap: 12 }}>
          <Space direction="vertical" size={6}>
            <Text type="secondary">章节范围</Text>
            <Input
              value={chapterRange}
              onChange={(event) => onChapterRangeChange(event.target.value)}
              placeholder="例如：1、1-3、1,3,5"
            />
          </Space>
          <Space direction="vertical" size={6}>
            <Text type="secondary">生产阶段</Text>
            <Checkbox.Group
              options={pipelineStageOptions}
              value={stages}
              onChange={(values) => onStagesChange(values as PipelineStageValue[])}
            />
          </Space>
        </div>

        <Space size={16} wrap>
          <Checkbox checked={skipExisting} onChange={(event) => onSkipExistingChange(event.target.checked)}>
            跳过已有内容
          </Checkbox>
          {!skipExisting ? <Tag color="orange">将生成新版本并作为最新结果</Tag> : null}
          <Checkbox checked={continueOnError} onChange={(event) => onContinueOnErrorChange(event.target.checked)}>
            单步失败后继续
          </Checkbox>
          {result ? (
            <Space size={6} wrap>
              <Tag color="green">生成 {generated}</Tag>
              <Tag>跳过 {skipped}</Tag>
              <Tag color={failed ? 'red' : 'default'}>失败 {failed}</Tag>
            </Space>
          ) : null}
        </Space>

        {rows.length ? (
          <Table
            size="small"
            pagination={false}
            rowKey={(record, index) => `${record.stage}-${record.chapter_number || 'global'}-${index}`}
            columns={pipelineColumns}
            dataSource={rows}
          />
        ) : null}
      </Space>
    </section>
  )
}

type ProductionStageItem = {
  key: string
  tab: string
  label: string
  hint: string
  complete: number
  total: number
}

function ProductionStageRail({
  theme,
  stages,
  activeTab,
  onSelect,
}: {
  theme: ThemeColors
  stages: ProductionStageItem[]
  activeTab: string
  onSelect: (tab: string) => void
}) {
  return (
    <nav
      aria-label="项目生产阶段"
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${stages.length}, minmax(132px, 1fr))`,
        gap: 0,
        overflowX: 'auto',
        borderBottom: `1px solid ${theme.borderLight}`,
        background: theme.bgElevated,
      }}
    >
      {stages.map((stage, index) => {
        const isActive = stage.tab === activeTab
        const isComplete = stage.complete >= stage.total
        const ratio = Math.min(1, stage.complete / Math.max(stage.total, 1))
        return (
          <button
            key={stage.key}
            type="button"
            onClick={() => onSelect(stage.tab)}
            aria-current={isActive ? 'step' : undefined}
            style={{
              minWidth: 132,
              padding: '13px 14px 12px',
              border: 'none',
              borderRight: index < stages.length - 1 ? `1px solid ${theme.borderLight}` : 'none',
              borderBottom: isActive ? `2px solid ${theme.primary}` : '2px solid transparent',
              background: isActive ? theme.primaryAlpha(0.1) : 'transparent',
              color: theme.textPrimary,
              textAlign: 'left',
              cursor: 'pointer',
              transition: 'background 180ms ease, transform 160ms ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <Text strong style={{ color: theme.textPrimary, fontSize: 13 }}>{stage.label}</Text>
              <span
                aria-label={`${stage.complete}/${stage.total}`}
                style={{
                  width: 18,
                  height: 18,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 4,
                  border: `1px solid ${isComplete ? theme.primary : theme.border}`,
                  background: isComplete ? theme.primaryAlpha(0.18) : 'transparent',
                  color: isComplete ? theme.primary : theme.textSecondary,
                  fontSize: 10,
                  fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {isComplete ? '✓' : index + 1}
              </span>
            </div>
            <Text type="secondary" ellipsis={{ tooltip: stage.hint }} style={{ display: 'block', marginTop: 3, fontSize: 12 }}>
              {stage.hint}
            </Text>
            <div style={{ height: 3, marginTop: 9, background: theme.borderLight, overflow: 'hidden' }}>
              <div style={{ width: `${ratio * 100}%`, height: '100%', background: theme.primary, transition: 'width 220ms ease' }} />
            </div>
            <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
              {stage.complete}/{stage.total}
            </Text>
          </button>
        )
      })}
    </nav>
  )
}

function OutlineTab({
  outline,
  hasOutline,
  loading,
  saving,
  syncLoading,
  llmAvailable,
  templateOptions,
  selectedTemplateId,
  onTemplateChange,
  onGenerate,
  onSave,
  onSyncCharacters,
  characterColumns,
}: {
  outline: StoryOutline
  hasOutline: boolean
  loading: boolean
  saving: boolean
  syncLoading: boolean
  llmAvailable: boolean
  templateOptions: TemplateOption[]
  selectedTemplateId?: string
  onTemplateChange: (value: string) => void
  onGenerate: () => void
  onSave: (outline: StoryOutline) => Promise<void>
  onSyncCharacters: () => void
  characterColumns: any[]
}) {
  const [draft, setDraft] = useState<StoryOutline>(outline || {})
  const [jsonDraft, setJsonDraft] = useState('')
  const [jsonError, setJsonError] = useState('')

  useEffect(() => {
    setDraft(outline || {})
    setJsonDraft(JSON.stringify(outline || {}, null, 2))
    setJsonError('')
  }, [outline])

  const updateField = (field: keyof StoryOutline, value: any) => {
    setDraft((prev) => ({ ...prev, [field]: value }))
  }

  const updateStoryArc = (field: keyof NonNullable<StoryOutline['story_arc']>, value: string) => {
    setDraft((prev) => ({ ...prev, story_arc: { ...(prev.story_arc || {}), [field]: value } }))
  }

  const saveJson = async () => {
    try {
      const parsed = JSON.parse(jsonDraft || '{}')
      setJsonError('')
      setDraft(parsed)
      await onSave(parsed)
    } catch (error: any) {
      setJsonError(error?.message || 'JSON 格式不正确')
    }
  }

  if (!hasOutline) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%', padding: '24px 0' }}>
        <Alert
          message="创建故事蓝图"
          description="可先在下方手动填写故事大纲后保存；AI 生成需要先在设置中配置文本模型。"
          type="info"
          showIcon
        />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div>
            <Title level={4} style={{ marginBottom: 4 }}>
              新故事大纲
            </Title>
            <Text type="secondary">保存后可以继续补充角色、章节规划等内容。</Text>
          </div>
          <Space wrap style={{ justifyContent: 'flex-end' }}>
            <PromptTemplateSelect
              value={selectedTemplateId}
              options={templateOptions}
              placeholder="大纲模板"
              onChange={onTemplateChange}
            />
            <Tooltip title={llmAvailable ? '' : '请先在设置中配置文本模型'}>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={loading}
                onClick={onGenerate}
                disabled={!llmAvailable}
              >
                生成故事大纲
              </Button>
            </Tooltip>
            <Button type="primary" loading={saving} onClick={() => onSave(draft)}>
              保存大纲
            </Button>
          </Space>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(240px, 1fr)', gap: 12 }}>
          <EditorField label="标题">
            <Input value={draft.title} onChange={(event) => updateField('title', event.target.value)} />
          </EditorField>
          <EditorField label="类型">
            <TextArea
              value={listToLines(draft.genre)}
              onChange={(event) => updateField('genre', linesToList(event.target.value))}
              autoSize={{ minRows: 1, maxRows: 3 }}
            />
          </EditorField>
          <EditorField label="一句话卖点">
            <Input value={draft.logline} onChange={(event) => updateField('logline', event.target.value)} />
          </EditorField>
          <EditorField label="目标读者">
            <Input value={draft.target_reader} onChange={(event) => updateField('target_reader', event.target.value)} />
          </EditorField>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <EditorField label="核心前提">
            <TextArea value={draft.premise} onChange={(event) => updateField('premise', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
          <EditorField label="世界观">
            <TextArea value={draft.worldview} onChange={(event) => updateField('worldview', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
          <EditorField label="主线冲突">
            <TextArea value={draft.main_conflict} onChange={(event) => updateField('main_conflict', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
          <EditorField label="观众情绪">
            <TextArea value={draft.audience_emotion} onChange={(event) => updateField('audience_emotion', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <EditorField label="卖点" hint="一行一条">
            <TextArea value={listToLines(draft.selling_points)} onChange={(event) => updateField('selling_points', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
          <EditorField label="叙事规则" hint="一行一条">
            <TextArea value={listToLines(draft.narrative_rules)} onChange={(event) => updateField('narrative_rules', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
          <EditorField label="主题" hint="一行一条">
            <TextArea value={listToLines(draft.themes)} onChange={(event) => updateField('themes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
          <EditorField label="制作约束" hint="一行一条，会影响后续分镜/生图">
            <TextArea value={listToLines(draft.production_notes)} onChange={(event) => updateField('production_notes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
        </div>

        <WorkbenchSection title="故事弧线">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <EditorField label="开局">
              <TextArea value={draft.story_arc?.beginning} onChange={(event) => updateStoryArc('beginning', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
            <EditorField label="中段">
              <TextArea value={draft.story_arc?.middle} onChange={(event) => updateStoryArc('middle', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
            <EditorField label="高潮">
              <TextArea value={draft.story_arc?.climax} onChange={(event) => updateStoryArc('climax', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
            <EditorField label="结局方向">
              <TextArea value={draft.story_arc?.ending_direction} onChange={(event) => updateStoryArc('ending_direction', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
          </div>
        </WorkbenchSection>
      </Space>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ minWidth: 0, flex: '1 1 360px' }}>
          <Title level={4} style={{ marginBottom: 4 }}>
            {outline.title || '故事大纲'}
          </Title>
          <Text type="secondary" style={{ display: 'block', maxWidth: '72ch' }}>
            {outline.logline || '未填写一句话卖点'}
          </Text>
        </div>
        <Space wrap style={{ justifyContent: 'flex-end' }}>
          <PromptTemplateSelect
            value={selectedTemplateId}
            options={templateOptions}
            placeholder="大纲模板"
            onChange={onTemplateChange}
          />
          <Button icon={<UserOutlined />} loading={syncLoading} onClick={onSyncCharacters}>
            同步角色库
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={() => downloadTextFile(`${projectMarkdownFilename(draft.title || outline.title, 'outline')}.md`, buildOutlineMarkdown(draft))}
          >
            导出 Markdown
          </Button>
          <Button type="primary" loading={saving} onClick={() => onSave(draft)}>
            保存大纲
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={onGenerate}>
            重新生成
          </Button>
        </Space>
      </div>

      <Tabs
        items={[
          {
            key: 'structured',
            label: '结构化编辑',
            children: (
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(240px, 1fr)', gap: 12 }}>
                  <EditorField label="标题">
                    <Input value={draft.title} onChange={(event) => updateField('title', event.target.value)} />
                  </EditorField>
                  <EditorField label="类型">
                    <TextArea
                      value={listToLines(draft.genre)}
                      onChange={(event) => updateField('genre', linesToList(event.target.value))}
                      autoSize={{ minRows: 1, maxRows: 3 }}
                    />
                  </EditorField>
                  <EditorField label="一句话卖点">
                    <Input value={draft.logline} onChange={(event) => updateField('logline', event.target.value)} />
                  </EditorField>
                  <EditorField label="目标读者">
                    <Input value={draft.target_reader} onChange={(event) => updateField('target_reader', event.target.value)} />
                  </EditorField>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                  <EditorField label="核心前提">
                    <TextArea value={draft.premise} onChange={(event) => updateField('premise', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                  <EditorField label="世界观">
                    <TextArea value={draft.worldview} onChange={(event) => updateField('worldview', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                  <EditorField label="主线冲突">
                    <TextArea value={draft.main_conflict} onChange={(event) => updateField('main_conflict', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                  <EditorField label="观众情绪">
                    <TextArea value={draft.audience_emotion} onChange={(event) => updateField('audience_emotion', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                  <EditorField label="卖点" hint="一行一条">
                    <TextArea value={listToLines(draft.selling_points)} onChange={(event) => updateField('selling_points', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                  <EditorField label="叙事规则" hint="一行一条">
                    <TextArea value={listToLines(draft.narrative_rules)} onChange={(event) => updateField('narrative_rules', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                  <EditorField label="主题" hint="一行一条">
                    <TextArea value={listToLines(draft.themes)} onChange={(event) => updateField('themes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                  <EditorField label="制作约束" hint="一行一条，会影响后续分镜/生图">
                    <TextArea value={listToLines(draft.production_notes)} onChange={(event) => updateField('production_notes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                </div>

                <WorkbenchSection title="故事弧线">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                    <EditorField label="开局">
                      <TextArea value={draft.story_arc?.beginning} onChange={(event) => updateStoryArc('beginning', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                    <EditorField label="中段">
                      <TextArea value={draft.story_arc?.middle} onChange={(event) => updateStoryArc('middle', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                    <EditorField label="高潮">
                      <TextArea value={draft.story_arc?.climax} onChange={(event) => updateStoryArc('climax', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                    <EditorField label="结局方向">
                      <TextArea value={draft.story_arc?.ending_direction} onChange={(event) => updateStoryArc('ending_direction', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                  </div>
                </WorkbenchSection>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                  <EditorField label="叙事气质">
                    <TextArea value={draft.tone} onChange={(event) => updateField('tone', event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
                  </EditorField>
                  <EditorField label="视觉风格">
                    <TextArea value={draft.visual_style} onChange={(event) => updateField('visual_style', event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
                  </EditorField>
                  <EditorField label="统一生图提示">
                    <TextArea value={draft.image_style_prompt} onChange={(event) => updateField('image_style_prompt', event.target.value)} autoSize={{ minRows: 3, maxRows: 8 }} />
                  </EditorField>
                </div>
              </Space>
            ),
          },
          {
            key: 'json',
            label: 'JSON 高级编辑',
            children: (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Text type="secondary">复杂角色、场景、关系图可以在这里直接编辑完整 JSON。</Text>
                <TextArea
                  value={jsonDraft}
                  onChange={(event) => setJsonDraft(event.target.value)}
                  autoSize={{ minRows: 18, maxRows: 34 }}
                  style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' }}
                />
                {jsonError ? <Text type="danger">{jsonError}</Text> : null}
                <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
                  <Button onClick={() => setJsonDraft(JSON.stringify(draft || {}, null, 2))}>同步结构化草稿</Button>
                  <Button type="primary" loading={saving} onClick={saveJson}>保存 JSON</Button>
                </Space>
              </Space>
            ),
          },
          {
            key: 'preview',
            label: '预览',
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <InfoBlock title="核心前提" text={draft.premise} />
                  <InfoBlock title="世界观" text={draft.worldview} />
                  <InfoBlock title="主线冲突" text={draft.main_conflict} />
                  <InfoBlock title="观众情绪" text={draft.audience_emotion} />
                  <InfoListBlock title="卖点" items={draft.selling_points || []} />
                  <InfoListBlock title="叙事规则" items={draft.narrative_rules || []} />
                </div>
              </Space>
            ),
          },
        ]}
      />

      <div>
        <Title level={5}>角色</Title>
        <Table
          size="small"
          rowKey={(record: StoryOutlineCharacter, index?: number) => record.name || String(index)}
          columns={characterColumns}
          dataSource={draft.characters || []}
          pagination={false}
        />
      </div>
    </Space>
  )
}

const worldAssetRoleLabels: Record<string, string> = {
  map: '地图/关系',
  rule: '规则',
  faction: '势力',
  location: '地点',
  event: '事件',
  'power-system': '能力/系统',
  economy: '资源/代价',
  style: '画风',
  worldview: '世界观',
  premise: '前提',
  conflict: '冲突',
  relationship: '关系',
  arc: '弧线',
  constraint: '约束',
}

function ProjectBibleTab({
  hasOutline,
  bibleContents,
  worldAssets,
  loading,
  savingContentId,
  onSync,
  onSaveContent,
  onSaveAsAsset,
}: {
  hasOutline: boolean
  bibleContents: ProjectContent[]
  worldAssets: ProjectContent[]
  loading: boolean
  savingContentId: string | null
  onSync: (overwrite?: boolean) => void
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => Promise<void>
  onSaveAsAsset: (contentId: string) => void
}) {
  const lockedCount = [...bibleContents, ...worldAssets].filter((item) => item.is_locked).length

  if (!hasOutline) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description="先生成故事大纲，再拆分项目圣经和世界资产" />
      </div>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <WorkbenchSection
        title="项目圣经 / 世界资产"
        extra={
          <Space wrap>
            <Tag color={lockedCount ? 'green' : 'default'}>已锁定 {lockedCount}</Tag>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => onSync(false)}>
              从大纲补齐
            </Button>
            <Popconfirm
              title="重新同步会基于当前大纲创建新版本，旧卡仍保留在版本历史里。"
              okText="创建新版本"
              cancelText="取消"
              onConfirm={() => onSync(true)}
            >
              <Button loading={loading}>重新同步新版本</Button>
            </Popconfirm>
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          锁定后的卡片会注入后续“单话细纲”生成上下文，用来稳定世界规则、地点、画风、人物关系和连续性事实。
        </Paragraph>
      </WorkbenchSection>

      <WorkbenchSection title="项目圣经">
        {bibleContents.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            {sortBibleContents(bibleContents).map((content) => (
              <BibleContentCard
                key={content.id}
                content={content}
                saving={savingContentId === content.id}
                onSaveContent={onSaveContent}
                onSaveAsAsset={onSaveAsAsset}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无项目圣经卡，可先从大纲补齐" />
        )}
      </WorkbenchSection>

      <WorkbenchSection title="世界资产">
        {worldAssets.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            {sortBibleContents(worldAssets).map((content) => (
              <BibleContentCard
                key={content.id}
                content={content}
                saving={savingContentId === content.id}
                onSaveContent={onSaveContent}
                onSaveAsAsset={onSaveAsAsset}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无世界资产卡，可先从大纲补齐" />
        )}
      </WorkbenchSection>
    </Space>
  )
}

function BibleContentCard({
  content,
  saving,
  onSaveContent,
  onSaveAsAsset,
}: {
  content: ProjectContent
  saving: boolean
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => Promise<void>
  onSaveAsAsset: (contentId: string) => void
}) {
  const [title, setTitle] = useState(content.title || '')
  const [summary, setSummary] = useState(String(content.data?.summary || ''))
  const [details, setDetails] = useState(
    typeof content.data?.details === 'string'
      ? content.data.details
      : JSON.stringify(content.data?.details || '', null, 2),
  )

  useEffect(() => {
    setTitle(content.title || '')
    setSummary(String(content.data?.summary || ''))
    setDetails(
      typeof content.data?.details === 'string'
        ? content.data.details
        : JSON.stringify(content.data?.details || '', null, 2),
    )
  }, [content.id, content.title, content.data])

  const role = String(content.data?.role || content.content_type)
  const label = worldAssetRoleLabels[role] || role
  const keyLabel = content.data?.section_key || content.data?.asset_key || content.id.slice(0, 8)

  const save = () => {
    const nextData = {
      ...(content.data || {}),
      title,
      summary,
      details,
    }
    const textContent = [`# ${title}`, `类型：${label}`, summary, details].filter(Boolean).join('\n\n')
    return onSaveContent(content.id, {
      title,
      data: nextData,
      text_content: textContent,
    })
  }

  return (
    <section style={{ ...panelStyle, minHeight: 280 }}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
          <Space size={6} wrap>
            <Tag color={content.is_locked ? 'green' : 'default'}>{content.is_locked ? '已锁定' : '未锁定'}</Tag>
            <Tag>{label}</Tag>
            <Text type="secondary">{String(keyLabel)}</Text>
          </Space>
          <Checkbox
            checked={Boolean(content.is_locked)}
            onChange={(event) => onSaveContent(content.id, { is_locked: event.target.checked })}
          >
            锁定
          </Checkbox>
        </Space>
        <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="卡片标题" />
        <EditorField label="摘要" hint="一句话说明这张卡对剧情、画面或连续性的作用。">
          <TextArea value={summary} onChange={(event) => setSummary(event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
        </EditorField>
        <EditorField label="细节" hint="写清规则边界、视觉特征、场景用途、禁止偏离点，锁定后会进入细纲生成上下文。">
          <TextArea value={details} onChange={(event) => setDetails(event.target.value)} autoSize={{ minRows: 4, maxRows: 10 }} />
        </EditorField>
        <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
          <Button icon={<FolderAddOutlined />} onClick={() => onSaveAsAsset(content.id)}>
            存为素材
          </Button>
          <Button type="primary" loading={saving} onClick={save}>
            保存卡片
          </Button>
        </Space>
      </Space>
    </section>
  )
}

function sortBibleContents(items: ProjectContent[]) {
  return [...items].sort((left, right) => {
    const leftKey = String(left.data?.section_key || left.data?.asset_key || left.created_at || left.id)
    const rightKey = String(right.data?.section_key || right.data?.asset_key || right.created_at || right.id)
    return leftKey.localeCompare(rightKey, 'zh-CN')
  })
}

type EditableChapterPlanItem = ChapterPlanItem & { is_locked?: boolean }

function ChapterTab({
  chapterPlan,
  chapters,
  hasOutline,
  hasChapterPlan,
  chapterColumns,
  chapterCount,
  setChapterCount,
  comicPageCount,
  setComicPageCount,
  chapterTemplateOptions,
  selectedChapterTemplateId,
  onChapterTemplateChange,
  scriptTemplateOptions,
  selectedScriptTemplateId,
  onScriptTemplateChange,
  chapterOutlineTemplateOptions,
  selectedChapterOutlineTemplateId,
  onChapterOutlineTemplateChange,
  novelBodyTemplateOptions,
  selectedNovelBodyTemplateId,
  onNovelBodyTemplateChange,
  comicPagesTemplateOptions,
  selectedComicPagesTemplateId,
  onComicPagesTemplateChange,
  loading,
  saving,
  onGenerate,
  onSave,
}: {
  chapterPlan: ChapterPlan
  chapters: ChapterPlanItem[]
  hasOutline: boolean
  hasChapterPlan: boolean
  chapterColumns: any[]
  chapterCount: number
  setChapterCount: (value: number) => void
  comicPageCount: number
  setComicPageCount: (value: number) => void
  chapterTemplateOptions: TemplateOption[]
  selectedChapterTemplateId?: string
  onChapterTemplateChange: (value: string) => void
  scriptTemplateOptions: TemplateOption[]
  selectedScriptTemplateId?: string
  onScriptTemplateChange: (value: string) => void
  chapterOutlineTemplateOptions: TemplateOption[]
  selectedChapterOutlineTemplateId?: string
  onChapterOutlineTemplateChange: (value: string) => void
  novelBodyTemplateOptions: TemplateOption[]
  selectedNovelBodyTemplateId?: string
  onNovelBodyTemplateChange: (value: string) => void
  comicPagesTemplateOptions: TemplateOption[]
  selectedComicPagesTemplateId?: string
  onComicPagesTemplateChange: (value: string) => void
  loading: boolean
  saving: boolean
  onGenerate: (options?: { preserveLocked?: boolean }) => void
  onSave: (chapterPlan: ChapterPlan) => Promise<void>
}) {
  const [rows, setRows] = useState<EditableChapterPlanItem[]>([])
  const [jsonDraft, setJsonDraft] = useState('')
  const [jsonError, setJsonError] = useState('')

  useEffect(() => {
    const nextRows = chapters.map((item) => ({ ...normalizeChapterItem(item), is_locked: isChapterLocked(item) }))
    setRows(nextRows)
    setJsonDraft(JSON.stringify(normalizeChapterPlan({ ...chapterPlan, chapters: nextRows }), null, 2))
    setJsonError('')
  }, [chapterPlan, chapters])

  const updateRow = (index: number, patch: Partial<EditableChapterPlanItem>) => {
    setRows((prev) => prev.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)))
  }

  const saveRows = () => onSave({ ...chapterPlan, chapter_count: rows.length, chapters: rows.map(normalizeChapterItem) })

  const addRow = () => {
    const nextNumber = rows.reduce((max, item) => Math.max(max, Number(item.chapter_number || 0)), 0) + 1
    setRows((prev) => [
      ...prev,
      {
        chapter_number: nextNumber,
        title: `第 ${nextNumber} 章`,
        goal: '',
        conflict: '',
        key_events: [],
        character_focus: [],
        ending_hook: '',
        status: 'draft',
      },
    ])
  }

  const deleteRow = (index: number) => {
    setRows((prev) => prev.filter((_, itemIndex) => itemIndex !== index))
  }

  const saveJson = async () => {
    try {
      const parsed = normalizeChapterPlan(JSON.parse(jsonDraft || '{}'))
      setJsonError('')
      setRows((parsed.chapters || []).map((item) => ({ ...item, is_locked: isChapterLocked(item) })))
      await onSave(parsed)
    } catch (error: any) {
      setJsonError(error?.message || 'JSON 格式不正确')
    }
  }

  const editorColumns = [
    {
      title: '锁',
      width: 68,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Checkbox
          checked={isChapterLocked(record)}
          onChange={(event) => updateRow(index, { is_locked: event.target.checked, status: event.target.checked ? 'locked' : 'draft' })}
        />
      ),
    },
    {
      title: '章',
      width: 90,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <InputNumber
          min={1}
          value={record.chapter_number}
          onChange={(value) => updateRow(index, { chapter_number: Number(value || index + 1) })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '标题 / 尾钩',
      width: 260,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Input value={record.title} onChange={(event) => updateRow(index, { title: event.target.value })} placeholder="章节标题" />
          <TextArea
            value={record.ending_hook}
            onChange={(event) => updateRow(index, { ending_hook: event.target.value })}
            placeholder="章末钩子"
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Space>
      ),
    },
    {
      title: '目标 / 冲突',
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <TextArea value={record.goal} onChange={(event) => updateRow(index, { goal: event.target.value })} placeholder="本章目标" autoSize={{ minRows: 2, maxRows: 5 }} />
          <TextArea value={record.conflict} onChange={(event) => updateRow(index, { conflict: event.target.value })} placeholder="本章冲突" autoSize={{ minRows: 2, maxRows: 5 }} />
        </Space>
      ),
    },
    {
      title: '事件 / 角色',
      width: 300,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <TextArea
            value={listToLines(record.key_events)}
            onChange={(event) => updateRow(index, { key_events: linesToList(event.target.value) })}
            placeholder="关键事件，一行一条"
            autoSize={{ minRows: 3, maxRows: 6 }}
          />
          <TextArea
            value={listToLines(record.character_focus)}
            onChange={(event) => updateRow(index, { character_focus: linesToList(event.target.value) })}
            placeholder="焦点角色，一行一个"
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Space>
      ),
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, __: EditableChapterPlanItem, index: number) => (
        <Popconfirm title="删除这一章规划？" okText="删除" cancelText="取消" onConfirm={() => deleteRow(index)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space wrap>
          <Text strong>章节数量</Text>
          <InputNumber
            min={1}
            max={200}
            value={chapterCount}
            onChange={(value) => setChapterCount(Number(value || 12))}
          />
          <PromptTemplateSelect
            value={selectedChapterTemplateId}
            options={chapterTemplateOptions}
            placeholder="章节模板"
            onChange={onChapterTemplateChange}
          />
          <PromptTemplateSelect
            value={selectedScriptTemplateId}
            options={scriptTemplateOptions}
            placeholder="脚本模板"
            onChange={onScriptTemplateChange}
          />
        </Space>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          disabled={!hasOutline}
          loading={loading}
          onClick={() => onGenerate()}
        >
          {hasChapterPlan ? '重新生成章节' : '生成章节规划'}
        </Button>
      </Space>
      <Space wrap>
        <Space>
          <Text strong>漫画页数</Text>
          <InputNumber
            min={1}
            max={80}
            value={comicPageCount}
            onChange={(value) => setComicPageCount(Number(value || 10))}
          />
        </Space>
        <PromptTemplateSelect
          value={selectedChapterOutlineTemplateId}
          options={chapterOutlineTemplateOptions}
          placeholder="细纲模板"
          onChange={onChapterOutlineTemplateChange}
        />
        <PromptTemplateSelect
          value={selectedNovelBodyTemplateId}
          options={novelBodyTemplateOptions}
          placeholder="正文模板"
          onChange={onNovelBodyTemplateChange}
        />
        <PromptTemplateSelect
          value={selectedComicPagesTemplateId}
          options={comicPagesTemplateOptions}
          placeholder="漫画拆页模板"
          onChange={onComicPagesTemplateChange}
        />
      </Space>

      {!hasOutline ? (
        <Empty description="先生成故事大纲" />
      ) : !hasChapterPlan ? (
        <Empty description="暂无章节规划" />
      ) : (
        <Tabs
          items={[
            {
              key: 'edit',
              label: '章节规划编辑',
              children: (
                <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
                    <Space wrap>
                      <Tag color="blue">{rows.length} 章</Tag>
                      <Tag color={rows.some(isChapterLocked) ? 'green' : 'default'}>锁定 {rows.filter(isChapterLocked).length}</Tag>
                    </Space>
                    <Space wrap>
                      <Button icon={<PlusOutlined />} onClick={addRow}>新增章节</Button>
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={() => downloadTextFile('chapter-plan.md', buildChapterPlanMarkdown({ ...chapterPlan, chapters: rows }))}
                      >
                        导出 Markdown
                      </Button>
                      <Button loading={loading} onClick={() => onGenerate({ preserveLocked: true })}>保留现有并补齐</Button>
                      <Button type="primary" loading={saving} onClick={saveRows}>保存规划</Button>
                    </Space>
                  </Space>
                  <Table
                    rowKey={(record) => `${record.chapter_number}-${record.title || ''}`}
                    size="small"
                    columns={editorColumns}
                    dataSource={rows}
                    pagination={false}
                    scroll={{ x: 1120 }}
                  />
                </Space>
              ),
            },
            {
              key: 'json',
              label: 'JSON',
              children: (
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Text type="secondary">用于批量调整章节结构、导入外部规划或保留模型返回的扩展字段。</Text>
                  <TextArea
                    value={jsonDraft}
                    onChange={(event) => setJsonDraft(event.target.value)}
                    autoSize={{ minRows: 16, maxRows: 30 }}
                    style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' }}
                  />
                  {jsonError ? <Text type="danger">{jsonError}</Text> : null}
                  <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
                    <Button onClick={() => setJsonDraft(JSON.stringify(normalizeChapterPlan({ ...chapterPlan, chapters: rows }), null, 2))}>
                      同步编辑表
                    </Button>
                    <Button type="primary" loading={saving} onClick={saveJson}>保存 JSON</Button>
                  </Space>
                </Space>
              ),
            },
            {
              key: 'actions',
              label: '生产动作',
              children: (
                <Table
                  rowKey="chapter_number"
                  size="small"
                  columns={chapterColumns}
                  dataSource={rows}
                  pagination={false}
                />
              ),
            },
          ]}
        />
      )}
    </Space>
  )
}

function EpisodeWorkbenchTab({
  projectId,
  chapters,
  activeChapterNumber,
  onActiveChapterChange,
  activeChapter,
  contentForChapter,
  isChapterActionLoading,
  comicPageCount,
  setComicPageCount,
  comicStyle,
  setComicStyle,
  columnWidths,
  setColumnWidths,
  startHorizontalResize,
  projectAssets,
  assetDetails,
  characterDetails,
  savingContentId,
  linkingAsset,
  onGenerateChapterOutline,
  onRegenerateChapterOutlineScenes,
  onGenerateNovelBody,
  onRefineNovelBody,
  onSaveContentAsAsset,
  onExtractContinuity,
  continuityExtracting,
  onOpenFanqiePublish,
  onGenerateScript,
  onGenerateStoryboard,
  onMatchReferenceAssets,
  referenceMatching,
  onBatchGenerateStoryboardImages,
  onSplitComicPages,
  onSaveContent,
  onUpdateStoryboardPanelReferences,
  onLinkReferenceAsset,
  onSendImagePrompt,
  onOpenVideoGeneration,
  onOpenPrevis,
  inlineImages,
  inlineImageLoadingKey,
  pendingImageTaskKey,
  pendingImageTaskId,
  batchStoryboardImageChapter,
  defaultImageModelName,
  defaultImageSupportsReferenceImages,
  selectedCreativeSkillIds,
  onCreativeSkillIdsChange,
  compact,
}: {
  projectId: string
  chapters: ChapterPlanItem[]
  activeChapterNumber: number
  onActiveChapterChange: (chapterNumber: number) => void
  activeChapter: ChapterPlanItem | null
  contentForChapter: (contentType: string, chapterNumber: number) => ProjectContent | undefined
  isChapterActionLoading: (action: ChapterAction, chapterNumber: number) => boolean
  comicPageCount: number
  setComicPageCount: (value: number) => void
  comicStyle: string
  setComicStyle: (value: string) => void
  columnWidths: { outline: number; prose: number }
  setColumnWidths: React.Dispatch<React.SetStateAction<{ outline: number; prose: number }>>
  startHorizontalResize: (
    event: React.MouseEvent,
    options: { initial: number; min: number; max: number; onChange: (value: number) => void },
  ) => void
  projectAssets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  characterDetails: Record<string, CharacterReferenceSummary>
  savingContentId: string | null
  linkingAsset: boolean
  onGenerateChapterOutline: (chapterNumber: number) => void
  onRegenerateChapterOutlineScenes: (chapterNumber: number) => void
  onGenerateNovelBody: (chapterNumber: number) => void
  onRefineNovelBody: (chapterNumber: number, instruction: string) => void
  onSaveContentAsAsset: (contentId: string) => void
  onExtractContinuity: (contentId: string) => void
  continuityExtracting: boolean
  onOpenFanqiePublish: () => void
  onGenerateScript: (chapterNumber: number) => void
  onGenerateStoryboard: (chapterNumber: number) => void
  onMatchReferenceAssets: (contentId: string) => void
  referenceMatching: boolean
  onBatchGenerateStoryboardImages: (chapterNumber: number) => void
  onSplitComicPages: (chapterNumber: number) => void
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => void
  onUpdateStoryboardPanelReferences: (
    contentId: string,
    panelNumber: number,
    referenceAssetIds: string[],
  ) => void
  onLinkReferenceAsset: (assetId: string, role: string, metadata?: Record<string, any>) => void
  onSendImagePrompt: (prompt: string, context?: ImagePromptContext) => void
  onOpenVideoGeneration: (prompt: string, context?: VideoGenerationContext) => void
  onOpenPrevis: (storyboardContentId: string, panelNumber: number, title?: string) => void
  inlineImages: Record<string, InlineGeneratedImage>
  inlineImageLoadingKey: string | null
  pendingImageTaskKey?: string
  pendingImageTaskId?: string
  batchStoryboardImageChapter: number | null
  defaultImageModelName: string
  defaultImageSupportsReferenceImages: boolean
  selectedCreativeSkillIds: string[]
  onCreativeSkillIdsChange: (skillIds: string[]) => void
  compact: boolean
}) {
  const chapterOutline = contentForChapter('chapter_outline', activeChapterNumber)
  const novelBody = contentForChapter('novel_body', activeChapterNumber)
  const script = contentForChapter('script', activeChapterNumber)
  const storyboard = contentForChapter('storyboard', activeChapterNumber)
  const comic = contentForChapter('comic_pages', activeChapterNumber)
  const { theme } = useTheme()
  const themedWorkbenchHeaderStyle = createWorkbenchHeaderStyle(theme)
  const themedCompactBlockStyle = createCompactBlockStyle(theme)
  const [writingStage, setWritingStage] = useState<'chapter_outline' | 'novel_body' | 'novel_body_refine'>('novel_body')
  const [writingPreflight, setWritingPreflight] = useState<WritingPreflight | null>(null)
  const [writingPreflightLoading, setWritingPreflightLoading] = useState(false)
  const referenceAssetOptions = useMemo(
    () =>
      projectAssets
        .filter((asset) => ['character', 'background', 'style', 'world', 'reference'].includes(asset.role))
        .map((asset) => {
          const detail = assetDetails[asset.asset_id]
          const roleLabel = referenceRoleOptions.find((item) => item.value === asset.role)?.label || asset.role
          const title =
            asset.metadata?.label ||
            asset.metadata?.character_name ||
            asset.metadata?.source_title ||
            detail?.title ||
            asset.asset_id
          return {
            label: `${roleLabel} · ${title}`,
            value: asset.asset_id,
          }
        }),
    [projectAssets, assetDetails],
  )
  const [outlineDraft, setOutlineDraft] = useState<Record<string, any>>({})
  const [sceneDrafts, setSceneDrafts] = useState<any[]>([])
  const [novelDraft, setNovelDraft] = useState('')
  const [novelRefineInstruction, setNovelRefineInstruction] = useState('')
  const [comicDrafts, setComicDrafts] = useState<any[]>([])
  const [editingStoryboardPrompt, setEditingStoryboardPrompt] = useState<number | null>(null)
  const [storyboardPromptDraft, setStoryboardPromptDraft] = useState('')
  const writingStageMeta = useMemo(
    () =>
      ({
        chapter_outline: {
          label: '章节细纲',
          hint: '检查这一话的结构、场景和推进是否齐备。',
        },
        novel_body: {
          label: '正文',
          hint: '检查这一话的细纲与正文生成前置条件。',
        },
        novel_body_refine: {
          label: '正文润色',
          hint: '检查已有正文是否适合做定向改写。',
        },
      }) as const,
    [],
  )
  const storyboardVideoOutputs = useMemo(() => {
    if (!storyboard?.id) return new Map<number, ProjectAssetLink[]>()
    const outputs = new Map<number, ProjectAssetLink[]>()
    projectAssets.forEach((link) => {
      const metadata = link.metadata || {}
      const panelNumber = Number(metadata.source_index)
      if (
        link.role !== 'output' ||
        metadata.source !== 'video_generation' ||
        metadata.source_type !== 'storyboard_panel' ||
        link.content_id !== storyboard.id ||
        !Number.isFinite(panelNumber)
      ) {
        return
      }
      outputs.set(panelNumber, [...(outputs.get(panelNumber) || []), link])
    })
    return outputs
  }, [projectAssets, storyboard?.id])
  const writingMethodOptions = useMemo(() => {
    const merged = new Map<string, { label: string; value: string }>()
    ;(writingPreflight?.method_candidates || []).forEach((candidate: WritingMethodCandidate) => {
      merged.set(candidate.id, {
        label: `${candidate.title}${candidate.auto_apply ? ' · 自动' : ''}`,
        value: candidate.id,
      })
    })
    selectedCreativeSkillIds.forEach((skillId) => {
      if (!merged.has(skillId)) {
        merged.set(skillId, {
          label: `${skillId} · 已选`,
          value: skillId,
        })
      }
    })
    return Array.from(merged.values())
  }, [selectedCreativeSkillIds, writingPreflight?.method_candidates])
  const selectedWritingMethods = useMemo(() => {
    const candidateMap = new Map((writingPreflight?.method_candidates || []).map((item) => [item.id, item]))
    return selectedCreativeSkillIds.map((skillId) => candidateMap.get(skillId)).filter(Boolean)
  }, [selectedCreativeSkillIds, writingPreflight?.method_candidates])
  const writingPreflightChecks = writingPreflight?.checks || []
  const writingPreflightBlockers = writingPreflight?.blockers || []
  const writingPreflightReady = Boolean(writingPreflight?.ready)

  useEffect(() => {
    if (!projectId) {
      setWritingPreflight(null)
      setWritingPreflightLoading(false)
      return
    }

    const contentId =
      writingStage === 'novel_body_refine'
        ? novelBody?.id
        : writingStage === 'chapter_outline'
          ? chapterOutline?.id
          : undefined

    let cancelled = false
    setWritingPreflightLoading(true)
    ;(async () => {
      try {
        const response = await getCreativeProjectWritingPreflight(projectId, {
          chapterNumber: activeChapterNumber,
          stage: writingStage,
          contentId,
        })
        if (cancelled) return
        setWritingPreflight(response?.data || null)
      } catch {
        if (!cancelled) setWritingPreflight(null)
      } finally {
        if (!cancelled) setWritingPreflightLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [projectId, activeChapterNumber, chapterOutline?.id, novelBody?.id, writingStage])

  useEffect(() => {
    setOutlineDraft({
      title: chapterOutline?.data?.title || '',
      summary: chapterOutline?.data?.summary || '',
      objective: chapterOutline?.data?.objective || '',
      keywordsText: (chapterOutline?.data?.keywords || []).join('\n'),
      keyDialoguesText: (chapterOutline?.data?.key_dialogues || []).join('\n'),
      foreshadowingText: (chapterOutline?.data?.foreshadowing || []).join('\n'),
      ending_hook: chapterOutline?.data?.ending_hook || '',
      continuityNotesText: Array.isArray(chapterOutline?.data?.continuity_notes)
        ? chapterOutline?.data?.continuity_notes.join('\n')
        : chapterOutline?.data?.continuity_notes || '',
    })
    setSceneDrafts((chapterOutline?.data?.scenes || []).map((scene: any, index: number) => ({
      scene_number: scene.scene_number || index + 1,
      title: scene.title || '',
      location: scene.location || '',
      purpose: scene.purpose || '',
      scene_role: scene.scene_role || '',
      objective: scene.objective || '',
      conflict: scene.conflict || '',
      beatsText: (scene.beats || []).join('\n'),
      action: scene.action || '',
      key_dialogue: scene.key_dialogue || '',
      emotion: scene.emotion || '',
      emotional_turn: scene.emotional_turn || '',
      visual_focus: scene.visual_focus || '',
      shot_design: scene.shot_design || '',
      image_prompt: scene.image_prompt || '',
    })))
  }, [chapterOutline?.id, activeChapterNumber])

  useEffect(() => {
    setNovelDraft(novelBody?.text_content || novelBody?.data?.content || '')
  }, [novelBody?.id, activeChapterNumber])

  useEffect(() => {
    setEditingStoryboardPrompt(null)
    setStoryboardPromptDraft('')
  }, [storyboard?.id, activeChapterNumber])

  useEffect(() => {
    setComicDrafts((comic?.data?.pages || []).map((page: any, index: number) => ({
      page_number: page.page_number || index + 1,
      title: page.title || '',
      content: page.content || '',
      panel_count: page.panel_count || '',
      image_prompt: page.image_prompt || '',
      source_panel_numbers: page.source_panel_numbers || [],
      character_ids: page.character_ids || [],
      portrait_node_ids: page.portrait_node_ids || [],
      portrait_version_ids: page.portrait_version_ids || [],
      reference_asset_ids: page.reference_asset_ids || [],
      reference_notes: page.reference_notes || [],
    })))
  }, [comic?.id, activeChapterNumber])

  if (!chapters.length) {
    return <Empty description="先生成章节规划，再进入单话工作台" />
  }

  const canGenerateNovel = Boolean(chapterOutline)
  const canGenerateStoryboard = Boolean(script)
  const canGenerateComic = Boolean(storyboard)

  const sceneCount = sceneDrafts.length || chapterOutline?.data?.scenes?.length || 0
  const scriptSceneCount = script?.data?.scenes?.length || 0
  const panelCount = storyboard?.data?.panels?.length || 0
  const pageCount = comicDrafts.length || comic?.data?.pages?.length || 0
  const storyboardPanels = Array.isArray(storyboard?.data?.panels) ? storyboard?.data?.panels : []
  const storyboardPanelsWithPrompts = storyboardPanels.filter((panel: any) => panel?.image_prompt)
  const storyboardReferencePlans = storyboardPanelsWithPrompts.map((panel: any) =>
    buildStoryboardPanelReferencePlan({
      panel,
      projectAssets,
      characterDetails,
      supportsReferenceImages: defaultImageSupportsReferenceImages,
    }),
  )
  const storyboardGeneratedCount = storyboardPanelsWithPrompts.filter((panel: any) =>
    inlineImages[imageContextKey({
      contentId: storyboard?.id,
      sourceType: 'storyboard_panel',
      sourceIndex: panel.panel_number,
      chapterNumber: activeChapterNumber,
    })],
  ).length
  const storyboardReferenceSummary = buildStoryboardReferenceSummary(
    storyboardReferencePlans,
    storyboardGeneratedCount,
    defaultImageSupportsReferenceImages,
  )
  const episodeOutputs = [
    { label: '细纲', ready: Boolean(chapterOutline) },
    { label: '正文', ready: Boolean(novelBody) },
    { label: '脚本', ready: Boolean(script) },
    { label: '分镜', ready: Boolean(storyboard) },
  ]
  const nextEpisodeAction = !chapterOutline
    ? '先完成细纲'
    : !novelBody
      ? '生成正文'
      : !script
        ? '生成脚本'
        : !storyboard
          ? '拆分镜'
          : '补充参考与画面'
  const linesFromText = (value: string) =>
    String(value || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
  const buildChapterOutlineData = () => ({
    ...chapterOutline?.data,
    title: outlineDraft.title || '',
    summary: outlineDraft.summary || '',
    objective: outlineDraft.objective || '',
    keywords: linesFromText(outlineDraft.keywordsText),
    key_dialogues: linesFromText(outlineDraft.keyDialoguesText),
    foreshadowing: linesFromText(outlineDraft.foreshadowingText),
    ending_hook: outlineDraft.ending_hook || '',
    continuity_notes: linesFromText(outlineDraft.continuityNotesText),
    scenes: sceneDrafts.map((scene, index) => ({
      ...scene,
      scene_number: index + 1,
      beats: linesFromText(scene.beatsText),
    })),
  })
  const renderInlineImage = (context: ImagePromptContext) => {
    const key = imageContextKey(context)
    return (
      <InlineImageResult
        image={inlineImages[key]}
        loading={inlineImageLoadingKey === key}
        taskId={inlineImages[key]?.taskId || (pendingImageTaskKey === key ? pendingImageTaskId : undefined)}
        onPromoteReference={
          inlineImages[key]?.assetId
            ? (role) => onLinkReferenceAsset(inlineImages[key].assetId!, role, {
                label: `${context.sourceTitle || context.sourceType || '生成图'}参考`,
                source_type: context.sourceType,
                source_index: context.sourceIndex,
                chapter_number: context.chapterNumber,
                promoted_from_output: true,
                promoted_at: new Date().toISOString(),
              })
            : undefined
        }
      />
    )
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
      <div style={{ ...themedWorkbenchHeaderStyle, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Space direction="vertical" size={4} style={{ minWidth: 0, flex: '1 1 280px' }}>
          <Space size={8} wrap>
            <Title level={4} style={{ margin: 0 }}>第 {activeChapterNumber} 话</Title>
            <Tag color="processing">制作单元</Tag>
            {comic ? <Tag color="purple">漫画页已拆分</Tag> : null}
          </Space>
          <Text type="secondary" ellipsis={{ tooltip: activeChapter?.title || '未命名章节' }}>
            {activeChapter?.title || '未命名章节'} · 下一步：{nextEpisodeAction}
          </Text>
        </Space>
        <Select
          aria-label="选择制作章节"
          value={activeChapterNumber}
          style={{ width: 240, maxWidth: '100%' }}
          options={chapters.map((chapter) => ({
            value: chapter.chapter_number,
            label: `第 ${chapter.chapter_number} 话 · ${chapter.title || '未命名章节'}`,
          }))}
          onChange={onActiveChapterChange}
        />
      </div>

      <WorkbenchSection
        title="写作门禁"
        extra={
          <Space size={8} wrap>
            <Tag color={writingPreflightReady ? 'green' : 'warning'}>
              {writingPreflightReady ? '可直接生成' : '存在阻塞'}
            </Tag>
            <Tag>{writingStageMeta[writingStage].label}</Tag>
          </Space>
        }
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Alert
            type={writingPreflightReady ? 'success' : 'warning'}
            showIcon
            message={writingPreflightReady ? '当前章节门禁已通过' : '当前章节还缺少前置条件'}
            description={writingPreflightLoading ? '正在检查当前章节的写作门禁...' : writingPreflight?.next_action || '等待检查结果'}
          />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: compact ? 'minmax(0, 1fr)' : '180px minmax(0, 1fr)',
              gap: 10,
              alignItems: 'start',
            }}
          >
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text strong>检查阶段</Text>
              <Segmented
                value={writingStage}
                options={[
                  { label: '章节细纲', value: 'chapter_outline' },
                  { label: '正文', value: 'novel_body' },
                  { label: '正文润色', value: 'novel_body_refine' },
                ]}
                onChange={(value) => setWritingStage(value as 'chapter_outline' | 'novel_body' | 'novel_body_refine')}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {writingStageMeta[writingStage].hint}
              </Text>
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text strong>方法包</Text>
              <Select
                mode="multiple"
                allowClear
                loading={writingPreflightLoading}
                placeholder="选择项目可用的写作方法包"
                value={selectedCreativeSkillIds}
                options={writingMethodOptions}
                onChange={(values) => onCreativeSkillIdsChange((values as string[]).filter(Boolean))}
                style={{ width: '100%' }}
                maxTagCount="responsive"
              />
              <Space wrap size={[6, 6]}>
                <Tag color="blue">{selectedCreativeSkillIds.length} 个方法包已保存</Tag>
                {selectedWritingMethods.map((item) =>
                  item ? (
                    <Tag key={item.id} color={item.auto_apply ? 'geekblue' : 'default'}>
                      {item.title}
                      {item.auto_apply ? ' · 自动' : ''}
                    </Tag>
                  ) : null,
                )}
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                选中的方法包会写入 `settings.creative_skill_ids`，并在上下文中按兼容性进入 T6。
              </Text>
            </Space>
          </div>
          <Space wrap size={[6, 6]}>
            {writingPreflightChecks.map((check) => (
              <Tag key={check.id} color={check.status === 'pass' ? 'green' : 'red'}>
                {check.label}
              </Tag>
            ))}
          </Space>
          {writingPreflightBlockers.length ? (
            <List
              size="small"
              bordered={false}
              dataSource={writingPreflightBlockers}
              renderItem={(item) => (
                <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Text strong style={{ fontSize: 12 }}>
                      {item.label}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {item.detail}
                    </Text>
                  </Space>
                </List.Item>
              )}
            />
          ) : null}
        </Space>
      </WorkbenchSection>

      <div
        aria-label="当前话生产状态"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(116px, 1fr))',
          border: `1px solid ${theme.borderLight}`,
          background: theme.bgElevated,
        }}
      >
        {episodeOutputs.map((item, index) => (
          <div
            key={item.label}
            style={{
              padding: '9px 12px',
              borderRight: index < episodeOutputs.length - 1 ? `1px solid ${theme.borderLight}` : 'none',
              minWidth: 0,
            }}
          >
            <Text type="secondary" style={{ display: 'block', fontSize: 11 }}>{item.label}</Text>
            <Text strong style={{ color: item.ready ? theme.primary : theme.textSecondary, fontSize: 13 }}>
              {item.ready ? '已就绪' : '待生产'}
            </Text>
          </div>
        ))}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: compact
            ? 'minmax(0, 1fr)'
            : `${columnWidths.outline}px 10px ${columnWidths.prose}px 10px minmax(300px, 360px)`,
          gap: 8,
          alignItems: 'stretch',
          height: compact ? undefined : 'calc(100vh - 320px)',
          minHeight: 640,
        }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <WorkbenchSection
          title="当前细纲"
          extra={
            <Space>
              {chapterOutline ? (
                <Button
                  size="small"
                  loading={savingContentId === chapterOutline.id}
                  onClick={() =>
                    onSaveContent(chapterOutline.id, {
                      data: buildChapterOutlineData(),
                      text_content: [
                        outlineDraft.summary,
                        outlineDraft.objective,
                        ...sceneDrafts.map((scene, index) =>
                          `场景 ${index + 1} ${scene.title || scene.location || ''}\n${scene.action || scene.objective || ''}`,
                        ),
                      ]
                        .filter(Boolean)
                        .join('\n\n'),
                    })
                  }
                >
                  保存
                </Button>
              ) : null}
              <Button
                type="primary"
                size="small"
                icon={<ThunderboltOutlined />}
                loading={isChapterActionLoading('chapter_outline', activeChapterNumber)}
                onClick={() => onGenerateChapterOutline(activeChapterNumber)}
              >
                {chapterOutline ? '重生成细纲' : '生成细纲'}
              </Button>
            </Space>
          }
        >
          {chapterOutline ? (
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Text type="secondary">本页负责这一话的写作清单，正文和漫画会使用保存后的细纲。</Text>
              <EditorField label="本话标题" hint="用于目录、正文标题和后续漫画页标题。">
                <Input
                  value={outlineDraft.title}
                  placeholder="例如：第一话：神坛坠落与降维打击"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, title: event.target.value }))}
                />
              </EditorField>
              <EditorField label="本话摘要" hint="讲清起因、冲突、反转和落点，正文生成会优先参考这里。">
                <TextArea
                  rows={4}
                  value={outlineDraft.summary}
                  placeholder="这一话完整发生了什么..."
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, summary: event.target.value }))}
                />
              </EditorField>
              <EditorField label="写作目标" hint="告诉 AI 这一话要立住什么人物、推进什么关系、制造什么爽点。">
                <TextArea
                  rows={3}
                  value={outlineDraft.objective}
                  placeholder="例如：立住女主智商碾压，制造片场救火爽点..."
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, objective: event.target.value }))}
                />
              </EditorField>
              <EditorField label="关键词" hint="每行一个，作为正文、脚本和漫画分镜的关键词锚点。">
                <TextArea
                  rows={3}
                  value={outlineDraft.keywordsText}
                  placeholder="版权剽窃&#10;降维打击&#10;片场救火"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, keywordsText: event.target.value }))}
                />
              </EditorField>
              <EditorField label="关键台词" hint="每行一句，可直接进入正文、脚本对白或漫画气泡。">
                <TextArea
                  rows={4}
                  value={outlineDraft.keyDialoguesText}
                  placeholder="例如：明天下午三点，花园喷泉第三块砖下，我知道你不是 NPC。"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, keyDialoguesText: event.target.value }))}
                />
              </EditorField>
              <EditorField label="伏笔" hint="后续章节要回收的线索，每行一条。">
                <TextArea
                  rows={3}
                  value={outlineDraft.foreshadowingText}
                  placeholder="例如：合同编号异常，为后续版权反击埋线。"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, foreshadowingText: event.target.value }))}
                />
              </EditorField>
              <EditorField label="结尾钩子" hint="这一话最后吊住读者继续看下一话的悬念。">
                <TextArea
                  rows={2}
                  value={outlineDraft.ending_hook}
                  placeholder="例如：她抬头看向监控，像是知道屏幕后的人是谁。"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, ending_hook: event.target.value }))}
                />
              </EditorField>
              <EditorField label="连续性说明" hint="给下一话、脚本和分镜使用，避免设定和人物状态断掉。">
                <TextArea
                  rows={3}
                  value={outlineDraft.continuityNotesText}
                  placeholder="每行一条连续性备注..."
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, continuityNotesText: event.target.value }))}
                />
              </EditorField>
            </Space>
          ) : (
            <>
              <InfoBlock title="本话标题" text={activeChapter?.title} compact />
              <InfoBlock title="目标 / 冲突" text={[activeChapter?.goal, activeChapter?.conflict].filter(Boolean).join('；')} compact />
              <InfoListBlock title="关键事件" items={activeChapter?.key_events || []} />
            </>
          )}
        </WorkbenchSection>

        {chapterOutline ? (
          <WorkbenchSection
            title="场景编辑"
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<ThunderboltOutlined />}
                  loading={isChapterActionLoading('chapter_outline_scenes', activeChapterNumber)}
                  onClick={() => onRegenerateChapterOutlineScenes(activeChapterNumber)}
                >
                  重生成场景
                </Button>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    setSceneDrafts((prev) => [
                      ...prev,
                      {
                        scene_number: prev.length + 1,
                        title: '',
                        location: '',
                        purpose: '',
                        scene_role: '',
                        objective: '',
                        conflict: '',
                        beatsText: '',
                        action: '',
                        key_dialogue: '',
                        emotion: '',
                        emotional_turn: '',
                        visual_focus: '',
                        shot_design: '',
                        image_prompt: '',
                      },
                    ])
                  }
                >
                  添加场景
                </Button>
                <Button
                  size="small"
                  type="primary"
                  loading={savingContentId === chapterOutline.id}
                  onClick={() =>
                    onSaveContent(chapterOutline.id, {
                      data: buildChapterOutlineData(),
                      text_content: [
                        outlineDraft.summary,
                        ...sceneDrafts.map((scene) =>
                          `场景 ${scene.scene_number} ${scene.title || scene.location || ''}\n${scene.action || scene.objective || ''}`,
                        ),
                      ]
                        .filter(Boolean)
                        .join('\n\n'),
                    })
                  }
                >
                  保存场景
                </Button>
              </Space>
            }
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              {sceneDrafts.map((scene: any, index: number) => (
                <div key={`${scene.scene_number}-${index}`} style={themedCompactBlockStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Text strong>场景 {index + 1}</Text>
                      <Space>
                        {scene.image_prompt ? (
                          <Button
                            size="small"
                            onClick={() =>
                              onSendImagePrompt(scene.image_prompt, {
                                contentId: chapterOutline.id,
                                sourceType: 'chapter_outline_scene',
                                sourceIndex: scene.scene_number || index + 1,
                                sourceTitle: scene.title || scene.location || `场景 ${index + 1}`,
                                chapterNumber: activeChapterNumber,
                              })
                            }
                          >
                            生图
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          danger
                          onClick={() => setSceneDrafts((prev) => prev.filter((_, itemIndex) => itemIndex !== index))}
                        >
                          删除
                        </Button>
                      </Space>
                    </Space>
                    <EditorField label="场景标题" hint="用于快速识别这一场戏。">
                      <Input
                        value={scene.title}
                        placeholder="例如：不属于自己的眼睛"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, title: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="地点 / 时间 / 氛围" hint="给正文、脚本和分镜提供空间锚点。">
                      <Input
                        value={scene.location}
                        placeholder="例如：豪门别墅管家卧室 / 深夜 / 压抑"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, location: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="场景位置" hint="标记这个场景在单话结构里的作用位置。">
                      <Input
                        value={scene.scene_role}
                        placeholder="开场钩子 / 冲突升级 / 反转 / 情绪落点 / 结尾钩子"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, scene_role: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="场景作用" hint="说明这个场景为什么存在，推进什么信息、情绪或关系。">
                      <TextArea
                        rows={2}
                        value={scene.purpose}
                        placeholder="例如：开篇即制造错位感，让主角意识到自己身份异常。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, purpose: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="场景冲突" hint="谁和谁的目标冲突，压力来自哪里。">
                      <TextArea
                        rows={2}
                        value={scene.conflict}
                        placeholder="例如：主角想确认身份，系统和环境不断制造误导。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, conflict: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="剧情节拍" hint="每行一个具体动作、镜头或信息揭示，后续分镜会按它拆。">
                      <TextArea
                        rows={4}
                        value={scene.beatsText}
                        placeholder="镜子里出现陌生脸&#10;手机弹出系统提示&#10;主角发现合同不对劲"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, beatsText: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="剧情动作" hint="人物怎么移动、做什么决定、信息如何推进。">
                      <TextArea
                        rows={3}
                        value={scene.action}
                        placeholder="描述这一场戏的主要动作和调度..."
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, action: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="关键台词" hint="可直接进入正文、脚本对白或漫画气泡。">
                      <TextArea
                        rows={2}
                        value={scene.key_dialogue}
                        placeholder="例如：明天下午三点，花园喷泉第三块砖下，我知道你不是 NPC。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, key_dialogue: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="主要情绪" hint="这一场戏的情绪底色。">
                      <Input
                        value={scene.emotion}
                        placeholder="例如：压抑、怀疑、惊醒、冷静"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, emotion: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="情绪转折" hint="场景中情绪如何变化，帮助正文和分镜做节奏。">
                      <Input
                        value={scene.emotional_turn}
                        placeholder="例如：迷茫 -> 惊醒 -> 冷静掌控"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, emotional_turn: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="画面核心看点" hint="漫画/生图最该抓住的视觉重点。">
                      <TextArea
                        rows={2}
                        value={scene.visual_focus}
                        placeholder="例如：镜中陌生脸、冷色卧室、红色系统警告。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, visual_focus: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="镜头设计" hint="景别、角度、构图、运动和光线，用于后续分镜。">
                      <TextArea
                        rows={2}
                        value={scene.shot_design}
                        placeholder="例如：低角度中景，镜中反射，冷蓝侧光，人物居中压迫构图。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, shot_design: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="生图提示词" hint="可直接送到图片生成，写清角色、地点、动作、表情、构图、光线、风格和一致性要求。">
                      <TextArea
                        rows={4}
                        value={scene.image_prompt}
                        placeholder="半写实彩色漫画，年轻管家在冷色卧室中凝视镜子，镜中是不属于自己的脸..."
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, image_prompt: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    {renderInlineImage({
                      contentId: chapterOutline.id,
                      sourceType: 'chapter_outline_scene',
                      sourceIndex: scene.scene_number || index + 1,
                      chapterNumber: activeChapterNumber,
                    })}
                  </Space>
                </div>
              ))}
            </Space>
          </WorkbenchSection>
        ) : null}
        </Space>

        {!compact ? (
          <ResizeHandle
            onMouseDown={(event) =>
              startHorizontalResize(event, {
                initial: columnWidths.outline,
                min: 260,
                max: 560,
                onChange: (value) => setColumnWidths((prev) => ({ ...prev, outline: value })),
              })
            }
          />
        ) : null}

        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <WorkbenchSection
          title="正文"
          extra={
            <Space size={8}>
              <Tooltip title={canGenerateNovel ? '' : '先生成细纲'}>
                <Button
                  size="small"
                  icon={<FileTextOutlined />}
                  disabled={!canGenerateNovel}
                  loading={isChapterActionLoading('novel_body', activeChapterNumber)}
                  onClick={() => onGenerateNovelBody(activeChapterNumber)}
                >
                  {novelBody ? '重生成正文' : '生成正文'}
                </Button>
              </Tooltip>
              {novelBody ? (
                <Button
                  size="small"
                  icon={<FolderAddOutlined />}
                  onClick={() => onSaveContentAsAsset(novelBody.id)}
                >
                  存为素材
                </Button>
              ) : null}
              {novelBody ? (
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  loading={continuityExtracting}
                  onClick={() => onExtractContinuity(novelBody.id)}
                >
                  提取连续性
                </Button>
              ) : null}
              <Button
                size="small"
                icon={<CloudUploadOutlined />}
                disabled={!novelBody}
                onClick={onOpenFanqiePublish}
              >
                保存到番茄草稿
              </Button>
            </Space>
          }
        >
          {novelBody ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <TextArea
                rows={28}
                value={novelDraft}
                onChange={(event) => setNovelDraft(event.target.value)}
                placeholder="这里可以人工润色本话正文，保存后会覆盖当前版本内容"
                style={{ minHeight: 640 }}
              />
              <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                <Text type="secondary">字数：{novelDraft.length}</Text>
                <Button
                  type="primary"
                  loading={savingContentId === novelBody.id}
                  onClick={() =>
                    onSaveContent(novelBody.id, {
                      text_content: novelDraft,
                      data: { ...novelBody.data, content: novelDraft, word_count: novelDraft.length },
                    })
                  }
                >
                  保存正文
                </Button>
              </Space>
              <EditorField label="中文微调" hint="告诉 AI 如何改正文，例如加强冲突、压缩对白、增加爽点。会覆盖保存当前正文。">
                <Space.Compact style={{ width: '100%' }}>
                  <Input
                    value={novelRefineInstruction}
                    onChange={(event) => setNovelRefineInstruction(event.target.value)}
                    placeholder="输入正文修改要求，例如：加强冲突，压缩对白，让反转更爽"
                    onPressEnter={() => {
                      onRefineNovelBody(activeChapterNumber, novelRefineInstruction)
                    }}
                  />
                  <Button
                    type="primary"
                    loading={isChapterActionLoading('novel_body_refine', activeChapterNumber)}
                    onClick={() => onRefineNovelBody(activeChapterNumber, novelRefineInstruction)}
                  >
                    发送
                  </Button>
                </Space.Compact>
              </EditorField>
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本话还没有正文" />
          )}
        </WorkbenchSection>
      </Space>

      {!compact ? (
        <ResizeHandle
          onMouseDown={(event) =>
            startHorizontalResize(event, {
              initial: columnWidths.prose,
              min: 360,
              max: 760,
              onChange: (value) => setColumnWidths((prev) => ({ ...prev, prose: value })),
            })
          }
        />
      ) : null}

      <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <ReferenceCardsPanel
          assets={projectAssets}
          assetDetails={assetDetails}
          loading={linkingAsset}
          onLinkAsset={onLinkReferenceAsset}
        />

        <WorkbenchSection
          title={`脚本${scriptSceneCount ? ` · ${scriptSceneCount}` : ''}`}
          extra={
            <Space size={6}>
              {script ? (
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() => openProjectTextPreview(script.title || `第 ${activeChapterNumber} 章脚本`, buildScriptMarkdown(script))}
                >
                  预览
                </Button>
              ) : null}
              {script ? (
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  loading={referenceMatching}
                  disabled={!referenceAssetOptions.length}
                  onClick={() => onMatchReferenceAssets(script.id)}
                >
                  匹配参考卡
                </Button>
              ) : null}
              {script ? (
                <Button size="small" icon={<FolderAddOutlined />} onClick={() => onSaveContentAsAsset(script.id)}>
                  存为素材
                </Button>
              ) : null}
              {script ? (
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() =>
                    downloadTextFile(
                      `${projectMarkdownFilename(script.title || `chapter-${activeChapterNumber}`, 'script')}.md`,
                      buildScriptMarkdown(script),
                    )
                  }
                >
                  导出脚本
                </Button>
              ) : null}
              <Button
                size="small"
                icon={<FileTextOutlined />}
                loading={isChapterActionLoading('script', activeChapterNumber)}
                onClick={() => onGenerateScript(activeChapterNumber)}
              >
                {script ? '重写脚本' : '由细纲生成脚本'}
              </Button>
            </Space>
          }
        >
          {script ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {script.data?.hook ? (
                <div style={themedCompactBlockStyle}>
                  <Text strong>开头钩子</Text>
                  <Paragraph style={{ margin: '6px 0 0' }}>{script.data.hook}</Paragraph>
                </div>
              ) : null}
              {(script.data?.scenes || []).slice(0, 8).map((scene: any) => (
                <div key={scene.scene_number} style={themedCompactBlockStyle}>
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Text strong>场景 {scene.scene_number} · {scene.location || '未设定地点'}</Text>
                      {scene.image_prompt ? (
                        <Button
                          size="small"
                          onClick={() =>
                            onSendImagePrompt(scene.image_prompt, {
                              contentId: script.id,
                              sourceType: 'script_scene',
                              sourceIndex: scene.scene_number,
                              sourceTitle: scene.location || `脚本场景 ${scene.scene_number}`,
                              chapterNumber: activeChapterNumber,
                              referenceAssetIds: scene.reference_asset_ids || [],
                            })
                          }
                        >
                          生图
                        </Button>
                      ) : null}
                    </Space>
                    <Text type="secondary">{[scene.camera_hint, scene.emotion].filter(Boolean).join(' · ')}</Text>
                    <ReferenceAssetPreviewStrip
                      assetIds={scene.reference_asset_ids || []}
                      notes={scene.reference_notes || []}
                      assets={projectAssets}
                      assetDetails={assetDetails}
                    />
                    <Paragraph style={{ margin: 0 }}>{scene.action}</Paragraph>
                    {(scene.dialogue || []).length ? (
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        {(scene.dialogue || []).slice(0, 4).map((line: any, index: number) => (
                          <Text key={`${line.character || 'dialogue'}-${index}`}>
                            {line.character ? `${line.character}：` : ''}{line.line || line}
                          </Text>
                        ))}
                      </Space>
                    ) : null}
                    {renderInlineImage({
                      contentId: script.id,
                      sourceType: 'script_scene',
                      sourceIndex: scene.scene_number,
                      chapterNumber: activeChapterNumber,
                    })}
                  </Space>
                </div>
              ))}
              {script.data?.ending_hook ? (
                <div style={themedCompactBlockStyle}>
                  <Text strong>结尾钩子</Text>
                  <Paragraph style={{ margin: '6px 0 0' }}>{script.data.ending_hook}</Paragraph>
                </div>
              ) : null}
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本话还没有脚本，先由细纲生成脚本" />
          )}
        </WorkbenchSection>

        <WorkbenchSection
          title={`分镜${panelCount ? ` · ${panelCount}` : ''}`}
          extra={
            <Space size={6}>
              {storyboard ? (
                <Tooltip
                  title={
                    defaultImageSupportsReferenceImages
                      ? '当前默认生图模型会接收参考图'
                      : '当前默认生图模型未声明支持参考图，只会记录参考关系并写入提示词'
                  }
                >
                  <Tag color={defaultImageSupportsReferenceImages ? 'green' : 'orange'}>
                    {defaultImageSupportsReferenceImages ? '参考图可发送' : '仅记录参考'}
                  </Tag>
                </Tooltip>
              ) : null}
              {storyboard ? (
                <Tag color={storyboardReferenceSummary.missingEffectivePlanPanels ? 'orange' : 'blue'}>
                  参考 {storyboardReferenceSummary.effectivePlanPanels}/{storyboardReferenceSummary.promptPanels}
                </Tag>
              ) : null}
              {storyboard ? <Tag color="green">已生图 {storyboardReferenceSummary.generatedPanels}</Tag> : null}
              {storyboard ? (
                <>
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => openProjectTextPreview(storyboard.title || `第 ${activeChapterNumber} 章分镜`, buildStoryboardMarkdown(storyboard))}
                  >
                    预览
                  </Button>
                  <Button
                    size="small"
                    icon={<BranchesOutlined />}
                    loading={referenceMatching}
                    disabled={!referenceAssetOptions.length}
                    onClick={() => onMatchReferenceAssets(storyboard.id)}
                  >
                    匹配参考卡
                  </Button>
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={batchStoryboardImageChapter === activeChapterNumber}
                    onClick={() => onBatchGenerateStoryboardImages(activeChapterNumber)}
                  >
                    批量生图
                  </Button>
                </>
              ) : null}
              <Tooltip title={canGenerateStoryboard ? '' : '先生成脚本'}>
                <Button
                  size="small"
                  icon={<PictureOutlined />}
                  disabled={!canGenerateStoryboard}
                  loading={isChapterActionLoading('storyboard', activeChapterNumber)}
                  onClick={() => onGenerateStoryboard(activeChapterNumber)}
                >
                  {storyboard ? '重拆分镜' : '生成分镜'}
                </Button>
              </Tooltip>
            </Space>
          }
        >
          {storyboard ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <StoryboardReferencePreflight
                summary={storyboardReferenceSummary}
                supportsReferenceImages={defaultImageSupportsReferenceImages}
                hasImageModel={Boolean(defaultImageModelName)}
              />
              {(storyboard.data?.panels || []).slice(0, 10).map((panel: any) => (
                <div key={panel.panel_number} style={themedCompactBlockStyle}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <Text strong>分镜 {panel.panel_number}</Text>
                    {panel.image_prompt ? (
                      <Space size={4}>
                        <Button
                          size="small"
                          onClick={() =>
                            onSendImagePrompt(panel.image_prompt, {
                              contentId: storyboard.id,
                              sourceType: 'storyboard_panel',
                              sourceIndex: panel.panel_number,
                              sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
                              chapterNumber: activeChapterNumber,
                              referenceAssetIds: panel.reference_asset_ids || [],
                              characterIds: panel.character_ids || [],
                              portraitNodeIds: panel.portrait_node_ids || [],
                              portraitVersionIds: panel.portrait_version_ids || [],
                            })
                          }
                        >
                          生图
                        </Button>
                        <Button
                          size="small"
                          icon={<DeploymentUnitOutlined />}
                          onClick={() =>
                            onOpenPrevis(
                              storyboard.id,
                              Number(panel.panel_number),
                              panel.action || `分镜 ${panel.panel_number} · 3D 预演`,
                            )
                          }
                        >
                          3D 预演
                        </Button>
                        <Button
                          size="small"
                          icon={<VideoCameraOutlined />}
                          onClick={() =>
                            onOpenVideoGeneration(
                              panel.video_prompt || buildStoryboardVideoFallbackPrompt(panel),
                              {
                                contentId: storyboard.id,
                                sourceType: 'storyboard_panel',
                                sourceIndex: panel.panel_number,
                                sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
                                chapterNumber: activeChapterNumber,
                                referenceAssetIds: panel.reference_asset_ids || [],
                                characterIds: panel.character_ids || [],
                                portraitNodeIds: panel.portrait_node_ids || [],
                                portraitVersionIds: panel.portrait_version_ids || [],
                                durationSeconds: panel.duration_seconds,
                                generateAudio: panel.generate_audio === true,
                                musicHint: panel.music_hint || '',
                              },
                            )
                          }
                        >
                          视频
                        </Button>
                      </Space>
                    ) : null}
                  </Space>
                  <Text type="secondary">{panel.action || panel.image_prompt}</Text>
                  <ReferenceAssetPreviewStrip
                    assetIds={panel.reference_asset_ids || []}
                    notes={panel.reference_notes || []}
                    assets={projectAssets}
                    assetDetails={assetDetails}
                  />
                  <StoryboardReferenceDiagnostics
                    panel={panel}
                    projectAssets={projectAssets}
                    characterDetails={characterDetails}
                    supportsReferenceImages={defaultImageSupportsReferenceImages}
                  />
                  {panel.image_prompt ? (
                    editingStoryboardPrompt === panel.panel_number ? (
                      <Space direction="vertical" size={6} style={{ width: '100%', marginTop: 8 }}>
                        <Input.TextArea
                          value={storyboardPromptDraft}
                          autoSize={{ minRows: 4, maxRows: 10 }}
                          onChange={(event) => setStoryboardPromptDraft(event.target.value)}
                        />
                        <Space>
                          <Button
                            type="primary"
                            size="small"
                            loading={savingContentId === storyboard.id}
                            disabled={!storyboardPromptDraft.trim()}
                            onClick={() => {
                              const nextData = {
                                ...storyboard.data,
                                panels: (storyboard.data?.panels || []).map((item: any) =>
                                  Number(item.panel_number) === Number(panel.panel_number)
                                    ? { ...item, image_prompt: storyboardPromptDraft.trim() }
                                    : item,
                                ),
                              }
                              onSaveContent(storyboard.id, { data: nextData })
                              setEditingStoryboardPrompt(null)
                            }}
                          >保存提示词</Button>
                          <Button size="small" onClick={() => setEditingStoryboardPrompt(null)}>取消</Button>
                        </Space>
                      </Space>
                    ) : (
                      <Space style={{ width: '100%', justifyContent: 'space-between', marginTop: 6 }} align="start">
                        <Paragraph
                          type="secondary"
                          ellipsis={{ rows: 3, tooltip: panel.image_prompt }}
                          style={{ margin: 0, fontSize: 12, flex: 1 }}
                        >
                          生图提示：{panel.image_prompt}
                        </Paragraph>
                        <Button
                          size="small"
                          type="text"
                          onClick={() => {
                            setStoryboardPromptDraft(panel.image_prompt || '')
                            setEditingStoryboardPrompt(panel.panel_number)
                          }}
                        >改提示词</Button>
                      </Space>
                    )
                  ) : null}
                  <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      本格参考卡：用于指定这一格额外参考的角色、背景、道具或画风素材。
                    </Text>
                    <Select
                      mode="multiple"
                      allowClear
                      size="small"
                      placeholder="选择项目参考卡，或先在右侧参考卡面板关联素材"
                      value={panel.reference_asset_ids || []}
                      options={referenceAssetOptions}
                      loading={savingContentId === storyboard.id}
                      disabled={!referenceAssetOptions.length || savingContentId === storyboard.id}
                      maxTagCount="responsive"
                      optionFilterProp="label"
                      style={{ width: '100%' }}
                      onChange={(values) =>
                        onUpdateStoryboardPanelReferences(storyboard.id, panel.panel_number, values)
                      }
                    />
                  </Space>
                  {renderInlineImage({
                    contentId: storyboard.id,
                    sourceType: 'storyboard_panel',
                    sourceIndex: panel.panel_number,
                    chapterNumber: activeChapterNumber,
                  })}
                  <StoryboardVideoOutputStrip
                    links={storyboardVideoOutputs.get(Number(panel.panel_number)) || []}
                    assetDetails={assetDetails}
                  />
                </div>
              ))}
            </Space>
          ) : script ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="脚本已生成，可以继续拆分镜" />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本话还没有脚本/分镜" />
          )}
        </WorkbenchSection>

        <WorkbenchSection
          title={`漫画页${pageCount ? ` · ${pageCount}` : ''}`}
          extra={
            <Space>
              <Select
                size="small"
                value={comicStyle}
                onChange={setComicStyle}
                style={{ width: 118 }}
                options={comicStyleOptions}
                title="漫画风格"
              />
              <InputNumber
                min={1}
                max={80}
                size="small"
                value={comicPageCount}
                onChange={(value) => setComicPageCount(Number(value || 10))}
              />
              {comic ? (
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  loading={referenceMatching}
                  disabled={!referenceAssetOptions.length}
                  onClick={() => onMatchReferenceAssets(comic.id)}
                >
                  匹配参考卡
                </Button>
              ) : null}
              <Tooltip title={canGenerateComic ? '' : '先生成分镜'}>
                <Button
                  size="small"
                  type="primary"
                  icon={<PictureOutlined />}
                  disabled={!canGenerateComic}
                  loading={isChapterActionLoading('comic_pages', activeChapterNumber)}
                  onClick={() => onSplitComicPages(activeChapterNumber)}
                >
                  {comic ? '重生成漫画' : '生成漫画'}
                </Button>
              </Tooltip>
            </Space>
          }
        >
          {comic ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Button
                type="primary"
                loading={savingContentId === comic.id}
                onClick={() =>
                  onSaveContent(comic.id, {
                    data: { ...comic.data, pages: comicDrafts },
                    text_content: comicDrafts
                      .map((page) => `第 ${page.page_number} 页\n${page.content || ''}\n${page.image_prompt || ''}`)
                      .join('\n\n'),
                  })
                }
              >
                保存漫画页
              </Button>
              {comicDrafts.map((page: any, index: number) => (
                <div key={`${page.page_number}-${index}`} style={themedCompactBlockStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Text strong>第 {index + 1} 页</Text>
                      {page.image_prompt ? (
                        <Button
                          size="small"
                          onClick={() =>
                            onSendImagePrompt(page.image_prompt, {
                              contentId: comic.id,
                              sourceType: 'comic_page',
                              sourceIndex: page.page_number || index + 1,
                              sourceTitle: page.title || `第 ${index + 1} 页`,
                              chapterNumber: activeChapterNumber,
                              referenceAssetIds: page.reference_asset_ids || [],
                              characterIds: page.character_ids || [],
                              portraitNodeIds: page.portrait_node_ids || [],
                              portraitVersionIds: page.portrait_version_ids || [],
                            })
                          }
                        >
                          生图
                        </Button>
                      ) : null}
                    </Space>
                    <Input
                      value={page.title}
                      placeholder="页面标题 / 节奏说明"
                      onChange={(event) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, title: event.target.value } : item
                        )))
                      }
                    />
                    <TextArea
                      rows={4}
                      value={page.content}
                      placeholder="本页剧情、对白、画面节奏"
                      onChange={(event) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, content: event.target.value } : item
                        )))
                      }
                    />
                    <TextArea
                      rows={3}
                      value={page.image_prompt}
                      placeholder="本页漫画图像提示词"
                      onChange={(event) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, image_prompt: event.target.value } : item
                        )))
                      }
                    />
                    <ReferenceAssetPreviewStrip
                      assetIds={page.reference_asset_ids || []}
                      notes={page.reference_notes || []}
                      assets={projectAssets}
                      assetDetails={assetDetails}
                    />
                    <Select
                      mode="multiple"
                      allowClear
                      size="small"
                      placeholder="选择本页参考卡"
                      value={page.reference_asset_ids || []}
                      options={referenceAssetOptions}
                      disabled={!referenceAssetOptions.length}
                      maxTagCount="responsive"
                      optionFilterProp="label"
                      style={{ width: '100%' }}
                      onChange={(values) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, reference_asset_ids: dedupeStrings(values) } : item
                        )))
                      }
                    />
                    {renderInlineImage({
                      contentId: comic.id,
                      sourceType: 'comic_page',
                      sourceIndex: page.page_number || index + 1,
                      chapterNumber: activeChapterNumber,
                    })}
                  </Space>
                </div>
              ))}
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="分镜完成后生成漫画页" />
          )}
        </WorkbenchSection>
      </Space>
      </div>
    </Space>
  )
}

const referenceRoleOptions = [
  { label: '角色参考', value: 'character' },
  { label: '背景参考', value: 'background' },
  { label: '画风参考', value: 'style' },
  { label: '世界观参考', value: 'world' },
  { label: '通用参考', value: 'reference' },
]

const comicStyleOptions = [
  { label: '彩色', value: '彩色影视漫画，竖屏短剧分镜感，半写实人物，高对比光影，画风统一' },
  { label: '黑白漫画', value: '日式黑白漫画，高对比网点，清晰线稿，强烈明暗，分格节奏明确' },
  { label: '国漫', value: '现代国漫彩色风格，人物精致，情绪表演强，电影感构图，细腻光影' },
  { label: '电影分镜', value: '电影故事板风格，镜头语言明确，低饱和色彩，强调构图、景别和调度' },
  { label: '写实短剧', value: '写实短剧剧照风格，真实室内外光线，人物表演自然，商业剧质感' },
]

function StoryboardVideoOutputStrip({
  links,
  assetDetails,
}: {
  links: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
}) {
  if (!links.length) return null

  return (
    <div
      style={{
        display: 'grid',
        gap: 8,
        marginTop: 8,
        paddingTop: 8,
        borderTop: '1px solid var(--borderLight)',
      }}
    >
      <Text strong style={{ fontSize: 12 }}>本格已生成视频 · {links.length}</Text>
      {links.map((link) => {
        const metadata = link.metadata || {}
        const detail = assetDetails[link.asset_id]
        const source = assetFileUrl(detail?.file_path || detail?.source_url || detail?.cover_url || '')
        const duration = Number(metadata.duration)
        return (
          <div
            key={link.id}
            style={{
              display: 'grid',
              gridTemplateColumns: source ? '168px minmax(0, 1fr)' : '1fr',
              gap: 10,
              alignItems: 'start',
            }}
          >
            {source ? (
              <video
                controls
                preload="metadata"
                src={source}
                style={{ width: 168, maxWidth: '100%', height: 96, objectFit: 'cover', borderRadius: 6, background: '#10121a' }}
              />
            ) : (
              <Skeleton.Image active style={{ width: 168, height: 96 }} />
            )}
            <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
              <Text ellipsis={{ tooltip: detail?.title || metadata.source_title || link.asset_id }}>
                {detail?.title || metadata.source_title || '分镜视频'}
              </Text>
              <Space size={4} wrap>
                <Tag color="green">已入项目素材</Tag>
                {(metadata.model || metadata.provider) ? <Tag>{metadata.model || metadata.provider}</Tag> : null}
                {Number.isFinite(duration) && duration > 0 ? <Tag>{duration}s</Tag> : null}
                {metadata.task_id ? <Tag color="blue">任务 {String(metadata.task_id).slice(0, 8)}</Tag> : null}
              </Space>
              <Space size={4} wrap>
                <Button size="small" href={`/video-gen?project_id=${encodeURIComponent(link.project_id)}&content_id=${encodeURIComponent(link.content_id || '')}&source_type=storyboard_panel&source_index=${encodeURIComponent(String(metadata.source_index || ''))}`}>
                  打开视频生成
                </Button>
                <Button size="small" href={`/assets?asset_id=${encodeURIComponent(link.asset_id)}`}>
                  查看素材
                </Button>
              </Space>
            </Space>
          </div>
        )
      })}
    </div>
  )
}

function InlineImageResult({
  image,
  loading,
  taskId,
  onPromoteReference,
}: {
  image?: InlineGeneratedImage
  loading: boolean
  taskId?: string
  onPromoteReference?: (role: string) => void
}) {
  if (loading) {
    return (
      <div style={inlineImageShellStyle}>
        <Skeleton.Image active style={{ width: 168, height: 112 }} />
        <Space direction="vertical" size={4}>
          <Text strong>正在生成图片</Text>
          <Text type="secondary">完成后会显示在这里，并同步关联到项目素材。</Text>
          {taskId ? <Text type="secondary" copyable style={{ fontSize: 12 }}>任务 {taskId}</Text> : null}
        </Space>
      </div>
    )
  }

  const src = assetFileUrl(image?.url || image?.localPath)
  if (!image || !src) return null
  const referenceImages = image.referenceImages || []

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <div style={inlineImageShellStyle}>
        <Image
          src={src}
          width={168}
          height={112}
          style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
        />
        <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
          <Text strong>已生成图片</Text>
          <Text type="secondary" ellipsis={{ tooltip: image.prompt }}>
            {image.model || image.provider || 'image'}
          </Text>
          <Space size={4} wrap>
            {image.assetId ? <Tag color="green">已入项目素材</Tag> : <Tag>本次结果</Tag>}
            {taskId ? <Tag color="blue">异步任务</Tag> : null}
            {referenceImages.length ? (
              <Tag color={image.referenceImagesSupported ? 'blue' : 'default'}>
                参考图 {image.referenceImagesSent || 0}/{referenceImages.length}
              </Tag>
            ) : null}
          </Space>
          {image.assetId && onPromoteReference ? (
            <Space.Compact size="small">
              <Button size="small" onClick={() => onPromoteReference('reference')}>
                设为参考
              </Button>
              <Select
                size="small"
                defaultValue="reference"
                style={{ width: 92 }}
                options={referenceRoleOptions}
                onChange={(role) => onPromoteReference(role)}
              />
            </Space.Compact>
          ) : null}
          {taskId ? (
            <Button size="small" href={`/tasks?task_id=${encodeURIComponent(taskId)}`}>
              查看任务详情
            </Button>
          ) : null}
        </Space>
      </div>
      {referenceImages.length ? (
        <div>
          <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
            本次参考图集合
          </Text>
          <Image.PreviewGroup>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {referenceImages.map((item, index) => (
                <Tooltip
                  key={`${item.url}-${index}`}
                  title={`${item.label || item.source}${item.role ? ` · ${item.role}` : ''}`}
                >
                  <Image
                    src={assetFileUrl(item.url)}
                    width={48}
                    height={48}
                    style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
                  />
                </Tooltip>
              ))}
            </div>
          </Image.PreviewGroup>
        </div>
      ) : null}
    </Space>
  )
}

function ReferenceAssetPreviewStrip({
  assetIds,
  assets,
  assetDetails,
  notes = [],
}: {
  assetIds?: string[]
  assets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  notes?: string[]
}) {
  const ids = dedupeStrings(assetIds || [])
  if (!ids.length) return null
  const linksByAssetId = new Map(assets.map((asset) => [asset.asset_id, asset]))
  return (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <Space size={4} wrap>
        <Tag color="blue">参考卡 {ids.length}</Tag>
        {(notes || []).slice(0, 3).map((note, index) => (
          <Tag key={`${note}-${index}`}>{note}</Tag>
        ))}
      </Space>
      <Image.PreviewGroup>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {ids.map((assetId) => {
            const link = linksByAssetId.get(assetId)
            const detail = assetDetails[assetId]
            const preview = assetFileUrl(detail?.thumbnail_url || detail?.cover_url || detail?.source_url || detail?.file_path)
            const roleLabel = referenceRoleOptions.find((item) => item.value === link?.role)?.label || link?.role || '参考'
            const label = link?.metadata?.label || link?.metadata?.character_name || link?.metadata?.source_title || detail?.title || assetId
            return (
              <Tooltip key={assetId} title={`${roleLabel} · ${label}`}>
                {preview ? (
                  <Image
                    src={preview}
                    width={48}
                    height={48}
                    style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
                  />
                ) : (
                  <Tag>{label}</Tag>
                )}
              </Tooltip>
            )
          })}
        </div>
      </Image.PreviewGroup>
    </Space>
  )
}

function StoryboardReferencePreflight({
  summary,
  supportsReferenceImages,
  hasImageModel,
}: {
  summary: StoryboardReferenceSummary
  supportsReferenceImages: boolean
  hasImageModel: boolean
}) {
  const { theme } = useTheme()
  if (!summary.promptPanels) return null

  const warnings = [
    !hasImageModel ? '未选择默认生图模型' : '',
    !supportsReferenceImages ? '当前模型不会上传参考图，只记录参考关系' : '',
    summary.missingEffectivePlanPanels ? `${summary.missingEffectivePlanPanels} 个分镜缺少角色/参考卡规划` : '',
    summary.noUsableReferencePanels ? `${summary.noUsableReferencePanels} 个分镜没有可发送参考图` : '',
    summary.unresolvedCharacterIds.length ? `${summary.unresolvedCharacterIds.length} 个角色资料待加载` : '',
  ].filter(Boolean)

  return (
    <div
      style={{
        border: `1px solid ${warnings.length ? theme.warning : theme.borderLight}`,
        background: theme.bgPage,
        borderRadius: 8,
        padding: 10,
      }}
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space size={4} wrap>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>分镜 {summary.promptPanels}</Tag>
          <Tag color={summary.effectivePlanPanels === summary.promptPanels ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
            有效参考 {summary.effectivePlanPanels}/{summary.promptPanels}
          </Tag>
          <Tag color={summary.usableReferencePanels === summary.promptPanels ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
            可用参考图 {summary.usableReferencePanels}/{summary.promptPanels}
          </Tag>
          <Tag color={summary.sentReferenceImages ? 'green' : supportsReferenceImages ? 'orange' : 'default'} style={{ marginInlineEnd: 0 }}>
            实际发送 {summary.sentReferenceImages}
          </Tag>
          <Tag color={summary.uniqueReferenceImages ? 'cyan' : 'default'} style={{ marginInlineEnd: 0 }}>
            去重参考图 {summary.uniqueReferenceImages}
          </Tag>
          <Tag color={summary.uniqueCharacterIds.length ? 'purple' : 'default'} style={{ marginInlineEnd: 0 }}>
            角色 {summary.uniqueCharacterIds.length}
          </Tag>
          <Tag color="green" style={{ marginInlineEnd: 0 }}>已生图 {summary.generatedPanels}</Tag>
        </Space>
        {warnings.length ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {warnings.join('；')}。可以先补角色基准图、手动选择参考卡，或点击“匹配参考卡”后再批量生图。
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            本话分镜已有可发送参考图，批量生图会把角色/项目参考一起带入请求。
          </Text>
        )}
      </Space>
    </div>
  )
}

function StoryboardReferenceDiagnostics({
  panel,
  projectAssets,
  characterDetails,
  supportsReferenceImages,
}: {
  panel: any
  projectAssets: ProjectAssetLink[]
  characterDetails: Record<string, CharacterReferenceSummary>
  supportsReferenceImages: boolean
}) {
  const { theme } = useTheme()
  const plan = buildStoryboardPanelReferencePlan({
    panel,
    projectAssets,
    characterDetails,
    supportsReferenceImages,
  })
  const unresolvedCharacters = plan.unresolvedCharacterIds.length

  return (
    <div style={{
      border: `1px solid ${theme.borderLight}`,
      background: theme.bgPage,
      borderRadius: 8,
      padding: 8,
      marginTop: 6,
    }}>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space size={4} wrap>
          <Tag color={plan.characterIds.length ? 'purple' : 'default'} style={{ marginInlineEnd: 0 }}>
            角色 {plan.characterIds.length}
          </Tag>
          <Tag color={plan.referenceAssetIds.length ? 'blue' : 'default'} style={{ marginInlineEnd: 0 }}>
            项目卡 {plan.referenceAssetIds.length}
          </Tag>
          <Tag color={plan.portraitNodeIds.length ? 'cyan' : 'default'} style={{ marginInlineEnd: 0 }}>
            立绘节点 {plan.portraitNodeIds.length}
          </Tag>
          <Tag color={plan.imageCollection.length ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
            可用参考图 {plan.imageCollection.length}
          </Tag>
          <Tag color={plan.sentCount ? 'green' : supportsReferenceImages ? 'orange' : 'default'} style={{ marginInlineEnd: 0 }}>
            实际发送 {plan.sentCount}
          </Tag>
          {unresolvedCharacters ? (
            <Tag color="orange" style={{ marginInlineEnd: 0 }}>角色资料加载中 {unresolvedCharacters}</Tag>
          ) : null}
        </Space>
        {plan.imageCollection.length ? (
          <Image.PreviewGroup>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {plan.imageCollection.map((item, index) => (
                <Tooltip
                  key={`${item.url}-${index}`}
                  title={`${item.label || item.source}${item.character_name ? ` · ${item.character_name}` : ''}`}
                >
                  <Image
                    src={assetFileUrl(item.url)}
                    width={42}
                    height={42}
                    style={{ objectFit: 'cover', borderRadius: 6, border: `1px solid ${theme.borderLight}` }}
                  />
                </Tooltip>
              ))}
            </div>
          </Image.PreviewGroup>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            暂无可发送参考图。可先同步角色、设置身份基准图，或点击“匹配参考卡”。
          </Text>
        )}
      </Space>
    </div>
  )
}

function ReferenceCardsPanel({
  assets,
  assetDetails,
  loading,
  onLinkAsset,
}: {
  assets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  loading: boolean
  onLinkAsset: (assetId: string, role: string, metadata?: Record<string, any>) => void
}) {
  const [assetId, setAssetId] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<AssetSummary[]>([])
  const [role, setRole] = useState('character')
  const [label, setLabel] = useState('')
  const [characterName, setCharacterName] = useState('')
  const [referenceFilter, setReferenceFilter] = useState('all')
  const referenceAssets = assets.filter((asset) =>
    ['character', 'background', 'style', 'world', 'reference'].includes(asset.role),
  )
  const visibleReferenceAssets = referenceFilter === 'all'
    ? referenceAssets
    : referenceAssets.filter((asset) => asset.role === referenceFilter)
  const buildMetadata = (source?: AssetSummary) => ({
    label: label.trim() || source?.title || '',
    character_name: role === 'character' ? characterName.trim() || label.trim() || source?.title || '' : '',
    source_title: source?.title || '',
    source_type: source?.type || '',
    linked_from: 'story_workbench_reference_card',
  })
  const linkAsset = (id: string, source?: AssetSummary) => {
    if (!id.trim()) return
    onLinkAsset(id.trim(), role, buildMetadata(source))
    setAssetId('')
    setLabel('')
    setCharacterName('')
  }
  const searchAssets = async () => {
    setSearching(true)
    try {
      const response = await listAssets({
        search: searchKeyword.trim() || undefined,
        page_size: 12,
      })
      setSearchResults(response?.data || [])
    } catch (error: any) {
      message.error(error?.message || '搜索素材失败')
    } finally {
      setSearching(false)
    }
  }

  return (
    <WorkbenchSection
      title="项目参考卡"
      extra={
        <Tag color={referenceAssets.length ? 'blue' : 'default'}>
          {referenceAssets.length} 个
        </Tag>
      }
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Segmented
          size="small"
          value={referenceFilter}
          onChange={(value) => setReferenceFilter(String(value))}
          options={[
            { label: `全部 ${referenceAssets.length}`, value: 'all' },
            ...referenceRoleOptions.map((item) => ({
              label: `${item.label.replace('参考', '')} ${referenceAssets.filter((asset) => asset.role === item.value).length}`,
              value: item.value,
            })),
          ]}
          style={{ maxWidth: '100%' }}
        />
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={searchKeyword}
            onChange={(event) => setSearchKeyword(event.target.value)}
            onPressEnter={searchAssets}
            placeholder="搜索素材库：角色名 / 背景 / 画风 / 分镜图"
          />
          <Button loading={searching} onClick={searchAssets}>
            搜索
          </Button>
        </Space.Compact>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="参考名称：如 萧然立绘 / 夜晚办公室 / 统一漫画风格"
          />
          <Input
            value={characterName}
            disabled={role !== 'character'}
            onChange={(event) => setCharacterName(event.target.value)}
            placeholder="角色名"
            style={{ width: 160 }}
          />
          <Select
            value={role}
            onChange={setRole}
            style={{ width: 120 }}
            options={referenceRoleOptions}
          />
        </Space.Compact>
        {searchResults.length ? (
          <List
            size="small"
            dataSource={searchResults}
            renderItem={(asset) => {
              const preview = assetFileUrl(asset.thumbnail_url || asset.cover_url || asset.source_url || asset.file_path)
              return (
                <List.Item
                  actions={[
                    <Button
                      key="link"
                      size="small"
                      icon={<PlusOutlined />}
                      loading={loading}
                      onClick={() => linkAsset(asset.id, asset)}
                    >
                      关联
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={
                      preview ? (
                        <Image
                          src={preview}
                          width={44}
                          height={44}
                          preview={false}
                          style={{ objectFit: 'cover', borderRadius: 6 }}
                        />
                      ) : null
                    }
                    title={<Text ellipsis={{ tooltip: asset.title }}>{asset.title || asset.id}</Text>}
                    description={
                      <Space size={4} wrap>
                        {asset.type ? <Tag>{asset.type}</Tag> : null}
                        {(asset.tags || []).slice(0, 3).map((tag) => (
                          <Tag key={tag}>{tag}</Tag>
                        ))}
                      </Space>
                    }
                  />
                </List.Item>
              )
            }}
          />
        ) : null}
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={assetId}
            onChange={(event) => setAssetId(event.target.value)}
            placeholder="素材 asset_id：角色卡 / 背景 / 画风参考"
          />
          <Select
            value={role}
            onChange={setRole}
            style={{ width: 120 }}
            options={referenceRoleOptions}
          />
          <Button
            type="primary"
            loading={loading}
            onClick={() => {
              linkAsset(assetId)
            }}
          >
            关联
          </Button>
        </Space.Compact>
        <Text type="secondary">
          角色卡、背景和画风参考会作为漫画生成的一致性资产入口；当前先建立项目关联，后续生成提示会读取这些参考。
        </Text>
        {visibleReferenceAssets.length ? (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {visibleReferenceAssets.map((asset) => (
              <ReferenceAssetCard key={asset.id} link={asset} asset={assetDetails[asset.asset_id]} />
            ))}
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={referenceAssets.length ? '这个分类暂无参考卡' : '暂无参考卡'} />
        )}
      </Space>
    </WorkbenchSection>
  )
}

function ReferenceAssetCard({
  link,
  asset,
}: {
  link: ProjectAssetLink
  asset?: AssetSummary
}) {
  const roleLabel = referenceRoleOptions.find((item) => item.value === link.role)?.label || link.role
  const preview = assetFileUrl(asset?.thumbnail_url || asset?.cover_url || asset?.source_url || asset?.file_path)
  const title = link.metadata?.label || link.metadata?.character_name || asset?.title || link.asset_id
  const roleColor = link.role === 'character'
    ? 'green'
    : link.role === 'style'
      ? 'purple'
      : link.role === 'world'
        ? 'gold'
        : 'blue'

  return (
    <div style={referenceAssetCardStyle}>
      {preview ? (
        <Image
          src={preview}
          width={52}
          height={52}
          preview={false}
          style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
        />
      ) : (
        <div style={referenceAssetPlaceholderStyle}>
          <PictureOutlined />
        </div>
      )}
      <Space direction="vertical" size={3} style={{ minWidth: 0, flex: 1 }}>
        <Space size={4} wrap>
          <Tag color={roleColor}>{roleLabel}</Tag>
          {link.metadata?.character_name ? <Tag>{link.metadata.character_name}</Tag> : null}
        </Space>
        <Text strong ellipsis={{ tooltip: title }}>
          {title}
        </Text>
        <Text type="secondary" copyable ellipsis={{ tooltip: link.asset_id }} style={{ fontSize: 12 }}>
          {link.asset_id}
        </Text>
      </Space>
    </div>
  )
}

function EditorField({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text strong>{label}</Text>
      {hint ? <Text type="secondary" style={{ fontSize: 12 }}>{hint}</Text> : null}
      {children}
    </Space>
  )
}

function WorkbenchSection({
  title,
  extra,
  children,
}: {
  title: string
  extra?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section style={panelStyle}>
      <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }} align="start">
        <Text strong>{title}</Text>
        {extra}
      </Space>
      {children}
    </section>
  )
}

function ResizeHandle({ onMouseDown }: { onMouseDown: (event: React.MouseEvent) => void }) {
  const { theme } = useTheme()
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="拖动调整宽度"
      onMouseDown={onMouseDown}
      style={createResizeHandleStyle(theme)}
      onMouseEnter={(event) => {
        event.currentTarget.style.background = theme.primaryAlpha(0.1)
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.background = 'transparent'
      }}
    >
      <span style={createResizeHandleLineStyle(theme)} />
    </div>
  )
}

function sortProjectContentsForReading(items: ProjectContent[]) {
  return [...items].sort((left, right) => {
    const leftChapter = Number(left.chapter_number || left.episode_number || Number.MAX_SAFE_INTEGER)
    const rightChapter = Number(right.chapter_number || right.episode_number || Number.MAX_SAFE_INTEGER)
    if (leftChapter !== rightChapter) return leftChapter - rightChapter

    const leftVersion = Number(left.version || 0)
    const rightVersion = Number(right.version || 0)
    if (leftVersion !== rightVersion) return leftVersion - rightVersion

    const leftCreated = left.created_at ? new Date(left.created_at).getTime() : 0
    const rightCreated = right.created_at ? new Date(right.created_at).getTime() : 0
    return leftCreated - rightCreated
  })
}

function isProjectContentNewer(next: ProjectContent, current?: ProjectContent) {
  if (!current) return true
  const nextVersion = Number(next.version || 0)
  const currentVersion = Number(current.version || 0)
  if (nextVersion !== currentVersion) return nextVersion > currentVersion

  const nextUpdated = next.updated_at ? new Date(next.updated_at).getTime() : 0
  const currentUpdated = current.updated_at ? new Date(current.updated_at).getTime() : 0
  if (nextUpdated !== currentUpdated) return nextUpdated > currentUpdated

  const nextCreated = next.created_at ? new Date(next.created_at).getTime() : 0
  const currentCreated = current.created_at ? new Date(current.created_at).getTime() : 0
  return nextCreated > currentCreated
}

function projectContentChapterKey(item: ProjectContent): number | null {
  const directValues = [item.chapter_number, item.episode_number]
  for (const value of directValues) {
    const number = Number(value)
    if (Number.isInteger(number) && number > 0) return number
  }

  // Older imports can lack a normalized chapter field. Keep their historical
  // versions out of the reader by recovering the chapter number from the title.
  const titleMatch = String(item.title || '').match(/(?:第\s*)?(\d+)\s*[章节集话]/)
  return titleMatch ? Number(titleMatch[1]) : null
}

function latestProjectContentsByChapter(items: ProjectContent[]) {
  const grouped = new Map<number, ProjectContent>()
  items.forEach((item) => {
    const chapterNumber = projectContentChapterKey(item)
    if (!chapterNumber) return
    const current = grouped.get(chapterNumber)
    if (isProjectContentNewer(item, current)) {
      grouped.set(chapterNumber, item)
    }
  })
  return sortProjectContentsForReading(Array.from(grouped.values()))
}

function textForNovelBody(body?: ProjectContent | null) {
  return String(body?.text_content || body?.data?.content || '')
}

function compactNovelReaderText(text: string) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\n[\t ]*\n+/g, '\n')
    .trim()
}

function buildNovelChapterMarkdown(body: ProjectContent) {
  const chapterNumber = body.chapter_number || body.episode_number || ''
  const title = body.title || `第 ${chapterNumber} 章`
  const text = textForNovelBody(body)
  return `# 第 ${chapterNumber} 章 ${title}\n\n${text}`.trim() + '\n'
}

function projectMarkdownFilename(title: string | undefined, fallback: string) {
  const normalized = String(title || '').trim().replace(/[\\/:*?"<>|]/g, '_')
  return normalized || fallback
}

function markdownList(items: unknown) {
  const values = Array.isArray(items) ? items : []
  return values
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .map((item) => `- ${item}`)
    .join('\n')
}

function markdownSection(title: string, text: unknown) {
  const value = Array.isArray(text) ? markdownList(text) : String(text || '').trim()
  return value ? `## ${title}\n\n${value}` : ''
}

function buildOutlineMarkdown(outline: StoryOutline) {
  const sections = [
    `# ${outline.title || '故事大纲'}`,
    markdownSection('一句话卖点', outline.logline),
    markdownSection('类型', outline.genre),
    markdownSection('核心前提', outline.premise),
    markdownSection('世界观', outline.worldview),
    markdownSection('主线冲突', outline.main_conflict),
    markdownSection('目标读者', outline.target_reader),
    markdownSection('卖点', outline.selling_points),
    markdownSection('叙事规则', outline.narrative_rules),
    markdownSection('主题', outline.themes),
    markdownSection('故事弧线', [
      outline.story_arc?.beginning ? `开局：${outline.story_arc.beginning}` : '',
      outline.story_arc?.middle ? `中段：${outline.story_arc.middle}` : '',
      outline.story_arc?.climax ? `高潮：${outline.story_arc.climax}` : '',
      outline.story_arc?.ending_direction ? `结局方向：${outline.story_arc.ending_direction}` : '',
    ]),
    markdownSection('叙事气质', outline.tone),
    markdownSection('视觉风格', outline.visual_style),
    markdownSection('统一生图提示', outline.image_style_prompt),
    markdownSection('制作约束', outline.production_notes),
    markdownSection('角色', (outline.characters || []).map((character) => {
      const lines = [
        `### ${character.name || '未命名角色'}`,
        character.role ? `- 定位：${character.role}` : '',
        character.personality ? `- 性格：${character.personality}` : '',
        character.background ? `- 背景：${character.background}` : '',
        character.appearance ? `- 外貌：${character.appearance}` : '',
      ].filter(Boolean)
      return lines.join('\n')
    })),
  ]
  return `${sections.filter(Boolean).join('\n\n')}\n`
}

function buildChapterPlanMarkdown(plan: ChapterPlan) {
  const chapters = (plan.chapters || []).map((chapter) => {
    const sections = [
      `## 第 ${chapter.chapter_number || ''} 章 ${chapter.title || ''}`.trim(),
      chapter.goal ? `**目标**：${chapter.goal}` : '',
      chapter.conflict ? `**冲突**：${chapter.conflict}` : '',
      markdownSection('关键事件', chapter.key_events),
      markdownSection('焦点角色', chapter.character_focus),
      chapter.ending_hook ? `**章末钩子**：${chapter.ending_hook}` : '',
      chapter.status ? `**状态**：${chapter.status}` : '',
    ]
    return sections.filter(Boolean).join('\n\n')
  })
  return `# 章节规划\n\n${chapters.join('\n\n')}\n`
}

function buildScriptMarkdown(script: ProjectContent) {
  const data = script.data || {}
  const scenes = Array.isArray(data.scenes) ? data.scenes : []
  const parts = [
    `# ${script.title || `第 ${script.chapter_number || script.episode_number || ''} 章脚本`}`,
    data.hook ? `**开头钩子**：${data.hook}` : '',
    ...scenes.map((scene: any) => {
      const dialogue = (scene.dialogue || [])
        .map((line: any) => `> ${line.character ? `${line.character}：` : ''}${line.line || line}`)
        .join('\n')
      return [
        `## 场景 ${scene.scene_number || ''} ${scene.location || ''}`.trim(),
        scene.action ? `**动作**：${scene.action}` : '',
        scene.camera_hint ? `**镜头**：${scene.camera_hint}` : '',
        scene.emotion ? `**情绪**：${scene.emotion}` : '',
        dialogue,
      ].filter(Boolean).join('\n\n')
    }),
    data.ending_hook ? `## 结尾钩子\n\n${data.ending_hook}` : '',
  ]
  return `${parts.filter(Boolean).join('\n\n')}\n`
}

function buildStoryboardMarkdown(storyboard: ProjectContent) {
  const panels = Array.isArray(storyboard.data?.panels) ? storyboard.data.panels : []
  const parts = [
    `# ${storyboard.title || `第 ${storyboard.chapter_number || storyboard.episode_number || ''} 章分镜`}`,
    ...panels.map((panel: any) => [
      `## 分镜 ${panel.panel_number || ''}`.trim(),
      panel.action ? `**画面动作**：${panel.action}` : '',
      panel.dialogue ? `**对白**：${panel.dialogue}` : '',
      panel.shot_size ? `**景别**：${panel.shot_size}` : '',
      panel.camera_angle ? `**角度**：${panel.camera_angle}` : '',
      panel.camera_motion ? `**运镜**：${panel.camera_motion}` : '',
      panel.image_prompt ? `**生图提示**：${panel.image_prompt}` : '',
    ].filter(Boolean).join('\n\n')),
  ]
  return `${parts.filter(Boolean).join('\n\n')}\n`
}

function escapePreviewHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[character] || character))
}

function openProjectTextPreview(title: string, markdown: string) {
  const preview = window.open('', '_blank')
  if (!preview) {
    message.warning('浏览器阻止了预览窗口')
    return
  }
  preview.opener = null
  preview.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${escapePreviewHtml(title)}</title><style>body{margin:0;background:#f5f5f3;color:#1c1c1b;font-family:ui-serif,Georgia,"Noto Serif SC",serif}.page{box-sizing:border-box;max-width:860px;margin:0 auto;padding:56px 68px;background:#fff;min-height:100vh}pre{white-space:pre-wrap;word-break:break-word;font:16px/1.8 ui-serif,Georgia,"Noto Serif SC",serif;margin:0} @media print{body{background:#fff}.page{max-width:none;padding:24px}}</style></head><body><main class="page"><pre>${escapePreviewHtml(markdown)}</pre></main></body></html>`)
  preview.document.close()
  preview.focus()
}

function downloadTextFile(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function findWriterRoomLog(logs: ProjectGenerationLog[], content?: ProjectContent) {
  if (!content) return undefined
  // Only match by the stable candidate->log association. Historical candidates
  // without a linked log return undefined so the UI can show a clear notice
  // instead of falling back to another candidate's log by stage.
  const logId = content.data?.writer_room?.generation_log_id
  return logs.find((log) => log.content_id === content.id || (logId ? log.id === logId : false))
}

function reviewIssuesForContent(content?: ProjectContent): WriterRoomReviewIssue[] {
  const data = content?.data || {}
  const candidates = [data.issues, data.review?.issues, data.result?.issues]
  const issues = candidates.find((item) => Array.isArray(item))
  return Array.isArray(issues) ? issues.filter(Boolean) : []
}

function qualitySummaryForContent(content?: ProjectContent): WriterRoomQualitySummary | null {
  if (!content?.data) return null
  const issues = reviewIssuesForContent(content)
  const tags = Array.isArray(content.data.quality_tags)
    ? content.data.quality_tags
    : Array.from(new Set(issues.map((item) => item.category).filter(Boolean)))
  const checks = Array.isArray(content.data.ai_smell_checks) ? content.data.ai_smell_checks : []
  const hasScore = Number(content.data.overall_score || content.data.ai_smell_score || 0) > 0
  if (!hasScore && !tags.length && !checks.length) return null
  return {
    overallScore: Number(content.data.overall_score || 0),
    aiSmellScore: Number(content.data.ai_smell_score || 0),
    tags: tags.map(String).filter(Boolean),
    checks: checks.map(String).filter(Boolean),
  }
}

function writerRoomPreviewText(content?: ProjectContent, maxJsonLength = 1800) {
  if (!content) return ''
  if (content.text_content?.trim()) return content.text_content.trim()

  const data = content.data || {}
  const lines: string[] = []
  const push = (label: string, value: unknown) => {
    if (Array.isArray(value)) {
      const text = value.map((item) => String(item || '').trim()).filter(Boolean).join('；')
      if (text) lines.push(`${label}：${text}`)
      return
    }
    const text = String(value || '').trim()
    if (text) lines.push(`${label}：${text}`)
  }

  push('摘要', data.summary)
  push('目标', data.objective || data.purpose)
  push('结论', data.approval_recommendation)
  push('连续性', data.continuity_notes)

  if (Array.isArray(data.scene_beats)) {
    data.scene_beats.slice(0, 6).forEach((scene: Record<string, any>, index: number) => {
      const title = scene.title || `场景 ${scene.scene_number || index + 1}`
      const core = [scene.purpose, scene.location, scene.dramatic_question].filter(Boolean).join(' · ')
      lines.push(`${index + 1}. ${title}${core ? `：${core}` : ''}`)
      push('动作节拍', scene.action_beats)
      push('转折', scene.turning_point)
      push('尾钩', scene.hook)
    })
  }

  if (Array.isArray(data.scene_rehearsals)) {
    data.scene_rehearsals.slice(0, 6).forEach((scene: Record<string, any>, index: number) => {
      lines.push(`${index + 1}. 场景 ${scene.scene_number || index + 1}：${scene.conflict || scene.summary || '角色冲突'}`)
      push('可写瞬间', scene.usable_moments)
    })
  }

  if (Array.isArray(data.character_reactions)) {
    data.character_reactions.slice(0, 8).forEach((item: Record<string, any>) => {
      const goal = item.private_goal || item.public_goal || item.likely_action || ''
      lines.push(`${item.character || '角色'}：${goal}`)
      push('潜台词', item.subtext)
      push('可能台词', item.likely_dialogue)
    })
  }

  push('可用冲突', data.usable_conflicts)
  push('质量标签', data.quality_tags)
  push('重写计划', data.rewrite_plan)
  if (lines.length) return lines.filter(Boolean).join('\n')

  const jsonText = JSON.stringify(data, null, 2)
  return jsonText.length > maxJsonLength ? `${jsonText.slice(0, maxJsonLength)}\n...` : jsonText
}

function writerRoomContentWordCount(content?: ProjectContent) {
  if (!content) return 0
  const explicit = Number(content.data?.word_count || content.data?.characters || 0)
  if (Number.isFinite(explicit) && explicit > 0) return Math.round(explicit)
  return String(content.text_content || '').replace(/\s/g, '').length
}

function splitWriterRoomParagraphs(text: string) {
  const normalized = String(text || '').replace(/\r\n/g, '\n').trim()
  if (!normalized) return []
  const byBlankLine = normalized
    .split(/\n\s*\n+/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (byBlankLine.length > 1) return byBlankLine
  return normalized
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

type ProseDiffRow = {
  kind: 'added' | 'removed' | 'changed'
  approved?: string
  candidate?: string
}

function buildProseDiffRows(approvedText: string, candidateText: string): ProseDiffRow[] {
  const approved = splitWriterRoomParagraphs(approvedText)
  const candidate = splitWriterRoomParagraphs(candidateText)
  const scores = Array.from({ length: approved.length + 1 }, () => Array(candidate.length + 1).fill(0) as number[])

  for (let approvedIndex = approved.length - 1; approvedIndex >= 0; approvedIndex -= 1) {
    for (let candidateIndex = candidate.length - 1; candidateIndex >= 0; candidateIndex -= 1) {
      scores[approvedIndex][candidateIndex] = approved[approvedIndex] === candidate[candidateIndex]
        ? scores[approvedIndex + 1][candidateIndex + 1] + 1
        : Math.max(scores[approvedIndex + 1][candidateIndex], scores[approvedIndex][candidateIndex + 1])
    }
  }

  const raw: Array<{ kind: 'same' | 'added' | 'removed'; text: string }> = []
  let approvedIndex = 0
  let candidateIndex = 0
  while (approvedIndex < approved.length && candidateIndex < candidate.length) {
    if (approved[approvedIndex] === candidate[candidateIndex]) {
      raw.push({ kind: 'same', text: approved[approvedIndex] })
      approvedIndex += 1
      candidateIndex += 1
    } else if (scores[approvedIndex + 1][candidateIndex] >= scores[approvedIndex][candidateIndex + 1]) {
      raw.push({ kind: 'removed', text: approved[approvedIndex] })
      approvedIndex += 1
    } else {
      raw.push({ kind: 'added', text: candidate[candidateIndex] })
      candidateIndex += 1
    }
  }
  while (approvedIndex < approved.length) raw.push({ kind: 'removed', text: approved[approvedIndex++] })
  while (candidateIndex < candidate.length) raw.push({ kind: 'added', text: candidate[candidateIndex++] })

  const rows: ProseDiffRow[] = []
  for (let index = 0; index < raw.length; index += 1) {
    const current = raw[index]
    if (current.kind === 'same') continue
    const next = raw[index + 1]
    if (current.kind === 'removed' && next?.kind === 'added') {
      rows.push({ kind: 'changed', approved: current.text, candidate: next.text })
      index += 1
      continue
    }
    rows.push(current.kind === 'removed'
      ? { kind: 'removed', approved: current.text }
      : { kind: 'added', candidate: current.text })
  }
  return rows
}

function ProseParagraphDiff({ approvedText, candidateText }: { approvedText: string; candidateText: string }) {
  const rows = useMemo(() => buildProseDiffRows(approvedText, candidateText), [approvedText, candidateText])
  if (!rows.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="候选与当前正文内容一致，没有段落差异" />
  }
  return (
    <div style={writerRoomDiffListStyle}>
      <Text type="secondary" style={{ fontSize: 12 }}>仅展示 {rows.length} 处变更；未变段落已折叠。此视图只用于审阅，不会改写正文。</Text>
      {rows.map((row, index) => (
        <div key={`${row.kind}-${index}`} style={writerRoomDiffRowStyle}>
          <Tag color={row.kind === 'added' ? 'green' : row.kind === 'removed' ? 'red' : 'gold'}>
            {row.kind === 'added' ? '新增' : row.kind === 'removed' ? '删除' : '改写'}
          </Tag>
          <div style={writerRoomDiffColumnsStyle}>
            <div style={{ ...writerRoomDiffTextStyle, background: row.approved ? 'rgba(207, 19, 34, 0.08)' : 'transparent' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>当前正文</Text>
              <Text style={{ display: 'block', marginTop: 4, whiteSpace: 'pre-wrap' }}>{row.approved || '—'}</Text>
            </div>
            <div style={{ ...writerRoomDiffTextStyle, background: row.candidate ? 'rgba(56, 158, 13, 0.08)' : 'transparent' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>候选正文</Text>
              <Text style={{ display: 'block', marginTop: 4, whiteSpace: 'pre-wrap' }}>{row.candidate || '—'}</Text>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function writerRoomStepStatusColor(content?: ProjectContent, log?: ProjectGenerationLog) {
  const status = String(log?.status || '').toLowerCase()
  if (status.includes('fail') || status.includes('error')) return 'red'
  if (content) return 'green'
  if (log) return 'orange'
  return 'default'
}

function writerRoomIssueSeverityColor(severity?: string) {
  const value = (severity || '').toLowerCase()
  if (['high', '严重', '高'].some((item) => value.includes(item))) return 'red'
  if (['medium', '中'].some((item) => value.includes(item))) return 'orange'
  if (['low', '轻', '低'].some((item) => value.includes(item))) return 'blue'
  return 'default'
}

function WriterRoomQualitySummaryPanel({ summary }: { summary: WriterRoomQualitySummary }) {
  return (
    <div style={writerRoomQualityStyle}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space wrap>
          <Tag color={summary.overallScore >= 80 ? 'green' : summary.overallScore >= 60 ? 'orange' : 'red'}>
            总分 {summary.overallScore || '-'}
          </Tag>
          <Tag color={summary.aiSmellScore >= 70 ? 'red' : summary.aiSmellScore >= 40 ? 'orange' : 'green'}>
            AI味 {summary.aiSmellScore || '-'}
          </Tag>
          {summary.tags.slice(0, 8).map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </Space>
        {summary.checks.length ? (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">AI味检查</Text>
            {summary.checks.slice(0, 6).map((check, index) => (
              <Text key={`${check}-${index}`} style={{ fontSize: 12 }}>
                {index + 1}. {check}
              </Text>
            ))}
          </Space>
        ) : null}
      </Space>
    </div>
  )
}

function CharacterRehearsalCard({
  character,
  performance,
  index,
}: {
  character: string
  performance: string
  index: number
}) {
  const [open, setOpen] = useState(index === 0)
  const initial = (character || '?').trim().charAt(0)
  return (
    <div style={writerRoomTeamRoleStyle}>
      <div
        style={writerRoomTeamRoleHeaderStyle}
        role="button"
        tabIndex={0}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setOpen((value) => !value)
          }
        }}
        aria-expanded={open}
      >
        <span style={writerRoomTeamAvatarStyle}>{initial}</span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <Text strong ellipsis={{ tooltip: character }} style={{ fontSize: 14, color: 'var(--textPrimary)' }}>
            {character || `角色 ${index + 1}`}
          </Text>
        </span>
        <Tag color="geekblue" style={{ fontSize: 11, marginInlineEnd: 0 }}>子智能体</Tag>
        <DownOutlined
          style={{
            fontSize: 12,
            color: 'var(--textSecondary)',
            transition: 'transform 0.2s ease',
            transform: open ? 'rotate(180deg)' : 'none',
          }}
        />
      </div>
      {open ? (
        <div style={writerRoomTeamRoleBodyStyle}>
          <Text style={{ display: 'block', whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 13, color: 'var(--textPrimary)' }}>
            {performance || '该角色本轮没有产出'}
          </Text>
        </div>
      ) : null}
    </div>
  )
}

function TeamRehearsalPanel({
  performances,
  joined,
}: {
  performances: Array<{ character: string; performance: string; child_run_id?: string }>
  joined?: string
}) {
  const [showJoined, setShowJoined] = useState(true)
  if (!performances.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无角色演绎产出" />
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={writerRoomTeamGridStyle}>
        {performances.map((item, index) => (
          <CharacterRehearsalCard
            key={item.character || index}
            character={item.character}
            performance={item.performance}
            index={index}
          />
        ))}
      </div>
      {joined ? (
        <div style={writerRoomTeamJoinStyle}>
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
            role="button"
            tabIndex={0}
            onClick={() => setShowJoined((value) => !value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setShowJoined((value) => !value)
              }
            }}
          >
            <Text strong style={{ fontSize: 13 }}>编辑连接</Text>
            <Tag style={{ fontSize: 11 }}>汇合</Tag>
            <DownOutlined
              style={{
                fontSize: 11,
                color: 'var(--textSecondary)',
                transition: 'transform 0.2s ease',
                transform: showJoined ? 'rotate(180deg)' : 'none',
              }}
            />
          </div>
          {showJoined ? (
            <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', lineHeight: 1.7, fontSize: 13, color: 'var(--textPrimary)' }}>
              {joined}
            </Paragraph>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function WriterRoomLogSummary({ log }: { log: ProjectGenerationLog }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Space size={4} wrap>
        <Tag color={log.status === 'success' ? 'green' : log.status === 'success_repaired' ? 'blue' : 'red'}>
          {log.status}
        </Tag>
        <Tag>{log.provider || 'provider'}</Tag>
        <Tag>{log.model || 'model'}</Tag>
        {log.created_at ? <Tag>{log.created_at}</Tag> : null}
        {log.prompt_template ? (
          <Tooltip title={log.prompt_template.description || log.prompt_template.platform || ''}>
            <Tag color="purple">{log.prompt_template.name || writerRoomStepLabelMap[log.stage] || log.stage}</Tag>
          </Tooltip>
        ) : (
          <Tag>内置默认</Tag>
        )}
        <Button size="small" type="link" onClick={() => setOpen(true)}>
          查看请求
        </Button>
      </Space>
      <Modal
        title="写作室生成日志"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={920}
      >
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
          <Space wrap>
            <Tag>{writerRoomStepLabelMap[log.stage] || log.stage}</Tag>
            <Tag color={log.status === 'success' ? 'green' : 'red'}>{log.status}</Tag>
            <Tag>{log.provider || '-'}</Tag>
            <Tag>{log.model || '-'}</Tag>
          </Space>
          {log.validation_error ? (
            <div style={writerRoomIssueStyle}>
              <Text type="danger">{log.validation_error}</Text>
            </div>
          ) : null}
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>Prompt</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{log.prompt || '无'}</Paragraph>
          </Space>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>请求参数</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{JSON.stringify(log.request || {}, null, 2)}</Paragraph>
          </Space>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>标准化结果</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{JSON.stringify(log.normalized || {}, null, 2)}</Paragraph>
          </Space>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>原始返回</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{log.raw_response || '无'}</Paragraph>
          </Space>
        </Space>
      </Modal>
    </>
  )
}

function WriterRoomTab({
  chapters,
  activeChapterNumber,
  onActiveChapterChange,
  contents,
  loadError,
  loadingContents,
  onRetryContents,
  contentForChapter,
  logs,
  templateOptionsByStage,
  selectedPromptTemplates,
  onTemplateChange,
  llmOptions,
  selectedLlm,
  selectedModel,
  modelOptions,
  onLlmChange,
  onModelChange,
  loading,
  rehearsalMode,
  onRehearsalModeChange,
  onRunStep,
  onRunBatch,
  onPromote,
  continuityCandidates,
  continuitySummary,
  onResolveContinuityCandidate,
  onRewriteParagraph,
}: {
  chapters: ChapterPlanItem[]
  activeChapterNumber: number
  onActiveChapterChange: (value: number) => void
  contents: ProjectContent[]
  loadError?: string
  loadingContents: boolean
  onRetryContents: () => void
  contentForChapter: (contentType: string, chapterNumber: number) => ProjectContent | undefined
  logs: ProjectGenerationLog[]
  templateOptionsByStage: Record<string, TemplateOption[]>
  selectedPromptTemplates: Record<string, string>
  onTemplateChange: (stage: string, value: string) => void
  llmOptions: TemplateOption[]
  selectedLlm: string
  selectedModel: string
  modelOptions: TemplateOption[]
  onLlmChange: (value: string) => void
  onModelChange: (value: string) => void
  loading: boolean
  rehearsalMode: 'fast' | 'team'
  onRehearsalModeChange: (value: 'fast' | 'team') => void
  onRunStep: (step: string, chapterNumber: number, contentId?: string, instruction?: string, selectedText?: string) => void
  onRunBatch: (chapterNumber: number, steps?: string[], contentId?: string) => void
  onPromote: (contentId: string) => void
  continuityCandidates: CreativeProjectContinuityCandidate[]
  continuitySummary: Record<string, any> | null
  onResolveContinuityCandidate: (candidateId: string, action: 'accept' | 'ignore') => void
  onRewriteParagraph: (contentId: string, paragraphIndex: number, instruction: string) => void
}) {
  const latestWriterRoomForStep = (step: string) =>
    contents
      .filter(
        (content) =>
          content.content_type === step &&
          Number(content.chapter_number || content.episode_number || 0) === activeChapterNumber,
      )
      .sort((left, right) => right.version - left.version || String(right.created_at || '').localeCompare(String(left.created_at || '')))[0]
  const latestByStep = Object.fromEntries(
    writerRoomStepOptions.map((step) => [
      step.value,
      latestWriterRoomForStep(step.value),
    ]),
  ) as Record<string, ProjectContent | undefined>
  const canPromote = latestByStep.prose_rewrite || latestByStep.prose_humanized || latestByStep.prose_draft
  const currentNovelBody = contentForChapter('novel_body', activeChapterNumber)
  const [partialRewriteInstruction, setPartialRewriteInstruction] = useState('压低解释，增加具体动作、物件互动和对白潜台词。')
  const [selectedParagraphIndex, setSelectedParagraphIndex] = useState(0)
  const [activeStep, setActiveStep] = useState(writerRoomStepOptions[0].value)
  const [batchSteps, setBatchSteps] = useState<string[]>([
    'scene_beats',
    'character_rehearsal',
    'prose_draft',
    'prose_humanized',
    'prose_review',
  ])
  const [promoteTarget, setPromoteTarget] = useState<ProjectContent | null>(null)
  const [promoteChecked, setPromoteChecked] = useState(false)
  const [selectedContentIds, setSelectedContentIds] = useState<Record<string, string>>({})
  const [compareMode, setCompareMode] = useState<'side-by-side' | 'diff'>('side-by-side')
  const lastActiveChapterRef = useRef<number | null>(null)
  const hasAutoSelectedReadableStepRef = useRef(false)

  const versionsForStep = (step: string) =>
    contents
      .filter(
        (content) =>
          content.content_type === step &&
          Number(content.chapter_number || content.episode_number || 0) === activeChapterNumber,
      )
      .sort((left, right) => right.version - left.version || String(right.created_at || '').localeCompare(String(left.created_at || '')))

  const selectedVersionForStep = (step: string) => {
    const versions = versionsForStep(step)
    return versions.find((content) => content.id === selectedContentIds[step]) || latestByStep[step]
  }

  // A user may be inspecting an older candidate on purpose. The next Writer
  // Room action must use that visible candidate, never silently swap to the
  // newest one of the same type.
  const sourceForStep = (step: string) => {
    if (step === 'character_rehearsal') return selectedVersionForStep('scene_beats')
    if (step === 'prose_draft') return selectedVersionForStep('character_rehearsal') || selectedVersionForStep('scene_beats')
    if (step === 'prose_humanized') return selectedVersionForStep('prose_draft') || currentNovelBody
    if (step === 'prose_review' || step === 'prose_rewrite') {
      return selectedVersionForStep('prose_humanized') || selectedVersionForStep('prose_draft') || currentNovelBody
    }
    return undefined
  }
  const rewriteSource = sourceForStep('prose_rewrite')
  const rewriteParagraphs = useMemo(
    () => splitWriterRoomParagraphs(rewriteSource?.text_content || ''),
    [rewriteSource?.text_content],
  )

  const runStep = (step: string, instruction?: string) => {
    const sourceId = sourceForStep(step)?.id
    onRunStep(step, activeChapterNumber, sourceId, instruction)
  }

  const runRewriteFromIssue = (issue: WriterRoomReviewIssue) => {
    const instruction = issue.rewrite_instruction || issue.suggestion || issue.problem || ''
    onRunStep('prose_rewrite', activeChapterNumber, rewriteSource?.id, instruction)
  }

  const runRewriteFromAllIssues = (issues: WriterRoomReviewIssue[]) => {
    const instruction = issues
      .map((issue, index) => {
        const target = issue.location ? `位置：${issue.location}` : '位置：全文相关'
        const problem = issue.problem ? `问题：${issue.problem}` : ''
        const suggestion = issue.rewrite_instruction || issue.suggestion || ''
        return `${index + 1}. ${target}\n${problem}\n重写要求：${suggestion}`.trim()
      })
      .join('\n\n')
    onRunStep('prose_rewrite', activeChapterNumber, rewriteSource?.id, instruction)
  }

  const runParagraphRewrite = () => {
    if (!rewriteSource?.id) {
      message.warning('请先选择一个可重写的正文候选')
      return
    }
    if (!rewriteParagraphs.length) {
      message.warning('当前候选没有可定位的段落')
      return
    }
    onRewriteParagraph(
      rewriteSource.id,
      selectedParagraphIndex,
      partialRewriteInstruction || '只重写该段落，保留剧情事实、人物关系和前后文语气。',
    )
  }

  const writerRoomRows = writerRoomStepOptions.map((step, index) => {
    const content = latestByStep[step.value]
    const latestLog = findWriterRoomLog(logs, content)
    return {
      step,
      index,
      content,
      latestLog,
      statusColor: writerRoomStepStatusColor(content, latestLog),
      wordCount: writerRoomContentWordCount(content),
      description: writerRoomStepDescriptions[step.value] || '',
      agentName: writerRoomAgentNames[step.value] || '工序角色',
    }
  })
  const activeRow = writerRoomRows.find((row) => row.step.value === activeStep) || writerRoomRows[0]
  const activeStepVersions = versionsForStep(activeRow.step.value)
  const activeContent =
    activeStepVersions.find((content) => content.id === selectedContentIds[activeRow.step.value]) || activeRow?.content
  const activeLog = findWriterRoomLog(logs, activeContent)
  const activePreview = writerRoomPreviewText(activeContent)
  const activeTeamPerformances =
    activeContent?.content_type === 'character_rehearsal'
      ? ((activeContent.data as Record<string, any>)?.character_performances || [])
      : []
  const activeTeamJoined =
    activeContent?.content_type === 'character_rehearsal'
      ? ((activeContent.data as Record<string, any>)?.joined_observation || '')
      : ''
  const activeReviewIssues = activeRow?.step.value === 'prose_review' ? reviewIssuesForContent(activeContent) : []
  const activeQualitySummary = activeRow?.step.value === 'prose_review' ? qualitySummaryForContent(activeContent) : null
  const activeContinuityCandidates = activeContent?.content_type === 'prose_review'
    ? continuityCandidates.filter((candidate) => candidate.source_content_id === activeContent.id)
    : []
  const activeIsProseResult = ['prose_draft', 'prose_humanized', 'prose_rewrite'].includes(activeRow?.step.value || '')
  const preferredReadableStep = latestByStep.prose_rewrite
    ? 'prose_rewrite'
    : latestByStep.prose_humanized
      ? 'prose_humanized'
      : latestByStep.prose_draft
        ? 'prose_draft'
        : writerRoomStepOptions[0].value
  const activeCandidateIsPromoted = Boolean(
    activeIsProseResult && activeContent && currentNovelBody?.source_content_id === activeContent.id,
  )
  const completedCount = writerRoomRows.filter((row) => row.content).length
  const progressPercent = Math.round((completedCount / Math.max(writerRoomRows.length, 1)) * 100)
  const candidateContent = activeIsProseResult ? activeContent : canPromote
  const nextRow = writerRoomRows[activeRow.index + 1]
  const inputLabels = writerRoomStepInputs[activeRow.step.value] || []
  const outputLabels = writerRoomStepOutputs[activeRow.step.value] || []
  const nextHint = writerRoomStepNextHints[activeRow.step.value] || ''
  const batchStepOptions = writerRoomStepOptions.map((step) => ({
    label: step.label,
    value: step.value,
  }))

  useEffect(() => {
    if (lastActiveChapterRef.current !== activeChapterNumber) {
      lastActiveChapterRef.current = activeChapterNumber
      hasAutoSelectedReadableStepRef.current = preferredReadableStep !== writerRoomStepOptions[0].value
      setSelectedContentIds({})
      setActiveStep(preferredReadableStep)
      return
    }

    // Content can arrive after the workbench mounts. Auto-open the first
    // readable candidate once, but never override a deliberate step click.
    if (!hasAutoSelectedReadableStepRef.current && preferredReadableStep !== writerRoomStepOptions[0].value) {
      hasAutoSelectedReadableStepRef.current = true
      setActiveStep(preferredReadableStep)
    }
  }, [activeChapterNumber, preferredReadableStep])

  useEffect(() => {
    if (selectedParagraphIndex >= rewriteParagraphs.length) {
      setSelectedParagraphIndex(Math.max(0, rewriteParagraphs.length - 1))
    }
  }, [rewriteParagraphs.length, selectedParagraphIndex])

  const jumpToNextStep = () => {
    if (!nextRow) return
    setActiveStep(nextRow.step.value)
    if (!nextRow.content) {
      runStep(nextRow.step.value)
    }
  }

  const openPromoteDialog = (content: ProjectContent) => {
    setPromoteTarget(content)
    setPromoteChecked(false)
  }

  const confirmPromote = () => {
    if (!promoteTarget) return
    onPromote(promoteTarget.id)
    setPromoteTarget(null)
    setPromoteChecked(false)
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <section style={writerRoomShellStyle}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start" wrap>
          <Space direction="vertical" size={6} style={{ maxWidth: 760 }}>
            <Space size={8} wrap>
              <Text strong style={{ fontSize: 18 }}>小说写作室</Text>
              <Tag color="blue">分阶段写作流水线</Tag>
              <Tag>正文不自动覆盖</Tag>
            </Space>
            <Text type="secondary">
              先让导演拆戏、角色演一遍，再写初稿、做人味润色和主编审稿；每一步都保留为候选产物，确认后再提升为正式正文。
            </Text>
          </Space>
          <Space wrap align="start">
            <Select
              value={activeChapterNumber}
              style={{ width: 180 }}
              onChange={onActiveChapterChange}
              options={chapters.map((chapter) => ({
                value: chapter.chapter_number,
                label: `第 ${chapter.chapter_number} 章 ${chapter.title || ''}`,
              }))}
            />
            <Select
              placeholder="文本模型"
              value={selectedLlm || undefined}
              style={{ width: 210 }}
              options={llmOptions}
              onChange={onLlmChange}
            />
            <Select
              placeholder="模型"
              value={selectedModel || undefined}
              style={{ width: 240 }}
              options={modelOptions}
              onChange={onModelChange}
              disabled={!selectedLlm}
            />
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={loading}
              disabled={!batchSteps.length}
              onClick={() => {
                const orderedSteps = writerRoomStepOptions
                  .map((item) => item.value)
                  .filter((step) => batchSteps.includes(step))
                const source = orderedSteps.length ? sourceForStep(orderedSteps[0]) : undefined
                onRunBatch(activeChapterNumber, orderedSteps, source?.id)
              }}
            >
              按勾选生成候选
            </Button>
          </Space>
        </Space>
        <div style={writerRoomProgressStyle}>
          <Progress percent={progressPercent} size="small" showInfo={false} strokeColor="var(--primary)" />
          <Text type="secondary">已完成 {completedCount}/{writerRoomRows.length}</Text>
        </div>
        <div style={writerRoomBatchControlStyle}>
          <Segmented
            value={rehearsalMode}
            onChange={(value) => onRehearsalModeChange(value as 'fast' | 'team')}
            options={[
              { label: '角色团队推演（每角色子智能体）', value: 'team' },
              { label: '快速演绎（单模型）', value: 'fast' },
            ]}
            block
            style={{ marginBottom: 10 }}
          />
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
              <Text type="secondary">批量执行步骤</Text>
              <Space size={6}>
                <Button size="small" onClick={() => setBatchSteps(batchStepOptions.map((item) => String(item.value)))}>
                  全选
                </Button>
                <Button size="small" onClick={() => setBatchSteps(['scene_beats', 'character_rehearsal', 'prose_draft', 'prose_humanized', 'prose_review'])}>
                  推荐
                </Button>
              </Space>
            </Space>
            <Checkbox.Group
              value={batchSteps}
              options={batchStepOptions}
              onChange={(values) => setBatchSteps(values.map(String))}
            />
          </Space>
        </div>
      </section>

      <div style={writerRoomWorkspaceStyle}>
        <section style={writerRoomPipelineStyle}>
          <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
            <Space direction="vertical" size={2}>
              <Text strong>工序</Text>
              <Text type="secondary">角色演绎支持「角色团队推演」（每角色一个独立子智能体）与「快速演绎」（单模型）；其余工序为单模型分阶段执行。</Text>
            </Space>
            <div style={writerRoomStepListStyle}>
              {writerRoomRows.map((row) => {
                const isActive = row.step.value === activeRow.step.value
                return (
                  <button
                    key={row.step.value}
                    type="button"
                    onClick={() => setActiveStep(row.step.value)}
                    style={isActive ? writerRoomStepButtonActiveStyle : writerRoomStepButtonStyle}
                  >
                    <span style={writerRoomStepIndexStyle}>{row.index + 1}</span>
                    <span style={{ minWidth: 0, flex: 1 }}>
                      <span style={writerRoomStepTitleStyle}>
                        <Badge color={row.statusColor} />
                        <Text strong>{row.step.label}</Text>
                        <Tag style={{ marginLeft: 'auto' }}>{row.agentName}</Tag>
                      </span>
                      <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
                        {row.content ? `v${row.content.version} · ${row.wordCount || '-'}字` : '尚未生成'}
                      </Text>
                    </span>
                  </button>
                )
              })}
            </div>
          </Space>
        </section>

        <section style={writerRoomMainPanelStyle}>
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            {loadError ? (
              <Alert
                type="error"
                showIcon
                message="写作室候选加载失败"
                description={loadError}
                action={<Button size="small" onClick={onRetryContents}>重试读取</Button>}
              />
            ) : null}
            {loadingContents && !contents.length ? <Alert type="info" showIcon message="正在读取本章写作室候选" /> : null}
            <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start" wrap>
              <Space direction="vertical" size={4} style={{ maxWidth: 760 }}>
                <Space size={8} wrap>
                  <Text strong style={{ fontSize: 17 }}>{activeRow.step.label}</Text>
                  <Tag color="processing">{activeRow.agentName}</Tag>
                  {activeContent ? <Tag color="green">v{activeContent.version}</Tag> : <Tag>未生成</Tag>}
                  {activeStepVersions.length > 1 ? (
                    <Select
                      size="small"
                      value={activeContent?.id}
                      style={{ minWidth: 150 }}
                      onChange={(contentId) =>
                        setSelectedContentIds((previous) => ({ ...previous, [activeRow.step.value]: contentId }))
                      }
                      options={activeStepVersions.map((content) => ({
                        value: content.id,
                        label: `候选 v${content.version} · ${writerRoomContentWordCount(content)} 字`,
                      }))}
                    />
                  ) : null}
                </Space>
                <Text type="secondary">{activeRow.description}</Text>
              </Space>
              <Space wrap>
                <Button loading={loading} onClick={() => runStep(activeRow.step.value)}>
                  {activeContent ? '生成新候选' : '生成候选'}
                </Button>
              </Space>
            </Space>

            <div style={writerRoomMetricGridStyle}>
              <div style={writerRoomMetricStyle}>
                <Text type="secondary">状态</Text>
                <Text strong>{activeContent ? '已有产物' : activeLog ? activeLog.status : '等待生成'}</Text>
              </div>
              <div style={writerRoomMetricStyle}>
                <Text type="secondary">字数</Text>
                <Text strong>{writerRoomContentWordCount(activeContent) || '-'}</Text>
              </div>
              <div style={writerRoomMetricStyle}>
                <Text type="secondary">Prompt</Text>
                <Text strong>{selectedPromptTemplates[activeRow.step.value] ? '自定义' : '默认'}</Text>
              </div>
            </div>

            <div style={writerRoomContextGridStyle}>
              <div style={writerRoomContextBlockStyle}>
                <Text type="secondary">上游输入</Text>
                <Space wrap size={[4, 4]}>
                  {inputLabels.map((label) => (
                    <Tag key={label}>{label}</Tag>
                  ))}
                </Space>
                {activeContent?.source_content_id ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    本版来源：{(() => {
                      const source = contents.find((content) => content.id === activeContent.source_content_id)
                      return source ? `${writerRoomStepLabelMap[source.content_type] || source.content_type} v${source.version}` : '历史内容'
                    })()}
                  </Text>
                ) : null}
                {!activeContent && sourceForStep(activeRow.step.value) ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    将使用：{writerRoomStepLabelMap[sourceForStep(activeRow.step.value)?.content_type || ''] || sourceForStep(activeRow.step.value)?.content_type}
                    {' '}v{sourceForStep(activeRow.step.value)?.version}
                  </Text>
                ) : null}
              </div>
              <div style={writerRoomContextBlockStyle}>
                <Text type="secondary">产物用途</Text>
                <Space wrap size={[4, 4]}>
                  {outputLabels.map((label) => (
                    <Tag key={label} color="blue">{label}</Tag>
                  ))}
                </Space>
              </div>
              <div style={writerRoomContextBlockStyle}>
                <Text type="secondary">推荐下一步</Text>
                <Text>{nextHint}</Text>
                {nextRow ? (
                  <Button size="small" loading={loading} onClick={jumpToNextStep}>
                    {nextRow.content ? `查看${nextRow.step.label}` : `生成${nextRow.step.label}`}
                  </Button>
                ) : activeContent && activeIsProseResult ? (
                  <Text type="secondary">已经到最后一个节点，可以对比后提升正文。</Text>
                ) : null}
              </div>
            </div>

            <Select
              allowClear
              size="middle"
              placeholder="使用默认 Prompt"
              value={selectedPromptTemplates[activeRow.step.value] || undefined}
              options={templateOptionsByStage[activeRow.step.value] || []}
              onChange={(value) => onTemplateChange(activeRow.step.value, value || '')}
            />

            <div style={writerRoomVersionStatusStyle}>
              <Space wrap size={[6, 6]}>
                {activeIsProseResult ? (
                  <Tag color={activeCandidateIsPromoted ? 'green' : 'gold'}>
                    {activeCandidateIsPromoted ? '已提升为当前正文' : '候选稿，尚未提升'}
                  </Tag>
                ) : (
                  <Tag>工作室中间产物，不是正文</Tag>
                )}
                {currentNovelBody ? <Tag color="blue">当前正文 v{currentNovelBody.version}</Tag> : <Tag>当前章节暂无正式正文</Tag>}
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {activeIsProseResult
                  ? activeCandidateIsPromoted
                    ? '当前预览与正文阅读区使用同一版本。'
                    : '候选不会自动覆盖正文，请在下方对比后手动提升。'
                  : '场景节拍、角色演绎和审稿用于下一步写作，内容与正文不同是正常的。'}
              </Text>
            </div>

            {activeLog ? (
              <WriterRoomLogSummary log={activeLog} />
            ) : activeContent ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该历史候选暂无可追溯日志" />
            ) : null}

            {activeContent ? (
              activeTeamPerformances.length ? (
                <div style={writerRoomPreviewStyle}>
                  <TeamRehearsalPanel performances={activeTeamPerformances} joined={activeTeamJoined} />
                </div>
              ) : (
                <div style={writerRoomPreviewStyle}>
                  <Paragraph ellipsis={{ rows: 22, expandable: true }} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {activePreview}
                  </Paragraph>
                </div>
              )
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前节点还没有生成结果" />
            )}

            {activeQualitySummary ? <WriterRoomQualitySummaryPanel summary={activeQualitySummary} /> : null}
            {activeRow.step.value === 'prose_review' ? (
              <div style={writerRoomContinuityStyle}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
                    <Space direction="vertical" size={0}>
                      <Text strong>连续性事实候选</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        已锁定 {continuitySummary?.locked_fact_count || 0} 条事实，待确认 {continuitySummary?.pending_candidate_count || 0} 条
                      </Text>
                    </Space>
                    <Tag color="blue">仅确认后进入后续上下文</Tag>
                  </Space>
                  {activeContinuityCandidates.length ? activeContinuityCandidates.map((candidate) => (
                    <div key={candidate.id} style={writerRoomContinuityItemStyle}>
                      <Space direction="vertical" size={5} style={{ width: '100%' }}>
                        <Space wrap>
                          <Tag color={candidate.status === 'pending' ? 'gold' : 'green'}>{candidate.status}</Tag>
                          <Tag>{candidate.entity_type}</Tag>
                          <Tag color="blue">{candidate.target_fact_type}</Tag>
                          {candidate.entity_name ? <Text strong>{candidate.entity_name}</Text> : null}
                        </Space>
                        <Text>{candidate.claim || candidate.evidence_excerpt}</Text>
                        {candidate.evidence_excerpt ? <Text type="secondary" style={{ fontSize: 12 }}>证据：{candidate.evidence_excerpt}</Text> : null}
                        {candidate.status === 'pending' ? (
                          <Space>
                            <Button size="small" type="primary" loading={loading} onClick={() => onResolveContinuityCandidate(candidate.id, 'accept')}>确认事实</Button>
                            <Button size="small" loading={loading} onClick={() => onResolveContinuityCandidate(candidate.id, 'ignore')}>忽略</Button>
                          </Space>
                        ) : null}
                      </Space>
                    </div>
                  )) : <Text type="secondary">当前审稿没有提取到需要锁定的连续性事实。</Text>}
                </Space>
              </div>
            ) : null}

            {activeReviewIssues.length ? (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
                  <Text strong>可执行审稿意见</Text>
                  <Button size="small" loading={loading} onClick={() => runRewriteFromAllIssues(activeReviewIssues)}>
                    应用全部重写
                  </Button>
                </Space>
                {activeReviewIssues.slice(0, 6).map((issue, index) => (
                  <div key={`${issue.category || 'issue'}-${index}`} style={writerRoomIssueStyle}>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Space wrap>
                        <Tag color={writerRoomIssueSeverityColor(issue.severity)}>{issue.severity || 'normal'}</Tag>
                        {issue.category ? <Tag>{issue.category}</Tag> : null}
                        {issue.location ? <Text type="secondary">{issue.location}</Text> : null}
                      </Space>
                      {issue.problem ? <Text>{issue.problem}</Text> : null}
                      {issue.suggestion || issue.rewrite_instruction ? (
                        <Text type="secondary">{issue.rewrite_instruction || issue.suggestion}</Text>
                      ) : null}
                      <Button size="small" loading={loading} onClick={() => runRewriteFromIssue(issue)}>
                        按此问题重写
                      </Button>
                    </Space>
                  </div>
                ))}
              </Space>
            ) : null}
          </Space>
        </section>
      </div>

      <section style={panelStyle}>
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
            <Space direction="vertical" size={4}>
              <Space wrap>
                <Text strong>正文对比</Text>
                {currentNovelBody ? <Tag>正式 v{currentNovelBody.version}</Tag> : <Tag>暂无正式正文</Tag>}
                {candidateContent ? <Tag color="processing">{writerRoomStepLabelMap[candidateContent.content_type] || candidateContent.content_type} v{candidateContent.version}</Tag> : null}
              </Space>
              {candidateContent?.source_content_id ? <Text type="secondary" style={{ fontSize: 12 }}>候选来源已绑定到内容版本，可从上方生成日志回溯请求与响应。</Text> : null}
            </Space>
            <Space wrap>
              <Segmented
                size="small"
                value={compareMode}
                onChange={(value) => setCompareMode(value as 'side-by-side' | 'diff')}
                options={[{ label: '并列阅读', value: 'side-by-side' }, { label: '仅看差异', value: 'diff' }]}
              />
              {candidateContent ? (
                <Button type="primary" loading={loading} onClick={() => openPromoteDialog(candidateContent)}>
                  审核并提升候选
                </Button>
              ) : null}
            </Space>
          </Space>
          {candidateContent ? (
            compareMode === 'diff' ? (
              <ProseParagraphDiff approvedText={currentNovelBody?.text_content || ''} candidateText={candidateContent.text_content || ''} />
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 360px), 1fr))', gap: 12 }}>
                <div style={writerRoomComparePaneStyle}>
                  <Text type="secondary">当前正文</Text>
                  <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 16, expandable: true }}>
                    {currentNovelBody?.text_content || '当前章节还没有正式正文'}
                  </Paragraph>
                </div>
                <div style={writerRoomComparePaneStyle}>
                  <Text type="secondary">写作室候选</Text>
                  <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 16, expandable: true }}>
                    {candidateContent.text_content}
                  </Paragraph>
                </div>
              </div>
            )
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有正文初稿、润色或重写结果" />
        )}
        </Space>
      </section>

      <Modal
        title="人工确认后提升为正文"
        open={Boolean(promoteTarget)}
        onCancel={() => {
          setPromoteTarget(null)
          setPromoteChecked(false)
        }}
        onOk={confirmPromote}
        okText="确认提升为正文"
        cancelText="再看看"
        okButtonProps={{ disabled: !promoteChecked, loading }}
        width={860}
      >
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
          <Text type="secondary">
            提升会创建新的正式正文版本，旧正文会保留为历史版本。建议先确认候选正文已经通过审稿或人工阅读。
          </Text>
          <div style={writerRoomPromoteSummaryStyle}>
            <div style={writerRoomMetricStyle}>
              <Text type="secondary">当前正文</Text>
              <Text strong>{writerRoomContentWordCount(currentNovelBody) || '-'} 字</Text>
              <Text type="secondary">v{currentNovelBody?.version || '-'}</Text>
            </div>
            <div style={writerRoomMetricStyle}>
              <Text type="secondary">候选来源</Text>
              <Text strong>{promoteTarget ? writerRoomStepLabelMap[promoteTarget.content_type] || promoteTarget.content_type : '-'}</Text>
              <Text type="secondary">v{promoteTarget?.version || '-'}</Text>
            </div>
            <div style={writerRoomMetricStyle}>
              <Text type="secondary">候选正文</Text>
              <Text strong>{writerRoomContentWordCount(promoteTarget || undefined) || '-'} 字</Text>
              <Text type="secondary">{promoteTarget?.created_at || '-'}</Text>
            </div>
          </div>
          <div style={writerRoomComparePaneStyle}>
            <Text type="secondary">候选预览</Text>
            <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 14, expandable: true }}>
              {promoteTarget?.text_content || '无正文内容'}
            </Paragraph>
          </div>
          <Checkbox checked={promoteChecked} onChange={(event) => setPromoteChecked(event.target.checked)}>
            我已确认候选正文质量、剧情连续性和角色声音，可以作为本章新的正式正文版本。
          </Checkbox>
        </Space>
      </Modal>

      <section style={panelStyle}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space direction="vertical" size={2}>
            <Text strong>段落锚点重写</Text>
            <Text type="secondary">从当前候选正文里选择一个段落，只生成新的候选版本，不覆盖正式正文。</Text>
          </Space>
          <Select
            value={selectedParagraphIndex}
            onChange={(value) => setSelectedParagraphIndex(Number(value))}
            options={rewriteParagraphs.map((paragraph, index) => ({
              value: index,
              label: `段落 ${index + 1} · ${paragraph.slice(0, 40) || '空段落'}`,
            }))}
            placeholder="选择要重写的段落"
            disabled={!rewriteParagraphs.length}
          />
          <div style={writerRoomParagraphListStyle}>
            {rewriteParagraphs.length ? rewriteParagraphs.map((paragraph, index) => {
              const isActive = index === selectedParagraphIndex
              return (
                <button
                  key={`${index}-${paragraph.slice(0, 12)}`}
                  type="button"
                  onClick={() => setSelectedParagraphIndex(index)}
                  style={{
                    ...writerRoomParagraphButtonStyle,
                    ...(isActive ? writerRoomParagraphButtonActiveStyle : {}),
                  }}
                >
                  <Text strong>段落 {index + 1}</Text>
                  <Text type="secondary" style={{ display: 'block', marginTop: 4, whiteSpace: 'pre-wrap' }}>
                    {paragraph}
                  </Text>
                </button>
              )
            }) : <Empty description="当前候选没有可重写的段落" />}
          </div>
          <TextArea
            value={partialRewriteInstruction}
            onChange={(event) => setPartialRewriteInstruction(event.target.value)}
            placeholder="局部重写要求，例如：压低解释，增加动作和潜台词"
            autoSize={{ minRows: 2, maxRows: 5 }}
          />
          <Space wrap>
            <Button type="primary" loading={loading} onClick={runParagraphRewrite}>
              生成新的候选版本
            </Button>
            <Button onClick={() => setSelectedParagraphIndex(0)}>
              回到首段
            </Button>
            <Button onClick={() => setSelectedParagraphIndex(Math.max(0, rewriteParagraphs.length - 1))}>跳到末段</Button>
          </Space>
        </Space>
      </section>
    </Space>
  )
}

function ScriptTab({
  novelBodies,
  comicPages,
  chapterPlan,
  onSendImagePrompt,
  inlineImages,
  inlineImageLoadingKey,
  projectTitle = '',
}: {
  novelBodies: ProjectContent[]
  comicPages: ProjectContent[]
  chapterPlan?: any
  onSendImagePrompt: (prompt: string, context?: ImagePromptContext) => void
  inlineImages: Record<string, InlineGeneratedImage>
  inlineImageLoadingKey: string | null
  projectTitle?: string
}) {
  const sortedNovelBodies = useMemo(() => latestProjectContentsByChapter(novelBodies), [novelBodies])
  const sortedComicPages = useMemo(() => sortProjectContentsForReading(comicPages), [comicPages])
  const [activeReaderId, setActiveReaderId] = useState<string>('')
  const renderInlineImage = (context: ImagePromptContext) => {
    const key = imageContextKey(context)
    return <InlineImageResult image={inlineImages[key]} loading={inlineImageLoadingKey === key} />
  }
  const activeReaderBody =
    sortedNovelBodies.find((body) => body.id === activeReaderId) ||
    sortedNovelBodies[0]
  const activeReaderIndex = activeReaderBody
    ? sortedNovelBodies.findIndex((body) => body.id === activeReaderBody.id)
    : -1
  const plannedChapterCount = Number(chapterPlan?.chapter_count || 0)
  const actualPlanChapterCount = Array.isArray(chapterPlan?.chapters) ? chapterPlan.chapters.length : 0
  const allNovelMarkdown = sortedNovelBodies.map(buildNovelChapterMarkdown).join('\n\n')
  // 文件名优先使用当前项目名（从父组件传下来），去除文件名非法字符
  const safeProjectTitle = (projectTitle || '').trim().replace(/[\\/:*?"<>|]/g, '_')
  const exportTitle = safeProjectTitle || (sortedNovelBodies[0]?.title ? 'creative-project-novel' : 'novel')

  useEffect(() => {
    if (!sortedNovelBodies.length) {
      setActiveReaderId('')
      return
    }
    if (!sortedNovelBodies.some((body) => body.id === activeReaderId)) {
      setActiveReaderId(sortedNovelBodies[0].id)
    }
  }, [activeReaderId, sortedNovelBodies])

  if (!sortedNovelBodies.length && !comicPages.length) {
    return (
      <Space direction="vertical" size={12} style={{ width: '100%', alignItems: 'center', padding: 40 }}>
        <Empty description="还没有可阅读的正文或漫画页，请先在单话工作台生成正文/漫画页" />
      </Space>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Tabs
        items={[
          {
            key: 'reader',
            label: `正文阅读 ${sortedNovelBodies.length ? `(${sortedNovelBodies.length})` : ''}`,
            children: sortedNovelBodies.length ? (
              <div style={readerLayoutStyle}>
                <aside style={readerTocStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Text strong>章节目录</Text>
                      <Tag color="green">{sortedNovelBodies.length} 章正文</Tag>
                    </Space>
                    {plannedChapterCount && plannedChapterCount !== actualPlanChapterCount ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        规划标记 {plannedChapterCount} 章，实际规划 {actualPlanChapterCount || sortedNovelBodies.length} 章。
                      </Text>
                    ) : null}
                    <div style={readerTocListStyle}>
                      {sortedNovelBodies.map((body) => {
                        const isActive = body.id === activeReaderBody?.id
                        const chapterNumber = body.chapter_number || body.episode_number || '-'
                        return (
                          <button
                            key={body.id}
                            type="button"
                            onClick={() => setActiveReaderId(body.id)}
                            style={{
                              ...readerTocButtonStyle,
                              ...(isActive ? readerTocButtonActiveStyle : null),
                            }}
                            title={body.title}
                          >
                            <span>第 {chapterNumber} 章</span>
                            <strong>{body.title}</strong>
                          </button>
                        )
                      })}
                    </div>
                    <Button
                      block
                      onClick={() => downloadTextFile(`${exportTitle}.md`, allNovelMarkdown)}
                    >
                      导出全文
                    </Button>
                  </Space>
                </aside>
                <article style={readerPanelStyle}>
                  {activeReaderBody ? (
                    <Space direction="vertical" size={14} style={{ width: '100%' }}>
                      <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                        <div>
                          <Title level={4} style={{ margin: 0 }}>
                            {activeReaderBody.title}
                          </Title>
                          <Text type="secondary">
                            第 {activeReaderBody.chapter_number || '-'} 章 · v{activeReaderBody.version} · {textForNovelBody(activeReaderBody).length} 字
                          </Text>
                        </div>
                        <Space wrap>
                          <Button
                            disabled={activeReaderIndex <= 0}
                            onClick={() => setActiveReaderId(sortedNovelBodies[activeReaderIndex - 1]?.id)}
                          >
                            上一章
                          </Button>
                          <Button
                            disabled={activeReaderIndex < 0 || activeReaderIndex >= sortedNovelBodies.length - 1}
                            onClick={() => setActiveReaderId(sortedNovelBodies[activeReaderIndex + 1]?.id)}
                          >
                            下一章
                          </Button>
                          <Button
                            onClick={() =>
                              downloadTextFile(
                                `chapter-${activeReaderBody.chapter_number || activeReaderIndex + 1}.md`,
                                buildNovelChapterMarkdown(activeReaderBody),
                              )
                            }
                          >
                            导出本章
                          </Button>
                          <Tooltip title="复制当前章节正文">
                            <Button
                              icon={<CopyOutlined />}
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(compactNovelReaderText(textForNovelBody(activeReaderBody)))
                                  message.success('本章正文已复制')
                                } catch {
                                  message.error('复制失败，请检查浏览器剪贴板权限')
                                }
                              }}
                            >
                              复制本章
                            </Button>
                          </Tooltip>
                        </Space>
                      </Space>
                      <Paragraph style={readerTextStyle}>{compactNovelReaderText(textForNovelBody(activeReaderBody))}</Paragraph>
                    </Space>
                  ) : (
                    <Empty description="还没有正文，请先在单话工作台生成正文" />
                  )}
                </article>
              </div>
            ) : (
              <Empty description="还没有正文，请先在单话工作台生成正文" />
            ),
          },
          {
            key: 'comic',
            label: `漫画预览 ${comicPages.length ? `(${comicPages.length})` : ''}`,
            children: comicPages.length ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {sortedComicPages.map((comic) => (
                  <div key={comic.id} style={panelStyle}>
                    <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }} align="start">
                      <div>
                        <Text strong>{comic.title}</Text>
                        <div>
                          <Text type="secondary">
                            第 {comic.chapter_number || '-'} 章 · {comic.data?.page_count || comic.data?.pages?.length || 0} 页 · v{comic.version}
                          </Text>
                        </div>
                      </div>
                    </Space>
                    <div style={comicPreviewGridStyle}>
                      {(comic.data?.pages || []).map((page: any, index: number) => (
                        <div key={page.page_number} style={comicPreviewPageStyle}>
                          <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                            <Text strong>第 {page.page_number} 页</Text>
                            {page.image_prompt && (
                              <Button
                                size="small"
                                onClick={() =>
                                  onSendImagePrompt(page.image_prompt, {
                                    contentId: comic.id,
                                    sourceType: 'comic_page',
                                    sourceIndex: page.page_number || index + 1,
                                    sourceTitle: page.title || `第 ${index + 1} 页`,
                                    chapterNumber: comic.chapter_number,
                                    referenceAssetIds: page.reference_asset_ids || [],
                                    characterIds: page.character_ids || [],
                                    portraitNodeIds: page.portrait_node_ids || [],
                                    portraitVersionIds: page.portrait_version_ids || [],
                                  })
                                }
                              >
                                生图
                              </Button>
                            )}
                          </Space>
                          {page.title ? <Text type="secondary">{page.title}</Text> : null}
                          <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>
                            {page.content}
                          </Paragraph>
                          {renderInlineImage({
                            contentId: comic.id,
                            sourceType: 'comic_page',
                            sourceIndex: page.page_number || index + 1,
                            chapterNumber: comic.chapter_number,
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </Space>
            ) : (
              <Empty description="还没有漫画页，请先在单话工作台生成漫画页" />
            ),
          },
        ]}
      />
    </Space>
  )
}

function PromptTemplateSelect({
  value,
  options,
  placeholder,
  onChange,
}: {
  value?: string
  options: TemplateOption[]
  placeholder: string
  onChange: (value: string) => void
}) {
  return (
    <Select
      allowClear
      showSearch
      placeholder={options.length ? placeholder : `${placeholder}（内置默认）`}
      value={value || undefined}
      options={options}
      optionFilterProp="label"
      style={{ minWidth: 220, textAlign: 'left' }}
      onChange={(next) => onChange(next || '')}
    />
  )
}

function LogsTab({
  logs,
  onRefresh,
}: {
  logs: ProjectGenerationLog[]
  onRefresh: () => void
}) {
  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 190,
      render: (value: string) => <Text type="secondary">{value ? new Date(value).toLocaleString() : '-'}</Text>,
    },
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 120,
      render: (value: string) => <Tag>{stageLabels[value] || value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 130,
      render: (value: string) => (
        <Tag color={value === 'success' ? 'green' : value === 'success_repaired' ? 'blue' : 'red'}>
          {value}
        </Tag>
      ),
    },
    {
      title: '模型',
      key: 'model',
      render: (_: unknown, record: ProjectGenerationLog) => (
        <Space direction="vertical" size={0}>
          <Text>{record.provider || '-'}</Text>
          <Text type="secondary">{record.model || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '模板',
      key: 'template',
      render: (_: unknown, record: ProjectGenerationLog) => (
        record.prompt_template ? (
          <Space direction="vertical" size={0}>
            <Text>{record.prompt_template.name || record.prompt_template.platform || '-'}</Text>
            <Text type="secondary">{record.prompt_template.template_stage || record.stage}</Text>
          </Space>
        ) : (
          <Text type="secondary">内置默认</Text>
        )
      ),
    },
    {
      title: '错误',
      dataIndex: 'validation_error',
      ellipsis: true,
      render: (value: string) => value ? <Text type="danger">{value}</Text> : <Text type="secondary">-</Text>,
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Text type="secondary">记录当前项目的 AI 生成请求、响应、模板、模型和校验错误。</Text>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          刷新日志
        </Button>
      </Space>
      {logs.length ? (
        <Table
          size="small"
          rowKey="id"
          columns={columns}
          dataSource={logs}
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender: (record: ProjectGenerationLog) => (
              <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
                <LogTextBlock title="Prompt" value={record.prompt} rows={8} />
                <LogTextBlock title="请求 JSON" value={JSON.stringify(record.request || {}, null, 2)} rows={6} />
                <LogTextBlock title="原始响应" value={record.raw_response || ''} rows={8} />
                <LogTextBlock title="规范化 JSON" value={JSON.stringify(record.normalized || {}, null, 2)} rows={8} />
                {record.validation_error ? (
                  <LogTextBlock title="错误" value={record.validation_error} rows={3} />
                ) : null}
              </Space>
            ),
          }}
        />
      ) : (
        <Empty description="暂无生成日志" />
      )}
    </Space>
  )
}

function LogTextBlock({ title, value, rows }: { title: string; value: string; rows: number }) {
  return (
    <div>
      <Text strong>{title}</Text>
      <TextArea
        rows={rows}
        value={value || ''}
        readOnly
        style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 12 }}
      />
    </div>
  )
}

function ChapterRail({
  theme,
  chapters,
  activeChapterNumber,
  contents,
  writerRoomSummary,
  ledger,
  health,
  onChapterChange,
}: {
  theme: ThemeColors
  chapters: ChapterPlanItem[]
  activeChapterNumber: number
  contents: ProjectContent[]
  writerRoomSummary: ProjectContentSummary[]
  ledger: NarrativeForeshadowing[]
  health: NarrativeHealth | null
  onChapterChange: (chapterNumber: number) => void | Promise<void>
}) {
  const candidateTypes = new Set(['prose_draft', 'prose_humanized', 'prose_rewrite'])
  const healthIssuesByChapter = useMemo(() => {
    const result = new Map<number, NarrativeHealth['issues']>()
    for (const issue of health?.issues || []) {
      const details = issue.details || {}
      const values = [
        details.chapter_number,
        ...(Array.isArray(details.chapter_numbers) ? details.chapter_numbers : []),
      ]
      for (const value of values) {
        const chapterNumber = Number(value)
        if (!Number.isInteger(chapterNumber) || chapterNumber < 1) continue
        result.set(chapterNumber, [...(result.get(chapterNumber) || []), issue])
      }
    }
    return result
  }, [health])

  const chapterRows = useMemo(() => chapters
    .map((chapter) => {
      const chapterNumber = Number(chapter.chapter_number)
      const approved = contents.some((item) => item.content_type === 'novel_body' && Number(item.chapter_number || item.episode_number) === chapterNumber)
      const candidateCount = writerRoomSummary.filter((item) => candidateTypes.has(item.content_type) && Number(item.chapter_number || item.episode_number) === chapterNumber).length
      const reviewed = writerRoomSummary.some((item) => item.content_type === 'prose_review' && Number(item.chapter_number || item.episode_number) === chapterNumber)
      const ledgerCount = ledger.filter((item) => item.planted_chapter === chapterNumber && !['ignored', 'superseded'].includes(item.status)).length
      const issues = healthIssuesByChapter.get(chapterNumber) || []
      return { chapter, chapterNumber, approved, candidateCount, reviewed, ledgerCount, issues }
    })
    .filter((row) => Number.isInteger(row.chapterNumber) && row.chapterNumber > 0)
    .sort((left, right) => left.chapterNumber - right.chapterNumber), [chapters, contents, writerRoomSummary, ledger, healthIssuesByChapter])

  const healthColor = health?.status === 'blocked' ? '#cf1322' : health?.status === 'attention' ? '#d46b08' : '#389e0d'
  const healthLabel = health?.status === 'blocked' ? '需要处理' : health?.status === 'attention' ? '有待处理项' : '健康'

  return (
    <section style={{ marginTop: 'auto', borderTop: `1px solid ${theme.border}`, minHeight: 0 }} aria-label="章节轨">
      <div style={{ padding: '12px 16px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Space size={7}>
          <FileTextOutlined style={{ color: theme.primary }} />
          <Text strong>章节轨</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{chapterRows.length}</Text>
        </Space>
        <Tooltip title={health ? `${healthLabel}：${health?.summary?.issue_count || 0} 项` : '正在读取健康检查'}>
          <span style={{ display: 'inline-flex', alignItems: 'center', color: healthColor }}>
            {health?.status === 'healthy' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
          </span>
        </Tooltip>
      </div>
      {chapterRows.length ? (
        <div style={{ maxHeight: 350, overflowY: 'auto', padding: '0 8px 10px' }}>
          {chapterRows.map((row) => {
            const isActive = row.chapterNumber === activeChapterNumber
            const statusMarkers = [
              { key: 'plan', label: '已规划', color: theme.primary, visible: true },
              { key: 'approved', label: '正式正文', color: '#389e0d', visible: row.approved },
              { key: 'candidate', label: `${row.candidateCount} 个正文候选`, color: '#722ed1', visible: row.candidateCount > 0 },
              { key: 'review', label: '已有主编审稿', color: '#13a8a8', visible: row.reviewed },
              { key: 'ledger', label: `${row.ledgerCount} 条伏笔记录`, color: '#d48806', visible: row.ledgerCount > 0 },
              { key: 'health', label: row.issues.map((issue) => issue.message).join('；'), color: '#cf1322', visible: row.issues.length > 0 },
            ].filter((marker) => marker.visible)
            return (
              <button
                key={row.chapterNumber}
                type="button"
                onClick={() => void onChapterChange(row.chapterNumber)}
                aria-current={isActive ? 'step' : undefined}
                style={{
                  appearance: 'none',
                  border: 0,
                  borderLeft: `2px solid ${isActive ? theme.primary : 'transparent'}`,
                  background: isActive ? theme.primaryAlpha(0.1) : 'transparent',
                  color: theme.textPrimary,
                  cursor: 'pointer',
                  display: 'block',
                  padding: '9px 8px 8px 10px',
                  textAlign: 'left',
                  width: '100%',
                }}
              >
                <div style={{ alignItems: 'baseline', display: 'flex', gap: 7, minWidth: 0 }}>
                  <Text strong style={{ color: theme.textPrimary, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>#{row.chapterNumber}</Text>
                  <Text ellipsis={{ tooltip: row.chapter.title }} style={{ color: theme.textPrimary, minWidth: 0 }}>{row.chapter.title || `第 ${row.chapterNumber} 章`}</Text>
                </div>
                <div style={{ alignItems: 'center', display: 'flex', gap: 5, marginTop: 6, minHeight: 8 }}>
                  {statusMarkers.map((marker) => (
                    <Tooltip key={marker.key} title={marker.label}>
                      <span
                        aria-label={marker.label}
                        style={{ background: marker.color, borderRadius: '50%', display: 'inline-block', height: 6, width: 6 }}
                      />
                    </Tooltip>
                  ))}
                </div>
              </button>
            )
          })}
        </div>
      ) : (
        <div style={{ padding: '4px 16px 16px' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>生成章节规划后，会在这里展示写作与审阅状态。</Text>
        </div>
      )}
    </section>
  )
}

function NarrativeInspector({
  theme,
  chapterNumber,
  context,
  ledger,
  graph,
  facts,
  continuityCandidates,
  continuitySummary,
  logs,
  runs,
  loading,
  onRefresh,
  onDecision,
  onRunControl,
  onAutopilot,
  onOpenWriterRoom,
  onOpenFacts,
}: {
  theme: ThemeColors
  chapterNumber: number
  context: NarrativeContextPreview | null
  ledger: NarrativeForeshadowing[]
  graph: NarrativeGraphData | null
  facts: ProjectContent[]
  continuityCandidates: CreativeProjectContinuityCandidate[]
  continuitySummary: Record<string, any> | null
  logs: ProjectGenerationLog[]
  runs: NarrativeRun[]
  loading: boolean
  onRefresh: () => void
  onDecision: (itemId: string, action: 'accept' | 'advance' | 'resolve' | 'ignore') => Promise<void>
  onRunControl: (runId: string, action: 'pause' | 'resume' | 'retry' | 'cancel') => Promise<void>
  onAutopilot: (enabled: boolean) => Promise<void>
  onOpenWriterRoom: () => void
  onOpenFacts: () => void
}) {
  const [activeTab, setActiveTab] = useState('context')
  const overflow = context?.metadata?.overflow || []
  const layers = context?.metadata?.layers || []
  const activeLedger = ledger.filter((item) => ['active', 'advanced', 'overdue'].includes(item.status))
  const pendingLedger = ledger.filter((item) => item.status === 'pending_review')
  const pendingFacts = continuityCandidates.filter((candidate) => candidate.status === 'pending')
  const lockedFacts = facts.filter((item) => item.is_locked)

  return (
    <div style={{ minWidth: 0 }}>
      <header style={{ padding: '14px 14px 10px', borderBottom: `1px solid ${theme.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <Space size={7}>
            <BranchesOutlined style={{ color: theme.primary }} />
            <Text strong>叙事检查器</Text>
          </Space>
          <Tooltip title="刷新叙事状态">
            <Button type="text" size="small" icon={<ReloadOutlined />} aria-label="刷新叙事状态" loading={loading} onClick={onRefresh} />
          </Tooltip>
        </div>
        <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
          第 {chapterNumber} 章
          {context?.metadata?.fingerprint ? ` · ${context.metadata.fingerprint.slice(0, 8)}` : ''}
        </Text>
      </header>
      <Tabs
        size="small"
        activeKey={activeTab}
        onChange={setActiveTab}
        tabBarStyle={{ margin: '0 12px' }}
        items={[
          {
            key: 'context',
            label: '上下文',
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                {overflow.length ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="锁定设定超过上下文预算"
                    description={overflow.map((item) => `${item.layer}: ${item.actual}/${item.budget}`).join('；')}
                    style={{ marginBottom: 12 }}
                  />
                ) : null}
                {layers.length ? (
                  <List
                    size="small"
                    dataSource={layers}
                    renderItem={(layer) => (
                      <List.Item style={{ padding: '8px 0' }}>
                        <Space direction="vertical" size={1} style={{ width: '100%' }}>
                          <Space size={6}>
                            <Tag bordered={false}>{layer.id}</Tag>
                            <Text>{contextLayerLabel(layer.label)}</Text>
                          </Space>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {layer.characters || 0}/{layer.budget || 0} 字{layer.status ? ` · ${layer.status}` : ''}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可预览上下文" />
                )}
              </div>
            ),
          },
          {
            key: 'review',
            label: `审阅 ${pendingFacts.length}`,
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    待确认事实不会进入正文上下文。审稿的来源、质量意见和确认动作只在写作室中处理，避免出现两套审批入口。
                  </Text>
                  {pendingFacts.length ? (
                    <List
                      size="small"
                      dataSource={pendingFacts.slice(0, 12)}
                      renderItem={(candidate) => (
                        <List.Item style={{ display: 'block', padding: '10px 0' }}>
                          <Space direction="vertical" size={3} style={{ width: '100%' }}>
                            <Space size={6} wrap>
                              <Tag color="gold">待确认</Tag>
                              <Tag>{candidate.entity_type}</Tag>
                              {candidate.entity_name ? <Text strong>{candidate.entity_name}</Text> : null}
                            </Space>
                            <Text ellipsis={{ tooltip: candidate.claim }}>{candidate.claim || candidate.evidence_excerpt}</Text>
                            {candidate.evidence_anchor?.chapter_number ? <Text type="secondary" style={{ fontSize: 12 }}>第 {candidate.evidence_anchor.chapter_number} 章证据</Text> : null}
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有待确认的连续性事实" />
                  )}
                  <Button size="small" onClick={onOpenWriterRoom}>打开写作室审核</Button>
                </Space>
              </div>
            ),
          },
          {
            key: 'facts',
            label: `事实 ${lockedFacts.length || continuitySummary?.locked_fact_count || 0}`,
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                {lockedFacts.length ? (
                  <List
                    size="small"
                    dataSource={lockedFacts.slice(0, 16)}
                    renderItem={(item) => (
                      <List.Item style={{ display: 'block', padding: '10px 0' }}>
                        <Space direction="vertical" size={3} style={{ width: '100%' }}>
                          <Space size={6}><Tag color={item.content_type === 'project_bible' ? 'blue' : 'cyan'}>{item.content_type === 'project_bible' ? '项目圣经' : '世界设定'}</Tag><Text ellipsis>{item.title || '未命名事实'}</Text></Space>
                          <Text type="secondary" ellipsis={{ tooltip: writerRoomPreviewText(item, 320) }} style={{ fontSize: 12 }}>{writerRoomPreviewText(item, 320)}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有锁定的项目事实" />
                    <Button size="small" onClick={onOpenFacts}>打开圣经/世界设定</Button>
                  </Space>
                )}
              </div>
            ),
          },
          {
            key: 'foreshadowing',
            label: `伏笔 ${activeLedger.length + pendingLedger.length}`,
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                {ledger.length ? (
                  <List
                    size="small"
                    dataSource={ledger}
                    renderItem={(item) => (
                      <List.Item style={{ display: 'block', padding: '10px 0' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <Text ellipsis style={{ maxWidth: 190 }}>{item.statement || '未命名伏笔'}</Text>
                          <Tag color={foreshadowingColor(item.status)}>{foreshadowingLabel(item.status)}</Tag>
                        </div>
                        <Text type="secondary" style={{ display: 'block', margin: '4px 0 7px', fontSize: 12 }}>
                          第 {item.planted_chapter} 章 · {timingLabel(item.timing)}
                        </Text>
                        <Space size={4} wrap>
                          {item.status === 'pending_review' ? <Button size="small" onClick={() => void onDecision(item.id, 'accept')}>确认</Button> : null}
                          {['active', 'advanced', 'overdue'].includes(item.status) ? <Button size="small" onClick={() => void onDecision(item.id, 'advance')}>推进</Button> : null}
                          {['active', 'advanced', 'overdue'].includes(item.status) ? <Button size="small" onClick={() => void onDecision(item.id, 'resolve')}>回收</Button> : null}
                          {['pending_review', 'active', 'advanced', 'overdue'].includes(item.status) ? <Button size="small" type="text" onClick={() => void onDecision(item.id, 'ignore')}>忽略</Button> : null}
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前章节没有伏笔记录" />}
              </div>
            ),
          },
          {
            key: 'run',
            label: '运行',
            children: (
              <div style={{ padding: '10px 14px 14px' }}>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Space size={6} wrap>
                    <Tag color={context?.persisted ? 'green' : 'default'}>{context?.persisted ? '已冻结上下文' : '预览上下文'}</Tag>
                    {context?.metadata?.context_snapshot_id ? <Text code ellipsis style={{ maxWidth: 160 }}>{context.metadata.context_snapshot_id}</Text> : null}
                    <Text type="secondary" style={{ fontSize: 12 }}>本章日志 {logs.length}</Text>
                  </Space>
                  {logs.length ? (
                    <List
                      size="small"
                      dataSource={logs}
                      renderItem={(log) => (
                        <List.Item style={{ padding: '8px 0' }}>
                          <Space direction="vertical" size={3} style={{ width: '100%' }}>
                            <Space size={6} wrap><Tag color={log.status === 'success' || log.status === 'success_repaired' ? 'green' : 'red'}>{log.status}</Tag><Text>{writerRoomStepLabelMap[log.stage.replace('writer_room:', '')] || stageLabels[log.stage] || log.stage}</Text></Space>
                            <Text type="secondary" style={{ fontSize: 12 }} ellipsis>{log.model || log.provider || '未记录模型'}</Text>
                            <WriterRoomLogSummary log={log} />
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前章节还没有可追溯的生成运行" />}
                  <Space size={12} style={{ marginTop: 2 }}>
                    <Text type="secondary">叙事节点 {graph?.nodes?.length || 0}</Text>
                    <Text type="secondary">关系 {graph?.edges?.length || 0}</Text>
                  </Space>
                  <div style={{ borderTop: `1px solid ${theme.borderLight}`, paddingTop: 10 }}>
                    <Space size={6} wrap style={{ marginBottom: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>受控状态更新</Text>
                      <Button size="small" onClick={() => void onAutopilot(true)}>处理本章</Button>
                    </Space>
                    {runs.length ? <List size="small" dataSource={runs.slice(0, 4)} renderItem={(run) => (
                      <List.Item style={{ display: 'block', padding: '7px 0' }}>
                        <Space direction="vertical" size={3} style={{ width: '100%' }}>
                          <Space size={5} wrap>
                            <Tag color={run.status === 'success' ? 'green' : run.status === 'failed' ? 'red' : run.status === 'paused' ? 'gold' : 'blue'}>{run.status}</Tag>
                            <Text style={{ fontSize: 12 }}>{run.mode === 'guarded_autopilot' ? '受控推进' : run.mode === 'batch' ? '批次重建' : '章节后处理'}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{run.current_cursor}/{run.target_chapters?.length || 0} 章</Text>
                          </Space>
                          {run.error_message ? <Text type="danger" ellipsis style={{ fontSize: 12 }}>{run.error_message}</Text> : null}
                          <Text type="secondary" style={{ fontSize: 12 }}>重试 {run.retry_count || 0} 次 · 用量 {run.token_usage || 0} tokens · 费用 {run.cost_amount || 0}</Text>
                          {['running', 'paused', 'pending'].includes(run.status) ? <Space size={4}>
                            {run.status === 'running' ? <Button size="small" onClick={() => void onRunControl(run.id, 'pause')}>暂停</Button> : null}
                            {run.status === 'paused' ? <Button size="small" onClick={() => void onRunControl(run.id, 'resume')}>继续</Button> : null}
                            <Button size="small" type="text" danger onClick={() => void onRunControl(run.id, 'cancel')}>取消</Button>
                          </Space> : ['partial', 'failed'].includes(run.status) ? <Button size="small" onClick={() => void onRunControl(run.id, 'retry')}>重试失败章节</Button> : null}
                        </Space>
                      </List.Item>
                    )} /> : <Text type="secondary" style={{ fontSize: 12 }}>还没有叙事运行记录。</Text>}
                  </div>
                </Space>
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}

function contextLayerLabel(label: string) {
  return ({ locked_canon: '锁定设定', narrative_state: '叙事状态', active_foreshadowing: '已确认伏笔', chapter_contract: '章节契约', local_continuity: '前文连续性', semantic_recall: '语义召回', style_genre_skills: '文风与技能' } as Record<string, string>)[label] || label
}

function foreshadowingLabel(status: string) {
  return ({ pending_review: '待确认', active: '进行中', advanced: '已推进', resolved: '已回收', overdue: '已逾期', ignored: '已忽略', superseded: '已替换' } as Record<string, string>)[status] || status
}

function foreshadowingColor(status: string) {
  return ({ pending_review: 'default', active: 'blue', advanced: 'cyan', resolved: 'green', overdue: 'orange', ignored: 'default', superseded: 'default' } as Record<string, string>)[status]
}

function timingLabel(timing: string) {
  return ({ upcoming: '待推进', in_window: '回收窗口', overdue: '超过窗口', unscheduled: '未设窗口' } as Record<string, string>)[timing] || timing
}

function graphNodeTypeLabel(type: string) {
  return ({ character: '角色', location: '地点', organization: '组织', item: '物件', event: '事件', world_rule: '规则', chapter: '章节', foreshadowing: '伏笔' } as Record<string, string>)[type] || type
}

function NarrativeGraphTab({ graph, chapterNumber }: { graph: NarrativeGraphData | null; chapterNumber: number }) {
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const nodeTypes = ['character', 'location', 'organization', 'item', 'event', 'world_rule', 'foreshadowing', 'chapter']
  const positionedNodes = useMemo(() => {
    const buckets = new Map<string, NarrativeGraphData['nodes']>()
    for (const node of graph?.nodes || []) {
      const type = nodeTypes.includes(node.type) ? node.type : 'world_rule'
      buckets.set(type, [...(buckets.get(type) || []), node])
    }
    return (graph?.nodes || []).map((node) => {
      const type = nodeTypes.includes(node.type) ? node.type : 'world_rule'
      const typeIndex = nodeTypes.indexOf(type)
      const itemIndex = (buckets.get(type) || []).findIndex((item) => item.id === node.id)
      return { ...node, x: 40 + typeIndex * 218, y: 54 + itemIndex * 116 }
    })
  }, [graph])
  const nodeMap = useMemo(() => new Map(positionedNodes.map((node) => [node.id, node])), [positionedNodes])
  const selectedNode = nodeMap.get(selectedNodeId) || positionedNodes[0] || null
  const width = Math.max(920, nodeTypes.length * 218 + 60)
  const height = Math.max(440, ...positionedNodes.map((node) => node.y + 104))

  useEffect(() => {
    setSelectedNodeId((current) => nodeMap.has(current) ? current : positionedNodes[0]?.id || '')
  }, [nodeMap, positionedNodes])

  if (!positionedNodes.length) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description={`第 ${chapterNumber} 章还没有可视化的确认叙事关系。提升正文并完成后处理后，事件与伏笔会在这里出现。`} />
      </div>
    )
  }

  const edgePath = (edge: NarrativeGraphData['edges'][number]) => {
    const source = nodeMap.get(edge.source)
    const target = nodeMap.get(edge.target)
    if (!source || !target) return ''
    const fromX = source.x + 174
    const fromY = source.y + 42
    const toX = target.x
    const toY = target.y + 42
    const bend = Math.max(42, Math.abs(toX - fromX) / 2)
    return `M ${fromX} ${fromY} C ${fromX + bend} ${fromY}, ${toX - bend} ${toY}, ${toX} ${toY}`
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 276px', gap: 12, minHeight: 560 }}>
      <section style={{ ...panelStyle, overflow: 'hidden', padding: 0 }}>
        <div style={{ borderBottom: '1px solid var(--borderLight)', padding: '10px 12px' }}>
          <Space size={10} wrap>
            <Text strong>第 {chapterNumber} 章叙事图谱</Text>
            <Text type="secondary">{positionedNodes.length} 节点</Text>
            <Text type="secondary">{graph?.edges.length || 0} 关系</Text>
            <Tag color="green">只显示已确认事实</Tag>
          </Space>
        </div>
        <div style={{ height: 540, overflow: 'auto', background: 'var(--bgLayout)' }}>
          <div style={{ height, minWidth: width, position: 'relative' }}>
            <svg width={width} height={height} style={{ inset: 0, pointerEvents: 'none', position: 'absolute' }}>
              <defs>
                <marker id="narrative-graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
                  <path d="M 0 0 L 7 3.5 L 0 7 z" fill="var(--textTertiary)" />
                </marker>
              </defs>
              {(graph?.edges || []).map((edge) => {
                const path = edgePath(edge)
                return path ? <path key={edge.id} d={path} fill="none" markerEnd="url(#narrative-graph-arrow)" opacity={edge.confirmed ? 0.75 : 0.4} stroke="var(--textTertiary)" strokeWidth={1.4} /> : null
              })}
            </svg>
            {positionedNodes.map((node) => (
              <button
                key={node.id}
                type="button"
                onClick={() => setSelectedNodeId(node.id)}
                style={{
                  background: selectedNode?.id === node.id ? 'var(--bgHover)' : 'var(--bgCard)',
                  border: `1px solid ${selectedNode?.id === node.id ? 'var(--primary)' : 'var(--borderLight)'}`,
                  borderLeft: `3px solid ${narrativeGraphNodeColor(node.type)}`,
                  borderRadius: 6,
                  color: 'var(--textPrimary)',
                  cursor: 'pointer',
                  left: node.x,
                  minHeight: 84,
                  padding: '8px 10px',
                  position: 'absolute',
                  textAlign: 'left',
                  top: node.y,
                  width: 174,
                }}
              >
                <Space direction="vertical" size={3} style={{ width: '100%' }}>
                  <Space size={5} wrap><Tag bordered={false} color={narrativeGraphNodeColor(node.type)}>{graphNodeTypeLabel(node.type)}</Tag>{node.status ? <Tag>{foreshadowingLabel(node.status)}</Tag> : null}</Space>
                  <Text strong ellipsis={{ tooltip: node.label }} style={{ color: 'var(--textPrimary)' }}>{node.label}</Text>
                  {node.summary ? <Text type="secondary" ellipsis style={{ fontSize: 12 }}>{node.summary}</Text> : null}
                </Space>
              </button>
            ))}
          </div>
        </div>
      </section>
      <section style={panelStyle}>
        {selectedNode ? (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space direction="vertical" size={3}>
              <Tag color={narrativeGraphNodeColor(selectedNode.type)}>{graphNodeTypeLabel(selectedNode.type)}</Tag>
              <Text strong>{selectedNode.label}</Text>
              {selectedNode.summary ? <Text type="secondary">{selectedNode.summary}</Text> : null}
            </Space>
            <div>
              <Text type="secondary">来源证据</Text>
              <Space direction="vertical" size={3} style={{ display: 'flex', marginTop: 6 }}>
                {selectedNode.source?.chapter_number ? <Text>第 {selectedNode.source.chapter_number} 章</Text> : null}
                {selectedNode.source?.content_id ? <Text code ellipsis>{selectedNode.source.content_id}</Text> : null}
                {selectedNode.source?.snapshot_id ? <Text code ellipsis>{selectedNode.source.snapshot_id}</Text> : null}
                {!selectedNode.source?.content_id && !selectedNode.source?.snapshot_id ? <Text type="secondary">该节点没有额外来源标识。</Text> : null}
              </Space>
            </div>
            <div>
              <Text type="secondary">关联</Text>
              <Space direction="vertical" size={4} style={{ display: 'flex', marginTop: 6 }}>
                {(graph?.edges || []).filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).map((edge) => (
                  <Text key={edge.id} style={{ fontSize: 12 }}>{edge.source === selectedNode.id ? '->' : '<-'} {edge.type}</Text>
                ))}
              </Space>
            </div>
          </Space>
        ) : null}
      </section>
    </div>
  )
}

function narrativeGraphNodeColor(type: string) {
  return ({ character: 'blue', location: 'cyan', organization: 'purple', item: 'gold', event: 'green', world_rule: 'geekblue', chapter: 'default', foreshadowing: 'orange' } as Record<string, string>)[type] || 'default'
}

function ProjectGraphTab({
  graph,
  saving,
  generating,
  onSave,
  onOpenNode,
  onToggleLock,
  onRegenerate,
  onSendToCanvas,
  onSendImagePrompt,
}: {
  graph: ProjectGraphState
  saving: boolean
  generating: boolean
  onSave: (graph: ProjectGraphState) => Promise<void>
  onOpenNode: (node: ProjectGraphNode) => void
  onToggleLock: (node: ProjectGraphNode) => Promise<void>
  onRegenerate: (node: ProjectGraphNode) => Promise<void>
  onSendToCanvas: (node: ProjectGraphNode) => void
  onSendImagePrompt: (node: ProjectGraphNode) => void
}) {
  const [nodes, setNodes] = useState<ProjectGraphNode[]>(graph.nodes || [])
  const [selectedId, setSelectedId] = useState<string>('')
  const [dragging, setDragging] = useState<{ id: string; offsetX: number; offsetY: number } | null>(null)

  useEffect(() => {
    setNodes(graph.nodes || [])
    setSelectedId((current) => (graph.nodes || []).some((node) => node.id === current) ? current : graph.nodes?.[0]?.id || '')
  }, [graph])

  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const selectedNode = nodeMap.get(selectedId) || null
  const edges = graph.edges || []
  const width = Math.max(2200, ...nodes.map((node) => node.x + (node.width || 210) + 120), 900)
  const height = Math.max(900, ...nodes.map((node) => node.y + (node.height || 92) + 120), 520)

  const saveLayout = () =>
    onSave({
      ...graph,
      nodes,
      edges,
      viewport: graph.viewport || { x: 0, y: 0, zoom: 1 },
    })

  const startDrag = (event: React.MouseEvent, node: ProjectGraphNode) => {
    event.preventDefault()
    setSelectedId(node.id)
    setDragging({ id: node.id, offsetX: event.clientX - node.x, offsetY: event.clientY - node.y })
  }

  const moveDrag = (event: React.MouseEvent) => {
    if (!dragging) return
    const nextX = Math.max(0, event.clientX - dragging.offsetX)
    const nextY = Math.max(0, event.clientY - dragging.offsetY)
    setNodes((prev) => prev.map((node) => (node.id === dragging.id ? { ...node, x: nextX, y: nextY } : node)))
  }

  const edgePath = (edge: ProjectGraphEdge) => {
    const from = nodeMap.get(edge.from)
    const to = nodeMap.get(edge.to)
    if (!from || !to) return ''
    const fromX = from.x + (from.width || 210)
    const fromY = from.y + (from.height || 92) / 2
    const toX = to.x
    const toY = to.y + (to.height || 92) / 2
    const mid = Math.max(40, Math.abs(toX - fromX) / 2)
    return `M ${fromX} ${fromY} C ${fromX + mid} ${fromY}, ${toX - mid} ${toY}, ${toX} ${toY}`
  }

  const stats = {
    nodes: nodes.length,
    edges: edges.length,
    locked: nodes.filter((node) => node.status === 'locked').length,
    prompts: nodes.filter((node) => node.type === 'prompt').length,
    assets: nodes.filter((node) => node.type === 'asset').length,
  }

  if (!nodes.length) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description="暂无可绘制节点。先生成大纲、章节或关联素材后再查看关系图谱。" />
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 12, minHeight: 620 }}>
      <section style={{ ...panelStyle, padding: 0, overflow: 'hidden' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between', padding: 12, borderBottom: '1px solid var(--borderLight)' }} wrap>
          <Space size={[6, 6]} wrap>
            <Tag color="blue">{stats.nodes} 节点</Tag>
            <Tag>{stats.edges} 连线</Tag>
            <Tag color={stats.locked ? 'green' : 'default'}>{stats.locked} 锁定</Tag>
            <Tag color={stats.prompts ? 'purple' : 'default'}>{stats.prompts} Prompt</Tag>
            <Tag color={stats.assets ? 'cyan' : 'default'}>{stats.assets} 素材</Tag>
          </Space>
          <Space>
            <Button loading={saving} onClick={saveLayout}>保存布局</Button>
          </Space>
        </Space>
        <div
          style={{ position: 'relative', height: 620, overflow: 'auto', background: 'var(--bgLayout)' }}
          onMouseMove={moveDrag}
          onMouseUp={() => setDragging(null)}
          onMouseLeave={() => setDragging(null)}
        >
          <div style={{ position: 'relative', width, height }}>
            <svg width={width} height={height} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
              <defs>
                <marker id="project-graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--textTertiary)" />
                </marker>
              </defs>
              {edges.map((edge) => {
                const path = edgePath(edge)
                if (!path) return null
                return (
                  <path
                    key={edge.id}
                    d={path}
                    stroke={graphEdgeColor(edge.type)}
                    strokeWidth={1.6}
                    fill="none"
                    markerEnd="url(#project-graph-arrow)"
                    opacity={0.78}
                  />
                )
              })}
            </svg>
            {nodes.map((node) => (
              <div
                key={node.id}
                onMouseDown={(event) => startDrag(event, node)}
                onDoubleClick={() => onOpenNode(node)}
                style={{
                  ...graphNodeStyle(node, selectedId === node.id),
                  left: node.x,
                  top: node.y,
                  width: node.width || 210,
                  minHeight: node.height || 92,
                }}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <Tag color={graphNodeColor(node.type)} style={{ marginInlineEnd: 0 }}>{graphNodeLabel(node.type)}</Tag>
                    {node.status ? <Tag color={node.status === 'locked' ? 'green' : 'default'} style={{ marginInlineEnd: 0 }}>{node.status}</Tag> : null}
                  </Space>
                  <Text strong ellipsis={{ tooltip: node.label }}>{node.label}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: node.subtitle }}>
                    {node.subtitle || node.id}
                  </Text>
                </Space>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ ...panelStyle, minHeight: 620 }}>
        {selectedNode ? (
          <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Tag color={graphNodeColor(selectedNode.type)}>{graphNodeLabel(selectedNode.type)}</Tag>
              <Title level={5} style={{ margin: 0 }}>{selectedNode.label}</Title>
              <Text type="secondary">{selectedNode.subtitle || selectedNode.id}</Text>
            </Space>
            <Space size={[6, 6]} wrap>
              <Button size="small" onClick={() => onOpenNode(selectedNode)}>打开来源</Button>
              <Button size="small" icon={<BranchesOutlined />} onClick={() => onSendToCanvas(selectedNode)}>发送到画布</Button>
              {(selectedNode.type === 'chapter' || selectedNode.type === 'content') ? (
                <Button size="small" onClick={() => onToggleLock(selectedNode)}>
                  {selectedNode.status === 'locked' ? '解除锁定' : '锁定'}
                </Button>
              ) : null}
              {selectedNode.type === 'outline' || selectedNode.type === 'chapter' || selectedNode.type === 'content' ? (
                <Button size="small" loading={generating} onClick={() => onRegenerate(selectedNode)}>再生成</Button>
              ) : null}
              {selectedNode.type === 'prompt' ? (
                <Button size="small" type="primary" loading={generating} onClick={() => onSendImagePrompt(selectedNode)}>
                  生图入库
                </Button>
              ) : null}
            </Space>
            <div>
              <Text strong>关系</Text>
              <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                {edges
                  .filter((edge) => edge.from === selectedNode.id || edge.to === selectedNode.id)
                  .slice(0, 24)
                  .map((edge) => (
                    <Text key={edge.id} type="secondary" style={{ fontSize: 12 }}>
                      {edge.from === selectedNode.id ? '->' : '<-'} {edge.type} {edge.label ? `/${edge.label}` : ''}
                    </Text>
                  ))}
              </Space>
            </div>
            <div>
              <Text strong>数据</Text>
              <TextArea
                rows={14}
                value={JSON.stringify({ source: selectedNode.source, data: selectedNode.data }, null, 2)}
                readOnly
                style={{ marginTop: 8, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 12 }}
              />
            </div>
          </Space>
        ) : (
          <Empty description="选择一个节点查看详情" />
        )}
      </section>
    </div>
  )
}

function graphNodeLabel(type: ProjectGraphNodeType) {
  const labels: Record<ProjectGraphNodeType, string> = {
    outline: '大纲',
    chapter: '章节',
    character: '角色',
    content: '内容',
    scene: '场景',
    prompt: 'Prompt',
    asset: '素材',
  }
  return labels[type] || type
}

function graphNodeColor(type: ProjectGraphNodeType) {
  const colors: Record<ProjectGraphNodeType, string> = {
    outline: 'blue',
    chapter: 'geekblue',
    character: 'cyan',
    content: 'purple',
    scene: 'orange',
    prompt: 'magenta',
    asset: 'green',
  }
  return colors[type] || 'default'
}

function graphEdgeColor(type: ProjectGraphEdge['type']) {
  const colors: Record<ProjectGraphEdge['type'], string> = {
    contains: 'var(--textTertiary)',
    uses: '#7c3aed',
    references: '#0891b2',
    derived_from: '#16a34a',
  }
  return colors[type] || 'var(--textTertiary)'
}

function graphNodeStyle(node: ProjectGraphNode, selected: boolean): React.CSSProperties {
  return {
    position: 'absolute',
    border: selected ? '2px solid var(--primary)' : '1px solid var(--borderLight)',
    borderRadius: 8,
    padding: 10,
    background: 'var(--bgElevated)',
    boxShadow: selected ? '0 10px 30px rgba(0, 0, 0, 0.18)' : '0 6px 18px rgba(0, 0, 0, 0.08)',
    cursor: 'grab',
    userSelect: 'none',
    color: 'var(--textPrimary)',
    outline: node.type === 'prompt' ? '1px dashed rgba(168, 85, 247, 0.35)' : undefined,
  }
}

function JsonTab({
  outline,
  chapterPlan,
  contents,
  assets,
}: {
  outline: any
  chapterPlan: any
  contents: ProjectContent[]
  assets: ProjectAssetLink[]
}) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Text strong>故事大纲 JSON</Text>
        <TextArea rows={10} value={JSON.stringify(outline || {}, null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
      <div>
        <Text strong>章节规划 JSON</Text>
        <TextArea rows={10} value={JSON.stringify(chapterPlan || {}, null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
      <div>
        <Text strong>阶段内容 JSON</Text>
        <TextArea rows={8} value={JSON.stringify(contents || [], null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
      <div>
        <Text strong>项目素材 JSON</Text>
        <TextArea rows={6} value={JSON.stringify(assets || [], null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
    </Space>
  )
}

function AssetsTab({
  assets,
  unavailableAssetIds,
  loading,
  onLinkAsset,
}: {
  assets: ProjectAssetLink[]
  unavailableAssetIds: Record<string, true>
  loading: boolean
  onLinkAsset: (assetId: string, role: string) => void
}) {
  const [assetId, setAssetId] = useState('')
  const [role, setRole] = useState('reference')

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={panelStyle}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={assetId}
            onChange={(event) => setAssetId(event.target.value)}
            placeholder="输入素材 asset_id，先手动关联；后续由生成流程自动回写"
          />
          <Select
            value={role}
            onChange={setRole}
            style={{ width: 140 }}
            options={[
              { label: '参考', value: 'reference' },
              { label: '角色', value: 'character' },
              { label: '背景', value: 'background' },
              { label: '画风', value: 'style' },
              { label: '世界观', value: 'world' },
              { label: '输出', value: 'output' },
              { label: '封面', value: 'cover' },
            ]}
          />
          <Button
            type="primary"
            loading={loading}
            onClick={() => {
              onLinkAsset(assetId, role)
              setAssetId('')
            }}
          >
            关联
          </Button>
        </Space.Compact>
      </div>

      {assets.length ? (
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={assets}
          columns={[
            {
              title: '素材 ID',
              dataIndex: 'asset_id',
              ellipsis: true,
              render: (assetId: string) => (
                <Space size={6}>
                  <Text code ellipsis style={{ maxWidth: 190 }}>{assetId}</Text>
                  {unavailableAssetIds[assetId] ? <Tag color="warning">素材库中已不可用</Tag> : null}
                </Space>
              ),
            },
            {
              title: '角色',
              dataIndex: 'role',
              width: 120,
              render: (value: string) => <Tag>{value}</Tag>,
            },
            {
              title: '关系',
              dataIndex: 'relation',
              width: 140,
              render: (value: string) => <Text type="secondary">{value}</Text>,
            },
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 190,
              render: (value: string) => value || '-',
            },
          ]}
        />
      ) : (
        <Empty description="暂无项目素材关联" />
      )}
    </Space>
  )
}

function InfoBlock({ title, text, compact = false }: { title: string; text?: string; compact?: boolean }) {
  return (
    <div style={panelStyle}>
      <Text type="secondary">{title}</Text>
      <Paragraph
        style={{ margin: compact ? '4px 0 0' : '8px 0 0' }}
        ellipsis={compact ? { rows: 4 } : { rows: 5 }}
      >
        {text || '未填写'}
      </Paragraph>
    </div>
  )
}

function InfoListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={panelStyle}>
      <Text type="secondary">{title}</Text>
      {items?.length ? (
        <Space size={[4, 4]} wrap style={{ marginTop: 8 }}>
          {items.map((item, index) => (
            <Tag key={`${item}-${index}`}>{item}</Tag>
          ))}
        </Space>
      ) : (
        <Paragraph style={{ margin: '8px 0 0' }}>未填写</Paragraph>
      )}
    </div>
  )
}

function projectTypeLabel(value: string) {
  return projectTypeOptions.find((item) => item.value === value)?.label || value
}

const panelStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 14,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

function createWorkbenchHeaderStyle(theme: ThemeColors): React.CSSProperties {
  return {
  border: `1px solid ${theme.borderLight}`,
  borderRadius: 8,
  padding: 14,
  background: theme.bgElevated,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 16,
  color: theme.textPrimary,
  }
}

function createCompactBlockStyle(theme: ThemeColors): React.CSSProperties {
  return {
  border: `1px solid ${theme.borderLight}`,
  borderRadius: 8,
  padding: 10,
  background: theme.bgElevated,
  color: theme.textPrimary,
  }
}

const readerPanelStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: '22px 26px',
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  minWidth: 0,
}

const readerTextStyle: React.CSSProperties = {
  margin: '18px 0 0',
  whiteSpace: 'pre-wrap',
  fontSize: 16,
  lineHeight: 1.9,
  color: 'var(--textPrimary)',
}

const readerLayoutStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '260px minmax(0, 1fr)',
  gap: 12,
  alignItems: 'start',
}

const readerTocStyle: React.CSSProperties = {
  ...panelStyle,
  position: 'sticky',
  top: 12,
}

const readerTocListStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  maxHeight: 520,
  overflow: 'auto',
}

const readerTocButtonStyle: React.CSSProperties = {
  width: '100%',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: '8px 10px',
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  textAlign: 'left',
  cursor: 'pointer',
  display: 'grid',
  gap: 2,
}

const readerTocButtonActiveStyle: React.CSSProperties = {
  borderColor: 'var(--primary)',
  background: 'var(--bgHover)',
}

const writerRoomComparePaneStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 12,
  background: 'var(--bgCard)',
  minWidth: 0,
}

const writerRoomDiffListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  maxHeight: 720,
  overflow: 'auto',
  paddingRight: 4,
}

const writerRoomDiffRowStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgCard)',
}

const writerRoomDiffColumnsStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))',
  gap: 8,
  marginTop: 8,
}

const writerRoomDiffTextStyle: React.CSSProperties = {
  borderRadius: 6,
  minWidth: 0,
  padding: '8px 10px',
}

const writerRoomShellStyle: React.CSSProperties = {
  ...panelStyle,
  background: 'linear-gradient(135deg, var(--bgElevated), var(--bgCard))',
}

const writerRoomProgressStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(160px, 1fr) auto',
  gap: 10,
  alignItems: 'center',
  marginTop: 12,
}

const writerRoomBatchControlStyle: React.CSSProperties = {
  marginTop: 12,
  borderTop: '1px solid var(--borderLight)',
  paddingTop: 12,
}

const writerRoomWorkspaceStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(min(100%, 280px), 0.42fr) minmax(min(100%, 420px), 1fr)',
  gap: 12,
  alignItems: 'start',
}

const writerRoomPipelineStyle: React.CSSProperties = {
  ...panelStyle,
  position: 'sticky',
  top: 12,
}

const writerRoomStepListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
}

const writerRoomStepButtonStyle: React.CSSProperties = {
  width: '100%',
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: '10px 11px',
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
  textAlign: 'left',
  cursor: 'pointer',
  transition: 'border-color 160ms ease, background 160ms ease, transform 160ms ease',
}

const writerRoomStepButtonActiveStyle: React.CSSProperties = {
  ...writerRoomStepButtonStyle,
  border: '1px solid var(--primary)',
  background: 'var(--bgHover)',
  transform: 'translateX(2px)',
}

const writerRoomStepIndexStyle: React.CSSProperties = {
  width: 24,
  height: 24,
  borderRadius: 6,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flex: '0 0 auto',
  background: 'var(--bgElevated)',
  border: '1px solid var(--borderLight)',
  color: 'var(--textSecondary)',
  fontSize: 12,
}

const writerRoomStepTitleStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  minWidth: 0,
}

const writerRoomMainPanelStyle: React.CSSProperties = {
  ...panelStyle,
  minWidth: 0,
}

const writerRoomMetricGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
  gap: 8,
}

const writerRoomMetricStyle: React.CSSProperties = {
  display: 'grid',
  gap: 4,
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

const writerRoomContextGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
  gap: 8,
}

const writerRoomContextBlockStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
  minWidth: 0,
}

const writerRoomPreviewStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 12,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  minHeight: 260,
  maxHeight: 680,
  overflow: 'auto',
}

const writerRoomVersionStatusStyle: React.CSSProperties = {
  display: 'grid',
  gap: 6,
  padding: '10px 12px',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  background: 'var(--bgElevated)',
}

const writerRoomPromoteSummaryStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
  gap: 8,
}

const writerRoomIssueStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
}

const writerRoomContinuityStyle: React.CSSProperties = {
  borderTop: '1px solid var(--border-color)',
  paddingTop: 14,
}

const writerRoomContinuityItemStyle: React.CSSProperties = {
  border: '1px solid var(--border-color)',
  borderRadius: 6,
  padding: '10px 12px',
  background: 'var(--component-background)',
}

const writerRoomParagraphListStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  maxHeight: 320,
  overflow: 'auto',
  paddingRight: 4,
}

const writerRoomParagraphButtonStyle: React.CSSProperties = {
  width: '100%',
  textAlign: 'left',
  border: '1px solid var(--border-color)',
  borderRadius: 6,
  background: 'var(--component-background)',
  padding: '10px 12px',
  cursor: 'pointer',
}

const writerRoomParagraphButtonActiveStyle: React.CSSProperties = {
  borderColor: 'var(--primary)',
  boxShadow: 'inset 3px 0 0 var(--primary)',
}

const writerRoomQualityStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgHover)',
  color: 'var(--textPrimary)',
}

const writerRoomTeamGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
  alignItems: 'start',
}

const writerRoomTeamRoleStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderLeft: '3px solid var(--primary)',
  borderRadius: 10,
  background: 'var(--bgCard)',
  color: 'var(--textPrimary)',
  overflow: 'hidden',
  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
}

const writerRoomTeamRoleHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '12px 14px',
  cursor: 'pointer',
  userSelect: 'none',
  transition: 'background 0.2s ease',
}

const writerRoomTeamAvatarStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: '50%',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bgHover)',
  border: '1px solid var(--borderLight)',
  color: 'var(--textPrimary)',
  fontSize: 13,
  fontWeight: 600,
  flexShrink: 0,
}

const writerRoomTeamRoleBodyStyle: React.CSSProperties = {
  padding: '4px 14px 14px',
  borderTop: '1px solid var(--borderLight)',
  background: 'var(--bgElevated)',
}

const writerRoomTeamJoinStyle: React.CSSProperties = {
  borderTop: '1px dashed var(--borderLight)',
  paddingTop: 12,
}

const writerRoomLogBlockStyle: React.CSSProperties = {
  margin: 0,
  maxHeight: 260,
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

const comicPreviewGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
}

const comicPreviewPageStyle: React.CSSProperties = {
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 12,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  minHeight: 180,
}

const inlineImageShellStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  alignItems: 'center',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 10,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

const referenceAssetCardStyle: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  alignItems: 'center',
  border: '1px solid var(--borderLight)',
  borderRadius: 8,
  padding: 8,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
}

const referenceAssetPlaceholderStyle: React.CSSProperties = {
  width: 52,
  height: 52,
  borderRadius: 6,
  border: '1px solid var(--borderLight)',
  background: 'var(--bgInput)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--textSecondary)',
}

function createResizeHandleStyle(_theme: ThemeColors): React.CSSProperties {
  return {
  alignSelf: 'stretch',
  minHeight: 120,
  cursor: 'col-resize',
  display: 'flex',
  alignItems: 'stretch',
  justifyContent: 'center',
  borderRadius: 8,
  transition: 'background 120ms ease',
  }
}

function createResizeHandleLineStyle(theme: ThemeColors): React.CSSProperties {
  return {
  width: 2,
  borderRadius: 2,
  background: theme.borderStrong,
  margin: '8px 0',
  }
}
