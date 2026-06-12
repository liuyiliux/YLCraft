/**
 * 书源管理 API
 * 兼容阅读App格式
 */

const BASE = '/api/v1'

function request(path: string, init?: RequestInit) {
  return fetch(`${BASE}${path}`, {
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  }).then(async r => {
    const ct = r.headers.get('content-type') || ''
    const payload = ct.includes('application/json') ? await r.json() : await r.text()
    if (!r.ok) {
      const detail = typeof payload === 'object' && payload ? (payload.detail || payload.error) : payload
      throw new Error(detail || `HTTP ${r.status}`)
    }
    return payload
  })
}

export interface BookSource {
  id: string
  book_source_name: string
  book_source_url: string
  book_source_type: number
  enabled: boolean
  book_source_group?: string
  enabled_by_user: boolean
  is_js_source: boolean
  rule_format?: string
  rule_version?: string
  created_at?: string
}

export interface BookSourceImportResponse {
  success: boolean
  added: number
  updated: number
  total: number
  failed?: number
  error?: string
}

export interface BookSourceTestResult {
  success: boolean
  data?: {
    url: string
    request_info?: any
    status_code: number
    headers: Record<string, string>
    response_time_ms: number
    raw_html: string
    raw_html_truncated: boolean
    parsed_result: any
    browser_cookie?: {
      domain: string
      cookie_count: number
      cookie_content: string
      source_domains?: string[]
    } | null
    browser_request_headers?: Record<string, string> | null
    diagnostics?: Array<{
      type: string
      message: string
      suggestion?: string
    }>
    debug_info: {
      cookie_used: boolean
      cookie_match?: any
      rule_type: 'search' | 'toc' | 'content'
      rule_format?: 'legado' | 'ylcraft'
      fetch_mode?: 'http' | 'browser' | 'visible_browser'
      rule_used?: any
      rule_trace?: Array<{
        name: string
        rule: any
        matches: number
        sample?: string
      }>
      matched_elements?: number
      parse_time_ms?: number
      diagnostics?: Array<{
        type: string
        message: string
        suggestion?: string
      }>
    }
  }
  detail?: string
}

export interface BookSourceRules {
  id: string
  book_source_name: string
  book_source_url: string
  rule_format: string
  rule_version?: string
  original_format?: string
  migration_log?: string
  legado: {
    bookSourceName: string
    bookSourceUrl: string
    searchUrl?: string
    ruleSearch?: Record<string, any>
    ruleBookInfo?: Record<string, any>
    ruleToc?: Record<string, any>
    ruleContent?: Record<string, any>
    ruleExplore?: Record<string, any>
  }
  ylcraft: Record<string, any>
}

export interface BookSourceRulesPayload {
  search_url?: string
  rule_search?: Record<string, any>
  rule_book_info?: Record<string, any>
  rule_toc?: Record<string, any>
  rule_content?: Record<string, any>
  rule_explore?: Record<string, any>
  ylcraft_rule?: Record<string, any>
  save_format?: 'legado' | 'ylcraft'
}

export interface BookSourceCookie {
  id: string
  book_source_id: string
  domain: string
  description: string
  is_active: boolean
  expires_at?: string | null
  cookie_count: number
  created_at?: string
  updated_at?: string
}

export interface BookSourceCookiePayload {
  domain: string
  cookie_content?: string
  description?: string
  is_active?: boolean
  expires_at?: string | null
}

/**
 * 获取书源列表
 */
export async function getBookSources(enabledOnly: boolean = true): Promise<BookSource[]> {
  const res = await request(`/book-sources?enabled_only=${enabledOnly}`)
  return res.data || []
}

/**
 * 导入书源JSON文件
 */
export async function importBookSources(file: File): Promise<BookSourceImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  
  return fetch(`${BASE}/book-sources/import`, {
    method: 'POST',
    body: formData,
  }).then(r => r.json())
}

/**
 * 导入书源JSON字符串
 */
export async function importBookSourcesJson(json: string): Promise<BookSourceImportResponse> {
  return request('/book-sources/import-json', {
    method: 'POST',
    body: JSON.stringify({ json }),
  })
}

/**
 * 切换书源启用状态
 */
export async function toggleBookSource(sourceId: string, enabled: boolean): Promise<void> {
  return request(`/book-sources/${sourceId}/toggle?enabled=${enabled}`, {
    method: 'PUT',
  })
}

/**
 * 批量切换书源启用状态
 */
export async function batchToggleBookSources(sourceIds: string[], enabled: boolean): Promise<any> {
  return request('/book-sources/batch-toggle', {
    method: 'POST',
    body: JSON.stringify({ ids: sourceIds, enabled }),
  })
}

/**
 * 删除书源
 */
export async function deleteBookSource(sourceId: string): Promise<void> {
  return request(`/book-sources/${sourceId}`, {
    method: 'DELETE',
  })
}

/**
 * 批量删除书源
 */
export async function batchDeleteBookSources(sourceIds: string[]): Promise<any> {
  return request('/book-sources/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids: sourceIds }),
  })
}

/**
 * 导出书源
 */
export async function exportBookSources(): Promise<void> {
  const url = `${BASE}/book-sources/export`
  const a = document.createElement('a')
  a.href = url
  a.download = 'book_sources.json'
  a.click()
}

export async function getBookSourceRules(sourceId: string): Promise<BookSourceRules> {
  const res = await request(`/book-sources/${sourceId}/rules`)
  return res.data
}

export async function updateBookSourceRules(
  sourceId: string,
  payload: BookSourceRulesPayload,
): Promise<BookSourceRules> {
  const res = await request(`/book-sources/${sourceId}/rules`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return res.data
}

export async function updateBookSourceHeaders(
  sourceId: string,
  headers: Record<string, string>,
): Promise<Record<string, string>> {
  const res = await request(`/book-sources/${sourceId}/headers`, {
    method: 'PUT',
    body: JSON.stringify({ headers }),
  })
  return res.data?.headers || {}
}

export async function convertBookSourceRules(
  direction: 'legado_to_ylcraft' | 'ylcraft_to_legado',
  source: Record<string, any>,
): Promise<Record<string, any>> {
  const res = await request('/book-sources/rules/convert', {
    method: 'POST',
    body: JSON.stringify({ direction, source }),
  })
  return res.data
}

export async function getBookSourceCookies(sourceId: string): Promise<BookSourceCookie[]> {
  const res = await request(`/book-sources/${sourceId}/cookies`)
  return res.data || []
}

export async function createBookSourceCookie(
  sourceId: string,
  payload: BookSourceCookiePayload,
): Promise<BookSourceCookie> {
  const res = await request(`/book-sources/${sourceId}/cookies`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return res.data
}

export async function updateBookSourceCookie(
  sourceId: string,
  cookieId: string,
  payload: Partial<BookSourceCookiePayload>,
): Promise<BookSourceCookie> {
  const res = await request(`/book-sources/${sourceId}/cookies/${cookieId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return res.data
}

export async function deleteBookSourceCookie(sourceId: string, cookieId: string): Promise<void> {
  await request(`/book-sources/${sourceId}/cookies/${cookieId}`, {
    method: 'DELETE',
  })
}

/**
 * 在所有制用书源中搜索小说
 */
export async function searchBooks(keyword: string): Promise<any[]> {
  const res = await request(`/book-sources/search?keyword=${encodeURIComponent(keyword)}`)
  return res.data || []
}

export interface BookSourceTestParams {
  url?: string
  keyword?: string
  page?: number
  rule_type?: 'search' | 'toc' | 'content'
  show_raw?: boolean
  rule_format?: 'legado' | 'ylcraft'
  fetch_mode?: 'http' | 'browser'
  headers?: Record<string, string>
  rules?: BookSourceRulesPayload
}

export interface RuleAssistantPatch {
  target: string
  format: 'legado' | 'ylcraft'
  mode?: 'merge' | 'replace'
  value: any
  reason?: string
  confidence?: number
  risks?: string[]
  validation?: Record<string, any>
}

export interface RuleAssistantSuggestion {
  success: boolean
  plugin?: string
  summary?: string
  patches?: RuleAssistantPatch[]
  selector_candidates?: Array<Record<string, any>>
  test_plan?: string[]
  warnings?: string[]
  usage?: Record<string, any>
  provider?: string
  model?: string
  raw_response?: string
  error?: string
}

export interface RuleAssistantSuggestPayload {
  domain: 'book_source'
  rule_type: 'search' | 'toc' | 'content'
  rule_format: 'legado' | 'ylcraft'
  current_rules: BookSourceRulesPayload
  source_id: string
  source_name: string
  source_url: string
  target_url?: string
  test_result?: Record<string, any>
  provider?: string
  model?: string
}

export interface LlmBackendInfo {
  name: string
  provider: string
  provider_label?: string
  model: string
  available_models?: string[]
  support_vision_input?: boolean
}

export async function getBookSourceLlmBackends(): Promise<LlmBackendInfo[]> {
  const res = await request('/llm/backends')
  return res.backends || []
}

export interface BookSourceBrowserSession {
  success: boolean
  data: {
    session_id: string
    url: string
    status_code: number
    headers: Record<string, string>
    request_info?: any
  }
  detail?: string
}

/**
 * 测试单个书源规则
 */
export async function testBookSource(
  sourceId: string,
  params: BookSourceTestParams,
): Promise<BookSourceTestResult> {
  return request(`/book-sources/${sourceId}/test`, {
    method: 'POST',
    body: JSON.stringify({
      ...params,
      page: params.page || 1,
      show_raw: params.show_raw ?? true,
      rule_format: params.rule_format || 'legado',
      fetch_mode: params.fetch_mode || 'http',
    }),
  })
}

export async function suggestBookSourceRule(
  payload: RuleAssistantSuggestPayload,
): Promise<RuleAssistantSuggestion> {
  const res = await request('/rule-assistant/suggest', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return res.data
}

export async function startBookSourceBrowserSession(
  sourceId: string,
  params: BookSourceTestParams,
): Promise<BookSourceBrowserSession> {
  return request(`/book-sources/${sourceId}/browser-session/start`, {
    method: 'POST',
    body: JSON.stringify({
      ...params,
      page: params.page || 1,
      show_raw: params.show_raw ?? true,
      rule_format: params.rule_format || 'legado',
      fetch_mode: 'browser',
    }),
  })
}

export async function snapshotBookSourceBrowserSession(
  sessionId: string,
  showRaw: boolean = true,
): Promise<BookSourceTestResult> {
  return request(`/book-sources/browser-sessions/${sessionId}/snapshot`, {
    method: 'POST',
    body: JSON.stringify({ show_raw: showRaw }),
  })
}

export async function closeBookSourceBrowserSession(sessionId: string): Promise<void> {
  await request(`/book-sources/browser-sessions/${sessionId}`, {
    method: 'DELETE',
  })
}
