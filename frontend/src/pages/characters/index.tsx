/**
 * YLCraft — 角色管理页面
 */

import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Input, Select, Button, Tag, Typography, Spin,
  message, Space, Modal, Tooltip, Badge, Avatar, Segmented, Empty,
  Checkbox, Divider, Popconfirm, Image, Drawer, Descriptions,
  Statistic, Popover, Collapse, InputNumber, Switch, Alert,
  Tabs, Table,
} from 'antd'
import {
  UserOutlined, StarOutlined, StarFilled, LockOutlined,
  DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined,
  HeartOutlined, RobotOutlined, PictureOutlined, TeamOutlined, ReadOutlined,
  DatabaseOutlined, HistoryOutlined, ReloadOutlined, CopyOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { chat, listGenerationLogsGlobal } from '../../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const { Panel } = Collapse

const PAGE_SIZE = 24

const SOURCE_TYPE_COLORS: Record<string, string> = {
  ai_generated: '#a855f7',
  local_material: '#3b82f6',
  real_person: '#10b981',
  anime_reference: '#f59e0b',
  stock_footage: '#6366f1',
  other: '#8b8ba8',
}

const SOURCE_TYPE_ICONS: Record<string, React.ReactNode> = {
  ai_generated: <RobotOutlined />,
  local_material: <PictureOutlined />,
  real_person: <UserOutlined />,
  anime_reference: <TeamOutlined />,
  stock_footage: <span style={{ fontSize: 12 }}>📦</span>,
  other: <span style={{ fontSize: 12 }}>🏷️</span>,
}

const ROLE_COLORS: Record<string, string> = {
  protagonist: '#f59e0b',
  antagonist: '#ef4444',
  supporting: '#3b82f6',
  extra: '#8b8ba8',
}

export const CHARACTER_SOURCE_TYPE_OPTIONS = [
  { value: 'ai_generated', label: 'AI生成' },
  { value: 'local_material', label: '本地素材' },
  { value: 'real_person', label: '真人对白' },
  { value: 'anime_reference', label: '动漫原型' },
  { value: 'stock_footage', label: '库存人物' },
  { value: 'other', label: '其他' },
]

export const CHARACTER_ROLE_OPTIONS = [
  { value: 'protagonist', label: '主角' },
  { value: 'antagonist', label: '反派' },
  { value: 'supporting', label: '配角' },
  { value: 'extra', label: '路人' },
]

export interface Character {
  id: string
  name: string
  role: string
  source_types: string[]
  source_type_labels: string[]
  appearance: string
  personality: string
  costume_hint: string
  background: string
  age_range: string
  tags: string[]
  portrait_url: string
  portrait_asset_id: string
  portrait_node_id?: string | null
  is_favorite: boolean
  is_frozen: boolean
  role_label: string
  use_count: number
  created_at: string
}

export type CharacterSourceType = string
export type CharacterRole = string

export interface CharacterCreateRequest {
  name: string
  role: string
  source_types: string[]
  appearance?: string
  personality?: string
  costume_hint?: string
  background?: string
  age_range?: string
  tags?: string[]
  portrait_url?: string
  portrait_asset_id?: string
}

export interface CharacterUpdateRequest {
  name?: string
  role?: string
  source_types?: string[]
  appearance?: string
  personality?: string
  costume_hint?: string
  background?: string
  age_range?: string
  tags?: string[]
  portrait_url?: string
  portrait_asset_id?: string
}

export function listCharacters(params: {
  keyword?: string
  source_type?: string
  role?: string
  is_favorite?: boolean
  page?: number
  page_size?: number
}) {
  const sp = new URLSearchParams()
  if (params.keyword) sp.set('keyword', params.keyword)
  if (params.source_type) sp.set('source_type', params.source_type)
  if (params.role) sp.set('role', params.role)
  if (params.is_favorite) sp.set('is_favorite', '1')
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  return fetch(`/api/v1/characters?${sp}`, { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
}

export function getCharacter(id: string) {
  return fetch(`/api/v1/characters/${id}`, { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
}

export function createCharacter(data: CharacterCreateRequest) {
  return fetch('/api/v1/characters', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

export function updateCharacter(id: string, data: CharacterUpdateRequest) {
  return fetch(`/api/v1/characters/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

export function deleteCharacter(id: string) {
  return fetch(`/api/v1/characters/${id}`, {
    method: 'DELETE',
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function toggleCharacterFavorite(id: string) {
  return fetch(`/api/v1/characters/${id}/favorite`, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function addCharacterTag(id: string, tag: string) {
  return fetch(`/api/v1/characters/${id}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({ tag }),
  }).then(r => r.json())
}

// ===== 角色立绘 AI 生图 =====

export interface ImageBackendInfo {
  provider: string
  provider_label: string
  name: string
  model: string
  available_models: string[]
  supported_sizes: string[]
}

export interface ImageBackendsResponse {
  success: boolean
  backends: ImageBackendInfo[]
  default: string | null
}

export function getImageBackends(): Promise<ImageBackendsResponse> {
  return fetch('/api/v1/images/backends', { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
}

export interface ImageGenerateResponse {
  success: boolean
  url?: string
  urls?: string[]
  asset_id?: string
  all_asset_ids?: string[]
  error?: string
}

export function generateCharacterPortraitImage(data: {
  prompt: string
  provider?: string
  size?: string
  n?: number
}): Promise<ImageGenerateResponse> {
  return fetch('/api/v1/images/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

/**
 * 角色立绘生成（资产中枢版）
 * 调用 /api/v1/characters/{id}/portrait/generate，自动创建 AssetNode + Version + Representation
 * 编辑已有角色时优先使用，可保留版本历史
 */
export interface PortraitGenerateAssetHubResponse {
  success: boolean
  detail?: string
  data?: {
    url: string
    local_path: string
    node_id: string
    version_id: string
    version_number: number
    representation_id: string
    character: {
      id: string
      name: string
      portrait_url: string
      portrait_node_id: string
    }
  }
}

export function generateCharacterPortraitViaAssetHub(
  characterId: string,
  data: {
    prompt: string
    provider?: string
    size?: string
    n?: number
  }
): Promise<PortraitGenerateAssetHubResponse> {
  return fetch(`/api/v1/characters/${characterId}/portrait/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

/**
 * 把已有 portrait_url 升级到资产中枢（补登记 Node + Version + Representation）
 * 适用于之前用旧 /images/generate 生成了立绘但还没入中枢的角色
 */
export function upgradeCharacterPortraitToAssetHub(
  characterId: string
): Promise<PortraitGenerateAssetHubResponse> {
  return fetch(`/api/v1/characters/${characterId}/portrait/upgrade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function removeCharacterTag(id: string, tag: string) {
  return fetch(`/api/v1/characters/${id}/tags/${encodeURIComponent(tag)}`, {
    method: 'DELETE',
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function getAllCharacterTags() {
  return fetch('/api/v1/characters/tags/all', { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
}

function buildCharacterPortraitPrompt(form: CharacterCreateRequest): string {
  const roleLabel = CHARACTER_ROLE_OPTIONS.find(o => o.value === form.role)?.label || form.role || '角色'
  const sourceLabels = (form.source_types || [])
    .map(value => CHARACTER_SOURCE_TYPE_OPTIONS.find(o => o.value === value)?.label || value)
    .filter(Boolean)
  const tags = (form.tags || []).filter(Boolean)
  const lines = [
    '单人角色立绘，完整角色设定图，适合作为后续漫画/短剧分镜的一致性参考图。',
    form.name ? `角色名：${form.name}` : '',
    roleLabel ? `角色定位：${roleLabel}` : '',
    form.age_range ? `年龄范围：${form.age_range}` : '',
    sourceLabels.length ? `来源/风格标签：${sourceLabels.join('、')}` : '',
    form.appearance ? `外貌特征：${form.appearance.trim()}` : '',
    form.costume_hint ? `服装与配饰：${form.costume_hint.trim()}` : '',
    form.personality ? `性格气质：${form.personality.trim()}` : '',
    form.background ? `角色背景暗示：${form.background.trim()}` : '',
    tags.length ? `补充标签：${tags.join('、')}` : '',
    '构图要求：单人，正面或轻微三分之二角度，全身或膝上立绘，头发、五官、服装、配饰清晰可辨，站姿自然，轮廓干净。',
    '画面要求：简洁纯色或浅灰背景，无复杂场景，不遮挡身体，不裁切头部和脚部，适合作为角色卡、参考图和后续一致性生图素材。',
    '质量要求：高质量，细节明确，面部稳定，服饰结构准确，干净线条，统一光照，专业角色设计，character reference sheet, clean background.',
    '避免：多人、背影、夸张透视、过度遮挡、低清晰度、畸形手指、脸部崩坏、文字、水印、logo、复杂背景。',
  ]
  return lines.filter(Boolean).join('\n')
}

function cleanPromptResponse(content: string): string {
  const trimmed = (content || '').trim()
  if (!trimmed) return ''
  return trimmed
    .replace(/^```(?:text|markdown|json)?/i, '')
    .replace(/```$/i, '')
    .trim()
}

export default function CharactersPage() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [characters, setCharacters] = useState<Character[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [filterSourceType, setFilterSourceType] = useState<string | null>(null)
  const [filterRole, setFilterRole] = useState<string | null>(null)
  const [filterFavorite, setFilterFavorite] = useState(false)
  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [formModalOpen, setFormModalOpen] = useState(false)
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null)
  const [tagInput, setTagInput] = useState('')
  const [form, setForm] = useState<CharacterCreateRequest>({
    name: '', role: 'supporting', source_types: [], appearance: '',
    personality: '', costume_hint: '', background: '', age_range: '', tags: [],
    portrait_url: '', portrait_asset_id: '',
  })
  const [saving, setSaving] = useState(false)
  // 角色立绘 AI 生图状态
  const [portraitBackends, setPortraitBackends] = useState<ImageBackendInfo[]>([])
  const [selectedPortraitBackend, setSelectedPortraitBackend] = useState<string>('')
  const [generatingPortrait, setGeneratingPortrait] = useState(false)
  const [portraitPromptDraft, setPortraitPromptDraft] = useState('')
  const [optimizingPortraitPrompt, setOptimizingPortraitPrompt] = useState(false)
  // 资产中枢升级状态（在 Drawer 中点"升级到资产中枢"时使用）
  const [upgradingPortrait, setUpgradingPortrait] = useState(false)

  // 角色生图日志（Drawer 内 Tab 用）
  interface PortraitLog {
    id: string
    scene: string
    ref_id: string | null
    stage: string
    provider: string
    model: string
    status: string
    prompt: string
    request: Record<string, any>
    raw_response: string
    normalized: Record<string, any>
    validation_error: string
    created_at: string
  }
  const [portraitLogs, setPortraitLogs] = useState<PortraitLog[]>([])
  const [portraitLogsLoading, setPortraitLogsLoading] = useState(false)
  const [drawerActiveTab, setDrawerActiveTab] = useState<'detail' | 'logs'>('detail')

  const loadPortraitLogs = useCallback(async (characterId: string) => {
    setPortraitLogsLoading(true)
    try {
      const res = await listGenerationLogsGlobal({
        scene: 'character_portrait',
        ref_id: characterId,
        limit: 50,
      })
      setPortraitLogs(res?.data || [])
    } catch {
      setPortraitLogs([])
    } finally {
      setPortraitLogsLoading(false)
    }
  }, [])

  // 打开 Drawer 时加载日志
  useEffect(() => {
    if (drawerOpen && selectedCharacter) {
      setDrawerActiveTab('detail')
      loadPortraitLogs(selectedCharacter.id)
    }
  }, [drawerOpen, selectedCharacter, loadPortraitLogs])

  const load = useCallback(async (p: number, opts: {
    keyword?: string
    source_type?: string | null
    role?: string | null
    is_favorite?: boolean
  }) => {
    setLoading(true)
    try {
      const data = await listCharacters({
        keyword: opts.keyword || undefined,
        source_type: opts.source_type || undefined,
        role: opts.role || undefined,
        is_favorite: opts.is_favorite,
        page: p,
        page_size: PAGE_SIZE,
      })
      setCharacters(data.data || [])
      setTotal(data.total || 0)
    } catch {
      message.error('加载角色失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(1, { keyword, source_type: filterSourceType, role: filterRole, is_favorite: filterFavorite || undefined })
    setPage(1)
  }, [keyword, filterSourceType, filterRole, filterFavorite, load])

  // 弹窗打开时加载生图后端列表（缓存，第二次起不重复拉）
  useEffect(() => {
    if (!formModalOpen) return
    if (portraitBackends.length > 0) return
    getImageBackends()
      .then((data) => {
        if (data?.success) {
          setPortraitBackends(data.backends || [])
          if (data.default && !selectedPortraitBackend) {
            setSelectedPortraitBackend(data.default)
          }
        }
      })
      .catch(() => { /* 静默失败，立绘 AI 生图为可选能力 */ })
  }, [formModalOpen, portraitBackends.length, selectedPortraitBackend])

  useEffect(() => {
    if (!formModalOpen) return
    setPortraitPromptDraft(buildCharacterPortraitPrompt(form))
  }, [formModalOpen, editingCharacter?.id])

  const handleOpenDetail = async (character: Character) => {
    try {
      const data = await getCharacter(character.id)
      setSelectedCharacter(data.data)
    } catch {
      setSelectedCharacter(character)
    }
    setDrawerOpen(true)
  }

  const handleFavorite = async (character: Character) => {
    try {
      const data = await toggleCharacterFavorite(character.id)
      const updated = data.data
      setCharacters(cs => cs.map(c => c.id === character.id ? { ...c, is_favorite: updated.is_favorite } : c))
      setSelectedCharacter(prev => prev?.id === character.id ? { ...prev, is_favorite: updated.is_favorite } : prev)
    } catch {
      message.error('操作失败')
    }
  }

  const handleDelete = async (character: Character) => {
    try {
      await deleteCharacter(character.id)
      setCharacters(cs => cs.filter(c => c.id !== character.id))
      setDrawerOpen(false)
      message.success('已删除')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const handleAddTag = async (tag: string) => {
    if (!selectedCharacter) return
    try {
      const data = await addCharacterTag(selectedCharacter.id, tag)
      setSelectedCharacter(data.data)
      setCharacters(cs => cs.map(c => c.id === selectedCharacter.id ? data.data : c))
    } catch {
      message.error('添加标签失败')
    }
  }

  const handleRemoveTag = async (tag: string) => {
    if (!selectedCharacter) return
    try {
      const data = await removeCharacterTag(selectedCharacter.id, tag)
      setSelectedCharacter(data.data)
      setCharacters(cs => cs.map(c => c.id === selectedCharacter.id ? data.data : c))
    } catch {
      message.error('移除标签失败')
    }
  }

  // 把已有 portrait_url 升级到资产中枢（补登记 Node + Version + Representation）
  const handleUpgradePortrait = async () => {
    if (!selectedCharacter || upgradingPortrait) return
    setUpgradingPortrait(true)
    try {
      const data = await upgradeCharacterPortraitToAssetHub(selectedCharacter.id)
      if (!data?.success || !data.data) {
        message.error(data?.detail || '升级失败')
        return
      }
      const info = data.data
      const updated: Character = {
        ...selectedCharacter,
        portrait_node_id: info.character.portrait_node_id,
      }
      setSelectedCharacter(updated)
      setCharacters(cs => cs.map(c => c.id === selectedCharacter.id ? updated : c))
      message.success(`已升级到资产中枢（v${info.version_number}）`)
      // 刷新日志 Tab
      loadPortraitLogs(selectedCharacter.id)
    } catch (e: any) {
      message.error(e?.message || '升级失败')
    } finally {
      setUpgradingPortrait(false)
    }
  }

  // AI 生成立绘：编辑模式走资产中枢端点（保留版本历史），新建模式走旧 /images/generate
  const handleRefreshPortraitPrompt = () => {
    const prompt = buildCharacterPortraitPrompt(form)
    setPortraitPromptDraft(prompt)
    message.success('已根据当前角色信息生成完整提示词')
  }

  const handleCopyPortraitPrompt = async () => {
    const prompt = portraitPromptDraft.trim() || buildCharacterPortraitPrompt(form)
    if (!prompt) {
      message.warning('暂无可复制的提示词')
      return
    }
    try {
      await navigator.clipboard.writeText(prompt)
      message.success('完整生图提示词已复制')
    } catch {
      message.error('复制失败，请手动复制文本框内容')
    }
  }

  const handleOptimizePortraitPrompt = async () => {
    const basePrompt = portraitPromptDraft.trim() || buildCharacterPortraitPrompt(form)
    if (!basePrompt.trim()) {
      message.warning('请先填写角色信息或生成提示词')
      return
    }
    setOptimizingPortraitPrompt(true)
    try {
      const res = await chat({
        messages: [
          {
            role: 'system',
            content:
              '你是资深角色设定师和 AI 生图提示词工程师。只输出一段可直接用于生图的完整提示词，不要 Markdown，不要解释。',
          },
          {
            role: 'user',
            content:
              `请把下面的角色立绘提示词优化成更稳定、更完整的生图提示词。\n` +
              `要求：保留角色身份和外观，不添加矛盾设定；强调单人立绘、角色卡、清晰五官、服装细节、简洁背景、后续漫画一致性参考；包含必要负面约束。\n\n` +
              basePrompt,
          },
        ],
        temperature: 0.35,
        max_tokens: 1200,
      })
      const optimized = cleanPromptResponse(res?.content || '')
      if (!res?.success || !optimized) {
        message.error(res?.error || 'AI 优化提示词失败')
        return
      }
      setPortraitPromptDraft(optimized)
      message.success('AI 已优化完整提示词')
    } catch (e: any) {
      message.error(e?.message || 'AI 优化提示词失败')
    } finally {
      setOptimizingPortraitPrompt(false)
    }
  }

  const handleGeneratePortrait = async () => {
    if (generatingPortrait) return
    if (!form.appearance?.trim() && !form.costume_hint?.trim()) {
      message.warning('请先填写"外貌描述"或"服装提示"')
      return
    }
    if (!selectedPortraitBackend) {
      message.warning('请先选择生图模型')
      return
    }
    const prompt = portraitPromptDraft.trim() || buildCharacterPortraitPrompt(form)
    if (!portraitPromptDraft.trim()) {
      setPortraitPromptDraft(prompt)
    }

    setGeneratingPortrait(true)
    try {
      if (editingCharacter) {
        // 编辑已有角色 → 走资产中枢端点（自动创建/复用 AssetNode + 新 Version）
        const data = await generateCharacterPortraitViaAssetHub(
          editingCharacter.id,
          {
            prompt,
            provider: selectedPortraitBackend,
            size: '1024x1024',
            n: 1,
          }
        )
        if (!data?.success || !data.data) {
          message.error(data?.detail || '生成立绘失败')
          return
        }
        const info = data.data
        setForm(f => ({
          ...f,
          portrait_url: info.url,
          portrait_asset_id: '',
          portrait_node_id: info.character.portrait_node_id,
        }))
        message.success(`立绘已生成并入资产中枢（v${info.version_number}）`)
        // 刷新日志 Tab
        if (editingCharacter?.id) {
          loadPortraitLogs(editingCharacter.id)
        }
      } else {
        // 新建模式 → 走旧 /images/generate（保存后可在 Drawer 中点"升级到资产中枢"补登记）
        const data = await generateCharacterPortraitImage({
          prompt,
          provider: selectedPortraitBackend,
          size: '1024x1024',
          n: 1,
        })
        if (!data?.success) {
          message.error(data?.error || '生成立绘失败')
          return
        }
        const url = data.url || data.urls?.[0] || ''
        const assetId = data.asset_id || data.all_asset_ids?.[0] || ''
        if (!url) {
          message.error('生成成功但未返回图片 URL')
          return
        }
        setForm(f => ({ ...f, portrait_url: url, portrait_asset_id: assetId }))
        message.success(assetId ? '立绘已生成并入库' : '立绘已生成')
      }
    } catch (e: any) {
      message.error(e?.message || '生成立绘失败')
    } finally {
      setGeneratingPortrait(false)
    }
  }

  const handleSave = async () => {
    if (!form.name.trim()) { message.warning('请输入角色名称'); return }
    if (form.source_types.length === 0) { message.warning('请至少选择一个来源类型'); return }
    setSaving(true)
    try {
      if (editingCharacter) {
        const req: CharacterUpdateRequest = {}
        if (form.name !== editingCharacter.name) req.name = form.name
        if (form.role !== editingCharacter.role) req.role = form.role
        if (JSON.stringify(form.source_types) !== JSON.stringify(editingCharacter.source_types)) req.source_types = form.source_types
        if (form.appearance !== editingCharacter.appearance) req.appearance = form.appearance
        if (form.personality !== editingCharacter.personality) req.personality = form.personality
        if (form.costume_hint !== editingCharacter.costume_hint) req.costume_hint = form.costume_hint
        if (form.background !== editingCharacter.background) req.background = form.background
        if (form.age_range !== editingCharacter.age_range) req.age_range = form.age_range
        if (JSON.stringify(form.tags) !== JSON.stringify(editingCharacter.tags)) req.tags = form.tags
        if (form.portrait_url !== editingCharacter.portrait_url) req.portrait_url = form.portrait_url
        if ((form.portrait_asset_id || '') !== (editingCharacter.portrait_asset_id || '')) req.portrait_asset_id = form.portrait_asset_id || ''
        await updateCharacter(editingCharacter.id, req)
        message.success('角色已更新')
      } else {
        await createCharacter(form)
        message.success('角色已创建')
      }
      setFormModalOpen(false)
      setEditingCharacter(null)
      load(page, { keyword, source_type: filterSourceType, role: filterRole, is_favorite: filterFavorite || undefined })
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const addTagToForm = () => {
    const t = tagInput.trim()
    if (t && !form.tags?.includes(t)) {
      setForm(f => ({ ...f, tags: [...(f.tags || []), t ] }))
    }
    setTagInput('')
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ color: '#fff', marginBottom: 4 }}>
            <TeamOutlined style={{ color: '#00d4ff', marginRight: 8 }} />
            角色管理
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            共 {total} 个角色 · 支持 AI生成 / 本地素材 / 真人对白 等来源标签
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="large"
          onClick={() => { setEditingCharacter(null); setForm({ name: '', role: 'supporting', source_types: [], appearance: '', personality: '', costume_hint: '', background: '', age_range: '', tags: [], portrait_url: '', portrait_asset_id: '' }); setFormModalOpen(true) }}
          style={{ height: 44 }}
        >
          新建角色
        </Button>
      </div>

      <Card style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)', marginBottom: 20 }}
        styles={{ body: { padding: '16px 20px' } }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 13, marginRight: 4 }}>来源：</Text>
          <Tag style={{ cursor: 'pointer', background: !filterSourceType ? 'rgba(0,212,255,0.15)' : 'transparent', border: !filterSourceType ? '1px solid rgba(0,212,255,0.5)' : '1px solid rgba(255,255,255,0.15)', color: !filterSourceType ? '#00d4ff' : '#8b8ba8' }} onClick={() => setFilterSourceType(null)}>全部</Tag>
          {CHARACTER_SOURCE_TYPE_OPTIONS.map(opt => {
            const active = filterSourceType === opt.value
            return (
              <Tag key={opt.value} style={{ cursor: 'pointer', background: active ? `${SOURCE_TYPE_COLORS[opt.value]}20` : 'transparent', border: active ? `1px solid ${SOURCE_TYPE_COLORS[opt.value]}` : '1px solid rgba(255,255,255,0.15)', color: active ? SOURCE_TYPE_COLORS[opt.value] : '#8b8ba8' }} onClick={() => setFilterSourceType(active ? null : opt.value)}>
                {SOURCE_TYPE_ICONS[opt.value]} {opt.label}
              </Tag>
            )
          })}
          <Divider type="vertical" style={{ borderColor: 'rgba(255,255,255,0.1)', height: 20, margin: '0 8px' }} />
          <Text type="secondary" style={{ fontSize: 13, marginRight: 4 }}>定位：</Text>
          <Select size="small" placeholder="全部定位" allowClear value={filterRole} onChange={v => setFilterRole(v)} style={{ width: 100 }}
            options={CHARACTER_ROLE_OPTIONS}
          />
          <Divider type="vertical" style={{ borderColor: 'rgba(255,255,255,0.1)', height: 20, margin: '0 8px' }} />
          <Tag style={{ cursor: 'pointer', background: filterFavorite ? 'rgba(245,158,11,0.15)' : 'transparent', border: filterFavorite ? '1px solid rgba(245,158,11,0.5)' : '1px solid rgba(255,255,255,0.15)', color: filterFavorite ? '#f59e0b' : '#8b8ba8' }}
            onClick={() => setFilterFavorite(f => !f)} icon={filterFavorite ? <StarFilled /> : <StarOutlined />}>
            仅收藏
          </Tag>
        </div>
        <Input placeholder="搜索角色名称..." prefix={<SearchOutlined style={{ color: '#8b8ba8' }} />} value={keyword}
          onChange={e => setKeyword(e.target.value)} allowClear style={{ background: '#12122a', maxWidth: 360 }} />
      </Card>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <Spin size="large" />
          <Paragraph style={{ color: '#8b8b9e', marginTop: 16 }}>加载中...</Paragraph>
        </div>
      ) : characters.length === 0 ? (
        <Empty description={<Text type="secondary">{keyword || filterSourceType || filterRole || filterFavorite ? '没有符合条件的角色' : '还没有角色，点击右上角新建'}</Text>} style={{ padding: '80px 0' }} />
      ) : (
        <Row gutter={[16, 16]}>
          {characters.map(character => (
            <Col key={character.id} xs={24} sm={12} md={8} lg={6}>
              <Card hoverable onClick={() => handleOpenDetail(character)}
                style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 12, overflow: 'hidden', position: 'relative' }}
                styles={{ body: { padding: 0 } }}
              >
                <div style={{ height: 160, background: `linear-gradient(135deg, ${SOURCE_TYPE_COLORS[character.source_types[0]] || '#1890ff'}20, #1a1a2e)`, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                  {character.portrait_url ? (
                    <img src={character.portrait_url} alt={character.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  ) : (
                    <Avatar size={80} icon={<UserOutlined />} style={{ background: `${SOURCE_TYPE_COLORS[character.source_types[0]] || '#1890ff'}40` }} />
                  )}
                  <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 4 }}>
                    {character.is_frozen && <Tag style={{ background: 'rgba(245,158,11,0.15)', border: `1px solid rgba(245,158,11,0.3)`, color: '#f59e0b' }}><LockOutlined /> 冻结</Tag>}
                    <Button type="text" size="small" icon={character.is_favorite ? <StarFilled style={{ color: '#f59e0b' }} /> : <StarOutlined style={{ color: '#8b8ba8' }} />}
                      onClick={e => { e.stopPropagation(); handleFavorite(character) }} style={{ background: 'rgba(255,255,255,0.06)', color: 'inherit' }} />
                  </div>
                  <div style={{ position: 'absolute', bottom: 8, left: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {character.source_types.slice(0, 2).map(st => (
                      <Tag key={st} style={{ background: `${SOURCE_TYPE_COLORS[st]}30`, border: `1px solid ${SOURCE_TYPE_COLORS[st]}60`, color: SOURCE_TYPE_COLORS[st], fontSize: 11, padding: '0 6px', lineHeight: '18px' }}>
                        {SOURCE_TYPE_ICONS[st]} {CHARACTER_SOURCE_TYPE_OPTIONS.find(o => o.value === st)?.label}
                      </Tag>
                    ))}
                  </div>
                </div>
                <div style={{ padding: '10px 12px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <Text strong style={{ color: '#fff', fontSize: 15 }} ellipsis>{character.name}</Text>
                    <Tag style={{ background: `${ROLE_COLORS[character.role]}20`, border: `1px solid ${ROLE_COLORS[character.role]}50`, color: ROLE_COLORS[character.role], fontSize: 11, padding: '0 4px', lineHeight: '16px' }}>
                      {CHARACTER_ROLE_OPTIONS.find(o => o.value === character.role)?.label}
                    </Tag>
                  </div>
                  {character.appearance && <Text style={{ color: '#8b8ba8', fontSize: 12 }} ellipsis>{character.appearance}</Text>}
                  {character.tags.length > 0 && (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                      {character.tags.slice(0, 3).map(tag => (
                        <Tag key={tag} style={{ fontSize: 11, background: 'rgba(255,255,255,0.06)', border: 'none', color: '#8b8ba8' }}>{tag}</Tag>
                      ))}
                      {character.tags.length > 3 && <Tag style={{ fontSize: 11, background: 'transparent', border: 'none', color: '#8b8ba8' }}>+{character.tags.length - 3}</Tag>}
                    </div>
                  )}
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {total > PAGE_SIZE && (
        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Button disabled={page === 1} onClick={() => { const p = page - 1; setPage(p); load(p, { keyword, source_type: filterSourceType, role: filterRole, is_favorite: filterFavorite || undefined }) }} style={{ marginRight: 8 }}>上一页</Button>
          <Text style={{ color: '#8b8ba8', margin: '0 16px' }}>第 {page} / {Math.ceil(total / PAGE_SIZE)} 页，共 {total} 条</Text>
          <Button disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => { const p = page + 1; setPage(p); load(p, { keyword, source_type: filterSourceType, role: filterRole, is_favorite: filterFavorite || undefined }) }}>下一页</Button>
        </div>
      )}

      {/* Detail Drawer */}
      <Drawer open={drawerOpen} onClose={() => { setDrawerOpen(false); setSelectedCharacter(null) }}
        title={<Space><UserOutlined style={{ color: '#00d4ff' }} /><span style={{ color: '#fff' }}>{selectedCharacter?.name}</span>
          {selectedCharacter && <Tag style={{ background: `${ROLE_COLORS[selectedCharacter.role]}20`, border: `1px solid ${ROLE_COLORS[selectedCharacter.role]}50`, color: ROLE_COLORS[selectedCharacter.role] }}>{CHARACTER_ROLE_OPTIONS.find(o => o.value === selectedCharacter.role)?.label}</Tag>}
          {selectedCharacter?.is_frozen && <Tag icon={<LockOutlined />} style={{ color: '#f59e0b', background: 'rgba(245,158,11,0.1)' }}>已冻结</Tag>}
        </Space>}
        width={480} styles={{ body: { background: '#0f0f23', padding: 0 } }}>
        {selectedCharacter && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {selectedCharacter.portrait_url && (
              <div style={{ height: 240, overflow: 'hidden' }}>
                <img src={selectedCharacter.portrait_url} alt={selectedCharacter.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              </div>
            )}
            <div style={{ padding: 20, flex: 1, overflow: 'auto' }}>
              <Tabs
                activeKey={drawerActiveTab}
                onChange={(k) => setDrawerActiveTab(k as 'detail' | 'logs')}
                items={[
                  {
                    key: 'detail',
                    label: '详情',
                    children: (
                      <>
              <div style={{ marginBottom: 16 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>来源类型</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                  {selectedCharacter.source_types.map(st => (
                    <Tag key={st} style={{ background: `${SOURCE_TYPE_COLORS[st]}20`, border: `1px solid ${SOURCE_TYPE_COLORS[st]}50`, color: SOURCE_TYPE_COLORS[st] }}>
                      {SOURCE_TYPE_ICONS[st]} {CHARACTER_SOURCE_TYPE_OPTIONS.find(o => o.value === st)?.label}
                    </Tag>
                  ))}
                </div>
              </div>
              <Collapse ghost defaultActiveKey={['appearance', 'personality', 'tags']} style={{ marginBottom: 16 }}>
                <Panel header={<Text style={{ color: '#00d4ff' }}>外观描述</Text>} key="appearance">
                  {selectedCharacter.appearance ? <Paragraph style={{ color: '#e0e0e0', whiteSpace: 'pre-wrap' }}>{selectedCharacter.appearance}</Paragraph> : <Text type="secondary">暂无</Text>}
                  {selectedCharacter.costume_hint && <><Text type="secondary" style={{ fontSize: 12 }}>服装提示</Text><Paragraph style={{ color: '#e0e0e0', whiteSpace: 'pre-wrap' }}>{selectedCharacter.costume_hint}</Paragraph></>}
                </Panel>
                <Panel header={<Text style={{ color: '#00d4ff' }}>性格特点</Text>} key="personality">
                  {selectedCharacter.personality ? <Paragraph style={{ color: '#e0e0e0', whiteSpace: 'pre-wrap' }}>{selectedCharacter.personality}</Paragraph> : <Text type="secondary">暂无</Text>}
                </Panel>
                <Panel header={<Text style={{ color: '#00d4ff' }}>背景故事</Text>} key="background">
                  {selectedCharacter.background ? <Paragraph style={{ color: '#e0e0e0', whiteSpace: 'pre-wrap' }}>{selectedCharacter.background}</Paragraph> : <Text type="secondary">暂无</Text>}
                </Panel>
              </Collapse>
              <div style={{ marginBottom: 16 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>自定义标签</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6, marginBottom: 8 }}>
                  {selectedCharacter.tags.map(tag => (
                    <Tag key={tag} closable onClose={() => handleRemoveTag(tag)} style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>{tag}</Tag>
                  ))}
                </div>
                <Space>
                  <Input size="small" placeholder="新标签" value={tagInput} onChange={e => setTagInput(e.target.value)} onPressEnter={() => { if (tagInput.trim()) { handleAddTag(tagInput.trim()); setTagInput('') } }} style={{ width: 120 }} />
                  <Button size="small" onClick={() => { if (tagInput.trim()) { handleAddTag(tagInput.trim()); setTagInput('') } }}>添加</Button>
                </Space>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <Statistic title="引用次数" value={selectedCharacter.use_count || 0} />
                {selectedCharacter.age_range && <Statistic title="年龄范围" value={selectedCharacter.age_range} />}
              </div>
              <Divider style={{ borderColor: 'rgba(255,255,255,0.08)' }} />
              <Space wrap>
                <Button icon={<EditOutlined />} onClick={() => { setEditingCharacter(selectedCharacter); setForm({ name: selectedCharacter.name, role: selectedCharacter.role, source_types: selectedCharacter.source_types, appearance: selectedCharacter.appearance, personality: selectedCharacter.personality, costume_hint: selectedCharacter.costume_hint, background: selectedCharacter.background, age_range: selectedCharacter.age_range, tags: selectedCharacter.tags, portrait_url: selectedCharacter.portrait_url, portrait_asset_id: selectedCharacter.portrait_asset_id || '' }); setDrawerOpen(false); setFormModalOpen(true) }}>编辑</Button>
                <Button icon={<ReadOutlined />} onClick={() => navigate(`/story?character_id=${selectedCharacter.id}`)}>在 Story Maker 中使用</Button>
                <Button icon={selectedCharacter.is_favorite ? <StarFilled style={{ color: '#f59e0b' }} /> : <StarOutlined />} onClick={() => handleFavorite(selectedCharacter)}>{selectedCharacter.is_favorite ? '取消收藏' : '收藏'}</Button>
                {selectedCharacter.portrait_url && !selectedCharacter.portrait_node_id && (
                  <Popconfirm
                    title="把现有立绘升级到资产中枢？"
                    description="将创建 AssetNode + Version + Representation，并绑定到此角色"
                    onConfirm={handleUpgradePortrait}
                    okText="升级"
                    cancelText="取消"
                  >
                    <Button icon={<DatabaseOutlined />} loading={upgradingPortrait}>升级到资产中枢</Button>
                  </Popconfirm>
                )}
                {selectedCharacter.portrait_node_id && (
                  <Tooltip title={`Node ID: ${selectedCharacter.portrait_node_id}`}>
                    <Tag color="green" icon={<DatabaseOutlined />} style={{ marginInlineStart: 0 }}>资产中枢已绑定</Tag>
                  </Tooltip>
                )}
                <Popconfirm title="确认删除此角色？" onConfirm={() => handleDelete(selectedCharacter)} okText="删除" cancelText="取消" okButtonProps={{ danger: true }}>
                  <Button danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>
              </Space>
                      </>
                    ),
                  },
                  {
                    key: 'logs',
                    label: (
                      <Space>
                        <HistoryOutlined />
                        生图日志
                        {portraitLogs.length > 0 && (
                          <Tag color="blue" style={{ marginInlineStart: 0 }}>{portraitLogs.length}</Tag>
                        )}
                      </Space>
                    ),
                    children: (
                      <CharacterPortraitLogsTab
                        logs={portraitLogs}
                        loading={portraitLogsLoading}
                        onRefresh={() => selectedCharacter && loadPortraitLogs(selectedCharacter.id)}
                      />
                    ),
                  },
                ]}
              />
            </div>
          </div>
        )}
      </Drawer>

      {/* Create/Edit Modal */}
      <Modal open={formModalOpen} title={editingCharacter ? '编辑角色' : '新建角色'} onCancel={() => { setFormModalOpen(false); setEditingCharacter(null) }}
        footer={<Space><Button onClick={() => { setFormModalOpen(false); setEditingCharacter(null) }}>取消</Button><Button type="primary" loading={saving} onClick={handleSave}>{editingCharacter ? '保存修改' : '创建角色'}</Button></Space>}
        width={640} destroyOnClose>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <Text strong style={{ color: '#fff' }}>基本信息</Text>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 8 }}>
              <Input placeholder="角色名称 *" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} maxLength={50} />
              <Select value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))}
                options={CHARACTER_ROLE_OPTIONS.map(o => ({ ...o, label: <Space><span style={{ width: 8, height: 8, borderRadius: '50%', background: ROLE_COLORS[o.value] || '#8b8ba8', display: 'inline-block' }} />{o.label}</Space> }))} />
            </div>
            <Input placeholder="年龄范围，如 20-25岁" value={form.age_range} onChange={e => setForm(f => ({ ...f, age_range: e.target.value }))} style={{ marginTop: 8 }} />
          </div>
          <div>
            <Text strong style={{ color: '#fff' }}>来源类型 *（可多选）</Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {CHARACTER_SOURCE_TYPE_OPTIONS.map(opt => {
                const selected = form.source_types?.includes(opt.value)
                return (
                  <Tag key={opt.value} style={{ cursor: 'pointer', border: selected ? `1px solid ${SOURCE_TYPE_COLORS[opt.value]}` : '1px solid rgba(255,255,255,0.15)', color: selected ? SOURCE_TYPE_COLORS[opt.value] : '#8b8ba8', background: selected ? `${SOURCE_TYPE_COLORS[opt.value]}15` : 'transparent', padding: '4px 10px', fontSize: 13 }}
                    onClick={() => setForm(f => ({ ...f, source_types: selected ? f.source_types.filter(t => t !== opt.value) : [...(f.source_types || []), opt.value] }))}>
                    {SOURCE_TYPE_ICONS[opt.value]} {opt.label}
                  </Tag>
                )
              })}
            </div>
          </div>
          <div>
            <Text strong style={{ color: '#00d4ff' }}>外观描述（用于 AI 生图提示词）</Text>
            <TextArea placeholder="外貌特征，如：黑长直、瓜子脸、肤白貌美..." value={form.appearance} onChange={e => setForm(f => ({ ...f, appearance: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
            <TextArea placeholder="服装提示，如：白色衬衫+黑色短裙、古典汉服..." value={form.costume_hint} onChange={e => setForm(f => ({ ...f, costume_hint: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
          </div>
          <div>
            <Text strong style={{ color: '#fff' }}>其他信息</Text>
            <TextArea placeholder="性格特点，如：温柔善良、傲娇..." value={form.personality} onChange={e => setForm(f => ({ ...f, personality: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
            <TextArea placeholder="背景故事（可选）" value={form.background} onChange={e => setForm(f => ({ ...f, background: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ color: '#fff' }}>立绘 / 参考图</Text>
              <Space size={4}>
                <Select
                  size="small"
                  style={{ width: 160 }}
                  placeholder="选择生图模型"
                  value={selectedPortraitBackend || undefined}
                  onChange={setSelectedPortraitBackend}
                  options={portraitBackends.map((b) => ({
                    label: b.name || b.model || b.provider,
                    value: b.name,
                  }))}
                  disabled={generatingPortrait}
                />
                <Button
                  size="small"
                  type="primary"
                  icon={<RobotOutlined />}
                  loading={generatingPortrait}
                  onClick={handleGeneratePortrait}
                  disabled={portraitBackends.length === 0}
                >
                  AI 生成立绘
                </Button>
              </Space>
            </div>
            <div style={{ marginTop: 10, padding: 12, borderRadius: 10, border: '1px solid rgba(0,212,255,0.18)', background: 'rgba(0,212,255,0.04)' }}>
              <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }} align="center">
                <Space size={8}>
                  <Text strong style={{ color: '#00d4ff' }}>完整生图提示词</Text>
                  <Tooltip title="这里的提示词会直接用于 AI 生成立绘，也可以复制到其他生图工具。">
                    <Tag color="cyan">可复制</Tag>
                  </Tooltip>
                </Space>
                <Space size={6} wrap>
                  <Button size="small" onClick={handleRefreshPortraitPrompt}>
                    根据角色信息生成
                  </Button>
                  <Button
                    size="small"
                    icon={<RobotOutlined />}
                    loading={optimizingPortraitPrompt}
                    onClick={handleOptimizePortraitPrompt}
                  >
                    AI 优化提示词
                  </Button>
                  <Button size="small" icon={<CopyOutlined />} onClick={handleCopyPortraitPrompt}>
                    复制
                  </Button>
                </Space>
              </Space>
              <TextArea
                value={portraitPromptDraft}
                onChange={e => setPortraitPromptDraft(e.target.value)}
                rows={8}
                placeholder="根据角色信息生成或手动编辑完整立绘提示词；AI 生成立绘会使用这里的内容。"
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
            </div>
            <Input placeholder="输入立绘图片 URL（也可由 AI 生成自动回填）" value={form.portrait_url} onChange={e => setForm(f => ({ ...f, portrait_url: e.target.value }))} style={{ marginTop: 8 }} />
            {form.portrait_url && <Image src={form.portrait_url} width={120} height={120} style={{ objectFit: 'cover', borderRadius: 8, marginTop: 8 }} fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" />}
            {form.portrait_asset_id && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#8b8ba8' }}>
                已绑定资产 ID: <span style={{ fontFamily: 'monospace' }}>{form.portrait_asset_id}</span>
              </div>
            )}
          </div>
          <div>
            <Text strong style={{ color: '#fff' }}>自定义标签</Text>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <Input placeholder="输入标签后回车添加" value={tagInput} onChange={e => setTagInput(e.target.value)} onPressEnter={addTagToForm} style={{ flex: 1 }} />
              <Button onClick={addTagToForm}>添加</Button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {(form.tags || []).map(tag => (
                <Tag key={tag} closable onClose={() => setForm(f => ({ ...f, tags: (f.tags || []).filter(t => t !== tag) }))} style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.3)', color: '#00d4ff' }}>{tag}</Tag>
              ))}
            </div>
          </div>
          {editingCharacter?.is_frozen && <Alert type="warning" message="此角色已冻结（生成后为保持一致性禁止修改外观描述）" showIcon />}
        </div>
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 角色立绘生成日志 Tab
// ---------------------------------------------------------------------------

interface PortraitLogItem {
  id: string
  scene: string
  ref_id: string | null
  stage: string
  provider: string
  model: string
  status: string
  prompt: string
  request: Record<string, any>
  raw_response: string
  normalized: Record<string, any>
  validation_error: string
  created_at: string
}

const STAGE_LABELS: Record<string, string> = {
  portrait_generate: '立绘生成',
  generate_image: '调用生图',
  asset_hub_sync: '资产中枢写入',
}

function CharacterPortraitLogsTab({
  logs,
  loading,
  onRefresh,
}: {
  logs: PortraitLogItem[]
  loading: boolean
  onRefresh: () => void
}) {
  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-',
    },
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 110,
      render: (v: string) => <Tag>{STAGE_LABELS[v] || v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string) => (
        <Tag color={v === 'success' ? 'green' : 'red'}>{v === 'success' ? '成功' : '失败'}</Tag>
      ),
    },
    {
      title: '模型',
      dataIndex: 'model',
      width: 180,
      ellipsis: true,
      render: (v: string) => v ? <Text style={{ color: '#e0e0e0' }}>{v}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: 'Prompt',
      dataIndex: 'prompt',
      ellipsis: true,
      render: (v: string) => v ? <Text style={{ color: '#e0e0e0' }}>{v.slice(0, 60)}{v.length > 60 ? '...' : ''}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: '错误',
      dataIndex: 'validation_error',
      width: 150,
      ellipsis: true,
      render: (v: string) => v ? <Text type="danger">{v}</Text> : <Text type="secondary">-</Text>,
    },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          记录此角色的立绘生成请求：Prompt、模型、参数、响应、错误。
        </Text>
        <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
          刷新
        </Button>
      </Space>
      {logs.length ? (
        <Table
          size="small"
          rowKey="id"
          columns={columns}
          dataSource={logs}
          loading={loading}
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender: (record: PortraitLogItem) => (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                {record.prompt && (
                  <LogTextBlock title="Prompt" value={record.prompt} rows={4} />
                )}
                {Object.keys(record.request || {}).length > 0 && (
                  <LogTextBlock
                    title="请求参数"
                    value={JSON.stringify(record.request, null, 2)}
                    rows={6}
                  />
                )}
                {record.raw_response && (
                  <LogTextBlock title="响应" value={record.raw_response} rows={4} />
                )}
                {Object.keys(record.normalized || {}).length > 0 && (
                  <LogTextBlock
                    title="结果"
                    value={JSON.stringify(record.normalized, null, 2)}
                    rows={6}
                  />
                )}
                {record.validation_error && (
                  <LogTextBlock title="错误" value={record.validation_error} rows={3} />
                )}
              </Space>
            ),
          }}
        />
      ) : (
        <Empty description={loading ? '加载中...' : '暂无生图日志'} />
      )}
    </Space>
  )
}

function LogTextBlock({ title, value, rows }: { title: string; value: string; rows: number }) {
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
      <Input.TextArea
        value={value}
        readOnly
        autoSize={{ minRows: Math.min(rows, 12), maxRows: 12 }}
        style={{
          marginTop: 4,
          background: 'rgba(0,0,0,0.3)',
          borderColor: 'rgba(255,255,255,0.1)',
          color: '#e0e0e0',
          fontFamily: 'monospace',
          fontSize: 12,
        }}
      />
    </div>
  )
}
