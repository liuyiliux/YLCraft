/**
 * 媒体生成结果的通用缩略图（结果回流 UI）。
 *
 * 提取自 `/multi-platform-gen` 页卡里的内联结果区。该区块原先只服务「多平台生图」页面，
 * 而**内容包工作台的条目同样会生成图片并把 `image_url` / `asset_ids` / `status` 写回表单**
 * （见 `useProjectContentActions.handleBatchGenerateContentPackageImages`），数据早就在，
 * 界面却什么都不显示。抽成组件后两处共用同一实现，避免再写第二份。
 *
 * 两种形态：
 *   - 已有图片：图片 + 悬浮操作（重新生成 / 删除）
 *   - 无图片：虚线占位 + 失败原因（或空态文案）+ 可选「重试」
 *
 * 两处刻意保留的原有行为：
 *   - 悬浮操作按钮**只在有图时出现**（占位形态给的是「重试」，不重复给删除）。
 *   - 占位形态的「重试」使用渐变底，与页面卡片里的主操作保持同一视觉语言。
 */
import { DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { Image } from 'antd'
import { useTheme } from '../../constants/theme'

export interface GeneratedMediaThumbProps {
  /** 已生成媒体的 URL；为空时渲染占位形态 */
  url?: string
  /** 占位形态要显示的原因（生成失败时传） */
  error?: string
  /** 占位形态的兜底文案，在无 error 时显示 */
  emptyText?: string
  /** 操作进行中：两个按钮都进入禁用态并降透明度 */
  loading?: boolean
  /** 画布比例，默认沿用多平台页的 3/4 */
  aspectRatio?: string
  /** 宽度；页面卡片传 '100%'，条目行传固定像素 */
  width?: number | string
  onRegenerate?: () => void
  onRemove?: () => void
  regenerateTitle?: string
  removeTitle?: string
}

export default function GeneratedMediaThumb({
  url,
  error,
  emptyText = '尚未生成',
  loading = false,
  aspectRatio = '3/4',
  width = '100%',
  onRegenerate,
  onRemove,
  regenerateTitle = '重新生成',
  removeTitle = '删除',
}: GeneratedMediaThumbProps) {
  const { theme: T } = useTheme()

  if (!url) {
    return (
      <div
        style={{
          width,
          aspectRatio,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: T.bgElevated,
          borderRadius: T.radiusMD,
          border: `1px dashed ${T.border}`,
          gap: 10,
        }}
      >
        <span style={{ color: T.textSecondary, fontSize: 13, padding: '0 8px', textAlign: 'center' }}>
          {error || emptyText}
        </span>
        {onRegenerate ? (
          <button
            // 原生 <button> 的默认 type 是 submit：本组件会被放进 antd <Form>（内容包编辑器），
            // 不显式声明就会**把整个表单提交掉**（保存 + 关闭弹窗）。必须显式 type="button"。
            type="button"
            disabled={loading}
            onClick={onRegenerate}
            style={{
              height: 30,
              borderRadius: 999,
              border: 'none',
              background: 'linear-gradient(90deg, #7c3aed 0%, #a78bfa 100%)',
              color: '#fff',
              fontSize: 12,
              fontWeight: 500,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
              padding: '0 16px',
              transition: 'opacity 0.2s',
            }}
            onMouseEnter={(e) => { if (!loading) e.currentTarget.style.opacity = '0.9' }}
            onMouseLeave={(e) => { e.currentTarget.style.opacity = loading ? '0.6' : '1' }}
          >
            <ReloadOutlined style={{ fontSize: 11 }} />
            重试
          </button>
        ) : null}
      </div>
    )
  }

  const overlayButtonStyle = (disabled: boolean): React.CSSProperties => ({
    background: 'rgba(0,0,0,0.45)',
    borderRadius: '50%',
    width: 26,
    height: 26,
    padding: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#fff',
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    fontSize: 11,
    fontWeight: 500,
    transition: 'background 0.2s',
  })

  return (
    <div style={{ position: 'relative', width }}>
      <div
        style={{
          width: '100%',
          aspectRatio,
          borderRadius: T.radiusMD,
          overflow: 'hidden',
          background: T.bgElevated,
        }}
      >
        <Image src={url} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
      </div>
      <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 6 }}>
        {onRegenerate ? (
          <button
            // 同上：放进 <Form> 时必须显式 type="button"，否则会提交整个表单。
            type="button"
            disabled={loading}
            onClick={onRegenerate}
            style={overlayButtonStyle(loading)}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.65)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.45)' }}
            title={regenerateTitle}
          >
            <ReloadOutlined style={{ fontSize: 11 }} />
          </button>
        ) : null}
        {onRemove ? (
          <button
            type="button"
            onClick={onRemove}
            style={overlayButtonStyle(false)}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.65)' }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.45)' }}
            title={removeTitle}
          >
            <DeleteOutlined style={{ fontSize: 11 }} />
          </button>
        ) : null}
      </div>
    </div>
  )
}
