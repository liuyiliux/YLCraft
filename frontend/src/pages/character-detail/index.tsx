import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Alert, Avatar, Button, Card, Checkbox, Col, Dropdown, Empty, Image, Input, InputNumber, Modal, Popconfirm, Popover, Row, Segmented, Select, Space, Spin, Tabs, Tag, Typography, message } from 'antd'
import type { MenuProps } from 'antd'
import { ArrowLeftOutlined, ArrowRightOutlined, BranchesOutlined, CopyOutlined, DatabaseOutlined, DeleteOutlined, DownOutlined, EditOutlined, EllipsisOutlined, FullscreenExitOutlined, FullscreenOutlined, GlobalOutlined, PictureOutlined, PlusOutlined, PushpinOutlined, SearchOutlined, SettingOutlined, StarFilled, StarOutlined, UpOutlined, UserOutlined } from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { useFullscreenWorkspace } from '../../components/layout/AppLayout'
import { chat } from '../../api'
import FieldRenderer from './components/FieldRenderer'
import { browserAssetUrl, displayValue, fieldSourceMeta, mapSourceValues } from './components/utils'
import { visualProfileFieldLabel } from './components/visualProfileSchema'
import './styles.css'

const { Title, Text, Paragraph } = Typography

type Character = Record<string, any>

const ROLE_OPTIONS = [
  { value: 'protagonist', label: '主角' },
  { value: 'antagonist', label: '反派' },
  { value: 'supporting', label: '配角' },
  { value: 'extra', label: '路人' },
]
const SOURCE_OPTIONS = [
  { value: 'ai_generated', label: 'AI生成' },
  { value: 'local_material', label: '本地素材' },
  { value: 'real_person', label: '真人对白' },
  { value: 'anime_reference', label: '动漫原型' },
  { value: 'stock_footage', label: '库存人物' },
  { value: 'other', label: '其他' },
]
const WORKFLOW_SOURCE_OPTIONS = [
  { value: 'extract', label: '小说/正文提取' },
  { value: 'character_first', label: '角色先行' },
  { value: 'asset_import', label: '素材库导入' },
  { value: 'unknown', label: '未标记' },
]
const EXTRACT_ORIGIN_OPTIONS = [
  { value: 'uploaded_novel', label: '上传小说提取' },
  { value: 'imported_novel', label: '外来小说导入' },
  { value: 'original_outline', label: '原创大纲（AI 推断）' },
  { value: 'unknown', label: '未标记' },
]

/** 视觉素材分类：一个角色的设定图按语义拆成这几类，用于视图矩阵横向填满 */
type VisualAssetKind = 'turnaround' | 'expression' | 'pose' | 'item'
type VisualAsset = {
  id: string
  url: string
  label: string
  kind: VisualAssetKind
  versionId?: string
  versionNumber?: number
  worldScoped?: boolean
  fromSlice?: boolean
}
const VISUAL_ASSET_GROUPS: { key: VisualAssetKind; label: string }[] = [
  { key: 'turnaround', label: '三视图' },
  { key: 'item', label: '道具' },
  { key: 'expression', label: '表情' },
  { key: 'pose', label: '姿态' },
]
/** 把标签类字段规整成字符串数组，兼容数组与逗号分隔字符串两种存储形态 */
const toTagList = (raw: unknown): string[] => {
  if (Array.isArray(raw)) return raw.map((item) => String(item ?? '').trim()).filter(Boolean)
  if (typeof raw === 'string') return raw.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
  return []
}
/** 从立绘预设反推素材分类；无法归类的（主立绘、头像等）不进视图矩阵 */
const inferAssetKind = (preset: string): VisualAssetKind | null => {
  const value = String(preset || '').toLowerCase()
  if (value.includes('multi_view') || value.includes('turnaround')) return 'turnaround'
  if (value.includes('item')) return 'item'
  if (value.includes('expression')) return 'expression'
  if (value.includes('pose') || value.includes('action')) return 'pose'
  return null
}

export function CharacterWorkspaceEntry() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    getJson('/api/v1/characters?limit=1').then((res) => {
      const items = res.data?.items || res.items || res.data || []
      if (items[0]?.id) navigate(`/characters/${items[0].id}`, { replace: true })
      else navigate('/characters/new', { replace: true })
    }).catch(() => navigate('/characters/new', { replace: true })).finally(() => setLoading(false))
  }, [navigate])
  return <div style={{ minHeight: '70vh', display: 'grid', placeItems: 'center' }}>{loading ? <Spin size="large" /> : null}</div>
}

/**
 * 发起 JSON 请求。signal 可选，用于切换角色时取消上一轮未完成的请求，
 * 避免旧响应后到覆盖新数据（快速连续切换角色时会出现数据错乱）。
 */
const getJson = async (url: string, options?: { signal?: AbortSignal }) => {
  const response = await fetch(url, { headers: { Accept: 'application/json' }, signal: options?.signal })
  if (!response.ok) throw new Error(`请求失败：${response.status}`)
  return response.json()
}

const EXTRACT_ORIGIN_LABELS: Record<string, string> = {
  uploaded_novel: '上传小说提取',
  imported_novel: '外来小说导入',
  original_outline: '原创大纲（AI 推断）',
  unknown: '未标记',
}

function extractOriginLabel(origin: unknown): string {
  return EXTRACT_ORIGIN_LABELS[String(origin || '').trim()] || '未标记'
}

/** field_sources 的字段名 → 中文标签 */
const FIELD_SOURCE_LABELS: Record<string, string> = {
  name: '名称',
  role: '角色定位',
  workflow_source: '流程来源',
  source_types: '来源类型',
  appearance: '外观',
  personality: '性格',
  costume_hint: '服装提示',
  signature_items: '标志物',
  expressions: '表情',
  poses: '姿态',
  visual_consistency: '视觉一致性',
  background: '背景故事',
  age_range: '年龄范围',
  identity: '身份设定',
  motivation: '动机心理',
  speech: '语言语态',
  behavior: '行为底线',
  ability: '能力设定',
  arc: '人物弧光',
  tags: '自定义标签',
  portrait_url: '立绘图片',
  logline: '身份',
  position: '身份',
  visual_profile: '视觉档案',
}

function fieldSourceLabel(field: unknown): string {
  const key = String(field || '').trim()
  return FIELD_SOURCE_LABELS[key] || key
}



/**
 * 世界切换条：角色是全局基准设定，但在不同创作项目/世界中可以有别名、阵营、服装、
 * OOC/出模约束和 Bible/视觉覆盖。切换后工作区展示的是「基准 + 该世界覆盖」的有效设定。
 */
function WorldSwitcher({
  worlds,
  activeId,
  onChange,
  theme,
}: {
  worlds: any[]
  activeId: string
  onChange: (value: string) => void
  theme: any
}) {
  if (!worlds.length) return null
  const tabs: { key: string; label: string; title: string }[] = [
    { key: '', label: '基准设定', title: '角色库中的全局设定，不含任何世界覆盖' },
    ...worlds.map((item: any) => ({
      key: String(item.id),
      label: String(item.world_name || item.project_title || '未命名世界').slice(0, 12),
      title: [item.world_name || item.project_title, item.local_alias, item.usage_role].filter(Boolean).join(' · '),
    })),
  ]
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 12 }}>
      <Space size={6}>
        <GlobalOutlined style={{ color: theme.textSecondary }} />
        <Text style={{ color: theme.textSecondary, fontSize: 12 }}>世界视角</Text>
      </Space>
      {tabs.map((tab) => {
        const selected = String(activeId) === tab.key
        return (
          <button
            key={tab.key || '__base__'}
            type="button"
            title={tab.title}
            onClick={() => onChange(tab.key)}
            style={{
              border: `1px solid ${selected ? theme.primary : theme.borderLight}`,
              background: selected ? theme.primaryAlpha(0.14) : 'transparent',
              color: selected ? theme.primary : theme.textSecondary,
              borderRadius: 999,
              padding: '3px 12px',
              fontSize: 12,
              cursor: 'pointer',
              maxWidth: 190,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}

/**
 * 覆盖差异卡：切换世界后，明确列出该世界改写了哪些设定，避免「为什么和我填的不一样」。
 */
function WorldOverrideNotice({ world, theme }: { world: any; theme: any }) {
  if (!world) return null
  const rows: [string, any][] = [
    ['别名 / 代号', world.local_alias],
    ['阵营 / 派系', world.local_faction],
    ['本世界身份', world.local_identity],
    ['服装覆盖', world.local_costume],
    ['局部 Prompt 标签', Array.isArray(world.local_prompt_tags) ? world.local_prompt_tags : []],
    ['OOC 约束', world.ooc_notes],
    ['出模约束', world.off_model_notes],
  ]
  const overrideKeys = Object.keys(world.bible_overrides || {}).length
    ? Object.keys(world.bible_overrides)
    : []
  const visualKeys = Object.keys(world.visual_overrides || {})
  const hasAny = rows.some(([, value]) => displayValue(value).trim()) || overrideKeys.length > 0 || visualKeys.length > 0
  if (!hasAny) return null
  return (
    <div
      style={{
        border: `1px solid ${theme.borderLight}`,
        borderLeft: `3px solid ${theme.primary}`,
        borderRadius: 8,
        background: theme.bgElevated,
        padding: '10px 12px',
        marginBottom: 12,
      }}
    >
      <Space size={6} wrap>
        <Text strong style={{ color: theme.textPrimary, fontSize: 13 }}>
          {world.world_name || world.project_title || '未命名世界'}
        </Text>
        {world.usage_role ? <Tag color="cyan" style={{ marginInlineEnd: 0 }}>{world.usage_role}</Tag> : null}
        {world.local_status ? <Tag color={world.local_status === 'active' ? 'green' : 'default'} style={{ marginInlineEnd: 0 }}>{world.local_status}</Tag> : null}
      </Space>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '6px 18px', marginTop: 8 }}>
        {rows
          .filter(([, value]) => displayValue(value).trim())
          .map(([label, value]) => (
            <div key={label}>
              <Text style={{ color: theme.textSecondary, fontSize: 11 }}>{label}</Text>
              <Paragraph style={{ color: theme.textPrimary, margin: '2px 0 0', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {displayValue(value)}
              </Paragraph>
            </div>
          ))}
      </div>
      {overrideKeys.length > 0 ? (
        <Text style={{ color: theme.textSecondary, fontSize: 11, display: 'block', marginTop: 6 }}>
          Bible 覆盖字段：{overrideKeys.join('、')}
        </Text>
      ) : null}
      {visualKeys.length > 0 ? (
        <Text style={{ color: theme.textSecondary, fontSize: 11, display: 'block', marginTop: 2 }}>
          视觉覆盖字段：{visualKeys.join('、')}
        </Text>
      ) : null}
    </div>
  )
}

function RelationshipGraph({ graph, theme, onOpen }: { graph: any; theme: any; onOpen: (id: string) => void }) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []
  if (!nodes.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无角色关系图谱" />
  const width = 760
  const height = 340
  const center = { x: width / 2, y: height / 2 }
  const radius = Math.max(90, Math.min(145, nodes.length * 16))
  const positions = new Map<string, { x: number; y: number }>(nodes.map((node: any, index: number) => {
    const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2
    return [String(node.id), { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius }] as [string, { x: number; y: number }]
  }))
  return <div style={{ overflowX: 'auto', background: theme.bgElevated, border: `1px solid ${theme.borderLight}`, borderRadius: 8 }}><svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', minWidth: 600, display: 'block' }}>{edges.map((edge: any, index: number) => { const a = positions.get(String(edge.character_id)); const b = positions.get(String(edge.related_character_id)); if (!a || !b) return null; return <g key={edge.id || index}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={theme.primary} strokeOpacity=".42" strokeWidth="2" /><text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6} textAnchor="middle" fontSize="11" fill={theme.textSecondary}>{edge.relation_type || '关系'}</text></g> })}{nodes.map((node: any) => { const point = positions.get(String(node.id)); if (!point) return null; const selected = String(node.id) === String(graph?.focus_id || ''); return <g key={node.id} onClick={() => onOpen(String(node.id))} style={{ cursor: 'pointer' }}><circle cx={point.x} cy={point.y} r="29" fill={selected ? theme.primaryAlpha(0.22) : theme.bgCard} stroke={selected ? theme.primary : node.role === 'protagonist' ? '#f59e0b' : theme.borderLight} strokeWidth="3" /><text x={point.x} y={point.y + 4} textAnchor="middle" fontSize="12" fill={theme.textPrimary}>{String(node.name || '角色').slice(0, 7)}</text></g> })}</svg><div style={{ padding: '8px 12px', color: theme.textSecondary, fontSize: 12 }}>共 {nodes.length} 个角色 · {edges.length} 条关系，点击节点切换角色</div></div>
}

export default function CharacterDetailPage() {
  const { characterId } = useParams()
  const navigate = useNavigate()
  const { theme } = useTheme()
  const [character, setCharacter] = useState<Character | null>(null)
  const [pack, setPack] = useState<any>(null)
  const [relationships, setRelationships] = useState<any[]>([])
  const [relationshipGraph, setRelationshipGraph] = useState<any>({ nodes: [], edges: [] })
  const [worldUsages, setWorldUsages] = useState<any[]>([])
  const [characterTimeline, setCharacterTimeline] = useState<any>(null)
  const [portraitVersions, setPortraitVersions] = useState<any[]>([])
  const [selectedVersionId, setSelectedVersionId] = useState('')
  const [portraitSlices, setPortraitSlices] = useState<any[]>([])
  const [portraitLogs, setPortraitLogs] = useState<any[]>([])
  const [selectedVisualUrl, setSelectedVisualUrl] = useState('')
  const [editOpen, setEditOpen] = useState(false)
  const [editMode, setEditMode] = useState<'create' | 'edit'>('edit')
  const [editSaving, setEditSaving] = useState(false)
  const [editForm, setEditForm] = useState<Record<string, any>>({})
  const [referenceOpen, setReferenceOpen] = useState(false)
  const [referenceAssets, setReferenceAssets] = useState<any[]>([])
  const [referenceLoading, setReferenceLoading] = useState(false)
  const [referenceSearch, setReferenceSearch] = useState('')
  const [worldModalOpen, setWorldModalOpen] = useState(false)
  const [editingWorld, setEditingWorld] = useState<any | null>(null)
  const [worldSaving, setWorldSaving] = useState(false)
  const [worldForm, setWorldForm] = useState({ story_id: '', world_name: '', usage_role: '', local_alias: '', local_identity: '', local_faction: '', local_status: 'active', local_costume: '', local_prompt_tags: '', ooc_notes: '', off_model_notes: '', bible_overrides: '{}', visual_overrides: '{}' })
  // 世界视觉覆盖的便捷输入字段（自动序列化到 visual_overrides JSON）
  const [worldVisualPortraitUrl, setWorldVisualPortraitUrl] = useState('')
  const [worldVisualRefUrls, setWorldVisualRefUrls] = useState('')
  const [projects, setProjects] = useState<any[]>([])
  const [aiBusy, setAiBusy] = useState(false)
  const [relationModalOpen, setRelationModalOpen] = useState(false)
  const [editingRelation, setEditingRelation] = useState<any | null>(null)
  const [relationSaving, setRelationSaving] = useState(false)
  const [relationForm, setRelationForm] = useState<{
    related_character_id: string
    relation_type: string
    relation_note: string
    is_directed: boolean
    world_usage_id: string | null
    timeline_phase: string
    chapter_number: number | null
  }>({ related_character_id: '', relation_type: '', relation_note: '', is_directed: false, world_usage_id: null, timeline_phase: '', chapter_number: null })
  const [sliceModalOpen, setSliceModalOpen] = useState(false)
  const [sliceVersionId, setSliceVersionId] = useState('')
  const [sliceRows, setSliceRows] = useState(3)
  const [sliceCols, setSliceCols] = useState(3)
  const [sliceBusy, setSliceBusy] = useState(false)
  const [portraitPreset, setPortraitPreset] = useState('main_portrait')
  const [portraitSize, setPortraitSize] = useState('1024x1024')
  const [portraitPrompt, setPortraitPrompt] = useState('')
  const [portraitNegativePrompt, setPortraitNegativePrompt] = useState('')
  const [promptPreview, setPromptPreview] = useState<any>(null)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [versionDetailVersion, setVersionDetailVersion] = useState<any>(null)
  const [promptPreviewOpen, setPromptPreviewOpen] = useState(false)
  const [promptPreviewLoading, setPromptPreviewLoading] = useState(false)
  const [promptOptimizing, setPromptOptimizing] = useState(false)
  const [imageBackends, setImageBackends] = useState<any[]>([])
  const [llmBackends, setLlmBackends] = useState<any[]>([])
  const [enrichProvider, setEnrichProvider] = useState('')
  const [enrichModel, setEnrichModel] = useState('')
  const [portraitProvider, setPortraitProvider] = useState('')
  const [portraitModel, setPortraitModel] = useState('')
  // 文生图不携带参考图（走 /images/generations），图生图携带勾选的参考图（走 /images/edits）
  const [portraitMode, setPortraitMode] = useState<'text2img' | 'img2img'>('img2img')
  const [portraitControlsCollapsed, setPortraitControlsCollapsed] = useState(true)
  const [portraitVersionsCollapsed, setPortraitVersionsCollapsed] = useState(true)
  const [selectedReferenceUrls, setSelectedReferenceUrls] = useState<string[]>([])
  const seenReferenceUrls = useRef<Set<string>>(new Set())
  const [characters, setCharacters] = useState<Character[]>([])
  const [characterKeyword, setCharacterKeyword] = useState('')
  const [characterRole, setCharacterRole] = useState<string>()
  const [characterSource, setCharacterSource] = useState<string>()
  const [characterWorkflowSource, setCharacterWorkflowSource] = useState<string>()
  const [characterExtractOrigin, setCharacterExtractOrigin] = useState<string>()
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [tagInput, setTagInput] = useState('')
  const [activeWorldId, setActiveWorldId] = useState('')
  // 关系列表独立的世界筛选器（与角色设定世界视角分开）
  const [relationWorldFilter, setRelationWorldFilter] = useState<string>('__all__')
  const { fullscreen: workspaceFullscreen, toggleFullscreen: toggleWorkspaceFullscreen } = useFullscreenWorkspace()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!characterId) return
    if (characterId === 'new') {
      const draft = { id: '__new__', name: '', role: 'supporting', workflow_source: 'character_first', source_types: ['ai_generated'], appearance: '', personality: '', costume_hint: '', background: '', age_range: '', visual_consistency: '', signature_items: [], expressions: [], poses: [], tags: [], identity: {}, motivation: {}, speech: {}, behavior: {}, ability: {}, arc: {}, field_sources: {}, portrait_url: '', portrait_node_id: null, is_favorite: false }
      setCharacter(draft)
      setCharacters([])
      setPack(null)
      setRelationships([])
      setRelationshipGraph({ nodes: [], edges: [], focus_id: '' })
      setWorldUsages([])
      setPortraitVersions([])
      setPortraitSlices([])
      setPortraitLogs([])
      setLoading(false)
      setEditMode('create')
      setEditForm({ name: '', role: 'supporting', workflow_source: 'character_first', source_types: 'ai_generated', appearance: '', costume_hint: '', personality: '', background: '', age_range: '', visual_consistency: '', signature_items: '', expressions: '', poses: '', tags: '', identity: '{}', motivation: '{}', speech: '{}', behavior: '{}', ability: '{}', arc: '{}', voice: '{}', voice_asset_id: '', visual_profile: '{}' })
      setEditOpen(true)
      return
    }
    const controller = new AbortController()
    const { signal } = controller
    setLoading(true)
    Promise.all([
      getJson(`/api/v1/characters/${characterId}`, { signal }),
      getJson(`/api/v1/characters/${characterId}/prompt-pack`, { signal }),
      getJson(`/api/v1/characters/${characterId}/relationships`, { signal }),
      getJson('/api/v1/characters/relationships/graph', { signal }),
      getJson('/api/v1/characters?limit=100', { signal }),
      getJson(`/api/v1/characters/${characterId}/world-usages`, { signal }),
      getJson(`/api/v1/characters/${characterId}/portrait/versions`, { signal }),
      getJson(`/api/v1/characters/${characterId}/portrait/slices`, { signal }),
      getJson(`/api/v1/logs?task_type=character_portrait&ref_id=${characterId}&limit=50`, { signal }),
      getJson(`/api/v1/characters/${characterId}/state-timeline`, { signal }),
      getJson('/api/v1/creative-projects?limit=200', { signal }),
    ]).then(([characterRes, packRes, relationRes, graphRes, charactersRes, worldsRes, versionsRes, slicesRes, logsRes, timelineRes, projectsRes]) => {
      setCharacter(characterRes.data || characterRes)
      setPack(packRes.data || packRes)
      setRelationships(relationRes.data || [])
      setRelationshipGraph({ ...(graphRes.data || graphRes), focus_id: characterId })
      setCharacters(charactersRes.data?.items || charactersRes.items || charactersRes.data || [])
      const loadedWorldUsages = worldsRes.data || worldsRes.items || []
      setWorldUsages(loadedWorldUsages)
      setActiveWorldId((current) => current && loadedWorldUsages.some((item: any) => String(item.id) === String(current)) ? current : '')
      setPortraitVersions(versionsRes.data?.versions || [])
      setPortraitSlices(slicesRes.data?.items || [])
      setPortraitLogs(logsRes.data || logsRes.items || [])
      setCharacterTimeline(timelineRes.data || null)
      setProjects(projectsRes.data || projectsRes.items || [])
      const loadedCharacter = characterRes.data || characterRes
      const loadedProfile = loadedCharacter?.identity?.visual_profile || {}
      setSelectedVisualUrl(loadedProfile.identity_reference_url || loadedCharacter?.portrait_url || '')
      const mainVersionId = loadedProfile.identity_reference_version_id
      const mainVersion = (versionsRes.data?.versions || []).find((item: any) => String(item.id) === String(mainVersionId) || item.is_main)
      if (mainVersion) setSelectedVersionId(String(mainVersion.id))
    }).catch((e) => {
      // 主动取消（切换角色）不算失败，静默忽略，由新一轮请求负责设置状态
      if (e?.name === 'AbortError') return
      setError(e.message || '角色加载失败')
    }).finally(() => {
      if (!signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [characterId])
  useEffect(() => {
    if (!workspaceFullscreen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') toggleWorkspaceFullscreen()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [workspaceFullscreen, toggleWorkspaceFullscreen])
  useEffect(() => {
    getJson('/api/v1/images/backends').then((result) => {
      const items = result.backends || result.data || []
      setImageBackends(items)
      if (!portraitProvider && items[0]) {
        setPortraitProvider(items[0].name || items[0].provider || '')
        setPortraitModel(items[0].model || items[0].available_models?.[0] || '')
      }
    }).catch(() => setImageBackends([]))
  }, [portraitProvider])
  useEffect(() => {
    getJson('/api/v1/ai/connectors?provider_type=llm&active_only=true').then((result) => {
      const items = result.connectors || result.data || result.items || []
      setLlmBackends(items)
      if (!enrichProvider && items[0]) {
        setEnrichProvider(items[0].name || items[0].provider || '')
        setEnrichModel(items[0].default_model || items[0].model || items[0].available_models?.[0] || '')
      }
    }).catch(() => setLlmBackends([]))
  }, [enrichProvider])

  // 按生图模式过滤供应商：图生图只显示 image_to_image 能力，文生图只显示 text_to_image
  const portraitBackendOptions = useMemo(() => {
    const wanted = portraitMode === 'img2img' ? 'image_to_image' : 'text_to_image'
    return imageBackends.filter((item: any) => {
      const caps: string[] = Array.isArray(item?.capabilities) ? item.capabilities : []
      return !caps.length || caps.includes(wanted)
    })
  }, [imageBackends, portraitMode])

  // 切换模式后当前供应商若不支持新模式，自动落到第一个可用供应商
  useEffect(() => {
    if (!portraitBackendOptions.length) return
    const matched = portraitBackendOptions.some((item: any) => (item.name || item.provider) === portraitProvider)
    if (matched) return
    const first: any = portraitBackendOptions[0]
    setPortraitProvider(first.name || first.provider || '')
    setPortraitModel(first.model || first.available_models?.[0] || '')
  }, [portraitBackendOptions, portraitProvider])

  const canonicalMainVisualUrl = useMemo(() => {
    const profile = character?.identity?.visual_profile || {}
    return browserAssetUrl(profile.identity_reference_url || character?.portrait_url || '')
  }, [character])

  const portraitSizeOptions = useMemo(() => {
    const backend = imageBackends.find((item) => (item.name || item.provider) === portraitProvider)
    const configured = Array.isArray(backend?.supported_sizes)
      ? backend.supported_sizes.filter((value: any) => typeof value === 'string' && value.trim())
      : []
    const fallback = ['1024x1024', '1024x1536', '1536x1024', '1152x896', '896x1152']
    return Array.from(new Set(configured.length ? configured : fallback))
  }, [imageBackends, portraitProvider])

  useEffect(() => {
    if (portraitSizeOptions.length && !portraitSizeOptions.includes(portraitSize)) {
      setPortraitSize(String(portraitSizeOptions[0]))
    }
  }, [portraitSizeOptions, portraitSize])

  // ---- 世界切换：同一角色在不同项目/世界下的差异化设定 ----
  const activeWorld = useMemo(
    () => worldUsages.find((item: any) => String(item.id) === String(activeWorldId)) || null,
    [worldUsages, activeWorldId],
  )

  /**
   * 当前世界视角下的主视图URL
   * 如果当前世界有 visual_overrides.identity_reference_url，优先使用世界专属立绘
   */
  const worldScopedMainUrl = useMemo(() => {
    if (!activeWorld) return ''
    const worldVisual = activeWorld.visual_overrides || {}
    return browserAssetUrl(worldVisual.identity_reference_url || worldVisual.portrait_url || '')
  }, [activeWorld])

  /**
   * 当前世界视角下的参考图集合
   */
  const worldScopedReferences = useMemo(() => {
    if (!activeWorld) return []
    const worldVisual = activeWorld.visual_overrides || {}
    const urls = Array.isArray(worldVisual.reference_image_urls) ? worldVisual.reference_image_urls : []
    return Array.from(new Set(urls.map((url: any) => browserAssetUrl(url)).filter(Boolean)))
  }, [activeWorld])

  // 最终显示的主视图：手动选择预览 > 世界专属 > 全局基准
  const effectiveMainUrl = worldScopedMainUrl || canonicalMainVisualUrl
  const mainVisualUrl = selectedVisualUrl || effectiveMainUrl
  const isPreviewVisual = Boolean(selectedVisualUrl && effectiveMainUrl && selectedVisualUrl !== effectiveMainUrl)
  const isWorldScopedVisual = Boolean(worldScopedMainUrl && !selectedVisualUrl)
  const selectedVersion = portraitVersions.find((version: any) => String(version.id) === String(selectedVersionId))

  const referenceImages = useMemo(() => {
    if (!character) return []
    const profile = character.identity?.visual_profile || {}
    const main = browserAssetUrl(profile.identity_reference_url || character.portrait_url || '')
    const globalRefs = Array.from(new Set((profile.reference_image_urls || []).map((url: any) => browserAssetUrl(url)).filter((url: string) => Boolean(url) && url !== main)))
    // 世界视角下合并：世界专属参考图 + 全局参考图（去重）
    if (activeWorld) {
      const worldMain = worldScopedMainUrl || main
      return Array.from(new Set([...worldScopedReferences, ...globalRefs].filter((url: string) => Boolean(url) && url !== worldMain)))
    }
    return globalRefs
  }, [character, activeWorld, worldScopedReferences, worldScopedMainUrl])
  const visualImages = useMemo(() => Array.from(new Set<string>([mainVisualUrl, ...referenceImages].filter((item: unknown): item is string => typeof item === 'string' && Boolean(item)))), [mainVisualUrl, referenceImages])

  // 参考图默认全选；用户取消过的不会因列表刷新被重新选中，新加入的图自动补为选中
  useEffect(() => {
    setSelectedReferenceUrls((prev) => {
      const kept = prev.filter((url) => visualImages.includes(url))
      const added = visualImages.filter((url) => !seenReferenceUrls.current.has(url))
      visualImages.forEach((url) => seenReferenceUrls.current.add(url))
      return added.length ? [...kept, ...added] : kept
    })
  }, [visualImages])

  const toggleReferenceUrl = (url: string) => {
    setSelectedReferenceUrls((prev) => (prev.includes(url) ? prev.filter((item) => item !== url) : [...prev, url]))
  }
  const mergeOverride = (base: any, overrides: any) => {
    if (!overrides || typeof overrides !== 'object') return base
    if (!base || typeof base !== 'object') return { ...overrides }
    return { ...base, ...overrides }
  }
  const effectiveIdentity = useMemo(() => mergeOverride(character?.identity || {}, activeWorld?.bible_overrides?.identity || activeWorld?.bible_overrides), [character, activeWorld])
  const effectiveMotivation = useMemo(() => mergeOverride(character?.motivation || {}, activeWorld?.bible_overrides?.motivation), [character, activeWorld])
  const effectiveSpeech = useMemo(() => mergeOverride(character?.speech || {}, activeWorld?.bible_overrides?.speech), [character, activeWorld])
  const effectiveBehavior = useMemo(() => mergeOverride(character?.behavior || {}, activeWorld?.bible_overrides?.behavior), [character, activeWorld])
  const effectiveAbility = useMemo(() => mergeOverride(character?.ability || {}, activeWorld?.bible_overrides?.ability), [character, activeWorld])
  const effectiveArc = useMemo(() => mergeOverride(character?.arc || {}, activeWorld?.bible_overrides?.arc), [character, activeWorld])
  const effectiveCostume = activeWorld?.local_costume || character?.costume_hint || ''
  // 剧情演变：角色状态随章节累积变化（数据来自 ProjectStateEntry，由正文 AI 提取写入）
  const [timelineProjectId, setTimelineProjectId] = useState<string>('')
  const timelineChapters = useMemo(() => (characterTimeline?.timeline || []).filter((node: any) => (node.entries || []).length > 0), [characterTimeline])
  const formatStateValue = (value: any) => {
    if (value === null || value === undefined) return '—'
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
  }
  // 加载剧情演变（按项目筛选）
  useEffect(() => {
    if (!character?.id) return
    const controller = new AbortController()
    getJson(`/api/v1/characters/${character.id}/state-timeline${timelineProjectId ? `?project_id=${timelineProjectId}` : ''}`, { signal: controller.signal })
      .then((res) => setCharacterTimeline(res.data || null))
      .catch(() => {})
    return () => controller.abort()
  }, [character?.id, timelineProjectId])
  // memo 化以保持引用稳定，否则每次渲染都是新对象，会让下游素材分组的 memo 全部失效
  const effectiveVisualOverrides = useMemo(() => activeWorld?.visual_overrides || {}, [activeWorld])

  /**
   * 视觉素材池：把切片（已拆好的独立格）与未切片的设定板版本聚合为分类素材。
   * 切片优先——同一版本既出现在切片里又作为整张 sheet 时只用切片，避免重复展示。
   */
  const visualAssets = useMemo(() => {
    const assets: VisualAsset[] = []
    portraitSlices.forEach((slice: any) => {
      const gridType = String(slice.grid_type || '')
      const kind = (['turnaround', 'expression', 'pose'].includes(gridType)
        ? gridType
        : inferAssetKind(slice.source_preset)) as VisualAssetKind | null
      if (!kind) return
      const url = browserAssetUrl(slice.image_url || slice.file_path || '')
      if (!url) return
      assets.push({ id: `slice-${slice.node_id}`, url, label: String(slice.label || ''), kind, versionId: String(slice.source_version_id || ''), fromSlice: true })
    })
    const slicedVersionIds = new Set(portraitSlices.map((slice: any) => String(slice.source_version_id || '')))
    portraitVersions.forEach((version: any) => {
      const kind = inferAssetKind(version.preset)
      if (!kind) return
      if (slicedVersionIds.has(String(version.id))) return
      const url = browserAssetUrl(version.image_url || '')
      if (!url) return
      assets.push({ id: `version-${version.id}`, url, label: '', kind, versionId: String(version.id), versionNumber: version.version_number, fromSlice: false })
    })
    return assets
  }, [portraitSlices, portraitVersions])

  /**
   * 按分类分组后的素材。世界专属素材（visual_overrides.turnaround_urls / item_urls）排在最前，
   * 无专属时则沿用全局基准素材，由 hasWorldScoped 控制「沿用基准」标注。
   */
  const visualAssetGroups = useMemo(() => {
    const worldScopedUrls: Partial<Record<VisualAssetKind, any[]>> = {
      turnaround: Array.isArray(effectiveVisualOverrides.turnaround_urls) ? effectiveVisualOverrides.turnaround_urls : [],
      item: Array.isArray(effectiveVisualOverrides.item_urls) ? effectiveVisualOverrides.item_urls : [],
    }
    return VISUAL_ASSET_GROUPS.map((group) => {
      const worldItems: VisualAsset[] = (worldScopedUrls[group.key] || [])
        .map((raw: string, index: number) => browserAssetUrl(raw))
        .filter(Boolean)
        .map((url: string, index: number) => ({ id: `world-${group.key}-${index}`, url, label: group.label, kind: group.key, worldScoped: true, fromSlice: false }))
      const baseItems = visualAssets.filter((asset) => asset.kind === group.key)
      return { ...group, items: [...worldItems, ...baseItems], hasWorldScoped: worldItems.length > 0 }
    }).filter((group) => group.items.length > 0)
  }, [visualAssets, effectiveVisualOverrides])

  const signatureItems = useMemo(() => toTagList(character?.signature_items), [character])
  const characterTags = useMemo(() => toTagList(character?.tags), [character])

  /**
   * 恢复主视图：手动选择预览时恢复到当前视角主图（世界专属或全局基准）
   */
  const restoreMainVisual = () => {
    setSelectedVisualUrl('')
    setSelectedVersionId('')
  }

  const filteredCharacters = useMemo(() => characters.filter((item) => {
    const keywordMatch = !characterKeyword.trim() || String(item.name || '').toLowerCase().includes(characterKeyword.trim().toLowerCase())
    const roleMatch = !characterRole || item.role === characterRole
    const sourceMatch = !characterSource || (item.source_types || []).includes(characterSource)
    const workflowMatch = !characterWorkflowSource || (item.workflow_source || 'unknown') === characterWorkflowSource
    const origins: string[] = Array.isArray(item.extract_origins) ? item.extract_origins : []
    const originMatch = !characterExtractOrigin || origins.includes(characterExtractOrigin)
    const favoriteMatch = !favoritesOnly || Boolean(item.is_favorite)
    return keywordMatch && roleMatch && sourceMatch && workflowMatch && originMatch && favoriteMatch
  }), [characters, characterKeyword, characterRole, characterSource, characterWorkflowSource, characterExtractOrigin, favoritesOnly])

  // 上下方向键在角色间快速切换。输入框内与弹层打开时不拦截，避免干扰编辑和下拉选择。
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
      if (document.body.classList.contains('ant-scrolling-effect')) return
      if (!character || filteredCharacters.length < 2) return
      const currentIndex = filteredCharacters.findIndex((item: any) => item.id === character.id)
      if (currentIndex < 0) return
      const nextIndex = event.key === 'ArrowDown' ? Math.min(currentIndex + 1, filteredCharacters.length - 1) : Math.max(currentIndex - 1, 0)
      if (nextIndex === currentIndex) return
      event.preventDefault()
      navigate(`/characters/${filteredCharacters[nextIndex].id}`)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [filteredCharacters, character, navigate])

  if (loading) return <div style={{ minHeight: '70vh', display: 'grid', placeItems: 'center' }}><Spin size="large" /></div>
  // /characters/new 走新建模式：此时 character 尚未创建，不能按「角色不存在」拦截
  const isNewCharacter = characterId === 'new'
  if (error || (!character && !isNewCharacter)) return <div style={{ padding: 32 }}><Alert type="error" message={error || '角色不存在'} showIcon /><Button style={{ marginTop: 16 }} icon={<ArrowLeftOutlined />} onClick={() => navigate('/characters')}>返回角色库</Button></div>

  const identity = character?.identity || {}
  const motivation = character?.motivation || {}
  const speech = character?.speech || {}
  const behavior = character?.behavior || {}
  /**
   * 根据角色ID查找角色中文名
   * 优先使用后端返回的名称，否则从已加载的角色列表中查找
   */
  const getRelationTargetName = (item: any): string => {
    // 优先使用后端返回的名称
    if (item.related_character_name) return item.related_character_name
    // 从已加载的角色列表中查找
    const targetId = item.related_character_id || item.character_id
    if (targetId) {
      const found = characters.find((c: any) => String(c.id) === String(targetId))
      if (found?.name) return found.name
    }
    return String(targetId || '未知角色')
  }

  /**
   * 根据角色ID查找角色头像URL
   */
  const getRelationTargetAvatar = (item: any): string => {
    const targetId = item.related_character_id || item.character_id
    if (targetId) {
      const found = characters.find((c: any) => String(c.id) === String(targetId))
      if (found?.portrait_url) return browserAssetUrl(found.portrait_url)
    }
    return ''
  }
  const openEdit = () => {
    if (!character) return
    setEditForm({
      name: character.name || '', role: character.role || 'supporting', workflow_source: character.workflow_source || 'unknown', source_types: (character.source_types || []).join(', '),
      appearance: character.appearance || '', personality: character.personality || '', costume_hint: character.costume_hint || '',
      background: character.background || '', age_range: character.age_range || '', visual_consistency: character.visual_consistency || '',
      signature_items: (character.signature_items || []).join(', '), expressions: (character.expressions || []).join(', '), poses: (character.poses || []).join(', '),
      tags: (character.tags || []).join(', '), identity: JSON.stringify(character.identity || {}, null, 2), motivation: JSON.stringify(character.motivation || {}, null, 2),
      speech: JSON.stringify(character.speech || {}, null, 2), behavior: JSON.stringify(character.behavior || {}, null, 2), ability: JSON.stringify(character.ability || {}, null, 2), arc: JSON.stringify(character.arc || {}, null, 2), voice: JSON.stringify(character.voice || {}, null, 2), voice_asset_id: character.voice_asset_id || '', visual_profile: JSON.stringify(character.identity?.visual_profile || {}, null, 2),
    })
    setEditMode('edit')
    setEditOpen(true)
  }
  const openCreate = () => {
    setEditMode('create')
    setEditForm({ name: '', role: 'supporting', workflow_source: 'character_first', source_types: 'ai_generated', appearance: '', costume_hint: '', personality: '', background: '', age_range: '', visual_consistency: '', signature_items: '', expressions: '', poses: '', tags: '', identity: '{}', motivation: '{}', speech: '{}', behavior: '{}', ability: '{}', arc: '{}', voice: '{}', voice_asset_id: '' })
    setEditOpen(true)
  }
  const saveEdit = async () => {
    // 新建模式下 character 为空属正常，只有编辑已有角色才需要它
    if (editMode === 'edit' && !character) return
    setEditSaving(true)
    try {
      const parseJson = (value: string) => { try { return value?.trim() ? JSON.parse(value) : {} } catch { throw new Error('身份、动机等 JSON 字段格式不正确') } }
      const payload = {
        name: editForm.name, role: editForm.role, workflow_source: editForm.workflow_source || 'unknown', source_types: String(editForm.source_types || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), appearance: editForm.appearance, personality: editForm.personality, costume_hint: editForm.costume_hint, background: editForm.background, age_range: editForm.age_range, visual_consistency: editForm.visual_consistency, signature_items: String(editForm.signature_items || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), expressions: String(editForm.expressions || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), poses: String(editForm.poses || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), tags: String(editForm.tags || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), identity: { ...parseJson(editForm.identity), visual_profile: parseJson(editForm.visual_profile) }, motivation: parseJson(editForm.motivation), speech: parseJson(editForm.speech), behavior: parseJson(editForm.behavior), ability: parseJson(editForm.ability), arc: parseJson(editForm.arc), voice: parseJson(editForm.voice || '{}'), voice_asset_id: editForm.voice_asset_id || '',
      }
      const response = await fetch(editMode === 'edit' ? `/api/v1/characters/${character.id}` : '/api/v1/characters', { method: editMode === 'edit' ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(payload) })
      // 先读文本再解析，避免 response.json() 失败后二次读流报 body stream already read
      const text = await response.text()
      let result: any
      try { result = text ? JSON.parse(text) : {} } catch {
        throw new Error(`服务器错误 (${response.status})${text ? `: ${text.slice(0, 200)}` : ''}`)
      }
      if (!response.ok || result?.success === false) throw new Error(result?.detail || result?.message || `保存角色失败 (${response.status})`)
      const saved = result.data || result
      setCharacter(saved)
      setCharacters((items) => items.map((item) => item.id === saved?.id ? { ...item, ...saved } : item))
      setEditOpen(false)
      message.success(editMode === 'edit' ? '角色已保存' : '角色已创建')
      if (editMode === 'create' && saved?.id) navigate(`/characters/${saved.id}`, { replace: true })
    } catch (error: any) { message.error(error?.message || '保存角色失败') } finally { setEditSaving(false) }
  }
  const openReferencePicker = async () => {
    setReferenceOpen(true)
    await loadReferenceAssets(referenceSearch)
  }
  const loadReferenceAssets = async (search = '') => {
    setReferenceLoading(true)
    try {
      const query = new URLSearchParams({ asset_type: 'image', page: '1', page_size: '48' })
      if (search.trim()) query.set('search', search.trim())
      const result = await getJson(`/api/v1/assets?${query.toString()}`)
      setReferenceAssets(result.data || result.items || [])
    } catch { setReferenceAssets([]) } finally { setReferenceLoading(false) }
  }
  const addReferenceAsset = async (asset: any) => {
    const url = asset.thumbnail_url || asset.preview_url || asset.url || asset.file_url
    if (!url || !character) return
    const profile = character.identity?.visual_profile || {}
    const urls = Array.from(new Set([...(profile.reference_image_urls || []).map((item: any) => browserAssetUrl(item)), browserAssetUrl(url)]))
    const response = await fetch(`/api/v1/characters/${character.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ identity: { ...(character.identity || {}), visual_profile: { ...profile, reference_image_urls: urls } } }) })
    const result = await response.json()
    if (!response.ok || result?.success === false) { message.error(result?.detail || '添加参考图失败'); return }
    setCharacter(result.data || result)
    setReferenceOpen(false)
    message.success('参考图已加入角色')
  }
  const addReferenceVersion = async (version: any) => {
    const url = browserAssetUrl(version.image_url || version.url || version.file_path)
    if (!url || !character) return
    const profile = character.identity?.visual_profile || {}
    const urls = Array.from(new Set([...(profile.reference_image_urls || []).map((item: any) => browserAssetUrl(item)), browserAssetUrl(url)]))
    const response = await fetch(`/api/v1/characters/${character.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ identity: { ...(character.identity || {}), visual_profile: { ...profile, reference_image_urls: urls } } }) })
    const result = await response.json()
    if (!response.ok || result?.success === false) { message.error(result?.detail || '加入参考图失败'); return }
    setCharacter(result.data || result)
    message.success(`已加入参考图集合（共 ${urls.length} 张）`)
  }
  const removeReferenceImage = async (url: string) => {
    if (!character || !url) return
    const profile = character.identity?.visual_profile || {}
    const currentMain = profile.identity_reference_url || character.portrait_url || ''
    if (url === currentMain) { message.info('主视图请通过版本操作切换，不能从参考集合移除'); return }
    const urls = (profile.reference_image_urls || []).filter((item: any) => browserAssetUrl(item) !== browserAssetUrl(url))
    const response = await fetch(`/api/v1/characters/${character.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ identity: { ...(character.identity || {}), visual_profile: { ...profile, reference_image_urls: urls } } }) })
    const result = await response.json()
    if (!response.ok || result?.success === false) { message.error(result?.detail || '移除参考图失败'); return }
    setCharacter(result.data || result)
    message.success('已从参考图集合移除')
  }
  const setMainVersion = async (version: any) => {
    if (!character || !version?.id) return
    const url = browserAssetUrl(version.image_url || version.url || version.file_path || '')
    try {
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/versions/${version.id}/set-main`, { method: 'POST', headers: { Accept: 'application/json' } })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '设置主视图失败')
      const [characterRes, versionsRes] = await Promise.all([getJson(`/api/v1/characters/${character.id}`), getJson(`/api/v1/characters/${character.id}/portrait/versions` )])
      const refreshed = characterRes.data || characterRes
      setCharacter(refreshed)
      setPortraitVersions(versionsRes.data?.versions || [])
       setSelectedVisualUrl(browserAssetUrl(refreshed.identity?.visual_profile?.identity_reference_url || refreshed.portrait_url || url))
       setSelectedVersionId(String(version.id))
      message.success(`已设为主视图 / 身份基准图 v${version.version_number || '?'}`)
    } catch (error: any) { message.error(error?.message || '设置主视图失败') }
  }
  const toggleFavorite = async () => {
    if (!character) return
    const response = await fetch(`/api/v1/characters/${character.id}/favorite`, { method: 'POST', headers: { Accept: 'application/json' } })
    const result = await response.json()
    if (!response.ok || result?.success === false) { message.error(result?.detail || '收藏状态更新失败'); return }
    const updated = result.data || result
    setCharacter(updated)
    setCharacters((items) => items.map((item) => item.id === updated.id ? { ...item, ...updated } : item))
    message.success(updated.is_favorite ? '已收藏角色' : '已取消收藏')
  }
  const upgradePortrait = async () => {
    if (!character || character.portrait_node_id || !character.portrait_url) return
    try {
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/upgrade`, { method: 'POST', headers: { Accept: 'application/json' } })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '升级到资产中枢失败')
      const refreshed = await getJson(`/api/v1/characters/${character.id}`)
      setCharacter(refreshed.data || refreshed)
      const versions = await getJson(`/api/v1/characters/${character.id}/portrait/versions`)
      setPortraitVersions(versions.data?.versions || [])
      message.success('旧立绘已升级到资产中枢')
    } catch (error: any) { message.error(error?.message || '升级到资产中枢失败') }
  }
  const deleteCharacter = async () => {
    if (!character) return
    const response = await fetch(`/api/v1/characters/${character.id}`, { method: 'DELETE', headers: { Accept: 'application/json' } })
    if (!response.ok) { const result = await response.json().catch(() => null); message.error(result?.detail || '删除角色失败'); return }
    message.success('角色已删除')
    navigate('/characters', { replace: true })
  }
  const deletePortraitVersion = async (version: any) => {
    if (!character || !version?.id) return
    if (version.is_main) { message.info('主视图版本不能直接删除，请先切换到其他版本'); return }
    try {
      const response = await fetch(`/api/v1/assets/versions/${version.id}?mode=del_file`, { method: 'DELETE', headers: { Accept: 'application/json' } })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '删除失败')

      // 顺带从参考图集合里移除该版本的 URL（避免残留悬空引用）
      const versionUrl = browserAssetUrl(version.image_url || version.url || version.file_path)
      let cleanedCharacter = character
      if (versionUrl) {
        const profile = character.identity?.visual_profile || {}
        const refUrls = (profile.reference_image_urls || []).filter((item: any) => browserAssetUrl(item) !== versionUrl)
        if (refUrls.length < (profile.reference_image_urls || []).length) {
          const putResp = await fetch(`/api/v1/characters/${character.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({
              identity: { ...(character.identity || {}), visual_profile: { ...profile, reference_image_urls: refUrls } }
            }),
          })
          const putResult = await putResp.json()
          if (putResp.ok) cleanedCharacter = putResult.data || putResult
        }
      }

      const versions = await getJson(`/api/v1/characters/${character.id}/portrait/versions`)
      setPortraitVersions(versions.data?.versions || [])
      setCharacter(cleanedCharacter)
      message.success('立绘版本已删除（含文件），已同步清理参考图')
    } catch (error: any) { message.error(error?.message || '删除立绘版本失败') }
  }
  const toggleFrozen = async () => {
    if (!character) return
    const next = !Boolean(character.is_frozen)
    const response = await fetch(`/api/v1/characters/${character.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ is_frozen: next }) })
    const result = await response.json()
    if (!response.ok || result?.success === false) { message.error(result?.detail || '冻结状态更新失败'); return }
    const updated = result.data || result
    setCharacter(updated)
    setCharacters((items) => items.map((item) => item.id === updated.id ? { ...item, ...updated } : item))
    message.success(next ? '角色已冻结，外观设定将受到保护' : '角色已解冻，可继续修改外观设定')
  }
  const saveWorldUsage = async () => {
    if (!character || !worldForm.world_name.trim()) { message.warning('请填写世界/项目名称'); return }
    setWorldSaving(true)
    try {
      if (!worldForm.story_id.trim()) { message.warning('请填写项目 ID（story_id）'); setWorldSaving(false); return }
      const parseJson = (value: string, label: string) => { try { return value?.trim() ? JSON.parse(value) : {} } catch { throw new Error(`${label} JSON 格式不正确`) } }
      // 解析原始视觉覆盖JSON，再用便捷字段覆盖/追加
      const visualBase = parseJson(worldForm.visual_overrides, '视觉覆盖')
      const portraitUrl = worldVisualPortraitUrl.trim()
      const refUrls = worldVisualRefUrls.split(/[\n,]/).map((u) => u.trim()).filter(Boolean)
      const visualOverrides = {
        ...visualBase,
        ...(portraitUrl ? { identity_reference_url: portraitUrl, portrait_url: portraitUrl } : {}),
        ...(refUrls.length ? { reference_image_urls: refUrls } : {}),
      }
      // 如果便捷字段都为空且原始JSON为空对象，保持为空
      const finalVisual = (portraitUrl || refUrls.length || Object.keys(visualBase).length) ? visualOverrides : {}
      const payload = { story_id: worldForm.story_id.trim(), world_name: worldForm.world_name.trim(), usage_role: worldForm.usage_role, local_alias: worldForm.local_alias, local_identity: worldForm.local_identity, local_faction: worldForm.local_faction, local_status: worldForm.local_status, local_costume: worldForm.local_costume, local_prompt_tags: worldForm.local_prompt_tags.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean), ooc_notes: worldForm.ooc_notes, off_model_notes: worldForm.off_model_notes, bible_overrides: parseJson(worldForm.bible_overrides, 'Bible 覆盖'), visual_overrides: finalVisual }
      const response = await fetch(editingWorld ? `/api/v1/characters/${character.id}/world-usages/${editingWorld.id}` : `/api/v1/characters/${character.id}/link-story`, { method: editingWorld ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(editingWorld ? { world_name: payload.world_name, usage_role: payload.usage_role, local_alias: payload.local_alias, local_identity: payload.local_identity, local_faction: payload.local_faction, local_status: payload.local_status, local_costume: payload.local_costume, local_prompt_tags: payload.local_prompt_tags, ooc_notes: payload.ooc_notes, off_model_notes: payload.off_model_notes, bible_overrides: payload.bible_overrides, visual_overrides: payload.visual_overrides } : payload) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '保存世界使用失败')
      const refreshed = await getJson(`/api/v1/characters/${character.id}/world-usages`)
      setWorldUsages(refreshed.data || [])
      setWorldModalOpen(false)
      setEditingWorld(null)
      setWorldVisualPortraitUrl('')
      setWorldVisualRefUrls('')
      setWorldForm({ story_id: '', world_name: '', usage_role: '', local_alias: '', local_identity: '', local_faction: '', local_status: 'active', local_costume: '', local_prompt_tags: '', ooc_notes: '', off_model_notes: '', bible_overrides: '{}', visual_overrides: '{}' })
      message.success(editingWorld ? '世界使用已更新' : '已加入世界使用')
    } catch (error: any) { message.error(error?.message || '保存世界使用失败') } finally { setWorldSaving(false) }
  }
  const sliceTargetVersion = portraitVersions.find((item: any) => String(item.id) === String(sliceVersionId))
  /** 按立绘预设推荐切片网格：三视图与道具板是 1×3 横排，九宫格是 3×3 */
  const recommendedSlice = (preset: any) => {
    const value = String(preset || '').toLowerCase()
    if (value.includes('multi_view') || value.includes('turnaround')) return { rows: 1, cols: 3, hint: '三视图按 正面 / 侧面 / 背面 拆成三格' }
    if (value.includes('item')) return { rows: 1, cols: 3, hint: '道具设定板按每件道具拆成三格' }
    if (value.includes('grid_3x3')) return { rows: 3, cols: 3, hint: '九宫格按 3×3 拆分' }
    return { rows: 3, cols: 3, hint: '通用设定板默认按 3×3 拆分，可手动调整' }
  }
  const openSliceModal = (version: any) => {
    setSliceVersionId(String(version?.id || ''))
    const recommend = recommendedSlice(version?.preset)
    setSliceRows(recommend.rows)
    setSliceCols(recommend.cols)
    setSliceModalOpen(true)
  }
  const slicePortrait = async () => {
    if (!character || !sliceVersionId) return
    setSliceBusy(true)
    try {
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/versions/${sliceVersionId}/slice-grid`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ grid_type: 'auto', rows: sliceRows, cols: sliceCols, overwrite_existing: false }) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '切片失败')
      setPortraitSlices(result.data?.items || [])
      setSliceModalOpen(false)
      message.success(`已生成 ${result.data?.items?.length || 0} 个切片`)
    } catch (error: any) { message.error(error?.message || '切片失败') } finally { setSliceBusy(false) }
  }
  /**
   * 把视图矩阵中的素材设为当前世界专属：写入该世界 visual_overrides 的
   * turnaround_urls / item_urls。后端 PUT 会跳过 None 字段，所以只传
   * visual_overrides 即可局部更新，不会动到世界其它配置。
   */
  const pinAssetToWorld = async (asset: VisualAsset) => {
    if (!character || !activeWorld || asset.worldScoped) return
    const key = asset.kind === 'turnaround' ? 'turnaround_urls' : asset.kind === 'item' ? 'item_urls' : ''
    if (!key) { message.info('目前只有三视图与道具支持设为世界专属'); return }
    const visual: Record<string, any> = { ...(activeWorld.visual_overrides || {}) }
    const current: string[] = Array.isArray(visual[key]) ? visual[key] : []
    if (current.includes(asset.url)) { message.info('该素材已是当前世界专属'); return }
    visual[key] = [...current, asset.url]
    setWorldSaving(true)
    try {
      const response = await fetch(`/api/v1/characters/${character.id}/world-usages/${activeWorld.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ visual_overrides: visual }) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '设置世界专属失败')
      const refreshed = await getJson(`/api/v1/characters/${character.id}/world-usages`)
      setWorldUsages(refreshed.data || [])
      message.success(`已设为「${activeWorld.world_name || activeWorld.project_title || '当前世界'}」专属`)
    } catch (error: any) { message.error(error?.message || '设置世界专属失败') } finally { setWorldSaving(false) }
  }
  const removeWorldUsage = async (usageId: string) => {
    if (!character) return
    const response = await fetch(`/api/v1/characters/${character.id}/world-usages/${usageId}`, { method: 'DELETE', headers: { Accept: 'application/json' } })
    if (!response.ok) { message.error('删除世界使用失败'); return }
    setWorldUsages((items) => items.filter((item) => item.id !== usageId))
    message.success('已移除世界使用')
  }
  const openWorldEdit = (item: any) => {
    setEditingWorld(item)
    const visual = item.visual_overrides || {}
    setWorldForm({ story_id: item.story_id || item.project_id || '', world_name: item.world_name || item.project_title || '', usage_role: item.usage_role || '', local_alias: item.local_alias || '', local_identity: item.local_identity || '', local_faction: item.local_faction || '', local_status: item.local_status || 'active', local_costume: item.local_costume || '', local_prompt_tags: Array.isArray(item.local_prompt_tags) ? item.local_prompt_tags.join(', ') : '', ooc_notes: item.ooc_notes || '', off_model_notes: item.off_model_notes || '', bible_overrides: JSON.stringify(item.bible_overrides || {}, null, 2), visual_overrides: JSON.stringify(visual, null, 2) })
    // 便捷字段：解析出世界专属立绘URL和参考图URL
    setWorldVisualPortraitUrl(visual.identity_reference_url || visual.portrait_url || '')
    const refs = Array.isArray(visual.reference_image_urls) ? visual.reference_image_urls : []
    setWorldVisualRefUrls(refs.join('\n'))
    setWorldModalOpen(true)
  }
  const enrichCharacter = async (mode: 'fill_missing' | 'rewrite') => {
    if (!character) return
    setAiBusy(true)
    try {
      const response = await fetch(`/api/v1/characters/${character.id}/enrich`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ mode, apply: true, provider: enrichProvider || undefined, model: enrichModel || undefined, context: '请保持现有角色身份、外观和世界使用设定，不要凭空改变已确认事实。' }) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || 'AI 补全失败')
      if (result.data?.character) {
        setCharacter(result.data.character)
        setCharacters((items) => items.map((item) => item.id === result.data.character.id ? { ...item, ...result.data.character } : item))
      }
      const refreshedPack = await getJson(`/api/v1/characters/${character.id}/prompt-pack`)
      setPack(refreshedPack.data || refreshedPack)
      message.success(mode === 'fill_missing' ? '已补全缺失设定' : '已统一重写角色设定')
    } catch (error: any) { message.error(error?.message || 'AI 补全失败') } finally { setAiBusy(false) }
  }
  const previewPortraitPrompt = async () => {
    if (!character) return
    setPromptPreviewLoading(true)
    try {
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/prompt-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ preset: portraitPreset, prompt_override: portraitPrompt || undefined, negative_override: portraitNegativePrompt }) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '生成提示词预览失败')
      setPromptPreview(result.data || result)
      setPromptPreviewOpen(true)
    } catch (error: any) { message.error(error?.message || '生成提示词预览失败') } finally { setPromptPreviewLoading(false) }
  }
  const optimizePortraitPrompt = async () => {
    if (!character) return
    const basePrompt = portraitPrompt.trim() || displayValue(pack?.image_prompt || '')
    if (!basePrompt.trim()) { message.warning('请先填写提示词或载入 Prompt 资产包'); return }
    setPromptOptimizing(true)
    try {
      const result = await chat({
        messages: [
          { role: 'system', content: '你是角色立绘提示词工程师。只输出一段可直接用于生图的中文提示词，不要 Markdown、不要解释。保持角色身份、脸部、发型、服装和标志物一致。' },
          { role: 'user', content: `请优化下面这段角色立绘提示词，补充构图、光线、材质和一致性约束，不要添加矛盾设定：\n\n${basePrompt}` },
        ],
        provider: enrichProvider || undefined,
        model: enrichModel || undefined,
        temperature: 0.35,
        log_scene: 'character_portrait',
        log_ref_id: character.id,
        log_stage: 'portrait_prompt_optimize',
      })
      const optimized = String(result?.content || result?.data?.content || '').trim()
      if (!result?.success || !optimized) throw new Error(result?.error || 'AI 优化提示词失败')
      setPortraitPrompt(optimized)
      message.success('已优化角色生图提示词')
    } catch (error: any) { message.error(error?.message || 'AI 优化提示词失败') } finally { setPromptOptimizing(false) }
  }
  const generatePortrait = async () => {
    if (!character) return
    setAiBusy(true)
    try {
      // 文生图不携带参考图；图生图按用户勾选顺序提交，顺序即图 1、图 2……
      const generationReferences = portraitMode === 'img2img'
        ? selectedReferenceUrls.filter((url) => visualImages.includes(url))
        : []
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ prompt: portraitPrompt, provider: portraitProvider || undefined, model: portraitModel || undefined, negative_prompt: portraitNegativePrompt, preset: portraitPreset, size: portraitSize, reference_images: generationReferences, set_as_main: true }) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '角色生图失败')
      const saved = result.data?.character || result.character
      if (saved) {
        setCharacter(saved)
        setCharacters((items) => items.map((item) => item.id === saved.id ? { ...item, ...saved } : item))
        setSelectedVisualUrl(saved.identity?.visual_profile?.identity_reference_url || saved.portrait_url || '')
      }
      const [versions, logs] = await Promise.all([getJson(`/api/v1/characters/${character.id}/portrait/versions`), getJson(`/api/v1/logs?task_type=character_portrait&ref_id=${character.id}&limit=50`),])
      setPortraitVersions(versions.data?.versions || [])
      setPortraitLogs(logs.data || logs.items || [])
      message.success('角色立绘已生成并设为主视图')
    } catch (error: any) { message.error(error?.message || '角色生图失败') } finally { setAiBusy(false) }
  }
  const saveRelation = async () => {
    if (!character || !relationForm.related_character_id || !relationForm.relation_type.trim()) { message.warning('请选择关联角色并填写关系类型'); return }
    setRelationSaving(true)
    try {
      // 处理 world_usage_id：空串表示「全局关系」，发送 null
      const payload = {
        ...relationForm,
        world_usage_id: relationForm.world_usage_id || null,
        chapter_number: relationForm.chapter_number ?? null,
      }
      const response = await fetch(editingRelation ? `/api/v1/characters/${character.id}/relationships/${editingRelation.id}` : `/api/v1/characters/${character.id}/relationships`, { method: editingRelation ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(payload) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '保存关系失败')
      // 按当前筛选器刷新关系列表
      const filterParam = relationWorldFilter === '__all__' ? '' : `?world_usage_id=${encodeURIComponent(relationWorldFilter === '' ? '' : relationWorldFilter)}`
      const refreshed = await getJson(`/api/v1/characters/${character.id}/relationships${filterParam}`)
      setRelationships(refreshed.data || [])
      const refreshedGraph = await getJson('/api/v1/characters/relationships/graph')
      setRelationshipGraph({ ...(refreshedGraph.data || refreshedGraph), focus_id: character.id })
      setRelationModalOpen(false)
      setRelationForm({ related_character_id: '', relation_type: '', relation_note: '', is_directed: false, world_usage_id: null, timeline_phase: '', chapter_number: null })
      setEditingRelation(null)
      message.success(editingRelation ? '关系已更新' : '关系已添加')
    } catch (error: any) { message.error(error?.message || '保存关系失败') } finally { setRelationSaving(false) }
  }
  const editRelation = (item: any) => {
    setEditingRelation(item)
    setRelationForm({
      related_character_id: item.related_character_id || '',
      relation_type: item.relation_type || '',
      relation_note: item.relation_note || '',
      is_directed: Boolean(item.is_directed),
      world_usage_id: item.world_usage_id || null,
      timeline_phase: item.timeline_phase || '',
      chapter_number: item.chapter_number ?? null,
    })
    setRelationModalOpen(true)
  }
  const removeRelation = async (item: any) => { if (!character) return; const response = await fetch(`/api/v1/characters/${character.id}/relationships/${item.id}`, { method: 'DELETE', headers: { Accept: 'application/json' } }); if (!response.ok) { message.error('删除关系失败'); return }; setRelationships((items) => items.filter((value) => value.id !== item.id)); const refreshedGraph = await getJson('/api/v1/characters/relationships/graph').catch(() => null); if (refreshedGraph) setRelationshipGraph({ ...(refreshedGraph.data || refreshedGraph), focus_id: character.id }); message.success('关系已删除') }
  const updateTag = async (tag: string, method: 'POST' | 'DELETE') => {
    if (!character || !tag.trim()) return
    const response = await fetch(`/api/v1/characters/${character.id}/tags${method === 'DELETE' ? `/${encodeURIComponent(tag.trim())}` : ''}`, {
      method,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...(method === 'POST' ? { body: JSON.stringify({ tag: tag.trim() }) } : {}),
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok || result?.success === false) { message.error(result?.detail || '标签更新失败'); return }
    const saved = result.data || result.character || result
    if (saved?.id) {
      setCharacter((current) => current ? { ...current, ...saved } : current)
      setCharacters((items) => items.map((item) => item.id === character.id ? { ...item, ...saved } : item))
    }
  }
  const renderHistoryRecords = (title: string, values: any[]) => {
    if (!values.length) return <Text style={{ color: theme.textSecondary }}>暂无记录</Text>
    if (title === '生图日志') return <Space direction="vertical" size={8} style={{ width: '100%' }}>{values.map((item, index) => <div key={item.id || index} style={{ background: theme.bgElevated, border: `1px solid ${theme.borderLight}`, padding: 10, borderRadius: 6 }}><Space wrap><Tag color={item.status === 'success' ? 'green' : item.status === 'failed' ? 'red' : 'blue'}>{item.status || 'unknown'}</Tag><Text style={{ color: theme.textSecondary }}>{item.provider || '默认供应商'} · {item.model || '默认模型'}</Text><Text style={{ color: theme.textSecondary }}>{item.created_at ? new Date(item.created_at).toLocaleString() : '时间未知'}</Text></Space>{item.prompt && <Paragraph style={{ color: theme.textPrimary, margin: '6px 0 0', whiteSpace: 'pre-wrap' }}>{item.prompt}</Paragraph>}{(item.error || item.validation_error) && <Text type="danger">{item.error || item.validation_error}</Text>}</div>)}</Space>
    if (title === '切片记录') return <Image.PreviewGroup><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 10 }}>{values.map((item, index) => { const url = item.image_url || item.url || item.file_path; return <div key={item.id || index} style={{ background: theme.bgElevated, border: `1px solid ${theme.borderLight}`, padding: 8, borderRadius: 6 }}>{url ? <Image src={url} width="100%" height={110} style={{ objectFit: 'cover' }} /> : <div style={{ height: 110, display: 'grid', placeItems: 'center' }}><PictureOutlined /></div>}<Text style={{ color: theme.textSecondary, fontSize: 11, display: 'block', marginTop: 5 }}>{item.label || item.name || `切片 ${index + 1}`}</Text></div> })}</div></Image.PreviewGroup>
    return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>{values.map((value, index) => <div key={index} style={{ background: theme.bgElevated, border: `1px solid ${theme.borderLight}`, padding: 12, borderRadius: 6 }}><Text style={{ color: theme.textSecondary, fontSize: 11 }}>记录 {index + 1}</Text><Paragraph style={{ color: theme.textPrimary, margin: '6px 0 0', whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}>{displayValue(value)}</Paragraph></div>)}</div>
  }
  // 次要操作收进「更多」下拉，避免 12 个按钮平权堆叠导致核心操作被淹没
  const moreActions: MenuProps['items'] = [
    { key: 'fullscreen', icon: workspaceFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />, label: workspaceFullscreen ? '退出全屏' : '全屏工作区', onClick: toggleWorkspaceFullscreen },
    { type: 'divider' },
    ...(character ? [
      { key: 'new-project', icon: <PlusOutlined />, label: '以此角色新建项目', onClick: () => navigate(`/story?new=1&character_id=${encodeURIComponent(character.id)}`) },
      { key: 'enter-project', icon: <ArrowRightOutlined />, label: '进入创作项目', onClick: () => navigate(worldUsages[0]?.story_id || worldUsages[0]?.project_id ? `/story?project_id=${encodeURIComponent(worldUsages[0].story_id || worldUsages[0].project_id)}` : '/story') },
      { key: 'graph', icon: <BranchesOutlined />, label: '关系图谱', onClick: () => document.getElementById('character-relationship-graph')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) },
      ...(character.portrait_url && !character.portrait_node_id ? [{ key: 'upgrade', icon: <DatabaseOutlined />, label: '升级到资产中枢', onClick: upgradePortrait }] : []),
      { type: 'divider' },
      { key: 'freeze', label: character.is_frozen ? '解冻角色' : '冻结角色', onClick: toggleFrozen },
      { key: 'favorite', icon: character.is_favorite ? <StarFilled /> : <StarOutlined />, label: character.is_favorite ? '取消收藏' : '收藏', onClick: toggleFavorite },
      { type: 'divider' },
      { key: 'delete', icon: <DeleteOutlined />, label: '删除角色', danger: true, onClick: () => setDeleteConfirmOpen(true) },
    ] : []),
  ] as MenuProps['items']

  return <div style={{ minHeight: '100%', background: theme.bgPage, padding: workspaceFullscreen ? 14 : 18 }}>
    <div className={workspaceFullscreen ? 'character-detail-shell is-fullscreen' : 'character-detail-shell'}>
      <aside className="character-detail-sidebar" style={{ background: theme.bgCard, border: `1px solid ${theme.borderLight}`, borderRadius: 10, padding: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}><Text strong style={{ color: theme.textPrimary }}>角色列表</Text><Button size="small" type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建</Button></div>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Input size="small" allowClear prefix={<SearchOutlined />} placeholder="搜索角色" value={characterKeyword} onChange={(event) => setCharacterKeyword(event.target.value)} />
          <Select size="small" allowClear placeholder="全部定位" value={characterRole} onChange={setCharacterRole} options={ROLE_OPTIONS} style={{ width: '100%' }} />
           <Select size="small" allowClear placeholder="全部来源" value={characterSource} onChange={setCharacterSource} options={SOURCE_OPTIONS} style={{ width: '100%' }} />
           <Select size="small" allowClear placeholder="全部流程" value={characterWorkflowSource} onChange={setCharacterWorkflowSource} options={WORKFLOW_SOURCE_OPTIONS} style={{ width: '100%' }} />
           <Select size="small" allowClear placeholder="全部提取来源" value={characterExtractOrigin} onChange={setCharacterExtractOrigin} options={EXTRACT_ORIGIN_OPTIONS} style={{ width: '100%' }} />
          <Button size="small" type={favoritesOnly ? 'primary' : 'default'} onClick={() => setFavoritesOnly((value) => !value)} block>仅收藏</Button>
        </Space>
        <div className="character-detail-sidebar-list" style={{ marginTop: 14 }}>
          {filteredCharacters.map((item) => {
            const active = !!character && item.id === character.id
            return <button key={item.id} type="button" onClick={() => navigate(`/characters/${item.id}`)} className={active ? 'cd-char-item is-active' : 'cd-char-item'} title={item.name}>
              {item.portrait_url ? <img src={browserAssetUrl(item.portrait_url)} alt="" className="cd-char-avatar" loading="lazy" /> : <span className="cd-char-avatar cd-char-avatar-empty">{String(item.name || '?').trim().charAt(0)}</span>}
              <span className="cd-char-meta"><span className="cd-char-name">{item.name}</span><span className="cd-char-sub">{item.role_label || item.role || '角色'}</span></span>
              <span className="cd-char-flags">{item.is_favorite ? <StarFilled className="cd-char-star" /> : null}{item.portrait_url ? null : <Tag className="cd-char-tag">无立绘</Tag>}</span>
            </button>
          })}
          {!filteredCharacters.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配角色" />}
        </div>
      </aside>
      <main style={{ minWidth: 0 }}>
      {!character ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 400 }}>
          <Space direction="vertical" size={16}>
            <Title level={3} style={{ color: theme.textPrimary, margin: 0 }}>新建角色</Title>
            <Text style={{ color: theme.textSecondary }}>填写角色基础信息即可创建，创建后可补充立绘与设定</Text>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>开始创建</Button>
          </Space>
        </div>
      ) : (
      <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
         <div><Title level={2} style={{ color: theme.textPrimary, margin: 0 }}>{character.name}</Title><Space size={6}><Text style={{ color: theme.textSecondary }}>{character.role_label || character.role || '角色'} · 设定集报告</Text><Tag color="blue">{character.workflow_source_label || '未标记'}</Tag>{(character.extract_origins || []).map((origin: string) => <Tag key={origin} color={origin === 'original_outline' ? 'gold' : 'green'}>{extractOriginLabel(origin)}</Tag>)}{!(character.extract_origins || []).length && character.workflow_source === 'extract' ? <Tag color="default">未标记提取来源</Tag> : null}</Space></div>
        <Space wrap size={8}>
          <Button type="primary" icon={<EditOutlined />} onClick={openEdit}>编辑角色</Button>
          <Space.Compact>
            <Button loading={aiBusy} onClick={() => enrichCharacter('fill_missing')}>AI 补全</Button>
            <Button loading={aiBusy} onClick={() => enrichCharacter('rewrite')}>统一重写</Button>
          </Space.Compact>
          <Popover
            trigger="click"
            placement="bottomRight"
            title="AI 补全配置"
            content={
              <Space direction="vertical" size={8} style={{ width: 240 }}>
                <Select size="small" value={enrichProvider || undefined} placeholder="AI 补全供应商" style={{ width: '100%' }} onChange={(value) => { setEnrichProvider(value); const backend = llmBackends.find((item) => (item.name || item.provider) === value); setEnrichModel(backend?.default_model || backend?.model || backend?.available_models?.[0] || '') }} options={llmBackends.map((item) => ({ value: item.name || item.provider, label: item.provider_label || item.name || item.provider }))} />
                <Select size="small" value={enrichModel || undefined} placeholder="AI 补全模型" style={{ width: '100%' }} onChange={setEnrichModel} options={Array.from(new Set((llmBackends.find((item) => (item.name || item.provider) === enrichProvider)?.available_models || [llmBackends.find((item) => (item.name || item.provider) === enrichProvider)?.default_model]).filter(Boolean))).map((value) => ({ value, label: value }))} />
              </Space>
            }
          >
            <Button icon={<SettingOutlined />} />
          </Popover>
          <Dropdown menu={{ items: moreActions }} trigger={['click']}>
            <Button icon={<EllipsisOutlined />}>更多</Button>
          </Dropdown>
        </Space>
      </div>

      {/* 生成模式：默认折叠，展开后显示完整参数 */}
      <section className="character-portrait-controls" style={{ marginBottom: 14, padding: portraitControlsCollapsed ? '10px 14px' : '12px 14px', background: theme.bgCard, borderBottom: `1px solid ${theme.borderLight}`, transition: 'padding .15s' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => setPortraitControlsCollapsed(!portraitControlsCollapsed)}>
          <Space size={8}>
            <Text strong style={{ color: theme.textPrimary, fontSize: 14 }}>立绘生成</Text>
            <Tag>{portraitMode === 'img2img' ? '图生图' : '文生图'} · {portraitProvider || '默认'} · {portraitModel || '默认模型'} · {portraitSize}</Tag>
          </Space>
          <Button type="text" size="small" icon={portraitControlsCollapsed ? <DownOutlined /> : <UpOutlined />} />
        </div>
        {!portraitControlsCollapsed && (
          <div style={{ marginTop: 10 }} id="portrait-controls-content">
            <div style={{ gridColumn: '1 / -1' }}><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>生成模式</Text><Segmented value={portraitMode} onChange={(value) => setPortraitMode(value as 'text2img' | 'img2img')} options={[{ value: 'img2img', label: '图生图（携带参考图）' }, { value: 'text2img', label: '文生图（不携带参考图）' }]} /></div>
            <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>图像供应商</Text><Select value={portraitProvider || undefined} onChange={(value) => { setPortraitProvider(value); const backend = portraitBackendOptions.find((item) => (item.name || item.provider) === value); setPortraitModel(backend?.model || backend?.available_models?.[0] || '') }} style={{ width: '100%' }} options={portraitBackendOptions.map((item) => { const value = item.name || item.provider; const providerLabel = item.provider_label || item.provider || '通用供应商'; const connectorLabel = item.name && item.name !== item.provider ? item.name : ''; const modelLabel = item.model || item.available_models?.[0] || ''; return { value, label: connectorLabel ? `${providerLabel} · ${connectorLabel}${modelLabel ? ` · ${modelLabel}` : ''}` : `${providerLabel}${modelLabel ? ` · ${modelLabel}` : ''}` } })} placeholder="默认后端" /></div>
            <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>模型</Text><Select value={portraitModel || undefined} onChange={setPortraitModel} style={{ width: '100%' }} options={Array.from(new Set((portraitBackendOptions.find((item) => (item.name || item.provider) === portraitProvider)?.available_models || [portraitBackendOptions.find((item) => (item.name || item.provider) === portraitProvider)?.model]).filter(Boolean))).map((value) => ({ value, label: value }))} placeholder="默认模型" /></div>
            <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>立绘预设</Text><Select value={portraitPreset} onChange={setPortraitPreset} style={{ width: '100%' }} options={[
              { label: '基础立绘', options: [
                { value: 'main_portrait', label: '主立绘' },
                { value: 'headshot_icon', label: '头像 / 图标' },
                { value: 'key_visual', label: '主视觉海报（Key Visual）' },
                { value: 'transparent_or_white_background', label: '白底 / 透明底素材（可抠图）' },
              ] },
              { label: '设定板', options: [
                { value: 'character_sheet_16_9', label: '16:9 角色设定板（推荐）' },
                { value: 'multi_view_sheet', label: 'Turnaround 三视图' },
                { value: 'identity_board_16_9', label: '16:9 身份板（兼容）' },
                { value: 'expression_pose_sheet', label: '表情 + 姿态设定板' },
              ] },
              { label: '素材包', options: [
                { value: 'expression_grid_3x3', label: '表情九宫格（需先有主立绘）' },
                { value: 'expression_pack', label: '表情包设定板' },
                { value: 'pose_grid_3x3', label: '动作九宫格（需先有主立绘）' },
                { value: 'action_pose_pack', label: '动作姿态设定板' },
                { value: 'item_sheet', label: '道具 / 标志物设定板' },
              ] },
            ]} /></div>
            <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>尺寸</Text><Select value={portraitSize} onChange={setPortraitSize} style={{ width: '100%' }} options={portraitSizeOptions.map((value) => ({ value, label: value }))} /></div>
            <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>提示词覆盖（可选）</Text><Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} value={portraitPrompt} onChange={(event) => setPortraitPrompt(event.target.value)} placeholder="留空则按角色设定和预设自动生成" /></div>
            <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>负面提示词（可选）</Text><Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} value={portraitNegativePrompt} onChange={(event) => setPortraitNegativePrompt(event.target.value)} placeholder="例如：模糊、畸形手指、多余人物" /></div>
            {portraitMode === 'img2img' && (
              <div style={{ gridColumn: '1 / -1' }}>
                <Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 6 }}>参考图：勾选参与本次生图，顺序即图 1、图 2……（已选 {selectedReferenceUrls.length} 张）</Text>
                {visualImages.length ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(92px, 1fr))', gap: 8 }}>
                    {visualImages.map((url: string) => {
                      const checked = selectedReferenceUrls.includes(url)
                      return (
                        <div key={url} onClick={() => toggleReferenceUrl(url)} style={{ position: 'relative', border: `2px solid ${checked ? '#1677ff' : theme.borderLight}`, borderRadius: 6, overflow: 'hidden', cursor: 'pointer', background: theme.bgElevated }}>
                          <img src={url} alt="" style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', display: 'block', opacity: checked ? 1 : 0.4 }} />
                          <div style={{ position: 'absolute', top: 2, left: 2 }}><Checkbox checked={checked} onChange={() => toggleReferenceUrl(url)} /></div>
                          {url === mainVisualUrl && <Tag color="blue" style={{ position: 'absolute', bottom: 2, left: 2, margin: 0, fontSize: 10 }}>主视图</Tag>}
                          <Popconfirm title="从参考图集合移除？" onConfirm={() => removeReferenceImage(url)} okText="移除" cancelText="取消">
                            <Button type="text" danger icon={<DeleteOutlined />} size="small" style={{ position: 'absolute', top: 2, right: 2, background: 'rgba(0,0,0,.55)', padding: 0, width: 22, height: 22, fontSize: 10, lineHeight: '22px' }} />
                          </Popconfirm>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <Text style={{ color: theme.textSecondary, fontSize: 12 }}>暂无参考图，可先生成立绘或从素材库加入参考图</Text>
                )}
              </div>
            )}
            <Space style={{ marginTop: 6 }}><Button loading={promptPreviewLoading} onClick={previewPortraitPrompt}>预览 Prompt</Button><Button loading={promptOptimizing} onClick={optimizePortraitPrompt}>AI 优化</Button><Button loading={aiBusy} onClick={() => setPortraitPrompt(displayValue(pack?.image_prompt || ''))}>载入提示词</Button><Button type="primary" icon={<PictureOutlined />} loading={aiBusy} onClick={generatePortrait}>生成主立绘</Button></Space>
          </div>
        )}
      </section>

      <section style={{ padding: '12px 16px', marginBottom: 12, background: theme.bgCard, border: `1px solid ${theme.borderLight}`, borderRadius: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: activeWorld || worldUsages.length ? 10 : 0 }}>
          <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>世界视角</Text>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>角色是全局基准；切到某个项目后展示「基准 + 该项目覆盖」的有效设定</Text>
        </div>
        <WorldSwitcher worlds={worldUsages} activeId={activeWorldId} onChange={setActiveWorldId} theme={theme} />
        <WorldOverrideNotice world={activeWorld} theme={theme} />
        {!worldUsages.length ? <Text style={{ color: theme.textSecondary, fontSize: 12 }}>该角色还没有加入任何项目/世界，添加世界使用后可在这里切换视角。</Text> : null}
      </section>

      {/* ===== 视觉中心区：主视图大图 + 角色 Bible（版本缩略图已移至下方立绘版本区） ===== */}
      <section className="character-report-hero" style={{ background: theme.bgCard, borderTop: `1px solid ${theme.borderLight}`, borderBottom: `1px solid ${theme.borderLight}`, padding: 18 }}>
        <div className="flex-row" style={{ display: 'flex', gap: 24, minHeight: 560 }}>
          {/* 左侧：主视图 */}
          <div className="cd-hero-main">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Space size={10}>
                <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>角色视觉参考</Text>
                <Text style={{ color: isPreviewVisual ? '#f59e0b' : (isWorldScopedVisual ? '#8b5cf6' : theme.textSecondary), fontSize: 12 }}>
                  {isPreviewVisual ? `版本预览 · v${selectedVersion?.version_number || '?'}` : (isWorldScopedVisual ? `${activeWorld?.world_name || '当前世界'}专属立绘` : '主视图 / 身份基准图')}
                </Text>
                {!isPreviewVisual && !isWorldScopedVisual && selectedVersion?.is_main ? <Tag color="cyan" style={{ margin: 0 }}>主视图</Tag> : null}
                {isWorldScopedVisual && !isPreviewVisual ? <Tag color="purple" style={{ margin: 0 }}>世界专属</Tag> : null}
              </Space>
              <Space size={4}>
                {isPreviewVisual ? <Button type="link" size="small" onClick={restoreMainVisual}>返回主视图</Button> : null}
                <Button size="small" icon={<PictureOutlined />} onClick={openReferencePicker}>从素材库加入</Button>
              </Space>
            </div>

            {/* 主视图：独占视觉中心，参考图已合并到顶部操作栏 */}
            <div className="character-report-media" style={{ display: 'flex', gap: 12 }}>
              <div style={{ background: theme.bgElevated, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 520, maxHeight: 840, borderRadius: 6 }}>
                <div style={{ flex: 1, display: 'grid', placeItems: 'center', padding: 8, overflow: 'hidden' }}>
                  {mainVisualUrl ? (
                    <Image src={mainVisualUrl} preview={{ src: mainVisualUrl }} style={{ width: '100%', height: '100%', objectFit: 'contain', maxHeight: 800 }} />
                  ) : (
                    <Avatar size={120} icon={<UserOutlined />} />
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 中间：视图矩阵，承接三视图 / 道具 / 表情 / 姿态，填满主视图与 Bible 之间的横向空间 */}
          <div className="cd-hero-matrix">
            <Space size={8} style={{ marginBottom: 10 }}>
              <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>视图矩阵</Text>
              {activeWorld ? <Tag color="cyan" style={{ marginInlineEnd: 0 }}>{activeWorld.world_name || activeWorld.project_title || '当前世界'}</Tag> : null}
            </Space>
            {visualAssetGroups.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxHeight: 800, overflowY: 'auto', paddingRight: 4 }}>
                {visualAssetGroups.map((group) => (
                  <div key={group.key}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                      <Text style={{ color: theme.textPrimary, fontSize: 12, fontWeight: 600 }}>{group.label}</Text>
                      <Text style={{ color: theme.textSecondary, fontSize: 11 }}>{group.items.length}</Text>
                      {group.hasWorldScoped ? <Tag color="purple" style={{ margin: 0, fontSize: 10 }}>世界专属</Tag> : (activeWorld ? <Tag style={{ margin: 0, fontSize: 10 }}>沿用基准</Tag> : null)}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: group.key === 'turnaround' ? 'repeat(3, minmax(0, 1fr))' : 'repeat(auto-fill, minmax(62px, 1fr))', gap: 6 }}>
                      {group.items.map((asset) => (
                        <button
                          key={asset.id}
                          type="button"
                          title={asset.label || group.label}
                          onClick={() => setSelectedVisualUrl(asset.url)}
                          className={selectedVisualUrl === asset.url ? 'cd-view-cell is-active' : 'cd-view-cell'}
                        >
                          <img src={asset.url} alt={asset.label || group.label} loading="lazy" />
                          {asset.label ? <span className="cd-view-cell-label">{asset.label}</span> : null}
                          {activeWorld && !asset.worldScoped && (asset.kind === 'turnaround' || asset.kind === 'item') ? (
                            <span className="cd-view-cell-pin" title="设为当前世界专属" onClick={(event) => { event.stopPropagation(); pinAssetToWorld(asset) }}><PushpinOutlined /></span>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: theme.textSecondary, fontSize: 12, lineHeight: 1.9 }}>
                暂无三视图 / 道具 / 表情素材。
                <br />
                在「生成立绘」中选择「Turnaround 三视图」或「道具 / 标志物设定板」生成后，
                再做网格切片即可自动归入这里。
              </div>
            )}
          </div>

          {/* 右侧：角色 Bible */}
          <div className="cd-hero-bible">
            <Space size={6} style={{ marginBottom: 8 }}>
              <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>角色 Bible</Text>
              {activeWorld ? <Tag color="cyan" style={{ marginInlineEnd: 0 }}>{activeWorld.world_name || activeWorld.project_title || '当前世界'}</Tag> : null}
            </Space>
            <FieldRenderer label="身份" value={effectiveIdentity.logline || effectiveIdentity.position || effectiveIdentity.organization} theme={theme} source={character.field_sources?.identity || character.field_sources?.logline} overridden={Boolean(activeWorld?.bible_overrides?.identity || activeWorld?.bible_overrides?.logline)} />
            {signatureItems.length ? (
              <div style={{ marginBottom: 8 }}>
                <Text style={{ color: theme.textSecondary, fontSize: 11, display: 'block', marginBottom: 3 }}>标志物</Text>
                <Space size={4} wrap>{signatureItems.map((item: string) => <Tag key={item} color="gold" style={{ marginInlineEnd: 0, fontSize: 11 }}>{item}</Tag>)}</Space>
              </div>
            ) : null}
            <FieldRenderer label="核心欲望" value={effectiveMotivation.desire || effectiveMotivation.core_desire} theme={theme} source={character.field_sources?.motivation} overridden={Boolean(activeWorld?.bible_overrides?.motivation)} />
            <FieldRenderer label="深层恐惧" value={effectiveMotivation.fear || effectiveMotivation.deep_fear} theme={theme} source={character.field_sources?.motivation} overridden={Boolean(activeWorld?.bible_overrides?.motivation)} />
            <FieldRenderer label="说话方式" value={effectiveSpeech.tone || effectiveSpeech.style} theme={theme} source={character.field_sources?.speech} overridden={Boolean(activeWorld?.bible_overrides?.speech)} />
            {effectiveSpeech.catchphrase ? <FieldRenderer label="口头禅" value={effectiveSpeech.catchphrase} theme={theme} source={character.field_sources?.speech} overridden={Boolean(activeWorld?.bible_overrides?.speech)} /> : null}
            <FieldRenderer label="行为底线" value={effectiveBehavior.never_do || effectiveBehavior.boundary || effectiveBehavior.ooc_boundary} theme={theme} source={character.field_sources?.behavior} overridden={Boolean(activeWorld?.bible_overrides?.behavior)} />
            {Object.keys(effectiveAbility).length ? <FieldRenderer label="能力" value={effectiveAbility} theme={theme} source={character.field_sources?.ability} overridden={Boolean(activeWorld?.bible_overrides?.ability)} /> : null}
            {Object.keys(effectiveArc).length ? <FieldRenderer label="角色弧光" value={effectiveArc} theme={theme} source={character.field_sources?.arc} overridden={Boolean(activeWorld?.bible_overrides?.arc)} /> : null}
            {Object.keys(effectiveVisualOverrides).length ? <FieldRenderer label="视觉覆盖" value={effectiveVisualOverrides} theme={theme} source="世界覆盖" /> : null}
            {characterTags.length ? (
              <div style={{ marginTop: 6 }}>
                <Text style={{ color: theme.textSecondary, fontSize: 11, display: 'block', marginBottom: 3 }}>标签</Text>
                <Space size={4} wrap>{characterTags.map((tag: string) => <Tag key={tag} style={{ marginInlineEnd: 0, fontSize: 11 }}>{tag}</Tag>)}</Space>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {/* 立绘版本：小缩略图横向滚动，点击切换主视图；详情弹窗展示 */}
      {portraitVersions.length ? (
        <section id="portrait-versions-section" style={{ marginTop: 18, borderTop: `1px solid ${theme.borderLight}`, padding: portraitVersionsCollapsed ? '10px 4px' : '14px 4px', transition: 'padding .15s' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => setPortraitVersionsCollapsed(!portraitVersionsCollapsed)}>
            <Space size={8}>
              <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>立绘版本</Text>
              <Tag>{portraitVersions.length} 个</Tag>
            </Space>
            <Button type="text" size="small" icon={portraitVersionsCollapsed ? <DownOutlined /> : <UpOutlined />} />
          </div>
          {!portraitVersionsCollapsed && (
            <div style={{ marginTop: 10 }}>
              {/* 小缩略图横向滚动条：点击切换主视图，不弹窗 */}
              <div className="cd-version-strip" style={{ display: 'flex', gap: 7, overflowX: 'auto', padding: '4px 0 10px', alignItems: 'flex-start' }}>
                {portraitVersions.map((version: any) => {
                  const url = version.image_url || version.url || version.file_path
                  const active = String(version.id) === String(selectedVersionId)
                  return (
                    <button
                      key={version.id}
                      type="button"
                      onClick={() => url && (setSelectedVisualUrl(url), setSelectedVersionId(String(version.id)))}
                      title={`V${version.version_number || '?'}${version.is_main ? ' · 主视图' : ''}`}
                      className={active ? 'cd-version-thumb is-active' : 'cd-version-thumb'}
                    >
                      <div className="cd-version-thumb-img">
                        {url ? <img src={url} alt="" loading="lazy" /> : <PictureOutlined />}
                      </div>
                      <span className="cd-version-thumb-label">V{version.version_number || '?'}{version.is_main ? ' · 主' : ''}</span>
                    </button>
                  )
                })}
              </div>

              {/* 选中版本的紧凑操作栏 */}
              {selectedVersion && (() => {
                const v = selectedVersion
                const url = v.image_url || v.url || v.file_path
                const hasDetails = [v.prompt, v.negative_prompt, v.params].some((x) => x)
                return (
                  <div className="cd-version-actions" style={{ borderTop: `1px solid ${theme.borderLight}`, paddingTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <Space size={4}>
                      <Text style={{ color: theme.textPrimary, fontSize: 12 }}>V{v.version_number || '?'}</Text>
                      {v.is_main ? <Tag color="cyan" style={{ marginInlineEnd: 0, fontSize: 11 }}>主视图</Tag> : null}
                      {!v.isPreviewVisual && !isWorldScopedVisual && String(v.id) === String(selectedVersionId) ? <Tag color="gold" style={{ marginInlineEnd: 0, fontSize: 11 }}>当前查看</Tag> : null}
                    </Space>
                    <Space size={3} wrap>
                      {!v.is_main && <Button size="small" onClick={() => setMainVersion(v)}>设为主视图</Button>}
                      <Button size="small" disabled={!url} onClick={() => addReferenceVersion(v)}>加入参考</Button>
                      <Button size="small" onClick={() => openSliceModal(v)}>切片</Button>
                      {hasDetails ? <Button size="small" onClick={() => setVersionDetailVersion(v)}>详情</Button> : null}
                      {!v.is_main && <Popconfirm title="删除此立绘版本（含文件）？" onConfirm={() => deletePortraitVersion(v)} okText="删除" cancelText="取消"><Button size="small" danger icon={<DeleteOutlined />} /></Popconfirm>}
                    </Space>
                  </div>
                )
              })()}
            </div>
          )}
        </section>
      ) : null}

      {/* 版本详情弹窗：替代内联 Collapse 展开 */}
      <Modal
        open={Boolean(versionDetailVersion)}
        title={`V${versionDetailVersion?.version_number || '?'} 生成详情`}
        onCancel={() => setVersionDetailVersion(null)}
        footer={[
          <Button key="close" onClick={() => setVersionDetailVersion(null)}>关闭</Button>,
          versionDetailVersion?.is_main !== true ? <Button key="main" type="primary" size="small" onClick={() => { setMainVersion(versionDetailVersion); setVersionDetailVersion(null) }}>设为主视图</Button> : null,
        ]}
        width={640}
      >
        {versionDetailVersion ? (() => {
          const v = versionDetailVersion
          const detailItems = [
            { label: '生成提示词', value: v.prompt },
            { label: '负面提示词', value: v.negative_prompt },
            { label: '生成参数', value: Object.keys(v.params || {}).length ? JSON.stringify(v.params, null, 2) : '' },
            { label: '供应商 / 模型', value: [v.provider, v.model].filter(Boolean).join(' / ') || undefined },
            { label: '预设', value: v.preset },
            { label: '尺寸', value: v.size },
            { label: '创建时间', value: v.created_at ? new Date(v.created_at).toLocaleString() : undefined },
          ].filter((item) => item.value !== undefined && item.value !== '')
          if (!detailItems.length) return <Text type="secondary">暂无详细记录</Text>
          return (
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              {(v.image_url || v.url || v.file_path) && (
                <div style={{ textAlign: 'center' }}><Image src={v.image_url || v.url || v.file_path} preview={{ src: v.image_url || v.url || v.file_path }} style={{ maxHeight: 300, objectFit: 'contain' }} /></div>
              )}
              {detailItems.map((item) => (
                <div key={item.label}>
                  <Text style={{ color: theme.textSecondary, fontSize: 12 }}>{item.label}</Text>
                  <Paragraph copyable style={{ color: theme.textPrimary, whiteSpace: 'pre-wrap', margin: '3px 0 0', fontSize: 12 }}>{String(item.value)}</Paragraph>
                </div>
              ))}
            </Space>
          )
        })() : null}
      </Modal>

      <section className="character-report-lower" style={{ padding: '22px 4px', borderBottom: `1px solid ${theme.borderLight}` }}>
        <div><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>人物摘要</Text><div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginTop: 8 }}><FieldRenderer label="外观" value={character.appearance} theme={theme} source={character.field_sources?.appearance} /><FieldRenderer label="服装" value={effectiveCostume} theme={theme} source={character.field_sources?.costume_hint} overridden={Boolean(activeWorld?.local_costume)} /><FieldRenderer label="性格" value={character.personality} theme={theme} source={character.field_sources?.personality} /><FieldRenderer label="背景" value={character.background} theme={theme} source={character.field_sources?.background} /></div></div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <Space size={8}>
              <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>关系</Text>
              <Select
                size="small"
                value={relationWorldFilter}
                onChange={async (value) => {
                  setRelationWorldFilter(value)
                  // 切换筛选时立即重新加载关系数据
                  if (character) {
                    const filterParam = value === '__all__' ? '' : `?world_usage_id=${encodeURIComponent(value === '' ? '' : value)}`
                    try {
                      const refreshed = await getJson(`/api/v1/characters/${character.id}/relationships${filterParam}`)
                      setRelationships(refreshed.data || [])
                    } catch (e) {
                      message.error('加载关系失败')
                    }
                  }
                }}
                style={{ width: 160 }}
                options={[
                  { value: '__all__', label: '全部世界/全局' },
                  { value: '', label: '仅全局关系' },
                  ...worldUsages.map((w: any) => ({ value: String(w.id), label: w.world_name || w.project_title || '未命名世界' }))
                ]}
              />
            </Space>
            <Button size="small" icon={<PlusOutlined />} onClick={() => { setEditingRelation(null); setRelationForm({ related_character_id: '', relation_type: '', relation_note: '', is_directed: false, world_usage_id: null, timeline_phase: '', chapter_number: null }); setRelationModalOpen(true) }}>添加关系</Button>
          </div>
          {relationships.length ? (() => {
            // 后端已按筛选器返回对应关系，这里直接显示
            // 但如果前端筛选器是「全部」且后端返回了所有数据，可以在这里做额外展示处理
            // 目前后端已处理筛选，直接使用返回结果即可
            return relationships.map((item) => {
              const avatarUrl = getRelationTargetAvatar(item)
              const worldInfo = item.world_usage_id ? worldUsages.find((w: any) => String(w.id) === String(item.world_usage_id)) : null
              return <div key={item.id} style={{ padding: '10px 0', borderBottom: `1px solid ${theme.borderLight}`, display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                {avatarUrl ? <img src={avatarUrl} alt="" style={{ width: 36, height: 36, borderRadius: 6, objectFit: 'cover', background: theme.bgElevated, flexShrink: 0 }} /> : <Avatar size={36} icon={<UserOutlined />} style={{ flexShrink: 0 }} />}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Space size={6} wrap>
                    <Text style={{ color: theme.textPrimary }}>{getRelationTargetName(item)}</Text>
                    <Tag color="cyan" style={{ margin: 0 }}>{item.relation_type || '关系'}</Tag>
                    {worldInfo && <Tag color="geekblue" style={{ margin: 0, fontSize: 11 }}>{worldInfo.world_name || worldInfo.project_title}</Tag>}
                    {item.timeline_phase && <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>{item.timeline_phase}</Tag>}
                    {item.chapter_number && <Tag color="default" style={{ margin: 0, fontSize: 11 }}>第{item.chapter_number}章</Tag>}
                  </Space>
                  {item.related_character_name && item.related_character_name !== getRelationTargetName(item) && (
                    <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>{getRelationTargetName(item)}</Text>
                  )}
                  {item.relation_note && <Paragraph style={{ color: theme.textSecondary, margin: '4px 0 0', fontSize: 13 }}>{item.relation_note}</Paragraph>}
                </div>
                <Space size={2}>
                  <Button type="text" size="small" onClick={() => navigate(`/characters/${item.related_character_id || item.character_id}`)}>查看</Button>
                  <Button type="text" size="small" onClick={() => editRelation(item)}>编辑</Button>
                  <Popconfirm title="删除这条关系？" onConfirm={() => removeRelation(item)}><Button type="text" danger size="small" icon={<DeleteOutlined />} /></Popconfirm>
                </Space>
              </div>
            })
          })() : <div style={{ paddingTop: 12 }}><Text style={{ color: theme.textSecondary }}>暂无关系</Text></div>}
        </div>
      </section>
      <section style={{ padding: '16px 4px', borderBottom: `1px solid ${theme.borderLight}` }}>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>自定义标签</Text>
          <Space wrap size={[6, 6]}>{(character.tags || []).map((tag: string) => <Tag key={tag} closable onClose={(event) => { event.preventDefault(); updateTag(tag, 'DELETE') }} color="blue">{tag}</Tag>)}{!(character.tags || []).length && <Text style={{ color: theme.textSecondary }}>暂无标签</Text>}</Space>
          <Space.Compact style={{ maxWidth: 360 }}><Input size="small" placeholder="添加标签" value={tagInput} onChange={(event) => setTagInput(event.target.value)} onPressEnter={() => { if (tagInput.trim()) { updateTag(tagInput, 'POST'); setTagInput('') } }} /><Button size="small" onClick={() => { if (tagInput.trim()) { updateTag(tagInput, 'POST'); setTagInput('') } }}>添加</Button></Space.Compact>
        </Space>
      </section>
      <section id="character-relationship-graph" style={{ padding: '18px 4px', borderBottom: `1px solid ${theme.borderLight}` }}><details><summary><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>角色关系图谱</Text></summary><div style={{ marginTop: 10 }}><Text style={{ color: theme.textSecondary, fontSize: 12, display: 'block', marginBottom: 6 }}>关系数据与角色详情共用，点击节点切换角色</Text><RelationshipGraph graph={relationshipGraph} theme={theme} onOpen={(id) => navigate(`/characters/${id}`)} /></div></details></section>
      <section style={{ padding: '16px 4px', borderBottom: `1px solid ${theme.borderLight}` }}><details><summary><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>Prompt 资产包</Text>{pack ? <Tag color="blue" style={{ marginInlineStart: 8, marginInlineEnd: 0, fontSize: 11 }}>{[pack.image_prompt, pack.portrait_prompt, pack.character_sheet_prompt, pack.identity_board_prompt, pack.voice_prompt].filter(Boolean).length} 项</Tag> : null}</summary><div className="character-report-prompts" style={{ marginTop: 10 }}>{pack ? [['出图提示词', pack.image_prompt || pack.portrait_prompt], ['设定图提示词', pack.character_sheet_prompt || pack.identity_board_prompt], ['音色提示词', pack.voice_prompt]].map(([label, value]) => <div key={label as string} style={{ minWidth: 0 }}><Text style={{ color: theme.textSecondary, fontSize: 12 }}>{label as string}</Text><Paragraph copyable={{ icon: <CopyOutlined /> }} style={{ color: theme.textPrimary, background: theme.bgElevated, padding: 10, marginTop: 4, minHeight: 74, whiteSpace: 'pre-wrap' }}>{displayValue(value) || '未生成'}</Paragraph></div>) : <Text style={{ color: theme.textSecondary }}>暂无 Prompt 资产包</Text>}</div></details></section>
      <section className="character-report-details" style={{ borderTop: `1px solid ${theme.borderLight}`, marginTop: 4 }}>
        {[
          ['身份设定', identity],
          ['动机设定', motivation],
          ['说话方式', speech],
          ['行为与底线', behavior],
          ['能力设定', character.ability || {}],
          ['角色弧光', character.arc || {}],
          ['音色设定', character.voice || {}],
          ['视觉一致性', { 外观: character.appearance, 服装提示: character.costume_hint, 一致性要求: character.visual_consistency, 标志物: character.signature_items, 表情: character.expressions, 姿态: character.poses }],
          ['来源与使用', { 来源类型: character.source_type_labels || character.source_types, 标签: character.tags, 年龄范围: character.age_range, 流程来源: character.workflow_source_label, 提取来源: (character.extract_origins || []).map((origin: string) => extractOriginLabel(origin)), 世界使用: (worldUsages || []).map((item: any) => `${item.world_name || item.project_title || item.story_id}（${extractOriginLabel(item.extract_origin)}）`) }],
        ].map(([title, values]) => <details key={title as string}><summary>{title as string}</summary><div className="character-report-details-content">{Object.entries((values || {}) as Record<string, any>).map(([label, value]) => <FieldRenderer key={label} label={fieldSourceLabel(label)} value={value} theme={theme} source={character.field_sources?.[label]} />)}</div></details>)}
      </section>
      <section className="character-report-details" style={{ borderTop: `1px solid ${theme.borderLight}`, marginTop: 18 }}>
        {[
          ['切片记录', portraitSlices],
          ['生图日志', portraitLogs],
          ['字段来源', character.field_sources || {}],
        ].map(([title, values]) => <details key={title as string}><summary>{title as string} <span style={{ color: theme.textSecondary, fontSize: 12, fontWeight: 400 }}>（{Array.isArray(values) ? values.length : Object.keys(values || {}).length}）</span></summary><div className="character-report-details-content">{Array.isArray(values) ? renderHistoryRecords(title as string, values) : Object.entries(mapSourceValues(values || {})).map(([label, value]) => <FieldRenderer key={label} label={fieldSourceLabel(label)} value={value} theme={theme} />)}</div></details>)}
      </section>
      <section style={{ marginTop: 18, borderTop: `1px solid ${theme.borderLight}`, padding: '18px 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>世界使用</Text><Button size="small" icon={<PlusOutlined />} onClick={() => { setEditingWorld(null); setWorldForm({ story_id: '', world_name: '', usage_role: '', local_alias: '', local_identity: '', local_faction: '', local_status: 'active', local_costume: '', local_prompt_tags: '', ooc_notes: '', off_model_notes: '', bible_overrides: '{}', visual_overrides: '{}' }); setWorldVisualPortraitUrl(''); setWorldVisualRefUrls(''); setWorldModalOpen(true) }}>添加世界</Button></div>
        {worldUsages.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>{worldUsages.map((item: any) => <div key={item.id} style={{ background: theme.bgCard, border: `1px solid ${theme.borderLight}`, padding: 12, borderRadius: 6 }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Text strong style={{ color: theme.textPrimary }}>{item.world_name || item.project_title || '未命名世界'}</Text><Space size={2}><Button type="text" size="small" onClick={() => openWorldEdit(item)}>编辑</Button><Popconfirm title="移除这条世界使用？" onConfirm={() => removeWorldUsage(item.id)}><Button type="text" danger size="small" icon={<DeleteOutlined />} /></Popconfirm></Space></div><Space size={4} wrap style={{ marginTop: 4 }}><Text style={{ color: theme.textSecondary, fontSize: 12 }}>{item.usage_role || '未设置角色职责'}</Text>{item.extract_origin && item.extract_origin !== 'unknown' ? <Tag color={item.extract_origin === 'original_outline' ? 'gold' : 'green'} style={{ marginInlineEnd: 0, fontSize: 10, lineHeight: '18px' }}>{extractOriginLabel(item.extract_origin)}</Tag> : null}</Space>{item.local_identity && <Paragraph style={{ color: theme.textPrimary, margin: '8px 0 0' }}>{item.local_identity}</Paragraph>}{item.local_costume && <Text style={{ color: theme.textSecondary, fontSize: 12 }}>服装覆盖：{item.local_costume}</Text>}{(item.story_id || item.project_id) && <Button type="link" size="small" icon={<ArrowRightOutlined />} onClick={() => navigate(`/story?project_id=${encodeURIComponent(item.story_id || item.project_id)}`)} style={{ padding: '6px 0 0' }}>打开项目生产线</Button>}</div>)}</div> : <Text style={{ color: theme.textSecondary }}>暂无世界使用记录</Text>}
      </section>

      {/* 剧情演变：角色状态随章节累积变化（数据来自 ProjectStateEntry） */}
      <section style={{ marginTop: 18, borderTop: `1px solid ${theme.borderLight}`, padding: '18px 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, flexWrap: 'wrap', gap: 8 }}>
          <Space size={8}>
            <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>剧情演变</Text>
            <Tag>{characterTimeline?.total_entries || 0} 条变化</Tag>
          </Space>
          <Select
            size="small"
            allowClear
            placeholder="按项目/世界筛选"
            value={timelineProjectId || undefined}
            onChange={(value) => setTimelineProjectId(value || '')}
            style={{ width: 220 }}
            options={[
              { value: '', label: '全部项目' },
              ...worldUsages.map((item: any) => ({ value: item.story_id || item.project_id || '', label: item.world_name || item.project_title || item.story_id || '未命名' })),
            ]}
          />
        </div>
        <Text style={{ color: theme.textSecondary, fontSize: 12, display: 'block', marginBottom: 12 }}>
          项目中写完正文后，系统自动提取的角色状态变化，按章节顺序累积
        </Text>
        {timelineChapters.length ? (
          <div>
            {timelineChapters.map((node: any, index: number) => (
              <div key={node.chapter_number} style={{ display: 'flex', gap: 12 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 10, flexShrink: 0 }}>
                  <div style={{ width: 9, height: 9, borderRadius: '50%', background: theme.primary, marginTop: 5 }} />
                  {index < timelineChapters.length - 1 ? <div style={{ flex: 1, width: 1, background: theme.borderLight, margin: '4px 0' }} /> : null}
                </div>
                <div style={{ flex: 1, minWidth: 0, paddingBottom: 14 }}>
                  <Text strong style={{ color: theme.textPrimary, fontSize: 13 }}>第 {node.chapter_number} 章</Text>
                  <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {(node.entries || []).map((entry: any) => (
                      <div key={entry.id} style={{ display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}>
                        <Tag color={entry.op === 'remove' ? 'red' : entry.op === 'add' ? 'green' : 'blue'} style={{ marginInlineEnd: 0, fontSize: 10, lineHeight: '18px' }}>
                          {entry.op === 'remove' ? '移除' : entry.op === 'add' ? '新增' : '设为'}
                        </Tag>
                        <Text style={{ color: theme.textPrimary, fontSize: 12 }}>{entry.key}</Text>
                        <Text style={{ color: theme.textSecondary, fontSize: 12 }}>{formatStateValue(entry.value)}</Text>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>
            暂无剧情状态变化。在项目中写完正文后，系统会自动提取角色状态变化并出现在这里。
          </Text>
        )}
      </section>
      </>
      )}

      {/* 新建角色时 character 为空，编辑弹窗必须能独立渲染 */}
      <Modal open={editOpen} title={editMode === 'edit' ? `编辑角色 · ${character?.name}` : '新建角色'} width={860} onCancel={() => setEditOpen(false)} confirmLoading={editSaving} onOk={saveEdit} okText={editMode === 'edit' ? '保存修改' : '创建角色'}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
           <div><Text style={{ display: 'block', marginBottom: 4 }}>角色定位</Text><Select style={{ width: '100%' }} value={editForm.role} onChange={(value) => setEditForm((form) => ({ ...form, role: value }))} options={ROLE_OPTIONS} /></div>
           <div><Text style={{ display: 'block', marginBottom: 4 }}>流程来源</Text><Select style={{ width: '100%' }} value={editForm.workflow_source || 'unknown'} onChange={(value) => setEditForm((form) => ({ ...form, workflow_source: value }))} options={WORKFLOW_SOURCE_OPTIONS} /></div>
          {['name', 'age_range', 'source_types', 'appearance', 'costume_hint', 'personality', 'background', 'visual_consistency', 'signature_items', 'expressions', 'poses', 'tags'].map((field) => <div key={field} style={{ gridColumn: ['appearance', 'costume_hint', 'personality', 'background', 'visual_consistency', 'source_types'].includes(field) ? '1 / -1' : undefined }}><Text style={{ display: 'block', marginBottom: 4 }}>{({ name: '名称', age_range: '年龄范围', source_types: '来源类型（逗号分隔）', appearance: '外观', costume_hint: '服装提示', personality: '性格', background: '背景', visual_consistency: '视觉一致性', signature_items: '标志物（逗号分隔）', expressions: '表情（逗号分隔）', poses: '姿态（逗号分隔）', tags: '标签（逗号分隔）' } as any)[field]}</Text><Input.TextArea autoSize={{ minRows: ['appearance', 'costume_hint', 'personality', 'background', 'visual_consistency', 'source_types'].includes(field) ? 2 : 1, maxRows: 6 }} value={editForm[field] || ''} onChange={(event) => setEditForm((form) => ({ ...form, [field]: event.target.value }))} /></div>)}
          <div style={{ gridColumn: '1 / -1', borderTop: `1px solid ${theme.borderLight}`, paddingTop: 12 }}><Text strong style={{ color: theme.textPrimary }}>完整设定 JSON（保留旧角色详情中的扩展字段）</Text><div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 8 }}>{[['identity', '身份设定'], ['motivation', '动机设定'], ['speech', '说话方式'], ['behavior', '行为与底线'], ['ability', '能力设定'], ['arc', '角色弧光'], ['voice', '音色设定']].map(([field, label]) => <div key={field}><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>{label}</Text><Input.TextArea rows={4} value={editForm[field] || '{}'} onChange={(event) => setEditForm((form) => ({ ...form, [field]: event.target.value }))} /></div>)}</div></div>
          {/* 视觉档案：结构化编辑（中文标签 + 值），存回 JSON */}
          <div style={{ gridColumn: '1 / -1', borderTop: `1px solid ${theme.borderLight}`, paddingTop: 12 }}>
            <Space size={6}>
              <Text strong style={{ color: theme.textPrimary }}>视觉档案</Text>
              <Button size="small" type="link" onClick={() => { const vp = (() => { try { return JSON.parse(editForm.visual_profile || '{}') } catch { return {} } })(); setEditForm((form) => ({ ...form, visual_profile: JSON.stringify(vp, null, 2) })) }}>重置格式</Button>
            </Space>
            <div style={{ marginTop: 8, maxHeight: 320, overflowY: 'auto', border: `1px solid ${theme.borderLight}`, borderRadius: 6, padding: 10, background: theme.bgElevated }}>
              {(() => {
                let parsed: Record<string, any> = {}
                try { parsed = JSON.parse(editForm.visual_profile || '{}') } catch { parsed = {} }
                const entries = Object.entries(parsed)
                if (!entries.length) return <Text style={{ color: theme.textDisabled, fontSize: 12 }}>暂无数据</Text>
                return entries.map(([key, value]) => (
                  <div key={key} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: entries[entries.length - 1][0] !== key ? `1px solid ${theme.borderLight}` : undefined }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <Text style={{ color: theme.textSecondary, fontSize: 11, minWidth: 80 }}>{visualProfileFieldLabel(key)}</Text>
                      <Tag style={{ margin: 0, fontSize: 9, fontFamily: 'monospace' }}>{key}</Tag>
                      <Popconfirm title="删除此字段？" onConfirm={() => { const copy = { ...parsed }; delete copy[key]; setEditForm((form) => ({ ...form, visual_profile: JSON.stringify(copy, null, 2) })) }} okText="删除" cancelText="取消"><Button type="text" danger size="small" icon={<DeleteOutlined />} style={{ fontSize: 10, marginLeft: 'auto' }} /></Popconfirm>
                    </div>
                    <Input.TextArea
                      autoSize={{ minRows: 1, maxRows: 4 }}
                      value={typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                      onChange={(event) => {
                        let raw = event.target.value
                        // 尝试解析为对象/数组，否则存字符串
                        let parsedValue: any = raw
                        if (raw.startsWith('{') || raw.startsWith('[')) {
                          try { parsedValue = JSON.parse(raw) } catch { /* 保持原始字符串 */ }
                        }
                        setEditForm((form) => ({ ...form, visual_profile: JSON.stringify({ ...parsed, [key]: parsedValue }, null, 2) }))
                      }}
                    />
                  </div>
                ))
              })()}
              {/* 添加新字段 */}
              <div style={{ marginTop: 8, display: 'flex', gap: 6, alignItems: 'center' }}>
                <Input placeholder="新字段名（英文 key）" size="small" style={{ width: 140 }} id="vp-new-key" />
                <Input.TextArea placeholder="值" size="small" autoSize={{ minRows: 1, maxRows: 2 }} style={{ flex: 1 }} id="vp-new-value" />
                <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={() => {
                  const keyEl = document.getElementById('vp-new-key') as HTMLInputElement | null
                  const valEl = document.getElementById('vp-new-value') as HTMLTextAreaElement | null
                  const newKey = (keyEl?.value || '').trim()
                  if (!newKey) return
                  let parsed: Record<string, any> = {}
                  try { parsed = JSON.parse(editForm.visual_profile || '{}') } catch { parsed = {} }
                  let newVal: any = valEl?.value || ''
                  if (newVal.startsWith('{') || newVal.startsWith('[')) { try { newVal = JSON.parse(newVal) } catch { /* string */ } }
                  setEditForm((form) => ({ ...form, visual_profile: JSON.stringify({ ...parsed, [newKey]: newVal }, null, 2) }))
                  if (keyEl) keyEl.value = ''
                  if (valEl) valEl.value = ''
                }}>添加</Button>
              </div>
            </div>
          </div>
        </div>
      </Modal>
      {/* 以下弹窗均依赖已有角色数据，仅在 character 存在时渲染 */}
      {character && (<>
      <Modal open={referenceOpen} title="加入角色参考图" footer={null} width={900} onCancel={() => setReferenceOpen(false)}>
        <Tabs items={[{ key: 'assets', label: '素材库图片', children: <Space direction="vertical" style={{ width: '100%' }} size={10}><Input.Search allowClear placeholder="搜索标题、标签或来源" value={referenceSearch} onChange={(event) => setReferenceSearch(event.target.value)} onSearch={(value) => loadReferenceAssets(value)} enterButton="搜索" /><Spin spinning={referenceLoading}><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10, minHeight: 180 }}>{referenceAssets.length ? referenceAssets.map((asset: any) => { const url = asset.thumbnail_url || asset.preview_url || asset.url || asset.file_url; return <button key={asset.id} type="button" onClick={() => addReferenceAsset(asset)} style={{ padding: 6, textAlign: 'left', border: `1px solid ${theme.borderLight}`, background: theme.bgElevated, cursor: 'pointer', color: theme.textPrimary }}>{url ? <img src={url} alt="" style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', display: 'block' }} /> : <div style={{ aspectRatio: '1 / 1', display: 'grid', placeItems: 'center' }}><PictureOutlined /></div>}<Text ellipsis style={{ display: 'block', marginTop: 5, color: theme.textPrimary, fontSize: 12 }}>{asset.title || asset.id}</Text><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 11 }}>{asset.source_type || '素材库图片'}</Text></button> }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有找到图片素材" />}</div></Spin></Space> }, { key: 'versions', label: `历史立绘版本 (${portraitVersions.length})`, children: portraitVersions.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>{portraitVersions.map((version: any) => { const url = version.image_url || version.url || version.file_path; return <div key={version.id} style={{ padding: 6, border: `1px solid ${theme.borderLight}`, background: theme.bgElevated }}>{url ? <Image src={url} width="100%" height={120} style={{ objectFit: 'cover' }} /> : <div style={{ height: 120, display: 'grid', placeItems: 'center' }}><PictureOutlined /></div>}<Text style={{ display: 'block', color: theme.textPrimary, fontSize: 12, marginTop: 5 }}>V{version.version_number || '?'}</Text><Button size="small" block style={{ marginTop: 5 }} disabled={!url} onClick={() => addReferenceVersion(version)}>加入参考</Button></div> })}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史立绘版本" /> }]} />
      </Modal>
      <Modal open={promptPreviewOpen} title="角色生图 Prompt 预览" footer={null} width={860} onCancel={() => setPromptPreviewOpen(false)}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}><div><Text strong style={{ color: theme.textPrimary }}>正向提示词</Text><Paragraph copyable style={{ whiteSpace: 'pre-wrap', background: theme.bgElevated, padding: 12, color: theme.textPrimary }}>{displayValue(promptPreview?.prompt) || '暂无'}</Paragraph></div><div><Text strong style={{ color: theme.textPrimary }}>参考图（{portraitMode === 'img2img' ? selectedReferenceUrls.length : 0} 张）</Text>{portraitMode === 'img2img' && selectedReferenceUrls.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))', gap: 8, marginTop: 6 }}>{selectedReferenceUrls.map((url: string, index: number) => <div key={url} style={{ position: 'relative', border: `1px solid ${theme.borderLight}`, borderRadius: 6, overflow: 'hidden' }}><img src={url} alt="" style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', display: 'block' }} /><Tag color="blue" style={{ position: 'absolute', top: 2, left: 2, margin: 0, fontSize: 10 }}>图 {index + 1}</Tag></div>)}</div> : <Paragraph style={{ color: theme.textSecondary, marginTop: 4 }}>本次为文生图，不携带参考图。</Paragraph>}</div><Text style={{ color: theme.textSecondary }}>预览只生成参数，不会创建图片或版本。</Text></Space>
      </Modal>
      <Modal
        open={deleteConfirmOpen}
        title="删除角色"
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={aiBusy}
        onCancel={() => setDeleteConfirmOpen(false)}
        onOk={async () => { await deleteCharacter(); setDeleteConfirmOpen(false) }}
      >
        <Text style={{ color: theme.textPrimary }}>确认删除「{character.name}」？该操作不可恢复，相关立绘版本与关系记录将一并移除。</Text>
      </Modal>
      <Modal open={worldModalOpen} title={editingWorld ? '编辑世界使用' : '添加世界使用'} width={860} onCancel={() => { setWorldModalOpen(false); setEditingWorld(null) }} onOk={saveWorldUsage} confirmLoading={worldSaving} okText="保存">
        <Space direction="vertical" style={{ width: '100%' }} size={10}>{!editingWorld && <Select showSearch optionFilterProp="label" placeholder="选择创作项目（必选）" value={worldForm.story_id || undefined} onChange={(value) => { const project = projects.find((item) => item.id === value); setWorldForm((form) => ({ ...form, story_id: value, world_name: form.world_name || project?.title || '' })) }} options={projects.map((item) => ({ value: item.id, label: item.title || item.name || item.id }))} />}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><Input placeholder="世界/项目名称" value={worldForm.world_name} onChange={(event) => setWorldForm((form) => ({ ...form, world_name: event.target.value }))} /><Input placeholder="角色职责：主角/NPC/反派" value={worldForm.usage_role} onChange={(event) => setWorldForm((form) => ({ ...form, usage_role: event.target.value }))} /><Input placeholder="本世界别名/代号" value={worldForm.local_alias} onChange={(event) => setWorldForm((form) => ({ ...form, local_alias: event.target.value }))} /><Input placeholder="阵营/组织/派系" value={worldForm.local_faction} onChange={(event) => setWorldForm((form) => ({ ...form, local_faction: event.target.value }))} /><Select value={worldForm.local_status} onChange={(value) => setWorldForm((form) => ({ ...form, local_status: value }))} options={[{ value: 'active', label: '启用' }, { value: 'draft', label: '草稿' }, { value: 'archived', label: '归档' }]} /></div>
          <Input.TextArea placeholder="该世界中的身份说明" value={worldForm.local_identity} onChange={(event) => setWorldForm((form) => ({ ...form, local_identity: event.target.value }))} />
          <Input.TextArea placeholder="服装/形态覆盖（文字描述）" value={worldForm.local_costume} onChange={(event) => setWorldForm((form) => ({ ...form, local_costume: event.target.value }))} />
          <div style={{ padding: '10px 12px', background: theme.bgElevated, borderRadius: 6, border: `1px dashed ${theme.borderLight}` }}>
            <Text style={{ color: theme.textPrimary, fontSize: 13 }}><PictureOutlined /> 世界专属视觉（可选）</Text>
            <div style={{ fontSize: 12, color: theme.textSecondary, marginTop: 4, marginBottom: 8 }}>切换到这个世界视角时，会优先显示这里配置的立绘和参考图；不填则使用角色全局基准图。</div>
            <Input
              placeholder="世界专属立绘 URL（粘贴 /static/... 或完整URL）"
              value={worldVisualPortraitUrl}
              onChange={(event) => setWorldVisualPortraitUrl(event.target.value)}
              prefix={<PictureOutlined style={{ color: theme.textSecondary }} />}
            />
            <Input.TextArea
              rows={3}
              placeholder="世界专属参考图 URL，每行一个（会和全局参考图合并展示）"
              value={worldVisualRefUrls}
              onChange={(event) => setWorldVisualRefUrls(event.target.value)}
              style={{ marginTop: 8 }}
            />
            {worldVisualPortraitUrl && (
              <div style={{ marginTop: 8 }}>
                <Text style={{ fontSize: 12, color: theme.textSecondary }}>预览：</Text>
                <img src={worldVisualPortraitUrl} alt="立绘预览" style={{ maxWidth: 140, maxHeight: 140, objectFit: 'contain', display: 'block', marginTop: 4, border: `1px solid ${theme.borderLight}`, borderRadius: 4, background: '#000' }} />
              </div>
            )}
          </div>
          <Input.TextArea placeholder="局部 Prompt 标签，逗号或换行分隔" value={worldForm.local_prompt_tags} onChange={(event) => setWorldForm((form) => ({ ...form, local_prompt_tags: event.target.value }))} />
          <Input.TextArea rows={3} placeholder="OOC 约束：不能做什么、不能说什么" value={worldForm.ooc_notes} onChange={(event) => setWorldForm((form) => ({ ...form, ooc_notes: event.target.value }))} />
          <Input.TextArea rows={3} placeholder="出模约束：外观、服装、比例、道具不能画错" value={worldForm.off_model_notes} onChange={(event) => setWorldForm((form) => ({ ...form, off_model_notes: event.target.value }))} />
          <details>
            <summary style={{ cursor: 'pointer', color: theme.textSecondary, fontSize: 12 }}>高级：Bible / 视觉覆盖 JSON（进阶覆盖，会与上面字段自动合并）</summary>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 8 }}><div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>Bible 覆盖 JSON</Text><Input.TextArea rows={5} value={worldForm.bible_overrides} onChange={(event) => setWorldForm((form) => ({ ...form, bible_overrides: event.target.value }))} /></div><div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>视觉覆盖 JSON（会与上方URL字段合并）</Text><Input.TextArea rows={5} value={worldForm.visual_overrides} onChange={(event) => setWorldForm((form) => ({ ...form, visual_overrides: event.target.value }))} /></div></div>
          </details>
        </Space>
      </Modal>
      <Modal open={sliceModalOpen} title="生成立绘切片" onCancel={() => setSliceModalOpen(false)} onOk={slicePortrait} confirmLoading={sliceBusy} okText="生成切片">
        <Space direction="vertical" style={{ width: '100%' }} size={10}>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>{sliceTargetVersion ? recommendedSlice(sliceTargetVersion.preset).hint : '选择切片行列，切片会进入素材中枢并保留来源版本血缘。'}</Text>
          <Space size={10} wrap>
            <Select value={sliceRows} onChange={setSliceRows} options={[1, 2, 3, 4, 5, 6].map((value) => ({ value, label: `${value} 行` }))} style={{ width: 108 }} />
            <Select value={sliceCols} onChange={setSliceCols} options={[1, 2, 3, 4, 5, 6].map((value) => ({ value, label: `${value} 列` }))} style={{ width: 108 }} />
          </Space>
          <Text style={{ color: theme.textSecondary, fontSize: 12 }}>切片会进入素材中枢并保留来源版本血缘，之后会自动归入上方「视图矩阵」对应分类。</Text>
        </Space>
      </Modal>
      <Modal open={relationModalOpen} title={editingRelation ? '编辑角色关系' : '添加角色关系'} onCancel={() => { setRelationModalOpen(false); setEditingRelation(null); }} onOk={saveRelation} confirmLoading={relationSaving} okText="保存" width={520}>
        <Space direction="vertical" style={{ width: '100%' }} size={10}>
          <Select
            showSearch
            optionFilterProp="label"
            style={{ width: '100%' }}
            placeholder="选择关联角色"
            value={relationForm.related_character_id || undefined}
            onChange={(value) => setRelationForm((form) => ({ ...form, related_character_id: value }))}
            options={characters.filter((item) => item.id !== character?.id).map((item) => ({ value: item.id, label: item.name }))}
          />
          <Input
            placeholder="关系类型，如盟友、敌人、师徒、战友"
            value={relationForm.relation_type}
            onChange={(event) => setRelationForm((form) => ({ ...form, relation_type: event.target.value }))}
          />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="归属世界（不选=全局通用）"
              value={relationForm.world_usage_id || undefined}
              onChange={(value) => setRelationForm((form) => ({ ...form, world_usage_id: value || null }))}
              options={[
                { value: '', label: '全局关系（所有世界通用）' },
                ...worldUsages.map((w: any) => ({ value: String(w.id), label: w.world_name || w.project_title || '未命名世界' })),
              ]}
            />
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="时间阶段（可选）"
              value={relationForm.timeline_phase || undefined}
              onChange={(value) => setRelationForm((form) => ({ ...form, timeline_phase: value || '' }))}
              options={[
                { value: '前期', label: '故事前期' },
                { value: '中期', label: '故事中期' },
                { value: '后期', label: '故事后期' },
                { value: '回忆', label: '回忆/过去' },
                { value: '未来', label: '未来/结局' },
              ]}
            />
          </div>
          <InputNumber
            style={{ width: '100%' }}
            placeholder="章节号（可选，标记关系变化的章节）"
            min={1}
            value={relationForm.chapter_number ?? undefined}
            onChange={(value) => setRelationForm((form) => ({ ...form, chapter_number: value ? Number(value) : null }))}
          />
          <Input.TextArea
            placeholder="关系说明（可选，补充细节）"
            rows={3}
            value={relationForm.relation_note}
            onChange={(event) => setRelationForm((form) => ({ ...form, relation_note: event.target.value }))}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            提示：不选世界时，这条关系会在所有世界视角下显示；选了具体世界后，只在该世界视角下额外显示这条特定关系。
          </Text>
        </Space>
      </Modal>
      </>
      )}
      </main>
    </div>
  </div>
}
