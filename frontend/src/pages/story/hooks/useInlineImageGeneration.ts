/**
 * 内联生图（章节正文/分镜里的就地配图）。
 *
 * 从 story/index.tsx 抽出的第三个 hook（拆分计划 creative-project-ui-redesign #9）。
 * 项目/章节/模型由外部注入，素材与角色详情复用数据层，行为不变。
 */
import { generateImage as generateImageApi, getImageTask, linkCreativeProjectAsset } from '../../../api'
import { useTaskPolling } from '../../../hooks/useTaskPolling'
import { ImagePromptContext, InlineGeneratedImage, PendingInlineImageTask, ProjectAssetLink, ReferenceImageItem } from '../types'
import { dedupeReferenceImageItems, dedupeStrings, getCharacterReferenceItems, imageContextKey, portraitNodeToReferenceItem, selectReferenceAssetsForPrompt } from '../utils'
import { message } from 'antd'
import { useCallback, useState } from 'react'
import type { CreativeProject } from '../../../types/api'
import type { CharacterReferenceSummary } from '../types'

export function useInlineImageGeneration({
  selectedProject,
  activeChapterNumber,
  defaultImageModel,
  defaultImageSupportsReferenceImages,
  characterDetails,
  projectAssets,
  loadProjectAssets,
  loadCharacterDetailsForIds,
}: {
  selectedProject: CreativeProject | null
  activeChapterNumber: number
  defaultImageModel: Record<string, any>
  defaultImageSupportsReferenceImages: boolean
  characterDetails: Record<string, CharacterReferenceSummary>
  projectAssets: ProjectAssetLink[]
  loadProjectAssets: (projectId: string) => Promise<void>
  loadCharacterDetailsForIds: (ids: string[]) => Promise<Record<string, CharacterReferenceSummary>>
}) {

  const [inlineImageLoadingKey, setInlineImageLoadingKey] = useState<string | null>(null)
  const [pendingInlineImageTask, setPendingInlineImageTask] = useState<PendingInlineImageTask | null>(null)
  const [inlineImages, setInlineImages] = useState<Record<string, InlineGeneratedImage>>({})

  const finalizeInlineImageResult = useCallback(async (data: any, task: PendingInlineImageTask) => {
    if (!data?.success) throw new Error(data?.error || '图片生成失败')

    const urls = data.urls?.length ? data.urls : data.url ? [data.url] : []
    const localPaths = data.all_local_paths?.length
      ? data.all_local_paths
      : data.local_path
        ? [data.local_path]
        : []
    const assetIds = data.all_asset_hub_node_ids?.length
      ? data.all_asset_hub_node_ids
      : data.asset_hub_node_id
        ? [data.asset_hub_node_id]
        : data.all_asset_ids?.length
          ? data.all_asset_ids
          : data.asset_id
            ? [data.asset_id]
            : []
    const assetId = assetIds[0]
    const referenceImages = task.referenceImageCollection.map((item) => item.url)

    if (assetId) {
      try {
        await linkCreativeProjectAsset(task.projectId, {
          asset_id: assetId,
          content_id: task.context.contentId || undefined,
          role: 'output',
          relation: 'derived_from',
          metadata: {
            source_type: task.context.sourceType,
            source_index: task.context.sourceIndex,
            source_title: task.context.sourceTitle,
            chapter_number: task.context.chapterNumber,
            prompt: task.prompt,
            provider: task.provider,
            model: task.model,
            size: task.size,
            reference_asset_ids: task.referenceLineage.referenceAssetIds,
            character_ids: task.referenceLineage.characterIds,
            portrait_node_ids: task.referenceLineage.portraitNodeIds,
            portrait_version_ids: task.referenceLineage.portraitVersionIds,
            reference_images: referenceImages,
            reference_images_count: referenceImages.length,
            reference_image_collection: task.referenceImageCollection,
            reference_images_sent: task.referenceImagesSent,
            reference_images_supported: task.referenceImagesSupported,
            task_id: data.task_id || '',
            generated_at: new Date().toISOString(),
          },
        })
      } catch (error: any) {
        message.warning(error?.message || '图片已生成，但回写项目素材失败')
      }
    }

    setInlineImages((prev) => ({
      ...prev,
      [task.key]: {
        assetId,
        taskId: String(data.task_id || task.taskId || ''),
        url: urls[0] || '',
        localPath: localPaths[0] || data.local_path,
        referenceImages: task.referenceImageCollection,
        referenceImagesSent: task.referenceImagesSent,
        referenceImagesSupported: task.referenceImagesSupported,
        prompt: task.prompt,
        provider: data.provider || task.provider,
        model: data.model || task.model,
        createdAt: new Date().toISOString(),
      },
    }))
    await loadProjectAssets(task.projectId)
    message.success(assetId ? '图片已生成并关联到项目素材' : '图片已生成')
    return { assetId: assetId || '', url: urls[0] || '', localPath: localPaths[0] || data.local_path || '' }
  }, [])

  useTaskPolling({
    enabled: Boolean(pendingInlineImageTask?.taskId),
    intervalMs: 5000,
    fetcher: useCallback(() => {
      if (!pendingInlineImageTask) return Promise.resolve(null as any)
      return getImageTask(pendingInlineImageTask.taskId, pendingInlineImageTask.provider)
    }, [pendingInlineImageTask]),
    isDone: useCallback((data: any) => data?.success && data?.status === 'done', []),
    isFailed: useCallback((data: any) => data?.success === false || data?.status === 'error' || data?.status === 'failed', []),
    onData: useCallback(() => undefined, []),
    onDone: useCallback(async (data: any) => {
      if (!pendingInlineImageTask) return
      try {
        await finalizeInlineImageResult(data, pendingInlineImageTask)
      } catch (error: any) {
        message.error(error?.message || '异步生图结果处理失败')
      } finally {
        setPendingInlineImageTask(null)
        setInlineImageLoadingKey(null)
      }
    }, [finalizeInlineImageResult, pendingInlineImageTask]),
    onFailed: useCallback((data: any) => {
      message.error(data?.error || '异步生图失败')
      setPendingInlineImageTask(null)
      setInlineImageLoadingKey(null)
    }, []),
    onError: useCallback(() => undefined, []),
  })

  async function waitForInlineImageTask(task: PendingInlineImageTask) {
    const maxAttempts = 120
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const data = await getImageTask(task.taskId, task.provider)
      if (data?.success && data?.status === 'done') {
        return finalizeInlineImageResult(data, task)
      }
      if (data?.success === false || data?.status === 'error' || data?.status === 'failed') {
        throw new Error(data?.error || '异步生图失败')
      }
      await new Promise((resolve) => window.setTimeout(resolve, 5000))
    }
    throw new Error('异步生图等待超时，请到任务中心查看详情')
  }

  const handleInlineGenerateImage = async (
    prompt: string,
    context: ImagePromptContext = {},
    options: { awaitAsync?: boolean } = {},
  ) => {
    const trimmedPrompt = prompt.trim()
    if (!trimmedPrompt) {
      message.warning('请先填写生图提示词')
      return
    }
    if (!selectedProject) {
      message.warning('请先选择创作项目')
      return
    }
    if (!defaultImageModel.name) {
      message.warning('请先在顶部选择默认生图模型')
      return
    }

    const chapterNumber = context.chapterNumber ?? activeChapterNumber
    const normalizedContext = { ...context, chapterNumber }
    const key = imageContextKey(normalizedContext)
    const size = defaultImageModel.default_size || '1024x1024'
    setInlineImageLoadingKey(key)
    const referenceAssets = pickReferenceAssetsForContext(trimmedPrompt, normalizedContext)
    const referenceLineage = buildReferenceLineage(normalizedContext, referenceAssets)
    const loadedCharacters = await loadCharacterDetailsForIds(referenceLineage.characterIds)
    const projectReferenceItems: ReferenceImageItem[] = referenceAssets.map((asset) => ({
      url: `/api/v1/assets/${asset.asset_id}/thumbnail?original=true`,
      source: 'project_asset',
      label:
        asset.metadata?.label ||
        asset.metadata?.character_name ||
        asset.metadata?.source_title ||
        asset.role ||
        asset.asset_id,
      asset_id: asset.asset_id,
      role: asset.role,
      character_id: asset.metadata?.character_id,
      character_name: asset.metadata?.character_name,
    }))
    const characterReferenceItems = referenceLineage.characterIds.flatMap((characterId) =>
      getCharacterReferenceItems(loadedCharacters[characterId] || characterDetails[characterId]),
    )
    const portraitNodeReferenceItems = referenceLineage.portraitNodeIds.map((assetId) => {
      const character = referenceLineage.characterIds
        .map((characterId) => loadedCharacters[characterId] || characterDetails[characterId])
        .find((item) => item?.portrait_node_id === assetId)
      return portraitNodeToReferenceItem(assetId, character)
    })
    const referenceImageCollection = dedupeReferenceImageItems([
      ...projectReferenceItems,
      ...characterReferenceItems,
      ...portraitNodeReferenceItems,
    ]).slice(0, 6)
    const referenceImages = referenceImageCollection.map((item) => item.url)
    const supportsReferenceImages = defaultImageSupportsReferenceImages
    const requestReferenceImages = supportsReferenceImages ? referenceImages : []

    let startedAsyncTask = false
    try {
      const data = await generateImageApi({
        prompt: trimmedPrompt,
        provider: defaultImageModel.name,
        size,
        n: 1,
        project_id: selectedProject.id,
        content_id: normalizedContext.contentId || undefined,
        source_type: normalizedContext.sourceType || undefined,
        source_index:
          normalizedContext.sourceIndex !== undefined ? String(normalizedContext.sourceIndex) : undefined,
        source_title: normalizedContext.sourceTitle || undefined,
        chapter_number: chapterNumber !== undefined && chapterNumber !== null ? String(chapterNumber) : undefined,
        reference_asset_ids: referenceLineage.referenceAssetIds,
        character_ids: referenceLineage.characterIds,
        portrait_node_ids: referenceLineage.portraitNodeIds,
        portrait_version_ids: referenceLineage.portraitVersionIds,
        reference_image_collection: referenceImageCollection,
        reference_images: requestReferenceImages.length ? requestReferenceImages : undefined,
      })

      if (!data?.success) {
        message.error(data?.error || '图片生成失败')
        return
      }

      if (data.status === 'pending' && data.task_id) {
        const pendingTask: PendingInlineImageTask = {
          taskId: String(data.task_id),
          projectId: selectedProject.id,
          key,
          context: normalizedContext,
          prompt: trimmedPrompt,
          size,
          provider: data.provider || defaultImageModel.name,
          model: data.model || defaultImageModel.model || '',
          referenceLineage,
          referenceImageCollection,
          referenceImagesSent: requestReferenceImages.length,
          referenceImagesSupported: supportsReferenceImages,
        }
        if (options.awaitAsync) {
          return waitForInlineImageTask(pendingTask)
        }
        startedAsyncTask = true
        setPendingInlineImageTask(pendingTask)
        message.info(`图片任务已提交，完成后自动回写项目：${data.task_id}`)
        return { taskId: String(data.task_id), pending: true }
      }
      const urls = data.urls?.length ? data.urls : data.url ? [data.url] : []
      const localPaths = data.all_local_paths?.length
        ? data.all_local_paths
        : data.local_path
          ? [data.local_path]
          : []
      const assetIds = data.all_asset_hub_node_ids?.length
        ? data.all_asset_hub_node_ids
        : data.asset_hub_node_id
          ? [data.asset_hub_node_id]
          : data.all_asset_ids?.length
            ? data.all_asset_ids
            : data.asset_id
              ? [data.asset_id]
              : []
      const assetId = assetIds[0]

      if (assetId) {
        try {
          await linkCreativeProjectAsset(selectedProject.id, {
            asset_id: assetId,
            content_id: normalizedContext.contentId || undefined,
            role: 'output',
            relation: 'derived_from',
            metadata: {
              source_type: normalizedContext.sourceType,
              source_index: normalizedContext.sourceIndex,
              source_title: normalizedContext.sourceTitle,
              chapter_number: chapterNumber,
              prompt: trimmedPrompt,
              provider: defaultImageModel.name,
              model: defaultImageModel.model || '',
              size,
              reference_asset_ids: referenceLineage.referenceAssetIds,
              character_ids: referenceLineage.characterIds,
              portrait_node_ids: referenceLineage.portraitNodeIds,
              portrait_version_ids: referenceLineage.portraitVersionIds,
              reference_images: referenceImages,
              reference_images_count: referenceImages.length,
              reference_image_collection: referenceImageCollection,
              reference_images_sent: requestReferenceImages.length,
              reference_images_supported: supportsReferenceImages,
              generated_at: new Date().toISOString(),
            },
          })
        } catch (error: any) {
          message.warning(error?.message || '图片已生成，但回写项目素材失败')
        }
      }

      setInlineImages((prev) => ({
        ...prev,
        [key]: {
          assetId,
          url: urls[0] || '',
          localPath: localPaths[0] || data.local_path,
          referenceImages: referenceImageCollection,
          referenceImagesSent: requestReferenceImages.length,
          referenceImagesSupported: supportsReferenceImages,
          prompt: trimmedPrompt,
          provider: data.provider || defaultImageModel.name,
          model: data.model || defaultImageModel.model || '',
          createdAt: new Date().toISOString(),
        },
      }))
      await loadProjectAssets(selectedProject.id)
      message.success(assetId ? '图片已生成并关联到项目素材' : '图片已生成')
      return { assetId: assetId || '', url: urls[0] || '', localPath: localPaths[0] || data.local_path || '' }
    } catch (error: any) {
      message.error(error?.message || '图片生成失败')
      return false
    } finally {
      if (!startedAsyncTask) setInlineImageLoadingKey(null)
    }
  }


  function pickReferenceAssetsForContext(prompt: string, context: ImagePromptContext = {}, maxCount = 4) {
    const explicitIds = new Set([
      ...(context.referenceAssetIds || []),
      ...(context.portraitNodeIds || []),
    ].filter(Boolean))
    const explicitAssets = explicitIds.size
      ? projectAssets.filter((asset) => explicitIds.has(asset.asset_id))
      : []
    const pickedAssets = pickReferenceAssetsForPrompt(prompt, maxCount)
    const merged = [...explicitAssets, ...pickedAssets]
    const seen = new Set<string>()
    return merged.filter((asset) => {
      if (!asset.asset_id || seen.has(asset.asset_id)) return false
      seen.add(asset.asset_id)
      return true
    }).slice(0, maxCount)
  }

  function buildReferenceLineage(context: ImagePromptContext, referenceAssets: ProjectAssetLink[]) {
    const referenceAssetIds = dedupeStrings([
      ...(context.referenceAssetIds || []),
      ...referenceAssets.map((asset) => asset.asset_id),
    ])
    const characterIds = dedupeStrings([
      ...(context.characterIds || []),
      ...referenceAssets.map((asset) => asset.metadata?.character_id),
    ])
    const portraitNodeIds = dedupeStrings([
      ...(context.portraitNodeIds || []),
      ...referenceAssets
        .filter((asset) => asset.role === 'character')
        .map((asset) => asset.asset_id),
      ...referenceAssets.map((asset) => asset.metadata?.portrait_node_id),
    ])
    const portraitVersionIds = dedupeStrings([
      ...(context.portraitVersionIds || []),
      ...referenceAssets.map((asset) => asset.metadata?.portrait_version_id || asset.metadata?.main_portrait_version_id),
    ])
    return { referenceAssetIds, characterIds, portraitNodeIds, portraitVersionIds }
  }

  function pickReferenceAssetsForPrompt(prompt: string, maxCount = 4) {
    return selectReferenceAssetsForPrompt(projectAssets, prompt, maxCount)
  }


  return {
    handleInlineGenerateImage,
    inlineImages,
    setInlineImages,
    inlineImageLoadingKey,
    setInlineImageLoadingKey,
    pendingInlineImageTask,
    setPendingInlineImageTask,
  }
}
