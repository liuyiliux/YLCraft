/**
 * 创作项目工作台：components/chapter-studio.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { getCreativeProjectWritingPreflight } from '../../../api'
import { useTheme, type ThemeColors } from '../../../constants/theme'
import { ChapterPlan, ChapterPlanItem, WritingMethodCandidate, WritingPreflight } from '../../../types/api'
import { EditorField, InfoBlock, InfoListBlock, PromptTemplateSelect, ResizeHandle, WorkbenchSection } from './common'
import { InlineImageResult, ReferenceAssetPreviewStrip, ReferenceCardsPanel, StoryboardReferenceDiagnostics, StoryboardReferencePreflight, StoryboardVideoOutputStrip } from './storyboard-parts'
import { createCompactBlockStyle, createWorkbenchHeaderStyle } from '../styles'
import { AssetSummary, ChapterAction, CharacterReferenceSummary, EditableChapterPlanItem, ImagePromptContext, InlineGeneratedImage, NarrativeForeshadowing, NarrativeHealth, ProjectAssetLink, ProjectContent, ProjectContentSummary, TemplateOption, VideoGenerationContext } from '../types'
import { REFERENCE_LINK_ROLES, buildChapterPlanMarkdown, buildScriptMarkdown, buildStoryboardMarkdown, buildStoryboardPanelReferencePlan, buildStoryboardReferenceSummary, buildStoryboardVideoFallbackPrompt, comicStyleOptions, dedupeStrings, downloadTextFile, imageContextKey, isChapterLocked, linesToList, listToLines, normalizeChapterItem, normalizeChapterPlan, openProjectTextPreview, projectMarkdownFilename, referenceRoleOptions } from '../utils'
import { BranchesOutlined, BulbOutlined, CheckCircleOutlined, CloudUploadOutlined, DeleteOutlined, DeploymentUnitOutlined, DownloadOutlined, ExclamationCircleOutlined, EyeOutlined, FileTextOutlined, FolderAddOutlined, PictureOutlined, PlusOutlined, ThunderboltOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { Button, Checkbox, Empty, Input, InputNumber, List, Popconfirm, Segmented, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import React, { useEffect, useMemo, useState } from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function ChapterRail({
  theme,
  chapters,
  activeChapterNumber,
  contents,
  writerRoomSummary,
  ledger,
  health,
  onChapterChange,
}: {
  theme: ThemeColors
  chapters: ChapterPlanItem[]
  activeChapterNumber: number
  contents: ProjectContent[]
  writerRoomSummary: ProjectContentSummary[]
  ledger: NarrativeForeshadowing[]
  health: NarrativeHealth | null
  onChapterChange: (chapterNumber: number) => void | Promise<void>
}) {
  const candidateTypes = new Set(['prose_draft', 'prose_humanized', 'prose_rewrite'])
  const healthIssuesByChapter = useMemo(() => {
    const result = new Map<number, NarrativeHealth['issues']>()
    for (const issue of health?.issues || []) {
      const details = issue.details || {}
      const values = [
        details.chapter_number,
        ...(Array.isArray(details.chapter_numbers) ? details.chapter_numbers : []),
      ]
      for (const value of values) {
        const chapterNumber = Number(value)
        if (!Number.isInteger(chapterNumber) || chapterNumber < 1) continue
        result.set(chapterNumber, [...(result.get(chapterNumber) || []), issue])
      }
    }
    return result
  }, [health])

  const chapterRows = useMemo(() => chapters
    .map((chapter) => {
      const chapterNumber = Number(chapter.chapter_number)
      const approved = contents.some((item) => item.content_type === 'novel_body' && Number(item.chapter_number || item.episode_number) === chapterNumber)
      const candidateCount = writerRoomSummary.filter((item) => candidateTypes.has(item.content_type) && Number(item.chapter_number || item.episode_number) === chapterNumber).length
      const reviewed = writerRoomSummary.some((item) => item.content_type === 'prose_review' && Number(item.chapter_number || item.episode_number) === chapterNumber)
      const ledgerCount = ledger.filter((item) => item.planted_chapter === chapterNumber && !['ignored', 'superseded'].includes(item.status)).length
      const issues = healthIssuesByChapter.get(chapterNumber) || []
      return { chapter, chapterNumber, approved, candidateCount, reviewed, ledgerCount, issues }
    })
    .filter((row) => Number.isInteger(row.chapterNumber) && row.chapterNumber > 0)
    .sort((left, right) => left.chapterNumber - right.chapterNumber), [chapters, contents, writerRoomSummary, ledger, healthIssuesByChapter])

  const healthColor = health?.status === 'blocked' ? '#cf1322' : health?.status === 'attention' ? '#d46b08' : '#389e0d'
  const healthLabel = health?.status === 'blocked' ? '需要处理' : health?.status === 'attention' ? '有待处理项' : '健康'

  return (
    <section style={{ marginTop: 'auto', borderTop: `1px solid ${theme.border}`, minHeight: 0 }} aria-label="章节轨">
      <div style={{ padding: '12px 16px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Space size={7}>
          <FileTextOutlined style={{ color: theme.primary }} />
          <Text strong>章节轨</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{chapterRows.length}</Text>
        </Space>
        <Tooltip title={health ? `${healthLabel}：${health?.summary?.issue_count || 0} 项` : '正在读取健康检查'}>
          <span style={{ display: 'inline-flex', alignItems: 'center', color: healthColor }}>
            {health?.status === 'healthy' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
          </span>
        </Tooltip>
      </div>
      {chapterRows.length ? (
        <div style={{ maxHeight: 350, overflowY: 'auto', padding: '0 8px 10px' }}>
          {chapterRows.map((row) => {
            const isActive = row.chapterNumber === activeChapterNumber
            const statusMarkers = [
              { key: 'plan', label: '已规划', color: theme.primary, visible: true },
              { key: 'approved', label: '正式正文', color: '#389e0d', visible: row.approved },
              { key: 'candidate', label: `${row.candidateCount} 个正文候选`, color: '#722ed1', visible: row.candidateCount > 0 },
              { key: 'review', label: '已有主编审稿', color: '#13a8a8', visible: row.reviewed },
              { key: 'ledger', label: `${row.ledgerCount} 条伏笔记录`, color: '#d48806', visible: row.ledgerCount > 0 },
              { key: 'health', label: row.issues.map((issue) => issue.message).join('；'), color: '#cf1322', visible: row.issues.length > 0 },
            ].filter((marker) => marker.visible)
            return (
              <button
                key={row.chapterNumber}
                type="button"
                onClick={() => void onChapterChange(row.chapterNumber)}
                aria-current={isActive ? 'step' : undefined}
                style={{
                  appearance: 'none',
                  border: 0,
                  borderLeft: `2px solid ${isActive ? theme.primary : 'transparent'}`,
                  background: isActive ? theme.primaryAlpha(0.1) : 'transparent',
                  color: theme.textPrimary,
                  cursor: 'pointer',
                  display: 'block',
                  padding: '9px 8px 8px 10px',
                  textAlign: 'left',
                  width: '100%',
                }}
              >
                <div style={{ alignItems: 'baseline', display: 'flex', gap: 7, minWidth: 0 }}>
                  <Text strong style={{ color: theme.textPrimary, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>#{row.chapterNumber}</Text>
                  <Text ellipsis={{ tooltip: row.chapter.title }} style={{ color: theme.textPrimary, minWidth: 0 }}>{row.chapter.title || `第 ${row.chapterNumber} 章`}</Text>
                </div>
                <div style={{ alignItems: 'center', display: 'flex', gap: 5, marginTop: 6, minHeight: 8 }}>
                  {statusMarkers.map((marker) => (
                    <Tooltip key={marker.key} title={marker.label}>
                      <span
                        aria-label={marker.label}
                        style={{ background: marker.color, borderRadius: '50%', display: 'inline-block', height: 6, width: 6 }}
                      />
                    </Tooltip>
                  ))}
                </div>
              </button>
            )
          })}
        </div>
      ) : (
        <div style={{ padding: '4px 16px 16px' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>生成章节规划后，会在这里展示写作与审阅状态。</Text>
        </div>
      )}
    </section>
  )
}

export function ChapterTab({
  chapterPlan,
  chapters,
  hasOutline,
  hasChapterPlan,
  chapterColumns,
  chapterCount,
  setChapterCount,
  comicPageCount,
  setComicPageCount,
  chapterTemplateOptions,
  selectedChapterTemplateId,
  onChapterTemplateChange,
  scriptTemplateOptions,
  selectedScriptTemplateId,
  onScriptTemplateChange,
  chapterOutlineTemplateOptions,
  selectedChapterOutlineTemplateId,
  onChapterOutlineTemplateChange,
  novelBodyTemplateOptions,
  selectedNovelBodyTemplateId,
  onNovelBodyTemplateChange,
  comicPagesTemplateOptions,
  selectedComicPagesTemplateId,
  onComicPagesTemplateChange,
  loading,
  saving,
  onGenerate,
  onSave,
}: {
  chapterPlan: ChapterPlan
  chapters: ChapterPlanItem[]
  hasOutline: boolean
  hasChapterPlan: boolean
  chapterColumns: any[]
  chapterCount: number
  setChapterCount: (value: number) => void
  comicPageCount: number
  setComicPageCount: (value: number) => void
  chapterTemplateOptions: TemplateOption[]
  selectedChapterTemplateId?: string
  onChapterTemplateChange: (value: string) => void
  scriptTemplateOptions: TemplateOption[]
  selectedScriptTemplateId?: string
  onScriptTemplateChange: (value: string) => void
  chapterOutlineTemplateOptions: TemplateOption[]
  selectedChapterOutlineTemplateId?: string
  onChapterOutlineTemplateChange: (value: string) => void
  novelBodyTemplateOptions: TemplateOption[]
  selectedNovelBodyTemplateId?: string
  onNovelBodyTemplateChange: (value: string) => void
  comicPagesTemplateOptions: TemplateOption[]
  selectedComicPagesTemplateId?: string
  onComicPagesTemplateChange: (value: string) => void
  loading: boolean
  saving: boolean
  onGenerate: (options?: { preserveLocked?: boolean }) => void
  onSave: (chapterPlan: ChapterPlan) => Promise<void>
}) {
  const [rows, setRows] = useState<EditableChapterPlanItem[]>([])
  const [jsonDraft, setJsonDraft] = useState('')
  const [jsonError, setJsonError] = useState('')

  useEffect(() => {
    const nextRows = chapters.map((item) => ({ ...normalizeChapterItem(item), is_locked: isChapterLocked(item) }))
    setRows(nextRows)
    setJsonDraft(JSON.stringify(normalizeChapterPlan({ ...chapterPlan, chapters: nextRows }), null, 2))
    setJsonError('')
  }, [chapterPlan, chapters])

  const updateRow = (index: number, patch: Partial<EditableChapterPlanItem>) => {
    setRows((prev) => prev.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)))
  }

  const saveRows = () => onSave({ ...chapterPlan, chapter_count: rows.length, chapters: rows.map(normalizeChapterItem) })

  const addRow = () => {
    const nextNumber = rows.reduce((max, item) => Math.max(max, Number(item.chapter_number || 0)), 0) + 1
    setRows((prev) => [
      ...prev,
      {
        chapter_number: nextNumber,
        title: `第 ${nextNumber} 章`,
        goal: '',
        conflict: '',
        key_events: [],
        character_focus: [],
        ending_hook: '',
        status: 'draft',
      },
    ])
  }

  const deleteRow = (index: number) => {
    setRows((prev) => prev.filter((_, itemIndex) => itemIndex !== index))
  }

  const saveJson = async () => {
    try {
      const parsed = normalizeChapterPlan(JSON.parse(jsonDraft || '{}'))
      setJsonError('')
      setRows((parsed.chapters || []).map((item) => ({ ...item, is_locked: isChapterLocked(item) })))
      await onSave(parsed)
    } catch (error: any) {
      setJsonError(error?.message || 'JSON 格式不正确')
    }
  }

  const editorColumns = [
    {
      title: '锁',
      width: 68,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Checkbox
          checked={isChapterLocked(record)}
          onChange={(event) => updateRow(index, { is_locked: event.target.checked, status: event.target.checked ? 'locked' : 'draft' })}
        />
      ),
    },
    {
      title: '章',
      width: 90,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <InputNumber
          min={1}
          value={record.chapter_number}
          onChange={(value) => updateRow(index, { chapter_number: Number(value || index + 1) })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '标题 / 尾钩',
      width: 260,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Input value={record.title} onChange={(event) => updateRow(index, { title: event.target.value })} placeholder="章节标题" />
          <TextArea
            value={record.ending_hook}
            onChange={(event) => updateRow(index, { ending_hook: event.target.value })}
            placeholder="章末钩子"
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Space>
      ),
    },
    {
      title: '目标 / 冲突',
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <TextArea value={record.goal} onChange={(event) => updateRow(index, { goal: event.target.value })} placeholder="本章目标" autoSize={{ minRows: 2, maxRows: 5 }} />
          <TextArea value={record.conflict} onChange={(event) => updateRow(index, { conflict: event.target.value })} placeholder="本章冲突" autoSize={{ minRows: 2, maxRows: 5 }} />
        </Space>
      ),
    },
    {
      title: '事件 / 角色',
      width: 300,
      render: (_: unknown, record: EditableChapterPlanItem, index: number) => (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <TextArea
            value={listToLines(record.key_events)}
            onChange={(event) => updateRow(index, { key_events: linesToList(event.target.value) })}
            placeholder="关键事件，一行一条"
            autoSize={{ minRows: 3, maxRows: 6 }}
          />
          <TextArea
            value={listToLines(record.character_focus)}
            onChange={(event) => updateRow(index, { character_focus: linesToList(event.target.value) })}
            placeholder="焦点角色，一行一个"
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Space>
      ),
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, __: EditableChapterPlanItem, index: number) => (
        <Popconfirm title="删除这一章规划？" okText="删除" cancelText="取消" onConfirm={() => deleteRow(index)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space wrap>
          <Text strong>章节数量</Text>
          <InputNumber
            min={1}
            max={200}
            value={chapterCount}
            onChange={(value) => setChapterCount(Number(value || 12))}
          />
          <PromptTemplateSelect
            value={selectedChapterTemplateId}
            options={chapterTemplateOptions}
            placeholder="章节模板"
            onChange={onChapterTemplateChange}
          />
          <PromptTemplateSelect
            value={selectedScriptTemplateId}
            options={scriptTemplateOptions}
            placeholder="脚本模板"
            onChange={onScriptTemplateChange}
          />
        </Space>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          disabled={!hasOutline}
          loading={loading}
          onClick={() => onGenerate()}
        >
          {hasChapterPlan ? '重新生成章节' : '生成章节规划'}
        </Button>
      </Space>
      <Space wrap>
        <Space>
          <Text strong>漫画页数</Text>
          <InputNumber
            min={1}
            max={80}
            value={comicPageCount}
            onChange={(value) => setComicPageCount(Number(value || 10))}
          />
        </Space>
        <PromptTemplateSelect
          value={selectedChapterOutlineTemplateId}
          options={chapterOutlineTemplateOptions}
          placeholder="细纲模板"
          onChange={onChapterOutlineTemplateChange}
        />
        <PromptTemplateSelect
          value={selectedNovelBodyTemplateId}
          options={novelBodyTemplateOptions}
          placeholder="正文模板"
          onChange={onNovelBodyTemplateChange}
        />
        <PromptTemplateSelect
          value={selectedComicPagesTemplateId}
          options={comicPagesTemplateOptions}
          placeholder="漫画拆页模板"
          onChange={onComicPagesTemplateChange}
        />
      </Space>

      {!hasOutline ? (
        <Empty description="先生成故事大纲" />
      ) : !hasChapterPlan ? (
        <Empty description="暂无章节规划" />
      ) : (
        <Tabs
          items={[
            {
              key: 'edit',
              label: '章节规划编辑',
              children: (
                <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
                    <Space wrap>
                      <Tag color="blue">{rows.length} 章</Tag>
                      <Tag color={rows.some(isChapterLocked) ? 'green' : 'default'}>锁定 {rows.filter(isChapterLocked).length}</Tag>
                    </Space>
                    <Space wrap>
                      <Button icon={<PlusOutlined />} onClick={addRow}>新增章节</Button>
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={() => downloadTextFile('chapter-plan.md', buildChapterPlanMarkdown({ ...chapterPlan, chapters: rows }))}
                      >
                        导出 Markdown
                      </Button>
                      <Button loading={loading} onClick={() => onGenerate({ preserveLocked: true })}>保留现有并补齐</Button>
                      <Button type="primary" loading={saving} onClick={saveRows}>保存规划</Button>
                    </Space>
                  </Space>
                  <Table
                    rowKey={(record) => `${record.chapter_number}-${record.title || ''}`}
                    size="small"
                    columns={editorColumns}
                    dataSource={rows}
                    pagination={false}
                    scroll={{ x: 1120 }}
                  />
                </Space>
              ),
            },
            {
              key: 'json',
              label: 'JSON',
              children: (
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Text type="secondary">用于批量调整章节结构、导入外部规划或保留模型返回的扩展字段。</Text>
                  <TextArea
                    value={jsonDraft}
                    onChange={(event) => setJsonDraft(event.target.value)}
                    autoSize={{ minRows: 16, maxRows: 30 }}
                    style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' }}
                  />
                  {jsonError ? <Text type="danger">{jsonError}</Text> : null}
                  <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
                    <Button onClick={() => setJsonDraft(JSON.stringify(normalizeChapterPlan({ ...chapterPlan, chapters: rows }), null, 2))}>
                      同步编辑表
                    </Button>
                    <Button type="primary" loading={saving} onClick={saveJson}>保存 JSON</Button>
                  </Space>
                </Space>
              ),
            },
            {
              key: 'actions',
              label: '生产动作',
              children: (
                <Table
                  rowKey="chapter_number"
                  size="small"
                  columns={chapterColumns}
                  dataSource={rows}
                  pagination={false}
                />
              ),
            },
          ]}
        />
      )}
    </Space>
  )
}

export function EpisodeWorkbenchTab({
  projectId,
  chapters,
  activeChapterNumber,
  onActiveChapterChange,
  activeChapter,
  contentForChapter,
  isChapterActionLoading,
  comicPageCount,
  setComicPageCount,
  comicStyle,
  setComicStyle,
  columnWidths,
  setColumnWidths,
  startHorizontalResize,
  projectAssets,
  assetDetails,
  characterDetails,
  savingContentId,
  linkingAsset,
  onGenerateChapterOutline,
  onRegenerateChapterOutlineScenes,
  onGenerateNovelBody,
  onRefineNovelBody,
  onSaveContentAsAsset,
  onExtractContinuity,
  continuityExtracting,
  onOpenFanqiePublish,
  onGenerateScript,
  onGenerateStoryboard,
  onMatchReferenceAssets,
  referenceMatching,
  onBatchGenerateStoryboardImages,
  onSplitComicPages,
  onSaveContent,
  onUpdateStoryboardPanelReferences,
  onLinkReferenceAsset,
  onSendImagePrompt,
  onOpenVideoGeneration,
  onOpenPrevis,
  inlineImages,
  inlineImageLoadingKey,
  pendingImageTaskKey,
  pendingImageTaskId,
  batchStoryboardImageChapter,
  defaultImageModelName,
  defaultImageSupportsReferenceImages,
  selectedCreativeSkillIds,
  onCreativeSkillIdsChange,
  compact,
}: {
  projectId: string
  chapters: ChapterPlanItem[]
  activeChapterNumber: number
  onActiveChapterChange: (chapterNumber: number) => void
  activeChapter: ChapterPlanItem | null
  contentForChapter: (contentType: string, chapterNumber: number) => ProjectContent | undefined
  isChapterActionLoading: (action: ChapterAction, chapterNumber: number) => boolean
  comicPageCount: number
  setComicPageCount: (value: number) => void
  comicStyle: string
  setComicStyle: (value: string) => void
  columnWidths: { outline: number; prose: number }
  setColumnWidths: React.Dispatch<React.SetStateAction<{ outline: number; prose: number }>>
  startHorizontalResize: (
    event: React.MouseEvent,
    options: { initial: number; min: number; max: number; onChange: (value: number) => void },
  ) => void
  projectAssets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  characterDetails: Record<string, CharacterReferenceSummary>
  savingContentId: string | null
  linkingAsset: boolean
  onGenerateChapterOutline: (chapterNumber: number) => void
  onRegenerateChapterOutlineScenes: (chapterNumber: number) => void
  onGenerateNovelBody: (chapterNumber: number) => void
  onRefineNovelBody: (chapterNumber: number, instruction: string) => void
  onSaveContentAsAsset: (contentId: string) => void
  onExtractContinuity: (contentId: string) => void
  continuityExtracting: boolean
  onOpenFanqiePublish: () => void
  onGenerateScript: (chapterNumber: number) => void
  onGenerateStoryboard: (chapterNumber: number) => void
  onMatchReferenceAssets: (contentId: string) => void
  referenceMatching: boolean
  onBatchGenerateStoryboardImages: (chapterNumber: number) => void
  onSplitComicPages: (chapterNumber: number) => void
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => void
  onUpdateStoryboardPanelReferences: (
    contentId: string,
    panelNumber: number,
    referenceAssetIds: string[],
  ) => void
  onLinkReferenceAsset: (assetId: string, role: string, metadata?: Record<string, any>) => void
  onSendImagePrompt: (prompt: string, context?: ImagePromptContext) => void
  onOpenVideoGeneration: (prompt: string, context?: VideoGenerationContext) => void
  onOpenPrevis: (
    storyboardContentId: string,
    panelNumber: number,
    title?: string,
    options?: { draft?: boolean; queue?: number[] },
  ) => void
  inlineImages: Record<string, InlineGeneratedImage>
  inlineImageLoadingKey: string | null
  pendingImageTaskKey?: string
  pendingImageTaskId?: string
  batchStoryboardImageChapter: number | null
  defaultImageModelName: string
  defaultImageSupportsReferenceImages: boolean
  selectedCreativeSkillIds: string[]
  onCreativeSkillIdsChange: (skillIds: string[]) => void
  compact: boolean
}) {
  const chapterOutline = contentForChapter('chapter_outline', activeChapterNumber)
  const novelBody = contentForChapter('novel_body', activeChapterNumber)
  const script = contentForChapter('script', activeChapterNumber)
  const storyboard = contentForChapter('storyboard', activeChapterNumber)
  const comic = contentForChapter('comic_pages', activeChapterNumber)
  const { theme } = useTheme()
  const themedWorkbenchHeaderStyle = createWorkbenchHeaderStyle(theme)
  const themedCompactBlockStyle = createCompactBlockStyle(theme)
  /**
   * 批量初稿勾选的分镜号（tasks 6.12）。
   *
   * 放在**分镜卡片上勾选**而不是"整章一键"：批量初稿的语义是"逐格确认"，
   * 一次过整章会让人连着点十几次确认；让用户先圈出真正要过的那几格，
   * 其余留到需要时再单独生成。
   */
  const [previsBatchPanels, setPrevisBatchPanels] = useState<number[]>([])
  const [writingStage, setWritingStage] = useState<'chapter_outline' | 'novel_body' | 'novel_body_refine'>('novel_body')
  const [writingPreflight, setWritingPreflight] = useState<WritingPreflight | null>(null)
  const [writingPreflightLoading, setWritingPreflightLoading] = useState(false)
  const referenceAssetOptions = useMemo(
    () =>
      projectAssets
        .filter((asset) => (REFERENCE_LINK_ROLES as readonly string[]).includes(asset.role))
        .map((asset) => {
          const detail = assetDetails[asset.asset_id]
          const roleLabel = referenceRoleOptions.find((item) => item.value === asset.role)?.label || asset.role
          const title =
            asset.metadata?.label ||
            asset.metadata?.character_name ||
            asset.metadata?.source_title ||
            detail?.title ||
            asset.asset_id
          return {
            label: `${roleLabel} · ${title}`,
            value: asset.asset_id,
          }
        }),
    [projectAssets, assetDetails],
  )
  const [outlineDraft, setOutlineDraft] = useState<Record<string, any>>({})
  const [sceneDrafts, setSceneDrafts] = useState<any[]>([])
  const [novelDraft, setNovelDraft] = useState('')
  const [novelRefineInstruction, setNovelRefineInstruction] = useState('')
  const [comicDrafts, setComicDrafts] = useState<any[]>([])
  const [editingStoryboardPrompt, setEditingStoryboardPrompt] = useState<number | null>(null)
  const [storyboardPromptDraft, setStoryboardPromptDraft] = useState('')
  const writingStageMeta = useMemo(
    () =>
      ({
        chapter_outline: {
          label: '章节细纲',
          hint: '检查这一话的结构、场景和推进是否齐备。',
        },
        novel_body: {
          label: '正文',
          hint: '检查这一话的细纲与正文生成前置条件。',
        },
        novel_body_refine: {
          label: '正文润色',
          hint: '检查已有正文是否适合做定向改写。',
        },
      }) as const,
    [],
  )
  const storyboardVideoOutputs = useMemo(() => {
    if (!storyboard?.id) return new Map<number, ProjectAssetLink[]>()
    const outputs = new Map<number, ProjectAssetLink[]>()
    projectAssets.forEach((link) => {
      const metadata = link.metadata || {}
      const panelNumber = Number(metadata.source_index)
      if (
        link.role !== 'output' ||
        metadata.source !== 'video_generation' ||
        metadata.source_type !== 'storyboard_panel' ||
        link.content_id !== storyboard.id ||
        !Number.isFinite(panelNumber)
      ) {
        return
      }
      outputs.set(panelNumber, [...(outputs.get(panelNumber) || []), link])
    })
    return outputs
  }, [projectAssets, storyboard?.id])
  const writingMethodOptions = useMemo(() => {
    const merged = new Map<string, { label: string; value: string }>()
    ;(writingPreflight?.method_candidates || []).forEach((candidate: WritingMethodCandidate) => {
      merged.set(candidate.id, {
        label: `${candidate.title}${candidate.auto_apply ? ' · 自动' : ''}`,
        value: candidate.id,
      })
    })
    selectedCreativeSkillIds.forEach((skillId) => {
      if (!merged.has(skillId)) {
        merged.set(skillId, {
          label: `${skillId} · 已选`,
          value: skillId,
        })
      }
    })
    return Array.from(merged.values())
  }, [selectedCreativeSkillIds, writingPreflight?.method_candidates])
  const selectedWritingMethods = useMemo(() => {
    const candidateMap = new Map((writingPreflight?.method_candidates || []).map((item) => [item.id, item]))
    return selectedCreativeSkillIds.map((skillId) => candidateMap.get(skillId)).filter(Boolean)
  }, [selectedCreativeSkillIds, writingPreflight?.method_candidates])
  const writingPreflightChecks = writingPreflight?.checks || []
  const writingPreflightBlockers = writingPreflight?.blockers || []
  const writingPreflightReady = Boolean(writingPreflight?.ready)

  useEffect(() => {
    if (!projectId) {
      setWritingPreflight(null)
      setWritingPreflightLoading(false)
      return
    }

    const contentId =
      writingStage === 'novel_body_refine'
        ? novelBody?.id
        : writingStage === 'chapter_outline'
          ? chapterOutline?.id
          : undefined

    let cancelled = false
    setWritingPreflightLoading(true)
    ;(async () => {
      try {
        const response = await getCreativeProjectWritingPreflight(projectId, {
          chapterNumber: activeChapterNumber,
          stage: writingStage,
          contentId,
        })
        if (cancelled) return
        setWritingPreflight(response?.data || null)
      } catch {
        if (!cancelled) setWritingPreflight(null)
      } finally {
        if (!cancelled) setWritingPreflightLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [projectId, activeChapterNumber, chapterOutline?.id, novelBody?.id, writingStage])

  useEffect(() => {
    setOutlineDraft({
      title: chapterOutline?.data?.title || '',
      summary: chapterOutline?.data?.summary || '',
      objective: chapterOutline?.data?.objective || '',
      keywordsText: (chapterOutline?.data?.keywords || []).join('\n'),
      keyDialoguesText: (chapterOutline?.data?.key_dialogues || []).join('\n'),
      foreshadowingText: (chapterOutline?.data?.foreshadowing || []).join('\n'),
      ending_hook: chapterOutline?.data?.ending_hook || '',
      continuityNotesText: Array.isArray(chapterOutline?.data?.continuity_notes)
        ? chapterOutline?.data?.continuity_notes.join('\n')
        : chapterOutline?.data?.continuity_notes || '',
    })
    setSceneDrafts((chapterOutline?.data?.scenes || []).map((scene: any, index: number) => ({
      scene_number: scene.scene_number || index + 1,
      title: scene.title || '',
      location: scene.location || '',
      purpose: scene.purpose || '',
      scene_role: scene.scene_role || '',
      objective: scene.objective || '',
      conflict: scene.conflict || '',
      beatsText: (scene.beats || []).join('\n'),
      action: scene.action || '',
      key_dialogue: scene.key_dialogue || '',
      emotion: scene.emotion || '',
      emotional_turn: scene.emotional_turn || '',
      visual_focus: scene.visual_focus || '',
      shot_design: scene.shot_design || '',
      image_prompt: scene.image_prompt || '',
    })))
  }, [chapterOutline?.id, activeChapterNumber])

  useEffect(() => {
    setNovelDraft(novelBody?.text_content || novelBody?.data?.content || '')
  }, [novelBody?.id, activeChapterNumber])

  useEffect(() => {
    setEditingStoryboardPrompt(null)
    setStoryboardPromptDraft('')
  }, [storyboard?.id, activeChapterNumber])

  useEffect(() => {
    setComicDrafts((comic?.data?.pages || []).map((page: any, index: number) => ({
      page_number: page.page_number || index + 1,
      title: page.title || '',
      content: page.content || '',
      panel_count: page.panel_count || '',
      image_prompt: page.image_prompt || '',
      source_panel_numbers: page.source_panel_numbers || [],
      character_ids: page.character_ids || [],
      portrait_node_ids: page.portrait_node_ids || [],
      portrait_version_ids: page.portrait_version_ids || [],
      reference_asset_ids: page.reference_asset_ids || [],
      reference_notes: page.reference_notes || [],
    })))
  }, [comic?.id, activeChapterNumber])

  if (!chapters.length) {
    return <Empty description="先生成章节规划，再进入单话工作台" />
  }

  const canGenerateNovel = Boolean(chapterOutline)
  const canGenerateStoryboard = Boolean(script)
  const canGenerateComic = Boolean(storyboard)

  const sceneCount = sceneDrafts.length || chapterOutline?.data?.scenes?.length || 0
  const scriptSceneCount = script?.data?.scenes?.length || 0
  const panelCount = storyboard?.data?.panels?.length || 0
  const pageCount = comicDrafts.length || comic?.data?.pages?.length || 0
  const storyboardPanels = Array.isArray(storyboard?.data?.panels) ? storyboard?.data?.panels : []
  const storyboardPanelsWithPrompts = storyboardPanels.filter((panel: any) => panel?.image_prompt)
  const storyboardReferencePlans = storyboardPanelsWithPrompts.map((panel: any) =>
    buildStoryboardPanelReferencePlan({
      panel,
      projectAssets,
      characterDetails,
      supportsReferenceImages: defaultImageSupportsReferenceImages,
    }),
  )
  const storyboardGeneratedCount = storyboardPanelsWithPrompts.filter((panel: any) =>
    inlineImages[imageContextKey({
      contentId: storyboard?.id,
      sourceType: 'storyboard_panel',
      sourceIndex: panel.panel_number,
      chapterNumber: activeChapterNumber,
    })],
  ).length
  const storyboardReferenceSummary = buildStoryboardReferenceSummary(
    storyboardReferencePlans,
    storyboardGeneratedCount,
    defaultImageSupportsReferenceImages,
  )
  const episodeOutputs = [
    { label: '细纲', ready: Boolean(chapterOutline) },
    { label: '正文', ready: Boolean(novelBody) },
    { label: '脚本', ready: Boolean(script) },
    { label: '分镜', ready: Boolean(storyboard) },
  ]
  const nextEpisodeAction = !chapterOutline
    ? '先完成细纲'
    : !novelBody
      ? '生成正文'
      : !script
        ? '生成脚本'
        : !storyboard
          ? '拆分镜'
          : '补充参考与画面'
  const linesFromText = (value: string) =>
    String(value || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
  const buildChapterOutlineData = () => ({
    ...chapterOutline?.data,
    title: outlineDraft.title || '',
    summary: outlineDraft.summary || '',
    objective: outlineDraft.objective || '',
    keywords: linesFromText(outlineDraft.keywordsText),
    key_dialogues: linesFromText(outlineDraft.keyDialoguesText),
    foreshadowing: linesFromText(outlineDraft.foreshadowingText),
    ending_hook: outlineDraft.ending_hook || '',
    continuity_notes: linesFromText(outlineDraft.continuityNotesText),
    scenes: sceneDrafts.map((scene, index) => ({
      ...scene,
      scene_number: index + 1,
      beats: linesFromText(scene.beatsText),
    })),
  })
  const renderInlineImage = (context: ImagePromptContext) => {
    const key = imageContextKey(context)
    return (
      <InlineImageResult
        image={inlineImages[key]}
        loading={inlineImageLoadingKey === key}
        taskId={inlineImages[key]?.taskId || (pendingImageTaskKey === key ? pendingImageTaskId : undefined)}
        onPromoteReference={
          inlineImages[key]?.assetId
            ? (role) => onLinkReferenceAsset(inlineImages[key].assetId!, role, {
                label: `${context.sourceTitle || context.sourceType || '生成图'}参考`,
                source_type: context.sourceType,
                source_index: context.sourceIndex,
                chapter_number: context.chapterNumber,
                promoted_from_output: true,
                promoted_at: new Date().toISOString(),
              })
            : undefined
        }
      />
    )
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
      <div style={{ ...themedWorkbenchHeaderStyle, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Space direction="vertical" size={4} style={{ minWidth: 0, flex: '1 1 280px' }}>
          <Space size={8} wrap>
            <Title level={4} style={{ margin: 0 }}>第 {activeChapterNumber} 话</Title>
            <Tag color="processing">制作单元</Tag>
            {comic ? <Tag color="purple">漫画页已拆分</Tag> : null}
          </Space>
          <Text type="secondary" ellipsis={{ tooltip: activeChapter?.title || '未命名章节' }}>
            {activeChapter?.title || '未命名章节'} · 下一步：{nextEpisodeAction}
          </Text>
          <Space size={6} wrap>
            <Tag color={writingPreflightReady ? 'green' : 'warning'}>
              {writingPreflightLoading ? '检查中' : writingPreflightReady ? '门禁通过' : '存在阻塞'}
            </Tag>
            <Tag>{writingStageMeta[writingStage].label}</Tag>
            <Text type={writingPreflightReady ? 'success' : 'warning'} style={{ fontSize: 12 }}>
              {writingPreflightLoading
                ? '正在检查当前章节...'
                : writingPreflightReady
                  ? '当前章节可以进入生成。'
                  : writingPreflight?.next_action || '等待检查结果'}
            </Text>
          </Space>
        </Space>
        <Select
          aria-label="选择制作章节"
          value={activeChapterNumber}
          style={{ width: 240, maxWidth: '100%' }}
          options={chapters.map((chapter) => ({
            value: chapter.chapter_number,
            label: `第 ${chapter.chapter_number} 话 · ${chapter.title || '未命名章节'}`,
          }))}
          onChange={onActiveChapterChange}
        />
      </div>

      <WorkbenchSection
        title="检查阶段与方法包"
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: compact ? 'minmax(0, 1fr)' : 'minmax(220px, 0.44fr) minmax(280px, 1fr)',
              gap: 10,
              alignItems: 'start',
            }}
          >
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text strong>检查阶段</Text>
                <Segmented
                  block
                  size="small"
                value={writingStage}
                options={[
                  { label: '章节细纲', value: 'chapter_outline' },
                  { label: '正文', value: 'novel_body' },
                  { label: '正文润色', value: 'novel_body_refine' },
                ]}
                onChange={(value) => setWritingStage(value as 'chapter_outline' | 'novel_body' | 'novel_body_refine')}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {writingStageMeta[writingStage].hint}
              </Text>
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text strong>方法包</Text>
              <Select
                mode="multiple"
                allowClear
                loading={writingPreflightLoading}
                placeholder="选择项目可用的写作方法包"
                value={selectedCreativeSkillIds}
                options={writingMethodOptions}
                onChange={(values) => onCreativeSkillIdsChange((values as string[]).filter(Boolean))}
                style={{ width: '100%' }}
                maxTagCount="responsive"
              />
              <Space wrap size={[6, 6]}>
                <Tag color="blue">{selectedCreativeSkillIds.length} 个方法包已保存</Tag>
                {selectedWritingMethods.map((item) =>
                  item ? (
                    <Tag key={item.id} color={item.auto_apply ? 'geekblue' : 'default'}>
                      {item.title}
                      {item.auto_apply ? ' · 自动' : ''}
                    </Tag>
                  ) : null,
                )}
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                方法包是可选的写作增强：选中后会在生成前注入上下文 T6，影响节奏、对白或审稿提示；不选也可以正常生成。保存后，下一次正文/润色/Writer Room 请求会使用它。
              </Text>
            </Space>
          </div>
          <Space wrap size={[6, 6]}>
            {writingPreflightChecks.map((check) => (
              <Tag key={check.id} color={check.status === 'pass' ? 'green' : 'red'}>
                {check.label}
              </Tag>
            ))}
          </Space>
          {writingPreflightBlockers.length ? (
            <List
              size="small"
              bordered={false}
              dataSource={writingPreflightBlockers}
              renderItem={(item) => (
                <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Text strong style={{ fontSize: 12 }}>
                      {item.label}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {item.detail}
                    </Text>
                  </Space>
                </List.Item>
              )}
            />
          ) : null}
        </Space>
      </WorkbenchSection>

      <div
        aria-label="当前话生产状态"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(116px, 1fr))',
          border: `1px solid ${theme.borderLight}`,
          background: theme.bgElevated,
        }}
      >
        {episodeOutputs.map((item, index) => (
          <div
            key={item.label}
            style={{
              padding: '9px 12px',
              borderRight: index < episodeOutputs.length - 1 ? `1px solid ${theme.borderLight}` : 'none',
              minWidth: 0,
            }}
          >
            <Text type="secondary" style={{ display: 'block', fontSize: 11 }}>{item.label}</Text>
            <Text strong style={{ color: item.ready ? theme.primary : theme.textSecondary, fontSize: 13 }}>
              {item.ready ? '已就绪' : '待生产'}
            </Text>
          </div>
        ))}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: compact
            ? 'minmax(0, 1fr)'
            : `${columnWidths.outline}px 10px ${columnWidths.prose}px 10px minmax(300px, 1fr)`,
          gap: 8,
          alignItems: 'stretch',
          height: compact ? undefined : 'calc(100vh - 320px)',
          minHeight: 640,
        }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <WorkbenchSection
          title="当前细纲"
          extra={
            <Space>
              {chapterOutline ? (
                <Button
                  size="small"
                  loading={savingContentId === chapterOutline.id}
                  onClick={() =>
                    onSaveContent(chapterOutline.id, {
                      data: buildChapterOutlineData(),
                      text_content: [
                        outlineDraft.summary,
                        outlineDraft.objective,
                        ...sceneDrafts.map((scene, index) =>
                          `场景 ${index + 1} ${scene.title || scene.location || ''}\n${scene.action || scene.objective || ''}`,
                        ),
                      ]
                        .filter(Boolean)
                        .join('\n\n'),
                    })
                  }
                >
                  保存
                </Button>
              ) : null}
              <Button
                type="primary"
                size="small"
                icon={<ThunderboltOutlined />}
                loading={isChapterActionLoading('chapter_outline', activeChapterNumber)}
                onClick={() => onGenerateChapterOutline(activeChapterNumber)}
              >
                {chapterOutline ? '重生成细纲' : '生成细纲'}
              </Button>
            </Space>
          }
        >
          {chapterOutline ? (
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Text type="secondary">本页负责这一话的写作清单，正文和漫画会使用保存后的细纲。</Text>
              <EditorField label="本话标题" hint="用于目录、正文标题和后续漫画页标题。">
                <Input
                  value={outlineDraft.title}
                  placeholder="例如：第一话：神坛坠落与降维打击"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, title: event.target.value }))}
                />
              </EditorField>
              <EditorField label="本话摘要" hint="讲清起因、冲突、反转和落点，正文生成会优先参考这里。">
                <TextArea
                  rows={4}
                  value={outlineDraft.summary}
                  placeholder="这一话完整发生了什么..."
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, summary: event.target.value }))}
                />
              </EditorField>
              <EditorField label="写作目标" hint="告诉 AI 这一话要立住什么人物、推进什么关系、制造什么爽点。">
                <TextArea
                  rows={3}
                  value={outlineDraft.objective}
                  placeholder="例如：立住女主智商碾压，制造片场救火爽点..."
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, objective: event.target.value }))}
                />
              </EditorField>
              <EditorField label="关键词" hint="每行一个，作为正文、脚本和漫画分镜的关键词锚点。">
                <TextArea
                  rows={3}
                  value={outlineDraft.keywordsText}
                  placeholder="版权剽窃&#10;降维打击&#10;片场救火"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, keywordsText: event.target.value }))}
                />
              </EditorField>
              <EditorField label="关键台词" hint="每行一句，可直接进入正文、脚本对白或漫画气泡。">
                <TextArea
                  rows={4}
                  value={outlineDraft.keyDialoguesText}
                  placeholder="例如：明天下午三点，花园喷泉第三块砖下，我知道你不是 NPC。"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, keyDialoguesText: event.target.value }))}
                />
              </EditorField>
              <EditorField label="伏笔" hint="后续章节要回收的线索，每行一条。">
                <TextArea
                  rows={3}
                  value={outlineDraft.foreshadowingText}
                  placeholder="例如：合同编号异常，为后续版权反击埋线。"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, foreshadowingText: event.target.value }))}
                />
              </EditorField>
              <EditorField label="结尾钩子" hint="这一话最后吊住读者继续看下一话的悬念。">
                <TextArea
                  rows={2}
                  value={outlineDraft.ending_hook}
                  placeholder="例如：她抬头看向监控，像是知道屏幕后的人是谁。"
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, ending_hook: event.target.value }))}
                />
              </EditorField>
              <EditorField label="连续性说明" hint="给下一话、脚本和分镜使用，避免设定和人物状态断掉。">
                <TextArea
                  rows={3}
                  value={outlineDraft.continuityNotesText}
                  placeholder="每行一条连续性备注..."
                  onChange={(event) => setOutlineDraft((prev) => ({ ...prev, continuityNotesText: event.target.value }))}
                />
              </EditorField>
            </Space>
          ) : (
            <>
              <InfoBlock title="本话标题" text={activeChapter?.title} compact />
              <InfoBlock title="目标 / 冲突" text={[activeChapter?.goal, activeChapter?.conflict].filter(Boolean).join('；')} compact />
              <InfoListBlock title="关键事件" items={activeChapter?.key_events || []} />
            </>
          )}
        </WorkbenchSection>

        {chapterOutline ? (
          <WorkbenchSection
            title="场景编辑"
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<ThunderboltOutlined />}
                  loading={isChapterActionLoading('chapter_outline_scenes', activeChapterNumber)}
                  onClick={() => onRegenerateChapterOutlineScenes(activeChapterNumber)}
                >
                  重生成场景
                </Button>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    setSceneDrafts((prev) => [
                      ...prev,
                      {
                        scene_number: prev.length + 1,
                        title: '',
                        location: '',
                        purpose: '',
                        scene_role: '',
                        objective: '',
                        conflict: '',
                        beatsText: '',
                        action: '',
                        key_dialogue: '',
                        emotion: '',
                        emotional_turn: '',
                        visual_focus: '',
                        shot_design: '',
                        image_prompt: '',
                      },
                    ])
                  }
                >
                  添加场景
                </Button>
                <Button
                  size="small"
                  type="primary"
                  loading={savingContentId === chapterOutline.id}
                  onClick={() =>
                    onSaveContent(chapterOutline.id, {
                      data: buildChapterOutlineData(),
                      text_content: [
                        outlineDraft.summary,
                        ...sceneDrafts.map((scene) =>
                          `场景 ${scene.scene_number} ${scene.title || scene.location || ''}\n${scene.action || scene.objective || ''}`,
                        ),
                      ]
                        .filter(Boolean)
                        .join('\n\n'),
                    })
                  }
                >
                  保存场景
                </Button>
              </Space>
            }
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              {sceneDrafts.map((scene: any, index: number) => (
                <div key={`${scene.scene_number}-${index}`} style={themedCompactBlockStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Text strong>场景 {index + 1}</Text>
                      <Space>
                        {scene.image_prompt ? (
                          <Button
                            size="small"
                            onClick={() =>
                              onSendImagePrompt(scene.image_prompt, {
                                contentId: chapterOutline.id,
                                sourceType: 'chapter_outline_scene',
                                sourceIndex: scene.scene_number || index + 1,
                                sourceTitle: scene.title || scene.location || `场景 ${index + 1}`,
                                chapterNumber: activeChapterNumber,
                              })
                            }
                          >
                            生图
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          danger
                          onClick={() => setSceneDrafts((prev) => prev.filter((_, itemIndex) => itemIndex !== index))}
                        >
                          删除
                        </Button>
                      </Space>
                    </Space>
                    <EditorField label="场景标题" hint="用于快速识别这一场戏。">
                      <Input
                        value={scene.title}
                        placeholder="例如：不属于自己的眼睛"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, title: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="地点 / 时间 / 氛围" hint="给正文、脚本和分镜提供空间锚点。">
                      <Input
                        value={scene.location}
                        placeholder="例如：豪门别墅管家卧室 / 深夜 / 压抑"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, location: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="场景位置" hint="标记这个场景在单话结构里的作用位置。">
                      <Input
                        value={scene.scene_role}
                        placeholder="开场钩子 / 冲突升级 / 反转 / 情绪落点 / 结尾钩子"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, scene_role: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="场景作用" hint="说明这个场景为什么存在，推进什么信息、情绪或关系。">
                      <TextArea
                        rows={2}
                        value={scene.purpose}
                        placeholder="例如：开篇即制造错位感，让主角意识到自己身份异常。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, purpose: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="场景冲突" hint="谁和谁的目标冲突，压力来自哪里。">
                      <TextArea
                        rows={2}
                        value={scene.conflict}
                        placeholder="例如：主角想确认身份，系统和环境不断制造误导。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, conflict: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="剧情节拍" hint="每行一个具体动作、镜头或信息揭示，后续分镜会按它拆。">
                      <TextArea
                        rows={4}
                        value={scene.beatsText}
                        placeholder="镜子里出现陌生脸&#10;手机弹出系统提示&#10;主角发现合同不对劲"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, beatsText: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="剧情动作" hint="人物怎么移动、做什么决定、信息如何推进。">
                      <TextArea
                        rows={3}
                        value={scene.action}
                        placeholder="描述这一场戏的主要动作和调度..."
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, action: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="关键台词" hint="可直接进入正文、脚本对白或漫画气泡。">
                      <TextArea
                        rows={2}
                        value={scene.key_dialogue}
                        placeholder="例如：明天下午三点，花园喷泉第三块砖下，我知道你不是 NPC。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, key_dialogue: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="主要情绪" hint="这一场戏的情绪底色。">
                      <Input
                        value={scene.emotion}
                        placeholder="例如：压抑、怀疑、惊醒、冷静"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, emotion: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="情绪转折" hint="场景中情绪如何变化，帮助正文和分镜做节奏。">
                      <Input
                        value={scene.emotional_turn}
                        placeholder="例如：迷茫 -> 惊醒 -> 冷静掌控"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, emotional_turn: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="画面核心看点" hint="漫画/生图最该抓住的视觉重点。">
                      <TextArea
                        rows={2}
                        value={scene.visual_focus}
                        placeholder="例如：镜中陌生脸、冷色卧室、红色系统警告。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, visual_focus: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="镜头设计" hint="景别、角度、构图、运动和光线，用于后续分镜。">
                      <TextArea
                        rows={2}
                        value={scene.shot_design}
                        placeholder="例如：低角度中景，镜中反射，冷蓝侧光，人物居中压迫构图。"
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, shot_design: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    <EditorField label="生图提示词" hint="可直接送到图片生成，写清角色、地点、动作、表情、构图、光线、风格和一致性要求。">
                      <TextArea
                        rows={4}
                        value={scene.image_prompt}
                        placeholder="半写实彩色漫画，年轻管家在冷色卧室中凝视镜子，镜中是不属于自己的脸..."
                        onChange={(event) =>
                          setSceneDrafts((prev) => prev.map((item, itemIndex) => (
                            itemIndex === index ? { ...item, image_prompt: event.target.value } : item
                          )))
                        }
                      />
                    </EditorField>
                    {renderInlineImage({
                      contentId: chapterOutline.id,
                      sourceType: 'chapter_outline_scene',
                      sourceIndex: scene.scene_number || index + 1,
                      chapterNumber: activeChapterNumber,
                    })}
                  </Space>
                </div>
              ))}
            </Space>
          </WorkbenchSection>
        ) : null}
        </Space>

        {!compact ? (
          <ResizeHandle
            onMouseDown={(event) =>
              startHorizontalResize(event, {
                initial: columnWidths.outline,
                min: 260,
                max: 560,
                onChange: (value) => setColumnWidths((prev) => ({ ...prev, outline: value })),
              })
            }
          />
        ) : null}

        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <WorkbenchSection
          title="正文"
          extra={
            <Space size={8}>
              <Tooltip title={canGenerateNovel ? '' : '先生成细纲'}>
                <Button
                  size="small"
                  icon={<FileTextOutlined />}
                  disabled={!canGenerateNovel}
                  loading={isChapterActionLoading('novel_body', activeChapterNumber)}
                  onClick={() => onGenerateNovelBody(activeChapterNumber)}
                >
                  {novelBody ? '重生成正文' : '生成正文'}
                </Button>
              </Tooltip>
              {novelBody ? (
                <Button
                  size="small"
                  icon={<FolderAddOutlined />}
                  onClick={() => onSaveContentAsAsset(novelBody.id)}
                >
                  存为素材
                </Button>
              ) : null}
              {novelBody ? (
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  loading={continuityExtracting}
                  onClick={() => onExtractContinuity(novelBody.id)}
                >
                  提取连续性
                </Button>
              ) : null}
              <Button
                size="small"
                icon={<CloudUploadOutlined />}
                disabled={!novelBody}
                onClick={onOpenFanqiePublish}
              >
                保存到番茄草稿
              </Button>
            </Space>
          }
        >
          {novelBody ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <TextArea
                rows={28}
                value={novelDraft}
                onChange={(event) => setNovelDraft(event.target.value)}
                placeholder="这里可以人工润色本话正文，保存后会覆盖当前版本内容"
                style={{ minHeight: 640 }}
              />
              <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                <Text type="secondary">字数：{novelDraft.length}</Text>
                <Button
                  type="primary"
                  loading={savingContentId === novelBody.id}
                  onClick={() =>
                    onSaveContent(novelBody.id, {
                      text_content: novelDraft,
                      data: { ...novelBody.data, content: novelDraft, word_count: novelDraft.length },
                    })
                  }
                >
                  保存正文
                </Button>
              </Space>
              <EditorField label="中文微调" hint="告诉 AI 如何改正文，例如加强冲突、压缩对白、增加爽点。会覆盖保存当前正文。">
                <Space.Compact style={{ width: '100%' }}>
                  <Input
                    value={novelRefineInstruction}
                    onChange={(event) => setNovelRefineInstruction(event.target.value)}
                    placeholder="输入正文修改要求，例如：加强冲突，压缩对白，让反转更爽"
                    onPressEnter={() => {
                      onRefineNovelBody(activeChapterNumber, novelRefineInstruction)
                    }}
                  />
                  <Button
                    type="primary"
                    loading={isChapterActionLoading('novel_body_refine', activeChapterNumber)}
                    onClick={() => onRefineNovelBody(activeChapterNumber, novelRefineInstruction)}
                  >
                    发送
                  </Button>
                </Space.Compact>
              </EditorField>
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本话还没有正文" />
          )}
        </WorkbenchSection>
      </Space>

      {!compact ? (
        <ResizeHandle
          onMouseDown={(event) =>
            startHorizontalResize(event, {
              initial: columnWidths.prose,
              min: 360,
              max: 760,
              onChange: (value) => setColumnWidths((prev) => ({ ...prev, prose: value })),
            })
          }
        />
      ) : null}

      <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, alignSelf: 'start', maxHeight: '100%', overflowY: 'auto' }}>
        <ReferenceCardsPanel
          assets={projectAssets}
          assetDetails={assetDetails}
          loading={linkingAsset}
          onLinkAsset={onLinkReferenceAsset}
        />

        <WorkbenchSection
          title={`脚本${scriptSceneCount ? ` · ${scriptSceneCount}` : ''}`}
          extra={
            <Space size={6}>
              {script ? (
                <Button
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() => openProjectTextPreview(script.title || `第 ${activeChapterNumber} 章脚本`, buildScriptMarkdown(script))}
                >
                  预览
                </Button>
              ) : null}
              {script ? (
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  loading={referenceMatching}
                  disabled={!referenceAssetOptions.length}
                  onClick={() => onMatchReferenceAssets(script.id)}
                >
                  匹配参考卡
                </Button>
              ) : null}
              {script ? (
                <Button size="small" icon={<FolderAddOutlined />} onClick={() => onSaveContentAsAsset(script.id)}>
                  存为素材
                </Button>
              ) : null}
              {script ? (
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={() =>
                    downloadTextFile(
                      `${projectMarkdownFilename(script.title || `chapter-${activeChapterNumber}`, 'script')}.md`,
                      buildScriptMarkdown(script),
                    )
                  }
                >
                  导出脚本
                </Button>
              ) : null}
              <Button
                size="small"
                icon={<FileTextOutlined />}
                loading={isChapterActionLoading('script', activeChapterNumber)}
                onClick={() => onGenerateScript(activeChapterNumber)}
              >
                {script ? '重写脚本' : '由细纲生成脚本'}
              </Button>
            </Space>
          }
        >
          {script ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              {script.data?.hook ? (
                <div style={themedCompactBlockStyle}>
                  <Text strong>开头钩子</Text>
                  <Paragraph style={{ margin: '6px 0 0' }}>{script.data.hook}</Paragraph>
                </div>
              ) : null}
              {(script.data?.scenes || []).slice(0, 8).map((scene: any) => (
                <div key={scene.scene_number} style={themedCompactBlockStyle}>
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Text strong>场景 {scene.scene_number} · {scene.location || '未设定地点'}</Text>
                      {scene.image_prompt ? (
                        <Button
                          size="small"
                          onClick={() =>
                            onSendImagePrompt(scene.image_prompt, {
                              contentId: script.id,
                              sourceType: 'script_scene',
                              sourceIndex: scene.scene_number,
                              sourceTitle: scene.location || `脚本场景 ${scene.scene_number}`,
                              chapterNumber: activeChapterNumber,
                              referenceAssetIds: scene.reference_asset_ids || [],
                            })
                          }
                        >
                          生图
                        </Button>
                      ) : null}
                    </Space>
                    <Text type="secondary">{[scene.camera_hint, scene.emotion].filter(Boolean).join(' · ')}</Text>
                    <ReferenceAssetPreviewStrip
                      assetIds={scene.reference_asset_ids || []}
                      notes={scene.reference_notes || []}
                      assets={projectAssets}
                      assetDetails={assetDetails}
                    />
                    <Paragraph style={{ margin: 0 }}>{scene.action}</Paragraph>
                    {(scene.dialogue || []).length ? (
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        {(scene.dialogue || []).slice(0, 4).map((line: any, index: number) => (
                          <Text key={`${line.character || 'dialogue'}-${index}`}>
                            {line.character ? `${line.character}：` : ''}{line.line || line}
                          </Text>
                        ))}
                      </Space>
                    ) : null}
                    {renderInlineImage({
                      contentId: script.id,
                      sourceType: 'script_scene',
                      sourceIndex: scene.scene_number,
                      chapterNumber: activeChapterNumber,
                    })}
                  </Space>
                </div>
              ))}
              {script.data?.ending_hook ? (
                <div style={themedCompactBlockStyle}>
                  <Text strong>结尾钩子</Text>
                  <Paragraph style={{ margin: '6px 0 0' }}>{script.data.ending_hook}</Paragraph>
                </div>
              ) : null}
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本话还没有脚本，先由细纲生成脚本" />
          )}
        </WorkbenchSection>

        <WorkbenchSection
          title={`分镜${panelCount ? ` · ${panelCount}` : ''}`}
          extra={
            <Space size={6}>
              {storyboard ? (
                <Tooltip
                  title={
                    defaultImageSupportsReferenceImages
                      ? '当前默认生图模型会接收参考图'
                      : '当前默认生图模型未声明支持参考图，只会记录参考关系并写入提示词'
                  }
                >
                  <Tag color={defaultImageSupportsReferenceImages ? 'green' : 'orange'}>
                    {defaultImageSupportsReferenceImages ? '参考图可发送' : '仅记录参考'}
                  </Tag>
                </Tooltip>
              ) : null}
              {storyboard ? (
                <Tag color={storyboardReferenceSummary.missingEffectivePlanPanels ? 'orange' : 'blue'}>
                  参考 {storyboardReferenceSummary.effectivePlanPanels}/{storyboardReferenceSummary.promptPanels}
                </Tag>
              ) : null}
              {storyboard ? <Tag color="green">已生图 {storyboardReferenceSummary.generatedPanels}</Tag> : null}
              {storyboard ? (
                <>
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => openProjectTextPreview(storyboard.title || `第 ${activeChapterNumber} 章分镜`, buildStoryboardMarkdown(storyboard))}
                  >
                    预览
                  </Button>
                  <Button
                    size="small"
                    icon={<BranchesOutlined />}
                    loading={referenceMatching}
                    disabled={!referenceAssetOptions.length}
                    onClick={() => onMatchReferenceAssets(storyboard.id)}
                  >
                    匹配参考卡
                  </Button>
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={batchStoryboardImageChapter === activeChapterNumber}
                    onClick={() => onBatchGenerateStoryboardImages(activeChapterNumber)}
                  >
                    批量生图
                  </Button>
                  <Tooltip
                    title={
                      previsBatchPanels.length
                        ? `对已勾选的 ${previsBatchPanels.length} 格逐格生成初稿：每格看完半透明预览后自己点确认，确认或放弃都会自动进入下一格`
                        : '先在分镜卡片上勾选要生成初稿的格子（可多选）'
                    }
                  >
                    <Button
                      size="small"
                      icon={<BulbOutlined />}
                      disabled={!previsBatchPanels.length}
                      onClick={() => {
                        // 按分镜号排序：队列顺序就是执行顺序，必须与画面上的顺序一致
                        const queue = [...previsBatchPanels].sort((a, b) => a - b)
                        onOpenPrevis(
                          storyboard.id,
                          queue[0],
                          `第 ${activeChapterNumber} 章 · 批量初稿`,
                          { draft: true, queue },
                        )
                        setPrevisBatchPanels([])
                      }}
                    >
                      批量初稿{previsBatchPanels.length ? `（${previsBatchPanels.length}）` : ''}
                    </Button>
                  </Tooltip>
                </>
              ) : null}
              <Tooltip title={canGenerateStoryboard ? '' : '先生成脚本'}>
                <Button
                  size="small"
                  icon={<PictureOutlined />}
                  disabled={!canGenerateStoryboard}
                  loading={isChapterActionLoading('storyboard', activeChapterNumber)}
                  onClick={() => onGenerateStoryboard(activeChapterNumber)}
                >
                  {storyboard ? '重拆分镜' : '生成分镜'}
                </Button>
              </Tooltip>
            </Space>
          }
        >
          {storyboard ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <StoryboardReferencePreflight
                summary={storyboardReferenceSummary}
                supportsReferenceImages={defaultImageSupportsReferenceImages}
                hasImageModel={Boolean(defaultImageModelName)}
              />
              {(storyboard.data?.panels || []).slice(0, 10).map((panel: any) => (
                <div key={panel.panel_number} style={themedCompactBlockStyle}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <Space align="center" size={6}>
                      <Tooltip title="勾选后，用分镜面板右上角的「批量初稿」逐格生成并确认">
                        <Checkbox
                          checked={previsBatchPanels.includes(Number(panel.panel_number))}
                          onChange={event => {
                            const number = Number(panel.panel_number)
                            setPrevisBatchPanels(prev =>
                              event.target.checked ? [...prev, number] : prev.filter(item => item !== number),
                            )
                          }}
                        />
                      </Tooltip>
                      <Text strong>分镜 {panel.panel_number}</Text>
                    </Space>
                    {panel.image_prompt ? (
                      <Space size={4}>
                        <Button
                          size="small"
                          onClick={() =>
                            onSendImagePrompt(panel.image_prompt, {
                              contentId: storyboard.id,
                              sourceType: 'storyboard_panel',
                              sourceIndex: panel.panel_number,
                              sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
                              chapterNumber: activeChapterNumber,
                              referenceAssetIds: panel.reference_asset_ids || [],
                              characterIds: panel.character_ids || [],
                              portraitNodeIds: panel.portrait_node_ids || [],
                              portraitVersionIds: panel.portrait_version_ids || [],
                            })
                          }
                        >
                          生图
                        </Button>
                        <Button
                          size="small"
                          icon={<DeploymentUnitOutlined />}
                          onClick={() =>
                            onOpenPrevis(
                              storyboard.id,
                              Number(panel.panel_number),
                              panel.action || `分镜 ${panel.panel_number} · 3D 预演`,
                            )
                          }
                        >
                          3D 预演
                        </Button>
                        {/* 主动线：把这一格已经写好的调度/景别/角度直接翻译成场景初稿（只读预览，确认后才落库） */}
                        <Tooltip title="按这一格的调度、景别、镜头角度生成 3D 初稿；进预演台后先看半透明预览，确认才落库">
                          <Button
                            size="small"
                            icon={<BulbOutlined />}
                            onClick={() =>
                              onOpenPrevis(
                                storyboard.id,
                                Number(panel.panel_number),
                                panel.action || `分镜 ${panel.panel_number} · 3D 预演`,
                                { draft: true },
                              )
                            }
                          >
                            生成初稿
                          </Button>
                        </Tooltip>
                        <Button
                          size="small"
                          icon={<VideoCameraOutlined />}
                          onClick={() =>
                            onOpenVideoGeneration(
                              panel.video_prompt || buildStoryboardVideoFallbackPrompt(panel),
                              {
                                contentId: storyboard.id,
                                sourceType: 'storyboard_panel',
                                sourceIndex: panel.panel_number,
                                sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
                                chapterNumber: activeChapterNumber,
                                referenceAssetIds: panel.reference_asset_ids || [],
                                characterIds: panel.character_ids || [],
                                portraitNodeIds: panel.portrait_node_ids || [],
                                portraitVersionIds: panel.portrait_version_ids || [],
                                durationSeconds: panel.duration_seconds,
                                generateAudio: panel.generate_audio === true,
                                musicHint: panel.music_hint || '',
                              },
                            )
                          }
                        >
                          视频
                        </Button>
                      </Space>
                    ) : null}
                  </Space>
                  <Text type="secondary">{panel.action || panel.image_prompt}</Text>
                  <ReferenceAssetPreviewStrip
                    assetIds={panel.reference_asset_ids || []}
                    notes={panel.reference_notes || []}
                    assets={projectAssets}
                    assetDetails={assetDetails}
                  />
                  <StoryboardReferenceDiagnostics
                    panel={panel}
                    projectAssets={projectAssets}
                    characterDetails={characterDetails}
                    supportsReferenceImages={defaultImageSupportsReferenceImages}
                  />
                  {panel.image_prompt ? (
                    editingStoryboardPrompt === panel.panel_number ? (
                      <Space direction="vertical" size={6} style={{ width: '100%', marginTop: 8 }}>
                        <Input.TextArea
                          value={storyboardPromptDraft}
                          autoSize={{ minRows: 4, maxRows: 10 }}
                          onChange={(event) => setStoryboardPromptDraft(event.target.value)}
                        />
                        <Space>
                          <Button
                            type="primary"
                            size="small"
                            loading={savingContentId === storyboard.id}
                            disabled={!storyboardPromptDraft.trim()}
                            onClick={() => {
                              const nextData = {
                                ...storyboard.data,
                                panels: (storyboard.data?.panels || []).map((item: any) =>
                                  Number(item.panel_number) === Number(panel.panel_number)
                                    ? { ...item, image_prompt: storyboardPromptDraft.trim() }
                                    : item,
                                ),
                              }
                              onSaveContent(storyboard.id, { data: nextData })
                              setEditingStoryboardPrompt(null)
                            }}
                          >保存提示词</Button>
                          <Button size="small" onClick={() => setEditingStoryboardPrompt(null)}>取消</Button>
                        </Space>
                      </Space>
                    ) : (
                      <Space style={{ width: '100%', justifyContent: 'space-between', marginTop: 6 }} align="start">
                        <Paragraph
                          type="secondary"
                          ellipsis={{ rows: 3, tooltip: panel.image_prompt }}
                          style={{ margin: 0, fontSize: 12, flex: 1 }}
                        >
                          生图提示：{panel.image_prompt}
                        </Paragraph>
                        <Button
                          size="small"
                          type="text"
                          onClick={() => {
                            setStoryboardPromptDraft(panel.image_prompt || '')
                            setEditingStoryboardPrompt(panel.panel_number)
                          }}
                        >改提示词</Button>
                      </Space>
                    )
                  ) : null}
                  <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      本格参考卡：用于指定这一格额外参考的角色、背景、道具或画风素材。
                    </Text>
                    <Select
                      mode="multiple"
                      allowClear
                      size="small"
                      placeholder="选择项目参考卡，或先在右侧参考卡面板关联素材"
                      value={panel.reference_asset_ids || []}
                      options={referenceAssetOptions}
                      loading={savingContentId === storyboard.id}
                      disabled={!referenceAssetOptions.length || savingContentId === storyboard.id}
                      maxTagCount="responsive"
                      optionFilterProp="label"
                      style={{ width: '100%' }}
                      onChange={(values) =>
                        onUpdateStoryboardPanelReferences(storyboard.id, panel.panel_number, values)
                      }
                    />
                  </Space>
                  {renderInlineImage({
                    contentId: storyboard.id,
                    sourceType: 'storyboard_panel',
                    sourceIndex: panel.panel_number,
                    chapterNumber: activeChapterNumber,
                  })}
                  <StoryboardVideoOutputStrip
                    links={storyboardVideoOutputs.get(Number(panel.panel_number)) || []}
                    assetDetails={assetDetails}
                  />
                </div>
              ))}
            </Space>
          ) : script ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="脚本已生成，可以继续拆分镜" />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本话还没有脚本/分镜" />
          )}
        </WorkbenchSection>

        <WorkbenchSection
          title={`漫画页${pageCount ? ` · ${pageCount}` : ''}`}
          extra={
            <Space>
              <Select
                size="small"
                value={comicStyle}
                onChange={setComicStyle}
                style={{ width: 118 }}
                options={comicStyleOptions}
                title="漫画风格"
              />
              <InputNumber
                min={1}
                max={80}
                size="small"
                value={comicPageCount}
                onChange={(value) => setComicPageCount(Number(value || 10))}
              />
              {comic ? (
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  loading={referenceMatching}
                  disabled={!referenceAssetOptions.length}
                  onClick={() => onMatchReferenceAssets(comic.id)}
                >
                  匹配参考卡
                </Button>
              ) : null}
              <Tooltip title={canGenerateComic ? '' : '先生成分镜'}>
                <Button
                  size="small"
                  type="primary"
                  icon={<PictureOutlined />}
                  disabled={!canGenerateComic}
                  loading={isChapterActionLoading('comic_pages', activeChapterNumber)}
                  onClick={() => onSplitComicPages(activeChapterNumber)}
                >
                  {comic ? '重生成漫画' : '生成漫画'}
                </Button>
              </Tooltip>
            </Space>
          }
        >
          {comic ? (
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Button
                type="primary"
                loading={savingContentId === comic.id}
                onClick={() =>
                  onSaveContent(comic.id, {
                    data: { ...comic.data, pages: comicDrafts },
                    text_content: comicDrafts
                      .map((page) => `第 ${page.page_number} 页\n${page.content || ''}\n${page.image_prompt || ''}`)
                      .join('\n\n'),
                  })
                }
              >
                保存漫画页
              </Button>
              {comicDrafts.map((page: any, index: number) => (
                <div key={`${page.page_number}-${index}`} style={themedCompactBlockStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Text strong>第 {index + 1} 页</Text>
                      {page.image_prompt ? (
                        <Button
                          size="small"
                          onClick={() =>
                            onSendImagePrompt(page.image_prompt, {
                              contentId: comic.id,
                              sourceType: 'comic_page',
                              sourceIndex: page.page_number || index + 1,
                              sourceTitle: page.title || `第 ${index + 1} 页`,
                              chapterNumber: activeChapterNumber,
                              referenceAssetIds: page.reference_asset_ids || [],
                              characterIds: page.character_ids || [],
                              portraitNodeIds: page.portrait_node_ids || [],
                              portraitVersionIds: page.portrait_version_ids || [],
                            })
                          }
                        >
                          生图
                        </Button>
                      ) : null}
                    </Space>
                    <Input
                      value={page.title}
                      placeholder="页面标题 / 节奏说明"
                      onChange={(event) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, title: event.target.value } : item
                        )))
                      }
                    />
                    <TextArea
                      rows={4}
                      value={page.content}
                      placeholder="本页剧情、对白、画面节奏"
                      onChange={(event) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, content: event.target.value } : item
                        )))
                      }
                    />
                    <TextArea
                      rows={3}
                      value={page.image_prompt}
                      placeholder="本页漫画图像提示词"
                      onChange={(event) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, image_prompt: event.target.value } : item
                        )))
                      }
                    />
                    <ReferenceAssetPreviewStrip
                      assetIds={page.reference_asset_ids || []}
                      notes={page.reference_notes || []}
                      assets={projectAssets}
                      assetDetails={assetDetails}
                    />
                    <Select
                      mode="multiple"
                      allowClear
                      size="small"
                      placeholder="选择本页参考卡"
                      value={page.reference_asset_ids || []}
                      options={referenceAssetOptions}
                      disabled={!referenceAssetOptions.length}
                      maxTagCount="responsive"
                      optionFilterProp="label"
                      style={{ width: '100%' }}
                      onChange={(values) =>
                        setComicDrafts((prev) => prev.map((item, itemIndex) => (
                          itemIndex === index ? { ...item, reference_asset_ids: dedupeStrings(values) } : item
                        )))
                      }
                    />
                    {renderInlineImage({
                      contentId: comic.id,
                      sourceType: 'comic_page',
                      sourceIndex: page.page_number || index + 1,
                      chapterNumber: activeChapterNumber,
                    })}
                  </Space>
                </div>
              ))}
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="分镜完成后生成漫画页" />
          )}
        </WorkbenchSection>
      </Space>
      </div>
    </Space>
  )
}

