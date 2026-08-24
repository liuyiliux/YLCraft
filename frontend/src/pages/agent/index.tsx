/**
 * YLCraft Agent Center
 *
 * Practical Hermes-style agent workspace:
 * profile/persona + tool permissions + memory + traceable project tools.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ApiOutlined,
  ApartmentOutlined,
  CheckCircleOutlined,
  ClearOutlined,
  CustomerServiceOutlined,
  DeleteOutlined,
  FileTextOutlined,
  PictureOutlined,
  FireOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  PlusOutlined,
  ProjectOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  ScissorOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  StopOutlined,
  ToolOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import {
  cancelAgentRun,
  confirmAgentRunStep,
  createAgentSkillDraftFromRun,
  createAgentProfile,
  continueAgentRun,
  delegateAgentRun,
  deleteAgentSession,
  exportAgentRunMarkdown,
  getAgentMemories,
  getAgentRun,
  getAgentRunTree,
  getAgentRunLinkedLogs,
  getAgentSession,
  inspectAgentRunSkillCandidate,
  listAgentRuns,
  listAgentSkills,
  listAgentProfiles,
  listAgentSessions,
  listAgentTools,
  retryAgentRunStep,
  saveAgentMemoryCandidates,
  saveAgentMemory,
  deleteAgentMemory,
  discardAgentMemoryCandidates,
  deleteAgentThread,
  testAgentTool,
  getAgentThread,
  listAgentThreads,
  updateAgentProfile,
} from '../../api/agent'
import { listConnectors } from '../../api'
import type {
  AgentMessage,
  AgentDelegation,
  AgentMemory,
  AgentProfile,
  AgentRun,
  AgentRunStep,
  AgentSkill,
  AgentToolCall,
  AgentToolCallResult,
} from '../../types/agent'
import { useTheme } from '../../constants/theme'
import AgentPageErrorBoundary from '../../components/agent/AgentPageErrorBoundary'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

const normalizeModelList = (value?: string[] | string) => {
  if (Array.isArray(value)) return value
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.map(item => String(item))
  } catch {
    // Some connector imports store models as comma/newline separated text.
  }
  return value
    .split(/[\n,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

interface RoutedSkillSummary {
  skill_id: string
  reason?: string
  score?: number
  source?: string
  trigger_type?: string
  matches?: string[]
}

const extractRunRoutedSkills = (run?: AgentRun | null): RoutedSkillSummary[] => {
  const byId = new Map<string, RoutedSkillSummary>()
  ;(run?.steps || [])
    .filter(step => step.step_type === 'skill_route')
    .forEach(step => {
      const routed = Array.isArray(step.output?.routed_skills) ? step.output.routed_skills : []
      routed.forEach((item: any) => {
        const skillId = String(item?.skill_id || '').trim()
        if (!skillId) return
        const current = byId.get(skillId)
        if (!current || Number(item?.score || 0) > Number(current.score || 0)) {
          byId.set(skillId, {
            skill_id: skillId,
            reason: item?.reason,
            score: item?.score,
            source: item?.source,
            trigger_type: item?.trigger_type,
            matches: Array.isArray(item?.matches) ? item.matches.map((match: any) => String(match)) : [],
          })
        }
      })
    })
  return Array.from(byId.values()).sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  creative_project: <ProjectOutlined />,
  character: <RobotOutlined />,
  novel: <FileTextOutlined />,
  asset: <FolderOpenOutlined />,
  semantic_search: <SearchOutlined />,
  lineage: <ApartmentOutlined />,
  reader: <FileTextOutlined />,
  export: <FolderOpenOutlined />,
  platform_source: <SearchOutlined />,
  download: <FolderOpenOutlined />,
  wechat_mp: <FileTextOutlined />,
  tts: <CustomerServiceOutlined />,
  ebook: <FileTextOutlined />,
  clip: <ScissorOutlined />,
  subtitle: <FileTextOutlined />,
  bgm: <CustomerServiceOutlined />,
  breaker: <FireOutlined />,
  image: <PictureOutlined />,
  video: <VideoCameraOutlined />,
  ai_config: <ApiOutlined />,
  prompt_template: <FileTextOutlined />,
  task: <HistoryOutlined />,
  general: <ToolOutlined />,
}

const CATEGORY_COLORS: Record<string, string> = {
  creative_project: 'cyan',
  character: 'geekblue',
  novel: 'green',
  asset: 'blue',
  semantic_search: 'cyan',
  lineage: 'purple',
  reader: 'geekblue',
  export: 'volcano',
  platform_source: 'magenta',
  download: 'blue',
  wechat_mp: 'green',
  tts: 'orange',
  ebook: 'gold',
  clip: 'purple',
  subtitle: 'orange',
  bgm: 'green',
  breaker: 'red',
  image: 'cyan',
  video: 'magenta',
  ai_config: 'volcano',
  prompt_template: 'gold',
  task: 'lime',
  general: 'default',
}

const CATEGORY_LABELS: Record<string, string> = {
  download: '下载解析',
  wechat_mp: '公众号',
  tts: '语音合成',
  ebook: '电子书',
  semantic_search: '语义检索',
  lineage: '素材血缘',
  reader: '本地阅读',
  export: '导出质检',
  platform_source: '平台采集',
  creative_project: '创作项目',
  character: '角色库',
  novel: '小说库',
  asset: '素材库',
  clip: '剪辑',
  subtitle: '字幕',
  bgm: 'BGM',
  breaker: '爆款拆解',
  image: 'AI 生图',
  video: 'AI 视频',
  ai_config: 'AI 配置',
  prompt_template: 'Prompt 模板',
  task: '任务中心',
  general: '通用',
}

const GROUPED_CATEGORIES = ['creative_project', 'character', 'novel', 'asset', 'semantic_search', 'lineage', 'reader', 'export', 'platform_source', 'download', 'wechat_mp', 'tts', 'ebook', 'task', 'ai_config', 'prompt_template', 'image', 'video', 'clip', 'subtitle', 'bgm', 'breaker', 'general']

const RISK_LABELS: Record<string, string> = {
  read: '只读',
  write: '写入',
  delete: '删除',
  external: '外部访问',
  costly: '消耗模型',
}

const RISK_COLORS: Record<string, string> = {
  read: 'default',
  write: 'blue',
  delete: 'red',
  external: 'magenta',
  costly: 'orange',
}

const ROLE_TYPE_LABELS: Record<string, string> = {
  orchestrator: '总控 / 编排',
  director: '天意导演',
  writer: '小说作者',
  character_designer: '角色设定',
  storyboard_director: '分镜导演',
  role_actor: '角色演员',
  editor: '编辑润色',
  asset_curator: '素材管家',
  reviewer: '质检编辑',
  assistant: '通用助手',
}

const ROLE_TYPE_OPTIONS = Object.entries(ROLE_TYPE_LABELS).map(([value, label]) => ({ value, label }))

const QUICK_PROMPTS = [
  '列出最近的创作项目，并告诉我哪个最适合继续推进',
  '检查当前短剧项目的大纲、正文、脚本和分镜完成情况',
  '帮我同步项目圣经，并指出角色卡和参考图还缺什么',
  '搜索素材库里最近生成的角色立绘和分镜图',
]

const EXECUTION_LOOP_STAGES = ['计划', '工具', '观察', '继续']

const STEP_TYPE_LABELS: Record<string, string> = {
  intake: '接收请求',
  context_pack: '组装上下文',
  skill_route: '匹配 Skill',
  llm_response: '模型响应',
  tool_call: '工具调用',
  observe: '观察结果',
  delegate_subtask: '委派子任务',
  final: '最终回答',
}

const DEFAULT_WORKFLOW_OPTIONS = [
  { label: '通用助手', value: 'general_assistant' },
  { label: '创作项目推进', value: 'creative_project_advance' },
  { label: '小说写作室', value: 'novel_writer_room' },
  { label: '角色视觉卡', value: 'character_visual_card' },
  { label: '分镜参考匹配', value: 'storyboard_reference_match' },
  { label: '素材整理', value: 'asset_curation' },
  { label: '质量检查', value: 'quality_review' },
]

const LAST_AGENT_THREAD_STORAGE_KEY = 'ylcraft.agent.last_thread_id'
const LAST_AGENT_SESSION_STORAGE_KEY = 'ylcraft.agent.last_session_id'

const summarizeToolResult = (result: unknown) => {
  if (result === null || result === undefined) return '工具没有返回内容'
  if (typeof result === 'string') return result.length > 160 ? `${result.slice(0, 160)}...` : result
  if (Array.isArray(result)) return `返回 ${result.length} 条记录`
  if (typeof result === 'object') {
    const data = result as Record<string, unknown>
    const keys = Object.keys(data)
    const title = data.title || data.name || data.project_name || data.id
    if (title) return `返回对象：${String(title)}`
    return `返回字段：${keys.slice(0, 6).join('、')}${keys.length > 6 ? '...' : ''}`
  }
  return String(result)
}

const buildStepFailureAdvice = (step: AgentRunStep) => {
  const raw = [
    step.error,
    step.summary,
    typeof step.output === 'string' ? step.output : '',
    typeof step.raw_json === 'string' ? step.raw_json : '',
  ]
    .filter(Boolean)
    .join('\n')
    .toLowerCase()
  const advice: string[] = []

  if (raw.includes('unauthorized') || raw.includes('未授权') || raw.includes('not allowed')) {
    advice.push('到“智能体设定 - 工具授权”里勾选该工具，或临时选择允许全部工具的总控智能体。')
  }
  if (raw.includes('json') || raw.includes('parse') || raw.includes('invalid')) {
    advice.push('检查工具输入 JSON 是否完整，字符串里的换行、引号和数组对象结构最容易导致失败。')
  }
  if (raw.includes('missing') || raw.includes('required') || raw.includes('参数') || raw.includes('field')) {
    advice.push('打开工具抽屉查看输入规范，补齐必填字段后再重试当前步骤。')
  }
  if (raw.includes('confirm') || raw.includes('pending') || step.status === 'pending') {
    advice.push('这是需要人工确认的写入/删除/消耗型操作，确认后才会真正执行。')
  }
  if (raw.includes('timeout') || raw.includes('network') || raw.includes('http') || raw.includes('connection')) {
    advice.push('如果是外部服务或模型接口失败，先确认配置和网络，再重试该步骤。')
  }
  if (!advice.length) {
    advice.push('先展开“输入 / 输出”查看原始参数和返回；如果参数没问题，可以直接点“重试”。')
  }
  return advice
}

const getStepStatusColor = (status?: string) => {
  if (status === 'failed') return 'error'
  if (status === 'pending' || status === 'warning') return 'warning'
  if (status === 'dismissed') return 'default'
  if (status === 'completed') return 'success'
  return 'default'
}

type MarkdownSegment =
  | { type: 'text'; text: string }
  | { type: 'inline_code'; text: string }
  | { type: 'bold'; text: string }
  | { type: 'link'; text: string; href: string }

type MarkdownBlock =
  | { type: 'paragraph'; content: MarkdownSegment[] }
  | { type: 'heading'; level: number; content: MarkdownSegment[] }
  | { type: 'list'; ordered: boolean; items: MarkdownSegment[][] }
  | { type: 'quote'; content: MarkdownSegment[] }
  | { type: 'code'; language?: string; code: string }
  | { type: 'table'; header: MarkdownSegment[][]; rows: MarkdownSegment[][][] }

const parseInlineMarkdown = (text: string): MarkdownSegment[] => {
  const segments: MarkdownSegment[] = []
  const pattern = /(`([^`]+)`)|(\*\*([^*]+)\*\*)|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', text: text.slice(lastIndex, match.index) })
    }
    if (match[2] !== undefined) {
      segments.push({ type: 'inline_code', text: match[2] })
    } else if (match[4] !== undefined) {
      segments.push({ type: 'bold', text: match[4] })
    } else {
      segments.push({ type: 'link', text: match[5], href: match[6] })
    }
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', text: text.slice(lastIndex) })
  }
  return segments.length ? segments : [{ type: 'text', text }]
}

const parseSimpleMarkdown = (source: string): MarkdownBlock[] => {
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const blocks: MarkdownBlock[] = []
  let paragraph: string[] = []
  let listItems: MarkdownSegment[][] = []
  let listOrdered = false
  let codeLines: string[] = []
  let codeLanguage = ''
  let inCode = false
  let tableRows: string[] = []

  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push({ type: 'paragraph', content: parseInlineMarkdown(paragraph.join('\n')) })
    paragraph = []
  }

  const flushList = () => {
    if (!listItems.length) return
    blocks.push({ type: 'list', ordered: listOrdered, items: listItems })
    listItems = []
    listOrdered = false
  }

  const isTableRow = (row: string) => /^\s*\|.+\|\s*$/.test(row)
  const isTableDivider = (row: string) => /^\s*\|[\s:|-]+\|\s*$/.test(row)
  const flushTable = () => {
    if (!tableRows.length) return
    const dataRows = tableRows.filter(row => !isTableDivider(row))
    if (dataRows.length >= 1) {
      const parseRow = (row: string): MarkdownSegment[][] =>
        row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => parseInlineMarkdown(c.trim()))
      blocks.push({ type: 'table', header: parseRow(dataRows[0]), rows: dataRows.slice(1).map(parseRow) })
    } else {
      for (const row of tableRows) paragraph.push(row)
    }
    tableRows = []
  }

  for (const line of lines) {
    const fence = line.match(/^```([\w-]*)\s*$/)
    if (fence) {
      if (inCode) {
        blocks.push({ type: 'code', language: codeLanguage, code: codeLines.join('\n') })
        codeLines = []
        codeLanguage = ''
        inCode = false
      } else {
        flushParagraph()
        flushList()
        flushTable()
        inCode = true
        codeLanguage = fence[1] || ''
      }
      continue
    }

    if (inCode) {
      codeLines.push(line)
      continue
    }

    if (isTableRow(line)) {
      flushParagraph()
      flushList()
      tableRows.push(line)
      continue
    }

    flushTable()

    if (!line.trim()) {
      flushParagraph()
      flushList()
      continue
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'heading', level: heading[1].length, content: parseInlineMarkdown(heading[2]) })
      continue
    }

    const quote = line.match(/^>\s?(.+)$/)
    if (quote) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'quote', content: parseInlineMarkdown(quote[1]) })
      continue
    }

    const bullet = line.match(/^\s*[-*]\s+(.+)$/)
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (bullet || ordered) {
      flushParagraph()
      const nextOrdered = Boolean(ordered)
      if (listItems.length && listOrdered !== nextOrdered) flushList()
      listOrdered = nextOrdered
      listItems.push(parseInlineMarkdown((ordered?.[1] || bullet?.[1] || '').trim()))
      continue
    }

    flushList()
    paragraph.push(line)
  }

  if (inCode) {
    blocks.push({ type: 'code', language: codeLanguage, code: codeLines.join('\n') })
  }
  flushTable()
  flushParagraph()
  flushList()
  return blocks
}

interface SessionItem {
  id: string
  title: string
  created_at: string
  updated_at: string
}

interface ToolItem extends AgentToolCall {}

interface LlmConnector {
  id?: string
  name: string
  provider?: string
  provider_type?: string
  default_model?: string
  model?: string
  available_models?: string[] | string
  is_default?: boolean
  priority?: number
}

interface AgentLinkedLogs {
  linked_object_counts?: Record<string, number>
  project_ids?: string[]
  content_ids?: string[]
  task_ids?: string[]
  tool_calls?: any[]
  generation_logs?: any[]
  tasks?: any[]
}

type AgentResource = 'sessions' | 'profiles' | 'tools' | 'connectors'

function AgentPageContent() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [profileForm] = Form.useForm()
  const [memoryForm] = Form.useForm()

  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [tools, setTools] = useState<ToolItem[]>([])
  const [toolCalls, setToolCalls] = useState<AgentToolCallResult[]>([])
  const [currentRun, setCurrentRun] = useState<AgentRun | null>(null)
  // 当前运行中等待人工确认的步骤（工具写入/删除/消耗、记忆候选项），用于顶部显眼的确认卡片
  const pendingToolSteps = (currentRun?.steps || []).filter(s => s.status === 'pending' && s.step_type === 'tool_call')
  const pendingMemorySteps = (currentRun?.steps || []).filter(s => s.status === 'pending' && s.step_type === 'memory_extract')
  // 底部状态栏：步骤/工具/耗时统计（对标 Harness 底部一行）
  const toolSteps = (currentRun?.steps || []).filter(s => s.step_type === 'tool_call')
  const runDurationMs = (currentRun?.steps || []).reduce((sum, s) => sum + (s.duration_ms || 0), 0)
  const [runTree, setRunTree] = useState<{
    root_run_id: string
    runs: AgentRun[]
    delegations: AgentDelegation[]
    limits?: Record<string, number>
  } | null>(null)
  const [threadRuns, setThreadRuns] = useState<AgentRun[]>([])
  const [linkedLogs, setLinkedLogs] = useState<AgentLinkedLogs | null>(null)
  const [runSkillAnalysis, setRunSkillAnalysis] = useState<any>(null)
  const [runSkillLoading, setRunSkillLoading] = useState(false)
  const [memories, setMemories] = useState<AgentMemory[]>([])
  const [skills, setSkills] = useState<AgentSkill[]>([])
  const [memoryLoadError, setMemoryLoadError] = useState('')
  const [resourceErrors, setResourceErrors] = useState<Partial<Record<AgentResource, string>>>({})
  const [threadRestoreError, setThreadRestoreError] = useState('')
  const [sendError, setSendError] = useState('')
  const [failedPrompt, setFailedPrompt] = useState('')
  const [profiles, setProfiles] = useState<AgentProfile[]>([])
  const [llmConnectors, setLlmConnectors] = useState<LlmConnector[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>('')
  const [editingProvider, setEditingProvider] = useState<string>('')
  const [sessionsOpen, setSessionsOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [toolSearch, setToolSearch] = useState('')
  const [toolCategoryFilter, setToolCategoryFilter] = useState<string>('all')
  const [toolAuthFilter, setToolAuthFilter] = useState<string>('all')
  const [toolRiskFilter, setToolRiskFilter] = useState<string>('all')
  const [testingToolName, setTestingToolName] = useState('')
  const [toolTestArgs, setToolTestArgs] = useState<Record<string, string>>({})
  const [toolTestResults, setToolTestResults] = useState<Record<string, any>>({})
  const [delegateProfileId, setDelegateProfileId] = useState<string>('')
  const [delegateMessage, setDelegateMessage] = useState('')
  const [stepStatusFilter, setStepStatusFilter] = useState('all')
  const [stepTypeFilter, setStepTypeFilter] = useState('all')
  const [profileOpen, setProfileOpen] = useState(false)
  const [savingMemory, setSavingMemory] = useState(false)
  const [activeTab, setActiveTab] = useState('chat')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const shouldAutoRestoreSessionRef = useRef(true)
  const currentSessionIdRef = useRef<string | null>(null)
  const forceNewSessionRef = useRef(false)

  const setResourceError = useCallback((resource: AgentResource, error?: unknown) => {
    setResourceErrors(current => {
      const next = { ...current }
      if (!error) {
        delete next[resource]
      } else {
        next[resource] = error instanceof Error ? error.message : String(error)
      }
      return next
    })
  }, [])

  const selectedProfile = useMemo(
    () => profiles.find(item => item.id === selectedProfileId) || profiles[0],
    [profiles, selectedProfileId],
  )

  const allowedToolSet = useMemo(() => new Set(selectedProfile?.allowed_tools || []), [selectedProfile])
  const allowAllTools = allowedToolSet.has('*')
  const authorizedTools = useMemo(
    () => (selectedProfile ? tools.filter(tool => allowAllTools || allowedToolSet.has(tool.name)) : []),
    [allowAllTools, allowedToolSet, selectedProfile, tools],
  )

  const toolOptions = useMemo(
    () =>
      tools.map(tool => ({
        label: `${tool.name} (${CATEGORY_LABELS[tool.category] || tool.category})`,
        value: tool.name,
      })),
    [tools],
  )

  const filteredTools = useMemo(() => {
    const search = toolSearch.trim().toLowerCase()
    return tools.filter(tool => {
      const authorized = Boolean(selectedProfile && (allowAllTools || allowedToolSet.has(tool.name)))
      const risk = tool.risk_level || 'read'
      if (toolCategoryFilter !== 'all' && tool.category !== toolCategoryFilter) return false
      if (toolAuthFilter === 'authorized' && !authorized) return false
      if (toolAuthFilter === 'blocked' && authorized) return false
      if (toolRiskFilter !== 'all' && risk !== toolRiskFilter) return false
      if (!search) return true
      return [
        tool.name,
        tool.description,
        tool.input_schema_note,
        tool.output_schema_note,
        tool.output_type,
        CATEGORY_LABELS[tool.category] || tool.category,
      ]
        .filter(Boolean)
        .some(value => String(value).toLowerCase().includes(search))
    })
  }, [allowAllTools, allowedToolSet, selectedProfile, toolAuthFilter, toolCategoryFilter, toolRiskFilter, toolSearch, tools])

  const visibleCategories = useMemo(
    () => GROUPED_CATEGORIES.filter(category => filteredTools.some(tool => tool.category === category)),
    [filteredTools],
  )

  const llmProviderOptions = useMemo(
    () =>
      llmConnectors.map(connector => ({
        label: `${connector.name}${connector.default_model || connector.model ? ` · ${connector.default_model || connector.model}` : ''}`,
        value: connector.name,
      })),
    [llmConnectors],
  )

  const delegateProfileOptions = useMemo(
    () =>
      profiles
        .filter(profile => profile.id !== currentRun?.profile_id)
        .map(profile => ({
          label: `${profile.avatar || 'Agent'} ${profile.name} · ${ROLE_TYPE_LABELS[profile.role_type || 'assistant'] || profile.role_type || '通用助手'}`,
          value: profile.id,
        })),
    [currentRun?.profile_id, profiles],
  )

  const llmModelOptions = useMemo(() => {
    const active = llmConnectors.find(item => item.name === editingProvider)
    const availableModels = normalizeModelList(active?.available_models)
    const models = availableModels.length
      ? availableModels
      : active?.default_model
        ? [active.default_model]
        : active?.model
          ? [active.model]
          : []
    return Array.from(new Set(models.map(item => String(item || '').trim()).filter(Boolean))).map(model => ({
      label: model,
      value: model,
    }))
  }, [editingProvider, llmConnectors])

  const skillOptions = useMemo(
    () =>
      skills.map(skill => ({
        label: `${skill.name}${skill.description ? ` · ${skill.description}` : ''}`,
        value: skill.name,
      })),
    [skills],
  )

  const visibleMessages = useMemo(
    () => messages.filter(message => message.role !== 'tool' && message.metadata?.phase !== 'tool_observation'),
    [messages],
  )

  const runStats = useMemo(() => {
    const userCount = visibleMessages.filter(message => message.role === 'user').length
    const assistantCount = visibleMessages.filter(message => message.role === 'assistant').length
    const maxSteps = selectedProfile?.max_steps || 0
    const stepCount = currentRun?.steps?.length || 0
    return {
      userCount,
      assistantCount,
      toolCount: toolCalls.length,
      stepCount,
      maxSteps,
      progress: maxSteps ? Math.min(100, Math.round((stepCount / maxSteps) * 100)) : 0,
    }
  }, [currentRun?.steps?.length, selectedProfile?.max_steps, toolCalls.length, visibleMessages])

  const currentRunRoutedSkills = useMemo(
    () => extractRunRoutedSkills(currentRun),
    [currentRun],
  )

  const runTraceByMessageIndex = useMemo(() => {
    const map = new Map<number, AgentRun>()
    const byId = new Map<string, AgentRun>()
    threadRuns.forEach(run => {
      if (run?.id) byId.set(run.id, run)
    })
    if (currentRun?.id) byId.set(currentRun.id, currentRun)
    byId.forEach(run => {
      const index = visibleMessages.findIndex(message => message.role === 'assistant' && message.run_id === run.id)
      if (index >= 0) map.set(index, run)
    })
    return map
  }, [currentRun, threadRuns, visibleMessages])

  const shouldRenderFloatingTrace = useMemo(() => {
    if (!loading && !toolCalls.length && !currentRun?.steps?.length) return false
    if (!currentRun?.id) return true
    return !Array.from(runTraceByMessageIndex.values()).some(run => run.id === currentRun.id)
  }, [currentRun?.id, currentRun?.steps?.length, loading, runTraceByMessageIndex, toolCalls.length])

  const activeSession = useMemo(
    () => sessions.find(item => item.id === currentSessionId) || null,
    [currentSessionId, sessions],
  )

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId
  }, [currentSessionId])

  const sessionStatus = useMemo(() => {
    if (loading) return '执行中'
    if (currentSessionId && visibleMessages.length > 0) return '已恢复上下文'
    if (currentSessionId) return '线程已绑定'
    return '新线程'
  }, [currentSessionId, loading, visibleMessages.length])

  const filteredRunSteps = useMemo(() => {
    const steps = currentRun?.steps || []
    return steps.filter(step => {
      if (stepStatusFilter !== 'all' && step.status !== stepStatusFilter) return false
      if (stepTypeFilter !== 'all' && step.step_type !== stepTypeFilter) return false
      return true
    })
  }, [currentRun?.steps, stepStatusFilter, stepTypeFilter])

  const runStepTypeOptions = useMemo(() => {
    const stepTypes = Array.from(new Set((currentRun?.steps || []).map(step => step.step_type).filter(Boolean)))
    return [
      { label: '全部步骤', value: 'all' },
      ...stepTypes.map(type => ({ label: STEP_TYPE_LABELS[type] || type, value: type })),
    ]
  }, [currentRun?.steps])

  const runStepStatusOptions = useMemo(() => {
    const statuses = Array.from(new Set((currentRun?.steps || []).map(step => step.status).filter(Boolean)))
    return [
      { label: '全部状态', value: 'all' },
      ...statuses.map(status => ({ label: status, value: status })),
    ]
  }, [currentRun?.steps])

  const pageShell: CSSProperties = {
    height: 'calc(100dvh - 88px)',
    minHeight: 620,
    display: 'grid',
    gridTemplateRows: '52px minmax(0, 1fr)',
    gap: 0,
    color: THEME.textPrimary,
    fontFamily: '"Geist", "SF Pro Display", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
    background: THEME.bgCard,
    border: `1px solid ${THEME.borderLight}`,
    borderRadius: 8,
    overflow: 'hidden',
  }

  const panelStyle: CSSProperties = {
    background: `linear-gradient(180deg, ${THEME.bgCard}, ${THEME.bgPage})`,
    border: `1px solid ${THEME.primaryAlpha?.(0.14) || THEME.borderLight}`,
    borderRadius: 10,
    boxShadow: `0 18px 42px ${THEME.primaryAlpha?.(0.075) || 'rgba(16, 80, 76, 0.075)'}`,
  }

  const controlButtonStyle: CSSProperties = {
    borderRadius: 6,
    fontWeight: 500,
    fontSize: 13,
    height: 34,
  }

  const consoleHeaderStyle: CSSProperties = {
    padding: '8px 12px',
    background: THEME.bgCard,
    borderBottom: `1px solid ${THEME.borderLight}`,
  }

  const headerGridStyle: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'minmax(220px, 1fr) minmax(360px, auto)',
    alignItems: 'center',
    gap: 12,
  }

  const commandBarStyle: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'minmax(190px, 260px) repeat(4, auto)',
    gap: 6,
    justifyContent: 'end',
    alignItems: 'center',
  }

  const workspaceGridStyle: CSSProperties = {
    minHeight: 0,
    display: 'grid',
    gridTemplateColumns: '252px minmax(0, 1fr)',
    gap: 0,
  }

  const leftRailStyle: CSSProperties = {
    minHeight: 0,
    overflow: 'hidden',
    display: 'grid',
    gridTemplateRows: 'auto minmax(0, 1fr) auto',
    background: THEME.bgPage,
    borderRight: `1px solid ${THEME.borderLight}`,
  }

  const railSectionStyle: CSSProperties = {
    padding: 12,
    borderBottom: `1px solid ${THEME.borderLight}`,
  }

  const inspectorSectionStyle: CSSProperties = {
    padding: '14px 0',
    borderBottom: `1px solid ${THEME.borderLight}`,
  }

  const compactMetaStyle: CSSProperties = {
    color: THEME.textSecondary,
    fontSize: 12,
    lineHeight: 1.55,
  }

  const loadSessions = useCallback(async () => {
    try {
      const data = await listAgentThreads()
      setSessions(Array.isArray(data) ? data : [])
      setResourceError('sessions')
    } catch (e) {
      console.error('Failed to load agent sessions', e)
      try {
        const data = await listAgentSessions()
        setSessions(Array.isArray(data) ? data : [])
        setResourceError('sessions')
      } catch (fallbackError) {
        console.error('Failed to load legacy agent sessions', fallbackError)
        setResourceError('sessions', fallbackError)
      }
    }
  }, [setResourceError])

  const loadTools = useCallback(async () => {
    try {
      const data = await listAgentTools()
      setTools(Array.isArray(data) ? data : [])
      setResourceError('tools')
    } catch (e) {
      console.error('Failed to load agent tools', e)
      setResourceError('tools', e)
    }
  }, [setResourceError])

  const loadProfiles = useCallback(async () => {
    try {
      const data = await listAgentProfiles()
      const profileList = Array.isArray(data) ? data : []
      setProfiles(profileList)
      setResourceError('profiles')
      setSelectedProfileId(prev => {
        if (prev && profileList.some((item: AgentProfile) => item.id === prev)) return prev
        return profileList.find((item: AgentProfile) => item.is_default)?.id || profileList[0]?.id || ''
      })
    } catch (e) {
      console.error('Failed to load agent profiles', e)
      setProfiles([])
      setSelectedProfileId('')
      setResourceError('profiles', e)
    }
  }, [setResourceError])

  const loadLlmConnectors = useCallback(async () => {
    try {
      const response = await listConnectors({ provider_type: 'llm', active_only: true })
      const connectors = (response?.connectors || response?.data || []) as LlmConnector[]
      const sorted = [...connectors].sort((a, b) => {
        if (a.is_default !== b.is_default) return a.is_default ? -1 : 1
        return (a.priority || 0) - (b.priority || 0)
      })
      setLlmConnectors(sorted)
      setResourceError('connectors')
    } catch (error) {
      console.error('Failed to load LLM connectors', error)
      setLlmConnectors([])
      setResourceError('connectors', error)
    }
  }, [setResourceError])

  const loadMemories = useCallback(async () => {
    try {
      setMemoryLoadError('')
      const [data, skillData] = await Promise.all([getAgentMemories(), listAgentSkills()])
      setMemories(Array.isArray(data?.memories) ? data.memories : [])
      setSkills(Array.isArray(skillData) ? skillData : (Array.isArray(data?.skills) ? data.skills : []))
    } catch (error) {
      console.error('Failed to load agent memories', error)
      setMemoryLoadError(error instanceof Error ? error.message : '记忆 / 技能加载失败')
      setMemories([])
      setSkills([])
    }
  }, [])

  const loadRunLinkedLogs = useCallback(async (runId: string) => {
    try {
      setLinkedLogs(await getAgentRunLinkedLogs(runId))
    } catch (error) {
      console.error('Failed to load agent linked logs', error)
      setLinkedLogs(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!currentRun?.id) {
      setRunTree(null)
      return () => {
        cancelled = true
      }
    }
    getAgentRunTree(currentRun.id)
      .then(data => {
        if (!cancelled) setRunTree(data)
      })
      .catch(error => {
        console.error('Failed to load agent run tree', error)
        if (!cancelled) setRunTree(null)
      })
    return () => {
      cancelled = true
    }
  }, [currentRun?.id, currentRun?.status, currentRun?.steps?.length])

  const syncThreadMessages = useCallback(async (threadId: string) => {
    if (!threadId) return false
    try {
      let data: any
      try {
        data = await getAgentThread(threadId)
      } catch {
        data = await getAgentSession(threadId)
      }
      setMessages(Array.isArray(data?.messages) ? data.messages : [])
      setThreadRestoreError('')
      return true
    } catch (error) {
      console.error('Failed to sync agent thread messages', error)
      setThreadRestoreError(error instanceof Error ? error.message : '无法恢复这段对话')
      return false
    }
  }, [])

  const loadThreadRuns = useCallback(async (threadId: string, limit = 12) => {
    if (!threadId) {
      setThreadRuns([])
      return []
    }
    try {
      const runs = await listAgentRuns({ thread_id: threadId, limit })
      if (!Array.isArray(runs) || runs.length === 0) {
        setThreadRuns([])
        return []
      }
      const detailedRuns = await Promise.all(
        runs
          .filter(run => run?.id)
          .map(run => getAgentRun(run.id).catch(() => null)),
      )
      const nextRuns = detailedRuns.filter(Boolean) as AgentRun[]
      setThreadRuns(nextRuns)
      return nextRuns
    } catch (error) {
      console.error('Failed to load agent thread runs', error)
      setThreadRuns([])
      return []
    }
  }, [])

  const restoreSession = useCallback(async (sessionId: string, options?: { openChat?: boolean; closeDrawer?: boolean }) => {
    if (!sessionId) return false
    try {
      setCurrentSessionId(sessionId)
      currentSessionIdRef.current = sessionId
      forceNewSessionRef.current = false
      if (options?.closeDrawer) setSessionsOpen(false)
      const restored = await syncThreadMessages(sessionId)
      if (!restored) throw new Error('无法恢复这段对话，请重试。')
      setReplyText('')
      setToolCalls([])
      setCurrentRun(null)
      setRunSkillAnalysis(null)
      setLinkedLogs(null)
      if (options?.openChat !== false) setActiveTab('chat')

      const runs = await loadThreadRuns(sessionId)
      if (runs[0]?.id) {
        setCurrentRun(runs[0])
        setRunSkillAnalysis(null)
        await loadRunLinkedLogs(runs[0].id)
      }
      localStorage.setItem(LAST_AGENT_THREAD_STORAGE_KEY, sessionId)
      localStorage.setItem(LAST_AGENT_SESSION_STORAGE_KEY, sessionId)
      return true
    } catch (error) {
      console.error('Failed to restore agent session', error)
      if (localStorage.getItem(LAST_AGENT_THREAD_STORAGE_KEY) === sessionId) {
        localStorage.removeItem(LAST_AGENT_THREAD_STORAGE_KEY)
      }
      if (localStorage.getItem(LAST_AGENT_SESSION_STORAGE_KEY) === sessionId) {
        localStorage.removeItem(LAST_AGENT_SESSION_STORAGE_KEY)
      }
      setCurrentSessionId(prev => (prev === sessionId ? null : prev))
      if (currentSessionIdRef.current === sessionId) currentSessionIdRef.current = null
      return false
    }
  }, [loadRunLinkedLogs, loadThreadRuns, syncThreadMessages])

  const reloadAll = useCallback(async () => {
    await Promise.all([loadSessions(), loadTools(), loadProfiles(), loadLlmConnectors(), loadMemories()])
  }, [loadLlmConnectors, loadMemories, loadProfiles, loadSessions, loadTools])

  useEffect(() => {
    reloadAll()
  }, [reloadAll])

  useEffect(() => {
    if (currentSessionId || loading || sessions.length === 0) return
    if (!shouldAutoRestoreSessionRef.current) return
    let cancelled = false
    const restoreLastSession = async () => {
      const storedSessionId = localStorage.getItem(LAST_AGENT_THREAD_STORAGE_KEY) || localStorage.getItem(LAST_AGENT_SESSION_STORAGE_KEY)
      if (!storedSessionId) {
        shouldAutoRestoreSessionRef.current = false
        return
      }
      const candidate = sessions.some(item => item.id === storedSessionId) ? storedSessionId : ''
      if (!candidate) {
        localStorage.removeItem(LAST_AGENT_THREAD_STORAGE_KEY)
        localStorage.removeItem(LAST_AGENT_SESSION_STORAGE_KEY)
        shouldAutoRestoreSessionRef.current = false
        return
      }
      if (cancelled) return
      shouldAutoRestoreSessionRef.current = false
      await restoreSession(candidate, { openChat: true })
    }
    restoreLastSession()
    return () => {
      cancelled = true
    }
  }, [currentSessionId, loading, restoreSession, sessions])

  useEffect(() => {
    if (visibleMessages.length === 0 && !replyText) return
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [replyText, visibleMessages.length])

  useEffect(() => {
    if (!profileOpen || !selectedProfile) return
    profileForm.setFieldsValue({
      name: selectedProfile.name,
      avatar: selectedProfile.avatar,
      role_type: selectedProfile.role_type || 'assistant',
      description: selectedProfile.description,
      system_prompt: selectedProfile.system_prompt,
      provider: selectedProfile.provider,
      model: selectedProfile.model,
      max_steps: selectedProfile.max_steps,
      can_delegate: selectedProfile.can_delegate,
      allowed_tools: selectedProfile.allowed_tools?.includes('*') ? ['*'] : selectedProfile.allowed_tools,
      default_context: JSON.stringify(selectedProfile.default_context || {}, null, 2),
      default_project_id: selectedProfile.default_project_id || '',
      default_workflow: selectedProfile.default_workflow || '',
      default_skill_ids: selectedProfile.default_skill_ids || [],
      is_default: selectedProfile.is_default,
    })
    setEditingProvider(selectedProfile.provider || '')
  }, [profileForm, profileOpen, selectedProfile])

  useEffect(() => {
    if (!profileOpen) return
    memoryForm.setFieldsValue({
      memory_type: 'preference',
      importance: 5,
    })
  }, [memoryForm, profileOpen])

  const isToolAuthorized = (toolName: string) => Boolean(selectedProfile && (allowAllTools || allowedToolSet.has(toolName)))

  const permissionTag = (toolName: string) => {
    if (!selectedProfile) return <Tag>未选择智能体</Tag>
    if (isToolAuthorized(toolName)) return <Tag color="success">已授权</Tag>
    return <Tag color="warning">未授权</Tag>
  }

  const bubbleStyle = (role: AgentMessage['role']): CSSProperties => ({
    background: role === 'user'
      ? THEME.primary
      : 'transparent',
    color: role === 'user' ? '#fff' : THEME.textPrimary,
    border: role === 'user' ? `1px solid ${THEME.primary}` : 'none',
    borderRadius: role === 'user' ? '8px 8px 3px 8px' : 0,
    padding: role === 'user' ? '10px 13px' : '4px 0',
    maxWidth: role === 'user' ? 'min(620px, 72%)' : 'min(880px, 86%)',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    lineHeight: 1.72,
    boxShadow: 'none',
    fontFamily: '"Geist", "SF Pro Text", "PingFang SC", system-ui, sans-serif',
  })

  const inlineCodeStyle = (role: AgentMessage['role']): CSSProperties => ({
    padding: '1px 5px',
    borderRadius: 5,
    background: role === 'user' ? 'rgba(255,255,255,0.18)' : THEME.bgElevated,
    border: role === 'user' ? '1px solid rgba(255,255,255,0.2)' : `1px solid ${THEME.borderLight}`,
    color: role === 'user' ? '#fff' : THEME.textPrimary,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    fontSize: '0.92em',
  })

  const renderInlineMarkdown = (segments: MarkdownSegment[], role: AgentMessage['role']) =>
    segments.map((segment, index) => {
      if (segment.type === 'inline_code') {
        return <code key={`${segment.type}-${index}`} style={inlineCodeStyle(role)}>{segment.text}</code>
      }
      if (segment.type === 'bold') {
        return <strong key={`${segment.type}-${index}`} style={{ fontWeight: 750 }}>{segment.text}</strong>
      }
      if (segment.type === 'link') {
        return (
          <a
            key={`${segment.type}-${index}`}
            href={segment.href}
            target="_blank"
            rel="noreferrer"
            style={{
              color: role === 'user' ? '#fff' : THEME.primary,
              textDecoration: 'underline',
              textUnderlineOffset: 3,
            }}
          >
            {segment.text}
          </a>
        )
      }
      return <span key={`${segment.type}-${index}`}>{segment.text}</span>
    })

  const renderMarkdown = (content: string, role: AgentMessage['role']) => {
    const blocks = parseSimpleMarkdown(content)
    if (!blocks.length) return null
    const textColor = role === 'user' ? '#fff' : THEME.textPrimary
    const secondaryColor = role === 'user' ? 'rgba(255,255,255,0.82)' : THEME.textSecondary
    return (
      <div style={{ display: 'grid', gap: 8 }}>
        {blocks.map((block, index) => {
          if (block.type === 'heading') {
            const fontSize = block.level === 1 ? 20 : block.level === 2 ? 17 : 15
            return (
              <div key={`${block.type}-${index}`} style={{ color: textColor, fontSize, fontWeight: 750, lineHeight: 1.35 }}>
                {renderInlineMarkdown(block.content, role)}
              </div>
            )
          }
          if (block.type === 'list') {
            const ListTag = block.ordered ? 'ol' : 'ul'
            return (
              <ListTag
                key={`${block.type}-${index}`}
                style={{
                  margin: 0,
                  paddingLeft: 20,
                  color: textColor,
                  display: 'grid',
                  gap: 4,
                }}
              >
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInlineMarkdown(item, role)}</li>
                ))}
              </ListTag>
            )
          }
          if (block.type === 'quote') {
            return (
              <blockquote
                key={`${block.type}-${index}`}
                style={{
                  margin: 0,
                  padding: '6px 10px',
                  borderLeft: `3px solid ${role === 'user' ? 'rgba(255,255,255,0.5)' : THEME.primary}`,
                  background: role === 'user' ? 'rgba(255,255,255,0.1)' : THEME.bgElevated,
                  color: secondaryColor,
                  borderRadius: 6,
                }}
              >
                {renderInlineMarkdown(block.content, role)}
              </blockquote>
            )
          }
          if (block.type === 'code') {
            return (
              <pre
                key={`${block.type}-${index}`}
                style={{
                  margin: 0,
                  padding: 10,
                  borderRadius: 7,
                  background: role === 'user' ? 'rgba(0,0,0,0.22)' : THEME.bgElevated,
                  border: role === 'user' ? '1px solid rgba(255,255,255,0.16)' : `1px solid ${THEME.borderLight}`,
                  color: textColor,
                  overflow: 'auto',
                  fontSize: 12,
                  lineHeight: 1.65,
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                }}
              >
                {block.language && <div style={{ color: secondaryColor, marginBottom: 6 }}>{block.language}</div>}
                <code>{block.code}</code>
              </pre>
            )
          }
          if (block.type === 'table') {
            return (
              <div key={`${block.type}-${index}`} style={{ overflowX: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13, color: textColor }}>
                  <thead>
                    <tr>
                      {block.header.map((cell, i) => (
                        <th key={i} style={{ border: `1px solid ${THEME.borderLight}`, padding: '6px 10px', background: role === 'user' ? 'rgba(255,255,255,0.12)' : THEME.bgElevated, textAlign: 'left', fontWeight: 750 }}>{renderInlineMarkdown(cell, role)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((cell, c) => (
                          <td key={c} style={{ border: `1px solid ${THEME.borderLight}`, padding: '6px 10px', color: textColor }}>{renderInlineMarkdown(cell, role)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
          return (
            <div key={`${block.type}-${index}`} style={{ color: textColor, whiteSpace: 'pre-wrap' }}>
              {renderInlineMarkdown(block.content, role)}
            </div>
          )
        })}
      </div>
    )
  }

  const sendMessage = useCallback(async (overrideText?: string) => {
    const isRetry = typeof overrideText === 'string'
    const text = (typeof overrideText === 'string' ? overrideText : input).trim()
    if (!text || loading) return
    const pendingToolStep = currentRun?.steps?.find(step => step.status === 'pending' && step.step_type === 'tool_call')
    const isConfirmIntent = /^(确认|确认执行|同意|授权|执行|可以|继续|好的|好|是|ok|OK|yes|Yes)[。.!！\s]*$/.test(text)

    setInput('')
    setLoading(true)
    setReplyText('')
    setSendError('')
    setFailedPrompt('')
    setToolCalls([])
    setLinkedLogs(null)
    setActiveTab('chat')

    const userMsg: AgentMessage = { role: 'user', content: text }
    if (!isRetry) setMessages(prev => [...prev, userMsg])

    if (pendingToolStep && isConfirmIntent && currentRun) {
      try {
        const result = await confirmAgentRunStep(currentRun.id, pendingToolStep.id)
        const assistantText = result?.message || `已确认执行工具 ${pendingToolStep.tool_name || ''}。`
        setMessages(prev => [...prev, { role: 'assistant', content: assistantText }])
        const run = await getAgentRun(currentRun.id)
        setCurrentRun(run)
        setRunSkillAnalysis(null)
        setThreadRuns(prev => [run, ...prev.filter(item => item.id !== run.id)].slice(0, 12))
        await loadRunLinkedLogs(currentRun.id)
        await loadSessions()
        if (result?.success === false) {
          message.error(result?.error || '工具执行失败')
          return
        }
        message.success('已确认执行待处理工具')
      } catch (error: any) {
        message.error(`确认失败：${error.message}`)
        setMessages(prev => prev.slice(0, -1))
      } finally {
        setLoading(false)
      }
      return
    }

    setCurrentRun(null)
    setRunSkillAnalysis(null)
    let streamedReply = ''

    try {
      const requestSessionId = currentSessionIdRef.current
      const params = new URLSearchParams()
      if (requestSessionId) params.set('thread_id', requestSessionId)
      const forceNewSession = forceNewSessionRef.current && !requestSessionId

      const response = await fetch(`/api/v1/agent/chat?${params}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          thread_id: requestSessionId || undefined,
          session_id: requestSessionId || undefined,
          context: {},
          force_new_thread: forceNewSession,
          stream: true,
          profile_id: selectedProfileId || undefined,
        }),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      if (!response.body) throw new Error('SSE stream not available')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let sessionId = requestSessionId
      let runId = ''
      const handleSseLine = (line: string) => {
        if (!line.startsWith('data: ')) return
        const event = JSON.parse(line.slice(6))
        if (event.event === 'token') {
          streamedReply += event.data || ''
          setReplyText(streamedReply)
        }
        if (event.event === 'tool_calls') {
          setToolCalls(event.data || [])
        }
        if (event.event === 'done') {
          sessionId = event.data?.thread_id || event.data?.session_id || sessionId
          runId = event.data?.run_id || runId
          if (sessionId) {
            forceNewSessionRef.current = false
            currentSessionIdRef.current = sessionId
            setCurrentSessionId(sessionId)
            localStorage.setItem(LAST_AGENT_THREAD_STORAGE_KEY, sessionId)
            localStorage.setItem(LAST_AGENT_SESSION_STORAGE_KEY, sessionId)
          }
        }
        if (event.event === 'error') {
          throw new Error(event.data || 'Agent 调用失败')
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (buffer.trim()) {
            for (const line of buffer.split('\n')) {
              handleSseLine(line.trimEnd())
            }
          }
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.event === 'token') {
              streamedReply += event.data || ''
              setReplyText(streamedReply)
            }
            if (event.event === 'tool_calls') {
              setToolCalls(event.data || [])
            }
            if (event.event === 'done') {
              sessionId = event.data?.thread_id || event.data?.session_id || sessionId
              runId = event.data?.run_id || runId
              if (sessionId) {
                forceNewSessionRef.current = false
                currentSessionIdRef.current = sessionId
                setCurrentSessionId(sessionId)
                localStorage.setItem(LAST_AGENT_THREAD_STORAGE_KEY, sessionId)
                localStorage.setItem(LAST_AGENT_SESSION_STORAGE_KEY, sessionId)
              }
            }
            if (event.event === 'error') {
              throw new Error(event.data || 'Agent 调用失败')
            }
          } catch (e) {
            if (e instanceof Error) throw e
          }
        }
      }

      if (streamedReply) {
        setMessages(prev => [...prev, { role: 'assistant', content: streamedReply }])
        setReplyText('')
      }
      if (sessionId) {
        forceNewSessionRef.current = false
        setCurrentSessionId(sessionId)
        currentSessionIdRef.current = sessionId
        localStorage.setItem(LAST_AGENT_THREAD_STORAGE_KEY, sessionId)
        localStorage.setItem(LAST_AGENT_SESSION_STORAGE_KEY, sessionId)
        await syncThreadMessages(sessionId)
      }
      if (runId) {
        try {
          const run = await getAgentRun(runId)
          setCurrentRun(run)
          setRunSkillAnalysis(null)
          setThreadRuns(prev => [run, ...prev.filter(item => item.id !== run.id)].slice(0, 12))
          await loadRunLinkedLogs(runId)
        } catch (error) {
          console.error('Failed to load agent run', error)
        }
      }
      await loadSessions()
    } catch (e: any) {
      message.error(`发送失败：${e.message}`)
      setSendError(e.message || '发送失败')
      setFailedPrompt(text)
      if (streamedReply) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `${streamedReply}\n\n> 响应在完成前中断，可在当前对话重试。`,
        }])
        setReplyText('')
      }
    } finally {
      setLoading(false)
    }
  }, [currentRun, currentSessionId, input, loadRunLinkedLogs, loadSessions, loading, selectedProfileId, syncThreadMessages])

  const switchSession = async (sessionId: string) => {
    await restoreSession(sessionId, { openChat: true, closeDrawer: true })
  }

  const newSession = () => {
    shouldAutoRestoreSessionRef.current = false
    setCurrentSessionId(null)
    currentSessionIdRef.current = null
    forceNewSessionRef.current = true
    localStorage.removeItem(LAST_AGENT_THREAD_STORAGE_KEY)
    localStorage.removeItem(LAST_AGENT_SESSION_STORAGE_KEY)
    setMessages([])
    setReplyText('')
    setToolCalls([])
    setCurrentRun(null)
    setThreadRuns([])
    setLinkedLogs(null)
    setActiveTab('chat')
    setSessionsOpen(false)
  }

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteAgentThread(sessionId)
    } catch {
      await deleteAgentSession(sessionId)
    }
    if (localStorage.getItem(LAST_AGENT_THREAD_STORAGE_KEY) === sessionId) {
      localStorage.removeItem(LAST_AGENT_THREAD_STORAGE_KEY)
    }
    if (localStorage.getItem(LAST_AGENT_SESSION_STORAGE_KEY) === sessionId) {
      localStorage.removeItem(LAST_AGENT_SESSION_STORAGE_KEY)
    }
    if (currentSessionId === sessionId) newSession()
    await loadSessions()
    message.success('线程已删除')
  }

  const handleSaveProfile = async () => {
    if (!selectedProfile) return
    const values = await profileForm.validateFields()
    let defaultContext = {}
    try {
      defaultContext = values.default_context ? JSON.parse(values.default_context) : {}
    } catch {
      message.error('默认上下文必须是合法 JSON')
      return
    }
    const allowedTools = values.allowed_tools?.includes('*') ? ['*'] : values.allowed_tools || []
    await updateAgentProfile(selectedProfile.id, {
      ...values,
        allowed_tools: allowedTools,
        default_context: defaultContext,
        default_project_id: values.default_project_id || '',
        default_workflow: values.default_workflow || '',
        default_skill_ids: values.default_skill_ids || [],
      })
    message.success('智能体设定已保存')
    await loadProfiles()
  }

  const handleCreateProfile = async () => {
    try {
      const base = selectedProfile
      const defaultConnector =
        llmConnectors.find(item => item.is_default) ||
        llmConnectors[0]
      const created = await createAgentProfile({
        name: base ? `${base.name} 副本` : '新智能体',
        avatar: base?.avatar || '',
        role_type: base?.role_type || 'assistant',
        description: base?.description || '',
        system_prompt: base?.system_prompt || '',
        allowed_tools: base?.allowed_tools || ['*'],
        default_context: base?.default_context || {},
        default_project_id: base?.default_project_id || '',
        default_workflow: base?.default_workflow || '',
        default_skill_ids: base?.default_skill_ids || [],
        provider: base?.provider || defaultConnector?.name || '',
        model: base?.model || defaultConnector?.default_model || defaultConnector?.model || normalizeModelList(defaultConnector?.available_models)[0] || '',
        max_steps: base?.max_steps || 8,
        can_delegate: base?.can_delegate || false,
        is_default: !base,
      })
      if (created?.id) {
        message.success(base ? '已创建智能体副本' : '已创建新智能体')
        await loadProfiles()
        setSelectedProfileId(created.id)
        setProfileOpen(true)
        return
      }
      message.error(created?.detail || '创建智能体失败')
    } catch (e: any) {
      message.error(`创建智能体失败：${e.message}`)
    }
  }

  const handleSaveMemory = async () => {
    const values = await memoryForm.validateFields()
    setSavingMemory(true)
    try {
      await saveAgentMemory({
        key: values.key,
        value: values.value,
        memory_type: values.memory_type,
        importance: values.importance,
      })
      memoryForm.resetFields(['key', 'value'])
      memoryForm.setFieldsValue({ memory_type: values.memory_type || 'preference', importance: values.importance || 5 })
      await loadMemories()
      message.success('长期记忆已保存')
    } catch (error: any) {
      message.error(`保存记忆失败：${error.message}`)
    } finally {
      setSavingMemory(false)
    }
  }

  const handleDeleteMemory = async (key: string) => {
    try {
      await deleteAgentMemory(key)
      await loadMemories()
      message.success('记忆已删除')
    } catch (error: any) {
      message.error(`删除记忆失败：${error.message}`)
    }
  }

  const refreshRun = async (runId?: string) => {
    const id = runId || currentRun?.id
    if (!id) return
    const run = await getAgentRun(id)
    setCurrentRun(run)
    setRunSkillAnalysis(null)
    setThreadRuns(prev => [run, ...prev.filter(item => item.id !== run.id)].slice(0, 12))
    await loadRunLinkedLogs(id)
  }

  const handleContinueRun = async () => {
    if (!currentRun || loading) return
    setLoading(true)
    try {
      const result = await continueAgentRun(currentRun.id)
      if (result?.reply) {
        setMessages(prev => [...prev, { role: 'assistant', content: result.reply }])
      }
      const resultThreadId = result?.thread_id || result?.session_id
      if (resultThreadId) {
        setCurrentSessionId(resultThreadId)
        currentSessionIdRef.current = resultThreadId
        localStorage.setItem(LAST_AGENT_THREAD_STORAGE_KEY, resultThreadId)
        localStorage.setItem(LAST_AGENT_SESSION_STORAGE_KEY, resultThreadId)
      }
      if (result?.run_id) {
        await refreshRun(result.run_id)
      }
      await loadSessions()
      message.success('已继续执行')
    } catch (e: any) {
      message.error(`继续执行失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDelegateRun = async () => {
    if (!currentRun || !delegateProfileId || loading) return
    setLoading(true)
    try {
      const result = await delegateAgentRun(currentRun.id, {
        profile_id: delegateProfileId,
        message: delegateMessage || `请接手处理这个父任务：${currentRun.objective}`,
        context: currentRun.context || {},
        resume_parent: true,
      })
      if (!result?.success) {
        message.warning(result?.error || '委派任务未成功完成')
      } else {
        const resumedReply = result?.parent_resume?.reply
        if (resumedReply) {
          setMessages(prev => [...prev, { role: 'assistant', content: resumedReply }])
        }
        message.success(resumedReply ? '子智能体已完成，父智能体已继续汇总' : '子智能体已完成委派任务')
      }
      setDelegateMessage('')
      await refreshRun(currentRun.id)
    } catch (error: any) {
      message.error(`委派失败：${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleRetryRunStep = async (stepId?: number) => {
    if (!currentRun || loading) return
    setLoading(true)
    try {
      await retryAgentRunStep(currentRun.id, stepId)
      await refreshRun(currentRun.id)
      message.success('已重试失败步骤')
    } catch (e: any) {
      message.error(`重试失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleStopRun = useCallback(async () => {
    if (!currentRun || !loading) return
    try {
      await cancelAgentRun(currentRun.id)
      message.info('已请求停止本轮生成')
      setLoading(false)
    } catch (error: any) {
      message.error(error?.message || '停止失败')
    }
  }, [currentRun, loading])

  const handleConfirmRunStep = async (stepId: number) => {
    if (!currentRun || loading) return
    setLoading(true)
    try {
      await confirmAgentRunStep(currentRun.id, stepId)
      await refreshRun(currentRun.id)
      message.success('已确认并执行工具')
    } catch (error: any) {
      message.error(`确认执行失败：${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveMemoryCandidates = async (stepId: number, indices?: number[]) => {
    if (!currentRun || loading) return
    setLoading(true)
    try {
      const result = await saveAgentMemoryCandidates(currentRun.id, stepId, indices)
      await refreshRun(currentRun.id)
      await loadMemories()
      message.success(`已保存 ${result?.saved?.length || 0} 条记忆`)
    } catch (error: any) {
      message.error(`保存记忆失败：${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDiscardMemoryCandidates = async (stepId: number) => {
    if (!currentRun || loading) return
    setLoading(true)
    try {
      await discardAgentMemoryCandidates(currentRun.id, stepId)
      await refreshRun(currentRun.id)
      message.success('已丢弃待确认记忆')
    } catch (error: any) {
      message.error(`丢弃记忆失败：${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleExportRunMarkdown = async (mode: 'copy' | 'download') => {
    if (!currentRun) return
    try {
      const markdown = await exportAgentRunMarkdown(currentRun.id)
      if (mode === 'copy') {
        await navigator.clipboard.writeText(markdown)
        message.success('Run Markdown 已复制')
        return
      }
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `agent-run-${currentRun.id}.md`
      link.click()
      URL.revokeObjectURL(url)
      message.success('Run Markdown 已下载')
    } catch (error: any) {
      message.error(`导出失败：${error.message}`)
    }
  }

  const handleInspectRunSkillCandidate = async () => {
    if (!currentRun) return
    setRunSkillLoading(true)
    try {
      const result = await inspectAgentRunSkillCandidate(currentRun.id)
      const analysis = result?.analysis || null
      setRunSkillAnalysis(analysis)
      if (analysis?.eligible) {
        message.success('当前 Run 适合沉淀为 Skill 草稿')
      } else {
        message.warning(`暂不适合沉淀：${(analysis?.reasons || []).join('；') || '证据不足'}`)
      }
    } catch (error: any) {
      message.error(`分析失败：${error.message}`)
    } finally {
      setRunSkillLoading(false)
    }
  }

  const handleCreateSkillDraftFromRun = async () => {
    if (!currentRun) return
    setRunSkillLoading(true)
    try {
      const result = await createAgentSkillDraftFromRun(currentRun.id)
      if (result?.success) {
        setRunSkillAnalysis(null)
        message.success({
          content: (
            <Space>
              <span>已生成待审批 Skill 草稿：{result.draft?.name || ''}</span>
              <Button size="small" type="link" onClick={() => navigate('/settings?tab=agent-skills')}>
                去审批
              </Button>
            </Space>
          ),
          duration: 6,
        })
      } else {
        message.error(result?.error || '生成 Skill 草稿失败')
      }
    } catch (error: any) {
      message.error(`生成 Skill 草稿失败：${error.message}`)
    } finally {
      setRunSkillLoading(false)
    }
  }

  const handleTestTool = async (tool: ToolItem, confirmed = false) => {
    setTestingToolName(tool.name)
    try {
      let args: Record<string, any> = {}
      const raw = toolTestArgs[tool.name]?.trim()
      if (raw) {
        try {
          args = JSON.parse(raw)
        } catch {
          message.error('测试参数必须是合法 JSON')
          return
        }
      }
      const result = await testAgentTool({
        tool_name: tool.name,
        arguments: args,
        profile_id: selectedProfile?.id,
        confirmed,
      })
      setToolTestResults(prev => ({ ...prev, [tool.name]: result }))
      if (result?.pending_confirmation) {
        message.warning('该工具需要确认后才会真正执行')
      } else if (result?.success) {
        message.success('工具测试执行成功')
      } else {
        message.error(result?.error || '工具测试失败')
      }
    } catch (error: any) {
      message.error(`工具测试失败：${error.message}`)
    } finally {
      setTestingToolName('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const renderProductionPlanResult = (toolName: string, value: unknown) => {
    if (
      !['run_creative_production_plan', 'analyze_creative_production_plan_impact'].includes(toolName)
      || !value
      || typeof value !== 'object'
    ) return null

    const payload = value as Record<string, any>
    const plan = payload.production_plan as Record<string, any> | undefined
    const nodes = Array.isArray(payload.selected_nodes)
      ? payload.selected_nodes
      : Array.isArray(payload.affected_nodes)
        ? payload.affected_nodes
        : []
    if (!plan && nodes.length === 0) return null

    const renderIds = (label: string, ids: unknown, color?: string) => {
      const values = Array.isArray(ids) ? ids.filter(Boolean).map(String) : []
      if (!values.length) return null
      return (
        <Space wrap size={[4, 4]}>
          <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
          {values.map(id => <Tag key={`${label}-${id}`} color={color}>{id}</Tag>)}
        </Space>
      )
    }

    return (
      <div
        style={{
          display: 'grid',
          gap: 10,
          padding: 12,
          border: `1px solid ${THEME.primaryAlpha?.(0.28) || THEME.borderLight}`,
          borderRadius: 8,
          background: THEME.bgElevated,
        }}
      >
        <Space wrap size={[6, 6]}>
          <Text strong>{toolName === 'analyze_creative_production_plan_impact' ? '局部重跑影响分析' : '生产计划执行'}</Text>
          {plan?.title && <Tag color="blue">{plan.title}</Tag>}
          {plan?.version && <Tag>版本 {plan.version}</Tag>}
          {plan?.status && <Tag color="processing">{plan.status}</Tag>}
        </Space>
        {plan?.goal && <Text type="secondary" style={{ fontSize: 12 }}>{plan.goal}</Text>}
        {payload.rerun_hint && <Alert type="info" showIcon message="局部重跑" description={String(payload.rerun_hint)} />}
        {nodes.map((node: Record<string, any>) => (
          <div
            key={node.id || node.node_id}
            style={{ borderTop: `1px solid ${THEME.borderLight}`, paddingTop: 10, display: 'grid', gap: 7 }}
          >
            <Space wrap size={[5, 5]}>
              <Text strong>{node.label || node.id || node.node_id}</Text>
              {node.stage && <Tag color="cyan">{node.stage}</Tag>}
              {node.specialist_role && <Tag>{node.specialist_role}</Tag>}
              {node.status && <Tag color="processing">{node.status}</Tag>}
              {node.reason && <Tag color={node.reason === 'changed' ? 'gold' : 'orange'}>{node.reason === 'changed' ? '直接变更' : `受 ${node.reason.replace('depends_on:', '')} 影响`}</Tag>}
              {node.requires_confirmation && <Tag color="gold">生成前需确认</Tag>}
            </Space>
            {renderIds('输入内容', node.input_content_ids)}
            {renderIds('参考素材', node.input_asset_ids, 'purple')}
            {(node.provider || node.model) && (
              <Text type="secondary" style={{ fontSize: 12 }}>模型：{node.provider || '-'} {node.model || ''}</Text>
            )}
            {node.planning_summary && Object.keys(node.planning_summary).length > 0 && (
              <div style={{ padding: '8px 10px', borderRadius: 6, background: THEME.bgPage }}>
                <Text type="secondary" style={{ fontSize: 12 }}>可审计规划摘要</Text>
                <pre style={{ margin: '5px 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: THEME.textPrimary, fontSize: 12 }}>
                  {JSON.stringify(node.planning_summary, null, 2)}
                </pre>
              </div>
            )}
            {renderIds('输出内容', node.output_content_ids, 'green')}
            {renderIds('输出素材', node.output_asset_ids, 'green')}
          </div>
        ))}
      </div>
    )
  }

  const renderToolResult = (item: AgentToolCallResult, index: number) => (
    <div
      key={`${item.name || item.tool_name}-${index}`}
      style={{
        border: `1px solid ${item.success ? THEME.primaryAlpha?.(0.22) || THEME.borderLight : '#ff7875'}`,
        borderRadius: 10,
        padding: 12,
        background: item.success ? THEME.bgCard : 'rgba(255, 77, 79, 0.06)',
      }}
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
          <Space wrap>
            <Tag color={item.success ? 'processing' : 'error'} icon={<ToolOutlined />}>
              {item.name || item.tool_name}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              第 {index + 1} 步 / {item.duration_ms || 0}ms
            </Text>
          </Space>
          <Tag color={item.success ? 'success' : 'error'}>{item.success ? '完成' : '失败'}</Tag>
        </Space>
        <Text style={{ color: item.success ? THEME.textPrimary : '#ff4d4f' }}>
          {item.error || summarizeToolResult(item.result)}
        </Text>
        {renderProductionPlanResult(item.tool_name || item.name, item.result)}
        {item.result !== undefined && (
          <details>
            <summary style={{ cursor: 'pointer', color: THEME.textSecondary, fontSize: 12 }}>
              查看原始 JSON
            </summary>
            <pre
              style={{
                margin: '8px 0 0',
                padding: 10,
                borderRadius: 8,
                background: THEME.bgPage,
                color: THEME.textPrimary,
                border: `1px solid ${THEME.borderLight}`,
                maxHeight: 220,
                overflow: 'auto',
                fontSize: 12,
              }}
            >
              {JSON.stringify(item.result, null, 2)}
            </pre>
          </details>
        )}
      </Space>
    </div>
  )

  const renderLinkedLogs = () => {
    if (!linkedLogs) return null
    const toolLogCount = linkedLogs.tool_calls?.length || 0
    const generationLogCount = linkedLogs.generation_logs?.length || 0
    const taskCount = linkedLogs.tasks?.length || 0
    if (!toolLogCount && !generationLogCount && !taskCount) {
      return (
        <Alert
          type="info"
          showIcon
          message="暂无关联日志"
          description="当前 run 还没有匹配到工具调用日志、项目生成日志或后台任务。"
        />
      )
    }
    return (
      <div
        style={{
          border: `1px solid ${THEME.borderLight}`,
          borderRadius: 10,
          padding: 12,
          background: THEME.bgCard,
        }}
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
            <Space wrap>
              <Text strong>关联日志</Text>
              <Tag>工具 {toolLogCount}</Tag>
              <Tag>生成 {generationLogCount}</Tag>
              <Tag>任务 {taskCount}</Tag>
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              从当前 run 的上下文和 linked_objects 反查
            </Text>
          </Space>
          {toolLogCount > 0 && (
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>工具调用日志</Text>
              {linkedLogs.tool_calls?.slice(0, 4).map(item => (
                <Space key={item.id} wrap style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Space wrap>
                    <Tag color={item.success ? 'success' : 'error'}>{item.success ? '成功' : '失败'}</Tag>
                    <Text code>{item.tool_name}</Text>
                    <Text type="secondary">{item.duration_ms || 0}ms</Text>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.created_at || '-'}</Text>
                </Space>
              ))}
            </Space>
          )}
          {generationLogCount > 0 && (
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>项目生成日志</Text>
              {linkedLogs.generation_logs?.slice(0, 4).map(item => (
                <Space key={item.id} wrap style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Space wrap>
                    <Tag color={item.status === 'success' ? 'success' : 'warning'}>{item.status || '-'}</Tag>
                    <Text code>{item.stage || item.scene || 'generation'}</Text>
                    <Text>{item.provider || '-'}</Text>
                    <Text type="secondary">{item.model || '-'}</Text>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.created_at || '-'}</Text>
                </Space>
              ))}
            </Space>
          )}
          {taskCount > 0 && (
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>后台任务</Text>
              {linkedLogs.tasks?.slice(0, 4).map(item => (
                <Space key={item.task_id} wrap style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Space wrap>
                    <Tag color={item.status === 'done' ? 'success' : item.status === 'failed' ? 'error' : 'processing'}>
                      {item.status || '-'}
                    </Tag>
                    <Text code>{item.task_id}</Text>
                    <Text>{item.task_type || '-'}</Text>
                    <Text type="secondary">{item.progress || 0}% {item.progress_message || ''}</Text>
                  </Space>
                  <Tag>{item.events?.length || 0} events</Tag>
                </Space>
              ))}
            </Space>
          )}
        </Space>
      </div>
    )
  }

  const renderRunStep = (step: AgentRunStep) => {
    const memoryCandidates = Array.isArray(step.output?.candidates) ? step.output.candidates : []
    const routedSkills = Array.isArray(step.output?.routed_skills) ? step.output.routed_skills : []
    return (
      <div
        key={step.id}
        style={{
          border: `1px solid ${step.status === 'failed' ? '#ff7875' : step.status === 'pending' ? '#faad14' : THEME.borderLight}`,
          borderRadius: 10,
          padding: 12,
          background: step.status === 'failed' ? 'rgba(255, 77, 79, 0.06)' : step.status === 'pending' ? 'rgba(250, 173, 20, 0.08)' : THEME.bgCard,
        }}
      >
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
          <Space wrap>
            <Tag color={step.step_type === 'tool_call' && step.status === 'completed' ? 'processing' : getStepStatusColor(step.status)}>
              {STEP_TYPE_LABELS[step.step_type] || step.step_type}
            </Tag>
            {step.tool_name && <Tag icon={<ToolOutlined />}>{step.tool_name}</Tag>}
            <Text type="secondary" style={{ fontSize: 12 }}>
              #{step.order_index + 1} / {step.duration_ms || 0}ms
            </Text>
          </Space>
          <Space>
            {step.status === 'pending' && step.step_type === 'tool_call' && (
              <Button size="small" type="primary" onClick={() => handleConfirmRunStep(step.id)} loading={loading}>
                确认执行
              </Button>
            )}
            {step.status === 'pending' && step.step_type === 'memory_extract' && (
              <>
                <Button size="small" type="primary" onClick={() => handleSaveMemoryCandidates(step.id)} loading={loading}>
                  保存记忆
                </Button>
                <Button size="small" onClick={() => handleDiscardMemoryCandidates(step.id)} loading={loading}>
                  丢弃
                </Button>
              </>
            )}
            {step.status === 'failed' && step.step_type === 'tool_call' && (
              <Button size="small" onClick={() => handleRetryRunStep(step.id)} loading={loading}>
                重试
              </Button>
            )}
            <Tag color={getStepStatusColor(step.status)}>{step.status}</Tag>
          </Space>
        </Space>
        <Text style={{ color: step.status === 'failed' ? '#ff4d4f' : THEME.textPrimary }}>
          {step.error || step.summary || '步骤已记录'}
        </Text>
        {renderProductionPlanResult(step.tool_name, step.output)}
        {step.step_type === 'skill_route' && routedSkills.length > 0 && (
          <div style={{ display: 'grid', gap: 8 }}>
            {routedSkills.map((item: any) => (
              <div
                key={`${item.skill_id}-${item.source}-${item.reason}`}
                style={{
                  border: `1px solid ${THEME.borderLight}`,
                  borderRadius: 8,
                  padding: '8px 10px',
                  background: THEME.bgElevated,
                }}
              >
                <Space direction="vertical" size={5} style={{ width: '100%' }}>
                  <Space wrap size={[5, 5]}>
                    <Tag color={item.source === 'slash' ? 'purple' : item.source === 'profile' ? 'blue' : 'default'}>
                      {item.skill_id}
                    </Tag>
                    <Tag>分数 {item.score ?? 0}</Tag>
                    <Tag>{item.source || 'route'}</Tag>
                    {item.trigger_type && <Tag>{item.trigger_type}</Tag>}
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {item.reason || '命中路由规则'}
                    {Array.isArray(item.matches) && item.matches.length > 0 ? ` · ${item.matches.join(' / ')}` : ''}
                  </Text>
                </Space>
              </div>
            ))}
          </div>
        )}
        {step.status === 'failed' && (
          <Alert
            type="error"
            showIcon
            message="失败定位"
            description={
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {buildStepFailureAdvice(step).map((item) => (
                  <Text key={item} style={{ color: THEME.textPrimary, fontSize: 12 }}>
                    {item}
                  </Text>
                ))}
              </Space>
            }
          />
        )}
        {step.status === 'pending' && (
          <Alert
            type="warning"
            showIcon
            message={step.step_type === 'memory_extract' ? '发现可保存的长期记忆' : '等待确认'}
            description={
              step.step_type === 'memory_extract'
                ? '这些内容只是候选项，保存后才会进入智能体长期记忆；丢弃则不会影响本次回答。'
                : '这个步骤涉及写入、删除或模型消耗。确认前不会真正执行；确认后结果会回写到同一个 run。'
            }
          />
        )}
        {memoryCandidates.length > 0 && (
          <div style={{ display: 'grid', gap: 8 }}>
            {memoryCandidates.map((item: any, index: number) => (
              <div
                key={`${item.key || 'memory'}-${index}`}
                style={{
                  border: `1px solid ${THEME.borderLight}`,
                  borderRadius: 8,
                  padding: 10,
                  background: THEME.bgPage,
                }}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color="gold">#{index + 1}</Tag>
                    <Tag color="blue">{item.memory_type || item.type || 'fact'}</Tag>
                    <Tag>重要度 {item.importance || 5}</Tag>
                    <Text code style={{ whiteSpace: 'normal' }}>{item.key || '未命名记忆'}</Text>
                  </Space>
                  <Text style={{ color: THEME.textPrimary }}>{item.value || '无内容'}</Text>
                  {item.reason && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      原因：{item.reason}
                    </Text>
                  )}
                  {step.status === 'pending' && step.step_type === 'memory_extract' && (
                    <Space>
                      <Button
                        size="small"
                        onClick={() => handleSaveMemoryCandidates(step.id, [index])}
                        loading={loading}
                      >
                        只保存这条
                      </Button>
                    </Space>
                  )}
                </Space>
              </div>
            ))}
          </div>
        )}
        {Array.isArray(step.linked_objects) && step.linked_objects.length > 0 && (
          <Space wrap size={[4, 4]}>
            {step.linked_objects.slice(0, 8).map((item, index) => (
              <Tag key={`${item.type || 'object'}-${item.id || index}`} color="blue">
                {item.type || 'object'}: {item.title || item.id}
              </Tag>
            ))}
            {step.linked_objects.length > 8 && <Tag>+{step.linked_objects.length - 8}</Tag>}
          </Space>
        )}
        <details>
          <summary style={{ cursor: 'pointer', color: THEME.textSecondary, fontSize: 12 }}>
            查看输入 / 输出
          </summary>
          <pre
            style={{
              margin: '8px 0 0',
              padding: 10,
              borderRadius: 8,
              background: THEME.bgPage,
              color: THEME.textPrimary,
              border: `1px solid ${THEME.borderLight}`,
              maxHeight: 260,
              overflow: 'auto',
              fontSize: 12,
            }}
          >
            {JSON.stringify({ input: step.input, output: step.output }, null, 2)}
          </pre>
        </details>
        {step.raw_json !== undefined && (
          <details>
            <summary style={{ cursor: 'pointer', color: THEME.textSecondary, fontSize: 12 }}>
              查看原始错误 / raw_json
            </summary>
            <pre
              style={{
                margin: '8px 0 0',
                padding: 10,
                borderRadius: 8,
                background: THEME.bgPage,
                color: THEME.textPrimary,
                border: `1px solid ${THEME.borderLight}`,
                maxHeight: 220,
                overflow: 'auto',
                fontSize: 12,
              }}
            >
              {JSON.stringify(step.raw_json, null, 2)}
            </pre>
          </details>
        )}
      </Space>
    </div>
    )
  }

  const renderRunSkillSummary = (run?: AgentRun | null, options: { compact?: boolean } = {}) => {
    const routedSkills = extractRunRoutedSkills(run)
    const compact = Boolean(options.compact)
    if (!run) return null
    if (!routedSkills.length) {
      return (
        <div
          style={{
            border: `1px dashed ${THEME.borderLight}`,
            borderRadius: 8,
            padding: compact ? '7px 9px' : '10px 12px',
            background: THEME.bgPage,
          }}
        >
          <Space wrap size={[6, 6]}>
            <Text type="secondary" style={{ fontSize: 12 }}>本轮未命中 Skill</Text>
            <Button size="small" type="link" onClick={() => navigate('/settings?tab=agent-skills')}>
              打开匹配测试
            </Button>
          </Space>
        </div>
      )
    }
    return (
      <div
        style={{
          border: `1px solid ${THEME.borderLight}`,
          borderRadius: 8,
          padding: compact ? '7px 9px' : '10px 12px',
          background: THEME.bgElevated,
        }}
      >
        <Space direction="vertical" size={compact ? 5 : 8} style={{ width: '100%' }}>
          <Space wrap size={[6, 6]}>
            <Text strong style={{ fontSize: compact ? 12 : 13 }}>本轮 Skill</Text>
            <Tag color="blue">{routedSkills.length} 个</Tag>
            {routedSkills.slice(0, compact ? 4 : 8).map(skill => (
              <Tooltip
                key={skill.skill_id}
                title={`${skill.reason || '命中路由'}${skill.matches?.length ? ` · ${skill.matches.join(' / ')}` : ''}`}
              >
                <Tag
                  color={skill.source === 'slash' ? 'purple' : skill.source === 'profile' ? 'blue' : 'default'}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/settings?tab=agent-skills&skill=${encodeURIComponent(skill.skill_id)}`)}
                >
                  {skill.skill_id}
                  {typeof skill.score === 'number' ? ` · ${skill.score}` : ''}
                </Tag>
              </Tooltip>
            ))}
            {routedSkills.length > (compact ? 4 : 8) && <Tag>+{routedSkills.length - (compact ? 4 : 8)}</Tag>}
          </Space>
          {!compact && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              点击 Skill 可跳到管理页查看 SKILL.md；分数越高越优先注入完整指令。
            </Text>
          )}
        </Space>
      </div>
    )
  }

  const renderInlineRunTrace = (run?: AgentRun | null) => {
    const targetRun = run || null
    const isCurrentTrace = !targetRun || targetRun.id === currentRun?.id
    const steps = targetRun?.steps || []
    const hasTrace = steps.length > 0 || toolCalls.length > 0 || loading
    if (!hasTrace) return null
    const isRunning = (isCurrentTrace && loading) || targetRun?.status === 'running'
    const visibleSteps = steps.length ? steps : []
    const succeededCount = visibleSteps.filter(s => s.status === 'completed').length
    const failedCount = visibleSteps.filter(s => s.status === 'failed').length
    const pendingCount = visibleSteps.filter(s => s.status === 'pending').length
    const toolCount = visibleSteps.filter(s => s.step_type === 'tool_call').length
    return (
      <div
        className="agent-inline-trace"
        style={{
          width: 'min(820px, calc(100% - 48px))',
          margin: '0 0 14px 36px',
          border: `1px solid ${THEME.borderLight}`,
          borderRadius: 10,
          background: `linear-gradient(180deg, ${THEME.bgCard}, ${THEME.bgElevated})`,
          boxShadow: `0 10px 24px ${THEME.primaryAlpha?.(0.045) || 'rgba(22,119,255,0.045)'}`,
          overflow: 'hidden',
        }}
      >
        <details open={isRunning}>
          <summary
            style={{
              cursor: 'pointer',
              padding: '11px 13px',
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) auto',
              gap: 10,
              alignItems: 'center',
              color: THEME.textPrimary,
              borderBottom: `1px solid ${THEME.borderLight}`,
            }}
          >
            <Space wrap size={[6, 6]}>
              <RobotOutlined style={{ color: THEME.primary }} />
              <Text strong>本轮执行过程</Text>
              <Tag color={isRunning ? 'processing' : targetRun?.status === 'failed' ? 'error' : 'success'}>
                {isRunning ? '执行中' : targetRun?.status || '已记录'}
              </Tag>
              <Tag>{visibleSteps.length || toolCalls.length} 步</Tag>
              {toolCount > 0 && <Tag color="blue">{toolCount} 工具</Tag>}
              {succeededCount > 0 && <Tag color="success">{succeededCount} 成功</Tag>}
              {failedCount > 0 && <Tag color="error">{failedCount} 失败</Tag>}
              {pendingCount > 0 && <Tag color="warning">{pendingCount} 待确认</Tag>}
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {isRunning ? '展开查看实时步骤' : '点击展开步骤、输入输出与错误细节'}
            </Text>
          </summary>
          {targetRun && (
            <div style={{ padding: '10px 12px 0' }}>
              {renderRunSkillSummary(targetRun, { compact: true })}
            </div>
          )}
          <div style={{ padding: 12, display: 'grid', gap: 9 }}>
            {visibleSteps.length > 0 ? (
              visibleSteps.map(step => (
                <div
                  key={step.id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '26px minmax(0, 1fr)',
                    gap: 9,
                    alignItems: 'start',
                  }}
                >
                  <span
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: 7,
                      display: 'grid',
                      placeItems: 'center',
                      background: step.status === 'failed'
                        ? 'rgba(255,77,79,0.12)'
                        : step.status === 'pending'
                          ? 'rgba(250,173,20,0.14)'
                          : THEME.primaryAlpha?.(0.12),
                      color: step.status === 'failed' ? '#ff4d4f' : (step.status === 'pending' || step.status === 'warning') ? '#faad14' : THEME.primary,
                      fontSize: 11,
                      fontWeight: 800,
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {step.order_index + 1}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <Space wrap size={[5, 5]}>
                      <Text strong style={{ fontSize: 13 }}>
                        {STEP_TYPE_LABELS[step.step_type] || step.step_type}
                      </Text>
                      {step.tool_name && <Tag icon={<ToolOutlined />}>{step.tool_name}</Tag>}
                      <Tag color={getStepStatusColor(step.status)}>
                        {step.status}
                      </Tag>
                      {step.duration_ms != null && step.duration_ms > 0 && (
                        <Text type="secondary" style={{ fontSize: 11 }}>{step.duration_ms}ms</Text>
                      )}
                    </Space>
                    {step.status === 'pending' && step.step_type === 'tool_call' && (
                      <Space size={6} style={{ marginTop: 8 }}>
                        <Button size="small" type="primary" onClick={() => handleConfirmRunStep(step.id)} loading={loading}>
                          确认执行
                        </Button>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          仅写入、删除或消耗型工具需要确认
                        </Text>
                      </Space>
                    )}
                    {step.status === 'failed' && step.step_type === 'tool_call' && (
                      <Button size="small" style={{ marginTop: 8 }} onClick={() => handleRetryRunStep(step.id)} loading={loading}>
                        重试
                      </Button>
                    )}
                    {step.step_type === 'skill_route' && Array.isArray(step.output?.routed_skills) && step.output.routed_skills.length > 0 && (
                      <Space wrap size={[4, 4]} style={{ marginTop: 7 }}>
                        {step.output.routed_skills.slice(0, 4).map((item: any) => (
                          <Tag key={`${item.skill_id}-${item.source}`} color={item.source === 'slash' ? 'purple' : 'default'}>
                            {item.skill_id}
                          </Tag>
                        ))}
                        {step.output.routed_skills.length > 4 && <Tag>+{step.output.routed_skills.length - 4}</Tag>}
                      </Space>
                    )}
                    <details style={{ marginTop: 4 }}>
                      <summary style={{ cursor: 'pointer', fontSize: 12, color: THEME.textSecondary }}>
                        {step.error ? `错误：${step.error.slice(0, 80)}...` : step.summary?.slice(0, 80) || '查看详情'}
                      </summary>
                      <div style={{ marginTop: 6, fontSize: 12, color: THEME.textSecondary, lineHeight: 1.55 }}>
                        {(step.input && Object.keys(step.input).length > 0) && (
                          <div style={{ marginBottom: 6 }}>
                            <Text type="secondary">输入：</Text>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11, background: THEME.bgElevated, padding: '6px 8px', borderRadius: 6, maxHeight: 120, overflow: 'auto' }}>
                              {typeof step.input === 'string' ? step.input : JSON.stringify(step.input, null, 2)}
                            </pre>
                          </div>
                        )}
                        {step.error && (
                          <div style={{ marginBottom: 6 }}>
                            <Text type="danger">错误：</Text>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11, background: 'rgba(255,77,79,0.06)', padding: '6px 8px', borderRadius: 6, maxHeight: 120, overflow: 'auto' }}>
                              {step.error}
                            </pre>
                          </div>
                        )}
                        {(step.output != null && (typeof step.output === 'string' ? step.output : Object.keys(step.output || {}).length > 0)) && (
                          <div>
                            <Text type="secondary">输出：</Text>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11, background: THEME.bgElevated, padding: '6px 8px', borderRadius: 6, maxHeight: 160, overflow: 'auto' }}>
                              {typeof step.output === 'string' ? step.output : JSON.stringify(step.output, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </details>
                  </div>
                </div>
              ))
            ) : (
              toolCalls.map((call, index) => (
                <div key={`${call.name || call.tool_name}-${index}`} style={{ display: 'grid', gridTemplateColumns: '26px minmax(0, 1fr)', gap: 9 }}>
                  <span
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: 7,
                      display: 'grid',
                      placeItems: 'center',
                      background: call.success ? THEME.primaryAlpha?.(0.12) : 'rgba(255,77,79,0.12)',
                      color: call.success ? THEME.primary : '#ff4d4f',
                      fontSize: 11,
                      fontWeight: 800,
                    }}
                  >
                    {index + 1}
                  </span>
                  <div>
                    <Text strong style={{ fontSize: 13 }}>{call.name || call.tool_name}</Text>
                    <div style={compactMetaStyle}>{call.success ? summarizeToolResult(call.result) : call.error || '工具调用失败'}</div>
                  </div>
                </div>
              ))
            )}
            {isRunning && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: THEME.textSecondary, fontSize: 12 }}>
                <Spin size="small" />
                正在继续推理或等待工具返回
              </div>
            )}
          </div>
        </details>
      </div>
    )
  }

  const renderContextSummary = (context: Record<string, any> | undefined) => {
    const conversationState = context?.conversation_state
    if (conversationState?.active_intent || conversationState?.pending_action || Object.keys(conversationState?.slots || {}).length) {
      const slots = conversationState.slots || {}
      const pendingAction = conversationState.pending_action || {}
      return (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <div style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: '10px 12px', background: THEME.bgPage }}>
            <Text type="secondary" style={{ fontSize: 12 }}>线程状态</Text>
            <div style={{ color: THEME.textPrimary, fontWeight: 700, marginTop: 2 }}>
              {conversationState.intent_label || conversationState.active_intent || '上下文跟踪中'}
            </div>
            <Space wrap size={[6, 6]} style={{ marginTop: 8 }}>
              {slots.keyword && <Tag color="blue">关键词：{slots.keyword}</Tag>}
              {slots.platform_label && <Tag color="cyan">平台：{slots.platform_label}</Tag>}
              {(conversationState.missing_slots || []).map((slot: string) => (
                <Tag key={slot} color="warning">缺少：{slot}</Tag>
              ))}
              {pendingAction.type && <Tag color={pendingAction.type === 'tool_confirmation' ? 'orange' : 'processing'}>{pendingAction.type}</Tag>}
            </Space>
          </div>
          {pendingAction.tool_calls?.length > 0 && (
            <div style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: '8px 10px', background: THEME.bgCard }}>
              <Text type="secondary" style={{ fontSize: 12 }}>待确认动作</Text>
              <div style={{ marginTop: 6, display: 'grid', gap: 6 }}>
                {pendingAction.tool_calls.slice(0, 3).map((call: any, index: number) => (
                  <div key={`${call.name || call.tool_name || 'tool'}-${index}`} style={{ fontSize: 12, color: THEME.textPrimary }}>
                    <Tag>{call.name || call.tool_name || 'tool'}</Tag>
                    {call.arguments?.platform && <Tag>{call.arguments.platform}</Tag>}
                    {call.arguments?.keyword && <Text type="secondary">{call.arguments.keyword}</Text>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {conversationState.last_tool_result && (
            <div style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: '8px 10px', background: THEME.bgCard }}>
              <Text type="secondary" style={{ fontSize: 12 }}>最近工具结果</Text>
              <div style={{ color: THEME.textPrimary, fontSize: 13, marginTop: 4 }}>
                {conversationState.last_tool_result.tool_name} · {conversationState.last_tool_result.success ? '成功' : '失败'}
              </div>
              {conversationState.last_tool_result.summary && (
                <Text type="secondary" style={{ fontSize: 12 }}>{conversationState.last_tool_result.summary}</Text>
              )}
            </div>
          )}
          <details>
            <summary style={{ cursor: 'pointer', color: THEME.primary, fontSize: 12 }}>查看完整上下文 JSON</summary>
            <pre style={{ marginTop: 8, padding: 10, borderRadius: 8, background: THEME.bgPage, border: `1px solid ${THEME.borderLight}`, color: THEME.textPrimary, fontSize: 12, whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>
              {JSON.stringify(context, null, 2)}
            </pre>
          </details>
        </Space>
      )
    }
    const creativePack = context?.creative_project_context
    if (creativePack?.project) {
      return (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <div
            style={{
              border: `1px solid ${THEME.borderLight}`,
              borderRadius: 8,
              padding: '10px 12px',
              background: THEME.bgPage,
            }}
          >
            <Text type="secondary" style={{ fontSize: 12 }}>创作项目</Text>
            <div style={{ color: THEME.textPrimary, fontWeight: 600 }}>{creativePack.project.title}</div>
            <Space wrap size={[6, 6]} style={{ marginTop: 6 }}>
              <Tag>{creativePack.project.current_stage || '未标记阶段'}</Tag>
              <Tag>{creativePack.project.chapter_count || 0} 章</Tag>
              {(creativePack.known_gaps || []).slice(0, 3).map((gap: string) => (
                <Tag key={gap} color="warning">{gap}</Tag>
              ))}
            </Space>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: 10, background: THEME.bgCard }}>
              <Text type="secondary" style={{ fontSize: 12 }}>章节状态</Text>
              <div style={{ fontWeight: 700 }}>{creativePack.chapter_status?.length || 0}</div>
            </div>
            <div style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: 10, background: THEME.bgCard }}>
              <Text type="secondary" style={{ fontSize: 12 }}>角色摘要</Text>
              <div style={{ fontWeight: 700 }}>{creativePack.characters?.length || 0}</div>
            </div>
          </div>
          {!!creativePack.characters?.length && (
            <Space wrap size={[6, 6]}>
              {creativePack.characters.slice(0, 6).map((item: any) => (
                <Tag key={item.character_id || item.name}>{item.name}</Tag>
              ))}
            </Space>
          )}
        </Space>
      )
    }
    const entries = Object.entries(context || {}).filter(([, value]) => value !== undefined && value !== null && value !== '')
    if (!entries.length) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行上下文" />
    }
    return (
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        {entries.slice(0, 8).map(([key, value]) => (
          <div
            key={key}
            style={{
              border: `1px solid ${THEME.borderLight}`,
              borderRadius: 8,
              padding: '8px 10px',
              background: THEME.bgPage,
            }}
          >
            <Text type="secondary" style={{ fontSize: 12 }}>{key}</Text>
            <div style={{ color: THEME.textPrimary, fontSize: 13, wordBreak: 'break-word' }}>
              {typeof value === 'object' ? JSON.stringify(value).slice(0, 120) : String(value)}
            </div>
          </div>
        ))}
        {entries.length > 8 && <Text type="secondary">还有 {entries.length - 8} 个上下文字段</Text>}
      </Space>
    )
  }

  const renderEmptyState = () => (
    <div
      className="agent-empty-state"
      style={{
        minHeight: 320,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 760, textAlign: 'center' }}>
        <div
          style={{
            width: 64,
            height: 64,
            margin: '0 auto 18px',
            borderRadius: 18,
            display: 'grid',
            placeItems: 'center',
            background: THEME.primaryAlpha?.(0.12) || 'rgba(22,119,255,0.12)',
            color: THEME.primary,
            fontSize: 30,
          }}
        >
          <RobotOutlined />
        </div>
        <Title level={4} style={{ marginBottom: 6, color: THEME.textPrimary }}>
          让智能体先接管一个明确任务
        </Title>
        <Paragraph style={{ color: THEME.textSecondary, marginBottom: 18 }}>
          它会根据当前设定选择可用工具，执行过程会按顺序折叠在对话流里，完整轨迹可随时展开查看。
        </Paragraph>
        <Space wrap size={[8, 8]} style={{ justifyContent: 'center' }}>
          {QUICK_PROMPTS.map(prompt => (
            <Button key={prompt} size="small" onClick={() => setInput(prompt)}>
              {prompt}
            </Button>
          ))}
        </Space>
      </div>
    </div>
  )

  return (
    <div className="agent-workbench" style={pageShell}>
      <section style={consoleHeaderStyle}>
        <div style={headerGridStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: 7,
                display: 'grid',
                placeItems: 'center',
                color: '#fff',
                background: THEME.primary,
                fontSize: 15,
                flex: '0 0 auto',
              }}
            >
              <RobotOutlined />
            </div>
            <div style={{ minWidth: 0 }}>
              <Text strong style={{ display: 'block', fontSize: 15, lineHeight: 1.2 }}>智能体</Text>
              <Text type="secondary" ellipsis style={{ display: 'block', maxWidth: 480, fontSize: 11 }}>
                {activeSession?.title || '新对话会在首次发送后自动保存'}
              </Text>
            </div>
          </div>
          <div style={commandBarStyle}>
            <Select
              value={selectedProfileId || undefined}
              onChange={setSelectedProfileId}
              style={{ minWidth: 190, width: '100%' }}
              placeholder="选择智能体"
              options={profiles.map(profile => ({
                value: profile.id,
                label: `${profile.avatar || 'Agent'} ${profile.name} · ${ROLE_TYPE_LABELS[profile.role_type || 'assistant'] || profile.role_type || '通用助手'}`,
              }))}
            />
            <Tooltip title={activeTab === 'chat' ? '查看完整运行轨迹' : '返回对话'}>
              <Button
                aria-label={activeTab === 'chat' ? '查看完整运行轨迹' : '返回对话'}
                icon={<HistoryOutlined />}
                onClick={() => setActiveTab(activeTab === 'chat' ? 'tools' : 'chat')}
                style={controlButtonStyle}
              />
            </Tooltip>
            <Tooltip title="工具与权限">
              <Button aria-label="工具与权限" icon={<ToolOutlined />} onClick={() => setToolsOpen(true)} style={controlButtonStyle} />
            </Tooltip>
            <Tooltip title="智能体设置">
              <Button aria-label="智能体设置" icon={<SettingOutlined />} onClick={() => setProfileOpen(true)} style={controlButtonStyle} />
            </Tooltip>
            <Tooltip title="刷新工作台数据">
              <Button aria-label="刷新工作台数据" icon={<ReloadOutlined />} onClick={reloadAll} style={controlButtonStyle} />
            </Tooltip>
          </div>
        </div>
      </section>

      <section
        style={workspaceGridStyle}
      >
        <aside style={leftRailStyle}>
          <section style={railSectionStyle}>
            <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 10 }}>
              <Text strong style={{ fontSize: 14 }}>对话</Text>
              <Badge count={sessions.length} size="small">
                <Button size="small" icon={<HistoryOutlined />} onClick={() => setSessionsOpen(true)}>
                  全部
                </Button>
              </Badge>
            </Space>
            <Button block type="primary" icon={<ClearOutlined />} onClick={newSession}>
              新对话
            </Button>
          </section>

          <section style={{ minHeight: 0, overflow: 'auto', padding: 10 }}>
            {resourceErrors.sessions ? (
              <div className="agent-resource-error">
                <Text type="secondary">对话列表加载失败</Text>
                <Button size="small" onClick={loadSessions}>重试</Button>
              </div>
            ) : sessions.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无对话" />
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {sessions.slice(0, 12).map(item => {
                  const isActive = currentSessionId === item.id
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => switchSession(item.id)}
                      className="agent-profile-row"
                      style={{
                        width: '100%',
                        border: `1px solid ${isActive ? THEME.primary : THEME.borderLight}`,
                        borderRadius: 8,
                        padding: '9px 10px',
                        background: isActive ? (THEME.primaryAlpha?.(0.1) || THEME.bgElevated) : THEME.bgElevated,
                        color: THEME.textPrimary,
                        textAlign: 'left',
                        cursor: 'pointer',
                      }}
                    >
                      <Text ellipsis style={{ display: 'block', fontSize: 12.5, lineHeight: 1.4, fontWeight: isActive ? 700 : 500 }}>
                        {item.title || '未命名线程'}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 10.5 }}>
                        {new Date(item.updated_at).toLocaleString('zh-CN')}
                      </Text>
                    </button>
                  )
                })}
              </div>
            )}
          </section>

          <section style={{ padding: 12, borderTop: `1px solid ${THEME.borderLight}` }}>
            <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
              <Text strong style={{ fontSize: 14 }}>智能体</Text>
              <Button size="small" icon={<SettingOutlined />} onClick={() => setProfileOpen(true)}>
                设置
              </Button>
            </Space>
            {selectedProfile ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Avatar size={24} icon={<RobotOutlined />} style={{ background: THEME.primary }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Text ellipsis strong style={{ display: 'block', fontSize: 13 }}>{selectedProfile.name}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{selectedProfile.model || selectedProfile.provider || '默认模型'}</Text>
                </div>
                <Tag>{memories.length} 记忆</Tag>
              </div>
            ) : (
              <div className="agent-resource-error">
                <Text type="secondary">未加载智能体</Text>
                <Button size="small" onClick={loadProfiles}>重试</Button>
              </div>
            )}
          </section>
        </aside>

        <Card
          className="agent-main-panel"
          style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', border: 0, borderRadius: 0, boxShadow: 'none', background: THEME.bgCard }}
          styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 } }}
        >
          <div className="agent-conversation-header">
            <div style={{ minWidth: 0 }}>
              <Text strong ellipsis style={{ display: 'block', fontSize: 14 }}>
                {activeSession?.title || '新对话'}
              </Text>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {sessionStatus}{currentRun?.steps?.length ? ` · ${currentRun.steps.length} 个执行步骤` : ''}
              </Text>
            </div>
            <Space size={4}>
              <Tooltip title="新对话">
                <Button aria-label="新对话" type="text" icon={<PlusOutlined />} onClick={newSession} />
              </Tooltip>
              <Tooltip title="全部对话">
                <Button aria-label="全部对话" type="text" icon={<HistoryOutlined />} onClick={() => setSessionsOpen(true)} />
              </Tooltip>
            </Space>
          </div>
          <Tabs
            className="agent-main-tabs"
            style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
            activeKey={activeTab}
            onChange={setActiveTab}
            renderTabBar={() => null}
            tabBarStyle={{ margin: 0, padding: '0 18px', height: 48 }}
            items={[
              {
                key: 'chat',
                label: '对话',
                children: (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateRows: 'minmax(0, 1fr) auto',
                      height: '100%',
                      minHeight: 0,
                    }}
                  >
                    <div
                      className="agent-message-scroll"
                      style={{
                        minHeight: 0,
                        overflow: 'auto',
                        padding: '24px clamp(16px, 4vw, 54px)',
                        background: THEME.bgCard,
                      }}
                    >
                      {(pendingToolSteps.length > 0 || pendingMemorySteps.length > 0) && (
                        <Space direction="vertical" size={10} style={{ width: '100%', marginBottom: 14 }}>
                          <Alert
                            type="warning"
                            showIcon
                            message={`有 ${pendingToolSteps.length + pendingMemorySteps.length} 个操作等待你的确认`}
                            description="确认后才会真正执行；这些操作涉及写入、删除或模型消耗。"
                          />
                          {pendingToolSteps.map(step => (
                            <div key={step.id} style={{ border: '1px solid #faad14', borderLeft: '4px solid #faad14', borderRadius: 10, padding: '12px 14px', background: 'rgba(250,173,20,0.06)' }}>
                              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                <Space wrap>
                                  <Tag color="warning">待确认</Tag>
                                  {step.tool_name && <Tag icon={<ToolOutlined />}>{step.tool_name}</Tag>}
                                  {step.summary && <Text type="secondary" style={{ fontSize: 12 }}>{step.summary}</Text>}
                                </Space>
                                <Space>
                                  <Button type="primary" size="small" onClick={() => handleConfirmRunStep(step.id)} loading={loading}>确认执行</Button>
                                  <Text type="secondary" style={{ fontSize: 12 }}>仅写入、删除或消耗型工具需要确认</Text>
                                </Space>
                              </Space>
                            </div>
                          ))}
                          {pendingMemorySteps.map(step => (
                            <div key={step.id} style={{ border: '1px solid #faad14', borderLeft: '4px solid #faad14', borderRadius: 10, padding: '12px 14px', background: 'rgba(250,173,20,0.06)' }}>
                              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                <Space wrap>
                                  <Tag color="warning">记忆候选项</Tag>
                                  <Text>发现可保存的长期记忆</Text>
                                </Space>
                                <Space>
                                  <Button type="primary" size="small" onClick={() => handleSaveMemoryCandidates(step.id)} loading={loading}>保存记忆</Button>
                                  <Button size="small" onClick={() => handleDiscardMemoryCandidates(step.id)} loading={loading}>丢弃</Button>
                                </Space>
                              </Space>
                            </div>
                          ))}
                        </Space>
                      )}
                      {threadRestoreError && (
                        <Alert
                          type="warning"
                          showIcon
                          closable
                          onClose={() => setThreadRestoreError('')}
                          style={{ marginBottom: 14 }}
                          message="这段对话暂时无法恢复"
                          description={threadRestoreError}
                          action={currentSessionId ? <Button size="small" onClick={() => restoreSession(currentSessionId)}>重试</Button> : undefined}
                        />
                      )}
                      {!selectedProfile && (
                        <div className="agent-message-warning">
                          <span>
                            <Text strong>智能体配置未加载</Text>
                            <Text type="secondary">仍可查看已有对话；配置恢复后再发送任务。</Text>
                          </span>
                          <Button size="small" onClick={loadProfiles}>重试</Button>
                        </div>
                      )}
                      {visibleMessages.length === 0 && !replyText && renderEmptyState()}
                      {visibleMessages.map((msg, index) => (
                        <div key={`${msg.role}-${index}`}>
                          {runTraceByMessageIndex.has(index) && renderInlineRunTrace(runTraceByMessageIndex.get(index))}
                          <div
                            style={{
                              display: 'flex',
                              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                              marginBottom: 16,
                            }}
                          >
                            <Space align="end" style={{ maxWidth: '100%', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
                              {msg.role === 'assistant' && (
                                <Avatar size={24} icon={<RobotOutlined />} style={{ backgroundColor: THEME.bgElevated, color: THEME.primary }} />
                              )}
                              <div style={bubbleStyle(msg.role)}>{renderMarkdown(msg.content, msg.role)}</div>
                            </Space>
                          </div>
                        </div>
                      ))}
                      {shouldRenderFloatingTrace && renderInlineRunTrace(currentRun)}
                      {replyText && (
                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, marginBottom: 14 }}>
                          <Avatar size={28} icon={<RobotOutlined />} style={{ backgroundColor: THEME.bgElevated, color: THEME.primary }} />
                          <div style={bubbleStyle('assistant')}>
                            {renderMarkdown(replyText, 'assistant')}
                            <Spin size="small" style={{ marginLeft: 8 }} />
                          </div>
                        </div>
                      )}
                      <div ref={messagesEndRef} />
                    </div>
                    <div
                      className="agent-command-composer"
                      style={{
                        borderTop: `1px solid ${THEME.borderLight}`,
                        padding: '12px clamp(14px, 4vw, 54px) 14px',
                        background: THEME.bgCard,
                      }}
                    >
                      {sendError && (
                        <div className="agent-send-error">
                          <Text type="danger" ellipsis={{ tooltip: sendError }}>发送失败：{sendError}</Text>
                          <Button size="small" onClick={() => sendMessage(failedPrompt)} disabled={!failedPrompt || loading}>重试</Button>
                        </div>
                      )}
                      <div className="agent-composer-frame">
                        <TextArea
                          value={input}
                          onChange={e => setInput(e.target.value)}
                          onKeyDown={handleKeyDown}
                          placeholder="告诉智能体要做什么。Enter 发送，Shift+Enter 换行。"
                          autoSize={{ minRows: 2, maxRows: 8 }}
                          variant="borderless"
                          style={{ flex: 1, minHeight: 60, resize: 'none', fontSize: 14, lineHeight: 1.5 }}
                          disabled={loading}
                        />
                        {loading ? (
                          <Tooltip title="停止生成">
                            <Button aria-label="停止" danger shape="circle" icon={<StopOutlined />} onClick={handleStopRun} />
                          </Tooltip>
                        ) : (
                          <Tooltip title={selectedProfile ? `使用「${selectedProfile.name}」` : '未选择智能体时会走默认后端逻辑'}>
                            <Button aria-label="发送" type="primary" shape="circle" icon={<SendOutlined />} onClick={() => sendMessage()} />
                          </Tooltip>
                        )}
                      </div>
                      <div style={{ marginTop: 8, borderTop: `1px solid ${THEME.borderLight}`, paddingTop: 7, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>Enter 发送 · Shift+Enter 换行</Text>
                        <Space size={10} wrap>
                          <Text type="secondary" style={{ fontSize: 11 }}>Run <span style={{ fontVariantNumeric: 'tabular-nums' }}>{currentRun?.status || '—'}</span></Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>步骤 <span style={{ fontVariantNumeric: 'tabular-nums' }}>{currentRun?.steps?.length ?? 0}</span></Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>工具 <span style={{ fontVariantNumeric: 'tabular-nums' }}>{toolSteps.length}</span></Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>耗时 <span style={{ fontVariantNumeric: 'tabular-nums' }}>{runDurationMs ? `${runDurationMs}ms` : '—'}</span></Text>
                        </Space>
                      </div>
                    </div>
                  </div>
                ),
              },
              {
                key: 'tools',
                label: (
                  <span>
                    运行轨迹
                    {(currentRun?.steps?.length || toolCalls.length) > 0 && (
                      <Badge count={currentRun?.steps?.length || toolCalls.length} style={{ marginLeft: 8 }} />
                    )}
                  </span>
                ),
                children: (
                  <div style={{ height: '100%', overflow: 'auto', padding: 16 }}>
                    {currentRun?.steps?.length ? (
                      <div style={{ display: 'grid', gap: 10 }}>
                        <Alert
                          type={currentRun.status === 'completed' ? 'success' : currentRun.status === 'failed' ? 'error' : 'info'}
                          showIcon
                          message={`Run ${currentRun.status} · ${currentRun.steps.length} 条轨迹 · 预算 ${runStats.maxSteps || 8} 轮`}
                          description={currentRun.objective || '本轮智能体执行已落库，可回放计划、工具调用、观察结果、委派子任务和最终回答。'}
                          action={
                            <Space>
                              <Button size="small" onClick={() => handleExportRunMarkdown('copy')}>
                                复制 MD
                              </Button>
                              <Button size="small" onClick={() => handleExportRunMarkdown('download')}>
                                下载 MD
                              </Button>
                              <Button size="small" onClick={handleInspectRunSkillCandidate} loading={runSkillLoading}>
                                分析 Skill
                              </Button>
                              <Button
                                size="small"
                                onClick={handleCreateSkillDraftFromRun}
                                loading={runSkillLoading}
                                disabled={runSkillAnalysis ? !runSkillAnalysis.eligible : currentRun.status !== 'completed'}
                              >
                                生成草稿
                              </Button>
                              {currentRun.steps.some(step => step.status === 'failed' && step.step_type === 'tool_call') && (
                                <Button size="small" onClick={() => handleRetryRunStep()} loading={loading}>
                                  重试失败
                                </Button>
                              )}
                              <Button size="small" type="primary" onClick={handleContinueRun} loading={loading}>
                                继续执行
                              </Button>
                            </Space>
                          }
                        />
                        {renderRunSkillSummary(currentRun)}
                        {runSkillAnalysis && (
                          <Alert
                            type={runSkillAnalysis.eligible ? 'success' : 'warning'}
                            showIcon
                            message={runSkillAnalysis.eligible ? '这个 Run 可以沉淀为 Skill 草稿' : '这个 Run 暂不适合沉淀'}
                            description={
                              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                <Space wrap>
                                  <Tag>评分 {runSkillAnalysis.score || 0}</Tag>
                                  <Tag>成功工具 {runSkillAnalysis.successful_tool_count || 0}</Tag>
                                  <Tag>工具种类 {(runSkillAnalysis.unique_tools || []).length}</Tag>
                                  {(runSkillAnalysis.unique_tools || []).slice(0, 6).map((tool: string) => (
                                    <Tag key={tool}>{tool}</Tag>
                                  ))}
                                </Space>
                                {!runSkillAnalysis.eligible && (runSkillAnalysis.reasons || []).length > 0 && (
                                  <Text type="secondary">
                                    原因：{runSkillAnalysis.reasons.join('；')}
                                  </Text>
                                )}
                                {runSkillAnalysis.eligible && (
                                  <Space wrap>
                                    <Text type="secondary">
                                      点击“生成草稿”会创建待审批 SKILL.md，不会自动启用。
                                    </Text>
                                    <Button size="small" type="link" onClick={() => navigate('/settings?tab=agent-skills')}>
                                      打开审批页
                                    </Button>
                                  </Space>
                                )}
                              </Space>
                            }
                          />
                        )}
                        {renderLinkedLogs()}
                        {runTree && runTree.delegations.length > 0 && (
                          <section
                            style={{
                              borderTop: `1px solid ${THEME.borderLight}`,
                              borderBottom: `1px solid ${THEME.borderLight}`,
                              padding: '12px 0',
                              display: 'grid',
                              gap: 10,
                            }}
                          >
                            <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
                              <Space>
                                <ApartmentOutlined style={{ color: THEME.primary }} />
                                <Text strong>Agent 执行树</Text>
                                <Tag>{runTree.runs.length} Runs</Tag>
                                <Tag>{runTree.delegations.length} 子任务</Tag>
                              </Space>
                              <Space size={4} wrap>
                                <Tag>深度 {Math.max(0, ...runTree.runs.map(run => run.delegation_depth || 0))}/{runTree.limits?.max_depth || 2}</Tag>
                                <Tag>并发 {runTree.limits?.max_concurrency || 3}</Tag>
                                <Tag>根预算 {runTree.delegations.length}/{runTree.limits?.max_children_per_root || 12}</Tag>
                              </Space>
                            </Space>
                            <div style={{ overflowX: 'auto' }}>
                              <div style={{ minWidth: 620, display: 'grid' }}>
                                {runTree.delegations.map((delegation, index) => {
                                  const childRun = runTree.runs.find(run => run.id === delegation.child_run_id)
                                  const profile = profiles.find(item => item.id === delegation.target_profile_id)
                                  const detail = delegation.error || String(delegation.result?.reply || '')
                                  return (
                                    <div
                                      key={delegation.id}
                                      style={{
                                        display: 'grid',
                                        gridTemplateColumns: '38px minmax(130px, 180px) minmax(260px, 1fr)',
                                        gap: 10,
                                        alignItems: 'start',
                                        padding: '10px 8px',
                                        borderTop: index === 0 ? 'none' : `1px solid ${THEME.borderLight}`,
                                      }}
                                    >
                                      <span
                                        style={{
                                          width: 24,
                                          height: 24,
                                          display: 'grid',
                                          placeItems: 'center',
                                          borderRadius: 6,
                                          background: THEME.bgElevated,
                                          color: THEME.textSecondary,
                                          marginLeft: Math.min((childRun?.delegation_depth || 1) - 1, 1) * 8,
                                        }}
                                      >
                                        {index + 1}
                                      </span>
                                      <Space direction="vertical" size={2}>
                                        <Text strong>{profile?.name || delegation.target_profile_id}</Text>
                                        <Space size={4} wrap>
                                          <Tag color={getStepStatusColor(delegation.status)}>{delegation.status}</Tag>
                                          <Text type="secondary" style={{ fontSize: 11 }}>
                                            L{childRun?.delegation_depth || 1}
                                          </Text>
                                        </Space>
                                      </Space>
                                      <Space direction="vertical" size={3} style={{ minWidth: 0 }}>
                                        <Text>{delegation.objective}</Text>
                                        {detail && (
                                          <Text type={delegation.error ? 'danger' : 'secondary'} ellipsis={{ tooltip: detail }}>
                                            {detail}
                                          </Text>
                                        )}
                                        {delegation.depends_on.length > 0 && (
                                          <Text type="secondary" style={{ fontSize: 11 }}>
                                            依赖：{delegation.depends_on.join('、')}
                                          </Text>
                                        )}
                                        <Space size={4} wrap>
                                          <Tag>{delegation.execution_mode === 'parallel' ? '并行批次' : '顺序任务'}</Tag>
                                          {Array.isArray(delegation.result?.linked_objects) && delegation.result.linked_objects.length > 0 && (
                                            <Tag color="processing">{delegation.result.linked_objects.length} 个产物</Tag>
                                          )}
                                          {delegation.child_run_id && <Tag>Run {delegation.child_run_id.slice(0, 8)}</Tag>}
                                        </Space>
                                      </Space>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          </section>
                        )}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'minmax(150px, 180px) minmax(150px, 180px) minmax(160px, 1fr)',
                            gap: 8,
                            alignItems: 'center',
                          }}
                        >
                          <Select
                            value={stepStatusFilter}
                            onChange={setStepStatusFilter}
                            options={runStepStatusOptions}
                          />
                          <Select
                            value={stepTypeFilter}
                            onChange={setStepTypeFilter}
                            options={runStepTypeOptions}
                          />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            当前显示 {filteredRunSteps.length}/{currentRun.steps.length} 个步骤
                          </Text>
                        </div>
                        <div
                          style={{
                            border: `1px solid ${THEME.borderLight}`,
                            borderRadius: 10,
                            padding: 12,
                            background: THEME.bgCard,
                          }}
                        >
                          <Space direction="vertical" size={8} style={{ width: '100%' }}>
                            <Space style={{ justifyContent: 'space-between', width: '100%' }} align="center">
                              <Space>
                                <RobotOutlined style={{ color: THEME.primary }} />
                                <Text strong>委派子任务</Text>
                              </Space>
                              <Tag>父子 Run 链</Tag>
                            </Space>
                            <div style={{ display: 'grid', gridTemplateColumns: '180px minmax(180px, 1fr) auto', gap: 8 }}>
                              <Select
                                value={delegateProfileId || undefined}
                                onChange={setDelegateProfileId}
                                placeholder="选择子智能体"
                                options={delegateProfileOptions}
                              />
                              <Input
                                value={delegateMessage}
                                onChange={event => setDelegateMessage(event.target.value)}
                                placeholder="例如：请以分镜导演身份检查第 2 章分镜缺口"
                              />
                              <Button
                                type="primary"
                                onClick={handleDelegateRun}
                                disabled={!delegateProfileId || !currentRun}
                                loading={loading}
                              >
                                委派并续跑
                              </Button>
                            </div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              子智能体使用独立对话和数据库 Session；结果汇合后，父智能体会在当前 Run 中继续规划并给出答复。
                            </Text>
                          </Space>
                        </div>
                        {filteredRunSteps.length > 0 ? (
                          filteredRunSteps.map(renderRunStep)
                        ) : (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的运行步骤" />
                        )}
                      </div>
                    ) : toolCalls.length === 0 ? (
                      <div style={{ display: 'grid', gap: 12 }}>
                        <Alert
                          type="info"
                          showIcon
                          message="还没有运行轨迹"
                          description="发送请求后，后端会创建 run，并按计划、工具、观察、继续的循环记录每一次推进。执行预算只是防跑偏阈值，不是能力上限。"
                        />
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
                          {EXECUTION_LOOP_STAGES.map((step, index) => (
                            <div
                              key={step}
                              style={{
                                border: `1px solid ${THEME.borderLight}`,
                                borderRadius: 8,
                                padding: 12,
                                background: THEME.bgCard,
                              }}
                            >
                              <Text type="secondary" style={{ fontSize: 12 }}>0{index + 1}</Text>
                              <div style={{ color: THEME.textPrimary, fontWeight: 600 }}>{step}</div>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {index === 0 ? '拆解目标' : index === 1 ? '调用能力' : index === 2 ? '读取返回' : '决定续跑'}
                              </Text>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'grid', gap: 10 }}>
                        <Alert
                          type={toolCalls.every(item => item.success) ? 'success' : 'warning'}
                          showIcon
                          message={`本轮执行了 ${toolCalls.length} 个工具`}
                          description="这是流式事件里的临时工具摘要；run 详情加载后会显示完整步骤。"
                        />
                        {toolCalls.map(renderToolResult)}
                      </div>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </Card>

        <aside style={{ display: 'none' }}>
          <Card className="agent-inspector-panel" style={{ ...panelStyle, height: '100%' }} styles={{ body: { padding: '0 16px', height: '100%', overflow: 'auto' } }}>
            <section style={inspectorSectionStyle}>
              <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }}>
                <Text strong style={{ fontSize: 15 }}>运行 Inspector</Text>
                <Tag color={currentRun ? 'processing' : selectedProfile ? 'success' : 'warning'}>
                  {currentRun?.status || (selectedProfile ? 'ready' : 'empty')}
                </Tag>
              </Space>
              {selectedProfile ? (
                <Space align="start" style={{ width: '100%' }}>
                  <Avatar
                    size={44}
                    icon={<RobotOutlined />}
                    style={{
                      borderRadius: 10,
                      background: THEME.primary,
                      boxShadow: `0 10px 24px ${THEME.primaryAlpha?.(0.18) || 'rgba(22,119,255,0.18)'}`,
                    }}
                  >
                    {selectedProfile.avatar}
                  </Avatar>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <Text strong style={{ display: 'block', fontSize: 15 }}>{selectedProfile.name}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {ROLE_TYPE_LABELS[selectedProfile.role_type || 'assistant'] || selectedProfile.role_type || '通用助手'} / 预算 {selectedProfile.max_steps} 轮
                    </Text>
                    <Space wrap size={[4, 4]} style={{ marginTop: 8 }}>
                      <Tag>{selectedProfile.model || '默认模型'}</Tag>
                      <Tag color={allowAllTools ? 'success' : 'processing'}>{allowAllTools ? tools.length : authorizedTools.length} 工具</Tag>
                      <Tag color={currentSessionId ? 'processing' : 'default'}>{sessionStatus}</Tag>
                    </Space>
                  </div>
                </Space>
              ) : (
                <Alert type="warning" showIcon message="没有拿到智能体配置" />
              )}
            </section>

            <section style={inspectorSectionStyle}>
              <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
                <Text strong>当前线程</Text>
                <Tag>{visibleMessages.length} 条消息</Tag>
              </Space>
              <div style={{ color: THEME.textPrimary, fontWeight: 700, wordBreak: 'break-word', marginBottom: 4 }}>
                {activeSession?.title || (currentSessionId ? '已绑定线程' : '新线程，首轮发送后保存')}
              </div>
              <Text style={compactMetaStyle}>刷新会优先恢复上次线程，并加载最近一次 run 轨迹。</Text>
            </section>

            {/* 待确认的线程注解（pending memory candidates 作为线程级别提示） */}
            {(() => {
              const pendingMemorySteps = (currentRun?.steps || []).filter(
                step => step.step_type === 'memory_extract' && step.status === 'pending'
              )
              if (pendingMemorySteps.length === 0) return null
              const totalCandidates = pendingMemorySteps.reduce(
                (acc, step) => acc + (Array.isArray(step.output?.candidates) ? step.output.candidates.length : 0), 0
              )
              return (
                <section style={{ ...inspectorSectionStyle, border: '1px solid #faad14', borderRadius: 8, background: 'rgba(250,173,20,0.04)' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong style={{ fontSize: 13 }}>待确认的线程注解</Text>
                    <Badge count={totalCandidates} size="small" />
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                    {totalCandidates} 条记忆候选项需要确认，可在轨迹面板操作保存或丢弃。
                  </Text>
                  {pendingMemorySteps.map((step, stepIdx) => {
                    const candidates = Array.isArray(step.output?.candidates) ? step.output.candidates : []
                    return candidates.map((item: any, idx: number) => (
                      <div key={`${step.id}-${idx}`} style={{ marginTop: 8, padding: '6px 8px', background: THEME.bgCard, borderRadius: 6 }}>
                        <Text strong style={{ fontSize: 12 }}>{item.key || `候选项 ${idx + 1}`}</Text>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 2 }}>
                          {typeof item.value === 'string' ? item.value.slice(0, 80) : JSON.stringify(item.value).slice(0, 80)}
                          {typeof item.value === 'string' && item.value.length > 80 ? '...' : ''}
                        </Text>
                      </div>
                    ))
                  })}
                </section>
              )
            })()}

            <section style={inspectorSectionStyle}>
              <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 10 }}>
                <Text strong>模型来源</Text>
                <Tag color={llmConnectors.length ? 'processing' : 'warning'}>
                  {llmConnectors.length ? `${llmConnectors.length} 个连接` : '未配置'}
                </Tag>
              </Space>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>供应商</Text>
                  <div style={{ color: THEME.textPrimary, fontWeight: 700, wordBreak: 'break-word' }}>
                    {selectedProfile?.provider || '系统默认'}
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>模型</Text>
                  <div style={{ color: THEME.textPrimary, fontWeight: 700, wordBreak: 'break-word' }}>
                    {selectedProfile?.model || '供应商默认'}
                  </div>
                </div>
              </div>
            </section>

            <details className="agent-inspector-details" style={inspectorSectionStyle}>
              <summary>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>创作团队</Text>
                  <Tag>{profiles.length} 个</Tag>
                </Space>
              </summary>
              <div style={{ display: 'grid', gap: 6, maxHeight: 210, overflow: 'auto' }}>
                {profiles.map(profile => {
                  const isActive = profile.id === selectedProfileId
                  const toolCount = profile.allowed_tools?.includes('*') ? tools.length : (profile.allowed_tools || []).length
                  return (
                    <button
                      key={profile.id}
                      type="button"
                      className="agent-profile-row"
                      onClick={() => setSelectedProfileId(profile.id)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        border: `1px solid ${isActive ? THEME.primary : THEME.borderLight}`,
                        borderRadius: 9,
                        padding: '9px 10px',
                        background: isActive ? (THEME.primaryAlpha?.(0.08) || 'rgba(22,119,255,0.08)') : THEME.bgElevated,
                        color: THEME.textPrimary,
                        cursor: 'pointer',
                      }}
                    >
                      <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                        <span>
                          <Text strong style={{ display: 'block', fontSize: 13 }}>{profile.avatar || 'AI'} {profile.name}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {ROLE_TYPE_LABELS[profile.role_type || 'assistant'] || profile.role_type || '通用助手'}
                          </Text>
                        </span>
                        <Tag style={{ marginInlineEnd: 0 }}>{toolCount}</Tag>
                      </Space>
                    </button>
                  )
                })}
              </div>
            </details>

            <details className="agent-inspector-details" style={inspectorSectionStyle}>
              <summary>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>运行上下文</Text>
                  <Tag color={currentRun ? 'processing' : 'default'}>{currentRun ? '已注入' : '未开始'}</Tag>
                </Space>
              </summary>
              {currentRun ? renderContextSummary(currentRun.context) : <Text type="secondary" style={{ fontSize: 12 }}>暂无运行中的上下文</Text>}
              {currentRun && (
                <details style={{ marginTop: 10 }}>
                  <summary style={{ cursor: 'pointer', color: THEME.textSecondary, fontSize: 12 }}>
                    查看完整上下文 JSON
                  </summary>
                  <pre
                    style={{
                      margin: '8px 0 0',
                      padding: 10,
                      borderRadius: 8,
                      background: THEME.bgPage,
                      color: THEME.textPrimary,
                      border: `1px solid ${THEME.borderLight}`,
                      maxHeight: 180,
                      overflow: 'auto',
                      fontSize: 12,
                    }}
                  >
                    {JSON.stringify(currentRun.context || {}, null, 2)}
                  </pre>
                </details>
              )}
            </details>

            <details className="agent-inspector-details" style={inspectorSectionStyle}>
              <summary>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>记忆 / 技能</Text>
                  <Space size={4}>
                    <Tag>{memories.length} 记忆</Tag>
                    <Tag>{skills.length} 技能</Tag>
                    <Button type="link" size="small" onClick={loadMemories}>刷新</Button>
                  </Space>
                </Space>
              </summary>
              {memoryLoadError && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 8 }}
                  message="记忆 / 技能加载失败"
                  description={memoryLoadError}
                />
              )}
              {memories.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无长期记忆" />
              ) : (
                <div style={{ display: 'grid', gap: 8 }}>
                  {memories.slice(0, 3).map(memory => (
                    <div key={memory.key} style={{ paddingBottom: 8, borderBottom: `1px solid ${THEME.borderLight}` }}>
                      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                        <Text strong style={{ fontSize: 13 }}>{memory.key}</Text>
                        <Space size={4}>
                          <Tag>{memory.type}</Tag>
                          {typeof memory.confidence === 'number' && <Tag>{Math.round(memory.confidence * 100)}%</Tag>}
                        </Space>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>{String(memory.value).slice(0, 92)}</Text>
                    </div>
                  ))}
                </div>
              )}
              {skills.length > 0 && (
                <Space wrap size={[6, 6]} style={{ marginTop: 10 }}>
                  {skills.slice(0, 5).map(skill => <Tag key={skill.id}>{skill.name}</Tag>)}
                </Space>
              )}
            </details>

            <details className="agent-inspector-details" style={{ padding: '14px 0' }}>
              <summary>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Text strong>最近线程</Text>
                  <Button type="link" size="small" onClick={() => setSessionsOpen(true)}>全部</Button>
                </Space>
              </summary>
              {sessions.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无线程" />
              ) : (
                <List
                  size="small"
                  dataSource={sessions.slice(0, 5)}
                  renderItem={item => {
                    const isActive = currentSessionId === item.id
                    return (
                      <List.Item
                        style={{
                          cursor: 'pointer',
                          marginBottom: 6,
                          padding: '9px 10px',
                          borderRadius: 9,
                          border: `1px solid ${isActive ? THEME.primary : THEME.borderLight}`,
                          background: isActive ? (THEME.primaryAlpha?.(0.08) || 'rgba(22,119,255,0.08)') : THEME.bgElevated,
                        }}
                        onClick={() => switchSession(item.id)}
                      >
                        <List.Item.Meta
                          title={<Text ellipsis style={{ fontWeight: isActive ? 700 : 500 }}>{item.title}</Text>}
                          description={new Date(item.updated_at).toLocaleString('zh-CN')}
                        />
                        {isActive && <CheckCircleOutlined style={{ color: THEME.primary }} />}
                      </List.Item>
                    )
                  }}
                />
              )}
            </details>
          </Card>
        </aside>
      </section>

      <Drawer
        title="线程历史"
        placement="right"
        width={380}
        open={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        extra={
          <Button type="primary" size="small" icon={<ClearOutlined />} onClick={newSession}>
            新线程
          </Button>
        }
      >
        <List
          dataSource={sessions}
          locale={{ emptyText: '暂无历史线程' }}
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
                    style={{ backgroundColor: currentSessionId === item.id ? THEME.primary : '#8c8c8c' }}
                  />
                }
                title={item.title}
                description={new Date(item.updated_at).toLocaleString('zh-CN')}
              />
            </List.Item>
          )}
        />
      </Drawer>

      <Drawer
        title={
          <Space direction="vertical" size={2}>
            <Text strong style={{ color: THEME.textPrimary }}>可用工具</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              授权状态、风险等级和输入输出规范会直接影响智能体能否自动调用。
            </Text>
          </Space>
        }
        placement="right"
        width={760}
        open={toolsOpen}
        onClose={() => setToolsOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type={selectedProfile ? 'info' : 'warning'}
            showIcon
            message={selectedProfile ? `当前智能体：${selectedProfile.name}` : '未选择智能体'}
            description="未授权表示该工具不在当前智能体的工具白名单里，模型即使想调用也会被后端拦截。到“设定 - 工具授权”里勾选，或选择 * 全部工具。"
          />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
              gap: 8,
            }}
          >
            {[
              { label: '全部工具', value: tools.length },
              { label: '已授权', value: authorizedTools.length },
              { label: '当前显示', value: filteredTools.length },
              { label: '分类数', value: visibleCategories.length },
            ].map(item => (
              <div
                key={item.label}
                style={{
                  border: `1px solid ${THEME.borderLight}`,
                  borderRadius: 8,
                  padding: '8px 10px',
                  background: THEME.bgCard,
                }}
              >
                <div style={{ fontSize: 12, color: THEME.textSecondary }}>{item.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: THEME.textPrimary }}>{item.value}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) 150px 130px 130px', gap: 8 }}>
            <Input
              allowClear
              placeholder="搜索工具名、说明、输入输出"
              value={toolSearch}
              onChange={event => setToolSearch(event.target.value)}
            />
            <Select
              value={toolCategoryFilter}
              onChange={setToolCategoryFilter}
              options={[
                { label: '全部分类', value: 'all' },
                ...GROUPED_CATEGORIES.map(category => ({
                  label: CATEGORY_LABELS[category] || category,
                  value: category,
                })),
              ]}
            />
            <Select
              value={toolAuthFilter}
              onChange={setToolAuthFilter}
              options={[
                { label: '全部权限', value: 'all' },
                { label: '已授权', value: 'authorized' },
                { label: '未授权', value: 'blocked' },
              ]}
            />
            <Select
              value={toolRiskFilter}
              onChange={setToolRiskFilter}
              options={[
                { label: '全部风险', value: 'all' },
                ...Object.keys(RISK_LABELS).map(risk => ({
                  label: RISK_LABELS[risk],
                  value: risk,
                })),
              ]}
            />
          </div>
        </Space>
        <div style={{ marginTop: 16 }}>
        {visibleCategories.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的工具" />
        ) : visibleCategories.map(category => {
          const catTools = filteredTools.filter(tool => tool.category === category)
          if (!catTools.length) return null
          return (
            <div key={category} style={{ marginBottom: 18 }}>
              <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
                <Space>
                  <span style={{ color: THEME.primary }}>{CATEGORY_ICONS[category]}</span>
                  <Text strong>{CATEGORY_LABELS[category] || category}</Text>
                </Space>
                <Badge count={catTools.length} color={THEME.primary} />
              </Space>
              <div style={{ display: 'grid', gap: 10 }}>
                {catTools.map(tool => (
                  <div
                    key={tool.name}
                    style={{
                      border: `1px solid ${isToolAuthorized(tool.name) ? THEME.primaryAlpha?.(0.28) || THEME.borderLight : THEME.borderLight}`,
                      borderRadius: 8,
                      padding: 12,
                      background: isToolAuthorized(tool.name)
                        ? (THEME.primaryAlpha?.(0.055) || 'rgba(22,119,255,0.055)')
                        : THEME.bgCard,
                    }}
                  >
                    <Space style={{ justifyContent: 'space-between', width: '100%', alignItems: 'start' }}>
                      <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
                        <Space wrap>
                          <Tag color={CATEGORY_COLORS[tool.category]}>{CATEGORY_LABELS[tool.category] || tool.category}</Tag>
                          <Tag color={RISK_COLORS[tool.risk_level || 'read'] || 'default'}>
                            {RISK_LABELS[tool.risk_level || 'read'] || tool.risk_level || '只读'}
                          </Tag>
                          {tool.output_type && <Tag>{tool.output_type}</Tag>}
                          {tool.cost_hint && <Tag color="orange">成本提示</Tag>}
                        </Space>
                        <Text strong style={{ color: THEME.textPrimary, wordBreak: 'break-word' }}>
                          {tool.name}
                        </Text>
                      </Space>
                      <Space wrap style={{ justifyContent: 'flex-end' }}>
                        {permissionTag(tool.name)}
                        <Button size="small" onClick={() => setProfileOpen(true)} icon={<SettingOutlined />}>
                          调整授权
                        </Button>
                      </Space>
                    </Space>
                    <div style={{ marginTop: 6, color: THEME.textSecondary, lineHeight: 1.6 }}>
                      {tool.description}
                    </div>
                    {!isToolAuthorized(tool.name) && (
                      <div
                        style={{
                          marginTop: 8,
                          padding: '6px 8px',
                          borderRadius: 8,
                          background: 'rgba(250, 173, 20, 0.1)',
                          color: THEME.textSecondary,
                          fontSize: 12,
                        }}
                      >
                        当前智能体不能自动调用这个工具；需要在设定里授权后才会进入候选工具列表。
                      </div>
                    )}
                    {(tool.input_schema_note || tool.output_schema_note) && (
                      <div
                        style={{
                          marginTop: 10,
                          display: 'grid',
                          gap: 8,
                          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                        }}
                      >
                        {tool.input_schema_note && (
                          <div
                            style={{
                              border: `1px solid ${THEME.borderLight}`,
                              borderRadius: 8,
                              padding: 8,
                              background: THEME.bgPage,
                            }}
                          >
                            <Text strong style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                              输入规范
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.6 }}>
                              {tool.input_schema_note}
                            </Text>
                          </div>
                        )}
                        {tool.output_schema_note && (
                          <div
                            style={{
                              border: `1px solid ${THEME.borderLight}`,
                              borderRadius: 8,
                              padding: 8,
                              background: THEME.bgPage,
                            }}
                          >
                            <Text strong style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                              输出规范
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.6 }}>
                              {tool.output_schema_note}
                            </Text>
                          </div>
                        )}
                      </div>
                    )}
                    {tool.cost_hint && (
                      <Alert
                        type="warning"
                        showIcon
                        style={{ marginTop: 8 }}
                        message="成本提示"
                        description={tool.cost_hint}
                      />
                    )}
                    {tool.examples?.length > 0 && (
                      <Space wrap size={[4, 4]} style={{ marginTop: 8 }}>
                        {tool.examples.slice(0, 2).map(example => (
                          <Tag key={example}>{example}</Tag>
                        ))}
                      </Space>
                    )}
                    <div
                      style={{
                        marginTop: 10,
                        borderTop: `1px solid ${THEME.borderLight}`,
                        paddingTop: 10,
                        display: 'grid',
                        gap: 8,
                      }}
                    >
                      <Input.TextArea
                        value={toolTestArgs[tool.name] || ''}
                        onChange={event => setToolTestArgs(prev => ({ ...prev, [tool.name]: event.target.value }))}
                        placeholder='测试参数 JSON，例如 {"project_id":"..."}；无参数可留空'
                        autoSize={{ minRows: 1, maxRows: 4 }}
                      />
                      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
                        <Space>
                          <Button
                            size="small"
                            icon={<ToolOutlined />}
                            loading={testingToolName === tool.name}
                            onClick={() => handleTestTool(tool)}
                            disabled={!isToolAuthorized(tool.name)}
                          >
                            测试工具
                          </Button>
                          {toolTestResults[tool.name]?.pending_confirmation && (
                            <Button
                              size="small"
                              type="primary"
                              loading={testingToolName === tool.name}
                              onClick={() => handleTestTool(tool, true)}
                            >
                              确认测试执行
                            </Button>
                          )}
                        </Space>
                        {toolTestResults[tool.name] && (
                          <Tag color={toolTestResults[tool.name]?.success ? 'success' : toolTestResults[tool.name]?.pending_confirmation ? 'warning' : 'error'}>
                            {toolTestResults[tool.name]?.pending_confirmation
                              ? '等待确认'
                              : toolTestResults[tool.name]?.success
                                ? '测试成功'
                                : '测试失败'}
                          </Tag>
                        )}
                      </Space>
                      {toolTestResults[tool.name] && (
                        <details>
                          <summary style={{ cursor: 'pointer', color: THEME.textSecondary, fontSize: 12 }}>
                            查看测试返回
                          </summary>
                          <pre
                            style={{
                              margin: '8px 0 0',
                              padding: 10,
                              borderRadius: 8,
                              background: THEME.bgPage,
                              color: THEME.textPrimary,
                              border: `1px solid ${THEME.borderLight}`,
                              maxHeight: 220,
                              overflow: 'auto',
                              fontSize: 12,
                            }}
                          >
                            {JSON.stringify(toolTestResults[tool.name], null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
        </div>
      </Drawer>

      <Drawer
        title="智能体设定"
        placement="right"
        width={580}
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        extra={
          <Space>
            <Button icon={<PlusOutlined />} onClick={handleCreateProfile}>
              复制新建
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveProfile} disabled={!selectedProfile}>
              保存
            </Button>
          </Space>
        }
      >
        {selectedProfile ? (
          <Form form={profileForm} layout="vertical">
            <Tabs
              items={[
                {
                  key: 'profile',
                  label: 'Profile',
                  forceRender: true,
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Alert
                        type="info"
                        showIcon
                        message="基础身份"
                        description="这里决定智能体在团队里的角色、名称和对用户可见的定位说明。"
                      />
                      <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
                        <Input />
                      </Form.Item>
                      <Form.Item name="avatar" label="头像标识">
                        <Input maxLength={8} placeholder="可留空" />
                      </Form.Item>
                      <Form.Item name="role_type" label="智能体角色">
                        <Select options={ROLE_TYPE_OPTIONS} placeholder="选择这个智能体在团队里的职责" />
                      </Form.Item>
                      <Form.Item name="description" label="定位说明">
                        <Input />
                      </Form.Item>
                      <Form.Item name="is_default" valuePropName="checked">
                        <Checkbox>设为默认智能体</Checkbox>
                      </Form.Item>
                    </Space>
                  ),
                },
                {
                  key: 'model',
                  label: 'Model',
                  forceRender: true,
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Alert
                        type="info"
                        showIcon
                        message="模型和行为"
                        description="系统设定会和中枢提示、记忆、默认上下文一起发送给文本模型；迭代预算决定它一轮最多自动规划、调用工具、观察结果并继续执行的轮数，达到上限后自动总结已完成和下一步。"
                      />
                      <Form.Item
                        name="system_prompt"
                        label="系统设定"
                        tooltip="描述这个智能体的职责、边界、输出风格和协作方式。"
                      >
                        <TextArea rows={10} placeholder="例如：你是短剧创作导演，先检查项目缺口，再按授权工具推进。" />
                      </Form.Item>
                      <Form.Item name="provider" label="文本供应商">
                        <Select
                          allowClear
                          showSearch
                          placeholder="留空则使用系统默认文本模型"
                          options={llmProviderOptions}
                          optionFilterProp="label"
                          onChange={(value) => {
                            const nextProvider = value || ''
                            setEditingProvider(nextProvider)
                            const connector = llmConnectors.find(item => item.name === nextProvider)
                            profileForm.setFieldValue('model', connector?.default_model || connector?.model || normalizeModelList(connector?.available_models)[0] || '')
                          }}
                          notFoundContent="暂无可用文本模型，请先到设置里配置 LLM"
                        />
                      </Form.Item>
                      <Form.Item name="model" label="文本模型">
                        <Select
                          allowClear
                          showSearch
                          placeholder="留空则使用供应商默认模型"
                          options={llmModelOptions}
                          optionFilterProp="label"
                          disabled={!editingProvider}
                          notFoundContent="该供应商未配置模型列表"
                        />
                      </Form.Item>
                      <Form.Item
                        name="max_steps"
                        label="迭代预算（轮）"
                        tooltip="每轮智能体自动运行时会先规划、再调用工具、观察结果并继续推进；预算耗尽后自动总结已完成工作和下一步建议。这是防跑偏的安全阈值，不是智能体能力上限。推荐 8-12 轮。"
                      >
                        <InputNumber min={1} max={20} style={{ width: '100%' }} />
                      </Form.Item>
                      <Form.Item
                        name="can_delegate"
                        valuePropName="checked"
                        tooltip="启用后，该智能体可以把复杂任务拆给专业子智能体并在结果汇合后继续推理。Worker 建议关闭。"
                      >
                        <Checkbox>Supervisor：允许委派子智能体</Checkbox>
                      </Form.Item>
                    </Space>
                  ),
                },
                {
                  key: 'tools',
                  label: 'Tools',
                  forceRender: true,
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Alert
                        type="warning"
                        showIcon
                        message={`当前已授权 ${allowAllTools ? tools.length : authorizedTools.length}/${tools.length} 个工具`}
                        description="未授权工具不会进入模型候选列表；高风险工具即使授权，也会先生成待确认步骤。"
                      />
                      <Form.Item
                        name="allowed_tools"
                        label="工具授权"
                        tooltip="选择 * 表示允许调用全部工具；否则只允许调用勾选工具。"
                      >
                        <Select
                          mode="multiple"
                          allowClear
                          showSearch
                          options={[{ label: '* 全部工具', value: '*' }, ...toolOptions]}
                          placeholder="选择允许调用的工具"
                          optionFilterProp="label"
                        />
                      </Form.Item>
                      <div style={{ display: 'grid', gap: 8, maxHeight: 440, overflow: 'auto' }}>
                        {tools.map(tool => (
                          <div
                            key={tool.name}
                            style={{
                              border: `1px solid ${THEME.borderLight}`,
                              borderRadius: 8,
                              padding: 10,
                              background: isToolAuthorized(tool.name) ? (THEME.primaryAlpha?.(0.06) || 'rgba(22,119,255,0.06)') : THEME.bgCard,
                            }}
                          >
                            <Space wrap size={[6, 6]}>
                              <Tag color={CATEGORY_COLORS[tool.category]}>{CATEGORY_LABELS[tool.category] || tool.category}</Tag>
                              <Tag>{tool.name}</Tag>
                              {permissionTag(tool.name)}
                              <Tag color={RISK_COLORS[tool.risk_level || 'read'] || 'default'}>
                                {RISK_LABELS[tool.risk_level || 'read'] || tool.risk_level || '只读'}
                              </Tag>
                              {tool.cost_hint && <Tag color="orange">成本提示</Tag>}
                            </Space>
                            <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
                              {tool.description}
                            </Text>
                            {(tool.input_schema_note || tool.output_schema_note) && (
                              <div style={{ marginTop: 6, display: 'grid', gap: 2 }}>
                                {tool.input_schema_note && <Text type="secondary" style={{ fontSize: 12 }}>输入：{tool.input_schema_note}</Text>}
                                {tool.output_schema_note && <Text type="secondary" style={{ fontSize: 12 }}>输出：{tool.output_schema_note}</Text>}
                                {tool.cost_hint && <Text type="secondary" style={{ fontSize: 12 }}>成本：{tool.cost_hint}</Text>}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </Space>
                  ),
                },
                {
                  key: 'memory',
                  label: 'Memory',
                  forceRender: true,
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Alert
                        type="info"
                        showIcon
                        message="长期记忆"
                        description="用于保存用户偏好、项目规则和事实片段。后续对话会注入这些记忆，当前版本先手动维护。"
                      />
                      <Form form={memoryForm} layout="vertical" component={false}>
                        <Form.Item name="key" label="记忆键" rules={[{ required: true, message: '请输入记忆键' }]}>
                          <Input placeholder="例如 creative.project.rule.visual_consistency" />
                        </Form.Item>
                        <Form.Item name="value" label="记忆内容" rules={[{ required: true, message: '请输入记忆内容' }]}>
                          <TextArea rows={4} placeholder="例如：角色立绘优先二次元国漫美型，不使用 3D 写实风格。" />
                        </Form.Item>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: 8 }}>
                          <Form.Item name="memory_type" label="类型">
                            <Select
                              options={[
                                { label: '偏好', value: 'preference' },
                                { label: '项目上下文', value: 'project_context' },
                                { label: '事实', value: 'fact' },
                              ]}
                            />
                          </Form.Item>
                          <Form.Item name="importance" label="重要性">
                            <InputNumber min={1} max={10} style={{ width: '100%' }} />
                          </Form.Item>
                        </div>
                        <Button type="primary" onClick={handleSaveMemory} loading={savingMemory}>
                          保存记忆
                        </Button>
                      </Form>
                      <div style={{ display: 'grid', gap: 8, maxHeight: 320, overflow: 'auto' }}>
                        {memories.length === 0 ? (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无长期记忆" />
                        ) : (
                          memories.map(memory => (
                            <div key={memory.key} style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: 10 }}>
                              <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start">
                                <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
                                  <Space wrap>
                                    <Text strong>{memory.key}</Text>
                                    <Tag>{memory.type}</Tag>
                                    <Tag>重要性 {memory.importance}</Tag>
                                  </Space>
                                  <Text type="secondary" style={{ whiteSpace: 'pre-wrap' }}>{memory.value}</Text>
                                </Space>
                                <Button danger size="small" onClick={() => handleDeleteMemory(memory.key)}>
                                  删除
                                </Button>
                              </Space>
                            </div>
                          ))
                        )}
                      </div>
                      <div style={{ display: 'grid', gap: 8 }}>
                        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                          <Text strong>Skill 模板</Text>
                          <Tag>{skills.length} 个</Tag>
                        </Space>
                        {skills.length === 0 ? (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Skill 模板" />
                        ) : (
                          <div style={{ display: 'grid', gap: 8, maxHeight: 360, overflow: 'auto' }}>
                            {skills.map(skill => (
                              <details
                                key={skill.id}
                                style={{
                                  border: `1px solid ${THEME.borderLight}`,
                                  borderRadius: 8,
                                  padding: 10,
                                  background: skill.is_builtin ? (THEME.primaryAlpha?.(0.04) || 'rgba(22,119,255,0.04)') : THEME.bgCard,
                                }}
                              >
                                <summary style={{ cursor: 'pointer', color: THEME.textPrimary }}>
                                  <Space wrap>
                                    <Text strong>{skill.name}</Text>
                                    <Tag>{skill.skill_type}</Tag>
                                    {skill.is_builtin && <Tag color="blue">内置</Tag>}
                                    <Tag>使用 {skill.usage_count}</Tag>
                                  </Space>
                                </summary>
                                <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                                  {skill.description}
                                </Text>
                                {skill.content && (
                                  <pre
                                    style={{
                                      margin: '8px 0 0',
                                      padding: 10,
                                      borderRadius: 8,
                                      background: THEME.bgPage,
                                      color: THEME.textPrimary,
                                      border: `1px solid ${THEME.borderLight}`,
                                      whiteSpace: 'pre-wrap',
                                      fontSize: 12,
                                      lineHeight: 1.7,
                                    }}
                                  >
                                    {skill.content}
                                  </pre>
                                )}
                              </details>
                            ))}
                          </div>
                        )}
                      </div>
                    </Space>
                  ),
                },
                {
                  key: 'context',
                  label: 'Default Context',
                  forceRender: true,
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Alert
                        type="info"
                        showIcon
                        message="默认项目 / 工作流 / Skill"
                        description="结构化绑定会自动注入每次 run；下面的 JSON 仍可补充章节号、默认参数等自由上下文。"
                      />
                      <Form.Item
                        name="default_project_id"
                        label="默认创作项目 ID"
                        tooltip="启动该智能体时，如果请求没有指定 project_id，会自动使用这个项目并构建项目上下文包。"
                      >
                        <Input placeholder="例如 creative_project_id / project_id" />
                      </Form.Item>
                      <Form.Item name="default_workflow" label="默认工作流">
                        <Select
                          allowClear
                          showSearch
                          options={DEFAULT_WORKFLOW_OPTIONS}
                          placeholder="选择或输入工作流标识"
                          optionFilterProp="label"
                        />
                      </Form.Item>
                      <Form.Item
                        name="default_skill_ids"
                        label="默认 Skill IDs"
                        tooltip="用于声明该智能体默认采用的能力模板；当前先作为运行上下文注入。"
                      >
                        <Select
                          mode="tags"
                          allowClear
                          showSearch
                          options={skillOptions}
                          placeholder="例如 novel_completion / character_visual_card / reference_match"
                          optionFilterProp="label"
                        />
                      </Form.Item>
                      <Form.Item
                        name="default_context"
                        label="默认上下文 JSON"
                        tooltip="必须是合法 JSON 对象。"
                      >
                        <TextArea rows={14} placeholder='{"project_id":"...","chapter_number":1}' />
                      </Form.Item>
                    </Space>
                  ),
                },
              ]}
            />
          </Form>
        ) : (
          <Alert
            type="warning"
            showIcon
            message="暂无可编辑智能体"
            description="请先刷新配置。如果仍为空，需要重启后端或创建 agent_profiles 表。"
          />
        )}
      </Drawer>
    </div>
  )
}

export default function AgentPage() {
  return (
    <AgentPageErrorBoundary>
      <AgentPageContent />
    </AgentPageErrorBoundary>
  )
}
