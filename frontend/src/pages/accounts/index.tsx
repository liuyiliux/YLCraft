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
  Spin,
  Image,
  Progress,
  Badge,
  Empty,
  Dropdown,
  Avatar,
  Divider,
  Drawer,
  Segmented,
  Statistic,
  Row,
  Col,
} from 'antd'
import {
  GlobalOutlined,
  LinkOutlined,
  KeyOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
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
  SyncOutlined,
  ImportOutlined,
  MessageOutlined,
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
  wechatMpLoginQrcode,
  wechatMpLoginStatus,
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
  authTypes: string[]
  supportQrcode: boolean
}

const PLATFORM_METAS: PlatformMeta[] = [
  { value: 'xhs',       label: '小红书',  icon: <span style={{fontSize:18}}>📕</span>, color: '#fe2c55', authTypes: ['cookie'], supportQrcode: true },
  { value: 'douyin',     label: '抖音',    icon: <span style={{fontSize:18}}>🎬</span>, color: '#000000', authTypes: ['cookie'], supportQrcode: true },
  { value: 'kuaishou',   label: '快手',    icon: <span style={{fontSize:18}}>🎥</span>, color: '#ff5000', authTypes: ['cookie'], supportQrcode: true },
  { value: 'bilibili',   label: 'B站',     icon: <span style={{fontSize:18}}>📺</span>, color: '#00aeec', authTypes: ['cookie'], supportQrcode: true },
  { value: 'weibo',      label: '微博',    icon: <span style={{fontSize:18}}>💬</span>, color: '#ff8200', authTypes: ['cookie'], supportQrcode: false },
  { value: 'zhihu',      label: '知乎',    icon: <span style={{fontSize:18}}>❓</span>, color: '#0066ff', authTypes: ['cookie'], supportQrcode: false },
  { value: 'wechat_mp',  label: '微信公众号', icon: <MessageOutlined style={{color:'#07C160',fontSize:16}} />, color: '#07C160', authTypes: ['qrcode'], supportQrcode: true },
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
const statusColorMap: Record<string, string> = {
  active: '#52c41a',
  healthy: '#52c41a',
  failed: '#ff4d4f',
  expired: '#faad14',
  unknown: '#8c8c8c',
}

const statusLabelMap: Record<string, string> = {
  active: '有效',
  healthy: '正常',
  failed: '失败',
  expired: '已过期',
  unknown: '未测试',
}

function StatusTag({ status, errorMessage }: { status: string; errorMessage?: string | null }) {
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

// ===== 连接卡片组件 — 参考 XHS_ALL_IN_ONE 账号矩阵卡片 =====
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
  const isChecking = testingId === conn.id
  const statusColor = statusColorMap[conn.status] || theme.textDisabled
  const isApiPlatform = platformMeta && !platformMeta.authTypes.includes('cookie')

  return (
    <div
      style={{
        background: theme.bgElevated,
        border: `1px solid ${theme.border}`,
        borderRadius: 10,
        padding: 16,
        minWidth: 240,
        flex: '1 1 240px',
        maxWidth: 320,
        transition: 'border-color 0.2s, box-shadow 0.2s',
        display: 'flex',
        flexDirection: 'column',
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
      {/* 头部：Avatar + 名称 + 状态 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <Avatar
          size={40}
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
            <StatusTag status={conn.status} errorMessage={conn.error_message} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
            {acquisitionMethodTag((conn as any).acquisition_method || 'manual')}
            <Text style={{ color: theme.textSecondary, fontSize: 12 }}>
              {authTypeLabel(conn.auth_type)}
            </Text>
          </div>
        </div>
      </div>

      {/* 统计行 — 参考 XHS_ALL_IN_ONE 的 Statistic 展示 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <div style={{ flex: 1, background: `${theme.primary}08`, borderRadius: 6, padding: '6px 8px' }}>
          <Text style={{ color: theme.textSecondary, fontSize: 10 }}>类型</Text>
          <div style={{ color: theme.textPrimary, fontSize: 13, fontWeight: 500 }}>
            {isApiPlatform ? 'API' : 'Cookie'}
          </div>
        </div>
        <div style={{ flex: 1, background: `${theme.primary}08`, borderRadius: 6, padding: '6px 8px' }}>
          <Text style={{ color: theme.textSecondary, fontSize: 10 }}>最后使用</Text>
          <div style={{ color: theme.textPrimary, fontSize: 13, fontWeight: 500 }}>
            {conn.last_used ? new Date(conn.last_used).toLocaleDateString() : '-'}
          </div>
        </div>
      </div>

      {/* 状态消息 */}
      {conn.error_message && (
        <div style={{ marginBottom: 8 }}>
          <Text style={{ color: theme.error, fontSize: 12 }} ellipsis>
            <ExclamationCircleOutlined style={{ marginRight: 4 }} />
            {conn.error_message}
          </Text>
        </div>
      )}

      {/* 底部操作按钮 — 参考 XHS_ALL_IN_ONE 的检查 + 删除 */}
      <div style={{ display: 'flex', gap: 6, marginTop: 'auto', borderTop: `1px solid ${theme.border}`, paddingTop: 10 }}>
        <Tooltip title="健康检查">
          <Button
            type="text"
            size="small"
            icon={isChecking ? <LoadingOutlined /> : <SafetyCertificateOutlined />}
            loading={isChecking}
            onClick={() => onTest(conn.id)}
            style={{ color: isChecking ? theme.primary : theme.textSecondary }}
          >
            {isChecking ? '检查中' : '检查'}
          </Button>
        </Tooltip>
        <div style={{ flex: 1 }} />
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
  onOpenAddDrawer,
}: {
  platformMeta: PlatformMeta
  connections: PlatformConnectionResponse[]
  testingId: string | null
  playwrightAvailable: boolean
  onTest: (id: string) => void
  onEdit: (conn: PlatformConnectionResponse) => void
  onDelete: (id: string) => void
  onOpenAddDrawer: (platform: string) => void
}) {
  const { theme } = useTheme()
  const isApiPlatform = !platformMeta.authTypes.includes('cookie')
  const activeCount = connections.filter(c => c.status === 'active').length
  const totalCount = connections.length

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
          <div style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: `${platformMeta.color}18`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            {platformMeta.icon}
          </div>
          <div>
            <Text style={{ color: theme.textPrimary, fontSize: 16, fontWeight: 600 }}>
              {platformMeta.label}
            </Text>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Badge
                count={totalCount}
                style={{ backgroundColor: `${platformMeta.color}33`, color: platformMeta.color }}
              />
              {activeCount > 0 && (
                <Text style={{ color: theme.success, fontSize: 12 }}>
                  {activeCount} 个有效
                </Text>
              )}
            </div>
          </div>
        </div>

        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => onOpenAddDrawer(platformMeta.value)}
          style={{ background: platformMeta.color, borderColor: platformMeta.color }}
        >
          绑定账号
        </Button>
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
          padding: '32px 0',
          textAlign: 'center',
          border: `1px dashed ${theme.borderLight}`,
          borderRadius: 8,
        }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <Text style={{ color: theme.textSecondary, fontSize: 13, display: 'block', marginBottom: 8 }}>
                  还没有绑定{platformMeta.label}的账号
                </Text>
                <Text style={{ color: theme.textDisabled, fontSize: 12, display: 'block', marginBottom: 12 }}>
                  {isApiPlatform
                    ? '添加 API Key 以使用该平台服务'
                    : '先绑定一个账号，用于数据采集、内容发布等功能'
                  }
                </Text>
                <Button
                  type="primary"
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() => onOpenAddDrawer(platformMeta.value)}
                  style={{ background: platformMeta.color, borderColor: platformMeta.color }}
                >
                  添加账号
                </Button>
              </div>
            }
          />
        </div>
      )}
    </Card>
  )
}

// ===== Cookie 导入面板 — 参考 XHS_ALL_IN_ONE 的 CookieImportPanel =====
function CookieImportPanel({
  platform,
  onImported,
}: {
  platform: string
  onImported: () => void
}) {
  const { theme } = useTheme()
  const [cookieString, setCookieString] = useState('')
  const [accountName, setAccountName] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const platformInfo = getPlatformMeta(platform)

  const handleImport = async () => {
    setError(null)
    if (!cookieString.includes('=')) {
      setError('请粘贴完整 Cookie 字符串，需包含 key=value 格式')
      return
    }
    setIsSubmitting(true)
    try {
      const name = accountName.trim() || `${platformInfo?.label || platform} (Cookie导入)`
      await createPlatformConnection({
        platform,
        name,
        auth_type: 'cookie',
        credentials: { content: cookieString.trim() },
      })
      message.success(`${name} 已加入账号矩阵`)
      onImported()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Cookie 无效或已过期')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block', fontSize: 13 }}>
          账号名称
        </Text>
        <Input
          placeholder="给这个账号起个名字，如：我的小红书小号"
          value={accountName}
          onChange={e => setAccountName(e.target.value)}
          style={{ background: theme.bgElevated, borderColor: theme.border, color: theme.textPrimary }}
        />
        <Text style={{ color: theme.textDisabled, fontSize: 11, marginTop: 4, display: 'block' }}>
          同一平台可以有多个账号，请用名称区分
        </Text>
      </div>

      <div>
        <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block', fontSize: 13 }}>
          Cookie 字符串
        </Text>
        <TextArea
          rows={6}
          value={cookieString}
          onChange={e => setCookieString(e.target.value)}
          placeholder="a1=...; web_session=...;"
          style={{
            background: theme.bgElevated,
            borderColor: theme.border,
            color: theme.textPrimary,
            fontFamily: 'monospace',
            fontSize: 12,
          }}
        />
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      <Button
        type="primary"
        icon={<ImportOutlined />}
        onClick={handleImport}
        loading={isSubmitting}
        block
      >
        {isSubmitting ? '校验中...' : '校验并导入'}
      </Button>
    </div>
  )
}

// ===== 二维码登录面板 — 参考 XHS_ALL_IN_ONE 的 QrLoginPanel =====
function QrLoginPanel({
  platform,
  playwrightAvailable,
  onConfirmed,
}: {
  platform: string
  playwrightAvailable: boolean
  onConfirmed: () => void
}) {
  const { theme } = useTheme()
  const [connectorName, setConnectorName] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [qrImage, setQrImage] = useState('')
  const [status, setStatus] = useState<string>('')
  const [statusText, setStatusText] = useState('点击下方按钮生成二维码')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval>>()
  const confirmedRef = useRef(false)
  // 记录刚创建但还未完成扫码的 connId，失败/取消时自动删除
  const pendingConnIdRef = useRef<string>('')
  const platformInfo = getPlatformMeta(platform)

  const isActive = isLoading || (status && !['success', 'failed', 'cancelled', 'expired'].includes(status))

  const statusColor = (s: string): string => {
    if (s === 'success') return theme.success
    if (['failed', 'expired', 'cancelled'].includes(s)) return theme.error
    if (['saving', 'cookies_extracting', 'cookies_extracted'].includes(s)) return theme.primary
    return theme.warning
  }

  // 微信公众号专用：轮询登录状态
  const startWechatMpPolling = (sid: string, connId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    setStatus('waiting')
    setStatusText('请使用微信扫描上方二维码')

    pollRef.current = setInterval(async () => {
      try {
        const res = await wechatMpLoginStatus(sid)
        const s = res?.status || 'waiting'
        setStatus(s)

        if (s === 'waiting') {
          setStatusText('请使用微信扫描上方二维码')
        } else if (s === 'scanned') {
          setStatusText(res?.message || '已扫码，请在手机端确认登录')
        } else if (s === 'confirmed') {
          clearInterval(pollRef.current)
          setStatusText('登录成功，正在保存...')
          setIsLoading(false)

          // 保存 Cookie 和 Token 到平台连接
          try {
            await updatePlatformConnection(connId, {
              credentials: {
                raw: res.cookie || '',
                token: res.token || '',
                source: 'qrcode',
              },
              status: 'active',
              account_id: res.token || undefined,
              account_avatar: res.head_img || undefined,
              acquisition_method: 'qrcode',
              account_name: res.nickname || connectorName || '微信公众号',
            })
            // 确认成功，清空 pending 标记（不再回滚）
            pendingConnIdRef.current = ''
            if (!confirmedRef.current) {
              confirmedRef.current = true
              setStatusText('账号绑定成功')
              message.success('微信公众号扫码登录成功！')
              onConfirmed()
            }
          } catch (e: any) {
            setStatus('failed')
            setStatusText('保存登录信息失败')
            setError(e?.response?.data?.detail || '保存失败')
            // 保存失败 → 删除这个半成品
            await rollbackPendingConn(connId)
          }
        } else if (s === 'expired') {
          clearInterval(pollRef.current)
          setStatusText('二维码已过期，请点击刷新')
          setIsLoading(false)
          // 过期 → 不删除（用户可能想刷新重试）
        } else if (s === 'error') {
          clearInterval(pollRef.current)
          setStatus('failed')
          setStatusText(res.message || '登录失败')
          setIsLoading(false)
          // 错误 → 删除半成品
          await rollbackPendingConn(connId)
        }
      } catch { /* ignore poll errors */ }
    }, 2000)
  }

  const connectWebSocket = (sid: string) => {
    // 开发环境直接连接后端 8000，生产环境通过当前 origin
    const isDev = import.meta.env.DEV
    const wsUrl = isDev
      ? `ws://${window.location.hostname}:8000/api/v1/acquire/qrcode/${sid}/ws`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws://'}${window.location.host}/api/v1/acquire/qrcode/${sid}/ws`
    console.log('[WS] Connecting to:', wsUrl)
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => { console.log('[WS] Connected!'); setIsLoading(true) }
    ws.onerror = (e) => { console.error('[WS] Error:', e); }

    ws.onmessage = (event) => {
      try {
        const msg: AcquisitionWSMessage = JSON.parse(event.data)
        if (msg.type === 'status_update') {
          setStatus(msg.status)
          setStatusText(msg.message)
          if (msg.data?.qr_image_base64) setQrImage(msg.data.qr_image_base64)
          if (msg.status === 'qr_scanned') {
            setStatusText('已扫码，请在手机端确认登录')
          }
        } else if (msg.type === 'completed') {
          setStatus(msg.status)
          setStatusText(msg.message)
          setIsLoading(false)
          if (msg.status === 'success' && !confirmedRef.current) {
            confirmedRef.current = true
            setStatusText('账号绑定成功')
            message.success('扫码登录成功！')
            onConfirmed()
          }
          ws.close()
        } else if (msg.type === 'error') {
          setStatus('failed')
          setStatusText(msg.message || '未知错误')
          setIsLoading(false)
          ws.close()
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => { setIsLoading(false) }
    ws.onerror = () => {
      setStatus('failed')
      setStatusText('WebSocket 连接失败')
      setIsLoading(false)
    }

    wsRef.current = ws
  }

  // 浏览器方式（Playwright/Patchright）的 WebSocket —— 微信公众号专用
  const connectPlaywrightWebSocket = (sid: string) => {
    const isDev = import.meta.env.DEV
    const wsUrl = isDev
      ? `ws://${window.location.hostname}:8000/api/v1/platforms/acquire/playwright/${sid}/ws`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws://'}${window.location.host}/api/v1/platforms/acquire/playwright/${sid}/ws`
    console.log('[WS Playwright] Connecting to:', wsUrl)
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => { setIsLoading(true) }

    ws.onmessage = (event) => {
      try {
        const msg: AcquisitionWSMessage = JSON.parse(event.data)
        if (msg.type === 'status_update') {
          setStatus(msg.status)
          setStatusText(msg.message)
        } else if (msg.type === 'completed') {
          setStatus(msg.status)
          setStatusText(msg.message)
          setIsLoading(false)
          if (msg.status === 'success' && !confirmedRef.current) {
            confirmedRef.current = true
            setStatusText('账号绑定成功')
            message.success('微信公众号登录成功！')
            onConfirmed()
          }
          ws.close()
        } else if (msg.type === 'error') {
          setStatus('failed')
          setStatusText(msg.message || '未知错误')
          setIsLoading(false)
          ws.close()
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => { setIsLoading(false) }
    ws.onerror = () => {
      setStatus('failed')
      setStatusText('WebSocket 连接失败')
      setIsLoading(false)
    }

    wsRef.current = ws
  }

  const startSession = async () => {
    setIsLoading(true)
    setError(null)
    confirmedRef.current = false

    // 微信公众号走专用扫码登录 API（bizlogin 流程）
    if (platform === 'wechat_mp') {
      try {
        // 先创建一个空的 PlatformConnection 用于关联
        const name = connectorName.trim() || '微信公众号'
        const connRes = await createPlatformConnection({
          platform: 'wechat_mp',
          name,
          auth_type: 'cookie',       // 最终获取的是 cookie 凭证
          acquisition_method: 'qrcode',  // 获取方式是扫码
          credentials: {},
        })
        const connId = (connRes as any)?.connection?.id || (connRes as any)?.id || ''
        if (!connId) {
          setStatus('failed')
          setStatusText('创建连接失败')
          setIsLoading(false)
          return
        }
        pendingConnIdRef.current = connId

        const qrRes = await wechatMpLoginQrcode(connId)
        if (qrRes?.qr_url) {
          setSessionId(qrRes.session_id || '')
          setQrImage(qrRes.qr_url)  // data:image/jpg;base64,... 格式
          setStatus('qr_generated')
          setStatusText('请使用微信扫描上方二维码')
          startWechatMpPolling(qrRes.session_id, connId)
        } else {
          setStatus('failed')
          setStatusText(qrRes?.message || '生成二维码失败')
          setIsLoading(false)
          await rollbackPendingConn(connId)
        }
      } catch (e: any) {
        setError(e?.message || '二维码生成失败，请稍后重试')
        setIsLoading(false)
      }
      return
    }

    // 其他平台使用通用 Qrcode 流程
    try {
      const res = await qrcodeGenerate({
        platform,
        connector_name: connectorName || undefined,
      })
      if (res.success && res.session_id) {
        setSessionId(res.session_id)
        setQrImage(res.qr_image_base64)
        setStatus('qr_generated')
        setStatusText(res.message || `请使用${platformInfo?.label || ''} App 扫描二维码`)
        connectWebSocket(res.session_id)
      } else {
        setStatus('failed')
        setStatusText(res.message || '生成失败')
        setIsLoading(false)
      }
    } catch (e: any) {
      setError(e?.message || '二维码生成失败，请稍后重试。')
      setIsLoading(false)
    }
  }

  const handleRefresh = async () => {
    if (!sessionId) return

    // 微信公众号刷新：重新调用登录接口（重新 startlogin）
    if (platform === 'wechat_mp') {
      try {
        // 获取当前 connId（可能存在 pendingConnIdRef 中）
        const connId = pendingConnIdRef.current
        if (!connId) {
          message.error('会话已过期，请重新生成')
          return
        }
        const res = await wechatMpLoginQrcode(connId)
        if (res?.qr_url) {
          setQrImage(res.qr_url)
          setStatus('qr_generated')
          setStatusText('二维码已刷新，请重新扫描')
          // 重新开始轮询（用新的 session_id）
          if (res.session_id) {
            setSessionId(res.session_id)
            startWechatMpPolling(res.session_id, connId)
          }
        }
      } catch { message.error('刷新失败') }
      return
    }

    try {
      const res = await refreshQrcode(sessionId)
      if (res.success) {
        setQrImage(res.qr_image_base64 || '')
        setStatus('qr_generated')
        setStatusText('二维码已刷新')
      }
    } catch { message.error('刷新失败') }
  }

  const reset = () => {
    wsRef.current?.close()
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = undefined }
    setSessionId('')
    setStatus('')
    setStatusText('点击下方按钮生成二维码')
    setQrImage('')
    setIsLoading(false)
    setError(null)
    confirmedRef.current = false
    pendingConnIdRef.current = ''
  }

  // 回滚：删除刚创建但未完成扫码的 PlatformConnection 记录
  const rollbackPendingConn = async (connId: string) => {
    if (!connId) return
    try {
      await deletePlatformConnection(connId)
      console.info(`[QrLoginPanel] Rolled back pending conn: ${connId}`)
    } catch (e) {
      console.warn(`[QrLoginPanel] Failed to rollback conn ${connId}:`, e)
    } finally {
      if (pendingConnIdRef.current === connId) {
        pendingConnIdRef.current = ''
      }
    }
  }

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 二维码展示区 */}
      <div style={{ textAlign: 'center' }}>
        {qrImage ? (
          <div style={{
            display: 'inline-block',
            padding: 16,
            background: '#fff',
            borderRadius: 12,
            marginBottom: 8,
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
            padding: '48px 0',
            textAlign: 'center',
            border: `1px dashed ${theme.borderLight}`,
            borderRadius: 12,
            marginBottom: 8,
          }}>
            <QrcodeOutlined style={{ fontSize: 48, color: theme.textDisabled }} />
            <div style={{ marginTop: 8 }}>
              <Text style={{ color: theme.textSecondary, fontSize: 13 }}>点击下方按钮生成二维码</Text>
            </div>
          </div>
        )}

        {/* 状态提示 */}
        {status && (
          <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            {isActive && <Spin indicator={<LoadingOutlined style={{ fontSize: 14 }} />} />}
            <Text style={{ color: statusColor(status), fontSize: 13 }}>
              {statusText}
            </Text>
          </div>
        )}

        {status === 'expired' && (
          <Button type="link" icon={<ReloadOutlined />} onClick={handleRefresh} style={{ marginBottom: 4 }}>
            刷新二维码
          </Button>
        )}
      </div>

      {/* 账号名称输入 */}
      <div>
        <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block', fontSize: 13 }}>账号名称</Text>
        <Input
          placeholder="给这个账号起个名字"
          value={connectorName}
          onChange={e => setConnectorName(e.target.value)}
          disabled={!!isActive}
          style={{ background: theme.bgElevated, borderColor: theme.border, color: theme.textPrimary }}
        />
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      {/* 操作按钮 */}
      <Space style={{ justifyContent: 'center', width: '100%' }}>
        {!isActive ? (
          <Button
            type="primary"
            icon={<QrcodeOutlined />}
            onClick={startSession}
            loading={isLoading}
          >
            {status === 'success' ? '重新生成' : '生成二维码'}
          </Button>
        ) : (
          <Button danger icon={<CloseCircleOutlined />} onClick={reset}>
            取消
          </Button>
        )}
        {status && !isActive && (
          <Button icon={<ReloadOutlined />} onClick={reset}>
            重置
          </Button>
        )}
      </Space>
    </div>
  )
}

// ===== 浏览器登录面板 — 使用 Patchright（Stealth 版 Playwright）=====
// Patchright 内置反检测功能，无需手动注入 Stealth JS
function BrowserLoginPanel({
  platform,
  playwrightAvailable,
  onConfirmed,
}: {
  platform: string
  playwrightAvailable: boolean
  onConfirmed: () => void
}) {
  const { theme } = useTheme()
  const [connectorName, setConnectorName] = useState('')
  const [status, setStatus] = useState<string>('')
  const [statusText, setStatusText] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const isActive = isLoading || (status && !['success', 'failed', 'cancelled', 'expired'].includes(status))

  const statusColor = (s: string): string => {
    if (s === 'success') return theme.success
    if (['failed', 'expired', 'cancelled'].includes(s)) return theme.error
    if (['saving', 'cookies_extracting', 'cookies_extracted'].includes(s)) return theme.primary
    return theme.warning
  }

  function statusToStep(s: string): number {
    switch (s) {
      case 'initializing': case 'browser_launching': return 0
      case 'page_loading': return 1
      case 'waiting_for_login': return 2
      case 'cookies_extracting': case 'cookies_extracted': return 3
      case 'saving': case 'success': case 'failed': case 'cancelled': case 'expired': return 4
      default: return 0
    }
  }

  function statusToProgress(s: string): number {
    switch (s) {
      case 'initializing': return 5
      case 'browser_launching': return 15
      case 'page_loading': return 30
      case 'waiting_for_login': return 45
      case 'cookies_extracting': return 70
      case 'cookies_extracted': return 80
      case 'saving': return 90
      case 'success': return 100
      default: return 0
    }
  }

  const connectWebSocket = (sid: string) => {
    // 开发环境直接连接后端 8000，生产环境通过当前 origin
    const isDev = import.meta.env.DEV
    const wsUrl = isDev
      ? `ws://${window.location.hostname}:8000/api/v1/platforms/acquire/playwright/${sid}/ws`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws://'}${window.location.host}/api/v1/platforms/acquire/playwright/${sid}/ws`
    console.log('[WS] Connecting to:', wsUrl)
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => { setIsLoading(true) }

    ws.onmessage = (event) => {
      try {
        const msg: AcquisitionWSMessage = JSON.parse(event.data)
        if (msg.type === 'status_update') {
          setStatus(msg.status)
          setStatusText(msg.message)
        } else if (msg.type === 'completed') {
          setStatus(msg.status)
          setStatusText(msg.message)
          setIsLoading(false)
          if (msg.status === 'success') {
            message.success('Cookie 获取成功！')
            onConfirmed()
          }
          ws.close()
        } else if (msg.type === 'error') {
          setStatus('failed')
          setStatusText(msg.message || '未知错误')
          setIsLoading(false)
          ws.close()
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => { setIsLoading(false) }
    ws.onerror = () => {
      setStatus('failed')
      setStatusText('WebSocket 连接失败')
      setIsLoading(false)
    }

    wsRef.current = ws
  }

  const handleStart = async () => {
    if (!platform) return
    setIsLoading(true)
    setStatus('initializing')
    setStatusText('正在初始化...')
    setError(null)
    try {
      const res = await playwrightStart({
        platform,
        headless: false,
        connector_name: connectorName || undefined,
      })
      if (res.success && res.session_id) {
        setSessionId(res.session_id)
        setStatus('browser_launching')
        setStatusText(res.message || '浏览器启动中...')
        connectWebSocket(res.session_id)
      } else {
        setStatus('failed')
        setStatusText(res.message || '启动失败')
        setIsLoading(false)
      }
    } catch (e: any) {
      setError(e?.message || '启动失败')
      setIsLoading(false)
    }
  }

  const handleCancel = async () => {
    if (sessionId) {
      try { await cancelPlaywrightSession(sessionId) } catch { /* ignore */ }
    }
    wsRef.current?.close()
    setIsLoading(false)
    setStatus('cancelled')
    setStatusText('已取消')
  }

  const reset = () => {
    wsRef.current?.close()
    setSessionId('')
    setStatus('')
    setStatusText('')
    setIsLoading(false)
    setError(null)
  }

  useEffect(() => {
    return () => { wsRef.current?.close() }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {!playwrightAvailable && (
        <Alert
          type="warning"
          showIcon
          message="浏览器自动化工具未安装"
          description="请在服务器执行: pip install patchright && patchright install chromium"
        />
      )}

      {/* 进度展示 */}
      {status && (
        <div style={{
          background: 'rgba(0,0,0,0.2)',
          border: `1px solid ${statusColor(status)}`,
          borderRadius: 8,
          padding: 16,
        }}>
          <Progress
            percent={statusToProgress(status)}
            status={
              ['failed', 'cancelled', 'expired'].includes(status) ? 'exception' :
              status === 'success' ? 'success' : 'active'
            }
            strokeColor={statusColor(status)}
          />
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
            {isActive && <Spin indicator={<LoadingOutlined style={{ fontSize: 14 }} />} />}
            <Text style={{ color: statusColor(status), fontSize: 13 }}>{statusText}</Text>
          </div>
        </div>
      )}

      {/* 账号名称 */}
      <div>
        <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block', fontSize: 13 }}>账号名称</Text>
        <Input
          placeholder="给这个账号起个名字，如：我的抖音企业号"
          value={connectorName}
          onChange={e => setConnectorName(e.target.value)}
          disabled={!!isActive}
          style={{ background: theme.bgElevated, borderColor: theme.border, color: theme.textPrimary }}
        />
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      {/* 操作按钮 */}
      <Space>
        {!isActive ? (
          <Button
            type="primary"
            icon={<DesktopOutlined />}
            onClick={handleStart}
            disabled={!playwrightAvailable}
          >
            {status === 'success' ? '重新获取' : '启动浏览器'}
          </Button>
        ) : (
          <Button danger icon={<CloseCircleOutlined />} onClick={handleCancel}>
            取消
          </Button>
        )}
        {status && !isActive && (
          <Button icon={<ReloadOutlined />} onClick={reset}>
            重置
          </Button>
        )}
      </Space>

      <Alert
        type="info"
        showIcon
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
  )
}

// ===== API Key 导入面板 =====
function ApiKeyPanel({
  platform,
  onImported,
}: {
  platform: string
  onImported: () => void
}) {
  const { theme } = useTheme()
  const [accountName, setAccountName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const platformInfo = getPlatformMeta(platform)

  const handleImport = async () => {
    setError(null)
    if (!apiKey.trim()) {
      setError('请输入 API Key')
      return
    }
    setIsSubmitting(true)
    try {
      const name = accountName.trim() || `${platformInfo?.label || platform} API`
      await createPlatformConnection({
        platform,
        name,
        auth_type: 'api_key',
        credentials: { api_key: apiKey.trim() },
      })
      message.success(`${name} 已加入账号矩阵`)
      onImported()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'API Key 无效')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block', fontSize: 13 }}>
          账号名称
        </Text>
        <Input
          placeholder={`如：${platformInfo?.label || platform} API`}
          value={accountName}
          onChange={e => setAccountName(e.target.value)}
          style={{ background: theme.bgElevated, borderColor: theme.border, color: theme.textPrimary }}
        />
      </div>

      <div>
        <Text style={{ color: theme.textPrimary, marginBottom: 6, display: 'block', fontSize: 13 }}>
          API Key
        </Text>
        <Input.Password
          placeholder="输入 API Key..."
          value={apiKey}
          onChange={e => setApiKey(e.target.value)}
          style={{ background: theme.bgElevated, borderColor: theme.border, color: theme.textPrimary }}
        />
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      <Button
        type="primary"
        icon={<ApiOutlined />}
        onClick={handleImport}
        loading={isSubmitting}
        block
      >
        {isSubmitting ? '校验中...' : '保存'}
      </Button>
    </div>
  )
}

// ===== 添加账号抽屉 — 参考 XHS_ALL_IN_ONE 的 AddAccountDrawer =====
type AddMethod = 'cookie' | 'qrcode' | 'browser'

function AddAccountDrawer({
  open,
  platform,
  onClose,
  onBound,
  playwrightAvailable,
}: {
  open: boolean
  platform: string
  onClose: () => void
  onBound: () => void
  playwrightAvailable: boolean
}) {
  const { theme } = useTheme()
  const platformMeta = getPlatformMeta(platform)
  // API Key 平台：既不支持 Cookie 也不支持扫码
  const isApiPlatform = platformMeta && !platformMeta.authTypes.includes('cookie') && !platformMeta.authTypes.includes('qrcode')

  // Cookie 平台有三种方式，扫码平台有扫码+浏览器，API 平台只有 API Key
  const methodOptions = isApiPlatform
    ? [{ label: 'API Key', value: 'cookie' as AddMethod }]
    : [
        ...(platformMeta?.authTypes.includes('cookie') ? [{ label: 'Cookie', value: 'cookie' as AddMethod, icon: <KeyOutlined /> }] : []),
        ...(platformMeta?.supportQrcode ? [{ label: '扫码登录', value: 'qrcode' as AddMethod, icon: <QrcodeOutlined /> }] : []),
        ...(playwrightAvailable ? [{ label: '浏览器', value: 'browser' as AddMethod, icon: <ChromeOutlined /> }] : []),
      ]

  const [method, setMethod] = useState<AddMethod>('cookie')

  // 平台切换时重置方法
  useEffect(() => {
    if (isApiPlatform) {
      setMethod('cookie')
    } else if (platformMeta?.supportQrcode) {
      setMethod('qrcode')
    } else {
      setMethod('cookie')
    }
  }, [platform, isApiPlatform, platformMeta])

  return (
    <Drawer
      title={
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {platformMeta?.icon}
            <span>绑定 {platformMeta?.label || platform} 账号</span>
          </div>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>
            选择认证方式，添加平台账号
          </Text>
        </div>
      }
      placement="right"
      width={420}
      open={open}
      onClose={onClose}
      destroyOnClose
      styles={{
        header: { background: theme.bgCard, borderBottom: `1px solid ${theme.border}` },
        body: { background: theme.bgPage, padding: 24 },
      }}
    >
      {/* 方式选择 — 参考 XHS_ALL_IN_ONE 的 Segmented */}
      {methodOptions.length > 1 && (
        <div style={{ marginBottom: 20 }}>
          <Segmented
            block
            value={method}
            onChange={(val) => setMethod(val as AddMethod)}
            options={methodOptions.map(opt => ({
              label: (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
                  {opt.icon}
                  <span>{opt.label}</span>
                </div>
              ),
              value: opt.value,
            }))}
          />
        </div>
      )}

      {/* 面板内容 */}
      {isApiPlatform ? (
        <ApiKeyPanel platform={platform} onImported={onBound} />
      ) : method === 'cookie' ? (
        <CookieImportPanel platform={platform} onImported={onBound} />
      ) : method === 'qrcode' ? (
        <QrLoginPanel platform={platform} playwrightAvailable={playwrightAvailable} onConfirmed={onBound} />
      ) : (
        <BrowserLoginPanel platform={platform} playwrightAvailable={playwrightAvailable} onConfirmed={onBound} />
      )}
    </Drawer>
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

  // ===== 抽屉状态 =====
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerPlatform, setDrawerPlatform] = useState('')

  // ===== 编辑弹窗 =====
  const [modalVisible, setModalVisible] = useState(false)
  const [editingConn, setEditingConn] = useState<PlatformConnectionResponse | null>(null)
  const [form] = Form.useForm()

  // ===== 加载数据 =====
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [connRes, platformRes] = await Promise.all([
        listPlatformConnections(),
        getSupportedPlatforms(),
      ])
      const visibleConnections = (connRes.connections || []).filter((conn: PlatformConnectionResponse) => {
        return !(
          conn.platform === 'wechat_mp' &&
          conn.acquisition_method === 'qrcode' &&
          conn.status !== 'active' &&
          !conn.has_cookie_content
        )
      })
      setConnections(visibleConnections)
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

  // ===== 按平台分组 =====
  const groupedConnections = useCallback(() => {
    const groups: Record<string, PlatformConnectionResponse[]> = {}
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

  const groups = groupedConnections()

  // 有连接的平台
  const activePlatforms = PLATFORM_METAS.filter(pm => groups[pm.value] && groups[pm.value].length > 0)

  // 没有连接的平台
  const inactivePlatforms = PLATFORM_METAS.filter(pm => !groups[pm.value] || groups[pm.value].length === 0)

  // ===== 统计 =====
  const activeCount = connections.filter(c => c.status === 'active').length
  const failedCount = connections.filter(c => c.status === 'failed').length
  const expiredCount = connections.filter(c => c.status === 'expired').length

  // ===== 连接 CRUD =====
  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await testPlatformConnection(id)
      if (result.success) {
        message.success('健康检查通过：' + result.message)
      } else {
        message.error('健康检查失败：' + result.message)
      }
      loadData()
    } catch (e: any) {
      message.error('检查失败：' + (e?.response?.data?.detail || '未知错误'))
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

  // ===== 打开添加账号抽屉 =====
  const onOpenAddDrawer = (platform: string) => {
    setDrawerPlatform(platform)
    setDrawerOpen(true)
  }

  return (
    <div style={{ maxWidth: 1200 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ color: theme.textPrimary, marginBottom: 4 }}>
          <KeyOutlined style={{ marginRight: 12 }} />
          账号中心
        </Title>
        <Text style={{ color: theme.textSecondary, fontSize: 14 }}>
          管理各平台 Cookie / 授权凭证，支持多账号登录态、健康检查
        </Text>
      </div>

      {/* 统计栏 — 参考 XHS_ALL_IN_ONE 的统计卡片 */}
      <Row gutter={12} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <div style={{
            background: theme.bgCard,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            padding: '14px 20px',
          }}>
            <Statistic
              title={<span style={{ color: theme.textSecondary, fontSize: 12 }}>已配置平台</span>}
              value={activePlatforms.length}
              valueStyle={{ color: theme.textPrimary, fontWeight: 600 }}
            />
          </div>
        </Col>
        <Col span={6}>
          <div style={{
            background: theme.bgCard,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            padding: '14px 20px',
          }}>
            <Statistic
              title={<span style={{ color: theme.textSecondary, fontSize: 12 }}>有效连接</span>}
              value={activeCount}
              valueStyle={{ color: theme.success, fontWeight: 600 }}
              prefix={<CheckCircleOutlined />}
            />
          </div>
        </Col>
        <Col span={6}>
          <div style={{
            background: theme.bgCard,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            padding: '14px 20px',
          }}>
            <Statistic
              title={<span style={{ color: theme.textSecondary, fontSize: 12 }}>连接失败</span>}
              value={failedCount}
              valueStyle={{ color: theme.error, fontWeight: 600 }}
              prefix={failedCount > 0 ? <CloseCircleOutlined /> : undefined}
            />
          </div>
        </Col>
        <Col span={6}>
          <div style={{
            background: theme.bgCard,
            border: `1px solid ${theme.border}`,
            borderRadius: 10,
            padding: '14px 20px',
          }}>
            <Statistic
              title={<span style={{ color: theme.textSecondary, fontSize: 12 }}>已过期</span>}
              value={expiredCount}
              valueStyle={{ color: theme.warning, fontWeight: 600 }}
              prefix={expiredCount > 0 ? <ExclamationCircleOutlined /> : undefined}
            />
          </div>
        </Col>
      </Row>

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
          onOpenAddDrawer={onOpenAddDrawer}
        />
      ))}

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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <Text style={{ color: theme.textSecondary, fontSize: 13 }}>
              其他平台 — 点击快速添加
            </Text>
            <Badge count={inactivePlatforms.length} style={{ backgroundColor: `${theme.textDisabled}22`, color: theme.textDisabled }} />
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {inactivePlatforms.map(pm => {
              const isApiPlatform = !pm.authTypes.includes('cookie')
              return (
                <Button
                  key={pm.value}
                  type="dashed"
                  size="small"
                  style={{
                    borderColor: `${pm.color}44`,
                    color: pm.color,
                    borderRadius: 6,
                  }}
                  icon={pm.icon}
                  onClick={() => onOpenAddDrawer(pm.value)}
                >
                  {pm.label} <PlusOutlined style={{ fontSize: 10 }} />
                </Button>
              )
            })}
          </div>
        </Card>
      )}

      {/* ===== 添加账号抽屉 — 参考 XHS_ALL_IN_ONE 的 AddAccountDrawer ===== */}
      <AddAccountDrawer
        open={drawerOpen}
        platform={drawerPlatform}
        onClose={() => setDrawerOpen(false)}
        onBound={() => {
          loadData()
          setDrawerOpen(false)
        }}
        playwrightAvailable={playwrightAvailable}
      />

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
