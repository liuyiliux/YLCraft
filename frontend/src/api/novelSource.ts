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

/**
 * 区域几何：形状是区域的**独立几何**，不再由成员据点围合推导。
 * - auto：由「成员据点 + 语义参数 + seed」确定性展开，可重放；
 * - manual：顶点被手绘编辑后固化，重新生成会覆盖（需确认）。
 */
export interface WorldMapRegionShape {
  mode: 'auto' | 'manual'
  seed: number
  params: {
    nature?: string
    settlement?: string
    structure?: string
    scale?: '小' | '中' | '大'
    irregularity?: number
  }
  /** 顶点 [y, x]（与渲染端 Leaflet 一致），上限 64，闭合由渲染端处理。 */
  vertices: [number, number][]
}

export interface WorldMapRegion {
  id: string
  name: string
  kind: string
  /** 父区域（不限层嵌套），null/空为顶层。 */
  parent_id?: string | null
  description: string
  /** 区域几何；缺失或 vertices 为空表示尚未生成（渲染端按 seed 派生临时形状）。 */
  shape?: WorldMapRegionShape | null
}

/** 空间层（位面）：由项目/世界观自定义（名称与数量不写死）；缺省时视为单层地图。 */
export interface WorldMapLayer {
  id: string
  name: string
}

export interface WorldMapNode {
  id: string
  name: string
  kind: string
  x: number
  y: number
  region_id?: string | null
  description: string
  /** 引用的地点实体 id：正典在 world_entities，地图只存指针（引用不复制）。 */
  entity_id?: string | null
  /** 所属空间层 id（引用 map_json.layers，为空即未分层）。 */
  layer?: string | null
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
  /** 空间层定义（数据驱动，不写死）；缺省或为空时为单层地图。 */
  layers?: WorldMapLayer[]
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

/** 证据锚点：逐字原文 + 章节/块定位（实体与关系共用形状）。 */
export interface WorldMapEvidence {
  chunk_id?: string
  quote?: string
  [k: string]: unknown
}

/** 据点 → 实体解析结果：引用不复制，实体信息按需回查。 */
export interface WorldMapNodeEntity {
  node: WorldMapNode
  entity_id: string | null
  entity: {
    id: string
    name: string
    domain: string
    entity_type: string
    summary: string
    attributes: Record<string, unknown>
    evidence: WorldMapEvidence[]
    fact_layer: string
    is_locked: boolean
  } | null
  relations: {
    id: string
    source_entity_id: string
    target_entity_id: string
    relation_type: string
    note: string
    evidence: WorldMapEvidence[]
    is_directed: boolean
  }[]
}

export interface WorldMapEntitiesResult {
  map_id: string
  title: string
  revision: number
  nodes: WorldMapNodeEntity[]
  /** 游离标记：没有关联实体（或实体已不存在）的据点 id，UI 应提示去关联。 */
  orphan_node_ids: string[]
}

/** 结构化点位导出：空间关系 + 实体引用 + 证据锚点，不是图片。 */
export interface WorldMapExportResult {
  map: { map_id: string; title: string; revision: number }
  nodes: (WorldMapNode & {
    entity_id: string | null
    evidence: WorldMapEvidence[]
    confidence: unknown
    relations: WorldMapNodeEntity['relations']
  })[]
  regions: WorldMapRegion[]
  routes: WorldMapRoute[]
  notes: string[]
}

/** 项目世界模块（内置 + 项目扩展的属性契约）。 */
export interface WorldDomainSpec {
  key: string
  label: string
  entity_type: string
  attributes: string[]
  builtin_attributes: string[]
  is_builtin: boolean
  is_enabled: boolean
  source: string
  prompt_hint: string
}

export interface WorldDomainsResult {
  domains: WorldDomainSpec[]
}

/** 写入项目级模块定义的结果。 */
export interface WorldDomainDefinition {
  key: string
  label: string
  entity_type: string
  extra_attributes: string[]
  prompt_hint: string
  is_enabled: boolean
  source: string
}

/** 列出项目世界模块（含属性契约），用于「补充哪些字段」。 */
export function listProjectWorldDomains(projectId: string): Promise<WorldDomainsResult> {
  return request<WorldDomainsResult>(`/projects/${projectId}/world-domains`)
}

/** 世界构建模板：层次策略 + 每档提示词（名称与层数由数据决定）。 */
export interface WorldBuildingTemplate {
  id: string
  name: string
  layers: string[]
  prompts: Record<string, string>
  is_default: boolean
  is_builtin: boolean
}

export function listWorldTemplates(
  projectId: string,
): Promise<{ templates: WorldBuildingTemplate[] }> {
  return request<{ templates: WorldBuildingTemplate[] }>(`/projects/${projectId}/world-templates`)
}

export function upsertWorldTemplate(
  projectId: string,
  payload: {
    template_id?: string
    name?: string
    layers?: string[]
    prompts?: Record<string, string>
    is_default?: boolean
  },
): Promise<WorldBuildingTemplate> {
  return jsonRequest<WorldBuildingTemplate>(
    `/projects/${projectId}/world-templates`,
    'POST',
    payload,
  )
}

export function deleteWorldTemplate(
  projectId: string,
  templateId: string,
): Promise<{ project_id: string; template_id: string }> {
  return jsonRequest(`/projects/${projectId}/world-templates/${templateId}`, 'DELETE')
}

/** AI 起草的模板草案（只回显、不落库，确认后走 upsertWorldTemplate 保存）。 */
export interface WorldTemplateDraft {
  name: string
  layers: string[]
  prompts: Record<string, string>
  note?: string
}

export function draftWorldTemplate(
  projectId: string,
  payload: { domain?: string; hint?: string },
): Promise<WorldTemplateDraft> {
  return jsonRequest<WorldTemplateDraft>(
    `/projects/${projectId}/world-templates/draft`,
    'POST',
    payload,
  )
}

/** 域级细化提交结果（异步：返回 task_id，用既有任务中心轮询）。 */
export interface WorldDomainExpansionTask {
  task_id: string
  status: string
  domain: string
  poll: string
}

export function expandWorldDomain(
  projectId: string,
  payload: {
    domain: string
    hint?: string
    template_id?: string
    prompt_override?: string
    limit?: number
    provider?: string
    model?: string
  },
): Promise<WorldDomainExpansionTask> {
  return jsonRequest<WorldDomainExpansionTask>(
    `/projects/${projectId}/world-generation/expand-domain`,
    'POST',
    payload,
  )
}

/** 待确认的 AI 结构建议（模块级 + 字段级）：不会自动成为 schema。 */
export interface WorldBuildingSuggestions {
  domains: { key: string; label: string; attributes: string[]; reason: string; state: string }[]
  fields: { domain: string; domain_label: string; field: string; reason: string; state: string }[]
}

export function listWorldBuildingSuggestions(projectId: string): Promise<WorldBuildingSuggestions> {
  return request<WorldBuildingSuggestions>(`/projects/${projectId}/world-generation/suggestions`)
}

/** 确认字段建议：写入该模块的属性契约。 */
export function confirmSuggestedField(
  projectId: string,
  payload: { domain: string; field: string },
): Promise<{ domain: string; field: string; state: string }> {
  return jsonRequest(
    `/projects/${projectId}/world-generation/suggestions/fields/confirm`,
    'POST',
    payload,
  )
}

/** 忽略字段建议：不再重复提示。 */
export function ignoreSuggestedField(
  projectId: string,
  payload: { domain: string; field: string },
): Promise<{ domain: string; field: string; state: string }> {
  return jsonRequest(
    `/projects/${projectId}/world-generation/suggestions/fields/ignore`,
    'POST',
    payload,
  )
}

/** 确认模块建议（转 custom 并启用）或覆盖内置模块。 */
export function upsertProjectWorldDomain(
  projectId: string,
  domainKey: string,
  payload: {
    label?: string
    entity_type?: string
    extra_attributes?: string[]
    prompt_hint?: string
    is_enabled?: boolean
    source?: string
  },
): Promise<WorldDomainDefinition> {
  return jsonRequest<WorldDomainDefinition>(
    `/projects/${projectId}/world-domains/${domainKey}`,
    'PUT',
    payload,
  )
}

/** 忽略模块建议：移除建议（内置模块则恢复默认）。 */
export function resetProjectWorldDomain(
  projectId: string,
  domainKey: string,
): Promise<{ project_id: string; domain_key: string }> {
  return jsonRequest(`/projects/${projectId}/world-domains/${domainKey}`, 'DELETE')
}

/** AI 补充实体属性的预览（只返回提示词，不调用模型）。 */
export interface EntityExpansionPreview {
  entity_id: string
  entity: string
  domain: string
  fields: string[]
  prompt: string
}

export function previewEntityExpansion(
  projectId: string,
  payload: { entity_id: string; fields: string[]; template_id?: string; prompt_override?: string },
): Promise<EntityExpansionPreview> {
  return jsonRequest<EntityExpansionPreview>(
    `/projects/${projectId}/world-generation/expand-entity/preview`,
    'POST',
    payload,
  )
}

/** AI 补充实体属性的结果（产出 ai_draft 候选，需审阅确认后写入）。 */
export interface EntityExpansionResult {
  run_id: string
  candidate_id: string
  entity_id: string
  entity: string
  domain: string
  fields: string[]
  values: Record<string, unknown>
  origin: string
  suggested_fields: { domain: string; field: string; reason: string }[]
  suggested_domains: { key: string; label: string; attributes: string[]; state: string }[]
}

export function expandEntityAttributes(
  projectId: string,
  payload: {
    entity_id: string
    fields: string[]
    template_id?: string
    prompt_override?: string
    provider?: string
    model?: string
  },
): Promise<EntityExpansionResult> {
  return jsonRequest<EntityExpansionResult>(
    `/projects/${projectId}/world-generation/expand-entity`,
    'POST',
    payload,
  )
}

/** 解析地图据点关联的实体、证据与关系（游离标记以 orphan_node_ids 标出）。 */
export function resolveWorldMapEntities(mapId: string): Promise<WorldMapEntitiesResult> {
  return request<WorldMapEntitiesResult>(`/world-maps/${mapId}/entities`)
}

/** 导出结构化点位 JSON（含 entity_id / evidence；confidence 待实体层补字段）。 */
export function exportWorldMapPoints(mapId: string): Promise<WorldMapExportResult> {
  return request<WorldMapExportResult>(`/world-maps/${mapId}/export?format=json`)
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
    reference_asset_ids?: string[]
    reference_images?: string[]
    save_to_asset_hub?: boolean
  },
): Promise<WorldMapVisualResult> {
  return jsonRequest(`/world-maps/${mapId}/generate-visual`, 'POST', payload)
}

/** 地图 AI 生图：用 LLM 优化提示词（只改写提示词、不生成图，需预览确认后再生图）。 */
export function optimizeWorldMapVisualPrompt(
  mapId: string,
  payload: {
    prompt?: string
    style?: string
    focus?: string
    provider?: string
    model?: string
  } = {},
): Promise<{ map_id: string; prompt: string; optimized_prompt: string }> {
  return jsonRequest(
    `/world-maps/${mapId}/generate-visual/prompt-optimize`,
    'POST',
    payload,
  )
}

/** 地图版本历史（SCN-05）：每次保存落 append-only 快照，回滚产生新 revision。 */
export interface WorldMapRevisionItem {
  id: string
  map_id: string
  revision: number
  title: string
  operator: string
  summary: string
  created_at: string | null
  map_json?: WorldMapData
}

export function listWorldMapRevisions(
  mapId: string,
): Promise<{ map_id: string; current_revision: number; revisions: WorldMapRevisionItem[] }> {
  return request(`/world-maps/${mapId}/revisions`)
}

export function getWorldMapRevision(
  mapId: string,
  revision: number,
): Promise<WorldMapRevisionItem> {
  return request(`/world-maps/${mapId}/revisions/${revision}`)
}

export function rollbackWorldMap(
  mapId: string,
  payload: { revision: number; operator?: string },
): Promise<WorldMapDocument> {
  return jsonRequest(`/world-maps/${mapId}/rollback`, 'POST', payload)
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
