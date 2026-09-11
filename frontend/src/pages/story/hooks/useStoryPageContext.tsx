/**
 * 创作项目工作台的上下文：状态、副作用、派生值与全部动作。
 *
 * 从 story/index.tsx 的主组件整体抽出（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；返回值即视图所需的全部数据与回调，类型由对象字面量自动推断。
 */
import { listTasks } from '../../../api'
import { useTheme } from '../../../constants/theme'
import { ChapterPlanItem, StoryOutlineCharacter } from '../../../types/api'
import { useChapterContentActions } from './useChapterContentActions'
import { useGraphNarrativeActions } from './useGraphNarrativeActions'
import { useInlineImageGeneration } from './useInlineImageGeneration'
import { usePortraitStoryboardActions } from './usePortraitStoryboardActions'
import { useProjectContentActions } from './useProjectContentActions'
import { useWorkbenchPreferenceActions } from './useWorkbenchPreferenceActions'
import { useWorkspaceData } from './useWorkspaceData'
import { useWriterRoomActions } from './useWriterRoomActions'
import { AssetSummary, ChapterAction, ImagePromptContext, InlineGeneratedImage, LoadingAction, PipelineResult, PipelineRunStatus, PipelineStageValue, ProjectContent } from '../types'
import { buildCreativeProjectGraph, collectStoryboardCharacterIds, getNovelChapterOptions, imageContextKey, isProjectContentNewer, productionProfileOptions, resolveProjectAssetDetail, unavailableProjectAssetIds } from '../utils'
import { BranchesOutlined, FileTextOutlined, PictureOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Form, Space, Tag, Tooltip, Typography, message } from 'antd'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

const { Text, Title, Paragraph } = Typography

export function useStoryPageContext() {
  const { theme } = useTheme()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

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

  const {
    projects,
    setProjects,
    selectedId,
    setSelectedId,
    selectedProject,
    setSelectedProject,
    contents,
    setContents,
    writerRoomContents,
    setWriterRoomContents,
    writerRoomSummary,
    setWriterRoomSummary,
    projectAssets,
    setProjectAssets,
    assetDetails,
    setAssetDetails,
    unavailableAssetIds,
    setUnavailableAssetIds,
    projectGraph,
    setProjectGraph,
    characterDetails,
    setCharacterDetails,
    generationLogs,
    setGenerationLogs,
    continuityCandidates,
    setContinuityCandidates,
    continuitySummary,
    setContinuitySummary,
    narrativeContext,
    setNarrativeContext,
    foreshadowingLedger,
    setForeshadowingLedger,
    allForeshadowingLedger,
    setAllForeshadowingLedger,
    narrativeGraphData,
    setNarrativeGraphData,
    narrativeHealth,
    setNarrativeHealth,
    narrativeRuns,
    setNarrativeRuns,
    narrativeLoading,
    setNarrativeLoading,
    llmConnectors,
    setLlmConnectors,
    imageBackends,
    setImageBackends,
    novelAssets,
    setNovelAssets,
    loadingNovelAssets,
    setLoadingNovelAssets,
    promptTemplates,
    setPromptTemplates,
    selectedPromptTemplates,
    setSelectedPromptTemplates,
    selectedLlm,
    setSelectedLlm,
    selectedModel,
    setSelectedModel,
    workspaceLoading,
    setWorkspaceLoading,
    workspaceErrors,
    setWorkspaceErrors,
    projectListError,
    setProjectListError,
    loadProjects,
    loadLlmConnectors,
    loadImageBackends,
    persistChatModel,
    loadPromptTemplates,
    loadContents,
    loadWriterRoomContents,
    loadProjectAssets,
    loadGenerationLogs,
    loadContinuityFacts,
    ensureWritingPreflight,
    loadNarrativeRuntime,
    loadProjectGraph,
    loadNovelAssets,
    loadCharacterDetailsForIds,
    refreshSelected,
    writerRoomRequestRef,
  } = useWorkspaceData({ setLoadingAction })

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
  const [batchStoryboardImageChapter, setBatchStoryboardImageChapter] = useState<number | null>(null)
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

  // 内联生图（含任务轮询、引用图选择）抽到 hooks/useInlineImageGeneration.ts
  const {
    handleInlineGenerateImage,
    inlineImages,
    setInlineImages,
    inlineImageLoadingKey,
    setInlineImageLoadingKey,
    pendingInlineImageTask,
    setPendingInlineImageTask,
  } = useInlineImageGeneration({
    selectedProject,
    activeChapterNumber,
    defaultImageModel,
    defaultImageSupportsReferenceImages,
    characterDetails,
    projectAssets,
    loadProjectAssets,
    loadCharacterDetailsForIds,
  })
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

  // handleCreate 等 抽到 hooks/useProjectContentActions.ts
  const {
    handleCreate,
    handleRename,
    handleDeleteProject,
    handleLinkAsset,
    handleSaveContent,
    handleSaveContentPackage,
    handlePlanContentPackage,
    handleGenerateContentPackageImage,
    handleBatchGenerateContentPackageImages,
    handleExtractCharacters,
    handleSyncCharacters,
    handleSyncProjectBible,
    handleExtractWorld,
    openRenameModal,
    openContentPackageEditor,
  } = useProjectContentActions({
    characterExtractionResult,
    contentPackageContent,
    contentPackageData,
    contentPackageForm,
    form,
    handleInlineGenerateImage,
    idea,
    isContentPackageProject,
    loadContents,
    loadProjectAssets,
    loadProjects,
    refreshSelected,
    renameForm,
    searchParams,
    selectedLlm,
    selectedModel,
    selectedNovelAsset,
    selectedProject,
    setCharacterExtractionLoading,
    setCharacterExtractionOpen,
    setCharacterExtractionResult,
    setContentPackageBatchRunning,
    setContentPackageOpen,
    setContents,
    setCreateOpen,
    setGenerationLogs,
    setLoadingAction,
    setPendingContentPackageProjectId,
    setProjectAssets,
    setProjects,
    setRenameOpen,
    setSavingContentId,
    setSelectedId,
    setSelectedProject,
    setWriterRoomContents,
  })

  // handleGenerateCharacterPortrait 等 抽到 hooks/usePortraitStoryboardActions.ts
  const {
    handleGenerateCharacterPortrait,
    buildProjectCharacterPortraitPrompt,
    handleBatchGenerateStoryboardImages,
    handleUpdateStoryboardPanelReferences,
    handleMatchReferenceAssets,
  } = usePortraitStoryboardActions({
    activeChapterNumber,
    characterDetails,
    contentForChapter,
    contents,
    defaultImageModel,
    defaultImageSupportsReferenceImages,
    handleInlineGenerateImage,
    handleSaveContent,
    inlineImages,
    loadCharacterDetailsForIds,
    loadContents,
    loadGenerationLogs,
    loadProjectAssets,
    outline,
    projectAssets,
    refreshSelected,
    selectedLlm,
    selectedModel,
    selectedProject,
    setBatchStoryboardImageChapter,
    setLoadingAction,
    setLoadingChapterAction,
    setPortraitGeneratingCharacter,
  })

  // handleActiveChapterChange 等 抽到 hooks/useWorkbenchPreferenceActions.ts
  const {
    handleActiveChapterChange,
    handleCreativeSkillIdsChange,
    handleDefaultImageModelChange,
    handleRunPipeline,
    handleAgentAdvanceProject,
    handleOpenVideoGeneration,
    handleOpenPrevis,
  } = useWorkbenchPreferenceActions({
    activeChapterNumber,
    activeChapterRestoreRef,
    activeProjectMeta,
    chapterCount,
    chapters,
    comicPageCount,
    comicStyle,
    defaultImageModel,
    imageBackends,
    loadContents,
    loadGenerationLogs,
    loadProjectAssets,
    navigate,
    outline,
    pipelineChapters,
    pipelineContinueOnError,
    pipelineResult,
    pipelineSkipExisting,
    pipelineStages,
    refreshSelected,
    selectedLlm,
    selectedModel,
    selectedProject,
    setActiveChapterNumber,
    setLoadingAction,
    setPipelineResult,
    setPipelineRunStatus,
    setProjects,
    setSavingImageModel,
    setSelectedProject,
  })

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




  // 持久化：项目顶部"文本模型 / 模型"选择会写入项目 metadata，
  // 刷新页面后能恢复（与默认生图模型一致的处理方式）。
















  useEffect(() => {
    if (!pendingContentPackageProjectId || selectedProject?.id !== pendingContentPackageProjectId) return
    setPendingContentPackageProjectId('')
    openContentPackageEditor()
  }, [pendingContentPackageProjectId, selectedProject?.id])

  // 打开重命名弹窗，并把当前项目名预填到表单

  // 提交重命名：调用 PATCH 接口更新项目名，并刷新当前项目


  // 数据层（项目/内容/素材/日志/连续性/叙事等 32 个状态与 16 个加载函数）
  // 抽到 hooks/useWorkspaceData.ts













































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

  // handleGenerateOutline 等 抽到 hooks/useChapterContentActions.ts
  const {
    handleGenerateOutline,
    handleSaveOutline,
    handleSaveChapterPlan,
    handleGenerateChapterPlan,
    handleGenerateChapterOutline,
    handleRegenerateChapterOutlineScenes,
    handleGenerateNovelBody,
    handleRefineNovelBody,
    handleGenerateScript,
    handleGenerateStoryboard,
    handleGenerateStoryboardForChapter,
    handleSplitComicPages,
  } = useChapterContentActions({
    chapterCount,
    comicPageCount,
    comicStyle,
    contentForChapter,
    contents,
    ensureWritingPreflight,
    idea,
    loadContents,
    loadGenerationLogs,
    outline,
    refreshSelected,
    selectedLlm,
    selectedModel,
    selectedProject,
    selectedPromptTemplates,
    setLoadingAction,
    setLoadingChapterAction,
    setProjects,
    setSelectedProject,
  })

  // handleRunWriterRoomStep 等 抽到 hooks/useWriterRoomActions.ts
  const {
    handleRunWriterRoomStep,
    handleRunWriterRoomBatch,
    handleRewriteParagraph,
    handlePromoteWriterRoomContent,
  } = useWriterRoomActions({
    activeChapterNumber,
    loadContents,
    loadGenerationLogs,
    loadWriterRoomContents,
    refreshSelected,
    rehearsalMode,
    selectedLlm,
    selectedModel,
    selectedProject,
    selectedPromptTemplates,
    setLoadingAction,
    setWriterRoomContents,
  })

  // handleRegenerateGraphNode 等 抽到 hooks/useGraphNarrativeActions.ts
  const {
    handleRegenerateGraphNode,
    handleToggleGraphNodeLock,
    handleSendGraphNodeToCanvas,
    handleOpenGraphNode,
    handleExtractContinuity,
    handleResolveContinuityCandidate,
    handleSaveContentAsAsset,
    handleNarrativeRunControl,
    handleNarrativeAutopilot,
    handleForeshadowingDecision,
    handleSaveProjectGraph,
  } = useGraphNarrativeActions({
    activeChapterNumber,
    chapterPlan,
    chapters,
    handleGenerateChapterOutline,
    handleGenerateChapterPlan,
    handleGenerateNovelBody,
    handleGenerateOutline,
    handleGenerateScript,
    handleGenerateStoryboardForChapter,
    handleSaveChapterPlan,
    handleSaveContent,
    handleSplitComicPages,
    loadContents,
    loadContinuityFacts,
    loadNarrativeRuntime,
    loadProjectAssets,
    navigate,
    openChapterStudio,
    openWorkspaceTab,
    outline,
    selectedProject,
    setLoadingAction,
    setProjectGraph,
  })


  return {
    activeChapter,
    activeChapterNumber,
    activeWorkspaceTab,
    allForeshadowingLedger,
    assetDetails,
    batchStoryboardImageChapter,
    chapterColumns,
    chapterCount,
    chapterPlan,
    chapters,
    characterColumns,
    characterDetails,
    characterExtractionLoading,
    characterExtractionOpen,
    characterExtractionResult,
    cockpitCompact,
    comicPageCount,
    comicPages,
    comicStyle,
    contentForChapter,
    contentPackageBatchRunning,
    contentPackageContent,
    contentPackageData,
    contentPackageForm,
    contentPackageOpen,
    contents,
    continuityCandidates,
    continuitySummary,
    createIsContentPackage,
    createOpen,
    createSourceType,
    defaultImageModel,
    defaultImageSupportsReferenceImages,
    fanqieOpen,
    foreshadowingLedger,
    form,
    generationLogs,
    handleActiveChapterChange,
    handleAgentAdvanceProject,
    handleBatchGenerateContentPackageImages,
    handleBatchGenerateStoryboardImages,
    handleCreate,
    handleCreativeSkillIdsChange,
    handleDefaultImageModelChange,
    handleDeleteProject,
    handleExtractCharacters,
    handleExtractContinuity,
    handleExtractWorld,
    handleForeshadowingDecision,
    handleGenerateChapterOutline,
    handleGenerateChapterPlan,
    handleGenerateContentPackageImage,
    handleGenerateNovelBody,
    handleGenerateOutline,
    handleGenerateScript,
    handleGenerateStoryboardForChapter,
    handleInlineGenerateImage,
    handleLinkAsset,
    handleMatchReferenceAssets,
    handleNarrativeAutopilot,
    handleNarrativeRunControl,
    handleOpenGraphNode,
    handleOpenPrevis,
    handleOpenVideoGeneration,
    handlePlanContentPackage,
    handlePromoteWriterRoomContent,
    handleRefineNovelBody,
    handleRegenerateChapterOutlineScenes,
    handleRegenerateGraphNode,
    handleRename,
    handleResolveContinuityCandidate,
    handleRewriteParagraph,
    handleRunPipeline,
    handleRunWriterRoomBatch,
    handleRunWriterRoomStep,
    handleSaveChapterPlan,
    handleSaveContent,
    handleSaveContentAsAsset,
    handleSaveContentPackage,
    handleSaveOutline,
    handleSaveProjectGraph,
    handleSendGraphNodeToCanvas,
    handleSplitComicPages,
    handleSyncCharacters,
    handleSyncProjectBible,
    handleToggleGraphNodeLock,
    handleUpdateStoryboardPanelReferences,
    hasChapterPlan,
    hasOutline,
    idea,
    imageModelOptions,
    inlineImageLoadingKey,
    inlineImages,
    inspectorOpen,
    isChapterActionLoading,
    isContentPackageProject,
    llmAvailable,
    llmConnectors,
    loadGenerationLogs,
    loadNarrativeRuntime,
    loadNovelAssets,
    loadProjects,
    loadWriterRoomContents,
    loadingAction,
    loadingChapterAction,
    loadingNovelAssets,
    modelOptions,
    narrativeContext,
    narrativeGraphData,
    narrativeHealth,
    narrativeInspectorLogs,
    narrativeLoading,
    narrativeRuns,
    navigate,
    novelAssets,
    novelBodies,
    openChapterStudio,
    openContentPackageEditor,
    openRenameModal,
    openWorkspaceTab,
    outline,
    overviewDetailLabel,
    overviewDetailOpen,
    pendingInlineImageTask,
    persistChatModel,
    pipelineChapters,
    pipelineContinueOnError,
    pipelineOpen,
    pipelineResult,
    pipelineRunStatus,
    pipelineSkipExisting,
    pipelineStages,
    productionStages,
    projectAssets,
    projectBibleContents,
    projectGraphView,
    projectLibraryCollapsed,
    projectLibraryWidth,
    projectListError,
    projects,
    rehearsalMode,
    renameForm,
    renameOpen,
    retryWorkspaceLoads,
    runtimeSettingsOpen,
    savingContentId,
    savingImageModel,
    selectedCreativeSkillIds,
    selectedId,
    selectedLlm,
    selectedModel,
    selectedNovelAsset,
    selectedNovelChapterOptions,
    selectedProject,
    selectedProjectIndex,
    selectedPromptTemplates,
    setActiveWorkspaceTab,
    setChapterCount,
    setCharacterExtractionOpen,
    setComicPageCount,
    setComicStyle,
    setContentPackageOpen,
    setCreateOpen,
    setFanqieOpen,
    setInspectorOpen,
    setOverviewDetailOpen,
    setPipelineChapters,
    setPipelineContinueOnError,
    setPipelineOpen,
    setPipelineSkipExisting,
    setPipelineStages,
    setProjectLibraryCollapsed,
    setProjectLibraryWidth,
    setRehearsalMode,
    setRenameOpen,
    setRuntimeSettingsOpen,
    setSelectedId,
    setSelectedLlm,
    setSelectedModel,
    setSelectedPromptTemplates,
    setWorkbenchWidths,
    setWorkspaceMode,
    startHorizontalResize,
    storyPageRef,
    templateOptionsByStage,
    theme,
    unavailableAssetIds,
    workbenchWidths,
    workspaceErrorEntries,
    workspaceErrors,
    workspaceLoading,
    workspaceMode,
    workspaceNarrow,
    worldAssetContents,
    writerRoomContents,
    writerRoomSummary,
  }
}

export type StoryPageContext = ReturnType<typeof useStoryPageContext>
