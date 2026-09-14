/**
 * 创作项目工作台：utils.ts。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { getAsset } from '../../api'
import { CanvasNode, CanvasNodeType } from '../../components/canvas/types'
import { ChapterPlan, ChapterPlanItem, CreativeProject, StoryOutline, StoryOutlineCharacter } from '../../types/api'
import { AssetSummary, CharacterReferenceSummary, ImagePromptContext, PipelineResult, PipelineResultItem, PipelineStageValue, ProjectAssetLink, ProjectContent, ProjectGenerationLog, ProjectGraphEdge, ProjectGraphNode, ProjectGraphNodeType, ProjectGraphState, ProseDiffRow, ReferenceImageItem, StoryboardPanelReferencePlan, StoryboardReferenceSummary, WriterRoomQualitySummary, WriterRoomReviewIssue } from './types'
import { message } from 'antd'
import React from 'react'

export const STORY_WORKSPACE_CONTENT_TYPES = [
  'chapter_outline',
  'novel_body',
  'comic_pages',
  'script',
  'storyboard',
  'content_package',
  'project_bible',
  'world_asset',
]

export function canvasTypeForGraphNode(node: ProjectGraphNode): CanvasNodeType {
  if (node.type === 'prompt') return 'prompt'
  if (node.type === 'asset' || node.type === 'character') return 'asset'
  if (node.type === 'content' || node.type === 'scene' || node.type === 'chapter' || node.type === 'outline') return 'content'
  return 'text'
}

export function graphNodeToCanvasNode(node: ProjectGraphNode, project?: CreativeProject | null): CanvasNode {
  const source = node.source || {}
  const data = node.data || {}
  const type = canvasTypeForGraphNode(node)
  const prompt = source.prompt || data.image_prompt || data.prompt || ''
  const content = data.summary || data.content || data.text || node.subtitle || node.label
  const assetId = source.assetId || data.asset_id || data.assetId || data.portrait_node_id || ''
  const metadata: Record<string, unknown> = {
    projectId: project?.id || data.project_id || '',
    projectTitle: project?.title || '',
    contentId: source.contentId || '',
    sourceType: source.sourceType || node.type,
    sourceIndex: source.sourceIndex,
    chapterNumber: source.chapterNumber,
    graphNodeId: node.id,
    graphNodeType: node.type,
    graphNodeLabel: node.label,
    rawSource: source,
    rawData: data,
  }

  if (type === 'prompt') metadata.prompt = prompt || content
  else if (type === 'asset') metadata.assetId = assetId
  else metadata.content = prompt || content

  if (Array.isArray(data.reference_asset_ids)) metadata.referenceAssetIds = data.reference_asset_ids
  if (Array.isArray(data.character_ids)) metadata.characterIds = data.character_ids
  if (Array.isArray(data.portrait_node_ids)) metadata.portraitNodeIds = data.portrait_node_ids

  return {
    id: `node-graph-${node.id}-${Date.now()}`,
    type,
    title: node.label,
    position: { x: 180, y: 160 },
    width: type === 'prompt' ? 292 : type === 'asset' ? 248 : 276,
    height: type === 'prompt' ? 152 : 140,
    metadata,
  }
}

export const projectTypeOptions = [
  { label: '短剧', value: 'short_drama' },
  { label: '小说', value: 'novel' },
  { label: '漫画', value: 'manga' },
  { label: '混合项目', value: 'mixed' },
]

export const productionProfileOptions = [
  { value: 'vertical_drama', label: '竖屏短剧', description: '创意 → 分集节拍 → 脚本 → 分镜 → 视频，不要求正文。', projectType: 'short_drama', family: 'narrative' },
  { value: 'storybook', label: '故事漫画 / 童话绘本', description: '主题 → 页面 / 图片提示词 → 批量生图，不需要正文或世界观。', projectType: 'manga', family: 'content_package' },
  { value: 'knowledge_content', label: '科普内容', description: '主题 → 知识卡 / 图片提示词 → 批量生图，不需要章节。', projectType: 'mixed', family: 'content_package' },
  { value: 'platform_note', label: '平台图文', description: '主题或素材 → 文章包 → 平台适配，不需要完整故事线。', projectType: 'mixed', family: 'content_package' },
  { value: 'novel_serial', label: '小说连载', description: '完整大纲、细纲、正文和连续性检查流程。', projectType: 'novel', family: 'narrative' },
  { value: 'single_shot', label: '单镜头 / 单页实验', description: '一句创意或一张素材快速试做一个镜头或画面。', projectType: 'mixed', family: 'content_package' },
]

export const stageLabels: Record<string, string> = {
  outline: '大纲',
  chapter_plan: '章节',
  chapter_outline: '细纲',
  novel_body: '正文',
  comic_pages: '漫画页',
  script: '脚本',
  storyboard: '分镜',
  assets: '素材',
  scene_simulation_candidate: '多智能体候选',
}

// Kept outside StoryPage so React Strict Mode's development-only remount does
// not probe the same stale Asset Hub link twice during one page visit.
export const unavailableProjectAssetIds = new Map<string, Set<string>>()
export const projectAssetDetailRequests = new Map<string, Promise<AssetSummary | null>>()

export function resolveProjectAssetDetail(assetId: string): Promise<AssetSummary | null> {
  const pendingOrResolved = projectAssetDetailRequests.get(assetId)
  if (pendingOrResolved) return pendingOrResolved

  const request = getAsset(assetId)
    .then((response) => response?.data || null)
    .catch(() => null)
  projectAssetDetailRequests.set(assetId, request)
  return request
}

export const statusLabels: Record<string, string> = {
  draft: '草稿',
  outlining: '大纲中',
  planning: '规划中',
  scripting: '脚本中',
  storyboarding: '分镜中',
  ready: '可整理',
  archived: '归档',
  failed: '失败',
}

export const pipelineStageOptions: { label: string; value: PipelineStageValue }[] = [
  { label: '大纲', value: 'outline' },
  { label: '同步角色', value: 'sync_characters' },
  { label: '章节规划', value: 'chapter_plan' },
  { label: '细纲', value: 'chapter_outline' },
  { label: '正文', value: 'novel_body' },
  { label: '脚本', value: 'script' },
  { label: '分镜', value: 'storyboard' },
  { label: '参考卡匹配', value: 'match_references' },
  { label: '漫画拆页', value: 'comic_pages' },
]

export const pipelineStageLabels = Object.fromEntries(pipelineStageOptions.map((item) => [item.value, item.label])) as Record<
  PipelineStageValue,
  string
>

export const writerRoomStepOptions = [
  { label: '导演场景节拍', value: 'scene_beats' },
  { label: '角色演绎', value: 'character_rehearsal' },
  { label: '正文初稿', value: 'prose_draft' },
  { label: '人味润色', value: 'prose_humanized' },
  { label: '主编审稿', value: 'prose_review' },
  { label: '定向重写', value: 'prose_rewrite' },
  { label: '去水印改写', value: 'prose_watermark_clean', optional: true },
]

export const writerRoomStepLabelMap = Object.fromEntries(writerRoomStepOptions.map((item) => [item.value, item.label]))

export const writerRoomStepDescriptions: Record<string, string> = {
  scene_beats: '拆解本章场景目标、节奏、转折和连续性。',
  character_rehearsal: '让关键角色先演一遍，暴露欲望、恐惧和可用冲突。',
  prose_draft: '把细纲和演绎结果写成可读正文初稿。',
  prose_humanized: '压低解释感，补动作、物件互动、停顿和潜台词。',
  prose_review: '主编审稿，给出 AI 味、逻辑、节奏和可执行改法。',
  prose_rewrite: '按审稿意见或选段要求生成新的候选正文。',
  prose_watermark_clean: '对正文做统计型文本水印的最大努力改写扰动（同义替换/句法重组/连接词变换），保留事实与篇幅。',
}

export const writerRoomAgentNames: Record<string, string> = {
  scene_beats: '导演',
  character_rehearsal: '演员组',
  prose_draft: '写手',
  prose_humanized: '润色师',
  prose_review: '主编',
  prose_rewrite: '改稿师',
  prose_watermark_clean: '水印清洗员',
}

export const writerRoomStepInputs: Record<string, string[]> = {
  scene_beats: ['项目大纲', '章节规划', '本章细纲', '前文上下文'],
  character_rehearsal: ['项目大纲', '本章细纲', '场景节拍'],
  prose_draft: ['本章细纲', '场景节拍', '角色演绎'],
  prose_humanized: ['正文初稿或候选正文', '用户额外要求'],
  prose_review: ['正文候选', '大纲与连续性上下文'],
  prose_rewrite: ['正文候选', '主编审稿意见', '用户选段或要求'],
  prose_watermark_clean: ['最终正文候选', '用户额外要求'],
}

export const writerRoomStepOutputs: Record<string, string[]> = {
  scene_beats: ['场景目标', '动作节拍', '转折', '尾钩'],
  character_rehearsal: ['角色目标', '隐瞒信息', '潜台词', '可写冲突'],
  prose_draft: ['完整正文初稿'],
  prose_humanized: ['更自然的正文候选'],
  prose_review: ['质量标签', 'AI味检查', '可执行重写指令'],
  prose_rewrite: ['可提升为正式正文的候选版本'],
  prose_watermark_clean: ['可提升为正式正文的扰动改写版'],
}

export const writerRoomStepNextHints: Record<string, string> = {
  scene_beats: '生成后进入“角色演绎”，让角色按自己的欲望和隐瞒信息先演一遍。',
  character_rehearsal: '生成后进入“正文初稿”，把细纲、场景节拍和角色反应合成完整正文。',
  prose_draft: '初稿不要急着提升，优先进入“人味润色”压低解释感。',
  prose_humanized: '润色后进入“主编审稿”，检查逻辑、节奏、AI腔和角色声音。',
  prose_review: '审稿后可以按单条意见重写，也可以应用全部意见生成定向重写版。',
  prose_rewrite: '确认效果后再提升为正式正文，旧正文会作为历史版本保留。',
  prose_watermark_clean: '确认扰动改写效果后再提升为正式正文；该步骤可选，默认不在批量流程里。',
}

export function parseChapterRange(value: string): number[] {
  const chapters = new Set<number>()
  String(value || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      if (part.includes('-')) {
        const [left, right] = part.split('-').map((item) => Number(item.trim()))
        if (!Number.isFinite(left) || !Number.isFinite(right)) return
        const start = Math.max(1, Math.min(left, right))
        const end = Math.max(left, right)
        for (let chapter = start; chapter <= end; chapter += 1) chapters.add(chapter)
        return
      }
      const chapter = Number(part)
      if (Number.isFinite(chapter) && chapter > 0) chapters.add(chapter)
    })
  return Array.from(chapters).sort((a, b) => a - b)
}

export function linesToList(value: string): string[] {
  return String(value || '')
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function listToLines(value: unknown): string {
  return Array.isArray(value) ? value.filter(Boolean).join('\n') : ''
}

export function isChapterLocked(item: ChapterPlanItem | Record<string, any>) {
  return Boolean((item as any).is_locked) || item.status === 'locked'
}

export function normalizeChapterItem(item: ChapterPlanItem | Record<string, any>): ChapterPlanItem {
  const chapterNumber = Number(item.chapter_number || 1)
  const locked = isChapterLocked(item)
  return {
    ...item,
    chapter_number: Number.isFinite(chapterNumber) && chapterNumber > 0 ? chapterNumber : 1,
    title: String(item.title || ''),
    goal: String(item.goal || ''),
    conflict: String(item.conflict || ''),
    key_events: Array.isArray(item.key_events) ? item.key_events.filter(Boolean).map(String) : linesToList(String(item.key_events || '')),
    character_focus: Array.isArray(item.character_focus)
      ? item.character_focus.filter(Boolean).map(String)
      : linesToList(String(item.character_focus || '')),
    ending_hook: String(item.ending_hook || ''),
    status: locked ? 'locked' : String(item.status || 'draft'),
  }
}

export function normalizeChapterPlan(plan: ChapterPlan | Record<string, any>): ChapterPlan {
  const chapters = Array.isArray(plan.chapters) ? plan.chapters.map(normalizeChapterItem) : []
  return {
    ...plan,
    chapter_count: chapters.length || Number(plan.chapter_count || 0),
    chapters,
  }
}

export function buildCreativeProjectGraph(params: {
  project?: CreativeProject | null
  contents: ProjectContent[]
  assets: ProjectAssetLink[]
  assetDetails: Record<string, AssetSummary>
  saved?: ProjectGraphState | null
}): ProjectGraphState {
  const { project, contents, assets, assetDetails, saved } = params
  const savedNodes = new Map((saved?.nodes || []).map((node) => [node.id, node]))
  const nodes: ProjectGraphNode[] = []
  const edges: ProjectGraphEdge[] = []
  const addNode = (node: ProjectGraphNode) => {
    const savedNode = savedNodes.get(node.id)
    nodes.push({
      ...node,
      x: Number(savedNode?.x ?? node.x),
      y: Number(savedNode?.y ?? node.y),
      width: savedNode?.width || node.width || 210,
      height: savedNode?.height || node.height || 92,
    })
  }
  const addEdge = (edge: ProjectGraphEdge) => {
    if (edge.from === edge.to) return
    if (edges.some((item) => item.id === edge.id)) return
    edges.push(edge)
  }

  if (!project) return { nodes: [], edges: [] }

  const outline = project.outline || {}
  const chapters = project.chapter_plan?.chapters || []
  const outlineId = 'outline:root'
  addNode({
    id: outlineId,
    type: 'outline',
    label: outline.title || project.title || '故事大纲',
    subtitle: outline.logline || outline.premise || '项目核心设定',
    status: project.current_stage,
    x: 40,
    y: 180,
    source: { tab: 'outline' },
  })

  ;(outline.characters || []).slice(0, 12).forEach((character: StoryOutlineCharacter, index: number) => {
    const id = `character:${character.character_id || character.name || index}`
    addNode({
      id,
      type: 'character',
      label: character.name || `角色 ${index + 1}`,
      subtitle: [character.role, character.goal || character.personality].filter(Boolean).join(' / '),
      status: character.character_id ? 'linked' : 'draft',
      x: 330,
      y: 40 + index * 118,
      source: { tab: 'outline', assetId: character.portrait_asset_id },
      data: character as Record<string, any>,
    })
    addEdge({ id: `${outlineId}->${id}`, from: outlineId, to: id, type: 'contains', label: 'character' })
  })

  chapters.forEach((chapter: ChapterPlanItem, index: number) => {
    const chapterNumber = Number(chapter.chapter_number || index + 1)
    const chapterId = `chapter:${chapterNumber}`
    addNode({
      id: chapterId,
      type: 'chapter',
      label: chapter.title || `第 ${chapterNumber} 章`,
      subtitle: chapter.goal || chapter.conflict || chapter.ending_hook,
      status: isChapterLocked(chapter) ? 'locked' : chapter.status || 'draft',
      x: 650,
      y: 40 + index * 132,
      source: { tab: 'episode-workbench', chapterNumber },
      data: chapter as Record<string, any>,
    })
    addEdge({ id: `${outlineId}->${chapterId}`, from: outlineId, to: chapterId, type: 'contains', label: 'chapter' })
  })

  const contentTypeOrder: Record<string, number> = {
    chapter_outline: 0,
    novel_body: 1,
    script: 2,
    storyboard: 3,
    comic_pages: 4,
    project_bible: -1,
    world_asset: -1,
  }
  const sortedContents = [...contents].sort((left, right) => {
    const leftChapter = Number(left.chapter_number || left.episode_number || 0)
    const rightChapter = Number(right.chapter_number || right.episode_number || 0)
    if (leftChapter !== rightChapter) return leftChapter - rightChapter
    return (contentTypeOrder[left.content_type] ?? 9) - (contentTypeOrder[right.content_type] ?? 9)
  })

  sortedContents.forEach((content, index) => {
    const chapterNumber = Number(content.chapter_number || content.episode_number || 0)
    const contentId = `content:${content.id}`
    const contentLabel = stageLabels[content.content_type] || content.content_type
    const column = content.content_type === 'project_bible' || content.content_type === 'world_asset' ? 1 : 4
    addNode({
      id: contentId,
      type: 'content',
      label: content.title || contentLabel,
      subtitle: chapterNumber ? `第 ${chapterNumber} 章 / ${contentLabel} v${content.version}` : `${contentLabel} v${content.version}`,
      status: content.is_locked ? 'locked' : 'ready',
      x: column === 1 ? 330 : 950,
      y: column === 1 ? 720 + index * 112 : 50 + index * 104,
      source: { tab: content.content_type === 'novel_body' || content.content_type === 'comic_pages' ? 'script' : 'episode-workbench', contentId: content.id, chapterNumber, contentType: content.content_type },
      data: content.data,
    })
    if (chapterNumber) {
      addEdge({ id: `chapter:${chapterNumber}->${contentId}`, from: `chapter:${chapterNumber}`, to: contentId, type: 'contains', label: contentLabel })
    } else {
      addEdge({ id: `${outlineId}->${contentId}`, from: outlineId, to: contentId, type: 'contains', label: contentLabel })
    }

    const panels = Array.isArray(content.data?.panels) ? content.data.panels : []
    panels.slice(0, 24).forEach((panel: any, panelIndex: number) => {
      const panelNumber = Number(panel.panel_number || panel.page_number || panelIndex + 1)
      const sceneId = `scene:${content.id}:${panelNumber}`
      addNode({
        id: sceneId,
        type: 'scene',
        label: panel.action || panel.scene || `镜头 ${panelNumber}`,
        subtitle: panel.shot_type || panel.dialogue || panel.camera || '',
        status: panel.image_url ? 'generated' : 'draft',
        x: 1250,
        y: 60 + (index * 3 + panelIndex) * 94,
        source: { tab: 'episode-workbench', contentId: content.id, chapterNumber, sourceIndex: panelNumber, sourceType: 'storyboard_panel' },
        data: panel,
      })
      addEdge({ id: `${contentId}->${sceneId}`, from: contentId, to: sceneId, type: 'contains', label: 'scene' })
      if (panel.image_prompt) {
        const promptId = `prompt:${content.id}:${panelNumber}`
        addNode({
          id: promptId,
          type: 'prompt',
          label: `生图提示 ${panelNumber}`,
          subtitle: String(panel.image_prompt).slice(0, 90),
          status: panel.reference_asset_ids?.length ? 'with_refs' : 'ready',
          x: 1540,
          y: 60 + (index * 3 + panelIndex) * 94,
          source: { tab: 'episode-workbench', contentId: content.id, chapterNumber, prompt: panel.image_prompt, sourceIndex: panelNumber, sourceType: 'storyboard_panel' },
          data: panel,
        })
        addEdge({ id: `${sceneId}->${promptId}`, from: sceneId, to: promptId, type: 'uses', label: 'prompt' })
        ;(panel.reference_asset_ids || []).forEach((assetId: string) => {
          addEdge({ id: `asset:${assetId}->${promptId}`, from: `asset:${assetId}`, to: promptId, type: 'references', label: 'ref' })
        })
      }
    })
  })

  assets.forEach((asset, index) => {
    const detail = assetDetails[asset.asset_id]
    const metadata = asset.metadata || {}
    const assetId = `asset:${asset.asset_id}`
    addNode({
      id: assetId,
      type: 'asset',
      label: detail?.title || metadata.title || asset.asset_id.slice(0, 10),
      subtitle: [asset.role, asset.relation, detail?.type].filter(Boolean).join(' / '),
      status: asset.relation || asset.role,
      x: asset.role === 'output' ? 1840 : 40,
      y: 40 + index * 112,
      source: { tab: 'assets', assetId: asset.asset_id, contentId: asset.content_id, sourceType: metadata.source_type, sourceIndex: metadata.source_index, prompt: metadata.prompt },
      data: { ...asset.metadata, asset_id: asset.asset_id, role: asset.role, relation: asset.relation },
    })
    if (asset.content_id) {
      addEdge({ id: `content:${asset.content_id}->${assetId}`, from: `content:${asset.content_id}`, to: assetId, type: asset.relation === 'references' ? 'references' : 'derived_from', label: asset.role })
    }
    if (metadata.source_type && metadata.source_index !== undefined && asset.content_id) {
      addEdge({
        id: `prompt:${asset.content_id}:${metadata.source_index}->${assetId}`,
        from: `prompt:${asset.content_id}:${metadata.source_index}`,
        to: assetId,
        type: 'derived_from',
        label: 'generated',
      })
    }
  })

  return { nodes, edges, viewport: saved?.viewport || { x: 0, y: 0, zoom: 1 }, updated_at: saved?.updated_at }
}

export function isPipelineStageValue(value?: string): value is PipelineStageValue {
  return pipelineStageOptions.some((item) => item.value === value)
}

export function getPipelineFailedRows(result: PipelineResult | null): PipelineResultItem[] {
  return (result?.results || []).filter((item) => item.status === 'failed')
}

export function getPipelineSummary(result: PipelineResult | null) {
  const rows = result?.results || []
  return {
    generated: result?.summary?.generated ?? result?.generated ?? rows.filter((item) => item.status === 'generated').length,
    skipped: result?.summary?.skipped ?? result?.skipped ?? rows.filter((item) => item.status === 'skipped').length,
    failed: result?.summary?.failed ?? result?.failed ?? rows.filter((item) => item.status === 'failed').length,
    total: result?.summary?.total ?? result?.total ?? rows.length,
  }
}

export function imageContextKey(context: ImagePromptContext = {}) {
  return [
    context.contentId || 'project',
    context.sourceType || 'prompt',
    context.sourceIndex ?? '0',
    context.chapterNumber ?? '0',
  ].join(':')
}

export function normalizeStoryboardVideoDuration(value?: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 5
  return Math.max(3, Math.min(Math.round(parsed), 6))
}

export function buildStoryboardVideoFallbackPrompt(panel: Record<string, any>) {
  const action = String(panel.action || panel.panel_goal || '人物完成当前镜头动作').trim()
  const motion = String(panel.camera_motion || panel.camera_hint || '静止').trim()
  const shotSize = String(panel.shot_size || '中景').trim()
  const angle = String(panel.camera_angle || '平视').trim()
  const location = String(panel.location || '当前场景').trim()
  const emotion = String(panel.emotion || '').trim()
  return [
    `竖屏短剧${shotSize}${angle}镜头：${action}`,
    `在${location}内以${motion}完成镜头运动`,
    emotion ? `人物情绪保持${emotion}` : '',
    '动作自然连贯，保持首帧中的角色、服装、场景和光线一致，不出现字幕或新增人物',
  ].filter(Boolean).join('；')
}

export function dedupeStrings(values: Array<unknown>) {
  const seen = new Set<string>()
  return values
    .map((value) => String(value || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false
      seen.add(value)
      return true
    })
}

export function assetFileUrl(path?: string): string {
  if (!path) return ''
  if (/^(https?:|data:|blob:|\/api\/)/i.test(path)) return path
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}`
}

export function normalizeCharacterReference(payload: any): CharacterReferenceSummary | null {
  const source = payload?.data || payload?.character || payload
  if (!source?.id) return null
  return {
    id: String(source.id),
    name: source.name || '',
    portrait_url: source.portrait_url || '',
    portrait_node_id: source.portrait_node_id || '',
    reference_asset_ids: Array.isArray(source.reference_asset_ids) ? source.reference_asset_ids : [],
    identity: source.identity && typeof source.identity === 'object' ? source.identity : {},
  }
}

export function getCharacterReferenceItems(character?: CharacterReferenceSummary): ReferenceImageItem[] {
  if (!character) return []
  const identity = character.identity || {}
  const visualProfile = (
    identity.visual_profile ||
    identity.visualProfile ||
    {}
  ) as Record<string, any>
  const identityReferenceUrl = String(visualProfile.identity_reference_url || '').trim()
  const visualReferenceUrls = [
    visualProfile.reference_image_urls,
    visualProfile.reference_images,
    visualProfile.reference_urls,
    visualProfile.main_reference_url,
  ].flatMap((value) => (Array.isArray(value) ? value : value ? [value] : []))

  const items: ReferenceImageItem[] = []
  if (identityReferenceUrl) {
    items.push({
      url: assetFileUrl(identityReferenceUrl),
      source: 'character_portrait',
      label: `${character.name || '角色'}身份基准图`,
      character_id: character.id,
      character_name: character.name,
    })
  }
  if (character.portrait_url) {
    items.push({
      url: assetFileUrl(character.portrait_url),
      source: 'character_portrait',
      label: `${character.name || '角色'}主立绘`,
      character_id: character.id,
      character_name: character.name,
    })
  }
  if (character.portrait_node_id) {
    items.push({
      url: `/api/v1/assets/${character.portrait_node_id}/thumbnail?original=true`,
      source: 'character_portrait',
      label: `${character.name || '角色'}立绘节点`,
      asset_id: character.portrait_node_id,
      character_id: character.id,
      character_name: character.name,
    })
  }
  for (const assetId of character.reference_asset_ids || []) {
    items.push({
      url: `/api/v1/assets/${assetId}/thumbnail?original=true`,
      source: 'character_reference',
      label: `${character.name || '角色'}参考素材`,
      asset_id: assetId,
      character_id: character.id,
      character_name: character.name,
    })
  }
  for (const url of visualReferenceUrls) {
    items.push({
      url: assetFileUrl(String(url)),
      source: 'character_reference',
      label: `${character.name || '角色'}视觉卡参考图`,
      character_id: character.id,
      character_name: character.name,
    })
  }

  const seen = new Set<string>()
  return items.filter((item) => {
    const url = String(item.url || '').trim()
    if (!url || seen.has(url)) return false
    seen.add(url)
    item.url = url
    return true
  })
}

export function dedupeReferenceImageItems(items: ReferenceImageItem[]): ReferenceImageItem[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const url = String(item.url || '').trim()
    if (!url || seen.has(url)) return false
    seen.add(url)
    item.url = url
    return true
  })
}

export function collectStoryboardCharacterIds(contents: ProjectContent[]): string[] {
  return dedupeStrings(
    contents
      .filter((content) => content.content_type === 'storyboard')
      .flatMap((content) => content.data?.panels || [])
      .flatMap((panel: any) => panel?.character_ids || []),
  )
}

export function selectReferenceAssetsForPrompt(projectAssets: ProjectAssetLink[], prompt: string, maxCount = 4) {
  const references = projectAssets.filter((asset) =>
    ['character', 'background', 'style', 'world', 'reference'].includes(asset.role),
  )
  if (!references.length) return []

  const promptText = String(prompt || '').toLowerCase()
  const scored = references.map((asset, index) => {
    const meta = asset.metadata || {}
    const marker = [
      meta.character_name,
      meta.name,
      meta.source_title,
      meta.label,
      asset.role,
      asset.asset_id,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    let score = 0
    if (asset.role === 'style') score += 8
    if (asset.role === 'background') score += 6
    if (asset.role === 'reference') score += 4
    if (asset.role === 'character') score += 3
    if (marker && promptText.includes(marker)) score += 20
    if (meta.character_name && promptText.includes(String(meta.character_name).toLowerCase())) score += 30
    return { asset, score, index }
  })

  return scored
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, maxCount)
    .map((item) => item.asset)
}

export function dedupeProjectAssetLinks(assets: ProjectAssetLink[]) {
  const seen = new Set<string>()
  return assets.filter((asset) => {
    if (!asset.asset_id || seen.has(asset.asset_id)) return false
    seen.add(asset.asset_id)
    return true
  })
}

export function projectAssetToReferenceItem(assetId: string, link?: ProjectAssetLink): ReferenceImageItem {
  return {
    url: `/api/v1/assets/${assetId}/thumbnail?original=true`,
    source: 'project_asset',
    label:
      link?.metadata?.label ||
      link?.metadata?.character_name ||
      link?.metadata?.source_title ||
      link?.role ||
      assetId,
    asset_id: assetId,
    role: link?.role,
    character_id: link?.metadata?.character_id,
    character_name: link?.metadata?.character_name,
  }
}

export function portraitNodeToReferenceItem(assetId: string, character?: CharacterReferenceSummary): ReferenceImageItem {
  return {
    url: `/api/v1/assets/${assetId}/thumbnail?original=true`,
    source: 'character_portrait',
    label: `${character?.name || '角色'}立绘节点`,
    asset_id: assetId,
    character_id: character?.id,
    character_name: character?.name,
  }
}

export function buildStoryboardPanelReferencePlan({
  panel,
  projectAssets,
  characterDetails,
  supportsReferenceImages,
  maxImages = 6,
}: {
  panel: any
  projectAssets: ProjectAssetLink[]
  characterDetails: Record<string, CharacterReferenceSummary>
  supportsReferenceImages: boolean
  maxImages?: number
}): StoryboardPanelReferencePlan {
  const panelReferenceAssetIds = dedupeStrings(panel?.reference_asset_ids || [])
  const panelCharacterIds = dedupeStrings(panel?.character_ids || [])
  const panelPortraitNodeIds = dedupeStrings(panel?.portrait_node_ids || [])
  const panelPortraitVersionIds = dedupeStrings(panel?.portrait_version_ids || [])
  const explicitAssetIds = new Set([...panelReferenceAssetIds, ...panelPortraitNodeIds])
  const explicitAssets = explicitAssetIds.size
    ? projectAssets.filter((asset) => explicitAssetIds.has(asset.asset_id))
    : []
  const promptAssets = selectReferenceAssetsForPrompt(
    projectAssets,
    [panel?.image_prompt, panel?.action, panel?.location].filter(Boolean).join('\n'),
    4,
  )
  const referenceAssets = dedupeProjectAssetLinks([...explicitAssets, ...promptAssets]).slice(0, 4)
  const linksByAssetId = new Map(projectAssets.map((asset) => [asset.asset_id, asset]))
  const referenceAssetIds = dedupeStrings([
    ...panelReferenceAssetIds,
    ...referenceAssets.map((asset) => asset.asset_id),
  ])
  const characterIds = dedupeStrings([
    ...panelCharacterIds,
    ...referenceAssets.map((asset) => asset.metadata?.character_id),
  ])
  const portraitNodeIds = dedupeStrings([
    ...panelPortraitNodeIds,
    ...referenceAssets
      .filter((asset) => asset.role === 'character')
      .map((asset) => asset.asset_id),
    ...referenceAssets.map((asset) => asset.metadata?.portrait_node_id),
  ])
  const portraitVersionIds = dedupeStrings([
    ...panelPortraitVersionIds,
    ...referenceAssets.map((asset) => asset.metadata?.portrait_version_id || asset.metadata?.main_portrait_version_id),
  ])
  const projectReferenceItems = referenceAssetIds.map((assetId) =>
    projectAssetToReferenceItem(assetId, linksByAssetId.get(assetId)),
  )
  const characterReferenceItems = characterIds.flatMap((characterId) =>
    getCharacterReferenceItems(characterDetails[characterId]),
  )
  const portraitNodeReferenceItems = portraitNodeIds.map((assetId) => {
    const character = characterIds
      .map((characterId) => characterDetails[characterId])
      .find((item) => item?.portrait_node_id === assetId)
    return portraitNodeToReferenceItem(assetId, character)
  })
  const imageCollection = dedupeReferenceImageItems([
    ...projectReferenceItems,
    ...characterReferenceItems,
    ...portraitNodeReferenceItems,
  ]).slice(0, maxImages)
  const unresolvedCharacterIds = characterIds.filter((id) => !characterDetails[id])
  const hasEffectivePlan = Boolean(
    referenceAssetIds.length || characterIds.length || portraitNodeIds.length || portraitVersionIds.length,
  )

  return {
    referenceAssetIds,
    characterIds,
    portraitNodeIds,
    portraitVersionIds,
    projectReferenceItems,
    characterReferenceItems,
    portraitNodeReferenceItems,
    imageCollection,
    unresolvedCharacterIds,
    sentCount: supportsReferenceImages ? imageCollection.length : 0,
    hasEffectivePlan,
  }
}

export function buildStoryboardReferenceSummary(
  plans: StoryboardPanelReferencePlan[],
  generatedPanels: number,
  supportsReferenceImages: boolean,
): StoryboardReferenceSummary {
  const uniqueReferenceUrls = dedupeStrings(plans.flatMap((plan) => plan.imageCollection.map((item) => item.url)))
  const uniqueCharacterIds = dedupeStrings(plans.flatMap((plan) => plan.characterIds))
  const unresolvedCharacterIds = dedupeStrings(plans.flatMap((plan) => plan.unresolvedCharacterIds))
  const effectivePlanPanels = plans.filter((plan) => plan.hasEffectivePlan).length
  const usableReferencePanels = plans.filter((plan) => plan.imageCollection.length).length
  const totalReferenceImages = plans.reduce((total, plan) => total + plan.imageCollection.length, 0)

  return {
    promptPanels: plans.length,
    effectivePlanPanels,
    usableReferencePanels,
    generatedPanels,
    totalReferenceImages,
    uniqueReferenceImages: uniqueReferenceUrls.length,
    sentReferenceImages: supportsReferenceImages ? totalReferenceImages : 0,
    uniqueCharacterIds,
    unresolvedCharacterIds,
    missingEffectivePlanPanels: plans.length - effectivePlanPanels,
    noUsableReferencePanels: plans.length - usableReferencePanels,
  }
}

export function getNovelDisplayTitle(asset?: AssetSummary | null): string {
  if (!asset) return ''
  const meta = asset.metadata || {}
  return String(asset.title || meta.novel_title || meta.book_title || '未命名小说')
}

export function getNovelChapterOptions(asset?: AssetSummary | null) {
  const meta = asset?.metadata || {}
  const chapters = Array.isArray(meta.chapters) ? meta.chapters : []
  const downloaded = Array.isArray(meta.downloaded_chapter_indices)
    ? new Set(meta.downloaded_chapter_indices.map((item: unknown) => Number(item)))
    : null
  return chapters
    .map((chapter: any, index: number) => {
      const chapterIndex = Number(chapter?.index ?? index + 1)
      return {
        label: `第 ${chapterIndex} 章 ${chapter?.title || ''}`.trim(),
        value: chapterIndex,
        downloaded: downloaded ? downloaded.has(chapterIndex) : true,
      }
    })
    .filter((item) => Number.isFinite(item.value) && item.value > 0 && item.downloaded)
}

export const worldAssetRoleLabels: Record<string, string> = {
  map: '地图/关系',
  rule: '规则',
  faction: '势力',
  location: '地点',
  event: '事件',
  'power-system': '能力/系统',
  economy: '资源/代价',
  style: '画风',
  worldview: '世界观',
  premise: '前提',
  conflict: '冲突',
  relationship: '关系',
  arc: '弧线',
  constraint: '约束',
}

export function sortBibleContents(items: ProjectContent[]) {
  return [...items].sort((left, right) => {
    const leftKey = String(left.data?.section_key || left.data?.asset_key || left.created_at || left.id)
    const rightKey = String(right.data?.section_key || right.data?.asset_key || right.created_at || right.id)
    return leftKey.localeCompare(rightKey, 'zh-CN')
  })
}

export const referenceRoleOptions = [
  { label: '角色参考', value: 'character' },
  { label: '背景参考', value: 'background' },
  { label: '画风参考', value: 'style' },
  { label: '世界观参考', value: 'world' },
  { label: '通用参考', value: 'reference' },
]

export const comicStyleOptions = [
  { label: '彩色', value: '彩色影视漫画，竖屏短剧分镜感，半写实人物，高对比光影，画风统一' },
  { label: '黑白漫画', value: '日式黑白漫画，高对比网点，清晰线稿，强烈明暗，分格节奏明确' },
  { label: '国漫', value: '现代国漫彩色风格，人物精致，情绪表演强，电影感构图，细腻光影' },
  { label: '电影分镜', value: '电影故事板风格，镜头语言明确，低饱和色彩，强调构图、景别和调度' },
  { label: '写实短剧', value: '写实短剧剧照风格，真实室内外光线，人物表演自然，商业剧质感' },
]

export function sortProjectContentsForReading(items: ProjectContent[]) {
  return [...items].sort((left, right) => {
    const leftChapter = Number(left.chapter_number || left.episode_number || Number.MAX_SAFE_INTEGER)
    const rightChapter = Number(right.chapter_number || right.episode_number || Number.MAX_SAFE_INTEGER)
    if (leftChapter !== rightChapter) return leftChapter - rightChapter

    const leftVersion = Number(left.version || 0)
    const rightVersion = Number(right.version || 0)
    if (leftVersion !== rightVersion) return leftVersion - rightVersion

    const leftCreated = left.created_at ? new Date(left.created_at).getTime() : 0
    const rightCreated = right.created_at ? new Date(right.created_at).getTime() : 0
    return leftCreated - rightCreated
  })
}

export function isProjectContentNewer(next: ProjectContent, current?: ProjectContent) {
  if (!current) return true
  const nextVersion = Number(next.version || 0)
  const currentVersion = Number(current.version || 0)
  if (nextVersion !== currentVersion) return nextVersion > currentVersion

  const nextUpdated = next.updated_at ? new Date(next.updated_at).getTime() : 0
  const currentUpdated = current.updated_at ? new Date(current.updated_at).getTime() : 0
  if (nextUpdated !== currentUpdated) return nextUpdated > currentUpdated

  const nextCreated = next.created_at ? new Date(next.created_at).getTime() : 0
  const currentCreated = current.created_at ? new Date(current.created_at).getTime() : 0
  return nextCreated > currentCreated
}

export function projectContentChapterKey(item: ProjectContent): number | null {
  const directValues = [item.chapter_number, item.episode_number]
  for (const value of directValues) {
    const number = Number(value)
    if (Number.isInteger(number) && number > 0) return number
  }

  // Older imports can lack a normalized chapter field. Keep their historical
  // versions out of the reader by recovering the chapter number from the title.
  const titleMatch = String(item.title || '').match(/(?:第\s*)?(\d+)\s*[章节集话]/)
  return titleMatch ? Number(titleMatch[1]) : null
}

export function latestProjectContentsByChapter(items: ProjectContent[]) {
  const grouped = new Map<number, ProjectContent>()
  items.forEach((item) => {
    const chapterNumber = projectContentChapterKey(item)
    if (!chapterNumber) return
    const current = grouped.get(chapterNumber)
    if (isProjectContentNewer(item, current)) {
      grouped.set(chapterNumber, item)
    }
  })
  return sortProjectContentsForReading(Array.from(grouped.values()))
}

export function textForNovelBody(body?: ProjectContent | null) {
  return String(body?.text_content || body?.data?.content || '')
}

export function compactNovelReaderText(text: string) {
  return String(text || '')
    .replace(/\r\n/g, '\n')
    .replace(/\n[\t ]*\n+/g, '\n')
    .trim()
}

export function buildNovelChapterMarkdown(body: ProjectContent) {
  const chapterNumber = body.chapter_number || body.episode_number || ''
  const title = body.title || `第 ${chapterNumber} 章`
  const text = textForNovelBody(body)
  return `# 第 ${chapterNumber} 章 ${title}\n\n${text}`.trim() + '\n'
}

export function projectMarkdownFilename(title: string | undefined, fallback: string) {
  const normalized = String(title || '').trim().replace(/[\\/:*?"<>|]/g, '_')
  return normalized || fallback
}

export function markdownList(items: unknown) {
  const values = Array.isArray(items) ? items : []
  return values
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .map((item) => `- ${item}`)
    .join('\n')
}

export function markdownSection(title: string, text: unknown) {
  const value = Array.isArray(text) ? markdownList(text) : String(text || '').trim()
  return value ? `## ${title}\n\n${value}` : ''
}

export function buildOutlineMarkdown(outline: StoryOutline) {
  const sections = [
    `# ${outline.title || '故事大纲'}`,
    markdownSection('一句话卖点', outline.logline),
    markdownSection('类型', outline.genre),
    markdownSection('核心前提', outline.premise),
    markdownSection('世界观', outline.worldview),
    markdownSection('主线冲突', outline.main_conflict),
    markdownSection('目标读者', outline.target_reader),
    markdownSection('卖点', outline.selling_points),
    markdownSection('叙事规则', outline.narrative_rules),
    markdownSection('主题', outline.themes),
    markdownSection('故事弧线', [
      outline.story_arc?.beginning ? `开局：${outline.story_arc.beginning}` : '',
      outline.story_arc?.middle ? `中段：${outline.story_arc.middle}` : '',
      outline.story_arc?.climax ? `高潮：${outline.story_arc.climax}` : '',
      outline.story_arc?.ending_direction ? `结局方向：${outline.story_arc.ending_direction}` : '',
    ]),
    markdownSection('叙事气质', outline.tone),
    markdownSection('视觉风格', outline.visual_style),
    markdownSection('统一生图提示', outline.image_style_prompt),
    markdownSection('制作约束', outline.production_notes),
    markdownSection('角色', (outline.characters || []).map((character) => {
      const lines = [
        `### ${character.name || '未命名角色'}`,
        character.role ? `- 定位：${character.role}` : '',
        character.personality ? `- 性格：${character.personality}` : '',
        character.background ? `- 背景：${character.background}` : '',
        character.appearance ? `- 外貌：${character.appearance}` : '',
      ].filter(Boolean)
      return lines.join('\n')
    })),
  ]
  return `${sections.filter(Boolean).join('\n\n')}\n`
}

export function buildChapterPlanMarkdown(plan: ChapterPlan) {
  const chapters = (plan.chapters || []).map((chapter) => {
    const sections = [
      `## 第 ${chapter.chapter_number || ''} 章 ${chapter.title || ''}`.trim(),
      chapter.goal ? `**目标**：${chapter.goal}` : '',
      chapter.conflict ? `**冲突**：${chapter.conflict}` : '',
      markdownSection('关键事件', chapter.key_events),
      markdownSection('焦点角色', chapter.character_focus),
      chapter.ending_hook ? `**章末钩子**：${chapter.ending_hook}` : '',
      chapter.status ? `**状态**：${chapter.status}` : '',
    ]
    return sections.filter(Boolean).join('\n\n')
  })
  return `# 章节规划\n\n${chapters.join('\n\n')}\n`
}

export function buildScriptMarkdown(script: ProjectContent) {
  const data = script.data || {}
  const scenes = Array.isArray(data.scenes) ? data.scenes : []
  const parts = [
    `# ${script.title || `第 ${script.chapter_number || script.episode_number || ''} 章脚本`}`,
    data.hook ? `**开头钩子**：${data.hook}` : '',
    ...scenes.map((scene: any) => {
      const dialogue = (scene.dialogue || [])
        .map((line: any) => `> ${line.character ? `${line.character}：` : ''}${line.line || line}`)
        .join('\n')
      return [
        `## 场景 ${scene.scene_number || ''} ${scene.location || ''}`.trim(),
        scene.action ? `**动作**：${scene.action}` : '',
        scene.camera_hint ? `**镜头**：${scene.camera_hint}` : '',
        scene.emotion ? `**情绪**：${scene.emotion}` : '',
        dialogue,
      ].filter(Boolean).join('\n\n')
    }),
    data.ending_hook ? `## 结尾钩子\n\n${data.ending_hook}` : '',
  ]
  return `${parts.filter(Boolean).join('\n\n')}\n`
}

export function buildStoryboardMarkdown(storyboard: ProjectContent) {
  const panels = Array.isArray(storyboard.data?.panels) ? storyboard.data.panels : []
  const parts = [
    `# ${storyboard.title || `第 ${storyboard.chapter_number || storyboard.episode_number || ''} 章分镜`}`,
    ...panels.map((panel: any) => [
      `## 分镜 ${panel.panel_number || ''}`.trim(),
      panel.action ? `**画面动作**：${panel.action}` : '',
      panel.dialogue ? `**对白**：${panel.dialogue}` : '',
      panel.shot_size ? `**景别**：${panel.shot_size}` : '',
      panel.camera_angle ? `**角度**：${panel.camera_angle}` : '',
      panel.camera_motion ? `**运镜**：${panel.camera_motion}` : '',
      panel.image_prompt ? `**生图提示**：${panel.image_prompt}` : '',
    ].filter(Boolean).join('\n\n')),
  ]
  return `${parts.filter(Boolean).join('\n\n')}\n`
}

export function escapePreviewHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[character] || character))
}

export function openProjectTextPreview(title: string, markdown: string) {
  const preview = window.open('', '_blank')
  if (!preview) {
    message.warning('浏览器阻止了预览窗口')
    return
  }
  preview.opener = null
  preview.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${escapePreviewHtml(title)}</title><style>body{margin:0;background:#f5f5f3;color:#1c1c1b;font-family:ui-serif,Georgia,"Noto Serif SC",serif}.page{box-sizing:border-box;max-width:860px;margin:0 auto;padding:56px 68px;background:#fff;min-height:100vh}pre{white-space:pre-wrap;word-break:break-word;font:16px/1.8 ui-serif,Georgia,"Noto Serif SC",serif;margin:0} @media print{body{background:#fff}.page{max-width:none;padding:24px}}</style></head><body><main class="page"><pre>${escapePreviewHtml(markdown)}</pre></main></body></html>`)
  preview.document.close()
  preview.focus()
}

// 实现已下沉到 `utils/download`（它是通用工具，不该只服务 Story 页面；共享组件需要它）。
// 这里保留同名 re-export，本文件原有的 3 处调用与其它导入方无需改动。
export { downloadTextFile } from '../../utils/download'

export function findWriterRoomLog(logs: ProjectGenerationLog[], content?: ProjectContent) {
  if (!content) return undefined
  // Only match by the stable candidate->log association. Historical candidates
  // without a linked log return undefined so the UI can show a clear notice
  // instead of falling back to another candidate's log by stage.
  const logId = content.data?.writer_room?.generation_log_id
  return logs.find((log) => log.content_id === content.id || (logId ? log.id === logId : false))
}

export function reviewIssuesForContent(content?: ProjectContent): WriterRoomReviewIssue[] {
  const data = content?.data || {}
  const candidates = [data.issues, data.review?.issues, data.result?.issues]
  const issues = candidates.find((item) => Array.isArray(item))
  return Array.isArray(issues) ? issues.filter(Boolean) : []
}

export function qualitySummaryForContent(content?: ProjectContent): WriterRoomQualitySummary | null {
  if (!content?.data) return null
  const issues = reviewIssuesForContent(content)
  const tags = Array.isArray(content.data.quality_tags)
    ? content.data.quality_tags
    : Array.from(new Set(issues.map((item) => item.category).filter(Boolean)))
  const checks = Array.isArray(content.data.ai_smell_checks) ? content.data.ai_smell_checks : []
  const hasScore = Number(content.data.overall_score || content.data.ai_smell_score || 0) > 0
  if (!hasScore && !tags.length && !checks.length) return null
  return {
    overallScore: Number(content.data.overall_score || 0),
    aiSmellScore: Number(content.data.ai_smell_score || 0),
    tags: tags.map(String).filter(Boolean),
    checks: checks.map(String).filter(Boolean),
  }
}

export function writerRoomPreviewText(content?: ProjectContent, maxJsonLength = 1800) {
  if (!content) return ''
  if (content.text_content?.trim()) return content.text_content.trim()

  const data = content.data || {}
  const lines: string[] = []
  const push = (label: string, value: unknown) => {
    if (Array.isArray(value)) {
      const text = value.map((item) => String(item || '').trim()).filter(Boolean).join('；')
      if (text) lines.push(`${label}：${text}`)
      return
    }
    const text = String(value || '').trim()
    if (text) lines.push(`${label}：${text}`)
  }

  push('摘要', data.summary)
  push('目标', data.objective || data.purpose)
  push('结论', data.approval_recommendation)
  push('连续性', data.continuity_notes)

  if (Array.isArray(data.scene_beats)) {
    data.scene_beats.slice(0, 6).forEach((scene: Record<string, any>, index: number) => {
      const title = scene.title || `场景 ${scene.scene_number || index + 1}`
      const core = [scene.purpose, scene.location, scene.dramatic_question].filter(Boolean).join(' · ')
      lines.push(`${index + 1}. ${title}${core ? `：${core}` : ''}`)
      push('动作节拍', scene.action_beats)
      push('转折', scene.turning_point)
      push('尾钩', scene.hook)
    })
  }

  if (Array.isArray(data.scene_rehearsals)) {
    data.scene_rehearsals.slice(0, 6).forEach((scene: Record<string, any>, index: number) => {
      lines.push(`${index + 1}. 场景 ${scene.scene_number || index + 1}：${scene.conflict || scene.summary || '角色冲突'}`)
      push('可写瞬间', scene.usable_moments)
    })
  }

  if (Array.isArray(data.character_reactions)) {
    data.character_reactions.slice(0, 8).forEach((item: Record<string, any>) => {
      const goal = item.private_goal || item.public_goal || item.likely_action || ''
      lines.push(`${item.character || '角色'}：${goal}`)
      push('潜台词', item.subtext)
      push('可能台词', item.likely_dialogue)
    })
  }

  push('可用冲突', data.usable_conflicts)
  push('质量标签', data.quality_tags)
  push('重写计划', data.rewrite_plan)
  if (lines.length) return lines.filter(Boolean).join('\n')

  const jsonText = JSON.stringify(data, null, 2)
  return jsonText.length > maxJsonLength ? `${jsonText.slice(0, maxJsonLength)}\n...` : jsonText
}

export function writerRoomContentWordCount(content?: ProjectContent) {
  if (!content) return 0
  const explicit = Number(content.data?.word_count || content.data?.characters || 0)
  if (Number.isFinite(explicit) && explicit > 0) return Math.round(explicit)
  return String(content.text_content || '').replace(/\s/g, '').length
}

export function splitWriterRoomParagraphs(text: string) {
  const normalized = String(text || '').replace(/\r\n/g, '\n').trim()
  if (!normalized) return []
  const byBlankLine = normalized
    .split(/\n\s*\n+/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (byBlankLine.length > 1) return byBlankLine
  return normalized
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function buildProseDiffRows(approvedText: string, candidateText: string): ProseDiffRow[] {
  const approved = splitWriterRoomParagraphs(approvedText)
  const candidate = splitWriterRoomParagraphs(candidateText)
  const scores = Array.from({ length: approved.length + 1 }, () => Array(candidate.length + 1).fill(0) as number[])

  for (let approvedIndex = approved.length - 1; approvedIndex >= 0; approvedIndex -= 1) {
    for (let candidateIndex = candidate.length - 1; candidateIndex >= 0; candidateIndex -= 1) {
      scores[approvedIndex][candidateIndex] = approved[approvedIndex] === candidate[candidateIndex]
        ? scores[approvedIndex + 1][candidateIndex + 1] + 1
        : Math.max(scores[approvedIndex + 1][candidateIndex], scores[approvedIndex][candidateIndex + 1])
    }
  }

  const raw: Array<{ kind: 'same' | 'added' | 'removed'; text: string }> = []
  let approvedIndex = 0
  let candidateIndex = 0
  while (approvedIndex < approved.length && candidateIndex < candidate.length) {
    if (approved[approvedIndex] === candidate[candidateIndex]) {
      raw.push({ kind: 'same', text: approved[approvedIndex] })
      approvedIndex += 1
      candidateIndex += 1
    } else if (scores[approvedIndex + 1][candidateIndex] >= scores[approvedIndex][candidateIndex + 1]) {
      raw.push({ kind: 'removed', text: approved[approvedIndex] })
      approvedIndex += 1
    } else {
      raw.push({ kind: 'added', text: candidate[candidateIndex] })
      candidateIndex += 1
    }
  }
  while (approvedIndex < approved.length) raw.push({ kind: 'removed', text: approved[approvedIndex++] })
  while (candidateIndex < candidate.length) raw.push({ kind: 'added', text: candidate[candidateIndex++] })

  const rows: ProseDiffRow[] = []
  for (let index = 0; index < raw.length; index += 1) {
    const current = raw[index]
    if (current.kind === 'same') continue
    const next = raw[index + 1]
    if (current.kind === 'removed' && next?.kind === 'added') {
      rows.push({ kind: 'changed', approved: current.text, candidate: next.text })
      index += 1
      continue
    }
    rows.push(current.kind === 'removed'
      ? { kind: 'removed', approved: current.text }
      : { kind: 'added', candidate: current.text })
  }
  return rows
}

export function writerRoomStepStatusColor(content?: ProjectContent, log?: ProjectGenerationLog) {
  const status = String(log?.status || '').toLowerCase()
  if (status.includes('fail') || status.includes('error')) return 'red'
  if (content) return 'green'
  if (log) return 'orange'
  return 'default'
}

export function writerRoomIssueSeverityColor(severity?: string) {
  const value = (severity || '').toLowerCase()
  if (['high', '严重', '高'].some((item) => value.includes(item))) return 'red'
  if (['medium', '中'].some((item) => value.includes(item))) return 'orange'
  if (['low', '轻', '低'].some((item) => value.includes(item))) return 'blue'
  return 'default'
}

export function contextLayerLabel(label: string) {
  return ({ locked_canon: '锁定设定', narrative_state: '叙事状态', active_foreshadowing: '已确认伏笔', chapter_contract: '章节契约', local_continuity: '前文连续性', semantic_recall: '语义召回', style_genre_skills: '文风与技能' } as Record<string, string>)[label] || label
}

export function foreshadowingLabel(status: string) {
  return ({ pending_review: '待确认', active: '进行中', advanced: '已推进', resolved: '已回收', overdue: '已逾期', ignored: '已忽略', superseded: '已替换' } as Record<string, string>)[status] || status
}

export function foreshadowingColor(status: string) {
  return ({ pending_review: 'default', active: 'blue', advanced: 'cyan', resolved: 'green', overdue: 'orange', ignored: 'default', superseded: 'default' } as Record<string, string>)[status]
}

export function timingLabel(timing: string) {
  return ({ upcoming: '待推进', in_window: '回收窗口', overdue: '超过窗口', unscheduled: '未设窗口' } as Record<string, string>)[timing] || timing
}

export function graphNodeTypeLabel(type: string) {
  return ({ character: '角色', location: '地点', organization: '组织', item: '物件', event: '事件', world_rule: '规则', chapter: '章节', foreshadowing: '伏笔' } as Record<string, string>)[type] || type
}

export function narrativeGraphNodeColor(type: string) {
  return ({ character: 'blue', location: 'cyan', organization: 'purple', item: 'gold', event: 'green', world_rule: 'geekblue', chapter: 'default', foreshadowing: 'orange' } as Record<string, string>)[type] || 'default'
}

export function graphNodeLabel(type: ProjectGraphNodeType) {
  const labels: Record<ProjectGraphNodeType, string> = {
    outline: '大纲',
    chapter: '章节',
    character: '角色',
    content: '内容',
    scene: '场景',
    prompt: 'Prompt',
    asset: '素材',
  }
  return labels[type] || type
}

export function graphNodeColor(type: ProjectGraphNodeType) {
  const colors: Record<ProjectGraphNodeType, string> = {
    outline: 'blue',
    chapter: 'geekblue',
    character: 'cyan',
    content: 'purple',
    scene: 'orange',
    prompt: 'magenta',
    asset: 'green',
  }
  return colors[type] || 'default'
}

export function graphEdgeColor(type: ProjectGraphEdge['type']) {
  const colors: Record<ProjectGraphEdge['type'], string> = {
    contains: 'var(--textTertiary)',
    uses: '#7c3aed',
    references: '#0891b2',
    derived_from: '#16a34a',
  }
  return colors[type] || 'var(--textTertiary)'
}

export function projectTypeLabel(value: string) {
  return projectTypeOptions.find((item) => item.value === value)?.label || value
}

