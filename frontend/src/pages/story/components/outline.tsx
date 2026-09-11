/**
 * 创作项目工作台：components/outline.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { type ThemeColors } from '../../../constants/theme'
import { StoryOutline, StoryOutlineCharacter } from '../../../types/api'
import { EditorField, InfoBlock, InfoListBlock, PromptTemplateSelect, WorkbenchSection } from './common'
import { PipelineResult, PipelineResultItem, PipelineRunStatus, PipelineStageValue, ProductionStageItem, TemplateOption } from '../types'
import { buildOutlineMarkdown, downloadTextFile, getPipelineSummary, linesToList, listToLines, pipelineStageOptions, productionProfileOptions, projectMarkdownFilename } from '../utils'
import { DownloadOutlined, ReloadOutlined, RobotOutlined, ThunderboltOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, Input, Space, Table, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import { useEffect, useState } from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function PipelinePanel({
  theme,
  stages,
  onStagesChange,
  chapterRange,
  onChapterRangeChange,
  skipExisting,
  onSkipExistingChange,
  continueOnError,
  onContinueOnErrorChange,
  loading,
  result,
  runStatus,
  onRun,
  onRetryFailed,
}: {
  theme: ThemeColors
  stages: PipelineStageValue[]
  onStagesChange: (value: PipelineStageValue[]) => void
  chapterRange: string
  onChapterRangeChange: (value: string) => void
  skipExisting: boolean
  onSkipExistingChange: (value: boolean) => void
  continueOnError: boolean
  onContinueOnErrorChange: (value: boolean) => void
  loading: boolean
  result: PipelineResult | null
  runStatus: PipelineRunStatus
  onRun: () => void
  onRetryFailed: () => void
}) {
  const rows = result?.results || []
  const { generated, skipped, failed } = getPipelineSummary(result)

  const pipelineColumns = [
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 120,
      render: (value: string) => pipelineStageOptions.find((item) => item.value === value)?.label || value,
    },
    {
      title: '章节',
      dataIndex: 'chapter_number',
      width: 76,
      render: (value?: number) => (value ? `第 ${value} 章` : '全局'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => {
        const color = value === 'failed' ? 'red' : value === 'skipped' ? 'default' : 'green'
        const label = value === 'failed' ? '失败' : value === 'skipped' ? '跳过' : '完成'
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '结果',
      render: (_: unknown, record: PipelineResultItem) => (
        <Text type={record.status === 'failed' ? 'danger' : 'secondary'} ellipsis={{ tooltip: record.error || record.reason || record.title }}>
          {record.error || record.reason || record.title || record.content_type || record.count || record.word_count || '-'}
        </Text>
      ),
    },
  ]

  return (
    <section
      style={{
        margin: '8px 0 0',
        padding: 16,
        border: `1px solid ${theme.border}`,
        borderRadius: 8,
        background: theme.bgElevated,
      }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
        <Space align="start" style={{ justifyContent: 'space-between', width: '100%' }} wrap>
          <div>
            <Text strong>批量生产</Text>
            <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>
              按章节连续生成细纲、正文、脚本、分镜和参考卡；默认跳过已有内容，适合补齐后续章节。
            </Paragraph>
          </div>
          <Space wrap>
            {failed ? (
              <Button loading={loading} onClick={onRetryFailed}>
                只重试失败
              </Button>
            ) : null}
            <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={() => onRun()}>
              开始批量生产
            </Button>
          </Space>
        </Space>

        {runStatus === 'running' ? (
          <Alert
            type="info"
            showIcon
            message="批量生产进行中"
            description="后端会按依赖顺序执行各阶段；关闭或刷新页面不会把已完成的步骤当成空结果。"
          />
        ) : null}
        {runStatus === 'partial' ? (
          <Alert
            type="warning"
            showIcon
            message="批量生产部分完成"
            description="成功和跳过的步骤已经保留，下面只需重试失败步骤，不会重复提交已完成内容。"
          />
        ) : null}
        {runStatus === 'failed' ? (
          <Alert
            type="error"
            showIcon
            message="批量生产失败"
            description="请查看步骤结果和生成日志中的具体错误；修复配置后可以只重试失败步骤。"
          />
        ) : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 0.7fr) minmax(320px, 1.3fr)', gap: 12 }}>
          <Space direction="vertical" size={6}>
            <Text type="secondary">章节范围</Text>
            <Input
              value={chapterRange}
              onChange={(event) => onChapterRangeChange(event.target.value)}
              placeholder="例如：1、1-3、1,3,5"
            />
          </Space>
          <Space direction="vertical" size={6}>
            <Text type="secondary">生产阶段</Text>
            <Checkbox.Group
              options={pipelineStageOptions}
              value={stages}
              onChange={(values) => onStagesChange(values as PipelineStageValue[])}
            />
          </Space>
        </div>

        <Space size={16} wrap>
          <Checkbox checked={skipExisting} onChange={(event) => onSkipExistingChange(event.target.checked)}>
            跳过已有内容
          </Checkbox>
          {!skipExisting ? <Tag color="orange">将生成新版本并作为最新结果</Tag> : null}
          <Checkbox checked={continueOnError} onChange={(event) => onContinueOnErrorChange(event.target.checked)}>
            单步失败后继续
          </Checkbox>
          {result ? (
            <Space size={6} wrap>
              <Tag color="green">生成 {generated}</Tag>
              <Tag>跳过 {skipped}</Tag>
              <Tag color={failed ? 'red' : 'default'}>失败 {failed}</Tag>
            </Space>
          ) : null}
        </Space>

        {rows.length ? (
          <Table
            size="small"
            pagination={false}
            rowKey={(record, index) => `${record.stage}-${record.chapter_number || 'global'}-${index}`}
            columns={pipelineColumns}
            dataSource={rows}
          />
        ) : null}
      </Space>
    </section>
  )
}

export function ProductionStageRail({
  theme,
  stages,
  activeTab,
  onSelect,
}: {
  theme: ThemeColors
  stages: ProductionStageItem[]
  activeTab: string
  onSelect: (tab: string) => void
}) {
  return (
    <nav
      aria-label="项目生产阶段"
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${stages.length}, minmax(132px, 1fr))`,
        gap: 0,
        overflowX: 'auto',
        borderBottom: `1px solid ${theme.borderLight}`,
        background: theme.bgElevated,
      }}
    >
      {stages.map((stage, index) => {
        const isActive = stage.tab === activeTab
        const isComplete = stage.complete >= stage.total
        const ratio = Math.min(1, stage.complete / Math.max(stage.total, 1))
        return (
          <button
            key={stage.key}
            type="button"
            onClick={() => onSelect(stage.tab)}
            aria-current={isActive ? 'step' : undefined}
            style={{
              minWidth: 132,
              padding: '13px 14px 12px',
              border: 'none',
              borderRight: index < stages.length - 1 ? `1px solid ${theme.borderLight}` : 'none',
              borderBottom: isActive ? `2px solid ${theme.primary}` : '2px solid transparent',
              background: isActive ? theme.primaryAlpha(0.1) : 'transparent',
              color: theme.textPrimary,
              textAlign: 'left',
              cursor: 'pointer',
              transition: 'background 180ms ease, transform 160ms ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <Text strong style={{ color: theme.textPrimary, fontSize: 13 }}>{stage.label}</Text>
              <span
                aria-label={`${stage.complete}/${stage.total}`}
                style={{
                  width: 18,
                  height: 18,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: 4,
                  border: `1px solid ${isComplete ? theme.primary : theme.border}`,
                  background: isComplete ? theme.primaryAlpha(0.18) : 'transparent',
                  color: isComplete ? theme.primary : theme.textSecondary,
                  fontSize: 10,
                  fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {isComplete ? '✓' : index + 1}
              </span>
            </div>
            <Text type="secondary" ellipsis={{ tooltip: stage.hint }} style={{ display: 'block', marginTop: 3, fontSize: 12 }}>
              {stage.hint}
            </Text>
            <div style={{ height: 3, marginTop: 9, background: theme.borderLight, overflow: 'hidden' }}>
              <div style={{ width: `${ratio * 100}%`, height: '100%', background: theme.primary, transition: 'width 220ms ease' }} />
            </div>
            <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
              {stage.complete}/{stage.total}
            </Text>
          </button>
        )
      })}
    </nav>
  )
}

export function OutlineTab({
  outline,
  hasOutline,
  productionProfileId,
  loading,
  saving,
  syncLoading,
  extractLoading,
  llmAvailable,
  templateOptions,
  selectedTemplateId,
  onTemplateChange,
  onGenerate,
  onSave,
  onSyncCharacters,
  onExtractCharacters,
  characterColumns,
}: {
  outline: StoryOutline
  hasOutline: boolean
  productionProfileId?: string
  loading: boolean
  saving: boolean
  syncLoading: boolean
  extractLoading: boolean
  llmAvailable: boolean
  templateOptions: TemplateOption[]
  selectedTemplateId?: string
  onTemplateChange: (value: string) => void
  onGenerate: () => void
  onSave: (outline: StoryOutline) => Promise<void>
  onSyncCharacters: () => void
  onExtractCharacters: () => void
  characterColumns: any[]
}) {
  const [draft, setDraft] = useState<StoryOutline>(outline || {})
  // Content-package workflows (storybook, knowledge cards, platform notes,
  // single-shot) start from a topic/material and must not expose the full
  // novel-style outline gate. Narrative workflows keep the complete path.
  const lightweightProduction = productionProfileOptions.some((option) => option.value === productionProfileId && option.family === 'content_package')
  const [detailsOpen, setDetailsOpen] = useState(!lightweightProduction)
  const [jsonDraft, setJsonDraft] = useState('')
  const [jsonError, setJsonError] = useState('')

  useEffect(() => {
    setDraft(outline || {})
    setJsonDraft(JSON.stringify(outline || {}, null, 2))
    setJsonError('')
  }, [outline])

  const updateField = (field: keyof StoryOutline, value: any) => {
    setDraft((prev) => ({ ...prev, [field]: value }))
  }

  const updateStoryArc = (field: keyof NonNullable<StoryOutline['story_arc']>, value: string) => {
    setDraft((prev) => ({ ...prev, story_arc: { ...(prev.story_arc || {}), [field]: value } }))
  }

  const saveJson = async () => {
    try {
      const parsed = JSON.parse(jsonDraft || '{}')
      setJsonError('')
      setDraft(parsed)
      await onSave(parsed)
    } catch (error: any) {
      setJsonError(error?.message || 'JSON 格式不正确')
    }
  }

  if (!hasOutline) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%', padding: '24px 0' }}>
        <Alert
          message={lightweightProduction ? '轻量故事创作' : '创建故事蓝图'}
          description={lightweightProduction
            ? '先填标题和一句话创意即可生成，角色、世界观和叙事规则都是可选补充。'
            : '可先在下方手动填写故事大纲后保存；AI 生成需要先在设置中配置文本模型。'}
          type="info"
          showIcon
        />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div>
            <Title level={4} style={{ marginBottom: 4 }}>
              新故事大纲
            </Title>
            <Text type="secondary">保存后可以继续补充角色、章节规划等内容。</Text>
          </div>
          <Space wrap style={{ justifyContent: 'flex-end' }}>
            <PromptTemplateSelect
              value={selectedTemplateId}
              options={templateOptions}
              placeholder="大纲模板"
              onChange={onTemplateChange}
            />
            <Tooltip title={llmAvailable ? '' : '请先在设置中配置文本模型'}>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={loading}
                onClick={onGenerate}
                disabled={!llmAvailable}
              >
                {lightweightProduction ? '生成故事页纲' : '生成故事大纲'}
              </Button>
            </Tooltip>
            <Button type="primary" loading={saving} onClick={() => onSave(draft)}>
              保存大纲
            </Button>
          </Space>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(240px, 1fr)', gap: 12 }}>
          <EditorField label="标题">
            <Input value={draft.title} onChange={(event) => updateField('title', event.target.value)} />
          </EditorField>
          <EditorField label="类型">
            <TextArea
              value={listToLines(draft.genre)}
              onChange={(event) => updateField('genre', linesToList(event.target.value))}
              autoSize={{ minRows: 1, maxRows: 3 }}
            />
          </EditorField>
          <EditorField label="一句话卖点">
            <Input value={draft.logline} onChange={(event) => updateField('logline', event.target.value)} />
          </EditorField>
          {lightweightProduction ? null : (
            <EditorField label="目标读者">
              <Input value={draft.target_reader} onChange={(event) => updateField('target_reader', event.target.value)} />
            </EditorField>
          )}
        </div>

        {lightweightProduction ? (
          <Button type="link" onClick={() => setDetailsOpen((open) => !open)}>
            {detailsOpen ? '收起详细设定' : '补充详细设定（可选）'}
          </Button>
        ) : null}

        {(!lightweightProduction || detailsOpen) ? <>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <EditorField label="核心前提">
            <TextArea value={draft.premise} onChange={(event) => updateField('premise', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
          <EditorField label="世界观">
            <TextArea value={draft.worldview} onChange={(event) => updateField('worldview', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
          <EditorField label="主线冲突">
            <TextArea value={draft.main_conflict} onChange={(event) => updateField('main_conflict', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
          <EditorField label="观众情绪">
            <TextArea value={draft.audience_emotion} onChange={(event) => updateField('audience_emotion', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
          </EditorField>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <EditorField label="卖点" hint="一行一条">
            <TextArea value={listToLines(draft.selling_points)} onChange={(event) => updateField('selling_points', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
          <EditorField label="叙事规则" hint="一行一条">
            <TextArea value={listToLines(draft.narrative_rules)} onChange={(event) => updateField('narrative_rules', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
          <EditorField label="主题" hint="一行一条">
            <TextArea value={listToLines(draft.themes)} onChange={(event) => updateField('themes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
          <EditorField label="制作约束" hint="一行一条，会影响后续分镜/生图">
            <TextArea value={listToLines(draft.production_notes)} onChange={(event) => updateField('production_notes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
          </EditorField>
        </div>

        <WorkbenchSection title="故事弧线">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <EditorField label="开局">
              <TextArea value={draft.story_arc?.beginning} onChange={(event) => updateStoryArc('beginning', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
            <EditorField label="中段">
              <TextArea value={draft.story_arc?.middle} onChange={(event) => updateStoryArc('middle', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
            <EditorField label="高潮">
              <TextArea value={draft.story_arc?.climax} onChange={(event) => updateStoryArc('climax', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
            <EditorField label="结局方向">
              <TextArea value={draft.story_arc?.ending_direction} onChange={(event) => updateStoryArc('ending_direction', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
            </EditorField>
          </div>
        </WorkbenchSection>
        </> : null}
      </Space>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ minWidth: 0, flex: '1 1 360px' }}>
          <Title level={4} style={{ marginBottom: 4 }}>
            {outline.title || '故事大纲'}
          </Title>
          <Text type="secondary" style={{ display: 'block', maxWidth: '72ch' }}>
            {outline.logline || '未填写一句话卖点'}
          </Text>
        </div>
        <Space wrap style={{ justifyContent: 'flex-end' }}>
          <PromptTemplateSelect
            value={selectedTemplateId}
            options={templateOptions}
            placeholder="大纲模板"
            onChange={onTemplateChange}
          />
          <Button icon={<UserOutlined />} loading={syncLoading} onClick={onSyncCharacters}>
            同步角色库
          </Button>
          <Button icon={<RobotOutlined />} loading={extractLoading} onClick={onExtractCharacters}>
            提取角色并预览
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={() => downloadTextFile(`${projectMarkdownFilename(draft.title || outline.title, 'outline')}.md`, buildOutlineMarkdown(draft))}
          >
            导出 Markdown
          </Button>
          <Button type="primary" loading={saving} onClick={() => onSave(draft)}>
            保存大纲
          </Button>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={onGenerate}>
            重新生成
          </Button>
        </Space>
      </div>

      <Tabs
        items={[
          {
            key: 'structured',
            label: '结构化编辑',
            children: (
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(240px, 1fr)', gap: 12 }}>
                  <EditorField label="标题">
                    <Input value={draft.title} onChange={(event) => updateField('title', event.target.value)} />
                  </EditorField>
                  <EditorField label="类型">
                    <TextArea
                      value={listToLines(draft.genre)}
                      onChange={(event) => updateField('genre', linesToList(event.target.value))}
                      autoSize={{ minRows: 1, maxRows: 3 }}
                    />
                  </EditorField>
                  <EditorField label="一句话卖点">
                    <Input value={draft.logline} onChange={(event) => updateField('logline', event.target.value)} />
                  </EditorField>
                  <EditorField label="目标读者">
                    <Input value={draft.target_reader} onChange={(event) => updateField('target_reader', event.target.value)} />
                  </EditorField>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                  <EditorField label="核心前提">
                    <TextArea value={draft.premise} onChange={(event) => updateField('premise', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                  <EditorField label="世界观">
                    <TextArea value={draft.worldview} onChange={(event) => updateField('worldview', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                  <EditorField label="主线冲突">
                    <TextArea value={draft.main_conflict} onChange={(event) => updateField('main_conflict', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                  <EditorField label="观众情绪">
                    <TextArea value={draft.audience_emotion} onChange={(event) => updateField('audience_emotion', event.target.value)} autoSize={{ minRows: 4, maxRows: 9 }} />
                  </EditorField>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                  <EditorField label="卖点" hint="一行一条">
                    <TextArea value={listToLines(draft.selling_points)} onChange={(event) => updateField('selling_points', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                  <EditorField label="叙事规则" hint="一行一条">
                    <TextArea value={listToLines(draft.narrative_rules)} onChange={(event) => updateField('narrative_rules', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                  <EditorField label="主题" hint="一行一条">
                    <TextArea value={listToLines(draft.themes)} onChange={(event) => updateField('themes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                  <EditorField label="制作约束" hint="一行一条，会影响后续分镜/生图">
                    <TextArea value={listToLines(draft.production_notes)} onChange={(event) => updateField('production_notes', linesToList(event.target.value))} autoSize={{ minRows: 4, maxRows: 8 }} />
                  </EditorField>
                </div>

                <WorkbenchSection title="故事弧线">
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                    <EditorField label="开局">
                      <TextArea value={draft.story_arc?.beginning} onChange={(event) => updateStoryArc('beginning', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                    <EditorField label="中段">
                      <TextArea value={draft.story_arc?.middle} onChange={(event) => updateStoryArc('middle', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                    <EditorField label="高潮">
                      <TextArea value={draft.story_arc?.climax} onChange={(event) => updateStoryArc('climax', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                    <EditorField label="结局方向">
                      <TextArea value={draft.story_arc?.ending_direction} onChange={(event) => updateStoryArc('ending_direction', event.target.value)} autoSize={{ minRows: 3, maxRows: 7 }} />
                    </EditorField>
                  </div>
                </WorkbenchSection>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                  <EditorField label="叙事气质">
                    <TextArea value={draft.tone} onChange={(event) => updateField('tone', event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
                  </EditorField>
                  <EditorField label="视觉风格">
                    <TextArea value={draft.visual_style} onChange={(event) => updateField('visual_style', event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
                  </EditorField>
                  <EditorField label="统一生图提示">
                    <TextArea value={draft.image_style_prompt} onChange={(event) => updateField('image_style_prompt', event.target.value)} autoSize={{ minRows: 3, maxRows: 8 }} />
                  </EditorField>
                </div>
              </Space>
            ),
          },
          {
            key: 'json',
            label: 'JSON 高级编辑',
            children: (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Text type="secondary">复杂角色、场景、关系图可以在这里直接编辑完整 JSON。</Text>
                <TextArea
                  value={jsonDraft}
                  onChange={(event) => setJsonDraft(event.target.value)}
                  autoSize={{ minRows: 18, maxRows: 34 }}
                  style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' }}
                />
                {jsonError ? <Text type="danger">{jsonError}</Text> : null}
                <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
                  <Button onClick={() => setJsonDraft(JSON.stringify(draft || {}, null, 2))}>同步结构化草稿</Button>
                  <Button type="primary" loading={saving} onClick={saveJson}>保存 JSON</Button>
                </Space>
              </Space>
            ),
          },
          {
            key: 'preview',
            label: '预览',
            children: (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <InfoBlock title="核心前提" text={draft.premise} />
                  <InfoBlock title="世界观" text={draft.worldview} />
                  <InfoBlock title="主线冲突" text={draft.main_conflict} />
                  <InfoBlock title="观众情绪" text={draft.audience_emotion} />
                  <InfoListBlock title="卖点" items={draft.selling_points || []} />
                  <InfoListBlock title="叙事规则" items={draft.narrative_rules || []} />
                </div>
              </Space>
            ),
          },
        ]}
      />

      <div>
        <Title level={5}>角色</Title>
        <Table
          size="small"
          rowKey={(record: StoryOutlineCharacter, index?: number) => record.name || String(index)}
          columns={characterColumns}
          dataSource={draft.characters || []}
          pagination={false}
        />
      </div>
    </Space>
  )
}

