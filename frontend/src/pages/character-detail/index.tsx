import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Alert, Avatar, Button, Card, Col, Collapse, Empty, Image, Input, Modal, Popconfirm, Row, Select, Space, Spin, Tabs, Tag, Typography, message } from 'antd'
import { ArrowLeftOutlined, ArrowRightOutlined, BranchesOutlined, CopyOutlined, DatabaseOutlined, DeleteOutlined, EditOutlined, PictureOutlined, PlusOutlined, SearchOutlined, StarFilled, StarOutlined, UserOutlined } from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { chat } from '../../api'

const { Title, Text, Paragraph } = Typography

type Character = Record<string, any>

function displayValue(value: any): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.filter(Boolean).map((item) => displayValue(item)).filter(Boolean).join('、')
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}：${displayValue(item)}`).join('\n')
  return String(value)
}

function browserAssetUrl(value: unknown): string {
  const text = String(value || '').trim()
  if (!text || text.startsWith('/api/') || text.startsWith('http://') || text.startsWith('https://') || text.startsWith('data:')) return text
  return `/api/v1/assets/download?path=${encodeURIComponent(text)}`
}

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

const getJson = async (url: string) => {
  const response = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`请求失败：${response.status}`)
  return response.json()
}

function fieldSourceMeta(source: unknown): { label: string; color: string } | null {
  const normalized = String(source || '').trim().toLowerCase()
  if (!normalized) return null
  if (['original', 'source', 'novel', '原文', '原始'].some((value) => normalized.includes(value))) return { label: '原文', color: 'green' }
  if (['ai_inferred', 'inferred', 'ai', '推断', '推测'].some((value) => normalized.includes(value))) return { label: 'AI 推断', color: 'gold' }
  if (['user', 'manual', '用户', '手填'].some((value) => normalized.includes(value))) return { label: '用户填写', color: 'blue' }
  return { label: String(source), color: 'default' }
}

function Field({ label, value, theme, source }: { label: string; value: any; theme: any; source?: unknown }) {
  const sourceMeta = fieldSourceMeta(source)
  return <div style={{ padding: '12px 0', borderBottom: `1px solid ${theme.borderLight}` }}>
    <Space size={6} align="center"><Text style={{ color: theme.textSecondary, fontSize: 12 }}>{label}</Text>{sourceMeta ? <Tag color={sourceMeta.color} style={{ marginInlineEnd: 0, fontSize: 10, lineHeight: '18px' }}>{sourceMeta.label}</Tag> : null}</Space>
    <Paragraph style={{ color: value ? theme.textPrimary : theme.textDisabled, margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{displayValue(value) || '未设置'}</Paragraph>
  </div>
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
  const [projects, setProjects] = useState<any[]>([])
  const [aiBusy, setAiBusy] = useState(false)
  const [relationModalOpen, setRelationModalOpen] = useState(false)
  const [editingRelation, setEditingRelation] = useState<any | null>(null)
  const [relationSaving, setRelationSaving] = useState(false)
  const [relationForm, setRelationForm] = useState({ related_character_id: '', relation_type: '', relation_note: '', is_directed: false })
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
  const [promptPreviewOpen, setPromptPreviewOpen] = useState(false)
  const [promptPreviewLoading, setPromptPreviewLoading] = useState(false)
  const [promptOptimizing, setPromptOptimizing] = useState(false)
  const [imageBackends, setImageBackends] = useState<any[]>([])
  const [llmBackends, setLlmBackends] = useState<any[]>([])
  const [enrichProvider, setEnrichProvider] = useState('')
  const [enrichModel, setEnrichModel] = useState('')
  const [portraitProvider, setPortraitProvider] = useState('')
  const [portraitModel, setPortraitModel] = useState('')
  const [characters, setCharacters] = useState<Character[]>([])
  const [characterKeyword, setCharacterKeyword] = useState('')
  const [characterRole, setCharacterRole] = useState<string>()
  const [characterSource, setCharacterSource] = useState<string>()
  const [characterWorkflowSource, setCharacterWorkflowSource] = useState<string>()
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [tagInput, setTagInput] = useState('')
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
      setEditForm({ name: '', role: 'supporting', workflow_source: 'character_first', source_types: 'ai_generated', appearance: '', costume_hint: '', personality: '', background: '', age_range: '', visual_consistency: '', signature_items: '', expressions: '', poses: '', tags: '', identity: '{}', motivation: '{}', speech: '{}', behavior: '{}', ability: '{}', arc: '{}', visual_profile: '{}' })
      setEditOpen(true)
      return
    }
    setLoading(true)
    Promise.all([
      getJson(`/api/v1/characters/${characterId}`),
      getJson(`/api/v1/characters/${characterId}/prompt-pack`),
      getJson(`/api/v1/characters/${characterId}/relationships`),
      getJson('/api/v1/characters/relationships/graph'),
      getJson('/api/v1/characters?limit=100'),
      getJson(`/api/v1/characters/${characterId}/world-usages`),
      getJson(`/api/v1/characters/${characterId}/portrait/versions`),
      getJson(`/api/v1/characters/${characterId}/portrait/slices`),
      getJson(`/api/v1/logs?scene=character_portrait&ref_id=${characterId}&limit=50`),
      getJson('/api/v1/creative-projects?limit=200'),
    ]).then(([characterRes, packRes, relationRes, graphRes, charactersRes, worldsRes, versionsRes, slicesRes, logsRes, projectsRes]) => {
      setCharacter(characterRes.data || characterRes)
      setPack(packRes.data || packRes)
      setRelationships(relationRes.data || [])
      setRelationshipGraph({ ...(graphRes.data || graphRes), focus_id: characterId })
      setCharacters(charactersRes.data?.items || charactersRes.items || charactersRes.data || [])
      setWorldUsages(worldsRes.data || worldsRes.items || [])
      setPortraitVersions(versionsRes.data?.versions || [])
      setPortraitSlices(slicesRes.data?.items || [])
      setPortraitLogs(logsRes.data || logsRes.items || [])
      setProjects(projectsRes.data || projectsRes.items || [])
      const loadedCharacter = characterRes.data || characterRes
      const loadedProfile = loadedCharacter?.identity?.visual_profile || {}
      setSelectedVisualUrl(loadedProfile.identity_reference_url || loadedCharacter?.portrait_url || '')
      const mainVersionId = loadedProfile.identity_reference_version_id
      const mainVersion = (versionsRes.data?.versions || []).find((item: any) => String(item.id) === String(mainVersionId) || item.is_main)
      if (mainVersion) setSelectedVersionId(String(mainVersion.id))
    }).catch((e) => setError(e.message || '角色加载失败')).finally(() => setLoading(false))
  }, [characterId])
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

  const canonicalMainVisualUrl = useMemo(() => {
    const profile = character?.identity?.visual_profile || {}
    return browserAssetUrl(profile.identity_reference_url || character?.portrait_url || '')
  }, [character])
  const mainVisualUrl = selectedVisualUrl || canonicalMainVisualUrl
  const isPreviewVisual = Boolean(selectedVisualUrl && canonicalMainVisualUrl && selectedVisualUrl !== canonicalMainVisualUrl)
  const selectedVersion = portraitVersions.find((version: any) => String(version.id) === String(selectedVersionId))
  const referenceImages = useMemo(() => {
    if (!character) return []
    const profile = character.identity?.visual_profile || {}
    const main = browserAssetUrl(profile.identity_reference_url || character.portrait_url || '')
    return Array.from(new Set((profile.reference_image_urls || []).map((url: any) => browserAssetUrl(url)).filter((url: string) => Boolean(url) && url !== main)))
  }, [character])
  const visualImages = useMemo(() => Array.from(new Set([mainVisualUrl, ...referenceImages].filter(Boolean))), [mainVisualUrl, referenceImages])
  const restoreMainVisual = () => {
    setSelectedVisualUrl(canonicalMainVisualUrl)
    setSelectedVersionId('')
  }

  const filteredCharacters = useMemo(() => characters.filter((item) => {
    const keywordMatch = !characterKeyword.trim() || String(item.name || '').toLowerCase().includes(characterKeyword.trim().toLowerCase())
    const roleMatch = !characterRole || item.role === characterRole
    const sourceMatch = !characterSource || (item.source_types || []).includes(characterSource)
    const workflowMatch = !characterWorkflowSource || (item.workflow_source || 'unknown') === characterWorkflowSource
    const favoriteMatch = !favoritesOnly || Boolean(item.is_favorite)
    return keywordMatch && roleMatch && sourceMatch && workflowMatch && favoriteMatch
  }), [characters, characterKeyword, characterRole, characterSource, characterWorkflowSource, favoritesOnly])

  if (loading) return <div style={{ minHeight: '70vh', display: 'grid', placeItems: 'center' }}><Spin size="large" /></div>
  if (error || !character) return <div style={{ padding: 32 }}><Alert type="error" message={error || '角色不存在'} showIcon /><Button style={{ marginTop: 16 }} icon={<ArrowLeftOutlined />} onClick={() => navigate('/characters')}>返回角色库</Button></div>

  const identity = character.identity || {}
  const motivation = character.motivation || {}
  const speech = character.speech || {}
  const behavior = character.behavior || {}
  const relationTarget = (item: any) => item.related_character_name || item.related_character_id || item.character_id
  const openEdit = () => {
    if (!character) return
    setEditForm({
      name: character.name || '', role: character.role || 'supporting', workflow_source: character.workflow_source || 'unknown', source_types: (character.source_types || []).join(', '),
      appearance: character.appearance || '', personality: character.personality || '', costume_hint: character.costume_hint || '',
      background: character.background || '', age_range: character.age_range || '', visual_consistency: character.visual_consistency || '',
      signature_items: (character.signature_items || []).join(', '), expressions: (character.expressions || []).join(', '), poses: (character.poses || []).join(', '),
      tags: (character.tags || []).join(', '), identity: JSON.stringify(character.identity || {}, null, 2), motivation: JSON.stringify(character.motivation || {}, null, 2),
      speech: JSON.stringify(character.speech || {}, null, 2), behavior: JSON.stringify(character.behavior || {}, null, 2), ability: JSON.stringify(character.ability || {}, null, 2), arc: JSON.stringify(character.arc || {}, null, 2), visual_profile: JSON.stringify(character.identity?.visual_profile || {}, null, 2),
    })
    setEditMode('edit')
    setEditOpen(true)
  }
  const openCreate = () => {
    setEditMode('create')
    setEditForm({ name: '', role: 'supporting', workflow_source: 'character_first', source_types: 'ai_generated', appearance: '', costume_hint: '', personality: '', background: '', age_range: '', visual_consistency: '', signature_items: '', expressions: '', poses: '', tags: '', identity: '{}', motivation: '{}', speech: '{}', behavior: '{}', ability: '{}', arc: '{}' })
    setEditOpen(true)
  }
  const saveEdit = async () => {
    if (!character) return
    setEditSaving(true)
    try {
      const parseJson = (value: string) => { try { return value?.trim() ? JSON.parse(value) : {} } catch { throw new Error('身份、动机等 JSON 字段格式不正确') } }
      const payload = {
        name: editForm.name, role: editForm.role, workflow_source: editForm.workflow_source || 'unknown', source_types: String(editForm.source_types || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), appearance: editForm.appearance, personality: editForm.personality, costume_hint: editForm.costume_hint, background: editForm.background, age_range: editForm.age_range, visual_consistency: editForm.visual_consistency, signature_items: String(editForm.signature_items || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), expressions: String(editForm.expressions || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), poses: String(editForm.poses || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), tags: String(editForm.tags || '').split(/[,，]/).map((item) => item.trim()).filter(Boolean), identity: { ...parseJson(editForm.identity), visual_profile: parseJson(editForm.visual_profile) }, motivation: parseJson(editForm.motivation), speech: parseJson(editForm.speech), behavior: parseJson(editForm.behavior), ability: parseJson(editForm.ability), arc: parseJson(editForm.arc),
      }
      const response = await fetch(editMode === 'edit' ? `/api/v1/characters/${character.id}` : '/api/v1/characters', { method: editMode === 'edit' ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(payload) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '保存角色失败')
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
      const payload = { story_id: worldForm.story_id.trim(), world_name: worldForm.world_name.trim(), usage_role: worldForm.usage_role, local_alias: worldForm.local_alias, local_identity: worldForm.local_identity, local_faction: worldForm.local_faction, local_status: worldForm.local_status, local_costume: worldForm.local_costume, local_prompt_tags: worldForm.local_prompt_tags.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean), ooc_notes: worldForm.ooc_notes, off_model_notes: worldForm.off_model_notes, bible_overrides: parseJson(worldForm.bible_overrides, 'Bible 覆盖'), visual_overrides: parseJson(worldForm.visual_overrides, '视觉覆盖') }
      const response = await fetch(editingWorld ? `/api/v1/characters/${character.id}/world-usages/${editingWorld.id}` : `/api/v1/characters/${character.id}/link-story`, { method: editingWorld ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(editingWorld ? { world_name: payload.world_name, usage_role: payload.usage_role, local_alias: payload.local_alias, local_identity: payload.local_identity, local_faction: payload.local_faction, local_status: payload.local_status, local_costume: payload.local_costume, local_prompt_tags: payload.local_prompt_tags, ooc_notes: payload.ooc_notes, off_model_notes: payload.off_model_notes, bible_overrides: payload.bible_overrides, visual_overrides: payload.visual_overrides } : payload) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '保存世界使用失败')
      const refreshed = await getJson(`/api/v1/characters/${character.id}/world-usages`)
      setWorldUsages(refreshed.data || [])
      setWorldModalOpen(false)
      setEditingWorld(null)
      setWorldForm({ story_id: '', world_name: '', usage_role: '', local_alias: '', local_identity: '', local_faction: '', local_status: 'active', local_costume: '', local_prompt_tags: '', ooc_notes: '', off_model_notes: '', bible_overrides: '{}', visual_overrides: '{}' })
      message.success('已加入世界使用')
    } catch (error: any) { message.error(error?.message || '保存世界使用失败') } finally { setWorldSaving(false) }
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
  const removeWorldUsage = async (usageId: string) => {
    if (!character) return
    const response = await fetch(`/api/v1/characters/${character.id}/world-usages/${usageId}`, { method: 'DELETE', headers: { Accept: 'application/json' } })
    if (!response.ok) { message.error('删除世界使用失败'); return }
    setWorldUsages((items) => items.filter((item) => item.id !== usageId))
    message.success('已移除世界使用')
  }
  const openWorldEdit = (item: any) => {
    setEditingWorld(item)
    setWorldForm({ story_id: item.story_id || item.project_id || '', world_name: item.world_name || item.project_title || '', usage_role: item.usage_role || '', local_alias: item.local_alias || '', local_identity: item.local_identity || '', local_faction: item.local_faction || '', local_status: item.local_status || 'active', local_costume: item.local_costume || '', local_prompt_tags: Array.isArray(item.local_prompt_tags) ? item.local_prompt_tags.join(', ') : '', ooc_notes: item.ooc_notes || '', off_model_notes: item.off_model_notes || '', bible_overrides: JSON.stringify(item.bible_overrides || {}, null, 2), visual_overrides: JSON.stringify(item.visual_overrides || {}, null, 2) })
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
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/prompt-preview`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ preset: portraitPreset, negative_override: portraitNegativePrompt }) })
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
      const generationReferences = Array.from(new Set([canonicalMainVisualUrl, ...referenceImages].filter(Boolean)))
      const response = await fetch(`/api/v1/characters/${character.id}/portrait/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ prompt: portraitPrompt, provider: portraitProvider || undefined, model: portraitModel || undefined, negative_prompt: portraitNegativePrompt, preset: portraitPreset, size: portraitSize, reference_images: generationReferences, set_as_main: true }) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '角色生图失败')
      const saved = result.data?.character || result.character
      if (saved) {
        setCharacter(saved)
        setCharacters((items) => items.map((item) => item.id === saved.id ? { ...item, ...saved } : item))
        setSelectedVisualUrl(saved.identity?.visual_profile?.identity_reference_url || saved.portrait_url || '')
      }
      const [versions, logs] = await Promise.all([getJson(`/api/v1/characters/${character.id}/portrait/versions`), getJson(`/api/v1/logs?scene=character_portrait&ref_id=${character.id}&limit=50`),])
      setPortraitVersions(versions.data?.versions || [])
      setPortraitLogs(logs.data || logs.items || [])
      message.success('角色立绘已生成并设为主视图')
    } catch (error: any) { message.error(error?.message || '角色生图失败') } finally { setAiBusy(false) }
  }
  const saveRelation = async () => {
    if (!character || !relationForm.related_character_id || !relationForm.relation_type.trim()) { message.warning('请选择关联角色并填写关系类型'); return }
    setRelationSaving(true)
    try {
      const response = await fetch(editingRelation ? `/api/v1/characters/${character.id}/relationships/${editingRelation.id}` : `/api/v1/characters/${character.id}/relationships`, { method: editingRelation ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(relationForm) })
      const result = await response.json()
      if (!response.ok || result?.success === false) throw new Error(result?.detail || '保存关系失败')
      const refreshed = await getJson(`/api/v1/characters/${character.id}/relationships`)
      setRelationships(refreshed.data || [])
      const refreshedGraph = await getJson('/api/v1/characters/relationships/graph')
      setRelationshipGraph({ ...(refreshedGraph.data || refreshedGraph), focus_id: character.id })
      setRelationModalOpen(false)
      setRelationForm({ related_character_id: '', relation_type: '', relation_note: '', is_directed: false })
      message.success(editingRelation ? '关系已更新' : '关系已添加')
    } catch (error: any) { message.error(error?.message || '保存关系失败') } finally { setRelationSaving(false) }
  }
  const editRelation = (item: any) => { setEditingRelation(item); setRelationForm({ related_character_id: item.related_character_id || '', relation_type: item.relation_type || '', relation_note: item.relation_note || '', is_directed: Boolean(item.is_directed) }); setRelationModalOpen(true) }
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
  return <div style={{ minHeight: '100%', background: theme.bgPage, padding: 18 }}>
    <style>{`.character-detail-shell{max-width:1600px;margin:0 auto;display:grid;grid-template-columns:260px minmax(0,1fr);gap:18px;align-items:start}.character-detail-sidebar{position:sticky;top:18px;min-height:calc(100vh - 36px);max-height:calc(100vh - 36px);overflow:hidden}.character-detail-sidebar-list{max-height:calc(100vh - 170px);overflow-y:auto;padding-right:3px}.character-report-hero{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(260px,.85fr);gap:18px}.character-report-media{display:grid;grid-template-columns:minmax(220px,.9fr) minmax(0,1.4fr);gap:10px;min-height:470px}.character-report-lower{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px}.character-report-prompts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.character-report-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}.character-report-details details{border-bottom:1px solid rgba(255,255,255,.1);padding:12px 0}.character-report-details summary{cursor:pointer;color:var(--character-text-primary,#e4e4e7);font-weight:600}.character-report-details details[open] summary{color:#22d3ee}.character-report-details-content{padding-top:10px}.character-portrait-controls{display:grid;grid-template-columns:190px 180px 150px 150px minmax(0,1fr) auto;gap:10px;align-items:end}@media(max-width:1100px){.character-portrait-controls{grid-template-columns:repeat(3,minmax(0,1fr))}.character-portrait-controls>*:nth-child(5){grid-column:1 / -1}.character-portrait-controls>*:nth-child(6){grid-column:1 / -1}}@media(max-width:900px){.character-detail-shell{display:block}.character-detail-sidebar{position:static;min-height:0;max-height:none;margin-bottom:16px}.character-detail-sidebar-list{max-height:320px}.character-report-hero,.character-report-lower,.character-report-details{display:block}.character-report-hero>div+div{border-left:0!important;border-top:1px solid rgba(255,255,255,.1);padding:18px 0 0!important;margin-top:18px}.character-report-media{grid-template-columns:1fr;min-height:0}.character-report-prompts{grid-template-columns:1fr}.character-portrait-controls{grid-template-columns:1fr}.character-portrait-controls>*{grid-column:auto!important}}`}</style>
    <div className="character-detail-shell">
      <aside className="character-detail-sidebar" style={{ background: theme.bgCard, border: `1px solid ${theme.borderLight}`, borderRadius: 10, padding: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}><Text strong style={{ color: theme.textPrimary }}>角色列表</Text><Button size="small" type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建</Button></div>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Input size="small" allowClear prefix={<SearchOutlined />} placeholder="搜索角色" value={characterKeyword} onChange={(event) => setCharacterKeyword(event.target.value)} />
          <Select size="small" allowClear placeholder="全部定位" value={characterRole} onChange={setCharacterRole} options={ROLE_OPTIONS} style={{ width: '100%' }} />
           <Select size="small" allowClear placeholder="全部来源" value={characterSource} onChange={setCharacterSource} options={SOURCE_OPTIONS} style={{ width: '100%' }} />
           <Select size="small" allowClear placeholder="全部流程" value={characterWorkflowSource} onChange={setCharacterWorkflowSource} options={WORKFLOW_SOURCE_OPTIONS} style={{ width: '100%' }} />
          <Button size="small" type={favoritesOnly ? 'primary' : 'default'} onClick={() => setFavoritesOnly((value) => !value)} block>仅收藏</Button>
        </Space>
        <div className="character-detail-sidebar-list" style={{ marginTop: 14 }}>
          {filteredCharacters.map((item) => <button key={item.id} type="button" onClick={() => navigate(`/characters/${item.id}`)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, padding: '8px 6px', marginBottom: 3, textAlign: 'left', border: 0, borderRadius: 7, background: item.id === character.id ? theme.primaryAlpha(0.14) : 'transparent', color: theme.textPrimary, cursor: 'pointer' }}>
            {item.portrait_url ? <img src={item.portrait_url} alt="" style={{ width: 34, height: 34, borderRadius: 6, objectFit: 'cover', background: theme.bgElevated }} /> : <Avatar size={34} icon={<UserOutlined />} />}
            <span style={{ minWidth: 0, flex: 1 }}><span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name}</span><span style={{ display: 'block', color: theme.textSecondary, fontSize: 11 }}>{item.role_label || item.role || '角色'}</span></span>
          </button>)}
          {!filteredCharacters.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配角色" />}
        </div>
      </aside>
      <main style={{ minWidth: 0 }}>
      <Space style={{ marginBottom: 18 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/characters')}>返回角色工作区</Button>
        <Text style={{ color: theme.textSecondary }}>角色设定集 / {character.name}</Text>
      </Space>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 }}>
         <div><Title level={2} style={{ color: theme.textPrimary, margin: 0 }}>{character.name}</Title><Space size={6}><Text style={{ color: theme.textSecondary }}>{character.role_label || character.role || '角色'} · 设定集报告</Text><Tag color="blue">{character.workflow_source_label || '未标记'}</Tag></Space></div>
        <Space wrap><Select size="small" value={enrichProvider || undefined} placeholder="AI 补全供应商" style={{ width: 190 }} onChange={(value) => { setEnrichProvider(value); const backend = llmBackends.find((item) => (item.name || item.provider) === value); setEnrichModel(backend?.default_model || backend?.model || backend?.available_models?.[0] || '') }} options={llmBackends.map((item) => ({ value: item.name || item.provider, label: item.provider_label || item.name || item.provider }))} /><Select size="small" value={enrichModel || undefined} placeholder="AI 补全模型" style={{ width: 180 }} onChange={setEnrichModel} options={Array.from(new Set((llmBackends.find((item) => (item.name || item.provider) === enrichProvider)?.available_models || [llmBackends.find((item) => (item.name || item.provider) === enrichProvider)?.default_model]).filter(Boolean))).map((value) => ({ value, label: value }))} /><Button loading={aiBusy} onClick={() => enrichCharacter('fill_missing')}>AI 补全</Button><Button loading={aiBusy} onClick={() => enrichCharacter('rewrite')}>统一重写</Button><Button loading={aiBusy} onClick={generatePortrait} icon={<PictureOutlined />}>生成主立绘</Button><Button icon={<PlusOutlined />} onClick={() => navigate(`/story?new=1&character_id=${encodeURIComponent(character.id)}`)}>以此角色新建项目</Button><Button icon={<ArrowRightOutlined />} onClick={() => navigate(worldUsages[0]?.story_id || worldUsages[0]?.project_id ? `/story?project_id=${encodeURIComponent(worldUsages[0].story_id || worldUsages[0].project_id)}` : '/story')}>进入创作项目</Button><Button icon={<BranchesOutlined />} onClick={() => document.getElementById('character-relationship-graph')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>关系图谱</Button>{character.portrait_url && !character.portrait_node_id && <Button icon={<DatabaseOutlined />} onClick={upgradePortrait}>升级到资产中枢</Button>}<Button onClick={toggleFrozen}>{character.is_frozen ? '解冻角色' : '冻结角色'}</Button><Button icon={character.is_favorite ? <StarFilled style={{ color: '#f59e0b' }} /> : <StarOutlined />} onClick={toggleFavorite}>{character.is_favorite ? '取消收藏' : '收藏'}</Button><Popconfirm title="确认删除此角色？" onConfirm={deleteCharacter} okText="删除" cancelText="取消"><Button danger icon={<DeleteOutlined />}>删除</Button></Popconfirm><Button type="primary" icon={<EditOutlined />} onClick={openEdit}>编辑角色</Button></Space>
      </div>

      <section className="character-portrait-controls" style={{ marginBottom: 14, padding: '12px 14px', background: theme.bgCard, borderBottom: `1px solid ${theme.borderLight}` }}>
        <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>图像供应商</Text><Select value={portraitProvider || undefined} onChange={(value) => { setPortraitProvider(value); const backend = imageBackends.find((item) => (item.name || item.provider) === value); setPortraitModel(backend?.model || backend?.available_models?.[0] || '') }} style={{ width: '100%' }} options={imageBackends.map((item) => ({ value: item.name || item.provider, label: item.provider_label || item.name || item.provider }))} placeholder="默认后端" /></div>
        <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>模型</Text><Select value={portraitModel || undefined} onChange={setPortraitModel} style={{ width: '100%' }} options={Array.from(new Set((imageBackends.find((item) => (item.name || item.provider) === portraitProvider)?.available_models || [imageBackends.find((item) => (item.name || item.provider) === portraitProvider)?.model]).filter(Boolean))).map((value) => ({ value, label: value }))} placeholder="默认模型" /></div>
         <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>立绘预设</Text><Select value={portraitPreset} onChange={setPortraitPreset} style={{ width: '100%' }} options={[{ value: 'main_portrait', label: '主立绘' }, { value: 'multi_view_sheet', label: '多视图设定图' }, { value: 'character_sheet_16_9', label: '16:9 角色设定板' }, { value: 'identity_board_16_9', label: '16:9 身份板（兼容）' }, { value: 'expression_grid_3x3', label: '表情九宫格' }, { value: 'action_pose_pack', label: '动作姿态' }]} /></div>
        <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>尺寸</Text><Select value={portraitSize} onChange={setPortraitSize} style={{ width: '100%' }} options={['1024x1024', '1024x1536', '1536x1024', '1152x896', '896x1152'].map((value) => ({ value, label: value }))} /></div>
        <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>提示词覆盖（可选）</Text><Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} value={portraitPrompt} onChange={(event) => setPortraitPrompt(event.target.value)} placeholder="留空则按角色设定和预设自动生成" /></div>
        <div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>负面提示词（可选）</Text><Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} value={portraitNegativePrompt} onChange={(event) => setPortraitNegativePrompt(event.target.value)} placeholder="例如：模糊、畸形手指、多余人物" /></div>
        <Space><Button loading={promptPreviewLoading} onClick={previewPortraitPrompt}>预览 Prompt</Button><Button loading={promptOptimizing} onClick={optimizePortraitPrompt}>AI 优化</Button><Button loading={aiBusy} onClick={() => setPortraitPrompt(displayValue(pack?.image_prompt || ''))}>载入提示词</Button></Space>
      </section>

      <section className="character-report-hero" style={{ background: theme.bgCard, borderTop: `1px solid ${theme.borderLight}`, borderBottom: `1px solid ${theme.borderLight}`, padding: 18 }}>
        <div style={{ minWidth: 0 }}>
           <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}><Space size={10}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>角色视觉参考</Text><Text style={{ color: theme.textSecondary, fontSize: 12 }}>主视图是身份基准；参考图用于辅助一致性，不会覆盖主视图</Text></Space><Button size="small" icon={<PictureOutlined />} onClick={openReferencePicker}>从素材库加入</Button></div>
          <div className="character-report-media">
             <div style={{ background: theme.bgElevated, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 470 }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px 0' }}><Space size={6}><Text style={{ color: isPreviewVisual ? '#f59e0b' : theme.textSecondary, fontSize: 12 }}>{isPreviewVisual ? `版本预览 · v${selectedVersion?.version_number || '?'}` : '当前主视图 / 身份基准图'}</Text>{!isPreviewVisual && selectedVersion?.is_main ? <Tag color="cyan" style={{ margin: 0 }}>主视图</Tag> : null}</Space>{isPreviewVisual ? <Button type="link" size="small" onClick={restoreMainVisual}>返回主视图</Button> : null}</div><div style={{ flex: 1, display: 'grid', placeItems: 'center', padding: 10 }}>{mainVisualUrl ? <Image src={mainVisualUrl} preview={{ src: mainVisualUrl }} style={{ width: '100%', height: '100%', maxHeight: 520, objectFit: 'contain' }} /> : <Avatar size={100} icon={<UserOutlined />} />}</div></div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}><Text style={{ color: theme.textSecondary, fontSize: 12 }}>参考图集合（不改变主视图）</Text><div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10, alignContent: 'start' }}>{referenceImages.length ? referenceImages.map((url: string, index: number) => <div key={`${url}-${index}`} style={{ position: 'relative', minWidth: 0 }}><Image src={url} preview={{ src: url }} style={{ width: '100%', aspectRatio: '4 / 3', objectFit: 'cover', background: theme.bgElevated }} /><Popconfirm title="移除这张参考图？" description="不会删除素材库原图，只会从当前角色的参考集合移除。" onConfirm={() => removeReferenceImage(url)}><Button type="text" danger icon={<DeleteOutlined />} aria-label="移除参考图" style={{ position: 'absolute', top: 2, right: 2, background: 'rgba(0,0,0,.62)' }} /></Popconfirm></div>) : <div style={{ gridColumn: '1 / -1', minHeight: 300, display: 'grid', placeItems: 'center', border: `1px dashed ${theme.borderLight}` }}><Empty description="暂无参考图，可从素材库加入或从版本中加入" /></div>}</div></div>
          </div>
        </div>
        <div style={{ borderLeft: `1px solid ${theme.borderLight}`, paddingLeft: 18 }}>
          <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>角色 Bible</Text>
          <Field label="身份" value={identity.logline || identity.position || identity.organization} theme={theme} source={character.field_sources?.identity || character.field_sources?.logline} />
          <Field label="核心欲望" value={motivation.desire || motivation.core_desire} theme={theme} source={character.field_sources?.motivation} />
          <Field label="深层恐惧" value={motivation.fear || motivation.deep_fear} theme={theme} source={character.field_sources?.motivation} />
          <Field label="说话方式" value={speech.tone || speech.style || speech.catchphrase} theme={theme} source={character.field_sources?.speech} />
          <Field label="行为底线" value={behavior.never_do || behavior.boundary || behavior.ooc_boundary} theme={theme} source={character.field_sources?.behavior} />
        </div>
      </section>

      <section className="character-report-lower" style={{ padding: '22px 4px', borderBottom: `1px solid ${theme.borderLight}` }}>
        <div><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>人物摘要</Text><div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginTop: 8 }}><Field label="外观" value={character.appearance} theme={theme} source={character.field_sources?.appearance} /><Field label="服装" value={character.costume_hint} theme={theme} source={character.field_sources?.costume_hint} /><Field label="性格" value={character.personality} theme={theme} source={character.field_sources?.personality} /><Field label="背景" value={character.background} theme={theme} source={character.field_sources?.background} /></div></div>
        <div><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>关系</Text><Button size="small" icon={<PlusOutlined />} onClick={() => { setEditingRelation(null); setRelationForm({ related_character_id: '', relation_type: '', relation_note: '', is_directed: false }); setRelationModalOpen(true) }}>添加关系</Button></div>{relationships.length ? relationships.map((item) => <div key={item.id} style={{ padding: '10px 0', borderBottom: `1px solid ${theme.borderLight}`, display: 'flex', gap: 8, alignItems: 'flex-start' }}><div style={{ minWidth: 0, flex: 1 }}><Text style={{ color: theme.textPrimary }}>{relationTarget(item)}</Text><Tag color="cyan" style={{ marginLeft: 8 }}>{item.relation_type || '关系'}</Tag>{item.relation_note && <Paragraph style={{ color: theme.textSecondary, margin: '4px 0 0' }}>{item.relation_note}</Paragraph>}</div><Space size={2}><Button type="text" size="small" onClick={() => editRelation(item)}>编辑</Button><Popconfirm title="删除这条关系？" onConfirm={() => removeRelation(item)}><Button type="text" danger size="small" icon={<DeleteOutlined />} /></Popconfirm></Space></div>) : <div style={{ paddingTop: 12 }}><Text style={{ color: theme.textSecondary }}>暂无关系</Text></div>}</div>
      </section>
      <section style={{ padding: '16px 4px', borderBottom: `1px solid ${theme.borderLight}` }}>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>自定义标签</Text>
          <Space wrap size={[6, 6]}>{(character.tags || []).map((tag: string) => <Tag key={tag} closable onClose={(event) => { event.preventDefault(); updateTag(tag, 'DELETE') }} color="blue">{tag}</Tag>)}{!(character.tags || []).length && <Text style={{ color: theme.textSecondary }}>暂无标签</Text>}</Space>
          <Space.Compact style={{ maxWidth: 360 }}><Input size="small" placeholder="添加标签" value={tagInput} onChange={(event) => setTagInput(event.target.value)} onPressEnter={() => { if (tagInput.trim()) { updateTag(tagInput, 'POST'); setTagInput('') } }} /><Button size="small" onClick={() => { if (tagInput.trim()) { updateTag(tagInput, 'POST'); setTagInput('') } }}>添加</Button></Space.Compact>
        </Space>
      </section>
      <section id="character-relationship-graph" style={{ padding: '18px 4px', borderBottom: `1px solid ${theme.borderLight}` }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>角色关系图谱</Text><Text style={{ color: theme.textSecondary, fontSize: 12 }}>关系数据与角色详情共用，点击节点切换角色</Text></div><RelationshipGraph graph={relationshipGraph} theme={theme} onOpen={(id) => navigate(`/characters/${id}`)} /></section>
      <section style={{ padding: '22px 4px' }}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>Prompt 资产包</Text>{pack ? <div className="character-report-prompts" style={{ marginTop: 10 }}>{[['出图提示词', pack.image_prompt || pack.portrait_prompt], ['设定图提示词', pack.character_sheet_prompt || pack.identity_board_prompt], ['音色提示词', pack.voice_prompt]].map(([label, value]) => <div key={label as string} style={{ minWidth: 0 }}><Text style={{ color: theme.textSecondary, fontSize: 12 }}>{label as string}</Text><Paragraph copyable={{ icon: <CopyOutlined /> }} style={{ color: theme.textPrimary, background: theme.bgElevated, padding: 10, marginTop: 4, minHeight: 74, whiteSpace: 'pre-wrap' }}>{displayValue(value) || '未生成'}</Paragraph></div>)}</div> : <Text style={{ color: theme.textSecondary }}>暂无 Prompt 资产包</Text>}</section>
      <section className="character-report-details" style={{ borderTop: `1px solid ${theme.borderLight}`, marginTop: 4 }}>
        {[
          ['身份设定', identity],
          ['动机设定', motivation],
          ['说话方式', speech],
          ['行为与底线', behavior],
          ['能力设定', character.ability || {}],
          ['角色弧光', character.arc || {}],
          ['视觉一致性', { 外观: character.appearance, 服装提示: character.costume_hint, 一致性要求: character.visual_consistency, 标志物: character.signature_items, 表情: character.expressions, 姿态: character.poses }],
          ['来源与使用', { 来源类型: character.source_type_labels || character.source_types, 标签: character.tags, 年龄范围: character.age_range, 世界使用: character.world_usages?.map((item: any) => item.project_title || item.story_id) }],
        ].map(([title, values]) => <details key={title as string}><summary>{title as string}</summary><div className="character-report-details-content">{Object.entries((values || {}) as Record<string, any>).map(([label, value]) => <Field key={label} label={label} value={value} theme={theme} source={character.field_sources?.[label]} />)}</div></details>)}
      </section>
      <section className="character-report-details" style={{ borderTop: `1px solid ${theme.borderLight}`, marginTop: 18 }}>
        {[
          ['世界使用', worldUsages],
          ['立绘版本', portraitVersions],
          ['切片记录', portraitSlices],
          ['生图日志', portraitLogs],
          ['字段来源', character.field_sources || {}],
        ].map(([title, values]) => <details key={title as string}><summary>{title as string} <span style={{ color: theme.textSecondary, fontSize: 12, fontWeight: 400 }}>（{Array.isArray(values) ? values.length : Object.keys(values || {}).length}）</span></summary><div className="character-report-details-content">{Array.isArray(values) ? renderHistoryRecords(title as string, values) : Object.entries(values || {}).map(([label, value]) => <Field key={label} label={label} value={value} theme={theme} />)}</div></details>)}
      </section>
      <section style={{ marginTop: 18, borderTop: `1px solid ${theme.borderLight}`, padding: '18px 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>立绘版本</Text><Text style={{ color: theme.textSecondary, fontSize: 12 }}>点击缩略图切换主视图，设为主视图会同步角色基准图</Text></div>
         {portraitVersions.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>{portraitVersions.map((version: any) => { const url = version.image_url || version.url || version.file_path; const detailItems = [{ key: 'prompt', label: '生成提示词', value: version.prompt }, { key: 'negative', label: '负面提示词', value: version.negative_prompt }, { key: 'params', label: '生成参数', value: Object.keys(version.params || {}).length ? JSON.stringify(version.params, null, 2) : '' }].filter((item) => item.value); const selected = String(version.id) === String(selectedVersionId); return <div key={version.id} style={{ background: theme.bgCard, border: `1px solid ${selected ? theme.primary : version.is_main ? theme.primary : theme.borderLight}`, padding: 8, borderRadius: 6 }}><div onClick={() => { if (url) { setSelectedVisualUrl(url); setSelectedVersionId(String(version.id)); window.scrollTo({ top: 0, behavior: 'smooth' }) } }} style={{ cursor: url ? 'pointer' : 'default', background: theme.bgElevated, minHeight: 170, display: 'grid', placeItems: 'center' }}>{url ? <Image src={url} preview={{ src: url }} width="100%" height={170} style={{ objectFit: 'cover' }} /> : <PictureOutlined style={{ color: theme.textSecondary, fontSize: 28 }} />}</div><div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', gap: 6, alignItems: 'center' }}><Space size={4}><Text style={{ color: theme.textPrimary, fontSize: 12 }}>V{version.version_number || '?'}</Text>{version.is_main ? <Tag color="cyan">主视图</Tag> : selected ? <Tag color="gold">当前查看</Tag> : null}</Space><Space size={4} wrap>{!version.is_main && <Button size="small" onClick={() => setMainVersion(version)}>设为主视图</Button>}<Button size="small" disabled={!url} onClick={() => { setSelectedVisualUrl(url); setSelectedVersionId(String(version.id)); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>查看</Button><Button size="small" disabled={!url} onClick={() => addReferenceVersion(version)}>加入参考</Button><Button size="small" onClick={() => { setSliceVersionId(version.id); setSliceModalOpen(true) }}>生成切片</Button></Space></div><Text style={{ color: theme.textSecondary, fontSize: 11, display: 'block', marginTop: 4 }}>{[version.preset, version.provider, version.model].filter(Boolean).join(' · ') || '未记录模型'} · {version.created_at ? new Date(version.created_at).toLocaleString() : '时间未知'}</Text>{detailItems.length ? <Collapse ghost size="small" style={{ marginTop: 4 }} items={[{ key: 'details', label: '查看生成详情', children: <Space direction="vertical" size={8} style={{ width: '100%' }}>{detailItems.map((item) => <div key={item.key}><Text style={{ color: theme.textSecondary, fontSize: 11 }}>{item.label}</Text><Paragraph copyable style={{ color: theme.textPrimary, whiteSpace: 'pre-wrap', margin: '3px 0 0', fontSize: 11 }}>{String(item.value)}</Paragraph></div>)}</Space> }]} /> : null}</div> })}</div> : <Text style={{ color: theme.textSecondary }}>暂无立绘版本</Text>}
      </section>
      <section style={{ marginTop: 18, borderTop: `1px solid ${theme.borderLight}`, padding: '18px 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}><Text strong style={{ color: theme.textPrimary, fontSize: 15 }}>世界使用</Text><Button size="small" icon={<PlusOutlined />} onClick={() => setWorldModalOpen(true)}>添加世界</Button></div>
        {worldUsages.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>{worldUsages.map((item: any) => <div key={item.id} style={{ background: theme.bgCard, border: `1px solid ${theme.borderLight}`, padding: 12, borderRadius: 6 }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><Text strong style={{ color: theme.textPrimary }}>{item.world_name || item.project_title || '未命名世界'}</Text><Space size={2}><Button type="text" size="small" onClick={() => openWorldEdit(item)}>编辑</Button><Popconfirm title="移除这条世界使用？" onConfirm={() => removeWorldUsage(item.id)}><Button type="text" danger size="small" icon={<DeleteOutlined />} /></Popconfirm></Space></div><Text style={{ color: theme.textSecondary, fontSize: 12 }}>{item.usage_role || '未设置角色职责'}</Text>{item.local_identity && <Paragraph style={{ color: theme.textPrimary, margin: '8px 0 0' }}>{item.local_identity}</Paragraph>}{item.local_costume && <Text style={{ color: theme.textSecondary, fontSize: 12 }}>服装覆盖：{item.local_costume}</Text>}{(item.story_id || item.project_id) && <Button type="link" size="small" icon={<ArrowRightOutlined />} onClick={() => navigate(`/story?project_id=${encodeURIComponent(item.story_id || item.project_id)}`)} style={{ padding: '6px 0 0' }}>打开项目生产线</Button>}</div>)}</div> : <Text style={{ color: theme.textSecondary }}>暂无世界使用记录</Text>}
      </section>
      <Modal open={editOpen} title={editMode === 'edit' ? `编辑角色 · ${character.name}` : '新建角色'} width={860} onCancel={() => setEditOpen(false)} confirmLoading={editSaving} onOk={saveEdit} okText={editMode === 'edit' ? '保存修改' : '创建角色'}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
           <div><Text style={{ display: 'block', marginBottom: 4 }}>角色定位</Text><Select style={{ width: '100%' }} value={editForm.role} onChange={(value) => setEditForm((form) => ({ ...form, role: value }))} options={ROLE_OPTIONS} /></div>
           <div><Text style={{ display: 'block', marginBottom: 4 }}>流程来源</Text><Select style={{ width: '100%' }} value={editForm.workflow_source || 'unknown'} onChange={(value) => setEditForm((form) => ({ ...form, workflow_source: value }))} options={WORKFLOW_SOURCE_OPTIONS} /></div>
          {['name', 'age_range', 'source_types', 'appearance', 'costume_hint', 'personality', 'background', 'visual_consistency', 'signature_items', 'expressions', 'poses', 'tags'].map((field) => <div key={field} style={{ gridColumn: ['appearance', 'costume_hint', 'personality', 'background', 'visual_consistency', 'source_types'].includes(field) ? '1 / -1' : undefined }}><Text style={{ display: 'block', marginBottom: 4 }}>{({ name: '名称', age_range: '年龄范围', source_types: '来源类型（逗号分隔）', appearance: '外观', costume_hint: '服装提示', personality: '性格', background: '背景', visual_consistency: '视觉一致性', signature_items: '标志物（逗号分隔）', expressions: '表情（逗号分隔）', poses: '姿态（逗号分隔）', tags: '标签（逗号分隔）' } as any)[field]}</Text><Input.TextArea autoSize={{ minRows: ['appearance', 'costume_hint', 'personality', 'background', 'visual_consistency', 'source_types'].includes(field) ? 2 : 1, maxRows: 6 }} value={editForm[field] || ''} onChange={(event) => setEditForm((form) => ({ ...form, [field]: event.target.value }))} /></div>)}
          <div style={{ gridColumn: '1 / -1', borderTop: `1px solid ${theme.borderLight}`, paddingTop: 12 }}><Text strong style={{ color: theme.textPrimary }}>完整设定 JSON（保留旧角色详情中的扩展字段）</Text><div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 8 }}>{[['identity', '身份设定'], ['motivation', '动机设定'], ['speech', '说话方式'], ['behavior', '行为与底线'], ['ability', '能力设定'], ['arc', '角色弧光'], ['visual_profile', '视觉 Profile（含主视图/参考图）']].map(([field, label]) => <div key={field}><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>{label}</Text><Input.TextArea rows={4} value={editForm[field] || '{}'} onChange={(event) => setEditForm((form) => ({ ...form, [field]: event.target.value }))} /></div>)}</div></div>
        </div>
      </Modal>
      <Modal open={referenceOpen} title="加入角色参考图" footer={null} width={900} onCancel={() => setReferenceOpen(false)}>
        <Tabs items={[{ key: 'assets', label: '素材库图片', children: <Space direction="vertical" style={{ width: '100%' }} size={10}><Input.Search allowClear placeholder="搜索标题、标签或来源" value={referenceSearch} onChange={(event) => setReferenceSearch(event.target.value)} onSearch={(value) => loadReferenceAssets(value)} enterButton="搜索" /><Spin spinning={referenceLoading}><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10, minHeight: 180 }}>{referenceAssets.length ? referenceAssets.map((asset: any) => { const url = asset.thumbnail_url || asset.preview_url || asset.url || asset.file_url; return <button key={asset.id} type="button" onClick={() => addReferenceAsset(asset)} style={{ padding: 6, textAlign: 'left', border: `1px solid ${theme.borderLight}`, background: theme.bgElevated, cursor: 'pointer', color: theme.textPrimary }}>{url ? <img src={url} alt="" style={{ width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', display: 'block' }} /> : <div style={{ aspectRatio: '1 / 1', display: 'grid', placeItems: 'center' }}><PictureOutlined /></div>}<Text ellipsis style={{ display: 'block', marginTop: 5, color: theme.textPrimary, fontSize: 12 }}>{asset.title || asset.id}</Text><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 11 }}>{asset.source_type || '素材库图片'}</Text></button> }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有找到图片素材" />}</div></Spin></Space> }, { key: 'versions', label: `历史立绘版本 (${portraitVersions.length})`, children: portraitVersions.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>{portraitVersions.map((version: any) => { const url = version.image_url || version.url || version.file_path; return <div key={version.id} style={{ padding: 6, border: `1px solid ${theme.borderLight}`, background: theme.bgElevated }}>{url ? <Image src={url} width="100%" height={120} style={{ objectFit: 'cover' }} /> : <div style={{ height: 120, display: 'grid', placeItems: 'center' }}><PictureOutlined /></div>}<Text style={{ display: 'block', color: theme.textPrimary, fontSize: 12, marginTop: 5 }}>V{version.version_number || '?'}</Text><Button size="small" block style={{ marginTop: 5 }} disabled={!url} onClick={() => addReferenceVersion(version)}>加入参考</Button></div> })}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史立绘版本" /> }]} />
      </Modal>
      <Modal open={promptPreviewOpen} title="角色生图 Prompt 预览" footer={null} width={860} onCancel={() => setPromptPreviewOpen(false)}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}><div><Text strong style={{ color: theme.textPrimary }}>正向提示词</Text><Paragraph copyable style={{ whiteSpace: 'pre-wrap', background: theme.bgElevated, padding: 12, color: theme.textPrimary }}>{displayValue(promptPreview?.prompt) || '暂无'}</Paragraph></div><div><Text strong style={{ color: theme.textPrimary }}>负面提示词</Text><Paragraph copyable style={{ whiteSpace: 'pre-wrap', background: theme.bgElevated, padding: 12, color: theme.textPrimary }}>{displayValue(promptPreview?.negative_prompt) || '暂无'}</Paragraph></div><Text style={{ color: theme.textSecondary }}>预览只生成参数，不会创建图片或版本。</Text></Space>
      </Modal>
      <Modal open={worldModalOpen} title={editingWorld ? '编辑世界使用' : '添加世界使用'} width={820} onCancel={() => { setWorldModalOpen(false); setEditingWorld(null) }} onOk={saveWorldUsage} confirmLoading={worldSaving} okText="保存">
        <Space direction="vertical" style={{ width: '100%' }} size={10}>{!editingWorld && <Select showSearch optionFilterProp="label" placeholder="选择创作项目（必选）" value={worldForm.story_id || undefined} onChange={(value) => { const project = projects.find((item) => item.id === value); setWorldForm((form) => ({ ...form, story_id: value, world_name: form.world_name || project?.title || '' })) }} options={projects.map((item) => ({ value: item.id, label: item.title || item.name || item.id }))} />}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><Input placeholder="世界/项目名称" value={worldForm.world_name} onChange={(event) => setWorldForm((form) => ({ ...form, world_name: event.target.value }))} /><Input placeholder="角色职责：主角/NPC/反派" value={worldForm.usage_role} onChange={(event) => setWorldForm((form) => ({ ...form, usage_role: event.target.value }))} /><Input placeholder="本世界别名/代号" value={worldForm.local_alias} onChange={(event) => setWorldForm((form) => ({ ...form, local_alias: event.target.value }))} /><Input placeholder="阵营/组织/派系" value={worldForm.local_faction} onChange={(event) => setWorldForm((form) => ({ ...form, local_faction: event.target.value }))} /><Select value={worldForm.local_status} onChange={(value) => setWorldForm((form) => ({ ...form, local_status: value }))} options={[{ value: 'active', label: '启用' }, { value: 'draft', label: '草稿' }, { value: 'archived', label: '归档' }]} /></div>
          <Input.TextArea placeholder="该世界中的身份说明" value={worldForm.local_identity} onChange={(event) => setWorldForm((form) => ({ ...form, local_identity: event.target.value }))} /><Input.TextArea placeholder="服装/形态覆盖" value={worldForm.local_costume} onChange={(event) => setWorldForm((form) => ({ ...form, local_costume: event.target.value }))} /><Input.TextArea placeholder="局部 Prompt 标签，逗号或换行分隔" value={worldForm.local_prompt_tags} onChange={(event) => setWorldForm((form) => ({ ...form, local_prompt_tags: event.target.value }))} /><Input.TextArea rows={3} placeholder="OOC 约束：不能做什么、不能说什么" value={worldForm.ooc_notes} onChange={(event) => setWorldForm((form) => ({ ...form, ooc_notes: event.target.value }))} /><Input.TextArea rows={3} placeholder="出模约束：外观、服装、比例、道具不能画错" value={worldForm.off_model_notes} onChange={(event) => setWorldForm((form) => ({ ...form, off_model_notes: event.target.value }))} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>Bible 覆盖 JSON</Text><Input.TextArea rows={5} value={worldForm.bible_overrides} onChange={(event) => setWorldForm((form) => ({ ...form, bible_overrides: event.target.value }))} /></div><div><Text style={{ display: 'block', color: theme.textSecondary, fontSize: 12, marginBottom: 4 }}>视觉覆盖 JSON</Text><Input.TextArea rows={5} value={worldForm.visual_overrides} onChange={(event) => setWorldForm((form) => ({ ...form, visual_overrides: event.target.value }))} /></div></div>
        </Space>
      </Modal>
      <Modal open={sliceModalOpen} title="生成立绘切片" onCancel={() => setSliceModalOpen(false)} onOk={slicePortrait} confirmLoading={sliceBusy} okText="生成切片"><Space direction="vertical" style={{ width: '100%' }}><Select value={sliceRows} onChange={setSliceRows} options={[1, 2, 3, 4, 5, 6].map((value) => ({ value, label: `${value} 行` }))} /><Select value={sliceCols} onChange={setSliceCols} options={[1, 2, 3, 4, 5, 6].map((value) => ({ value, label: `${value} 列` }))} /><Text style={{ color: theme.textSecondary }}>切片会进入素材中枢，并保留来源版本血缘。</Text></Space></Modal>
      <Modal open={relationModalOpen} title={editingRelation ? '编辑角色关系' : '添加角色关系'} onCancel={() => setRelationModalOpen(false)} onOk={saveRelation} confirmLoading={relationSaving} okText="保存">
        <Space direction="vertical" style={{ width: '100%' }} size={10}><Select showSearch optionFilterProp="label" style={{ width: '100%' }} placeholder="选择关联角色" value={relationForm.related_character_id || undefined} onChange={(value) => setRelationForm((form) => ({ ...form, related_character_id: value }))} options={characters.filter((item) => item.id !== character.id).map((item) => ({ value: item.id, label: item.name }))} /><Input placeholder="关系类型，如盟友、敌人、师徒" value={relationForm.relation_type} onChange={(event) => setRelationForm((form) => ({ ...form, relation_type: event.target.value }))} /><Input.TextArea placeholder="关系说明（可选）" value={relationForm.relation_note} onChange={(event) => setRelationForm((form) => ({ ...form, relation_note: event.target.value }))} /></Space>
      </Modal>
      </main>
    </div>
  </div>
}
