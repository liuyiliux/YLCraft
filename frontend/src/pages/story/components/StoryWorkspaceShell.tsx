/**
 * 创作项目工作台的渲染主体。
 *
 * 从 story/index.tsx 抽出的展示组件（拆分计划 creative-project-ui-redesign #9）：
 * 顶部身份与模式切换、项目库、各工作区视图与弹窗的 JSX 整体搬迁，
 * 结构与文案逐字未改。数据与回调经 ctx 传入，类型取自 useStoryPageContext。
 */
import FanqiePublishPanel from '../FanqiePublishPanel'
import BaselinePickerModal from '../../../components/world/BaselinePickerModal'
import GeneratedMediaThumb from '../../../components/content-package/GeneratedMediaThumb'
import PackageOutputList from '../../../components/content-package/PackageOutputList'
import { useVisualBaseline } from '../hooks/useVisualBaseline'
import ProjectStatePanel from '../ProjectStatePanel'
import StoryWorkspaceOverview from '../StoryWorkspaceOverview'
import { ProjectBibleTab } from './bible'
import { ChapterRail, ChapterTab, EpisodeWorkbenchTab } from './chapter-studio'
import { ResizeHandle } from './common'
import { NarrativeGraphTab, NarrativeInspector, ProjectGraphTab } from './graph'
import { OutlineTab, PipelinePanel } from './outline'
import { ScriptTab } from './storyboard'
import { AssetsTab, JsonTab, LogsTab } from './tabs'
import { WriterRoomTab } from './writer-room'
import { getNovelDisplayTitle, imageContextKey, productionProfileOptions, projectTypeLabel, projectTypeOptions, stageLabels, statusLabels } from '../utils'
import { ArrowDownOutlined, ArrowUpOutlined, BranchesOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, FileTextOutlined, FolderOpenOutlined, HistoryOutlined, MenuFoldOutlined, MenuUnfoldOutlined, PictureOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Checkbox, Collapse, Divider, Empty, Form, Input, InputNumber, List, Modal, Popconfirm, Segmented, Select, Skeleton, Space, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import type { StoryPageContext } from '../hooks/useStoryPageContext'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function StoryWorkspaceShell({ ctx }: { ctx: StoryPageContext }) {
  const {
    activeChapter,
    activeChapterNumber,
    activeWorkspaceTab,
    allForeshadowingLedger,
    assetDetails,
    batchStoryboardImageChapter,
    chapterColumns,
    chapterCount,
    chapterPlan,
    chapters,
    characterColumns,
    characterDetails,
    characterExtractionLoading,
    characterExtractionOpen,
    characterExtractionResult,
    cockpitCompact,
    comicPageCount,
    comicPages,
    comicStyle,
    contentForChapter,
    contentPackageBatchRunning,
    contentPackageContent,
    contentPackageData,
    contentPackageForm,
    contentPackageOpen,
    contents,
    continuityCandidates,
    continuitySummary,
    createIsContentPackage,
    createOpen,
    createSourceType,
    defaultImageModel,
    defaultImageSupportsReferenceImages,
    fanqieOpen,
    foreshadowingLedger,
    form,
    generationLogs,
    handleActiveChapterChange,
    handleAgentAdvanceProject,
    handleBatchGenerateContentPackageImages,
    handleBuildContentPackageOutputs,
    handleRetryContentPackageItem,
    handleBatchGenerateStoryboardImages,
    handleCreate,
    handleCreativeSkillIdsChange,
    handleDefaultImageModelChange,
    handleDeleteProject,
    handleExtractCharacters,
    handleExtractContinuity,
    handleExtractWorld,
    handleForeshadowingDecision,
    handleGenerateChapterOutline,
    handleGenerateChapterPlan,
    handleGenerateContentPackageImage,
    handleGenerateNovelBody,
    handleGenerateOutline,
    handleGenerateScript,
    handleGenerateStoryboardForChapter,
    handleInlineGenerateImage,
    handleLinkAsset,
    handleMatchReferenceAssets,
    handleNarrativeAutopilot,
    handleNarrativeRunControl,
    handleOpenGraphNode,
    handleOpenPrevis,
    handleOpenVideoGeneration,
    handlePlanContentPackage,
    handlePromoteWriterRoomContent,
    handleRefineNovelBody,
    handleRegenerateChapterOutlineScenes,
    handleRegenerateGraphNode,
    handleRename,
    handleResolveContinuityCandidate,
    handleRewriteParagraph,
    handleRunPipeline,
    handleRunWriterRoomBatch,
    handleRunWriterRoomStep,
    handleSaveChapterPlan,
    handleSaveContent,
    handleSaveContentAsAsset,
    handleSaveContentPackage,
    handleSaveOutline,
    handleSaveProjectGraph,
    handleSendGraphNodeToCanvas,
    handleSplitComicPages,
    handleSyncCharacters,
    handleSyncProjectBible,
    handleToggleGraphNodeLock,
    handleUpdateStoryboardPanelReferences,
    hasChapterPlan,
    hasOutline,
    idea,
    imageModelOptions,
    inlineImageLoadingKey,
    inlineImages,
    inspectorOpen,
    isChapterActionLoading,
    isContentPackageProject,
    llmAvailable,
    llmConnectors,
    loadGenerationLogs,
    loadNarrativeRuntime,
    loadNovelAssets,
    loadProjects,
    loadWriterRoomContents,
    loadingAction,
    loadingChapterAction,
    loadingNovelAssets,
    modelOptions,
    narrativeContext,
    narrativeGraphData,
    narrativeHealth,
    narrativeInspectorLogs,
    narrativeLoading,
    narrativeRuns,
    navigate,
    novelAssets,
    novelBodies,
    openChapterStudio,
    openContentPackageEditor,
    openRenameModal,
    openWorkspaceTab,
    outline,
    overviewDetailLabel,
    overviewDetailOpen,
    pendingInlineImageTask,
    persistChatModel,
    pipelineChapters,
    pipelineContinueOnError,
    pipelineOpen,
    pipelineResult,
    pipelineRunStatus,
    pipelineSkipExisting,
    pipelineStages,
    productionStages,
    projectAssets,
    projectBibleContents,
    projectGraphView,
    projectLibraryCollapsed,
    projectLibraryWidth,
    projectListError,
    projects,
    rehearsalMode,
    renameForm,
    renameOpen,
    retryWorkspaceLoads,
    runtimeSettingsOpen,
    savingContentId,
    savingImageModel,
    selectedCreativeSkillIds,
    selectedId,
    selectedLlm,
    selectedModel,
    selectedNovelAsset,
    selectedNovelChapterOptions,
    selectedProject,
    selectedProjectIndex,
    selectedPromptTemplates,
    setActiveWorkspaceTab,
    setChapterCount,
    setCharacterExtractionOpen,
    setComicPageCount,
    setComicStyle,
    setContentPackageOpen,
    setCreateOpen,
    setFanqieOpen,
    setInspectorOpen,
    setOverviewDetailOpen,
    setPipelineChapters,
    setPipelineContinueOnError,
    setPipelineOpen,
    setPipelineSkipExisting,
    setPipelineStages,
    setProjectLibraryCollapsed,
    setProjectLibraryWidth,
    setRehearsalMode,
    setRenameOpen,
    setRuntimeSettingsOpen,
    setSelectedId,
    setSelectedLlm,
    setSelectedModel,
    setSelectedPromptTemplates,
    setWorkbenchWidths,
    setWorkspaceMode,
    startHorizontalResize,
    storyPageRef,
    templateOptionsByStage,
    theme,
    unavailableAssetIds,
    workbenchWidths,
    workspaceErrorEntries,
    workspaceErrors,
    workspaceLoading,
    workspaceMode,
    workspaceNarrow,
    worldAssetContents,
    writerRoomContents,
    writerRoomSummary,
  } = ctx

  // 项目视觉基准：一张项目级基准图，生图时由服务端自动注入为参考图。
  // 这是画风/人物一致性的载体——没有它，每页提示词各写各的风格，人物也会一页一个样。
  const visualBaseline = useVisualBaseline(selectedProject?.id)

  // 已产出的平台输出（公众号/小红书/短视频/PDF/素材包）。由后端适配器写入包版本，
  // 界面「输出适配」检查项与这里的列表都读它。
  const packageOutputs: any[] = Array.isArray((contentPackageData as any)?.outputs)
    ? ((contentPackageData as any).outputs as any[])
    : []

  // "最近活动"：取项目生成日志里最近的几条（时间倒序），阶段与状态转成中文展示。
  // 数据来自已在 ctx 里的 generationLogs，无新增请求。
  const recentActivities = [...(generationLogs || [])]
    .sort((a: any, b: any) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    .slice(0, 6)
    .map((log: any) => ({
      id: log.id,
      stageLabel: stageLabels[log.stage] || log.stage || '生成',
      statusLabel: log.status === 'success' ? '成功' : log.status === 'failed' ? '失败' : (log.status || '未知'),
      statusColor: log.status === 'success' ? 'success' : log.status === 'failed' ? 'error' : 'default',
      model: log.model || log.provider,
      timeLabel: String(log.created_at || '').replace('T', ' ').slice(5, 16),
    }))

  return (
    <div ref={storyPageRef} className="story-theme-page story-production-desk" style={{ padding: '18px 24px 24px', maxWidth: 2400, width: '100%', margin: '0 auto', color: theme.textPrimary }}>
      <header
        style={{
          display: 'grid',
          gridTemplateColumns: cockpitCompact ? 'minmax(0, 1fr)' : 'minmax(220px, 1fr) minmax(0, auto)',
          alignItems: 'center',
          gap: '10px 20px',
          marginBottom: 14,
          paddingBottom: 14,
          borderBottom: `1px solid ${theme.borderLight}`,
        }}
      >
        <div style={{ minWidth: 220 }}>
          <Text strong style={{ fontSize: 16 }}>项目制作台</Text>
          <Text type="secondary" style={{ display: 'block', marginTop: 2 }}>从故事设定到可追溯的内容与素材产出</Text>
          {selectedProject ? (
            <Segmented
              size="small"
              value={workspaceMode}
              style={{ marginTop: 10 }}
              options={[
                { label: '项目总览', value: 'overview' },
                { label: '单章工作室', value: 'chapter' },
              ]}
              onChange={(value) => {
                const nextMode = value as 'overview' | 'chapter'
                setWorkspaceMode(nextMode)
                if (nextMode === 'overview') setOverviewDetailOpen(false)
                if (nextMode === 'chapter' && !['episode-workbench', 'writer-room', 'script'].includes(activeWorkspaceTab)) {
                  setActiveWorkspaceTab('episode-workbench')
                }
                if (nextMode === 'overview' && ['episode-workbench', 'writer-room', 'script'].includes(activeWorkspaceTab)) {
                  setActiveWorkspaceTab('outline')
                }
              }}
            />
          ) : null}
        </div>
        <Space wrap size={[8, 8]} style={{ justifyContent: cockpitCompact ? 'flex-start' : 'flex-end', minWidth: 0 }}>
          {selectedProject ? (
            <Space size={6} wrap>
              {productionStages.map(stage => (
                <Tooltip key={stage.key} title={`${stage.label} · ${stage.complete}/${stage.total}`}>
                  <Tag
                    style={{ margin: 0, borderRadius: 999, lineHeight: '20px', padding: '0 8px', fontSize: 12, cursor: 'pointer' }}
                    color={stage.complete >= stage.total ? 'success' : 'processing'}
                    onClick={() => openWorkspaceTab(stage.tab)}
                  >
                    {stage.label}
                  </Tag>
                </Tooltip>
              ))}
            </Space>
          ) : null}
          {runtimeSettingsOpen ? <>
            <Select
            placeholder="文本模型"
            value={selectedLlm || undefined}
            style={{ width: 190 }}
            options={llmConnectors.map((item) => ({
              label: `${item.name}${item.is_default ? '（默认）' : ''}`,
              value: item.name,
            }))}
            onChange={(value) => {
              const connector = llmConnectors.find((item) => item.name === value)
              const nextModel = connector?.default_model || ''
              setSelectedLlm(value)
              setSelectedModel(nextModel)
              // 写入项目 metadata，刷新后能恢复
              persistChatModel(value, nextModel)
            }}
          />
            <Select
            placeholder="模型"
            value={selectedModel || undefined}
            style={{ width: 210 }}
            options={modelOptions}
            onChange={(value) => {
              setSelectedModel(value)
              if (selectedLlm) {
                persistChatModel(selectedLlm, value)
              }
            }}
            disabled={!selectedLlm}
          />
            <Select
            allowClear
            showSearch
            placeholder="默认生图模型"
            value={defaultImageModel.name || undefined}
            style={{ width: 230 }}
            options={imageModelOptions}
            loading={savingImageModel}
            onChange={handleDefaultImageModelChange}
            optionFilterProp="label"
              disabled={!selectedProject}
            />
            <Tooltip
              title={
                visualBaseline.hasBaseline
                  ? '已设置项目视觉基准：生图时自动作为参考图注入（点击可更换）'
                  : '可设一张项目级基准图。生图时自动作为参考图注入，是画风与人物一致性的载体——没有它，每页各画各的'
              }
            >
              <Button
                size="small"
                icon={<PictureOutlined />}
                disabled={!selectedProject}
                onClick={visualBaseline.openPicker}
              >
                {visualBaseline.hasBaseline ? '视觉基准（已设）' : '设视觉基准'}
              </Button>
            </Tooltip>
            {visualBaseline.hasBaseline ? (
              <Button type="text" size="small" danger onClick={visualBaseline.clear}>清除基准</Button>
            ) : null}
            <Button type="text" size="small" onClick={() => setRuntimeSettingsOpen(false)}>收起设置</Button>
          </> : (
            <Button icon={<EditOutlined />} onClick={() => setRuntimeSettingsOpen(true)}>
              运行设置
            </Button>
          )}
          <Tooltip title="提示词与平台模板">
            <Button icon={<FileTextOutlined />} onClick={() => navigate('/platform-templates?scope=creative_project')}>
              模板
            </Button>
          </Tooltip>
          <Tooltip title="刷新项目数据">
            <Button aria-label="刷新项目数据" icon={<ReloadOutlined />} onClick={() => loadProjects(selectedId)} />
          </Tooltip>
          {selectedProject ? (
            <Tooltip title={inspectorOpen ? '关闭上下文检查器' : '打开上下文检查器'}>
              <Button
                type={inspectorOpen ? 'default' : 'text'}
                aria-label={inspectorOpen ? '关闭上下文检查器' : '打开上下文检查器'}
                icon={<EyeOutlined />}
                onClick={() => setInspectorOpen((open) => !open)}
              />
            </Tooltip>
          ) : null}
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建项目</Button>
        </Space>
      </header>

      <BaselinePickerModal
        open={visualBaseline.pickerOpen}
        onClose={() => visualBaseline.setPickerOpen(false)}
        candidates={visualBaseline.candidates}
        loading={visualBaseline.loading}
        search={visualBaseline.search}
        onSearchChange={visualBaseline.setSearch}
        onSearch={() => visualBaseline.loadCandidates(visualBaseline.search)}
        onPick={visualBaseline.pick}
        currentAssetId={visualBaseline.assetId}
      />

      {workspaceErrorEntries.length > 0 ? (
        <Alert
          type="error"
          showIcon
          message="项目工作台有数据加载失败"
          description={workspaceErrorEntries.map(([key, value]) => `${key}: ${value}`).join('；')}
          action={<Button size="small" onClick={retryWorkspaceLoads}>重试</Button>}
          style={{ marginBottom: 16 }}
        />
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: workspaceNarrow
            ? 'minmax(0, 1fr)'
            : projectLibraryCollapsed
            ? cockpitCompact ? '48px 0 minmax(0, 1fr)' : '48px 0 minmax(0, 1fr)' + (inspectorOpen ? ' minmax(246px, 300px)' : '')
            : cockpitCompact
              ? `${projectLibraryWidth}px 10px minmax(0, 1fr)`
              : `${projectLibraryWidth}px 10px minmax(0, 1fr)` + (inspectorOpen ? ' minmax(246px, 300px)' : ''),
          gap: workspaceNarrow ? 12 : projectLibraryCollapsed ? 6 : 8,
          alignItems: 'start',
        }}
      >
        <section
          style={{
            border: `1px solid ${theme.borderLight}`,
            borderRadius: 8,
            background: theme.bgCard,
            overflow: 'hidden',
            minHeight: projectLibraryCollapsed ? 620 : undefined,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              padding: projectLibraryCollapsed ? '12px 8px' : '14px 16px',
              borderBottom: projectLibraryCollapsed ? 'none' : `1px solid ${theme.border}`,
            }}
          >
            {projectLibraryCollapsed ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                <Tooltip title="展开项目库">
                  <Button
                    type="text"
                    aria-label="展开项目库"
                    icon={<MenuUnfoldOutlined />}
                    onClick={() => setProjectLibraryCollapsed(false)}
                    style={{ color: theme.textPrimary }}
                  />
                </Tooltip>
                <Badge count={projects.length} showZero color="#1677ff">
                  <FolderOpenOutlined style={{ color: theme.textSecondary }} />
                </Badge>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%' }}>
                <Space size={8} style={{ minWidth: 0 }}>
                  <FolderOpenOutlined />
                  <Text strong>项目库</Text>
                  <Badge count={projects.length} showZero color="#1677ff" />
                </Space>
                <Tooltip title="折叠项目库">
                  <Button
                    type="text"
                    size="small"
                    aria-label="折叠项目库"
                    icon={<MenuFoldOutlined />}
                    onClick={() => setProjectLibraryCollapsed(true)}
                    style={{ color: theme.textSecondary, flex: '0 0 auto' }}
                  />
                </Tooltip>
              </div>
            )}
          </div>
          {!projectLibraryCollapsed && loadingAction === 'projects' && !projects.length ? (
            <div style={{ padding: 16 }}>
              <Skeleton active paragraph={{ rows: 8 }} />
            </div>
          ) : !projectLibraryCollapsed && projects.length ? (
            <List
              style={{ flex: '0 1 320px', minHeight: 0, overflowY: 'auto' }}
              dataSource={projects}
              rowKey="id"
              renderItem={(item, index) => (
                <List.Item
                  onClick={() => setSelectedId(item.id)}
                  style={{
                    cursor: 'pointer',
                    padding: '12px 16px',
                    background: item.id === selectedId ? theme.primaryAlpha(0.12) : theme.bgCard,
                    borderLeft: item.id === selectedId ? `3px solid ${theme.primary}` : '3px solid transparent',
                  }}
                >
                  <List.Item.Meta
                    title={
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong ellipsis style={{ maxWidth: Math.max(96, projectLibraryWidth - 110) }}>
                          {item.title || `项目 ${index + 1}`}
                        </Text>
                        <Tag color={item.status === 'ready' ? 'green' : 'blue'}>
                          {statusLabels[item.status] || item.status}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space size={6} wrap>
                        <Text type="secondary">{stageLabels[item.current_stage] || item.current_stage}</Text>
                        <Text type="secondary">#{projects.length - index}</Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          ) : !projectLibraryCollapsed && projectListError ? (
            <div style={{ padding: 16 }}>
              <Alert
                type="error"
                showIcon
                message="项目列表加载失败"
                description={projectListError}
                action={<Button size="small" onClick={() => loadProjects(selectedId)}>重试</Button>}
              />
            </div>
          ) : !projectLibraryCollapsed ? (
            <div style={{ padding: 24 }}>
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无项目" />
            </div>
          ) : null}
          {!projectLibraryCollapsed && selectedProject && workspaceMode === 'chapter' ? (
            <ChapterRail
              theme={theme}
              chapters={chapters}
              activeChapterNumber={activeChapterNumber}
              contents={contents}
              writerRoomSummary={writerRoomSummary}
              ledger={allForeshadowingLedger}
              health={narrativeHealth}
              onChapterChange={handleActiveChapterChange}
            />
          ) : null}
        </section>

        {workspaceNarrow ? null : projectLibraryCollapsed ? (
          <div />
        ) : (
          <ResizeHandle
            onMouseDown={(event) =>
              startHorizontalResize(event, {
                initial: projectLibraryWidth,
                min: 190,
                max: 360,
                onChange: setProjectLibraryWidth,
              })
            }
          />
        )}

        <main
          style={{
            minHeight: 620,
            border: `1px solid ${theme.borderLight}`,
            borderRadius: 8,
            background: theme.bgCard,
          }}
        >
          {!selectedProject ? (
            <div style={{ padding: 64 }}>
              <Empty description="选择或新建项目" />
            </div>
          ) : (
            <>
              <div className={`story-project-toolbar story-project-toolbar--${workspaceMode}`} style={{ padding: '20px 20px 16px', borderBottom: `1px solid ${theme.border}` }}>
                <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <div>
                      <Space size={10} wrap>
                        <Title level={3} style={{ margin: 0 }}>
                          {selectedProject.title}
                        </Title>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={openRenameModal}
                          loading={loadingAction === 'rename'}
                        >
                          重命名
                        </Button>
                        <Tag color="processing">{projectTypeLabel(selectedProject.project_type)}</Tag>
                        {selectedProject.production_profile?.label ? (
                          <Tooltip title={selectedProject.production_profile.description}>
                            <Tag color="cyan">方案：{selectedProject.production_profile.label}</Tag>
                          </Tooltip>
                        ) : null}
                        <Tag>{stageLabels[selectedProject.current_stage] || selectedProject.current_stage}</Tag>
                        <Tooltip
                          title={
                            llmAvailable
                              ? '由创作导演自动推进后续步骤'
                              : '请先在设置中配置文本模型'
                          }
                        >
                          <Button
                            type="primary"
                            icon={<RobotOutlined />}
                            onClick={handleAgentAdvanceProject}
                            loading={loadingAction === 'agent_advance'}
                            disabled={!llmAvailable}
                          >
                            智能体推进
                          </Button>
                        </Tooltip>
                        <Button
                          icon={<DownloadOutlined />}
                          href={`/api/v1/creative-projects/${selectedProject.id}/export`}
                        >
                          导出项目
                        </Button>
                      </Space>
                      {idea && (
                        <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: '8px 0 0' }}>
                          {idea}
                        </Paragraph>
                      )}
                    </div>
                    <Space direction="vertical" size={2} align="end">
                      <Text type="secondary">{selectedProjectIndex >= 0 ? `项目 ${projects.length - selectedProjectIndex}` : ''}</Text>
                      <Popconfirm
                        title="删除当前创作项目？"
                        description="只删除项目、内容版本、日志和项目关联，不删除角色库角色或素材库资产。"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true, loading: loadingAction === 'delete_project' }}
                        onConfirm={handleDeleteProject}
                      >
                        <Button type="text" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                      </Popconfirm>
                    </Space>
                  </Space>
                </Space>
              </div>

              {workspaceMode === 'overview' ? (
                <StoryWorkspaceOverview
                  theme={theme}
                  projectTitle={selectedProject.title}
                  projectType={projectTypeLabel(selectedProject.project_type)}
                  currentStage={stageLabels[selectedProject.current_stage] || selectedProject.current_stage}
                  idea={idea}
                  chapters={chapters}
                  stages={productionStages}
                  activeChapterNumber={activeChapterNumber}
                  hasOutline={hasOutline}
                  hasBible={Boolean(projectBibleContents.length || worldAssetContents.length)}
                  hasChapterPlan={hasChapterPlan}
                  assetCount={projectAssets.length}
                  unresolvedContinuityCount={continuityCandidates.filter((item) => item.status === 'pending').length}
                  onOpenSection={(tab) => {
                    const chapterTab = ['episode-workbench', 'writer-room', 'script'].includes(tab)
                    openWorkspaceTab(tab, chapterTab ? 'chapter' : 'overview')
                    setOverviewDetailOpen(!chapterTab)
                  }}
                  onOpenChapter={openChapterStudio}
                  productionFamily={selectedProject.production_profile?.production_family || 'narrative'}
                  packageType={selectedProject.production_profile?.package_type}
                  packageData={contentPackageData}
                  recentActivities={recentActivities}
                  onContinue={() => {
                    if (isContentPackageProject) {
                      openContentPackageEditor()
                    } else if (chapters.length) openChapterStudio(activeChapterNumber)
                    else {
                      openWorkspaceTab(hasOutline ? 'chapters' : 'outline', 'overview')
                      // 展开详情区，让大纲/章节规划编辑器可见（否则无章节时点击无视觉变化）
                      setOverviewDetailOpen(true)
                      if (!hasOutline) {
                        // 有创意则自动生成故事大纲，无创意则引导先填写
                        if (idea) void handleGenerateOutline()
                        else message.info('已打开大纲编辑器，请先填写创意（idea）后再点击「生成故事大纲」')
                      }
                    }
                  }}
                />
              ) : null}

              {workspaceMode === 'overview' && !isContentPackageProject ? <Collapse
                ghost
                size="small"
                activeKey={pipelineOpen ? ['production'] : []}
                onChange={(keys) => setPipelineOpen(keys.includes('production'))}
                style={{ margin: '0 20px' }}
                items={[
                  {
                    key: 'production',
                    label: <Text strong>批量生产设置</Text>,
                    extra: pipelineRunStatus !== 'idle' ? <Tag color={pipelineRunStatus === 'failed' ? 'red' : pipelineRunStatus === 'partial' ? 'orange' : 'blue'}>{pipelineRunStatus === 'running' ? '运行中' : pipelineRunStatus === 'partial' ? '部分完成' : pipelineRunStatus === 'failed' ? '失败' : '已完成'}</Tag> : <Text type="secondary">按依赖顺序补齐章节</Text>,
                    children: (
                      <PipelinePanel
                        theme={theme}
                        stages={pipelineStages}
                        onStagesChange={setPipelineStages}
                        chapterRange={pipelineChapters}
                        onChapterRangeChange={setPipelineChapters}
                        skipExisting={pipelineSkipExisting}
                        onSkipExistingChange={setPipelineSkipExisting}
                        continueOnError={pipelineContinueOnError}
                        onContinueOnErrorChange={setPipelineContinueOnError}
                        loading={loadingAction === 'pipeline'}
                        result={pipelineResult}
                        runStatus={pipelineRunStatus}
                        onRun={handleRunPipeline}
                        onRetryFailed={() => handleRunPipeline({ retryFailed: true })}
                      />
                    ),
                  },
                ]}
              /> : null}

              {Object.values(workspaceLoading).some(Boolean) ? (
                <Alert
                  type="info"
                  showIcon
                  message="正在加载项目工作台"
                  description="内容、素材、生成日志和关系图谱正在分别同步；已有数据仍可继续查看。"
                  style={{ margin: '16px 20px 0' }}
                />
              ) : null}

              {!isContentPackageProject ? <div className={`story-workspace-detail story-workspace-detail--${workspaceMode}`}>
                {workspaceMode === 'overview' ? (
                  <button
                    type="button"
                    className="story-workspace-detail__toggle"
                    onClick={() => setOverviewDetailOpen((open) => !open)}
                    aria-expanded={overviewDetailOpen}
                  >
                    <span>
                      <Text strong>{overviewDetailLabel}</Text>
                      <Text type="secondary">仅在需要编辑或查看完整资料时展开</Text>
                    </span>
                    <span>{overviewDetailOpen ? '收起' : '展开'}</span>
                  </button>
                ) : null}
                <div hidden={workspaceMode === 'overview' && !overviewDetailOpen}>
              <Tabs
                className={`story-workspace-tabs story-workspace-tabs--${workspaceMode}`}
                style={{ padding: workspaceMode === 'overview' ? '0 22px 22px' : '0 20px 20px' }}
                activeKey={workspaceMode === 'chapter' && !['episode-workbench', 'writer-room', 'script'].includes(activeWorkspaceTab) ? 'episode-workbench' : activeWorkspaceTab}
                onChange={openWorkspaceTab}
                items={[
                  {
                    key: 'outline',
                    label: (
                      <Space>
                        <ThunderboltOutlined />
                        大纲
                      </Space>
                    ),
                    children: (
                      <OutlineTab
                        outline={outline}
                        hasOutline={hasOutline}
                        productionProfileId={selectedProject?.production_profile?.id}
                        loading={loadingAction === 'outline'}
                        saving={loadingAction === 'outline_save'}
                        syncLoading={loadingAction === 'sync_characters'}
                        extractLoading={characterExtractionLoading}
                        llmAvailable={llmAvailable}
                        templateOptions={templateOptionsByStage.outline || []}
                        selectedTemplateId={selectedPromptTemplates.outline}
                        onTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, outline: value }))
                        }
                        onGenerate={handleGenerateOutline}
                        onSave={handleSaveOutline}
                        onSyncCharacters={handleSyncCharacters}
                        onExtractCharacters={() => void handleExtractCharacters(false)}
                        characterColumns={characterColumns}
                      />
                    ),
                  },
                  {
                    key: 'project-bible',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        圣经/世界
                      </Space>
                    ),
                    children: (
                      <ProjectBibleTab
                        projectId={selectedProject?.id || ''}
                        hasOutline={hasOutline}
                        bibleContents={projectBibleContents}
                        worldAssets={worldAssetContents}
                        loading={loadingAction === 'project_bible' || loadingAction === 'world_extract'}
                        savingContentId={savingContentId}
                        onSync={handleSyncProjectBible}
                        onExtractWorld={handleExtractWorld}
                        onSaveContent={handleSaveContent}
                        onSaveAsAsset={handleSaveContentAsAsset}
                      />
                    ),
                  },
                  {
                    key: 'dynamic-state',
                    label: (
                      <Space>
                        <HistoryOutlined />
                        动态状态
                      </Space>
                    ),
                    children: <ProjectStatePanel projectId={selectedProject?.id || ''} />,
                  },
                  {
                    key: 'chapters',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        章节
                      </Space>
                    ),
                    children: (
                      <ChapterTab
                        chapterPlan={chapterPlan}
                        chapters={chapters}
                        hasOutline={hasOutline}
                        hasChapterPlan={hasChapterPlan}
                        chapterColumns={chapterColumns}
                        chapterCount={chapterCount}
                        setChapterCount={setChapterCount}
                        comicPageCount={comicPageCount}
                        setComicPageCount={setComicPageCount}
                        chapterTemplateOptions={templateOptionsByStage.chapter_plan || []}
                        selectedChapterTemplateId={selectedPromptTemplates.chapter_plan}
                        onChapterTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, chapter_plan: value }))
                        }
                        scriptTemplateOptions={templateOptionsByStage.script || []}
                        selectedScriptTemplateId={selectedPromptTemplates.script}
                        onScriptTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, script: value }))
                        }
                        chapterOutlineTemplateOptions={templateOptionsByStage.chapter_outline || []}
                        selectedChapterOutlineTemplateId={selectedPromptTemplates.chapter_outline}
                        onChapterOutlineTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, chapter_outline: value }))
                        }
                        novelBodyTemplateOptions={templateOptionsByStage.novel_body || []}
                        selectedNovelBodyTemplateId={selectedPromptTemplates.novel_body}
                        onNovelBodyTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, novel_body: value }))
                        }
                        comicPagesTemplateOptions={templateOptionsByStage.comic_pages || []}
                        selectedComicPagesTemplateId={selectedPromptTemplates.comic_pages}
                        onComicPagesTemplateChange={(value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, comic_pages: value }))
                        }
                        loading={loadingAction === 'chapter_plan'}
                        saving={loadingAction === 'chapter_plan_save'}
                        onGenerate={handleGenerateChapterPlan}
                        onSave={handleSaveChapterPlan}
                      />
                    ),
                  },
                  {
                    key: 'episode-workbench',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        单话工作台
                      </Space>
                    ),
                    children: (
                      <EpisodeWorkbenchTab
                        projectId={selectedProject?.id || ''}
                        chapters={chapters}
                        activeChapterNumber={activeChapterNumber}
                        onActiveChapterChange={handleActiveChapterChange}
                        activeChapter={activeChapter}
                        contentForChapter={contentForChapter}
                        isChapterActionLoading={isChapterActionLoading}
                        comicPageCount={comicPageCount}
                        setComicPageCount={setComicPageCount}
                        comicStyle={comicStyle}
                        setComicStyle={setComicStyle}
                        columnWidths={workbenchWidths}
                        setColumnWidths={setWorkbenchWidths}
                        startHorizontalResize={startHorizontalResize}
                        projectAssets={projectAssets}
                        assetDetails={assetDetails}
                        characterDetails={characterDetails}
                        savingContentId={savingContentId}
                        linkingAsset={loadingAction === 'asset'}
                        onGenerateChapterOutline={handleGenerateChapterOutline}
                        onRegenerateChapterOutlineScenes={handleRegenerateChapterOutlineScenes}
                        onGenerateNovelBody={handleGenerateNovelBody}
                        onRefineNovelBody={handleRefineNovelBody}
                        onSaveContentAsAsset={handleSaveContentAsAsset}
                        onExtractContinuity={handleExtractContinuity}
                        continuityExtracting={loadingAction === 'project_bible'}
                        onOpenFanqiePublish={() => setFanqieOpen(true)}
                        onGenerateScript={handleGenerateScript}
                        onGenerateStoryboard={handleGenerateStoryboardForChapter}
                        onMatchReferenceAssets={handleMatchReferenceAssets}
                        referenceMatching={loadingAction === 'reference_match'}
                        onBatchGenerateStoryboardImages={handleBatchGenerateStoryboardImages}
                        onSplitComicPages={handleSplitComicPages}
                        onSaveContent={handleSaveContent}
                        onUpdateStoryboardPanelReferences={handleUpdateStoryboardPanelReferences}
                        onLinkReferenceAsset={handleLinkAsset}
                        onSendImagePrompt={handleInlineGenerateImage}
                        onOpenVideoGeneration={handleOpenVideoGeneration}
                         onOpenPrevis={handleOpenPrevis}
                        inlineImages={inlineImages}
                        inlineImageLoadingKey={inlineImageLoadingKey}
                        pendingImageTaskKey={pendingInlineImageTask?.key}
                        pendingImageTaskId={pendingInlineImageTask?.taskId}
                        batchStoryboardImageChapter={batchStoryboardImageChapter}
                        defaultImageModelName={defaultImageModel.name || ''}
                        defaultImageSupportsReferenceImages={defaultImageSupportsReferenceImages}
                        selectedCreativeSkillIds={selectedCreativeSkillIds}
                        onCreativeSkillIdsChange={handleCreativeSkillIdsChange}
                        compact={workspaceNarrow}
                      />
                    ),
                  },
                  {
                    key: 'writer-room',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        写作室
                      </Space>
                    ),
                    children: (
                      <WriterRoomTab
                        chapters={chapters}
                        activeChapterNumber={activeChapterNumber}
                        onActiveChapterChange={handleActiveChapterChange}
                        contents={writerRoomContents}
                        loadError={workspaceErrors.writerRoom}
                        loadingContents={workspaceLoading.writerRoom}
                        onRetryContents={() => selectedProject && loadWriterRoomContents(selectedProject.id, activeChapterNumber)}
                        contentForChapter={contentForChapter}
                        logs={generationLogs}
                        templateOptionsByStage={templateOptionsByStage}
                        selectedPromptTemplates={selectedPromptTemplates}
                        onTemplateChange={(stage, value) =>
                          setSelectedPromptTemplates((prev) => ({ ...prev, [stage]: value }))
                        }
                        llmOptions={llmConnectors.map((item) => ({
                          label: `${item.name}${item.is_default ? '（默认）' : ''}`,
                          value: item.name,
                        }))}
                        selectedLlm={selectedLlm}
                        selectedModel={selectedModel}
                        modelOptions={modelOptions}
                        onLlmChange={(value) => {
                          const connector = llmConnectors.find((item) => item.name === value)
                          setSelectedLlm(value)
                          setSelectedModel(connector?.default_model || '')
                        }}
                        onModelChange={setSelectedModel}
                        loading={loadingAction === 'writer_room'}
                        rehearsalMode={rehearsalMode}
                        onRehearsalModeChange={setRehearsalMode}
                        onRunStep={handleRunWriterRoomStep}
                        onRunBatch={handleRunWriterRoomBatch}
                        onPromote={handlePromoteWriterRoomContent}
                        continuityCandidates={continuityCandidates}
                        continuitySummary={continuitySummary}
                        onResolveContinuityCandidate={handleResolveContinuityCandidate}
                        onRewriteParagraph={handleRewriteParagraph}
                      />
                    ),
                  },
                  {
                    key: 'script',
                    label: (
                      <Space>
                        <FileTextOutlined />
                        正文/漫画
                      </Space>
                    ),
                    children: (
                      <ScriptTab
                        novelBodies={novelBodies}
                        comicPages={comicPages}
                        chapterPlan={chapterPlan}
                        onSendImagePrompt={handleInlineGenerateImage}
                        inlineImages={inlineImages}
                        inlineImageLoadingKey={inlineImageLoadingKey}
                        projectTitle={selectedProject?.title || ''}
                      />
                    ),
                  },
                  {
                    key: 'canvas',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        关系图谱
                      </Space>
                    ),
                    children: (
                      <ProjectGraphTab
                        graph={projectGraphView}
                        saving={loadingAction === 'canvas_save'}
                        generating={Boolean(loadingAction || loadingChapterAction.action || inlineImageLoadingKey)}
                        onSave={handleSaveProjectGraph}
                        onOpenNode={handleOpenGraphNode}
                        onToggleLock={handleToggleGraphNodeLock}
                        onRegenerate={handleRegenerateGraphNode}
                        onSendToCanvas={handleSendGraphNodeToCanvas}
                        onSendImagePrompt={(node) => {
                          const prompt = node.source?.prompt || node.data?.image_prompt || ''
                          if (!prompt) {
                            message.warning('这个节点没有可发送的生图提示词')
                            return
                          }
                          handleInlineGenerateImage(prompt, {
                            contentId: node.source?.contentId,
                            sourceType: node.source?.sourceType || 'project_graph_prompt',
                            sourceIndex: node.source?.sourceIndex,
                            sourceTitle: node.label,
                            chapterNumber: node.source?.chapterNumber,
                            referenceAssetIds: node.data?.reference_asset_ids || [],
                            characterIds: node.data?.character_ids || [],
                            portraitNodeIds: node.data?.portrait_node_ids || [],
                            portraitVersionIds: node.data?.portrait_version_ids || [],
                          })
                        }}
                      />
                    ),
                  },
                  {
                    key: 'narrative-graph',
                    label: (
                      <Space>
                        <BranchesOutlined />
                        叙事图谱
                      </Space>
                    ),
                    children: <NarrativeGraphTab graph={narrativeGraphData} chapterNumber={activeChapterNumber} />,
                  },
                  {
                    key: 'assets',
                    label: (
                      <Space>
                        <FolderOpenOutlined />
                        素材
                      </Space>
                    ),
                    children: (
                      <AssetsTab
                        assets={projectAssets}
                        unavailableAssetIds={unavailableAssetIds}
                        loading={loadingAction === 'asset'}
                        onLinkAsset={handleLinkAsset}
                      />
                    ),
                  },
                  {
                    key: 'logs',
                    label: (
                      <Space>
                        <HistoryOutlined />
                        日志
                      </Space>
                    ),
                    children: (
                      <LogsTab
                        logs={generationLogs}
                        onRefresh={() => selectedProject && loadGenerationLogs(selectedProject.id)}
                      />
                    ),
                  },
                  {
                    key: 'json',
                    label: 'JSON',
                    children: (
                      <JsonTab
                        outline={outline}
                        chapterPlan={chapterPlan}
                        contents={contents}
                        assets={projectAssets}
                      />
                    ),
                  },
                ].filter((item) =>
                  workspaceMode === 'chapter'
                    ? ['episode-workbench', 'writer-room', 'script'].includes(item.key)
                    : ['outline', 'project-bible', 'chapters', 'canvas', 'narrative-graph', 'assets', 'logs', 'json'].includes(item.key),
                )}
              />
                </div>
              </div> : null}
            </>
          )}
        </main>
        {inspectorOpen && !cockpitCompact && selectedProject ? (
          <aside
            aria-label="叙事检查器"
            style={{
              borderLeft: `1px solid ${theme.borderLight}`,
              background: theme.bgCard,
              minHeight: 620,
              minWidth: 0,
            }}
          >
            <NarrativeInspector
              theme={theme}
              chapterNumber={activeChapterNumber}
              context={narrativeContext}
              ledger={foreshadowingLedger}
              graph={narrativeGraphData}
              facts={[...projectBibleContents, ...worldAssetContents]}
              continuityCandidates={continuityCandidates}
              continuitySummary={continuitySummary}
              logs={narrativeInspectorLogs}
              runs={narrativeRuns}
              loading={narrativeLoading}
              onRefresh={() => selectedProject && loadNarrativeRuntime(selectedProject.id, activeChapterNumber)}
              onDecision={handleForeshadowingDecision}
              onRunControl={handleNarrativeRunControl}
              onAutopilot={handleNarrativeAutopilot}
              onOpenWriterRoom={() => openWorkspaceTab('writer-room', 'chapter')}
              onOpenFacts={() => openWorkspaceTab('project-bible', 'overview')}
            />
          </aside>
        ) : null}
      </div>

      {inspectorOpen && cockpitCompact && selectedProject ? (
        <aside
          aria-label="叙事检查器"
          style={{ marginTop: 12, border: `1px solid ${theme.borderLight}`, borderRadius: 8, background: theme.bgCard }}
        >
          <NarrativeInspector
            theme={theme}
            chapterNumber={activeChapterNumber}
            context={narrativeContext}
            ledger={foreshadowingLedger}
            graph={narrativeGraphData}
            facts={[...projectBibleContents, ...worldAssetContents]}
            continuityCandidates={continuityCandidates}
            continuitySummary={continuitySummary}
            logs={narrativeInspectorLogs}
            runs={narrativeRuns}
            loading={narrativeLoading}
            onRefresh={() => selectedProject && loadNarrativeRuntime(selectedProject.id, activeChapterNumber)}
            onDecision={handleForeshadowingDecision}
            onRunControl={handleNarrativeRunControl}
            onAutopilot={handleNarrativeAutopilot}
            onOpenWriterRoom={() => openWorkspaceTab('writer-room', 'chapter')}
            onOpenFacts={() => openWorkspaceTab('project-bible', 'overview')}
          />
        </aside>
      ) : null}

      <Modal
        title="新建创作项目"
        className="creative-project-create-modal"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        afterOpenChange={(open) => {
          if (open) {
            const current = form.getFieldsValue()
            if (!current.idea && !current.title) {
              form.setFieldsValue({ source_type: 'original_idea', project_type: 'short_drama', production_profile: 'vertical_drama' })
            }
            loadNovelAssets()
          }
        }}
        onOk={() => form.submit()}
        confirmLoading={loadingAction === 'create'}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ source_type: 'original_idea', project_type: 'short_drama', production_profile: 'vertical_drama' }}
          onFinish={handleCreate}
        >
          <Form.Item label="来源" name="source_type">
            <Select
              options={[
                { label: '原创创意', value: 'original_idea' },
                { label: '小说书架', value: 'novel' },
              ]}
              onChange={() => {
                form.setFieldsValue({ novel_asset_id: undefined, chapter_indices: [], chapter_range: '' })
              }}
            />
          </Form.Item>
          <Form.Item label="标题" name="title">
            <Input placeholder="可留空，生成大纲后会自动更新" />
          </Form.Item>
          <Form.Item label="内容生产方案" name="production_profile">
            <Select
              classNames={{ popup: { root: 'creative-project-profile-dropdown' } }}
              options={productionProfileOptions.map((item) => ({
                value: item.value,
                label: item.label,
                title: item.description,
              }))}
              optionRender={(option) => (
                <div>
                  <div>{option.data.label}</div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{option.data.title}</Text>
                </div>
              )}
              onChange={(value) => {
                const profile = productionProfileOptions.find((item) => item.value === value)
                if (profile) {
                  form.setFieldsValue({
                    project_type: profile.projectType,
                    source_type: profile.family === 'content_package' ? 'original_idea' : form.getFieldValue('source_type'),
                  })
                }
              }}
            />
          </Form.Item>
          <Form.Item label="项目类型" name="project_type" hidden>
            <Select options={projectTypeOptions} />
          </Form.Item>
          {createSourceType === 'novel' && !createIsContentPackage ? (
            <>
              <Form.Item
                label="小说"
                name="novel_asset_id"
                rules={[{ required: true, message: '请选择小说' }]}
              >
                <Select
                  showSearch
                  loading={loadingNovelAssets}
                  placeholder="选择已加入书架的小说"
                  optionFilterProp="label"
                  options={novelAssets.map((asset) => {
                    const meta = asset.metadata || {}
                    const downloaded = Array.isArray(meta.downloaded_chapter_indices)
                      ? meta.downloaded_chapter_indices.length
                      : 0
                    const total = meta.chapter_count || meta.chapters?.length || 0
                    return {
                      label: `${getNovelDisplayTitle(asset)}${downloaded || total ? `（已下载 ${downloaded}/${total || '?'}）` : ''}`,
                      value: asset.id,
                    }
                  })}
                  onChange={() => form.setFieldsValue({ chapter_indices: [], chapter_range: '' })}
                  dropdownRender={(menu) => (
                    <>
                      {menu}
                      {!novelAssets.length && !loadingNovelAssets ? (
                        <div style={{ padding: 8 }}>
                          <Button type="link" size="small" onClick={() => navigate('/novel-bookshelf')}>
                            去小说书架添加
                          </Button>
                        </div>
                      ) : null}
                    </>
                  )}
                />
              </Form.Item>
              <Form.Item label="已下载章节" name="chapter_indices">
                <Select
                  mode="multiple"
                  allowClear
                  placeholder={
                    selectedNovelAsset
                      ? selectedNovelChapterOptions.length
                        ? '选择要导入的已下载章节；留空则使用手填范围或全部已下载章节'
                        : '这本书暂无已下载章节，请先去书架下载'
                      : '先选择小说'
                  }
                  options={selectedNovelChapterOptions}
                  disabled={!selectedNovelAsset || !selectedNovelChapterOptions.length}
                />
              </Form.Item>
              <Form.Item label="章节范围" name="chapter_range">
                <Input placeholder="可选，例如 1-3,5；用于目录未展开或快速选择" />
              </Form.Item>
              <Text type="secondary">
                只会导入已经下载到本地的章节；如果章节未下载，请先到小说书架下载。
              </Text>
            </>
          ) : createIsContentPackage ? (
            <>
              <Form.Item
                label="主题"
                name="idea"
                rules={[{ required: true, message: '请输入主题' }]}
                extra="创建后会直接生成或编辑页面、知识卡和图片提示词，不需要先填写大纲、圣经或正文。"
              >
                <TextArea rows={4} placeholder="例如：给儿童介绍十二生肖；或：一个在雨夜寻找丢失玩偶的恐怖漫画" />
              </Form.Item>
              <Form.Item label="补充说明（可选）" name="creation_brief">
                <TextArea rows={2} placeholder="例如：水彩绘本风、共 12 页、适合 6-8 岁儿童；也可以创建后再补充" />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              label="创意"
              name="idea"
              rules={[{ required: true, message: '请输入创意' }]}
            >
              <TextArea rows={5} placeholder="例如：短剧但是不降智" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title="重命名项目"
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={() => renameForm.submit()}
        confirmLoading={loadingAction === 'rename'}
        destroyOnHidden
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={renameForm}
          layout="vertical"
          onFinish={handleRename}
        >
          <Form.Item
            label="项目名称"
            name="title"
            rules={[{ required: true, message: '请输入项目名称' }, { max: 80, message: '名称最多 80 字' }]}
          >
            <Input placeholder="请输入新的项目名称" maxLength={80} allowClear />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="角色提取预览"
        open={characterExtractionOpen}
        onCancel={() => setCharacterExtractionOpen(false)}
        width={900}
        footer={characterExtractionResult?.applied ? null : [
          <Button key="cancel" onClick={() => setCharacterExtractionOpen(false)}>取消</Button>,
          <Button key="apply" type="primary" loading={characterExtractionLoading} onClick={() => void handleExtractCharacters(true)}>
            确认写入角色库
          </Button>,
        ]}
        destroyOnHidden
      >
        {characterExtractionResult ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message={`已扫描 ${characterExtractionResult.chunks || 0} 个文本块，识别 ${characterExtractionResult.characters?.length || 0} 个角色`}
              description="第一轮负责角色归并和证据，第二轮生成角色设定。确认写入后会同步项目大纲、角色库和项目关联。"
            />
            {(characterExtractionResult.merge_candidates || []).length ? (
              <Alert
                type="warning"
                showIcon
                message="有需要人工确认的同名/包含名候选"
                description={characterExtractionResult.merge_candidates.map((item: any) => `${item.left} / ${item.right}`).join('；')}
              />
            ) : null}
            <List
              size="small"
              bordered
              dataSource={characterExtractionResult.characters || []}
              renderItem={(item: any) => (
                <List.Item>
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Space wrap>
                      <Text strong>{item.name}</Text>
                      {(item.aliases || []).map((alias: string) => <Tag key={alias}>{alias}</Tag>)}
                      <Tag color="blue">证据 {item.evidence?.length || 0}</Tag>
                    </Space>
                    <Text type="secondary">{item.oneLiner || item.personality || item.extraction_notes || '暂无摘要'}</Text>
                    {item.evidence?.length ? <Text code>{item.evidence[0]}</Text> : null}
                  </Space>
                </List.Item>
              )}
            />
          </Space>
        ) : <Skeleton active />}
      </Modal>

      <Modal
        title={selectedProject?.production_profile?.package_type === 'knowledge_cards' ? '编辑科普内容包' : '编辑绘本 / 漫画内容包'}
        open={contentPackageOpen}
        onCancel={() => setContentPackageOpen(false)}
        onOk={() => contentPackageForm.submit()}
        confirmLoading={loadingAction === 'create'}
        okText="保存内容包"
        width={860}
        destroyOnHidden
      >
        <Form form={contentPackageForm} layout="vertical" onFinish={handleSaveContentPackage}>
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item label="主题" name="topic" rules={[{ required: true, message: '请输入主题' }]}>
            <Input placeholder="例如：给儿童介绍十二生肖" maxLength={500} />
          </Form.Item>
          <Form.Item label="简介 / 导语" name="brief">
            <TextArea rows={3} placeholder="可选，保存后会显示在概览中" maxLength={2000} />
          </Form.Item>
          <Space wrap style={{ marginBottom: 12 }}>
            {/* 页数刻意**不在这里填**：它应当由内容推导（后端不传 item_count 即自动），
                生成后再看实际页数（下方「页面 / 内容卡」的计数）。
                原先这里是 initialValue={12}——那个 12 会在任何内容分析之前就被写进提示词，
                模型不知道故事有多少内容、只能凑够 12 页，是"画面平、节奏匀"的结构性来源。 */}
            <Form.Item name="prompt_only" valuePropName="checked" initialValue={false} style={{ marginBottom: 0, paddingTop: 30 }}>
              <Checkbox>只生成图片提示词</Checkbox>
            </Form.Item>
            <Button icon={<RobotOutlined />} onClick={() => void handlePlanContentPackage()} loading={loadingAction === 'create'} style={{ marginTop: 30 }}>
              AI 一次生成
            </Button>
            <Button icon={<PictureOutlined />} onClick={() => void handleBatchGenerateContentPackageImages()} loading={contentPackageBatchRunning} style={{ marginTop: 30 }}>
              批量生成图片
            </Button>
          </Space>
          <Form.List name="items">
            {(fields, { add, remove, move }) => (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                  {/* 页数是**推导结果**，不是入口输入：生成后这里显示实际页数，
                      调整顺序/增删也会同步反映。 */}
                  <Text strong>
                    页面 / 内容卡{fields.length ? `（共 ${fields.length} 页）` : ''}
                  </Text>
                  <Button size="small" icon={<PlusOutlined />} onClick={() => add({ title: '', text: '', fact: '', source: '', source_url: '', image_prompt: '' })}>添加内容单元</Button>
                </Space>
                {fields.map((field, index) => (
                  <div key={field.key} style={{ border: `1px solid ${theme.borderLight}`, borderRadius: 6, padding: 12, background: theme.bgElevated }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 8 }}>
                      <Text strong>第 {index + 1} 项</Text>
                      <Space size={2}>
                        {/* 页序是绘本/漫画的实质要求：保存时 `index` 由表单顺序重算
                            （handleSaveContentPackage），因此这里调整顺序即调整出图与导出顺序。
                            用 Form.List 自带的 move（无新依赖）；已有 id 的条目会带着 id 移动，
                            所以引用它的平台输出不会因换序而失效。 */}
                        <Button
                          type="text"
                          size="small"
                          icon={<ArrowUpOutlined />}
                          title="上移一页"
                          aria-label="上移一页"
                          disabled={index === 0}
                          onClick={() => move(field.name, field.name - 1)}
                        />
                        <Button
                          type="text"
                          size="small"
                          icon={<ArrowDownOutlined />}
                          title="下移一页"
                          aria-label="下移一页"
                          disabled={index === fields.length - 1}
                          onClick={() => move(field.name, field.name + 1)}
                        />
                        <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => remove(field.name)} disabled={fields.length === 1} />
                      </Space>
                    </Space>
                    <Form.Item label="标题" name={[field.name, 'title']} style={{ marginBottom: 8 }}><Input placeholder="例如：鼠" /></Form.Item>
                    <Form.Item label="文字内容" name={[field.name, 'text']} style={{ marginBottom: 8 }}><TextArea rows={2} placeholder="页面文字或知识卡说明，可留空只生成提示词" /></Form.Item>
                    {selectedProject?.production_profile?.package_type === 'knowledge_cards' ? (
                      <>
                        <Form.Item label="知识事实" name={[field.name, 'fact']} style={{ marginBottom: 8 }}><TextArea rows={2} placeholder="可核验的事实表述，避免把推测写成结论" /></Form.Item>
                        <Form.Item label="来源说明" name={[field.name, 'source']} style={{ marginBottom: 8 }}><Input placeholder="例如：中国国家博物馆、百科资料" /></Form.Item>
                        <Form.Item label="来源链接" name={[field.name, 'source_url']} style={{ marginBottom: 8 }}><Input placeholder="可选，填写公开网页链接" /></Form.Item>
                      </>
                    ) : null}
                    <Form.Item label="图片提示词" name={[field.name, 'image_prompt']} style={{ marginBottom: 8 }}>
                      <TextArea rows={2} placeholder="可直接用于 AI 生图" />
                    </Form.Item>
                    <Space size={6} wrap>
                      <Button
                        size="small"
                        icon={<PictureOutlined />}
                        loading={inlineImageLoadingKey === imageContextKey({
                          contentId: contentPackageContent?.id,
                          sourceType: 'content_package',
                          sourceIndex: index,
                        })}
                        onClick={() => void handleGenerateContentPackageImage(index, field.name)}
                      >
                        生成图片
                      </Button>
                      <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={() => {
                          // id 由服务端生成（item-1、item-2…）；表单里新加、还没保存过的行没有 id
                          const itemId = String(contentPackageForm.getFieldValue(['items', field.name, 'id']) || '')
                          if (!itemId) {
                            message.warning('这一条还没保存过，请先「保存内容包」，再重跑单条')
                            return
                          }
                          void handleRetryContentPackageItem(itemId)
                        }}
                      >
                        重跑本条
                      </Button>
                      <Text type="secondary" style={{ fontSize: 12 }}>只重跑这一条，其它条目不动</Text>
                    </Space>
                    {/* 生成结果：`image_url` / `asset_ids` / `status` 一直由生成链路写回表单
                        （见 useProjectContentActions.handleBatchGenerateContentPackageImages），
                        此前只是从未展示——这里复用从 /multi-platform-gen 抽出的同一组件。
                        `shouldUpdate` 保证批量/单条生成写回后立即反映到界面。 */}
                    <Form.Item
                      noStyle
                      shouldUpdate={(prevValues, curValues) => {
                        const prevItem = prevValues?.items?.[field.name] || {}
                        const curItem = curValues?.items?.[field.name] || {}
                        return prevItem.image_url !== curItem.image_url || prevItem.status !== curItem.status
                      }}
                    >
                      {({ getFieldValue }) => {
                        const contextKey = imageContextKey({
                          contentId: contentPackageContent?.id,
                          sourceType: 'content_package',
                          sourceIndex: index,
                          // 必须与写入端一致：`handleInlineGenerateImage` 会用
                          // `context.chapterNumber ?? activeChapterNumber` 补键，
                          // 这里漏掉就会读到另一个键（生成成功却显示不出来）。
                          chapterNumber: activeChapterNumber,
                        })
                        // 两条写入路径都要认：**单条生成**把结果放进页面级 `inlineImages`
                        // （useInlineImageGeneration 的同步分支），**批量生成**写回表单的
                        // `items[i].image_url`。只读其中一个会导致另一条路径"生成了却看不到"。
                        const inline = inlineImages?.[contextKey]
                        const imageUrl = String(inline?.url || getFieldValue(['items', field.name, 'image_url']) || '')
                        const itemStatus = String(getFieldValue(['items', field.name, 'status']) || '')
                        const generating = inlineImageLoadingKey === contextKey
                        return (
                          <div style={{ marginTop: 10, width: 96 }}>
                            <GeneratedMediaThumb
                              url={imageUrl}
                              error={itemStatus === 'failed' ? '生成失败' : undefined}
                              emptyText="尚未生成"
                              loading={generating}
                              // 无图时不传 onRegenerate：占位形态的按钮文案是「重试」，
                              // 而这一条还没生成过，上方已有「生成图片」按钮，不该出现重复且语义不符的入口。
                              onRegenerate={imageUrl ? () => void handleGenerateContentPackageImage(index, field.name) : undefined}
                              removeTitle="移除结果（素材库中的资产保留）"
                              onRemove={imageUrl
                                ? () => {
                                  // 只解除本条对结果的引用；资产仍在素材库，避免在编辑器里做不可逆删除
                                  contentPackageForm.setFieldValue(['items', field.name, 'image_url'], '')
                                  contentPackageForm.setFieldValue(['items', field.name, 'asset_ids'], [])
                                  contentPackageForm.setFieldValue(['items', field.name, 'status'], 'ready')
                                }
                                : undefined}
                            />
                          </div>
                        )
                      }}
                    </Form.Item>
                  </div>
                ))}
              </Space>
            )}
          </Form.List>

          <Divider style={{ margin: '18px 0 12px', fontSize: 13 }}>平台输出</Divider>
          <Space wrap style={{ marginBottom: 10 }}>
            <Button
              icon={<DownloadOutlined />}
              loading={loadingAction === 'create'}
              onClick={() => void handleBuildContentPackageOutputs()}
            >
              生成平台输出
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              按当前内容生产方案声明的输出一次全出；只在本地做格式转换，不会发到外部平台
            </Text>
          </Space>
          <PackageOutputList
            outputs={packageOutputs}
            packageType={selectedProject?.production_profile?.package_type}
          />
        </Form>
      </Modal>

      <FanqiePublishPanel
        visible={fanqieOpen}
        onClose={() => setFanqieOpen(false)}
        projectId={selectedProject?.id || ''}
        contentId={contentForChapter('novel_body', activeChapterNumber)?.id || ''}
        chapterNumber={activeChapterNumber}
        chapterTitle={contentForChapter('novel_body', activeChapterNumber)?.title}
      />
    </div>
  )
}
