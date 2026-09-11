import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Collapse,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Progress,
  Segmented,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeleteOutlined,
  DeploymentUnitOutlined,
  DownOutlined,
  DownloadOutlined,
  EditOutlined,
  EnvironmentOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  UserOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  agentChat,
  createCreativeProject,
  createCreativeProjectFromNovel,
  deleteCreativeProject,
  extractCreativeProjectContinuity,
  getCreativeProjectContinuityContextSummary,
  getCreativeProjectNarrativeContextPreview,
  getCreativeProjectNarrativeGraph,
  getCreativeProjectNarrativeHealth,
  getCreativeProjectWritingPreflight,
  listCreativeProjectNarrativeRuns,
  controlCreativeProjectNarrativeRun,
  configureCreativeProjectNarrativeAutopilot,
  generateCharacterPortrait,
  generateCreativeProjectChapterPlan,
  generateCreativeProjectChapterOutline,
  generateCreativeProjectNovelBody,
  generateCreativeProjectOutline,
  extractCreativeProjectCharacters,
  generateCreativeProjectScript,
  generateCreativeProjectStoryboard,
  generateImage as generateImageApi,
  getAsset,
  getCharacter,
  getCreativeProjectCanvas,
  getImageTask,
  getImageBackends,
  getPlatformTemplates,
  listAssets,
  linkCreativeProjectAsset,
  listConnectors,
  listCreativeProjectContents,
  listCreativeProjectContinuityCandidates,
  listCreativeProjectForeshadowing,
  listCreativeProjectAssets,
  listCreativeProjectGenerationLogs,
  listCreativeProjects,
  getOrCreatePrevisScene,
  listTasks,
  matchCreativeProjectReferenceAssets,
  promoteCreativeProjectWriterRoomContent,
  refineCreativeProjectNovelBody,
  regenerateCreativeProjectChapterOutlineScenes,
  runCreativeProjectPipeline,
  runCreativeProjectWriterRoomStep,
  rewriteCreativeProjectParagraph,
  resolveCreativeProjectContinuityCandidate,
  decideCreativeProjectForeshadowing,
  splitCreativeProjectComicPages,
  syncCreativeProjectBible,
  syncCreativeProjectCharacters,
  saveCreativeProjectCanvas,
  saveCreativeProjectContentAsAsset,
  saveCreativeProjectContentPackage,
  planCreativeProjectContentPackage,
  getTask,
  updateCreativeProject,
  updateCreativeProjectContent,
  type PlatformTemplate,
  type CreativeProjectContinuityCandidate,
} from '../../api'
import {
  startProjectWorldExtraction,
  listProjectWorldDomains,
  listProjectWorldEntities,
  listProjectWorldEntityRelations,
  listWorldBuildingSuggestions,
  confirmSuggestedField,
  ignoreSuggestedField,
  upsertProjectWorldDomain,
  resetProjectWorldDomain,
  previewEntityExpansion,
  expandEntityAttributes,
  expandWorldDomain,
  draftWorldTemplate,
  listWorldTemplates,
  upsertWorldTemplate,
  deleteWorldTemplate,
  type WorldBuildingSuggestions,
  type WorldBuildingTemplate,
  type WorldDomainExpansionTask,
  type WorldEntity,
  type WorldEntityRelation,
} from '../../api/novelSource'
import type {
  ChapterPlanItem,
  ChapterPlan,
  CreativeProject,
  CreativeProjectGenerateResponse,
  CreativeProjectListResponse,
  CreativeProjectResponse,
  Provider,
  StoryOutline,
  StoryOutlineCharacter,
  WritingPreflight,
  WritingMethodCandidate,
} from '../../types/api'
import { useTheme, type ThemeColors } from '../../constants/theme'
import { worldFieldLabel, worldFieldValueText } from '../../utils/worldFieldLabels'
import ProviderModelSelect from '../../components/ai/ProviderModelSelect'
import useLlmConnectors from '../../hooks/useLlmConnectors'
import { enqueueCanvasImport } from '../../components/canvas/bridge'
import type { CanvasNode, CanvasNodeType } from '../../components/canvas/types'
import { useTaskPolling } from '../../hooks/useTaskPolling'
import FanqiePublishPanel from './FanqiePublishPanel'
import ProjectStatePanel from './ProjectStatePanel'
import StoryWorkspaceOverview from './StoryWorkspaceOverview'
import type { AssetSummary, ChapterAction, CharacterReferenceSummary, EditableChapterPlanItem, ImageBackendOption, ImagePromptContext, InlineGeneratedImage, LoadingAction, NarrativeContextPreview, NarrativeForeshadowing, NarrativeGraphData, NarrativeHealth, NarrativeRun, PendingInlineImageTask, PipelineResult, PipelineResultItem, PipelineRunStatus, PipelineStageValue, ProductionStageItem, ProjectAssetLink, ProjectContent, ProjectContentSummary, ProjectGenerationLog, ProjectGraphEdge, ProjectGraphNode, ProjectGraphNodeType, ProjectGraphState, ProseDiffRow, ReferenceImageItem, StoryboardPanelReferencePlan, StoryboardReferenceSummary, TemplateOption, VideoGenerationContext, WorkspaceResource, WriterRoomQualitySummary, WriterRoomReviewIssue } from './types'
import { comicPreviewGridStyle, comicPreviewPageStyle, createCompactBlockStyle, createResizeHandleLineStyle, createResizeHandleStyle, createWorkbenchHeaderStyle, graphNodeStyle, inlineImageShellStyle, panelStyle, readerLayoutStyle, readerPanelStyle, readerTextStyle, readerTocButtonActiveStyle, readerTocButtonStyle, readerTocListStyle, readerTocStyle, referenceAssetCardStyle, referenceAssetPlaceholderStyle, writerRoomBatchControlStyle, writerRoomComparePaneStyle, writerRoomContextBlockStyle, writerRoomContextGridStyle, writerRoomContinuityItemStyle, writerRoomContinuityStyle, writerRoomDiffColumnsStyle, writerRoomDiffListStyle, writerRoomDiffRowStyle, writerRoomDiffTextStyle, writerRoomIssueStyle, writerRoomLogBlockStyle, writerRoomMainPanelStyle, writerRoomMetricGridStyle, writerRoomMetricStyle, writerRoomParagraphButtonActiveStyle, writerRoomParagraphButtonStyle, writerRoomParagraphListStyle, writerRoomPipelineStyle, writerRoomPreviewStyle, writerRoomProgressStyle, writerRoomPromoteSummaryStyle, writerRoomQualityStyle, writerRoomShellStyle, writerRoomStepButtonActiveStyle, writerRoomStepButtonStyle, writerRoomStepIndexStyle, writerRoomStepListStyle, writerRoomStepTitleStyle, writerRoomTeamAvatarStyle, writerRoomTeamGridStyle, writerRoomTeamJoinStyle, writerRoomTeamRoleBodyStyle, writerRoomTeamRoleHeaderStyle, writerRoomTeamRoleStyle, writerRoomVersionStatusStyle, writerRoomWorkspaceStyle } from './styles'
import { STORY_WORKSPACE_CONTENT_TYPES, assetFileUrl, buildChapterPlanMarkdown, buildCreativeProjectGraph, buildNovelChapterMarkdown, buildOutlineMarkdown, buildProseDiffRows, buildScriptMarkdown, buildStoryboardMarkdown, buildStoryboardPanelReferencePlan, buildStoryboardReferenceSummary, buildStoryboardVideoFallbackPrompt, canvasTypeForGraphNode, collectStoryboardCharacterIds, comicStyleOptions, compactNovelReaderText, contextLayerLabel, dedupeProjectAssetLinks, dedupeReferenceImageItems, dedupeStrings, downloadTextFile, escapePreviewHtml, findWriterRoomLog, foreshadowingColor, foreshadowingLabel, getCharacterReferenceItems, getNovelChapterOptions, getNovelDisplayTitle, getPipelineFailedRows, getPipelineSummary, graphEdgeColor, graphNodeColor, graphNodeLabel, graphNodeToCanvasNode, graphNodeTypeLabel, imageContextKey, isChapterLocked, isPipelineStageValue, isProjectContentNewer, latestProjectContentsByChapter, linesToList, listToLines, markdownList, markdownSection, narrativeGraphNodeColor, normalizeChapterItem, normalizeChapterPlan, normalizeCharacterReference, normalizeStoryboardVideoDuration, openProjectTextPreview, parseChapterRange, pipelineStageLabels, pipelineStageOptions, portraitNodeToReferenceItem, productionProfileOptions, projectAssetDetailRequests, projectAssetToReferenceItem, projectContentChapterKey, projectMarkdownFilename, projectTypeLabel, projectTypeOptions, qualitySummaryForContent, referenceRoleOptions, resolveProjectAssetDetail, reviewIssuesForContent, selectReferenceAssetsForPrompt, sortBibleContents, sortProjectContentsForReading, splitWriterRoomParagraphs, stageLabels, statusLabels, textForNovelBody, timingLabel, unavailableProjectAssetIds, worldAssetRoleLabels, writerRoomAgentNames, writerRoomContentWordCount, writerRoomIssueSeverityColor, writerRoomPreviewText, writerRoomStepDescriptions, writerRoomStepInputs, writerRoomStepLabelMap, writerRoomStepNextHints, writerRoomStepOptions, writerRoomStepOutputs, writerRoomStepStatusColor } from './utils'
import { EditorField, InfoBlock, InfoListBlock, LogTextBlock, PromptTemplateSelect, ResizeHandle, WorkbenchSection } from './components/common'
import { useStoryLayout } from './hooks/useStoryLayout'
import { useWorkspaceData } from './hooks/useWorkspaceData'
import { useInlineImageGeneration } from './hooks/useInlineImageGeneration'
import { useProjectContentActions } from './hooks/useProjectContentActions'
import { usePortraitStoryboardActions } from './hooks/usePortraitStoryboardActions'
import { useWorkbenchPreferenceActions } from './hooks/useWorkbenchPreferenceActions'
import { useStoryPageContext } from './hooks/useStoryPageContext'
import { StoryWorkspaceShell } from './components/StoryWorkspaceShell'
import { useChapterContentActions } from './hooks/useChapterContentActions'
import { useWriterRoomActions } from './hooks/useWriterRoomActions'
import { useGraphNarrativeActions } from './hooks/useGraphNarrativeActions'
import { InlineImageResult, ReferenceAssetCard, ReferenceAssetPreviewStrip, ReferenceCardsPanel, StoryboardReferenceDiagnostics, StoryboardReferencePreflight, StoryboardVideoOutputStrip } from './components/storyboard-parts'
import { CharacterRehearsalCard, ProseParagraphDiff, TeamRehearsalPanel, WriterRoomLogSummary, WriterRoomQualitySummaryPanel } from './components/writer-room-parts'
import { BibleContentCard, ProjectBibleTab } from './components/bible'
import { OutlineTab, PipelinePanel, ProductionStageRail } from './components/outline'
import { ScriptTab } from './components/storyboard'
import { ChapterRail, ChapterTab, EpisodeWorkbenchTab } from './components/chapter-studio'
import { WriterRoomTab } from './components/writer-room'
import { NarrativeGraphTab, NarrativeInspector, ProjectGraphTab } from './components/graph'
import { AssetsTab, JsonTab, LogsTab } from './components/tabs'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export default function StoryPage() {
  const ctx = useStoryPageContext()

  return <StoryWorkspaceShell ctx={ctx} />
}
