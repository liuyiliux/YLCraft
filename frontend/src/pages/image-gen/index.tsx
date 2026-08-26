/**
 * YLCraft — AI 图像生成页面
 *
 * 功能：
 * - 文生图 / 图生图
 * - 多 Provider 切换
 * - 批量生成
 * - 生成历史
 * - 图片下载 / 入库
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Input,
  Button,
  Select,
  Slider,
  Switch,
  Space,
  Spin,
  message,
  Image,
  Tag,
  Tooltip,
  Progress,
  Empty,
  Tabs,
  Upload,
  Modal,
} from 'antd'
import {
  ThunderboltOutlined,
  PictureOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SettingOutlined,
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  InboxOutlined,
  FileTextOutlined,
  BranchesOutlined,
  DatabaseOutlined,
  CloseOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTheme } from '../../constants/theme'
import { createUserImagePromptReference, getImageBackends, generateImage as generateImageApi, getImageTask, linkCreativeProjectAsset } from '../../api'
import AssetReferencePicker from '../../components/asset-reference-picker/AssetReferencePicker'
import type { ImagePromptReference } from '../../api'
import MultiPlatformGen from './MultiPlatformGen'
import { useTaskPolling } from '../../hooks/useTaskPolling'
import PromptReferencePicker, { type PromptReferenceAction } from '../../components/prompt-library/PromptReferencePicker'


const { TextArea } = Input
const { Dragger } = Upload

function safeDecode(value: string | null): string {
  if (!value) return ''
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

// 常见标准比例
function assetFileUrl(path?: string): string {
  if (!path) return ''
  if (/^(https?:|data:|blob:|\/api\/)/i.test(path)) return path
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}`
}

function getGeneratedImageSrc(img: GeneratedImage): string {
  return assetFileUrl(img.url || img.local_path)
}

const STANDARD_RATIOS = [
  { ratio: '1:1', threshold: 0.05 },
  { ratio: '16:9', threshold: 0.05 },
  { ratio: '9:16', threshold: 0.05 },
  { ratio: '4:3', threshold: 0.05 },
  { ratio: '3:4', threshold: 0.05 },
  { ratio: '3:2', threshold: 0.05 },
  { ratio: '2:3', threshold: 0.05 },
  { ratio: '21:9', threshold: 0.08 },
]

  // 计算宽高比例
function calculateAspectRatio(size: string): string {
  const match = size.match(/(\d+)\s*[x*]\s*(\d+)/i)
  if (!match) return ''
  
  const width = parseInt(match[1])
  const height = parseInt(match[2])
  
  // 计算实际比例
  const actualRatio = width / height
  
  // 匹配标准比例
  for (const { ratio, threshold } of STANDARD_RATIOS) {
    const [rw, rh] = ratio.split(':').map(Number)
    const expectedRatio = rw / rh
    if (Math.abs(actualRatio - expectedRatio) < threshold) {
      // 直接返回匹配到的比例，不需要交换
      return ratio
    }
  }
  
  // 如果没有匹配，返回简化比例
  const gcd = (a: number, b: number): number => b === 0 ? a : gcd(b, a % b)
  const divisor = gcd(width, height)
  
  if (divisor > 1) {
    const ratioWidth = width / divisor
    const ratioHeight = height / divisor
    // 确保是小数在前
    if (ratioWidth > ratioHeight) {
      return `${Math.round(ratioWidth)}:${Math.round(ratioHeight)}`
    } else {
      return `${Math.round(ratioHeight)}:${Math.round(ratioWidth)}`
    }
  }
  
  return ''  // 无法简化
}

// 获取尺寸显示标签
function getSizeLabel(size: string): string {
  const ratio = calculateAspectRatio(size)
  if (ratio) {
    return `${size} (${ratio})`
  }
  return size
}

interface GeneratedImage {
  id: string
  url: string
  prompt: string
  provider: string
  model: string
  seed?: number
  negative_prompt?: string
  generation_mode?: 'text_to_image' | 'image_to_image'
  size?: string
  created_at: string
  local_path?: string
  asset_id?: string
  project_linked?: boolean
  prompt_reference_title?: string
}

interface BackendInfo {
  provider: string
  provider_label: string
  name: string
  model: string
  available_models: string[]
  capabilities: string[]
  support_reference_image: boolean
  reference_image_field?: string
  supported_sizes: string[]         // 支持的尺寸列表（如 1024x1024）
  supported_aspect_ratios: string[]  // 支持的比例列表（如 1:1, 16:9）
}

function supportsBackendCapability(backend: BackendInfo, capability: 'text_to_image' | 'image_to_image'): boolean {
  if (backend.capabilities?.length) {
    return backend.capabilities.includes(capability)
  }
  return capability === 'image_to_image'
    ? Boolean(backend.support_reference_image)
    : true
}

interface ProjectContext {
  projectId: string
  contentId: string
  sourceType: string
  sourceIndex: string
  sourceTitle: string
  chapterNumber: string
  role: string
  relation: string
  hasContext: boolean
}

interface PendingImageTask {
  taskId: string
  externalTaskId?: string
  prompt: string
  negativePrompt: string
  provider?: string
  selectedModel?: string
  size: string
  projectContext: ProjectContext
  promptReference?: ImagePromptReference | null
}

export default function ImageGenPage() {
  const [searchParams] = useSearchParams()
  const urlTab = searchParams.get('tab')
  const multiTopic = safeDecode(searchParams.get('topic'))
  const multiPlatforms = safeDecode(searchParams.get('platforms'))
    .split(',')
    .map(p => p.trim())
    .filter(Boolean)

  if (urlTab === 'multi') {
    return (
      <MultiPlatformGen
        initialTopic={multiTopic}
        initialPlatforms={multiPlatforms.length > 0 ? multiPlatforms : undefined}
        autoGenerate={Boolean(multiTopic)}
      />
    )
  }

  return <ImageGenSinglePage />
}

function ImageGenSinglePage() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const projectContext = useMemo(() => {
    const projectId = searchParams.get('project_id') || ''
    const contentId = searchParams.get('content_id') || ''
    const sourceType = searchParams.get('source_type') || ''
    const sourceIndex = searchParams.get('source_index') || ''
    const sourceTitle = safeDecode(searchParams.get('source_title'))
    const chapterNumber = searchParams.get('chapter_number') || ''
    return {
      projectId,
      contentId,
      sourceType,
      sourceIndex,
      sourceTitle,
      chapterNumber,
      role: searchParams.get('role') || 'output',
      relation: searchParams.get('relation') || 'derived_from',
      hasContext: Boolean(projectId),
    }
  }, [searchParams])

  // 生成模式
  const [mode, setMode] = useState<'text2img' | 'img2img'>('text2img')

  // 输入
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [referenceImages, setReferenceImages] = useState<UploadFile[]>([])
  const [referenceAssetIds, setReferenceAssetIds] = useState<string[]>([])
  const [referenceUrl, setReferenceUrl] = useState('')
  const [assetPickerOpen, setAssetPickerOpen] = useState(false)

  const handleAssetPicked = (payload: any) => {
    // 方案 A：素材库选图走后端本地解析，仅记录 assetId，前端不下载转 base64
    setReferenceImages((prev) => [
      ...prev,
      {
        uid: `asset-${payload.asset?.id || Date.now()}`,
        name: payload.asset?.title || '素材库图片',
        status: 'done',
        url: payload.url || payload.asset?.thumbnail_url || '',
        assetId: payload.assetId,
      } as unknown as UploadFile,
    ])
    if (payload.assetId) {
      setReferenceAssetIds((prev) => [...prev, payload.assetId])
    }
  }
  const [promptReferencePickerOpen, setPromptReferencePickerOpen] = useState(false)
  const [selectedPromptReference, setSelectedPromptReference] = useState<ImagePromptReference | null>(null)

  // 参数
  const [provider, setProvider] = useState<string>()
  const [selectedModel, setSelectedModel] = useState<string>()  // 动态模型选择
  const [size, setSize] = useState('1024x1024')
  const [batchCount, setBatchCount] = useState(1)
  const [seed, setSeed] = useState<number>()

  // 状态
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [pendingTask, setPendingTask] = useState<PendingImageTask | null>(null)

  // 结果
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([])
  const [savedPromptImageIds, setSavedPromptImageIds] = useState<Set<string>>(new Set())
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [defaultBackend, setDefaultBackend] = useState<string>()
  const [lastProjectLinkStatus, setLastProjectLinkStatus] = useState<'idle' | 'success' | 'error'>('idle')

  // 预览
  const [previewImage, setPreviewImage] = useState<GeneratedImage | null>(null)
  const hasFetchedBackends = useRef(false)
  const hasAppliedUrlParams = useRef(false)  // 标记是否已应用 URL 参数

  const applyPromptReference = (reference: ImagePromptReference, action: PromptReferenceAction) => {
    setPrompt(current => {
      const currentPrompt = current.trim()
      if (action === 'append' && currentPrompt) {
        return `${currentPrompt}\n\n${reference.prompt}`.trim()
      }
      return reference.prompt
    })
    if (reference.negative_prompt && !negativePrompt.trim()) {
      setNegativePrompt(reference.negative_prompt)
    }
    setSelectedPromptReference(reference)
    setPromptReferencePickerOpen(false)
    message.success(action === 'append' ? '已追加 Prompt 参考' : '已替换为 Prompt 参考')
  }



  // 按厂商分组后端（根据 mode 过滤不支持的模型）
  const { groupedBackends, vendorOptions } = useMemo(() => {
    // 按当前模式过滤，避免 /images/edits 这类纯图片编辑连接器出现在文生图里。
    const filteredBackends = mode === 'img2img'
      ? backends.filter(b => supportsBackendCapability(b, 'image_to_image'))
      : backends.filter(b => supportsBackendCapability(b, 'text_to_image'))

    const groups = filteredBackends.reduce((acc, b) => {
      const key = b.provider_label || b.provider
      if (!acc[key]) {
        acc[key] = {
          provider: b.provider,
          provider_label: key,
          backends: [],
        }
      }
      acc[key].backends.push(b)
      return acc
    }, {} as Record<string, { provider: string, provider_label: string, backends: BackendInfo[] }>)
    
    // 对每个厂商的后端进行排序：有图生图能力的优先
    Object.values(groups).forEach(group => {
      group.backends.sort((a, b) => {
        const aIsImg2Img = a.support_reference_image ? 0 : 1
        const bIsImg2Img = b.support_reference_image ? 0 : 1
        return aIsImg2Img - bIsImg2Img
      })
    })
    
    const options = Object.values(groups).map(g => ({
      label: g.provider_label,
      value: g.provider_label,
    }))
    
    return { groupedBackends: groups, vendorOptions: options }
  }, [backends, mode])

  // 根据当前模型获取支持的尺寸选项
  const sizeOptions = useMemo(() => {
    // 查找当前选中的后端（通过 name 匹配）
    const vendorGroup = Object.values(groupedBackends).find(g => g.provider_label === provider)
    const currentBackend = vendorGroup?.backends.find(b => b.name === selectedModel)
    
    const options: { label: string, value: string }[] = []
    
    // 添加具体尺寸
    if (currentBackend?.supported_sizes && currentBackend.supported_sizes.length > 0) {
      currentBackend.supported_sizes.forEach(size => {
        options.push({
          label: getSizeLabel(size),
          value: size,
        })
      })
    }
    
    // 添加比例
    if (currentBackend?.supported_aspect_ratios && currentBackend.supported_aspect_ratios.length > 0) {
      currentBackend.supported_aspect_ratios.forEach(ratio => {
        options.push({
          label: `比例 ${ratio}`,
          value: ratio,
        })
      })
    }
    
    // 如果后端没有配置，返回默认选项
    if (options.length === 0) {
      return [
        { label: '1024 × 1024 (1:1)', value: '1024x1024' },
        { label: '1280 × 720 (16:9)', value: '1280x720' },
        { label: '720 × 1280 (9:16)', value: '720x1280' },
        { label: '1920 × 1080 (16:9)', value: '1920x1080' },
        { label: '1080 × 1920 (9:16)', value: '1080x1920' },
      ]
    }
    
    return options
  }, [backends, provider, selectedModel, groupedBackends])

  // 尺寸选项
  useEffect(() => {
    // 避免重复应用
    if (hasAppliedUrlParams.current) return
    hasAppliedUrlParams.current = true

    const promptParam = searchParams.get('prompt')
    const negativePromptParam = searchParams.get('negative_prompt')
    const modelParam = searchParams.get('model')
    const sizeParam = searchParams.get('size')
    const referenceImageParam = searchParams.get('reference_image')

    if (promptParam) {
      console.log('[ImageGen] Setting prompt:', promptParam)
      setPrompt(promptParam)
    }
    if (negativePromptParam) setNegativePrompt(negativePromptParam)
    if (sizeParam) setSize(sizeParam)
    if (referenceImageParam) {
      // 自动切换到图生图模式并设置参考图
      setMode('img2img')
      // 创建 UploadFile 格式的参考图
      const refImage: UploadFile = {
        uid: '-1',
        name: 'reference_image.png',
        status: 'done',
        url: referenceImageParam,
      }
      console.log('[ImageGen] Setting reference image:', referenceImageParam)
      setReferenceImages([refImage])
    }
  }, [searchParams])

  // 当后端加载完成后，根据 URL 参数设置模型
  useEffect(() => {
    const modelParam = searchParams.get('model')
    if (modelParam && backends.length > 0) {
      console.log('[ImageGen] Trying to set model from URL:', modelParam)
      console.log('[ImageGen] Available backends:', backends.map(b => ({ provider: b.provider_label, name: b.name, model: b.model, available: b.available_models })))
      
      // 查找包含该模型的厂商（通过 name、model 或 available_models 匹配）
      const targetBackend = backends.find(b =>
        supportsBackendCapability(b, mode === 'img2img' ? 'image_to_image' : 'text_to_image') && (
          b.name === modelParam ||
          b.model === modelParam ||
          b.available_models?.includes(modelParam)
        )
      )
      if (targetBackend) {
        console.log('[ImageGen] Found matching backend:', targetBackend.provider_label, targetBackend.name, targetBackend.model)
        setProvider(targetBackend.provider_label)
        setSelectedModel(targetBackend.name)  // 使用后端的 name 作为选中值
      } else {
        console.log('[ImageGen] Model not found in any backend. URL model:', modelParam)
        console.log('[ImageGen] Will keep existing selection or set default')
      }
    }
  }, [backends, searchParams, mode])

  // 切换模型时，如果当前尺寸不在支持列表中，自动切换到第一个可用尺寸
  useEffect(() => {
    if (sizeOptions.length > 0 && !sizeOptions.find(o => o.value === size)) {
      setSize(sizeOptions[0].value)
    }
  }, [selectedModel, sizeOptions])

  // 加载后端列表
  useEffect(() => {
    if (hasFetchedBackends.current) return
    hasFetchedBackends.current = true
    getImageBackends()
      .then(data => {
        if (data.success && data.backends.length > 0) {
          console.log('[ImageGen] Backends loaded:', data.backends.map(b => ({ name: b.name, model: b.model, available: b.available_models })))
          setBackends(data.backends)
          // 只有在没有从 URL 设置模型时，才设置默认模型
          const modelParam = searchParams.get('model')
          if (!hasAppliedUrlParams.current || !modelParam) {
            const firstBackend = data.backends.find((b: BackendInfo) => supportsBackendCapability(b, 'text_to_image')) || data.backends[0]
            const firstVendor = firstBackend.provider_label
            console.log('[ImageGen] Setting default provider/model:', firstVendor, firstBackend.name)
            setProvider(firstVendor)
            setSelectedModel(firstBackend.name)
          } else {
            console.log('[ImageGen] Skipping default model - URL model param:', modelParam)
          }
        }
      })
      .catch(() => message.error('加载后端列表失败'))
  }, [])

  // 厂商切换时，重置模型选择
  const handleProviderChange = (newVendor: string) => {
    setProvider(newVendor)
    const vendorGroup = Object.values(groupedBackends).find(g => g.provider_label === newVendor)
    if (vendorGroup && vendorGroup.backends.length > 0) {
      const firstBackend = vendorGroup.backends[0]
      setSelectedModel(firstBackend.name)
      // 自动选中第一个尺寸
      if (firstBackend.supported_sizes?.length > 0) {
        setSize(firstBackend.supported_sizes[0])
      }
    }
  }

  // 模式切换时：如果当前厂商/模型不可用，自动切换
  useEffect(() => {
    const availableVendors = Object.values(groupedBackends)
    if (availableVendors.length === 0) {
      // 没有可用后端，清空选择
      setProvider(undefined)
      setSelectedModel(undefined)
      return
    }

    // 检查当前厂商是否还可用
    const currentVendorAvailable = availableVendors.some(g => g.provider_label === provider)
    if (!currentVendorAvailable) {
      // 切换到第一个可用厂商
      const firstVendor = availableVendors[0]
      setProvider(firstVendor.provider_label)
      setSelectedModel(firstVendor.backends[0]?.name)
    } else {
      // 检查当前模型是否还可用（通过 name 匹配）
      const vendorGroup = availableVendors.find(g => g.provider_label === provider)
      const currentModelAvailable = vendorGroup?.backends.some(b => b.name === selectedModel)
      if (!currentModelAvailable && vendorGroup?.backends[0]) {
        setSelectedModel(vendorGroup.backends[0].name)
        if (vendorGroup.backends[0].supported_sizes?.length > 0) {
          setSize(vendorGroup.backends[0].supported_sizes[0])
        }
      }
    }
  }, [mode])

  const appendGeneratedImages = useCallback(async (
    data: any,
    context: {
      prompt: string
      negativePrompt: string
      provider?: string
      selectedModel?: string
      size: string
      projectContext: ProjectContext
      promptReference?: ImagePromptReference | null
    }
  ) => {
    let projectLinkOk = false
    const linkedAssetIds: string[] = []
    const newImages: GeneratedImage[] = []
    const urls = (data.urls && data.urls.length > 0) ? data.urls : (data.url ? [data.url] : [])
    const localPaths = (data.all_local_paths && data.all_local_paths.length > 0)
      ? data.all_local_paths
      : (data.local_path ? [data.local_path] : [])
    const assetIds = (data.all_asset_hub_node_ids && data.all_asset_hub_node_ids.length > 0)
      ? data.all_asset_hub_node_ids
      : (data.asset_hub_node_id
        ? [data.asset_hub_node_id]
        : (data.all_asset_ids && data.all_asset_ids.length > 0)
          ? data.all_asset_ids
          : (data.asset_id ? [data.asset_id] : []))
    const resultCount = Math.max(urls.length, localPaths.length, assetIds.length)

    if (context.projectContext.hasContext && assetIds.length > 0) {
      try {
        for (let idx = 0; idx < assetIds.length; idx += 1) {
          const assetId = assetIds[idx]
          if (!assetId) continue
          await linkCreativeProjectAsset(context.projectContext.projectId, {
            asset_id: assetId,
            content_id: context.projectContext.contentId || undefined,
            role: context.projectContext.role,
            relation: context.projectContext.relation,
            metadata: {
              source_type: context.projectContext.sourceType,
              source_index: context.projectContext.sourceIndex,
              source_title: context.projectContext.sourceTitle,
              chapter_number: context.projectContext.chapterNumber,
              prompt: context.prompt,
              negative_prompt: context.negativePrompt || '',
              provider: context.selectedModel || context.provider || '',
              size: context.size,
              prompt_reference_id: context.promptReference?.id || '',
              prompt_reference_source_id: context.promptReference?.source_id || '',
              prompt_reference_title: context.promptReference?.title || '',
              prompt_reference_category: context.promptReference?.category || '',
              generated_at: new Date().toISOString(),
            },
          })
          linkedAssetIds.push(assetId)
        }
        projectLinkOk = linkedAssetIds.length > 0
        setLastProjectLinkStatus(projectLinkOk ? 'success' : 'idle')
      } catch (error: any) {
        setLastProjectLinkStatus('error')
        message.warning(error?.message || '图片已生成，但回写项目素材失败')
      }
    }

    for (let idx = 0; idx < resultCount; idx += 1) {
      newImages.push({
        id: `img_${Date.now()}_${idx}`,
        url: urls[idx] || '',
        prompt: context.prompt,
        provider: data.provider || context.provider || 'unknown',
        model: context.selectedModel || data.model || '',
        negative_prompt: context.negativePrompt || '',
        generation_mode: mode === 'img2img' ? 'image_to_image' : 'text_to_image',
        size: context.size,
        local_path: localPaths[idx] || data.local_path,
        asset_id: assetIds[idx],
        project_linked: projectLinkOk && Boolean(assetIds[idx]) && linkedAssetIds.includes(assetIds[idx]),
        prompt_reference_title: context.promptReference?.title,
        created_at: new Date().toISOString(),
      })
    }

    setGeneratedImages(prev => [...newImages, ...prev])
    message.success(
      <span>
        成功生成 {newImages.length} 张图片，
        {projectLinkOk ? '已回写到项目素材，' : ''}
        <a onClick={() => navigate('/assets')}>查看资产库</a>
      </span>,
      5
    )
  }, [mode, navigate])

  useTaskPolling({
    enabled: Boolean(pendingTask?.taskId),
    intervalMs: 5000,
    fetcher: useCallback(() => {
      if (!pendingTask) return Promise.resolve(null as any)
      return getImageTask(pendingTask.taskId, pendingTask.selectedModel)
    }, [pendingTask]),
    isDone: useCallback((data: any) => data?.success && data?.status === 'done', []),
    isFailed: useCallback((data: any) => data?.success === false || data?.status === 'error' || data?.status === 'failed', []),
    onData: useCallback((data: any) => {
      if (!data) return
      if (data.status === 'pending' || data.status === 'running') {
        setProgress(prev => Math.max(prev, Math.min(95, Math.round(data.progress || prev || 35))))
      }
    }, []),
    onDone: useCallback(async (data: any) => {
      if (!pendingTask) return
      setProgress(100)
      await appendGeneratedImages(data, pendingTask)
      setPendingTask(null)
      setLoading(false)
      setProgress(0)
    }, [appendGeneratedImages, pendingTask]),
    onFailed: useCallback((data: any) => {
      message.error(data?.error || '异步生图失败')
      setPendingTask(null)
      setLoading(false)
      setProgress(0)
    }, []),
    onError: useCallback((error: any) => {
      message.warning(error?.message ? `查询生图任务失败：${error.message}` : '查询生图任务失败')
    }, []),
  })

  // 生成图片
  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入提示词')
      return
    }

    setLoading(true)
    setProgress(10)
    let startedAsyncTask = false

    try {
      const isRatioSelection = /^\d+\s*:\s*\d+$/.test(size.trim())
      const body: any = {
        prompt,
        negative_prompt: negativePrompt || undefined,
        provider: selectedModel,  // provider 传入部署配置名称 (name)
        n: batchCount,
        seed,
      }
      if (isRatioSelection) {
        // 选中比例时作为 aspect_ratio 发送，由后端映射为 ratio 字段
        const activeBackend = backends.find((b) => b.name === selectedModel)
        body.aspect_ratio = size.trim()
        body.size = activeBackend?.supported_sizes?.[0] || '1K'
      } else {
        body.size = size
      }
      if (selectedPromptReference) {
        body.prompt_reference_id = selectedPromptReference.id
        body.prompt_reference_source_id = selectedPromptReference.source_id
        body.prompt_reference_title = selectedPromptReference.title
        body.prompt_reference_category = selectedPromptReference.category || undefined
        body.prompt_reference_source_url = selectedPromptReference.source_url || undefined
      }
      if (projectContext.hasContext) {
        body.project_id = projectContext.projectId
        body.content_id = projectContext.contentId || undefined
        body.source_type = projectContext.sourceType || undefined
        body.source_index = projectContext.sourceIndex || undefined
        body.source_title = projectContext.sourceTitle || undefined
        body.chapter_number = projectContext.chapterNumber || undefined
      }

      // 图生图模式：参考图
      // 素材库选图（assetId）→ 交后端本地解析转 base64；上传文件/手动 URL → 前端转 base64
      if (mode === 'img2img') {
        if (referenceAssetIds.length > 0) {
          body.reference_asset_ids = referenceAssetIds
        }
        const manualImages = referenceImages.filter((f) => !(f as any).assetId)
        if (manualImages.length > 0) {
          body.reference_images = await Promise.all(
            manualImages.map(async (f) => {
              if (f.originFileObj) {
                // blob -> base64
                return new Promise<string>((resolve, reject) => {
                  const reader = new FileReader()
                  reader.onload = () => resolve(reader.result as string)
                  reader.onerror = reject
                  reader.readAsDataURL(f.originFileObj!)
                })
              }
              // 手动 URL 参考图：需 fetch 下载后转 base64
              if (f.url) {
                try {
                  const resp = await fetch(f.url)
                  const blob = await resp.blob()
                  return new Promise<string>((resolve, reject) => {
                    const reader = new FileReader()
                    reader.onload = () => resolve(reader.result as string)
                    reader.onerror = reject
                    reader.readAsDataURL(blob)
                  })
                } catch (e) {
                  console.error('[ImageGen] 下载参考图失败:', e)
                  return f.url
                }
              }
              return ''
            })
          )
        }
      }

      setProgress(30)

      const data = await generateImageApi(body)

      setProgress(80)

      if (data.success) {
        if (data.status === 'pending' && data.task_id) {
          startedAsyncTask = true
          setPendingTask({
            taskId: data.task_id,
            externalTaskId: data.external_task_id,
            prompt,
            negativePrompt,
            provider,
            selectedModel,
            size,
            projectContext,
            promptReference: selectedPromptReference,
          })
          setProgress(35)
          message.info(`图片任务已提交，任务 ID：${data.task_id}`)
          return
        }

        await appendGeneratedImages(data, {
          prompt,
          negativePrompt,
          provider,
          selectedModel,
          size,
          projectContext,
          promptReference: selectedPromptReference,
        })
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error('生成失败: ' + e.message)
    } finally {
      if (!startedAsyncTask) {
        setLoading(false)
        setProgress(0)
      }
    }
  }

  // 下载图片
  const handleDownload = async (img: GeneratedImage) => {
    if (img.local_path) {
      window.open(assetFileUrl(img.local_path))
    } else if (img.url) {
      window.open(assetFileUrl(img.url))
    }
  }

  // 复制提示词
  const handleCopyPrompt = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制到剪贴板')
  }

  const saveGeneratedImagePrompt = async (image: GeneratedImage) => {
    try {
      const response = await createUserImagePromptReference({
        title: `${image.provider || '图片'} · ${image.prompt.slice(0, 22) || '已保存提示词'}`,
        prompt: image.prompt,
        negative_prompt: image.negative_prompt || '',
        provider: image.provider,
        model: image.model,
        asset_id: image.asset_id || '',
        generation_mode: image.generation_mode || 'text_to_image',
        size: image.size || '',
        seed: image.seed,
        tags: ['AI生成'],
      })
      if (!response?.success) {
        message.error(response?.error || '保存图片提示词失败')
        return
      }
      setSavedPromptImageIds((current) => new Set(current).add(image.id))
      message.success(response.created ? '已保存到“我的生图提示词”' : '已合并为现有提示词的新生成样例')
    } catch (error: any) {
      message.error(error?.message || '保存图片提示词失败')
    }
  }

  return (
    <div style={{ padding: 0 }}>
      <Row gutter={24}>
        {/* 左侧：输入面板 */}
        <Col xs={24} lg={10}>
          <Card
            title={
              <span>
                <PictureOutlined style={{ marginRight: 8, color: '#7c3aed' }} />
                AI 图像生成
              </span>
            }
            style={{ marginBottom: 16 }}
          >
            {/* 模式切换 */}
            <Tabs
              activeKey={mode}
              onChange={key => setMode(key as any)}
              items={[
                { key: 'text2img', label: '📝 文生图' },
                { key: 'img2img', label: '🖼️ 图生图' },
              ]}
              size="small"
            />

            {/* 提示词输入 */}
            <div style={{ marginBottom: 16 }}>
              <Space wrap style={{ width: '100%', justifyContent: 'space-between', marginBottom: 6 }}>
                <div style={{ fontWeight: 500, color: '#e2e8f0' }}>提示词</div>
                <Space size={8} wrap>
                  {selectedPromptReference ? (
                    <Tag
                      color="purple"
                      closable
                      onClose={() => setSelectedPromptReference(null)}
                      style={{ marginInlineEnd: 0 }}
                    >
                      {selectedPromptReference.title}
                    </Tag>
                  ) : null}
                  <Button size="small" icon={<FileTextOutlined />} onClick={() => setPromptReferencePickerOpen(true)}>
                    Prompt 参考库
                  </Button>
                </Space>
              </Space>
              <TextArea
                placeholder="描述你想要生成的图像，例如：一个身穿红色旗袍的年轻女性，站在古老的街道上，柔和的光线..."
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={4}
                style={{
                  background: '#1e1e2e',
                  border: '1px solid #333',
                  color: '#e2e8f0',
                }}
              />
            </div>

            {/* 反向提示词 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                反向提示词（可选）
              </div>
              <TextArea
                placeholder="不想出现的内容，例如：模糊、低质量、变形..."
                value={negativePrompt}
                onChange={e => setNegativePrompt(e.target.value)}
                rows={2}
                style={{
                  background: '#1e1e2e',
                  border: '1px solid #333',
                  color: '#e2e8f0',
                }}
              />
            </div>

            {/* 图生图：参考图上传 */}
            {mode === 'img2img' && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                  参考图片
                </div>
                <Dragger
                  multiple
                  maxCount={3}
                  fileList={referenceImages}
                  showUploadList={false}
                  onChange={({ fileList }) => {
                    setReferenceImages(fileList)
                    // 同步 assetId 列表（删除素材图时同步移除）
                    setReferenceAssetIds(fileList.map((f) => (f as any).assetId).filter(Boolean))
                  }}
                  beforeUpload={() => false}
                  style={{ background: '#1e1e2e', border: '1px dashed #444' }}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined style={{ color: '#7c3aed' }} />
                  </p>
                  <p style={{ color: '#8b8ba8' }}>点击或拖拽上传参考图片</p>
                  <p style={{ color: '#8b8ba8', fontSize: 12 }}>支持 1-3 张参考图</p>
                </Dragger>
                {/* 自定义参考图列表：缩略图 + 标题 + 删除按钮（避免 Dragger 默认列表无删除入口） */}
                {referenceImages.length > 0 && (
                  <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {referenceImages.map((f) => {
                      const thumbUrl = f.url || (f as any).thumbUrl || ''
                      return (
                        <div
                          key={f.uid}
                          style={{
                            position: 'relative',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            padding: '6px 10px',
                            background: '#1e1e2e',
                            border: '1px solid #333',
                            borderRadius: 6,
                            maxWidth: 260,
                          }}
                        >
                          {thumbUrl && (
                            <img
                              src={thumbUrl}
                              alt={f.name}
                              style={{
                                width: 36,
                                height: 36,
                                objectFit: 'cover',
                                borderRadius: 4,
                                background: '#0f0f1a',
                              }}
                            />
                          )}
                          <span
                            title={f.name}
                            style={{
                              color: '#e2e8f0',
                              fontSize: 12,
                              maxWidth: 160,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {f.name}
                          </span>
                          <Button
                            type="text"
                            size="small"
                            icon={<CloseOutlined />}
                            onClick={() => {
                              setReferenceImages((prev) => prev.filter((x) => x.uid !== f.uid))
                              setReferenceAssetIds((prev) =>
                                prev.filter((id) => id !== (f as any).assetId),
                              )
                            }}
                            style={{ color: '#8b8ba8' }}
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
                <div style={{ marginTop: 12 }}>
                  <Space wrap style={{ marginBottom: 8 }}>
                    <Button
                      icon={<DatabaseOutlined />}
                      onClick={() => setAssetPickerOpen(true)}
                      disabled={referenceImages.length >= 3}
                    >
                      从素材库选择
                    </Button>
                  </Space>
                  <Space.Compact style={{ width: '100%' }}>
                    <Input
                      placeholder="粘贴图片 URL（也可从素材库复制来源链接）"
                      value={referenceUrl}
                      onChange={(e) => setReferenceUrl(e.target.value)}
                      onPressEnter={() => {
                        const url = referenceUrl.trim()
                        if (!url) return
                        setReferenceImages((prev) => [
                          ...prev,
                          {
                            uid: `url-${Date.now()}`,
                            name: url.split('/').pop() || 'url-reference',
                            status: 'done',
                            url,
                          } as unknown as UploadFile,
                        ])
                        setReferenceUrl('')
                      }}
                      style={{ background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                    />
                    <Button
                      type="primary"
                      onClick={() => {
                        const url = referenceUrl.trim()
                        if (!url) return
                        setReferenceImages((prev) => [
                          ...prev,
                          {
                            uid: `url-${Date.now()}`,
                            name: url.split('/').pop() || 'url-reference',
                            status: 'done',
                            url,
                          } as unknown as UploadFile,
                        ])
                        setReferenceUrl('')
                      }}
                    >
                      添加 URL
                    </Button>
                  </Space.Compact>
                  <div style={{ marginTop: 6, fontSize: 12, color: '#8b8ba8' }}>
                    支持通过 URL 图生图：可从素材库选择图片，或手动输入图片地址（含素材库「来源 URL」）。最多 3 张。
                  </div>
                </div>
                <AssetReferencePicker
                  open={assetPickerOpen}
                  onClose={() => setAssetPickerOpen(false)}
                  onSelect={handleAssetPicked}
                />
              </div>
            )}

            {/* 参数设置 */}
            <Card
              size="small"
              title={
                <span>
                  <SettingOutlined style={{ marginRight: 6 }} />
                  高级设置
                </span>
              }
              style={{
                marginBottom: 16,
                background: '#1a1a2e',
                border: '1px solid #333',
              }}
            >
              <Row gutter={[16, 12]}>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    厂商
                  </div>
                  <Select
                    value={provider}
                    onChange={handleProviderChange}
                    style={{ width: '100%' }}
                    placeholder="选择厂商"
                    options={vendorOptions}
                  />
                </Col>
                <Col span={12}>
                  {(() => {
                    const vendorGroup = Object.values(groupedBackends).find(g => g.provider_label === provider)
                    return (
                      <>
                        <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                          模型（{vendorGroup?.backends.length || 0} 个部署配置）
                        </div>
                        <Select
                          value={selectedModel}
                          onChange={(val) => {
                            setSelectedModel(val)
                            // 切换模型后自动选中第一个尺寸
                            const targetBackend = vendorGroup?.backends.find(b => b.name === val)
                            if (targetBackend?.supported_sizes?.length > 0) {
                              setSize(targetBackend.supported_sizes[0])
                            }
                          }}
                          style={{ width: '100%' }}
                          placeholder="选择模型"
                          options={vendorGroup?.backends.map(b => ({
                            label: b.name,
                            value: b.name,
                          }))}
                          optionRender={(option) => {
                            const backend = vendorGroup?.backends.find(b => b.name === option.data.value)
                            return (
                              <div>
                                <div>{option.label}</div>
                                {backend?.supported_sizes?.length > 0 && (
                                  <div style={{ fontSize: 11, color: '#888' }}>
                                    尺寸: {backend.supported_sizes.length} 种
                                  </div>
                                )}
                              </div>
                            )
                          }}
                        />
                      </>
                    )
                  })()}
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    尺寸 / 比例
                    {sizeOptions.length < 5 && <Tag color="purple" style={{ marginLeft: 8, fontSize: 10 }}>模型限定</Tag>}
                  </div>
                  <Select
                    value={size}
                    onChange={(val) => {
                      setSize(val)
                    }}
                    style={{ width: '100%' }}
                    options={sizeOptions}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    批量数量：{batchCount}
                  </div>
                  <Slider
                    min={1}
                    max={4}
                    value={batchCount}
                    onChange={setBatchCount}
                    marks={{ 1: '1', 2: '2', 3: '3', 4: '4' }}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    随机种子（可选）
                  </div>
                  <Input
                    placeholder="留空随机"
                    type="number"
                    value={seed}
                    onChange={e => setSeed(e.target.value ? parseInt(e.target.value) : undefined)}
                    style={{ background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                  />
                </Col>
              </Row>
            </Card>

            {/* 生成按钮 */}
            {projectContext.hasContext && (
              <Card
                size="small"
                style={{
                  marginBottom: 12,
                  background: '#171827',
                  border: `1px solid ${lastProjectLinkStatus === 'error' ? '#7f1d1d' : '#2f365f'}`,
                }}
              >
                <Space direction="vertical" size={4}>
                  <Space wrap>
                    <Tag color={lastProjectLinkStatus === 'success' ? 'green' : 'blue'}>项目回写</Tag>
                    {projectContext.chapterNumber && <Tag>第 {projectContext.chapterNumber} 章</Tag>}
                    {projectContext.sourceType && <Tag>{projectContext.sourceType}</Tag>}
                  </Space>
                  <div style={{ fontSize: 12, color: THEME.textSecondary }}>
                    {lastProjectLinkStatus === 'success'
                      ? '本次生成图片已自动关联到项目素材。'
                      : lastProjectLinkStatus === 'error'
                        ? '图片已生成，但项目素材回写失败，可到资产库手动关联。'
                        : '生成成功后会自动保存到资产库，并关联回当前项目。'}
                  </div>
                </Space>
              </Card>
            )}

            <Button
              type="primary"
              size="large"
              block
              icon={<ThunderboltOutlined />}
              onClick={handleGenerate}
              loading={loading}
              style={{
                height: 48,
                fontSize: 16,
                fontWeight: 600,
                background: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
                border: 'none',
              }}
            >
              {pendingTask ? '等待生成结果...' : loading ? '生成中...' : '开始生成'}
            </Button>

            {/* 进度条 */}
            {loading && (
              <>
                <Progress
                  percent={progress}
                  status="active"
                  style={{ marginTop: 12 }}
                  strokeColor={{ '0%': '#7c3aed', '100%': '#a855f7' }}
                />
                {pendingTask && (
                  <Space direction="vertical" size={4} style={{ marginTop: 6, width: '100%' }}>
                    <div style={{ fontSize: 12, color: THEME.textSecondary }}>
                      异步任务 {pendingTask.taskId} 正在生成，完成后会自动保存到素材库。
                    </div>
                    {pendingTask.externalTaskId && (
                      <div style={{ fontSize: 12, color: THEME.textSecondary }}>
                        外部任务 {pendingTask.externalTaskId}
                      </div>
                    )}
                    <Button
                      size="small"
                      type="link"
                      style={{ alignSelf: 'flex-start', padding: 0 }}
                      onClick={() => navigate(`/tasks?task_id=${encodeURIComponent(pendingTask.taskId)}`)}
                    >
                      查看任务详情
                    </Button>
                  </Space>
                )}
              </>
            )}
          </Card>
        </Col>

        {/* 右侧：生成结果 */}
        <Col xs={24} lg={14}>
          <Card
            title={
              <span>
                <ThunderboltOutlined style={{ marginRight: 8, color: '#a855f7' }} />
                生成结果
                {generatedImages.length > 0 && (
                  <Tag color="purple" style={{ marginLeft: 8 }}>
                    {generatedImages.length} 张
                  </Tag>
                )}
              </span>
            }
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => setGeneratedImages([])}
                >
                  清空
                </Button>
              </Space>
            }
          >
            {generatedImages.length === 0 ? (
              <Empty
                description="暂无生成结果"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: '48px 0' }}
              />
            ) : (
              <Row gutter={[16, 16]}>
                {generatedImages.map(img => (
                  <Col xs={24} sm={12} md={8} key={img.id}>
                    <Card
                      hoverable
                      cover={
                        <div
                          style={{
                            height: 200,
                            background: THEME.bgElevated,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            overflow: 'hidden',
                          }}
                        >
                          <Image
                            src={getGeneratedImageSrc(img)}
                            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                            preview={{ src: getGeneratedImageSrc(img) }}
                            placeholder
                          />
                        </div>
                      }
                      actions={[
                        <Tooltip title="下载" key="download">
                          <DownloadOutlined style={{ color: THEME.textSecondary }} onClick={() => handleDownload(img)} />
                        </Tooltip>,
                        <Tooltip title="复制提示词" key="copy">
                          <CopyOutlined style={{ color: THEME.textSecondary }} onClick={() => handleCopyPrompt(img.prompt)} />
                        </Tooltip>,
                        <Button
                          key="save-prompt"
                          type="text"
                          size="small"
                          icon={<SaveOutlined />}
                          disabled={savedPromptImageIds.has(img.id)}
                          onClick={() => void saveGeneratedImagePrompt(img)}
                        >
                          {savedPromptImageIds.has(img.id) ? '已保存' : '保存提示词'}
                        </Button>,
                        <Tooltip title="删除" key="delete">
                          <DeleteOutlined
                            style={{ color: THEME.textSecondary }}
                            onClick={() => setGeneratedImages(prev => prev.filter(i => i.id !== img.id))}
                          />
                        </Tooltip>,
                      ]}
                      size="small"
                    >
                      <Card.Meta
                        title={
                          <div
                            style={{
                              fontSize: 12,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {img.prompt.slice(0, 30)}...
                          </div>
                        }
                        description={
                          <Space direction="vertical" size={2} style={{ width: '100%' }}>
                            <Space size={4}>
                              <Tag color="blue">{img.provider}</Tag>
                              {img.project_linked && <Tag color="green">已回写项目</Tag>}
                              {img.seed && <span style={{ fontSize: 11, color: THEME.textSecondary }}>seed: {img.seed}</span>}
                            </Space>
                            <div style={{ height: 22 }} />
                          </Space>
                        }
                      />
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </Card>
        </Col>
      </Row>
      <PromptReferencePicker
        open={promptReferencePickerOpen}
        onCancel={() => setPromptReferencePickerOpen(false)}
        onApply={applyPromptReference}
      />
    </div>
  )
}
