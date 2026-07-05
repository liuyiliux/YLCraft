/**
 * YLCraft — 角色管理页面
 */

import { useState, useCallback, useEffect, useMemo } from 'react'
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
  CheckOutlined, FileImageOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { chat, listAssets, listConnectors, listCreativeProjects, listGenerationLogsGlobal } from '../../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const { Panel } = Collapse

const PAGE_SIZE = 24
const CHARACTER_FORM_MODAL_WIDTH = 860
const PORTRAIT_PROMPT_LANGUAGE_RULE =
  '语言要求：最终提示词必须以中文开头，主体必须使用中文输出；如果输入里有英文长句或英文段落，必须翻译并改写为中文，不要照抄；只允许在末尾保留少量必要英文模型关键词、风格标签或固定短语，例如 character reference sheet, clean background。'

const getModalPopupContainer = (triggerNode: HTMLElement) =>
  (triggerNode.closest('.ant-modal') as HTMLElement | null) || triggerNode.parentElement || document.body

const compactTagSelectProps = {
  maxTagCount: 'responsive' as const,
  maxTagTextLength: 18,
  listHeight: 192,
  popupMatchSelectWidth: true,
  getPopupContainer: getModalPopupContainer,
  style: { width: '100%' },
  dropdownStyle: { maxWidth: 'min(420px, calc(100vw - 48px))' },
}

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
  stock_footage: <DatabaseOutlined />,
  other: <ReadOutlined />,
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

type PortraitPreset =
  | 'main_portrait'
  | 'headshot_icon'
  | 'key_visual'
  | 'multi_view_sheet'
  | 'identity_board_16_9'
  | 'expression_pack'
  | 'expression_grid_3x3'
  | 'action_pose_pack'
  | 'pose_grid_3x3'
  | 'transparent_or_white_background'
  | 'expression_pose_sheet'

const PORTRAIT_PRESET_OPTIONS: { label: string; value: PortraitPreset }[] = [
  { label: '主立绘', value: 'main_portrait' },
  { label: '头像/半身', value: 'headshot_icon' },
  { label: 'Key Visual', value: 'key_visual' },
  { label: '多视图', value: 'multi_view_sheet' },
  { label: '16:9 身份板', value: 'identity_board_16_9' },
  { label: '表情包', value: 'expression_pack' },
  { label: '表情九宫格', value: 'expression_grid_3x3' },
  { label: '动作姿态', value: 'action_pose_pack' },
  { label: '动作九宫格', value: 'pose_grid_3x3' },
  { label: '透明/白底', value: 'transparent_or_white_background' },
]

const PORTRAIT_PRESET_HELP: Record<PortraitPreset, { title: string; detail: string; sizeHint?: string }> = {
  main_portrait: {
    title: '第一步锁定角色身份',
    detail: '优先生成单人主立绘，先把脸、发型、服装和标志物稳定下来，再用作后续九宫格和分镜参考。',
    sizeHint: '建议 1024x1536 或 1024x1024。',
  },
  headshot_icon: {
    title: '头像/半身用于头像和对话框',
    detail: '聚焦五官、眼睛和服装领口，不适合用来判断完整服装比例。',
  },
  key_visual: {
    title: '氛围宣传图',
    detail: '适合封面、海报和PV氛围，不建议作为角色服装结构和比例的最终基准。',
  },
  multi_view_sheet: {
    title: '生产级三视图',
    detail: '用于锁定正面、侧面、背面比例和服装结构，是后续漫画一致性最重要的参考之一。',
  },
  identity_board_16_9: {
    title: '角色身份板',
    detail: '用于快速总览角色气质、道具和设定摘要，不要把完整九宫格和大量说明都塞进一张图。',
  },
  expression_pack: {
    title: '表情包设定',
    detail: '适合生成多个头像表情，要求同脸同发同配饰。',
  },
  expression_grid_3x3: {
    title: '表情九宫格用于切片素材',
    detail: '九格会稀释脸部细节，最好先有主立绘或三视图参考图，再生成表情九宫格。',
    sizeHint: '建议尽量用 1536x1536、2048x2048 或模型支持的更大方图。',
  },
  action_pose_pack: {
    title: '动作姿态设定板',
    detail: '用于少量姿态参考，动作要简单，避免道具和大幅度动作抢走脸部细节。',
  },
  pose_grid_3x3: {
    title: '动作九宫格用于切成9张动作素材',
    detail: '不要第一次就生成九宫格锁脸。推荐先生成主立绘/多视图，再用同一角色参考图生成九个简单站姿。',
    sizeHint: '建议尽量用 1536x1536、2048x2048 或模型支持的更大方图。',
  },
  transparent_or_white_background: {
    title: '透明/白底素材',
    detail: '适合抠图、Live2D、分镜合成和漫画复用。',
  },
  expression_pose_sheet: {
    title: '紧凑表情+姿态板',
    detail: '适合快速探索，但一致性不如先锁脸再分别生成表情/动作。',
  },
}

const REFERENCE_FIRST_PRESETS: PortraitPreset[] = [
  'expression_grid_3x3',
  'action_pose_pack',
  'pose_grid_3x3',
  'expression_pose_sheet',
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
  signature_items: string[]
  expressions: string[]
  poses: string[]
  visual_consistency: string
  background: string
  age_range: string
  identity?: Record<string, any>
  motivation?: Record<string, any>
  speech?: Record<string, any>
  behavior?: Record<string, any>
  ability?: Record<string, any>
  arc?: Record<string, any>
  tags: string[]
  portrait_url: string
  portrait_asset_id: string
  portrait_node_id?: string | null
  is_favorite: boolean
  is_frozen: boolean
  role_label: string
  use_count: number
  created_at: string
  world_usages?: CharacterWorldUsage[]
}

export interface CharacterWorldUsage {
  id: string
  character_id: string
  story_id: string
  project_id: string
  project_title: string
  project_type: string
  world_id: string
  world_name: string
  usage_role: string
  local_alias: string
  local_identity: string
  local_faction: string
  local_status: string
  local_costume: string
  local_prompt_tags: string[]
  ooc_notes: string
  off_model_notes: string
  bible_overrides: Record<string, any>
  visual_overrides: Record<string, any>
  linked_at: string
  updated_at: string
}

interface CreativeProjectOption {
  id: string
  title: string
  project_type?: string
  settings?: Record<string, any>
  metadata?: Record<string, any>
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
  signature_items?: string[]
  expressions?: string[]
  poses?: string[]
  visual_consistency?: string
  background?: string
  age_range?: string
  identity?: Record<string, any>
  motivation?: Record<string, any>
  speech?: Record<string, any>
  behavior?: Record<string, any>
  ability?: Record<string, any>
  arc?: Record<string, any>
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
  signature_items?: string[]
  expressions?: string[]
  poses?: string[]
  visual_consistency?: string
  background?: string
  age_range?: string
  identity?: Record<string, any>
  motivation?: Record<string, any>
  speech?: Record<string, any>
  behavior?: Record<string, any>
  ability?: Record<string, any>
  arc?: Record<string, any>
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

interface AssetImageItem {
  id: string
  title?: string
  type?: string
  thumbnail_url?: string
  cover_url?: string
  source_url?: string
  width?: number
  height?: number
  platform?: string
  source_type?: string
  created_at?: string
  metadata?: Record<string, any>
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
    character: Character
  }
}

export interface PortraitPromptPreviewResponse {
  success: boolean
  detail?: string
  data?: {
    preset: PortraitPreset
    prompt: string
    negative_prompt: string
    visual_profile_snapshot: Record<string, any>
    prompt_template_version: string
  }
}

export interface PortraitVersionItem {
  id: string
  version_number: number
  created_at: string | null
  model: string
  provider: string
  preset: string
  prompt: string
  negative_prompt: string
  image_url: string
  file_path: string
  representation_id: string | null
  width?: number | null
  height?: number | null
  is_main: boolean
  params: Record<string, any>
}

export interface PortraitSliceItem {
  node_id: string
  version_id?: string | null
  representation_id?: string | null
  title: string
  label: string
  grid_type: string
  grid_index: number
  row: number
  col: number
  source_version_id: string
  source_representation_id: string
  source_preset: string
  file_path: string
  image_url: string
  width?: number | null
  height?: number | null
  created_at?: string | null
}

export function listCharacterPortraitVersions(
  characterId: string
): Promise<{ success: boolean; detail?: string; data?: { node_id: string | null; versions: PortraitVersionItem[] } }> {
  return fetch(`/api/v1/characters/${characterId}/portrait/versions`, {
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function listCharacterPortraitSlices(
  characterId: string,
): Promise<{ success: boolean; detail?: string; data?: { node_id: string | null; items: PortraitSliceItem[] } }> {
  return fetch(`/api/v1/characters/${characterId}/portrait/slices`, {
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function setCharacterMainPortraitVersion(
  characterId: string,
  versionId: string,
): Promise<{ success: boolean; detail?: string; data?: { character: Character; portrait_url: string } }> {
  return fetch(`/api/v1/characters/${characterId}/portrait/versions/${versionId}/set-main`, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function sliceCharacterPortraitGrid(
  characterId: string,
  versionId: string,
  data: {
    grid_type?: 'auto' | 'expression' | 'pose'
    rows?: number
    cols?: number
    overwrite_existing?: boolean
  } = {},
): Promise<{
  success: boolean
  detail?: string
  data?: {
    source_version_id: string
    grid_type: string
    rows: number
    cols: number
    reused?: boolean
    items: Array<{
      node_id: string
      version_id?: string
      representation_id?: string
      file_path?: string
      label: string
      index: number
      row: number
      col: number
      width?: number
      height?: number
      reused?: boolean
    }>
  }
}> {
  return fetch(`/api/v1/characters/${characterId}/portrait/versions/${versionId}/slice-grid`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({
      grid_type: data.grid_type || 'auto',
      rows: data.rows || 3,
      cols: data.cols || 3,
      overwrite_existing: Boolean(data.overwrite_existing),
    }),
  }).then(r => r.json())
}

export function enrichCharacter(
  characterId: string,
  data: {
    mode?: 'fill_missing' | 'rewrite'
    context?: string
    apply?: boolean
    provider?: string
    model?: string
  }
): Promise<{
  success: boolean
  detail?: string
  data?: {
    mode: string
    proposal: Record<string, any>
    merged: Record<string, any>
    applied_fields: string[]
    character: Character | null
    provider: string
    model: string
  }
}> {
  return fetch(`/api/v1/characters/${characterId}/enrich`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

export function previewCharacterPortraitPrompt(
  characterId: string,
  data: {
    preset?: PortraitPreset
    visual_profile?: Record<string, any>
    style_override?: string
    negative_override?: string
    language?: string
  }
): Promise<PortraitPromptPreviewResponse> {
  return fetch(`/api/v1/characters/${characterId}/portrait/prompt-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

export function generateCharacterPortraitViaAssetHub(
  characterId: string,
  data: {
    prompt: string
    provider?: string
    size?: string
    n?: number
    preset?: PortraitPreset
    negative_prompt?: string
    reference_images?: string[]
    visual_profile?: Record<string, any>
    style_override?: string
    negative_override?: string
    set_as_main?: boolean
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

export function listCharacterWorldUsages(characterId: string): Promise<{ success: boolean; data: CharacterWorldUsage[]; detail?: string }> {
  return fetch(`/api/v1/characters/${characterId}/world-usages`, {
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

export function linkCharacterToWorld(characterId: string, data: Record<string, any>) {
  return fetch(`/api/v1/characters/${characterId}/link-story`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

export function updateCharacterWorldUsage(characterId: string, usageId: string, data: Record<string, any>) {
  return fetch(`/api/v1/characters/${characterId}/world-usages/${usageId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  }).then(r => r.json())
}

export function deleteCharacterWorldUsage(characterId: string, usageId: string) {
  return fetch(`/api/v1/characters/${characterId}/world-usages/${usageId}`, {
    method: 'DELETE',
    headers: { 'Accept': 'application/json' },
  }).then(r => r.json())
}

/**
 * 快速生成立绘路径（保留行为）—— task 4.5
 *
 * 当用户仅填写 appearance / costume_hint 时，此函数从表单字段构建完整立绘提示词，
 * 无需依赖 visual_profile / identity_json / Bible 字段。
 * 该路径与资产中枢的 build_portrait_prompt 并行存在，确保轻量角色也能一键生图。
 */
function buildCharacterPortraitPrompt(form: CharacterCreateRequest): string {
  const roleLabel = CHARACTER_ROLE_OPTIONS.find(o => o.value === form.role)?.label || form.role || '角色'
  const sourceLabels = (form.source_types || [])
    .map(value => CHARACTER_SOURCE_TYPE_OPTIONS.find(o => o.value === value)?.label || value)
    .filter(Boolean)
  const tags = (form.tags || []).filter(Boolean)
  const signatureItems = (form.signature_items || []).filter(Boolean)
  const expressions = (form.expressions || []).filter(Boolean)
  const poses = (form.poses || []).filter(Boolean)
  const lines = [
    '单人角色立绘，完整角色设定图，适合作为后续漫画/短剧分镜的一致性参考图。',
    form.name ? `角色名：${form.name}` : '',
    roleLabel ? `角色定位：${roleLabel}` : '',
    form.age_range ? `年龄范围：${form.age_range}` : '',
    sourceLabels.length ? `来源/风格标签：${sourceLabels.join('、')}` : '',
    form.appearance ? `外貌特征：${form.appearance.trim()}` : '',
    form.costume_hint ? `服装与配饰：${form.costume_hint.trim()}` : '',
    signatureItems.length ? `角色标志物：${signatureItems.join('、')}` : '',
    expressions.length ? `常用表情：${expressions.join('、')}` : '',
    poses.length ? `常用姿态：${poses.join('、')}` : '',
    form.visual_consistency ? `一致性规则：${form.visual_consistency.trim()}` : '',
    form.personality ? `性格气质：${form.personality.trim()}` : '',
    form.background ? `角色背景暗示：${form.background.trim()}` : '',
    tags.length ? `补充标签：${tags.join('、')}` : '',
    '构图要求：单人，正面或轻微三分之二角度，全身或膝上立绘，头发、五官、服装、配饰清晰可辨，站姿自然，轮廓干净。',
    '画面要求：简洁纯色或浅灰背景，无复杂场景，不遮挡身体，不裁切头部和脚部，适合作为角色卡、参考图和后续一致性生图素材。',
    PORTRAIT_PROMPT_LANGUAGE_RULE,
    '质量要求：高质量，细节明确，面部稳定，服饰结构准确，干净线条，统一光照，专业角色设计，character reference sheet, clean background.',
    '避免：多人、背影、夸张透视、过度遮挡、低清晰度、畸形手指、脸部崩坏、文字、水印、logo、复杂背景。',
  ]
  return lines.filter(Boolean).join('\n')
}

function buildVisualProfileOverride(form: CharacterCreateRequest): Record<string, any> {
  const visualProfile = form.identity?.visual_profile || {}
  const data = {
    ...visualProfile,
    face: visualProfile.face || form.appearance || '',
    temperament: visualProfile.temperament || form.personality || '',
    costume: visualProfile.costume || form.costume_hint || '',
    signature_items: visualProfile.signature_items || form.signature_items || [],
    expression_set: visualProfile.expression_set || form.expressions || [],
    pose_set: visualProfile.pose_set || form.poses || [],
    visual_consistency: [visualProfile.visual_consistency, form.visual_consistency].filter(Boolean).join('\n'),
  }
  return Object.fromEntries(
    Object.entries(data).filter(([, value]) => {
      if (Array.isArray(value)) return value.length > 0
      return value !== undefined && value !== null && String(value).trim() !== ''
    }),
  )
}

function getSavedPortraitPrompts(form: CharacterCreateRequest): Record<string, { prompt?: string; negative_prompt?: string }> {
  const saved = form.identity?.visual_profile?.portrait_prompts
  return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}
}

function getSavedPortraitPrompt(form: CharacterCreateRequest, preset: PortraitPreset) {
  const saved = getSavedPortraitPrompts(form)[preset]
  return saved && typeof saved === 'object' ? saved : null
}

function mergePortraitPromptDrafts(
  form: CharacterCreateRequest,
  selectedPreset: PortraitPreset,
  prompt: string,
  negativePrompt: string,
  cache: Partial<Record<PortraitPreset, { prompt: string; negativePrompt: string }>>,
): CharacterCreateRequest {
  const promptEntries: Record<string, { prompt: string; negative_prompt: string }> = {
    ...getSavedPortraitPrompts(form),
  } as Record<string, { prompt: string; negative_prompt: string }>
  Object.entries(cache).forEach(([preset, item]) => {
    if (!item) return
    promptEntries[preset] = {
      prompt: item.prompt || '',
      negative_prompt: item.negativePrompt || '',
    }
  })
  promptEntries[selectedPreset] = {
    prompt: prompt || '',
    negative_prompt: negativePrompt || '',
  }
  return {
    ...form,
    identity: {
      ...(form.identity || {}),
      visual_profile: {
        ...((form.identity || {}).visual_profile || {}),
        portrait_prompts: promptEntries,
      },
    },
  }
}

function cleanImageUrls(urls: any[]): string[] {
  return Array.from(new Set(urls.map(url => String(url || '').trim()).filter(Boolean)))
}

function getVisualProfileReferenceImages(form: CharacterCreateRequest): string[] {
  const raw = form.identity?.visual_profile?.reference_image_urls
  return Array.isArray(raw) ? cleanImageUrls(raw) : []
}

function getIdentityReferenceImage(form: CharacterCreateRequest): string {
  return String(form.identity?.visual_profile?.identity_reference_url || form.portrait_url || '').trim()
}

function shouldAutoAttachMainPortrait(preset: PortraitPreset): boolean {
  return REFERENCE_FIRST_PRESETS.includes(preset)
}

function getGenerationReferenceImages(form: CharacterCreateRequest, preset: PortraitPreset): string[] {
  const identityReference = getIdentityReferenceImage(form)
  return cleanImageUrls([
    ...getVisualProfileReferenceImages(form),
    ...(shouldAutoAttachMainPortrait(preset) && identityReference ? [identityReference] : []),
  ])
}

function mergeReferenceImagesIntoForm(form: CharacterCreateRequest, referenceImages: string[]): CharacterCreateRequest {
  return {
    ...form,
    identity: {
      ...(form.identity || {}),
      visual_profile: {
        ...((form.identity || {}).visual_profile || {}),
        reference_image_urls: cleanImageUrls(referenceImages),
      },
    },
  }
}

function mergeIdentityReferenceIntoForm(
  form: CharacterCreateRequest,
  url: string,
  versionId?: string,
  representationId?: string | null,
): CharacterCreateRequest {
  const referenceUrl = String(url || '').trim()
  const referenceImages = cleanImageUrls([referenceUrl, ...getVisualProfileReferenceImages(form)])
  return {
    ...form,
    identity: {
      ...(form.identity || {}),
      visual_profile: {
        ...((form.identity || {}).visual_profile || {}),
        ...(referenceUrl ? { identity_reference_url: referenceUrl } : {}),
        ...(versionId ? { identity_reference_version_id: versionId } : {}),
        ...(representationId ? { identity_reference_representation_id: representationId } : {}),
        reference_image_urls: referenceImages,
      },
    },
  }
}

function buildCharacterEnrichmentContext(character: Character): string {
  const data = {
    name: character.name,
    role: character.role,
    source_types: character.source_types || [],
    age_range: character.age_range || '',
    appearance: character.appearance || '',
    costume_hint: character.costume_hint || '',
    personality: character.personality || '',
    background: character.background || '',
    visual_consistency: character.visual_consistency || '',
    signature_items: character.signature_items || [],
    expressions: character.expressions || [],
    poses: character.poses || [],
    tags: character.tags || [],
    identity: character.identity || {},
    motivation: character.motivation || {},
    speech: character.speech || {},
    behavior: character.behavior || {},
    ability: character.ability || {},
    arc: character.arc || {},
    world_usages: (character.world_usages || []).map((usage) => ({
      project_title: usage.project_title,
      world_name: usage.world_name,
      usage_role: usage.usage_role,
      local_alias: usage.local_alias,
      local_identity: usage.local_identity,
      local_faction: usage.local_faction,
      local_costume: usage.local_costume,
      local_prompt_tags: usage.local_prompt_tags || [],
      ooc_notes: usage.ooc_notes,
      off_model_notes: usage.off_model_notes,
    })),
  }
  return [
    '请基于下面“当前角色完整资料”补全，不要忽略已有字段；fill_missing 模式只补空缺，rewrite 模式也必须保留核心身份。',
    JSON.stringify(data, null, 2),
  ].join('\n')
}

function cleanPromptResponse(content: string): string {
  const trimmed = (content || '').trim()
  if (!trimmed) return ''
  return trimmed
    .replace(/^```(?:text|markdown|json)?/i, '')
    .replace(/```$/i, '')
    .trim()
}

function getAssetReferenceUrl(asset: AssetImageItem): string {
  const sourceUrl = asset.source_url || ''
  if (sourceUrl.startsWith('/api/') || sourceUrl.startsWith('http') || sourceUrl.startsWith('data:')) {
    return sourceUrl
  }
  if (asset.id) return `/api/v1/assets/${asset.id}/thumbnail?original=true`
  return asset.thumbnail_url || asset.cover_url || ''
}

function getAssetPreviewUrl(asset: AssetImageItem): string {
  return asset.thumbnail_url || asset.cover_url || getAssetReferenceUrl(asset)
}

function formatImageSizeLabel(item: { width?: number | null; height?: number | null }): string {
  return item.width && item.height ? `${item.width}x${item.height}` : ''
}

function emptyCharacterForm(): CharacterCreateRequest {
  return {
    name: '',
    role: 'supporting',
    source_types: [],
    appearance: '',
    personality: '',
    costume_hint: '',
    signature_items: [],
    expressions: [],
    poses: [],
    visual_consistency: '',
    background: '',
    age_range: '',
    identity: {},
    motivation: {},
    speech: {},
    behavior: {},
    ability: {},
    arc: {},
    tags: [],
    portrait_url: '',
    portrait_asset_id: '',
  }
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
  const [form, setForm] = useState<CharacterCreateRequest>(emptyCharacterForm())
  const [saving, setSaving] = useState(false)
  // 角色立绘 AI 生图状态
  const [portraitBackends, setPortraitBackends] = useState<ImageBackendInfo[]>([])
  const [selectedPortraitBackend, setSelectedPortraitBackend] = useState<string>('')
  const [selectedPortraitSize, setSelectedPortraitSize] = useState<string>('1024x1024')
  const [generatingPortrait, setGeneratingPortrait] = useState(false)
  const [portraitPromptDraft, setPortraitPromptDraft] = useState('')
  const [portraitNegativePromptDraft, setPortraitNegativePromptDraft] = useState('')
  const [selectedPortraitPreset, setSelectedPortraitPreset] = useState<PortraitPreset>('main_portrait')
  const [portraitPromptCache, setPortraitPromptCache] = useState<Partial<Record<PortraitPreset, { prompt: string; negativePrompt: string }>>>({})
  const [previewingPortraitPrompt, setPreviewingPortraitPrompt] = useState(false)
  const [optimizingPortraitPrompt, setOptimizingPortraitPrompt] = useState(false)
  const [llmConnectors, setLlmConnectors] = useState<any[]>([])
  const [selectedEnrichProvider, setSelectedEnrichProvider] = useState<string>('')
  const [selectedEnrichModel, setSelectedEnrichModel] = useState<string>('')
  const [referencePickerOpen, setReferencePickerOpen] = useState(false)
  const [referenceAssetSearch, setReferenceAssetSearch] = useState('')
  const [referenceAssets, setReferenceAssets] = useState<AssetImageItem[]>([])
  const [referenceAssetsLoading, setReferenceAssetsLoading] = useState(false)
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
  const [portraitVersions, setPortraitVersions] = useState<PortraitVersionItem[]>([])
  const [portraitVersionsLoading, setPortraitVersionsLoading] = useState(false)
  const [portraitSlices, setPortraitSlices] = useState<PortraitSliceItem[]>([])
  const [portraitSlicesLoading, setPortraitSlicesLoading] = useState(false)
  const [settingMainPortrait, setSettingMainPortrait] = useState<string>('')
  const [slicingPortraitVersion, setSlicingPortraitVersion] = useState<string>('')
  const [enrichingCharacter, setEnrichingCharacter] = useState(false)
  const [worldUsages, setWorldUsages] = useState<CharacterWorldUsage[]>([])
  const [worldUsagesLoading, setWorldUsagesLoading] = useState(false)
  const [creativeProjects, setCreativeProjects] = useState<CreativeProjectOption[]>([])
  const [worldUsageModalOpen, setWorldUsageModalOpen] = useState(false)
  const [editingWorldUsage, setEditingWorldUsage] = useState<CharacterWorldUsage | null>(null)
  const [worldUsageSaving, setWorldUsageSaving] = useState(false)
  const [worldUsageForm, setWorldUsageForm] = useState({
    story_id: '',
    world_id: '',
    world_name: '',
    usage_role: '',
    local_alias: '',
    local_identity: '',
    local_faction: '',
    local_status: 'active',
    local_costume: '',
    local_prompt_tags: [] as string[],
    ooc_notes: '',
    off_model_notes: '',
  })
  const [drawerActiveTab, setDrawerActiveTab] = useState<'detail' | 'worlds' | 'portraits' | 'logs'>('detail')
  const surfaceCardStyle: React.CSSProperties = {
    background: THEME.bgCard,
    border: `1px solid ${THEME.borderLight}`,
  }
  const accentTagStyle: React.CSSProperties = {
    background: THEME.primaryAlpha(0.1),
    border: `1px solid ${THEME.primaryAlpha(0.3)}`,
    color: THEME.primary,
  }

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

  const loadPortraitVersions = useCallback(async (characterId: string) => {
    setPortraitVersionsLoading(true)
    try {
      const res = await listCharacterPortraitVersions(characterId)
      setPortraitVersions(res?.data?.versions || [])
    } catch {
      setPortraitVersions([])
    } finally {
      setPortraitVersionsLoading(false)
    }
  }, [])

  const loadPortraitSlices = useCallback(async (characterId: string) => {
    setPortraitSlicesLoading(true)
    try {
      const res = await listCharacterPortraitSlices(characterId)
      setPortraitSlices(res?.data?.items || [])
    } catch {
      setPortraitSlices([])
    } finally {
      setPortraitSlicesLoading(false)
    }
  }, [])

  const loadWorldUsages = useCallback(async (characterId: string) => {
    setWorldUsagesLoading(true)
    try {
      const res = await listCharacterWorldUsages(characterId)
      const usages = res?.data || []
      setWorldUsages(usages)
      setSelectedCharacter(prev => prev?.id === characterId ? { ...prev, world_usages: usages } : prev)
    } catch {
      setWorldUsages([])
    } finally {
      setWorldUsagesLoading(false)
    }
  }, [])

  const loadCreativeProjectsForWorldUsage = useCallback(async () => {
    try {
      const res = await listCreativeProjects({ limit: 200 }) as any
      setCreativeProjects(res?.data || [])
    } catch {
      setCreativeProjects([])
    }
  }, [])

  const resetWorldUsageForm = () => {
    setWorldUsageForm({
      story_id: '',
      world_id: '',
      world_name: '',
      usage_role: '',
      local_alias: '',
      local_identity: '',
      local_faction: '',
      local_status: 'active',
      local_costume: '',
      local_prompt_tags: [],
      ooc_notes: '',
      off_model_notes: '',
    })
  }

  const openWorldUsageModal = (usage?: CharacterWorldUsage) => {
    setEditingWorldUsage(usage || null)
    if (usage) {
      setWorldUsageForm({
        story_id: usage.story_id,
        world_id: usage.world_id || '',
        world_name: usage.world_name || '',
        usage_role: usage.usage_role || '',
        local_alias: usage.local_alias || '',
        local_identity: usage.local_identity || '',
        local_faction: usage.local_faction || '',
        local_status: usage.local_status || 'active',
        local_costume: usage.local_costume || '',
        local_prompt_tags: usage.local_prompt_tags || [],
        ooc_notes: usage.ooc_notes || '',
        off_model_notes: usage.off_model_notes || '',
      })
    } else {
      resetWorldUsageForm()
    }
    setWorldUsageModalOpen(true)
    loadCreativeProjectsForWorldUsage()
  }

  const handleSaveWorldUsage = async () => {
    if (!selectedCharacter) return
    if (!editingWorldUsage && !worldUsageForm.story_id) {
      message.warning('请选择要使用此角色的项目/世界')
      return
    }
    setWorldUsageSaving(true)
    try {
      const payload = {
        ...worldUsageForm,
        bible_overrides: {},
        visual_overrides: {},
      }
      const res = editingWorldUsage
        ? await updateCharacterWorldUsage(selectedCharacter.id, editingWorldUsage.id, payload)
        : await linkCharacterToWorld(selectedCharacter.id, payload)
      if (!res?.success) {
        message.error(res?.detail || '保存世界使用失败')
        return
      }
      message.success(editingWorldUsage ? '世界使用已更新' : '已绑定到项目/世界')
      setWorldUsageModalOpen(false)
      setEditingWorldUsage(null)
      await loadWorldUsages(selectedCharacter.id)
    } catch (e: any) {
      message.error(e?.message || '保存世界使用失败')
    } finally {
      setWorldUsageSaving(false)
    }
  }

  const handleDeleteWorldUsage = async (usage: CharacterWorldUsage) => {
    if (!selectedCharacter) return
    try {
      const res = await deleteCharacterWorldUsage(selectedCharacter.id, usage.id)
      if (!res?.success) {
        message.error(res?.detail || '移除失败')
        return
      }
      message.success('已移除世界使用关系')
      loadWorldUsages(selectedCharacter.id)
    } catch (e: any) {
      message.error(e?.message || '移除失败')
    }
  }

  // 打开 Drawer 时加载日志
  useEffect(() => {
    if (drawerOpen && selectedCharacter) {
      setDrawerActiveTab('detail')
      loadPortraitLogs(selectedCharacter.id)
      loadPortraitVersions(selectedCharacter.id)
      loadPortraitSlices(selectedCharacter.id)
      loadWorldUsages(selectedCharacter.id)
    }
  }, [drawerOpen, selectedCharacter?.id, loadPortraitLogs, loadPortraitVersions, loadPortraitSlices, loadWorldUsages])

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

  useEffect(() => {
    listConnectors({ provider_type: 'llm', active_only: true })
      .then((res: any) => {
        const items = res?.connectors || res?.data || []
        setLlmConnectors(items)
        if (!selectedEnrichProvider && items.length) {
          const first = items[0]
          setSelectedEnrichProvider(first.name || '')
          setSelectedEnrichModel(first.default_model || first.model || first.available_models?.[0] || '')
        }
      })
      .catch(() => setLlmConnectors([]))
  }, [selectedEnrichProvider])

  const enrichProviderOptions = useMemo(
    () =>
      llmConnectors.map((item) => ({
        label: `${item.name || item.provider || 'LLM'}${item.default_model ? ` · ${item.default_model}` : ''}`,
        value: item.name,
      })),
    [llmConnectors],
  )

  const enrichModelOptions = useMemo(() => {
    const active = llmConnectors.find((item) => item.name === selectedEnrichProvider)
    const models = active?.available_models?.length
      ? active.available_models
      : active?.default_model
        ? [active.default_model]
        : active?.model
          ? [active.model]
          : []
    const uniqueModels: string[] = Array.from(new Set<string>(models.map((model: any) => String(model || '').trim()).filter(Boolean)))
    return uniqueModels.map((model) => ({
      label: model,
      value: model,
    }))
  }, [llmConnectors, selectedEnrichProvider])

  const portraitSizeOptions = useMemo(() => {
    const activeBackend = portraitBackends.find((item) => item.name === selectedPortraitBackend)
    const backendSizes = (activeBackend?.supported_sizes || []).map(size => String(size || '').trim()).filter(Boolean)
    const fallbackSizes = ['1024x1024', '1024x1536', '1536x1024', '1152x896', '896x1152']
    const uniqueSizes = Array.from(new Set([...backendSizes, ...fallbackSizes]))
    return uniqueSizes.map(size => {
      const [w, h] = size.split(/[x*]/i).map(v => Number(v))
      const ratio = w && h
        ? w === h
          ? '1:1'
          : w > h
            ? '横图'
            : '竖图'
        : ''
      return { label: ratio ? `${size} · ${ratio}` : size, value: size }
    })
  }, [portraitBackends, selectedPortraitBackend])

  useEffect(() => {
    if (!selectedPortraitSize || portraitSizeOptions.some(option => option.value === selectedPortraitSize)) return
    setSelectedPortraitSize(portraitSizeOptions[0]?.value || '1024x1024')
  }, [portraitSizeOptions, selectedPortraitSize])

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
    const savedPrompts = getSavedPortraitPrompts(form)
    const savedMainPrompt = getSavedPortraitPrompt(form, 'main_portrait')
    const initialPrompt = savedMainPrompt?.prompt || buildCharacterPortraitPrompt(form)
    const initialNegativePrompt = savedMainPrompt?.negative_prompt || ''
    setPortraitPromptDraft(initialPrompt)
    setPortraitNegativePromptDraft(initialNegativePrompt)
    setSelectedPortraitPreset('main_portrait')
    setPortraitPromptCache({
      ...Object.fromEntries(
        Object.entries(savedPrompts).map(([preset, item]) => [
          preset,
          {
            prompt: item?.prompt || '',
            negativePrompt: item?.negative_prompt || '',
          },
        ]),
      ),
      main_portrait: {
        prompt: initialPrompt,
        negativePrompt: initialNegativePrompt,
      },
    })
  }, [formModalOpen, editingCharacter?.id])

  const updatePortraitPromptDraft = (prompt: string) => {
    setPortraitPromptDraft(prompt)
    setPortraitPromptCache(prev => ({
      ...prev,
      [selectedPortraitPreset]: {
        prompt,
        negativePrompt: portraitNegativePromptDraft,
      },
    }))
  }

  const updatePortraitNegativePromptDraft = (negativePrompt: string) => {
    setPortraitNegativePromptDraft(negativePrompt)
    setPortraitPromptCache(prev => ({
      ...prev,
      [selectedPortraitPreset]: {
        prompt: portraitPromptDraft,
        negativePrompt,
      },
    }))
  }

  const handleChangePortraitPreset = (preset: PortraitPreset) => {
    const nextCache = {
      ...portraitPromptCache,
      [selectedPortraitPreset]: {
        prompt: portraitPromptDraft,
        negativePrompt: portraitNegativePromptDraft,
      },
    }
    const cached = nextCache[preset]
    setPortraitPromptCache(nextCache)
    setSelectedPortraitPreset(preset)
    setPortraitPromptDraft(cached?.prompt || '')
    setPortraitNegativePromptDraft(cached?.negativePrompt || '')
  }

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
      loadPortraitVersions(selectedCharacter.id)
    } catch (e: any) {
      message.error(e?.message || '升级失败')
    } finally {
      setUpgradingPortrait(false)
    }
  }

  const refreshSelectedCharacter = async (characterId: string) => {
    try {
      const data = await getCharacter(characterId)
      if (data?.data) {
        setSelectedCharacter(data.data)
        setCharacters(cs => cs.map(c => c.id === characterId ? data.data : c))
      }
    } catch {
      // 保持当前页面状态即可
    }
  }

  const handleSetMainPortraitVersion = async (version: PortraitVersionItem) => {
    if (!selectedCharacter || settingMainPortrait) return
    setSettingMainPortrait(version.id)
    try {
      const res = await setCharacterMainPortraitVersion(selectedCharacter.id, version.id)
      if (!res?.success || !res.data?.character) {
        message.error(res?.detail || '设置主立绘失败')
        return
      }
      const updated = {
        ...res.data.character,
        world_usages: selectedCharacter.world_usages || [],
      }
      setSelectedCharacter(updated)
      setCharacters(cs => cs.map(c => c.id === selectedCharacter.id ? updated : c))
      await loadPortraitVersions(selectedCharacter.id)
      message.success(`已设为主立绘/身份基准图 v${version.version_number}`)
    } catch (e: any) {
      message.error(e?.message || '设置主立绘失败')
    } finally {
      setSettingMainPortrait('')
    }
  }

  const handleAddPortraitVersionToReferences = async (version: PortraitVersionItem) => {
    if (!selectedCharacter || !version.image_url) return
    try {
      const identity = selectedCharacter.identity || {}
      const visualProfile = identity.visual_profile && typeof identity.visual_profile === 'object'
        ? identity.visual_profile
        : {}
      const referenceImages = cleanImageUrls([
        ...(
          Array.isArray(visualProfile.reference_image_urls)
            ? visualProfile.reference_image_urls
            : []
        ),
        version.image_url,
      ])
      const res = await updateCharacter(selectedCharacter.id, {
        identity: {
          ...identity,
          visual_profile: {
            ...visualProfile,
            reference_image_urls: referenceImages,
          },
        },
      })
      if (!res?.success || !res.data) {
        message.error(res?.detail || '加入参考图失败')
        return
      }
      const updated = {
        ...res.data,
        world_usages: selectedCharacter.world_usages || [],
      }
      setSelectedCharacter(updated)
      setCharacters(cs => cs.map(c => c.id === selectedCharacter.id ? updated : c))
      message.success(`已加入默认参考图集合（共 ${referenceImages.length} 张）`)
    } catch (e: any) {
      message.error(e?.message || '加入参考图失败')
    }
  }

  const handleSlicePortraitGrid = async (version: PortraitVersionItem) => {
    if (!selectedCharacter || slicingPortraitVersion) return
    const gridType = version.preset === 'pose_grid_3x3' ? 'pose' : 'expression'
    setSlicingPortraitVersion(version.id)
    try {
      const res = await sliceCharacterPortraitGrid(selectedCharacter.id, version.id, {
        grid_type: gridType,
        rows: 3,
        cols: 3,
      })
      if (!res?.success || !res.data) {
        message.error(res?.detail || '九宫格切片失败')
        return
      }
      const count = res.data.items?.length || 0
      message.success(res.data.reused ? `已复用 ${count} 张九宫格子素材` : `已切出 ${count} 张九宫格子素材`)
      await Promise.all([
        loadPortraitVersions(selectedCharacter.id),
        loadPortraitSlices(selectedCharacter.id),
        loadPortraitLogs(selectedCharacter.id),
      ])
    } catch (e: any) {
      message.error(e?.message || '九宫格切片失败')
    } finally {
      setSlicingPortraitVersion('')
    }
  }

  const handleEnrichCharacter = async (mode: 'fill_missing' | 'rewrite' = 'fill_missing') => {
    if (!selectedCharacter || enrichingCharacter) return
    setEnrichingCharacter(true)
    try {
      const contextParts = [
        buildCharacterEnrichmentContext(selectedCharacter),
        selectedCharacter.world_usages?.length
          ? `该角色已用于 ${selectedCharacter.world_usages.length} 个世界，请保持角色本体可复用，不要写死单一项目身份。`
          : '',
        selectedCharacter.appearance ? `已有外观：${selectedCharacter.appearance}` : '',
        selectedCharacter.background ? `已有背景：${selectedCharacter.background}` : '',
      ].filter(Boolean)
      const res = await enrichCharacter(selectedCharacter.id, {
        mode,
        apply: true,
        context: contextParts.join('\n'),
        provider: selectedEnrichProvider || undefined,
        model: selectedEnrichModel || undefined,
      })
      if (!res?.success) {
        message.error(res?.detail || 'AI 补全失败')
        return
      }
      if (!res.data?.character) {
        message.info('AI 没有找到需要补全的字段')
        return
      }
      const updated = {
        ...res.data.character,
        world_usages: selectedCharacter.world_usages || [],
      }
      setSelectedCharacter(updated)
      setCharacters(cs => cs.map(c => c.id === selectedCharacter.id ? updated : c))
      message.success(
        res.data.applied_fields.length
          ? `已补全 ${res.data.applied_fields.length} 类角色信息`
          : '角色信息已检查',
      )
    } catch (e: any) {
      message.error(e?.message || 'AI 补全失败')
    } finally {
      if (selectedCharacter?.id) {
        await loadPortraitLogs(selectedCharacter.id)
      }
      setEnrichingCharacter(false)
    }
  }

  // AI 生成立绘：编辑模式走资产中枢端点（保留版本历史），新建模式走旧 /images/generate
  //
  // 快速生成路径（task 4.5）：
  //   - 新建：buildCharacterPortraitPrompt(form) 从 appearance/costume_hint 直接构建 prompt
  //   - 编辑：buildVisualProfileOverride(form) 桥接表单字段 → visual_profile → 后端 build_portrait_prompt
  //   两者均无需用户填写完整 visual card，保留轻量一键生图行为。
  const handleRefreshPortraitPrompt = async () => {
    if (editingCharacter?.id) {
      setPreviewingPortraitPrompt(true)
      try {
        const data = await previewCharacterPortraitPrompt(editingCharacter.id, {
          preset: selectedPortraitPreset,
          visual_profile: buildVisualProfileOverride(form),
          language: 'zh',
        })
        if (!data?.success || !data.data) {
          message.error(data?.detail || '生成提示词失败')
          return
        }
        updatePortraitPromptDraft(data.data.prompt)
        updatePortraitNegativePromptDraft(data.data.negative_prompt || '')
        message.success('已根据预设生成完整提示词')
      } catch (e: any) {
        message.error(e?.message || '生成提示词失败')
      } finally {
        setPreviewingPortraitPrompt(false)
      }
      return
    }
    const prompt = buildCharacterPortraitPrompt(form)
    updatePortraitPromptDraft(prompt)
    updatePortraitNegativePromptDraft('')
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
              `你是资深角色设定师和 AI 生图提示词工程师。只输出一段可直接用于生图的完整提示词，不要 Markdown，不要解释。你必须优先保证角色一致性：同一张脸、同一发型、同一眼型和瞳色、同一服装结构、同一身体比例。${PORTRAIT_PROMPT_LANGUAGE_RULE}`,
          },
          {
            role: 'user',
            content:
              `请把下面的角色立绘提示词优化成更稳定、更完整的生图提示词。\n` +
              `要求：保留角色身份和外观，不添加矛盾设定；强调单人立绘、角色卡、清晰五官、服装细节、简洁背景、后续漫画一致性参考；包含必要负面约束；${PORTRAIT_PROMPT_LANGUAGE_RULE} 输出不要出现英文整句，不要以 "3x3 grid layout"、"Panel 1" 这类英文段落开头。若输入是九宫格/分格提示词，必须完整输出第 1 到第 9 格，不能只写前几格；动作九宫格只安排简单站姿或轻微身体动作，不要坐下、奔跑、跳跃、打斗或复杂道具；明确提醒使用已确认主立绘/身份板作为参考图，九宫格用于切素材而不是第一次锁脸。\n\n` +
              basePrompt,
          },
        ],
        provider: selectedEnrichProvider || undefined,
        model: selectedEnrichModel || undefined,
        temperature: 0.35,
        log_scene: 'character_portrait',
        log_ref_id: editingCharacter?.id || undefined,
        log_stage: 'portrait_prompt_optimize',
        log_request: {
          character_id: editingCharacter?.id || '',
          character_name: form.name || editingCharacter?.name || '',
          source: 'character_edit_modal',
        },
      })
      const optimized = cleanPromptResponse(res?.content || '')
      if (!res?.success || !optimized) {
        message.error(res?.error || 'AI 优化提示词失败')
        return
      }
      updatePortraitPromptDraft(optimized)
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
    const prompt = portraitPromptDraft.trim() || (editingCharacter ? '' : buildCharacterPortraitPrompt(form))
    if (!portraitPromptDraft.trim() && !editingCharacter) {
      updatePortraitPromptDraft(prompt)
    }
    let formForGenerate = mergePortraitPromptDrafts(
      form,
      selectedPortraitPreset,
      prompt,
      portraitNegativePromptDraft,
      portraitPromptCache,
    )
    const generationReferenceImages = getGenerationReferenceImages(formForGenerate, selectedPortraitPreset)
    if (generationReferenceImages.length) {
      formForGenerate = mergeReferenceImagesIntoForm(formForGenerate, generationReferenceImages)
    }
    if (JSON.stringify(formForGenerate.identity || {}) !== JSON.stringify(form.identity || {})) {
      setForm(formForGenerate)
    }

    setGeneratingPortrait(true)
    try {
      if (editingCharacter) {
        if (JSON.stringify(formForGenerate.identity || {}) !== JSON.stringify(editingCharacter.identity || {})) {
          const saveRes = await updateCharacter(editingCharacter.id, { identity: formForGenerate.identity || {} })
          if (!saveRes?.success) {
            message.warning(saveRes?.detail || '提示词/参考图暂未保存，但会继续用于本次生成')
          }
        }
        // 编辑已有角色 → 走资产中枢端点（自动创建/复用 AssetNode + 新 Version）
        const data = await generateCharacterPortraitViaAssetHub(
          editingCharacter.id,
          {
            prompt,
            provider: selectedPortraitBackend,
            size: selectedPortraitSize || '1024x1024',
            n: 1,
            preset: selectedPortraitPreset,
            negative_prompt: portraitNegativePromptDraft,
            reference_images: generationReferenceImages,
            visual_profile: buildVisualProfileOverride(formForGenerate),
            set_as_main: true,
          }
        )
        if (!data?.success || !data.data) {
          message.error(data?.detail || '生成立绘失败')
          return
        }
        const info = data.data
        const updatedCharacter = info.character
        setForm(f => ({
          ...f,
          identity: updatedCharacter.identity || formForGenerate.identity || {},
          portrait_url: updatedCharacter.portrait_url || info.url,
          portrait_asset_id: updatedCharacter.portrait_asset_id || '',
        }))
        setEditingCharacter(updatedCharacter)
        setSelectedCharacter(prev => prev?.id === updatedCharacter.id ? { ...updatedCharacter, world_usages: prev.world_usages || [] } : prev)
        setCharacters(cs => cs.map(c => c.id === updatedCharacter.id ? updatedCharacter : c))
        message.success(`立绘已生成并入资产中枢（v${info.version_number}）`)
        // 刷新日志 Tab
        if (editingCharacter?.id) {
          loadPortraitLogs(editingCharacter.id)
          loadPortraitVersions(editingCharacter.id)
          refreshSelectedCharacter(editingCharacter.id)
        }
      } else {
        // 新建模式 → 走旧 /images/generate（保存后可在 Drawer 中点"升级到资产中枢"补登记）
        const data = await generateCharacterPortraitImage({
          prompt,
          provider: selectedPortraitBackend,
          size: selectedPortraitSize || '1024x1024',
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
      let formToSave = mergePortraitPromptDrafts(
        form,
        selectedPortraitPreset,
        portraitPromptDraft,
        portraitNegativePromptDraft,
        portraitPromptCache,
      )
      const generationReferenceImages = getGenerationReferenceImages(formToSave, selectedPortraitPreset)
      if (generationReferenceImages.length) {
        formToSave = mergeReferenceImagesIntoForm(formToSave, generationReferenceImages)
      }
      if (editingCharacter) {
        const req: CharacterUpdateRequest = {}
        if (formToSave.name !== editingCharacter.name) req.name = formToSave.name
        if (formToSave.role !== editingCharacter.role) req.role = formToSave.role
        if (JSON.stringify(formToSave.source_types) !== JSON.stringify(editingCharacter.source_types)) req.source_types = formToSave.source_types
        if (formToSave.appearance !== editingCharacter.appearance) req.appearance = formToSave.appearance
        if (formToSave.personality !== editingCharacter.personality) req.personality = formToSave.personality
        if (formToSave.costume_hint !== editingCharacter.costume_hint) req.costume_hint = formToSave.costume_hint
        if (JSON.stringify(formToSave.signature_items || []) !== JSON.stringify(editingCharacter.signature_items || [])) req.signature_items = formToSave.signature_items || []
        if (JSON.stringify(formToSave.expressions || []) !== JSON.stringify(editingCharacter.expressions || [])) req.expressions = formToSave.expressions || []
        if (JSON.stringify(formToSave.poses || []) !== JSON.stringify(editingCharacter.poses || [])) req.poses = formToSave.poses || []
        if ((formToSave.visual_consistency || '') !== (editingCharacter.visual_consistency || '')) req.visual_consistency = formToSave.visual_consistency || ''
        if (formToSave.background !== editingCharacter.background) req.background = formToSave.background
        if (formToSave.age_range !== editingCharacter.age_range) req.age_range = formToSave.age_range
        if (JSON.stringify(formToSave.identity || {}) !== JSON.stringify(editingCharacter.identity || {})) req.identity = formToSave.identity || {}
        if (JSON.stringify(formToSave.motivation || {}) !== JSON.stringify(editingCharacter.motivation || {})) req.motivation = formToSave.motivation || {}
        if (JSON.stringify(formToSave.speech || {}) !== JSON.stringify(editingCharacter.speech || {})) req.speech = formToSave.speech || {}
        if (JSON.stringify(formToSave.behavior || {}) !== JSON.stringify(editingCharacter.behavior || {})) req.behavior = formToSave.behavior || {}
        if (JSON.stringify(formToSave.ability || {}) !== JSON.stringify(editingCharacter.ability || {})) req.ability = formToSave.ability || {}
        if (JSON.stringify(formToSave.arc || {}) !== JSON.stringify(editingCharacter.arc || {})) req.arc = formToSave.arc || {}
        if (JSON.stringify(formToSave.tags) !== JSON.stringify(editingCharacter.tags)) req.tags = formToSave.tags
        if (formToSave.portrait_url !== editingCharacter.portrait_url) req.portrait_url = formToSave.portrait_url
        if ((formToSave.portrait_asset_id || '') !== (editingCharacter.portrait_asset_id || '')) req.portrait_asset_id = formToSave.portrait_asset_id || ''
        await updateCharacter(editingCharacter.id, req)
        message.success('角色已更新')
      } else {
        await createCharacter(formToSave)
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

  const setBibleField = (
    section: 'identity' | 'motivation' | 'speech' | 'behavior' | 'ability' | 'arc',
    key: string,
    value: any,
  ) => {
    setForm(f => ({
      ...f,
      [section]: {
        ...((f as any)[section] || {}),
        [key]: value,
      },
    }))
  }

  const setVisualProfileField = (key: string, value: any) => {
    setForm(f => ({
      ...f,
      identity: {
        ...(f.identity || {}),
        visual_profile: {
          ...((f.identity || {}).visual_profile || {}),
          [key]: value,
        },
      },
    }))
  }

  const visualProfile = form.identity?.visual_profile || {}
  const selectedPortraitHelp = PORTRAIT_PRESET_HELP[selectedPortraitPreset]
  const identityReferenceImage = getIdentityReferenceImage(form)
  const currentGenerationReferenceImages = getGenerationReferenceImages(form, selectedPortraitPreset)
  const portraitPreviewDuplicatedByBaseline =
    Boolean(form.portrait_url) && Boolean(identityReferenceImage) && form.portrait_url === identityReferenceImage
  const willAutoAttachMainPortrait =
    shouldAutoAttachMainPortrait(selectedPortraitPreset) &&
    Boolean(identityReferenceImage) &&
    !getVisualProfileReferenceImages(form).includes(identityReferenceImage)

  const appendReferenceImages = useCallback((urls: string[], successText?: string) => {
    const cleaned = urls.map(url => String(url || '').trim()).filter(Boolean)
    if (!cleaned.length) {
      message.warning('没有可用的参考图地址')
      return
    }
    const existing = (form.identity?.visual_profile?.reference_image_urls || []).map((url: string) => String(url || '').trim()).filter(Boolean)
    const merged = Array.from(new Set([...existing, ...cleaned]))
    setVisualProfileField('reference_image_urls', merged)
    const added = merged.length - existing.length
    message.success(successText || (added > 0 ? `已加入 ${added} 张参考图` : '参考图已存在'))
  }, [form.identity])

  const loadReferenceAssets = useCallback(async () => {
    setReferenceAssetsLoading(true)
    try {
      const res = await listAssets({
        asset_type: 'image',
        search: referenceAssetSearch.trim() || undefined,
        page: 1,
        page_size: 36,
      }) as any
      setReferenceAssets(res?.data || [])
    } catch (e: any) {
      setReferenceAssets([])
      message.error(e?.message || '加载素材库图片失败')
    } finally {
      setReferenceAssetsLoading(false)
    }
  }, [referenceAssetSearch])

  useEffect(() => {
    if (!referencePickerOpen) return
    const timer = window.setTimeout(() => {
      loadReferenceAssets()
    }, 250)
    return () => window.clearTimeout(timer)
  }, [referencePickerOpen, loadReferenceAssets])

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ color: THEME.textPrimary, marginBottom: 4 }}>
            <TeamOutlined style={{ color: THEME.primary, marginRight: 8 }} />
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
          onClick={() => { setEditingCharacter(null); setForm(emptyCharacterForm()); setFormModalOpen(true) }}
          style={{ height: 44 }}
        >
          新建角色
        </Button>
      </div>

      <Card style={{ ...surfaceCardStyle, marginBottom: 20 }}
        styles={{ body: { padding: '16px 20px' } }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 13, marginRight: 4 }}>来源：</Text>
          <Tag style={{ cursor: 'pointer', background: !filterSourceType ? THEME.primaryAlpha(0.15) : 'transparent', border: !filterSourceType ? `1px solid ${THEME.primaryAlpha(0.5)}` : `1px solid ${THEME.borderLight}`, color: !filterSourceType ? THEME.primary : THEME.textSecondary }} onClick={() => setFilterSourceType(null)}>全部</Tag>
          {CHARACTER_SOURCE_TYPE_OPTIONS.map(opt => {
            const active = filterSourceType === opt.value
            return (
              <Tag key={opt.value} style={{ cursor: 'pointer', background: active ? `${SOURCE_TYPE_COLORS[opt.value]}20` : 'transparent', border: active ? `1px solid ${SOURCE_TYPE_COLORS[opt.value]}` : `1px solid ${THEME.borderLight}`, color: active ? SOURCE_TYPE_COLORS[opt.value] : THEME.textSecondary }} onClick={() => setFilterSourceType(active ? null : opt.value)}>
                {SOURCE_TYPE_ICONS[opt.value]} {opt.label}
              </Tag>
            )
          })}
          <Divider type="vertical" style={{ borderColor: THEME.borderLight, height: 20, margin: '0 8px' }} />
          <Text type="secondary" style={{ fontSize: 13, marginRight: 4 }}>定位：</Text>
          <Select size="small" placeholder="全部定位" allowClear value={filterRole} onChange={v => setFilterRole(v)} style={{ width: 100 }}
            options={CHARACTER_ROLE_OPTIONS}
          />
          <Divider type="vertical" style={{ borderColor: THEME.borderLight, height: 20, margin: '0 8px' }} />
          <Tag style={{ cursor: 'pointer', background: filterFavorite ? 'rgba(245,158,11,0.15)' : 'transparent', border: filterFavorite ? '1px solid rgba(245,158,11,0.5)' : `1px solid ${THEME.borderLight}`, color: filterFavorite ? '#f59e0b' : THEME.textSecondary }}
            onClick={() => setFilterFavorite(f => !f)} icon={filterFavorite ? <StarFilled /> : <StarOutlined />}>
            仅收藏
          </Tag>
        </div>
        <Input placeholder="搜索角色名称..." prefix={<SearchOutlined style={{ color: THEME.textSecondary }} />} value={keyword}
          onChange={e => setKeyword(e.target.value)} allowClear style={{ background: THEME.bgInput, maxWidth: 360 }} />
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
                style={{ ...surfaceCardStyle, borderRadius: 12, overflow: 'hidden', position: 'relative' }}
                styles={{ body: { padding: 0 } }}
              >
                <div style={{ height: 160, background: `linear-gradient(135deg, ${SOURCE_TYPE_COLORS[character.source_types[0]] || '#1890ff'}20, ${THEME.bgElevated})`, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                  {character.portrait_url ? (
                    <img src={character.portrait_url} alt={character.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  ) : (
                    <Avatar size={80} icon={<UserOutlined />} style={{ background: `${SOURCE_TYPE_COLORS[character.source_types[0]] || '#1890ff'}40` }} />
                  )}
                  <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 4 }}>
                    {character.is_frozen && <Tag style={{ background: 'rgba(245,158,11,0.15)', border: `1px solid rgba(245,158,11,0.3)`, color: '#f59e0b' }}><LockOutlined /> 冻结</Tag>}
                    <Button type="text" size="small" icon={character.is_favorite ? <StarFilled style={{ color: '#f59e0b' }} /> : <StarOutlined style={{ color: THEME.textSecondary }} />}
                      onClick={e => { e.stopPropagation(); handleFavorite(character) }} style={{ background: THEME.bgHover, color: THEME.textPrimary }} />
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
                    <Text strong style={{ color: THEME.textPrimary, fontSize: 15 }} ellipsis>{character.name}</Text>
                    <Tag style={{ background: `${ROLE_COLORS[character.role]}20`, border: `1px solid ${ROLE_COLORS[character.role]}50`, color: ROLE_COLORS[character.role], fontSize: 11, padding: '0 4px', lineHeight: '16px' }}>
                      {CHARACTER_ROLE_OPTIONS.find(o => o.value === character.role)?.label}
                    </Tag>
                  </div>
                  {character.appearance && <Text style={{ color: THEME.textSecondary, fontSize: 12 }} ellipsis>{character.appearance}</Text>}
                  {(character.signature_items || []).length > 0 && (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                      {character.signature_items.slice(0, 3).map(item => (
                        <Tag key={item} color="cyan" style={{ fontSize: 11 }}>{item}</Tag>
                      ))}
                    </div>
                  )}
                  {character.tags.length > 0 && (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                      {character.tags.slice(0, 3).map(tag => (
                        <Tag key={tag} style={{ fontSize: 11, background: THEME.bgElevated, border: 'none', color: THEME.textSecondary }}>{tag}</Tag>
                      ))}
                      {character.tags.length > 3 && <Tag style={{ fontSize: 11, background: 'transparent', border: 'none', color: THEME.textSecondary }}>+{character.tags.length - 3}</Tag>}
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
          <Text style={{ color: THEME.textSecondary, margin: '0 16px' }}>第 {page} / {Math.ceil(total / PAGE_SIZE)} 页，共 {total} 条</Text>
          <Button disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => { const p = page + 1; setPage(p); load(p, { keyword, source_type: filterSourceType, role: filterRole, is_favorite: filterFavorite || undefined }) }}>下一页</Button>
        </div>
      )}

      {/* Detail Drawer */}
      <Drawer open={drawerOpen} onClose={() => { setDrawerOpen(false); setSelectedCharacter(null) }}
        title={<Space><UserOutlined style={{ color: THEME.primary }} /><span style={{ color: THEME.textPrimary }}>{selectedCharacter?.name}</span>
          {selectedCharacter && <Tag style={{ background: `${ROLE_COLORS[selectedCharacter.role]}20`, border: `1px solid ${ROLE_COLORS[selectedCharacter.role]}50`, color: ROLE_COLORS[selectedCharacter.role] }}>{CHARACTER_ROLE_OPTIONS.find(o => o.value === selectedCharacter.role)?.label}</Tag>}
          {selectedCharacter?.is_frozen && <Tag icon={<LockOutlined />} style={{ color: '#f59e0b', background: 'rgba(245,158,11,0.1)' }}>已冻结</Tag>}
        </Space>}
        width={860} styles={{ body: { background: THEME.bgPage, padding: 0 }, header: { background: THEME.bgCard, borderBottom: `1px solid ${THEME.borderLight}` } }}>
        {selectedCharacter && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <CharacterIdentityBoard character={selectedCharacter} theme={THEME} />
            <div style={{ padding: 20, flex: 1, overflow: 'auto' }}>
              <Tabs
                activeKey={drawerActiveTab}
                onChange={(k) => setDrawerActiveTab(k as 'detail' | 'worlds' | 'portraits' | 'logs')}
                items={[
                  {
                    key: 'detail',
                    label: '详情',
                    children: (
                      <>
              <CharacterEnrichmentStrip
                character={selectedCharacter}
                loading={enrichingCharacter}
                providerOptions={enrichProviderOptions}
                selectedProvider={selectedEnrichProvider}
                selectedModel={selectedEnrichModel}
                modelOptions={enrichModelOptions}
                onProviderChange={(value) => {
                  setSelectedEnrichProvider(value)
                  const connector = llmConnectors.find((item) => item.name === value)
                  setSelectedEnrichModel(connector?.default_model || connector?.model || connector?.available_models?.[0] || '')
                }}
                onModelChange={setSelectedEnrichModel}
                onFillMissing={() => handleEnrichCharacter('fill_missing')}
                onRewrite={() => handleEnrichCharacter('rewrite')}
              />
              <CharacterReferenceStatus character={selectedCharacter} theme={THEME} />
              <CharacterBibleQuickPanels character={selectedCharacter} theme={THEME} />
              <CharacterBibleDetailedPanels character={selectedCharacter} theme={THEME} />
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
                <Panel header={<Text style={{ color: THEME.primary }}>外观描述</Text>} key="appearance">
                  {selectedCharacter.appearance ? <Paragraph style={{ color: THEME.textPrimary, whiteSpace: 'pre-wrap' }}>{selectedCharacter.appearance}</Paragraph> : <Text type="secondary">暂无</Text>}
                  {selectedCharacter.costume_hint && <><Text type="secondary" style={{ fontSize: 12 }}>服装提示</Text><Paragraph style={{ color: THEME.textPrimary, whiteSpace: 'pre-wrap' }}>{selectedCharacter.costume_hint}</Paragraph></>}
                </Panel>
                <Panel header={<Text style={{ color: THEME.primary }}>视觉一致性</Text>} key="visual">
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>标志物</Text>
                      <div style={{ marginTop: 4 }}>
                        {(selectedCharacter.signature_items || []).length ? selectedCharacter.signature_items.map(item => <Tag key={item}>{item}</Tag>) : <Text type="secondary">暂无</Text>}
                      </div>
                    </div>
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>常用表情</Text>
                      <div style={{ marginTop: 4 }}>
                        {(selectedCharacter.expressions || []).length ? selectedCharacter.expressions.map(item => <Tag key={item}>{item}</Tag>) : <Text type="secondary">暂无</Text>}
                      </div>
                    </div>
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>常用姿态</Text>
                      <div style={{ marginTop: 4 }}>
                        {(selectedCharacter.poses || []).length ? selectedCharacter.poses.map(item => <Tag key={item}>{item}</Tag>) : <Text type="secondary">暂无</Text>}
                      </div>
                    </div>
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>一致性规则</Text>
                      {selectedCharacter.visual_consistency ? <Paragraph style={{ color: THEME.textPrimary, whiteSpace: 'pre-wrap', marginTop: 4 }}>{selectedCharacter.visual_consistency}</Paragraph> : <Text type="secondary">暂无</Text>}
                    </div>
                  </Space>
                </Panel>
                <Panel header={<Text style={{ color: THEME.primary }}>性格特点</Text>} key="personality">
                  {selectedCharacter.personality ? <Paragraph style={{ color: THEME.textPrimary, whiteSpace: 'pre-wrap' }}>{selectedCharacter.personality}</Paragraph> : <Text type="secondary">暂无</Text>}
                </Panel>
                <Panel header={<Text style={{ color: THEME.primary }}>背景故事</Text>} key="background">
                  {selectedCharacter.background ? <Paragraph style={{ color: THEME.textPrimary, whiteSpace: 'pre-wrap' }}>{selectedCharacter.background}</Paragraph> : <Text type="secondary">暂无</Text>}
                </Panel>
              </Collapse>
              <div style={{ marginBottom: 16 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>自定义标签</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6, marginBottom: 8 }}>
                  {selectedCharacter.tags.map(tag => (
                    <Tag key={tag} closable onClose={() => handleRemoveTag(tag)} style={accentTagStyle}>{tag}</Tag>
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
              <Divider style={{ borderColor: THEME.borderLight }} />
              <Space wrap>
                <Button icon={<EditOutlined />} onClick={() => { setEditingCharacter(selectedCharacter); setForm({ name: selectedCharacter.name, role: selectedCharacter.role, source_types: selectedCharacter.source_types, appearance: selectedCharacter.appearance, personality: selectedCharacter.personality, costume_hint: selectedCharacter.costume_hint, signature_items: selectedCharacter.signature_items || [], expressions: selectedCharacter.expressions || [], poses: selectedCharacter.poses || [], visual_consistency: selectedCharacter.visual_consistency || '', background: selectedCharacter.background, age_range: selectedCharacter.age_range, identity: selectedCharacter.identity || {}, motivation: selectedCharacter.motivation || {}, speech: selectedCharacter.speech || {}, behavior: selectedCharacter.behavior || {}, ability: selectedCharacter.ability || {}, arc: selectedCharacter.arc || {}, tags: selectedCharacter.tags, portrait_url: selectedCharacter.portrait_url, portrait_asset_id: selectedCharacter.portrait_asset_id || '' }); setDrawerOpen(false); setFormModalOpen(true) }}>编辑</Button>
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
                    key: 'worlds',
                    label: (
                      <Space>
                        <TeamOutlined />
                        世界使用
                        {worldUsages.length > 0 && (
                          <Tag color="purple" style={{ marginInlineStart: 0 }}>{worldUsages.length}</Tag>
                        )}
                      </Space>
                    ),
                    children: (
                      <CharacterWorldUsagesTab
                        usages={worldUsages}
                        loading={worldUsagesLoading}
                        onAdd={() => openWorldUsageModal()}
                        onEdit={openWorldUsageModal}
                        onDelete={handleDeleteWorldUsage}
                        onRefresh={() => selectedCharacter && loadWorldUsages(selectedCharacter.id)}
                      />
                    ),
                  },
                  {
                    key: 'portraits',
                    label: (
                      <Space>
                        <FileImageOutlined />
                        立绘版本
                        {portraitVersions.length > 0 && (
                          <Tag color="green" style={{ marginInlineStart: 0 }}>{portraitVersions.length}</Tag>
                        )}
                      </Space>
                    ),
                    children: (
                      <CharacterPortraitVersionsTab
                        versions={portraitVersions}
                        slices={portraitSlices}
                        loading={portraitVersionsLoading}
                        slicesLoading={portraitSlicesLoading}
                        settingMainId={settingMainPortrait}
                        slicingId={slicingPortraitVersion}
                        onSetMain={handleSetMainPortraitVersion}
                        onAddReference={handleAddPortraitVersionToReferences}
                        onSliceGrid={handleSlicePortraitGrid}
                        onRefresh={() => {
                          if (!selectedCharacter) return
                          loadPortraitVersions(selectedCharacter.id)
                          loadPortraitSlices(selectedCharacter.id)
                        }}
                      />
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

      <Modal
        open={worldUsageModalOpen}
        title={editingWorldUsage ? '编辑世界使用' : '绑定到项目/世界'}
        onCancel={() => { setWorldUsageModalOpen(false); setEditingWorldUsage(null) }}
        footer={
          <Space>
            <Button onClick={() => { setWorldUsageModalOpen(false); setEditingWorldUsage(null) }}>取消</Button>
            <Button type="primary" loading={worldUsageSaving} onClick={handleSaveWorldUsage}>
              {editingWorldUsage ? '保存' : '绑定'}
            </Button>
          </Space>
        }
        width={720}
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Text strong>项目/世界</Text>
            <Select
              showSearch
              disabled={Boolean(editingWorldUsage)}
              placeholder="选择创作项目"
              value={worldUsageForm.story_id || undefined}
              onChange={(projectId) => {
                const project = creativeProjects.find(item => item.id === projectId)
                setWorldUsageForm(f => ({
                  ...f,
                  story_id: projectId,
                  world_name: f.world_name || project?.settings?.world_name || project?.metadata?.world_name || project?.title || '',
                }))
              }}
              options={creativeProjects.map(project => ({
                value: project.id,
                label: `${project.title}${project.project_type ? ` · ${project.project_type}` : ''}`,
              }))}
              style={{ width: '100%', marginTop: 8 }}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Input placeholder="世界名/宇宙名" value={worldUsageForm.world_name} onChange={e => setWorldUsageForm(f => ({ ...f, world_name: e.target.value }))} />
            <Input placeholder="该世界中的角色职责：主角/NPC/反派" value={worldUsageForm.usage_role} onChange={e => setWorldUsageForm(f => ({ ...f, usage_role: e.target.value }))} />
            <Input placeholder="本世界别名/代号" value={worldUsageForm.local_alias} onChange={e => setWorldUsageForm(f => ({ ...f, local_alias: e.target.value }))} />
            <Input placeholder="阵营/组织/派系" value={worldUsageForm.local_faction} onChange={e => setWorldUsageForm(f => ({ ...f, local_faction: e.target.value }))} />
          </div>
          <TextArea rows={2} placeholder="该世界中的身份说明" value={worldUsageForm.local_identity} onChange={e => setWorldUsageForm(f => ({ ...f, local_identity: e.target.value }))} />
          <TextArea rows={2} placeholder="该世界服装/形态覆盖" value={worldUsageForm.local_costume} onChange={e => setWorldUsageForm(f => ({ ...f, local_costume: e.target.value }))} />
          <Select
            {...compactTagSelectProps}
            mode="tags"
            placeholder="局部 Prompt 标签：赛博世界 / 校服 / 受伤状态"
            value={worldUsageForm.local_prompt_tags}
            onChange={value => setWorldUsageForm(f => ({ ...f, local_prompt_tags: value }))}
          />
          <TextArea rows={3} placeholder="OOC 约束：这个世界里绝对不会做什么、说什么、如何避免人设跑偏" value={worldUsageForm.ooc_notes} onChange={e => setWorldUsageForm(f => ({ ...f, ooc_notes: e.target.value }))} />
          <TextArea rows={3} placeholder="Off-Model 约束：这个世界里哪些外观、服装、比例、道具不能画错" value={worldUsageForm.off_model_notes} onChange={e => setWorldUsageForm(f => ({ ...f, off_model_notes: e.target.value }))} />
        </Space>
      </Modal>

      {/* Create/Edit Modal */}
      <Modal open={formModalOpen} title={editingCharacter ? '编辑角色' : '新建角色'} onCancel={() => { setFormModalOpen(false); setEditingCharacter(null) }}
        footer={<Space><Button onClick={() => { setFormModalOpen(false); setEditingCharacter(null) }}>取消</Button><Button type="primary" loading={saving} onClick={handleSave}>{editingCharacter ? '保存修改' : '创建角色'}</Button></Space>}
        width={CHARACTER_FORM_MODAL_WIDTH}
        style={{ maxWidth: 'calc(100vw - 32px)' }}
        styles={{ body: { maxHeight: 'min(76vh, 760px)', overflowY: 'auto', paddingRight: 16 } }}
        destroyOnClose>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <Text strong style={{ color: THEME.textPrimary }}>基本信息</Text>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 8 }}>
              <Input placeholder="角色名称 *" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} maxLength={50} />
              <Select value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))}
                options={CHARACTER_ROLE_OPTIONS.map(o => ({ ...o, label: <Space><span style={{ width: 8, height: 8, borderRadius: '50%', background: ROLE_COLORS[o.value] || '#8b8ba8', display: 'inline-block' }} />{o.label}</Space> }))} />
            </div>
            <Input placeholder="年龄范围，如 20-25岁" value={form.age_range} onChange={e => setForm(f => ({ ...f, age_range: e.target.value }))} style={{ marginTop: 8 }} />
          </div>
          <div>
            <Text strong style={{ color: THEME.textPrimary }}>来源类型 *（可多选）</Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {CHARACTER_SOURCE_TYPE_OPTIONS.map(opt => {
                const selected = form.source_types?.includes(opt.value)
                return (
                  <Tag key={opt.value} style={{ cursor: 'pointer', border: selected ? `1px solid ${SOURCE_TYPE_COLORS[opt.value]}` : `1px solid ${THEME.borderLight}`, color: selected ? SOURCE_TYPE_COLORS[opt.value] : THEME.textSecondary, background: selected ? `${SOURCE_TYPE_COLORS[opt.value]}15` : 'transparent', padding: '4px 10px', fontSize: 13 }}
                    onClick={() => setForm(f => ({ ...f, source_types: selected ? f.source_types.filter(t => t !== opt.value) : [...(f.source_types || []), opt.value] }))}>
                    {SOURCE_TYPE_ICONS[opt.value]} {opt.label}
                  </Tag>
                )
              })}
            </div>
          </div>
          <div>
            <Text strong style={{ color: THEME.primary }}>外观描述（用于 AI 生图提示词）</Text>
            <TextArea placeholder="外貌特征，如：黑长直、瓜子脸、肤白貌美..." value={form.appearance} onChange={e => setForm(f => ({ ...f, appearance: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
            <TextArea placeholder="服装提示，如：白色衬衫+黑色短裙、古典汉服..." value={form.costume_hint} onChange={e => setForm(f => ({ ...f, costume_hint: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 8, marginTop: 8 }}>
              <Select {...compactTagSelectProps} mode="tags" placeholder="标志物：眼镜 / 银色钢笔 / 蝴蝶纹身" value={form.signature_items || []} onChange={value => setForm(f => ({ ...f, signature_items: value }))} />
              <Select {...compactTagSelectProps} mode="tags" placeholder="常用表情：冷静 / 讥讽 / 震惊" value={form.expressions || []} onChange={value => setForm(f => ({ ...f, expressions: value }))} />
              <Select {...compactTagSelectProps} mode="tags" placeholder="常用姿态：扶眼镜 / 抱臂 / 回头" value={form.poses || []} onChange={value => setForm(f => ({ ...f, poses: value }))} />
              <Input placeholder="一致性短规则：发型服装配色不要变" value={form.visual_consistency} onChange={e => setForm(f => ({ ...f, visual_consistency: e.target.value }))} />
            </div>
            <Collapse
              size="small"
              style={{ marginTop: 10, background: THEME.bgCard, border: `1px solid ${THEME.borderLight}` }}
              items={[
                {
                  key: 'visual-profile',
                  label: '视觉卡细项（用于稳定立绘、九宫格和分镜生图）',
                  children: (
                    <Space direction="vertical" size={10} style={{ width: '100%' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <Input placeholder="脸部识别点：脸型 / 痣 / 伤疤 / 眉眼特征" value={visualProfile.face || ''} onChange={e => setVisualProfileField('face', e.target.value)} />
                        <Input placeholder="发型发色：黑色短发 / 银白长发 / 刘海" value={visualProfile.hair || ''} onChange={e => setVisualProfileField('hair', e.target.value)} />
                        <Input placeholder="眼睛：瞳色 / 眼型 / 眼神" value={visualProfile.eyes || ''} onChange={e => setVisualProfileField('eyes', e.target.value)} />
                        <Input placeholder="肤色/皮肤特征" value={visualProfile.skin || ''} onChange={e => setVisualProfileField('skin', e.target.value)} />
                        <Input placeholder="体型：瘦削 / 高挑 / 健壮 / 娇小" value={visualProfile.body_shape || ''} onChange={e => setVisualProfileField('body_shape', e.target.value)} />
                        <Input placeholder="身体比例：九头身 / 少年感 / 宽肩窄腰" value={visualProfile.body_proportion || ''} onChange={e => setVisualProfileField('body_proportion', e.target.value)} />
                        <Input placeholder="鞋履：黑色短靴 / 白色运动鞋" value={visualProfile.shoes || ''} onChange={e => setVisualProfileField('shoes', e.target.value)} />
                        <Input placeholder="画风：日漫赛璐璐 / 写实电影感 / 国风厚涂" value={visualProfile.style || ''} onChange={e => setVisualProfileField('style', e.target.value)} />
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 8 }}>
                        <Select {...compactTagSelectProps} mode="tags" placeholder="视觉标签：冷峻 / 甜美 / 机械义体" value={visualProfile.visual_tags || []} onChange={value => setVisualProfileField('visual_tags', value)} />
                        <Select {...compactTagSelectProps} mode="tags" placeholder="服装配色：黑白灰 / 红金 / 蓝银" value={visualProfile.costume_colors || []} onChange={value => setVisualProfileField('costume_colors', value)} />
                        <Select {...compactTagSelectProps} mode="tags" placeholder="材质：皮革 / 金属 / 丝绸 / 校服布料" value={visualProfile.materials || []} onChange={value => setVisualProfileField('materials', value)} />
                        <Select {...compactTagSelectProps} mode="tags" placeholder="配饰：耳坠 / 眼镜 / 颈环 / 手套" value={visualProfile.accessories || []} onChange={value => setVisualProfileField('accessories', value)} />
                      </div>
                      <Select
                        {...compactTagSelectProps}
                        mode="tags"
                        placeholder="负面约束：不要换发型 / 不要新增配饰 / 不要改变瞳色"
                        value={visualProfile.negative_constraints || []}
                        onChange={value => setVisualProfileField('negative_constraints', value)}
                      />
                      <TextArea
                        rows={2}
                        placeholder="视觉一致性补充：哪些细节在所有立绘、分镜、漫画图里都必须保持一致"
                        value={visualProfile.visual_consistency || ''}
                        onChange={e => setVisualProfileField('visual_consistency', e.target.value)}
                      />
                    </Space>
                  ),
                },
              ]}
            />
          </div>
          <div>
            <Text strong style={{ color: THEME.textPrimary }}>其他信息</Text>
            <TextArea placeholder="性格特点，如：温柔善良、傲娇..." value={form.personality} onChange={e => setForm(f => ({ ...f, personality: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
            <TextArea placeholder="背景故事（可选）" value={form.background} onChange={e => setForm(f => ({ ...f, background: e.target.value }))} rows={2} style={{ marginTop: 8 }} />
          </div>
          <div>
            <Text strong style={{ color: THEME.textPrimary }}>角色圣经 Character Bible</Text>
            <Collapse
              size="small"
              style={{ marginTop: 8, background: THEME.bgCard, border: `1px solid ${THEME.borderLight}` }}
              items={[
                {
                  key: 'identity',
                  label: '身份档案',
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <Input placeholder="别名/代号" value={form.identity?.alias || ''} onChange={e => setBibleField('identity', 'alias', e.target.value)} />
                      <Input placeholder="性别/性别表达" value={form.identity?.gender || ''} onChange={e => setBibleField('identity', 'gender', e.target.value)} />
                      <Input placeholder="性别/种族/物种" value={form.identity?.species || ''} onChange={e => setBibleField('identity', 'species', e.target.value)} />
                      <Input placeholder="身高/体型" value={form.identity?.body_profile || ''} onChange={e => setBibleField('identity', 'body_profile', e.target.value)} />
                      <Input placeholder="组织/阵营" value={form.identity?.organization || ''} onChange={e => setBibleField('identity', 'organization', e.target.value)} />
                      <Input placeholder="职位/职级" value={form.identity?.position || ''} onChange={e => setBibleField('identity', 'position', e.target.value)} />
                      <Input placeholder="一句话人设摘要" value={form.identity?.logline || ''} onChange={e => setBibleField('identity', 'logline', e.target.value)} />
                    </div>
                  ),
                },
                {
                  key: 'motivation',
                  label: '动机与心理',
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <TextArea rows={2} placeholder="核心欲望：想要什么" value={form.motivation?.desire || ''} onChange={e => setBibleField('motivation', 'desire', e.target.value)} />
                      <TextArea rows={2} placeholder="深层恐惧：害怕失去什么" value={form.motivation?.fear || ''} onChange={e => setBibleField('motivation', 'fear', e.target.value)} />
                      <TextArea rows={2} placeholder="短期目标" value={form.motivation?.short_goal || ''} onChange={e => setBibleField('motivation', 'short_goal', e.target.value)} />
                      <TextArea rows={2} placeholder="长期目标/执念" value={form.motivation?.long_goal || ''} onChange={e => setBibleField('motivation', 'long_goal', e.target.value)} />
                      <TextArea rows={2} placeholder="执念：反复驱动 TA 的念头" value={form.motivation?.obsession || ''} onChange={e => setBibleField('motivation', 'obsession', e.target.value)} />
                      <TextArea rows={2} placeholder="价值观：判断取舍的底层原则" value={form.motivation?.values || ''} onChange={e => setBibleField('motivation', 'values', e.target.value)} />
                    </div>
                  ),
                },
                {
                  key: 'speech',
                  label: '语言语态',
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <Input placeholder="说话风格/语速/语气" value={form.speech?.tone || ''} onChange={e => setBibleField('speech', 'tone', e.target.value)} />
                      <Input placeholder="口头禅" value={form.speech?.catchphrase || ''} onChange={e => setBibleField('speech', 'catchphrase', e.target.value)} />
                      <TextArea rows={2} placeholder="常用句式/语言风格" value={form.speech?.style || form.speech?.sentence_pattern || ''} onChange={e => setBibleField('speech', 'style', e.target.value)} />
                      <TextArea rows={2} placeholder="不会说的话/回避话题" value={form.speech?.taboo || form.speech?.forbidden_topics || ''} onChange={e => setBibleField('speech', 'taboo', e.target.value)} />
                    </div>
                  ),
                },
                {
                  key: 'behavior',
                  label: '行为边界 / OOC',
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <TextArea rows={2} placeholder="习惯性动作/小癖好" value={form.behavior?.habit || form.behavior?.habits || ''} onChange={e => setBibleField('behavior', 'habit', e.target.value)} />
                      <TextArea rows={2} placeholder="应激反应" value={form.behavior?.stress_response || ''} onChange={e => setBibleField('behavior', 'stress_response', e.target.value)} />
                      <TextArea rows={2} placeholder="绝对底线" value={form.behavior?.boundary || ''} onChange={e => setBibleField('behavior', 'boundary', e.target.value)} />
                      <TextArea rows={2} placeholder="绝对不会做的事（OOC 判定）" value={form.behavior?.never_do || ''} onChange={e => setBibleField('behavior', 'never_do', e.target.value)} />
                    </div>
                  ),
                },
                {
                  key: 'ability',
                  label: '能力与限制',
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <TextArea rows={2} placeholder="天赋/技能" value={form.ability?.skills || ''} onChange={e => setBibleField('ability', 'skills', e.target.value)} />
                      <TextArea rows={2} placeholder="弱点/短板" value={form.ability?.weakness || ''} onChange={e => setBibleField('ability', 'weakness', e.target.value)} />
                      <TextArea rows={2} placeholder="使用限制/代价" value={form.ability?.limits || ''} onChange={e => setBibleField('ability', 'limits', e.target.value)} />
                      <TextArea rows={2} placeholder="代价：使用能力或达成目标要付出什么" value={form.ability?.cost || ''} onChange={e => setBibleField('ability', 'cost', e.target.value)} />
                      <TextArea rows={2} placeholder="知识特长" value={form.ability?.knowledge || ''} onChange={e => setBibleField('ability', 'knowledge', e.target.value)} />
                    </div>
                  ),
                },
                {
                  key: 'arc',
                  label: '人物弧光',
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                      <TextArea rows={2} placeholder="开局状态/前期人设" value={form.arc?.start_state || form.arc?.early || ''} onChange={e => setBibleField('arc', 'start_state', e.target.value)} />
                      <TextArea rows={2} placeholder="转变触发条件" value={form.arc?.turning_point || ''} onChange={e => setBibleField('arc', 'turning_point', e.target.value)} />
                      <TextArea rows={2} placeholder="结局走向" value={form.arc?.ending || ''} onChange={e => setBibleField('arc', 'ending', e.target.value)} />
                      <TextArea rows={2} placeholder="剧情雷点 / 容易 OOC 的桥段" value={form.arc?.risk || form.arc?.risk_notes || ''} onChange={e => setBibleField('arc', 'risk', e.target.value)} />
                    </div>
                  ),
                },
              ]}
            />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ color: THEME.textPrimary }}>立绘 / 参考图</Text>
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
                <Select
                  size="small"
                  style={{ width: 150 }}
                  placeholder="尺寸/比例"
                  value={selectedPortraitSize}
                  onChange={setSelectedPortraitSize}
                  options={portraitSizeOptions}
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
            <div style={{ marginTop: 10, padding: 12, borderRadius: 10, border: `1px solid ${THEME.primaryAlpha(0.18)}`, background: THEME.primaryAlpha(0.04) }}>
              <div style={{ marginBottom: 10 }}>
                <Text strong style={{ color: THEME.textPrimary, display: 'block', marginBottom: 6 }}>立绘模式</Text>
                <Segmented
                  size="small"
                  value={selectedPortraitPreset}
                  options={PORTRAIT_PRESET_OPTIONS}
                  onChange={(value) => {
                    handleChangePortraitPreset(value as PortraitPreset)
                  }}
                  style={{ maxWidth: '100%', overflowX: 'auto' }}
                />
                {selectedPortraitHelp && (
                  <Alert
                    type={selectedPortraitPreset.includes('grid') ? 'warning' : 'info'}
                    showIcon
                    message={selectedPortraitHelp.title}
                    description={[selectedPortraitHelp.detail, selectedPortraitHelp.sizeHint].filter(Boolean).join(' ')}
                    style={{ marginTop: 8 }}
                  />
                )}
              </div>
              <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }} align="center">
                <Space size={8}>
                  <Text strong style={{ color: THEME.primary }}>完整生图提示词</Text>
                  <Tooltip title="这里的提示词会直接用于 AI 生成立绘，也可以复制到其他生图工具。">
                    <Tag color="cyan">可复制</Tag>
                  </Tooltip>
                  <Tooltip title="保存角色时会按当前立绘模式保存，下次编辑会自动带回。">
                    <Tag color="green">随角色保存</Tag>
                  </Tooltip>
                </Space>
                <Space size={6} wrap>
                  <Select
                    size="small"
                    placeholder="LLM provider"
                    value={selectedEnrichProvider || undefined}
                    options={enrichProviderOptions}
                    onChange={(value) => {
                      setSelectedEnrichProvider(value)
                      const connector = llmConnectors.find((item) => item.name === value)
                      setSelectedEnrichModel(connector?.default_model || connector?.model || connector?.available_models?.[0] || '')
                    }}
                    style={{ width: 170 }}
                    disabled={optimizingPortraitPrompt}
                  />
                  <Select
                    size="small"
                    placeholder="LLM model"
                    value={selectedEnrichModel || undefined}
                    options={enrichModelOptions}
                    onChange={setSelectedEnrichModel}
                    style={{ width: 170 }}
                    disabled={optimizingPortraitPrompt || !selectedEnrichProvider}
                  />
                  <Button size="small" onClick={handleRefreshPortraitPrompt} loading={previewingPortraitPrompt}>
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
                onChange={e => updatePortraitPromptDraft(e.target.value)}
                rows={8}
                placeholder="根据角色信息生成或手动编辑完整立绘提示词；AI 生成立绘会使用这里的内容，保存角色后下次编辑会自动带回。"
                style={{ fontFamily: 'monospace', fontSize: 12 }}
              />
              <TextArea
                value={portraitNegativePromptDraft}
                onChange={e => updatePortraitNegativePromptDraft(e.target.value)}
                rows={3}
                placeholder="负向提示词。编辑已有角色时点击生成提示词会由后端按预设自动生成。"
                style={{ fontFamily: 'monospace', fontSize: 12, marginTop: 8 }}
              />
            </div>
            <Input placeholder="输入立绘图片 URL（也可由 AI 生成自动回填）" value={form.portrait_url} onChange={e => setForm(f => ({ ...f, portrait_url: e.target.value }))} style={{ marginTop: 8 }} />
            {form.portrait_url && !portraitPreviewDuplicatedByBaseline && (
              <div style={{ marginTop: 8 }}>
                <Space direction="vertical" size={4}>
                  <Text type="secondary" style={{ fontSize: 12 }}>当前立绘预览</Text>
                  <Image
                    src={form.portrait_url}
                    width={120}
                    height={120}
                    style={{ objectFit: 'cover', borderRadius: 8 }}
                    fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                  />
                </Space>
              </div>
            )}
            <div style={{ marginTop: 10 }}>
              {identityReferenceImage && (
                <div style={{ marginBottom: 10, padding: 10, borderRadius: 8, border: `1px solid ${THEME.borderLight}`, background: THEME.bgElevated }}>
                  <Space align="start" size={10}>
                    <Image
                      src={identityReferenceImage}
                      width={64}
                      height={64}
                      style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${THEME.borderLight}` }}
                      fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                    />
                    <Space direction="vertical" size={2}>
                      <Space size={6} wrap>
                        <Text strong style={{ color: THEME.textPrimary }}>身份基准图</Text>
                        <Tag color="green" style={{ marginInlineEnd: 0 }}>默认参考</Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        九宫格、动作姿态和后续分镜会优先用这张图保持同脸同服装。
                      </Text>
                      {visualProfile.identity_reference_version_id && (
                        <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
                          version: {visualProfile.identity_reference_version_id}
                        </Text>
                      )}
                    </Space>
                  </Space>
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  参考图 URL（用于支持图生图/参考图的模型；可填素材库图片下载地址或外部图片地址）
                </Text>
                <Space size={4} wrap>
                  <Tag color={currentGenerationReferenceImages.length ? 'blue' : 'default'} style={{ marginInlineEnd: 0 }}>
                    本次发送 {currentGenerationReferenceImages.length} 张
                  </Tag>
                  {willAutoAttachMainPortrait && (
                    <Tooltip title="表情/动作九宫格会自动把身份基准图加入本次参考图，并随角色视觉卡保存。">
                      <Tag color="gold" style={{ marginInlineEnd: 0 }}>自动带基准图</Tag>
                    </Tooltip>
                  )}
                </Space>
              </div>
              <Space size={6} wrap style={{ marginBottom: 8 }}>
                <Button
                  size="small"
                  icon={<CheckOutlined />}
                  onClick={() => {
                    if (!form.portrait_url) return
                    const nextForm = mergeIdentityReferenceIntoForm(form, form.portrait_url)
                    setForm(nextForm)
                    message.success('已设为身份基准图')
                  }}
                  disabled={!form.portrait_url || portraitPreviewDuplicatedByBaseline}
                >
                  设当前图为基准
                </Button>
                <Button
                  size="small"
                  icon={<PictureOutlined />}
                  onClick={() => appendReferenceImages([identityReferenceImage], '已加入身份基准图作为参考图')}
                  disabled={!identityReferenceImage}
                >
                  使用身份基准图
                </Button>
                <Button
                  size="small"
                  icon={<HistoryOutlined />}
                  onClick={() => appendReferenceImages(portraitVersions.map(version => version.image_url || '').filter(Boolean), '已加入历史立绘版本')}
                  disabled={!portraitVersions.length}
                >
                  加入历史立绘
                </Button>
                <Button
                  size="small"
                  icon={<FileImageOutlined />}
                  onClick={() => setReferencePickerOpen(true)}
                >
                  从素材库选择
                </Button>
              </Space>
              <Select
                {...compactTagSelectProps}
                mode="tags"
                placeholder="粘贴参考图 URL 后回车；例如素材库 /api/v1/assets/download?... 地址"
                value={visualProfile.reference_image_urls || []}
                onChange={value => setVisualProfileField('reference_image_urls', value)}
              />
              {(visualProfile.reference_image_urls || []).length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  {(visualProfile.reference_image_urls || []).slice(0, 6).map((url: string, index: number) => (
                    <Image
                      key={`${url}-${index}`}
                      src={url}
                      width={72}
                      height={72}
                      style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${THEME.borderLight}` }}
                      fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                    />
                  ))}
                </div>
              )}
            </div>
            {form.portrait_asset_id && (
              <div style={{ marginTop: 6, fontSize: 12, color: THEME.textSecondary }}>
                已绑定资产 ID: <span style={{ fontFamily: 'monospace' }}>{form.portrait_asset_id}</span>
              </div>
            )}
          </div>
          <div>
            <Text strong style={{ color: THEME.textPrimary }}>自定义标签</Text>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <Input placeholder="输入标签后回车添加" value={tagInput} onChange={e => setTagInput(e.target.value)} onPressEnter={addTagToForm} style={{ flex: 1 }} />
              <Button onClick={addTagToForm}>添加</Button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {(form.tags || []).map(tag => (
                <Tag key={tag} closable onClose={() => setForm(f => ({ ...f, tags: (f.tags || []).filter(t => t !== tag) }))} style={accentTagStyle}>{tag}</Tag>
              ))}
            </div>
          </div>
          {editingCharacter?.is_frozen && <Alert type="warning" message="此角色已冻结（生成后为保持一致性禁止修改外观描述）" showIcon />}
        </div>
      </Modal>
      <Modal
        open={referencePickerOpen}
        title="选择数据库参考图"
        width={760}
        footer={null}
        onCancel={() => setReferencePickerOpen(false)}
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="参考图会加入角色视觉卡的 reference_image_urls。生成立绘时，支持图生图/参考图的模型会收到这些图片。"
          />
          <Tabs
            items={[
              {
                key: 'portraits',
                label: `角色立绘版本 (${portraitVersions.length})`,
                children: portraitVersions.length ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
                    {portraitVersions.map(version => {
                      const url = version.image_url || ''
                      return (
                        <div key={version.id} style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: 8, background: THEME.bgElevated }}>
                          <Image
                            src={url}
                            width="100%"
                            height={110}
                            style={{ objectFit: 'cover', borderRadius: 6 }}
                            fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                          />
                          <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                            <Text strong style={{ fontSize: 12, color: THEME.textPrimary }}>
                              v{version.version_number}{version.is_main ? ' · 主立绘' : ''}
                            </Text>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {[version.preset, formatImageSizeLabel(version)].filter(Boolean).join(' · ') || '角色立绘'}
                            </Text>
                            <Button size="small" block onClick={() => appendReferenceImages([url])} disabled={!url}>
                              加入参考
                            </Button>
                          </Space>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <Empty description="暂无立绘版本，生成或升级到资产中枢后会出现在这里" />
                ),
              },
              {
                key: 'assets',
                label: '素材库图片',
                children: (
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Input.Search
                      allowClear
                      placeholder="搜索素材库图片标题、标签或模型"
                      value={referenceAssetSearch}
                      onChange={e => setReferenceAssetSearch(e.target.value)}
                      onSearch={loadReferenceAssets}
                      enterButton={<SearchOutlined />}
                    />
                    <Spin spinning={referenceAssetsLoading}>
                      {referenceAssets.length ? (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10, minHeight: 180 }}>
                          {referenceAssets.map(asset => {
                            const refUrl = getAssetReferenceUrl(asset)
                            const previewUrl = getAssetPreviewUrl(asset)
                            return (
                              <div key={asset.id} style={{ border: `1px solid ${THEME.borderLight}`, borderRadius: 8, padding: 8, background: THEME.bgElevated }}>
                                <Image
                                  src={previewUrl}
                                  width="100%"
                                  height={110}
                                  style={{ objectFit: 'cover', borderRadius: 6 }}
                                  fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                                />
                                <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                                  <Tooltip title={asset.title}>
                                    <Text strong ellipsis style={{ fontSize: 12, color: THEME.textPrimary, maxWidth: '100%' }}>
                                      {asset.title || asset.id}
                                    </Text>
                                  </Tooltip>
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    {[formatImageSizeLabel(asset), asset.platform || asset.source_type].filter(Boolean).join(' · ') || '素材库图片'}
                                  </Text>
                                  <Button size="small" block onClick={() => appendReferenceImages([refUrl])} disabled={!refUrl}>
                                    加入参考
                                  </Button>
                                </Space>
                              </div>
                            )
                          })}
                        </div>
                      ) : (
                        <Empty description={referenceAssetsLoading ? '加载中...' : '没有找到图片素材'} />
                      )}
                    </Spin>
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      </Modal>
    </div>
  )
}

function CharacterIdentityBoard({ character, theme }: { character: Character; theme: any }) {
  const identity = character.identity || {}
  const motivation = character.motivation || {}
  const behavior = character.behavior || {}
  const speech = character.speech || {}
  const primaryMeta = [
    character.age_range,
    identity.gender,
    identity.species,
    identity.organization || identity.faction,
    identity.position,
  ].filter(Boolean)
  return (
    <div style={{ padding: 20, background: `linear-gradient(135deg, ${theme.bgCard}, ${theme.bgElevated})`, borderBottom: `1px solid ${theme.borderLight}` }}>
      <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 18, alignItems: 'stretch' }}>
        <div style={{ borderRadius: 10, overflow: 'hidden', background: theme.bgElevated, minHeight: 220, border: `1px solid ${theme.borderLight}` }}>
          {character.portrait_url ? (
            <img src={character.portrait_url} alt={character.name} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
          ) : (
            <div style={{ height: '100%', minHeight: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Avatar size={88} icon={<UserOutlined />} />
            </div>
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <Space wrap size={6} style={{ marginBottom: 8 }}>
            <Tag color="blue">{CHARACTER_ROLE_OPTIONS.find(o => o.value === character.role)?.label || character.role}</Tag>
            {character.is_frozen ? <Tag color="gold" icon={<LockOutlined />}>冻结</Tag> : null}
            {character.portrait_node_id ? <Tag color="green" icon={<DatabaseOutlined />}>资产中枢</Tag> : null}
            {(character.world_usages || []).length ? <Tag color="purple">{(character.world_usages || []).length} 个世界</Tag> : null}
          </Space>
          <Title level={3} style={{ margin: 0, color: theme.textPrimary }}>{character.name}</Title>
          <Text style={{ display: 'block', color: theme.textSecondary, marginTop: 6 }}>
            {primaryMeta.length ? primaryMeta.join(' · ') : '未补充基础身份'}
          </Text>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 16 }}>
            <BibleMetric label="核心欲望" value={motivation.desire || motivation.core_desire} theme={theme} />
            <BibleMetric label="深层恐惧" value={motivation.fear || motivation.deep_fear} theme={theme} />
            <BibleMetric label="说话方式" value={speech.tone || speech.style || speech.catchphrase} theme={theme} />
            <BibleMetric label="OOC 底线" value={behavior.never_do || behavior.boundary || behavior.ooc_boundary} theme={theme} />
          </div>
          <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {(character.signature_items || []).slice(0, 5).map(item => <Tag key={item}>{item}</Tag>)}
            {(character.tags || []).slice(0, 5).map(tag => <Tag key={tag} style={{ background: theme.bgElevated, color: theme.textSecondary }}>{tag}</Tag>)}
          </div>
        </div>
      </div>
    </div>
  )
}

function BibleMetric({ label, value, theme }: { label: string; value: any; theme: any }) {
  return (
    <div style={{ padding: '10px 12px', borderRadius: 8, background: theme.bgPage, border: `1px solid ${theme.borderLight}`, minHeight: 62 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
      <div style={{ color: value ? theme.textPrimary : theme.textSecondary, marginTop: 4, fontSize: 13, lineHeight: 1.45 }}>
        {value || '未设置'}
      </div>
    </div>
  )
}

function CharacterBibleQuickPanels({ character, theme }: { character: Character; theme: any }) {
  const panels = [
    {
      title: '身份',
      items: [
        ['别名', character.identity?.alias],
        ['组织', character.identity?.organization],
        ['职位', character.identity?.position],
        ['摘要', character.identity?.logline],
      ],
    },
    {
      title: '动机',
      items: [
        ['欲望', character.motivation?.desire],
        ['恐惧', character.motivation?.fear],
        ['目标', character.motivation?.long_goal || character.motivation?.short_goal],
        ['执念', character.motivation?.obsession],
      ],
    },
    {
      title: '语言/OOC',
      items: [
        ['语气', character.speech?.tone],
        ['口头禅', character.speech?.catchphrase],
        ['底线', character.behavior?.boundary],
        ['绝不做', character.behavior?.never_do],
      ],
    },
    {
      title: '能力/弧光',
      items: [
        ['技能', character.ability?.skills],
        ['弱点', character.ability?.weakness],
        ['转折', character.arc?.turning_point],
        ['结局', character.arc?.ending],
      ],
    },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, marginBottom: 18 }}>
      {panels.map(panel => (
        <div key={panel.title} style={{ padding: 14, borderRadius: 10, background: theme.bgCard, border: `1px solid ${theme.borderLight}` }}>
          <Text strong style={{ color: theme.textPrimary }}>{panel.title}</Text>
          <div style={{ display: 'grid', gap: 7, marginTop: 10 }}>
            {panel.items.map(([label, value]) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '56px 1fr', gap: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
                <Text style={{ color: value ? theme.textPrimary : theme.textSecondary, fontSize: 13 }} ellipsis={{ tooltip: String(value || '') }}>
                  {value || '未设置'}
                </Text>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function CharacterBibleDetailedPanels({ character, theme }: { character: Character; theme: any }) {
  const visual = character.identity?.visual_profile || {}
  const sections = [
    {
      key: 'visual_profile',
      title: '视觉卡细项',
      items: [
        ['脸部识别点', visual.face],
        ['发型发色', visual.hair],
        ['眼睛', visual.eyes],
        ['肤色/皮肤', visual.skin],
        ['体型', visual.body_shape || character.identity?.body_profile],
        ['身体比例', visual.body_proportion],
        ['服装结构', visual.costume || character.costume_hint],
        ['服装配色', visual.costume_colors],
        ['材质', visual.materials],
        ['鞋履', visual.shoes],
        ['配饰', visual.accessories],
        ['画风', visual.style],
        ['负面约束', visual.negative_constraints],
      ],
    },
    {
      key: 'motivation_full',
      title: '动机与心理',
      items: [
        ['核心欲望', character.motivation?.desire],
        ['深层恐惧', character.motivation?.fear],
        ['短期目标', character.motivation?.short_goal],
        ['长期目标', character.motivation?.long_goal],
        ['执念', character.motivation?.obsession],
        ['价值观', character.motivation?.values],
      ],
    },
    {
      key: 'speech_full',
      title: '语言语态',
      items: [
        ['语气', character.speech?.tone],
        ['口头禅', character.speech?.catchphrase],
        ['句式/风格', character.speech?.style || character.speech?.sentence_pattern],
        ['禁忌话题', character.speech?.taboo || character.speech?.forbidden_topics],
      ],
    },
    {
      key: 'behavior_full',
      title: '行为与 OOC 边界',
      items: [
        ['行为习惯', character.behavior?.habit || character.behavior?.habits],
        ['压力反应', character.behavior?.stress_response],
        ['底线', character.behavior?.boundary],
        ['绝不会做', character.behavior?.never_do],
      ],
    },
    {
      key: 'ability_arc_full',
      title: '能力限制与人物弧光',
      items: [
        ['技能/特长', character.ability?.skills],
        ['弱点', character.ability?.weakness],
        ['限制', character.ability?.limits],
        ['代价', character.ability?.cost],
        ['开局状态', character.arc?.start_state || character.arc?.early],
        ['关键转折', character.arc?.turning_point],
        ['结局方向', character.arc?.ending],
        ['剧情风险', character.arc?.risk || character.arc?.risk_notes],
      ],
    },
  ]

  return (
    <Collapse
      size="small"
      style={{ marginBottom: 16, background: theme.bgCard, border: `1px solid ${theme.borderLight}` }}
      items={sections.map((section) => ({
        key: section.key,
        label: section.title,
        children: (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
            {section.items.map(([label, value]) => (
              <BibleDetailCell key={label} label={label} value={value} theme={theme} />
            ))}
          </div>
        ),
      }))}
    />
  )
}

function BibleDetailCell({ label, value, theme }: { label: string; value: any; theme: any }) {
  const text = formatBibleValue(value)
  return (
    <div style={{ padding: 10, borderRadius: 8, background: theme.bgPage, border: `1px solid ${theme.borderLight}` }}>
      <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>{label}</Text>
      <Paragraph
        style={{ margin: 0, color: text ? theme.textPrimary : theme.textSecondary, whiteSpace: 'pre-wrap' }}
        ellipsis={{ rows: 3, tooltip: text }}
      >
        {text || '未设置'}
      </Paragraph>
    </div>
  )
}

function formatBibleValue(value: any): string {
  if (Array.isArray(value)) return value.filter(Boolean).join('、')
  if (value && typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value || '').trim()
}

function CharacterReferenceStatus({ character, theme }: { character: Character; theme: any }) {
  const visualProfile = character.identity?.visual_profile || {}
  const identityReference = String(visualProfile.identity_reference_url || character.portrait_url || '').trim()
  const referenceImages = Array.isArray(visualProfile.reference_image_urls)
    ? cleanImageUrls(visualProfile.reference_image_urls)
    : []
  return (
    <div style={{
      marginBottom: 14,
      padding: 12,
      borderRadius: 10,
      background: theme.bgCard,
      border: `1px solid ${theme.borderLight}`,
    }}>
      <Space align="start" size={12} style={{ width: '100%' }}>
        {identityReference ? (
          <Image
            src={identityReference}
            width={72}
            height={72}
            style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${theme.borderLight}` }}
            fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
          />
        ) : (
          <div style={{
            width: 72,
            height: 72,
            borderRadius: 8,
            border: `1px dashed ${theme.borderLight}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: theme.textSecondary,
          }}>
            <PictureOutlined />
          </div>
        )}
        <Space direction="vertical" size={6} style={{ minWidth: 0, flex: 1 }}>
          <Space wrap size={6}>
            <Text strong style={{ color: theme.textPrimary }}>视觉参考状态</Text>
            <Tag color={identityReference ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
              {identityReference ? '已有身份基准图' : '缺身份基准图'}
            </Tag>
            <Tag color={referenceImages.length ? 'blue' : 'default'} style={{ marginInlineEnd: 0 }}>
              默认参考图 {referenceImages.length}
            </Tag>
            <Tag color={character.portrait_node_id ? 'green' : 'default'} style={{ marginInlineEnd: 0 }}>
              {character.portrait_node_id ? '资产中枢已绑定' : '未绑定资产中枢'}
            </Tag>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            身份基准图用于锁脸；默认参考图会在九宫格和后续分镜生图时优先参与参考。
          </Text>
          {visualProfile.identity_reference_version_id ? (
            <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
              baseline version: {visualProfile.identity_reference_version_id}
            </Text>
          ) : null}
        </Space>
      </Space>
    </div>
  )
}

function CharacterEnrichmentStrip({
  character,
  loading,
  providerOptions,
  selectedProvider,
  selectedModel,
  modelOptions,
  onProviderChange,
  onModelChange,
  onFillMissing,
  onRewrite,
}: {
  character: Character
  loading: boolean
  providerOptions: Array<{ label: string; value: string }>
  selectedProvider: string
  selectedModel: string
  modelOptions: Array<{ label: string; value: string }>
  onProviderChange: (value: string) => void
  onModelChange: (value: string) => void
  onFillMissing: () => void
  onRewrite: () => void
}) {
  const { theme } = useTheme()
  const completeness = getCharacterCompleteness(character)
  const missing = getCharacterMissingLabels(character)
  return (
    <div style={{
      marginBottom: 14,
      padding: 14,
      borderRadius: 10,
      background: theme.bgCard,
      border: `1px solid ${theme.borderLight}`,
      display: 'grid',
      gridTemplateColumns: '1fr auto',
      gap: 12,
      alignItems: 'center',
    }}>
      <Space direction="vertical" size={4}>
        <Space wrap>
          <Text strong style={{ color: theme.textPrimary }}>设定完整度 {completeness}%</Text>
          {missing.slice(0, 5).map(item => <Tag key={item}>{item}</Tag>)}
          {missing.length > 5 ? <Tag>+{missing.length - 5}</Tag> : null}
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          老角色和小说抽取角色适合先补空字段；已定稿角色需要统一口径时再重写。
        </Text>
      </Space>
      <Space wrap style={{ justifyContent: 'flex-end' }}>
        <Select
          size="small"
          placeholder="LLM provider"
          value={selectedProvider || undefined}
          options={providerOptions}
          onChange={onProviderChange}
          style={{ width: 190 }}
          disabled={loading}
        />
        <Select
          size="small"
          placeholder="LLM model"
          value={selectedModel || undefined}
          options={modelOptions}
          onChange={onModelChange}
          style={{ width: 190 }}
          disabled={loading || !selectedProvider}
        />
        <Button icon={<ThunderboltOutlined />} loading={loading} onClick={onFillMissing}>
          AI 补空字段
        </Button>
        <Popconfirm
          title="用 AI 统一重写角色设定？"
          description="会保留核心身份，但可能覆盖已有字段。建议只在早期开发或设定混乱时使用。"
          okText="重写"
          cancelText="取消"
          onConfirm={onRewrite}
        >
          <Button loading={loading}>统一重写</Button>
        </Popconfirm>
      </Space>
    </div>
  )
}

function getCharacterCompleteness(character: Character): number {
  const checks = [
    character.appearance,
    character.costume_hint,
    character.personality,
    character.background,
    character.age_range,
    character.visual_consistency,
    (character.signature_items || []).length,
    (character.expressions || []).length,
    (character.poses || []).length,
    character.identity?.logline || character.identity?.position,
    character.motivation?.desire,
    character.motivation?.fear,
    character.speech?.tone,
    character.behavior?.never_do || character.behavior?.boundary,
    character.ability?.skills,
    character.arc?.turning_point || character.arc?.ending,
  ]
  const done = checks.filter(Boolean).length
  return Math.round((done / checks.length) * 100)
}

function getCharacterMissingLabels(character: Character): string[] {
  const pairs: [string, any][] = [
    ['外观', character.appearance],
    ['服装', character.costume_hint],
    ['性格', character.personality],
    ['背景', character.background],
    ['年龄', character.age_range],
    ['一致性', character.visual_consistency],
    ['标志物', (character.signature_items || []).length],
    ['表情', (character.expressions || []).length],
    ['姿态', (character.poses || []).length],
    ['一句话人设', character.identity?.logline],
    ['欲望', character.motivation?.desire],
    ['恐惧', character.motivation?.fear],
    ['语气', character.speech?.tone],
    ['OOC 底线', character.behavior?.never_do || character.behavior?.boundary],
    ['能力', character.ability?.skills],
    ['弧光', character.arc?.turning_point || character.arc?.ending],
  ]
  return pairs.filter(([, value]) => !value).map(([label]) => label)
}

// ---------------------------------------------------------------------------
// 角色立绘版本 Tab
// ---------------------------------------------------------------------------

function CharacterPortraitVersionsTab({
  versions,
  slices,
  loading,
  slicesLoading,
  settingMainId,
  slicingId,
  onSetMain,
  onAddReference,
  onSliceGrid,
  onRefresh,
}: {
  versions: PortraitVersionItem[]
  slices: PortraitSliceItem[]
  loading: boolean
  slicesLoading: boolean
  settingMainId: string
  slicingId: string
  onSetMain: (version: PortraitVersionItem) => void
  onAddReference: (version: PortraitVersionItem) => void
  onSliceGrid: (version: PortraitVersionItem) => void
  onRefresh: () => void
}) {
  const { theme } = useTheme()
  const isGridVersion = (record: PortraitVersionItem) => ['expression_grid_3x3', 'pose_grid_3x3'].includes(record.preset)
  const columns = [
    {
      title: '预览',
      dataIndex: 'image_url',
      width: 92,
      render: (url: string, record: PortraitVersionItem) => url ? (
        <Image
          src={url}
          alt={`v${record.version_number}`}
          width={64}
          height={64}
          style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${theme.borderLight}` }}
          fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        />
      ) : <Text type="secondary">无图</Text>,
    },
    {
      title: '版本',
      dataIndex: 'version_number',
      width: 110,
      render: (_: number, record: PortraitVersionItem) => (
        <Space direction="vertical" size={2}>
          <Space>
            <Text strong style={{ color: theme.textPrimary }}>v{record.version_number}</Text>
            {record.is_main ? <Tag color="green" icon={<CheckOutlined />}>主立绘</Tag> : null}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.created_at ? new Date(record.created_at).toLocaleString('zh-CN', { hour12: false }) : '-'}
          </Text>
        </Space>
      ),
    },
    {
      title: '用途/模型',
      dataIndex: 'preset',
      render: (_: string, record: PortraitVersionItem) => (
        <Space direction="vertical" size={4}>
          <Space wrap size={4}>
            {record.preset ? <Tag>{PORTRAIT_PRESET_OPTIONS.find(item => item.value === record.preset)?.label || record.preset}</Tag> : null}
            {record.provider ? <Tag color="blue">{record.provider}</Tag> : null}
          </Space>
          <Text style={{ color: theme.textSecondary }} ellipsis={{ tooltip: record.model }}>
            {record.model || '未记录模型'}
          </Text>
        </Space>
      ),
    },
    {
      title: '尺寸',
      width: 90,
      render: (_: any, record: PortraitVersionItem) => (
        <Text type="secondary">
          {record.width && record.height ? `${record.width}x${record.height}` : '-'}
        </Text>
      ),
    },
    {
      title: '操作',
      width: 210,
      render: (_: any, record: PortraitVersionItem) => (
        <Space size={6} wrap>
          {isGridVersion(record) ? (
            <Popconfirm
              title="切出 3x3 子素材？"
              description="会把这张九宫格图切成 9 张图片，并挂到该角色立绘节点下供分镜引用。"
              okText="切片"
              cancelText="取消"
              onConfirm={() => onSliceGrid(record)}
            >
              <Button
                size="small"
                icon={<FileImageOutlined />}
                loading={slicingId === record.id}
              >
                切九宫格
              </Button>
            </Popconfirm>
          ) : null}
          <Button
            size="small"
            disabled={record.is_main}
            loading={settingMainId === record.id}
            onClick={() => onSetMain(record)}
          >
            设为基准
          </Button>
          <Button
            size="small"
            disabled={!record.image_url}
            onClick={() => onAddReference(record)}
          >
            加入参考
          </Button>
        </Space>
      ),
    },
  ]
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          每次生成都会保留一个 Asset Hub 版本；主立绘决定角色列表、详情页和后续参考图默认使用哪张。
        </Text>
        <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>刷新</Button>
      </Space>
      {versions.length ? (
        <Table
          size="small"
          rowKey="id"
          columns={columns}
          dataSource={versions}
          loading={loading}
          pagination={false}
          expandable={{
            expandedRowRender: (record: PortraitVersionItem) => (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <ReferenceImagesPreview urls={record.params?.reference_images || []} />
                {record.prompt ? <LogTextBlock title="Prompt" value={record.prompt} rows={5} /> : null}
                {record.negative_prompt ? <LogTextBlock title="负面提示词" value={record.negative_prompt} rows={3} /> : null}
                {Object.keys(record.params || {}).length ? (
                  <LogTextBlock title="生成参数" value={JSON.stringify(record.params, null, 2)} rows={5} />
                ) : null}
              </Space>
            ),
          }}
        />
      ) : (
        <Empty description={loading ? '加载中...' : '暂无立绘版本。生成或升级立绘后会出现在这里。'} />
      )}
      <Divider style={{ margin: '4px 0 0' }} />
      <Space style={{ justifyContent: 'space-between', width: '100%' }} align="center">
        <Space direction="vertical" size={2}>
          <Text strong style={{ color: theme.textPrimary }}>九宫格子素材</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            从表情/动作九宫格切出的可复用素材，会作为该角色立绘节点的子资产保存。
          </Text>
        </Space>
        {slices.length ? <Tag color="cyan">{slices.length} 张</Tag> : null}
      </Space>
      {slicesLoading ? (
        <Spin />
      ) : slices.length ? (
        <Image.PreviewGroup>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))', gap: 10 }}>
            {slices.map(slice => (
              <div
                key={slice.node_id}
                style={{
                  border: `1px solid ${theme.borderLight}`,
                  background: theme.bgCard,
                  borderRadius: 8,
                  overflow: 'hidden',
                }}
              >
                <div style={{ aspectRatio: '1 / 1', background: theme.bgElevated }}>
                  {slice.image_url ? (
                    <Image
                      src={slice.image_url}
                      alt={slice.label}
                      width="100%"
                      height="100%"
                      style={{ objectFit: 'cover', display: 'block' }}
                      fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
                    />
                  ) : (
                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <FileImageOutlined style={{ color: theme.textSecondary }} />
                    </div>
                  )}
                </div>
                <div style={{ padding: '6px 8px' }}>
                  <Text
                    strong
                    style={{ display: 'block', color: theme.textPrimary, fontSize: 12 }}
                    ellipsis={{ tooltip: slice.label }}
                  >
                    {slice.grid_index ? `${slice.grid_index}. ` : ''}{slice.label}
                  </Text>
                  <Space size={4} wrap style={{ marginTop: 4 }}>
                    <Tag color={slice.grid_type === 'pose' ? 'purple' : 'blue'} style={{ marginInlineEnd: 0 }}>
                      {slice.grid_type === 'pose' ? '动作' : '表情'}
                    </Tag>
                    {slice.row && slice.col ? <Tag style={{ marginInlineEnd: 0 }}>{slice.row}x{slice.col}</Tag> : null}
                  </Space>
                </div>
              </div>
            ))}
          </div>
        </Image.PreviewGroup>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无九宫格子素材。先生成表情九宫格或动作九宫格版本，再点击“切九宫格”。"
        />
      )}
    </Space>
  )
}

// ---------------------------------------------------------------------------
// 角色跨世界使用 Tab
// ---------------------------------------------------------------------------

function CharacterWorldUsagesTab({
  usages,
  loading,
  onAdd,
  onEdit,
  onDelete,
  onRefresh,
}: {
  usages: CharacterWorldUsage[]
  loading: boolean
  onAdd: () => void
  onEdit: (usage: CharacterWorldUsage) => void
  onDelete: (usage: CharacterWorldUsage) => void
  onRefresh: () => void
}) {
  const { theme } = useTheme()
  const columns = [
    {
      title: '项目/世界',
      dataIndex: 'project_title',
      render: (_: string, record: CharacterWorldUsage) => (
        <Space direction="vertical" size={2}>
          <Text strong style={{ color: theme.textPrimary }}>{record.project_title || record.story_id}</Text>
          <Space size={4} wrap>
            {record.world_name ? <Tag color="purple">{record.world_name}</Tag> : null}
            {record.project_type ? <Tag>{record.project_type}</Tag> : null}
          </Space>
        </Space>
      ),
    },
    {
      title: '局部身份',
      dataIndex: 'local_identity',
      render: (_: string, record: CharacterWorldUsage) => (
        <Space direction="vertical" size={2}>
          <Space size={4} wrap>
            {record.usage_role ? <Tag color="blue">{record.usage_role}</Tag> : null}
            {record.local_alias ? <Tag>{record.local_alias}</Tag> : null}
            {record.local_faction ? <Tag color="geekblue">{record.local_faction}</Tag> : null}
          </Space>
          {record.local_identity ? (
            <Text style={{ color: theme.textSecondary }}>{record.local_identity}</Text>
          ) : (
            <Text type="secondary">未设置局部身份</Text>
          )}
        </Space>
      ),
    },
    {
      title: '约束',
      dataIndex: 'ooc_notes',
      render: (_: string, record: CharacterWorldUsage) => (
        <Space direction="vertical" size={4}>
          {record.ooc_notes ? <Text style={{ color: theme.textPrimary }}>OOC：{record.ooc_notes.slice(0, 48)}{record.ooc_notes.length > 48 ? '...' : ''}</Text> : null}
          {record.off_model_notes ? <Text style={{ color: theme.textPrimary }}>Off-Model：{record.off_model_notes.slice(0, 48)}{record.off_model_notes.length > 48 ? '...' : ''}</Text> : null}
          {!record.ooc_notes && !record.off_model_notes ? <Text type="secondary">暂无约束</Text> : null}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 150,
      render: (_: any, record: CharacterWorldUsage) => (
        <Space size={6}>
          <Button size="small" onClick={() => onEdit(record)}>编辑</Button>
          <Popconfirm title="移除此世界使用关系？" onConfirm={() => onDelete(record)} okText="移除" cancelText="取消">
            <Button size="small" danger>移除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          角色本体可被多个项目/世界复用；这里记录每个世界里的局部身份、阵营、服装覆盖和 OOC/Off-Model 约束。
        </Text>
        <Space>
          <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>刷新</Button>
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={onAdd}>绑定项目</Button>
        </Space>
      </Space>
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={usages}
        loading={loading}
        pagination={false}
        locale={{ emptyText: '此角色还没有绑定到项目/世界' }}
      />
    </Space>
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
  character_enrich_fill_missing: 'AI 补空字段',
  character_enrich_rewrite: 'AI 统一重写',
  portrait_prompt_optimize: '提示词优化',
  portrait_grid_slice: '九宫格切片',
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
  const { theme } = useTheme()
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
      render: (v: string) => v ? <Text style={{ color: theme.textPrimary }}>{v}</Text> : <Text type="secondary">-</Text>,
    },
    {
      title: 'Prompt',
      dataIndex: 'prompt',
      ellipsis: true,
      render: (v: string) => v ? <Text style={{ color: theme.textPrimary }}>{v.slice(0, 60)}{v.length > 60 ? '...' : ''}</Text> : <Text type="secondary">-</Text>,
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
  const { theme } = useTheme()
  return (
    <div>
      <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
      <Input.TextArea
        value={value}
        readOnly
        autoSize={{ minRows: Math.min(rows, 12), maxRows: 12 }}
        style={{
          marginTop: 4,
          background: theme.bgInput,
          borderColor: theme.borderLight,
          color: theme.textPrimary,
          fontFamily: 'monospace',
          fontSize: 12,
        }}
      />
    </div>
  )
}

function ReferenceImagesPreview({ urls }: { urls: string[] }) {
  const { theme } = useTheme()
  const items = (urls || []).map(url => String(url || '').trim()).filter(Boolean)
  if (!items.length) return null
  return (
    <div>
      <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
        参考图 · {items.length}
      </Text>
      <Image.PreviewGroup>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {items.slice(0, 12).map((url, index) => (
            <Image
              key={`${url}-${index}`}
              src={url}
              width={72}
              height={72}
              style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${theme.borderLight}` }}
              fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            />
          ))}
        </div>
      </Image.PreviewGroup>
    </div>
  )
}
