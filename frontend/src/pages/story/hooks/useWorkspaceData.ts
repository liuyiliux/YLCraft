/**
 * 创作项目工作台的数据层。
 *
 * 从 story/index.tsx 抽出的第二个 hook（拆分计划 creative-project-ui-redesign #9）：
 * 项目/内容/素材/日志/连续性/叙事运行时等 32 个数据状态，以及加载它们的 16 个函数。
 * 纯数据读写，不含 UI 交互状态；StoryPage 通过解构消费，行为不变。
 */
import { getCharacter, getCreativeProjectCanvas, getCreativeProjectContinuityContextSummary, getCreativeProjectNarrativeContextPreview, getCreativeProjectNarrativeGraph, getCreativeProjectNarrativeHealth, getCreativeProjectWritingPreflight, getImageBackends, getPlatformTemplates, listAssets, listConnectors, listCreativeProjectAssets, listCreativeProjectContents, listCreativeProjectContinuityCandidates, listCreativeProjectForeshadowing, listCreativeProjectGenerationLogs, listCreativeProjectNarrativeRuns, listCreativeProjects, updateCreativeProject, type CreativeProjectContinuityCandidate, type PlatformTemplate } from '../../../api'
import { CreativeProject, CreativeProjectListResponse, CreativeProjectResponse, Provider } from '../../../types/api'
import { AssetSummary, CharacterReferenceSummary, ImageBackendOption, NarrativeContextPreview, NarrativeForeshadowing, NarrativeGraphData, NarrativeHealth, NarrativeRun, ProjectAssetLink, ProjectContent, ProjectContentSummary, ProjectGenerationLog, ProjectGraphState, WorkspaceResource } from '../types'
import { STORY_WORKSPACE_CONTENT_TYPES, dedupeStrings, normalizeCharacterReference, writerRoomStepOptions } from '../utils'
import { message } from 'antd'
import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { LoadingAction } from '../types'

export function useWorkspaceData({
  setLoadingAction,
}: {
  setLoadingAction: (value: LoadingAction) => void
}) {
  const [searchParams] = useSearchParams()

  const [projects, setProjects] = useState<CreativeProject[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [selectedProject, setSelectedProject] = useState<CreativeProject | null>(null)
  const [contents, setContents] = useState<ProjectContent[]>([])
  const [writerRoomContents, setWriterRoomContents] = useState<ProjectContent[]>([])
  const [writerRoomSummary, setWriterRoomSummary] = useState<ProjectContentSummary[]>([])
  const writerRoomRequestRef = useRef(0)
  const [projectAssets, setProjectAssets] = useState<ProjectAssetLink[]>([])
  const [assetDetails, setAssetDetails] = useState<Record<string, AssetSummary>>({})
  const [unavailableAssetIds, setUnavailableAssetIds] = useState<Record<string, true>>({})
  const [projectGraph, setProjectGraph] = useState<ProjectGraphState | null>(null)
  const [characterDetails, setCharacterDetails] = useState<Record<string, CharacterReferenceSummary>>({})
  const [generationLogs, setGenerationLogs] = useState<ProjectGenerationLog[]>([])
  const [continuityCandidates, setContinuityCandidates] = useState<CreativeProjectContinuityCandidate[]>([])
  const [continuitySummary, setContinuitySummary] = useState<Record<string, any> | null>(null)
  const [narrativeContext, setNarrativeContext] = useState<NarrativeContextPreview | null>(null)
  const [foreshadowingLedger, setForeshadowingLedger] = useState<NarrativeForeshadowing[]>([])
  const [allForeshadowingLedger, setAllForeshadowingLedger] = useState<NarrativeForeshadowing[]>([])
  const [narrativeGraphData, setNarrativeGraphData] = useState<NarrativeGraphData | null>(null)
  const [narrativeHealth, setNarrativeHealth] = useState<NarrativeHealth | null>(null)
  const [narrativeRuns, setNarrativeRuns] = useState<NarrativeRun[]>([])
  const [narrativeLoading, setNarrativeLoading] = useState(false)
  const [llmConnectors, setLlmConnectors] = useState<Provider[]>([])
  const [imageBackends, setImageBackends] = useState<ImageBackendOption[]>([])
  const [novelAssets, setNovelAssets] = useState<AssetSummary[]>([])
  const [loadingNovelAssets, setLoadingNovelAssets] = useState(false)
  const [promptTemplates, setPromptTemplates] = useState<PlatformTemplate[]>([])
  const [selectedPromptTemplates, setSelectedPromptTemplates] = useState<Record<string, string>>({})
  const [selectedLlm, setSelectedLlm] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [workspaceErrors, setWorkspaceErrors] = useState<Record<string, string>>({})
  const [projectListError, setProjectListError] = useState('')
  const [workspaceLoading, setWorkspaceLoading] = useState<Record<WorkspaceResource, boolean>>({
    contents: false,
    writerRoom: false,
    assets: false,
    logs: false,
    graph: false,
  })

  async function loadCharacterDetailsForIds(ids: string[]) {
    const uniqueIds = dedupeStrings(ids)
    const missingIds = uniqueIds.filter((id) => !characterDetails[id])
    if (!missingIds.length) return characterDetails

    const resolved: Record<string, CharacterReferenceSummary> = {}
    await Promise.all(
      missingIds.map(async (id) => {
        try {
          const payload = await getCharacter(id)
          const character = normalizeCharacterReference(payload)
          if (character?.id) resolved[character.id] = character
        } catch (error) {
          console.warn('[StoryPage] load character reference failed', id, error)
        }
      }),
    )

    if (Object.keys(resolved).length) {
      setCharacterDetails((prev) => ({ ...prev, ...resolved }))
    }
    return { ...characterDetails, ...resolved }
  }
  async function loadProjects(nextSelectedId?: string) {
    setLoadingAction('projects')
    try {
      const response = (await listCreativeProjects({ limit: 80 })) as CreativeProjectListResponse
      const data = response.data || []
      setProjects(data)
      setProjectListError('')
      const requestedId = nextSelectedId !== undefined
        ? nextSelectedId
        : searchParams.get('project_id') || selectedId
      const targetId = requestedId && data.some((item) => item.id === requestedId)
        ? requestedId
        : data[0]?.id || ''
      setSelectedId(targetId)
    } catch (error: any) {
      setProjectListError(error?.message || '项目列表加载失败')
      message.error(error?.message || '项目列表加载失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function loadLlmConnectors() {
    try {
      const response = await listConnectors({ provider_type: 'llm', active_only: true })
      const connectors = (response?.connectors || []) as Provider[]
      setLlmConnectors(connectors)
      const defaultConnector =
        connectors.find((item) => item.is_default) ||
        connectors.sort((a, b) => (a.priority || 0) - (b.priority || 0))[0]
      if (defaultConnector) {
        setSelectedLlm((current) => current || defaultConnector.name)
        setSelectedModel((current) => current || defaultConnector.default_model || '')
      }
    } catch (error) {
      setLlmConnectors([])
    }
  }
  async function loadImageBackends() {
    try {
      const response = await getImageBackends()
      setImageBackends((response?.backends || []) as ImageBackendOption[])
    } catch {
      setImageBackends([])
    }
  }
  async function persistChatModel(provider: string, model: string) {
    if (!selectedProject) return
    const nextMeta = {
      ...(selectedProject.metadata || {}),
      default_chat_provider: provider,
      default_chat_model: model,
    }
    try {
      const response = (await updateCreativeProject(selectedProject.id, { metadata: nextMeta })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
    } catch (error: any) {
      message.error(error?.message || '保存文本模型失败')
    }
  }
  async function loadPromptTemplates() {
    try {
      const response = await getPlatformTemplates({ template_scope: 'creative_project' })
      const templates = (response?.templates || []) as PlatformTemplate[]
      setPromptTemplates(templates)
      setSelectedPromptTemplates((current) => {
        const next = { ...current }
        ;[
          'outline',
          'chapter_plan',
          'chapter_outline',
          'novel_body',
          'comic_pages',
          'script',
          'storyboard',
          ...writerRoomStepOptions.map((item) => item.value),
        ].forEach((stage) => {
          if (!next[stage]) {
            const template = templates.find((item) => item.template_stage === stage)
            if (template) next[stage] = template.id
          }
        })
        return next
      })
    } catch {
      setPromptTemplates([])
    }
  }
  async function loadContents(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, contents: true }))
    try {
      const response = await listCreativeProjectContents(projectId, undefined, {
        contentTypes: STORY_WORKSPACE_CONTENT_TYPES,
      })
      setContents(response?.data || [])
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.contents; return next })
    } catch (error: any) {
      setContents([])
      setWorkspaceErrors((current) => ({ ...current, contents: error?.message || '项目内容加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, contents: false }))
    }
  }
  async function loadWriterRoomContents(projectId: string, chapterNumber?: number) {
    const requestId = writerRoomRequestRef.current + 1
    writerRoomRequestRef.current = requestId
    setWorkspaceLoading((current) => ({ ...current, writerRoom: true }))
    const contentTypes = writerRoomStepOptions.map((item) => item.value)
    const mergeCandidates = (incoming: ProjectContent[]) => {
      if (writerRoomRequestRef.current !== requestId) return
      setWriterRoomContents((current) => {
        const byId = new Map(current.map((item) => [item.id, item]))
        incoming.forEach((item) => byId.set(item.id, item))
        return Array.from(byId.values())
      })
    }
    try {
      // The inspected chapter is the user's immediate need. Load its small
      // version history first; project-wide latest candidates can reconcile
      // afterward without holding the workspace in an empty state.
      if (chapterNumber) {
        const historyResponse = await listCreativeProjectContents(projectId, undefined, {
          includeHistory: true,
          contentTypes,
          chapterNumber,
        })
        mergeCandidates(historyResponse?.data || [])
      }
      if (writerRoomRequestRef.current !== requestId) return
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.writerRoom; return next })

      // Project-wide stage counters power the chapter rail and overview badges.
      // They only need identity/version metadata, so fetch the summary rail
      // without text_content/data instead of shipping every chapter's prose.
      void listCreativeProjectContents(projectId, undefined, { contentTypes, summary: true })
        .then((response) => setWriterRoomSummary(response?.data || []))
        .catch((error: any) => {
          if (writerRoomRequestRef.current !== requestId) return
          // The current chapter remains usable even when the auxiliary rail
          // refresh fails. Surface the failure instead of turning it into an
          // empty "not generated" state.
          setWorkspaceErrors((current) => ({
            ...current,
            writerRoom: error?.message || '写作室章节轨刷新失败',
          }))
        })
    } catch (error: any) {
      if (writerRoomRequestRef.current !== requestId) return
      // Keep already visible candidates when this auxiliary refresh fails.
      setWorkspaceErrors((current) => ({ ...current, writerRoom: error?.message || '写作室候选加载失败' }))
    } finally {
      if (writerRoomRequestRef.current === requestId) {
        setWorkspaceLoading((current) => ({ ...current, writerRoom: false }))
      }
    }
  }
  async function loadProjectAssets(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, assets: true }))
    try {
      const response = await listCreativeProjectAssets(projectId)
      setProjectAssets(response?.data || [])
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.assets; return next })
    } catch (error: any) {
      setProjectAssets([])
      setWorkspaceErrors((current) => ({ ...current, assets: error?.message || '项目素材关联加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, assets: false }))
    }
  }
  async function loadGenerationLogs(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, logs: true }))
    try {
      const response = await listCreativeProjectGenerationLogs(projectId, { limit: 80 })
      setGenerationLogs(response?.data || [])
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.logs; return next })
    } catch (error: any) {
      setGenerationLogs([])
      setWorkspaceErrors((current) => ({ ...current, logs: error?.message || '生成日志加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, logs: false }))
    }
  }
  async function loadContinuityFacts(projectId: string) {
    try {
      const [candidates, summary] = await Promise.all([
        listCreativeProjectContinuityCandidates(projectId, { limit: 200 }),
        getCreativeProjectContinuityContextSummary(projectId),
      ])
      setContinuityCandidates(candidates?.data || [])
      setContinuitySummary(summary?.data || null)
    } catch {
      setContinuityCandidates([])
      setContinuitySummary(null)
    }
  }
  async function ensureWritingPreflight(chapterNumber: number, stage: string, contentId?: string) {
    if (!selectedProject) return false
    try {
      const response = await getCreativeProjectWritingPreflight(selectedProject.id, {
        chapterNumber,
        stage,
        contentId,
      })
      const result = response?.data
      if (result?.ready) return true
      message.warning(result?.next_action || '当前阶段还有前置条件未完成')
      return false
    } catch (error: any) {
      message.warning(error?.message || '无法检查当前写作阶段的前置条件')
      return false
    }
  }
  async function loadNarrativeRuntime(projectId: string, chapterNumber: number) {
    setNarrativeLoading(true)
    try {
      const [context, chapterLedger, fullLedger, graph, health, runs] = await Promise.allSettled([
        getCreativeProjectNarrativeContextPreview(projectId, chapterNumber),
        listCreativeProjectForeshadowing(projectId, { chapterNumber }),
        listCreativeProjectForeshadowing(projectId),
        getCreativeProjectNarrativeGraph(projectId, { chapterNumber }),
        getCreativeProjectNarrativeHealth(projectId),
        listCreativeProjectNarrativeRuns(projectId),
      ])
      setNarrativeContext(context.status === 'fulfilled' ? context.value?.data || null : null)
      setForeshadowingLedger(chapterLedger.status === 'fulfilled' ? chapterLedger.value?.data?.data || [] : [])
      setAllForeshadowingLedger(fullLedger.status === 'fulfilled' ? fullLedger.value?.data?.data || [] : [])
      setNarrativeGraphData(graph.status === 'fulfilled' ? graph.value?.data || null : null)
      setNarrativeHealth(health.status === 'fulfilled' ? health.value?.data || null : null)
      setNarrativeRuns(runs.status === 'fulfilled' ? runs.value?.data || [] : [])
    } finally {
      setNarrativeLoading(false)
    }
  }
  async function loadProjectGraph(projectId: string) {
    setWorkspaceLoading((current) => ({ ...current, graph: true }))
    try {
      const response = await getCreativeProjectCanvas(projectId)
      setProjectGraph(response?.data || { nodes: [], edges: [] })
      setWorkspaceErrors((current) => { const next = { ...current }; delete next.graph; return next })
    } catch (error: any) {
      setProjectGraph({ nodes: [], edges: [] })
      setWorkspaceErrors((current) => ({ ...current, graph: error?.message || '项目关系图谱加载失败' }))
    } finally {
      setWorkspaceLoading((current) => ({ ...current, graph: false }))
    }
  }
  async function loadNovelAssets() {
    setLoadingNovelAssets(true)
    try {
      const response = await listAssets({ asset_type: 'novel', page_size: 100 })
      setNovelAssets(response?.data || [])
    } catch (error: any) {
      setNovelAssets([])
      message.warning(error?.message || '加载小说书架失败')
    } finally {
      setLoadingNovelAssets(false)
    }
  }
  async function refreshSelected(project?: CreativeProject | null) {
    if (project) {
      setProjects((prev) => prev.map((item) => (item.id === project.id ? project : item)))
      setSelectedId(project.id)
      await loadContents(project.id)
      await loadProjectAssets(project.id)
      await loadGenerationLogs(project.id)
    } else {
      await loadProjects(selectedId)
    }
  }

  return {
    writerRoomRequestRef,
    projects,
    setProjects,
    selectedId,
    setSelectedId,
    selectedProject,
    setSelectedProject,
    contents,
    setContents,
    writerRoomContents,
    setWriterRoomContents,
    writerRoomSummary,
    setWriterRoomSummary,
    projectAssets,
    setProjectAssets,
    assetDetails,
    setAssetDetails,
    unavailableAssetIds,
    setUnavailableAssetIds,
    projectGraph,
    setProjectGraph,
    characterDetails,
    setCharacterDetails,
    generationLogs,
    setGenerationLogs,
    continuityCandidates,
    setContinuityCandidates,
    continuitySummary,
    setContinuitySummary,
    narrativeContext,
    setNarrativeContext,
    foreshadowingLedger,
    setForeshadowingLedger,
    allForeshadowingLedger,
    setAllForeshadowingLedger,
    narrativeGraphData,
    setNarrativeGraphData,
    narrativeHealth,
    setNarrativeHealth,
    narrativeRuns,
    setNarrativeRuns,
    narrativeLoading,
    setNarrativeLoading,
    llmConnectors,
    setLlmConnectors,
    imageBackends,
    setImageBackends,
    novelAssets,
    setNovelAssets,
    loadingNovelAssets,
    setLoadingNovelAssets,
    promptTemplates,
    setPromptTemplates,
    selectedPromptTemplates,
    setSelectedPromptTemplates,
    selectedLlm,
    setSelectedLlm,
    selectedModel,
    setSelectedModel,
    workspaceLoading,
    setWorkspaceLoading,
    workspaceErrors,
    setWorkspaceErrors,
    projectListError,
    setProjectListError,
    loadProjects,
    loadLlmConnectors,
    loadImageBackends,
    persistChatModel,
    loadPromptTemplates,
    loadContents,
    loadWriterRoomContents,
    loadProjectAssets,
    loadGenerationLogs,
    loadContinuityFacts,
    ensureWritingPreflight,
    loadNarrativeRuntime,
    loadProjectGraph,
    loadNovelAssets,
    loadCharacterDetailsForIds,
    refreshSelected,
  }
}
