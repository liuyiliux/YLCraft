/*
 * AI 拆成分镜弹窗（翻译参考项目 canvas-oss 的 canvas-node-ai-split-dialog.tsx）
 * 流程：文本节点内容 → LLM 出 JSON 分镜 → 预览可逐条改 → 确认才建节点。
 * 用户强偏好：AI 结果先给人确认再落库，绝不直接写画布。
 */
import { useEffect, useRef, useState } from 'react'
import { Button, Input, Modal, Spin, Tooltip } from 'antd'
import { chat as chatApi } from '../../api'

export type AiShot = { title: string; content: string }

export type AiSplitConnector = {
  id?: string
  name?: string
  model?: string
  default_model?: string
  is_default?: boolean
}

type Props = {
  sourceText: string
  connectors: AiSplitConnector[]
  open: boolean
  onClose: () => void
  onConfirm: (shots: AiShot[]) => void
  /** 画布 id，用于 LLM 日志关联 */
  canvasId?: string
  nodeId?: string
}

/** 容忍 ```json 包裹、前后解释文字、中英文字段名 */
export function parseAiShots(raw: string): AiShot[] {
  let text = (raw || '').trim()
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) text = fence[1].trim()
  const start = text.search(/[\[{]/)
  if (start < 0) return []
  let candidate = text.slice(start)
  let parsed: unknown
  try {
    parsed = JSON.parse(candidate)
  } catch {
    const end = Math.max(candidate.lastIndexOf(']'), candidate.lastIndexOf('}'))
    if (end <= 0) return []
    try {
      parsed = JSON.parse(candidate.slice(0, end + 1))
    } catch {
      return []
    }
  }
  let rows: unknown =
    typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)
      ? ((parsed as Record<string, unknown>).shots ?? (parsed as Record<string, unknown>).scenes ?? (parsed as Record<string, unknown>).items ?? parsed)
      : parsed
  if (!Array.isArray(rows)) return []
  return rows
    .map((row, index): AiShot | null => {
      if (typeof row === 'string') return { title: `镜 ${index + 1}`, content: row.trim() }
      if (typeof row !== 'object' || row === null) return null
      const obj = row as Record<string, unknown>
      const title = String(obj.title ?? obj.name ?? obj.shot ?? `镜 ${index + 1}`).trim()
      const content = String(obj.content ?? obj.text ?? obj.prompt ?? obj.description ?? '').trim()
      return content ? { title: title || `镜 ${index + 1}`, content } : null
    })
    .filter((shot): shot is AiShot => Boolean(shot))
}

export default function CanvasNodeAiSplitDialog({ sourceText, connectors, open, onClose, onConfirm, canvasId, nodeId }: Props) {
  const [instruction, setInstruction] = useState('')
  const [count, setCount] = useState(6)
  const [status, setStatus] = useState<'idle' | 'loading' | 'preview' | 'error'>('idle')
  const [shots, setShots] = useState<AiShot[]>([])
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!open) return
    setInstruction('')
    setCount(6)
    setStatus('idle')
    setShots([])
    setError('')
  }, [open, sourceText])

  useEffect(() => () => abortRef.current?.abort(), [])

  const run = async () => {
    const connector = connectors.find((item) => item.is_default) || connectors[0]
    setStatus('loading')
    setError('')
    setShots([])
    const sys = [
      '你是影视分镜助手。把用户给的剧本拆成一组可直接拿去生成视频的分镜。',
      `拆成 ${count} 个分镜，每个分镜是一句独立的画面描述（主体+动作+景别+光线/氛围）。`,
      '只输出 JSON 数组，不要 Markdown、不要解释。元素格式：{"title":"镜 1 · 短标题","content":"画面描述"}。',
      'title 里带镜号（镜 1 / 镜 2…），content 是给视频模型的中文提示词，保留原文的角色名和场景。',
    ].join('\n')
    const user = `${sys}\n\n${instruction ? `补充要求：${instruction}\n\n` : ''}剧本：\n${sourceText}`
    try {
      const res = await chatApi({
        messages: [{ role: 'user', content: user }],
        provider: connector?.name || connector?.id || undefined,
        model: connector?.model || connector?.default_model || undefined,
        temperature: 0.4,
        log_scene: 'creative_canvas',
        log_ref_id: canvasId,
        log_stage: 'ai_split',
        log_request: { canvas_id: canvasId, node_id: nodeId, count, has_instruction: Boolean(instruction.trim()) },
      }) as { success?: boolean; content?: string; error?: string }
      const raw = String(res?.content || '').trim()
      if (!res?.success || !raw) throw new Error(res?.error || '拆分失败')
      const parsed = parseAiShots(raw)
      if (!parsed.length) {
        setStatus('error')
        setError('模型没有返回可识别的分镜，请重试或改补充要求')
        return
      }
      setShots(parsed)
      setStatus('preview')
    } catch (err) {
      setStatus('error')
      setError(err instanceof Error ? err.message : '拆分失败')
    }
  }

  const updateShot = (index: number, patch: Partial<AiShot>) => {
    setShots((current) => current.map((shot, i) => (i === index ? { ...shot, ...patch } : shot)))
  }

  const inputStyle = {
    background: 'rgba(255,255,255,.04)',
    borderColor: 'rgba(245,245,244,.16)',
    color: '#f5f5f4',
  }

  return (
    <Modal
      title={null}
      open={open}
      onCancel={onClose}
      footer={null}
      width={680}
      centered
      destroyOnHidden
      transitionName=""
      maskTransitionName=""
    >
      <div style={{ display: 'grid', gap: 16, padding: '4px 0' }} data-canvas-no-zoom>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: '#f5f5f4' }}>AI 拆成分镜</h2>
          <p style={{ margin: '6px 0 0', fontSize: 13, opacity: .6, color: '#f5f5f4' }}>让模型把这段剧本拆成一组分镜，确认后再生成节点</p>
        </div>

        <div style={{ maxHeight: 112, overflow: 'auto', padding: '8px 12px', borderRadius: 8, border: '1px solid rgba(245,245,244,.14)', fontSize: 12, lineHeight: '22px', whiteSpace: 'pre-wrap', opacity: .72, color: '#f5f5f4' }}>
          {sourceText}
        </div>

        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 500, opacity: .75, color: '#f5f5f4' }}>补充要求（可选）</span>
          <Input.TextArea
            rows={2}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="例如：每镜 3–5 秒，冷色调，小林出镜的镜头用特写"
            disabled={status === 'loading'}
            style={inputStyle}
          />
        </label>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ flex: '0 0 auto', fontSize: 13, fontWeight: 500, opacity: .75, color: '#f5f5f4' }}>分镜数</span>
          <Input
            type="number"
            min={1}
            max={24}
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(24, Number(e.target.value) || 1)))}
            disabled={status === 'loading'}
            style={{ ...inputStyle, width: 96 }}
          />
          <span style={{ fontSize: 12, opacity: .5, color: '#f5f5f4' }}>1–24，模型可能按剧情微调</span>
        </div>

        {status === 'loading' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 16, borderRadius: 8, border: '1px solid rgba(245,245,244,.14)', fontSize: 13, opacity: .7, color: '#f5f5f4' }}>
            <Spin size="small" /> 正在拆分剧本…
          </div>
        ) : null}
        {status === 'error' ? (
          <div style={{ padding: 12, borderRadius: 8, border: '1px solid rgba(248,113,113,.5)', background: 'rgba(248,113,113,.06)', fontSize: 13, color: '#f87171' }}>{error}</div>
        ) : null}

        {status === 'preview' ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 500, opacity: .75, color: '#f5f5f4' }}>已拆出 {shots.length} 镜，可逐条改标题和描述</div>
            <div style={{ maxHeight: 256, overflow: 'auto', display: 'grid', gap: 8, paddingRight: 4 }}>
              {shots.map((shot, index) => (
                <div key={index} style={{ display: 'grid', gap: 6, padding: 10, borderRadius: 8, border: '1px solid rgba(245,245,244,.14)' }}>
                  <Input size="small" value={shot.title} onChange={(e) => updateShot(index, { title: e.target.value })} placeholder="分镜标题" aria-label="分镜标题" style={inputStyle} />
                  <Input.TextArea size="small" rows={2} value={shot.content} onChange={(e) => updateShot(index, { content: e.target.value })} placeholder="分镜描述" aria-label="分镜描述" style={inputStyle} />
                </div>
              ))}
            </div>
            <p style={{ margin: 0, fontSize: 12, opacity: .5, color: '#f5f5f4' }}>确认后才会在画布上创建节点，取消则不改动画布</p>
          </div>
        ) : null}

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, paddingTop: 4 }}>
          <Button onClick={onClose}>取消</Button>
          {status === 'preview' ? (
            <>
              <Tooltip title="改补充要求或分镜数后重新生成">
                <Button onClick={() => void run()}>重新拆分</Button>
              </Tooltip>
              <Button type="primary" onClick={() => onConfirm(shots)}>确认生成 {shots.length} 个节点</Button>
            </>
          ) : (
            <Button type="primary" loading={status === 'loading'} disabled={!sourceText.trim() || !connectors.length} onClick={() => void run()}>AI 拆分</Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
