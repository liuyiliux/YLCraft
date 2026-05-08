/**
 * YLCraft — 全局类型定义
 */

// ===== Provider =====

export interface Provider {
  id: string
  provider: string
  provider_label?: string  // 提供商中文名称
  name: string
  provider_type: string
  base_url?: string
  api_endpoint?: string
  api_key?: string
  default_model?: string
  max_tokens?: number
  temperature?: number
  priority?: number
  usage_count?: number
  total_cost?: number
  last_used?: string
  is_active: boolean
  is_default?: boolean
  description?: string
  // 扩展字段（用于图像/视频生成）
  request_template?: string
  response_config?: string
  supported_sizes?: string[]
  default_params?: Record<string, any>
  support_reference_image?: boolean
  support_multiple_reference_images?: boolean
  reference_image_field?: string
  has_api_key?: boolean
}

export interface ConnectorTestDebug {
  request?: {
    method?: string
    url?: string
    headers?: Record<string, string>
    body?: unknown
  }
  response?: {
    status_code?: number | null
    headers?: Record<string, string>
    body?: unknown
  }
  latency_ms?: number | null
  exception?: string
}

export interface ConnectorTestResult {
  success: boolean
  message: string
  connector_id: string
  debug?: ConnectorTestDebug
}

// Provider 枚举值列表（用于下拉选择）
// 注意：所有类型都使用 OpenAI 兼容 API 格式
// generic 用于完全自定义配置（自定义 request/response）
export const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'siliconflow', label: '硅基流动' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'generic', label: '通用配置' },
]

// ===== LLM =====

export interface ChatRequest {
  model?: string
  messages: LLMMessage[]
  temperature?: number
  max_tokens?: number
  provider?: string
  tools?: unknown[]
}

export interface LLMMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatResponse {
  success: boolean
  content: string
  usage?: { prompt_tokens: number; completion_tokens: number }
  error?: string
}

// ===== Images =====

export interface ImageGenerateRequest {
  prompt: string
  negative_prompt?: string
  size?: string
  style?: string
  n?: number
  provider?: string
}

export interface ImageResponse {
  success: boolean
  url?: string
  urls?: string[]
  error?: string
}

// ===== Breaker =====

export interface BreakerTask {
  task_id: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  progress?: number
  error?: string
}

export interface BreakerResult {
  report: {
    hook: string
    structure: string
    emotion_curve: string
    elements: string[]
  }
  script: BreakerShot[]
  prompts: { type: string; prompt: string }[]
  video_url?: string
}

export interface BreakerShot {
  shot: number
  description: string
  duration: number
  dialogue: string
}

// ===== XHS 小红书 =====

export interface XhsNote {
  title: string
  description: string
  images: string[]
  covers: string[]
  author: string
  author_id: string
  likes: number
  note_id: string
  source_url: string
  cover_url: string
}

export interface XhsPreviewResponse {
  success: boolean
  url: string
  platform: string
  parsed: XhsNote | null
  analysis: BreakerResult | null
  message: string
}

// ===== AI 剪辑 =====

export interface VideoAnalysis {
  duration_ms: number
  width: number
  height: number
  fps: number
  total_frames: number
  shots: ClipShot[]
  audio: AudioInfo
}

export interface ClipShot {
  index: number
  start_ms: number
  end_ms: number
  shot_type?: string
  description?: string
  aesthetic_score?: number
  emotion?: string
}

export interface AudioInfo {
  bpm?: number
  beat_times?: number[]
  energy_profile?: number[]
  music_genre?: string
  human_voice_segments?: number[][]
}

export interface CutClawRequest {
  video_path: string
  user_prompt: string
  max_turns?: number
  model?: string
}

export interface CutClawResult {
  task_id: string
  status: string
  analysis?: VideoAnalysis
  plan?: ClipPlan
  ffmpeg_command?: string
  error?: string
}

export interface ClipPlan {
  shots: { shot_index: number; in_ms: number; out_ms: number }[]
  narration?: string
  ffmpeg_command?: string
}

export interface MoERequest {
  video_path: string
  user_prompt?: string
  auto_approve?: boolean
  enabled_experts?: string[]
}

export interface MoEResult {
  task_id: string
  status: string
  auto_deltas: EditDelta[]
  pending_review: EditDelta[]
  conflicts: Conflict[]
  expert_results: Record<string, EditDelta[]>
}

export interface EditDelta {
  expert_id: string
  parameter: string
  value: unknown
  confidence: number
  impact: 'low' | 'medium' | 'high'
  rationale: string
}

export interface Conflict {
  parameter: string
  severity: string
  delta1: EditDelta
  delta2: EditDelta
}

export interface NarratoRequest {
  video_path: string
  mode: 'documentary' | 'short_drama'
  style?: string
  voice?: string
  frame_interval?: number
}

// ===== Story Maker =====

export interface StoryRequest {
  title: string
  genre: string
  plot_summary: string
  num_beats?: number
  character_names?: string[]
  character_descriptions?: Record<string, string>
  generate_images?: boolean
  style?: string
}

export interface StoryScript {
  title: string
  genre: string
  total_duration_sec: number
  plot_summary: string
  characters: StoryCharacter[]
  beats: StoryBeat[]
}

export interface StoryCharacter {
  name: string
  role: string
  appearance?: string
  personality?: string
  costume_hint?: string
  image_url?: string
}

export interface StoryBeat {
  beat_id: number
  title: string
  description: string
  shot_type: string
  duration_sec: number
  characters: string[]
  dialogue?: string
  sfx?: string
  emotion?: string
  background_hint?: string
  image_url?: string
}

// ===== Download =====

export interface VideoQuality {
  quality: string
  resolution: string
  filesize: string
  url: string
}

export interface DownloadParseResponse {
  success: boolean
  title: string
  author: string
  platform: string
  cover_url: string
  duration: number
  duration_str: string
  video_url: string
  qualities: VideoQuality[]
  audio_url: string
  page_url: string   // 原始分享页 URL
  error: string
}

// ===== Task Queue =====

export interface Task {
  id: string
  type: 'breaker' | 'cutclaw' | 'narrato' | 'moe' | 'story' | string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  progress?: number
  payload?: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string
  created_at: string
  updated_at?: string
  retry_count?: number
}

// ===== Asset Library =====

export type AssetType = 'video' | 'audio' | 'image' | 'document'
export type AssetStatus = 'parsed' | 'downloading' | 'ready' | 'processing' | 'error'

export interface AssetTag {
  id: string
  name: string
  color: string
  asset_count?: number
  created_at?: string
}

export interface AssetCollection {
  id: string
  name: string
  description?: string
  cover_asset_id?: string
  collection_type?: string
  asset_ids?: string[]
  created_at?: string
}

export interface Asset {
  id: string
  asset_type: AssetType
  title: string
  description?: string
  source_url: string
  platform?: string
  author?: string
  author_url?: string
  cover_url?: string
  thumbnail_path?: string
  duration?: number
  file_path?: string
  file_size?: number
  mime_type?: string
  width?: number
  height?: number
  status: AssetStatus
  error_message?: string
  tags: AssetTag[]
  metadata?: Record<string, unknown>
  use_count?: number
  last_used_at?: string
  created_at: string
  updated_at?: string
  downloaded_at?: string
}

export interface AssetListResponse {
  success: boolean
  data: Asset[]
  total: number
  page: number
  page_size: number
}

export interface AssetUpdateRequest {
  title?: string
  description?: string
  tags?: string[]
}

export interface AssetFilterParams {
  asset_type?: AssetType
  platform?: string
  status?: AssetStatus
  tags?: string
  search?: string
  page?: number
  page_size?: number
  sort_by?: 'created_at' | 'title' | 'download_count'
  sort_order?: 'asc' | 'desc'
}

export interface AssetStat {
  total: number
  by_type: { video: number; audio: number; image: number; document: number }
  by_status: Record<AssetStatus, number>
  total_size: number
}

// ===== Character =====

export type CharacterSourceType =
  | 'ai_generated'
  | 'local_material'
  | 'real_person'
  | 'anime_reference'
  | 'stock_footage'
  | 'other'

export type CharacterRole = 'protagonist' | 'antagonist' | 'supporting' | 'extra'

export const CHARACTER_SOURCE_TYPE_OPTIONS: { value: CharacterSourceType; label: string }[] = [
  { value: 'ai_generated', label: 'AI生成' },
  { value: 'local_material', label: '本地素材' },
  { value: 'real_person', label: '真人对白' },
  { value: 'anime_reference', label: '动漫原型' },
  { value: 'stock_footage', label: '库存人物' },
  { value: 'other', label: '其他' },
]

export const CHARACTER_ROLE_OPTIONS: { value: CharacterRole; label: string }[] = [
  { value: 'protagonist', label: '主角' },
  { value: 'antagonist', label: '反派' },
  { value: 'supporting', label: '配角' },
  { value: 'extra', label: '路人' },
]

export interface Character {
  id: string
  name: string
  role: CharacterRole
  role_label: string
  age_range: string
  appearance: string
  personality: string
  costume_hint: string
  background: string
  source_types: CharacterSourceType[]
  source_type_labels: string[]
  tags: string[]
  portrait_url: string
  portrait_asset_id: string
  reference_asset_ids: string[]
  use_count: number
  is_favorite: boolean
  is_frozen: boolean
  created_at: string
  updated_at: string
}

export interface CharacterCreateRequest {
  name: string
  role?: CharacterRole
  source_types?: CharacterSourceType[]
  appearance?: string
  personality?: string
  costume_hint?: string
  background?: string
  age_range?: string
  tags?: string[]
  portrait_url?: string
  portrait_asset_id?: string
  reference_asset_ids?: string[]
}

export interface CharacterUpdateRequest {
  name?: string
  role?: CharacterRole
  source_types?: CharacterSourceType[]
  appearance?: string
  personality?: string
  costume_hint?: string
  background?: string
  age_range?: string
  tags?: string[]
  portrait_url?: string
  portrait_asset_id?: string
  reference_asset_ids?: string[]
}

export interface CharacterFilterParams {
  keyword?: string
  source_type?: CharacterSourceType
  role?: CharacterRole
  tag?: string
  is_favorite?: boolean
  page?: number
  page_size?: number
}

export interface CharacterListResponse {
  success: boolean
  data: Character[]
  total: number
  page: number
  page_size: number
}
