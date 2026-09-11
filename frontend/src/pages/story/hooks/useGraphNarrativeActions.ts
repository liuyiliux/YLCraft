/**
 * 创作项目工作台的动作：handleRegenerateGraphNode, handleToggleGraphNodeLock, handleSendGraphNodeToCanvas, handleOpenGraphNode。…
 *
 * 从 story/index.tsx 抽出的动作 hook（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；入参由自由变量自动推导，本批为过渡拆分，签名待收紧。
 */
import { configureCreativeProjectNarrativeAutopilot, controlCreativeProjectNarrativeRun, decideCreativeProjectForeshadowing, extractCreativeProjectContinuity, resolveCreativeProjectContinuityCandidate, saveCreativeProjectCanvas, saveCreativeProjectContentAsAsset } from '../../../api'
import { enqueueCanvasImport } from '../../../components/canvas/bridge'
import { ChapterPlanItem } from '../../../types/api'
import { ProjectGraphNode, ProjectGraphState } from '../types'
import { graphNodeToCanvasNode, isChapterLocked } from '../utils'
import { message } from 'antd'

export function useGraphNarrativeActions(deps: Record<string, any>) {
  const {
    activeChapterNumber,
    chapterPlan,
    chapters,
    handleGenerateChapterOutline,
    handleGenerateChapterPlan,
    handleGenerateNovelBody,
    handleGenerateOutline,
    handleGenerateScript,
    handleGenerateStoryboardForChapter,
    handleSaveChapterPlan,
    handleSaveContent,
    handleSplitComicPages,
    loadContents,
    loadContinuityFacts,
    loadNarrativeRuntime,
    loadProjectAssets,
    navigate,
    openChapterStudio,
    openWorkspaceTab,
    outline,
    selectedProject,
    setLoadingAction,
    setProjectGraph,
  } = deps

  async function handleNarrativeRunControl(runId: string, action: 'pause' | 'resume' | 'retry' | 'cancel') {
    if (!selectedProject) return
    try {
      await controlCreativeProjectNarrativeRun(selectedProject.id, runId, action)
      await loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
    } catch (error: any) {
      message.error(error?.message || '叙事运行操作失败')
    }
  }
  async function handleNarrativeAutopilot(enabled: boolean) {
    if (!selectedProject) return
    try {
      await configureCreativeProjectNarrativeAutopilot(selectedProject.id, {
        enabled,
        chapter_numbers: [activeChapterNumber],
      })
      await loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
    } catch (error: any) {
      message.error(error?.message || '受控自动推进配置失败')
    }
  }
  async function handleForeshadowingDecision(itemId: string, action: 'accept' | 'advance' | 'resolve' | 'ignore') {
    if (!selectedProject) return
    try {
      await decideCreativeProjectForeshadowing(selectedProject.id, itemId, action, { current_chapter: activeChapterNumber })
      await loadNarrativeRuntime(selectedProject.id, activeChapterNumber)
    } catch (error: any) {
      message.error(error?.message || '伏笔状态更新失败')
    }
  }
  async function handleSaveProjectGraph(nextGraph: ProjectGraphState) {
    if (!selectedProject) return
    setLoadingAction('canvas_save')
    try {
      const payload = {
        ...nextGraph,
        updated_at: new Date().toISOString(),
      }
      const response = await saveCreativeProjectCanvas(selectedProject.id, payload)
      setProjectGraph(response?.data || payload)
      message.success('关系图谱布局已保存')
    } catch (error: any) {
      message.error(error?.message || '保存关系图谱布局失败')
    } finally {
      setLoadingAction(null)
    }
  }
  function handleOpenGraphNode(node: ProjectGraphNode) {
    const source = node.source || {}
    if (source.chapterNumber) {
      openChapterStudio(Number(source.chapterNumber), source.tab || 'episode-workbench')
      return
    }
    if (node.type === 'asset' && source.assetId) {
      openWorkspaceTab('assets', 'overview')
      return
    }
    if (source.tab) openWorkspaceTab(source.tab)
  }
  async function handleToggleGraphNodeLock(node: ProjectGraphNode) {
    if (node.type === 'content' && node.source?.contentId) {
      const nextLocked = node.status !== 'locked'
      await handleSaveContent(node.source.contentId, { is_locked: nextLocked })
      return
    }
    if (node.type === 'chapter' && node.source?.chapterNumber) {
      const nextChapters = chapters.map((chapter: ChapterPlanItem) => {
        if (Number(chapter.chapter_number) !== Number(node.source?.chapterNumber)) return chapter
        const nextLocked = !isChapterLocked(chapter)
        return { ...chapter, status: nextLocked ? 'locked' : 'draft' }
      })
      await handleSaveChapterPlan({ ...chapterPlan, chapter_count: nextChapters.length, chapters: nextChapters })
    }
  }
  async function handleRegenerateGraphNode(node: ProjectGraphNode) {
    const chapterNumber = Number(node.source?.chapterNumber || 0)
    const contentType = node.source?.contentType
    if (node.type === 'outline') {
      await handleGenerateOutline()
      return
    }
    if (node.type === 'chapter') {
      await handleGenerateChapterPlan({ preserveLocked: true })
      return
    }
    if (!chapterNumber) {
      message.warning('这个节点暂不支持直接再生成')
      return
    }
    if (contentType === 'chapter_outline') await handleGenerateChapterOutline(chapterNumber)
    else if (contentType === 'novel_body') await handleGenerateNovelBody(chapterNumber)
    else if (contentType === 'script') await handleGenerateScript(chapterNumber)
    else if (contentType === 'storyboard') await handleGenerateStoryboardForChapter(chapterNumber)
    else if (contentType === 'comic_pages') await handleSplitComicPages(chapterNumber)
    else message.warning('这个节点暂不支持直接再生成')
  }
  function handleSendGraphNodeToCanvas(node: ProjectGraphNode) {
    if (!selectedProject) return
    enqueueCanvasImport([
      {
        id: `graph-import-${node.id}-${Date.now()}`,
        projectId: selectedProject.id,
        sourceNodeId: node.id,
        createdAt: new Date().toISOString(),
        node: graphNodeToCanvasNode(node, selectedProject),
      },
    ])
    message.success('已发送到创作画布')
    navigate('/canvas')
  }
  async function handleResolveContinuityCandidate(candidateId: string, action: 'accept' | 'ignore') {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      await resolveCreativeProjectContinuityCandidate(selectedProject.id, candidateId, action)
      message.success(action === 'accept' ? '已锁定为项目事实' : '已忽略该候选')
      await Promise.all([loadContents(selectedProject.id), loadContinuityFacts(selectedProject.id)])
    } catch (error: any) {
      message.error(error?.message || '处理连续性候选失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleSaveContentAsAsset(contentId: string) {
    if (!selectedProject) return
    setLoadingAction('asset')
    try {
      const response = await saveCreativeProjectContentAsAsset(selectedProject.id, contentId)
      message.success(response?.created_node ? '已保存为文本素材' : '已新增文本素材版本')
      await loadProjectAssets(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '保存文本素材失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleExtractContinuity(contentId: string) {
    if (!selectedProject) return
    setLoadingAction('project_bible')
    try {
      const response = await extractCreativeProjectContinuity(selectedProject.id, contentId)
      const count = response?.data?.length || 0
      message.success(count ? `已提取 ${count} 条连续性候选卡` : '连续性候选卡已存在')
      await loadContents(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '提取连续性候选失败')
    } finally {
      setLoadingAction(null)
    }
  }

  return {
    handleRegenerateGraphNode,
    handleToggleGraphNodeLock,
    handleSendGraphNodeToCanvas,
    handleOpenGraphNode,
    handleExtractContinuity,
    handleResolveContinuityCandidate,
    handleSaveContentAsAsset,
    handleNarrativeRunControl,
    handleNarrativeAutopilot,
    handleForeshadowingDecision,
    handleSaveProjectGraph,
  }
}
