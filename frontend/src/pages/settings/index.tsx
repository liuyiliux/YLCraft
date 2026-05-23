import { useState, useEffect } from 'react'
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
  SearchOutlined,
  CopyOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { listConnectors, createConnector, updateConnector, deleteConnector, testConnector, getSettings, updateSettings } from '../../api'
import type { Provider, PROVIDER_OPTIONS, ConnectorTestResult } from '../../types/api'
import { useTheme } from '../../constants/theme'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// 计算宽高比例
function calculateAspectRatio(size: string): string {
  const match = size.match(/(\d+)\s*[x*]\s*(\d+)/i)
  if (!match) return ''
  
  const width = parseInt(match[1])
  const height = parseInt(match[2])
  
  const gcd = (a: number, b: number): number => b === 0 ? a : gcd(b, a % b)
  const divisor = gcd(width, height)
  
  const ratioWidth = width / divisor
  const ratioHeight = height / divisor
  
  if (ratioWidth > ratioHeight && ratioHeight === 1) {
    return `${ratioWidth}:1`
  }
  return `${ratioWidth}:${ratioHeight}`
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
}

// ==================== 组件 ====================
export default function SettingsPage() {
  const { theme: THEME } = useTheme()
  const [activeTab, setActiveTab] = useState('models')
  const [providers, setProviders] = useState<Provider[]>([])
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
  const [form] = Form.useForm()
  const { message } = AntApp.useApp()
  const selectedType = Form.useWatch('provider_type', form)

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

  useEffect(() => {
    loadProviders()
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
      test_prompt: provider.test_prompt || '',
    })
    setModalVisible(true)
  }

  const handleView = (provider: Provider) => {
    setViewingProvider(provider)
  }

  const handleAdd = () => {
    setEditingProvider(null)
    form.resetFields()
    // 自动生成唯一标识符
    const generatedId = `connector-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`
    form.setFieldsValue({ 
      id: generatedId,
      is_active: true 
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

      if (editingProvider) {
        // 更新现有连接器
        await updateConnector(editingProvider.id, processedValues)
        message.success('AI 模型更新成功')
      } else {
        // 创建新连接器
        await createConnector(processedValues)
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
    })
    setModalVisible(true)
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
    // 最后尝试单个 url
    else if (obj.url) {
      urls.push(obj.url)
    }
    
    // 去重
    return [...new Set(urls)]
  }

  const providerColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 280,
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
      title: '提供商',
      dataIndex: 'provider',
      key: 'provider',
      width: 120,
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
      title: '类型',
      dataIndex: 'provider_type',
      key: 'provider_type',
      width: 100,
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
      title: '模型',
      dataIndex: 'default_model',
      key: 'default_model',
      width: 150,
      render: (model: string) => model ? (
        <Tag style={{ background: 'rgba(255,255,255,0.06)', border: 'none', color: THEME.textSecondary }}>
          {model}
        </Tag>
      ) : <Text type="secondary" style={{ fontSize: 12 }}>未设置</Text>,
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_: any, record: Provider) => (
        <Badge 
          status={record.is_active ? 'success' : 'default'} 
          text={<span style={{ color: record.is_active ? THEME.success : THEME.textSecondary }}>{record.is_active ? '启用' : '禁用'}</span>} 
        />
      ),
    },
    {
      title: '使用统计',
      key: 'usage',
      width: 180,
      render: (_: any, record: Provider) => (
        <div style={{ display: 'flex', gap: 12 }}>
          <Text style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'nowrap' }}>使用: {record.usage_count || 0}</Text>
          <Text style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'nowrap' }}>费用: ${((record.total_cost || 0)).toFixed(4)}</Text>
        </div>
      ),
    },
    {
      title: '最后使用',
      dataIndex: 'last_used',
      key: 'last_used',
      width: 140,
      render: (time: string) => time ? (
        <Text style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'nowrap' }}>{new Date(time).toLocaleDateString('zh-CN')}</Text>
      ) : <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>从未使用</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 300,
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
                      <Button size="small" icon={<ReloadOutlined />} onClick={loadProviders} loading={loading}>刷新</Button>
                      <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
                    </Space>
                  </div>
                }
                style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
                bodyStyle={{ padding: '12px 16px' }}
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
                      scroll={{ x: 1200 }}
                      size="small"
                      components={{
                        header: {
                          cell: (props: any) => (
                            <th
                              {...props}
                              style={{
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
                options={PROVIDER_SELECT_OPTIONS} 
              />
            </Form.Item>
            <Form.Item name="name" label={<span style={{ color: THEME.textPrimary }}>显示名称</span>} rules={[{ required: true, message: '请输入名称' }]}>
              <Input placeholder="如：OpenAI GPT-4" />
            </Form.Item>
            <Form.Item name="provider_type" label={<span style={{ color: THEME.textPrimary }}>类型</span>} rules={[{ required: true, message: '请选择类型' }]}>
              <Select options={[
                { value: 'llm', label: '文本 (LLM)' },
                { value: 'image', label: '图像生成' },
                { value: 'video', label: '视频生成' },
                { value: 'tts', label: '语音合成 (TTS)' },
                { value: 'stt', label: '语音识别 (STT)' },
              ]} />
            </Form.Item>
          </div>
          
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
              <Input placeholder="gpt-4o" />
            </Form.Item>
            {selectedType === 'llm' && (
              <>
                <Form.Item name="max_tokens" label={<span style={{ color: THEME.textPrimary }}>最大 Token 数</span>}>
                  <InputNumber min={1} max={200000} style={{ width: '100%' }} placeholder="4096" />
                </Form.Item>
              </>
            )}
          </div>
          {selectedType === 'llm' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16' }}>
              <Form.Item name="temperature" label={<span style={{ color: THEME.textPrimary }}>温度参数</span>}>
                <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} placeholder="0.7" />
              </Form.Item>
              <div></div>
            </div>
          )}

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

          <Form.Item name="description" label={<span style={{ color: THEME.textPrimary }}>备注说明</span>}>
            <TextArea rows={2} placeholder="可选：记录此连接的用途、限制等" />
          </Form.Item>

          <Form.Item name="test_prompt" label={<span style={{ color: THEME.textPrimary }}>测试提示词 (可选)</span>}>
            <TextArea 
              rows={2} 
              placeholder={`LLM 模式：测试使用的提示词（默认："Reply with ok."）\nImage 模式：测试图片生成的提示词（默认："连接测试图片"）`}
            />
          </Form.Item>

          {selectedType === 'image' || selectedType === 'video' || selectedType === undefined ? (
            <div style={{ 
              marginTop: 16, 
              padding: 16, 
              background: 'rgba(168,85,247,0.05)', 
              border: '1px solid rgba(168,85,247,0.2)', 
              borderRadius: 8 
            }}>
              <Title level={5} style={{ color: '#a855f7', fontSize: 14, marginBottom: 12 }}>
                生成配置（请求模板/参考图）
              </Title>
              
              <Form.Item name="request_template" label={<span style={{ color: THEME.textPrimary }}>Request 模板 (Jinja2)</span>} style={{ marginBottom: 8 }}>
                <TextArea 
                  rows={4} 
                  placeholder={`JSON 格式的请求模板，例如：\n{"model": "{{ model }}", "prompt": "{{ prompt }}"}`}
                />
              </Form.Item>

              <Form.Item name="response_config" label={<span style={{ color: THEME.textPrimary }}>Response 解析配置</span>} style={{ marginBottom: 8 }}>
                <TextArea 
                  rows={3} 
                  placeholder={`JSON 格式的响应配置，例如：\n{"images_path": "$.data[*].url", "error_path": "$.error.message"}`}
                />
              </Form.Item>

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
                  参数名映射：size_param 指定尺寸字段名（如硅基流动用 image_size），seed_param 指定种子字段名
                </span>}
              >
                <TextArea 
                  rows={2} 
                  placeholder={`JSON 格式的默认参数，例如：\n{"n": 1, "quality": "standard", "size_param": "image_size", "seed_param": "seed"}`}
                />
              </Form.Item>
            </div>
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
            <Form.Item label={<span style={{ color: THEME.textPrimary }}>视频解析下载</span>} name="video_download_path" extra={<span style={{ color: THEME.textSecondary, fontSize: 11 }}>抖音、B站等平台视频下载保存路径</span>}>
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

