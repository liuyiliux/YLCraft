import { useState } from 'react'
import { Typography } from 'antd'
import { groupVisualProfile, META_FIELDS, REFERENCE_IMAGE_FIELDS, hasContent, isImageUrl, toDisplayText, visualProfileFieldLabel } from './visualProfileSchema'
import { browserAssetUrl } from './utils'

const { Text, Paragraph } = Typography

/** 超过该字符数的值默认折叠为 2 行，避免卡片高度失控 */
const CLAMP_THRESHOLD = 90

interface VisualProfilePanelProps {
  /** character.identity.visual_profile 原始对象 */
  profile: Record<string, any>
}

/**
 * 视觉档案分组卡片。
 *
 * 替代此前把整个对象交给 displayValue 展平成「key：value」纯文本的做法，
 * 改为按语义分组（头部 / 身形 / 服装 / 配饰 / 表现 / 风格约束）渲染，
 * AI 回填的未知字段自动归入「其他」，保证信息不丢且不再出现英文原始键。
 */
export default function VisualProfilePanel({ profile }: VisualProfilePanelProps) {
  const groups = groupVisualProfile(profile)
  const referenceUrls = collectReferenceUrls(profile)
  const metaEntries = Object.entries(profile || {}).filter(([key, value]) => META_FIELDS.has(key) && hasContent(value))

  if (!groups.length && !referenceUrls.length && !metaEntries.length) {
    return <Text className="cd-empty">暂无视觉档案</Text>
  }

  return (
    <div className="cd-vp">
      {groups.length ? (
        <div className="cd-vp-grid">
          {groups.map((group) => (
            <section key={group.key} className="cd-vp-card">
              <div className="cd-vp-card-title">{group.label}</div>
              <div className="cd-vp-fields">
                {group.fields.map((field) => (
                  <ProfileField key={field.key} label={field.label} value={field.value} />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : null}

      {referenceUrls.length ? (
        <section className="cd-vp-refs">
          <div className="cd-vp-card-title">参考图</div>
          <div className="cd-vp-thumbs">
            {referenceUrls.map((url) => (
              <a key={url} href={browserAssetUrl(url)} target="_blank" rel="noreferrer" className="cd-vp-thumb" title={String(url)}>
                <img src={browserAssetUrl(url)} alt="" loading="lazy" />
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {metaEntries.length ? (
        <div className="cd-vp-meta">
          {metaEntries.map(([key, value]) => (
            <Text key={key} className="cd-vp-meta-item">
              {visualProfileFieldLabel(key)}：{toDisplayText(value)}
            </Text>
          ))}
        </div>
      ) : null}
    </div>
  )
}

/** 单个字段：标签固定宽度 + 值，超长默认折叠 2 行，可展开与复制 */
function ProfileField({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false)
  const text = toDisplayText(value)
  const clampable = text.length > CLAMP_THRESHOLD

  return (
    <div className="cd-vp-field">
      <div className="cd-vp-field-label">
        <span title={label}>{label}</span>
      </div>
      <div className="cd-vp-field-value">
        <Paragraph
          className={clampable && !open ? 'cd-vp-clamped' : undefined}
          copyable={text ? { tooltips: ['复制', '已复制'] } : false}
          style={{ margin: 0 }}
        >
          {text || '未设置'}
        </Paragraph>
        {clampable ? (
          <button type="button" className="cd-vp-toggle" onClick={() => setOpen(!open)}>
            {open ? '收起' : '展开'}
          </button>
        ) : null}
      </div>
    </div>
  )
}

/** 收集需要以缩略图呈现的参考图地址，去重后返回 */
function collectReferenceUrls(profile: Record<string, any>): string[] {
  if (!profile || typeof profile !== 'object') return []
  const raw: unknown[] = []
  for (const key of REFERENCE_IMAGE_FIELDS) {
    const value = profile[key]
    if (Array.isArray(value)) raw.push(...value)
    else if (value) raw.push(value)
  }
  return Array.from(new Set(raw.filter(isImageUrl).map((url) => String(url).trim()))).filter(Boolean)
}
