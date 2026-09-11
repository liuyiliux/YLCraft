/**
 * 创作项目工作台的动作：handleRunWriterRoomStep, handleRunWriterRoomBatch, handleRewriteParagraph, handlePromoteWriterRoomContent。
 *
 * 从 story/index.tsx 抽出的动作 hook（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；入参由自由变量自动推导，本批为过渡拆分，签名待收紧。
 */
import { promoteCreativeProjectWriterRoomContent, rewriteCreativeProjectParagraph, runCreativeProjectWriterRoomStep } from '../../../api'
import { writerRoomStepLabelMap } from '../utils'
import { message } from 'antd'

export function useWriterRoomActions(deps: Record<string, any>) {
  const {
    activeChapterNumber,
    loadContents,
    loadGenerationLogs,
    loadWriterRoomContents,
    refreshSelected,
    rehearsalMode,
    selectedLlm,
    selectedModel,
    selectedProject,
    selectedPromptTemplates,
    setLoadingAction,
    setWriterRoomContents,
  } = deps

  async function handleRunWriterRoomStep(
    step: string,
    chapterNumber: number,
    contentId?: string,
    instruction?: string,
    selectedText?: string,
  ) {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      await runCreativeProjectWriterRoomStep(selectedProject.id, step, {
        chapter_number: chapterNumber,
        content_id: contentId,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates[step] || undefined,
        instruction: instruction?.trim() || undefined,
        selected_text: selectedText?.trim() || undefined,
        rehearsal_mode: rehearsalMode,
      })
      message.success('写作室步骤已完成')
      await Promise.all([loadContents(selectedProject.id), loadWriterRoomContents(selectedProject.id, chapterNumber)])
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '写作室步骤失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleRunWriterRoomBatch(chapterNumber: number, steps?: string[], contentId?: string) {
    if (!selectedProject) return
    const runSteps = steps?.length
      ? steps
      : ['scene_beats', 'character_rehearsal', 'prose_draft', 'prose_humanized', 'prose_review']
    if (!runSteps.length) {
      message.warning('请至少选择一个写作室步骤')
      return
    }
    setLoadingAction('writer_room')
    let sourceContentId = contentId
    let succeeded = 0
    let failed = 0
    let blockedBy: string | null = null
    try {
      // Run steps one request at a time so each success lands in the panel as
      // soon as it finishes.  The writer room is a linear candidate chain: when
      // a step fails, its downstream steps would only be able to fall back to a
      // stale candidate, so we stop the run instead of continuing with old data.
      for (const step of runSteps) {
        const stepLabel = writerRoomStepLabelMap[step] || step
        try {
          const response = await runCreativeProjectWriterRoomStep(selectedProject.id, step, {
            chapter_number: chapterNumber,
            content_id: sourceContentId,
            provider: selectedLlm || undefined,
            model: selectedModel || undefined,
            template_id: selectedPromptTemplates[step] || undefined,
            rehearsal_mode: rehearsalMode,
          })
          const content = response?.data
          if (content?.id) {
            sourceContentId = content.id
            succeeded += 1
            setWriterRoomContents((current) => {
              const byId = new Map(current.map((item) => [item.id, item]))
              byId.set(content.id, content)
              return Array.from(byId.values())
            })
            message.success(`「${stepLabel}」已完成`)
          } else {
            failed += 1
            blockedBy = stepLabel
            message.error(`「${stepLabel}」未返回结果`)
            break
          }
        } catch (error: any) {
          failed += 1
          blockedBy = stepLabel
          message.error(`「${stepLabel}」失败：${error?.message || '未知错误'}`)
          break
        }
      }
      if (blockedBy) {
        message.warning(`写作室已停止：成功 ${succeeded}，失败 ${failed}；「${blockedBy}」失败后，后续阶段不再使用旧候选继续。`)
      } else if (failed) {
        message.warning(`写作室批量结束：成功 ${succeeded}，失败 ${failed}`)
      } else {
        message.success(`写作室批量完成：成功 ${succeeded}`)
      }
    } finally {
      void loadWriterRoomContents(selectedProject.id, chapterNumber)
      void loadContents(selectedProject.id)
      void loadGenerationLogs(selectedProject.id)
      setLoadingAction(null)
    }
  }
  async function handlePromoteWriterRoomContent(contentId: string) {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      await promoteCreativeProjectWriterRoomContent(selectedProject.id, contentId)
      message.success('已提升为正文最新版本')
      await Promise.all([loadContents(selectedProject.id), loadWriterRoomContents(selectedProject.id, activeChapterNumber)])
      await loadGenerationLogs(selectedProject.id)
      await refreshSelected(selectedProject)
    } catch (error: any) {
      message.error(error?.message || '提升正文失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleRewriteParagraph(
    contentId: string,
    paragraphIndex: number,
    instruction: string,
  ) {
    if (!selectedProject) return
    setLoadingAction('writer_room')
    try {
      const response = await rewriteCreativeProjectParagraph(selectedProject.id, contentId, {
        paragraph_index: paragraphIndex,
        instruction,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
      })
      if (response?.data?.anchor_not_found) {
        message.warning('没有找到这个段落锚点，请重新选择段落')
      } else {
        message.success('已生成段落重写候选版本')
      }
      await Promise.all([loadContents(selectedProject.id), loadGenerationLogs(selectedProject.id)])
    } catch (error: any) {
      message.error(error?.message || '段落重写失败')
    } finally {
      setLoadingAction(null)
    }
  }

  return {
    handleRunWriterRoomStep,
    handleRunWriterRoomBatch,
    handleRewriteParagraph,
    handlePromoteWriterRoomContent,
  }
}
