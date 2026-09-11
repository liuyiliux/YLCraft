/**
 * 创作项目工作台：components/bible.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { getTask } from '../../../api'
import { confirmSuggestedField, draftWorldTemplate, expandEntityAttributes, expandWorldDomain, ignoreSuggestedField, listProjectWorldDomains, listProjectWorldEntities, listProjectWorldEntityRelations, listWorldBuildingSuggestions, listWorldTemplates, previewEntityExpansion, resetProjectWorldDomain, upsertProjectWorldDomain, upsertWorldTemplate, type WorldBuildingSuggestions, type WorldBuildingTemplate, type WorldDomainExpansionTask, type WorldEntity, type WorldEntityRelation } from '../../../api/novelSource'
import ProviderModelSelect from '../../../components/ai/ProviderModelSelect'
import useLlmConnectors from '../../../hooks/useLlmConnectors'
import { worldFieldLabel, worldFieldValueText } from '../../../utils/worldFieldLabels'
import { EditorField, WorkbenchSection } from './common'
import { panelStyle } from '../styles'
import { ProjectContent } from '../types'
import { sortBibleContents, worldAssetRoleLabels } from '../utils'
import { EnvironmentOutlined, FolderAddOutlined, ReloadOutlined, RobotOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Empty, Input, Modal, Popconfirm, Progress, Select, Space, Tag, Typography, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function BibleContentCard({
  content,
  saving,
  onSaveContent,
  onSaveAsAsset,
}: {
  content: ProjectContent
  saving: boolean
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => Promise<void>
  onSaveAsAsset: (contentId: string) => void
}) {
  const [title, setTitle] = useState(content.title || '')
  const [summary, setSummary] = useState(String(content.data?.summary || ''))
  const [details, setDetails] = useState(
    typeof content.data?.details === 'string'
      ? content.data.details
      : JSON.stringify(content.data?.details || '', null, 2),
  )

  useEffect(() => {
    setTitle(content.title || '')
    setSummary(String(content.data?.summary || ''))
    setDetails(
      typeof content.data?.details === 'string'
        ? content.data.details
        : JSON.stringify(content.data?.details || '', null, 2),
    )
  }, [content.id, content.title, content.data])

  const role = String(content.data?.role || content.content_type)
  const label = worldAssetRoleLabels[role] || role
  const keyLabel = content.data?.section_key || content.data?.asset_key || content.id.slice(0, 8)

  const save = () => {
    const nextData = {
      ...(content.data || {}),
      title,
      summary,
      details,
    }
    const textContent = [`# ${title}`, `类型：${label}`, summary, details].filter(Boolean).join('\n\n')
    return onSaveContent(content.id, {
      title,
      data: nextData,
      text_content: textContent,
    })
  }

  return (
    <section style={{ ...panelStyle, minHeight: 280 }}>
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
          <Space size={6} wrap>
            <Tag color={content.is_locked ? 'green' : 'default'}>{content.is_locked ? '已锁定' : '未锁定'}</Tag>
            <Tag>{label}</Tag>
            <Text type="secondary">{String(keyLabel)}</Text>
          </Space>
          <Checkbox
            checked={Boolean(content.is_locked)}
            onChange={(event) => onSaveContent(content.id, { is_locked: event.target.checked })}
          >
            锁定
          </Checkbox>
        </Space>
        <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="卡片标题" />
        <EditorField label="摘要" hint="一句话说明这张卡对剧情、画面或连续性的作用。">
          <TextArea value={summary} onChange={(event) => setSummary(event.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} />
        </EditorField>
        <EditorField label="细节" hint="写清规则边界、视觉特征、场景用途、禁止偏离点，锁定后会进入细纲生成上下文。">
          <TextArea value={details} onChange={(event) => setDetails(event.target.value)} autoSize={{ minRows: 4, maxRows: 10 }} />
        </EditorField>
        <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
          <Button icon={<FolderAddOutlined />} onClick={() => onSaveAsAsset(content.id)}>
            存为素材
          </Button>
          <Button type="primary" loading={saving} onClick={save}>
            保存卡片
          </Button>
        </Space>
      </Space>
    </section>
  )
}

export function ProjectBibleTab({
  projectId,
  hasOutline,
  bibleContents,
  worldAssets,
  loading,
  savingContentId,
  onSync,
  onExtractWorld,
  onSaveContent,
  onSaveAsAsset,
}: {
  projectId: string
  hasOutline: boolean
  bibleContents: ProjectContent[]
  worldAssets: ProjectContent[]
  loading: boolean
  savingContentId: string | null
  onSync: (overwrite?: boolean) => void
  onExtractWorld: () => void
  onSaveContent: (
    contentId: string,
    patch: { title?: string; data?: Record<string, any>; text_content?: string; is_locked?: boolean },
  ) => Promise<void>
  onSaveAsAsset: (contentId: string) => void
}) {
  const lockedCount = [...bibleContents, ...worldAssets].filter((item) => item.is_locked).length

  // 类型化世界设定（按域展示：地点/势力/角色/经济/规则/时间线/术语表/力量体系/物种/事件/物品）
  const [worldEntities, setWorldEntities] = useState<WorldEntity[]>([])
  const [worldRelations, setWorldRelations] = useState<WorldEntityRelation[]>([])
  const [worldLoading, setWorldLoading] = useState(false)

  useEffect(() => {
    if (!projectId) {
      setWorldEntities([])
      setWorldRelations([])
      return
    }
    setWorldLoading(true)
    Promise.all([
      listProjectWorldEntities(projectId).catch(() => []),
      listProjectWorldEntityRelations(projectId).catch(() => []),
    ])
      .then(([entities, relations]) => {
        setWorldEntities(entities)
        setWorldRelations(relations)
      })
      .finally(() => setWorldLoading(false))
  }, [projectId])

  const entitiesByType = useMemo(() => {
    const map: Record<string, WorldEntity[]> = {}
    for (const entity of worldEntities) {
      const key = entity.entity_type || entity.domain || '其他'
      ;(map[key] ||= []).push(entity)
    }
    return map
  }, [worldEntities])

  useEffect(() => {
    loadSuggestions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const entityNameById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const entity of worldEntities) map[entity.id] = entity.name
    return map
  }, [worldEntities])

  const entityTypeLabels: Record<string, string> = {
    character: '角色',
    place: '地点',
    faction: '势力',
    event: '事件',
    timeline_event: '时间线',
    world_rule: '世界规则',
    power_system: '力量体系',
    economy: '经济',
    species: '物种',
    item: '物品',
    glossary: '术语表',
  }

  // AI 补充实体属性：接在既有世界设定管线上（产出候选，需到 /novel-world 确认后写入）。
  const [expandEntity, setExpandEntity] = useState<WorldEntity | null>(null)
  const [expandFields, setExpandFields] = useState<string[]>([])
  const [expandPrompt, setExpandPrompt] = useState('')
  const [expandPreview, setExpandPreview] = useState('')
  const [expandLoading, setExpandLoading] = useState(false)
  const [expandElapsed, setExpandElapsed] = useState(0)
  const [domainSpecs, setDomainSpecs] = useState<Record<string, string[]>>({})
  // 生成时就地选 AI（供应商/模型）：与生成后的优化同一套连接器，默认取首个可用项。
  const {
    backends: llmBackends,
    provider: expandProvider,
    model: expandModel,
    setProvider: setExpandProvider,
    setModel: setExpandModel,
  } = useLlmConnectors()

  const attributesFor = (entity: WorldEntity): string[] => {
    const contract = domainSpecs[entity.domain] || []
    const existing = Object.keys(entity.attributes || {})
    return Array.from(new Set([...contract, ...existing]))
  }

  const openExpand = async (entity: WorldEntity) => {
    setExpandEntity(entity)
    setExpandFields([])
    setExpandPrompt('')
    setExpandPreview('')
    if (!Object.keys(domainSpecs).length && projectId) {
      try {
        const data = await listProjectWorldDomains(projectId)
        const map: Record<string, string[]> = {}
        for (const item of data.domains || []) map[item.key] = item.attributes || []
        setDomainSpecs(map)
      } catch {
        /* 属性契约拿不到时退回已填字段，不阻塞补充 */
      }
    }
  }

  const doPreviewExpand = async () => {
    if (!expandEntity || !projectId || !expandFields.length) return
    setExpandLoading(true)
    try {
      const data = await previewEntityExpansion(projectId, {
        entity_id: expandEntity.id,
        fields: expandFields,
        prompt_override: expandPrompt || undefined,
      })
      setExpandPreview(data.prompt)
    } catch (error: any) {
      message.error(error?.message || '预览提示词失败')
    } finally {
      setExpandLoading(false)
    }
  }

  // AI 结构建议（模块/字段）：必须经确认才成为 schema——过闸机制的真人入口。
  const [suggestions, setSuggestions] = useState<WorldBuildingSuggestions | null>(null)
  const [suggestionBusy, setSuggestionBusy] = useState('')

  const loadSuggestions = async () => {
    if (!projectId) return
    try {
      setSuggestions(await listWorldBuildingSuggestions(projectId))
    } catch {
      /* 建议加载失败不阻塞主流程 */
    }
  }

  const confirmDomainSuggestion = async (item: WorldBuildingSuggestions['domains'][number]) => {
    if (!projectId) return
    setSuggestionBusy(`domain:${item.key}`)
    try {
      await upsertProjectWorldDomain(projectId, item.key, {
        label: item.label,
        extra_attributes: item.attributes,
        is_enabled: true,
        source: 'custom',
      })
      message.success(`已启用模块「${item.label || item.key}」`)
      await Promise.all([loadSuggestions(), refreshDomainSpecs()])
    } catch (error: any) {
      message.error(error?.message || '确认模块失败')
    } finally {
      setSuggestionBusy('')
    }
  }

  const ignoreDomainSuggestion = async (item: WorldBuildingSuggestions['domains'][number]) => {
    if (!projectId) return
    setSuggestionBusy(`domain:${item.key}`)
    try {
      await resetProjectWorldDomain(projectId, item.key)
      await loadSuggestions()
    } catch (error: any) {
      message.error(error?.message || '忽略模块失败')
    } finally {
      setSuggestionBusy('')
    }
  }

  const confirmFieldSuggestion = async (item: WorldBuildingSuggestions['fields'][number]) => {
    if (!projectId) return
    setSuggestionBusy(`field:${item.domain}:${item.field}`)
    try {
      await confirmSuggestedField(projectId, { domain: item.domain, field: item.field })
      message.success(`已把「${item.field}」加入${item.domain_label || item.domain}的属性契约`)
      await Promise.all([loadSuggestions(), refreshDomainSpecs()])
    } catch (error: any) {
      message.error(error?.message || '确认字段失败')
    } finally {
      setSuggestionBusy('')
    }
  }

  const ignoreFieldSuggestion = async (item: WorldBuildingSuggestions['fields'][number]) => {
    if (!projectId) return
    setSuggestionBusy(`field:${item.domain}:${item.field}`)
    try {
      await ignoreSuggestedField(projectId, { domain: item.domain, field: item.field })
      await loadSuggestions()
    } catch (error: any) {
      message.error(error?.message || '忽略字段失败')
    } finally {
      setSuggestionBusy('')
    }
  }

  const refreshDomainSpecs = async () => {
    if (!projectId) return
    try {
      const data = await listProjectWorldDomains(projectId)
      const map: Record<string, string[]> = {}
      for (const item of data.domains || []) map[item.key] = item.attributes || []
      setDomainSpecs(map)
    } catch {
      /* 忽略 */
    }
  }

  // 世界构建模板：层次策略与提示词由数据决定，编辑内嵌在使用处（OQ-D）。
  const [templates, setTemplates] = useState<WorldBuildingTemplate[]>([])
  const [templateId, setTemplateId] = useState('')
  const [templateEditorOpen, setTemplateEditorOpen] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateLayers, setTemplateLayers] = useState('')
  const [templatePrompt, setTemplatePrompt] = useState('')
  const [templatePromptEntity, setTemplatePromptEntity] = useState('')
  const [templateDrafting, setTemplateDrafting] = useState(false)
  const [templateDraftNote, setTemplateDraftNote] = useState('')

  const loadTemplates = async () => {
    if (!projectId) return
    try {
      const data = await listWorldTemplates(projectId)
      const rows = data.templates || []
      setTemplates(rows)
      const fallback = rows.find((item) => item.is_default && !item.is_builtin)
      setTemplateId((prev) => prev || fallback?.id || '')
    } catch {
      /* 模板加载失败不阻塞细化 */
    }
  }

  const saveTemplate = async () => {
    if (!projectId) return
    const layers = templateLayers
      .split(/[、,，>/]+/)
      .map((item) => item.trim())
      .filter(Boolean)
    try {
      const prompts: Record<string, string> = {}
      if (templatePrompt.trim()) prompts.expand_domain = templatePrompt.trim()
      if (templatePromptEntity.trim()) prompts.expand_entity = templatePromptEntity.trim()
      const saved = await upsertWorldTemplate(projectId, {
        name: templateName || '自定义模板',
        layers,
        prompts: Object.keys(prompts).length ? prompts : undefined,
        is_default: true,
      })
      message.success(`已保存模板「${saved.name}」`)
      setTemplateDraftNote('')
      await loadTemplates()
      setTemplateId(saved.id)
      setTemplateEditorOpen(false)
    } catch (error: any) {
      message.error(error?.message || '保存模板失败')
    }
  }

  const draftTemplate = async () => {
    if (!projectId) return
    setTemplateDrafting(true)
    setTemplateDraftNote('')
    try {
      const draft = await draftWorldTemplate(projectId, {
        domain: domainTaskTarget || undefined,
        hint: domainHint || undefined,
      })
      setTemplateName(draft.name)
      setTemplateLayers((draft.layers || []).join(' > '))
      setTemplatePrompt(draft.prompts?.expand_domain || '')
      setTemplatePromptEntity(draft.prompts?.expand_entity || '')
      setTemplateDraftNote(draft.note || '已生成草案，可微调后保存')
      message.success(`已生成草案「${draft.name}」（未保存）`)
    } catch (error: any) {
      message.error(error?.message || '起草模板失败')
    } finally {
      setTemplateDrafting(false)
    }
  }

  // 域级细化：异步提交到既有任务中心，轮询进度（不新造轮询协议）。
  const [domainTaskOpen, setDomainTaskOpen] = useState(false)
  const [domainTaskTarget, setDomainTaskTarget] = useState('')
  const [domainHint, setDomainHint] = useState('')
  const [domainSubmitting, setDomainSubmitting] = useState(false)
  const [domainTask, setDomainTask] = useState<WorldDomainExpansionTask | null>(null)
  const [domainProgress, setDomainProgress] = useState({ progress: 0, message: '' })

  const pollDomainTask = async (taskId: string) => {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      // eslint-disable-next-line no-await-in-loop
      await new Promise((resolve) => setTimeout(resolve, 2000))
      try {
        const response: any = await getTask(taskId)
        const task = response?.task ?? response
        setDomainProgress({
          progress: Number(task?.progress ?? 0),
          message: String(task?.progress_message || ''),
        })
        if (task?.status === 'done') {
          const result = task?.result || {}
          message.success(
            `已产出 ${result.candidate_count ?? 0} 条候选，正在打开审阅`,
          )
          setDomainTaskOpen(false)
          await Promise.all([loadSuggestions(), refreshDomainSpecs()])
          if (result.run_id) {
            window.location.href = `/novel-world?run_id=${encodeURIComponent(String(result.run_id))}`
          }
          return
        }
        if (task?.status === 'failed') {
          message.error(task?.error || '域级细化失败')
          setDomainSubmitting(false)
          return
        }
      } catch {
        /* 轮询失败继续重试 */
      }
    }
    message.warning('任务仍在运行，可在任务中心查看进度')
    setDomainSubmitting(false)
  }

  const submitDomainExpansion = async () => {
    if (!projectId || !domainTaskTarget) return
    setDomainSubmitting(true)
    setDomainProgress({ progress: 0, message: '已提交，等待执行…' })
    try {
      const task = await expandWorldDomain(projectId, {
        domain: domainTaskTarget,
        hint: domainHint || undefined,
        template_id: templateId || undefined,
        provider: expandProvider || undefined,
        model: expandModel || undefined,
      })
      setDomainTask(task)
      await pollDomainTask(task.task_id)
    } catch (error: any) {
      message.error(error?.message || '提交域级细化失败')
      setDomainSubmitting(false)
    }
  }

  const doExpandEntity = async () => {
    if (!expandEntity || !projectId) return
    if (!expandFields.length) {
      message.warning('请先勾选待补充的字段')
      return
    }
    setExpandLoading(true)
    // 同步接口：LLM 通常需要 20-60 秒。Modal 的 loading 态只有一个转圈按钮，
    // 这里在弹窗里放显式的进度提示，让等待"有刻度、可预期"，而不是像卡死。
    const startedAt = Date.now()
    const timer = setInterval(() => {
      const seconds = Math.round((Date.now() - startedAt) / 1000)
      setExpandElapsed(seconds)
    }, 1000)
    try {
      const result = await expandEntityAttributes(projectId, {
        entity_id: expandEntity.id,
        fields: expandFields,
        prompt_override: expandPrompt || undefined,
        provider: expandProvider || undefined,
        model: expandModel || undefined,
      })
      message.success('已生成补充候选，正在打开审阅')
      setExpandEntity(null)
      window.location.href = `/novel-world?run_id=${encodeURIComponent(result.run_id)}`
    } catch (error: any) {
      message.error(error?.message || '补充属性失败')
    } finally {
      clearInterval(timer)
      setExpandElapsed(0)
      setExpandLoading(false)
    }
  }

  if (!hasOutline) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description="先生成故事大纲，再拆分项目圣经和世界资产" />
      </div>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <WorkbenchSection
        title="项目圣经 / 世界资产"
        extra={
          <Space wrap>
            <Tag color={lockedCount ? 'green' : 'default'}>已锁定 {lockedCount}</Tag>
            <Button
              type="primary"
              icon={<RobotOutlined />}
              loading={loading}
              onClick={onExtractWorld}
              title="按逐域检测生成带证据锚点的世界设定候选，到世界提取工作台审阅确认后写入本项目"
            >
              生成世界设定候选
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => onSync(false)}>
              从大纲补齐
            </Button>
            <Popconfirm
              title="重新同步会基于当前大纲创建新版本，旧卡仍保留在版本历史里。"
              okText="创建新版本"
              cancelText="取消"
              onConfirm={() => onSync(true)}
            >
              <Button loading={loading}>重新同步新版本</Button>
            </Popconfirm>
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          锁定后的卡片会注入后续“单话细纲”生成上下文，用来稳定世界规则、地点、画风、人物关系和连续性事实。
        </Paragraph>
      </WorkbenchSection>

      <WorkbenchSection title="项目圣经">
        {bibleContents.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            {sortBibleContents(bibleContents).map((content) => (
              <BibleContentCard
                key={content.id}
                content={content}
                saving={savingContentId === content.id}
                onSaveContent={onSaveContent}
                onSaveAsAsset={onSaveAsAsset}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无项目圣经卡，可先从大纲补齐" />
        )}
      </WorkbenchSection>

      <WorkbenchSection title="世界资产">
        {worldAssets.length ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            {sortBibleContents(worldAssets).map((content) => (
              <BibleContentCard
                key={content.id}
                content={content}
                saving={savingContentId === content.id}
                onSaveContent={onSaveContent}
                onSaveAsAsset={onSaveAsAsset}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无世界资产卡，可先从大纲补齐" />
        )}
      </WorkbenchSection>

      <WorkbenchSection
        title="世界设定（按域）"
        extra={
          <Space wrap>
            {worldEntities.length ? (
              <Tag color="blue">{worldEntities.length} 个实体 / {worldRelations.length} 条关系</Tag>
            ) : null}
            <Button
              size="small"
              icon={<EnvironmentOutlined />}
              disabled={!projectId}
              onClick={() => {
                window.location.href = `/novel-world?project_id=${encodeURIComponent(projectId)}`
              }}
            >
              打开世界地图工作台
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              类型化世界提取产物，按域分组展示
            </Text>
          </Space>
        }
      >
        {worldLoading ? (
          <div style={{ padding: 24, textAlign: 'center' }}>
            <Text type="secondary">加载中...</Text>
          </div>
        ) : worldEntities.length === 0 ? (
          <Empty description="尚未生成世界设定候选。点上方「生成世界设定候选」一键产出（推荐用 qwen3.8-27b 等中文模型）。" />
        ) : (
          <Space direction="vertical" size={20} style={{ width: '100%' }}>
            {suggestions && (suggestions.domains.length > 0 || suggestions.fields.length > 0) && (
              <div
                style={{
                  border: '1px dashed #91caff',
                  background: 'rgba(22,119,255,0.04)',
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                <Text strong style={{ fontSize: 13 }}>
                  AI 结构建议（{suggestions.domains.length + suggestions.fields.length}）待确认
                </Text>
                <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 8 }}>
                  这些是 AI 在补充设定时提出的结构变更。确认后才会成为该项目的模块或属性字段；
                  忽略后不再提示。未确认前不参与任何提取与生成。
                </Paragraph>
                {suggestions.domains.map((item) => (
                  <div
                    key={`domain-${item.key}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}
                  >
                    <Tag color="blue">新模块</Tag>
                    <Text style={{ fontSize: 12 }}>
                      {item.label || item.key}
                      {item.attributes?.length
                        ? `（${item.attributes.map((field) => worldFieldLabel(field)).join('、')}）`
                        : ''}
                    </Text>
                    {item.reason && (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {item.reason}
                      </Text>
                    )}
                    <Button
                      size="small"
                      type="primary"
                      loading={suggestionBusy === `domain:${item.key}`}
                      onClick={() => confirmDomainSuggestion(item)}
                    >
                      确认启用
                    </Button>
                    <Button
                      size="small"
                      loading={suggestionBusy === `domain:${item.key}`}
                      onClick={() => ignoreDomainSuggestion(item)}
                    >
                      忽略
                    </Button>
                  </div>
                ))}
                {suggestions.fields.map((item) => (
                  <div
                    key={`field-${item.domain}-${item.field}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}
                  >
                    <Tag color="geekblue">新字段</Tag>
                    <Text style={{ fontSize: 12 }}>
                      {item.domain_label || item.domain} · {item.field}
                    </Text>
                    {item.reason && (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {item.reason}
                      </Text>
                    )}
                    <Button
                      size="small"
                      type="primary"
                      loading={suggestionBusy === `field:${item.domain}:${item.field}`}
                      onClick={() => confirmFieldSuggestion(item)}
                    >
                      加入属性契约
                    </Button>
                    <Button
                      size="small"
                      loading={suggestionBusy === `field:${item.domain}:${item.field}`}
                      onClick={() => ignoreFieldSuggestion(item)}
                    >
                      忽略
                    </Button>
                  </div>
                ))}
              </div>
            )}
            {Object.entries(entitiesByType).map(([type, items]) => (
              <div key={type}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Text strong style={{ fontSize: 14 }}>
                    {entityTypeLabels[type] || type}（{items.length}）
                  </Text>
                  <Button
                    size="small"
                    type="link"
                    onClick={() => {
                      setDomainTaskTarget(type)
                      setDomainHint('')
                      setDomainTask(null)
                      setDomainProgress({ progress: 0, message: '' })
                      setTemplateEditorOpen(false)
                      setDomainTaskOpen(true)
                      loadTemplates()
                    }}
                    title="让 AI 按层次策略细化这个模块，异步执行并在任务中心可查进度"
                  >
                    AI 细化本模块
                  </Button>
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: 12,
                    marginTop: 8,
                  }}
                >
                  {items.map((entity) => (
                    <Card
                      size="small"
                      key={entity.id}
                      title={<Text strong>{entity.name}</Text>}
                      extra={
                        <Button
                          size="small"
                          type="link"
                          onClick={() => openExpand(entity)}
                          title="按模块属性契约让 AI 补充这个实体的字段（产出候选，需审阅确认后写入）"
                        >
                          AI 补充
                        </Button>
                      }
                    >
                      {entity.summary && (
                        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
                          {entity.summary}
                        </Paragraph>
                      )}
                      {Object.keys(entity.attributes || {}).length > 0 && (
                        <div style={{ fontSize: 11 }}>
                          {Object.entries(entity.attributes || {})
                            .filter(([, value]) => worldFieldValueText(value))
                            .slice(0, 5)
                            .map(([key, value]) => (
                              <div key={key} style={{ marginBottom: 2 }} title={key}>
                                <Text type="secondary">{worldFieldLabel(key)}：</Text>
                                {worldFieldValueText(value).slice(0, 80)}
                              </div>
                            ))}
                        </div>
                      )}
                    </Card>
                  ))}
                </div>
              </div>
            ))}

            {worldRelations.length > 0 && (
              <div>
                <Text strong style={{ fontSize: 14 }}>实体关系（{worldRelations.length}）</Text>
                <Space direction="vertical" size={4} style={{ marginTop: 8, width: '100%' }}>
                  {worldRelations.map((relation) => (
                    <div key={relation.id} style={{ fontSize: 12 }}>
                      {entityNameById[relation.source_entity_id] || '?'}
                      <Tag color="blue" style={{ marginInline: 6 }}>{relation.relation_type}</Tag>
                      {entityNameById[relation.target_entity_id] || '?'}
                      {relation.note && <Text type="secondary" style={{ marginLeft: 6 }}>（{relation.note}）</Text>}
                    </div>
                  ))}
                </Space>
              </div>
            )}
          </Space>
        )}
      </WorkbenchSection>

      <Modal
        open={domainTaskOpen}
        title={`AI 细化模块 · ${entityTypeLabels[domainTaskTarget] || domainTaskTarget}`}
        onCancel={() => {
          if (domainSubmitting) {
            message.info('任务已在后台运行，可在任务中心查看或取消')
            return
          }
          setDomainTaskOpen(false)
        }}
        footer={[
          <Button
            key="close"
            onClick={() => setDomainTaskOpen(false)}
            disabled={domainSubmitting}
          >
            关闭
          </Button>,
          <Button
            key="submit"
            type="primary"
            loading={domainSubmitting}
            disabled={!domainTaskTarget}
            onClick={submitDomainExpansion}
          >
            {domainSubmitting ? '执行中…' : '开始细化'}
          </Button>,
        ]}
        width={520}
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            按层次策略批量细化该模块：只补充尚未出现且有实际作用的条目。任务
            <Text strong> 异步执行</Text>
            ，可在任务中心查看进度或取消；完成后产出候选（标记 ai_draft），需审阅确认才写入正典。
          </Text>
          <div>
            <Space wrap style={{ marginBottom: 4 }}>
              <Text strong style={{ fontSize: 13 }}>
                层次模板
              </Text>
              <Select
                style={{ width: 220 }}
                value={templateId || undefined}
                onChange={setTemplateId}
                placeholder="选择模板（留空用默认提示词）"
                allowClear
                options={templates.map((item) => ({
                  value: item.id,
                  label: `${item.is_builtin ? '内置 · ' : ''}${item.name}`,
                }))}
              />
              <Button size="small" onClick={() => setTemplateEditorOpen((open) => !open)}>
                {templateEditorOpen ? '收起编辑' : '新建 / 编辑模板'}
              </Button>
            </Space>
            {(() => {
              const active = templates.find((item) => item.id === templateId)
              return active?.layers?.length ? (
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    层次：{active.layers.join(' → ')}
                  </Text>
                </div>
              ) : null
            })()}
            {templateEditorOpen && (
              <div
                style={{
                  border: '1px solid #d9d9d9',
                  borderRadius: 6,
                  padding: 8,
                  marginTop: 6,
                  display: 'grid',
                  gap: 8,
                }}
              >
                <Space wrap>
                  <Input
                    placeholder="模板名称"
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    style={{ width: 240 }}
                  />
                  <Button
                    size="small"
                    loading={templateDrafting}
                    onClick={draftTemplate}
                    icon={<ThunderboltOutlined />}
                  >
                    AI 起草
                  </Button>
                </Space>
                {templateDraftNote && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {templateDraftNote}
                  </Text>
                )}
                <Input
                  placeholder="层次策略，用 > 分隔，如：世界 > 大陆 > 国家 > 城市"
                  value={templateLayers}
                  onChange={(e) => setTemplateLayers(e.target.value)}
                />
                <Input.TextArea
                  rows={2}
                  placeholder="模块细化提示词（expand_domain，可选），支持 {domain} {layers} {known} {hint} 占位"
                  value={templatePrompt}
                  onChange={(e) => setTemplatePrompt(e.target.value)}
                />
                <Input.TextArea
                  rows={2}
                  placeholder="实体补字段提示词（expand_entity，可选），支持 {entity} {fields} 占位"
                  value={templatePromptEntity}
                  onChange={(e) => setTemplatePromptEntity(e.target.value)}
                />
                <Button size="small" type="primary" onClick={saveTemplate}>
                  保存模板
                </Button>
              </div>
            )}
          </div>
          <Input.TextArea
            rows={3}
            value={domainHint}
            onChange={(e) => setDomainHint(e.target.value)}
            placeholder="补充要求（可选）：例如「只补充镇上和码头的地点」「势力要体现彼此敌对关系」"
            disabled={domainSubmitting}
          />
          <div>
            <Text strong style={{ fontSize: 13 }}>
              AI 模型（生成时就地选择）
            </Text>
            <div style={{ marginTop: 6 }}>
              <ProviderModelSelect
                backends={llmBackends}
                provider={expandProvider}
                model={expandModel}
                onProviderChange={setExpandProvider}
                onModelChange={setExpandModel}
              />
            </div>
          </div>
          {domainSubmitting && (
            <div>
              <Progress
                percent={domainProgress.progress}
                status={domainProgress.progress >= 100 ? 'success' : 'active'}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {domainProgress.message || '正在处理…'}
                {domainTask?.task_id ? `（任务 ${domainTask.task_id}）` : ''}
              </Text>
            </div>
          )}
        </Space>
      </Modal>

      <Modal
        open={Boolean(expandEntity)}
        title={expandEntity ? `AI 补充属性 · ${expandEntity.name}` : 'AI 补充属性'}
        onCancel={() => setExpandEntity(null)}
        onOk={doExpandEntity}
        okText="生成候选"
        cancelText="取消"
        confirmLoading={expandLoading}
        width={620}
      >
        {expandEntity && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              按该模块的属性契约补充字段，只回写你勾选的字段、不覆盖已填内容。生成的是
              <Text strong> 候选（标记 ai_draft，没有原文证据）</Text>
              ，需在世界工作台审阅确认后才写入正典。
            </Text>
            <div>
              <Text strong style={{ fontSize: 13 }}>
                待补充字段（勾选）
              </Text>
              <div style={{ marginTop: 6 }}>
                {attributesFor(expandEntity).length ? (
                  attributesFor(expandEntity).map((field) => (
                    <Tag.CheckableTag
                      key={field}
                      checked={expandFields.includes(field)}
                      onChange={(checked) =>
                        setExpandFields((prev) =>
                          checked ? [...prev, field] : prev.filter((item) => item !== field),
                        )
                      }
                    >
                      {worldFieldLabel(field)}
                      {expandEntity.attributes?.[field] ? '（已填）' : ''}
                    </Tag.CheckableTag>
                  ))
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    该模块暂无属性契约，可先在「世界模块」里追加字段
                  </Text>
                )}
              </div>
            </div>
            <div>
              <Text strong style={{ fontSize: 13 }}>
                AI 模型（生成时就地选择）
              </Text>
              <div style={{ marginTop: 6 }}>
                <ProviderModelSelect
                  backends={llmBackends}
                  provider={expandProvider}
                  model={expandModel}
                  onProviderChange={setExpandProvider}
                  onModelChange={setExpandModel}
                />
              </div>
            </div>
            <div>
              <Text strong style={{ fontSize: 13 }}>
                提示词（可编辑，留空用默认模板）
              </Text>
              <Input.TextArea
                rows={4}
                value={expandPrompt}
                onChange={(e) => setExpandPrompt(e.target.value)}
                style={{ marginTop: 6 }}
                placeholder="留空则使用项目模板（或内置默认模板）"
              />
              <Button
                size="small"
                style={{ marginTop: 6 }}
                loading={expandLoading}
                disabled={!expandFields.length}
                onClick={doPreviewExpand}
              >
                预览提示词（不消耗配额）
              </Button>
            </div>
            {expandLoading && (
              <Alert
                type="info"
                showIcon
                message={`正在生成候选，已用时 ${expandElapsed} 秒…`}
                description={`已选模型：${expandProvider || '默认'} / ${expandModel || '默认'}。LLM 生成通常需要 20–60 秒，期间请勿关闭弹窗。`}
              />
            )}
            {expandPreview && (
              <div
                style={{
                  background: 'rgba(0,0,0,0.03)',
                  padding: 10,
                  borderRadius: 6,
                  fontSize: 12,
                  whiteSpace: 'pre-wrap',
                  maxHeight: 220,
                  overflow: 'auto',
                }}
              >
                {expandPreview}
              </div>
            )}
          </Space>
        )}
      </Modal>
    </Space>
  )
}

