/**
 * YLCraft — 智能体页面（Agent Hub）
 *
 * 参考 Hermes Agent 思想：
 * - 三层记忆（短期会话 / 中期上下文 / 长期 Skills）
 * - ToolRegistry 驱动的工具调用
 * - SSE 流式响应（打字机效果）
 * - 历史会话管理
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Card,
  Input,
  Button,
  List,
  Badge,
  Tag,
  Space,
  Tooltip,
  Drawer,
  Typography,
  Spin,
  message,
  Divider,
  Avatar,
  Empty,
  Tabs,
  Statistic,
  Row,
  Col,
} from 'antd'
import {
  RobotOutlined,
  SendOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ToolOutlined,
  ExperimentOutlined,
  ClearOutlined,
  FireOutlined,
  ThunderboltOutlined,
  FolderOpenOutlined,
  ScissorOutlined,
  FileTextOutlined,
  CustomerServiceOutlined,
} from '@ant-design/icons'
import { listAgentSessions, deleteAgentSession, listAgentTools } from '../../api/agent'
import type { AgentMessage, AgentToolCall, AgentToolCallResult } from '../../types/agent'

const { Text, Title } = Typography
const { TextArea } = Input

// 工具分类图标映射
const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  asset: <FolderOpenOutlined />,
  clip: <ScissorOutlined />,
  subtitle: <FileTextOutlined />,
  bgm: <CustomerServiceOutlined />,
  breaker: <FireOutlined />,
  general: <ToolOutlined />,
}

const CATEGORY_COLORS: Record<string, string> = {
  asset: 'blue',
  clip: 'purple',
  subtitle: 'orange',
  bgm: 'green',
  breaker: 'red',
  general: 'default',
}

interface SessionItem {
  id: string
  title: string
  created_at: string
  updated_at: string
}

interface ToolItem extends AgentToolCall {}

export default function AgentPage() {
  // ===== 状态 =====
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [replyText, setReplyText] = useState('') // 流式打字机
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [tools, setTools] = useState<ToolItem[]>([])
  const [toolCalls, setToolCalls] = useState<AgentToolCallResult[]>([])
  const [sessionsOpen, setSessionsOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('chat')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // ===== 加载会话列表 & 工具列表 =====
  const loadSessions = useCallback(async () => {
    try {
      const data = await listAgentSessions()
      setSessions(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error('Failed to load sessions', e)
    }
  }, [])

  const loadTools = useCallback(async () => {
    try {
      const data = await listAgentTools()
      setTools(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error('Failed to load tools', e)
    }
  }, [])

  useEffect(() => {
    loadSessions()
    loadTools()
  }, [loadSessions, loadTools])

  // ===== 自动滚动 =====
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, replyText])

  // ===== 发送消息 =====
  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)
    setReplyText('')
    setToolCalls([])
    setActiveTab('chat')

    // 追加用户消息
    const userMsg: AgentMessage = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])

    try {
      const params = new URLSearchParams()
      if (currentSessionId) params.set('session_id', currentSessionId)

      const response = await fetch(`/api/v1/agent/chat?${params}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, context: {}, stream: true }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let sessionId = currentSessionId

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            switch (event.event) {
              case 'token':
                setReplyText(prev => prev + event.data)
                break
              case 'tool_calls':
                setToolCalls(event.data || [])
                setActiveTab('tools')
                break
              case 'done':
                sessionId = event.data?.session_id
                break
              case 'error':
                message.error(`Agent 错误: ${event.data}`)
                break
            }
          } catch (e) {
            // ignore parse errors
          }
        }
      }

      // 追加 AI 回复
      if (replyText || sessionId !== currentSessionId) {
        const assistantMsg: AgentMessage = { role: 'assistant', content: replyText }
        setMessages(prev => [...prev, assistantMsg])
        setReplyText('')
      }

      // 更新当前会话
      if (sessionId) setCurrentSessionId(sessionId)

      // 刷新会话列表
      await loadSessions()
    } catch (e: any) {
      message.error(`发送失败: ${e.message}`)
      // 回退：移除刚添加的用户消息
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }, [input, loading, currentSessionId, replyText, loadSessions])

  // ===== 快捷提示 =====
  const quickPrompts = [
    '帮我搜索健身相关的视频素材',
    '提取这个视频的字幕',
    '给视频添加 BGM',
    '分析这个抖音链接的文案结构',
  ]

  // ===== 切换会话 =====
  const switchSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId)
    setSessionsOpen(false)
    const data = await fetch(`/api/v1/agent/sessions/${sessionId}`).then(r => r.json())
    setMessages(data.messages || [])
    setToolCalls([])
    setActiveTab('chat')
  }

  // ===== 新建会话 =====
  const newSession = () => {
    setCurrentSessionId(null)
    setMessages([])
    setToolCalls([])
    setActiveTab('chat')
    setSessionsOpen(false)
  }

  // ===== 删除会话 =====
  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await deleteAgentSession(sessionId)
    if (currentSessionId === sessionId) newSession()
    await loadSessions()
    message.success('会话已删除')
  }

  // ===== 按键事件 =====
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 12 }}>
      {/* ===== 头部工具栏 ===== */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <RobotOutlined style={{ fontSize: 24, color: '#00d4ff' }} />
        <Title level={4} style={{ margin: 0, flex: 1 }}>
          智能体
          <Text type="secondary" style={{ fontSize: 14, marginLeft: 12 }}>
            — 越用越聪明，懂你的视频创作助手
          </Text>
        </Title>
        <Space>
          <Badge count={sessions.length} offset={[6, 0]}>
            <Button icon={<HistoryOutlined />} onClick={() => setSessionsOpen(true)}>
              历史会话
            </Button>
          </Badge>
          <Button icon={<ToolOutlined />} onClick={() => setToolsOpen(true)}>
            工具 ({tools.length})
          </Button>
        </Space>
      </div>

      {/* ===== 主内容区 ===== */}
      <div style={{ flex: 1, display: 'flex', gap: 12, minHeight: 0 }}>
        {/* 左侧：对话 / 工具调用 */}
        <Card
          style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
          styles={{ body: { flex: 1, display: 'flex', flexDirection: 'column', padding: 0 } }}
        >
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'chat',
                label: '对话',
                children: (
                  <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
                    {/* 空状态 */}
                    {messages.length === 0 && !replyText && (
                      <Empty
                        image={<RobotOutlined style={{ fontSize: 64, color: '#00d4ff' }} />}
                        description={
                          <div>
                            <p>告诉我想做什么，比如：</p>
                            <Space wrap>
                              {quickPrompts.map((p, i) => (
                                <Tag
                                  key={i}
                                  style={{ cursor: 'pointer', padding: '4px 12px' }}
                                  onClick={() => setInput(p)}
                                >
                                  {p}
                                </Tag>
                              ))}
                            </Space>
                          </div>
                        }
                      />
                    )}

                    {/* 历史消息 */}
                    {messages.map((msg, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                          marginBottom: 16,
                        }}
                      >
                        <Space align="end">
                          {msg.role !== 'user' && (
                            <Avatar
                              size={28}
                              icon={<RobotOutlined />}
                              style={{ backgroundColor: '#00d4ff' }}
                            />
                          )}
                          <div
                            style={{
                              background:
                                msg.role === 'user'
                                  ? 'linear-gradient(135deg, #00d4ff, #0080ff)'
                                  : '#f5f5f5',
                              color: msg.role === 'user' ? '#fff' : '#333',
                              borderRadius: 12,
                              padding: '10px 14px',
                              maxWidth: '70%',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                            }}
                          >
                            {msg.content}
                          </div>
                          {msg.role === 'user' && (
                            <Avatar size={28} style={{ backgroundColor: '#1890ff' }}>
                              U
                            </Avatar>
                          )}
                        </Space>
                      </div>
                    ))}

                    {/* 流式回复中 */}
                    {replyText && (
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'flex-start',
                          marginBottom: 16,
                        }}
                      >
                        <Space align="end">
                          <Avatar
                            size={28}
                            icon={<RobotOutlined />}
                            style={{ backgroundColor: '#00d4ff' }}
                          />
                          <div
                            style={{
                              background: '#f5f5f5',
                              borderRadius: 12,
                              padding: '10px 14px',
                              maxWidth: '70%',
                              whiteSpace: 'pre-wrap',
                              color: '#333',
                            }}
                          >
                            {replyText}
                            <Spin size="small" style={{ marginLeft: 8 }} />
                          </div>
                        </Space>
                      </div>
                    )}

                    <div ref={messagesEndRef} />
                  </div>
                ),
              },
              {
                key: 'tools',
                label: (
                  <span>
                    工具调用
                    {toolCalls.length > 0 && (
                      <Badge count={toolCalls.length} style={{ marginLeft: 8 }} />
                    )}
                  </span>
                ),
                children: (
                  <div style={{ padding: 12 }}>
                    {toolCalls.length === 0 ? (
                      <Empty description="暂无工具调用" />
                    ) : (
                      <List
                        size="small"
                        dataSource={toolCalls}
                        renderItem={item => (
                          <List.Item>
                            <Space>
                              <Tag
                                color={item.success ? 'success' : 'error'}
                                icon={<ToolOutlined />}
                              >
                                {item.name}
                              </Tag>
                              {item.success ? (
                                <Text type="secondary">
                                  {item.duration_ms}ms
                                </Text>
                              ) : (
                                <Text type="danger">{item.error}</Text>
                              )}
                            </Space>
                          </List.Item>
                        )}
                      />
                    )}
                  </div>
                ),
              },
            ]}
          />
        </Card>
      </div>

      {/* ===== 输入框 ===== */}
      <Card styles={{ body: { padding: '12px 16px' } }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <TextArea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="告诉我想做什么...（Enter 发送，Shift+Enter 换行）"
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ flex: 1 }}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={sendMessage}
            loading={loading}
            style={{ height: 'auto' }}
          >
            发送
          </Button>
        </div>
        {/* 快捷提示 */}
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>快捷指令：</Text>
          {quickPrompts.slice(0, 2).map((p, i) => (
            <Tag
              key={i}
              style={{ cursor: 'pointer', marginLeft: 4, fontSize: 12 }}
              onClick={() => !loading && setInput(p)}
            >
              {p}
            </Tag>
          ))}
        </div>
      </Card>

      {/* ===== 历史会话抽屉 ===== */}
      <Drawer
        title="历史会话"
        placement="right"
        width={360}
        open={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        extra={
          <Button type="primary" size="small" onClick={newSession}>
            新建会话
          </Button>
        }
      >
        <List
          dataSource={sessions}
          locale={{ emptyText: '暂无历史会话' }}
          renderItem={item => (
            <List.Item
              key={item.id}
              style={{ cursor: 'pointer' }}
              onClick={() => switchSession(item.id)}
              extra={
                <Button
                  type="text"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={e => handleDeleteSession(item.id, e)}
                />
              }
            >
              <List.Item.Meta
                avatar={
                  <Avatar
                    icon={<RobotOutlined />}
                    style={{
                      backgroundColor:
                        currentSessionId === item.id ? '#00d4ff' : '#ccc',
                    }}
                  />
                }
                title={item.title}
                description={new Date(item.updated_at).toLocaleString('zh-CN')}
              />
            </List.Item>
          )}
        />
      </Drawer>

      {/* ===== 工具列表抽屉 ===== */}
      <Drawer
        title="可用工具"
        placement="right"
        width={400}
        open={toolsOpen}
        onClose={() => setToolsOpen(false)}
      >
        {['asset', 'clip', 'subtitle', 'bgm', 'breaker', 'general'].map(cat => {
          const catTools = tools.filter(t => t.category === cat)
          if (!catTools.length) return null
          return (
            <div key={cat} style={{ marginBottom: 16 }}>
              <Tag
                color={CATEGORY_COLORS[cat]}
                icon={CATEGORY_ICONS[cat]}
                style={{ marginBottom: 8 }}
              >
                {cat.toUpperCase()}
              </Tag>
              <List
                size="small"
                dataSource={catTools}
                renderItem={tool => (
                  <List.Item>
                    <div>
                      <Text strong style={{ fontSize: 13 }}>
                        {tool.name}
                      </Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {tool.description}
                      </Text>
                    </div>
                  </List.Item>
                )}
              />
            </div>
          )
        })}
      </Drawer>
    </div>
  )
}
