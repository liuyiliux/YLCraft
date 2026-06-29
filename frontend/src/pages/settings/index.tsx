import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Card,
  Tabs,
  Table,
  Button,
  Switch,
  Input,
  Modal,
  Form,
  Select,
  Tag,
  Typography,
  Space,
  Popconfirm,
  Alert,
  Skeleton,
  InputNumber,
  Badge,
  ConfigProvider,
  Tooltip,
  Row,
  Col,
  Divider,
  Collapse,
} from 'antd'
import { App as AntApp } from 'antd'
import {
  SettingOutlined,
  ApiOutlined,
  VideoCameraOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  PlusOutlined,
  EyeOutlined,
  EditOutlined,
  SearchOutlined,
  CopyOutlined,
  DeleteOutlined,
  QuestionCircleOutlined,
  UploadOutlined,
  DownloadOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import { listConnectors, createConnector, updateConnector, deleteConnector, testConnector, exportConnectors, importConnectors, discoverModels, getSettings, updateSettings, listProviders, createProvider, updateProvider, deleteProvider, initDefaultProviders, getProviderDefaults, listAICapabilities } from '../../api'
import type { Provider, PROVIDER_OPTIONS, ConnectorTestResult, ProviderMetadata } from '../../types/api'
import { useTheme } from '../../constants/theme'
import { calculateAspectRatio } from '../../utils/size'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// ==================== 可拖拽调整列宽的表头 ====================
function useResizableColumns(initialWidths: Record<string, number>) {
  const [colWidths, setColWidths] = useState<Record<string, number>>(initialWidths)
  const resizing = useRef<{ key: string; startX: number; startWidth: number } | null>(null)
  const moveRef = useRef<((e: MouseEvent) => void) | null>(null)
  const upRef = useRef<(() => void) | null>(null)

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!resizing.current) return
    const { key, startX, startWidth } = resizing.current
    const diff = e.clientX - startX
    const newWidth = Math.max(80, startWidth + diff)
    setColWidths(prev => ({ ...prev, [key]: newWidth }))
  }, [])

  const handleMouseUp = useCallback(() => {
    if (resizing.current) {
      document.removeEventListener('mousemove', moveRef.current!)
      document.removeEventListener('mouseup', upRef.current!)
      resizing.current = null
    }
  }, [])

  // 始终保持 ref 指向最新回调
  moveRef.current = handleMouseMove
  upRef.current = handleMouseUp

  const handleMouseDown = useCallback((key: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    resizing.current = { key, startX: e.clientX, startWidth: colWidths[key] || 0 }
    document.addEventListener('mousemove', moveRef.current!)
    document.addEventListener('mouseup', upRef.current!)
  }, [colWidths])

  // 给列定义添加 resize handle 的渲染器
  function wrapColumnTitle(title: string, key: string): React.ReactNode {
    return (
      <div style={{ display: 'flex', alignItems: 'center', width: '100%', position: 'relative' }}>
        <span style={{ flex: 1 }}>{title}</span>
        <div
          onMouseDown={(e) => handleMouseDown(key, e)}
          style={{
            width: 6,
            cursor: 'col-resize',
            position: 'absolute',
            right: -3,
            top: 0,
            bottom: 0,
            zIndex: 10,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderRight = '2px solid #00d4ff')}
          onMouseLeave={(e) => (e.currentTarget.style.borderRight = '2px solid transparent')}
        />
      </div>
    )
  }

  return { colWidths, wrapColumnTitle }
}

// 尺寸配置字段组件
function SizeConfigField({ value = [], onChange }: { value?: string[], onChange?: (v: string[]) => void }) {
  const { theme: THEME } = useTheme()
  
  const sizes = value || []
  
  const handleAdd = (type: 'size' | 'ratio') => {
    if (type === 'size') {
      onChange?.([...sizes, '1024x1024'])
    } else {
      onChange?.([...sizes, '1:1'])
    }
  }
  
  const handleChange = (index: number, newValue: string) => {
    const newSizes = [...sizes]
    newSizes[index] = newValue
    onChange?.(newSizes)
  }
  
  const handleDelete = (index: number) => {
    const newSizes = sizes.filter((_, i) => i !== index)
    onChange?.(newSizes)
  }
  
  const getDisplayLabel = (item: string) => {
    if (item.includes(':') && !item.match(/^\d+x\d+$/i)) {
      return item // 已经是比例格式
    }
    const ratio = calculateAspectRatio(item)
    return ratio ? `${item} (${ratio})` : item
  }
  
  return (
    <div style={{ border: '1px solid #333', borderRadius: 6, padding: 12, background: '#1a1a2e' }}>
      {sizes.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {sizes.map((item, index) => (
            <div key={index} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Tag color="purple">{getDisplayLabel(item)}</Tag>
              <Input
                size="small"
                value={item}
                onChange={e => handleChange(index, e.target.value)}
                style={{ flex: 1, background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                placeholder="如: 1024x1024 或 1:1"
              />
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(index)}
                style={{ color: '#ef4444' }}
              />
            </div>
          ))}
        </div>
      )}
      <Space>
        <Button size="small" icon={<PlusOutlined />} onClick={() => handleAdd('size')}>
          添加尺寸
        </Button>
        <Button size="small" icon={<PlusOutlined />} onClick={() => handleAdd('ratio')}>
          添加比例
        </Button>
      </Space>
    </div>
  )
}

const AI_TYPE_OPTIONS = [
  { value: 'llm', label: '文本 (LLM)' },
  { value: 'image', label: '图像生成' },
  { value: 'video', label: '视频生成' },
  { value: 'tts', label: '语音合成 (TTS)' },
  { value: 'stt', label: '语音识别 (STT)' },
  { value: 'embedding', label: '嵌入 (Embedding)' },
]

const AI_TYPE_HELP: Record<string, { title: string; description: string; focus: string; detail: string }> = {
  llm: {
    title: '文本 (LLM)',
    description: '用于聊天、提纲、规则修复、文案生成等文本推理能力。',
    focus: '主要配置 Base URL、API Key、默认模型、温度和最大 Token。',
    detail: 'OpenAI SDK 模式会由后端组装 Chat Completions 或 Responses API 请求，通常不需要写 Request 模板。',
  },
  image: {
    title: '图像生成',
    description: '用于文生图、图生图和多参考图生成。',
    focus: 'OpenAI SDK / Gemini SDK 适合对应的标准接口；通用 HTTP 模式需要配置 Request 模板和 Response 解析。',
    detail: 'Response 解析使用 JSONPath：URL 通常填 images_path，base64 通常填 base64_images_path；OpenAI SDK 图片接口如需强制 base64 返回，可在默认参数里加 {"response_format":"b64_json"}。',
  },
  video: {
    title: '视频生成',
    description: '用于文生视频、图生视频和生成任务提交类接口。',
    focus: '通常需要确认接口是同步返回结果，还是先返回 task_id 再轮询。',
    detail: '通用 HTTP 模式适合接入非标准视频平台；尺寸/比例和首帧字段建议按平台文档单独配置。',
  },
  tts: {
    title: '语音合成 (TTS)',
    description: '用于把文本生成语音或旁白音频。',
    focus: '主要配置默认模型、音色、语速、输出格式等参数。',
    detail: '如果平台兼容 OpenAI 音频接口，优先用 SDK；非标准接口再走通用 HTTP。',
  },
  stt: {
    title: '语音识别 (STT)',
    description: '用于把音频或视频里的声音转成文字。',
    focus: '主要关注模型、语言、时间戳和文件上传方式。',
    detail: '后续字幕识别会优先读取此类可用模型。',
  },
  embedding: {
    title: '嵌入 (Embedding)',
    description: '用于把文本、图片或多模态内容转为向量。',
    focus: '主要配置默认模型和向量维度，维度要和索引/数据库里保存的一致。',
    detail: '配置完成后可用于素材入库、相似搜索和混合搜索。',
  },
}

function TypeHelpBlock({ type, theme, compact = false }: { type?: string; theme: any; compact?: boolean }) {
  if (!type) return null
  const help = AI_TYPE_HELP[type]
  if (!help) return null

  return (
    <Alert
      type="info"
      showIcon
      message={`${help.title} 配置说明`}
      description={
        <div style={{ color: theme.textSecondary, lineHeight: 1.7 }}>
          <div>{help.description}</div>
          <div>{help.focus}</div>
          {!compact && <div>{help.detail}</div>}
        </div>
      }
      style={{
        marginBottom: 16,
        background: 'rgba(0,212,255,0.05)',
        border: '1px solid rgba(0,212,255,0.2)',
      }}
    />
  )
}

function getApiFormatHelp(apiFormat?: string, type?: string) {
  if (apiFormat === 'openai_sdk') {
    return type === 'image'
      ? '适合 OpenAI 兼容的图片生成接口，后端直接用 SDK 调用 images.generate，不需要填写 Request 模板和 Response 解析；如需强制 base64 返回，在默认参数加 {"response_format":"b64_json"}。'
      : '适合 OpenAI 兼容的聊天接口，后端直接用 SDK 调用 Chat Completions。'
  }
  if (apiFormat === 'openai_sdk_responses') {
    return '适合支持 Responses API 的服务。只有目标平台明确兼容时再选这个模式。'
  }
  if (apiFormat === 'gemini_sdk') {
    return '适合 Gemini 原生图片生成接口，后端会用 google-genai SDK 处理 inlineData/base64 图片结果。'
  }
  if (apiFormat === 'custom') {
    return type === 'image'
      ? '通用 HTTP 模式会按 Request 模板发请求，并用 Response 解析配置里的 JSONPath 提取图片 URL 或 base64。'
      : '通用 HTTP 模式会按你填写的模板和字段映射请求非标准接口，适合不兼容 SDK 的平台。'
  }
  return ''
}

// ==================== Provider 管理组件 ====================

interface ProviderCardProps {
  provider: ProviderMetadata
  onEdit: (provider: ProviderMetadata) => void
  onDelete: (providerId: string) => void
  onToggleActive: (providerId: string, active: boolean) => void
  theme: any
}

const ProviderCard: React.FC<ProviderCardProps> = ({ provider, onEdit, onDelete, onToggleActive, theme }) => {
  const typeLabels: Record<string, string> = {
    llm: '文本',
    image: '图像',
    video: '视频',
    tts: '语音',
    stt: '识别',
    embedding: '嵌入',
  }

  return (
    <Card
      size="small"
      style={{
        background: theme.bgCard,
        border: `1px solid ${provider.is_active ? provider.color + '40' : theme.border}`,
        borderRadius: 12,
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        {/* Logo 区域 */}
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 10,
            background: `linear-gradient(135deg, ${provider.color}30, ${provider.color}10)`,
            border: `1px solid ${provider.color}40`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            flexShrink: 0,
          }}
        >
          {provider.icon === 'brain' && '🧠'}
          {provider.icon === 'cloud' && '☁️'}
          {provider.icon === 'globe' && '🌐'}
          {provider.icon === 'settings' && '⚙️'}
        </div>

        {/* 信息区域 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>{provider.name}</Text>
            {!provider.is_active && (
              <Tag color="default" style={{ marginLeft: 4 }}>已禁用</Tag>
            )}
            {provider.has_api_key && (
              <Tag color="green" style={{ fontSize: 10 }}>已配置 Key</Tag>
            )}
          </div>

          <Text style={{ color: theme.textSecondary, fontSize: 12, display: 'block', marginBottom: 8 }}>
            {provider.description || provider.base_url || '无描述'}
          </Text>

          {/* 支持的类型 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
            {provider.supported_types?.map(type => (
              <Tag
                key={type}
                color={provider.color}
                style={{
                  borderRadius: 4,
                  fontSize: 11,
                  padding: '0 6px',
                  margin: 0,
                  background: provider.color + '15',
                  border: `1px solid ${provider.color}30`,
                }}
              >
                {typeLabels[type] || type}
              </Tag>
            ))}
          </div>

          {/* 默认模型信息 */}
          {Object.keys(provider.default_models || {}).length > 0 && (
            <div style={{ fontSize: 11, color: theme.textSecondary }}>
              {Object.entries(provider.default_models).map(([type, model]) => (
                <div key={type} style={{ marginBottom: 2 }}>
                  <span style={{ color: provider.color }}>{typeLabels[type] || type}:</span>{' '}
                  <Text code style={{ fontSize: 10 }}>{model}</Text>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flexShrink: 0 }}>
          <Switch
            size="small"
            checked={provider.is_active}
            onChange={(checked) => onToggleActive(provider.provider_id, checked)}
            disabled={!provider.is_editable}
          />
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(provider)}
            disabled={!provider.is_editable}
            style={{ color: provider.is_editable ? theme.primary : theme.textDisabled }}
          />
          <Popconfirm
            title="确定要删除这个 Provider 吗？"
            description="删除后，用户新增该 Provider 的模型时将无法继承默认配置"
            onConfirm={() => onDelete(provider.provider_id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            disabled={!provider.is_editable}
          >
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              danger
              disabled={!provider.is_editable}
            />
          </Popconfirm>
        </div>
      </div>
    </Card>
  )
}

interface ProviderFormModalProps {
  open: boolean
  provider?: ProviderMetadata | null
  onCancel: () => void
  onSave: (data: any) => void
  theme: any
}

const ProviderFormModal: React.FC<ProviderFormModalProps> = ({ open, provider, onCancel, onSave, theme }) => {
  const [form] = Form.useForm()
  const { message } = AntApp.useApp()
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('llm')
  
  const typeOptions = AI_TYPE_OPTIONS
  
  const supportedTypes = Form.useWatch(['supported_types'], form) || []

  useEffect(() => {
    if (open) {
      if (provider) {
        // 解析 JSON 字符串为对象
        const parseJson = (val: any) => {
          if (typeof val === 'string') {
            try { return JSON.parse(val) } catch { return {} }
          }
          return val || {}
        }

        const parseJsonArray = (val: any) => {
          if (typeof val === 'string') {
            try { return JSON.parse(val) } catch { return [] }
          }
          return val || []
        }
        
        // 设置各类型的配置
        const defaultParams = parseJson(provider.default_params)
        const defaultModels = parseJson(provider.default_models)
        const requestTemplates = parseJson(provider.request_templates)
        const responseConfigs = parseJson(provider.response_configs)
        const supportedSizes = parseJson(provider.supported_sizes)
        const refImageConfigs = parseJson(provider.reference_image_configs)
        const parameterTransforms = parseJson(provider.parameter_transforms)
        const supportedTypes = parseJsonArray(provider.supported_types)
        
        form.setFieldsValue({
          provider_id: provider.provider_id,
          name: provider.name,
          icon: provider.icon,
          color: provider.color,
          description: provider.description,
          base_url: provider.base_url,
          api_key: provider.api_key || '',
          api_format: provider.api_format,
          supported_types: supportedTypes,
        })
        
        typeOptions.forEach(({ value: type }) => {
          const params = defaultParams[type as keyof typeof defaultParams]
          const model = defaultModels[type as keyof typeof defaultModels]
          const template = requestTemplates[type as keyof typeof requestTemplates]
          const responseConfig = responseConfigs[type as keyof typeof responseConfigs]
          const sizes = supportedSizes[type as keyof typeof supportedSizes]
          const refImage = refImageConfigs[type as keyof typeof refImageConfigs]
          const transforms = parameterTransforms[type as keyof typeof parameterTransforms]
          
          if (params) {
            form.setFieldValue(`type_${type}_params`, JSON.stringify(params, null, 2))
          }
          
          if (model) {
            form.setFieldValue(`type_${type}_model`, model)
          }
          
          if (template) {
            form.setFieldValue(`type_${type}_template`, template)
          }
          
          if (responseConfig) {
            form.setFieldValue(`type_${type}_response_config`, JSON.stringify(responseConfig, null, 2))
          }
          
          if (sizes) {
            form.setFieldValue(`type_${type}_sizes`, Array.isArray(sizes) ? sizes.join(', ') : sizes)
          }
          
          if (refImage) {
            form.setFieldValue(`type_${type}_support_ref_image`, refImage.support_reference_image || false)
            form.setFieldValue(`type_${type}_support_multi_ref`, refImage.support_multiple_reference_images || false)
            form.setFieldValue(`type_${type}_ref_image_field`, refImage.reference_image_field || '')
            form.setFieldValue(`type_${type}_ref_image_array_field`, refImage.reference_image_array_field || '')
          }
          
          if (transforms) {
            form.setFieldValue(`type_${type}_transforms`, JSON.stringify(transforms, null, 2))
          }
        })
        
        if (supportedTypes.length > 0) {
          setActiveTab(supportedTypes[0])
        }
      } else {
        form.resetFields()
        form.setFieldsValue({
          provider_id: '',
          icon: 'settings',
          color: '#94a3b8',
          api_format: 'openai-compatible',
          supported_types: ['llm'],
        })
      }
    }
  }, [open, provider, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      
      // 处理各类型的配置
      const defaultParams: Record<string, any> = {}
      const defaultModels: Record<string, string> = {}
      const requestTemplates: Record<string, string> = {}
      const responseConfigs: Record<string, any> = {}
      const supportedSizes: Record<string, any> = {}
      const referenceImageConfigs: Record<string, any> = {}
      const parameterTransforms: Record<string, any> = {}
      
      typeOptions.forEach(({ value: type }) => {
        const params = values[`type_${type}_params`]
        const model = values[`type_${type}_model`]
        const template = values[`type_${type}_template`]
        const responseConfig = values[`type_${type}_response_config`]
        const sizes = values[`type_${type}_sizes`]
        const supportRefImage = values[`type_${type}_support_ref_image`]
        const supportMultiRef = values[`type_${type}_support_multi_ref`]
        const refImageField = values[`type_${type}_ref_image_field`]
        const refImageArrayField = values[`type_${type}_ref_image_array_field`]
        const transforms = values[`type_${type}_transforms`]
        
        if (params) {
          try {
            defaultParams[type] = JSON.parse(params)
          } catch (e) {
            // 忽略解析错误
          }
        }
        
        if (model) {
          defaultModels[type] = model
        }
        
        if (template) {
          requestTemplates[type] = template
        }
        
        if (responseConfig) {
          try {
            responseConfigs[type] = JSON.parse(responseConfig)
          } catch (e) {
            // 忽略解析错误
          }
        }
        
        if (sizes) {
          const sizesArray = sizes.split(',').map(s => s.trim()).filter(Boolean)
          if (sizesArray.length > 0) {
            supportedSizes[type] = sizesArray.length > 1 ? sizesArray : sizes
          }
        }
        
        if (supportRefImage || supportMultiRef || refImageField || refImageArrayField) {
          referenceImageConfigs[type] = {
            support_reference_image: supportRefImage || false,
            support_multiple_reference_images: supportMultiRef || false,
            reference_image_field: refImageField || '',
            reference_image_array_field: refImageArrayField || '',
          }
        }
        
        if (transforms) {
          try {
            parameterTransforms[type] = JSON.parse(transforms)
          } catch (e) {
            // 忽略解析错误
          }
        }
      })

      // 处理数据 - 只发送必要的字段，不包含临时字段
      const data = {
        provider_id: values.provider_id,
        name: values.name,
        icon: values.icon,
        color: values.color,
        description: values.description,
        base_url: values.base_url,
        api_key: values.api_key,
        api_format: values.api_format,
        supported_types: values.supported_types,
        default_params: defaultParams,
        default_models: defaultModels,
        request_templates: requestTemplates,
        response_configs: responseConfigs,
        supported_sizes: supportedSizes,
        reference_image_configs: referenceImageConfigs,
        parameter_transforms: parameterTransforms,
      }

      onSave(data)
    } catch (e: any) {
      if (e.errorFields) {
        message.error('请检查表单填写')
      } else {
        message.error(e.message || '保存失败')
      }
    } finally {
      setSaving(false)
    }
  }

  const iconOptions = [
    { value: 'brain', label: '🧠 Brain' },
    { value: 'cloud', label: '☁️ Cloud' },
    { value: 'globe', label: '🌐 Globe' },
    { value: 'settings', label: '⚙️ Settings' },
  ]

  const apiFormatOptions = [
    { value: 'openai-compatible', label: 'OpenAI 兼容 API' },
    { value: 'custom', label: '自定义格式' },
    { value: 'gemini', label: 'Google Gemini' },
  ]

  return (
    <Modal
      title={provider ? '编辑 Provider' : '新增 Provider'}
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      confirmLoading={saving}
      width={800}
      styles={{ body: { padding: '16px 24px' } }}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
          <Form.Item
            name="provider_id"
            label="英文标识"
            rules={[
              { required: !provider, message: '请输入英文标识' },
              { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅支持英文、数字、下划线和短横线' },
            ]}
            extra="模型配置里的“底层服务商”保存的就是这个值，如 modelscope、qwen。创建后不建议修改。"
          >
            <Input placeholder="如：modelscope" disabled={!!provider} />
          </Form.Item>

          <Form.Item
            name="name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="如：OpenAI" />
          </Form.Item>

          <Form.Item
            name="icon"
            label="图标"
          >
            <Select options={iconOptions} />
          </Form.Item>

          <Form.Item
            name="color"
            label="品牌颜色"
          >
            <Input type="color" style={{ width: '100%', height: 32 }} />
          </Form.Item>

          <Form.Item
            name="api_format"
            label="API 格式"
          >
            <Select options={apiFormatOptions} />
          </Form.Item>
        </div>

        <Form.Item name="description" label="描述">
          <Input.TextArea placeholder="描述这个 Provider" rows={2} />
        </Form.Item>

        <Form.Item name="base_url" label="默认 Base URL">
          <Input placeholder="https://api.openai.com/v1" />
        </Form.Item>

        <Form.Item name="api_key" label="默认 API Key">
          <Input.Password placeholder="可选，用于继承到新建的模型" />
        </Form.Item>

        <Form.Item name="supported_types" label="支持的类型">
          <Select
            mode="multiple"
            placeholder="选择支持的 AI 类型"
            options={typeOptions}
          />
        </Form.Item>
        {supportedTypes.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <Text style={{ color: theme.textSecondary, fontSize: 12 }}>
              下面每个标签页只配置对应类型的默认值；新增模型时可按“底层服务商 + 类型”继承这些默认配置。
            </Text>
          </div>
        )}
        
        {/* 按类型分别配置的标签页 */}
        {supportedTypes.length > 0 && (
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            destroyOnHidden={false}
            style={{ marginBottom: 16 }}
            items={supportedTypes.map((type: string) => {
              const typeOption = typeOptions.find(t => t.value === type)
              return {
                key: type,
                label: typeOption?.label || type,
                // 关键：把每个类型的表单内容放到 children 里
                // destroyInactiveTabPane=false 时 Ant Design 不会销毁非激活 tab 的 DOM
                // 这样 Form.Item 始终挂载，validateFields() 能收集到所有字段值
                children: (
                  <div style={{ marginTop: 16, padding: '16px', background: theme.bgSecondary, borderRadius: 8, marginBottom: 16 }}>
                    <TypeHelpBlock type={type} theme={theme} />
                    <div style={{ fontWeight: 600, marginBottom: 16, color: theme.textPrimary }}>
                      {typeOption?.label || type} 配置
                    </div>

                    <Form.Item
                      name={`type_${type}_model`}
                      label="默认模型"
                      extra={`${typeOption?.label || type} 类型的默认模型`}
                    >
                      <Input placeholder="如：gpt-4o" />
                    </Form.Item>

                    <Form.Item
                      name={`type_${type}_params`}
                      label="默认参数 (JSON)"
                      extra={
                        type === 'image'
                          ? '图像类型的默认请求参数；OpenAI SDK 图片接口如需强制 base64 返回，可加 {"response_format":"b64_json"}。'
                          : `${typeOption?.label || type} 类型的默认请求参数`
                      }
                    >
                      <Input.TextArea
                        placeholder={type === 'llm' 
                          ? '{"temperature": 0.7, "max_tokens": 4096}'
                          : type === 'image'
                          ? '{"n": 1, "size": "1024x1024", "response_format": "b64_json"}'
                          : type === 'tts'
                          ? '{"voice": "alloy", "speed": 1.0}'
                          : '{}'
                        }
                        rows={4}
                        style={{ fontFamily: 'monospace', fontSize: 12 }}
                      />
                    </Form.Item>

                    {/* 请求模板 - 主要用于 image 类型 */}
                    {type === 'image' && (
                      <Form.Item
                        name={`type_${type}_template`}
                        label="请求模板 (Jinja2)"
                        extra="用于构建 API 请求体的模板，支持 {{ model }}, {{ prompt }}, {{ size }} 等变量"
                      >
                        <Input.TextArea
                          placeholder={`{\n  "model": "{{ model }}",\n  "prompt": "{{ prompt }}",\n  "size": "{{ size }}"\n}`}
                          rows={6}
                          style={{ fontFamily: 'monospace', fontSize: 12 }}
                        />
                      </Form.Item>
                    )}

                    {/* 响应配置 - 主要用于 image 类型 */}
                    {type === 'image' && (
                      <Form.Item
                        name={`type_${type}_response_config`}
                        label="响应配置 (JSON)"
                        extra='使用 JSONPath 提取结果：URL 用 images_path，base64 用 base64_images_path；error_path 用于提取错误信息。'
                      >
                        <Input.TextArea
                          placeholder={`{\n  "images_path": "$.data[*].url",\n  "base64_images_path": "$.data[*].b64_json",\n  "error_path": "$.error.message",\n  "usage_path": "$.usage",\n  "response_format": "url"\n}`}
                          rows={6}
                          style={{ fontFamily: 'monospace', fontSize: 12 }}
                        />
                      </Form.Item>
                    )}

                    {/* 支持尺寸 - 主要用于 image/video 类型 */}
                    {(type === 'image' || type === 'video') && (
                      <Form.Item
                        name={`type_${type}_sizes`}
                        label="支持的尺寸"
                        extra="多个尺寸用逗号分隔，如: 1024x1024, 1024x1792, 1792x1024"
                      >
                        <Input placeholder="1024x1024, 1024x1792, 1792x1024" />
                      </Form.Item>
                    )}

                    {/* 参考图配置 - 主要用于 image 类型 */}
                    {type === 'image' && (
                      <>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                          <Form.Item
                            name={`type_${type}_support_ref_image`}
                            label="支持参考图"
                            valuePropName="checked"
                          >
                            <Switch />
                          </Form.Item>
                          <Form.Item
                            name={`type_${type}_support_multi_ref`}
                            label="支持多张参考图"
                            valuePropName="checked"
                          >
                            <Switch />
                          </Form.Item>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
                          <Form.Item
                            name={`type_${type}_ref_image_field`}
                            label="参考图片段名"
                          >
                            <Input placeholder="如：image" />
                          </Form.Item>
                          <Form.Item
                            name={`type_${type}_ref_image_array_field`}
                            label="参考图数组字段"
                          >
                            <Input placeholder="如：image_urls" />
                          </Form.Item>
                        </div>
                      </>
                    )}

                    {/* 参数转换 - 主要用于 image 类型 */}
                    {type === 'image' && (
                      <Form.Item
                        name={`type_${type}_transforms`}
                        label="参数转换 (JSON)"
                        extra='参数值的转换规则，如 {"size": "{{ size.replace("x", "*") }}"}'
                      >
                        <Input.TextArea
                          placeholder='{"size": "{{ size.replace("x", "*") }}"}'
                          rows={3}
                          style={{ fontFamily: 'monospace', fontSize: 12 }}
                        />
                      </Form.Item>
                    )}
                  </div>
                ),
              }
            })}
          />
        )}
      </Form>
    </Modal>
  )
}

// Provider 管理面板
const ProviderManagement: React.FC = () => {
  const { theme: THEME } = useTheme()
  const { message } = AntApp.useApp()
  const [providers, setProviders] = useState<ProviderMetadata[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingProvider, setEditingProvider] = useState<ProviderMetadata | null>(null)

  const loadProviders = async () => {
    setLoading(true)
    try {
      const result = await listProviders() as any
      setProviders(result.providers || [])
    } catch {
      message.error('加载 Provider 失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProviders()
  }, [])

  const handleEdit = (provider: ProviderMetadata) => {
    setEditingProvider(provider)
    setModalVisible(true)
  }

  const handleDelete = async (providerId: string) => {
    try {
      await deleteProvider(providerId)
      message.success('删除成功')
      loadProviders()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const handleToggleActive = async (providerId: string, active: boolean) => {
    try {
      await updateProvider(providerId, { is_active: active })
      message.success(active ? '已启用' : '已禁用')
      loadProviders()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    }
  }

  const handleSave = async (data: any) => {
    try {
      if (editingProvider) {
        await updateProvider(editingProvider.provider_id, data)
        message.success('更新成功')
      } else {
        await createProvider({
          provider_id: data.name.toLowerCase().replace(/\s+/g, '-'),
          ...data,
        })
        message.success('创建成功')
      }
      setModalVisible(false)
      loadProviders()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    }
  }

  const handleInitDefaults = async () => {
    try {
      const result = await initDefaultProviders() as any
      message.success(result.message || '初始化完成')
      loadProviders()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '初始化失败')
    }
  }

  return (
    <div>
      {/* 头部操作栏 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 16,
        flexWrap: 'wrap',
        gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Text strong style={{ color: THEME.textPrimary, fontSize: 15 }}>
            AI 服务商配置
          </Text>
          <Badge count={providers.length} style={{ backgroundColor: THEME.primary }} />
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadProviders} loading={loading} size="small">
            刷新
          </Button>
          <Button icon={<SettingOutlined />} onClick={handleInitDefaults} size="small">
            初始化默认
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => { setEditingProvider(null); setModalVisible(true) }}
            size="small"
          >
            新增 Provider
          </Button>
        </Space>
      </div>

      {/* 说明卡片 */}
      <Alert
        type="info"
        showIcon
        message="Provider 管理"
        description="Provider 定义了 AI 服务商的默认配置（URL、API Key、默认参数等）。用户创建模型时可以选择继承 Provider 的默认配置，也可以自定义覆盖。"
        style={{ marginBottom: 16, background: 'rgba(0,212,255,0.05)', border: `1px solid rgba(0,212,255,0.2)` }}
      />

      {/* Provider 列表 */}
      {loading ? (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {[1, 2, 3].map(i => (
            <Card key={i} size="small" style={{ width: 340, background: THEME.bgCard }}>
              <Skeleton active paragraph={{ rows: 3 }} />
            </Card>
          ))}
        </div>
      ) : providers.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Text style={{ color: THEME.textSecondary }}>暂无 Provider 配置</Text>
          <div style={{ marginTop: 12 }}>
            <Button type="primary" icon={<SettingOutlined />} onClick={handleInitDefaults}>
              初始化默认 Provider
            </Button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {providers.map(provider => (
            <ProviderCard
              key={provider.provider_id}
              provider={provider}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onToggleActive={handleToggleActive}
              theme={THEME}
            />
          ))}
        </div>
      )}

      {/* 编辑/新增 Modal */}
      <ProviderFormModal
        open={modalVisible}
        provider={editingProvider}
        onCancel={() => setModalVisible(false)}
        onSave={handleSave}
        theme={THEME}
      />
    </div>
  )
}

// 服务商预设配置（按 provider_type 区分）
interface ProviderPreset {
  base_url?: string
  api_endpoint?: string
  default_model?: string
  available_models?: string[]
  max_tokens?: number
  temperature?: number
  request_template?: string
  response_config?: string
  default_params?: Record<string, any>
  supported_sizes?: string[]
  support_reference_image?: boolean
  support_multiple_reference_images?: boolean
  reference_image_field?: string
  reference_image_array_field?: string
  support_vision_input?: boolean
}

const MODELSCOPE_ASYNC_CONFIG = {
  request_headers: {
    'X-ModelScope-Async-Mode': 'true',
  },
  task_id_path: '$.task_id',
  poll_endpoint: '/v1/tasks/{task_id}',
  poll_method: 'GET',
  poll_headers: {
    'X-ModelScope-Task-Type': 'image_generation',
  },
  status_path: '$.task_status',
  done_value: 'SUCCEED',
  failed_value: 'FAILED',
  images_path: '$.output_images[*]',
  error_path: '$.message',
  poll_interval: 5,
  max_wait: 300,
}

function parseJsonObject(value: any): Record<string, any> {
  if (!value) return {}
  if (typeof value === 'object' && !Array.isArray(value)) return value
  if (typeof value !== 'string') return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function stringifyJson(value: any): string {
  return JSON.stringify(value || {}, null, 2)
}

function asyncConfigToFields(responseConfig: any): Record<string, any> {
  const config = parseJsonObject(responseConfig)
  const asyncConfig = parseJsonObject(config.async_config)
  if (!Object.keys(asyncConfig).length) {
    return {
      async_enabled: false,
      async_request_headers: stringifyJson({}),
      async_poll_headers: stringifyJson({}),
    }
  }

  return {
    async_enabled: true,
    async_request_headers: stringifyJson(asyncConfig.request_headers || {}),
    async_task_id_path: asyncConfig.task_id_path || '$.task_id',
    async_poll_endpoint: asyncConfig.poll_endpoint || '',
    async_poll_method: asyncConfig.poll_method || 'GET',
    async_poll_headers: stringifyJson(asyncConfig.poll_headers || {}),
    async_status_path: asyncConfig.status_path || '',
    async_done_value: asyncConfig.done_value || 'SUCCEED',
    async_failed_value: asyncConfig.failed_value || 'FAILED',
    async_images_path: asyncConfig.images_path || '',
    async_error_path: asyncConfig.error_path || '',
    async_poll_interval: asyncConfig.poll_interval ?? 5,
    async_max_wait: asyncConfig.max_wait ?? 300,
  }
}

function buildResponseConfigWithAsync(values: any): string {
  const responseConfig = parseJsonObject(values.response_config)
  if (!values.async_enabled) {
    delete responseConfig.async_config
    return stringifyJson(responseConfig)
  }

  responseConfig.async_config = {
    request_headers: parseJsonObject(values.async_request_headers),
    task_id_path: values.async_task_id_path || '$.task_id',
    poll_endpoint: values.async_poll_endpoint || '',
    poll_method: values.async_poll_method || 'GET',
    poll_headers: parseJsonObject(values.async_poll_headers),
    status_path: values.async_status_path || '',
    done_value: values.async_done_value || 'SUCCEED',
    failed_value: values.async_failed_value || 'FAILED',
    images_path: values.async_images_path || '',
    error_path: values.async_error_path || '',
    poll_interval: values.async_poll_interval ?? 5,
    max_wait: values.async_max_wait ?? 300,
  }
  return stringifyJson(responseConfig)
}

const ASYNC_FORM_FIELDS = [
  'async_enabled',
  'async_request_headers',
  'async_task_id_path',
  'async_poll_endpoint',
  'async_poll_method',
  'async_poll_headers',
  'async_status_path',
  'async_done_value',
  'async_failed_value',
  'async_images_path',
  'async_error_path',
  'async_poll_interval',
  'async_max_wait',
]

const PROVIDER_PRESETS: Record<string, Record<string, ProviderPreset>> = {
  openai: {
    llm: {
      base_url: 'https://api.openai.com/v1',
      default_model: 'gpt-4o',
      available_models: ['gpt-4o', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
      max_tokens: 4096,
      temperature: 0.7,
      support_vision_input: true,
    },
    image: {
      base_url: 'https://api.openai.com/v1',
      api_endpoint: '/images/generations',
      default_model: 'dall-e-3',
      available_models: ['dall-e-3', 'dall-e-2'],
      supported_sizes: ['1024x1024', '1792x1024', '1024x1792'],
      request_template: '{"model": "{{ model }}", "prompt": "{{ prompt }}", "n": {{ n | default(1) }}, "size": "{{ size }}"}',
      response_config: '{"images_path": "$.data[*].url", "error_path": "$.error.message"}',
      default_params: { n: 1, quality: 'standard' },
    },
  },
  siliconflow: {
    llm: {
      base_url: 'https://api.siliconflow.cn/v1',
      default_model: 'Qwen/Qwen2.5-72B-Instruct',
      available_models: ['Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2-VL-72B-Instruct'],
      max_tokens: 8192,
      temperature: 0.7,
      support_vision_input: true,
    },
    image: {
      base_url: 'https://api.siliconflow.cn/v1',
      api_endpoint: '/images/generations',
      default_model: 'stabilityai/stable-diffusion-3.5-large',
      available_models: ['stabilityai/stable-diffusion-3.5-large', 'runwayml/stable-diffusion-v1-5'],
      supported_sizes: ['1024x1024', '768x1344', '1344x768'],
      request_template: '{"model": "{{ model }}", "prompt": "{{ prompt }}", "image_size": "{{ size }}", "n": {{ n | default(1) }}, "seed": {{ seed | default(-1) }}}',
      response_config: '{"images_path": "$.data[*].url", "error_path": "$.error.message"}',
      default_params: { n: 1, size_param: 'image_size', seed_param: 'seed' },
      support_reference_image: true,
      reference_image_field: 'image',
    },
  },
  modelscope: {
    image: {
      base_url: 'https://api-inference.modelscope.cn',
      api_endpoint: '/v1/images/generations',
      default_model: 'Qwen/Qwen-Image',
      available_models: ['Qwen/Qwen-Image'],
      supported_sizes: ['1024x1024'],
      request_template: '{"model": "{{ model }}", "prompt": "{{ prompt }}"}',
      response_config: stringifyJson({ async_config: MODELSCOPE_ASYNC_CONFIG }),
      default_params: { n: 1 },
    },
  },
  gemini: {
    llm: {
      base_url: 'https://generativelanguage.googleapis.com/v1beta',
      default_model: 'gemini-2.0-flash',
      available_models: ['gemini-2.0-flash', 'gemini-2.0-pro', 'gemini-1.5-flash', 'gemini-1.5-pro'],
      max_tokens: 8192,
      temperature: 0.7,
      support_vision_input: true,
    },
    image: {
      base_url: 'https://generativelanguage.googleapis.com/v1beta',
      default_model: 'gemini-2.5-flash-image',
      available_models: ['gemini-2.5-flash-image'],
      supported_sizes: ['1024x1024'],
      support_reference_image: true,
      support_multiple_reference_images: true,
    },
  },
  generic: {
    llm: {},
    image: {},
    video: {},
    tts: {},
    stt: {},
    embedding: {},
  },
}

// Provider 下拉选项（简化版：全部使用 OpenAI 兼容 API）
const PROVIDER_SELECT_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'siliconflow', label: '硅基流动 (SiliconFlow)' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'generic', label: '通用配置 (Generic)' },
]

// Provider 颜色映射
const PROVIDER_COLORS: Record<string, string> = {
  'openai': '#10a37f',
  'siliconflow': '#00d4aa',
  'gemini': '#4285f4',
  'generic': '#94a3b8',
}

const TYPE_COLORS: Record<string, string> = {
  llm: '#00d4ff',
  image: '#a855f7',
  audio: '#f59e0b',
  video: '#ef4444',
  stt: '#10b981',
}

const TYPE_LABELS: Record<string, string> = {
  llm: '文本',
  image: '图像',
  audio: '语音',
  video: '视频',
  stt: '识别',
  tts: '语音',
  embedding: '嵌入',
}

interface AICapability {
  id: string
  name: string
  provider: string
  provider_label: string
  type: string
  model: string
  available_models: string[]
  base_url?: string
  api_endpoint?: string
  api_format?: string
  has_api_key: boolean
  is_default: boolean
  priority: number
  status: string
  status_message: string
  capabilities: string[]
  supported_sizes: string[]
  support_reference_image: boolean
  support_multiple_reference_images: boolean
  support_vision_input: boolean
}

const CAPABILITY_STATUS: Record<string, { color: string; text: string }> = {
  available: { color: 'success', text: '可用' },
  disabled: { color: 'default', text: '已禁用' },
  missing_key: { color: 'warning', text: '缺少 Key' },
  missing_model: { color: 'error', text: '缺少模型' },
}

function AICapabilityPanel() {
  const { theme: THEME } = useTheme()
  const { message } = AntApp.useApp()
  const [items, setItems] = useState<AICapability[]>([])
  const [loading, setLoading] = useState(false)
  const [type, setType] = useState<string>('all')
  const [availableOnly, setAvailableOnly] = useState(false)

  const loadCapabilities = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listAICapabilities({
        type: type === 'all' ? undefined : type as any,
        availableOnly,
      })
      setItems(res.capabilities || [])
    } catch {
      message.error('加载 AI 能力失败')
    } finally {
      setLoading(false)
    }
  }, [availableOnly, message, type])

  useEffect(() => {
    loadCapabilities()
  }, [loadCapabilities])

  const availableCount = items.filter(item => item.status === 'available').length
  const issueCount = items.length - availableCount

  return (
    <Card
      title={
        <Space>
          <RocketOutlined />
          <Text strong style={{ color: THEME.textPrimary }}>AI 能力诊断</Text>
          <Badge count={availableCount} style={{ backgroundColor: THEME.success }} />
          {issueCount > 0 && <Badge count={issueCount} style={{ backgroundColor: '#faad14' }} />}
        </Space>
      }
      extra={
        <Space wrap>
          <Select
            value={type}
            onChange={setType}
            style={{ width: 130 }}
            options={[
              { value: 'all', label: '全部类型' },
              { value: 'llm', label: '文本' },
              { value: 'image', label: '图像' },
              { value: 'video', label: '视频' },
              { value: 'tts', label: '语音' },
              { value: 'stt', label: '识别' },
              { value: 'embedding', label: '嵌入' },
            ]}
          />
          <Switch checked={availableOnly} onChange={setAvailableOnly} checkedChildren="仅可用" unCheckedChildren="全部" />
          <Button icon={<ReloadOutlined />} onClick={loadCapabilities} loading={loading}>刷新</Button>
        </Space>
      }
      style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
    >
      <Alert
        type="info"
        showIcon
        message="这里统一读取设置里的 AI 模型配置。后续业务页会逐步只从这里取可用模型，避免出现未配置模型也能被选中、URL 被重复拼接的问题。"
        style={{ marginBottom: 12 }}
      />
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        size="small"
        pagination={{ pageSize: 12, showSizeChanger: true, showTotal: total => `共 ${total} 个` }}
        scroll={{ x: 980 }}
        columns={[
          {
            title: '模型',
            dataIndex: 'name',
            width: 220,
            render: (name: string, record: AICapability) => (
              <Space direction="vertical" size={2}>
                <Space>
                  <Text strong>{name}</Text>
                  {record.is_default && <Tag color="gold">默认</Tag>}
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>{record.id}</Text>
              </Space>
            ),
          },
          {
            title: '类型',
            dataIndex: 'type',
            width: 90,
            render: (value: string) => <Tag color={TYPE_COLORS[value] || 'default'}>{TYPE_LABELS[value] || value}</Tag>,
          },
          {
            title: '服务商',
            dataIndex: 'provider_label',
            width: 130,
            render: (value: string, record: AICapability) => (
              <Tag style={{ color: getReadableColor(PROVIDER_COLORS[record.provider] || THEME.textSecondary) }}>{value || record.provider}</Tag>
            ),
          },
          {
            title: '默认模型',
            dataIndex: 'model',
            width: 180,
            render: (model: string) => model ? <Text code>{model}</Text> : <Text type="secondary">未设置</Text>,
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 110,
            render: (status: string, record: AICapability) => {
              const item = CAPABILITY_STATUS[status] || { color: 'default', text: status }
              return <Tag color={item.color}>{record.status_message || item.text}</Tag>
            },
          },
          {
            title: '能力',
            dataIndex: 'capabilities',
            width: 220,
            render: (caps: string[]) => (
              <Space size={[4, 4]} wrap>
                {(caps || []).map(cap => <Tag key={cap}>{cap}</Tag>)}
              </Space>
            ),
          },
          {
            title: '接口',
            key: 'endpoint',
            width: 260,
            render: (_: any, record: AICapability) => (
              <Space direction="vertical" size={2}>
                <Text type="secondary" ellipsis style={{ maxWidth: 240 }}>{record.base_url || '-'}</Text>
                {record.api_endpoint && <Text type="secondary" style={{ fontSize: 12 }}>{record.api_endpoint}</Text>}
              </Space>
            ),
          },
        ]}
      />
    </Card>
  )
}

function getReadableColor(color: string) {
  return color || undefined
}

// ==================== 组件 ====================
export default function SettingsPage() {
  const { theme: THEME } = useTheme()
  const [activeTab, setActiveTab] = useState('models')
  const [providers, setProviders] = useState<Provider[]>([]) // 这里是 Connectors（具体模型）
  const [providerMetadata, setProviderMetadata] = useState<ProviderMetadata[]>([]) // 这里是 Provider 配置（服务商）
  const [filteredProviders, setFilteredProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null)
  const [viewingProvider, setViewingProvider] = useState<Provider | null>(null)
  const [testResult, setTestResult] = useState<ConnectorTestResult | null>(null)
  const [editableRequestBody, setEditableRequestBody] = useState<string>('')
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null)
  const [testProviderId, setTestProviderId] = useState<string | null>(null)
  const [searchText, setSearchText] = useState('')
  const [filterType, setFilterType] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [advancedManuallyToggled, setAdvancedManuallyToggled] = useState(false)
  const [fetchingModels, setFetchingModels] = useState(false)
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([])
  const [form] = Form.useForm()
  const { message } = AntApp.useApp()
  const selectedType = Form.useWatch('provider_type', form)
  const selectedProvider = Form.useWatch('provider', form)
  const selectedApiFormat = Form.useWatch('api_format', form)

  // 动态 API 格式选项（根据 provider + type 组合返回）
  const getApiFormatOptions = () => {
    // Gemini 图像生成 → 使用 google-genai 原生 SDK
    if (selectedProvider === 'gemini' && selectedType === 'image') {
      return [
        { value: 'gemini_sdk', label: '🌟 Google Gemini SDK（原生图片生成）' },
        { value: 'custom', label: '⚙️ 自定义 HTTP（手动）' },
      ]
    }
    if (selectedType === 'image') {
      return [
        { value: 'openai_sdk', label: '🧩 OpenAI SDK（Images API）' },
        { value: 'custom', label: '⚙️ 自定义 HTTP（手动）' },
      ]
    }
    // 默认选项（LLM / OpenAI 兼容）
    return [
      { value: 'openai_sdk', label: '🧩 OpenAI SDK（Chat Completions）' },
      { value: 'openai_sdk_responses', label: '🧩 OpenAI SDK（Responses API）' },
      { value: 'custom', label: '⚙️ 自定义 HTTP（手动）' },
    ]
  }

  // 当 provider + type 组合确定时，自动选择最合适的 api_format
  useEffect(() => {
    if (!selectedProvider || !selectedType) return
    if (form.getFieldValue('api_format')) {
      const current = form.getFieldValue('api_format')
      // 检查当前值是否在可用选项中，如果不在则自动切换
      const options = getApiFormatOptions()
      if (!options.some((o: any) => o.value === current)) {
        if (selectedProvider === 'gemini' && selectedType === 'image') {
          form.setFieldValue('api_format', 'gemini_sdk')
        } else {
          form.setFieldValue('api_format', 'openai_sdk')
        }
      }
    }
  }, [selectedProvider, selectedType])

  const getPreset = () => {
    if (!selectedProvider || !selectedType) return null
    return PROVIDER_PRESETS[selectedProvider]?.[selectedType] || null
  }

  const handleDiscoverModels = async () => {
    const baseUrl = form.getFieldValue('base_url')
    const apiKey = form.getFieldValue('api_key')
    const apiFormat = selectedApiFormat || 'custom'
    const modelsEndpoint = form.getFieldValue('models_endpoint') || '/v1/models'

    if (!baseUrl) {
      message.warning('请先填写 Base URL')
      return
    }

    setFetchingModels(true)
    try {
      const result = await discoverModels({
        api_format: apiFormat,
        base_url: baseUrl,
        api_key: apiKey || '',
        models_endpoint: apiFormat === 'custom' ? modelsEndpoint : undefined,
      }) as any

      if (result?.success && result?.models?.length > 0) {
        setDiscoveredModels(result.models)
        message.success(`发现 ${result.models.length} 个模型`)
      } else {
        setDiscoveredModels([])
        message.warning(result?.error || '未发现任何模型')
      }
    } catch (e: any) {
      setDiscoveredModels([])
      message.error(e?.message || '获取模型列表失败')
    } finally {
      setFetchingModels(false)
    }
  }

  useEffect(() => {
    if (!selectedProvider || !selectedType || editingProvider) return

    const preset = getPreset()
    if (!preset) return

    const format = selectedApiFormat || 'custom'

    // SDK 模式只预填基础字段，custom 模式填全部
    const values: Record<string, any> = {
      base_url: preset.base_url || '',
      default_model: preset.default_model || '',
      support_vision_input: preset.support_vision_input ?? false,
    }

    if (format === 'custom') {
      Object.assign(values, {
        api_endpoint: preset.api_endpoint || '',
        available_models: preset.available_models ? JSON.stringify(preset.available_models) : '',
        max_tokens: preset.max_tokens ?? 4096,
        temperature: preset.temperature ?? 0.7,
        request_template: preset.request_template || '',
        response_config: preset.response_config || '',
        supported_sizes: preset.supported_sizes || [],
        default_params: preset.default_params ? JSON.stringify(preset.default_params) : '',
        support_reference_image: preset.support_reference_image ?? false,
        support_multiple_reference_images: preset.support_multiple_reference_images ?? false,
        reference_image_field: preset.reference_image_field || '',
        reference_image_array_field: preset.reference_image_array_field || '',
      })
      if (preset.response_config) {
        Object.assign(values, asyncConfigToFields(preset.response_config))
      }
    }

    form.setFieldsValue(values)
  }, [selectedProvider, selectedType, selectedApiFormat, editingProvider, form])

  const loadProviders = async () => {
    setLoading(true)
    try {
      const result = await listConnectors()
      setProviders(result.connectors || [])
    } catch {
      message.error('加载 AI 模型配置失败')
    } finally {
      setLoading(false)
    }
  }

  const loadProviderMetadata = async () => {
    try {
      const result = await listProviders() as any
      setProviderMetadata(result.providers || [])
    } catch {
      message.error('加载 Provider 配置失败')
    }
  }

  useEffect(() => {
    loadProviders()
    loadProviderMetadata()
  }, [])

  // 搜索和筛选逻辑
  useEffect(() => {
    let filtered = [...providers]
    
    // 按类型筛选
    if (filterType !== 'all') {
      filtered = filtered.filter(p => p.provider_type === filterType)
    }
    
    // 按状态筛选
    if (filterStatus !== 'all') {
      const isActive = filterStatus === 'active'
      filtered = filtered.filter(p => p.is_active === isActive)
    }
    
    // 按搜索文本筛选
    if (searchText) {
      const keyword = searchText.toLowerCase()
      filtered = filtered.filter(p => 
        p.name?.toLowerCase().includes(keyword) ||
        p.id?.toLowerCase().includes(keyword) ||
        p.provider?.toLowerCase().includes(keyword)
      )
    }
    
    setFilteredProviders(filtered)
  }, [providers, filterType, filterStatus, searchText])

  const handleTest = async (id: string, customBody?: any) => {
    const hide = message.loading('正在测试连接...', 0)
    try {
      const result = await testConnector(id, customBody ? { body: customBody } : undefined) as ConnectorTestResult
      hide()
      setTestResult(result)
      setTestProviderId(id)
      // 初始化可编辑的请求体
      if (result.debug?.request?.body) {
        setEditableRequestBody(stringifyDebugValue(result.debug.request.body))
      }
      if (result?.success) {
        message.success(result.message || '连接测试成功')
        return
      }
      message.error(result?.message || '连接测试失败，请检查 API Key 和网络')
    } catch (e: any) {
      hide()
      const errorMsg = e?.response?.data?.detail || '连接测试失败，请检查 API Key 和网络'
      message.error(errorMsg)
    }
  }

  const handleEdit = (provider: Provider) => {
    setViewingProvider(null)
    setEditingProvider(provider)
    setAdvancedManuallyToggled(false)
    setDiscoveredModels([])
    form.setFieldsValue({
      id: provider.id,
      name: provider.name,
      provider: provider.provider,
      provider_type: provider.provider_type,
      api_key: provider.api_key || '',
      base_url: provider.base_url || '',
      api_endpoint: provider.api_endpoint || '',
      default_model: provider.default_model || '',
      max_tokens: provider.max_tokens || 4096,
      temperature: provider.temperature ?? 0.7,
      is_active: provider.is_active !== false,
      is_default: provider.is_default || false,
      priority: provider.priority || 0,
      description: provider.description || '',
      // 扩展字段
      request_template: provider.request_template || '',
      response_config: provider.response_config || '',
      supported_sizes: Array.isArray(provider.supported_sizes) 
        ? provider.supported_sizes 
        : (provider.supported_sizes ? [provider.supported_sizes] : []),
      default_params: typeof provider.default_params === 'object' 
        ? JSON.stringify(provider.default_params) 
        : (provider.default_params || ''),
      price_per_call: provider.price_per_call ?? undefined,
      support_reference_image: provider.support_reference_image || false,
      support_multiple_reference_images: provider.support_multiple_reference_images || false,
      reference_image_field: provider.reference_image_field || 'image',
      reference_image_array_field: provider.reference_image_array_field || '',
      support_vision_input: provider.support_vision_input || false,
      test_prompt: provider.test_prompt || '',
      timeout: provider.timeout || 300,
      test_timeout: provider.test_timeout || 20,
      api_format: provider.api_format || 'custom',
      ...asyncConfigToFields(provider.response_config),
    })
    setModalVisible(true)
  }

  const handleView = (provider: Provider) => {
    setViewingProvider(provider)
  }

  const handleAdd = () => {
    setEditingProvider(null)
    form.resetFields()
    setAdvancedManuallyToggled(false)
    setDiscoveredModels([])
    // 自动生成唯一标识符
    const generatedId = `connector-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`
    form.setFieldsValue({ 
      id: generatedId,
      is_active: true,
      api_format: 'custom',
      async_enabled: false,
      async_request_headers: stringifyJson({}),
      async_poll_headers: stringifyJson({}),
    })
    setModalVisible(true)
  }

  const handleSave = async (values: any) => {
    try {
      // 处理扩展配置字段（保持字符串格式，后端会解析 JSON）
      const processedValues = { ...values }
      
      // 如果是掩码格式（包含 "...")，不更新 API Key
      if (editingProvider && values.api_key && values.api_key.includes('...')) {
        delete processedValues.api_key
      }

      // supported_sizes 需要转换为 JSON 字符串
      if (processedValues.supported_sizes && Array.isArray(processedValues.supported_sizes)) {
        processedValues.supported_sizes = JSON.stringify(processedValues.supported_sizes)
      }

      if (processedValues.provider_type === 'image' && processedValues.api_format === 'custom') {
        processedValues.response_config = buildResponseConfigWithAsync(processedValues)
      }
      ASYNC_FORM_FIELDS.forEach(field => delete processedValues[field])

      if (editingProvider) {
        // 更新现有连接器
        await updateConnector(editingProvider.id, processedValues)
        message.success('AI 模型更新成功')
      } else {
        // 创建新连接器 - 移除 id 字段（让后端自动生成）
        const { id, ...createData } = processedValues
        await createConnector(createData)
        message.success('AI 模型创建成功')
      }
      setModalVisible(false)
      loadProviders()
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || e?.message || '保存失败'
      message.error(errorMsg)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteConnector(id)
      message.success('删除成功')
      loadProviders()
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || e?.message || '删除失败'
      message.error(errorMsg)
    }
  }

  // 使用自定义请求体重新测试
  const handleRetest = async () => {
    if (!testProviderId) return
    
    try {
      let customBody
      try {
        customBody = JSON.parse(editableRequestBody)
      } catch (e) {
        message.error('JSON 格式错误，请检查请求体')
        return
      }
      
      await handleTest(testProviderId, customBody)
    } catch (e: any) {
      // handleTest 内部已经处理错误
    }
  }

  // 复制连接器
  const handleDuplicate = (provider: Provider) => {
    setEditingProvider(null)
    form.resetFields()
    // 自动生成标识符
    const generatedId = `connector-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`
    form.setFieldsValue({
      id: generatedId,
      name: `${provider.name} (副本)`,
      provider: provider.provider,
      provider_type: provider.provider_type,
      api_key: provider.api_key || '',
      base_url: provider.base_url || '',
      api_endpoint: provider.api_endpoint || '',
      default_model: provider.default_model || '',
      max_tokens: provider.max_tokens || 4096,
      temperature: provider.temperature || 0.7,
      is_active: false, // 默认禁用
      description: `复制自 ${provider.name}`,
      test_prompt: provider.test_prompt || '',
      // 扩展字段（图像/视频生成专用）
      request_template: provider.request_template || '',
      response_config: provider.response_config || '',
      supported_sizes: Array.isArray(provider.supported_sizes) 
        ? provider.supported_sizes 
        : (provider.supported_sizes ? [provider.supported_sizes] : []),
      default_params: typeof provider.default_params === 'object' 
        ? JSON.stringify(provider.default_params) 
        : (provider.default_params || ''),
      price_per_call: provider.price_per_call ?? undefined,
      support_reference_image: provider.support_reference_image || false,
      support_multiple_reference_images: provider.support_multiple_reference_images || false,
      reference_image_field: provider.reference_image_field || 'image',
      reference_image_array_field: provider.reference_image_array_field || '',
      support_vision_input: provider.support_vision_input || false,
      api_format: provider.api_format || 'custom',
    })
    setModalVisible(true)
  }

  // 导出所有模型配置为 JSON
  const handleExport = async () => {
    try {
      const result = await exportConnectors() as any
      if (!result?.connectors) {
        message.error('导出失败：未获取到数据')
        return
      }
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ai-connectors-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success(`已导出 ${result.connectors.length} 个模型配置`)
    } catch (e: any) {
      message.error(e?.message || '导出失败')
    }
  }

  // 导入模型配置
  const handleImport = async (file: File) => {
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const connectors = data?.connectors || data
      if (!Array.isArray(connectors)) {
        message.error('JSON 格式错误：未找到 connectors 数组')
        return false
      }
      const result = await importConnectors(connectors, 'upsert') as any
      if (result?.success) {
        message.success(result.message || '导入成功')
        loadProviders()
      } else {
        message.error(result?.message || '导入失败')
      }
      return false // 阻止 antd Upload 自动上传
    } catch (e: any) {
      message.error(e?.message || '导入失败：请检查 JSON 文件格式')
      return false
    }
  }

  // 获取提供商对应的颜色
  const getProviderColor = (provider: string): string => {
    return PROVIDER_COLORS[provider] || THEME.textSecondary
  }

  const stringifyDebugValue = (value: unknown): string => {
    if (value == null) return ''
    if (typeof value === 'string') return value
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }

  // 从响应中提取图片 URL
  const extractImageUrls = (body: unknown): string[] => {
    if (!body) return []
    
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body)
      } catch {
        return []
      }
    }

    const urls: string[] = []
    const obj = body as Record<string, any>
    
    // 尝试多种常见的响应格式，优先选择 data（OpenAI 标准）
    if (obj.data && Array.isArray(obj.data)) {
      obj.data.forEach((item: any) => {
        if (item.url) urls.push(item.url)
        if (item.b64_json) urls.push(`data:image/png;base64,${item.b64_json}`)
      })
    } 
    // 如果没有 data，尝试 images
    else if (obj.images && Array.isArray(obj.images)) {
      obj.images.forEach((item: any) => {
        if (item.url) urls.push(item.url)
        if (item.b64_json) urls.push(`data:image/png;base64,${item.b64_json}`)
      })
    }
    // ModelScope 异步生图完成响应
    else if (obj.output_images && Array.isArray(obj.output_images)) {
      obj.output_images.forEach((item: any) => {
        if (typeof item === 'string') urls.push(item)
        else if (item?.url) urls.push(item.url)
      })
    }
    // 最后尝试单个 url
    else if (obj.url) {
      urls.push(obj.url)
    }
    
    // 去重
    return [...new Set(urls)]
  }

  // 可拖拽调整列宽
  const { colWidths, wrapColumnTitle } = useResizableColumns({
    name: 280,
    provider: 120,
    provider_type: 100,
    default_model: 150,
    status: 100,
    usage: 180,
    last_used: 140,
    action: 300,
  })

  const providerColumns = [
    {
      title: wrapColumnTitle('名称', 'name'),
      dataIndex: 'name',
      key: 'name',
      width: colWidths['name'],
      render: (text: string, record: Provider) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap' }}>
          <Text strong style={{ color: THEME.textPrimary, fontSize: 14 }}>{text}</Text>
          {record.is_default && <Tag color="gold" style={{ fontSize: 10 }}>默认</Tag>}
          <Tag style={{ background: 'rgba(255,255,255,0.06)', border: 'none', color: THEME.textSecondary, fontSize: 10 }}>
            {record.id.slice(0, 8)}...
          </Tag>
        </div>
      ),
    },
    {
      title: wrapColumnTitle('提供商', 'provider'),
      dataIndex: 'provider',
      key: 'provider',
      width: colWidths['provider'],
      render: (provider: string) => {
        const color = getProviderColor(provider)
        return (
          <Tag style={{ background: `${color}22`, border: `1px solid ${color}44`, color: color }}>
            {provider}
          </Tag>
        )
      },
    },
    {
      title: wrapColumnTitle('类型', 'provider_type'),
      dataIndex: 'provider_type',
      key: 'provider_type',
      width: colWidths['provider_type'],
      render: (type: string) => {
        const color = TYPE_COLORS[type] || THEME.textSecondary
        const label = TYPE_LABELS[type] || type
        return (
          <Tag style={{ background: `${color}22`, border: `1px solid ${color}44`, color: color }}>
            {label}
          </Tag>
        )
      },
    },
    {
      title: wrapColumnTitle('模型', 'default_model'),
      dataIndex: 'default_model',
      key: 'default_model',
      width: colWidths['default_model'],
      render: (model: string) => model ? (
        <Tag style={{ background: 'rgba(255,255,255,0.06)', border: 'none', color: THEME.textSecondary }}>
          {model}
        </Tag>
      ) : <Text type="secondary" style={{ fontSize: 12 }}>未设置</Text>,
    },
    {
      title: wrapColumnTitle('状态', 'status'),
      key: 'status',
      width: colWidths['status'],
      render: (_: any, record: Provider) => (
        <Badge 
          status={record.is_active ? 'success' : 'default'} 
          text={<span style={{ color: record.is_active ? THEME.success : THEME.textSecondary }}>{record.is_active ? '启用' : '禁用'}</span>} 
        />
      ),
    },
    {
      title: wrapColumnTitle('使用统计', 'usage'),
      key: 'usage',
      width: colWidths['usage'],
      render: (_: any, record: Provider) => (
        <div style={{ display: 'flex', gap: 12 }}>
          <Text style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'nowrap' }}>使用: {record.usage_count || 0}</Text>
          <Text style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'nowrap' }}>费用: ${((record.total_cost || 0)).toFixed(4)}</Text>
        </div>
      ),
    },
    {
      title: wrapColumnTitle('最后使用', 'last_used'),
      dataIndex: 'last_used',
      key: 'last_used',
      width: colWidths['last_used'],
      render: (time: string) => time ? (
        <Text style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'nowrap' }}>{new Date(time).toLocaleDateString('zh-CN')}</Text>
      ) : <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>从未使用</Text>,
    },
    {
      title: wrapColumnTitle('操作', 'action'),
      key: 'action',
      width: colWidths['action'],
      fixed: 'right' as const,
      render: (_: any, record: Provider) => (
        <Space size={0} split={<div style={{ width: 1, height: 14, background: THEME.borderLight }} />}>
          <Button type="text" size="small" onClick={() => handleView(record)} style={{ color: THEME.textSecondary, padding: '0 8px' }}>
            详情
          </Button>
          <Button type="text" size="small" onClick={() => handleDuplicate(record)} style={{ color: THEME.textSecondary, padding: '0 8px' }}>
            复制
          </Button>
          <Button type="text" size="small" onClick={() => handleTest(record.id)} style={{ color: THEME.primary, padding: '0 8px' }}>
            测试
          </Button>
          <Popconfirm
            title={record.is_active ? '确认禁用此连接？' : '确认启用此连接？'}
            onConfirm={async () => {
              try {
                await updateConnector(record.id, { is_active: !record.is_active })
                message.success(`已${record.is_active ? '禁用' : '启用'} ${record.name}`)
                loadProviders()
              } catch (e: any) {
                message.error(e?.response?.data?.detail || '操作失败')
              }
            }}
          >
            <Switch
              size="small"
              checked={record.is_active}
              checkedChildren="启用"
              unCheckedChildren="禁用"
              style={{ marginLeft: 4, marginRight: 4 }}
              onClick={(_, e) => e.stopPropagation()}
            />
          </Popconfirm>
          <Button type="text" size="small" onClick={() => handleEdit(record)} style={{ color: THEME.textSecondary, padding: '0 8px' }}>
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button type="text" size="small" danger style={{ padding: '0 8px' }}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1600, margin: '0 auto', padding: '24px' }}>
      <Title level={3} style={{ color: THEME.textPrimary, marginBottom: 16 }}>
        <SettingOutlined style={{ marginRight: 12 }} />
        系统设置
      </Title>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        size="large"
        items={[
          {
            key: 'provider',
            label: (
              <span><ApiOutlined style={{ marginRight: 8 }} />服务商管理</span>
            ),
            children: <ProviderManagement />,
          },
          {
            key: 'models',
            label: (
              <span><ApiOutlined style={{ marginRight: 8 }} />模型管理</span>
            ),
            children: (
              <Card
                title={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, padding: '4px 0' }}>
                    <Space>
                      <Text strong style={{ color: THEME.textPrimary }}>AI 模型配置</Text>
                      <Badge count={filteredProviders.length} showZero={false} style={{ backgroundColor: THEME.primary }} />
                    </Space>
                    <Space wrap size={[8, 8]}>
                      <Input
                        placeholder="搜索名称、标识符..."
                        prefix={<SearchOutlined style={{ color: THEME.textSecondary }} />}
                        value={searchText}
                        onChange={e => setSearchText(e.target.value)}
                        style={{ width: 200 }}
                        allowClear
                        size="small"
                      />
                      <Select
                        value={filterType}
                        onChange={setFilterType}
                        style={{ width: 110 }}
                        size="small"
                        options={[
                          { value: 'all', label: '全部类型' },
                          { value: 'llm', label: '文本' },
                          { value: 'image', label: '图像' },
                          { value: 'video', label: '视频' },
                          { value: 'tts', label: '语音' },
                          { value: 'stt', label: '语音识别' },
                          { value: 'embedding', label: '嵌入' },
                        ]}
                      />
                      <Select
                        value={filterStatus}
                        onChange={setFilterStatus}
                        style={{ width: 110 }}
                        size="small"
                        options={[
                          { value: 'all', label: '全部状态' },
                          { value: 'active', label: '已启用' },
                          { value: 'inactive', label: '已禁用' },
                        ]}
                      />
                      <Button size="small" icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
                      <Button size="small" icon={<UploadOutlined />} onClick={() => document.getElementById('import-connectors-input')?.click()}>导入</Button>
                      <input
                        id="import-connectors-input"
                        type="file"
                        accept=".json,application/json"
                        style={{ display: 'none' }}
                        onChange={e => {
                          const file = e.target.files?.[0]
                          if (file) {
                            handleImport(file)
                            e.target.value = ''
                          }
                        }}
                      />
                      <Button size="small" icon={<ReloadOutlined />} onClick={loadProviders} loading={loading}>刷新</Button>
                      <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
                    </Space>
                  </div>
                }
                style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
                styles={{ body: { padding: '12px 16px' } }}
              >
                <Alert
                  type="info"
                  showIcon
                  message="模型是用户实际选择的 AI 配置项，每个模型会绑定到底层连接器、默认模型名和能力类型。"
                  style={{ marginBottom: 12, background: 'rgba(0,212,255,0.05)', border: `1px solid rgba(0,212,255,0.2)`, fontSize: 13 }}
                  banner
                />
                {loading ? (
                  <Skeleton active paragraph={{ rows: 3 }} />
                ) : filteredProviders.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px 0' }}>
                    <Text style={{ color: THEME.textSecondary }}>{searchText || filterType !== 'all' || filterStatus !== 'all' ? '没有匹配的模型' : '暂无 AI 模型配置'}</Text>
                    <div style={{ marginTop: 12 }}>
                      {(searchText || filterType !== 'all' || filterStatus !== 'all') ? (
                        <Button type="link" onClick={() => { setSearchText(''); setFilterType('all'); setFilterStatus('all') }}>清除筛选</Button>
                      ) : (
                        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增模型</Button>
                      )}
                    </div>
                  </div>
                ) : (
                  <Table 
                      dataSource={filteredProviders} 
                      columns={providerColumns} 
                      rowKey="id" 
                      pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => (`共 ${total} 个`), size: 'small' }}
                      style={{ background: THEME.bgCard, borderRadius: 8 }}
                      scroll={{ x: Object.values(colWidths).reduce((a, b) => a + b, 0) }}
                      size="small"
                      components={{
                        header: {
                          cell: (props: any) => (
                            <th
                              {...props}
                              style={{
                                ...(props.style || {}),
                                background: THEME.bgElevated,
                                color: THEME.textPrimary,
                                borderColor: THEME.border,
                                padding: '8px 12px',
                                fontWeight: 600,
                                fontSize: 13,
                              }}
                            />
                          ),
                        },
                        body: {
                          cell: (props: any) => (
                            <td
                              {...props}
                              style={{
                                ...(props.style || {}),
                                background: THEME.bgCard,
                                color: THEME.textPrimary,
                                borderColor: THEME.border,
                                padding: '8px 12px',
                              }}
                            />
                          ),
                        },
                      }}
                    />
                )}
              </Card>
            ),
          },
          {
            key: 'capabilities',
            label: (
              <span><RocketOutlined style={{ marginRight: 8 }} />能力诊断</span>
            ),
            children: <AICapabilityPanel />,
          },
          {
            key: 'video',
            label: <span><VideoCameraOutlined style={{ marginRight: 8 }} />视频处理</span>,
            children: <VideoSettings />,
          },
          {
            key: 'transcribe',
            label: <span><FileTextOutlined style={{ marginRight: 8 }} />字幕识别</span>,
            children: <TranscribeSettings />,
          },
          {
            key: 'storage',
            label: <span><DatabaseOutlined style={{ marginRight: 8 }} />存储设置</span>,
            children: <StorageSettings />,
          },
        ]}
      />
      
      {/* 编辑/新增 Modal */}
      <Modal
        title={editingProvider ? '编辑 AI 模型' : '新增 AI 模型'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={760}
        styles={{ body: { padding: '12px 24px', maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16' }}>
            <Form.Item name="id" label={<span style={{ color: THEME.textPrimary }}>标识符</span>} rules={[{ required: true, message: '请输入标识符' }]}>
              <Input placeholder="如：openai-gpt4" disabled={!!editingProvider} />
            </Form.Item>
            <Form.Item name="provider" label={<span style={{ color: THEME.textPrimary }}>底层服务商</span>} rules={[{ required: true, message: '请选择服务商' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={providerMetadata.map(p => ({ value: p.provider_id, label: p.name }))}
              />
            </Form.Item>
            <Form.Item name="name" label={<span style={{ color: THEME.textPrimary }}>显示名称</span>} rules={[{ required: true, message: '请输入名称' }]}>
              <Input placeholder="如：OpenAI GPT-4" />
            </Form.Item>
            <Form.Item name="provider_type" label={<span style={{ color: THEME.textPrimary }}>类型</span>} rules={[{ required: true, message: '请选择类型' }]}>
              <Select options={AI_TYPE_OPTIONS} />
            </Form.Item>
          </div>
          <TypeHelpBlock type={selectedType} theme={THEME} compact />

          {/* 继承 Provider 默认配置按钮 */}
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.provider !== curr.provider || prev.provider_type !== curr.provider_type}>
            {({ getFieldValue }) => {
              const providerVal = getFieldValue('provider')
              const providerTypeVal = getFieldValue('provider_type')
              const providerTypeLabel = AI_TYPE_HELP[providerTypeVal]?.title || providerTypeVal
              return providerVal && providerTypeVal ? (
                <div style={{ marginBottom: 16, padding: '12px 16px', background: 'rgba(0,212,255,0.05)', borderRadius: 8, border: '1px solid rgba(0,212,255,0.2)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <RocketOutlined style={{ fontSize: 20, color: THEME.primary }} />
                    <div style={{ flex: 1 }}>
                      <Text strong style={{ color: THEME.textPrimary }}>从 Provider 继承默认配置</Text>
                      <Text style={{ color: THEME.textSecondary, fontSize: 12, display: 'block' }}>
                        自动填充服务商 {providerVal} 在 {providerTypeLabel} 类型下的默认 URL、模型、参数等
                      </Text>
                    </div>
                    <Button
                      type="primary"
                      size="small"
                      icon={<DownloadOutlined />}
                      onClick={async () => {
                        try {
                          const result = await getProviderDefaults(providerVal, providerTypeVal) as any
                          if (result.success) {
                            const defaults = result.defaults
                            // 自动填充表单字段
                            if (defaults.base_url) form.setFieldValue('base_url', defaults.base_url)
                            if (defaults.api_key && !form.getFieldValue('api_key')) form.setFieldValue('api_key', defaults.api_key)
                            if (defaults.api_format) form.setFieldValue('api_format', defaults.api_format)
                            if (defaults.default_model) form.setFieldValue('default_model', defaults.default_model)
                            // 设置默认参数
                            if (defaults.params) {
                              if (defaults.params.temperature !== undefined) form.setFieldValue('temperature', defaults.params.temperature)
                              if (defaults.params.max_tokens !== undefined) form.setFieldValue('max_tokens', defaults.params.max_tokens)
                              if (defaults.params.size) form.setFieldValue('supported_sizes', Array.isArray(defaults.params.size) ? defaults.params.size : [defaults.params.size])
                              if (defaults.params.quality) form.setFieldValue('default_quality', defaults.params.quality)
                              if (defaults.params.n) form.setFieldValue('default_n', defaults.params.n)
                            }
                            // 请求模板和响应配置（Image/Video 类型使用）
                            if (defaults.request_template) form.setFieldValue('request_template', defaults.request_template)
                            if (defaults.response_config) {
                              form.setFieldValue('response_config', defaults.response_config)
                              form.setFieldsValue(asyncConfigToFields(defaults.response_config))
                            }
                            if (defaults.supported_sizes) form.setFieldValue('supported_sizes', defaults.supported_sizes)
                            // 参考图配置
                            if (defaults.reference_image_config) {
                              const refCfg = defaults.reference_image_config
                              if (refCfg.reference_image_field) form.setFieldValue('reference_image_field', refCfg.reference_image_field)
                              if (refCfg.reference_image_array_field) form.setFieldValue('reference_image_array_field', refCfg.reference_image_array_field)
                              if (refCfg.support_reference_image !== undefined) form.setFieldValue('support_reference_image', refCfg.support_reference_image)
                              if (refCfg.support_multiple_reference_images !== undefined) form.setFieldValue('support_multiple_reference_images', refCfg.support_multiple_reference_images)
                            }
                            // 参数转换配置
                            if (defaults.parameter_transforms) form.setFieldValue('parameter_transforms', defaults.parameter_transforms)
                            message.success(`已继承 ${result.provider_name} 的默认配置`)
                          }
                        } catch (e: any) {
                          message.error(e?.response?.data?.detail || '获取默认配置失败')
                        }
                      }}
                    >
                      继承默认
                    </Button>
                  </div>
                </div>
              ) : null
            }}
          </Form.Item>

          {/* API格式选择 — 根据 provider+type 动态渲染选项 */}
          <Form.Item name="api_format" label={<span style={{ color: THEME.textPrimary }}>API 格式</span>} initialValue="custom">
            <Select
              options={getApiFormatOptions()}
              onChange={() => setDiscoveredModels([])}
            />
          </Form.Item>
          {selectedApiFormat && (
            <Alert
              type="info"
              showIcon
              message="API 格式说明"
              description={getApiFormatHelp(selectedApiFormat, selectedType)}
              style={{
                marginBottom: 16,
                background: selectedApiFormat === 'custom' ? 'rgba(168,85,247,0.05)' : 'rgba(0,212,255,0.05)',
                border: selectedApiFormat === 'custom' ? '1px solid rgba(168,85,247,0.2)' : '1px solid rgba(0,212,255,0.2)',
              }}
            />
          )}

          <Form.Item name="api_key" label={<span style={{ color: THEME.textPrimary }}>API Key</span>}>
            <Input.Password placeholder={editingProvider ? '留空表示不修改' : '请输入 API Key'} />
          </Form.Item>
          
          <Form.Item name="base_url" label={<span style={{ color: THEME.textPrimary }}>Base URL (可选)</span>}>
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>

          <Form.Item name="api_endpoint" label={<span style={{ color: THEME.textPrimary }}>API Endpoint (可选)</span>}>
            <Input placeholder="例如：/images/generations 或 /services/aigc/wanx/v1/image/generation" />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16' }}>
            <Form.Item name="default_model" label={<span style={{ color: THEME.textPrimary }}>默认模型</span>}>
              {discoveredModels.length > 0 ? (
                <Select
                  showSearch
                  placeholder="选择模型..."
                  options={discoveredModels.map(m => ({ value: m, label: m }))}
                  onChange={(val) => form.setFieldValue('default_model', val)}
                  notFoundContent="无匹配模型"
                />
              ) : (
                <Input placeholder="gpt-4o / text-embedding-3-large / BAAI/bge-m3" />
              )}
            </Form.Item>
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>&nbsp;</span>}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleDiscoverModels}
                loading={fetchingModels}
                style={{ width: '100%' }}
              >
                获取模型列表
              </Button>
            </Form.Item>
          </div>

          {/* custom 模式：模型列表端点 */}
          {selectedApiFormat === 'custom' && (
            <Form.Item name="models_endpoint" label={<span style={{ color: THEME.textPrimary }}>模型列表端点</span>} initialValue="/v1/models">
              <Input placeholder="/v1/models" />
            </Form.Item>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16' }}>
            {selectedType === 'llm' && (
              <>
                <Form.Item name="max_tokens" label={<span style={{ color: THEME.textPrimary }}>最大 Token 数</span>}>
                  <InputNumber min={1} max={200000} style={{ width: '100%' }} placeholder="留空使用默认值" />
                </Form.Item>
              </>
            )}
            {selectedType === 'embedding' && (
              <>
                <Form.Item name="embedding_dimension" label={<span style={{ color: THEME.textPrimary }}>向量维度</span>}>
                  <InputNumber min={64} max={8192} step={64} style={{ width: '100%' }} placeholder="1536" />
                </Form.Item>
              </>
            )}
          </div>
          {selectedType === 'llm' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16' }}>
              <Form.Item name="temperature" label={<span style={{ color: THEME.textPrimary }}>温度参数</span>}>
                <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} placeholder="留空使用默认值" />
              </Form.Item>
              <Form.Item name="support_vision_input" label={<span style={{ color: THEME.textPrimary }}>支持视觉输入</span>} valuePropName="checked">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </div>
          )}
          {selectedType === 'embedding' && (
            <>
              <Form.Item name="embedding_type" label={<span style={{ color: THEME.textPrimary }}>嵌入类型</span>}>
                <Select options={[
                  { value: 'text', label: '文本嵌入' },
                  { value: 'image', label: '图像嵌入' },
                  { value: 'multimodal', label: '多模态嵌入' },
                ]} placeholder="text" style={{ width: '100%' }} allowClear />
              </Form.Item>
              <Alert
                type="info"
                showIcon
                message="Embedding 配置说明"
                description="配置完成后，系统将在素材入库时自动调用此 API 生成向量，用于混合搜索（向量+全文+标签）。"
                style={{ marginBottom: 16 }}
                closable
              />
            </>
          )}

          {!selectedApiFormat?.startsWith('openai_sdk') && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0 16' }}>
            <Form.Item name="monthly_budget" label={<span style={{ color: THEME.textPrimary }}>月度预算 (美元，可选)</span>}>
              <InputNumber min={0} step={10} style={{ width: '100%' }} placeholder="如：100" />
            </Form.Item>
            {selectedType === 'image' || selectedType === 'video' || !selectedType ? (
              <Form.Item name="price_per_call" label={<span style={{ color: THEME.textPrimary }}>按次计费 (美元/次)</span>}>
                <InputNumber min={0} step={0.0001} style={{ width: '100%' }} placeholder="如：0.002" />
              </Form.Item>
            ) : null}
            <Form.Item name="daily_limit" label={<span style={{ color: THEME.textPrimary }}>每日请求限制 (可选)</span>}>
              <InputNumber min={0} style={{ width: '100%' }} placeholder="如：1000" />
            </Form.Item>
          </div>
          )}

          <Form.Item name="description" label={<span style={{ color: THEME.textPrimary }}>备注说明</span>}>
            <TextArea rows={2} placeholder="可选：记录此连接的用途、限制等" />
          </Form.Item>

          <Form.Item name="test_prompt" label={<span style={{ color: THEME.textPrimary }}>测试提示词 (可选)</span>}>
            <TextArea 
              rows={2} 
              placeholder={`LLM 模式：测试使用的提示词（默认："Reply with ok."）\nImage 模式：测试图片生成的提示词（默认："连接测试图片"）`}
            />
          </Form.Item>

          <Form.Item name="timeout" label={<span style={{ color: THEME.textPrimary }}>API 请求超时时间 (秒)</span>} initialValue={300}>
            <InputNumber 
              style={{ width: 200 }} 
              min={10} 
              max={3600} 
              step={10}
              placeholder="300"
            />
            <span style={{ marginLeft: 8, color: THEME.textSecondary }}>默认: 300秒 (5分钟)</span>
          </Form.Item>

          <Form.Item name="test_timeout" label={<span style={{ color: THEME.textPrimary }}>连接测试超时时间 (秒)</span>} initialValue={20}>
            <InputNumber 
              style={{ width: 200 }} 
              min={5} 
              max={300} 
              step={5}
              placeholder="20"
            />
            <span style={{ marginLeft: 8, color: THEME.textSecondary }}>默认: 20秒</span>
          </Form.Item>

          {selectedType === 'image' || selectedType === 'video' ? (
            <Collapse
              ghost
              activeKey={
                (advancedManuallyToggled || !selectedApiFormat?.startsWith('openai_sdk')) ? ['advanced'] : []
              }
              onChange={(keys) => {
                setAdvancedManuallyToggled(true)
              }}
              style={{ marginTop: 16 }}
              items={[
                {
                  key: 'advanced',
                  label: (
                    <span style={{ color: THEME.textPrimary }}>
                      <SettingOutlined style={{ marginRight: 8 }} />
                      高级配置（请求模板/参考图）
                    </span>
                  ),
                  children: (
                    <div style={{ 
                      padding: 16, 
                      background: 'rgba(168,85,247,0.05)', 
                      border: '1px solid rgba(168,85,247,0.2)', 
                      borderRadius: 8 
                    }}>
                      <Form.Item name="request_template" label={<span style={{ color: THEME.textPrimary }}>Request 模板 (Jinja2)</span>} style={{ marginBottom: 8 }}>
                        <TextArea 
                          rows={4} 
                          placeholder={`JSON 格式的请求模板，例如：\n{"model": "{{ model }}", "prompt": "{{ prompt }}"}`}
                        />
                      </Form.Item>

                      <Form.Item
                        name="response_config"
                        label={<span style={{ color: THEME.textPrimary }}>Response 解析配置</span>}
                        style={{ marginBottom: 8 }}
                        extra={<span style={{ color: THEME.textSecondary, fontSize: 12 }}>
                          通用 HTTP 模式使用 JSONPath 动态提取结果；URL 响应用 images_path，base64 响应用 base64_images_path 或 response_format=base64。
                        </span>}
                      >
                        <TextArea 
                          rows={6} 
                          placeholder={`JSON 格式的响应配置，例如：\n{\n  "images_path": "$.data[*].url",\n  "base64_images_path": "$.data[*].b64_json",\n  "error_path": "$.error.message",\n  "response_format": "url"\n}`}
                        />
                      </Form.Item>

                      {selectedType === 'image' && (
                        <div style={{ margin: '12px 0 16px', padding: 12, border: `1px solid ${THEME.border}`, borderRadius: 6, background: THEME.bgElevated }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
                            <Form.Item name="async_enabled" valuePropName="checked" style={{ marginBottom: 0 }}>
                              <Switch checkedChildren="异步" unCheckedChildren="同步" />
                            </Form.Item>
                            <Button
                              size="small"
                              icon={<DownloadOutlined />}
                              onClick={() => {
                                const responseConfig = parseJsonObject(form.getFieldValue('response_config'))
                                responseConfig.async_config = MODELSCOPE_ASYNC_CONFIG
                                form.setFieldsValue({
                                  response_config: stringifyJson(responseConfig),
                                  ...asyncConfigToFields(responseConfig),
                                })
                                if (!form.getFieldValue('base_url')) form.setFieldValue('base_url', 'https://api-inference.modelscope.cn')
                                if (!form.getFieldValue('api_endpoint')) form.setFieldValue('api_endpoint', '/v1/images/generations')
                                if (!form.getFieldValue('default_model')) form.setFieldValue('default_model', 'Qwen/Qwen-Image')
                                if (!form.getFieldValue('request_template')) {
                                  form.setFieldValue('request_template', '{"model": "{{ model }}", "prompt": "{{ prompt }}"}')
                                }
                                message.success('已填充 ModelScope 异步生图配置')
                              }}
                            >
                              填充 ModelScope
                            </Button>
                          </div>

                          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.async_enabled !== curr.async_enabled}>
                            {({ getFieldValue }) => getFieldValue('async_enabled') ? (
                              <>
                                <Alert
                                  type="info"
                                  showIcon
                                  message="异步任务模式"
                                  description="开启后，生成接口先返回 task_id，前端通过 /images/tasks/{task_id} 轮询结果；保存时这些字段会写入 response_config.async_config。"
                                  style={{ marginBottom: 12 }}
                                />
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
                                  <Form.Item name="async_task_id_path" label={<span style={{ color: THEME.textPrimary }}>Task ID 路径</span>} style={{ marginBottom: 8 }}>
                                    <Input placeholder="$.task_id" />
                                  </Form.Item>
                                  <Form.Item name="async_poll_endpoint" label={<span style={{ color: THEME.textPrimary }}>轮询 Endpoint</span>} style={{ marginBottom: 8 }}>
                                    <Input placeholder="/v1/tasks/{task_id}" />
                                  </Form.Item>
                                  <Form.Item name="async_poll_method" label={<span style={{ color: THEME.textPrimary }}>轮询 Method</span>} style={{ marginBottom: 8 }}>
                                    <Select options={[{ value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' }]} />
                                  </Form.Item>
                                  <Form.Item name="async_status_path" label={<span style={{ color: THEME.textPrimary }}>状态路径</span>} style={{ marginBottom: 8 }}>
                                    <Input placeholder="$.task_status" />
                                  </Form.Item>
                                  <Form.Item name="async_done_value" label={<span style={{ color: THEME.textPrimary }}>完成值</span>} style={{ marginBottom: 8 }}>
                                    <Input placeholder="SUCCEED" />
                                  </Form.Item>
                                  <Form.Item name="async_failed_value" label={<span style={{ color: THEME.textPrimary }}>失败值</span>} style={{ marginBottom: 8 }}>
                                    <Input placeholder="FAILED" />
                                  </Form.Item>
                                </div>
                                <Form.Item name="async_images_path" label={<span style={{ color: THEME.textPrimary }}>图片结果路径</span>} style={{ marginBottom: 8 }}>
                                  <Input placeholder="$.output_images[*]" />
                                </Form.Item>
                                <Form.Item name="async_error_path" label={<span style={{ color: THEME.textPrimary }}>错误信息路径</span>} style={{ marginBottom: 8 }}>
                                  <Input placeholder="$.message" />
                                </Form.Item>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
                                  <Form.Item name="async_poll_interval" label={<span style={{ color: THEME.textPrimary }}>轮询间隔 (秒)</span>} style={{ marginBottom: 8 }}>
                                    <InputNumber min={1} max={60} style={{ width: '100%' }} />
                                  </Form.Item>
                                  <Form.Item name="async_max_wait" label={<span style={{ color: THEME.textPrimary }}>最大等待 (秒)</span>} style={{ marginBottom: 8 }}>
                                    <InputNumber min={10} max={3600} style={{ width: '100%' }} />
                                  </Form.Item>
                                </div>
                                <Form.Item name="async_request_headers" label={<span style={{ color: THEME.textPrimary }}>创建请求 Header (JSON)</span>} style={{ marginBottom: 8 }}>
                                  <TextArea rows={2} placeholder='{"X-ModelScope-Async-Mode":"true"}' />
                                </Form.Item>
                                <Form.Item name="async_poll_headers" label={<span style={{ color: THEME.textPrimary }}>轮询 Header (JSON)</span>} style={{ marginBottom: 0 }}>
                                  <TextArea rows={2} placeholder='{"X-ModelScope-Task-Type":"image_generation"}' />
                                </Form.Item>
                              </>
                            ) : null}
                          </Form.Item>
                        </div>
                      )}

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0 16' }}>
                        <Form.Item 
                          name="supported_sizes" 
                          label={<span style={{ color: THEME.textPrimary }}>支持的尺寸/比例</span>} 
                          style={{ marginBottom: 8, gridColumn: 'span 3' }}
                        >
                          <SizeConfigField />
                        </Form.Item>
                        <Form.Item 
                          name="reference_image_field" 
                          label={
                            <span style={{ color: THEME.textPrimary }}>
                              参考图占位符
                              <Tooltip title="逗号分隔的字段名，如 image1,image2,image。模板中需要有对应空占位符">
                                <QuestionCircleOutlined style={{ marginLeft: 4, color: THEME.textSecondary }} />
                              </Tooltip>
                            </span>
                          } 
                          style={{ marginBottom: 8 }}
                        >
                          <Input placeholder="如: image1,image2,image" />
                        </Form.Item>
                        <Form.Item name="support_reference_image" label={<span style={{ color: THEME.textPrimary }}>支持参考图</span>} valuePropName="checked" style={{ marginBottom: 8 }}>
                          <Switch checkedChildren="是" unCheckedChildren="否" />
                        </Form.Item>
                      </div>

                      <Form.Item
                        name="reference_image_array_field"
                        label={
                          <span style={{ color: THEME.textPrimary }}>
                            参考图数组字段
                            <Tooltip title="所有参考图组成数组放入该字段。支持嵌套路径，如 reference.images。优先级高于占位符模式">
                              <QuestionCircleOutlined style={{ marginLeft: 4, color: THEME.textSecondary }} />
                            </Tooltip>
                          </span>
                        }
                        style={{ marginBottom: 8 }}
                      >
                        <Input placeholder="如: images 或 reference.images" />
                      </Form.Item>

                      <Form.Item name="default_params" label={<span style={{ color: THEME.textPrimary }}>默认参数 (JSON)</span>} style={{ marginBottom: 0 }}
                        extra={<span style={{ color: THEME.textSecondary, fontSize: 12 }}>
                          参数名映射：size_param 指定尺寸字段名，seed_param 指定种子字段名；OpenAI SDK 图片接口如需强制 base64 返回，可加 <code>{'{"response_format":"b64_json"}'}</code>。
                        </span>}
                      >
                        <TextArea 
                          rows={2} 
                          placeholder={`JSON 格式的默认参数，例如：\n{"n": 1, "response_format": "b64_json", "size_param": "image_size", "seed_param": "seed"}`}
                        />
                      </Form.Item>
                    </div>
                  ),
                },
              ]}
            />
          ) : null}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0 16' }}>
            <Form.Item name="is_active" label={<span style={{ color: THEME.textPrimary }}>启用状态</span>} valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="禁用" />
            </Form.Item>
            <Form.Item name="is_default" label={<span style={{ color: THEME.textPrimary }}>设为默认</span>} valuePropName="checked">
              <Switch checkedChildren="是" unCheckedChildren="否" />
            </Form.Item>
            <Form.Item name="priority" label={<span style={{ color: THEME.textPrimary }}>优先级</span>}>
              <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="0 = 最低优先级" />
            </Form.Item>
          </div>
        </Form>
      </Modal>

      {/* 详情查看 Modal */}
      {viewingProvider && (
        <Modal
          title="AI 模型详情"
          open={!!viewingProvider}
          onCancel={() => setViewingProvider(null)}
          footer={[
            <Button key="close" size="small" onClick={() => setViewingProvider(null)}>关闭</Button>,
            <Button key="edit" type="primary" size="small" onClick={() => {
              setViewingProvider(null)
              handleEdit(viewingProvider)
            }}>编辑</Button>,
          ]}
          width={650}
        >
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 24px', marginBottom: 16 }}>
              <div>
                <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>标识符</Text>
                <div style={{ color: THEME.textPrimary, marginTop: 2 }}>{viewingProvider.id}</div>
              </div>
              <div>
                <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>显示名称</Text>
                <div style={{ color: THEME.textPrimary, marginTop: 2 }}>{viewingProvider.name}</div>
              </div>
              <div>
                <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>底层服务商</Text>
                <div style={{ marginTop: 2 }}>
                  <Tag style={{ background: `${getProviderColor(viewingProvider.provider || '')}22`, border: `1px solid ${getProviderColor(viewingProvider.provider || '')}44`, color: getProviderColor(viewingProvider.provider || '') }}>
                    {viewingProvider.provider}
                  </Tag>
                </div>
              </div>
              <div>
                <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>类型</Text>
                <div style={{ marginTop: 2 }}>
                  <Tag color={viewingProvider.provider_type === 'llm' ? 'blue' : viewingProvider.provider_type === 'image' ? 'purple' : 'default'}>
                    {viewingProvider.provider_type}
                  </Tag>
                </div>
              </div>
            </div>

            <Card size="small" style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${THEME.border}`, marginBottom: 12 }}>
              <Title level={5} style={{ color: THEME.textPrimary, fontSize: 13, marginBottom: 8 }}>连接配置</Title>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 24px' }}>
                <div>
              <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>API Key</Text>
              <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.api_key || <Text type="secondary" style={{ fontSize: 12 }}>未设置</Text>}</div>
            </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>Base URL</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.base_url || <Text type="secondary" style={{ fontSize: 12 }}>未设置</Text>}</div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>API Endpoint</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.api_endpoint || <Text type="secondary" style={{ fontSize: 12 }}>未设置</Text>}</div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>默认模型</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.default_model || <Text type="secondary" style={{ fontSize: 12 }}>未设置</Text>}</div>
                </div>
                {viewingProvider.provider_type === 'llm' && (
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>最大 Token 数</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.max_tokens || 4096}</div>
                </div>
                )}
                {viewingProvider.provider_type === 'llm' && (
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>温度参数</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.temperature ?? 0.7}</div>
                </div>
                )}
                <div style={{ gridColumn: '1 / -1' }}>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>测试提示词</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.test_prompt || <Text type="secondary" style={{ fontSize: 12 }}>未设置（使用默认值）</Text>}</div>
                </div>
              </div>
            </Card>

            {(viewingProvider.provider_type === 'image' || viewingProvider.provider_type === 'video') && (
            <Card size="small" style={{ background: 'rgba(168,85,247,0.05)', border: '1px solid rgba(168,85,247,0.2)', marginBottom: 12 }}>
              <Title level={5} style={{ color: '#a855f7', fontSize: 13, marginBottom: 8 }}>生成配置</Title>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
                {viewingProvider.request_template && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>Request 模板</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13, whiteSpace: 'pre-wrap', fontFamily: 'monospace', background: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 4 }}>{viewingProvider.request_template}</div>
                </div>
                )}
                {viewingProvider.response_config && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>Response 解析配置</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13, whiteSpace: 'pre-wrap', fontFamily: 'monospace', background: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 4 }}>{viewingProvider.response_config}</div>
                </div>
                )}
                {viewingProvider.supported_sizes && viewingProvider.supported_sizes.length > 0 && (
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>支持尺寸</Text>
                  <div style={{ marginTop: 2 }}>{viewingProvider.supported_sizes.map((s: string) => <Tag key={s} style={{ fontSize: 12 }}>{s}</Tag>)}</div>
                </div>
                )}
                {viewingProvider.price_per_call != null && (
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>按次计费</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>${viewingProvider.price_per_call}/次</div>
                </div>
                )}
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>参考图</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.support_reference_image ? '支持' : '不支持'}</div>
                </div>
                {viewingProvider.reference_image_field && (
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>参考图字段</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.reference_image_field}</div>
                </div>
                )}
              </div>
            </Card>
            )}

            <Card size="small" style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${THEME.border}`, marginBottom: 12 }}>
              <Title level={5} style={{ color: THEME.textPrimary, fontSize: 13, marginBottom: 8 }}>状态与统计</Title>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px 16px' }}>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>启用状态</Text>
                  <div style={{ marginTop: 2 }}>
                    <Badge 
                      status={viewingProvider.is_active ? 'success' : 'default'} 
                      text={<span style={{ color: viewingProvider.is_active ? THEME.success : THEME.textSecondary }}>{viewingProvider.is_active ? '启用' : '禁用'}</span>} 
                    />
                  </div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>默认模型</Text>
                  <div style={{ marginTop: 2 }}>
                    <Tag color={viewingProvider.is_default ? 'gold' : 'default'}>{viewingProvider.is_default ? '是' : '否'}</Tag>
                  </div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>优先级</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.priority || 0}</div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>使用次数</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.usage_count || 0}</div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>总费用</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>${(viewingProvider.total_cost || 0).toFixed(4)}</div>
                </div>
                <div>
                  <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>最后使用</Text>
                  <div style={{ color: THEME.textPrimary, marginTop: 2, fontSize: 13 }}>{viewingProvider.last_used ? new Date(viewingProvider.last_used).toLocaleString('zh-CN') : '从未使用'}</div>
                </div>
              </div>
            </Card>

            {viewingProvider.description && (
              <Card size="small" style={{ background: 'rgba(255,255,255,0.03)', border: `1px solid ${THEME.border}` }}>
                <Title level={5} style={{ color: THEME.textPrimary, fontSize: 13, marginBottom: 8 }}>备注说明</Title>
                <Text style={{ color: THEME.textPrimary, fontSize: 13 }}>{viewingProvider.description}</Text>
              </Card>
            )}
          </div>
        </Modal>
      )}

      {testResult && (
        <Modal
          title="模型测试详情"
          open={!!testResult}
          onCancel={() => setTestResult(null)}
          footer={[
            <Button key="close" size="small" onClick={() => setTestResult(null)}>关闭</Button>,
          ]}
          width={860}
          styles={{ body: { paddingTop: 12 } }}
        >
          <Alert
            type={testResult.success ? 'success' : 'error'}
            showIcon
            message={testResult.success ? '本次测试已真实发出请求' : '本次测试请求已发出，但结果失败'}
            description={testResult.message}
            style={{ marginBottom: 16 }}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
            <Card size="small" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
              <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>方法</Text>
              <div style={{ color: THEME.textPrimary, marginTop: 4, fontWeight: 600 }}>
                {testResult.debug?.request?.method || '-'}
              </div>
            </Card>
            <Card size="small" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
              <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>响应状态</Text>
              <div style={{ color: THEME.textPrimary, marginTop: 4, fontWeight: 600 }}>
                {testResult.debug?.response?.status_code ?? '-'}
              </div>
            </Card>
            <Card size="small" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
              <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>耗时</Text>
              <div style={{ color: THEME.textPrimary, marginTop: 4, fontWeight: 600 }}>
                {testResult.debug?.latency_ms != null ? `${testResult.debug.latency_ms} ms` : '-'}
              </div>
            </Card>
          </div>

          <Card size="small" title="请求 URL" style={{ marginBottom: 12, background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
            <Text style={{ color: THEME.textPrimary, wordBreak: 'break-all' }}>
              {testResult.debug?.request?.url || '-'}
            </Text>
          </Card>

          <Card size="small" title="请求头" style={{ marginBottom: 12, background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
            <TextArea
              readOnly
              value={stringifyDebugValue(testResult.debug?.request?.headers)}
              autoSize={{ minRows: 4, maxRows: 10 }}
              style={{ fontFamily: 'Consolas, Monaco, monospace' }}
            />
          </Card>

          <Card size="small" title="请求体" extra={
            <Button type="primary" size="small" onClick={handleRetest}>
              重新测试
            </Button>
          } style={{ marginBottom: 12, background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
            <TextArea
              value={editableRequestBody}
              onChange={(e) => setEditableRequestBody(e.target.value)}
              autoSize={{ minRows: 6, maxRows: 14 }}
              style={{ fontFamily: 'Consolas, Monaco, monospace' }}
            />
          </Card>

          {/* 图片预览 */}
          {testResult.debug?.response?.body && (() => {
            const imageUrls = extractImageUrls(testResult.debug.response.body)
            if (imageUrls.length > 0) {
              return (
                <Card size="small" title="生成的图片" style={{ marginBottom: 12, background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
                    {imageUrls.map((url, idx) => (
                      <div 
                        key={idx} 
                        style={{ 
                          textAlign: 'center', 
                          cursor: 'pointer'
                        }}
                        onClick={() => setPreviewImageUrl(url)}
                      >
                        <img 
                          src={url} 
                          alt={`Generated image ${idx + 1}`}
                          style={{ 
                            width: '100%', 
                            maxHeight: 200, 
                            objectFit: 'contain',
                            borderRadius: 8,
                            border: `1px solid ${THEME.border}`
                          }} 
                        />
                        <div style={{ 
                          fontSize: 12, 
                          color: THEME.textSecondary, 
                          marginTop: 4 
                        }}>
                          点击查看大图
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )
            }
            return null
          })()}
          
          <Card size="small" title="响应体" style={{ marginBottom: 0, background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
            <TextArea
              readOnly
              value={stringifyDebugValue(testResult.debug?.response?.body || testResult.debug?.exception)}
              autoSize={{ minRows: 8, maxRows: 18 }}
              style={{ fontFamily: 'Consolas, Monaco, monospace' }}
            />
          </Card>
        </Modal>
      )}

      {/* 图片悬浮预览 */}
      {previewImageUrl && (
        <Modal
          open={true}
          onCancel={() => setPreviewImageUrl(null)}
          footer={null}
          width="auto"
          style={{ maxWidth: '90vw' }}
          centered
          closable
        >
          <div style={{ textAlign: 'center' }}>
            <img 
              src={previewImageUrl} 
              alt="Preview" 
              style={{ 
                maxWidth: '100%', 
                maxHeight: '80vh', 
                objectFit: 'contain' 
              }} 
            />
          </div>
        </Modal>
      )}
    </div>
  )
}

function VideoSettings() {
  const { theme: THEME } = useTheme()
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const { message } = AntApp.useApp()

  useEffect(() => {
    getSettings().then(({ data }) => {
      form.setFieldsValue({ ffmpeg_path: data.data.ffmpeg_path || '' })
    }).catch(() => {})
  }, [form])

  const handleSave = async (values: any) => {
    setSaving(true)
    try {
      await updateSettings(values)
      message.success('保存成功')
    } catch (e: any) {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
      <Title level={5} style={{ color: THEME.textPrimary }}>FFmpeg 配置</Title>
      <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
        <Form.Item label={<span style={{ color: THEME.textPrimary }}>FFmpeg 路径</span>} name="ffmpeg_path">
          <Input placeholder="留空则自动检测" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>保存设置</Button>
        </Form.Item>
      </Form>
    </Card>
  )
}

function TranscribeSettings() {
  const { theme: THEME } = useTheme()
  return (
    <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
      <Title level={5} style={{ color: THEME.textPrimary }}>Whisper 配置</Title>
      <Form layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item label={<span style={{ color: THEME.textPrimary }}>识别后端</span>}>
          <Select defaultValue="auto" options={[
            { value: 'auto', label: '自动选择' },
            { value: 'siliconflow', label: 'SiliconFlow API (云端)' },
          ]} style={{ width: 300 }} />
        </Form.Item>
        <Form.Item label={<span style={{ color: THEME.textPrimary }}>默认语言</span>}>
          <Input defaultValue="zh" placeholder="zh / en / auto" />
        </Form.Item>
        <Form.Item>
          <Button type="primary">保存设置</Button>
        </Form.Item>
      </Form>
    </Card>
  )
}

function StorageSettings() {
  const { theme: THEME } = useTheme()
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)
  const { message } = AntApp.useApp()

  useEffect(() => {
    getSettings()
      .then(({ data }) => {
        form.setFieldsValue({
          storage_type: data.data.storage_type || 'local',
          // 新配置（数据库优先）
          video_download_path: data.data.video_download_path || '',
          image_gen_path: data.data.image_gen_path || '',
          video_gen_path: data.data.video_gen_path || '',
          reference_image_path: data.data.reference_image_path || '',
          upload_path: data.data.upload_path || '',
          // 兼容旧配置
          download_path: data.data.download_path || '',
          media_storage_path: data.data.media_storage_path || '',
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [form])

  const handleSave = async (values: any) => {
    setSaving(true)
    try {
      await updateSettings(values)
      message.success('保存成功')
    } catch (e: any) {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Skeleton active paragraph={{ rows: 8 }} />

  return (
    <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
      <Title level={5} style={{ color: THEME.textPrimary }}>存储配置</Title>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 16 }}>
        配置为空时使用默认路径。存储路径优先级：数据库配置 &gt; 配置文件
      </Paragraph>
      <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>内容下载根目录</span>} name="video_download_path" extra={<span style={{ color: THEME.textSecondary, fontSize: 11 }}>公众号文章、平台视频和本地阅读器的默认下载根目录；文件会按平台或来源保存到子目录</span>}>
              <Input placeholder="/workspace/backend/downloads" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>AI 图片生成</span>} name="image_gen_path" extra={<span style={{ color: THEME.textSecondary, fontSize: 11 }}>文生图、图生图生成的图片保存路径</span>}>
              <Input placeholder="/workspace/backend/storage/images" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>AI 视频生成</span>} name="video_gen_path" extra={<span style={{ color: THEME.textSecondary, fontSize: 11 }}>AI视频生成保存路径</span>}>
              <Input placeholder="/workspace/backend/storage/videos" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>参考图存储</span>} name="reference_image_path" extra={<span style={{ color: THEME.textSecondary, fontSize: 11 }}>图生图参考图保存路径</span>}>
              <Input placeholder="/workspace/backend/storage/reference_images" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>本地上传</span>} name="upload_path" extra={<span style={{ color: THEME.textSecondary, fontSize: 11 }}>素材库本地上传文件保存路径</span>}>
              <Input placeholder="/workspace/backend/storage/uploads" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>保存设置</Button>
        </Form.Item>
      </Form>
    </Card>
  )
}
