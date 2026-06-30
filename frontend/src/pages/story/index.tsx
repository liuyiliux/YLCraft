import React, { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Button,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  List,
  Modal,
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
  FileTextOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  createCreativeProject,
  generateCreativeProjectChapterPlan,
  generateCreativeProjectChapterOutline,
  generateCreativeProjectNovelBody,
  generateCreativeProjectOutline,
  generateCreativeProjectScript,
  generateCreativeProjectStoryboard,
  generateImage as generateImageApi,
  getPlatformTemplates,
  getImageBackends,
  linkCreativeProjectAsset,
  listConnectors,
  listCreativeProjectContents,
  listCreativeProjectAssets,
  listCreativeProjectGenerationLogs,
  listCreativeProjects,
  refineCreativeProjectNovelBody,
  regenerateCreativeProjectChapterOutlineScenes,
  splitCreativeProjectComicPages,
  syncCreativeProjectCharacters,
  updateCreativeProject,
  updateCreativeProjectContent,
  type PlatformTemplate,
} from '../../api'
import type {
  ChapterPlanItem,
  CreativeProject,
  CreativeProjectGenerateResponse,
  CreativeProjectListResponse,
  CreativeProjectResponse,
  Provider,
  StoryOutlineCharacter,
} from '../../types/api'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

type LoadingAction =
  | 'projects'
  | 'create'
  | 'outline'
  | 'chapter_plan'
  | 'chapter_outline'
  | 'chapter_outline_scenes'
  | 'novel_body'
  | 'novel_body_refine'
  | 'comic_pages'
  | 'script'
  | 'storyboard'
  | 'asset'
  | 'sync_characters'
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
  version: number
  created_at?: string
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
}

type InlineGeneratedImage = {
  assetId?: string
  url?: string
  localPath?: string
  prompt: string
  provider?: string
  model?: string
  createdAt: string
}

function imageContextKey(context: ImagePromptContext = {}) {
  return [
    context.contentId || 'project',
    context.sourceType || 'prompt',
    context.sourceIndex ?? '0',
    context.chapterNumber ?? '0',
  ].join(':')
}

function assetFileUrl(path?: string): string {
  if (!path) return ''
  if (/^(https?:|data:|blob:|\/api\/)/i.test(path)) return path
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}`
}

type ImageBackendOption = {
  provider: string
  provider_label: string
  name: string
  model: string
  available_models?: string[]
  supported_sizes?: string[]
}

export default function StoryPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<CreativeProject[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [selectedProject, setSelectedProject] = useState<CreativeProject | null>(null)
  const [contents, setContents] = useState<ProjectContent[]>([])
  const [projectAssets, setProjectAssets] = useState<ProjectAssetLink[]>([])
  const [generationLogs, setGenerationLogs] = useState<ProjectGenerationLog[]>([])
  const [llmConnectors, setLlmConnectors] = useState<Provider[]>([])
  const [imageBackends, setImageBackends] = useState<ImageBackendOption[]>([])
  const [promptTemplates, setPromptTemplates] = useState<PlatformTemplate[]>([])
  const [selectedPromptTemplates, setSelectedPromptTemplates] = useState<Record<string, string>>({})
  const [selectedLlm, setSelectedLlm] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [createOpen, setCreateOpen] = useState(false)
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null)
  const [savingContentId, setSavingContentId] = useState<string | null>(null)
  const [loadingChapterAction, setLoadingChapterAction] = useState<{ action: ChapterAction; chapterNumber: number | null }>({
    action: null,
    chapterNumber: null,
  })
  const [chapterCount, setChapterCount] = useState(12)
  const [comicPageCount, setComicPageCount] = useState(10)
  const [comicStyle, setComicStyle] = useState('彩色影视漫画，竖屏短剧分镜感，半写实人物，高对比光影，画风统一')
  const [activeChapterNumber, setActiveChapterNumber] = useState(1)
  const [projectLibraryWidth, setProjectLibraryWidth] = useState(260)
  const [workbenchWidths, setWorkbenchWidths] = useState({ outline: 360, prose: 520 })
  const [savingImageModel, setSavingImageModel] = useState(false)
  const [inlineImageLoadingKey, setInlineImageLoadingKey] = useState<string | null>(null)
  const [inlineImages, setInlineImages] = useState<Record<string, InlineGeneratedImage>>({})
  const [form] = Form.useForm()

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

  const activeProjectMeta = selectedProject?.metadata || {}
  const idea = String(activeProjectMeta.idea || '')
  const defaultImageModel = activeProjectMeta.default_image_model || {}

  const handleInlineGenerateImage = async (prompt: string, context: ImagePromptContext = {}) => {
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
      })

      if (!data?.success) {
        message.error(data?.error || '图片生成失败')
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
          prompt: trimmedPrompt,
          provider: data.provider || defaultImageModel.name,
          model: data.model || defaultImageModel.model || '',
          createdAt: new Date().toISOString(),
        },
      }))
      await loadProjectAssets(selectedProject.id)
      message.success(assetId ? '图片已生成并关联到项目素材' : '图片已生成')
    } catch (error: any) {
      message.error(error?.message || '图片生成失败')
    } finally {
      setInlineImageLoadingKey(null)
    }
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
    if (found) {
      loadContents(found.id)
      loadProjectAssets(found.id)
      loadGenerationLogs(found.id)
    } else {
      setContents([])
      setProjectAssets([])
      setGenerationLogs([])
    }
  }, [selectedId, projects])

  useEffect(() => {
    if (!chapters.length) return
    const exists = chapters.some((item: ChapterPlanItem) => item.chapter_number === activeChapterNumber)
    if (!exists) {
      setActiveChapterNumber(chapters[0].chapter_number)
    }
  }, [chapters, activeChapterNumber])

  const selectedProjectIndex = useMemo(
    () => projects.findIndex((item) => item.id === selectedId),
    [projects, selectedId],
  )

  const activeLlm = useMemo(
    () => llmConnectors.find((item) => item.name === selectedLlm) || null,
    [llmConnectors, selectedLlm],
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
      const currentVersion = current?.version || 0
      const nextVersion = item.version || 0
      if (!current || nextVersion > currentVersion) {
        grouped[item.content_type][chapterNumber] = item
      }
    })
    return grouped
  }, [contents])

  const contentForChapter = (contentType: string, chapterNumber: number) =>
    contentByChapter[contentType]?.[chapterNumber]

  const activeChapter = useMemo(
    () => chapters.find((item: ChapterPlanItem) => item.chapter_number === activeChapterNumber) || null,
    [chapters, activeChapterNumber],
  )

  const isChapterActionLoading = (action: ChapterAction, chapterNumber: number) =>
    loadingChapterAction.action === action && loadingChapterAction.chapterNumber === chapterNumber

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
      const targetId = nextSelectedId || selectedId || data[0]?.id || ''
      setSelectedId(targetId)
    } catch (error: any) {
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
        ;['outline', 'chapter_plan', 'chapter_outline', 'novel_body', 'comic_pages', 'script', 'storyboard'].forEach((stage) => {
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
    try {
      const response = await listCreativeProjectContents(projectId)
      setContents(response?.data || [])
    } catch {
      setContents([])
    }
  }

  async function loadProjectAssets(projectId: string) {
    try {
      const response = await listCreativeProjectAssets(projectId)
      setProjectAssets(response?.data || [])
    } catch {
      setProjectAssets([])
    }
  }

  async function loadGenerationLogs(projectId: string) {
    try {
      const response = await listCreativeProjectGenerationLogs(projectId, { limit: 80 })
      setGenerationLogs(response?.data || [])
    } catch {
      setGenerationLogs([])
    }
  }

  async function handleCreate(values: any) {
    setLoadingAction('create')
    try {
      const response = (await createCreativeProject({
        title: values.title,
        idea: values.idea,
        project_type: values.project_type,
        source_type: 'original_idea',
      })) as CreativeProjectResponse
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

  async function handleLinkAsset(assetId: string, role: string) {
    if (!selectedProject || !assetId.trim()) return
    setLoadingAction('asset')
    try {
      await linkCreativeProjectAsset(selectedProject.id, {
        asset_id: assetId.trim(),
        role,
        relation: role === 'output' ? 'derived_from' : 'references',
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

  async function handleGenerateChapterPlan() {
    if (!selectedProject) return
    setLoadingAction('chapter_plan')
    try {
      const response = (await generateCreativeProjectChapterPlan(selectedProject.id, {
        chapter_count: chapterCount,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_plan || undefined,
      })) as CreativeProjectGenerateResponse
      message.success('章节规划已生成')
      await refreshSelected(response.project || null)
    } catch (error: any) {
      message.error(error?.message || '章节规划生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }

  async function handleGenerateChapterOutline(chapterNumber: number) {
    if (!selectedProject) return
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

  const chapterColumns = [
    {
      title: '章',
      dataIndex: 'chapter_number',
      width: 64,
    },
    {
      title: '标题',
      dataIndex: 'title',
      width: 180,
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
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24, maxWidth: 1760, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 20 }}>
        <div>
          <Title level={2} style={{ marginBottom: 4 }}>
            创作项目
          </Title>
          <Text type="secondary">小说、短剧、漫画的结构化创作工作台</Text>
        </div>
        <Space>
          <Select
            placeholder="文本模型"
            value={selectedLlm || undefined}
            style={{ width: 220 }}
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
            style={{ width: 260 }}
            options={modelOptions}
            onChange={setSelectedModel}
            disabled={!selectedLlm}
          />
          <Select
            allowClear
            showSearch
            placeholder="默认生图模型"
            value={defaultImageModel.name || undefined}
            style={{ width: 280 }}
            options={imageModelOptions}
            loading={savingImageModel}
            onChange={handleDefaultImageModelChange}
            optionFilterProp="label"
            disabled={!selectedProject}
          />
          <Button onClick={() => navigate('/platform-templates?scope=creative_project')}>
            模板管理
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => loadProjects(selectedId)}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建项目
          </Button>
        </Space>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `${projectLibraryWidth}px 10px minmax(0, 1fr)`,
          gap: 8,
          alignItems: 'start',
        }}
      >
        <section
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            background: '#fff',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #eef0f3' }}>
            <Space>
              <FolderOpenOutlined />
              <Text strong>项目库</Text>
              <Badge count={projects.length} showZero color="#1677ff" />
            </Space>
          </div>
          {loadingAction === 'projects' && !projects.length ? (
            <div style={{ padding: 16 }}>
              <Skeleton active paragraph={{ rows: 8 }} />
            </div>
          ) : projects.length ? (
            <List
              dataSource={projects}
              rowKey="id"
              renderItem={(item, index) => (
                <List.Item
                  onClick={() => setSelectedId(item.id)}
                  style={{
                    cursor: 'pointer',
                    padding: '12px 16px',
                    background: item.id === selectedId ? '#f0f6ff' : '#fff',
                    borderLeft: item.id === selectedId ? '3px solid #1677ff' : '3px solid transparent',
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
          ) : (
            <div style={{ padding: 24 }}>
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无项目" />
            </div>
          )}
        </section>

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

        <main
          style={{
            minHeight: 620,
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            background: '#fff',
          }}
        >
          {!selectedProject ? (
            <div style={{ padding: 64 }}>
              <Empty description="选择或新建项目" />
            </div>
          ) : (
            <>
              <div style={{ padding: 20, borderBottom: '1px solid #eef0f3' }}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <div>
                      <Space size={10} wrap>
                        <Title level={3} style={{ margin: 0 }}>
                          {selectedProject.title}
                        </Title>
                        <Tag color="processing">{projectTypeLabel(selectedProject.project_type)}</Tag>
                        <Tag>{stageLabels[selectedProject.current_stage] || selectedProject.current_stage}</Tag>
                      </Space>
                      {idea && (
                        <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: '8px 0 0' }}>
                          {idea}
                        </Paragraph>
                      )}
                    </div>
                    <Text type="secondary">
                      {selectedProjectIndex >= 0 ? `#${projects.length - selectedProjectIndex}` : ''}
                    </Text>
                  </Space>
                </Space>
              </div>

              <Tabs
                style={{ padding: '0 20px 20px' }}
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
                        syncLoading={loadingAction === 'sync_characters'}
                        templateOptions={templateOptionsByStage.outline || []}
                        selectedTemplateId={selectedPromptTemplates.outline}
                        onTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, outline: value }))
                        }
                        onGenerate={handleGenerateOutline}
                        onSyncCharacters={handleSyncCharacters}
                        characterColumns={characterColumns}
                      />
                    ),
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
                        onGenerate={handleGenerateChapterPlan}
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
                        chapters={chapters}
                        activeChapterNumber={activeChapterNumber}
                        onActiveChapterChange={setActiveChapterNumber}
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
                        savingContentId={savingContentId}
                        linkingAsset={loadingAction === 'asset'}
                        onGenerateChapterOutline={handleGenerateChapterOutline}
                        onRegenerateChapterOutlineScenes={handleRegenerateChapterOutlineScenes}
                        onGenerateNovelBody={handleGenerateNovelBody}
                        onRefineNovelBody={handleRefineNovelBody}
                        onGenerateScript={handleGenerateScript}
                        onGenerateStoryboard={handleGenerateStoryboardForChapter}
                        onSplitComicPages={handleSplitComicPages}
                        onSaveContent={handleSaveContent}
                        onLinkReferenceAsset={handleLinkAsset}
                        onSendImagePrompt={handleInlineGenerateImage}
                        inlineImages={inlineImages}
                        inlineImageLoadingKey={inlineImageLoadingKey}
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
                        onSendImagePrompt={handleInlineGenerateImage}
                        inlineImages={inlineImages}
                        inlineImageLoadingKey={inlineImageLoadingKey}
                      />
                    ),
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
                ]}
              />
            </>
          )}
        </main>
      </div>

      <Modal
        title="新建创作项目"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={loadingAction === 'create'}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ project_type: 'short_drama' }}
          onFinish={handleCreate}
        >
          <Form.Item label="标题" name="title">
            <Input placeholder="可留空，生成大纲后会自动更新" />
          </Form.Item>
          <Form.Item label="项目类型" name="project_type">
            <Select options={projectTypeOptions} />
          </Form.Item>
          <Form.Item
            label="创意"
            name="idea"
            rules={[{ required: true, message: '请输入创意' }]}
          >
            <TextArea rows={5} placeholder="例如：短剧但是不降智" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function OutlineTab({
  outline,
  hasOutline,
  loading,
  syncLoading,
  templateOptions,
  selectedTemplateId,
  onTemplateChange,
  onGenerate,
  onSyncCharacters,
  characterColumns,
}: {
  outline: any
  hasOutline: boolean
  loading: boolean
  syncLoading: boolean
  templateOptions: TemplateOption[]
  selectedTemplateId?: string
  onTemplateChange: (value: string) => void
  onGenerate: () => void
  onSyncCharacters: () => void
  characterColumns: any[]
}) {
  if (!hasOutline) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description="暂无故事大纲" />
        <Space style={{ marginTop: 12 }} wrap>
          <PromptTemplateSelect
            value={selectedTemplateId}
            options={templateOptions}
            placeholder="大纲模板"
            onChange={onTemplateChange}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={loading}
            onClick={onGenerate}
          >
            生成故事大纲
          </Button>
        </Space>
      </div>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>
            {outline.title || '故事大纲'}
          </Title>
          <Text type="secondary">{outline.logline || '未填写一句话卖点'}</Text>
        </div>
        <Space>
          <PromptTemplateSelect
            value={selectedTemplateId}
            options={templateOptions}
            placeholder="大纲模板"
            onChange={onTemplateChange}
          />
          <Button icon={<UserOutlined />} loading={syncLoading} onClick={onSyncCharacters}>
            同步角色库
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={onGenerate}>
            重新生成
          </Button>
        </Space>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <InfoBlock title="核心前提" text={outline.premise} />
        <InfoBlock title="世界观" text={outline.worldview} />
        <InfoBlock title="主线冲突" text={outline.main_conflict} />
        <InfoBlock title="观众情绪" text={outline.audience_emotion} />
        <InfoBlock title="叙事气质" text={outline.tone} />
        <InfoBlock title="视觉风格" text={outline.visual_style} />
        <InfoListBlock title="卖点" items={outline.selling_points || []} />
        <InfoListBlock title="叙事规则" items={outline.narrative_rules || []} />
      </div>

      <div>
        <Title level={5}>角色</Title>
        <Table
          size="small"
          rowKey={(record: StoryOutlineCharacter, index?: number) => record.name || String(index)}
          columns={characterColumns}
          dataSource={outline.characters || []}
          pagination={false}
        />
      </div>

      <div>
        <Title level={5}>故事弧线</Title>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
          <InfoBlock title="开局" text={outline.story_arc?.beginning} compact />
          <InfoBlock title="中段" text={outline.story_arc?.middle} compact />
          <InfoBlock title="高潮" text={outline.story_arc?.climax} compact />
          <InfoBlock title="方向" text={outline.story_arc?.ending_direction} compact />
        </div>
      </div>

      {outline.locations?.length ? (
        <div>
          <Title level={5}>核心场景</Title>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            {outline.locations.map((location: any, index: number) => (
              <InfoBlock
                key={location.name || index}
                title={location.name || `场景 ${index + 1}`}
                text={[location.role, location.visual_description, location.mood, location.reusable_asset_note].filter(Boolean).join('；')}
                compact
              />
            ))}
          </div>
        </div>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <InfoBlock title="统一生图提示" text={outline.image_style_prompt} />
        <InfoListBlock title="制作约束" items={outline.production_notes || []} />
      </div>
    </Space>
  )
}

function ChapterTab({
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
  onGenerate,
}: {
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
  onGenerate: () => void
}) {
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
          onClick={onGenerate}
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
        <Table
          rowKey="chapter_number"
          size="small"
          columns={chapterColumns}
          dataSource={chapters}
          pagination={false}
        />
      )}
    </Space>
  )
}

function EpisodeWorkbenchTab({
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
  savingContentId,
  linkingAsset,
  onGenerateChapterOutline,
  onRegenerateChapterOutlineScenes,
  onGenerateNovelBody,
  onRefineNovelBody,
  onGenerateScript,
  onGenerateStoryboard,
  onSplitComicPages,
  onSaveContent,
  onLinkReferenceAsset,
  onSendImagePrompt,
  inlineImages,
  inlineImageLoadingKey,
}: {
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
  savingContentId: string | null
  linkingAsset: boolean
  onGenerateChapterOutline: (chapterNumber: number) => void
  onRegenerateChapterOutlineScenes: (chapterNumber: number) => void
  onGenerateNovelBody: (chapterNumber: number) => void
  onRefineNovelBody: (chapterNumber: number, instruction: string) => void
  onGenerateScript: (chapterNumber: number) => void
  onGenerateStoryboard: (chapterNumber: number) => void
  onSplitComicPages: (chapterNumber: number) => void
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => void
  onLinkReferenceAsset: (assetId: string, role: string) => void
  onSendImagePrompt: (prompt: string, context?: ImagePromptContext) => void
  inlineImages: Record<string, InlineGeneratedImage>
  inlineImageLoadingKey: string | null
}) {
  const chapterOutline = contentForChapter('chapter_outline', activeChapterNumber)
  const novelBody = contentForChapter('novel_body', activeChapterNumber)
  const script = contentForChapter('script', activeChapterNumber)
  const storyboard = contentForChapter('storyboard', activeChapterNumber)
  const comic = contentForChapter('comic_pages', activeChapterNumber)
  const [outlineDraft, setOutlineDraft] = useState<Record<string, any>>({})
  const [sceneDrafts, setSceneDrafts] = useState<any[]>([])
  const [novelDraft, setNovelDraft] = useState('')
  const [novelRefineInstruction, setNovelRefineInstruction] = useState('')
  const [comicDrafts, setComicDrafts] = useState<any[]>([])

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
    setComicDrafts((comic?.data?.pages || []).map((page: any, index: number) => ({
      page_number: page.page_number || index + 1,
      title: page.title || '',
      content: page.content || '',
      panel_count: page.panel_count || '',
      image_prompt: page.image_prompt || '',
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
    return <InlineImageResult image={inlineImages[key]} loading={inlineImageLoadingKey === key} />
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <div style={workbenchHeaderStyle}>
        <div>
          <Space size={8} wrap>
            <Title level={4} style={{ margin: 0 }}>
              第 {activeChapterNumber} 话
            </Title>
            <Tag color={novelBody ? 'green' : 'default'}>{novelBody ? '已有正文' : '未正文'}</Tag>
            <Tag color={storyboard ? 'blue' : 'default'}>{storyboard ? '已有分镜' : '未分镜'}</Tag>
            <Tag color={comic ? 'purple' : 'default'}>{comic ? '已有漫画' : '未漫画'}</Tag>
          </Space>
          <Text type="secondary">{activeChapter?.title || '未命名章节'}</Text>
        </div>
        <Space size={8} wrap>
          {chapters.map((chapter) => {
            const isActive = chapter.chapter_number === activeChapterNumber
            return (
              <Button
                key={chapter.chapter_number}
                size="small"
                type={isActive ? 'primary' : 'default'}
                onClick={() => onActiveChapterChange(chapter.chapter_number)}
              >
                {chapter.chapter_number}
              </Button>
            )
          })}
        </Space>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `${columnWidths.outline}px 10px ${columnWidths.prose}px 10px minmax(320px, 1fr)`,
          gap: 8,
          alignItems: 'start',
        }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
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
                <div key={`${scene.scene_number}-${index}`} style={compactBlockStyle}>
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

        <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <WorkbenchSection
          title="正文"
          extra={
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

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <ReferenceCardsPanel
          assets={projectAssets}
          loading={linkingAsset}
          onLinkAsset={onLinkReferenceAsset}
        />

        <WorkbenchSection
          title={`脚本${scriptSceneCount ? ` · ${scriptSceneCount}` : ''}`}
          extra={
            <Button
              size="small"
              icon={<FileTextOutlined />}
              loading={isChapterActionLoading('script', activeChapterNumber)}
              onClick={() => onGenerateScript(activeChapterNumber)}
            >
              {script ? '重写脚本' : '由细纲生成脚本'}
            </Button>
          }
        >
          {script ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {script.data?.hook ? (
                <div style={compactBlockStyle}>
                  <Text strong>开头钩子</Text>
                  <Paragraph style={{ margin: '6px 0 0' }}>{script.data.hook}</Paragraph>
                </div>
              ) : null}
              {(script.data?.scenes || []).slice(0, 8).map((scene: any) => (
                <div key={scene.scene_number} style={compactBlockStyle}>
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
                            })
                          }
                        >
                          生图
                        </Button>
                      ) : null}
                    </Space>
                    <Text type="secondary">{[scene.camera_hint, scene.emotion].filter(Boolean).join(' · ')}</Text>
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
                <div style={compactBlockStyle}>
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
            <Tooltip title={canGenerateStoryboard ? '' : '先生成脚本'}>
              <Button
                size="small"
                icon={<PictureOutlined />}
                disabled={!canGenerateStoryboard}
                loading={isChapterActionLoading('storyboard', activeChapterNumber)}
                onClick={() => onGenerateStoryboard(activeChapterNumber)}
              >
                {storyboard ? '重拆分镜' : '由脚本生成分镜'}
              </Button>
            </Tooltip>
          }
        >
          {storyboard ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {(storyboard.data?.panels || []).slice(0, 10).map((panel: any) => (
                <div key={panel.panel_number} style={compactBlockStyle}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <Text strong>分镜 {panel.panel_number}</Text>
                    {panel.image_prompt ? (
                      <Button
                        size="small"
                        onClick={() =>
                          onSendImagePrompt(panel.image_prompt, {
                            contentId: storyboard.id,
                            sourceType: 'storyboard_panel',
                            sourceIndex: panel.panel_number,
                            sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
                            chapterNumber: activeChapterNumber,
                          })
                        }
                      >
                        生图
                      </Button>
                    ) : null}
                  </Space>
                  <Text type="secondary">{panel.action || panel.image_prompt}</Text>
                  {panel.image_prompt ? (
                    <Paragraph
                      type="secondary"
                      ellipsis={{ rows: 3, tooltip: panel.image_prompt }}
                      style={{ margin: '6px 0 0', fontSize: 12 }}
                    >
                      生图提示：{panel.image_prompt}
                    </Paragraph>
                  ) : null}
                  {renderInlineImage({
                    contentId: storyboard.id,
                    sourceType: 'storyboard_panel',
                    sourceIndex: panel.panel_number,
                    chapterNumber: activeChapterNumber,
                  })}
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
                <div key={`${page.page_number}-${index}`} style={compactBlockStyle}>
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
  { label: '通用参考', value: 'reference' },
]

const comicStyleOptions = [
  { label: '彩色', value: '彩色影视漫画，竖屏短剧分镜感，半写实人物，高对比光影，画风统一' },
  { label: '黑白漫画', value: '日式黑白漫画，高对比网点，清晰线稿，强烈明暗，分格节奏明确' },
  { label: '国漫', value: '现代国漫彩色风格，人物精致，情绪表演强，电影感构图，细腻光影' },
  { label: '电影分镜', value: '电影故事板风格，镜头语言明确，低饱和色彩，强调构图、景别和调度' },
  { label: '写实短剧', value: '写实短剧剧照风格，真实室内外光线，人物表演自然，商业剧质感' },
]

function InlineImageResult({
  image,
  loading,
}: {
  image?: InlineGeneratedImage
  loading: boolean
}) {
  if (loading) {
    return (
      <div style={inlineImageShellStyle}>
        <Skeleton.Image active style={{ width: 168, height: 112 }} />
        <Space direction="vertical" size={4}>
          <Text strong>正在生成图片</Text>
          <Text type="secondary">完成后会显示在这里，并同步关联到项目素材。</Text>
        </Space>
      </div>
    )
  }

  const src = assetFileUrl(image?.url || image?.localPath)
  if (!image || !src) return null

  return (
    <div style={inlineImageShellStyle}>
      <Image
        src={src}
        width={168}
        height={112}
        style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid #eef0f3' }}
      />
      <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
        <Text strong>已生成图片</Text>
        <Text type="secondary" ellipsis={{ tooltip: image.prompt }}>
          {image.model || image.provider || 'image'}
        </Text>
        {image.assetId ? <Tag color="green">已入项目素材</Tag> : <Tag>本次结果</Tag>}
      </Space>
    </div>
  )
}

function ReferenceCardsPanel({
  assets,
  loading,
  onLinkAsset,
}: {
  assets: ProjectAssetLink[]
  loading: boolean
  onLinkAsset: (assetId: string, role: string) => void
}) {
  const [assetId, setAssetId] = useState('')
  const [role, setRole] = useState('character')
  const referenceAssets = assets.filter((asset) =>
    ['character', 'background', 'style', 'reference'].includes(asset.role),
  )

  return (
    <WorkbenchSection
      title="参考卡"
      extra={
        <Tag color={referenceAssets.length ? 'blue' : 'default'}>
          {referenceAssets.length} 个
        </Tag>
      }
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
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
              onLinkAsset(assetId, role)
              setAssetId('')
            }}
          >
            关联
          </Button>
        </Space.Compact>
        <Text type="secondary">
          角色卡、背景和画风参考会作为漫画生成的一致性资产入口；当前先建立项目关联，后续生成提示会读取这些参考。
        </Text>
        {referenceAssets.length ? (
          <Space size={[6, 6]} wrap>
            {referenceAssets.map((asset) => (
              <Tooltip key={asset.id} title={asset.asset_id}>
                <Tag color={asset.role === 'character' ? 'green' : asset.role === 'style' ? 'purple' : 'blue'}>
                  {referenceRoleOptions.find((item) => item.value === asset.role)?.label || asset.role}
                </Tag>
              </Tooltip>
            ))}
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无参考卡" />
        )}
      </Space>
    </WorkbenchSection>
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
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="拖动调整宽度"
      onMouseDown={onMouseDown}
      style={resizeHandleStyle}
      onMouseEnter={(event) => {
        event.currentTarget.style.background = '#e6f4ff'
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.background = 'transparent'
      }}
    >
      <span style={resizeHandleLineStyle} />
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

function ScriptTab({
  novelBodies,
  comicPages,
  onSendImagePrompt,
  inlineImages,
  inlineImageLoadingKey,
}: {
  novelBodies: ProjectContent[]
  comicPages: ProjectContent[]
  onSendImagePrompt: (prompt: string, context?: ImagePromptContext) => void
  inlineImages: Record<string, InlineGeneratedImage>
  inlineImageLoadingKey: string | null
}) {
  if (!novelBodies.length && !comicPages.length) {
    return (
      <Space direction="vertical" size={12} style={{ width: '100%', alignItems: 'center', padding: 40 }}>
        <Empty description="还没有可阅读的正文或漫画页，请先在单话工作台生成正文/漫画页" />
      </Space>
    )
  }
  const renderInlineImage = (context: ImagePromptContext) => {
    const key = imageContextKey(context)
    return <InlineImageResult image={inlineImages[key]} loading={inlineImageLoadingKey === key} />
  }
  const sortedNovelBodies = sortProjectContentsForReading(novelBodies)
  const sortedComicPages = sortProjectContentsForReading(comicPages)

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Tabs
        items={[
          {
            key: 'reader',
            label: `正文阅读 ${novelBodies.length ? `(${novelBodies.length})` : ''}`,
            children: novelBodies.length ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {sortedNovelBodies.map((body) => (
                  <article key={body.id} style={readerPanelStyle}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <div>
                        <Title level={4} style={{ margin: 0 }}>
                          {body.title}
                        </Title>
                        <Text type="secondary">
                          第 {body.chapter_number || '-'} 章 · v{body.version} · {body.data?.word_count || body.text_content?.length || 0} 字
                        </Text>
                      </div>
                    </Space>
                    <Paragraph style={readerTextStyle}>
                      {body.text_content || body.data?.content}
                    </Paragraph>
                  </article>
                ))}
              </Space>
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
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
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
  loading,
  onLinkAsset,
}: {
  assets: ProjectAssetLink[]
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
            { title: '素材 ID', dataIndex: 'asset_id', ellipsis: true },
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
  border: '1px solid #eef0f3',
  borderRadius: 8,
  padding: 14,
  background: '#fafafa',
}

const workbenchHeaderStyle: React.CSSProperties = {
  border: '1px solid #eef0f3',
  borderRadius: 8,
  padding: 14,
  background: '#fff',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 16,
}

const compactBlockStyle: React.CSSProperties = {
  border: '1px solid #eef0f3',
  borderRadius: 8,
  padding: 10,
  background: '#fff',
}

const readerPanelStyle: React.CSSProperties = {
  border: '1px solid #eef0f3',
  borderRadius: 8,
  padding: '22px 26px',
  background: '#fff',
}

const readerTextStyle: React.CSSProperties = {
  margin: '18px 0 0',
  whiteSpace: 'pre-wrap',
  fontSize: 16,
  lineHeight: 1.9,
}

const comicPreviewGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 12,
}

const comicPreviewPageStyle: React.CSSProperties = {
  border: '1px solid #eef0f3',
  borderRadius: 8,
  padding: 12,
  background: '#fff',
  minHeight: 180,
}

const inlineImageShellStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  alignItems: 'center',
  border: '1px solid #eef0f3',
  borderRadius: 8,
  padding: 10,
  background: '#fbfcff',
}

const resizeHandleStyle: React.CSSProperties = {
  alignSelf: 'stretch',
  minHeight: 120,
  cursor: 'col-resize',
  display: 'flex',
  alignItems: 'stretch',
  justifyContent: 'center',
  borderRadius: 8,
  transition: 'background 120ms ease',
}

const resizeHandleLineStyle: React.CSSProperties = {
  width: 2,
  borderRadius: 2,
  background: '#d9dee8',
  margin: '8px 0',
}
