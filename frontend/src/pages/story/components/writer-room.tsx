/**
 * 创作项目工作台：components/writer-room.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { type CreativeProjectContinuityCandidate } from '../../../api'
import { ChapterPlanItem } from '../../../types/api'
import { ProseParagraphDiff, TeamRehearsalPanel, WriterRoomLogSummary, WriterRoomQualitySummaryPanel } from './writer-room-parts'
import { panelStyle, writerRoomBatchControlStyle, writerRoomComparePaneStyle, writerRoomContextBlockStyle, writerRoomContextGridStyle, writerRoomContinuityItemStyle, writerRoomContinuityStyle, writerRoomIssueStyle, writerRoomMainPanelStyle, writerRoomMetricGridStyle, writerRoomMetricStyle, writerRoomParagraphButtonActiveStyle, writerRoomParagraphButtonStyle, writerRoomParagraphListStyle, writerRoomPipelineStyle, writerRoomPreviewStyle, writerRoomProgressStyle, writerRoomPromoteSummaryStyle, writerRoomShellStyle, writerRoomStepButtonActiveStyle, writerRoomStepButtonStyle, writerRoomStepIndexStyle, writerRoomStepListStyle, writerRoomStepTitleStyle, writerRoomVersionStatusStyle, writerRoomWorkspaceStyle } from '../styles'
import { ProjectContent, ProjectGenerationLog, TemplateOption, WriterRoomReviewIssue } from '../types'
import { findWriterRoomLog, qualitySummaryForContent, reviewIssuesForContent, splitWriterRoomParagraphs, writerRoomAgentNames, writerRoomContentWordCount, writerRoomIssueSeverityColor, writerRoomPreviewText, writerRoomStepDescriptions, writerRoomStepInputs, writerRoomStepLabelMap, writerRoomStepNextHints, writerRoomStepOptions, writerRoomStepOutputs, writerRoomStepStatusColor } from '../utils'
import { ThunderboltOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Checkbox, Empty, Input, Modal, Progress, Segmented, Select, Space, Tag, Typography, message } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function WriterRoomTab({
  chapters,
  activeChapterNumber,
  onActiveChapterChange,
  contents,
  loadError,
  loadingContents,
  onRetryContents,
  contentForChapter,
  logs,
  templateOptionsByStage,
  selectedPromptTemplates,
  onTemplateChange,
  llmOptions,
  selectedLlm,
  selectedModel,
  modelOptions,
  onLlmChange,
  onModelChange,
  loading,
  rehearsalMode,
  onRehearsalModeChange,
  onRunStep,
  onRunBatch,
  onPromote,
  continuityCandidates,
  continuitySummary,
  onResolveContinuityCandidate,
  onRewriteParagraph,
}: {
  chapters: ChapterPlanItem[]
  activeChapterNumber: number
  onActiveChapterChange: (value: number) => void
  contents: ProjectContent[]
  loadError?: string
  loadingContents: boolean
  onRetryContents: () => void
  contentForChapter: (contentType: string, chapterNumber: number) => ProjectContent | undefined
  logs: ProjectGenerationLog[]
  templateOptionsByStage: Record<string, TemplateOption[]>
  selectedPromptTemplates: Record<string, string>
  onTemplateChange: (stage: string, value: string) => void
  llmOptions: TemplateOption[]
  selectedLlm: string
  selectedModel: string
  modelOptions: TemplateOption[]
  onLlmChange: (value: string) => void
  onModelChange: (value: string) => void
  loading: boolean
  rehearsalMode: 'fast' | 'team'
  onRehearsalModeChange: (value: 'fast' | 'team') => void
  onRunStep: (step: string, chapterNumber: number, contentId?: string, instruction?: string, selectedText?: string) => void
  onRunBatch: (chapterNumber: number, steps?: string[], contentId?: string) => void
  onPromote: (contentId: string) => void
  continuityCandidates: CreativeProjectContinuityCandidate[]
  continuitySummary: Record<string, any> | null
  onResolveContinuityCandidate: (candidateId: string, action: 'accept' | 'ignore') => void
  onRewriteParagraph: (contentId: string, paragraphIndex: number, instruction: string) => void
}) {
  const latestWriterRoomForStep = (step: string) =>
    contents
      .filter(
        (content) =>
          content.content_type === step &&
          Number(content.chapter_number || content.episode_number || 0) === activeChapterNumber,
      )
      .sort((left, right) => right.version - left.version || String(right.created_at || '').localeCompare(String(left.created_at || '')))[0]
  const latestByStep = Object.fromEntries(
    writerRoomStepOptions.map((step) => [
      step.value,
      latestWriterRoomForStep(step.value),
    ]),
  ) as Record<string, ProjectContent | undefined>
  const canPromote = latestByStep.prose_rewrite || latestByStep.prose_humanized || latestByStep.prose_draft
  const currentNovelBody = contentForChapter('novel_body', activeChapterNumber)
  const [partialRewriteInstruction, setPartialRewriteInstruction] = useState('压低解释，增加具体动作、物件互动和对白潜台词。')
  const [selectedParagraphIndex, setSelectedParagraphIndex] = useState(0)
  const [activeStep, setActiveStep] = useState(writerRoomStepOptions[0].value)
  const [batchSteps, setBatchSteps] = useState<string[]>([
    'scene_beats',
    'character_rehearsal',
    'prose_draft',
    'prose_humanized',
    'prose_review',
  ])
  const [promoteTarget, setPromoteTarget] = useState<ProjectContent | null>(null)
  const [promoteChecked, setPromoteChecked] = useState(false)
  const [selectedContentIds, setSelectedContentIds] = useState<Record<string, string>>({})
  const [compareMode, setCompareMode] = useState<'side-by-side' | 'diff'>('side-by-side')
  const lastActiveChapterRef = useRef<number | null>(null)
  const hasAutoSelectedReadableStepRef = useRef(false)

  const versionsForStep = (step: string) =>
    contents
      .filter(
        (content) =>
          content.content_type === step &&
          Number(content.chapter_number || content.episode_number || 0) === activeChapterNumber,
      )
      .sort((left, right) => right.version - left.version || String(right.created_at || '').localeCompare(String(left.created_at || '')))

  const selectedVersionForStep = (step: string) => {
    const versions = versionsForStep(step)
    return versions.find((content) => content.id === selectedContentIds[step]) || latestByStep[step]
  }

  // A user may be inspecting an older candidate on purpose. The next Writer
  // Room action must use that visible candidate, never silently swap to the
  // newest one of the same type.
  const sourceForStep = (step: string) => {
    if (step === 'character_rehearsal') return selectedVersionForStep('scene_beats')
    if (step === 'prose_draft') return selectedVersionForStep('character_rehearsal') || selectedVersionForStep('scene_beats')
    if (step === 'prose_humanized') return selectedVersionForStep('prose_draft') || currentNovelBody
    if (step === 'prose_review' || step === 'prose_rewrite') {
      return selectedVersionForStep('prose_humanized') || selectedVersionForStep('prose_draft') || currentNovelBody
    }
    return undefined
  }
  const rewriteSource = sourceForStep('prose_rewrite')
  const rewriteParagraphs = useMemo(
    () => splitWriterRoomParagraphs(rewriteSource?.text_content || ''),
    [rewriteSource?.text_content],
  )

  const runStep = (step: string, instruction?: string) => {
    const sourceId = sourceForStep(step)?.id
    onRunStep(step, activeChapterNumber, sourceId, instruction)
  }

  const runRewriteFromIssue = (issue: WriterRoomReviewIssue) => {
    const instruction = issue.rewrite_instruction || issue.suggestion || issue.problem || ''
    onRunStep('prose_rewrite', activeChapterNumber, rewriteSource?.id, instruction)
  }

  const runRewriteFromAllIssues = (issues: WriterRoomReviewIssue[]) => {
    const instruction = issues
      .map((issue, index) => {
        const target = issue.location ? `位置：${issue.location}` : '位置：全文相关'
        const problem = issue.problem ? `问题：${issue.problem}` : ''
        const suggestion = issue.rewrite_instruction || issue.suggestion || ''
        return `${index + 1}. ${target}\n${problem}\n重写要求：${suggestion}`.trim()
      })
      .join('\n\n')
    onRunStep('prose_rewrite', activeChapterNumber, rewriteSource?.id, instruction)
  }

  const runParagraphRewrite = () => {
    if (!rewriteSource?.id) {
      message.warning('请先选择一个可重写的正文候选')
      return
    }
    if (!rewriteParagraphs.length) {
      message.warning('当前候选没有可定位的段落')
      return
    }
    onRewriteParagraph(
      rewriteSource.id,
      selectedParagraphIndex,
      partialRewriteInstruction || '只重写该段落，保留剧情事实、人物关系和前后文语气。',
    )
  }

  const writerRoomRows = writerRoomStepOptions.map((step, index) => {
    const content = latestByStep[step.value]
    const latestLog = findWriterRoomLog(logs, content)
    return {
      step,
      index,
      content,
      latestLog,
      statusColor: writerRoomStepStatusColor(content, latestLog),
      wordCount: writerRoomContentWordCount(content),
      description: writerRoomStepDescriptions[step.value] || '',
      agentName: writerRoomAgentNames[step.value] || '工序角色',
    }
  })
  const activeRow = writerRoomRows.find((row) => row.step.value === activeStep) || writerRoomRows[0]
  const activeStepVersions = versionsForStep(activeRow.step.value)
  const activeContent =
    activeStepVersions.find((content) => content.id === selectedContentIds[activeRow.step.value]) || activeRow?.content
  const activeLog = findWriterRoomLog(logs, activeContent)
  const activePreview = writerRoomPreviewText(activeContent)
  const activeTeamPerformances =
    activeContent?.content_type === 'character_rehearsal'
      ? ((activeContent.data as Record<string, any>)?.character_performances || [])
      : []
  const activeTeamJoined =
    activeContent?.content_type === 'character_rehearsal'
      ? ((activeContent.data as Record<string, any>)?.joined_observation || '')
      : ''
  const activeReviewIssues = activeRow?.step.value === 'prose_review' ? reviewIssuesForContent(activeContent) : []
  const activeQualitySummary = activeRow?.step.value === 'prose_review' ? qualitySummaryForContent(activeContent) : null
  const activeContinuityCandidates = activeContent?.content_type === 'prose_review'
    ? continuityCandidates.filter((candidate) => candidate.source_content_id === activeContent.id)
    : []
  const activeIsProseResult = ['prose_draft', 'prose_humanized', 'prose_rewrite'].includes(activeRow?.step.value || '')
  const preferredReadableStep = latestByStep.prose_rewrite
    ? 'prose_rewrite'
    : latestByStep.prose_humanized
      ? 'prose_humanized'
      : latestByStep.prose_draft
        ? 'prose_draft'
        : writerRoomStepOptions[0].value
  const activeCandidateIsPromoted = Boolean(
    activeIsProseResult && activeContent && currentNovelBody?.source_content_id === activeContent.id,
  )
  const completedCount = writerRoomRows.filter((row) => row.content).length
  const progressPercent = Math.round((completedCount / Math.max(writerRoomRows.length, 1)) * 100)
  const candidateContent = activeIsProseResult ? activeContent : canPromote
  const nextRow = writerRoomRows[activeRow.index + 1]
  const inputLabels = writerRoomStepInputs[activeRow.step.value] || []
  const outputLabels = writerRoomStepOutputs[activeRow.step.value] || []
  const nextHint = writerRoomStepNextHints[activeRow.step.value] || ''
  const batchStepOptions = writerRoomStepOptions.map((step) => ({
    label: step.label,
    value: step.value,
  }))

  useEffect(() => {
    if (lastActiveChapterRef.current !== activeChapterNumber) {
      lastActiveChapterRef.current = activeChapterNumber
      hasAutoSelectedReadableStepRef.current = preferredReadableStep !== writerRoomStepOptions[0].value
      setSelectedContentIds({})
      setActiveStep(preferredReadableStep)
      return
    }

    // Content can arrive after the workbench mounts. Auto-open the first
    // readable candidate once, but never override a deliberate step click.
    if (!hasAutoSelectedReadableStepRef.current && preferredReadableStep !== writerRoomStepOptions[0].value) {
      hasAutoSelectedReadableStepRef.current = true
      setActiveStep(preferredReadableStep)
    }
  }, [activeChapterNumber, preferredReadableStep])

  useEffect(() => {
    if (selectedParagraphIndex >= rewriteParagraphs.length) {
      setSelectedParagraphIndex(Math.max(0, rewriteParagraphs.length - 1))
    }
  }, [rewriteParagraphs.length, selectedParagraphIndex])

  const jumpToNextStep = () => {
    if (!nextRow) return
    setActiveStep(nextRow.step.value)
    if (!nextRow.content) {
      runStep(nextRow.step.value)
    }
  }

  const openPromoteDialog = (content: ProjectContent) => {
    setPromoteTarget(content)
    setPromoteChecked(false)
  }

  const confirmPromote = () => {
    if (!promoteTarget) return
    onPromote(promoteTarget.id)
    setPromoteTarget(null)
    setPromoteChecked(false)
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <section style={writerRoomShellStyle}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start" wrap>
          <Space direction="vertical" size={6} style={{ maxWidth: 760 }}>
            <Space size={8} wrap>
              <Text strong style={{ fontSize: 18 }}>小说写作室</Text>
              <Tag color="blue">分阶段写作流水线</Tag>
              <Tag>正文不自动覆盖</Tag>
            </Space>
            <Text type="secondary">
              先让导演拆戏、角色演一遍，再写初稿、做人味润色和主编审稿；每一步都保留为候选产物，确认后再提升为正式正文。
            </Text>
          </Space>
          <Space wrap align="start">
            <Select
              value={activeChapterNumber}
              style={{ width: 180 }}
              onChange={onActiveChapterChange}
              options={chapters.map((chapter) => ({
                value: chapter.chapter_number,
                label: `第 ${chapter.chapter_number} 章 ${chapter.title || ''}`,
              }))}
            />
            <Select
              placeholder="文本模型"
              value={selectedLlm || undefined}
              style={{ width: 210 }}
              options={llmOptions}
              onChange={onLlmChange}
            />
            <Select
              placeholder="模型"
              value={selectedModel || undefined}
              style={{ width: 240 }}
              options={modelOptions}
              onChange={onModelChange}
              disabled={!selectedLlm}
            />
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={loading}
              disabled={!batchSteps.length}
              onClick={() => {
                const orderedSteps = writerRoomStepOptions
                  .map((item) => item.value)
                  .filter((step) => batchSteps.includes(step))
                const source = orderedSteps.length ? sourceForStep(orderedSteps[0]) : undefined
                onRunBatch(activeChapterNumber, orderedSteps, source?.id)
              }}
            >
              按勾选生成候选
            </Button>
          </Space>
        </Space>
        <div style={writerRoomProgressStyle}>
          <Progress percent={progressPercent} size="small" showInfo={false} strokeColor="var(--primary)" />
          <Text type="secondary">已完成 {completedCount}/{writerRoomRows.length}</Text>
        </div>
        <div style={writerRoomBatchControlStyle}>
          <Segmented
            value={rehearsalMode}
            onChange={(value) => onRehearsalModeChange(value as 'fast' | 'team')}
            options={[
              { label: '角色团队推演（每角色子智能体）', value: 'team' },
              { label: '快速演绎（单模型）', value: 'fast' },
            ]}
            block
            style={{ marginBottom: 10 }}
          />
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
              <Text type="secondary">批量执行步骤</Text>
              <Space size={6}>
                <Button size="small" onClick={() => setBatchSteps(batchStepOptions.map((item) => String(item.value)))}>
                  全选
                </Button>
                <Button size="small" onClick={() => setBatchSteps(['scene_beats', 'character_rehearsal', 'prose_draft', 'prose_humanized', 'prose_review'])}>
                  推荐
                </Button>
              </Space>
            </Space>
            <Checkbox.Group
              value={batchSteps}
              options={batchStepOptions}
              onChange={(values) => setBatchSteps(values.map(String))}
            />
          </Space>
        </div>
      </section>

      <div style={writerRoomWorkspaceStyle}>
        <section style={writerRoomPipelineStyle}>
          <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
            <Space direction="vertical" size={2}>
              <Text strong>工序</Text>
              <Text type="secondary">角色演绎支持「角色团队推演」（每角色一个独立子智能体）与「快速演绎」（单模型）；其余工序为单模型分阶段执行。</Text>
            </Space>
            <div style={writerRoomStepListStyle}>
              {writerRoomRows.map((row) => {
                const isActive = row.step.value === activeRow.step.value
                return (
                  <button
                    key={row.step.value}
                    type="button"
                    onClick={() => setActiveStep(row.step.value)}
                    style={isActive ? writerRoomStepButtonActiveStyle : writerRoomStepButtonStyle}
                  >
                    <span style={writerRoomStepIndexStyle}>{row.index + 1}</span>
                    <span style={{ minWidth: 0, flex: 1 }}>
                      <span style={writerRoomStepTitleStyle}>
                        <Badge color={row.statusColor} />
                        <Text strong>{row.step.label}</Text>
                        {(row.step as { optional?: boolean })?.optional ? (
                          <Tag color="orange" style={{ marginLeft: 6 }}>可选</Tag>
                        ) : null}
                        <Tag style={{ marginLeft: 'auto' }}>{row.agentName}</Tag>
                      </span>
                      <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
                        {row.content ? `v${row.content.version} · ${row.wordCount || '-'}字` : '尚未生成'}
                      </Text>
                    </span>
                  </button>
                )
              })}
            </div>
          </Space>
        </section>

        <section style={writerRoomMainPanelStyle}>
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            {loadError ? (
              <Alert
                type="error"
                showIcon
                message="写作室候选加载失败"
                description={loadError}
                action={<Button size="small" onClick={onRetryContents}>重试读取</Button>}
              />
            ) : null}
            {loadingContents && !contents.length ? <Alert type="info" showIcon message="正在读取本章写作室候选" /> : null}
            <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start" wrap>
              <Space direction="vertical" size={4} style={{ maxWidth: 760 }}>
                <Space size={8} wrap>
                  <Text strong style={{ fontSize: 17 }}>{activeRow.step.label}</Text>
                  <Tag color="processing">{activeRow.agentName}</Tag>
                  {activeContent ? <Tag color="green">v{activeContent.version}</Tag> : <Tag>未生成</Tag>}
                  {activeStepVersions.length > 1 ? (
                    <Select
                      size="small"
                      value={activeContent?.id}
                      style={{ minWidth: 150 }}
                      onChange={(contentId) =>
                        setSelectedContentIds((previous) => ({ ...previous, [activeRow.step.value]: contentId }))
                      }
                      options={activeStepVersions.map((content) => ({
                        value: content.id,
                        label: `候选 v${content.version} · ${writerRoomContentWordCount(content)} 字`,
                      }))}
                    />
                  ) : null}
                </Space>
                <Text type="secondary">{activeRow.description}</Text>
              </Space>
              <Space wrap>
                <Button loading={loading} onClick={() => runStep(activeRow.step.value)}>
                  {activeContent ? '生成新候选' : '生成候选'}
                </Button>
              </Space>
            </Space>

            <div style={writerRoomMetricGridStyle}>
              <div style={writerRoomMetricStyle}>
                <Text type="secondary">状态</Text>
                <Text strong>{activeContent ? '已有产物' : activeLog ? activeLog.status : '等待生成'}</Text>
              </div>
              <div style={writerRoomMetricStyle}>
                <Text type="secondary">字数</Text>
                <Text strong>{writerRoomContentWordCount(activeContent) || '-'}</Text>
              </div>
              <div style={writerRoomMetricStyle}>
                <Text type="secondary">Prompt</Text>
                <Text strong>{selectedPromptTemplates[activeRow.step.value] ? '自定义' : '默认'}</Text>
              </div>
            </div>

            <div style={writerRoomContextGridStyle}>
              <div style={writerRoomContextBlockStyle}>
                <Text type="secondary">上游输入</Text>
                <Space wrap size={[4, 4]}>
                  {inputLabels.map((label) => (
                    <Tag key={label}>{label}</Tag>
                  ))}
                </Space>
                {activeContent?.source_content_id ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    本版来源：{(() => {
                      const source = contents.find((content) => content.id === activeContent.source_content_id)
                      return source ? `${writerRoomStepLabelMap[source.content_type] || source.content_type} v${source.version}` : '历史内容'
                    })()}
                  </Text>
                ) : null}
                {!activeContent && sourceForStep(activeRow.step.value) ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    将使用：{writerRoomStepLabelMap[sourceForStep(activeRow.step.value)?.content_type || ''] || sourceForStep(activeRow.step.value)?.content_type}
                    {' '}v{sourceForStep(activeRow.step.value)?.version}
                  </Text>
                ) : null}
              </div>
              <div style={writerRoomContextBlockStyle}>
                <Text type="secondary">产物用途</Text>
                <Space wrap size={[4, 4]}>
                  {outputLabels.map((label) => (
                    <Tag key={label} color="blue">{label}</Tag>
                  ))}
                </Space>
              </div>
              <div style={writerRoomContextBlockStyle}>
                <Text type="secondary">推荐下一步</Text>
                <Text>{nextHint}</Text>
                {nextRow ? (
                  <Button size="small" loading={loading} onClick={jumpToNextStep}>
                    {nextRow.content ? `查看${nextRow.step.label}` : `生成${nextRow.step.label}`}
                  </Button>
                ) : activeContent && activeIsProseResult ? (
                  <Text type="secondary">已经到最后一个节点，可以对比后提升正文。</Text>
                ) : null}
              </div>
            </div>

            <Select
              allowClear
              size="middle"
              placeholder="使用默认 Prompt"
              value={selectedPromptTemplates[activeRow.step.value] || undefined}
              options={templateOptionsByStage[activeRow.step.value] || []}
              onChange={(value) => onTemplateChange(activeRow.step.value, value || '')}
            />

            <div style={writerRoomVersionStatusStyle}>
              <Space wrap size={[6, 6]}>
                {activeIsProseResult ? (
                  <Tag color={activeCandidateIsPromoted ? 'green' : 'gold'}>
                    {activeCandidateIsPromoted ? '已提升为当前正文' : '候选稿，尚未提升'}
                  </Tag>
                ) : (
                  <Tag>工作室中间产物，不是正文</Tag>
                )}
                {currentNovelBody ? <Tag color="blue">当前正文 v{currentNovelBody.version}</Tag> : <Tag>当前章节暂无正式正文</Tag>}
              </Space>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {activeIsProseResult
                  ? activeCandidateIsPromoted
                    ? '当前预览与正文阅读区使用同一版本。'
                    : '候选不会自动覆盖正文，请在下方对比后手动提升。'
                  : '场景节拍、角色演绎和审稿用于下一步写作，内容与正文不同是正常的。'}
              </Text>
            </div>

            {activeLog ? (
              <WriterRoomLogSummary log={activeLog} />
            ) : activeContent ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该历史候选暂无可追溯日志" />
            ) : null}

            {activeContent ? (
              activeTeamPerformances.length ? (
                <div style={writerRoomPreviewStyle}>
                  <TeamRehearsalPanel performances={activeTeamPerformances} joined={activeTeamJoined} />
                </div>
              ) : (
                <div style={writerRoomPreviewStyle}>
                  <Paragraph ellipsis={{ rows: 22, expandable: true }} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {activePreview}
                  </Paragraph>
                </div>
              )
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前节点还没有生成结果" />
            )}

            {activeQualitySummary ? <WriterRoomQualitySummaryPanel summary={activeQualitySummary} /> : null}
            {activeRow.step.value === 'prose_review' ? (
              <div style={writerRoomContinuityStyle}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
                    <Space direction="vertical" size={0}>
                      <Text strong>连续性事实候选</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        已锁定 {continuitySummary?.locked_fact_count || 0} 条事实，待确认 {continuitySummary?.pending_candidate_count || 0} 条
                      </Text>
                    </Space>
                    <Tag color="blue">仅确认后进入后续上下文</Tag>
                  </Space>
                  {activeContinuityCandidates.length ? activeContinuityCandidates.map((candidate) => (
                    <div key={candidate.id} style={writerRoomContinuityItemStyle}>
                      <Space direction="vertical" size={5} style={{ width: '100%' }}>
                        <Space wrap>
                          <Tag color={candidate.status === 'pending' ? 'gold' : 'green'}>{candidate.status}</Tag>
                          <Tag>{candidate.entity_type}</Tag>
                          <Tag color="blue">{candidate.target_fact_type}</Tag>
                          {candidate.entity_name ? <Text strong>{candidate.entity_name}</Text> : null}
                        </Space>
                        <Text>{candidate.claim || candidate.evidence_excerpt}</Text>
                        {candidate.evidence_excerpt ? <Text type="secondary" style={{ fontSize: 12 }}>证据：{candidate.evidence_excerpt}</Text> : null}
                        {candidate.status === 'pending' ? (
                          <Space>
                            <Button size="small" type="primary" loading={loading} onClick={() => onResolveContinuityCandidate(candidate.id, 'accept')}>确认事实</Button>
                            <Button size="small" loading={loading} onClick={() => onResolveContinuityCandidate(candidate.id, 'ignore')}>忽略</Button>
                          </Space>
                        ) : null}
                      </Space>
                    </div>
                  )) : <Text type="secondary">当前审稿没有提取到需要锁定的连续性事实。</Text>}
                </Space>
              </div>
            ) : null}

            {activeReviewIssues.length ? (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
                  <Text strong>可执行审稿意见</Text>
                  <Button size="small" loading={loading} onClick={() => runRewriteFromAllIssues(activeReviewIssues)}>
                    应用全部重写
                  </Button>
                </Space>
                {activeReviewIssues.slice(0, 6).map((issue, index) => (
                  <div key={`${issue.category || 'issue'}-${index}`} style={writerRoomIssueStyle}>
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Space wrap>
                        <Tag color={writerRoomIssueSeverityColor(issue.severity)}>{issue.severity || 'normal'}</Tag>
                        {issue.category ? <Tag>{issue.category}</Tag> : null}
                        {issue.location ? <Text type="secondary">{issue.location}</Text> : null}
                      </Space>
                      {issue.problem ? <Text>{issue.problem}</Text> : null}
                      {issue.suggestion || issue.rewrite_instruction ? (
                        <Text type="secondary">{issue.rewrite_instruction || issue.suggestion}</Text>
                      ) : null}
                      <Button size="small" loading={loading} onClick={() => runRewriteFromIssue(issue)}>
                        按此问题重写
                      </Button>
                    </Space>
                  </div>
                ))}
              </Space>
            ) : null}
          </Space>
        </section>
      </div>

      <section style={panelStyle}>
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
          <Space style={{ width: '100%', justifyContent: 'space-between' }} align="center" wrap>
            <Space direction="vertical" size={4}>
              <Space wrap>
                <Text strong>正文对比</Text>
                {currentNovelBody ? <Tag>正式 v{currentNovelBody.version}</Tag> : <Tag>暂无正式正文</Tag>}
                {candidateContent ? <Tag color="processing">{writerRoomStepLabelMap[candidateContent.content_type] || candidateContent.content_type} v{candidateContent.version}</Tag> : null}
              </Space>
              {candidateContent?.source_content_id ? <Text type="secondary" style={{ fontSize: 12 }}>候选来源已绑定到内容版本，可从上方生成日志回溯请求与响应。</Text> : null}
            </Space>
            <Space wrap>
              <Segmented
                size="small"
                value={compareMode}
                onChange={(value) => setCompareMode(value as 'side-by-side' | 'diff')}
                options={[{ label: '并列阅读', value: 'side-by-side' }, { label: '仅看差异', value: 'diff' }]}
              />
              {candidateContent ? (
                <Button type="primary" loading={loading} onClick={() => openPromoteDialog(candidateContent)}>
                  审核并提升候选
                </Button>
              ) : null}
            </Space>
          </Space>
          {candidateContent ? (
            compareMode === 'diff' ? (
              <ProseParagraphDiff approvedText={currentNovelBody?.text_content || ''} candidateText={candidateContent.text_content || ''} />
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 360px), 1fr))', gap: 12 }}>
                <div style={writerRoomComparePaneStyle}>
                  <Text type="secondary">当前正文</Text>
                  <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 16, expandable: true }}>
                    {currentNovelBody?.text_content || '当前章节还没有正式正文'}
                  </Paragraph>
                </div>
                <div style={writerRoomComparePaneStyle}>
                  <Text type="secondary">写作室候选</Text>
                  <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 16, expandable: true }}>
                    {candidateContent.text_content}
                  </Paragraph>
                </div>
              </div>
            )
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有正文初稿、润色或重写结果" />
        )}
        </Space>
      </section>

      <Modal
        title="人工确认后提升为正文"
        open={Boolean(promoteTarget)}
        onCancel={() => {
          setPromoteTarget(null)
          setPromoteChecked(false)
        }}
        onOk={confirmPromote}
        okText="确认提升为正文"
        cancelText="再看看"
        okButtonProps={{ disabled: !promoteChecked, loading }}
        width={860}
      >
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
          <Text type="secondary">
            提升会创建新的正式正文版本，旧正文会保留为历史版本。建议先确认候选正文已经通过审稿或人工阅读。
          </Text>
          <div style={writerRoomPromoteSummaryStyle}>
            <div style={writerRoomMetricStyle}>
              <Text type="secondary">当前正文</Text>
              <Text strong>{writerRoomContentWordCount(currentNovelBody) || '-'} 字</Text>
              <Text type="secondary">v{currentNovelBody?.version || '-'}</Text>
            </div>
            <div style={writerRoomMetricStyle}>
              <Text type="secondary">候选来源</Text>
              <Text strong>{promoteTarget ? writerRoomStepLabelMap[promoteTarget.content_type] || promoteTarget.content_type : '-'}</Text>
              <Text type="secondary">v{promoteTarget?.version || '-'}</Text>
            </div>
            <div style={writerRoomMetricStyle}>
              <Text type="secondary">候选正文</Text>
              <Text strong>{writerRoomContentWordCount(promoteTarget || undefined) || '-'} 字</Text>
              <Text type="secondary">{promoteTarget?.created_at || '-'}</Text>
            </div>
          </div>
          <div style={writerRoomComparePaneStyle}>
            <Text type="secondary">候选预览</Text>
            <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 14, expandable: true }}>
              {promoteTarget?.text_content || '无正文内容'}
            </Paragraph>
          </div>
          <Checkbox checked={promoteChecked} onChange={(event) => setPromoteChecked(event.target.checked)}>
            我已确认候选正文质量、剧情连续性和角色声音，可以作为本章新的正式正文版本。
          </Checkbox>
        </Space>
      </Modal>

      <section style={panelStyle}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space direction="vertical" size={2}>
            <Text strong>段落锚点重写</Text>
            <Text type="secondary">从当前候选正文里选择一个段落，只生成新的候选版本，不覆盖正式正文。</Text>
          </Space>
          <Select
            value={selectedParagraphIndex}
            onChange={(value) => setSelectedParagraphIndex(Number(value))}
            options={rewriteParagraphs.map((paragraph, index) => ({
              value: index,
              label: `段落 ${index + 1} · ${paragraph.slice(0, 40) || '空段落'}`,
            }))}
            placeholder="选择要重写的段落"
            disabled={!rewriteParagraphs.length}
          />
          <div style={writerRoomParagraphListStyle}>
            {rewriteParagraphs.length ? rewriteParagraphs.map((paragraph, index) => {
              const isActive = index === selectedParagraphIndex
              return (
                <button
                  key={`${index}-${paragraph.slice(0, 12)}`}
                  type="button"
                  onClick={() => setSelectedParagraphIndex(index)}
                  style={{
                    ...writerRoomParagraphButtonStyle,
                    ...(isActive ? writerRoomParagraphButtonActiveStyle : {}),
                  }}
                >
                  <Text strong>段落 {index + 1}</Text>
                  <Text type="secondary" style={{ display: 'block', marginTop: 4, whiteSpace: 'pre-wrap' }}>
                    {paragraph}
                  </Text>
                </button>
              )
            }) : <Empty description="当前候选没有可重写的段落" />}
          </div>
          <TextArea
            value={partialRewriteInstruction}
            onChange={(event) => setPartialRewriteInstruction(event.target.value)}
            placeholder="局部重写要求，例如：压低解释，增加动作和潜台词"
            autoSize={{ minRows: 2, maxRows: 5 }}
          />
          <Space wrap>
            <Button type="primary" loading={loading} onClick={runParagraphRewrite}>
              生成新的候选版本
            </Button>
            <Button onClick={() => setSelectedParagraphIndex(0)}>
              回到首段
            </Button>
            <Button onClick={() => setSelectedParagraphIndex(Math.max(0, rewriteParagraphs.length - 1))}>跳到末段</Button>
          </Space>
        </Space>
      </section>
    </Space>
  )
}

