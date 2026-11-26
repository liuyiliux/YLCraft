import type { CanvasImageReference, CanvasNode, CanvasResourceInput } from './types'

export function canvasNodeImageUrl(node: CanvasNode) {
  const meta = node.metadata || {}
  const output = meta.output && typeof meta.output === 'object' ? meta.output as Record<string, any> : {}
  return String(meta.imageUrl || meta.previewUrl || output.urls?.[0] || output.url || '')
}

export function isImageLikeCanvasNode(node: CanvasNode) {
  const meta = node.metadata || {}
  const mediaKind = String(meta.mediaKind || meta.assetKind || '').toLowerCase()
  const assetType = String(meta.assetType || '').toLowerCase()
  return node.type === 'image' || node.type === 'image_transform' || mediaKind === 'image' || assetType.includes('image')
}

export function readCanvasImageReferences(meta: Record<string, unknown> | undefined): CanvasImageReference[] {
  if (!Array.isArray(meta?.imageReferences)) return []
  return meta.imageReferences.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const reference = item as Partial<CanvasImageReference>
    const url = String(reference.url || '').trim()
    const title = String(reference.title || '').trim()
    if (!url || !title) return []
    return [{
      id: String(reference.id || `${reference.source || 'asset'}:${reference.assetId || reference.sourceNodeId || url}`),
      title,
      url,
      assetId: reference.assetId ? String(reference.assetId) : undefined,
      sourceNodeId: reference.sourceNodeId ? String(reference.sourceNodeId) : undefined,
      source: reference.source === 'canvas' ? 'canvas' : 'asset',
    }]
  })
}

export function canvasImageReferenceKey(reference: Pick<CanvasImageReference, 'assetId' | 'sourceNodeId' | 'url'>) {
  if (reference.assetId) return `asset:${reference.assetId}`
  if (reference.sourceNodeId) return `canvas:${reference.sourceNodeId}`
  return `url:${reference.url}`
}

export function canvasImageReferenceOptions(nodes: CanvasNode[], currentNodeId: string): CanvasImageReference[] {
  return nodes.flatMap((node) => {
    if (node.id === currentNodeId) return []
    const url = canvasNodeImageUrl(node)
    if (!url || !isImageLikeCanvasNode(node)) return []
    const output = node.metadata?.output && typeof node.metadata.output === 'object'
      ? node.metadata.output as Record<string, unknown>
      : {}
    return [{
      id: `canvas:${node.id}`,
      title: node.title,
      url,
      assetId: String(node.metadata?.assetId || output.assetId || '') || undefined,
      sourceNodeId: node.id,
      source: 'canvas' as const,
    }]
  })
}

export function imageReferenceInputs(node: CanvasNode, inputs: CanvasResourceInput[]): CanvasResourceInput[] {
  const references: CanvasResourceInput[] = []
  const seen = new Set<string>()
  const append = (input: CanvasResourceInput) => {
    const key = input.assetId ? `asset:${input.assetId}` : input.url ? `url:${input.url}` : `node:${input.nodeId}`
    if (seen.has(key)) return
    seen.add(key)
    references.push(input)
  }

  /* 2026-11-26 用户对齐参考项目：**不再把节点自身的图默认当参考**——
     参考只来自「参考内容」栏（显式 imageReferences）与上游连线。
     自身图要当参考需用户显式添加（+ 素材库/当前画布）。 */
  readCanvasImageReferences(node.metadata).forEach((reference) => {
    append({
      nodeId: reference.sourceNodeId || `asset:${reference.id}`,
      type: 'image',
      title: reference.title,
      url: reference.url,
      assetId: reference.assetId,
      value: reference,
    })
  })

  inputs.filter((input) => input.type === 'image' && input.url).forEach(append)
  return references
}
