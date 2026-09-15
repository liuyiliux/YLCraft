/**
 * 漫画页贴字编辑器：在成图的气泡里写对白。
 *
 * **为什么必须有这一步**（实测，不是推测）：后端引擎按框算，"文字塞得下"是真的，
 * 但**框位对不对只能靠看**。我两次按缩小预览估坐标都放偏——一次文字溢出气泡落到深色
 * 背景上，一次第二行压在气泡外面，而引擎两次都是对的。
 *
 * 所以打开时会先**自动量一遍气泡位置**（服务端检测模型画出的空白区域），再按阅读顺序
 * 把该页分格的对白逐条填进去——位置来自图像、文字来自分镜，人只需要微调。量不到时
 * 退回"按分格序号纵向粗略排开"，绝不让用户对着空画布手估坐标。
 *
 * 坐标全程用 0~1 相对比例（与后端 `page.json` 同构），所以图片怎么缩放都不用换算，
 * 也不用管用户屏幕多大。要调整就：在图上点一下新建框、拖动移动、拖右下角改大小。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Empty, Image, Input, InputNumber, Modal, Segmented, Space, Spin, Tag, Tooltip, Typography, message } from 'antd'
import { AimOutlined, DeleteOutlined, EyeOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'

import { detectCreativeProjectComicBlankBoxes, overlayCreativeProjectComicPageText } from '../../../api'

const { Text } = Typography

/** 一个待贴元素。`box` 是 0~1 的 [x0, y0, x1, y1]。 */
export interface OverlayItem {
  type: 'text' | 'bubble' | 'narration' | 'sfx'
  box: [number, number, number, number]
  text: string
  /** 仅 `sfx` 用。 */
  font_size?: number
  /** 仅 `bubble` 用：尾巴尖指向哪里（说话人）。 */
  tail?: [number, number]
}

export interface OverlayPanelHint {
  panel_index?: number
  dialogue?: string
  sfx?: string
  shot?: string
}

interface Props {
  open: boolean
  onClose: () => void
  projectId: string
  itemId: string
  /** 该页成图的可显示地址。 */
  imageUrl: string
  /** 该页分格，用来预填对白与音效。 */
  panels?: OverlayPanelHint[]
  onSaved?: (assetId: string) => void
}

/** 新建框的默认尺寸（相对比例）。够放两三个字，用户可以拖大。 */
const DEFAULT_W = 0.16
const DEFAULT_H = 0.07

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

export default function PageOverlayEditor({ open, onClose, projectId, itemId, imageUrl, panels, onSaved }: Props) {
  const [items, setItems] = useState<OverlayItem[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  /** 框位是怎么来的：`detected` 服务端量出来的 / `fallback` 按分格序号估的。 */
  const [placement, setPlacement] = useState<'detected' | 'fallback' | ''>('')
  const surfaceRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ mode: 'move' | 'resize'; index: number; startX: number; startY: number; box: OverlayItem['box'] } | null>(null)

  /** 该页要贴的文本行（按分格顺序）。 */
  const textLines = useMemo(() => {
    const lines: Array<{ type: OverlayItem['type']; text: string }> = []
    for (const hint of panels || []) {
      const dialogue = String(hint?.dialogue || '').trim()
      const sfx = String(hint?.sfx || '').trim()
      if (dialogue) lines.push({ type: 'text', text: dialogue })
      if (sfx) lines.push({ type: 'sfx', text: sfx })
    }
    return lines
  }, [panels])

  /** 问服务端要这一页的空白占位框（0~1 相对坐标，按阅读顺序）。失败就返回空数组。 */
  const fetchBlankBoxes = useCallback(async (): Promise<OverlayItem['box'][]> => {
    if (!projectId || !itemId) return []
    try {
      const res: any = await detectCreativeProjectComicBlankBoxes(projectId, itemId)
      const rows = Array.isArray(res?.boxes) ? res.boxes : []
      return rows.filter(
        (b: any) => Array.isArray(b) && b.length === 4 && b.every((n: any) => typeof n === 'number'),
      ) as OverlayItem['box'][]
    } catch {
      // 检测是**增强项**：失败不该让编辑器不可用，退回粗略排布即可。
      return []
    }
  }, [projectId, itemId])

  /** 量位置并摆框。打开时自动跑一次，「自动定位气泡」按钮也用它。 */
  const placeBoxes = useCallback(async () => {
    const boxes = await fetchBlankBoxes()
    let seeded: OverlayItem[]
    if (boxes.length) {
      // 检测结果按阅读顺序返回，正好与该页分格的对白顺序对应：逐条预填。
      // 框多出来时留空文本（可能是模型多画的空泡，用户删掉即可）。
      seeded = boxes.map((box, index) => {
        const line = textLines[index]
        return {
          type: line?.type ?? 'text',
          text: line?.text ?? '',
          box,
          ...(line?.type === 'sfx' ? { font_size: 44 } : {}),
        }
      })
      setPlacement('detected')
    } else {
      // 退路（旧行为）：一格一条，按序号纵向粗略排开。
      const total = Math.max(1, textLines.length)
      seeded = textLines.map((line, index) => {
        const y0 = clamp01(0.06 + (index / total) * 0.82)
        const x = line.type === 'sfx' ? 0.62 : 0.06
        return {
          type: line.type,
          text: line.text,
          box: [x, y0, x + DEFAULT_W, clamp01(y0 + DEFAULT_H)] as OverlayItem['box'],
          ...(line.type === 'sfx' ? { font_size: 44 } : {}),
        }
      })
      setPlacement('fallback')
    }
    setItems(seeded)
    setSelected(seeded.length ? 0 : null)
    setPreviewUrl('')
    setWarnings([])
  }, [fetchBlankBoxes, textLines])

  /**
   * 编辑后自动出预览。
   *
   * 编辑态的框是 DOM 覆盖层、字体是网页字体**占位**，与真实渲染**永远对不上**——
   * 用户会发现"保存后字号怎么变大了"。真实排版是服务端按框自动定字号、把气泡填满的。
   * 所以拖完框/改完字后自动跑一次服务端预览（防抖），而它用的就是最终出图的那个引擎，
   * 于是画面上看到的始终是成品效果。
   */
  useEffect(() => {
    if (!open || !items.length || previewUrl) return
    const timer = window.setTimeout(() => {
      void run(true, false)
    }, 900)
    return () => window.clearTimeout(timer)
    // 刻意不把 run 放进依赖：它每次渲染都是新引用，会把防抖变成不停重跑。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, items, previewUrl])

  /** 打开时自动摆框：先量气泡位置，量不到再退回按分格序号的粗略纵向排布。 */
  useEffect(() => {
    if (!open) return
    void placeBoxes()
  }, [open, placeBoxes])

  const containerSize = useCallback(() => {
    const rect = surfaceRef.current?.getBoundingClientRect()
    return rect ? { width: rect.width || 1, height: rect.height || 1, rect } : null
  }, [])

  const updateItem = useCallback((index: number, patch: Partial<OverlayItem>) => {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }, [])

  const addAt = useCallback((x: number, y: number) => {
    const box: OverlayItem['box'] = [
      clamp01(x - DEFAULT_W / 2),
      clamp01(y - DEFAULT_H / 2),
      clamp01(x + DEFAULT_W / 2),
      clamp01(y + DEFAULT_H / 2),
    ]
    setItems((current) => {
      const next = [...current, { type: 'text' as const, box, text: '' }]
      setSelected(next.length - 1)
      return next
    })
    setPreviewUrl('')
  }, [])

  /** 空处按下＝新建；框上按下＝拖动；手柄按下＝缩放。 */
  const onSurfacePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.target !== event.currentTarget && !(event.target as HTMLElement).dataset.surface) return
      const size = containerSize()
      if (!size) return
      addAt((event.clientX - size.rect.left) / size.width, (event.clientY - size.rect.top) / size.height)
    },
    [addAt, containerSize],
  )

  const beginDrag = useCallback(
    (event: React.PointerEvent, index: number, mode: 'move' | 'resize') => {
      event.stopPropagation()
      event.preventDefault()
      setSelected(index)
      dragRef.current = { mode, index, startX: event.clientX, startY: event.clientY, box: [...items[index].box] as OverlayItem['box'] }
    },
    [items],
  )

  useEffect(() => {
    if (!open) return
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current
      const size = containerSize()
      if (!drag || !size) return
      const dx = (event.clientX - drag.startX) / size.width
      const dy = (event.clientY - drag.startY) / size.height
      const [x0, y0, x1, y1] = drag.box
      let next: OverlayItem['box']
      if (drag.mode === 'move') {
        // 整体平移时先夹住左上角，再按同样位移推右下角——否则贴边时框会被压扁。
        const nx0 = Math.min(Math.max(0, x0 + dx), 1 - (x1 - x0))
        const ny0 = Math.min(Math.max(0, y0 + dy), 1 - (y1 - y0))
        next = [nx0, ny0, nx0 + (x1 - x0), ny0 + (y1 - y0)]
      } else {
        const minW = 0.04
        const minH = 0.025
        next = [x0, y0, clamp01(Math.max(x0 + minW, x1 + dx)), clamp01(Math.max(y0 + minH, y1 + dy))]
      }
      updateItem(drag.index, { box: next })
      setPreviewUrl('')
    }
    const onUp = () => {
      dragRef.current = null
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [open, containerSize, updateItem])

  const payloadItems = useMemo(
    () =>
      items
        .filter((item) => String(item.text || '').trim())
        .map((item) => ({
          type: item.type,
          box: item.box,
          text: item.text,
          ...(item.type === 'sfx' ? { font_size: item.font_size ?? 44, outline: 5 } : {}),
          ...(item.type === 'bubble' && item.tail ? { tail: item.tail } : {}),
        })),
    [items],
  )

  const run = useCallback(
    async (dryRun: boolean, saveAsset: boolean) => {
      if (!payloadItems.length) {
        message.warning('至少写一条对白再贴')
        return
      }
      setBusy(true)
      try {
        const response: any = await overlayCreativeProjectComicPageText(projectId, itemId, {
          items: payloadItems,
          dry_run: dryRun,
          save_asset: saveAsset,
        })
        const data = response?.data || response || {}
        setWarnings(Array.isArray(data.warnings) ? data.warnings : [])
        if (dryRun) {
          message.success(data.warnings?.length ? '框位有提示，请看下方' : '框位检查通过')
        } else {
          const url = String(data.output_url || '')
          if (url) setPreviewUrl(`${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`)
          if (data.asset_id) {
            message.success('已贴字并存入素材库（原图未被覆盖）')
            onSaved?.(String(data.asset_id))
          } else if (data.warnings?.length) {
            message.warning('贴字完成，但登记素材库失败，请看提示')
          }
        }
      } catch (error) {
        message.error((error as Error).message)
      } finally {
        setBusy(false)
      }
    },
    [itemId, onSaved, payloadItems, projectId],
  )

  const selectedItem = selected === null ? null : items[selected]

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={1080}
      title="贴字：把对白写进气泡"
      footer={null}
      destroyOnHidden
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="生图时气泡是留白的（模型写中文会出乱码），对白在这里贴。"
        description={
          <>
            在图上点一下新建框，拖动移动，<b>拖框右下角那个方块改大小</b>（悬停会显示「拖这里改大小」）。
            框要对着气泡放——框比气泡大，字就会跑到气泡外面去。
            <br />
            这里显示的字体只是**占位**（网页字体）。真实排版是服务端画的漫画字体——
            点「检查框位」就能看到真实效果（所见即所得，跟最终产图是同一个引擎）。
          </>
        }
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 12 }}>
        <div>
          <div
            ref={surfaceRef}
            onPointerDown={onSurfacePointerDown}
            style={{ position: 'relative', lineHeight: 0, border: '1px solid var(--p-border)', borderRadius: 6, overflow: 'hidden', cursor: 'crosshair' }}
          >
            <img
              data-surface="1"
              src={previewUrl || imageUrl}
              alt="漫画页"
              draggable={false}
              style={{ width: '100%', display: 'block', userSelect: 'none' }}
            />
            {!previewUrl &&
              items.map((item, index) => {
                const [x0, y0, x1, y1] = item.box
                const isSelected = selected === index
                return (
                  <div
                    key={index}
                    onPointerDown={(event) => beginDrag(event, index, 'move')}
                    style={{
                      position: 'absolute',
                      left: `${x0 * 100}%`,
                      top: `${y0 * 100}%`,
                      width: `${(x1 - x0) * 100}%`,
                      height: `${(y1 - y0) * 100}%`,
                      border: `2px ${isSelected ? 'solid' : 'dashed'} ${isSelected ? 'var(--p-accent)' : '#888'}`,
                      background: 'rgba(255,255,255,0.35)',
                      borderRadius: 4,
                      cursor: 'move',
                      overflow: 'hidden',
                      lineHeight: 1.25,
                    }}
                  >
                    <div style={{ fontSize: 11, color: '#222', padding: 2, wordBreak: 'break-all' }}>
                      {item.text || '（空）'}
                    </div>
                    <div
                      onPointerDown={(event) => beginDrag(event, index, 'resize')}
                      title="拖这里改大小"
                      style={{
                        position: 'absolute',
                        right: -2,
                        bottom: -2,
                        // 原来只有 12px、没有描边，在满是线条的漫画页上几乎看不见——
                        // 用户反馈"不知道怎么调大小"。放大到 18px 并加白描边 + 投影，
                        // 让它在一堆格线里也能一眼认出来。
                        width: 18,
                        height: 18,
                        background: isSelected ? 'var(--p-accent)' : '#888',
                        cursor: 'nwse-resize',
                        borderRadius: 3,
                        border: '2px solid #fff',
                        boxShadow: '0 1px 3px rgba(0,0,0,.45)',
                      }}
                    />
                  </div>
                )
              })}
          </div>
          {previewUrl ? (
            <Space style={{ marginTop: 8 }}>
              <Tag color="success">这是真实排版预览</Tag>
              <Button size="small" onClick={() => setPreviewUrl('')}>回到框编辑</Button>
            </Space>
          ) : null}
        </div>

        <div>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Space wrap>
              <Tooltip title="按这一页的空白气泡重新量一遍框位，并按阅读顺序重新预填对白">
                <Button
                  size="small"
                  icon={<AimOutlined />}
                  loading={detecting}
                  onClick={() => {
                    setDetecting(true)
                    void placeBoxes().finally(() => setDetecting(false))
                  }}
                >
                  自动定位气泡
                </Button>
              </Tooltip>
              <Button size="small" icon={<PlusOutlined />} onClick={() => addAt(0.5, 0.5)}>添加一条</Button>
              <Tooltip title="只检查越界与重叠，不出图">
                <Button size="small" icon={<EyeOutlined />} loading={busy} onClick={() => void run(true, false)}>检查框位</Button>
              </Tooltip>
            </Space>

            {placement ? (
              <Text type={placement === 'detected' ? 'success' : 'secondary'} style={{ fontSize: 12 }}>
                {placement === 'detected'
                  ? '框位是从图上量出来的（气泡留白处），已按阅读顺序预填该页对白——核对后微调即可'
                  : '没量到气泡位置，框位是按分格序号估的——请对着原图拖动校正'}
              </Text>
            ) : null}

            {selectedItem ? (
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                <Segmented
                  size="small"
                  value={selectedItem.type}
                  onChange={(value) =>
                    updateItem(selected as number, {
                      type: value as OverlayItem['type'],
                      font_size: value === 'sfx' ? selectedItem.font_size ?? 44 : undefined,
                    })
                  }
                  options={[
                    { label: '对白（写进空泡）', value: 'text' },
                    { label: '旁白框', value: 'narration' },
                    { label: '拟声字', value: 'sfx' },
                  ]}
                />
                <Input.TextArea
                  rows={2}
                  value={selectedItem.text}
                  placeholder="这条的字（用回车分行）"
                  // 主题对齐：这个 Modal 在深色主题下没吃到 `--p-bg` 一类主题变量，输入框
                  // 背景走深色、文字颜色也是深色，于是"发黑看不清"（用户反馈）。
                  // 用编辑器**本来就在用**的同一套变量（`--p-accent`/`--p-border` 同源），
                  // 而不是写死颜色——写死会在浅色主题下反过来出问题。
                  style={{
                    background: 'var(--p-bg, transparent)',
                    color: 'var(--p-text, inherit)',
                    borderColor: 'var(--p-border, transparent)',
                  }}
                  onChange={(event) => updateItem(selected as number, { text: event.target.value })}
                />
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>字号</Text>
                  <InputNumber
                    size="small"
                    min={8}
                    max={200}
                    style={{ width: 78 }}
                    value={selectedItem.font_size}
                    placeholder="自动"
                    onChange={(value) => updateItem(selected as number, { font_size: value ?? undefined })}
                  />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    留空 = 按框自动定；单位是「图高 1024 时的像素」，会按实际高度等比缩放
                  </Text>
                </Space>
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    框：{(selectedItem.box[2] - selectedItem.box[0]).toFixed(3)} × {(selectedItem.box[3] - selectedItem.box[1]).toFixed(3)}
                  </Text>
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      setItems((current) => current.filter((_, i) => i !== selected))
                      setSelected(null)
                      setPreviewUrl('')
                    }}
                  >
                    删除
                  </Button>
                </Space>
              </Space>
            ) : (
              <Text type="secondary" style={{ fontSize: 12 }}>在图上点一下，或在列表里选一条来编辑</Text>
            )}

            <div style={{ maxHeight: 220, overflowY: 'auto' }}>
              {items.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有对白" />
              ) : (
                items.map((item, index) => (
                  <div
                    key={index}
                    onClick={() => setSelected(index)}
                    style={{
                      padding: '4px 6px',
                      borderRadius: 4,
                      cursor: 'pointer',
                      background: selected === index ? 'var(--bgLayout)' : 'transparent',
                      fontSize: 12,
                    }}
                  >
                    <Tag style={{ marginRight: 6 }}>{item.type === 'text' ? '对白' : item.type === 'sfx' ? '音效' : '旁白'}</Tag>
                    {item.text || '（空）'}
                  </div>
                ))
              )}
            </div>

            {warnings.length ? (
              <Alert type="warning" showIcon message={`${warnings.length} 条提示`}
                     description={<ul style={{ margin: 0, paddingLeft: 16 }}>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>} />
            ) : null}

            <Button
              type="primary"
              block
              icon={<SaveOutlined />}
              loading={busy}
              onClick={() => void run(false, true)}
            >
              贴字并存入素材库
            </Button>
            <Text type="secondary" style={{ fontSize: 11 }}>
              产物是派生资产，原图不动——不满意可以重贴。
            </Text>
          </Space>
        </div>
      </div>
      {busy ? <Spin style={{ position: 'absolute', left: '50%', top: '50%' }} /> : null}
    </Modal>
  )
}
