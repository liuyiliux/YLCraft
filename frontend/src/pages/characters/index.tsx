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
} from 'antd'
import {
  UserOutlined, StarOutlined, StarFilled, LockOutlined,
  DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined,
  HeartOutlined, RobotOutlined, PictureOutlined, TeamOutlined, ReadOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'

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
    personality: '', costume_hint: '', background: '', age_range: '', tags: [], portrait_url: '',
  })
  const [saving, setSaving] = useState(false)

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
          onClick={() => { setEditingCharacter(null); setForm({ name: '', role: 'supporting', source_types: [], appearance: '', personality: '', costume_hint: '', background: '', age_range: '', tags: [], portrait_url: '' }); setFormModalOpen(true) }}
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
                <Button icon={<EditOutlined />} onClick={() => { setEditingCharacter(selectedCharacter); setForm({ name: selectedCharacter.name, role: selectedCharacter.role, source_types: selectedCharacter.source_types, appearance: selectedCharacter.appearance, personality: selectedCharacter.personality, costume_hint: selectedCharacter.costume_hint, background: selectedCharacter.background, age_range: selectedCharacter.age_range, tags: selectedCharacter.tags, portrait_url: selectedCharacter.portrait_url }); setDrawerOpen(false); setFormModalOpen(true) }}>编辑</Button>
                <Button icon={<ReadOutlined />} onClick={() => navigate(`/story?character_id=${selectedCharacter.id}`)}>在 Story Maker 中使用</Button>
                <Button icon={selectedCharacter.is_favorite ? <StarFilled style={{ color: '#f59e0b' }} /> : <StarOutlined />} onClick={() => handleFavorite(selectedCharacter)}>{selectedCharacter.is_favorite ? '取消收藏' : '收藏'}</Button>
                <Popconfirm title="确认删除此角色？" onConfirm={() => handleDelete(selectedCharacter)} okText="删除" cancelText="取消" okButtonProps={{ danger: true }}>
                  <Button danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>
              </Space>
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
            <Text strong style={{ color: '#fff' }}>立绘 / 参考图 URL</Text>
            <Input placeholder="输入立绘图片 URL" value={form.portrait_url} onChange={e => setForm(f => ({ ...f, portrait_url: e.target.value }))} style={{ marginTop: 8 }} />
            {form.portrait_url && <Image src={form.portrait_url} width={120} height={120} style={{ objectFit: 'cover', borderRadius: 8, marginTop: 8 }} fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" />}
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
