import type { CanvasNode } from './types'

export const CANVAS_DOCUMENTS_STORAGE_KEY = 'ylcraft-canvas-documents-v1'
export const CANVAS_IMPORT_QUEUE_STORAGE_KEY = 'ylcraft-canvas-import-queue-v1'
export const CANVAS_IMAGE_EDITOR_LAUNCH_STORAGE_KEY = 'ylcraft-canvas-image-editor-launch-v1'
export const CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY = 'ylcraft-canvas-image-editor-result-v1'

export type CanvasImageEditorLaunch = {
  documentId: string
  sourceNodeId: string
  sourceAssetId?: string
  sourceTitle: string
  imageUrl: string
  createdAt: string
}

export type CanvasImageEditorResult = {
  documentId: string
  sourceNodeId: string
  sourceAssetId?: string
  sourceTitle: string
  imageDataUrl: string
  width?: number
  height?: number
  createdAt: string
}

export type CanvasImportItem = {
  id: string
  projectId?: string
  sourceNodeId?: string
  createdAt: string
  node: CanvasNode
}

function readQueue(): CanvasImportItem[] {
  try {
    const raw = localStorage.getItem(CANVAS_IMPORT_QUEUE_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((item) => item?.node?.id) : []
  } catch {
    return []
  }
}

export function enqueueCanvasImport(items: CanvasImportItem[]) {
  if (!items.length) return
  const queue = [...readQueue(), ...items]
  localStorage.setItem(CANVAS_IMPORT_QUEUE_STORAGE_KEY, JSON.stringify(queue))
}

export function consumeCanvasImportQueue(): CanvasImportItem[] {
  const queue = readQueue()
  localStorage.removeItem(CANVAS_IMPORT_QUEUE_STORAGE_KEY)
  return queue
}


export function launchCanvasImageEditor(item: CanvasImageEditorLaunch) {
  localStorage.setItem(CANVAS_IMAGE_EDITOR_LAUNCH_STORAGE_KEY, JSON.stringify(item))
}

export function consumeCanvasImageEditorLaunch(): CanvasImageEditorLaunch | null {
  try {
    const raw = localStorage.getItem(CANVAS_IMAGE_EDITOR_LAUNCH_STORAGE_KEY)
    localStorage.removeItem(CANVAS_IMAGE_EDITOR_LAUNCH_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed?.imageUrl && parsed?.documentId && parsed?.sourceNodeId ? parsed : null
  } catch {
    return null
  }
}

export function enqueueCanvasImageEditorResult(item: CanvasImageEditorResult) {
  try {
    const raw = localStorage.getItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY)
    const queue = raw ? JSON.parse(raw) : []
    const next = Array.isArray(queue) ? queue : []
    next.push(item)
    localStorage.setItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY, JSON.stringify(next))
  } catch {
    localStorage.setItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY, JSON.stringify([item]))
  }
}

export function consumeCanvasImageEditorResults(): CanvasImageEditorResult[] {
  const raw = localStorage.getItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY)
  localStorage.removeItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY)
  const parsed = raw ? JSON.parse(raw) : []
  return Array.isArray(parsed) ? parsed.filter((item) => item?.imageDataUrl && item?.documentId && item?.sourceNodeId) : []
}

// ---------------------------------------------------------------------------
// 通用「送进图片编辑器」桥
// ---------------------------------------------------------------------------

/**
 * 通用启动参数。
 *
 * **为什么不复用画布那条**：`CanvasImageEditorLaunch` 的 `documentId` /
 * `sourceNodeId` 是**必填**（consume 时会校验），而且返回值写死了跳 `/canvas`。
 * 动图切帧要用同一个编辑器，但既没有画布文档、也不知道该跳哪 —— 复用会逼着
 * 造假字段，还会把用户送到错的页面。**宁可加一条独立的桥**。
 *
 * 走 localStorage 而不是 URL query：图片 URL 可能很长（含签名），
 * query 会被浏览器/网关截断；localStorage 没有长度焦虑，且同页跳转更可靠。
 */
export const IMAGE_EDITOR_LAUNCH_STORAGE_KEY = 'ylcraft-image-editor-launch-v1'
/**
 * 通用结果**单独一个 key**，不与画布共用。
 *
 * 共用会出事：`consumeCanvasImageEditorResults` 是"先删 key 再过滤"，
 * 画布页只要调一次就把整批清空了，通用那几条**被连带丢掉**，
 * 表现为"编辑完回来图没了"。两个消费者各写各的 key，互不干涉。
 */
export const IMAGE_EDITOR_RESULT_STORAGE_KEY = 'ylcraft-image-editor-result-v1'

export type ImageEditorLaunch = {
  imageUrl: string
  /** 完成后回到哪一页（如 `/image-gen`）。留空则编辑器不显示"返回"按钮。 */
  returnTo?: string
  /** 只用于编辑器里的提示文案。 */
  sourceTitle?: string
  /** 回传结果里带回去的自定义数据（调用方靠它认领自己的结果）。 */
  payload?: Record<string, unknown>
  createdAt: string
}

export type ImageEditorResult = {
  imageDataUrl: string
  width?: number
  height?: number
  payload?: Record<string, unknown>
  createdAt: string
}

export function launchImageEditor(item: ImageEditorLaunch) {
  localStorage.setItem(IMAGE_EDITOR_LAUNCH_STORAGE_KEY, JSON.stringify(item))
}

export function consumeImageEditorLaunch(): ImageEditorLaunch | null {
  try {
    const raw = localStorage.getItem(IMAGE_EDITOR_LAUNCH_STORAGE_KEY)
    localStorage.removeItem(IMAGE_EDITOR_LAUNCH_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed?.imageUrl ? parsed : null
  } catch {
    return null
  }
}

export function enqueueImageEditorResult(item: ImageEditorResult) {
  try {
    const raw = localStorage.getItem(IMAGE_EDITOR_RESULT_STORAGE_KEY)
    const queue = raw ? JSON.parse(raw) : []
    const next = Array.isArray(queue) ? queue : []
    next.push(item)
    localStorage.setItem(IMAGE_EDITOR_RESULT_STORAGE_KEY, JSON.stringify(next))
  } catch {
    localStorage.setItem(IMAGE_EDITOR_RESULT_STORAGE_KEY, JSON.stringify([item]))
  }
}

/** 取回通用编辑结果（与画布那批互不干涉）。 */
export function consumeImageEditorResults(): ImageEditorResult[] {
  try {
    const raw = localStorage.getItem(IMAGE_EDITOR_RESULT_STORAGE_KEY)
    localStorage.removeItem(IMAGE_EDITOR_RESULT_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item) => item?.imageDataUrl)
  } catch {
    return []
  }
}
