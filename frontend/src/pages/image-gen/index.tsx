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

import { useState, useEffect, useRef, useMemo } from 'react'
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
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTheme } from '../../constants/theme'
import { getImageBackends, generateImage as generateImageApi, linkCreativeProjectAsset } from '../../api'
import MultiPlatformGen from './MultiPlatformGen'


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
  created_at: string
  local_path?: string
  asset_id?: string
  project_linked?: boolean
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

  // 参数
  const [provider, setProvider] = useState<string>()
  const [selectedModel, setSelectedModel] = useState<string>()  // 动态模型选择
  const [size, setSize] = useState('1024x1024')
  const [batchCount, setBatchCount] = useState(1)
  const [seed, setSeed] = useState<number>()

  // 状态
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)

  // 结果
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([])
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [defaultBackend, setDefaultBackend] = useState<string>()
  const [lastProjectLinkStatus, setLastProjectLinkStatus] = useState<'idle' | 'success' | 'error'>('idle')

  // 预览
  const [previewImage, setPreviewImage] = useState<GeneratedImage | null>(null)
  const hasFetchedBackends = useRef(false)
  const hasAppliedUrlParams = useRef(false)  // 标记是否已应用 URL 参数



  // 按厂商分组后端（根据 mode 过滤不支持的模型）
  const { groupedBackends, vendorOptions } = useMemo(() => {
    // 图生图模式：只保留支持 image_to_image 的后端
    const filteredBackends = mode === 'img2img'
      ? backends.filter(b => b.capabilities?.includes('image_to_image'))
      : backends

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
          label: ratio,
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
        b.name === modelParam || 
        b.model === modelParam || 
        b.available_models?.includes(modelParam)
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
  }, [backends, searchParams])

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
            const firstBackend = data.backends[0]
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

  // 生成图片
  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入提示词')
      return
    }

    setLoading(true)
    setProgress(10)

    try {
      const body: any = {
        prompt,
        negative_prompt: negativePrompt || undefined,
        size,
        provider: selectedModel,  // provider 传入部署配置名称 (name)
        n: batchCount,
        seed,
      }
      if (projectContext.hasContext) {
        body.project_id = projectContext.projectId
        body.content_id = projectContext.contentId || undefined
        body.source_type = projectContext.sourceType || undefined
        body.source_index = projectContext.sourceIndex || undefined
        body.source_title = projectContext.sourceTitle || undefined
        body.chapter_number = projectContext.chapterNumber || undefined
      }

      // 图生图模式：将图片转换为 base64 数据 URI
      if (mode === 'img2img' && referenceImages.length > 0) {
        body.reference_images = await Promise.all(
          referenceImages.map(async (f) => {
            if (f.originFileObj) {
              // blob -> base64
              return new Promise<string>((resolve, reject) => {
                const reader = new FileReader()
                reader.onload = () => resolve(reader.result as string)
                reader.onerror = reject
                reader.readAsDataURL(f.originFileObj!)
              })
            }
            // URL 形式的参考图（如从资产库跳转），需要 fetch 下载后转 base64
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

      setProgress(30)

      const data = await generateImageApi(body)

      setProgress(80)

      if (data.success) {
        let projectLinkOk = false
        const linkedAssetIds: string[] = []
        const newImages: GeneratedImage[] = []
        const urls = (data.urls && data.urls.length > 0) ? data.urls : (data.url ? [data.url] : [])
        const localPaths = (data.all_local_paths && data.all_local_paths.length > 0)
          ? data.all_local_paths
          : (data.local_path ? [data.local_path] : [])
        const assetIds = (data.all_asset_ids && data.all_asset_ids.length > 0)
          ? data.all_asset_ids
          : (data.asset_id ? [data.asset_id] : [])
        const resultCount = Math.max(urls.length, localPaths.length, assetIds.length)

        if (projectContext.hasContext && assetIds.length > 0) {
          try {
            for (let idx = 0; idx < assetIds.length; idx += 1) {
              const assetId = assetIds[idx]
              if (!assetId) continue
              await linkCreativeProjectAsset(projectContext.projectId, {
                asset_id: assetId,
                content_id: projectContext.contentId || undefined,
                role: projectContext.role,
                relation: projectContext.relation,
                metadata: {
                  source_type: projectContext.sourceType,
                  source_index: projectContext.sourceIndex,
                  source_title: projectContext.sourceTitle,
                  chapter_number: projectContext.chapterNumber,
                  prompt,
                  negative_prompt: negativePrompt || '',
                  provider: selectedModel || provider || '',
                  size,
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
            prompt,
            provider: data.provider || provider || 'unknown',
            model: selectedModel || data.model || '',
            local_path: localPaths[idx] || data.local_path,
            asset_id: assetIds[idx],
            project_linked: projectLinkOk && Boolean(assetIds[idx]) && linkedAssetIds.includes(assetIds[idx]),
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
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error('生成失败: ' + e.message)
    } finally {
      setLoading(false)
      setProgress(0)
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
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                提示词
              </div>
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
                  onChange={({ fileList }) => setReferenceImages(fileList)}
                  beforeUpload={() => false}
                  style={{ background: '#1e1e2e', border: '1px dashed #444' }}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined style={{ color: '#7c3aed' }} />
                  </p>
                  <p style={{ color: '#8b8ba8' }}>点击或拖拽上传参考图片</p>
                  <p style={{ color: '#8b8ba8', fontSize: 12 }}>支持 1-3 张参考图</p>
                </Dragger>
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
                    尺寸
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
              {loading ? '生成中...' : '开始生成'}
            </Button>

            {/* 进度条 */}
            {loading && (
              <Progress
                percent={progress}
                status="active"
                style={{ marginTop: 12 }}
                strokeColor={{ '0%': '#7c3aed', '100%': '#a855f7' }}
              />
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
    </div>
  )
}
