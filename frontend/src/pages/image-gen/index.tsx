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
  Alert,
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
  EditOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTheme } from '../../constants/theme'
import { createUserImagePromptReference, getImageBackends, generateImage as generateImageApi, getImageTask, linkCreativeProjectAsset, optimizeImagePrompt } from '../../api'
import AssetReferencePicker from '../../components/asset-reference-picker/AssetReferencePicker'
import ImageEditorWorkspace from '../../components/image-annotation/ImageEditorWorkspace'
import { renderAnnotatedImage } from '../../components/image-annotation/renderAnnotatedImage'
// ⚠️ 只导入 `toAnnotationPayload` / `ImageAnnotation`，**不再导入
// `AnnotationCanvas` 组件本身**（2026-10-07）：主表单里的批注画布已移除，
// 批注统一在「改图工作台」（ImageEditorWorkspace）里画。
// 数据类型与提交载荷仍是共用的，所以这两个必须留。
import {
  toAnnotationPayload,
  type ImageAnnotation,
} from '../../components/image-annotation/AnnotationCanvas'
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
  // 工作台形态：`classic` = 单栏表单（默认）；`editor` = EditHere 式编辑台。
  //
  // **默认必须是 classic**：编辑台是给「看着图改图」用的，没有参考图就没有可圈的东西。
  // 文生图同样不该进编辑台——它连参考图都没有，进去只能看到一个空画布。
  // 用户真正需要批注时，在图生图下点「切换到编辑台」即可。
  const [workspace, setWorkspace] = useState<'classic' | 'editor'>('classic')
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null)

  // 输入
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [referenceImages, setReferenceImages] = useState<UploadFile[]>([])
  const [referenceAssetIds, setReferenceAssetIds] = useState<string[]>([])
  const [referenceUrl, setReferenceUrl] = useState('')
  const [assetPickerOpen, setAssetPickerOpen] = useState(false)

  // 图生图「画面批注」：在参考图上圈选区域并写下修改意见，随主提示词一起提交。
  // 空数组是常态，提交时若为空则完全不带该字段。
  const [annotations, setAnnotations] = useState<ImageAnnotation[]>([])
  // 批注定位方式：
  // - `marked`（默认）= 把框**画到像素上**，作为一张额外参考图随原图一起发给模型。
  //   多模态模型看图比读数字准，Google 的 Gemini 图像标记工具用的就是这个思路。
  // - `text` = 只发原图 + 文字坐标描述。留给"模型不认第二张图"或"框线反而干扰画质"的情况。
  //
  // 默认 `marked`：我们原先只报中心点，「圈一小撮头发」和「整头改色」会生成几乎
  // 一样的指令，模型分不出所以有时只改一撮、有时整张脸被重画。画出来就没有这个歧义。
  const [annotationHintMode, setAnnotationHintMode] = useState<'marked' | 'text'>('marked')
  // 标注图说明的自定义文案：`undefined` = 用内置默认；`''` = 已关闭；其余 = 自定义。
  // 三态必须分开——用户要能看见默认文案、能改、也能整段关掉。
  const [annotationHintText, setAnnotationHintText] = useState<string | undefined>(undefined)
  // 批注画布标注的是**第一张参考图**：多于一张时用户无法分辨意见对应哪张图，
  // 猜错比不猜更糟，所以固定第一张并在界面上写明。
  //
  // 三条参考图来源里只有「粘贴 URL」天然带地址：
  // - 本地上传走 `beforeUpload={() => false}`，**从不设置 `f.url`**，只有 `originFileObj`；
  // - 素材库选图默认走 base64 模式，`url` 是**空串**（图片由后端按 assetId 解析）。
  // 因此这里必须各自兜底，否则批注面板在这些路径下永不出现——
  // 用户明明加了参考图，却被告知「加上参考图后就能圈选」。
  const [localPreviewUrls, setLocalPreviewUrls] = useState<Record<string, string>>({})

  const annotationImage = useMemo(() => {
    const first = referenceImages[0]
    if (!first) return ''
    const meta = first as unknown as { assetId?: string; thumbUrl?: string }
    const direct = first.url || meta.thumbUrl || ''
    if (direct) return direct
    if (meta.assetId) return `/api/v1/assets/${encodeURIComponent(meta.assetId)}/thumbnail`
    if (first.uid && localPreviewUrls[first.uid]) return localPreviewUrls[first.uid]
    return ''
  }, [referenceImages, localPreviewUrls])

  // objectURL 不回收会一直占着内存直到页面关闭（参考图可能有好几 MB）。
  useEffect(() => {
    setLocalPreviewUrls((prev) => {
      const next: Record<string, string> = {}
      for (const file of referenceImages) {
        const existing = prev[file.uid]
        if (existing) {
          next[file.uid] = existing
          continue
        }
        const raw = file.originFileObj as unknown as Blob | undefined
        if (raw) next[file.uid] = URL.createObjectURL(raw)
      }
      // 已移除的引用要 revoke，否则每换一次参考图就漏一批。
      for (const uid of Object.keys(prev)) {
        if (!next[uid]) URL.revokeObjectURL(prev[uid])
      }
      return next
    })
  }, [referenceImages])

  useEffect(
    () => () => {
      Object.values(localPreviewUrls).forEach((url) => URL.revokeObjectURL(url))
    },
    [localPreviewUrls],
  )

  // 切走图生图时丢弃批注：这些坐标是相对**那一张**参考图的，换图后全部失效。
  useEffect(() => {
    if (mode !== 'img2img') {
      setAnnotations([])
      // 文生图没有参考图，编辑台留着只会看到一个空画布——没有可圈的东西。
      // 直接退回表单模式，而不是把人困在一个用不了的界面里。
      setWorkspace('classic')
      setActiveAnnotationId(null)
    }
  }, [mode])

  // 换参考图后同样作废——旧坐标指向的是上一张图。
  useEffect(() => {
    setAnnotations([])
  }, [annotationImage])

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

  // ===== AI 优化提示词 =====
  const [optimizeOpen, setOptimizeOpen] = useState(false)
  const [optimizeInstruction, setOptimizeInstruction] = useState('')
  const [optimizeResult, setOptimizeResult] = useState('')
  const [optimizing, setOptimizing] = useState(false)
  const [llmBackends, setLlmBackends] = useState<any[]>([])
  const [optimizeProvider, setOptimizeProvider] = useState<string>('')
  const [optimizeModel, setOptimizeModel] = useState<string>('')

  // 优化用的是 LLM，不是生图后端：单独拉一份可用的文本模型列表。
  useEffect(() => {
    if (!optimizeOpen) return
    fetch('/api/v1/ai/connectors?provider_type=llm&active_only=true')
      .then(res => res.json())
      .then(result => {
        const items = result?.connectors || result?.data || result?.items || []
        setLlmBackends(items)
        if (items.length && !optimizeProvider) {
          const first = items[0]
          setOptimizeProvider(first.name || first.provider || '')
          setOptimizeModel(
            first.default_model || first.model || first.available_models?.[0] || '',
          )
        }
      })
      .catch(() => setLlmBackends([]))
  }, [optimizeOpen, optimizeProvider])

  const openOptimize = () => {
    if (!prompt.trim()) {
      message.warning('请先填写提示词，再让 AI 优化')
      return
    }
    setOptimizeResult('')
    setOptimizeInstruction('')
    setOptimizeOpen(true)
  }

  const runOptimize = async () => {
    if (optimizing) return
    setOptimizing(true)
    try {
      const res: any = await optimizeImagePrompt({
        prompt,
        instruction: optimizeInstruction,
        provider: optimizeProvider || undefined,
        model: optimizeModel || undefined,
      })
      const data = res?.data ?? res
      if (data?.success && data?.optimized_prompt) {
        setOptimizeResult(data.optimized_prompt)
        message.success('已生成优化后的提示词')
      } else {
        message.error(data?.error || '优化失败')
      }
    } catch (error: any) {
      message.error(error?.message || '优化失败')
    } finally {
      setOptimizing(false)
    }
  }

  const applyOptimized = () => {
    if (!optimizeResult.trim()) return
    setPrompt(optimizeResult.trim())
    setOptimizeOpen(false)
    message.success('已应用优化后的提示词')
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
  const handleAddReferenceUrl = () => {
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
  }

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
    // ⚠️ 2026-10-07：主表单已**不再**提供批注 UI（批注只在「改图工作台」里），
    // 所以这里回到最朴素的判断——必须有提示词。
    //
    // 原来这里允许"没提示词、只有批注"就提交，因为主表单上就有批注画布。
    // 既然那块搬走了，`writtenAnnotations` 在经典表单下恒为空
    //（annotations 只在工作台模式下才可能被写入），保留那个分支只会让
    // 用户点生成后毫无反应（既没提示词、也没有批注可提交）。
    //
    // `toAnnotationPayload` / `writtenAnnotations` **保留**：工作台模式下
    // 它仍然是提交路径的一部分。
    const writtenAnnotations = toAnnotationPayload(annotations)
    if (!prompt.trim() && writtenAnnotations.length === 0) {
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
        // 图生图没有参考图就等于文生图，语义完全错了。编辑台默认就是图生图，
        // 用户很容易空着手点「开始生成」——这里拦下来并说清要做什么，而不是让后端
        // 当成文生图跑一趟（花钱且结果不对）。
        if (referenceImages.length === 0) {
          message.warning('图生图需要先放一张参考图：上传、粘贴链接，或从素材库选一张')
          return
        }
        if (referenceAssetIds.length > 0) {
          body.reference_asset_ids = referenceAssetIds
        }
        const manualImages = referenceImages.filter((f) => !(f as any).assetId)
        const manualImagePayloads: string[] = manualImages.length
          ? await Promise.all(
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
              }),
            )
          : []

        // 画面批注：只在「写好了意见」时提交。只框没写字的会被 toAnnotationPayload 滤掉，
        // 空数组则完全不发这个字段——后端收到空值时行为与接入前一致。
        // 复用上面已经算好的 writtenAnnotations，避免同一批数据算两遍（两处可能不一致）。
        if (writtenAnnotations.length > 0) {
          body.annotations = writtenAnnotations
          // 用户自定义 / 关闭的标注图说明。只有真正定义了才发这个字段——
          // `undefined` 走后端默认，`''` 表示明确不要这段。两者语义不同，不能互相兜底。
          if (annotationHintText !== undefined) {
            body.annotation_hint_text = annotationHintText
          }

          // 把框画到像素上，作为**追加的一张参考图**跟在原图后面。
          // 模型顺序即「参考 1 = 原图，参考 2 = 标了框的同一张图」，
          // 提示词里显式说明这两张的关系，避免模型把框线当成要保留的内容。
          if (annotationHintMode === 'marked' && annotationImage) {
            try {
              const marked = await renderAnnotatedImage(annotationImage, writtenAnnotations)
              if (marked) {
                // 注意顺序：后端 `merge_reference_images` 的合并次序是
                // 「显式 URL/base64 → 集合卡片 → 素材库 ID」。素材库选图走
                // `reference_asset_ids`，若标注图只塞进 reference_images，
                // 解析出的**原图反而会排在标注图后面**，与提示词里
                // 「第 2 张是带框图」的说法对不上。
              // 所以：素材库有图时把标注图放进集合卡片字段（排在 base64 之后、
              // asset 之前）；纯本地上传时才直接追加到 reference_images 末尾。
              if (referenceAssetIds.length > 0) {
                body.reference_image_collection = [
                  ...(body.reference_image_collection || []),
                  { url: marked },
                ]
              } else {
                body.reference_images = [...manualImagePayloads, marked]
              }
              body.annotation_marked_reference = true
              } else {
                message.info('带框标注图生成失败，已改用文字定位')
              }
            } catch (e: any) {
              // 跨域图片会因 canvas 污染导不出，退回纯文字而不是让整次提交失败。
              console.error('[ImageGen] 生成标注图失败:', e)
              message.info(`带框标注图不可用，已改用文字定位：${e?.message || e}`)
            }
          }
        }

        if (manualImagePayloads.length > 0 && !body.reference_images) {
          body.reference_images = manualImagePayloads
        }
      } else if (annotations.length > 0) {
        // 文生图没有参考图可圈，不静默吞掉用户的批注意图。
        message.warning('画面批注只用于图生图：切到图生图并添加参考图后才能标注')
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

  // 编辑工作台专用的模型下拉数据（沿用页面里既有的分组与过滤，不另起一套口径）
  const editorModelOptions = useMemo(() => {
    const vendorGroup = Object.values(groupedBackends).find(
      (g) => g.provider_label === provider,
    )
    return (vendorGroup?.backends || []).map((b) => ({
      label: b.name,
      value: b.name,
    }))
  }, [groupedBackends, provider])

  const editorSizeOptions = sizeOptions.length
    ? sizeOptions
    : [{ label: '默认', value: '1024x1024' }]

  // 生成结果卡片：表单模式放右栏、编辑台模式放工作台下方，两处共用同一份数据与操作，
  // 避免两套渲染逻辑各自漂移（曾经出现过一处图标缺失、另一处正常的分叉）。
  const resultsCard = (
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
        generatedImages.length > 0 ? (
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => setGeneratedImages([])}
          >
            清空
          </Button>
        ) : null
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
  )

  return (
    <div style={{ padding: 0 }}>
      {/* 编辑台模式：整块占满宽度，画布才能真正大起来；表单模式才用两栏 Row */}
      {workspace === 'editor' ? (
          <Col xs={24}>
            <ImageEditorWorkspace
              imageUrl={annotationImage}
              annotations={annotations}
              onAnnotationsChange={setAnnotations}
              activeId={activeAnnotationId}
              onActiveChange={setActiveAnnotationId}
              referenceImages={referenceImages}
              onReferenceImagesChange={(files) => {
                setReferenceImages(files)
                setReferenceAssetIds(
                  files.map((f) => (f as any).assetId).filter(Boolean),
                )
              }}
              onPickFromLibrary={() => setAssetPickerOpen(true)}
              referenceUrl={referenceUrl}
              onReferenceUrlChange={setReferenceUrl}
              onAddReferenceUrl={handleAddReferenceUrl}
              libraryPicker={
                <AssetReferencePicker
                  open={assetPickerOpen}
                  onClose={() => setAssetPickerOpen(false)}
                  onSelect={handleAssetPicked}
                />
              }
              provider={provider}
              providerOptions={vendorOptions}
              onProviderChange={handleProviderChange}
              selectedModel={selectedModel}
              modelOptions={editorModelOptions}
              onModelChange={(value) => {
                setSelectedModel(value)
                const vendorGroup = Object.values(groupedBackends).find(
                  (g) => g.provider_label === provider,
                )
                const target = vendorGroup?.backends.find((b) => b.name === value)
                if (target?.supported_sizes?.length) setSize(target.supported_sizes[0])
              }}
              size={size}
              sizeOptions={editorSizeOptions}
              onSizeChange={setSize}
              batchCount={batchCount}
              onBatchCountChange={setBatchCount}
              loading={loading}
              onGenerate={handleGenerate}
              onSwitchToClassic={() => setWorkspace('classic')}
              hintMode={annotationHintMode}
              onHintModeChange={setAnnotationHintMode}
              hintText={annotationHintText}
              onHintTextChange={setAnnotationHintText}
              prompt={prompt}
              onPromptChange={setPrompt}
              negativePrompt={negativePrompt}
              onNegativePromptChange={setNegativePrompt}
            />
          </Col>
        ) : (
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
            extra={
              // 只有图生图才进编辑台：文生图没有参考图，编辑台里没有可圈的画面。
              mode === 'img2img' ? (
                <Button size="small" icon={<EditOutlined />} onClick={() => setWorkspace('editor')}>
                  改图工作台
                </Button>
              ) : null
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
                  <Button size="small" icon={<ThunderboltOutlined />} onClick={openOptimize}>
                    AI 优化
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
                      onPressEnter={handleAddReferenceUrl}
                      style={{ background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                    />
                    <Button type="primary" onClick={handleAddReferenceUrl}>
                      添加 URL
                    </Button>
                  </Space.Compact>
                  <div style={{ marginTop: 6, fontSize: 12, color: '#8b8ba8' }}>
                    支持通过 URL 图生图：可从素材库选择图片，或手动输入图片地址（含素材库「来源 URL」）。最多 3 张。
                  </div>
                  {/* 已有参考图时才引导进编辑台：没图可圈时推荐过去只会让人撞上空画布。 */}
                  {referenceImages.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Button
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => setWorkspace('editor')}
                      >
                        打开改图工作台（圈选 + 批注）
                      </Button>
                      <div style={{ color: '#8b8ba8', fontSize: 12, marginTop: 4 }}>
                        想在图上圈出某处再改？进工作台，那里可以标注；本表单只填提示词。
                      </div>
                    </div>
                  )}
                </div>
                <AssetReferencePicker
                  open={assetPickerOpen}
                  onClose={() => setAssetPickerOpen(false)}
                  onSelect={handleAssetPicked}
                />

                {/* ⚠️ 这里**不再渲染批注 UI**（2026-10-07 用户要求）。
                    主表单恢复成**以前那种**图生图：填提示词 + 参考图，直接生成。

                    批注只在「打开改图工作台」那个页面里有
                    （workspace === 'editor' → <ImageEditorWorkspace>），
                    两种形态**分开**：主表单轻量、批注功能完整。

                    `annotations` state 与提交逻辑**保留不动** —— 工作台
                    圈出的批注仍要随生成一起提交，所以只删 UI，不删数据。
                */}
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
          {resultsCard}
        </Col>
      </Row>
      )}

      {/* 编辑台模式：结果排在工作台下方，而不是右侧——右侧已经被批注侧栏占了 */}
      {workspace === 'editor' && generatedImages.length > 0 && (
        <div style={{ marginTop: 16 }}>{resultsCard}</div>
      )}
      <PromptReferencePicker
        open={promptReferencePickerOpen}
        onCancel={() => setPromptReferencePickerOpen(false)}
        onApply={applyPromptReference}
      />

      <Modal
        title="AI 优化提示词"
        open={optimizeOpen}
        onCancel={() => !optimizing && setOptimizeOpen(false)}
        width={720}
        okText={optimizeResult ? '重新优化' : '开始优化'}
        confirmLoading={optimizing}
        onOk={runOptimize}
        cancelText="关闭"
        footer={[
          <Button key="close" onClick={() => setOptimizeOpen(false)} disabled={optimizing}>关闭</Button>,
          <Button key="run" type="default" loading={optimizing} onClick={runOptimize}>
            {optimizeResult ? '重新优化' : '开始优化'}
          </Button>,
          <Button key="apply" type="primary" disabled={!optimizeResult.trim()} onClick={applyOptimized}>
            应用到提示词
          </Button>,
        ]}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, opacity: 0.75 }}>修改描述（可选）</div>
            <TextArea
              rows={2}
              value={optimizeInstruction}
              onChange={e => setOptimizeInstruction(e.target.value)}
              placeholder="例如：改成雨天夜晚、用广角镜头、去掉文字元素、更偏胶片质感"
            />
          </div>
          <Space wrap>
            <Select
              placeholder="选择 LLM"
              style={{ width: 220 }}
              value={optimizeProvider || undefined}
              onChange={(value) => {
                setOptimizeProvider(value)
                const backend = llmBackends.find((item: any) => (item.name || item.provider) === value)
                setOptimizeModel(
                  backend?.default_model || backend?.model || backend?.available_models?.[0] || '',
                )
              }}
              options={llmBackends.map((item: any) => ({
                value: item.name || item.provider,
                label: item.provider_label || item.name || item.provider,
              }))}
            />
            <Select
              placeholder="选择模型"
              style={{ width: 240 }}
              value={optimizeModel || undefined}
              onChange={setOptimizeModel}
              options={(() => {
                const backend = llmBackends.find(
                  (item: any) => (item.name || item.provider) === optimizeProvider,
                )
                const models = Array.from(
                  new Set(
                    [
                      ...(backend?.available_models || []),
                      backend?.default_model,
                      backend?.model,
                    ].filter(Boolean),
                  ),
                )
                return models.map((model) => ({ value: model, label: model }))
              })()}
            />
          </Space>
          {optimizeResult ? (
            <div>
              <div style={{ marginBottom: 4, fontSize: 12, opacity: 0.75 }}>
                优化结果（可编辑后应用）
              </div>
              <TextArea
                rows={8}
                value={optimizeResult}
                onChange={e => setOptimizeResult(e.target.value)}
              />
            </div>
          ) : null}
        </Space>
      </Modal>
    </div>
  )
}
