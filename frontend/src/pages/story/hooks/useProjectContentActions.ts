/**
 * 创作项目工作台的动作：handleCreate, handleRename, handleDeleteProject, handleLinkAsset。…
 *
 * 从 story/index.tsx 抽出的动作 hook（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；入参由自由变量自动推导，本批为过渡拆分，签名待收紧。
 */
import { createCreativeProject, createCreativeProjectFromNovel, deleteCreativeProject, extractCreativeProjectCharacters, linkCreativeProjectAsset, planCreativeProjectContentPackage, saveCreativeProjectContentPackage, syncCreativeProjectBible, syncCreativeProjectCharacters, updateCreativeProject, updateCreativeProjectContent } from '../../../api'
import { startProjectWorldExtraction } from '../../../api/novelSource'
import { CreativeProjectGenerateResponse, CreativeProjectResponse } from '../../../types/api'
import { ProjectContent } from '../types'
import { getNovelDisplayTitle, parseChapterRange } from '../utils'
import { message } from 'antd'

export function useProjectContentActions(deps: Record<string, any>) {
  const {
    characterExtractionResult,
    contentPackageContent,
    contentPackageData,
    contentPackageForm,
    form,
    handleInlineGenerateImage,
    idea,
    isContentPackageProject,
    loadContents,
    loadProjectAssets,
    loadProjects,
    refreshSelected,
    renameForm,
    searchParams,
    selectedLlm,
    selectedModel,
    selectedNovelAsset,
    selectedProject,
    setCharacterExtractionLoading,
    setCharacterExtractionOpen,
    setCharacterExtractionResult,
    setContentPackageBatchRunning,
    setContentPackageOpen,
    setContents,
    setCreateOpen,
    setGenerationLogs,
    setLoadingAction,
    setPendingContentPackageProjectId,
    setProjectAssets,
    setProjects,
    setRenameOpen,
    setSavingContentId,
    setSelectedId,
    setSelectedProject,
    setWriterRoomContents,
  } = deps

  async function handleCreate(values: any) {
    setLoadingAction('create')
    try {
      let response: CreativeProjectResponse
      if (values.source_type === 'novel') {
        const chapterIndices = [
          ...(Array.isArray(values.chapter_indices) ? values.chapter_indices : []),
          ...parseChapterRange(values.chapter_range || ''),
        ].filter((value, index, array) => Number.isFinite(value) && value > 0 && array.indexOf(value) === index)
        response = (await createCreativeProjectFromNovel({
          asset_id: values.novel_asset_id,
          chapter_indices: chapterIndices,
          title: values.title || getNovelDisplayTitle(selectedNovelAsset),
          project_type: values.project_type,
          production_profile: values.production_profile,
        })) as CreativeProjectResponse
      } else {
        response = (await createCreativeProject({
          title: values.title,
          idea: values.idea,
          project_type: values.project_type,
           production_profile: values.production_profile,
           source_type: 'original_idea',
           character_id: searchParams.get('character_id') || undefined,
           metadata: values.creation_brief ? { creation_brief: values.creation_brief } : undefined,
        })) as CreativeProjectResponse
      }
      message.success('项目已创建')
      setCreateOpen(false)
      form.resetFields()
      if (response.data.production_profile?.production_family === 'content_package') {
        setPendingContentPackageProjectId(response.data.id)
      }
      await loadProjects(response.data.id)
    } catch (error: any) {
      message.error(error?.message || '创建失败')
    } finally {
      setLoadingAction(null)
    }
  }
  function openRenameModal() {
    if (!selectedProject) {
      message.warning('请先选择项目')
      return
    }
    renameForm.setFieldsValue({ title: selectedProject.title || '' })
    setRenameOpen(true)
  }
  async function handleRename(values: { title: string }) {
    if (!selectedProject) return
    const nextTitle = (values.title || '').trim()
    if (!nextTitle) {
      message.error('项目名不能为空')
      return
    }
    if (nextTitle === selectedProject.title) {
      setRenameOpen(false)
      return
    }
    setLoadingAction('rename')
    try {
      const response = (await updateCreativeProject(selectedProject.id, { title: nextTitle })) as CreativeProjectResponse
      setSelectedProject(response.data)
      // 同步刷新项目列表中的标题
      setProjects((prev) => prev.map((p) => (p.id === response.data.id ? response.data : p)))
      message.success('项目已重命名')
      setRenameOpen(false)
    } catch (error: any) {
      message.error(error?.message || '重命名失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleDeleteProject() {
    if (!selectedProject) return
    const deletingId = selectedProject.id
    setLoadingAction('delete_project')
    try {
      await deleteCreativeProject(deletingId)
      message.success('项目已删除，角色库和素材库资产已保留')
      setSelectedId('')
      setSelectedProject(null)
      setContents([])
      setWriterRoomContents([])
      setProjectAssets([])
      setGenerationLogs([])
      await loadProjects()
    } catch (error: any) {
      message.error(error?.message || '删除项目失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleLinkAsset(assetId: string, role: string, metadata?: Record<string, any>) {
    if (!selectedProject || !assetId.trim()) return
    setLoadingAction('asset')
    try {
      await linkCreativeProjectAsset(selectedProject.id, {
        asset_id: assetId.trim(),
        role,
        relation: role === 'output' ? 'derived_from' : 'references',
        metadata: metadata || {},
      })
      message.success('素材已关联到项目')
      await loadProjectAssets(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '关联素材失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleSaveContent(
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) {
    if (!selectedProject) return
    setSavingContentId(contentId)
    try {
      await updateCreativeProjectContent(selectedProject.id, contentId, patch)
      message.success('内容已保存')
      await loadContents(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '保存失败')
    } finally {
      setSavingContentId(null)
    }
  }
  function openContentPackageEditor() {
    if (!selectedProject || !isContentPackageProject) return
    const existing = contentPackageData || {}
    contentPackageForm.setFieldsValue({
      title: existing.title || selectedProject.title,
      topic: existing.topic || idea || selectedProject.title,
      brief: existing.brief || String(selectedProject.metadata?.creation_brief || ''),
      items: Array.isArray(existing.items) && existing.items.length
        ? existing.items
        : [{ title: '', text: '', fact: '', source: '', source_url: '', image_prompt: '' }],
    })
    setContentPackageOpen(true)
  }
  async function handleSaveContentPackage(values: any) {
    if (!selectedProject) return
    setLoadingAction('create')
    try {
      await saveCreativeProjectContentPackage(
        selectedProject.id,
        {
          package_type: selectedProject.production_profile?.package_type,
          title: values.title,
          topic: values.topic,
          brief: values.brief,
          items: (values.items || []).map((item: any, index: number) => ({
            ...item,
            id: item.id || `item-${index + 1}`,
            index: index + 1,
            status: item.status || 'draft',
          })),
        },
        contentPackageContent?.id,
      )
      message.success('内容包已保存为新版本')
      setContentPackageOpen(false)
      await loadContents(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '保存内容包失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handlePlanContentPackage() {
    if (!selectedProject || !isContentPackageProject) return
    const values = contentPackageForm.getFieldsValue()
    if (!String(values.topic || '').trim()) {
      message.warning('请先填写主题')
      return
    }
    setLoadingAction('create')
    try {
      const response: any = await planCreativeProjectContentPackage(selectedProject.id, {
        topic: String(values.topic).trim(),
        brief: String(values.brief || ''),
        item_count: Math.max(1, Math.min(Number(values.item_count || 12), 80)),
        prompt_only: Boolean(values.prompt_only),
      })
      const generated = response?.data?.data || response?.data || {}
      contentPackageForm.setFieldsValue({
        title: generated.title || values.title || selectedProject.title,
        topic: generated.topic || values.topic,
        brief: generated.brief || values.brief || '',
        items: Array.isArray(generated.items) ? generated.items : [],
      })
      await loadContents(selectedProject.id)
      message.success('内容包已生成并保存，可继续编辑')
    } catch (error: any) {
      message.error(error?.message || '生成内容包失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleGenerateContentPackageImage(index: number, fieldName: number) {
    if (!selectedProject) return
    const item = contentPackageForm.getFieldValue(['items', fieldName]) || {}
    const prompt = String(item.image_prompt || '').trim()
    if (!prompt) {
      message.warning('请先填写图片提示词')
      return
    }
    await handleInlineGenerateImage(prompt, {
      contentId: contentPackageContent?.id,
      sourceType: 'content_package',
      sourceIndex: index,
      sourceTitle: String(item.title || `内容单元 ${index + 1}`),
    }, { awaitAsync: true })
  }
  async function handleBatchGenerateContentPackageImages() {
    if (!selectedProject || !contentPackageContent) return
    const values = contentPackageForm.getFieldsValue(true)
    const items = Array.isArray(values.items) ? values.items : []
    const targets = items
      .map((item: any, index: number) => ({ item, index }))
      .filter(({ item }: any) => String(item?.image_prompt || '').trim())
    if (!targets.length) {
      message.warning('当前内容包没有可用的图片提示词')
      return
    }
    setContentPackageBatchRunning(true)
    let generated = 0
    let failed = 0
    try {
      for (const { item, index } of targets) {
        contentPackageForm.setFieldValue(['items', index, 'status'], 'generating')
        try {
          const result: any = await handleInlineGenerateImage(String(item.image_prompt).trim(), {
            contentId: contentPackageContent.id,
            sourceType: 'content_package',
            sourceIndex: index,
            sourceTitle: String(item.title || `内容单元 ${index + 1}`),
          }, { awaitAsync: true })
          contentPackageForm.setFieldValue(['items', index, 'status'], result?.assetId ? 'succeeded' : 'ready')
          if (result?.assetId) {
            contentPackageForm.setFieldValue(['items', index, 'asset_ids'], [result.assetId])
            contentPackageForm.setFieldValue(['items', index, 'image_url'], result.url || '')
          }
          generated += result?.assetId ? 1 : 0
        } catch (error: any) {
          contentPackageForm.setFieldValue(['items', index, 'status'], 'failed')
          failed += 1
          message.error(`${item.title || `第 ${index + 1} 项`}：${error?.message || '生图失败'}`)
        }
      }
      const latest = contentPackageForm.getFieldsValue(true)
      await saveCreativeProjectContentPackage(
        selectedProject.id,
        {
          package_type: selectedProject.production_profile?.package_type,
          title: latest.title,
          topic: latest.topic,
          brief: latest.brief,
          items: (latest.items || []).map((item: any, index: number) => ({
            ...item,
            id: item.id || `item-${index + 1}`,
            index: index + 1,
          })),
        },
        contentPackageContent.id,
      )
      await loadContents(selectedProject.id)
      message.success(`批量生图完成：成功 ${generated}，失败 ${failed}`)
    } finally {
      setContentPackageBatchRunning(false)
    }
  }
  async function handleSyncCharacters() {
    if (!selectedProject) return
    setLoadingAction('sync_characters')
    try {
      const response = (await syncCreativeProjectCharacters(selectedProject.id)) as CreativeProjectGenerateResponse
      message.success('大纲角色已同步到角色库')
      await refreshSelected(response.project || null)
      await loadProjectAssets(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '同步角色库失败')
    } finally {
      setLoadingAction(null)
    }
  }
  async function handleExtractCharacters(apply = false) {
    if (!selectedProject) return
    setCharacterExtractionLoading(true)
    try {
      const response: any = await extractCreativeProjectCharacters(selectedProject.id, {
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
        apply,
        cards: apply ? (characterExtractionResult?.characters || undefined) : undefined,
      })
      const result = response.data || response.result || response
      setCharacterExtractionResult(result)
      setCharacterExtractionOpen(true)
      if (apply) {
        message.success(`已写入 ${result.applied_characters?.length || 0} 个角色`)
        await refreshSelected(selectedProject)
        await loadProjectAssets(selectedProject.id)
      }
    } catch (error: any) {
      message.error(error?.message || '提取角色失败')
    } finally {
      setCharacterExtractionLoading(false)
    }
  }
  async function handleSyncProjectBible(overwrite = false) {
    if (!selectedProject) return
    setLoadingAction('project_bible')
    try {
      const response = (await syncCreativeProjectBible(selectedProject.id, { overwrite })) as { data?: ProjectContent[] }
      const count = response.data?.length || 0
      message.success(count ? `已同步 ${count} 张圣经/世界资产卡` : '圣经/世界资产已是最新，无需补齐')
      await loadContents(selectedProject.id)
      await refreshSelected(selectedProject)
    } catch (error: any) {
      message.error(error?.message || '同步项目圣经失败')
    } finally {
      setLoadingAction(null)
    }
  }
  const handleExtractWorld = async () => {
    if (!selectedProject) return
    setLoadingAction('world_extract')
    try {
      const result = await startProjectWorldExtraction(selectedProject.id, {
        model: selectedModel || undefined,
      })
      if (!result.run_id) {
        throw new Error(result.status || '提取未返回运行')
      }
      message.success(`已生成 ${result.candidate_count} 条世界设定候选，正在打开审阅`)
      window.location.href = `/novel-world?snapshot_id=${encodeURIComponent(result.snapshot_id)}&run_id=${encodeURIComponent(result.run_id)}`
    } catch (error: any) {
      message.error(error?.message || '生成世界设定候选失败')
    } finally {
      setLoadingAction(null)
    }
  }

  return {
    handleCreate,
    handleRename,
    handleDeleteProject,
    handleLinkAsset,
    handleSaveContent,
    handleSaveContentPackage,
    handlePlanContentPackage,
    handleGenerateContentPackageImage,
    handleBatchGenerateContentPackageImages,
    handleExtractCharacters,
    handleSyncCharacters,
    handleSyncProjectBible,
    handleExtractWorld,
    openRenameModal,
    openContentPackageEditor,
  }
}
