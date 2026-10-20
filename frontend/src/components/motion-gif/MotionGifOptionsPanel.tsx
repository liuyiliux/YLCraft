/**
 * 动图开关展开面板（生成前的参数区）。
 *
 * 只放**影响模型画什么**的参数：动效类型、格子排布、提示词语言。
 * 循环方式与帧率属于合成参数，**放在切帧面板里**——生成前画面还没出来，
 * 用户没法判断哪种接缝自然。
 */

import { useMemo, useState } from 'react'
import { Alert, Button, Segmented, Space, Tag, Tooltip, Typography } from 'antd'
import { EyeOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { useMotionGifOptions } from './useMotionGifOptions'
import type {
  GridLayoutKey,
  LoopMode,
  MotionKind,
  MotionKindOption,
  PromptLang,
} from './motionGifConfig'

const { Text } = Typography

/**
 * 解析尺寸字符串成宽高。
 *
 * 除了 `2048x2048` 这种像素值，还要认 `1K / 2K / 4K`（生图连接器常用这种写法，
 * 见 `BackendInfo.supported_sizes`）。把 `2K` 当成 2048 是保守取值——不确定时
 * 按偏大处理，宁可提示"够"也不要误报"发糊"。
 */
function parseSize(raw: string): { w: number; h: number } | null {
  if (!raw) return null
  const pixel = /^(\d+)\s*[x×*]\s*(\d+)$/i.exec(raw.trim())
  if (pixel) {
    const w = Number(pixel[1])
    const h = Number(pixel[2])
    return w > 0 && h > 0 ? { w, h } : null
  }
  const tier = /^([124])K$/i.exec(raw.trim())
  if (tier) {
    const side = { '1': 1024, '2': 2048, '4': 4096 }[tier[1]]!
    return { w: side, h: side }
  }
  return null
}

interface Props {
  motionKind: MotionKind
  onMotionKindChange: (kind: MotionKind) => void
  gridLayout: GridLayoutKey
  onGridLayoutChange: (layout: GridLayoutKey) => void
  promptLang: PromptLang
  onPromptLangChange: (lang: PromptLang) => void
  /** 当前是文生图还是图生图（用于提示带参考图的收益）。 */
  mode: 'text2img' | 'img2img'
  /** 当前生成尺寸（如 "2048x2048"），用于算单格像素。 */
  size: string
  /** 合成输出长边（px），用于判断单格像素够不够。 */
  outputSize: number
  onOpenPromptPreview: () => void
  /** 已应用的优化结果（存在时提示"不再追加系统块"）。 */
  optimized?: boolean
}

export function MotionGifOptionsPanel({
  motionKind,
  onMotionKindChange,
  gridLayout,
  onGridLayoutChange,
  promptLang,
  onPromptLangChange,
  mode,
  size,
  outputSize,
  onOpenPromptPreview,
  optimized,
}: Props) {
  const { theme: THEME } = useTheme()
  // 可选项由共享 hook 拉（页面与面板共用同一次请求，见 useMotionGifOptions 注释）
  const { options, grids } = useMotionGifOptions()

  const kinds: MotionKindOption[] = options?.motion_kinds || []

  const currentKind = kinds.find(k => k.key === motionKind)
  const currentGrid = grids.find(g => g.key === gridLayout)

  // 文生图也能做环绕/表情包，只是主体一致性差 —— 提示，不禁用也不自动切模式
  const needsRefHint =
    currentKind?.prefer_reference && mode === 'text2img'

  /**
   * 单格像素 = 图宽 ÷ 列数、图高 ÷ 行数。
   *
   * 关键前提：**格子是"等分"出来的**，不是"先出整图再缩小"。
   * 所以非 1:1 比例（尤其 9:16 这种细长）切出来的格子**又窄又高**，
   * 单格宽度不足时成品只能靠放大，必然发糊。
   *
   * 判据用**宽度**（成品的长边由宽的那边决定）而不是面积。
   */
  const parsedSize = parseSize(size)
  const cellPixels = currentGrid && parsedSize
    ? `${Math.floor(parsedSize.w / currentGrid.cols)}×${Math.floor(parsedSize.h / currentGrid.rows)}`
    : ''
  const cellQuality = useMemo<'ok' | 'warn' | 'unknown'>(() => {
    if (!currentGrid || !parsedSize) return 'unknown'
    const cellW = parsedSize.w / currentGrid.cols
    // 短边需 >= outputSize 才算原生（1:1 时刚好等值）
    if (cellW >= outputSize) return 'ok'
    // 低于 75% 属于"明显会糊"，高于则只是偏小
    return cellW >= outputSize * 0.75 ? 'warn' : 'warn'
  }, [currentGrid, parsedSize, outputSize])
  const motionOutputSize = outputSize

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ marginBottom: 6, fontWeight: 500, fontSize: 13 }}>动效类型</div>
      <Text style={{ display: 'block', fontSize: 12, color: THEME.textSecondary, marginBottom: 10 }}>
        决定「画面里到底在动什么」。四类写法不能互相照抄。
      </Text>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {kinds.map(k => (
          <div
            key={k.key}
            role="button"
            tabIndex={0}
            onClick={() => onMotionKindChange(k.key)}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') onMotionKindChange(k.key)
            }}
            style={{
              border: `1px solid ${k.key === motionKind ? THEME.primary : THEME.borderLight}`,
              background:
                k.key === motionKind
                  ? 'rgba(124,58,237,0.12)'
                  : THEME.bgElevated,
              borderRadius: THEME.radiusSM ?? '8px',
              padding: 10,
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 12.5 }}>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  flex: 'none',
                  background:
                    k.stability === 'good'
                      ? '#22c55e'
                      : k.stability === 'fair'
                        ? '#f59e0b'
                        : '#555',
                }}
              />
              {k.label}
            </div>
            <div style={{ fontSize: 11, color: THEME.textSecondary, marginTop: 3, lineHeight: 1.45 }}>
              {k.motion}
            </div>
            <div style={{ fontSize: 11, color: THEME.textSecondary, marginTop: 4 }}>
              {k.prefer_reference ? '建议带参考图' : '可不用参考图'} ·{' '}
              {k.stability === 'good'
                ? '已实测稳定'
                : k.stability === 'fair'
                  ? '实测需减帧'
                  : '未验证'}
            </div>
          </div>
        ))}
      </div>

      {needsRefHint && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 10, fontSize: 12 }}
          message={
            <span style={{ fontSize: 12 }}>
              「{currentKind?.label}」在<b>文生图</b>下也能做，但模型每格都在重新构想同一主体，
              <b>产品外观可能越转越走样</b>。带上参考图（图生图）可锁住外观。
            </span>
          }
        />
      )}

      <div style={{ margin: '14px 0 6px', fontWeight: 500, fontSize: 13 }}>格子排布</div>
      <div style={{ display: 'flex', gap: 8 }}>
        {grids.map(g => (
          <div
            key={g.key}
            role="button"
            tabIndex={0}
            onClick={() => onGridLayoutChange(g.key)}
            onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') onGridLayoutChange(g.key)
            }}
            style={{
              flex: 1,
              position: 'relative',
              border: `1px solid ${g.key === gridLayout ? THEME.primary : THEME.borderLight}`,
              background:
                g.key === gridLayout ? 'rgba(124,58,237,0.12)' : THEME.bgElevated,
              borderRadius: THEME.radiusSM ?? '8px',
              padding: 9,
              textAlign: 'center',
              cursor: 'pointer',
            }}
          >
            {g.recommended && (
              <span
                style={{
                  position: 'absolute',
                  top: -7,
                  right: 6,
                  background: '#22c55e',
                  color: '#04210f',
                  fontSize: 9.5,
                  fontWeight: 700,
                  padding: '1px 5px',
                  borderRadius: 4,
                }}
              >
                推荐
              </span>
            )}
            <b style={{ fontSize: 12.5 }}>{g.label}</b>
            <div style={{ fontSize: 10.5, color: THEME.textSecondary }}>
              {g.rows}×{g.cols}
            </div>
          </div>
        ))}
      </div>
      {currentGrid && (
        <Text style={{ display: 'block', fontSize: 11.5, color: THEME.textSecondary, marginTop: 8 }}>
          {currentGrid.note}
        </Text>
      )}

      {/* 单格像素：格子是「等分」出来的，比例越细长格子越窄 —— 这决定成品会不会发糊 */}
      {currentGrid && cellPixels && (
        <div
          style={{
            marginTop: 8,
            padding: '8px 10px',
            borderRadius: THEME.radiusSM ?? '8px',
            background: THEME.bgElevated,
            border: `1px solid ${
              cellQuality === 'ok' ? 'rgba(34,197,94,.35)' : 'rgba(245,158,11,.4)'
            }`,
            fontSize: 11.5,
            lineHeight: 1.6,
          }}
        >
          <span style={{ color: THEME.textSecondary }}>单格像素　</span>
          <b style={{ color: cellQuality === 'ok' ? '#86efac' : '#fcd34d' }}>
            {cellPixels}
          </b>
          <span style={{ color: THEME.textSecondary, marginLeft: 8 }}>
            {cellQuality === 'ok'
              ? `· 够支撑 ${motionOutputSize}px 成品`
              : `· 不足 ${motionOutputSize}px 成品，放大后会发糊`}
          </span>
          {cellQuality !== 'ok' && (
            <div style={{ marginTop: 4, color: '#fcd34d' }}>
              格子是按行列<strong>等分</strong>的 —— 非 1:1 比例切出的格子更窄。
              建议尺寸改成 <b>2048×2048</b>，或减少格数。
            </div>
          )}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          margin: '14px 0 6px',
          gap: 8,
        }}
      >
        <Space size={8}>
          <Text style={{ fontSize: 13, fontWeight: 500 }}>提示词语言</Text>
          <Tooltip title="中文给人和模型都看得懂；英文原句是实测验证过的">
            <Segmented
              size="small"
              value={promptLang}
              onChange={v => onPromptLangChange(v as PromptLang)}
              options={[
                { label: '中文', value: 'zh' },
                { label: 'English', value: 'en' },
              ]}
            />
          </Tooltip>
        </Space>
        <Text style={{ fontSize: 11, color: THEME.textSecondary }}>
          实际发送哪版，在预览里会标出来
        </Text>
      </div>

      <Space wrap style={{ marginTop: 10 }}>
        <Button size="small" icon={<EyeOutlined />} onClick={onOpenPromptPreview}>
          预览最终提示词
        </Button>
        {optimized && (
          <Tag color="green" icon={<ThunderboltOutlined />} style={{ margin: 0 }}>
            已应用 AI 优化 · 不再追加系统块
          </Tag>
        )}
      </Space>

      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12, fontSize: 12 }}
        message={
          <span style={{ fontSize: 12 }}>
            「循环方式」在<b>切帧面板</b>里选 —— 它决定 GIF 怎么拼帧，
            <b>不影响模型画什么</b>。生成前画面还没出来，没法判断哪种接缝自然。
          </span>
        }
      />
    </div>
  )
}

export default MotionGifOptionsPanel
