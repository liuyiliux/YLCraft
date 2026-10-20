/**
 * 动图切帧面板（第 2 步 · 免费 · 可反复切）。
 *
 * **为什么常驻而不是弹窗**：切帧是人工确认环节（模型可能把 8 格画成 4×4、
 * 或某格画崩），用户要边看边改。弹窗会把页面切走，多次操作时来回开关很别扭。
 *
 * **改多少次都不花钱**：本组件只改 order，不调用任何模型；真正合成要用户点
 * 「合成动图」才会走 `composeMotionGif`（同样不调模型）。
 *
 * 帧顺序用 `SliceRef`（来源标识）而不是数组下标表达：用户删格、补图、调顺序后
 * 下标会漂移，而「这格来自原图第几格」才是他要核对的信息。
 */

import { useCallback, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Segmented,
  Space,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  DeleteOutlined,
  PlayCircleOutlined,
  RedoOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  cellLabel,
  hasAdjust,
  isUpload,
  restoreAutoSlice,
} from './motionGifConfig'
import { uploadMotionGifFrame } from './api'
import MotionGridEditor from './MotionGridEditor'
import MotionFrameEditor from './MotionFrameEditor'
import type { FrameAdjust, LoopMode, SheetGridEdges, SliceRef } from './motionGifConfig'

const { Text } = Typography

/** 切帧预览返回的单格信息。 */
export interface SliceCellInfo {
  position: number
  label: string
  /** 该格的图片 URL（多格图裁切结果）。 */
  url?: string
  source: SliceRef
}

interface Props {
  cells: number
  cols: number
  order: SliceRef[]
  onOrderChange: (next: SliceRef[]) => void
  /** 每帧的小图 URL（与 order 等长）。后端切好并存盘后返回 —— 没有它面板就是黑框。 */
  frameUrls?: string[]
  loop: LoopMode
  onLoopChange: (next: LoopMode) => void
  loopOptions: { key: LoopMode; label: string; note: string }[]
  /** 是否把每帧主体平移居中（消除"主体上下跳动"）。 */
  alignSubject: boolean
  onAlignSubjectChange: (next: boolean) => void
  /** 是否裁掉每格主体之外的留白（默认关 —— 裁了会把主体切坏）。 */
  trim: boolean
  onTrimChange: (next: boolean) => void
  /** 已合成的产物存在时为 true（用于提示"改完可重新合成"）。 */
  composed?: boolean
  composing?: boolean
  onCompose: () => void
  disabled?: boolean
  /** 多格图原图 URL —— 「手动切格」编辑器要显示它才能看出拖对没拖对。 */
  sheetUrl?: string
  rows?: number
  gridEdges: SheetGridEdges | null
  onGridEdgesChange: (next: SheetGridEdges) => void
  /** 跳去图片编辑器（外部动作，由页面提供去处）。 */
  onOpenEditor?: (index: number) => void
}

export function MotionGifSlicePanel({
  cells,
  cols,
  order,
  onOrderChange,
  frameUrls,
  loop,
  onLoopChange,
  loopOptions,
  alignSubject,
  onAlignSubjectChange,
  trim,
  onTrimChange,
  composed,
  composing,
  onCompose,
  disabled,
  sheetUrl,
  rows,
  gridEdges,
  onGridEdgesChange,
  onOpenEditor,
}: Props) {
  const { theme: THEME } = useTheme()
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  /** 当前选中的帧（供「调这一帧」用）。删格后下标会漂移，超界就当没选。 */
  const [selected, setSelected] = useState(-1)
  const selectedSafe = selected >= 0 && selected < order.length ? selected : -1

  const setAdjust = useCallback(
    (index: number, adjust: FrameAdjust | null) => {
      if (index < 0 || index >= order.length) return
      const next = [...order]
      next[index] = adjust ? { ...next[index], adjust } : { ...next[index], adjust: null }
      onOrderChange(next)
    },
    [order, onOrderChange],
  )

  const currentLoopNote = useMemo(
    () => loopOptions.find(o => o.key === loop)?.note || '',
    [loop, loopOptions],
  )

  const move = useCallback(
    (from: number, to: number) => {
      if (from === to || from < 0 || to < 0) return
      if (from >= order.length || to >= order.length) return
      const next = [...order]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      onOrderChange(next)
    },
    [order, onOrderChange],
  )

  const removeAt = useCallback(
    (index: number) => {
      // 至少留两格，否则合成出来不是动画
      if (order.length <= 2) {
        message.warning('至少保留 2 格，否则合成出来不是动画')
        return
      }
      onOrderChange(order.filter((_, i) => i !== index))
    },
    [order, onOrderChange],
  )

  const [uploading, setUploading] = useState(false)

  const addUpload = useCallback(
    async (file: File) => {
      if (uploading) return false
      setUploading(true)
      try {
        // 必须**先传文件**再写进 order：order 里只有 {kind:'upload', index}，
        // 像素在后端。只写序号不传文件的话，切帧预览与合成都取不到图。
        const uploaded = await uploadMotionGifFrame(file)
        if (!uploaded?.success) {
          message.error('上传失败')
          return false
        }
        onOrderChange([...order, { kind: 'upload', index: uploaded.index }])
        message.success(`已加入上传图 #${uploaded.index}（${Math.round(uploaded.file_size / 1024)}KB）`)
      } catch (e: any) {
        message.error(`上传失败：${e?.message || e}`)
      } finally {
        setUploading(false)
      }
      return false
    },
    [order, onOrderChange, uploading],
  )

  const restore = useCallback(() => {
    onOrderChange(restoreAutoSlice(cells, order))
    message.info('已恢复自动切帧（保留了你上传的图片）')
  }, [cells, order, onOrderChange])

  const uploadCount = order.filter(isUpload).length
  // 还没生成多格图时 order 是空的，此时算「已删 N 格」会得到 cells-0=8，
  // 显示成「已删 8 格」——用户会以为删过。空序列一律不报删除数。
  const dropped =
    order.length === 0 ? 0 : cells - order.filter(r => r.kind === 'origin').length

  return (
    <div>
      {/* 手动切格放在**最上面**：它是"切几格、每格多大"的粗调，
          而下面的「切帧调整」是"哪一帧删掉/换顺序"的细调 —— 先定框再调帧，
          顺序反了用户得来回滚。 */}
      {sheetUrl && rows ? (
        <MotionGridEditor
          sheetUrl={sheetUrl}
          rows={rows}
          cols={cols}
          edges={gridEdges}
          onEdgesChange={onGridEdgesChange}
          disabled={disabled}
        />
      ) : null}

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: sheetUrl && rows ? 16 : 0,
          marginBottom: 8,
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <Space size={6} wrap>
          <Text strong style={{ fontSize: 12 }}>切帧调整</Text>
          <Tag color="purple" style={{ margin: 0 }}>免费 · 可反复切</Tag>
          {dropped > 0 && (
            <Tag color="orange" style={{ margin: 0 }}>已删 {dropped} 格</Tag>
          )}
          {uploadCount > 0 && (
            <Tag color="green" style={{ margin: 0 }}>上传补位 {uploadCount} 张</Tag>
          )}
        </Space>
        <Tooltip title="只重置顺序与删格，保留你上传的图片">
          <Button size="small" icon={<RedoOutlined />} onClick={restore} disabled={disabled}>
            恢复自动切帧
          </Button>
        </Tooltip>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12, fontSize: 12 }}
        message={
          <span style={{ fontSize: 12 }}>
            模型有时会把 {cells} 格画成别的排布，或某格画崩。拖动可换顺序、
            ✕ 可删格、＋ 可上传图片占一格 —— <b>改多少次都不花钱</b>，点下方按钮才合成。
          </span>
        }
      />

      {order.length === 0 ? (
        /* 上面已有「待切分的图片」三入口（图源与生成解耦），所以这里只提示
           "还没选图"，**不要再把用户引去「开始生成」**——那是三条路之一，
           不是前提，说出来反而误导。 */
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 4, fontSize: 12 }}
          message={
            <span style={{ fontSize: 12 }}>
              还没有可切的图 —— 先在<b>上方「待切分的图片」</b>里选一张
              （生成 / 素材库 / 上传都行），这里就会列出 {cells} 格供你拖动、删格、补图。
            </span>
          }
        />
      ) : (
        <>
          <div
            style={{
              display: 'grid',
              /*
               * ⚠️ 卡片**必须等宽**，不能让宽度跟着图片走。
               *
               * 试过"卡片宽度=图片比例"，结果很糟：被拖成细条的那格只有 18px 宽，
               * 而 441px 宽的格占了半屏 —— 一行放不下，**后面的帧被挤出可视区**，
               * 用户以为"格子丢了"。
               *
               * 正确做法：**卡片等宽，图片在卡片内按真实比例居中留白**（contain）。
               * 这样既不会撑破布局，又能一眼看出"这一格是细条"。
               */
              gridTemplateColumns: `repeat(${Math.min(cols, 8)}, minmax(0, 1fr))`,
              gap: 8,
              padding: 12,
              background: THEME.bgElevated,
              border: `1px dashed ${THEME.borderLight}`,
              borderRadius: THEME.radiusSM,
              justifyItems: 'center',
              alignItems: 'start',
            }}
          >
            {order.map((ref, index) => (
              <div
                /*
                 * ⚠️ key 里必须带上**当前这一帧的图片地址**。
                 *
                 * 原来只用 `${kind}-${index}-${位置}`，拖动分割线后这些值**一个都不变**，
                 * 于是 React 复用同一个 `<img>` 节点；而新旧地址指向的是**同名文件**
                 * （都在 `frames/frame_02.png`，只是换了目录），
                 * Chrome 会把上一次解码好的位图继续用 —— 表现为
                 * **"确认切法后下面的帧完全没变化"**（实测：接口返回 177/63，
                 * 页面上却仍是 120/120；刷新一次才对）。
                 *
                 * 把地址并进 key，地址一变就重建节点，图片必然重新加载。
                 */
                key={`${ref.kind}-${ref.index ?? index}-${index}-${frameUrls?.[index] ?? ''}`}
                draggable
                onDragStart={e => {
                  setDragIndex(index)
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onDragOver={e => {
                  e.preventDefault()
                  setOverIndex(index)
                }}
                onDragLeave={() => setOverIndex(prev => (prev === index ? null : prev))}
                onDrop={e => {
                  e.preventDefault()
                  if (dragIndex !== null) move(dragIndex, index)
                  setDragIndex(null)
                  setOverIndex(null)
                }}
                onDragEnd={() => {
                  setDragIndex(null)
                  setOverIndex(null)
                }}
                title="点一下选中这帧去调色；按住拖动可换顺序"
                onClick={() => setSelected(selected === index ? -1 : index)}
                style={{
                  position: 'relative',
                  /*
                   * 卡片**等宽正方形**，图片在里面按真实比例居中（contain）。
                   *
                   * 为什么不是"宽度跟随图片"：细条格只有 18px、宽格要 150px+，
                   * 一行放不下会把后面的帧挤出可视区（实测过，用户会以为格子丢了）。
                   * 等宽卡片 + contain 既不撑破布局，又能一眼看出哪格是细条 ——
                   * 因为细条在卡片里会显示成一根**两侧留白的窄柱**，与宽格明显不同。
                   */
                  width: '100%',
                  maxWidth: 150,
                  aspectRatio: '1 / 1',
                  borderRadius: THEME.radiusXS ?? '4px',
                  // 三种边框状态别混：拖放悬停（蓝虚线感）、选中（主色粗）、
                  // 普通。选中必须**一眼可见**，否则用户不知道该点哪张。
                  border: `2px solid ${
                    selected === index
                      ? THEME.primary
                      : overIndex === index && dragIndex !== null && dragIndex !== index
                        ? THEME.primary
                        : THEME.borderLight
                  }`,
                  boxShadow: selected === index ? `0 0 0 2px ${THEME.primary}33` : 'none',
                  opacity: dragIndex === index ? 0.4 : 1,
                  background: THEME.bgCard,
                  cursor: 'grab',
                  overflow: 'hidden',
                }}
              >
                <span
                  style={{
                    position: 'absolute',
                    top: 3,
                    left: 3,
                    zIndex: 2,
                    background: 'rgba(0,0,0,0.72)',
                    color: '#fff',
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '1px 5px',
                    borderRadius: 4,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {cellLabel(ref, index + 1)}
                </span>
                <Button
                  size="small"
                  type="text"
                  icon={<DeleteOutlined />}
                  onClick={() => removeAt(index)}
                  disabled={disabled}
                  aria-label="删掉这格"
                  style={{
                    position: 'absolute',
                    top: 2,
                    right: 2,
                    zIndex: 2,
                    minWidth: 20,
                    height: 20,
                    padding: 0,
                    color: '#fff',
                    background: 'rgba(220,38,38,0.9)',
                    borderRadius: 4,
                    lineHeight: '20px',
                  }}
                />
                {/* 「已调色」标记：黄点。原来只有「调这一帧」里那一排小图有，
                    删掉那排后这个信息必须在这里才看得见。 */}
                {hasAdjust(ref) && (
                  <span
                    title="这帧被调过亮度/颜色"
                    style={{
                      position: 'absolute',
                      bottom: 3,
                      right: 3,
                      zIndex: 2,
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: '#faad14',
                      boxShadow: '0 0 0 1.5px rgba(0,0,0,0.5)',
                    }}
                  />
                )}
                {/* 每帧小图：没有它面板就是黑框，用户没法判断切得对不对 */}
                {frameUrls?.[index] ? (
                  <img
                    src={frameUrls[index]}
                    alt=""
                    /*
                     * 图片在等宽卡片里**按真实比例居中显示**（contain）。
                     * 细条格会显示成"两侧留白的窄柱"，与宽格明显不同 ——
                     * 一眼能看出切法，又不会把布局撑破。
                     */
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'contain',
                      display: 'block',
                    }}
                  />
                ) : (
                  <div
                    style={{
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: THEME.textSecondary,
                      fontSize: 10,
                      textAlign: 'center',
                      padding: 4,
                    }}
                  >
                    预览生成中…
                  </div>
                )}
              </div>
            ))}

            <Upload
              accept="image/*"
              showUploadList={false}
              beforeUpload={addUpload}
              disabled={disabled}
              style={{ width: '100%', maxWidth: 150 }}
            >
              <div
                style={{
                  width: '100%',
                  aspectRatio: '1 / 1',
                  border: `2px dashed ${THEME.borderLight}`,
                  borderRadius: THEME.radiusXS ?? '4px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 4,
                  color: THEME.textSecondary,
                  fontSize: 11,
                  cursor: disabled || uploading ? 'not-allowed' : 'pointer',
                  opacity: uploading ? 0.6 : 1,
                }}
              >
                <UploadOutlined style={{ fontSize: 18 }} />
                {uploading ? '上传中…' : '上传占一格'}
              </div>
            </Upload>
          </div>

          {/* 单帧微调：右栏内嵌，不跳页不弹窗 */}
          <MotionFrameEditor
            order={order}
            selected={selectedSafe}
            onSelectedChange={setSelected}
            selectedUrl={selectedSafe >= 0 ? frameUrls?.[selectedSafe] : undefined}
            onAdjustChange={setAdjust}
            onOpenEditor={onOpenEditor}
            disabled={disabled}
          />

          <div
            style={{
              marginTop: 12,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <Space size={8}>
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>循环方式</Text>
              <Segmented
                size="small"
                value={loop}
                onChange={v => onLoopChange(v as LoopMode)}
                disabled={disabled}
                options={loopOptions.map(o => ({ label: o.label, value: o.key }))}
              />
            </Space>
            <Text style={{ fontSize: 11, color: THEME.textSecondary }}>{currentLoopNote}</Text>
          </div>

          {/* 主体对齐：模型不保证每格主体居中，不对齐就会在动画里上下跳动 */}
          <div
            style={{
              marginTop: 10,
              padding: '8px 10px',
              borderRadius: THEME.radiusSM,
              background: THEME.bgElevated,
              border: `1px solid ${THEME.borderLight}`,
              fontSize: 11.5,
            }}
          >
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={alignSubject}
                onChange={e => onAlignSubjectChange(e.target.checked)}
                disabled={disabled}
                style={{ accentColor: THEME.primary }}
              />
              <span style={{ color: THEME.textPrimary }}>把每格主体对齐到中心</span>
            </label>
            <div style={{ marginTop: 4, color: THEME.textSecondary }}>
              模型不保证主体在每格里居中，不对齐的话 GIF 里主体会上下跳动
              （表现为「整张图在抖」）。关掉则保留各格原始位置，背景不会被补边。
            </div>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                cursor: 'pointer',
                marginTop: 8,
              }}
            >
              <input
                type="checkbox"
                checked={trim}
                onChange={e => onTrimChange(e.target.checked)}
                disabled={disabled}
                style={{ accentColor: THEME.primary }}
              />
              <span style={{ color: THEME.textPrimary }}>裁掉每格主体之外的留白</span>
            </label>
            <div style={{ marginTop: 4, color: THEME.textSecondary }}>
              <b>默认不要开。</b>多格图每格本身已取好景，按并集裁切会切掉留白 ——
              实测把蓝狗顶满画布、切掉脚。只有当模型在每格里又画了一圈边距时才需要开。
            </div>
          </div>

          <Space style={{ marginTop: 14 }}>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={onCompose}
              loading={composing}
              disabled={disabled}
            >
              合成动图
            </Button>
            {composed && (
              <Text style={{ fontSize: 11, color: THEME.textSecondary }}>
                改完可以再点一次，不花钱
              </Text>
            )}
          </Space>
        </>
      )}
    </div>
  )
}

export default MotionGifSlicePanel
