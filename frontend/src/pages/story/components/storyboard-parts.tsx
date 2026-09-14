/**
 * 创作项目工作台：components/storyboard-parts.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { listAssets } from '../../../api'
import { useTheme } from '../../../constants/theme'
import { WorkbenchSection } from './common'
import { inlineImageShellStyle, referenceAssetCardStyle, referenceAssetPlaceholderStyle } from '../styles'
import { AssetSummary, CharacterReferenceSummary, InlineGeneratedImage, ProjectAssetLink, StoryboardReferenceSummary } from '../types'
import { REFERENCE_LINK_ROLES, assetFileUrl, buildStoryboardPanelReferencePlan, dedupeStrings, referenceRoleOptions } from '../utils'
import { PictureOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Empty, Image, Input, List, Segmented, Select, Skeleton, Space, Tag, Tooltip, Typography, message } from 'antd'
import { useState } from 'react'

const { Text, Title, Paragraph } = Typography

export function InlineImageResult({
  image,
  loading,
  taskId,
  onPromoteReference,
}: {
  image?: InlineGeneratedImage
  loading: boolean
  taskId?: string
  onPromoteReference?: (role: string) => void
}) {
  if (loading) {
    return (
      <div style={inlineImageShellStyle}>
        <Skeleton.Image active style={{ width: 168, height: 112 }} />
        <Space direction="vertical" size={4}>
          <Text strong>正在生成图片</Text>
          <Text type="secondary">完成后会显示在这里，并同步关联到项目素材。</Text>
          {taskId ? <Text type="secondary" copyable style={{ fontSize: 12 }}>任务 {taskId}</Text> : null}
        </Space>
      </div>
    )
  }

  const src = assetFileUrl(image?.url || image?.localPath)
  if (!image || !src) return null
  const referenceImages = image.referenceImages || []

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <div style={inlineImageShellStyle}>
        <Image
          src={src}
          width={168}
          height={112}
          style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
        />
        <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
          <Text strong>已生成图片</Text>
          <Text type="secondary" ellipsis={{ tooltip: image.prompt }}>
            {image.model || image.provider || 'image'}
          </Text>
          <Space size={4} wrap>
            {image.assetId ? <Tag color="green">已入项目素材</Tag> : <Tag>本次结果</Tag>}
            {taskId ? <Tag color="blue">异步任务</Tag> : null}
            {referenceImages.length ? (
              <Tag color={image.referenceImagesSupported ? 'blue' : 'default'}>
                参考图 {image.referenceImagesSent || 0}/{referenceImages.length}
              </Tag>
            ) : null}
          </Space>
          {image.assetId && onPromoteReference ? (
            <Space.Compact size="small">
              <Button size="small" onClick={() => onPromoteReference('reference')}>
                设为参考
              </Button>
              <Select
                size="small"
                defaultValue="reference"
                style={{ width: 92 }}
                options={referenceRoleOptions}
                onChange={(role) => onPromoteReference(role)}
              />
            </Space.Compact>
          ) : null}
          {taskId ? (
            <Button size="small" href={`/tasks?task_id=${encodeURIComponent(taskId)}`}>
              查看任务详情
            </Button>
          ) : null}
        </Space>
      </div>
      {referenceImages.length ? (
        <div>
          <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
            本次参考图集合
          </Text>
          <Image.PreviewGroup>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {referenceImages.map((item, index) => (
                <Tooltip
                  key={`${item.url}-${index}`}
                  title={`${item.label || item.source}${item.role ? ` · ${item.role}` : ''}`}
                >
                  <Image
                    src={assetFileUrl(item.url)}
                    width={48}
                    height={48}
                    style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
                  />
                </Tooltip>
              ))}
            </div>
          </Image.PreviewGroup>
        </div>
      ) : null}
    </Space>
  )
}

export function ReferenceAssetPreviewStrip({
  assetIds,
  assets,
  assetDetails,
  notes = [],
}: {
  assetIds?: string[]
  assets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  notes?: string[]
}) {
  const ids = dedupeStrings(assetIds || [])
  if (!ids.length) return null
  const linksByAssetId = new Map(assets.map((asset) => [asset.asset_id, asset]))
  return (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <Space size={4} wrap>
        <Tag color="blue">参考卡 {ids.length}</Tag>
        {(notes || []).slice(0, 3).map((note, index) => (
          <Tag key={`${note}-${index}`}>{note}</Tag>
        ))}
      </Space>
      <Image.PreviewGroup>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {ids.map((assetId) => {
            const link = linksByAssetId.get(assetId)
            const detail = assetDetails[assetId]
            const preview = assetFileUrl(detail?.thumbnail_url || detail?.cover_url || detail?.source_url || detail?.file_path)
            const roleLabel = referenceRoleOptions.find((item) => item.value === link?.role)?.label || link?.role || '参考'
            const label = link?.metadata?.label || link?.metadata?.character_name || link?.metadata?.source_title || detail?.title || assetId
            return (
              <Tooltip key={assetId} title={`${roleLabel} · ${label}`}>
                {preview ? (
                  <Image
                    src={preview}
                    width={48}
                    height={48}
                    style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
                  />
                ) : (
                  <Tag>{label}</Tag>
                )}
              </Tooltip>
            )
          })}
        </div>
      </Image.PreviewGroup>
    </Space>
  )
}

export function StoryboardReferencePreflight({
  summary,
  supportsReferenceImages,
  hasImageModel,
}: {
  summary: StoryboardReferenceSummary
  supportsReferenceImages: boolean
  hasImageModel: boolean
}) {
  const { theme } = useTheme()
  if (!summary.promptPanels) return null

  const warnings = [
    !hasImageModel ? '未选择默认生图模型' : '',
    !supportsReferenceImages ? '当前模型不会上传参考图，只记录参考关系' : '',
    summary.missingEffectivePlanPanels ? `${summary.missingEffectivePlanPanels} 个分镜缺少角色/参考卡规划` : '',
    summary.noUsableReferencePanels ? `${summary.noUsableReferencePanels} 个分镜没有可发送参考图` : '',
    summary.unresolvedCharacterIds.length ? `${summary.unresolvedCharacterIds.length} 个角色资料待加载` : '',
  ].filter(Boolean)

  return (
    <div
      style={{
        border: `1px solid ${warnings.length ? theme.warning : theme.borderLight}`,
        background: theme.bgPage,
        borderRadius: 8,
        padding: 10,
      }}
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space size={4} wrap>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>分镜 {summary.promptPanels}</Tag>
          <Tag color={summary.effectivePlanPanels === summary.promptPanels ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
            有效参考 {summary.effectivePlanPanels}/{summary.promptPanels}
          </Tag>
          <Tag color={summary.usableReferencePanels === summary.promptPanels ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
            可用参考图 {summary.usableReferencePanels}/{summary.promptPanels}
          </Tag>
          <Tag color={summary.sentReferenceImages ? 'green' : supportsReferenceImages ? 'orange' : 'default'} style={{ marginInlineEnd: 0 }}>
            实际发送 {summary.sentReferenceImages}
          </Tag>
          <Tag color={summary.uniqueReferenceImages ? 'cyan' : 'default'} style={{ marginInlineEnd: 0 }}>
            去重参考图 {summary.uniqueReferenceImages}
          </Tag>
          <Tag color={summary.uniqueCharacterIds.length ? 'purple' : 'default'} style={{ marginInlineEnd: 0 }}>
            角色 {summary.uniqueCharacterIds.length}
          </Tag>
          <Tag color="green" style={{ marginInlineEnd: 0 }}>已生图 {summary.generatedPanels}</Tag>
        </Space>
        {warnings.length ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {warnings.join('；')}。可以先补角色基准图、手动选择参考卡，或点击“匹配参考卡”后再批量生图。
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            本话分镜已有可发送参考图，批量生图会把角色/项目参考一起带入请求。
          </Text>
        )}
      </Space>
    </div>
  )
}

export function StoryboardReferenceDiagnostics({
  panel,
  projectAssets,
  characterDetails,
  supportsReferenceImages,
}: {
  panel: any
  projectAssets: ProjectAssetLink[]
  characterDetails: Record<string, CharacterReferenceSummary>
  supportsReferenceImages: boolean
}) {
  const { theme } = useTheme()
  const plan = buildStoryboardPanelReferencePlan({
    panel,
    projectAssets,
    characterDetails,
    supportsReferenceImages,
  })
  const unresolvedCharacters = plan.unresolvedCharacterIds.length

  return (
    <div style={{
      border: `1px solid ${theme.borderLight}`,
      background: theme.bgPage,
      borderRadius: 8,
      padding: 8,
      marginTop: 6,
    }}>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space size={4} wrap>
          <Tag color={plan.characterIds.length ? 'purple' : 'default'} style={{ marginInlineEnd: 0 }}>
            角色 {plan.characterIds.length}
          </Tag>
          <Tag color={plan.referenceAssetIds.length ? 'blue' : 'default'} style={{ marginInlineEnd: 0 }}>
            项目卡 {plan.referenceAssetIds.length}
          </Tag>
          <Tag color={plan.portraitNodeIds.length ? 'cyan' : 'default'} style={{ marginInlineEnd: 0 }}>
            立绘节点 {plan.portraitNodeIds.length}
          </Tag>
          <Tag color={plan.imageCollection.length ? 'green' : 'orange'} style={{ marginInlineEnd: 0 }}>
            可用参考图 {plan.imageCollection.length}
          </Tag>
          <Tag color={plan.sentCount ? 'green' : supportsReferenceImages ? 'orange' : 'default'} style={{ marginInlineEnd: 0 }}>
            实际发送 {plan.sentCount}
          </Tag>
          {unresolvedCharacters ? (
            <Tag color="orange" style={{ marginInlineEnd: 0 }}>角色资料加载中 {unresolvedCharacters}</Tag>
          ) : null}
        </Space>
        {plan.imageCollection.length ? (
          <Image.PreviewGroup>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {plan.imageCollection.map((item, index) => (
                <Tooltip
                  key={`${item.url}-${index}`}
                  title={`${item.label || item.source}${item.character_name ? ` · ${item.character_name}` : ''}`}
                >
                  <Image
                    src={assetFileUrl(item.url)}
                    width={42}
                    height={42}
                    style={{ objectFit: 'cover', borderRadius: 6, border: `1px solid ${theme.borderLight}` }}
                  />
                </Tooltip>
              ))}
            </div>
          </Image.PreviewGroup>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            暂无可发送参考图。可先同步角色、设置身份基准图，或点击“匹配参考卡”。
          </Text>
        )}
      </Space>
    </div>
  )
}

export function StoryboardVideoOutputStrip({
  links,
  assetDetails,
}: {
  links: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
}) {
  if (!links.length) return null

  return (
    <div
      style={{
        display: 'grid',
        gap: 8,
        marginTop: 8,
        paddingTop: 8,
        borderTop: '1px solid var(--borderLight)',
      }}
    >
      <Text strong style={{ fontSize: 12 }}>本格已生成视频 · {links.length}</Text>
      {links.map((link) => {
        const metadata = link.metadata || {}
        const detail = assetDetails[link.asset_id]
        const source = assetFileUrl(detail?.file_path || detail?.source_url || detail?.cover_url || '')
        const duration = Number(metadata.duration)
        return (
          <div
            key={link.id}
            style={{
              display: 'grid',
              gridTemplateColumns: source ? '168px minmax(0, 1fr)' : '1fr',
              gap: 10,
              alignItems: 'start',
            }}
          >
            {source ? (
              <video
                controls
                preload="metadata"
                src={source}
                style={{ width: 168, maxWidth: '100%', height: 96, objectFit: 'cover', borderRadius: 6, background: '#10121a' }}
              />
            ) : (
              <Skeleton.Image active style={{ width: 168, height: 96 }} />
            )}
            <Space direction="vertical" size={4} style={{ minWidth: 0 }}>
              <Text ellipsis={{ tooltip: detail?.title || metadata.source_title || link.asset_id }}>
                {detail?.title || metadata.source_title || '分镜视频'}
              </Text>
              <Space size={4} wrap>
                <Tag color="green">已入项目素材</Tag>
                {(metadata.model || metadata.provider) ? <Tag>{metadata.model || metadata.provider}</Tag> : null}
                {Number.isFinite(duration) && duration > 0 ? <Tag>{duration}s</Tag> : null}
                {metadata.task_id ? <Tag color="blue">任务 {String(metadata.task_id).slice(0, 8)}</Tag> : null}
              </Space>
              <Space size={4} wrap>
                <Button size="small" href={`/video-gen?project_id=${encodeURIComponent(link.project_id)}&content_id=${encodeURIComponent(link.content_id || '')}&source_type=storyboard_panel&source_index=${encodeURIComponent(String(metadata.source_index || ''))}`}>
                  打开视频生成
                </Button>
                <Button size="small" href={`/assets?asset_id=${encodeURIComponent(link.asset_id)}`}>
                  查看素材
                </Button>
              </Space>
            </Space>
          </div>
        )
      })}
    </div>
  )
}

export function ReferenceAssetCard({
  link,
  asset,
}: {
  link: ProjectAssetLink
  asset?: AssetSummary
}) {
  const roleLabel = referenceRoleOptions.find((item) => item.value === link.role)?.label || link.role
  const preview = assetFileUrl(asset?.thumbnail_url || asset?.cover_url || asset?.source_url || asset?.file_path)
  const title = link.metadata?.label || link.metadata?.character_name || asset?.title || link.asset_id
  const roleColor = link.role === 'character'
    ? 'green'
    : link.role === 'style'
      ? 'purple'
      : link.role === 'world'
        ? 'gold'
        : 'blue'

  return (
    <div style={referenceAssetCardStyle}>
      {preview ? (
        <Image
          src={preview}
          width={52}
          height={52}
          preview={false}
          style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid var(--borderLight)' }}
        />
      ) : (
        <div style={referenceAssetPlaceholderStyle}>
          <PictureOutlined />
        </div>
      )}
      <Space direction="vertical" size={3} style={{ minWidth: 0, flex: 1 }}>
        <Space size={4} wrap>
          <Tag color={roleColor}>{roleLabel}</Tag>
          {link.metadata?.character_name ? <Tag>{link.metadata.character_name}</Tag> : null}
        </Space>
        <Text strong ellipsis={{ tooltip: title }}>
          {title}
        </Text>
        <Text type="secondary" copyable ellipsis={{ tooltip: link.asset_id }} style={{ fontSize: 12 }}>
          {link.asset_id}
        </Text>
      </Space>
    </div>
  )
}

export function ReferenceCardsPanel({
  assets,
  assetDetails,
  loading,
  onLinkAsset,
}: {
  assets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  loading: boolean
  onLinkAsset: (assetId: string, role: string, metadata?: Record<string, any>) => void
}) {
  const [assetId, setAssetId] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<AssetSummary[]>([])
  const [role, setRole] = useState('character')
  const [label, setLabel] = useState('')
  const [characterName, setCharacterName] = useState('')
  const [referenceFilter, setReferenceFilter] = useState('all')
  const referenceAssets = assets.filter((asset) =>
    (REFERENCE_LINK_ROLES as readonly string[]).includes(asset.role),
  )
  const visibleReferenceAssets = referenceFilter === 'all'
    ? referenceAssets
    : referenceAssets.filter((asset) => asset.role === referenceFilter)
  const buildMetadata = (source?: AssetSummary) => ({
    label: label.trim() || source?.title || '',
    character_name: role === 'character' ? characterName.trim() || label.trim() || source?.title || '' : '',
    source_title: source?.title || '',
    source_type: source?.type || '',
    linked_from: 'story_workbench_reference_card',
  })
  const linkAsset = (id: string, source?: AssetSummary) => {
    if (!id.trim()) return
    onLinkAsset(id.trim(), role, buildMetadata(source))
    setAssetId('')
    setLabel('')
    setCharacterName('')
  }
  const searchAssets = async () => {
    setSearching(true)
    try {
      const response = await listAssets({
        search: searchKeyword.trim() || undefined,
        page_size: 12,
      })
      setSearchResults(response?.data || [])
    } catch (error: any) {
      message.error(error?.message || '搜索素材失败')
    } finally {
      setSearching(false)
    }
  }

  return (
    <WorkbenchSection
      title="项目参考卡"
      extra={
        <Tag color={referenceAssets.length ? 'blue' : 'default'}>
          {referenceAssets.length} 个
        </Tag>
      }
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Segmented
          size="small"
          value={referenceFilter}
          onChange={(value) => setReferenceFilter(String(value))}
          options={[
            { label: `全部 ${referenceAssets.length}`, value: 'all' },
            ...referenceRoleOptions.map((item) => ({
              label: `${item.label.replace('参考', '')} ${referenceAssets.filter((asset) => asset.role === item.value).length}`,
              value: item.value,
            })),
          ]}
          style={{ maxWidth: '100%' }}
        />
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={searchKeyword}
            onChange={(event) => setSearchKeyword(event.target.value)}
            onPressEnter={searchAssets}
            placeholder="搜索素材库：角色名 / 背景 / 画风 / 分镜图"
          />
          <Button loading={searching} onClick={searchAssets}>
            搜索
          </Button>
        </Space.Compact>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="参考名称：如 萧然立绘 / 夜晚办公室 / 统一漫画风格"
          />
          <Input
            value={characterName}
            disabled={role !== 'character'}
            onChange={(event) => setCharacterName(event.target.value)}
            placeholder="角色名"
            style={{ width: 160 }}
          />
          <Select
            value={role}
            onChange={setRole}
            style={{ width: 120 }}
            options={referenceRoleOptions}
          />
        </Space.Compact>
        {searchResults.length ? (
          <List
            size="small"
            dataSource={searchResults}
            renderItem={(asset) => {
              const preview = assetFileUrl(asset.thumbnail_url || asset.cover_url || asset.source_url || asset.file_path)
              return (
                <List.Item
                  actions={[
                    <Button
                      key="link"
                      size="small"
                      icon={<PlusOutlined />}
                      loading={loading}
                      onClick={() => linkAsset(asset.id, asset)}
                    >
                      关联
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={
                      preview ? (
                        <Image
                          src={preview}
                          width={44}
                          height={44}
                          preview={false}
                          style={{ objectFit: 'cover', borderRadius: 6 }}
                        />
                      ) : null
                    }
                    title={<Text ellipsis={{ tooltip: asset.title }}>{asset.title || asset.id}</Text>}
                    description={
                      <Space size={4} wrap>
                        {asset.type ? <Tag>{asset.type}</Tag> : null}
                        {(asset.tags || []).slice(0, 3).map((tag) => (
                          <Tag key={tag}>{tag}</Tag>
                        ))}
                      </Space>
                    }
                  />
                </List.Item>
              )
            }}
          />
        ) : null}
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={assetId}
            onChange={(event) => setAssetId(event.target.value)}
            placeholder="素材 asset_id：角色卡 / 背景 / 画风参考"
          />
          <Select
            value={role}
            onChange={setRole}
            style={{ width: 120 }}
            options={referenceRoleOptions}
          />
          <Button
            type="primary"
            loading={loading}
            onClick={() => {
              linkAsset(assetId)
            }}
          >
            关联
          </Button>
        </Space.Compact>
        <Text type="secondary">
          角色卡、背景和画风参考会作为漫画生成的一致性资产入口；当前先建立项目关联，后续生成提示会读取这些参考。
        </Text>
        {visibleReferenceAssets.length ? (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {visibleReferenceAssets.map((asset) => (
              <ReferenceAssetCard key={asset.id} link={asset} asset={assetDetails[asset.asset_id]} />
            ))}
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={referenceAssets.length ? '这个分类暂无参考卡' : '暂无参考卡'} />
        )}
      </Space>
    </WorkbenchSection>
  )
}

