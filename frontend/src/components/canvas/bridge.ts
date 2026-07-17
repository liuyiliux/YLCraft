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
  try {
    const raw = localStorage.getItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY)
    localStorage.removeItem(CANVAS_IMAGE_EDITOR_RESULT_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((item) => item?.imageDataUrl && item?.documentId && item?.sourceNodeId) : []
  } catch {
    return []
  }
}
