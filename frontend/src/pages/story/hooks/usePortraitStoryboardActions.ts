/**
 * 创作项目工作台的动作：handleGenerateCharacterPortrait, buildProjectCharacterPortraitPrompt, handleBatchGenerateStoryboardImages, handleUpdateStoryboardPanelReferences。…
 *
 * 从 story/index.tsx 抽出的动作 hook（拆分计划 creative-project-ui-redesign #9）。
 * 逻辑逐字未改；入参由自由变量自动推导，本批为过渡拆分，签名待收紧。
 */
import { generateCharacterPortrait, linkCreativeProjectAsset, matchCreativeProjectReferenceAssets, updateCreativeProject } from '../../../api'
import { CreativeProjectResponse, StoryOutlineCharacter } from '../../../types/api'
import { buildStoryboardPanelReferencePlan, buildStoryboardReferenceSummary, dedupeReferenceImageItems, dedupeStrings, getCharacterReferenceItems, imageContextKey, selectReferenceAssetsForPrompt } from '../utils'
import { Modal, message } from 'antd'

export function usePortraitStoryboardActions(deps: Record<string, any>) {
  const {
    activeChapterNumber,
    characterDetails,
    contentForChapter,
    contents,
    defaultImageModel,
    defaultImageSupportsReferenceImages,
    handleInlineGenerateImage,
    handleSaveContent,
    inlineImages,
    loadCharacterDetailsForIds,
    loadContents,
    loadGenerationLogs,
    loadProjectAssets,
    outline,
    projectAssets,
    refreshSelected,
    selectedLlm,
    selectedModel,
    selectedProject,
    setBatchStoryboardImageChapter,
    setLoadingAction,
    setLoadingChapterAction,
    setPortraitGeneratingCharacter,
  } = deps

  async function handleUpdateStoryboardPanelReferences(
    contentId: string,
    panelNumber: number,
    referenceAssetIds: string[],
  ) {
    const source = contents.find((item) => item.id === contentId)
    if (!source) return
    const panels = Array.isArray(source.data?.panels) ? source.data.panels : []
    const nextData = {
      ...source.data,
      panels: panels.map((panel: any) => {
        if (Number(panel.panel_number) !== Number(panelNumber)) return panel
        return { ...panel, reference_asset_ids: dedupeStrings(referenceAssetIds) }
      }),
    }
    await handleSaveContent(contentId, { data: nextData })
  }
  function buildProjectCharacterPortraitPrompt(record: StoryOutlineCharacter) {
    const parts = [
      '单人角色立绘，完整角色设定图，适合作为后续漫画/短剧分镜的一致性参考图。',
      record.name ? `角色名：${record.name}` : '',
      record.role ? `角色定位：${record.role}` : '',
      record.age_range ? `年龄范围：${record.age_range}` : '',
      record.appearance ? `外貌特征：${record.appearance}` : '',
      record.costume_hint ? `服装与配饰：${record.costume_hint}` : '',
      record.signature_items?.length ? `标志物：${record.signature_items.join('、')}` : '',
      record.expressions?.length ? `常用表情：${record.expressions.join('、')}` : '',
      record.poses?.length ? `常用姿态：${record.poses.join('、')}` : '',
      record.visual_consistency ? `一致性规则：${record.visual_consistency}` : '',
      record.personality ? `性格气质：${record.personality}` : '',
      record.image_prompt ? `既有生图提示：${record.image_prompt}` : '',
      outline.image_style_prompt ? `项目统一画风：${outline.image_style_prompt}` : '',
      '要求：正面半身或全身清晰可辨，干净背景，角色特征稳定，不添加无关人物，不遮挡脸部。',
    ]
    return parts.filter(Boolean).join('\n')
  }
  async function handleGenerateCharacterPortrait(record: StoryOutlineCharacter) {
    if (!selectedProject) return
    if (!record.character_id) {
      message.warning('请先同步角色库，再生成角色立绘')
      return
    }
    if (!defaultImageModel.name) {
      message.warning('请先在顶部选择默认生图模型')
      return
    }
    const key = record.character_id || record.name || ''
    setPortraitGeneratingCharacter(key)
    setLoadingAction('portrait_generate')
    try {
      const prompt = buildProjectCharacterPortraitPrompt(record)
      const size = defaultImageModel.default_size || '1024x1024'
      const loadedCharacters = await loadCharacterDetailsForIds([record.character_id])
      const referenceImages = dedupeReferenceImageItems(
        getCharacterReferenceItems(loadedCharacters[record.character_id] || characterDetails[record.character_id]),
      ).map((item) => item.url).filter(Boolean)
      const response = await generateCharacterPortrait(record.character_id, {
        prompt,
        provider: defaultImageModel.name,
        model: defaultImageModel.model || undefined,
        size,
        n: 1,
        reference_images: referenceImages,
      })
      const nodeId = response?.data?.node_id
      if (nodeId) {
        await linkCreativeProjectAsset(selectedProject.id, {
          asset_id: nodeId,
          role: 'character',
          relation: 'portrait',
          metadata: {
            character_id: record.character_id,
            character_name: record.name,
            prompt,
            provider: defaultImageModel.name,
            model: defaultImageModel.model || '',
            generated_from: 'creative_project_outline_character',
            generated_at: new Date().toISOString(),
          },
        })
        const nextOutline = {
          ...outline,
          characters: (outline.characters || []).map((item: StoryOutlineCharacter) => {
            const sameCharacter = item.character_id
              ? item.character_id === record.character_id
              : item.name === record.name
            if (!sameCharacter) return item
            const refs = Array.from(new Set([...(item.reference_asset_ids || []), nodeId]))
            return { ...item, portrait_asset_id: nodeId, reference_asset_ids: refs }
          }),
        }
        const projectResponse = (await updateCreativeProject(selectedProject.id, { outline: nextOutline })) as CreativeProjectResponse
        await refreshSelected(projectResponse.data || selectedProject)
        await loadProjectAssets(selectedProject.id)
      } else {
        await refreshSelected(selectedProject)
      }
      message.success(nodeId ? '角色立绘已生成并关联到项目参考卡' : '角色立绘已生成')
    } catch (error: any) {
      message.error(error?.message || '生成角色立绘失败')
    } finally {
      setPortraitGeneratingCharacter(null)
      setLoadingAction(null)
    }
  }
  async function handleMatchReferenceAssets(contentId: string) {
    if (!selectedProject) return
    const source = contents.find((item) => item.id === contentId)
    const chapterNumber = source?.chapter_number || source?.episode_number || activeChapterNumber
    setLoadingAction('reference_match')
    setLoadingChapterAction({ action: null, chapterNumber })
    try {
      await matchCreativeProjectReferenceAssets(selectedProject.id, {
        content_id: contentId,
        provider: selectedLlm || undefined,
        model: selectedModel || undefined,
      })
      message.success('参考卡已匹配并写回')
      await loadContents(selectedProject.id)
      await loadGenerationLogs(selectedProject.id)
    } catch (error: any) {
      message.error(error?.message || '参考卡匹配失败')
      await loadGenerationLogs(selectedProject.id)
    } finally {
      setLoadingAction(null)
      setLoadingChapterAction({ action: null, chapterNumber: null })
    }
  }
  async function handleBatchGenerateStoryboardImages(chapterNumber: number) {
    const storyboard = contentForChapter('storyboard', chapterNumber)
    if (!storyboard) {
      message.warning('请先生成这一章的分镜')
      return
    }
    if (!defaultImageModel.name) {
      message.warning('请先在顶部选择默认生图模型')
      return
    }

    const panels = (storyboard.data?.panels || []).filter((panel: any) => panel?.image_prompt)
    if (!panels.length) {
      message.warning('当前分镜没有可用的生图提示词')
      return
    }
    const pendingPanels = panels.filter((panel: any) => {
      const key = imageContextKey({
        contentId: storyboard.id,
        sourceType: 'storyboard_panel',
        sourceIndex: panel.panel_number,
        chapterNumber,
      })
      return !inlineImages[key]
    })
    if (!pendingPanels.length) {
      message.success('本话分镜图都已经生成过了')
      return
    }
    const plannedCharacterIds = dedupeStrings(
      panels.flatMap((panel: any) => [
        ...(panel.character_ids || []),
        ...selectReferenceAssetsForPrompt(
          projectAssets,
          [panel.image_prompt, panel.action, panel.location].filter(Boolean).join('\n'),
          4,
        ).map(
          (asset) => asset.metadata?.character_id,
        ),
      ]),
    )
    const loadedCharacters = await loadCharacterDetailsForIds(plannedCharacterIds)
    const referencePlans = panels.map((panel: any) =>
      buildStoryboardPanelReferencePlan({
        panel,
        projectAssets,
        characterDetails: loadedCharacters,
        supportsReferenceImages: defaultImageSupportsReferenceImages,
      }),
    )
    const referenceSummary = buildStoryboardReferenceSummary(referencePlans, 0, defaultImageSupportsReferenceImages)
    if (referenceSummary.missingEffectivePlanPanels) {
      message.warning(`有 ${referenceSummary.missingEffectivePlanPanels} 个分镜没有角色/参考卡规划，可先点“匹配参考卡”提升一致性`)
    }
    if (referenceSummary.noUsableReferencePanels) {
      message.warning(`有 ${referenceSummary.noUsableReferencePanels} 个分镜暂时没有可发送参考图，可先补角色基准图或项目参考卡`)
    }
    if (referenceSummary.unresolvedCharacterIds.length) {
      message.warning(`有 ${referenceSummary.unresolvedCharacterIds.length} 个角色资料未加载成功，本次会继续生成但参考图可能不完整`)
    }
    if (!defaultImageSupportsReferenceImages) {
      message.info('当前默认生图模型未声明支持参考图，本次会保留参考卡 lineage，但不会上传参考图图片')
    } else if (referenceSummary.sentReferenceImages) {
      message.info(`本次批量生成最多会随分镜发送 ${referenceSummary.sentReferenceImages} 张参考图`)
    }

    const confirmed = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '确认批量生图',
        content: `将使用「${defaultImageModel.name}」提交 ${pendingPanels.length} 个分镜任务，最多携带 ${referenceSummary.sentReferenceImages} 张参考图。${defaultImageSupportsReferenceImages ? '' : '当前模型不会上传参考图。'}`,
        okText: '开始生成',
        cancelText: '返回检查',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!confirmed) return

    setBatchStoryboardImageChapter(chapterNumber)
    try {
      let generated = 0
      for (const panel of panels) {
        const key = imageContextKey({
          contentId: storyboard.id,
          sourceType: 'storyboard_panel',
          sourceIndex: panel.panel_number,
          chapterNumber,
        })
        if (inlineImages[key]) continue
        const completed = await handleInlineGenerateImage(panel.image_prompt, {
          contentId: storyboard.id,
          sourceType: 'storyboard_panel',
          sourceIndex: panel.panel_number,
          sourceTitle: panel.action || `分镜 ${panel.panel_number}`,
          chapterNumber,
          referenceAssetIds: panel.reference_asset_ids || [],
          characterIds: panel.character_ids || [],
          portraitNodeIds: panel.portrait_node_ids || [],
          portraitVersionIds: panel.portrait_version_ids || [],
        }, { awaitAsync: true })
        if (completed) generated += 1
      }
      message.success(generated ? `已批量生成 ${generated} 张分镜图` : '本话分镜图都已经生成过了')
    } finally {
      setBatchStoryboardImageChapter(null)
    }
  }

  return {
    handleGenerateCharacterPortrait,
    buildProjectCharacterPortraitPrompt,
    handleBatchGenerateStoryboardImages,
    handleUpdateStoryboardPanelReferences,
    handleMatchReferenceAssets,
  }
}
