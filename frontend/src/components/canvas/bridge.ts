import type { CanvasNode } from './types'

export const CANVAS_DOCUMENTS_STORAGE_KEY = 'ylcraft-canvas-documents-v1'
export const CANVAS_IMPORT_QUEUE_STORAGE_KEY = 'ylcraft-canvas-import-queue-v1'

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
