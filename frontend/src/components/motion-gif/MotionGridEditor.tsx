/**
 * 可拖分割线的九宫格（**规整网格 + 可调比例**）。
 *
 * ## 为什么要有「确认切法」按钮
 *
 * 最初是**松手即生效**：拖完自动发请求重切。技术上没问题，但用户反馈
 * **"我拖动了但是没有切"** —— 因为中间隔着一次请求（几百毫秒到几秒），
 * 期间画面没有任何变化，用户无法判断是"没生效"还是"正在处理"。
 *
 * 改成显式确认后，因果关系是清楚的：
 * **拖 → 看到线停在哪 → 点「确认切法」→ 它变了**。
 * 而且连拖几条线可以**一起确认**（`pending` 会累积），不必每拖一次等一次。
 *
 * 代价是多一次点击。但对"切错了要重来"的操作，**让用户确认自己在做什么**
 * 比省一次点击重要。
 *
 * ## 布局约束
 *
 * **为什么不做"自由框"**：自由框虽然更灵活，但要处理任意重叠、任意大小的框，
 * 交互立刻变得难懂（用户会问"这两格为什么叠一起了"）。这里保留规整的
 * rows×cols 结构，只让**分割线可拖** —— 拖一条线，相邻两格同时变形，
 * 符合直觉，且不可能出现"格子重叠/空洞"。
 *
 * **坐标用归一化 0..1**，不是像素：换一张分辨率不同的多格图时同样的拖法能
 * 直接复用，不会把 256px 宽的框开在 1024px 的图上。
 *
 * **常驻而非弹窗**：与切帧面板同一条纪律 —— 切法是人工确认环节，
 * 弹窗会把页面切走，来回开关很别扭。
 *
 * **不花钱**：这里只改一组数字，切像素在后端本地完成，不调用模型。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Space, Tag, Typography } from 'antd'
import { BorderOutlined, CheckOutlined, RightOutlined, UndoOutlined } from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { beginDrag, endDrag, moveDrag } from './gridDrag'
import {
  isUniformGrid,
  sameEdges,
  uniformEdges,
} from './motionGifConfig'
import type { SheetGridEdges } from './motionGifConfig'

const { Text } = Typography

interface Props {
  /** 多格图预览图 URL。 */
  sheetUrl: string
  rows: number
  cols: number
  edges: SheetGridEdges | null
  onEdgesChange: (next: SheetGridEdges) => void
  disabled?: boolean
}

/** 拖动一条线时的最小视觉粗细（px），免得拖到看不见。 */
const HANDLE_PX = 14

export function MotionGridEditor({
  sheetUrl,
  rows,
  cols,
  edges,
  onEdgesChange,
  disabled,
}: Props) {
  const { theme: THEME } = useTheme()
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  /**
   * 拖动中的临时边界。
   *
   * ⚠️ **拖动过程中绝不把值发出去**（只在松手时提交一次）。原因不是省流量，
   * 是**布局会抖**：每挪一下鼠标就发一次请求 → 后端重切 → 上面的预览小图
   * 变高/变矮 → 页面出现或消失纵向滚动条 → **容器宽度变化几个像素** →
   * 线是按容器宽度算的百分比，于是**分割线跟着来回跳**。
   *
   * 顺带也避免了每个 pointermove 都打一个请求（一次拖动上百个）。
   */
  const [dragPreview, setDragPreview] = useState<SheetGridEdges | null>(null)
  /**
   * **待确认**的切法（拖完但还没点「确认切法」）。
   *
   * 为什么要有这一层：原来松手即生效，但用户**感知不到**——
   * "我拖了，可是没切"。原因是中间隔着一次请求（几百毫秒到几秒），
   * 期间画面没动静，用户不知道是没生效还是在处理。
   * 改成显式确认之后：拖 → 看到线停在哪儿 → 点确认 → 明确地重切一次。
   * 交互上"我做了一个动作、然后按了一个按钮、然后它变了"是清楚的因果关系。
   */
  const [pending, setPending] = useState<SheetGridEdges | null>(null)
  /** 面板展开状态。默认折叠 —— 见下面按钮处的注释。 */
  const [open, setOpen] = useState(false)

  // 外部把 edges 改了（重置/换图/后端校正）→ 清掉待确认值，避免拿着旧值去提交。
  useEffect(() => {
    setPending(null)
  }, [edges])

  const current = dragPreview ?? pending ?? edges ?? uniformEdges(rows, cols)
  /** 有待确认的改动吗（决定"确认切法"按钮是否可点）。 */
  const hasPending = pending != null && !sameEdges(pending, edges)

  // 用 ResizeObserver 而不是写死宽度：面板宽度随窗口和左右分栏变化，
  // 写死会让分割线的位置对不上（用户拖的是 A，实际切的是 B）。
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => setBox({ w: el.clientWidth, h: el.clientHeight })
    update()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [sheetUrl])

  const onPointerDown = useCallback(
    (axis: 'x' | 'y', index: number, e: React.PointerEvent<HTMLDivElement>) => {
      if (disabled) return
      e.preventDefault()
      e.stopPropagation()
      const startPointer = axis === 'x' ? e.clientX : e.clientY
      const span = axis === 'x' ? box.w : box.h
      if (span <= 0) return

      // 拖动状态机放在 `gridDrag.ts`（纯函数、有单测覆盖）——
      // 这里只负责把 DOM 事件喂给它、把结果落到 state 上。
      // 起点优先取**待确认值**：用户可能连拖两条线再一起确认，
      // 若每次都从已生效的 `edges` 起算，第二次拖动会把第一次的结果丢掉。
      let state = beginDrag({
        committed: pending ?? edges,
        uniform: uniformEdges(rows, cols),
        axis,
        index,
        startPointer,
        span,
      })

      const move = (ev: PointerEvent) => {
        state = moveDrag(state, axis === 'x' ? ev.clientX : ev.clientY)
        setDragPreview(state.preview)
      }
      const up = () => {
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', up)
        window.removeEventListener('pointercancel', up)
        // ⚠️ 提交是**普通语句**，不是写在 `setDragPreview(prev => ...)` 里。
        // React 要求更新函数纯 —— 写在里面会被重复调用、且**允许丢弃**，
        // 于是"拖动时线在动、松手什么都没留下"（用户反馈的「切了没反应」）。
        //
        // ⚠️⚠️ 但松手**不再直接生效**：只把结果存成"待确认"的草稿，
        // 用户点「确认切法」才真正提交。原因见文件头「为什么要有确认按钮」。
        const finalEdges = endDrag(state)
        setDragPreview(null)
        if (finalEdges) setPending(finalEdges)
      }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', up)
      window.addEventListener('pointercancel', up)
    },
    [box, cols, disabled, edges, pending, onEdgesChange, rows],
  )

  const uniform = isUniformGrid(edges, rows, cols)
  // 只有行列数变了才需要重置；拖过的网格切排布后必然对不上新格数
  const shapeMismatch =
    current.xs.length !== cols + 1 || current.ys.length !== rows + 1

  // 已有自定义网格时强制展开：折叠着会让用户看不到自己拖过的结果，
  // 以为拖丢了（尤其是从图片编辑器跳回来之后）。
  const expanded = open || !uniform

  return (
    <div
      style={{
        marginTop: 12,
        padding: '8px 10px',
        borderRadius: THEME.radiusSM,
        background: THEME.bgElevated,
        border: `1px solid ${THEME.borderLight}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          marginBottom: expanded ? 6 : 0,
        }}
      >
        <Space size={6} wrap>
          {/* 默认折叠：切法不是每次都要动，而这块占掉近一屏 —— 页面上同一张
              多格图已经出现多次，全展开会让用户找不到「合成」按钮。
              有自定义网格时**强制展开**（否则用户看不到自己拖过的结果，
              会以为拖丢了）。 */}
          <Button
            size="small"
            type="text"
            onClick={() => setOpen(v => !v)}
            style={{ padding: '0 4px', fontSize: 12, fontWeight: 700 }}
          >
            <RightOutlined
              style={{
                transform: expanded ? 'rotate(90deg)' : 'none',
                transition: 'transform 0.15s',
                marginRight: 4,
              }}
            />
            <BorderOutlined /> 手动切格
          </Button>
          <Tag color="purple" style={{ margin: 0 }}>
            免费
          </Tag>
          {!uniform && (
            <Tag color="orange" style={{ margin: 0 }}>
              已生效
            </Tag>
          )}
          {hasPending && (
            <Tag color="blue" style={{ margin: 0 }}>
              有未确认的改动
            </Tag>
          )}
        </Space>
        {expanded && (
          <Space size={6}>
            <Button
              size="small"
              icon={<UndoOutlined />}
              disabled={disabled || (uniform && !hasPending) || shapeMismatch}
              onClick={() => {
                setPending(null)
                onEdgesChange(uniformEdges(rows, cols))
              }}
            >
              重置网格
            </Button>
            {/* 「确认切法」：拖完必须点它才真正重切。
                见 `pending` 的注释 —— 自动生效时用户感受不到因果关系。 */}
            <Button
              size="small"
              type="primary"
              icon={<CheckOutlined />}
              disabled={disabled || !hasPending}
              onClick={() => onEdgesChange(pending!)}
            >
              确认切法
            </Button>
          </Space>
        )}
      </div>

      {expanded && (
        <>
          <Text style={{ fontSize: 11.5, color: THEME.textSecondary }}>
            拖图上的<b>竖线/横线</b>改每格的大小与位置。
            <b>拖一条线整行/整列一起变</b> —— 比如拖第 1 条竖线，是第 1 列变窄、
            第 2 列同时变宽，第 3、4 列不动。只能拖内部线，拖多少次都不花钱。
            <br />
            <b>拖完记得点「确认切法」</b>才会真的按新切法重切下面的帧。
          </Text>

          {shapeMismatch && (
            <div style={{ marginTop: 6, fontSize: 11.5, color: THEME.error }}>
              排布已改成 {rows}×{cols}，旧的拖法对不上了 —— 点「重置网格」。
            </div>
          )}
        </>
      )}

      <div
        ref={wrapRef}
        style={{
          position: 'relative',
          marginTop: 8,
          width: '100%',
          maxWidth: 420,
          // ⚠️ 必须是**正方形且不依赖兄弟元素的高度**。分割线按容器宽度的百分比
          // 定位，若容器宽会因为上方内容高度变化（预览小图重切 → 高度变化 →
          // 滚动条出现/消失）而抖，线就会跟着来回跳。给它固定宽高比即切断这条依赖。
          aspectRatio: '1 / 1',
          marginInline: 'auto',
          contain: 'layout',
          background: THEME.bgCard,
          border: `1px solid ${THEME.borderLight}`,
          borderRadius: THEME.radiusXS ?? '4px',
          overflow: 'hidden',
          touchAction: 'none',
          opacity: disabled ? 0.6 : 1,
          // 折叠时**不渲染**（而不是 display:none）：ResizeObserver 量不到
          // 尺寸会让 box 停在 0，展开后第一次拖动会因 span<=0 直接失效。
          display: expanded ? 'block' : 'none',
        }}
      >
        <img
          src={sheetUrl}
          alt="待切分的多格图"
          draggable={false}
          style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', pointerEvents: 'none' }}
        />

        {/* 竖线：xs 的内部位置（跳过两端固定的 0 和 1） */}
        {current.xs.slice(1, cols).map((value, i) => (
          <div
            key={`x${i}`}
            onPointerDown={e => onPointerDown('x', i + 1, e)}
            title="左右拖动改这列的宽度"
            style={{
              position: 'absolute',
              left: `calc(${value * 100}% - ${HANDLE_PX / 2}px)`,
              top: 0,
              bottom: 0,
              width: HANDLE_PX,
              cursor: 'col-resize',
              zIndex: 3,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                width: 2,
                height: '100%',
                background: THEME.primary,
                opacity: 0.85,
                borderRadius: 1,
                pointerEvents: 'none',
              }}
            />
          </div>
        ))}

        {/* 横线：ys 的内部位置 */}
        {current.ys.slice(1, rows).map((value, i) => (
          <div
            key={`y${i}`}
            onPointerDown={e => onPointerDown('y', i + 1, e)}
            title="上下拖动改这行的高度"
            style={{
              position: 'absolute',
              top: `calc(${value * 100}% - ${HANDLE_PX / 2}px)`,
              left: 0,
              right: 0,
              height: HANDLE_PX,
              cursor: 'row-resize',
              zIndex: 3,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                height: 2,
                width: '100%',
                background: THEME.primary,
                opacity: 0.85,
                borderRadius: 1,
                pointerEvents: 'none',
              }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export default MotionGridEditor
