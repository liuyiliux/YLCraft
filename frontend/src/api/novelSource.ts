/**
 * YLCraft — 小说来源与世界提取 API 调用层
 *
 * 真人与 Agent 走同一套契约：先预览候选与证据，再显式确认写入项目。
 */

const BASE = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json')
    ? await response.json()
    : ((await response.text()) as unknown)
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null ? (body as { detail?: string }).detail : undefined
    throw new Error(detail || `请求失败（${response.status}）`)
  }
  const payload = body as { success?: boolean; data?: T }
  return (payload && payload.data !== undefined ? payload.data : body) as T
}

function jsonRequest<T>(path: string, method: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
}

/** 来源快照。TXT 导入与书架导入共用同一份契约。 */
export interface NovelSourceSnapshot {
  id: string
  title: string
  author: string
  source_kind: 'txt' | 'bookshelf'
  source_status: 'completed' | 'serial' | 'unknown'
  project_id: string | null
  source_asset_id: string | null
  checksum: string
  encoding: string
  revision: number
  chapter_count: number
  char_count: number
  last_chapter_ordinal: number
  indexing_status: string
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export interface NovelSourceChapter {
  id: string
  ordinal: number
  title: string
  start_offset: number
  end_offset: number
  char_count: number
}

export type DomainDetectionStatus =
  | 'detected'
  | 'not_detected'
  | 'uncertain'
  | 'user_requested'

export interface DomainPlanItem {
  domain: string
  label: string
  status: DomainDetectionStatus
  reason: string
  signals: string[]
  estimated_cost: 'low' | 'medium' | 'high'
  basic: boolean
  extractable: boolean
  enabled: boolean
}

export interface DomainPlan {
  snapshot_id: string
  title: string
  provider: string
  model: string
  domains: DomainPlanItem[]
  recommended: string[]
}

export interface DomainRunState extends DomainPlanItem {
  run_state: string
  items: number
  error?: string
}

export interface ExtractResult {
  run_id: string
  snapshot_id: string
  project_id: string | null
  status: 'pending' | 'running' | 'success' | 'partial' | 'failed'
  mode: 'full' | 'delta'
  domains: DomainRunState[]
  candidate_count: number
  /** 增量运行把新证据并回既有候选的数量。 */
  updated_count: number
  from_chunk_ordinal: number
  failures: { domain: string; error: string }[]
  provider: string
  model: string
}

export interface EvidenceAnchor {
  chunk_id: string
  chunk_ordinal: number
  chapter_ordinal: number | null
  start_offset: number
  end_offset: number
  quote: string
}

export interface CandidatePayload {
  summary?: string
  aliases?: string[]
  attributes?: Record<string, unknown>
}

export interface WorldCandidate {
  id: string
  run_id: string
  /** 最近一次产出或更新该候选的运行；增量提取追加证据时回写。 */
  last_run_id: string | null
  snapshot_id: string
  project_id: string | null
  domain: string
  entity_name: string
  payload: CandidatePayload
  evidence: EvidenceAnchor[]
  confidence: number
  origin: 'original' | 'ai_inferred'
  status: 'pending' | 'accepted' | 'ignored' | 'merged'
  target_entity_type: string
  target_entity_id: string | null
  review_note: string
}

export interface DecideResult {
  run_id: string
  accepted: number
  ignored: number
  skipped: number
}

export interface ApplyResult {
  run_id: string
  project_id: string
  characters_written: number
  world_assets_written: number
  world_assets: { id: string; title: string; domain: string }[]
}

export interface DomainCapabilities {
  detectable: string[]
  extractable: string[]
  basic: string[]
}

/** 上传 TXT 生成来源快照。 */
export async function importTxt(
  file: File,
  options: {
    title?: string
    author?: string
    sourceStatus?: string
    projectId?: string
  } = {},
): Promise<NovelSourceSnapshot> {
  const form = new FormData()
  form.append('file', file)
  if (options.title) form.append('title', options.title)
  if (options.author) form.append('author', options.author)
  if (options.sourceStatus) form.append('source_status', options.sourceStatus)
  if (options.projectId) form.append('project_id', options.projectId)
  // 不设置 Content-Type，让浏览器自己带上 multipart boundary。
  return request<NovelSourceSnapshot>('/novel-sources/import-txt', {
    method: 'POST',
    body: form,
  })
}

/** 导入书架选定章节为来源快照。 */
export function importBookshelf(payload: {
  title: string
  author?: string
  source_status?: string
  chapters: { title: string; content: string; chapter_id?: string }[]
}): Promise<NovelSourceSnapshot> {
  return jsonRequest<NovelSourceSnapshot>('/novel-sources/import-bookshelf', 'POST', payload)
}

/** 连载来源追加新章节。 */
export function syncChapters(
  snapshotId: string,
  chapters: { title: string; content: string; chapter_id?: string }[],
): Promise<NovelSourceSnapshot> {
  return jsonRequest<NovelSourceSnapshot>(
    `/novel-sources/${snapshotId}/sync`,
    'POST',
    { chapters },
  )
}

export function listSnapshots(projectId?: string): Promise<NovelSourceSnapshot[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return request<NovelSourceSnapshot[]>(`/novel-sources${query}`)
}

export function getSnapshot(snapshotId: string): Promise<NovelSourceSnapshot> {
  return request<NovelSourceSnapshot>(`/novel-sources/${snapshotId}`)
}

export function listChapters(snapshotId: string): Promise<NovelSourceChapter[]> {
  return request<NovelSourceChapter[]>(`/novel-sources/${snapshotId}/chapters`)
}

export function listDomainCapabilities(): Promise<DomainCapabilities> {
  return request<DomainCapabilities>('/novel-sources/domains')
}

/** 逐模块判断世界设定是否存在。 */
export function planDomains(
  snapshotId: string,
  payload: { provider?: string; model?: string; requested_domains?: string[]; sample_chunks?: number } = {},
): Promise<DomainPlan> {
  return jsonRequest<DomainPlan>(`/novel-sources/${snapshotId}/plan`, 'POST', payload)
}

/** 按模块提取世界候选，只预览不写入。 */
export function extractWorld(
  snapshotId: string,
  payload: {
    domains?: string[]
    domain_plan?: DomainPlanItem[]
    project_id?: string | null
    provider?: string
    model?: string
    mode?: 'full' | 'delta'
    max_chunks?: number
  },
): Promise<ExtractResult> {
  return jsonRequest<ExtractResult>(`/novel-sources/${snapshotId}/extract`, 'POST', payload)
}

export function listCandidates(
  runId: string,
  params: { domain?: string; status?: string } = {},
): Promise<WorldCandidate[]> {
  const search = new URLSearchParams()
  if (params.domain) search.set('domain', params.domain)
  if (params.status) search.set('status', params.status)
  const query = search.toString() ? `?${search.toString()}` : ''
  return request<WorldCandidate[]>(`/world-extraction-runs/${runId}/candidates${query}`)
}

/** 标记候选为接受或忽略，不写项目事实。 */
export function decideCandidates(
  runId: string,
  decisions: { candidate_id: string; action: 'accept' | 'ignore'; note?: string }[],
): Promise<DecideResult> {
  return jsonRequest<DecideResult>(
    `/world-extraction-runs/${runId}/candidates/decide`,
    'POST',
    { decisions },
  )
}

/** 确认写入项目：角色进角色库，其余域进锁定的 world_asset 事实卡。 */
export function applyRun(runId: string, projectId?: string): Promise<ApplyResult> {
  return jsonRequest<ApplyResult>(`/world-extraction-runs/${runId}/apply`, 'POST', {
    project_id: projectId || null,
  })
}

export interface ChunkIndexResult {
  snapshot_id: string
  indexed: number
  failed: number
  total: number
}

export interface ChunkSearchResult {
  chunk_id: string
  chunk_ordinal: number
  chapter_id: string | null
  chapter_ordinal: number | null
  start_offset: number
  end_offset: number
  content: string
  exact_score: number
  vector_score: number
  score: number
  retrieval: 'hybrid' | 'exact'
}

/** 为小说来源文本块建立可选向量索引；失败块保留为 failed，来源仍可走精确检索。 */
export function indexChunks(
  snapshotId: string,
  payload: { provider?: string; max_chunks?: number } = {},
): Promise<ChunkIndexResult> {
  return jsonRequest<ChunkIndexResult>(
    `/novel-sources/${snapshotId}/chunks/index`,
    'POST',
    payload,
  )
}

/** 混合检索小说文本块，返回精确/向量混合召回结果与来源锚点。 */
export function searchChunks(
  snapshotId: string,
  payload: { query: string; query_embedding?: number[]; top_k?: number },
): Promise<ChunkSearchResult[]> {
  return jsonRequest<ChunkSearchResult[]>(
    `/novel-sources/${snapshotId}/chunks/search`,
    'POST',
    payload,
  )
}

export interface ReconcileCandidate {
  id: string
  domain: string
  domain_label: string
  entity_name: string
  summary: string
  aliases: string[]
  confidence: number
  status: string
  origin: string
}

export interface DuplicateGroup {
  kinds: string[]
  reason: string
  candidates: ReconcileCandidate[]
}

export interface EvidenceOverlap {
  chunk_id: string
  start_offset: number
  end_offset: number
  quote: string
  reason: string
  candidates: ReconcileCandidate[]
}

export interface ParsedRelativeTime {
  kind: 'relative' | 'unknown'
  raw: string
  amount?: number
  unit?: string
  direction?: number
  offset_days?: number
  note?: string
}

export interface TimelineEntry {
  candidate_id: string
  entity_name: string
  raw: string
  parsed: ParsedRelativeTime
}

export interface ReconcileReport {
  run_id: string
  snapshot_id: string
  candidate_count: number
  duplicate_groups: DuplicateGroup[]
  evidence_overlaps: EvidenceOverlap[]
  timeline: TimelineEntry[]
  conflict_count: number
}

/** 跨域调和：确定性找出跨模块重名、别名交叉、证据重叠与时序问题。只读，不合并候选。 */
export function reconcileRun(runId: string): Promise<ReconcileReport> {
  return request<ReconcileReport>(`/world-extraction-runs/${runId}/reconcile`)
}

export type ContradictionVerdict = 'consistent' | 'conflicting' | 'distinct'

export interface ContradictionGroup extends DuplicateGroup {
  verdict: ContradictionVerdict
  reason: string
  recommended_action: string
}

export interface ContradictionReport {
  run_id: string
  snapshot_id: string
  groups: ContradictionGroup[]
  conflicting: number
}

/** 对重复组做语义判断：同一实体/矛盾/不同实体。只读提示，不自动合并。 */
export function detectContradictions(
  runId: string,
  payload: { provider?: string; model?: string } = {},
): Promise<ContradictionReport> {
  return jsonRequest<ContradictionReport>(
    `/world-extraction-runs/${runId}/contradictions`,
    'POST',
    payload,
  )
}

export type DerivationKind = 'adaptation' | 'continuation' | 'fan_work'

export interface DeriveResult {
  project_id: string
  derivation_kind: DerivationKind
  source_snapshot_id: string
  source_canon_assets: number
  characters_linked: number
}

/** 从完本来源创建改编/续写/同人派生项目；原作正典复制为只读参考层。 */
export function deriveProject(
  snapshotId: string,
  payload: { derivation_kind: DerivationKind; title?: string; project_type?: string },
): Promise<DeriveResult> {
  return jsonRequest<DeriveResult>(`/novel-sources/${snapshotId}/derive`, 'POST', payload)
}

// ---------------------------------------------------------------------------
// 结构化世界地图
// ---------------------------------------------------------------------------

export interface WorldMapRegion {
  id: string
  name: string
  kind: string
  parent_id?: string | null
  description: string
}

export interface WorldMapNode {
  id: string
  name: string
  kind: string
  x: number
  y: number
  region_id?: string | null
  description: string
}

export interface WorldMapRoute {
  id: string
  name: string
  kind: string
  from: string
  to: string
  description: string
}

export interface WorldMapData {
  regions: WorldMapRegion[]
  nodes: WorldMapNode[]
  routes: WorldMapRoute[]
  /** AI 生图生成的派生视觉资产（只记引用，不是地图正典）。 */
  visuals?: WorldMapVisual[]
}

export interface WorldMapVisual {
  url: string
  local_path: string
  node_id: string
  provider: string
  model: string
  style: string
  prompt: string
  created_at: string
}

export interface WorldMapDocument {
  id: string
  project_id: string | null
  snapshot_id: string | null
  title: string
  map: WorldMapData
  revision: number
  created_at: string | null
  updated_at: string | null
}

export interface WorldMapVisualResult {
  map_id: string
  prompt: string
  url: string
  local_path: string
  node_id: string
  provider: string
  model: string
  task_id: string
  status: string
}

/** 获取一次世界提取运行的完整状态（用于从 run_id 恢复审阅上下文）。 */
export function getExtractionRun(runId: string): Promise<ExtractResult> {
  return request<ExtractResult>(`/world-extraction-runs/${runId}`)
}

/** 从确认写入的地点实体生成地图据点初稿（已有地图时追加，无地图时新建）。 */
export function createWorldMapFromProjectPlaces(projectId: string): Promise<WorldMapDocument> {
  return jsonRequest<WorldMapDocument>(`/projects/${projectId}/world-maps/from-places`, 'POST')
}

export function listWorldMaps(params: { project_id?: string; snapshot_id?: string } = {}): Promise<WorldMapDocument[]> {
  const search = new URLSearchParams()
  if (params.project_id) search.set('project_id', params.project_id)
  if (params.snapshot_id) search.set('snapshot_id', params.snapshot_id)
  const query = search.toString() ? `?${search.toString()}` : ''
  return request<WorldMapDocument[]>(`/world-maps${query}`)
}

export function createWorldMap(payload: {
  title: string
  project_id?: string | null
  snapshot_id?: string | null
  map_json?: WorldMapData
}): Promise<WorldMapDocument> {
  return jsonRequest<WorldMapDocument>('/world-maps', 'POST', payload)
}

export function getWorldMap(mapId: string): Promise<WorldMapDocument> {
  return request<WorldMapDocument>(`/world-maps/${mapId}`)
}

export function updateWorldMap(
  mapId: string,
  payload: { title?: string; map_json: WorldMapData; expected_revision: number },
): Promise<WorldMapDocument> {
  return jsonRequest<WorldMapDocument>(`/world-maps/${mapId}`, 'PUT', payload)
}

export function deleteWorldMap(mapId: string): Promise<{ id: string }> {
  return jsonRequest<{ id: string }>(`/world-maps/${mapId}`, 'DELETE')
}

/** 类型化世界实体：来自 world-extraction 确认写入的实体索引。 */
export interface WorldEntity {
  id: string
  project_id: string | null
  snapshot_id: string | null
  domain: string
  entity_type: string
  name: string
  summary: string
  attributes: Record<string, unknown>
  evidence: { chunk_id?: string; quote?: string; start_offset?: number; end_offset?: number; [k: string]: unknown }[]
  fact_layer: string
  source_candidate_id: string | null
  is_locked: boolean
  updated_at: string | null
}

/** 复杂实体间的类型化关系（不含角色相关，角色关系走 CharacterRelationship）。 */
export interface WorldEntityRelation {
  id: string
  project_id: string
  source_entity_id: string
  target_entity_id: string
  relation_type: string
  note: string
  evidence: { chunk_id?: string; quote?: string; [k: string]: unknown }[]
  is_directed: boolean
  created_at: string | null
}

export function listProjectWorldEntities(
  projectId: string,
  options: { domain?: string; entity_type?: string } = {},
): Promise<WorldEntity[]> {
  const search = new URLSearchParams()
  if (options.domain) search.set('domain', options.domain)
  if (options.entity_type) search.set('entity_type', options.entity_type)
  const query = search.toString() ? `?${search.toString()}` : ''
  return request<WorldEntity[]>(`/projects/${projectId}/world-entities${query}`)
}

export function listProjectWorldEntityRelations(
  projectId: string,
): Promise<WorldEntityRelation[]> {
  return request<WorldEntityRelation[]>(`/projects/${projectId}/world-entity-relations`)
}

/** 项目世界知识聚合视图：角色/实体/关系/事实卡/地图/来源快照一屏返回。 */
export interface WorldKnowledge {
  project_id: string
  title: string
  characters: { character_id: string; name: string; role: string; aliases: string[]; evidence: unknown[]; world_name: string; extract_origin: string }[]
  entities: WorldEntity[]
  relations: {
    source_entity_id: string
    source_name: string
    relation_type: string
    target_entity_id: string
    target_name: string
    note: string
    is_directed: boolean
  }[]
  facts: { id: string; title: string; domain: string; summary: string; is_locked: boolean }[]
  maps: { id: string; title: string; revision: number; node_count: number }[]
  snapshots: { id: string; title: string; source_kind: string; source_status: string; char_count: number; indexing_status: string }[]
  counts: { characters: number; entities: number; relations: number; facts: number; maps: number; snapshots: number }
}

export function getProjectWorldKnowledge(projectId: string): Promise<WorldKnowledge> {
  return request<WorldKnowledge>(`/creative-projects/${projectId}/world-knowledge`)
}

/** 从已导入的来源快照创建并绑定世界项目（design API from-novel-source）。 */
export function createProjectFromNovelSource(payload: {
  snapshot_id: string
  title?: string
  project_type?: string
}): Promise<{ project_id: string; reused: boolean }> {
  return jsonRequest('/creative-projects/from-novel-source', 'POST', payload)
}

/** 从创作项目大纲启动逐域世界提取，产出待确认候选。 */
export function startProjectWorldExtraction(
  projectId: string,
  payload: {
    provider?: string
    model?: string
    domains?: string[]
    force_reimport?: boolean
  } = {},
): Promise<{
  project_id: string
  snapshot_id: string
  run_id: string
  candidate_count: number
  status: string
}> {
  return jsonRequest(`/creative-projects/${projectId}/world-extraction/start`, 'POST', payload)
}

/** 地图 AI 生图：先预览提示词，不消耗生图配额。 */
export function previewWorldMapVisualPrompt(
  mapId: string,
  payload: { style_override?: string; prompt_override?: string } = {},
): Promise<{ map_id: string; prompt: string }> {
  return jsonRequest(`/world-maps/${mapId}/generate-visual/prompt-preview`, 'POST', payload)
}

/** 地图 AI 生图：生成视觉成图并（默认）入资产中枢。 */
export function generateWorldMapVisual(
  mapId: string,
  payload: {
    prompt?: string
    negative_prompt?: string
    provider?: string
    model?: string
    size?: string
    n?: number
    style?: string
    reference_images?: string[]
    save_to_asset_hub?: boolean
  },
): Promise<WorldMapVisualResult> {
  return jsonRequest(`/world-maps/${mapId}/generate-visual`, 'POST', payload)
}

/** 可用的图像生成后端（对齐角色立绘：name 作为 provider，available_models 供选模型）。 */
export interface WorldMapImageBackend {
  provider: string
  provider_label: string
  name: string
  model: string
  available_models: string[]
  capabilities: string[]
  support_reference_image: boolean
  supported_sizes: string[]
}

export async function listWorldMapImageBackends(): Promise<WorldMapImageBackend[]> {
  const response = await fetch(`${BASE}/images/backends`, {
    headers: { Accept: 'application/json' },
  })
  const body = await response.json()
  if (!response.ok) {
    throw new Error((body as { detail?: string }).detail || `请求失败（${response.status}）`)
  }
  return (body as { backends?: WorldMapImageBackend[] }).backends ?? []
}
