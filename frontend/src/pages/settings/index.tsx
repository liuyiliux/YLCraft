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
  message,
  Typography,
  Space,
  Popconfirm,
  Alert,
  Skeleton,
  Steps,
  InputNumber,
} from 'antd'
import {
  SettingOutlined,
  ApiOutlined,
  VideoCameraOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  KeyOutlined,
} from '@ant-design/icons'
import { listProviders, testProviderConnection, getSettings, updateSettings, listCookies, saveCookie, deleteCookie, testCookie } from '../../api'
import type { Provider } from '../../types/api'

const { Title, Text } = Typography
const { TextArea } = Input

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('providers')
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null)
  const [form] = Form.useForm()

  const loadProviders = async () => {
    setLoading(true)
    try {
      const { data } = await listProviders()
      setProviders(data.providers || [])
    } catch {
      message.error('加载 Provider 失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProviders()
  }, [])

  const handleTest = async (key: string) => {
    const hide = message.loading('正在测试连接...', 0)
    try {
      await testProviderConnection(key)
      hide()
      message.success('连接测试成功')
    } catch (e: any) {
      hide()
      const errorMsg = e?.response?.data?.detail || '连接测试失败，请检查 API Key 和网络'
      message.error(errorMsg)
    }
  }

  const handleEdit = (provider: Provider) => {
    setEditingProvider(provider)
    form.setFieldsValue({
      key: provider.key,
      name: provider.name,
      media_type: provider.media_type,
      enabled: provider.enabled,
      base_url: provider.base_url || '',
    })
    setModalVisible(true)
  }

  const handleAdd = () => {
    setEditingProvider(null)
    form.resetFields()
    form.setFieldsValue({ enabled: true })
    setModalVisible(true)
  }

  const handleSave = async (values: any) => {
    console.log('Save provider:', values)
    message.success('保存成功')
    setModalVisible(false)
    loadProviders()
  }

  const providerColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Provider) => (
        <Space>
          <Text style={{ color: '#fff' }}>{text}</Text>
          <Tag style={{ background: 'rgba(255,255,255,0.06)', border: 'none', color: '#8b8ba8' }}>
            {record.key}
          </Tag>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'media_type',
      key: 'media_type',
      render: (type: string) => {
        const colors: Record<string, string> = { text: '#00d4ff', image: '#a855f7', audio: '#f59e0b', video: '#ef4444' }
        return (
          <Tag style={{ background: `${colors[type] || '#8b8ba8'}22`, border: `1px solid ${colors[type] || '#8b8ba8'}44`, color: colors[type] || '#8b8ba8' }}>
            {type?.toUpperCase()}
          </Tag>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'success' : 'default'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Provider) => (
        <Space>
          <Button type="text" icon={<PlayCircleOutlined />} onClick={() => handleTest(record.key)} style={{ color: '#00d4ff' }}>
            测试
          </Button>
          <Button type="text" icon={<EditOutlined />} onClick={() => handleEdit(record)} style={{ color: '#8b8ba8' }}>
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => message.info('删除功能待实现')}>
            <Button type="text" icon={<DeleteOutlined />} danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1200 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        <SettingOutlined style={{ marginRight: 12 }} />
        系统设置
      </Title>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        items={[
          {
            key: 'providers',
            label: (
              <span><ApiOutlined style={{ marginRight: 8 }} />Provider 管理</span>
            ),
            children: (
              <Card
                title={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ color: '#fff' }}>AI Provider 配置</Text>
                    <Space>
                      <Button icon={<ReloadOutlined />} onClick={loadProviders} loading={loading}>刷新</Button>
                      <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增 Provider</Button>
                    </Space>
                  </div>
                }
                style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)' }}
              >
                <Alert
                  type="info"
                  showIcon
                  message="Provider 是 AI 服务的接入点，支持 LLM、图像生成、TTS 等多种类型"
                  style={{ marginBottom: 16, background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.2)' }}
                />
                {loading ? (
                  <Skeleton active paragraph={{ rows: 5 }} />
                ) : providers.length === 0 ? (
                  <Space direction="vertical" style={{ width: '100%', textAlign: 'center', padding: '40px 0' }}>
                    <Text style={{ color: '#8b8ba8' }}>暂无 Provider 配置</Text>
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增 Provider</Button>
                  </Space>
                ) : (
                  <Table dataSource={providers} columns={providerColumns} rowKey="key" pagination={false} style={{ background: 'transparent' }} />
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
            key: 'cookies',
            label: <span><KeyOutlined style={{ marginRight: 8 }} />Cookie 管理</span>,
            children: <CookieSettings />,
          },
          {
            key: 'storage',
            label: <span><DatabaseOutlined style={{ marginRight: 8 }} />存储设置</span>,
            children: <StorageSettings />,
          },
        ]}
      />

      <Modal
        title={editingProvider ? '编辑 Provider' : '新增 Provider'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
          <Form.Item name="key" label="标识符" rules={[{ required: true, message: '请输入标识符' }]}>
            <Input placeholder="如：openai-gpt4" disabled={!!editingProvider} />
          </Form.Item>
          <Form.Item name="name" label="显示名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：OpenAI GPT-4" />
          </Form.Item>
          <Form.Item name="media_type" label="类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'text', label: '文本 (LLM)' },
              { value: 'image', label: '图像生成' },
              { value: 'audio', label: '语音 (TTS)' },
              { value: 'video', label: '视频生成' },
            ]} />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password placeholder={editingProvider ? '留空表示不修改' : '请输入 API Key'} />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function VideoSettings() {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)

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
    <Card style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)' }}>
      <Title level={5} style={{ color: '#fff' }}>FFmpeg 配置</Title>
      <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
        <Form.Item label="FFmpeg 路径" name="ffmpeg_path">
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
  return (
    <Card style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)' }}>
      <Title level={5} style={{ color: '#fff' }}>Whisper 配置</Title>
      <Form layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item label="识别后端">
          <Select defaultValue="auto" options={[
            { value: 'auto', label: '自动选择' },
            { value: 'siliconflow', label: 'SiliconFlow API (云端)' },
          ]} style={{ width: 300 }} />
        </Form.Item>
        <Form.Item label="默认语言">
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
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getSettings()
      .then(({ data }) => {
        form.setFieldsValue({
          storage_type: data.data.storage_type || 'local',
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

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />

  return (
    <Card style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)' }}>
      <Title level={5} style={{ color: '#fff' }}>存储配置</Title>
      <Form form={form} layout="vertical" onFinish={handleSave} style={{ marginTop: 16 }}>
        <Form.Item label="存储类型" name="storage_type">
          <Select options={[
            { value: 'local', label: '本地存储' },
            { value: 's3', label: 'AWS S3（预留）' },
            { value: 'oss', label: '阿里云 OSS（预留）' },
          ]} style={{ width: 300 }} />
        </Form.Item>
        <Form.Item label="下载文件保存路径" name="download_path" extra="视频下载后保存的目录">
          <Input placeholder="例如：F:\YLCraft-Downloads" style={{ width: 400 }} />
        </Form.Item>
        <Form.Item label="素材库存储路径" name="media_storage_path" extra="图片、视频等素材的存储目录">
          <Input placeholder="例如：F:\YLCraft-Media" style={{ width: 400 }} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>保存设置</Button>
        </Form.Item>
      </Form>
    </Card>
  )
}

function CookieSettings() {
  const [activePlatform, setActivePlatform] = useState<string>('douyin')
  const [cookieData, setCookieData] = useState<Record<string, any>>({})
  const [rawInput, setRawInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)

  const platforms: Record<string, { name: string; color: string; steps: string[] }> = {
    douyin: {
      name: '抖音', color: '#fe2c55',
      steps: [
        '1. 打开抖音并登录（https://www.douyin.com）',
        '2. 按 F12 打开开发者工具，点击 Network 标签',
        '3. 刷新页面或点击任意视频',
        '4. 在 Network 列表中找到任意请求',
        '5. 点击该请求 → Headers 面板',
        '6. 找到 Request Headers 中的 Cookie 字段',
        '7. 复制整个 Cookie 值，粘贴到下方文本框',
      ],
    },
    bilibili: {
      name: '哔哩哔哩', color: '#00a1d6',
      steps: [
        '1. 打开 B站并登录（https://www.bilibili.com）',
        '2. 按 F12 → Network 标签',
        '3. 刷新页面，找到任意请求',
        '4. 查看 Headers → Request Headers → Cookie',
        '5. 复制完整 Cookie 值',
      ],
    },
    kuaishou: { name: '快手', color: '#ff4906', steps: ['同抖音流程，获取 Cookie 字段'] },
    xiaohongshu: { name: '小红书', color: '#fe2c55', steps: ['同抖音流程，获取 Cookie 字段'] },
    weibo: { name: '微博', color: '#e61432', steps: ['同抖音流程，获取 Cookie 字段'] },
    youtube: { name: 'YouTube', color: '#ff0000', steps: ['同抖音流程，获取 Cookie 字段'] },
  }

  const loadStatus = async () => {
    setLoading(true)
    try {
      const { data } = await listCookies()
      setCookieData(data.cookies || {})
    } catch {
      message.error('加载 Cookie 状态失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStatus() }, [])

  const handleSave = async () => {
    if (!rawInput.trim()) { message.warning('请先粘贴 Cookie 内容'); return }
    setSaving(true)
    try {
      await saveCookie(activePlatform, rawInput)
      message.success('Cookie 保存成功！')
      setRawInput('')
      setTestMsg(null)
      loadStatus()
    } catch (e: any) {
      message.error('保存失败：' + (e?.response?.data?.detail || String(e)))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestMsg(null)
    try {
      const { data } = await testCookie(activePlatform)
      setTestMsg({ ok: data.success, text: data.message })
    } catch (e: any) {
      setTestMsg({ ok: false, text: '测试失败' })
    } finally {
      setTesting(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteCookie(activePlatform)
      message.success('Cookie 已删除')
      setRawInput('')
      setTestMsg(null)
      loadStatus()
    } catch (e: any) {
      message.error('删除失败')
    } finally {
      setDeleting(false)
    }
  }

  const currentStatus = cookieData[activePlatform]
  const platformInfo = platforms[activePlatform]

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message="Cookie 为可选配置。公开放送视频无需登录即可下载；配置 Cookie 可解锁高清画质、私密/收藏夹内容。保存后自动注入，无需重启服务。"
        style={{ marginBottom: 16, background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.2)' }}
      />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
        {Object.entries(platforms).map(([key, p]) => {
          const status = cookieData[key]
          return (
            <Card
              key={key}
              size="small"
              onClick={() => { setActivePlatform(key); setRawInput(''); setTestMsg(null) }}
              style={{
                cursor: 'pointer',
                background: activePlatform === key ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.03)',
                border: activePlatform === key ? `1px solid ${p.color}` : '1px solid rgba(255,255,255,0.08)',
                minWidth: 90,
                textAlign: 'center',
              }}
              bodyStyle={{ padding: '10px 14px' }}
            >
              <Text style={{ color: activePlatform === key ? p.color : '#fff', fontWeight: activePlatform === key ? 600 : 400 }}>{p.name}</Text>
              <div style={{ marginTop: 4 }}>
                {status?.configured ? <Tag color="success" style={{ fontSize: 11 }}>已配置</Tag> : <Tag style={{ fontSize: 11, background: 'rgba(255,255,255,0.06)', border: 'none', color: '#8b8ba8' }}>未配置</Tag>}
              </div>
            </Card>
          )
        })}
      </div>

      <Card style={{ background: '#1a1a2e', border: `1px solid ${platformInfo.color}44` }} bodyStyle={{ padding: 24 }}>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: '0 0 320px' }}>
            <Title level={5} style={{ color: '#fff', marginBottom: 12 }}>如何获取 {platformInfo.name} Cookie</Title>
            <Steps direction="vertical" size="small" current={-1} items={platformInfo.steps.map((step, i) => ({ title: <Text style={{ color: '#c0c0d0', fontSize: 13 }}>{step}</Text> }))} />
          </div>
          <div style={{ flex: 1, minWidth: 300 }}>
            <Title level={5} style={{ color: '#fff', marginBottom: 12 }}>配置 {platformInfo.name} Cookie</Title>
            {currentStatus?.configured ? (
              <Alert type="success" showIcon message={`已配置（${currentStatus.size} bytes）`} style={{ marginBottom: 12, background: 'rgba(82,196,26,0.08)', border: '1px solid rgba(82,196,26,0.2)' }} />
            ) : (
              <Alert type="warning" showIcon message="该平台尚未配置 Cookie，将无法解析需要登录的内容" style={{ marginBottom: 12, background: 'rgba(250,173,20,0.08)', border: '1px solid rgba(250,173,20,0.2)' }} />
            )}
            <Text style={{ color: '#8b8ba8', fontSize: 13, display: 'block', marginBottom: 10 }}>
              将浏览器中的 Cookie header 内容粘贴到下方（支持原始格式和插件导出格式，自动识别）
            </Text>
            <TextArea value={rawInput} onChange={e => setRawInput(e.target.value)} rows={7} style={{ marginBottom: 12, fontFamily: 'monospace', fontSize: 12 }} placeholder="粘贴 Cookie 内容..." />
            {testMsg && <Alert type={testMsg.ok ? 'success' : 'error'} showIcon message={testMsg.text} style={{ marginBottom: 12 }} />}
            <Space>
              <Button type="primary" onClick={handleSave} loading={saving} style={{ background: platformInfo.color, borderColor: platformInfo.color }}>保存 Cookie</Button>
              <Button onClick={handleTest} loading={testing} disabled={!currentStatus?.configured}>测试有效性</Button>
              <Popconfirm title="确认删除该平台的 Cookie？" onConfirm={handleDelete} okText="删除" cancelText="取消">
                <Button danger loading={deleting} disabled={!currentStatus?.configured}>删除</Button>
              </Popconfirm>
            </Space>
          </div>
        </div>
      </Card>
    </div>
  )
}
