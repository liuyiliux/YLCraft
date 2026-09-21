/**
 * 创作项目工作台的动作：handleActiveChapterChange, handleCreativeSkillIdsChange, handleDefaultImageModelChange, handleRunPipeline。…
 *
 * 从 story/index.tsx 抽出的动作 hook（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；入参由自由变量自动推导，本批为过渡拆分，签名待收紧。
 */
import { agentChat, getOrCreatePrevisScene, runCreativeProjectPipeline, updateCreativeProject } from '../../../api'
import { ChapterPlanItem, CreativeProjectGenerateResponse, CreativeProjectResponse } from '../../../types/api'
import { PipelineResult, VideoGenerationContext } from '../types'
import { dedupeStrings, getPipelineFailedRows, getPipelineSummary, isPipelineStageValue, normalizeStoryboardVideoDuration, parseChapterRange, pipelineStageLabels } from '../utils'
import { Modal, message } from 'antd'

export function useWorkbenchPreferenceActions(deps: Record<string, any>) {
  const {
    activeChapterNumber,
    activeChapterRestoreRef,
    activeProjectMeta,
    chapterCount,
    chapters,
    comicPageCount,
    comicStyle,
    defaultImageModel,
    imageBackends,
    loadContents,
    loadGenerationLogs,
    loadProjectAssets,
    navigate,
    outline,
    pipelineChapters,
    pipelineContinueOnError,
    pipelineResult,
    pipelineSkipExisting,
    pipelineStages,
    refreshSelected,
    selectedLlm,
    selectedModel,
    selectedProject,
    setActiveChapterNumber,
    setLoadingAction,
    setPipelineResult,
    setPipelineRunStatus,
    setProjects,
    setSavingImageModel,
    setSelectedProject,
  } = deps

  async function handleActiveChapterChange(nextChapter: number) {
    if (!selectedProject) return
    const chapterNumber = Number(nextChapter)
    if (!chapters.some((item: ChapterPlanItem) => Number(item.chapter_number) === chapterNumber)) return

    activeChapterRestoreRef.current.pendingLocalChapter = chapterNumber
    setActiveChapterNumber(chapterNumber)
    const metadata = { ...(selectedProject.metadata || {}), writer_room_active_chapter: chapterNumber }
    try {
      const response = (await updateCreativeProject(selectedProject.id, { metadata })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
    } catch (error: any) {
      // The local selection remains usable; persistence can retry on the next chapter switch.
      message.warning(error?.message || '保存当前写作章节失败')
    }
  }
  async function handleCreativeSkillIdsChange(nextSkillIds: string[]) {
    if (!selectedProject) return
    const settings = {
      ...(selectedProject.settings || {}),
      creative_skill_ids: nextSkillIds,
    }
    try {
      const response = (await updateCreativeProject(selectedProject.id, { settings })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
        message.success('已保存写作方法包')
      }
    } catch (error: any) {
      message.error(error?.message || '保存写作方法包失败')
    }
  }
  async function handleDefaultImageModelChange(value?: string) {
    if (!selectedProject) return
    const backend = imageBackends.find((item) => item.name === value)
    const nextMeta = { ...activeProjectMeta }
    if (backend) {
      nextMeta.default_image_model = {
        name: backend.name,
        provider: backend.provider,
        provider_label: backend.provider_label,
        model: backend.model,
        default_size: backend.supported_sizes?.[0] || '1024x1024',
        support_reference_image: Boolean(backend.support_reference_image),
        capabilities: backend.capabilities || [],
      }
    } else {
      delete nextMeta.default_image_model
    }

    setSavingImageModel(true)
    try {
      const response = (await updateCreativeProject(selectedProject.id, { metadata: nextMeta })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
      message.success(backend ? '默认生图模型已保存' : '已清除默认生图模型')
    } catch (error: any) {
      message.error(error?.message || '保存默认生图模型失败')
    } finally {
      setSavingImageModel(false)
    }
  }
  async function handleRunPipeline(options: { retryFailed?: boolean } = {}) {
    if (!selectedProject) return
    const retryFailedRows = options.retryFailed ? getPipelineFailedRows(pipelineResult) : []
    const retryStages = Array.from(
      new Set(retryFailedRows.map((item) => item.stage).filter(isPipelineStageValue)),
    )
    const retryChapters = Array.from(
      new Set(
        retryFailedRows
          .map((item) => Number(item.chapter_number || 0))
          .filter((chapter) => Number.isFinite(chapter) && chapter > 0),
      ),
    ).sort((a, b) => a - b)
    const effectiveStages = options.retryFailed ? retryStages : pipelineStages
    const effectiveSkipExisting = options.retryFailed ? true : pipelineSkipExisting
    const effectiveContinueOnError = options.retryFailed ? true : pipelineContinueOnError

    if (options.retryFailed && !retryFailedRows.length) {
      message.info('本次批量生产没有失败步骤')
      return
    }
    if (!effectiveStages.length) {
      message.warning('请至少选择一个生产阶段')
      return
    }
    const parsedChapters = parseChapterRange(pipelineChapters)
    const effectiveChapters = options.retryFailed ? retryChapters : parsedChapters
    if (!effectiveChapters.length && !effectiveStages.some((stage) => ['outline', 'sync_characters', 'chapter_plan'].includes(stage))) {
      message.warning('请填写章节范围，例如 1、1-3 或 1,3,5')
      return
    }

    setLoadingAction('pipeline')
    setPipelineRunStatus('running')
    if (!options.retryFailed) {
      setPipelineResult(null)
    }
    try {
      const response = (await runCreativeProjectPipeline(selectedProject.id, {
        stages: effectiveStages,
        chapters: effectiveChapters.length ? effectiveChapters : undefined,
        chapter_count: effectiveChapters.length ? undefined : chapterCount,
        page_count: comicPageCount,
        visual_style: comicStyle || undefined,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        skip_existing: effectiveSkipExisting,
        continue_on_error: effectiveContinueOnError,
        match_source_type: 'storyboard',
      })) as CreativeProjectGenerateResponse<PipelineResult>

      const result = response.data || null
      setPipelineResult(result)
      const { generated, skipped, failed } = getPipelineSummary(result)
      setPipelineRunStatus(failed > 0 ? (generated > 0 || skipped > 0 ? 'partial' : 'failed') : 'success')
      message.success(`${options.retryFailed ? '失败步骤重试' : '批量生产'}完成：生成 ${generated}，跳过 ${skipped}，失败 ${failed}`)
      if (response.project) {
        await refreshSelected(response.project)
      } else {
        await refreshSelected(selectedProject)
      }
      await loadContents(selectedProject.id)
      await loadProjectAssets(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      setPipelineRunStatus('failed')
      message.error(error?.message || '批量生产失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleAgentAdvanceProject() {
    if (!selectedProject) return
    const parsedChapters = parseChapterRange(pipelineChapters)
    const targetChapters = parsedChapters.length ? parsedChapters : [activeChapterNumber]
    const selectedStageLabels = pipelineStages.map((stage) => pipelineStageLabels[stage] || stage)
    setLoadingAction('agent_advance')
    try {
      const response = await agentChat({
        profile_id: 'creative-director',
        message: [
          `请作为创作导演推进创作项目《${selectedProject.title}》。`,
          `优先检查并推进章节：${targetChapters.join('、')}。`,
          `当前勾选的生产阶段：${selectedStageLabels.join('、') || '未选择'}。`,
          '请先读取项目上下文，判断缺口，再在授权工具范围内调用创作项目工具；如果需要高风险或消耗型工具，请生成待确认步骤。',
          '输出时给出：已完成动作、发现的问题、下一步建议，以及涉及的项目/章节/素材对象。',
        ].join('\n'),
        context: {
          source_page: 'creative_project',
          action: 'advance_project',
          project_id: selectedProject.id,
          creative_project_id: selectedProject.id,
          project_title: selectedProject.title,
          current_stage: selectedProject.current_stage,
          active_chapter_number: activeChapterNumber,
          target_chapters: targetChapters,
          pipeline_stages: pipelineStages,
          pipeline_stage_labels: selectedStageLabels,
          chapter_count: chapterCount,
          page_count: comicPageCount,
          visual_style: comicStyle,
          provider: selectedLlm || undefined,
          model: selectedModel || undefined,
          default_image_model: defaultImageModel,
          skip_existing: pipelineSkipExisting,
          continue_on_error: pipelineContinueOnError,
        },
      })
      const runId = response?.run_id || ''
      Modal.success({
        title: '已创建智能体推进任务',
        content: runId
          ? `Run ${runId} 已创建，可以到智能体工作室查看执行轨迹、确认高风险步骤或继续委派子任务。`
          : '已发送给创作导演，可以到智能体工作室查看执行结果。',
        okText: '去智能体工作室',
        onOk: () => navigate('/agent'),
      })
    } catch (error: any) {
      message.error(error?.message || '创建智能体推进任务失败')
    } finally {
      setLoadingAction(null)
    }
  }
  /**
   * 打开某格分镜的 3D 预演。
   *
   * `options.draft` 为真时带 `draft=1` 进入：预演台**先把该格的初稿算出来并进入幽灵态**
   * （"分镜 → 初稿"这条主动线的一键入口，tasks 6.1）。参数由预演台在生成后自行去掉，
   * 因此刷新页面不会重复生成。
   */
  async function handleOpenPrevis(
    storyboardContentId: string,
    panelNumber: number,
    title?: string,
    options?: { draft?: boolean; queue?: number[] },
  ) {
    if (!selectedProject) return
    /**
     * 批量：把勾选的每一格都取到（或建出）自己的场景，然后**从第一格开始逐格确认**（tasks 6.12）。
     *
     * 队列放在 URL 上（`queue=场景ID,...`），由预演台按 `scene_id` 在队列里的位置推进——
     * 因此这里只负责"备齐场景"，**一格都不生成草案**：草案由预演台在每一格各自生成，
     * 确认也必须逐格点。"批量"批的是导航，不是确认。
     */
    const panelNumbers = options?.queue?.length ? options.queue : [panelNumber]
    try {
      const sceneIds: string[] = []
      const skipped: number[] = []
      for (const number of panelNumbers) {
        try {
          const scene = await getOrCreatePrevisScene({
            projectId: selectedProject.id,
            storyboardContentId,
            panelNumber: number,
            title,
          })
          sceneIds.push(scene.id)
        } catch {
          // 一格失败不该拖垮整批：先记下，最后一起说清楚跳过了哪几格
          skipped.push(number)
        }
      }
      if (!sceneIds.length) {
        message.error('没有可用的预演场景：这几格的场景都没能创建出来')
        return
      }
      if (skipped.length) {
        message.warning(`有 ${skipped.length} 格没能打开（分镜 ${skipped.join('、')}），已从批量中跳过`)
      }
      const params = new URLSearchParams({ scene_id: sceneIds[0] })
      if (options?.draft) params.set('draft', '1')
      // 只有一格时不写队列：预演台据此不显示批量进度，避免"1/1 的批量"这种噪音
      if (sceneIds.length > 1) params.set('queue', sceneIds.join(','))
      navigate(`/previs?${params.toString()}`)
    } catch (error: any) {
      message.error(error?.message || '打开 3D 预演失败')
    }
  }
  function handleOpenVideoGeneration(prompt: string, context: VideoGenerationContext = {}) {
    if (!selectedProject) return
    const params = new URLSearchParams({
      prompt: prompt.trim(),
      project_id: selectedProject.id,
      content_id: context.contentId || '',
      chapter_number: String(context.chapterNumber ?? activeChapterNumber),
      source_index: context.sourceIndex !== undefined ? String(context.sourceIndex) : '',
      source_type: context.sourceType || 'storyboard_panel',
      source_title: context.sourceTitle || '',
      aspect_ratio: '9:16',
      duration: String(normalizeStoryboardVideoDuration(context.durationSeconds)),
      generate_audio: context.generateAudio ? 'true' : 'false',
    })
    const referenceAssetIds = dedupeStrings([
      ...(context.referenceAssetIds || []),
      ...(context.portraitNodeIds || []),
    ])
    if (referenceAssetIds.length) params.set('reference_asset_ids', referenceAssetIds.join(','))
    if (context.musicHint?.trim()) params.set('music_hint', context.musicHint.trim())
    navigate(`/video-gen?${params.toString()}`)
  }

  return {
    handleActiveChapterChange,
    handleCreativeSkillIdsChange,
    handleDefaultImageModelChange,
    handleRunPipeline,
    handleAgentAdvanceProject,
    handleOpenVideoGeneration,
    handleOpenPrevis,
  }
}
