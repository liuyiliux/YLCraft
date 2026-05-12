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

/**
 * 搜索小说（多书源）
 * 使用新的书源管理API，搜索所有制用书源
 */
export async function searchNovels(
  keyword: string,
  site: string = '',  // 保留参数兼容旧代码，实际使用多书源搜索
  page: number = 1,
  limit: number = 20,
) {
  // 使用新的多书源搜索API
  const res = await request(`/book-sources/search?keyword=${encodeURIComponent(keyword)}`)
  return res.data
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
  return res.data
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
