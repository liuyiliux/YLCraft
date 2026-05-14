import { useState, useEffect, useRef, useCallback } from 'react'
import { useTheme } from '../../constants/theme'
import {
  Card,
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
  Steps,
  Spin,
  Image,
  Progress,
  Badge,
  Empty,
  Dropdown,
  Avatar,
  Divider,
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
  DownOutlined,
  UserOutlined,
  ApiOutlined,
  SafetyCertificateOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
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
  getConnectionCookieContent,
  saveConnectionCookieContent,
} from '../../api'
import type { PlatformConnectionResponse, AcquisitionWSMessage } from '../../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// ===== 平台元信息 =====
interface PlatformMeta {
  value: string
  label: string
  icon: React.ReactNode
  color: string
  authTypes: string[]     // 支持的认证类型
  supportQrcode: boolean  // 是否支持扫码
}

const PLATFORM_METAS: PlatformMeta[] = [
  { value: 'xhs',       label: '小红书',  icon: <span style={{fontSize:18}}>📕</span>, color: '#fe2c55', authTypes: ['cookie'], supportQrcode: true },
  { value: 'douyin',     label: '抖音',    icon: <span style={{fontSize:18}}>🎬</span>, color: '#000000', authTypes: ['cookie'], supportQrcode: true },
  { value: 'kuaishou',   label: '快手',    icon: <span style={{fontSize:18}}>🎥</span>, color: '#ff5000', authTypes: ['cookie'], supportQrcode: true },
  { value: 'bilibili',   label: 'B站',     icon: <span style={{fontSize:18}}>📺</span>, color: '#00aeec', authTypes: ['cookie'], supportQrcode: true },
  { value: 'weibo',      label: '微博',    icon: <span style={{fontSize:18}}>💬</span>, color: '#ff8200', authTypes: ['cookie'], supportQrcode: false },
  { value: 'zhihu',      label: '知乎',    icon: <span style={{fontSize:18}}>❓</span>, color: '#0066ff', authTypes: ['cookie'], supportQrcode: false },
  { value: 'youtube',    label: 'YouTube', icon: <span style={{fontSize:18}}>▶️</span>, color: '#ff0000', authTypes: ['cookie'], supportQrcode: false },
  { value: 'tiktok',     label: 'TikTok',  icon: <span style={{fontSize:18}}>♪</span>,  color: '#000000', authTypes: ['cookie'], supportQrcode: false },
  { value: 'twitter',    label: 'X',       icon: <span style={{fontSize:18}}>🐦</span>, color: '#1da1f2', authTypes: ['cookie'], supportQrcode: false },
  { value: 'openai',     label: 'OpenAI',  icon: <ThunderboltOutlined style={{color:'#10a37f',fontSize:16}} />, color: '#10a37f', authTypes: ['api_key'], supportQrcode: false },
  { value: 'anthropic',  label: 'Anthropic', icon: <ThunderboltOutlined style={{color:'#d4a0e7',fontSize:16}} />, color: '#d4a0e7', authTypes: ['api_key'], supportQrcode: false },
  { value: 'minimax',    label: 'MiniMax', icon: <ThunderboltOutlined style={{color:'#00d4ff',fontSize:16}} />, color: '#00d4ff', authTypes: ['api_key'], supportQrcode: false },
]

function getPlatformMeta(value: string): PlatformMeta | undefined {
  return PLATFORM_METAS.find(p => p.value === value)
}

// ===== 状态辅助函数 =====

function statusTag(status: string, errorMessage?: string | null) {
  if (status === 'active') {
    return <Tag icon={<CheckCircleOutlined />} color="success">有效</Tag>
  }
  if (status === 'failed') {
    return (
      <Tooltip title={errorMessage || '连接失败'}>
        <Tag icon={<CloseCircleOutlined />} color="error">失败</Tag>
      </Tooltip>
    )
  }
  if (status === 'expired') {
    return <Tag color="warning">已过期</Tag>
  }
  return <Tag color="default">未测试</Tag>
}

function acquisitionMethodTag(method: string) {
  switch (method) {
    case 'playwright':
      return <Tag icon={<ChromeOutlined />} color="processing">浏览器</Tag>
    case 'qrcode':
      return <Tag icon={<QrcodeOutlined />} color="processing">扫码</Tag>
    case 'manual':
    default:
      return <Tag icon={<KeyOutlined />}>手动</Tag>
  }
}

function authTypeLabel(authType: string) {
  switch (authType) {
    case 'cookie': return 'Cookie'
    case 'api_key': return 'API Key'
    case 'password': return '账号密码'
    default: return authType
  }
}

// ===== 连接卡片组件 =====
function ConnectionCard({
  conn,
  platformMeta,
  testingId,
  onTest,
  onEdit,
  onDelete,
}: {
  conn: PlatformConnectionResponse
  platformMeta: PlatformMeta | undefined
  testingId: string | null
  onTest: (id: string) => void
  onEdit: (conn: PlatformConnectionResponse) => void
  onDelete: (id: string) => void
}) {
  const { theme } = useTheme()

  return (
    <div
      style={{
        background: theme.bgElevated,
        border: `1px solid ${theme.border}`,
        borderRadius: 10,
        padding: 16,
        minWidth: 220,
        flex: '1 1 220px',
        maxWidth: 300,
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = platformMeta?.color || theme.primary
        e.currentTarget.style.boxShadow = `0 0 12px ${platformMeta?.color || theme.primary}22`
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = theme.border
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      {/* 头部：账号名 + 状态 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <Avatar
          size={36}
          style={{
            backgroundColor: `${platformMeta?.color || theme.primary}22`,
            color: platformMeta?.color || theme.primary,
            flexShrink: 0,
          }}
          icon={<UserOutlined />}
        >
          {(conn as any).account_name?.[0] || conn.name?.[0] || '?'}
        </Avatar>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Text
              style={{ color: theme.textPrimary, fontWeight: 500, fontSize: 14 }}
              ellipsis
            >
              {conn.name}
            </Text>
            {statusTag(conn.status, conn.error_message)}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
            {acquisitionMethodTag((conn as any).acquisition_method || 'manual')}
            <Text style={{ color: theme.textSecondary, fontSize: 12 }}>
              {authTypeLabel(conn.auth_type)}
            </Text>
          </div>
        </div>
      </div>

      {/* 账号信息 */}
      {(conn as any).account_name && (
        <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>
            {String((conn as any).account_name)}
          </Text>
        </div>
      )}

      {/* 最后使用 */}
      <div style={{ marginBottom: 12 }}>
        <Text style={{ color: theme.textDisabled, fontSize: 11 }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {conn.last_used ? new Date(conn.last_used).toLocaleDateString() : '从未使用'}
        </Text>
      </div>

      {/* 操作按钮 */}
      <div style={{ display: 'flex', gap: 6 }}>
        <Tooltip title="测试连接">
          <Button
            type="text"
            size="small"
            icon={<ExperimentOutlined />}
            loading={testingId === conn.id}
            onClick={() => onTest(conn.id)}
            style={{ color: theme.textSecondary }}
          />
        </Tooltip>
        <Tooltip title="编辑">
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => onEdit(conn)}
            style={{ color: theme.textSecondary }}
          />
        </Tooltip>
        <Popconfirm
          title="确认删除"
          description="删除后无法恢复，确定要删除吗？"
          onConfirm={() => onDelete(conn.id)}
          okText="确定"
          cancelText="取消"
        >
          <Tooltip title="删除">
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              danger
            />
          </Tooltip>
        </Popconfirm>
      </div>
    </div>
  )
}

// ===== 平台分组卡片组件 =====
function PlatformGroupCard({
  platformMeta,
  connections,
  testingId,
  playwrightAvailable,
  onTest,
  onEdit,
  onDelete,
  onAddManual,
  onAddPlaywright,
  onAddQrcode,
}: {
  platformMeta: PlatformMeta
  connections: PlatformConnectionResponse[]
  testingId: string | null
  playwrightAvailable: boolean
  onTest: (id: string) => void
  onEdit: (conn: PlatformConnectionResponse) => void
  onDelete: (id: string) => void
  onAddManual: (platform: string) => void
  onAddPlaywright: (platform: string) => void
  onAddQrcode: (platform: string) => void
}) {
  const { theme } = useTheme()
  const isApiPlatform = !platformMeta.authTypes.includes('cookie')

  return (
    <Card
      style={{
        background: theme.bgCard,
        border: `1px solid ${theme.border}`,
        borderRadius: 12,
        marginBottom: 20,
      }}
      styles={{ body: { padding: 20 } }}
    >
      {/* 平台头部 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {platformMeta.icon}
          <Text style={{ color: theme.textPrimary, fontSize: 16, fontWeight: 600 }}>
            {platformMeta.label}
          </Text>
          <Badge
            count={connections.length}
            style={{ backgroundColor: `${platformMeta.color}33`, color: platformMeta.color }}
          />
        </div>

        {/* 添加连接入口 */}
        {!isApiPlatform ? (
          <Dropdown
            menu={{
              items: [
                {
                  key: 'manual',
                  icon: <KeyOutlined />,
                  label: '手动粘贴 Cookie',
                  onClick: () => onAddManual(platformMeta.value),
                },
                ...(playwrightAvailable ? [{
                  key: 'playwright',
                  icon: <ChromeOutlined />,
                  label: '浏览器自动获取',
                  onClick: () => onAddPlaywright(platformMeta.value),
                }] : []),
                ...(platformMeta.supportQrcode ? [{
                  key: 'qrcode',
                  icon: <QrcodeOutlined />,
                  label: '扫码登录获取',
                  onClick: () => onAddQrcode(platformMeta.value),
                }] : []),
              ],
            }}
          >
            <Button type="primary" size="small" icon={<PlusOutlined />}>
              添加连接 <DownOutlined style={{ fontSize: 10 }} />
            </Button>
          </Dropdown>
        ) : (
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => onAddManual(platformMeta.value)}
          >
            添加连接
          </Button>
        )}
      </div>

      {/* 连接卡片网格 */}
      {connections.length > 0 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {connections.map(conn => (
            <ConnectionCard
              key={conn.id}
              conn={conn}
              platformMeta={platformMeta}
              testingId={testingId}
              onTest={onTest}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </div>
      ) : (
        <div style={{
          padding: '24px 0',
          textAlign: 'center',
          border: `1px dashed ${theme.borderLight}`,
          borderRadius: 8,
        }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text style={{ color: theme.textSecondary, fontSize: 13 }}>
                还没有{platformMeta.label}的连接，点击上方「添加连接」开始
              </Text>
            }
          />
        </div>
      )}
    </Card>
  )
}

// ===== 主页面 =====
export default function PlatformsPage() {
  const { theme } = useTheme()
  const [connections, setConnections] = useState<PlatformConnectionResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [supportedPlatforms, setSupportedPlatforms] = useState<any[]>([])
  const [authTypes, setAuthTypes] = useState<any[]>([])
  const [playwrightAvailable, setPlaywrightAvailable] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)

  // ===== 弹窗状态 =====
  const [modalVisible, setModalVisible] = useState(false)
  const [editingConn, setEditingConn] = useState<PlatformConnectionResponse | null>(null)
  const [modalPlatform, setModalPlatform] = useState<string>('')
  const [form] = Form.useForm()

  // ===== 手动 Cookie 弹窗 =====
  const [manualModalVisible, setManualModalVisible] = useState(false)
  const [manualPlatform, setManualPlatform] = useState<string>('')
  const [manualName, setManualName] = useState('')
  const [manualContent, setManualContent] = useState('')
  const [manualSaving, setManualSaving] = useState(false)

  // ===== Playwright 弹窗 =====
  const [pwModalVisible, setPwModalVisible] = useState(false)
  const [pwPlatform, setPwPlatform] = useState<string>('')
  const [pwConnectorName, setPwConnectorName] = useState('')
  const [pwStatus, setPwStatus] = useState<string>('')
  const [pwMessage, setPwMessage] = useState('')
  const [pwSessionId, setPwSessionId] = useState('')
  const [pwLoading, setPwLoading] = useState(false)
  const pwWsRef = useRef<WebSocket | null>(null)

  // ===== QrCode 弹窗 =====
  const [qrModalVisible, setQrModalVisible] = useState(false)
  const [qrPlatform, setQrPlatform] = useState<string>('')
  const [qrConnectorName, setQrConnectorName] = useState('')
  const [qrSessionId, setQrSessionId] = useState('')
  const [qrImage, setQrImage] = useState('')
  const [qrStatus, setQrStatus] = useState<string>('')
  const [qrMessage, setQrMessage] = useState('')
  const [qrLoading, setQrLoading] = useState(false)
  const qrWsRef = useRef<WebSocket | null>(null)
  const qrTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ===== 加载数据 =====
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
      setPlaywrightAvailable(platformRes.playwright_available || false)
    } catch (e: any) {
      message.error('加载失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    return () => {
      pwWsRef.current?.close()
      qrWsRef.current?.close()
      if (qrTimerRef.current) clearInterval(qrTimerRef.current)
    }
  }, [])

  // ===== 按平台分组 =====
  const groupedConnections = useCallback(() => {
    const groups: Record<string, PlatformConnectionResponse[]> = {}
    // 先按 PLATFORM_METAS 定义的顺序排
    for (const pm of PLATFORM_METAS) {
      groups[pm.value] = []
    }
    for (const conn of connections) {
      if (!groups[conn.platform]) {
        groups[conn.platform] = []
      }
      groups[conn.platform].push(conn)
    }
    return groups
  }, [connections])

  // 有连接的平台
  const activePlatforms = PLATFORM_METAS.filter(pm => {
    const groups = groupedConnections()
    return groups[pm.value] && groups[pm.value].length > 0
  })

  // 没有连接的平台
  const inactivePlatforms = PLATFORM_METAS.filter(pm => {
    const groups = groupedConnections()
    return !groups[pm.value] || groups[pm.value].length === 0
  })

  // ===== 手动 Cookie 保存 =====
  const handleManualSave = async () => {
    if (!manualPlatform) {
      message.warning('请确认平台')
      return
    }
    if (!manualContent || manualContent.trim().length < 10) {
      message.warning('Cookie 内容太短，请检查是否正确')
      return
    }
    setManualSaving(true)
    try {
      const platformInfo = getPlatformMeta(manualPlatform)
      const name = manualName.trim() || `${platformInfo?.label || manualPlatform} (手动)`
      await createPlatformConnection({
        platform: manualPlatform,
        name,
        auth_type: 'cookie',
        credentials: { content: manualContent },
      })
      message.success('连接已创建')
      setManualModalVisible(false)
      setManualContent('')
      setManualName('')
      setManualPlatform('')
      loadData()
    } catch (e: any) {
      message.error('保存失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setManualSaving(false)
    }
  }

  // ===== Playwright 操作 =====
  const handlePlaywrightStart = async () => {
    if (!pwPlatform) return
    setPwLoading(true)
    setPwStatus('initializing')
    setPwMessage('正在初始化...')
    try {
      const res = await playwrightStart({
        platform: pwPlatform,
        headless: false,
        connector_name: pwConnectorName || undefined,
      })
      if (res.success && res.session_id) {
        setPwSessionId(res.session_id)
        setPwStatus('browser_launching')
        setPwMessage(res.message || '浏览器启动中...')
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

    ws.onopen = () => { setPwLoading(true) }

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
      } catch { /* ignore */ }
    }

    ws.onclose = () => { setPwLoading(false) }
    ws.onerror = () => {
      setPwStatus('failed')
      setPwMessage('WebSocket 连接失败')
      setPwLoading(false)
    }

    pwWsRef.current = ws
  }

  const handlePlaywrightCancel = async () => {
    if (pwSessionId) {
      try { await cancelPlaywrightSession(pwSessionId) } catch { /* ignore */ }
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

  // ===== QrCode 操作 =====
  const handleQrcodeGenerate = async () => {
    if (!qrPlatform) return
    setQrLoading(true)
    setQrStatus('')
    setQrMessage('')
    setQrImage('')
    try {
      const res = await qrcodeGenerate({
        platform: qrPlatform,
        connector_name: qrConnectorName || undefined,
      })
      if (res.success && res.session_id) {
        setQrSessionId(res.session_id)
        setQrImage(res.qr_image_base64)
        setQrStatus('qr_generated')
        setQrMessage(res.message || '请扫描二维码')
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

    ws.onopen = () => { setQrLoading(true) }

    ws.onmessage = (event) => {
      try {
        const msg: AcquisitionWSMessage = JSON.parse(event.data)
        if (msg.type === 'status_update') {
          setQrStatus(msg.status)
          setQrMessage(msg.message)
          if (msg.data?.qr_image_base64) setQrImage(msg.data.qr_image_base64)
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
      } catch { /* ignore */ }
    }

    ws.onclose = () => { setQrLoading(false) }
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
      } else {
        message.error(res.message || '刷新失败')
      }
    } catch { message.error('刷新失败') }
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

  // ===== 连接 CRUD =====
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

  const handleDelete = async (id: string) => {
    try {
      await deletePlatformConnection(id)
      message.success('删除成功')
      loadData()
    } catch (e: any) {
      message.error('删除失败：' + (e?.response?.data?.detail || '未知错误'))
    }
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

  // ===== 添加连接入口 =====
  const onAddManual = (platform: string) => {
    const meta = getPlatformMeta(platform)
    setManualPlatform(platform)
    setManualName(`${meta?.label || platform} 账号`)
    setManualContent('')
    setManualModalVisible(true)
  }

  const onAddPlaywright = (platform: string) => {
    const meta = getPlatformMeta(platform)
    setPwPlatform(platform)
    setPwConnectorName(`${meta?.label || platform} 账号`)
    resetPlaywright()
    setPwModalVisible(true)
  }

  const onAddQrcode = (platform: string) => {
    const meta = getPlatformMeta(platform)
    setQrPlatform(platform)
    setQrConnectorName(`${meta?.label || platform} 账号`)
    resetQrcode()
    setQrModalVisible(true)
  }

  // ===== 统计 =====
  const activeCount = connections.filter(c => c.status === 'active').length
  const failedCount = connections.filter(c => c.status === 'failed').length
  const expiredCount = connections.filter(c => c.status === 'expired').length

  // ===== 获取状态辅助 =====
  const pwIsActive = pwLoading || (pwStatus && !['success', 'failed', 'cancelled', 'expired'].includes(pwStatus))
  const qrIsActive = qrLoading || (qrStatus && !['success', 'failed', 'cancelled', 'expired'].includes(qrStatus))

  function statusToStep(status: string): number {
    switch (status) {
      case 'initializing': case 'browser_launching': return 0
      case 'page_loading': return 1
      case 'waiting_for_login': case 'qr_generated': return 2
      case 'qr_scanned': case 'cookies_extracting': case 'cookies_extracted': return 3
      case 'saving': case 'success': case 'failed': case 'cancelled': case 'expired': return 4
      default: return 0
    }
  }

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

  function statusColor(status: string): string {
    if (status === 'success') return theme.success
    if (['failed', 'expired', 'cancelled'].includes(status)) return theme.error
    if (['saving', 'cookies_extracting', 'cookies_extracted'].includes(status)) return theme.primary
    return theme.warning
  }

  const groups = groupedConnections()

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ color: theme.textPrimary, marginBottom: 4 }}>
          <LinkOutlined style={{ marginRight: 12 }} />
          平台管理
        </Title>
        <Text style={{ color: theme.textSecondary, fontSize: 14 }}>
          管理各平台凭证，支持多账号、多种认证方式
        </Text>
      </div>

      {/* 统计栏 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{
          background: theme.bgCard,
          border: `1px solid ${theme.border}`,
          borderRadius: 10,
          padding: '12px 20px',
          flex: 1,
          minWidth: 140,
        }}>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>已配置平台</Text>
          <div style={{ fontSize: 24, fontWeight: 600, color: theme.textPrimary }}>
            {activePlatforms.length}
          </div>
        </div>
        <div style={{
          background: theme.bgCard,
          border: `1px solid ${theme.border}`,
          borderRadius: 10,
          padding: '12px 20px',
          flex: 1,
          minWidth: 140,
        }}>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>有效连接</Text>
          <div style={{ fontSize: 24, fontWeight: 600, color: theme.success }}>{activeCount}</div>
        </div>
        <div style={{
          background: theme.bgCard,
          border: `1px solid ${theme.border}`,
          borderRadius: 10,
          padding: '12px 20px',
          flex: 1,
          minWidth: 140,
        }}>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>连接失败</Text>
          <div style={{ fontSize: 24, fontWeight: 600, color: theme.error }}>{failedCount}</div>
        </div>
        <div style={{
          background: theme.bgCard,
          border: `1px solid ${theme.border}`,
          borderRadius: 10,
          padding: '12px 20px',
          flex: 1,
          minWidth: 140,
        }}>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>已过期</Text>
          <div style={{ fontSize: 24, fontWeight: 600, color: theme.warning }}>{expiredCount}</div>
        </div>
      </div>

      {/* 已有连接的平台 */}
      {activePlatforms.map(pm => (
        <PlatformGroupCard
          key={pm.value}
          platformMeta={pm}
          connections={groups[pm.value] || []}
          testingId={testingId}
          playwrightAvailable={playwrightAvailable}
          onTest={handleTest}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onAddManual={onAddManual}
          onAddPlaywright={onAddPlaywright}
          onAddQrcode={onAddQrcode}
        />
      ))}

      {/* 未配置的平台 — 折叠区 */}
      {inactivePlatforms.length > 0 && (
        <PlatformGroupCard
          platformMeta={inactivePlatforms[0]}
          connections={[]}
          testingId={testingId}
          playwrightAvailable={playwrightAvailable}
          onTest={handleTest}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onAddManual={onAddManual}
          onAddPlaywright={onAddPlaywright}
          onAddQrcode={onAddQrcode}
        />
      )}

      {/* 未配置的平台 — 紧凑网格 */}
      {inactivePlatforms.length > 0 && (
        <Card
          style={{
            background: theme.bgCard,
            border: `1px solid ${theme.border}`,
            borderRadius: 12,
          }}
          styles={{ body: { padding: 16 } }}
        >
          <Text style={{ color: theme.textSecondary, fontSize: 13, marginBottom: 12, display: 'block' }}>
            其他平台 — 点击快速添加
          </Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {inactivePlatforms.map(pm => {
              const isApiPlatform = !pm.authTypes.includes('cookie')
              return (
                <Dropdown
                  key={pm.value}
                  menu={{
                    items: isApiPlatform
                      ? [{ key: 'manual', icon: <ApiOutlined />, label: '添加 API Key', onClick: () => onAddManual(pm.value) }]
                      : [
                          { key: 'manual', icon: <KeyOutlined />, label: '手动粘贴', onClick: () => onAddManual(pm.value) },
                          ...(playwrightAvailable ? [{ key: 'playwright', icon: <ChromeOutlined />, label: '浏览器获取', onClick: () => onAddPlaywright(pm.value) }] : []),
                          ...(pm.supportQrcode ? [{ key: 'qrcode', icon: <QrcodeOutlined />, label: '扫码登录', onClick: () => onAddQrcode(pm.value) }] : []),
                        ],
                  }}
                >
                  <Button
                    type="dashed"
                    size="small"
                    style={{
                      borderColor: `${pm.color}44`,
                      color: pm.color,
                    }}
                    icon={pm.icon}
                  >
                    {pm.label} <PlusOutlined style={{ fontSize: 10 }} />
                  </Button>
                </Dropdown>
              )
            })}
          </div>
        </Card>
      )}

      {/* ===== 手动 Cookie 弹窗 ===== */}
      <Modal
        title={
          <Space>
            <KeyOutlined />
            <span>手动添加 {getPlatformMeta(manualPlatform)?.label || ''} 连接</span>
          </Space>
        }
        open={manualModalVisible}
        onCancel={() => {
          setManualModalVisible(false)
          setManualContent('')
          setManualName('')
        }}
        onOk={handleManualSave}
        confirmLoading={manualSaving}
        okText="保存连接"
        cancelText="取消"
        width={600}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
          <div>
            <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block' }}>
              连接名称
            </Text>
            <Input
              placeholder="给这个连接起个名字，如：我的小红书小号"
              value={manualName}
              onChange={e => setManualName(e.target.value)}
            />
            <Text style={{ color: theme.textDisabled, fontSize: 11, marginTop: 4, display: 'block' }}>
              同一平台可以有多个连接（多角色），请用名称区分
            </Text>
          </div>

          <div>
            <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block' }}>
              Cookie 内容
            </Text>
            <TextArea
              rows={8}
              value={manualContent}
              onChange={e => setManualContent(e.target.value)}
              placeholder={`粘贴 Cookie 内容...\n\nNetscape 格式示例：\n.xiaohongshu.com\tTRUE\t/\tFALSE\t0\tweb_session\tabc123\n\n或 key=value; 格式：\nweb_session=abc123; a1=def456`}
              style={{ fontFamily: 'monospace' }}
            />
          </div>

          <Alert
            type="info"
            showIcon
            message="如何获取 Cookie"
            description={
              <ol style={{ color: theme.textSecondary, marginBottom: 0, paddingLeft: 16, fontSize: 12 }}>
                <li>在浏览器中打开目标平台并登录</li>
                <li>按 F12 打开开发者工具</li>
                <li>切换到 Application → Cookies</li>
                <li>复制所有 Cookie 内容到上方</li>
              </ol>
            }
          />
        </div>
      </Modal>

      {/* ===== Playwright 弹窗 ===== */}
      <Modal
        title={
          <Space>
            <ChromeOutlined />
            <span>浏览器获取 {getPlatformMeta(pwPlatform)?.label || ''} Cookie</span>
          </Space>
        }
        open={pwModalVisible}
        onCancel={() => {
          if (pwIsActive) {
            handlePlaywrightCancel()
          }
          setPwModalVisible(false)
        }}
        footer={null}
        width={560}
      >
        <div style={{ marginTop: 16 }}>
          {!playwrightAvailable && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message="Playwright 未安装"
              description="请在服务器执行: pip install playwright && playwright install chromium"
            />
          )}

          {/* 进度展示 */}
          {pwStatus && (
            <div style={{
              background: 'rgba(0,0,0,0.2)',
              border: `1px solid ${statusColor(pwStatus)}`,
              borderRadius: 8,
              padding: 16,
              marginBottom: 16,
            }}>
              <Steps
                size="small"
                current={statusToStep(pwStatus)}
                status={
                  ['failed', 'cancelled', 'expired'].includes(pwStatus) ? 'error' :
                  pwStatus === 'success' ? 'finish' : 'process'
                }
                items={[
                  { title: '启动' },
                  { title: '加载' },
                  { title: '等待登录' },
                  { title: '提取' },
                  { title: '完成' },
                ]}
              />
              <Progress
                percent={statusToProgress(pwStatus)}
                status={
                  ['failed', 'cancelled', 'expired'].includes(pwStatus) ? 'exception' :
                  pwStatus === 'success' ? 'success' : 'active'
                }
                strokeColor={statusColor(pwStatus)}
                style={{ marginTop: 12 }}
              />
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                {pwIsActive && <Spin indicator={<LoadingOutlined style={{ fontSize: 14 }} />} />}
                <Text style={{ color: statusColor(pwStatus), fontSize: 13 }}>{pwMessage}</Text>
              </div>
            </div>
          )}

          {/* 操作区 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block' }}>连接名称</Text>
              <Input
                placeholder="给这个连接起个名字，如：我的抖音企业号"
                value={pwConnectorName}
                onChange={e => setPwConnectorName(e.target.value)}
                disabled={!!pwIsActive}
              />
            </div>

            <Space>
              {!pwIsActive ? (
                <Button
                  type="primary"
                  icon={<DesktopOutlined />}
                  onClick={handlePlaywrightStart}
                  disabled={!playwrightAvailable}
                >
                  {pwStatus === 'success' ? '重新获取' : '启动浏览器'}
                </Button>
              ) : (
                <Button danger icon={<CloseCircleOutlined />} onClick={handlePlaywrightCancel}>
                  取消
                </Button>
              )}
              {pwStatus && !pwIsActive && (
                <Button icon={<ReloadOutlined />} onClick={resetPlaywright}>
                  重置
                </Button>
              )}
            </Space>
          </div>

          <Alert
            type="info"
            showIcon
            style={{ marginTop: 16 }}
            message="使用说明"
            description={
              <ol style={{ color: theme.textSecondary, marginBottom: 0, paddingLeft: 16, fontSize: 12 }}>
                <li>点击「启动浏览器」，系统会自动打开浏览器窗口</li>
                <li>在浏览器中完成登录操作</li>
                <li>登录成功后系统会自动提取 Cookie 并保存</li>
              </ol>
            }
          />
        </div>
      </Modal>

      {/* ===== QrCode 弹窗 ===== */}
      <Modal
        title={
          <Space>
            <QrcodeOutlined />
            <span>扫码登录 {getPlatformMeta(qrPlatform)?.label || ''}</span>
          </Space>
        }
        open={qrModalVisible}
        onCancel={() => {
          if (qrIsActive) resetQrcode()
          setQrModalVisible(false)
        }}
        footer={null}
        width={460}
      >
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          {/* 二维码展示 */}
          {qrImage ? (
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
          ) : (
            <div style={{
              padding: '60px 0',
              textAlign: 'center',
              border: `1px dashed ${theme.borderLight}`,
              borderRadius: 8,
              marginBottom: 12,
            }}>
              <QrcodeOutlined style={{ fontSize: 48, color: theme.textDisabled }} />
              <div>
                <Text style={{ color: theme.textSecondary }}>点击下方按钮生成二维码</Text>
              </div>
            </div>
          )}

          {/* 状态提示 */}
          {qrStatus && (
            <div style={{ marginBottom: 12 }}>
              {qrIsActive && (
                <Space>
                  <Spin indicator={<LoadingOutlined style={{ fontSize: 14 }} />} />
                  <Text style={{ color: statusColor(qrStatus), fontSize: 13 }}>
                    {qrMessage || '等待扫码...'}
                  </Text>
                </Space>
              )}
              {!qrIsActive && (
                <Text style={{ color: statusColor(qrStatus), fontSize: 14, fontWeight: 500 }}>
                  {qrMessage}
                </Text>
              )}
            </div>
          )}

          {qrStatus === 'expired' && (
            <Button
              type="link"
              icon={<ReloadOutlined />}
              onClick={handleQrcodeRefresh}
              style={{ marginBottom: 8 }}
            >
              刷新二维码
            </Button>
          )}

          {/* 操作区 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, textAlign: 'left' }}>
            <div>
              <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block' }}>连接名称</Text>
              <Input
                placeholder="给这个连接起个名字"
                value={qrConnectorName}
                onChange={e => setQrConnectorName(e.target.value)}
                disabled={!!qrIsActive}
              />
            </div>

            <Space style={{ justifyContent: 'center', width: '100%' }}>
              {!qrIsActive ? (
                <Button
                  type="primary"
                  icon={<CameraOutlined />}
                  onClick={handleQrcodeGenerate}
                >
                  {qrStatus === 'success' ? '重新生成' : '生成二维码'}
                </Button>
              ) : (
                <Button danger icon={<CloseCircleOutlined />} onClick={resetQrcode}>
                  取消
                </Button>
              )}
              {qrStatus && !qrIsActive && (
                <Button icon={<ReloadOutlined />} onClick={resetQrcode}>
                  重置
                </Button>
              )}
            </Space>
          </div>
        </div>
      </Modal>

      {/* ===== 编辑连接弹窗 ===== */}
      <Modal
        title={editingConn ? '编辑连接' : '添加连接'}
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
          <Form.Item name="platform" label="平台">
            <Select
              disabled={!!editingConn}
              options={PLATFORM_METAS.map(p => ({
                value: p.value,
                label: (
                  <Space>
                    {p.icon}
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
            <Input placeholder="例如：我的抖音小号" />
          </Form.Item>

          <Form.Item
            name="auth_type"
            label="认证类型"
            rules={[{ required: true, message: '请选择认证类型' }]}
          >
            <Select
              placeholder="选择认证类型"
              options={authTypes.map((t: any) => ({
                value: t.value,
                label: t.label,
              }))}
            />
          </Form.Item>

          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.auth_type !== cur.auth_type}>
            {() => {
              const authType = form.getFieldValue('auth_type')
              if (authType === 'cookie') {
                return (
                  <Form.Item
                    name="cookie_content"
                    label="Cookie 内容"
                    rules={[{ required: true, message: '请输入 Cookie 内容' }]}
                  >
                    <TextArea rows={6} placeholder="粘贴 Cookie 内容..." />
                  </Form.Item>
                )
              }
              if (authType === 'api_key') {
                return (
                  <Form.Item
                    name="api_key"
                    label="API Key"
                    rules={[{ required: true, message: '请输入 API Key' }]}
                  >
                    <Input.Password placeholder="输入 API Key..." />
                  </Form.Item>
                )
              }
              if (authType === 'password') {
                return (
                  <>
                    <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
                      <Input placeholder="用户名..." />
                    </Form.Item>
                    <Form.Item name="password" label="密码" rules={[{ required: true }]}>
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
