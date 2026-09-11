import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
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
  EnvironmentOutlined,
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
  extractCreativeProjectCharacters,
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
  saveCreativeProjectContentPackage,
  planCreativeProjectContentPackage,
  getTask,
  updateCreativeProject,
  updateCreativeProjectContent,
  type PlatformTemplate,
  type CreativeProjectContinuityCandidate,
} from '../../api'
import {
  startProjectWorldExtraction,
  listProjectWorldDomains,
  listProjectWorldEntities,
  listProjectWorldEntityRelations,
  listWorldBuildingSuggestions,
  confirmSuggestedField,
  ignoreSuggestedField,
  upsertProjectWorldDomain,
  resetProjectWorldDomain,
  previewEntityExpansion,
  expandEntityAttributes,
  expandWorldDomain,
  draftWorldTemplate,
  listWorldTemplates,
  upsertWorldTemplate,
  deleteWorldTemplate,
  type WorldBuildingSuggestions,
  type WorldBuildingTemplate,
  type WorldDomainExpansionTask,
  type WorldEntity,
  type WorldEntityRelation,
} from '../../api/novelSource'
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
import { worldFieldLabel, worldFieldValueText } from '../../utils/worldFieldLabels'
import ProviderModelSelect from '../../components/ai/ProviderModelSelect'
import useLlmConnectors from '../../hooks/useLlmConnectors'
import { enqueueCanvasImport } from '../../components/canvas/bridge'
import type { CanvasNode, CanvasNodeType } from '../../components/canvas/types'
import { useTaskPolling } from '../../hooks/useTaskPolling'
import FanqiePublishPanel from './FanqiePublishPanel'
import ProjectStatePanel from './ProjectStatePanel'
import StoryWorkspaceOverview from './StoryWorkspaceOverview'
import type { AssetSummary, ChapterAction, CharacterReferenceSummary, EditableChapterPlanItem, ImageBackendOption, ImagePromptContext, InlineGeneratedImage, LoadingAction, NarrativeContextPreview, NarrativeForeshadowing, NarrativeGraphData, NarrativeHealth, NarrativeRun, PendingInlineImageTask, PipelineResult, PipelineResultItem, PipelineRunStatus, PipelineStageValue, ProductionStageItem, ProjectAssetLink, ProjectContent, ProjectContentSummary, ProjectGenerationLog, ProjectGraphEdge, ProjectGraphNode, ProjectGraphNodeType, ProjectGraphState, ProseDiffRow, ReferenceImageItem, StoryboardPanelReferencePlan, StoryboardReferenceSummary, TemplateOption, VideoGenerationContext, WorkspaceResource, WriterRoomQualitySummary, WriterRoomReviewIssue } from './types'
import { comicPreviewGridStyle, comicPreviewPageStyle, createCompactBlockStyle, createResizeHandleLineStyle, createResizeHandleStyle, createWorkbenchHeaderStyle, graphNodeStyle, inlineImageShellStyle, panelStyle, readerLayoutStyle, readerPanelStyle, readerTextStyle, readerTocButtonActiveStyle, readerTocButtonStyle, readerTocListStyle, readerTocStyle, referenceAssetCardStyle, referenceAssetPlaceholderStyle, writerRoomBatchControlStyle, writerRoomComparePaneStyle, writerRoomContextBlockStyle, writerRoomContextGridStyle, writerRoomContinuityItemStyle, writerRoomContinuityStyle, writerRoomDiffColumnsStyle, writerRoomDiffListStyle, writerRoomDiffRowStyle, writerRoomDiffTextStyle, writerRoomIssueStyle, writerRoomLogBlockStyle, writerRoomMainPanelStyle, writerRoomMetricGridStyle, writerRoomMetricStyle, writerRoomParagraphButtonActiveStyle, writerRoomParagraphButtonStyle, writerRoomParagraphListStyle, writerRoomPipelineStyle, writerRoomPreviewStyle, writerRoomProgressStyle, writerRoomPromoteSummaryStyle, writerRoomQualityStyle, writerRoomShellStyle, writerRoomStepButtonActiveStyle, writerRoomStepButtonStyle, writerRoomStepIndexStyle, writerRoomStepListStyle, writerRoomStepTitleStyle, writerRoomTeamAvatarStyle, writerRoomTeamGridStyle, writerRoomTeamJoinStyle, writerRoomTeamRoleBodyStyle, writerRoomTeamRoleHeaderStyle, writerRoomTeamRoleStyle, writerRoomVersionStatusStyle, writerRoomWorkspaceStyle } from './styles'
import { STORY_WORKSPACE_CONTENT_TYPES, assetFileUrl, buildChapterPlanMarkdown, buildCreativeProjectGraph, buildNovelChapterMarkdown, buildOutlineMarkdown, buildProseDiffRows, buildScriptMarkdown, buildStoryboardMarkdown, buildStoryboardPanelReferencePlan, buildStoryboardReferenceSummary, buildStoryboardVideoFallbackPrompt, canvasTypeForGraphNode, collectStoryboardCharacterIds, comicStyleOptions, compactNovelReaderText, contextLayerLabel, dedupeProjectAssetLinks, dedupeReferenceImageItems, dedupeStrings, downloadTextFile, escapePreviewHtml, findWriterRoomLog, foreshadowingColor, foreshadowingLabel, getCharacterReferenceItems, getNovelChapterOptions, getNovelDisplayTitle, getPipelineFailedRows, getPipelineSummary, graphEdgeColor, graphNodeColor, graphNodeLabel, graphNodeToCanvasNode, graphNodeTypeLabel, imageContextKey, isChapterLocked, isPipelineStageValue, isProjectContentNewer, latestProjectContentsByChapter, linesToList, listToLines, markdownList, markdownSection, narrativeGraphNodeColor, normalizeChapterItem, normalizeChapterPlan, normalizeCharacterReference, normalizeStoryboardVideoDuration, openProjectTextPreview, parseChapterRange, pipelineStageLabels, pipelineStageOptions, portraitNodeToReferenceItem, productionProfileOptions, projectAssetDetailRequests, projectAssetToReferenceItem, projectContentChapterKey, projectMarkdownFilename, projectTypeLabel, projectTypeOptions, qualitySummaryForContent, referenceRoleOptions, resolveProjectAssetDetail, reviewIssuesForContent, selectReferenceAssetsForPrompt, sortBibleContents, sortProjectContentsForReading, splitWriterRoomParagraphs, stageLabels, statusLabels, textForNovelBody, timingLabel, unavailableProjectAssetIds, worldAssetRoleLabels, writerRoomAgentNames, writerRoomContentWordCount, writerRoomIssueSeverityColor, writerRoomPreviewText, writerRoomStepDescriptions, writerRoomStepInputs, writerRoomStepLabelMap, writerRoomStepNextHints, writerRoomStepOptions, writerRoomStepOutputs, writerRoomStepStatusColor } from './utils'
import { EditorField, InfoBlock, InfoListBlock, LogTextBlock, PromptTemplateSelect, ResizeHandle, WorkbenchSection } from './components/common'
import { useStoryLayout } from './hooks/useStoryLayout'
import { InlineImageResult, ReferenceAssetCard, ReferenceAssetPreviewStrip, ReferenceCardsPanel, StoryboardReferenceDiagnostics, StoryboardReferencePreflight, StoryboardVideoOutputStrip } from './components/storyboard-parts'
import { CharacterRehearsalCard, ProseParagraphDiff, TeamRehearsalPanel, WriterRoomLogSummary, WriterRoomQualitySummaryPanel } from './components/writer-room-parts'
import { BibleContentCard, ProjectBibleTab } from './components/bible'
import { OutlineTab, PipelinePanel, ProductionStageRail } from './components/outline'
import { ScriptTab } from './components/storyboard'
import { ChapterRail, ChapterTab, EpisodeWorkbenchTab } from './components/chapter-studio'
import { WriterRoomTab } from './components/writer-room'
import { NarrativeGraphTab, NarrativeInspector, ProjectGraphTab } from './components/graph'
import { AssetsTab, JsonTab, LogsTab } from './components/tabs'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

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
  const [characterExtractionOpen, setCharacterExtractionOpen] = useState(false)
  const [characterExtractionLoading, setCharacterExtractionLoading] = useState(false)
  const [characterExtractionResult, setCharacterExtractionResult] = useState<any | null>(null)
  const characterCreateHandledRef = useRef(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [fanqieOpen, setFanqieOpen] = useState(false)
  const [contentPackageOpen, setContentPackageOpen] = useState(false)
  const [pendingContentPackageProjectId, setPendingContentPackageProjectId] = useState('')
  const [contentPackageBatchRunning, setContentPackageBatchRunning] = useState(false)
  const [renameForm] = Form.useForm()
  const [contentPackageForm] = Form.useForm()
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
  // 默认展开运行设置：项目顶部四个下拉/标签全部可见
  const [runtimeSettingsOpen, setRuntimeSettingsOpen] = useState(true)
  const [form] = Form.useForm()
  const createSourceType = Form.useWatch('source_type', form) || 'original_idea'
  const createProductionProfile = Form.useWatch('production_profile', form) || 'vertical_drama'
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
  const contentPackageContent = contents
    .filter((item) => item.content_type === 'content_package')
    .sort((left, right) => right.version - left.version)[0]
  const contentPackageData = contentPackageContent?.data || null
  const isContentPackageProject = selectedProject?.production_profile?.production_family === 'content_package'

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
  const createProfile = productionProfileOptions.find((item) => item.value === createProductionProfile)
  const createIsContentPackage = createProfile?.family === 'content_package'
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

  // 切换项目时，从项目 metadata 恢复顶部"文本模型 / 模型"选择
  // 流程：selectedProject 切换 -> 清空 + 标记"待恢复" -> 等 connectors 加载完 -> 回填
  // 之后用户手动改 onChange 时也会通过 persistChatModel 写回 metadata，无需再恢复。
  const chatModelRestoredRef = useRef<string>('')
  useEffect(() => {
    if (!selectedProject) return
    if (chatModelRestoredRef.current === selectedProject.id) {
      // 当前项目已恢复过，跳过
      return
    }
    if (llmConnectors.length === 0) {
      // connectors 还没就绪
      return
    }
    chatModelRestoredRef.current = selectedProject.id
    const meta = selectedProject.metadata || {}
    const persistedProvider = meta.default_chat_provider as string | undefined
    const persistedModel = meta.default_chat_model as string | undefined
    if (persistedProvider && llmConnectors.some((c) => c.name === persistedProvider)) {
      setSelectedLlm(persistedProvider)
      setSelectedModel(persistedModel || '')
      return
    }
    // 项目没持久化，使用系统默认连接器
    const def = llmConnectors.find((c) => c.is_default)
      || [...llmConnectors].sort((a, b) => (a.priority || 0) - (b.priority || 0))[0]
    if (def) {
      setSelectedLlm(def.name)
      setSelectedModel(def.default_model || '')
    } else {
      setSelectedLlm('')
      setSelectedModel('')
    }
  }, [selectedProject?.id, llmConnectors])

  useEffect(() => {
    const requestedProjectId = searchParams.get('project_id')
    if (requestedProjectId && projects.some((item) => item.id === requestedProjectId)) {
      setSelectedId(requestedProjectId)
    }
  }, [projects, searchParams])

  useEffect(() => {
    if (characterCreateHandledRef.current || searchParams.get('new') !== '1') return
    const requestedCharacterId = searchParams.get('character_id')
    if (!requestedCharacterId) return
    characterCreateHandledRef.current = true
    fetch(`/api/v1/characters/${encodeURIComponent(requestedCharacterId)}`, { headers: { Accept: 'application/json' } })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('角色加载失败')))
      .then((result) => {
        const character = result.data || result
        const identity = character.identity || {}
        const idea = `${character.name || '角色'}：${character.appearance || character.personality || '围绕该角色展开一个新故事'}`
        form.setFieldsValue({ source_type: 'original_idea', project_type: 'short_drama', production_profile: 'vertical_drama', title: character.name ? `${character.name}的新故事` : '', idea, creation_brief: `已有角色设定：${JSON.stringify({ identity, motivation: character.motivation || {}, speech: character.speech || {}, behavior: character.behavior || {} }, null, 2)}` })
        setCreateOpen(true)
      })
      .catch((error: any) => message.error(error?.message || '无法读取角色设定'))
  }, [form, searchParams])

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
    return { assetId: assetId || '', url: urls[0] || '', localPath: localPaths[0] || data.local_path || '' }
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
        return finalizeInlineImageResult(data, task)
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
          return waitForInlineImageTask(pendingTask)
        }
        startedAsyncTask = true
        setPendingInlineImageTask(pendingTask)
        message.info(`图片任务已提交，完成后自动回写项目：${data.task_id}`)
        return { taskId: String(data.task_id), pending: true }
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
      return { assetId: assetId || '', url: urls[0] || '', localPath: localPaths[0] || data.local_path || '' }
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

  // 持久化：项目顶部"文本模型 / 模型"选择会写入项目 metadata，
  // 刷新页面后能恢复（与默认生图模型一致的处理方式）。
  async function persistChatModel(provider: string, model: string) {
    if (!selectedProject) return
    const nextMeta = {
      ...(selectedProject.metadata || {}),
      default_chat_provider: provider,
      default_chat_model: model,
    }
    try {
      const response = (await updateCreativeProject(selectedProject.id, { metadata: nextMeta })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
    } catch (error: any) {
      message.error(error?.message || '保存文本模型失败')
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
          production_profile: values.production_profile,
        })) as CreativeProjectResponse
      } else {
        response = (await createCreativeProject({
          title: values.title,
          idea: values.idea,
          project_type: values.project_type,
           production_profile: values.production_profile,
           source_type: 'original_idea',
           character_id: searchParams.get('character_id') || undefined,
           metadata: values.creation_brief ? { creation_brief: values.creation_brief } : undefined,
        })) as CreativeProjectResponse
      }
      message.success('项目已创建')
      setCreateOpen(false)
      form.resetFields()
      if (response.data.production_profile?.production_family === 'content_package') {
        setPendingContentPackageProjectId(response.data.id)
      }
      await loadProjects(response.data.id)
    } catch (error: any) {
      message.error(error?.message || '创建失败')
    } finally {
      setLoadingAction(null)
    }
  }

  useEffect(() => {
    if (!pendingContentPackageProjectId || selectedProject?.id !== pendingContentPackageProjectId) return
    setPendingContentPackageProjectId('')
    openContentPackageEditor()
  }, [pendingContentPackageProjectId, selectedProject?.id])

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

  function openContentPackageEditor() {
    if (!selectedProject || !isContentPackageProject) return
    const existing = contentPackageData || {}
    contentPackageForm.setFieldsValue({
      title: existing.title || selectedProject.title,
      topic: existing.topic || idea || selectedProject.title,
      brief: existing.brief || String(selectedProject.metadata?.creation_brief || ''),
      items: Array.isArray(existing.items) && existing.items.length
        ? existing.items
        : [{ title: '', text: '', fact: '', source: '', source_url: '', image_prompt: '' }],
    })
    setContentPackageOpen(true)
  }

  async function handleSaveContentPackage(values: any) {
    if (!selectedProject) return
    setLoadingAction('create')
    try {
      await saveCreativeProjectContentPackage(
        selectedProject.id,
        {
          package_type: selectedProject.production_profile?.package_type,
          title: values.title,
          topic: values.topic,
          brief: values.brief,
          items: (values.items || []).map((item: any, index: number) => ({
            ...item,
            id: item.id || `item-${index + 1}`,
            index: index + 1,
            status: item.status || 'draft',
          })),
        },
        contentPackageContent?.id,
      )
      message.success('内容包已保存为新版本')
      setContentPackageOpen(false)
      await loadContents(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '保存内容包失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handlePlanContentPackage() {
    if (!selectedProject || !isContentPackageProject) return
    const values = contentPackageForm.getFieldsValue()
    if (!String(values.topic || '').trim()) {
      message.warning('请先填写主题')
      return
    }
    setLoadingAction('create')
    try {
      const response: any = await planCreativeProjectContentPackage(selectedProject.id, {
        topic: String(values.topic).trim(),
        brief: String(values.brief || ''),
        item_count: Math.max(1, Math.min(Number(values.item_count || 12), 80)),
        prompt_only: Boolean(values.prompt_only),
      })
      const generated = response?.data?.data || response?.data || {}
      contentPackageForm.setFieldsValue({
        title: generated.title || values.title || selectedProject.title,
        topic: generated.topic || values.topic,
        brief: generated.brief || values.brief || '',
        items: Array.isArray(generated.items) ? generated.items : [],
      })
      await loadContents(selectedProject.id)
      message.success('内容包已生成并保存，可继续编辑')
    } catch (error: any) {
      message.error(error?.message || '生成内容包失败')
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleGenerateContentPackageImage(index: number, fieldName: number) {
    if (!selectedProject) return
    const item = contentPackageForm.getFieldValue(['items', fieldName]) || {}
    const prompt = String(item.image_prompt || '').trim()
    if (!prompt) {
      message.warning('请先填写图片提示词')
      return
    }
    await handleInlineGenerateImage(prompt, {
      contentId: contentPackageContent?.id,
      sourceType: 'content_package',
      sourceIndex: index,
      sourceTitle: String(item.title || `内容单元 ${index + 1}`),
    }, { awaitAsync: true })
  }

  async function handleBatchGenerateContentPackageImages() {
    if (!selectedProject || !contentPackageContent) return
    const values = contentPackageForm.getFieldsValue(true)
    const items = Array.isArray(values.items) ? values.items : []
    const targets = items
      .map((item: any, index: number) => ({ item, index }))
      .filter(({ item }: any) => String(item?.image_prompt || '').trim())
    if (!targets.length) {
      message.warning('当前内容包没有可用的图片提示词')
      return
    }
    setContentPackageBatchRunning(true)
    let generated = 0
    let failed = 0
    try {
      for (const { item, index } of targets) {
        contentPackageForm.setFieldValue(['items', index, 'status'], 'generating')
        try {
          const result: any = await handleInlineGenerateImage(String(item.image_prompt).trim(), {
            contentId: contentPackageContent.id,
            sourceType: 'content_package',
            sourceIndex: index,
            sourceTitle: String(item.title || `内容单元 ${index + 1}`),
          }, { awaitAsync: true })
          contentPackageForm.setFieldValue(['items', index, 'status'], result?.assetId ? 'succeeded' : 'ready')
          if (result?.assetId) {
            contentPackageForm.setFieldValue(['items', index, 'asset_ids'], [result.assetId])
            contentPackageForm.setFieldValue(['items', index, 'image_url'], result.url || '')
          }
          generated += result?.assetId ? 1 : 0
        } catch (error: any) {
          contentPackageForm.setFieldValue(['items', index, 'status'], 'failed')
          failed += 1
          message.error(`${item.title || `第 ${index + 1} 项`}：${error?.message || '生图失败'}`)
        }
      }
      const latest = contentPackageForm.getFieldsValue(true)
      await saveCreativeProjectContentPackage(
        selectedProject.id,
        {
          package_type: selectedProject.production_profile?.package_type,
          title: latest.title,
          topic: latest.topic,
          brief: latest.brief,
          items: (latest.items || []).map((item: any, index: number) => ({
            ...item,
            id: item.id || `item-${index + 1}`,
            index: index + 1,
          })),
        },
        contentPackageContent.id,
      )
      await loadContents(selectedProject.id)
      message.success(`批量生图完成：成功 ${generated}，失败 ${failed}`)
    } finally {
      setContentPackageBatchRunning(false)
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

  async function handleExtractCharacters(apply = false) {
    if (!selectedProject) return
    setCharacterExtractionLoading(true)
    try {
      const response: any = await extractCreativeProjectCharacters(selectedProject.id, {
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        apply,
        cards: apply ? (characterExtractionResult?.characters || undefined) : undefined,
      })
      const result = response.data || response.result || response
      setCharacterExtractionResult(result)
      setCharacterExtractionOpen(true)
      if (apply) {
        message.success(`已写入 ${result.applied_characters?.length || 0} 个角色`)
        await refreshSelected(selectedProject)
        await loadProjectAssets(selectedProject.id)
      }
    } catch (error: any) {
      message.error(error?.message || '提取角色失败')
    } finally {
      setCharacterExtractionLoading(false)
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

  const handleExtractWorld = async () => {
    if (!selectedProject) return
    setLoadingAction('world_extract')
    try {
      const result = await startProjectWorldExtraction(selectedProject.id, {
        model: selectedModel || undefined,
      })
      if (!result.run_id) {
        throw new Error(result.status || '提取未返回运行')
      }
      message.success(`已生成 ${result.candidate_count} 条世界设定候选，正在打开审阅`)
      window.location.href = `/novel-world?snapshot_id=${encodeURIComponent(result.snapshot_id)}&run_id=${encodeURIComponent(result.run_id)}`
    } catch (error: any) {
      message.error(error?.message || '生成世界设定候选失败')
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
      const loadedCharacters = await loadCharacterDetailsForIds([record.character_id])
      const referenceImages = dedupeReferenceImageItems(
        getCharacterReferenceItems(loadedCharacters[record.character_id] || characterDetails[record.character_id]),
      ).map((item) => item.url).filter(Boolean)
      const response = await generateCharacterPortrait(record.character_id, {
        prompt,
        provider: defaultImageModel.name,
        model: defaultImageModel.model || undefined,
        size,
        n: 1,
        reference_images: referenceImages,
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
           {record.character_id ? (
             <Button
               size="small"
               type="link"
               style={{ padding: 0, alignSelf: 'flex-start' }}
               onClick={() => navigate(`/characters/${encodeURIComponent(record.character_id as string)}`)}
             >
               打开角色详情
             </Button>
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
          {selectedProject ? (
            <Space size={6} wrap>
              {productionStages.map(stage => (
                <Tooltip key={stage.key} title={`${stage.label} · ${stage.complete}/${stage.total}`}>
                  <Tag
                    style={{ margin: 0, borderRadius: 999, lineHeight: '20px', padding: '0 8px', fontSize: 12, cursor: 'pointer' }}
                    color={stage.complete >= stage.total ? 'success' : 'processing'}
                    onClick={() => openWorkspaceTab(stage.tab)}
                  >
                    {stage.label}
                  </Tag>
                </Tooltip>
              ))}
            </Space>
          ) : null}
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
              const nextModel = connector?.default_model || ''
              setSelectedLlm(value)
              setSelectedModel(nextModel)
              // 写入项目 metadata，刷新后能恢复
              persistChatModel(value, nextModel)
            }}
          />
            <Select
            placeholder="模型"
            value={selectedModel || undefined}
            style={{ width: 210 }}
            options={modelOptions}
            onChange={(value) => {
              setSelectedModel(value)
              if (selectedLlm) {
                persistChatModel(selectedLlm, value)
              }
            }}
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
            ? cockpitCompact ? '48px 0 minmax(0, 1fr)' : '48px 0 minmax(0, 1fr)' + (inspectorOpen ? ' minmax(246px, 300px)' : '')
            : cockpitCompact
              ? `${projectLibraryWidth}px 10px minmax(0, 1fr)`
              : `${projectLibraryWidth}px 10px minmax(0, 1fr)` + (inspectorOpen ? ' minmax(246px, 300px)' : ''),
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
                        {selectedProject.production_profile?.label ? (
                          <Tooltip title={selectedProject.production_profile.description}>
                            <Tag color="cyan">方案：{selectedProject.production_profile.label}</Tag>
                          </Tooltip>
                        ) : null}
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
                  productionFamily={selectedProject.production_profile?.production_family || 'narrative'}
                  packageType={selectedProject.production_profile?.package_type}
                  packageData={contentPackageData}
                  onContinue={() => {
                    if (isContentPackageProject) {
                      openContentPackageEditor()
                    } else if (chapters.length) openChapterStudio(activeChapterNumber)
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
              ) : null}

              {workspaceMode === 'overview' && !isContentPackageProject ? <Collapse
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

              {!isContentPackageProject ? <div className={`story-workspace-detail story-workspace-detail--${workspaceMode}`}>
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
                activeKey={workspaceMode === 'chapter' && !['episode-workbench', 'writer-room', 'script'].includes(activeWorkspaceTab) ? 'episode-workbench' : activeWorkspaceTab}
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
                        productionProfileId={selectedProject?.production_profile?.id}
                        loading={loadingAction === 'outline'}
                        saving={loadingAction === 'outline_save'}
                        syncLoading={loadingAction === 'sync_characters'}
                        extractLoading={characterExtractionLoading}
                        llmAvailable={llmAvailable}
                        templateOptions={templateOptionsByStage.outline || []}
                        selectedTemplateId={selectedPromptTemplates.outline}
                        onTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, outline: value }))
                        }
                        onGenerate={handleGenerateOutline}
                        onSave={handleSaveOutline}
                        onSyncCharacters={handleSyncCharacters}
                        onExtractCharacters={() => void handleExtractCharacters(false)}
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
                        projectId={selectedProject?.id || ''}
                        hasOutline={hasOutline}
                        bibleContents={projectBibleContents}
                        worldAssets={worldAssetContents}
                        loading={loadingAction === 'project_bible' || loadingAction === 'world_extract'}
                        savingContentId={savingContentId}
                        onSync={handleSyncProjectBible}
                        onExtractWorld={handleExtractWorld}
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
              </div> : null}
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
        className="creative-project-create-modal"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        afterOpenChange={(open) => {
          if (open) {
            const current = form.getFieldsValue()
            if (!current.idea && !current.title) {
              form.setFieldsValue({ source_type: 'original_idea', project_type: 'short_drama', production_profile: 'vertical_drama' })
            }
            loadNovelAssets()
          }
        }}
        onOk={() => form.submit()}
        confirmLoading={loadingAction === 'create'}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ source_type: 'original_idea', project_type: 'short_drama', production_profile: 'vertical_drama' }}
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
          <Form.Item label="内容生产方案" name="production_profile">
            <Select
              classNames={{ popup: { root: 'creative-project-profile-dropdown' } }}
              options={productionProfileOptions.map((item) => ({
                value: item.value,
                label: item.label,
                title: item.description,
              }))}
              optionRender={(option) => (
                <div>
                  <div>{option.data.label}</div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{option.data.title}</Text>
                </div>
              )}
              onChange={(value) => {
                const profile = productionProfileOptions.find((item) => item.value === value)
                if (profile) {
                  form.setFieldsValue({
                    project_type: profile.projectType,
                    source_type: profile.family === 'content_package' ? 'original_idea' : form.getFieldValue('source_type'),
                  })
                }
              }}
            />
          </Form.Item>
          <Form.Item label="项目类型" name="project_type" hidden>
            <Select options={projectTypeOptions} />
          </Form.Item>
          {createSourceType === 'novel' && !createIsContentPackage ? (
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
          ) : createIsContentPackage ? (
            <>
              <Form.Item
                label="主题"
                name="idea"
                rules={[{ required: true, message: '请输入主题' }]}
                extra="创建后会直接生成或编辑页面、知识卡和图片提示词，不需要先填写大纲、圣经或正文。"
              >
                <TextArea rows={4} placeholder="例如：给儿童介绍十二生肖；或：一个在雨夜寻找丢失玩偶的恐怖漫画" />
              </Form.Item>
              <Form.Item label="补充说明（可选）" name="creation_brief">
                <TextArea rows={2} placeholder="例如：水彩绘本风、共 12 页、适合 6-8 岁儿童；也可以创建后再补充" />
              </Form.Item>
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
        destroyOnHidden
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

      <Modal
        title="角色提取预览"
        open={characterExtractionOpen}
        onCancel={() => setCharacterExtractionOpen(false)}
        width={900}
        footer={characterExtractionResult?.applied ? null : [
          <Button key="cancel" onClick={() => setCharacterExtractionOpen(false)}>取消</Button>,
          <Button key="apply" type="primary" loading={characterExtractionLoading} onClick={() => void handleExtractCharacters(true)}>
            确认写入角色库
          </Button>,
        ]}
        destroyOnHidden
      >
        {characterExtractionResult ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message={`已扫描 ${characterExtractionResult.chunks || 0} 个文本块，识别 ${characterExtractionResult.characters?.length || 0} 个角色`}
              description="第一轮负责角色归并和证据，第二轮生成角色设定。确认写入后会同步项目大纲、角色库和项目关联。"
            />
            {(characterExtractionResult.merge_candidates || []).length ? (
              <Alert
                type="warning"
                showIcon
                message="有需要人工确认的同名/包含名候选"
                description={characterExtractionResult.merge_candidates.map((item: any) => `${item.left} / ${item.right}`).join('；')}
              />
            ) : null}
            <List
              size="small"
              bordered
              dataSource={characterExtractionResult.characters || []}
              renderItem={(item: any) => (
                <List.Item>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Space wrap>
                      <Text strong>{item.name}</Text>
                      {(item.aliases || []).map((alias: string) => <Tag key={alias}>{alias}</Tag>)}
                      <Tag color="blue">证据 {item.evidence?.length || 0}</Tag>
                    </Space>
                    <Text type="secondary">{item.oneLiner || item.personality || item.extraction_notes || '暂无摘要'}</Text>
                    {item.evidence?.length ? <Text code>{item.evidence[0]}</Text> : null}
                  </Space>
                </List.Item>
              )}
            />
          </Space>
        ) : <Skeleton active />}
      </Modal>

      <Modal
        title={selectedProject?.production_profile?.package_type === 'knowledge_cards' ? '编辑科普内容包' : '编辑绘本 / 漫画内容包'}
        open={contentPackageOpen}
        onCancel={() => setContentPackageOpen(false)}
        onOk={() => contentPackageForm.submit()}
        confirmLoading={loadingAction === 'create'}
        okText="保存内容包"
        width={860}
        destroyOnHidden
      >
        <Form form={contentPackageForm} layout="vertical" onFinish={handleSaveContentPackage}>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item label="主题" name="topic" rules={[{ required: true, message: '请输入主题' }]}>
            <Input placeholder="例如：给儿童介绍十二生肖" maxLength={500} />
          </Form.Item>
          <Form.Item label="简介 / 导语" name="brief">
            <TextArea rows={3} placeholder="可选，保存后会显示在概览中" maxLength={2000} />
          </Form.Item>
          <Space wrap style={{ marginBottom: 12 }}>
            <Form.Item label="生成数量" name="item_count" initialValue={12} style={{ marginBottom: 0 }}>
              <InputNumber min={1} max={80} />
            </Form.Item>
            <Form.Item name="prompt_only" valuePropName="checked" initialValue={false} style={{ marginBottom: 0, paddingTop: 30 }}>
              <Checkbox>只生成图片提示词</Checkbox>
            </Form.Item>
            <Button icon={<RobotOutlined />} onClick={() => void handlePlanContentPackage()} loading={loadingAction === 'create'} style={{ marginTop: 30 }}>
              AI 一次生成
            </Button>
            <Button icon={<PictureOutlined />} onClick={() => void handleBatchGenerateContentPackageImages()} loading={contentPackageBatchRunning} style={{ marginTop: 30 }}>
              批量生成图片
            </Button>
          </Space>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>页面 / 内容卡</Text>
                  <Button size="small" icon={<PlusOutlined />} onClick={() => add({ title: '', text: '', fact: '', source: '', source_url: '', image_prompt: '' })}>添加内容单元</Button>
                </Space>
                {fields.map((field, index) => (
                  <div key={field.key} style={{ border: `1px solid ${theme.borderLight}`, borderRadius: 6, padding: 12, background: theme.bgElevated }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
                      <Text strong>第 {index + 1} 项</Text>
                      <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => remove(field.name)} disabled={fields.length === 1} />
                    </Space>
                    <Form.Item label="标题" name={[field.name, 'title']} style={{ marginBottom: 8 }}><Input placeholder="例如：鼠" /></Form.Item>
                    <Form.Item label="文字内容" name={[field.name, 'text']} style={{ marginBottom: 8 }}><TextArea rows={2} placeholder="页面文字或知识卡说明，可留空只生成提示词" /></Form.Item>
                    {selectedProject?.production_profile?.package_type === 'knowledge_cards' ? (
                      <>
                        <Form.Item label="知识事实" name={[field.name, 'fact']} style={{ marginBottom: 8 }}><TextArea rows={2} placeholder="可核验的事实表述，避免把推测写成结论" /></Form.Item>
                        <Form.Item label="来源说明" name={[field.name, 'source']} style={{ marginBottom: 8 }}><Input placeholder="例如：中国国家博物馆、百科资料" /></Form.Item>
                        <Form.Item label="来源链接" name={[field.name, 'source_url']} style={{ marginBottom: 8 }}><Input placeholder="可选，填写公开网页链接" /></Form.Item>
                      </>
                    ) : null}
                    <Form.Item label="图片提示词" name={[field.name, 'image_prompt']} style={{ marginBottom: 8 }}>
                      <TextArea rows={2} placeholder="可直接用于 AI 生图" />
                    </Form.Item>
                    <Button
                      size="small"
                      icon={<PictureOutlined />}
                      loading={inlineImageLoadingKey === imageContextKey({
                        contentId: contentPackageContent?.id,
                        sourceType: 'content_package',
                        sourceIndex: index,
                      })}
                      onClick={() => void handleGenerateContentPackageImage(index, field.name)}
                    >
                      生成图片
                    </Button>
                  </div>
                ))}
              </Space>
            )}
          </Form.List>
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
