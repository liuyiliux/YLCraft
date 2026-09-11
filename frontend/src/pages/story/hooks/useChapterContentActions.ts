/**
 * 创作项目工作台的动作：handleGenerateOutline, handleSaveOutline, handleSaveChapterPlan, handleGenerateChapterPlan。…
 *
 * 从 story/index.tsx 抽出的动作 hook（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；入参由自由变量自动推导，本批为过渡拆分，签名待收紧。
 */
import { generateCreativeProjectChapterOutline, generateCreativeProjectChapterPlan, generateCreativeProjectNovelBody, generateCreativeProjectOutline, generateCreativeProjectScript, generateCreativeProjectStoryboard, refineCreativeProjectNovelBody, regenerateCreativeProjectChapterOutlineScenes, splitCreativeProjectComicPages, updateCreativeProject } from '../../../api'
import { ChapterPlan, CreativeProjectGenerateResponse, CreativeProjectResponse, StoryOutline } from '../../../types/api'
import { normalizeChapterPlan } from '../utils'
import { message } from 'antd'

export function useChapterContentActions(deps: Record<string, any>) {
  const {
    chapterCount,
    comicPageCount,
    comicStyle,
    contentForChapter,
    contents,
    ensureWritingPreflight,
    idea,
    loadContents,
    loadGenerationLogs,
    outline,
    refreshSelected,
    selectedLlm,
    selectedModel,
    selectedProject,
    selectedPromptTemplates,
    setLoadingAction,
    setLoadingChapterAction,
    setProjects,
    setSelectedProject,
  } = deps

  async function handleGenerateOutline() {
    if (!selectedProject) return
    setLoadingAction('outline')
    try {
      const response = (await generateCreativeProjectOutline(selectedProject.id, {
        idea,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.outline || undefined,
      })) as CreativeProjectGenerateResponse
      message.success('故事大纲已生成')
      await refreshSelected(response.project || null)
    } catch (error: any) {
      message.error(error?.message || '故事大纲生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleSaveOutline(nextOutline: StoryOutline) {
    if (!selectedProject) return
    setLoadingAction('outline_save')
    try {
      const response = (await updateCreativeProject(selectedProject.id, { outline: nextOutline })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
      message.success('故事大纲已保存')
    } catch (error: any) {
      message.error(error?.message || '保存故事大纲失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleSaveChapterPlan(nextChapterPlan: ChapterPlan) {
    if (!selectedProject) return
    setLoadingAction('chapter_plan_save')
    try {
      const response = (await updateCreativeProject(selectedProject.id, {
        chapter_plan: normalizeChapterPlan(nextChapterPlan),
      })) as CreativeProjectResponse
      if (response.data) {
        setSelectedProject(response.data)
        setProjects((prev) => prev.map((item) => (item.id === response.data.id ? response.data : item)))
      }
      message.success('章节规划已保存')
    } catch (error: any) {
      message.error(error?.message || '保存章节规划失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleGenerateChapterPlan(options: { preserveLocked?: boolean } = {}) {
    if (!selectedProject) return
    setLoadingAction('chapter_plan')
    try {
      const response = (await generateCreativeProjectChapterPlan(selectedProject.id, {
        chapter_count: chapterCount,
        append_existing: Boolean(options.preserveLocked),
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_plan || undefined,
      })) as CreativeProjectGenerateResponse
      await refreshSelected(response.project || null)
      if (options.preserveLocked) {
        const appended = Array.isArray(response.data?.appended_chapter_numbers)
          ? response.data.appended_chapter_numbers.length
          : 0
        message.success(appended ? `已保留现有规划，并续写 ${appended} 章` : '现有章节规划已保留，无需补充')
      } else {
        message.success('章节规划已生成')
      }
    } catch (error: any) {
      message.error(error?.message || '章节规划生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleGenerateChapterOutline(chapterNumber: number) {
    if (!selectedProject) return
    if (!(await ensureWritingPreflight(chapterNumber, 'chapter_outline'))) return
    setLoadingAction('chapter_outline')
    setLoadingChapterAction({ action: 'chapter_outline', chapterNumber })
    try {
      await generateCreativeProjectChapterOutline(selectedProject.id, {
        chapter_number: chapterNumber,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_outline || undefined,
      })
      message.success(`第 ${chapterNumber} 章细纲已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '细纲生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleRegenerateChapterOutlineScenes(chapterNumber: number) {
    if (!selectedProject) return
    const chapterOutline = contentForChapter('chapter_outline', chapterNumber)
    if (!chapterOutline) {
      message.warning('请先生成这一话的细纲')
      return
    }
    setLoadingAction('chapter_outline_scenes')
    setLoadingChapterAction({ action: 'chapter_outline_scenes', chapterNumber })
    try {
      await regenerateCreativeProjectChapterOutlineScenes(selectedProject.id, {
        content_id: chapterOutline.id,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.chapter_outline || undefined,
      })
      message.success(`第 ${chapterNumber} 话场景已重生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '场景重生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleGenerateNovelBody(chapterNumber: number) {
    if (!selectedProject) return
    if (!contentForChapter('chapter_outline', chapterNumber)) {
      message.warning('请先生成这一章的细纲')
      return
    }
    if (!(await ensureWritingPreflight(chapterNumber, 'novel_body'))) return
    setLoadingAction('novel_body')
    setLoadingChapterAction({ action: 'novel_body', chapterNumber })
    try {
      await generateCreativeProjectNovelBody(selectedProject.id, {
        chapter_number: chapterNumber,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.novel_body || undefined,
      })
      message.success(`第 ${chapterNumber} 章正文已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '正文生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleRefineNovelBody(chapterNumber: number, instruction: string) {
    if (!selectedProject) return
    const novelBody = contentForChapter('novel_body', chapterNumber)
    if (!novelBody) {
      message.warning('请先生成这一话的正文')
      return
    }
    if (!instruction.trim()) {
      message.warning('请填写正文修改要求')
      return
    }
    if (!(await ensureWritingPreflight(chapterNumber, 'novel_body_refine', novelBody.id))) return
    setLoadingAction('novel_body_refine')
    setLoadingChapterAction({ action: 'novel_body_refine', chapterNumber })
    try {
      await refineCreativeProjectNovelBody(selectedProject.id, {
        content_id: novelBody.id,
        instruction: instruction.trim(),
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.novel_body || undefined,
      })
      message.success(`第 ${chapterNumber} 话正文已按要求微调`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '正文微调失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleSplitComicPages(chapterNumber: number) {
    if (!selectedProject) return
    const storyboard = contentForChapter('storyboard', chapterNumber)
    if (!storyboard) {
      message.warning('请先生成这一章的分镜')
      return
    }
    setLoadingAction('comic_pages')
    setLoadingChapterAction({ action: 'comic_pages', chapterNumber })
    try {
      await splitCreativeProjectComicPages(selectedProject.id, {
        chapter_number: chapterNumber,
        content_id: storyboard.id,
        page_count: comicPageCount,
        visual_style: comicStyle || undefined,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.comic_pages || undefined,
      })
      message.success(`第 ${chapterNumber} 章漫画拆页已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '漫画拆页失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleGenerateStoryboardForChapter(chapterNumber: number) {
    const script = contentForChapter('script', chapterNumber)
    if (!script) {
      message.warning('请先生成这一章的脚本')
      return
    }
    await handleGenerateStoryboard(script.id)
  }
  async function handleGenerateScript(chapterNumber: number) {
    if (!selectedProject) return
    setLoadingAction('script')
    setLoadingChapterAction({ action: 'script', chapterNumber })
    try {
      await generateCreativeProjectScript(selectedProject.id, {
        chapter_number: chapterNumber,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.script || undefined,
      })
      message.success(`第 ${chapterNumber} 章脚本已生成`)
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '脚本生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleGenerateStoryboard(contentId: string) {
    if (!selectedProject) return
    const source = contents.find((item) => item.id === contentId)
    const chapterNumber = source?.chapter_number || source?.episode_number || null
    setLoadingAction('storyboard')
    setLoadingChapterAction({ action: 'storyboard', chapterNumber })
    try {
      await generateCreativeProjectStoryboard(selectedProject.id, {
        content_id: contentId,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        template_id: selectedPromptTemplates.storyboard || undefined,
      })
      message.success('分镜草稿已生成')
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '分镜生成失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }

  return {
    handleGenerateOutline,
    handleSaveOutline,
    handleSaveChapterPlan,
    handleGenerateChapterPlan,
    handleGenerateChapterOutline,
    handleRegenerateChapterOutlineScenes,
    handleGenerateNovelBody,
    handleRefineNovelBody,
    handleGenerateScript,
    handleGenerateStoryboard,
    handleGenerateStoryboardForChapter,
    handleSplitComicPages,
  }
}
