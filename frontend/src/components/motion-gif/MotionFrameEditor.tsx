/**
 * 单帧微调面板（**右栏内嵌，不跳页、不弹窗**）。
 *
 * **为什么内嵌**：跳转图片编辑器的话流程是 生成 → 跳出 → 编辑 → 跳回 →
 * 重新合成，五步来回。而"某格偏亮导致动图闪烁"这种问题只需要滑一下亮度。
 * 内嵌就是左边选帧、右边滑滑块，改完立刻看动图变化。
 *
 * **能做什么、不能做什么**（这个界线是刻意的）：
 * - 能做：亮度/对比度/饱和度/色相/旋转 —— 纯像素变换，**零模型调用、零费用**，
 *   用来抹掉各帧之间的亮度与色调差异。
 * - 不能做：重画、扩图、换背景 —— 那是"改画面内容"，要走图片编辑器，
 *   会花钱也可能对不上其它格。这里留一个跳转按钮（由调用方传入），
 *   但不塞进滑块区，免得工具栏变成大杂烩。
 */

import { Button, Slider, Space, Tag, Tooltip, Typography } from 'antd'
import { EditOutlined, UndoOutlined } from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  ADJUST_CONTROLS,
  NEUTRAL_ADJUST,
  cellLabel,
  hasAdjust,
} from './motionGifConfig'
import type { FrameAdjust, SliceRef } from './motionGifConfig'

const { Text } = Typography

interface Props {
  order: SliceRef[]
  /** 当前选中的帧下标；-1 = 没选。 */
  selected: number
  onSelectedChange: (index: number) => void
  /** 选中的那一帧的小图（只显示**一张**，不是一排 —— 见下方注释）。 */
  selectedUrl?: string
  onAdjustChange: (index: number, adjust: FrameAdjust | null) => void
  /** 跳到图片编辑器（外部动作，由页面决定去哪儿）。不传就不显示。 */
  onOpenEditor?: (index: number) => void
  disabled?: boolean
}

export function MotionFrameEditor({
  order,
  selected,
  onSelectedChange,
  selectedUrl,
  onAdjustChange,
  onOpenEditor,
  disabled,
}: Props) {
  const { theme: THEME } = useTheme()
  const ref = selected >= 0 ? order[selected] : undefined
  const current: Required<FrameAdjust> = { ...NEUTRAL_ADJUST, ...(ref?.adjust ?? {}) }
  const tuned = ref ? hasAdjust(ref) : false

  const set = (key: keyof FrameAdjust, value: number) => {
    if (!ref) return
    const next = { ...current, [key]: value }
    const isNeutral = ADJUST_CONTROLS.every(
      c => Math.abs(Number(next[c.key]) - c.neutral) < 1e-6,
    )
    onAdjustChange(selected, isNeutral ? null : next)
  }

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
          marginBottom: 6,
        }}
      >
        <Space size={6} wrap>
          <Text strong style={{ fontSize: 12 }}>
            <EditOutlined /> 调这一帧
          </Text>
          <Tag color="purple" style={{ margin: 0 }}>
            免费 · 不调模型
          </Tag>
          {tuned && (
            <Tag color="orange" style={{ margin: 0 }}>
              已调
            </Tag>
          )}
        </Space>
        {ref && tuned && (
          <Button
            size="small"
            icon={<UndoOutlined />}
            disabled={disabled}
            onClick={() => onAdjustChange(selected, null)}
          >
            还原
          </Button>
        )}
      </div>

      <Text style={{ fontSize: 11.5, color: THEME.textSecondary }}>
        在<b>上面的格子</b>点一帧来选，然后滑下面的条。用途是抹掉「某格偏亮/偏色」
        造成的闪烁 —— 改多少次都不花钱。想要真的重画内容，用下方按钮去图片编辑器。
      </Text>

      {/*
        **只显示选中那一帧的大图**，不再列一排小图。
        原来这里又排了 8 张小图，和上面「切帧调整」的 8 张卡**完全重复**
        （同一批 `frameUrls`、同样的顺序），白白占一屏还得二次选帧。
        选帧只在上面做一次，这里专职显示与调参。
      */}
      {ref ? (
        <div style={{ marginTop: 8, display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div
            style={{
              position: 'relative',
              width: 96,
              height: 96,
              flex: '0 0 auto',
              borderRadius: THEME.radiusXS ?? '4px',
              overflow: 'hidden',
              border: `1px solid ${THEME.borderLight}`,
              background: THEME.bgCard,
            }}
          >
            {selectedUrl ? (
              <img
                /* key 带地址：切法一变地址就变，强制重建节点以重新加载图片。
                   否则同名文件会被浏览器沿用旧位图（见 MotionGifSlicePanel 的说明）。 */
                key={selectedUrl}
                src={selectedUrl}
                alt=""
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
              />
            ) : (
              <div
                style={{
                  width: '100%',
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 10,
                  color: THEME.textSecondary,
                }}
              >
                预览中…
              </div>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Text style={{ fontSize: 11.5, color: THEME.textSecondary }}>
              当前：{cellLabel(ref, selected + 1)}
            </Text>
            {ADJUST_CONTROLS.map(control => {
              const value = Number(current[control.key])
              const changed = Math.abs(value - control.neutral) > 1e-6
              return (
                <div key={control.key} style={{ marginTop: 2 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 11,
                      color: changed ? THEME.primary : THEME.textSecondary,
                    }}
                  >
                    <span>{control.label}</span>
                    <span>{changed ? value.toFixed(2) : '默认'}</span>
                  </div>
                  <Slider
                    min={control.min}
                    max={control.max}
                    step={control.step}
                    value={value}
                    disabled={disabled}
                    tooltip={{ formatter: v => v?.toFixed(2) }}
                    marks={{
                      [control.min]: control.lowHint,
                      [control.max]: control.highHint,
                    }}
                    onChange={v => set(control.key, Number(v))}
                  />
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div
          style={{
            marginTop: 10,
            fontSize: 11.5,
            color: THEME.textSecondary,
            textAlign: 'center',
            padding: '12px 0',
          }}
        >
          在上面的格子里点一帧，选中的格会亮起来，这里就能调了。
        </div>
      )}

      {ref && onOpenEditor && (
        <Tooltip title="重画/扩图会调用图像模型并计费，且可能与其它格对不上">
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={disabled}
            onClick={() => onOpenEditor(selected)}
            style={{ marginTop: 10 }}
          >
            去图片编辑器改画面内容
          </Button>
        </Tooltip>
      )}
    </div>
  )
}

export default MotionFrameEditor
