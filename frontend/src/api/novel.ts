/**
 * YLCraft — 小说 API 调用层
 */

const BASE = '/api/v1'

function request(path: string, init?: RequestInit) {
  return fetch(`${BASE}${path}`, {
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  }).then(async r => {
    const ct = r.headers.get('content-type') || ''
    if (ct.includes('application/json')) return r.json()
    return r.text()
  })
}

export interface NovelSearchResult {
  title: string
  author: string
  url: string
  cover: string
  source_site: string
  source_id?: string
}

export interface Chapter {
  index: number
  title: string
  url: string
}

export interface NovelSource {
  id: string
  name: string
  enabled: boolean
}

/** 书架中的书籍详情（含 metadata 展开字段） */
export interface BookshelfItem {
  id: string
  title: string
  author: string
  cover_url: string
  status: string
  novel_title?: string
  book_url?: string
  toc_url?: string
  source_id?: string
  source_name?: string
  source_url?: string
  chapters?: Chapter[]
  chapter_count?: number
  downloaded_chapter_indices?: number[]
  last_read_chapter?: number
  last_read_position?: number
  intro?: string
  kind?: string
  content_path?: string
  created_at?: string
  /** 多源目录：key 为 source_id，value 包含该书源的章节列表 */
  catalogs?: Record<string, {
    chapters: Chapter[]
    chapter_count: number
    source_name: string
    source_url: string
    toc_url: string
  }>
}

/**
 * 搜索小说（SSE 流式，每个书源完成即推送结果）
 * @param onResults 收到新结果的回调
 * @onFinish 全部完成的回调
 * @onError 错误回调
 */
export function searchNovelsStream(
  keyword: string,
  options?: {
    onResults?: (data: any[]) => void
    onFinish?: (total: number, allData: any[]) => void
    onError?: (err: Error) => void
  },
): AbortController {
  const controller = new AbortController()
  const url = `/api/v1/book-sources/search?keyword=${encodeURIComponent(keyword)}`

  fetch(url, { signal: controller.signal })
    .then(async (response) => {
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let allData: any[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // 解析 SSE 数据（每条以 \n\n 分隔）
        const events = buffer.split('\n\n')
        buffer = events.pop() || '' // 最后一个可能不完整

        for (const event of events) {
          const line = event.replace(/^data:\s*/, '').trim()
          if (!line) continue
          try {
            const msg = JSON.parse(line)
            if (msg.type === 'results' && msg.data && msg.data.length > 0) {
              allData = allData.concat(msg.data)
              options?.onResults?.(allData)
            }
            if (msg.type === 'finish') {
              allData = msg.data || allData
              options?.onFinish?.(msg.total || allData.length, allData)
              return
            }
          } catch (e) {
            console.warn('SSE parse error:', e, line)
          }
        }
      }
    })
    .catch((err) => {
      if ((err as Error).name !== 'AbortError') {
        options?.onError?.(err as Error)
      }
    })

  return controller
}

/**
 * 搜索小说（兼容旧接口）
 */
export async function searchNovels(
  keyword: string,
  site: string = '',
  page: number = 1,
  limit: number = 20,
): Promise<any> {
  return new Promise((resolve, reject) => {
    searchNovelsStream(keyword, {
      onResults: () => {}, // 流式过程中不 resolve
      onFinish: (_total, data) => resolve({ success: true, data, total: _total }),
      onError: reject,
    })
  })
}

/**
 * 获取小说目录
 */
export async function getNovelCatalog(
  url: string,
  site: string = 'biqigecn',
) {
  const sp = new URLSearchParams()
  sp.set('url', url)
  sp.set('site', site)
  const res = await request(`/novels/catalog?${sp}`)
  // 返回完整响应对象，包含 success 和 data 字段
  return res
}

/**
 * 下载指定章节
 */
export async function downloadChapters(data: {
  book_url: string
  book_title: string
  author: string
  chapters: Chapter[]
  site?: string
}) {
  const res = await request('/novels/download-chapters', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res.data
}

/**
 * 获取可用书源列表
 */
export async function getNovelSources(): Promise<NovelSource[]> {
  const res = await request('/novels/sources')
  if (res.success) return res.data || []
  return []
}

/**
 * 从指定书源获取目录（换源时动态加载）
 */
export async function fetchSourceCatalog(bookUrl: string, sourceId: string, bookTitle?: string): Promise<{
  success: boolean
  data?: {
    source_id: string
    source_name: string
    catalog_url: string
    chapters: Chapter[]
  }
}> {
  const sp = new URLSearchParams()
  sp.set('book_url', bookUrl)
  sp.set('source_id', sourceId)
  if (bookTitle) {
    sp.set('book_title', bookTitle)
  }
  return request(`/novels/source-catalog?${sp}`)
}

/**
 * 加入书架（仅保存元信息，不下载内容）
 * 参考 Legado: Book 实体保存书籍信息+章节列表，阅读时在线获取
 */
export async function addToBookshelf(data: {
  book_url: string
  book_title: string
  author?: string
  cover_url?: string
  intro?: string
  kind?: string
  toc_url?: string
  source_id?: string
  source_name?: string
  source_url?: string
  chapters?: Chapter[]
  sources?: Array<{ id?: string; name?: string; url?: string; book_url?: string }>
}): Promise<{ success: boolean; message: string; asset_id?: string }> {
  return request('/novels/add-to-bookshelf', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/**
 * 在线获取章节正文（从网络抓取）
 * 用于阅读器在线模式，不依赖本地文件
 */
export async function getChapterContent(params: {
  chapter_url: string
  source_id?: string
  book_url?: string
}): Promise<{ success: boolean; data?: { content: string; source_name: string } }> {
  const sp = new URLSearchParams()
  sp.set('chapter_url', params.chapter_url)
  if (params.source_id) sp.set('source_id', params.source_id)
  if (params.book_url) sp.set('book_url', params.book_url)
  return request(`/novels/chapter-content?${sp}`)
}

/**
 * 获取书架中的书籍详情（含章节列表、书源信息等）
 */
export async function getBookshelfItem(assetId: string): Promise<{ success: boolean; data?: BookshelfItem }> {
  return request(`/novels/bookshelf-item/${assetId}`)
}
