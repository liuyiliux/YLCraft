/**
 * 图生图「画面批注」画布
 *
 * 让用户在参考图上**圈出一块区域 + 写一句话**，把「想改成什么样」变成坐标 + 文字，
 * 而不是再写一段含糊的提示词。
 *
 * 设计取舍（与后端 `services/image_annotation` 对齐）：
 * - 坐标一律用 **0~1 相对比例**，x2/y2 为**开区间**（右/下边界不含）。与贴字 `items.box`、
 *   地图布局同一套约定，也保证换分辨率后批注位置不会漂。
 * - 圈选与文字**解耦**：允许先框后写，也允许写完再补框。
 * - 组件**不直接调接口**，只产出数据结构，由调用方决定什么时候提交。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Input, Space, Tag, Tooltip, Typography, message } from 'antd'
import {
  ClearOutlined,
  EditOutlined,
  HighlightOutlined,
} from '@ant-design/icons'

const { Text } = Typography
const { TextArea } = Input

/** 与后端 `MAX_ANNOTATIONS` / `MAX_COMMENT_LEN` 保持一致，避免提交后才被拒。 */
const MAX_ANNOTATIONS = 64
const MAX_COMMENT_LEN = 1000

export interface AnnotationRect {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface ImageAnnotation {
  id: string
  comment: string
  rectangle: AnnotationRect
  created_at: string
}

/**
 * 提交给后端的载荷形状（`ImageGenerateRequest.annotations`）。
 *
 * `number` 是**过滤空意见之后**重新分配的序号：它同时是提示词里的序号和图上角标的数字，
 * 两边必须一致，否则模型会把意见安到错误的框上。
 */
export interface AnnotationPayloadItem {
  id: string
  number: number
  comment: string
  rectangle: AnnotationRect
  created_at: string
}

export type ImageAnnotationPayload = AnnotationPayloadItem[]

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v)

/**
 * 从一次拖拽的两个点算出规范化的矩形。
 *
 * 从右下往左上拖会产生 x2<x1，这里统一排序，因此用户不必讲究拖拽方向。
 */
function rectFromPoints(ax: number, ay: number, bx: number, by: number): AnnotationRect {
  return {
    x1: round6(Math.min(clamp01(ax), clamp01(bx))),
    y1: round6(Math.min(clamp01(ay), clamp01(by))),
    x2: round6(Math.max(clamp01(ax), clamp01(bx))),
    y2: round6(Math.max(clamp01(ay), clamp01(by))),
  }
}

const round6 = (v: number): number => Math.round(v * 1e6) / 1e6

interface Props {
  imageUrl: string
  annotations: ImageAnnotation[]
  onChange: (next: ImageAnnotation[]) => void
  disabled?: boolean
  height?: number
  /**
   * 当前选中的批注 id。受控可选：传了就用外部的值（编辑工作台里侧栏点一条，
   * 画布要跟着高亮），不传就组件自己管。
   */
  activeId?: string | null
  onActiveChange?: (id: string | null) => void
  /** 隐藏内置的批注列表（只留画布），列表交给侧栏渲染时用。 */
  hideList?: boolean
}

export default function AnnotationCanvas({
  imageUrl,
  annotations,
  onChange,
  disabled = false,
  height = 380,
  activeId: controlledActiveId,
  onActiveChange,
  hideList = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [dragging, setDragging] = useState<{ ax: number; ay: number; bx: number; by: number } | null>(null)
  const [internalActiveId, setInternalActiveId] = useState<string | null>(null)
  const activeId = controlledActiveId !== undefined ? controlledActiveId : internalActiveId
  const setActiveId = (id: string | null) => {
    if (controlledActiveId === undefined) setInternalActiveId(id)
    onActiveChange?.(id)
  }

  // 图片**实际绘制区域**在容器里的位置与尺寸。
  //
  // 为什么必须记 offset：容器用 `objectFit: contain`，图比容器窄时会**居中留黑边**。
  // 若拿容器原点当图片原点、拿容器宽高当图片宽高算坐标，框会整体偏移
  // （你的截图：框画在右眼，实际渲染到了两眼中间的鼻梁上）。
  // 所以这里记录图片在容器内的真实盒子，坐标一律相对**图片本身**。
  const [imageBox, setImageBox] = useState<{
    width: number
    height: number
    offsetX: number
    offsetY: number
  } | null>(null)

  const toRelative = useCallback(
    (clientX: number, clientY: number) => {
      const box = imageBox
      const rect = containerRef.current?.getBoundingClientRect()
      if (!box || !rect || box.width <= 0 || box.height <= 0) return null
      return {
        // 先减去图片在容器内的偏移，再除以图片自身尺寸——两步缺一不可。
        x: clamp01((clientX - rect.left - box.offsetX) / box.width),
        y: clamp01((clientY - rect.top - box.offsetY) / box.height),
      }
    },
    [imageBox],
  )

  const onPointerDown = (e: React.PointerEvent) => {
    if (disabled || !imageBox) return
    const point = toRelative(e.clientX, e.clientY)
    if (!point) return
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
    setDragging({ ax: point.x, ay: point.y, bx: point.x, by: point.y })
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return
    const point = toRelative(e.clientX, e.clientY)
    if (!point) return
    setDragging((prev) => (prev ? { ...prev, bx: point.x, by: point.y } : prev))
  }

  const onPointerUp = () => {
    if (!dragging) return
    const rect = rectFromPoints(dragging.ax, dragging.ay, dragging.bx, dragging.by)
    setDragging(null)

    // 退化成一条线的框（误点没拖）直接忽略，不要塞一条空批注进列表。
    if (rect.x2 - rect.x1 < 0.005 || rect.y2 - rect.y1 < 0.005) {
      message.info('框太小了，在图上按住鼠标拖出一块区域')
      return
    }

    if (annotations.length >= MAX_ANNOTATIONS) {
      message.warning(`最多 ${MAX_ANNOTATIONS} 条批注`)
      return
    }

    const id = `a${Date.now()}${Math.floor(Math.random() * 1000)}`
    const next: ImageAnnotation = {
      id,
      comment: '',
      rectangle: rect,
      created_at: new Date().toISOString(),
    }
    onChange([...annotations, next])
    setActiveId(id)
    // 新手最容易卡住的一步是「圈完不知道怎么写字」。画完直接把光标放进这条的意见输入框，
    // 让「圈 → 写」连成一个动作，不必先去找刚出现的那条。
    requestAnimationFrame(() => {
      document.querySelector<HTMLTextAreaElement>(`[data-annotation-input="${id}"]`)?.focus()
    })
  }

  // Esc 取消当前框选：拖拽中途反悔时不用非得拖完。
  useEffect(() => {
    if (!dragging) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDragging(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [dragging])

  const updateComment = (id: string, comment: string) => {
    onChange(annotations.map((item) => (item.id === id ? { ...item, comment } : item)))
  }

  const removeAnnotation = (id: string) => {
    onChange(annotations.filter((item) => item.id !== id))
    if (activeId === id) setActiveId(null)
  }

  const pending = dragging
    ? rectFromPoints(dragging.ax, dragging.ay, dragging.bx, dragging.by)
    : null

  // 「已写 / 共几条」是新手最需要的进度信号：一眼看出还有几条没填。
  const writtenCount = annotations.filter((item) => item.comment.trim()).length

  // 画布角标 / 侧栏序号 / 提示词编号必须用**同一套**编号。
  // 只有写了意见的框会被提交并进入提示词，所以空框不占号——
  // 否则「图上的第 2 个框」与「提示词里的第 2 条意见」会错位。
  const numbering = useMemo(() => {
    const map = new Map<string, number>()
    annotations.forEach((item) => {
      if (item.comment.trim() && !map.has(item.id)) map.set(item.id, map.size + 1)
    })
    return map
  }, [annotations])

  return (
    <div>
      <div
        ref={containerRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={{
          position: 'relative',
          height,
          background: '#0f0f1a',
          border: '1px solid #333',
          borderRadius: 8,
          overflow: 'hidden',
          cursor: disabled ? 'default' : 'crosshair',
          touchAction: 'none',
          userSelect: 'none',
        }}
      >
        <img
          src={imageUrl}
          alt="参考图"
          draggable={false}
          onLoad={(e) => {
            const el = e.currentTarget
            const container = el.parentElement
            if (!container) return
            const cw = container.clientWidth
            const ch = container.clientHeight
            const nw = el.naturalWidth
            const nh = el.naturalHeight
            if (!cw || !ch || !nw || !nh) return

            // 复刻 `object-fit: contain` 的计算：等比缩放到能装下，居中留边。
            // 直接用 getBoundingClientRect 拿 img 盒子**不行**——`object-fit`
            // 只改绘制内容不改元素盒子，量到的仍是整个容器。
            const scale = Math.min(cw / nw, ch / nh)
            const drawW = nw * scale
            const drawH = nh * scale
            setImageBox({
              width: drawW,
              height: drawH,
              offsetX: (cw - drawW) / 2,
              offsetY: (ch - drawH) / 2,
            })
          }}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: 'block',
            pointerEvents: 'none',
          }}
        />

        {/* 框的覆盖层。
            坐标是相对**图片**的，所以定位基准必须是图片在容器里的盒子，
            而不是容器本身——否则图片留边时框会整体偏移。 */}
        {annotations.map((item, index) => {
          const isActive = activeId === item.id
          if (!imageBox) return null
          return (
            <div
              key={item.id}
              onClick={(e) => {
                e.stopPropagation()
                if (disabled) return
                setActiveId(item.id)
              }}
              style={{
                position: 'absolute',
                left: imageBox.offsetX + item.rectangle.x1 * imageBox.width,
                top: imageBox.offsetY + item.rectangle.y1 * imageBox.height,
                width: (item.rectangle.x2 - item.rectangle.x1) * imageBox.width,
                height: (item.rectangle.y2 - item.rectangle.y1) * imageBox.height,
                border: `2px solid ${isActive ? '#7c3aed' : '#22d3ee'}`,
                background: isActive ? 'rgba(124,58,237,0.16)' : 'rgba(34,211,238,0.12)',
                cursor: disabled ? 'default' : 'pointer',
                boxSizing: 'border-box',
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  top: -10,
                  left: -2,
                  background: isActive ? '#7c3aed' : '#22d3ee',
                  color: '#0f0f1a',
                  fontSize: 10,
                  fontWeight: 700,
                  padding: '0 5px',
                  borderRadius: 3,
                  lineHeight: '16px',
                }}
              >
                {numbering.get(item.id) ?? index + 1}
              </span>
            </div>
          )
        })}

        {/* 拖拽中的预览框 */}
        {pending && imageBox && (
          <div
            style={{
              position: 'absolute',
              left: imageBox.offsetX + pending.x1 * imageBox.width,
              top: imageBox.offsetY + pending.y1 * imageBox.height,
              width: (pending.x2 - pending.x1) * imageBox.width,
              height: (pending.y2 - pending.y1) * imageBox.height,
              border: '2px dashed #facc15',
              background: 'rgba(250,204,21,0.12)',
              boxSizing: 'border-box',
              pointerEvents: 'none',
            }}
          />
        )}

        {/* 首次使用：直接在图上给出可执行的引导，而不是等用户读完文字再来试。
            定位在**图片**区域下沿，图留边时不会飘到黑边上。 */}
        {annotations.length === 0 && !dragging && imageBox && (
          <div
            style={{
              position: 'absolute',
              left: imageBox.offsetX,
              width: imageBox.width,
              top: imageBox.offsetY + imageBox.height - 48,
              display: 'flex',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <div
              style={{
                background: 'rgba(20,20,42,0.92)',
                border: '1px solid #3a3a5e',
                borderRadius: 999,
                padding: '6px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <HighlightOutlined style={{ color: '#a78bfa' }} />
              <span style={{ color: '#e2e8f0', fontSize: 12 }}>
                按住鼠标在这里拖一个框
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 状态条：每步都告诉用户「现在该做什么」。列表交给侧栏时不再重复计数。 */}
      {!hideList && (
      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <Tag color={annotations.length ? 'cyan' : 'default'} style={{ margin: 0 }}>
          已标 {writtenCount} / {annotations.length}
        </Tag>
        {annotations.length === 0 ? (
          <Text style={{ color: '#a78bfa', fontSize: 12, fontWeight: 500 }}>
            <span style={{ marginRight: 4 }}>第 1 步</span>
            在图上按住鼠标拖一个框，圈住想改的地方
          </Text>
        ) : (
          <Text style={{ color: '#a78bfa', fontSize: 12, fontWeight: 500 }}>
            <span style={{ marginRight: 4 }}>第 2 步</span>
            在下面的输入框写清楚想改成什么样
          </Text>
        )}
        {annotations.length > 0 && (
          <Button
            size="small"
            type="text"
            icon={<ClearOutlined />}
            disabled={disabled}
            onClick={() => {
              onChange([])
              setActiveId(null)
            }}
            style={{ color: '#8b8ba8', marginLeft: 'auto' }}
          >
            清空
          </Button>
        )}
      </div>
      )}

      {/* 批注列表：编号与画面上的角标一一对应。侧栏接管时整块不渲染。 */}
      {!hideList && (
      <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto' }}>
        {annotations.length === 0 ? (
          <div
            style={{
              padding: '14px 12px',
              borderRadius: 8,
              border: '1px dashed #3a3a5e',
              background: '#14142a',
              textAlign: 'center',
            }}
          >
            <Text style={{ color: '#8b8ba8', fontSize: 12 }}>
              还没有批注。圈一块区域后，在这里写下想改什么。
            </Text>
          </div>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={6}>
            {annotations.map((item, index) => {
              const isActive = activeId === item.id
              const isEmpty = !item.comment.trim()
              return (
                <div
                  key={item.id}
                  onClick={() => {
                    setActiveId(item.id)
                  }}
                  style={{
                    padding: 8,
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: isActive ? '#1e1e2e' : 'transparent',
                    // 还没写字的条目用琥珀色描边提示「这条还没填」，填完自动消失。
                    border: `1px solid ${
                      isEmpty ? '#f59e0b' : isActive ? '#7c3aed' : 'transparent'
                    }`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <Tag color={isEmpty ? 'orange' : 'cyan'} style={{ margin: 0 }}>
                      {isEmpty ? '—' : numbering.get(item.id)}
                    </Tag>
                    <Text style={{ color: '#6b6b8a', fontSize: 11 }}>
                      x {Math.round(item.rectangle.x1 * 100)}~{Math.round(item.rectangle.x2 * 100)}% · y{' '}
                      {Math.round(item.rectangle.y1 * 100)}~{Math.round(item.rectangle.y2 * 100)}%
                    </Text>
                    {isEmpty && (
                      <Tag color="warning" style={{ margin: 0, fontSize: 10 }}>
                        待填写
                      </Tag>
                    )}
                    <Tooltip title="删除这条批注">
                      <Button
                        size="small"
                        type="text"
                        disabled={disabled}
                        onClick={(e) => {
                          e.stopPropagation()
                          removeAnnotation(item.id)
                        }}
                        style={{ color: '#f87171', marginLeft: 'auto' }}
                      >
                        删除
                      </Button>
                    </Tooltip>
                  </div>
                  <TextArea
                    data-annotation-input={item.id}
                    value={item.comment}
                    disabled={disabled}
                    maxLength={MAX_COMMENT_LEN}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    placeholder={`第 ${index + 1} 处想改成什么？（例：这只手多了一根手指）`}
                    onChange={(e) => updateComment(item.id, e.target.value)}
                    onFocus={() => setActiveId(item.id)}
                  />
                </div>
              )
            })}
          </Space>
        )}
      </div>
      )}

      {/* 一旦有批注，按「怎么写才有用」给实例——新手最缺的不是位置，是措辞参考。
          只在仍有待填写条目时出现：都写完了还挂着一排示例，反而像在催用户继续用。
          侧栏接管时示例也在侧栏，这里不重复。 */}
      {!hideList && annotations.length > 0 && writtenCount < annotations.length && (
        <div
          style={{
            marginTop: 8,
            padding: '10px 12px',
            borderRadius: 8,
            background: '#14142a',
            border: '1px solid #2a2a4e',
          }}
        >
          <Text style={{ color: '#8b8ba8', fontSize: 11, display: 'block', marginBottom: 6 }}>
            点一个示例，填进当前选中的批注：
          </Text>
          <Space wrap size={[6, 6]}>
            {[
              '这只手多了一根手指',
              '角色外套换成红色风衣',
              '这个气泡不要压住脸',
              '背景的电线去掉',
              '这里再亮一些',
            ].map((sample) => (
              <Tag
                key={sample}
                color="purple"
                style={{ cursor: 'pointer', margin: 0 }}
                onClick={() => {
                  // 优先填「当前选中」那条（用户刚点的就是它）；没有选中才退回第一条空的。
                  const target =
                    annotations.find((a) => a.id === activeId && !a.comment.trim()) ||
                    annotations.find((a) => !a.comment.trim())
                  if (!target) return
                  updateComment(target.id, sample)
                  setActiveId(target.id)
                }}
              >
                {sample}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {!hideList && annotations.some((item) => !item.comment.trim()) && (
        <div style={{ marginTop: 6 }}>
          <Text style={{ color: '#fbbf24', fontSize: 12 }}>
            <EditOutlined /> 有 {annotations.length - writtenCount} 条还没写意见，只圈不写的不会生效。
          </Text>
        </div>
      )}
    </div>
  )
}

/**
 * 把批注转成提交载荷：丢掉空意见，避免把无效条目发到后端。
 *
 * 过滤后**重新编号**并写进 `number`：编号必须与图上画的角标严格一致，
 * 而角标是按这个载荷渲染的。服务端也会再做一次同样的编号，两边算法相同。
 */
export function toAnnotationPayload(annotations: ImageAnnotation[]): ImageAnnotationPayload {
  return annotations
    .filter((item) => item.comment.trim())
    .map((item, index) => ({
      id: item.id,
      number: index + 1,
      comment: item.comment.trim(),
      rectangle: {
        x1: round6(item.rectangle.x1),
        y1: round6(item.rectangle.y1),
        x2: round6(item.rectangle.x2),
        y2: round6(item.rectangle.y2),
      },
      created_at: item.created_at,
    }))
}