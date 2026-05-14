import { useState, useEffect, useRef, useCallback } from 'react'
import { useTheme } from '../../constants/theme'
import {
  Card,
  Table,
  Button,
  Tag,
  message,
  Space,
  Typography,
  Modal,
  Form,
  Input,
  Select,
  Popconfirm,
  Alert,
  Tooltip,
  Tabs,
  Steps,
  Spin,
  Image,
  Progress,
  Badge,
  Empty,
} from 'antd'
import {
  GlobalOutlined,
  LinkOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
  ChromeOutlined,
  QrcodeOutlined,
  CopyOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  CameraOutlined,
  DesktopOutlined,
} from '@ant-design/icons'
import {
  listPlatformConnections,
  createPlatformConnection,
  updatePlatformConnection,
  deletePlatformConnection,
  testPlatformConnection,
  getSupportedPlatforms,
  playwrightStart,
  listPlaywrightSessions,
  cancelPlaywrightSession,
  qrcodeGenerate,
  getQrcodeStatus,
  refreshQrcode,
  getCookieContent,
  saveCookieContent,
} from '../../api'
import type { PlatformConnectionResponse, AcquisitionWSMessage } from '../../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// 平台图标映射
const PLATFORM_ICONS: Record<string, React.ReactNode> = {
  xhs:        <FileTextOutlined style={{ color: '#fe2c55' }} />,
  douyin:     <span style={{ color: '#000', fontSize: 16 }}>🎬</span>,
  kuaishou:   <span style={{ color: '#ff5000', fontSize: 16 }}>🎥</span>,
  bilibili:   <span style={{ color: '#00aeec', fontSize: 16 }}>📺</span>,
  weibo:      <span style={{ color: '#ff8200', fontSize: 16 }}>💬</span>,
  zhihu:      <span style={{ color: '#0066ff', fontSize: 16 }}>❓</span>,
  youtube:    <span style={{ color: '#ff0000', fontSize: 16 }}>▶️</span>,
  tiktok:     <span style={{ color: '#000', fontSize: 16 }}>♪</span>,
  twitter:    <span style={{ color: '#1da1f2', fontSize: 16 }}>🐦</span>,
  telegram:   <span style={{ color: '#0088cc', fontSize: 16 }}>✈️</span>,
  openai:     <ThunderboltOutlined style={{ color: '#10a37f' }} />,
  anthropic:  <ThunderboltOutlined style={{ color: '#d4a0e7' }} />,
  minimax:    <ThunderboltOutlined style={{ color: '#00d4ff' }} />,
}

// 获取状态对应的步骤 index
function statusToStep(status: string): number {
  switch (status) {
    case 'initializing':
    case 'browser_launching':
      return 0
    case 'page_loading':
      return 1
    case 'waiting_for_login':
    case 'qr_generated':
      return 2
    case 'qr_scanned':
    case 'cookies_extracting':
    case 'cookies_extracted':
      return 3
    case 'saving':
    case 'success':
      return 4
    case 'failed':
    case 'cancelled':
    case 'expired':
      return 4
    default:
      return 0
  }
}

// 获取状态对应的进度百分比
function statusToProgress(status: string): number {
  switch (status) {
    case 'initializing': return 5
    case 'browser_launching': return 15
    case 'page_loading': return 30
    case 'waiting_for_login': return 45
    case 'qr_generated': return 40
    case 'qr_scanned': return 55
    case 'cookies_extracting': return 70
    case 'cookies_extracted': return 80
    case 'saving': return 90
    case 'success': return 100
    default: return 0
  }
}

// 获取状态颜色
function statusColor(status: string): string {
  if (status === 'success') return '#52c41a'
  if (status === 'failed' || status === 'expired' || status === 'cancelled') return '#ff4d4f'
  if (status === 'saving' || status === 'cookies_extracting' || status === 'cookies_extracted') return '#1890ff'
  return '#faad14'
}


export default function PlatformsPage() {
  const { theme } = useTheme()
  const [connections, setConnections] = useState<PlatformConnectionResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [supportedPlatforms, setSupportedPlatforms] = useState<any[]>([])
  const [authTypes, setAuthTypes] = useState<any[]>([])
  const [acquisitionMethods, setAcquisitionMethods] = useState<any[]>([])
  const [playwrightAvailable, setPlaywrightAvailable] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingConn, setEditingConn] = useState<PlatformConnectionResponse | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [form] = Form.useForm()
  const [activeTab, setActiveTab] = useState('connections')

  // Playwright 会话状态
  const [pwPlatform, setPwPlatform] = useState<string>('')
  const [pwConnectorName, setPwConnectorName] = useState('')
  const [pwStatus, setPwStatus] = useState<string>('')
  const [pwMessage, setPwMessage] = useState('')
  const [pwSessionId, setPwSessionId] = useState('')
  const [pwLoading, setPwLoading] = useState(false)
  const pwWsRef = useRef<WebSocket | null>(null)

  // QrCode 会话状态
  const [qrPlatform, setQrPlatform] = useState<string>('')
  const [qrConnectorName, setQrConnectorName] = useState('')
  const [qrSessionId, setQrSessionId] = useState('')
  const [qrImage, setQrImage] = useState('')
  const [qrStatus, setQrStatus] = useState<string>('')
  const [qrMessage, setQrMessage] = useState('')
  const [qrLoading, setQrLoading] = useState(false)
  const qrWsRef = useRef<WebSocket | null>(null)
  const qrTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 手动输入 Cookie
  const [manualPlatform, setManualPlatform] = useState<string>('')
  const [manualContent, setManualContent] = useState('')
  const [manualSaving, setManualSaving] = useState(false)

  // 加载数据
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [connRes, platformRes] = await Promise.all([
        listPlatformConnections(),
        getSupportedPlatforms(),
      ])
      setConnections(connRes.connections || [])
      setSupportedPlatforms(platformRes.platforms || [])
      setAuthTypes(platformRes.auth_types || [])
      setAcquisitionMethods(platformRes.acquisition_methods || [])
      setPlaywrightAvailable(platformRes.playwright_available || false)
    } catch (e: any) {
      message.error('加载失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 清理 WebSocket
  useEffect(() => {
    return () => {
      pwWsRef.current?.close()
      qrWsRef.current?.close()
      if (qrTimerRef.current) clearInterval(qrTimerRef.current)
    }
  }, [])

  // ============== 手动输入 Cookie ==============

  const handleManualSave = async () => {
    if (!manualPlatform) {
      message.warning('请选择平台')
      return
    }
    if (!manualContent || manualContent.trim().length < 10) {
      message.warning('Cookie 内容太短，请检查是否正确')
      return
    }

    setManualSaving(true)
    try {
      // 查找同平台是否已有连接
      const existing = connections.find(c => c.platform === manualPlatform)
      if (existing) {
        // 更新已有连接
        await saveCookieContent(existing.id, manualContent)
        message.success('Cookie 已更新')
      } else {
        // 创建新连接
        const platformInfo = supportedPlatforms.find(p => p.value === manualPlatform)
        await createPlatformConnection({
          platform: manualPlatform,
          name: `${platformInfo?.label || manualPlatform} (手动)`,
          auth_type: 'cookie',
          credentials: { content: manualContent },
        })
        message.success('连接已创建')
      }
      setManualContent('')
      loadData()
    } catch (e: any) {
      message.error('保存失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setManualSaving(false)
    }
  }

  // ============== Playwright 浏览器自动化 ==============

  const handlePlaywrightStart = async () => {
    if (!pwPlatform) {
      message.warning('请选择平台')
      return
    }
    setPwLoading(true)
    setPwStatus('initializing')
    setPwMessage('正在初始化...')
    try {
      const res = await playwrightStart({
        platform: pwPlatform,
        headless: false,
        connector_name: pwConnectorName,
      })
      if (res.success && res.session_id) {
        setPwSessionId(res.session_id)
        setPwStatus('browser_launching')
        setPwMessage(res.message || '浏览器启动中...')
        // 连接 WebSocket
        connectPwWebSocket(res.session_id)
      } else {
        setPwStatus('failed')
        setPwMessage(res.message || '启动失败')
        setPwLoading(false)
      }
    } catch (e: any) {
      setPwStatus('failed')
      setPwMessage(e?.message || '启动失败')
      setPwLoading(false)
    }
  }

  const connectPwWebSocket = (sid: string) => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.hostname}:${window.location.port || (window.location.protocol === 'https:' ? '443' : '8000')}/api/v1/acquire/playwright/${sid}/ws`)

    ws.onopen = () => {
      setPwLoading(true)
    }

    ws.onmessage = (event) => {
      try {
        const msg: AcquisitionWSMessage = JSON.parse(event.data)
        if (msg.type === 'status_update') {
          setPwStatus(msg.status)
          setPwMessage(msg.message)
        } else if (msg.type === 'completed') {
          setPwStatus(msg.status)
          setPwMessage(msg.message)
          setPwLoading(false)
          if (msg.status === 'success') {
            message.success('Cookie 获取成功！')
            loadData()
          } else if (msg.error_message) {
            message.error(msg.error_message)
          }
          ws.close()
        } else if (msg.type === 'error') {
          setPwStatus('failed')
          setPwMessage(msg.message || '未知错误')
          setPwLoading(false)
          ws.close()
        }
      } catch {
        // ignore
      }
    }

    ws.onclose = () => {
      setPwLoading(false)
    }

    ws.onerror = () => {
      setPwStatus('failed')
      setPwMessage('WebSocket 连接失败')
      setPwLoading(false)
    }

    pwWsRef.current = ws
  }

  const handlePlaywrightCancel = async () => {
    if (pwSessionId) {
      try {
        await cancelPlaywrightSession(pwSessionId)
        message.info('已取消')
      } catch {
        // ignore
      }
    }
    pwWsRef.current?.close()
    setPwLoading(false)
    setPwStatus('cancelled')
    setPwMessage('已取消')
  }

  const resetPlaywright = () => {
    pwWsRef.current?.close()
    setPwSessionId('')
    setPwStatus('')
    setPwMessage('')
    setPwLoading(false)
  }

  // ============== QrCode 二维码扫码 ==============

  const handleQrcodeGenerate = async () => {
    if (!qrPlatform) {
      message.warning('请选择平台')
      return
    }
    setQrLoading(true)
    setQrStatus('')
    setQrMessage('')
    setQrImage('')
    try {
      const res = await qrcodeGenerate({
        platform: qrPlatform,
        connector_name: qrConnectorName,
      })
      if (res.success && res.session_id) {
        setQrSessionId(res.session_id)
        setQrImage(res.qr_image_base64)
        setQrStatus('qr_generated')
        setQrMessage(res.message || '请扫描二维码')
        // 连接 WebSocket
        connectQrWebSocket(res.session_id)
      } else {
        setQrStatus('failed')
        setQrMessage(res.message || '生成失败')
        setQrLoading(false)
      }
    } catch (e: any) {
      setQrStatus('failed')
      setQrMessage(e?.message || '生成失败')
      setQrLoading(false)
    }
  }

  const connectQrWebSocket = (sid: string) => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.hostname}:${window.location.port || (window.location.protocol === 'https:' ? '443' : '8000')}/api/v1/acquire/qrcode/${sid}/ws`)

    ws.onopen = () => {
      setQrLoading(true)
    }

    ws.onmessage = (event) => {
      try {
        const msg: AcquisitionWSMessage = JSON.parse(event.data)
        if (msg.type === 'status_update') {
          setQrStatus(msg.status)
          setQrMessage(msg.message)
          if (msg.data?.qr_image_base64) {
            setQrImage(msg.data.qr_image_base64)
          }
        } else if (msg.type === 'completed') {
          setQrStatus(msg.status)
          setQrMessage(msg.message)
          setQrLoading(false)
          if (msg.status === 'success') {
            message.success('扫码登录成功！')
            loadData()
          } else if (msg.error_message) {
            message.error(msg.error_message)
          }
          ws.close()
        } else if (msg.type === 'error') {
          setQrStatus('failed')
          setQrMessage(msg.message || '未知错误')
          setQrLoading(false)
          ws.close()
        }
      } catch {
        // ignore
      }
    }

    ws.onclose = () => {
      setQrLoading(false)
    }

    ws.onerror = () => {
      setQrStatus('failed')
      setQrMessage('WebSocket 连接失败')
      setQrLoading(false)
    }

    qrWsRef.current = ws
  }

  const handleQrcodeRefresh = async () => {
    if (!qrSessionId) return
    try {
      const res = await refreshQrcode(qrSessionId)
      if (res.success) {
        setQrImage(res.qr_image_base64 || '')
        setQrStatus('qr_generated')
        setQrMessage('二维码已刷新')
        message.info('二维码已刷新')
      } else {
        message.error(res.message || '刷新失败')
      }
    } catch (e: any) {
      message.error('刷新失败')
    }
  }

  const resetQrcode = () => {
    qrWsRef.current?.close()
    if (qrTimerRef.current) clearInterval(qrTimerRef.current)
    setQrSessionId('')
    setQrStatus('')
    setQrMessage('')
    setQrImage('')
    setQrLoading(false)
  }

  // ============== 连接管理 CRUD ==============

  const handleSave = async (values: any) => {
    try {
      let credentials = {}
      if (values.cookie_content) {
        credentials = { content: values.cookie_content }
      } else if (values.api_key) {
        credentials = { api_key: values.api_key }
      } else if (values.username && values.password) {
        credentials = { username: values.username, password: values.password }
      }

      if (editingConn) {
        await updatePlatformConnection(editingConn.id, {
          name: values.name,
          auth_type: values.auth_type,
          credentials,
          description: values.description,
        })
        message.success('更新成功')
      } else {
        await createPlatformConnection({
          platform: values.platform,
          name: values.name,
          auth_type: values.auth_type,
          credentials,
          description: values.description,
        })
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      loadData()
    } catch (e: any) {
      message.error('保存失败：' + (e?.response?.data?.detail || '未知错误'))
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deletePlatformConnection(id)
      message.success('删除成功')
      loadData()
    } catch (e: any) {
      message.error('删除失败：' + (e?.response?.data?.detail || '未知错误'))
    }
  }

  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await testPlatformConnection(id)
      if (result.success) {
        message.success('连接测试成功：' + result.message)
      } else {
        message.error('连接测试失败：' + result.message)
      }
      loadData()
    } catch (e: any) {
      message.error('测试失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setTestingId(null)
    }
  }

  const handleCreate = () => {
    setEditingConn(null)
    form.resetFields()
    form.setFieldsValue({ auth_type: 'cookie', status: 'unknown' })
    setModalVisible(true)
  }

  const handleEdit = (conn: PlatformConnectionResponse) => {
    setEditingConn(conn)
    form.setFieldsValue({
      platform: conn.platform,
      name: conn.name,
      auth_type: conn.auth_type,
      description: conn.description,
    })
    setModalVisible(true)
  }

  // ============== 连接列表表格 ==============

  const columns = [
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 150,
      render: (platform: string) => {
        const p = supportedPlatforms.find(p => p.value === platform)
        return (
          <Space>
            {PLATFORM_ICONS[platform] || <GlobalOutlined />}
            <Text style={{ color: '#e0e0e0' }}>
              {p?.label || platform}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '连接名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text style={{ color: '#e0e0e0' }}>{text}</Text>,
    },
    {
      title: '认证类型',
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 120,
      render: (type: string) => {
        const t = authTypes.find(t => t.value === type)
        return <Tag>{t?.label || type}</Tag>
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string, record: PlatformConnectionResponse) => {
        if (status === 'active') {
          return <Tag icon={<CheckCircleOutlined />} color="success">有效</Tag>
        } else if (status === 'failed') {
          return (
            <Tooltip title={record.error_message}>
              <Tag icon={<CloseCircleOutlined />} color="error">失败</Tag>
            </Tooltip>
          )
        } else if (status === 'expired') {
          return <Tag color="warning">已过期</Tag>
        }
        return <Tag color="default">未测试</Tag>
      },
    },
    {
      title: '最后使用',
      dataIndex: 'last_used',
      key: 'last_used',
      width: 150,
      render: (time: string) => (
        <Text type="secondary">{time ? new Date(time).toLocaleString() : '从未使用'}</Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: PlatformConnectionResponse) => (
        <Space>
          <Tooltip title="测试连接">
            <Button
              type="text"
              size="small"
              icon={<ThunderboltOutlined />}
              loading={testingId === record.id}
              onClick={() => handleTest(record.id)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description="删除后无法恢复，确定要删除吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button type="text" size="small" icon={<DeleteOutlined />} danger />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // ============== 获取支持 Playwright 的平台列表 ==============
  const playwrightPlatforms = supportedPlatforms.filter(p =>
    p.auth_types?.includes('cookie') && !['openai', 'anthropic', 'minimax'].includes(p.value)
  )

  const qrcodePlatforms = supportedPlatforms.filter(p =>
    ['douyin', 'bilibili', 'kuaishou'].includes(p.value)
  )

  const cookiePlatforms = supportedPlatforms.filter(p =>
    p.auth_types?.includes('cookie')
  )

  // ============== Tab 内容 ==============

  const renderConnectionsTab = () => (
    <>
      {/* 统计卡片 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <Card style={{ background: theme.bgCard, border: theme.border, flex: 1, minWidth: 200 }}>
          <Statistic title="已配置平台" value={connections.length} />
        </Card>
        <Card style={{ background: theme.bgCard, border: theme.border, flex: 1, minWidth: 200 }}>
          <Statistic
            title="有效连接"
            value={connections.filter(c => c.status === 'active').length}
            valueStyle={{ color: '#52c41a' }}
          />
        </Card>
        <Card style={{ background: theme.bgCard, border: theme.border, flex: 1, minWidth: 200 }}>
          <Statistic
            title="连接失败"
            value={connections.filter(c => c.status === 'failed').length}
            valueStyle={{ color: '#ff4d4f' }}
          />
        </Card>
      </div>

      {/* 连接列表 */}
      <Card
        style={{ background: theme.bgCard, border: theme.border }}
        title={<Text style={{ color: '#fff' }}>平台连接列表</Text>}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            添加连接
          </Button>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={connections}
          loading={loading}
          pagination={{ pageSize: 10 }}
          style={{ color: '#e0e0e0' }}
        />
      </Card>
    </>
  )

  const renderManualTab = () => (
    <Card style={{ background: theme.bgCard, border: theme.border }}>
      <div style={{ marginBottom: 20 }}>
        <Title level={5} style={{ color: '#fff', marginBottom: 8 }}>
          <KeyOutlined style={{ marginRight: 8 }} />
          手动粘贴 Cookie
        </Title>
        <Paragraph style={{ color: '#8b8ba8', marginBottom: 0 }}>
          从浏览器开发者工具中复制 Cookie，粘贴到下方。支持 Netscape 格式和 key=value; 格式。
        </Paragraph>
      </div>

      <div style={{ display: 'flex', gap: 16, flexDirection: 'column', maxWidth: 700 }}>
        <div>
          <Text style={{ color: '#e0e0e0', marginBottom: 8, display: 'block' }}>选择平台</Text>
          <Select
            style={{ width: '100%' }}
            placeholder="选择平台"
            value={manualPlatform || undefined}
            onChange={setManualPlatform}
            options={cookiePlatforms.map(p => ({
              value: p.value,
              label: (
                <Space>
                  {PLATFORM_ICONS[p.value] || <GlobalOutlined />}
                  {p.label}
                </Space>
              ),
            }))}
          />
        </div>

        <div>
          <Text style={{ color: '#e0e0e0', marginBottom: 8, display: 'block' }}>Cookie 内容</Text>
          <TextArea
            rows={8}
            value={manualContent}
            onChange={e => setManualContent(e.target.value)}
            placeholder={`粘贴 Cookie 内容...\n\nNetscape 格式示例：\n.xiaohongshu.com\tTRUE\t/\tFALSE\t0\tweb_session\tabc123\n\n或 key=value; 格式：\nweb_session=abc123; a1=def456`}
            style={{ fontFamily: 'monospace' }}
          />
        </div>

        <div>
          <Button
            type="primary"
            icon={<CopyOutlined />}
            loading={manualSaving}
            onClick={handleManualSave}
            disabled={!manualPlatform || !manualContent}
          >
            保存 Cookie
          </Button>
        </div>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginTop: 24 }}
        message="如何获取 Cookie"
        description={
          <ol style={{ color: '#8b8ba8', marginBottom: 0, paddingLeft: 16 }}>
            <li>在浏览器中打开目标平台并登录</li>
            <li>按 F12 打开开发者工具</li>
            <li>切换到 Application / 存储 → Cookies</li>
            <li>复制所有 Cookie 内容到上方</li>
          </ol>
        }
      />
    </Card>
  )

  const renderPlaywrightTab = () => {
    const isActive = pwLoading || (pwStatus && !['success', 'failed', 'cancelled', 'expired'].includes(pwStatus))

    return (
      <Card style={{ background: theme.bgCard, border: theme.border }}>
        <div style={{ marginBottom: 20 }}>
          <Title level={5} style={{ color: '#fff', marginBottom: 8 }}>
            <ChromeOutlined style={{ marginRight: 8 }} />
            浏览器自动化获取
          </Title>
          <Paragraph style={{ color: '#8b8ba8', marginBottom: 0 }}>
            自动打开浏览器，登录后自动提取 Cookie。需要服务器安装 Playwright。
          </Paragraph>
        </div>

        {!playwrightAvailable && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 20 }}
            message="Playwright 未安装"
            description="请在服务器执行: pip install playwright && playwright install chromium"
          />
        )}

        {/* 进度展示 */}
        {pwStatus && (
          <Card
            size="small"
            style={{
              background: 'rgba(0,0,0,0.2)',
              border: `1px solid ${statusColor(pwStatus)}`,
              marginBottom: 20,
            }}
          >
            <div style={{ marginBottom: 12 }}>
              <Steps
                size="small"
                current={statusToStep(pwStatus)}
                status={
                  ['failed', 'cancelled', 'expired'].includes(pwStatus) ? 'error' :
                  pwStatus === 'success' ? 'finish' : 'process'
                }
                items={[
                  { title: '启动浏览器' },
                  { title: '加载页面' },
                  { title: '等待登录' },
                  { title: '提取 Cookie' },
                  { title: '完成' },
                ]}
              />
            </div>
            <Progress
              percent={statusToProgress(pwStatus)}
              status={
                ['failed', 'cancelled', 'expired'].includes(pwStatus) ? 'exception' :
                pwStatus === 'success' ? 'success' : 'active'
              }
              strokeColor={statusColor(pwStatus)}
            />
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              {isActive && <Spin indicator={<LoadingOutlined style={{ fontSize: 14 }} />} />}
              <Text style={{ color: statusColor(pwStatus), fontSize: 13 }}>
                {pwMessage}
              </Text>
            </div>
          </Card>
        )}

        {/* 操作区域 */}
        <div style={{ display: 'flex', gap: 16, flexDirection: 'column', maxWidth: 500 }}>
          <div>
            <Text style={{ color: '#e0e0e0', marginBottom: 8, display: 'block' }}>选择平台</Text>
            <Select
              style={{ width: '100%' }}
              placeholder="选择平台"
              value={pwPlatform || undefined}
              onChange={setPwPlatform}
              disabled={isActive}
              options={playwrightPlatforms.map(p => ({
                value: p.value,
                label: (
                  <Space>
                    {PLATFORM_ICONS[p.value] || <GlobalOutlined />}
                    {p.label}
                  </Space>
                ),
              }))}
            />
          </div>

          <div>
            <Text style={{ color: '#e0e0e0', marginBottom: 8, display: 'block' }}>连接名称（可选）</Text>
            <Input
              placeholder="例如：我的抖音账号"
              value={pwConnectorName}
              onChange={e => setPwConnectorName(e.target.value)}
              disabled={isActive}
            />
          </div>

          <Space>
            {!isActive ? (
              <Button
                type="primary"
                icon={<DesktopOutlined />}
                onClick={handlePlaywrightStart}
                disabled={!pwPlatform || !playwrightAvailable}
              >
                {pwStatus === 'success' ? '重新获取' : '启动浏览器'}
              </Button>
            ) : (
              <>
                <Button
                  danger
                  icon={<CloseCircleOutlined />}
                  onClick={handlePlaywrightCancel}
                >
                  取消
                </Button>
              </>
            )}
            {pwStatus && !isActive && (
              <Button icon={<ReloadOutlined />} onClick={resetPlaywright}>
                重置
              </Button>
            )}
          </Space>
        </div>

        <Alert
          type="info"
          showIcon
          style={{ marginTop: 24 }}
          message="使用说明"
          description={
            <ol style={{ color: '#8b8ba8', marginBottom: 0, paddingLeft: 16 }}>
              <li>选择要获取 Cookie 的平台</li>
              <li>点击"启动浏览器"，系统会自动打开浏览器窗口</li>
              <li>在浏览器中完成登录操作</li>
              <li>登录成功后系统会自动提取 Cookie 并保存</li>
            </ol>
          }
        />
      </Card>
    )
  }

  const renderQrcodeTab = () => {
    const isActive = qrLoading || (qrStatus && !['success', 'failed', 'cancelled', 'expired'].includes(qrStatus))

    return (
      <Card style={{ background: theme.bgCard, border: theme.border }}>
        <div style={{ marginBottom: 20 }}>
          <Title level={5} style={{ color: '#fff', marginBottom: 8 }}>
            <QrcodeOutlined style={{ marginRight: 8 }} />
            扫码登录获取
          </Title>
          <Paragraph style={{ color: '#8b8ba8', marginBottom: 0 }}>
            生成平台登录二维码，使用手机 App 扫码确认后自动获取 Cookie。
          </Paragraph>
        </div>

        {/* 二维码展示 */}
        {qrImage && (
          <Card
            size="small"
            style={{
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid #333',
              marginBottom: 20,
              textAlign: 'center',
            }}
          >
            <div style={{
              display: 'inline-block',
              padding: 16,
              background: '#fff',
              borderRadius: 8,
              marginBottom: 12,
            }}>
              <Image
                src={qrImage}
                alt="登录二维码"
                width={200}
                height={200}
                preview={false}
                style={{ borderRadius: 4 }}
              />
            </div>
            <div>
              {isActive && (
                <Space>
                  <Spin indicator={<LoadingOutlined style={{ fontSize: 14 }} />} />
                  <Text style={{ color: statusColor(qrStatus), fontSize: 13 }}>
                    {qrMessage || '等待扫码...'}
                  </Text>
                </Space>
              )}
              {!isActive && qrStatus && (
                <Text style={{ color: statusColor(qrStatus), fontSize: 14, fontWeight: 500 }}>
                  {qrMessage}
                </Text>
              )}
            </div>
            {qrStatus === 'expired' && (
              <Button
                type="link"
                icon={<ReloadOutlined />}
                onClick={handleQrcodeRefresh}
                style={{ marginTop: 8 }}
              >
                刷新二维码
              </Button>
            )}
          </Card>
        )}

        {/* 操作区域 */}
        <div style={{ display: 'flex', gap: 16, flexDirection: 'column', maxWidth: 500 }}>
          <div>
            <Text style={{ color: '#e0e0e0', marginBottom: 8, display: 'block' }}>选择平台</Text>
            <Select
              style={{ width: '100%' }}
              placeholder="选择平台"
              value={qrPlatform || undefined}
              onChange={setQrPlatform}
              disabled={isActive}
              options={qrcodePlatforms.map(p => ({
                value: p.value,
                label: (
                  <Space>
                    {PLATFORM_ICONS[p.value] || <GlobalOutlined />}
                    {p.label}
                  </Space>
                ),
              }))}
            />
          </div>

          <div>
            <Text style={{ color: '#e0e0e0', marginBottom: 8, display: 'block' }}>连接名称（可选）</Text>
            <Input
              placeholder="例如：我的B站账号"
              value={qrConnectorName}
              onChange={e => setQrConnectorName(e.target.value)}
              disabled={isActive}
            />
          </div>

          <Space>
            {!isActive ? (
              <Button
                type="primary"
                icon={<CameraOutlined />}
                onClick={handleQrcodeGenerate}
                disabled={!qrPlatform}
              >
                {qrStatus === 'success' ? '重新生成' : '生成二维码'}
              </Button>
            ) : (
              <Button danger icon={<CloseCircleOutlined />} onClick={resetQrcode}>
                取消
              </Button>
            )}
            {qrStatus && !isActive && (
              <Button icon={<ReloadOutlined />} onClick={resetQrcode}>
                重置
              </Button>
            )}
          </Space>
        </div>

        {qrcodePlatforms.length === 0 && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 16 }}
            message="暂不支持扫码登录"
            description="当前没有平台实现二维码适配器，后续会逐步支持。"
          />
        )}
      </Card>
    )
  }

  return (
    <div style={{ maxWidth: 1200 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        <LinkOutlined style={{ marginRight: 12 }} />
        平台管理
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          管理各平台凭证，支持手动粘贴、浏览器自动化、扫码登录
        </Text>
      </Title>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        items={[
          {
            key: 'connections',
            label: (
              <span>
                <LinkOutlined style={{ marginRight: 6 }} />
                连接管理
                <Badge
                  count={connections.filter(c => c.status === 'active').length}
                  style={{ marginLeft: 8 }}
                  size="small"
                />
              </span>
            ),
            children: renderConnectionsTab(),
          },
          {
            key: 'manual',
            label: (
              <span>
                <KeyOutlined style={{ marginRight: 6 }} />
                手动输入
              </span>
            ),
            children: renderManualTab(),
          },
          {
            key: 'playwright',
            label: (
              <span>
                <ChromeOutlined style={{ marginRight: 6 }} />
                浏览器自动化
                {!playwrightAvailable && (
                  <ExclamationCircleOutlined style={{ color: '#faad14', marginLeft: 4 }} />
                )}
              </span>
            ),
            children: renderPlaywrightTab(),
          },
          {
            key: 'qrcode',
            label: (
              <span>
                <QrcodeOutlined style={{ marginRight: 6 }} />
                扫码登录
              </span>
            ),
            children: renderQrcodeTab(),
          },
        ]}
      />

      {/* 创建/编辑弹窗 */}
      <Modal
        title={editingConn ? '编辑平台连接' : '添加平台连接'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{ auth_type: 'cookie' }}
        >
          <Form.Item
            name="platform"
            label="平台"
            rules={[{ required: true, message: '请选择平台' }]}
          >
            <Select
              placeholder="选择平台"
              options={supportedPlatforms.map(p => ({
                value: p.value,
                label: (
                  <Space>
                    {PLATFORM_ICONS[p.value] || <GlobalOutlined />}
                    {p.label}
                  </Space>
                ),
              }))}
            />
          </Form.Item>

          <Form.Item
            name="name"
            label="连接名称"
            rules={[{ required: true, message: '请输入连接名称' }]}
          >
            <Input placeholder="例如：我的抖音账号" />
          </Form.Item>

          <Form.Item
            name="auth_type"
            label="认证类型"
            rules={[{ required: true, message: '请选择认证类型' }]}
          >
            <Select
              placeholder="选择认证类型"
              options={authTypes.map(t => ({
                value: t.value,
                label: t.label,
              }))}
            />
          </Form.Item>

          {/* Cookie 认证 */}
          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.auth_type !== currentValues.auth_type
            }
          >
            {() => {
              const authType = form.getFieldValue('auth_type')
              if (authType === 'cookie') {
                return (
                  <Form.Item
                    name="cookie_content"
                    label="Cookie 内容"
                    rules={[{ required: true, message: '请输入 Cookie 内容' }]}
                  >
                    <TextArea
                      rows={6}
                      placeholder="粘贴 Cookie 内容（Netscape 格式）..."
                    />
                  </Form.Item>
                )
              } else if (authType === 'api_key') {
                return (
                  <Form.Item
                    name="api_key"
                    label="API Key"
                    rules={[{ required: true, message: '请输入 API Key' }]}
                  >
                    <Input.Password placeholder="输入 API Key..." />
                  </Form.Item>
                )
              } else if (authType === 'password') {
                return (
                  <>
                    <Form.Item
                      name="username"
                      label="用户名"
                      rules={[{ required: true, message: '请输入用户名' }]}
                    >
                      <Input placeholder="用户名..." />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      label="密码"
                      rules={[{ required: true, message: '请输入密码' }]}
                    >
                      <Input.Password placeholder="密码..." />
                    </Form.Item>
                  </>
                )
              }
              return null
            }}
          </Form.Item>

          <Form.Item name="description" label="备注说明">
            <TextArea rows={2} placeholder="可选：添加备注说明..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// 统计组件
function Statistic({ title, value, valueStyle }: { title: string; value: number; valueStyle?: any }) {
  return (
    <div>
      <Text style={{ color: '#8b8ba8', fontSize: 12 }}>{title}</Text>
      <div style={{ fontSize: 24, fontWeight: 600, color: '#fff', ...valueStyle }}>{value}</div>
    </div>
  )
}
