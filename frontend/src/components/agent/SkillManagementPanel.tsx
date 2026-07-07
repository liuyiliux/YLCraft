import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Input,
  Popconfirm,
  Row,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { App as AntApp } from 'antd'
import {
  BranchesOutlined,
  CodeOutlined,
  FileTextOutlined,
  ImportOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  approveAgentSkillDraft,
  createAgentSkillBundle,
  createAgentSkillDraft,
  deleteAgentSkillBundle,
  importAgentSkillDraftUrl,
  listAgentTools,
  listAgentSkills,
  listAgentSkillDrafts,
  listAgentSkillPackageFiles,
  listAgentSkillPackageIndex,
  previewAgentSkillRoute,
  readAgentSkillPackageFile,
  rejectAgentSkillDraft,
  updateAgentSkillBundle,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

interface SkillPackageIndexItem {
  name: string
  title: string
  description: string
  skill_type: string
  version: string
  category: string
  tags: string[]
  triggers: {
    keywords?: string[]
    context_keys?: string[]
    tools?: string[]
  }
  requires_tools: string[]
  risk: string
  source_path: string
  checksum: string
}

interface SkillBundleIndexItem {
  name: string
  description: string
  skills: string[]
  missing_skills?: string[]
  instruction: string
  source_path: string
  source_type?: string
}

interface SkillPackageFileItem {
  path: string
  kind: string
  size: number
}

interface RoutePreviewItem {
  skill_id: string
  reason: string
  score: number
  source: string
  trigger_type: string
  matches: string[]
}

interface RouteDiagnostic {
  target_skill_id?: string
  exists?: boolean
  matched?: boolean
  matched_route?: RoutePreviewItem | null
  keyword_hits?: string[]
  missing_keywords?: string[]
  context_hits?: string[]
  missing_context_keys?: string[]
  tool_hits?: string[]
  unavailable_tools?: string[]
  suggestions?: string[]
}

interface AgentSkillMetric {
  name: string
  is_builtin?: boolean
  usage_count?: number
  success_count?: number
  success_rate?: number
}

interface SkillDraftItem {
  id: number
  name: string
  title: string
  description: string
  skill_type: string
  content: string
  source_type: string
  source_url: string
  status: string
  target_path: string
  diagnostics: string[]
  review?: {
    mode?: string
    existing_path?: string
    diff?: string
  }
  created_at: string
}

function parseJsonObject(text: string) {
  if (!text.trim()) return {}
  return JSON.parse(text)
}

function splitRuleText(text: string) {
  return Array.from(new Set(
    text
      .split(/[\n,，]/)
      .map(item => item.trim())
      .filter(Boolean),
  ))
}

function sampleValueForContextKey(key: string) {
  const normalized = key.toLowerCase()
  if (normalized.includes('project')) return 'project-1'
  if (normalized.includes('character')) return 'char-1'
  if (normalized.includes('asset')) return 'asset-1'
  if (normalized.includes('chapter')) return 1
  if (normalized.includes('episode')) return 1
  if (normalized.includes('content')) return 'content-1'
  if (normalized.includes('provider')) return 'provider-1'
  if (normalized.includes('model')) return 'model-1'
  if (normalized.includes('platform')) return 'bili'
  if (normalized.includes('task')) return 'task-1'
  if (normalized.includes('run')) return 'run-1'
  return `${key}_sample`
}

function buildSkillRouteExample(skill?: SkillPackageIndexItem | null) {
  const keywords = skill?.triggers?.keywords?.filter(Boolean) || []
  const contextKeys = skill?.triggers?.context_keys?.filter(Boolean) || []
  const tools = skill?.triggers?.tools?.filter(Boolean) || []
  const title = skill?.title || skill?.name || '当前 Skill'
  const keywordText = keywords.slice(0, 3).join('、')
  const message = keywordText
    ? `请用${title}处理：${keywordText}`
    : `/${skill?.name || ''} 测试这个工作流`.trim()
  const context = Object.fromEntries(
    contextKeys.slice(0, 8).map(key => [key, sampleValueForContextKey(key)]),
  )
  return {
    message,
    context: JSON.stringify(context, null, 2),
    tools,
  }
}

function yamlInlineList(values: string[]) {
  if (!values.length) return '[]'
  return `[${values.map(value => JSON.stringify(value)).join(', ')}]`
}

function parseYamlListValue(value: string) {
  const trimmed = value.trim()
  if (!trimmed || trimmed === '[]') return []
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    return trimmed
      .slice(1, -1)
      .split(',')
      .map(item => item.trim().replace(/^['"]|['"]$/g, ''))
      .filter(Boolean)
  }
  return [trimmed.replace(/^['"]|['"]$/g, '')].filter(Boolean)
}

function parseSkillRouteRules(content: string) {
  const result = {
    keywords: [] as string[],
    context_keys: [] as string[],
    tools: [] as string[],
    requires_tools: [] as string[],
  }
  const lines = content.split(/\r?\n/)
  let section = ''
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed === '---' && section) break
    if (/^triggers\s*:/.test(line)) {
      section = 'triggers'
      continue
    }
    if (/^requires_tools\s*:/.test(line)) {
      result.requires_tools.push(...parseYamlListValue(line.replace(/^requires_tools\s*:\s*/, '')))
      section = 'requires_tools'
      continue
    }
    if (section === 'triggers') {
      const match = line.match(/^\s+(keywords|context_keys|tools)\s*:\s*(.*)$/)
      if (match) {
        result[match[1] as 'keywords' | 'context_keys' | 'tools'].push(...parseYamlListValue(match[2]))
        section = `triggers.${match[1]}`
        continue
      }
    }
    if (trimmed.startsWith('- ')) {
      const value = trimmed.slice(2).trim().replace(/^['"]|['"]$/g, '')
      if (section === 'requires_tools') result.requires_tools.push(value)
      if (section === 'triggers.keywords') result.keywords.push(value)
      if (section === 'triggers.context_keys') result.context_keys.push(value)
      if (section === 'triggers.tools') result.tools.push(value)
      continue
    }
    if (/^\S/.test(line) && !/^---$/.test(trimmed)) section = ''
  }
  return {
    keywords: Array.from(new Set(result.keywords.filter(Boolean))),
    context_keys: Array.from(new Set(result.context_keys.filter(Boolean))),
    tools: Array.from(new Set(result.tools.filter(Boolean))),
    requires_tools: Array.from(new Set(result.requires_tools.filter(Boolean))),
  }
}

function diffList(previous: string[], next: string[]) {
  const before = new Set(previous)
  const after = new Set(next)
  return {
    added: next.filter(item => !before.has(item)),
    removed: previous.filter(item => !after.has(item)),
  }
}

function buildRouteRuleDiff(currentContent: string, draftContent: string) {
  const current = parseSkillRouteRules(currentContent)
  const draft = parseSkillRouteRules(draftContent)
  return {
    current,
    draft,
    fields: {
      keywords: diffList(current.keywords, draft.keywords),
      context_keys: diffList(current.context_keys, draft.context_keys),
      tools: diffList(current.tools, draft.tools),
      requires_tools: diffList(current.requires_tools, draft.requires_tools),
    },
  }
}

function replaceSkillRouteRules(
  raw: string,
  triggers: { keywords: string[]; context_keys: string[]; tools: string[] },
  requiresTools: string[],
) {
  const text = raw.trimStart()
  if (!text.startsWith('---')) {
    throw new Error('SKILL.md 缺少 YAML frontmatter')
  }
  const lines = text.split(/\r?\n/)
  const endIndex = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
  if (endIndex <= 0) {
    throw new Error('SKILL.md frontmatter 没有结束分隔符')
  }
  const frontmatter = lines.slice(1, endIndex)
  const body = lines.slice(endIndex)
  let insertIndex = frontmatter.findIndex(line => /^triggers\s*:/.test(line))
  if (insertIndex < 0) insertIndex = frontmatter.findIndex(line => /^requires_tools\s*:/.test(line))
  if (insertIndex < 0) insertIndex = frontmatter.findIndex(line => /^risk\s*:/.test(line))
  if (insertIndex < 0) insertIndex = frontmatter.length

  const cleaned: string[] = []
  for (let index = 0; index < frontmatter.length; index += 1) {
    const line = frontmatter[index]
    if (/^triggers\s*:/.test(line) || /^requires_tools\s*:/.test(line)) {
      index += 1
      while (index < frontmatter.length && (/^\s+/.test(frontmatter[index]) || frontmatter[index].trim().startsWith('- '))) {
        index += 1
      }
      index -= 1
      continue
    }
    cleaned.push(line)
  }

  const routeBlock = [
    'triggers:',
    `  keywords: ${yamlInlineList(triggers.keywords)}`,
    `  context_keys: ${yamlInlineList(triggers.context_keys)}`,
    `  tools: ${yamlInlineList(triggers.tools)}`,
    `requires_tools: ${yamlInlineList(requiresTools)}`,
  ]
  const boundedInsertIndex = Math.min(insertIndex, cleaned.length)
  const nextFrontmatter = [
    ...cleaned.slice(0, boundedInsertIndex),
    ...routeBlock,
    ...cleaned.slice(boundedInsertIndex),
  ]
  return ['---', ...nextFrontmatter, ...body].join('\n').trimEnd() + '\n'
}

export function SkillManagementPanel() {
  const { theme: THEME } = useTheme()
  const { message } = AntApp.useApp()
  const [searchParams] = useSearchParams()
  const skillParam = searchParams.get('skill') || ''
  const [loading, setLoading] = useState(false)
  const [packages, setPackages] = useState<SkillPackageIndexItem[]>([])
  const [bundles, setBundles] = useState<SkillBundleIndexItem[]>([])
  const [skillMetrics, setSkillMetrics] = useState<Record<string, AgentSkillMetric>>({})
  const [agentTools, setAgentTools] = useState<any[]>([])
  const [selectedName, setSelectedName] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [fileLoading, setFileLoading] = useState(false)
  const [files, setFiles] = useState<SkillPackageFileItem[]>([])
  const [fileContent, setFileContent] = useState('')
  const [skillMdContent, setSkillMdContent] = useState('')
  const [filePath, setFilePath] = useState('SKILL.md')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [routeMessage, setRouteMessage] = useState('')
  const [routeContext, setRouteContext] = useState('{}')
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeResult, setRouteResult] = useState<RoutePreviewItem[]>([])
  const [routeDiagnostic, setRouteDiagnostic] = useState<RouteDiagnostic>({})
  const [routeError, setRouteError] = useState('')
  const [routeTargetSkill, setRouteTargetSkill] = useState('')
  const [routeAllowedTools, setRouteAllowedTools] = useState<string[]>([])
  const [drafts, setDrafts] = useState<SkillDraftItem[]>([])
  const [draftUrl, setDraftUrl] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const [draftLoading, setDraftLoading] = useState(false)
  const [selectedDraft, setSelectedDraft] = useState<SkillDraftItem | null>(null)
  const [selectedDraftCurrentContent, setSelectedDraftCurrentContent] = useState('')
  const [bundleName, setBundleName] = useState('')
  const [bundleDescription, setBundleDescription] = useState('')
  const [bundleInstruction, setBundleInstruction] = useState('')
  const [bundleSkills, setBundleSkills] = useState<string[]>([])
  const [bundleLoading, setBundleLoading] = useState(false)
  const [editingBundleName, setEditingBundleName] = useState('')
  const [ruleKeywords, setRuleKeywords] = useState('')
  const [ruleContextKeys, setRuleContextKeys] = useState('')
  const [ruleTools, setRuleTools] = useState<string[]>([])
  const [requiredTools, setRequiredTools] = useState<string[]>([])
  const [ruleDraftLoading, setRuleDraftLoading] = useState(false)

  const selectedPackage = useMemo(
    () => packages.find(item => item.name === selectedName) || null,
    [packages, selectedName],
  )

  const categories = useMemo(() => {
    const values = Array.from(new Set(packages.map(item => item.category).filter(Boolean))).sort()
    return [{ value: 'all', label: '全部分类' }, ...values.map(value => ({ value, label: value }))]
  }, [packages])

  const toolOptions = useMemo(
    () =>
      agentTools.map(tool => ({
        value: tool.name,
        label: `${tool.name}${tool.description_short || tool.description ? ` · ${tool.description_short || tool.description}` : ''}`,
      })),
    [agentTools],
  )

  const knownToolNames = useMemo(
    () => new Set(agentTools.map(tool => String(tool.name || '').trim()).filter(Boolean)),
    [agentTools],
  )

  const selectedDraftRouteDiff = useMemo(() => {
    if (!selectedDraft?.content) return null
    return buildRouteRuleDiff(selectedDraftCurrentContent || '', selectedDraft.content)
  }, [selectedDraft, selectedDraftCurrentContent])

  const filteredPackages = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return packages.filter(item => {
      if (category !== 'all' && item.category !== category) return false
      if (!keyword) return true
      return [
        item.name,
        item.title,
        item.description,
        item.category,
        ...(item.tags || []),
        ...(item.triggers?.keywords || []),
      ].some(value => String(value || '').toLowerCase().includes(keyword))
    })
  }, [category, packages, query])

  const loadIndex = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listAgentSkillPackageIndex()
      const skills = await listAgentSkills()
      const toolData = await listAgentTools()
      const draftData = await listAgentSkillDrafts('pending')
      const nextPackages = data.packages || []
      setPackages(nextPackages)
      setBundles(data.bundles || [])
      setDrafts(draftData.drafts || [])
      setAgentTools(toolData.tools || [])
      setSkillMetrics(
        Object.fromEntries((skills || []).map((item: AgentSkillMetric) => [item.name, item])),
      )
      setSelectedName(current => {
        if (skillParam && nextPackages.some((item: SkillPackageIndexItem) => item.name === skillParam)) return skillParam
        return current || nextPackages[0]?.name || ''
      })
      if (skillParam) setQuery(skillParam)
    } catch (err: any) {
      message.error(err?.message || '加载 Skill 包失败')
    } finally {
      setLoading(false)
    }
  }, [message, skillParam])

  const loadPackageFile = useCallback(async (skillName: string, path = 'SKILL.md') => {
    if (!skillName) return
    setFileLoading(true)
    try {
      const [fileList, content] = await Promise.all([
        listAgentSkillPackageFiles(skillName),
        readAgentSkillPackageFile(skillName, path),
      ])
      setFiles(fileList.files || [])
      setFilePath(content.file?.path || path)
      setFileContent(content.file?.content || '')
      if ((content.file?.path || path) === 'SKILL.md') {
        setSkillMdContent(content.file?.content || '')
      }
    } catch (err: any) {
      message.error(err?.message || '读取 Skill 文件失败')
    } finally {
      setFileLoading(false)
    }
  }, [message])

  useEffect(() => {
    loadIndex()
  }, [loadIndex])

  useEffect(() => {
    if (selectedName) loadPackageFile(selectedName)
  }, [loadPackageFile, selectedName])

  useEffect(() => {
    if (!selectedPackage) return
    const example = buildSkillRouteExample(selectedPackage)
    setRuleKeywords((selectedPackage.triggers?.keywords || []).join('\n'))
    setRuleContextKeys((selectedPackage.triggers?.context_keys || []).join('\n'))
    setRuleTools(selectedPackage.triggers?.tools || [])
    setRequiredTools(selectedPackage.requires_tools || [])
    setRouteTargetSkill(selectedPackage.name)
    setRouteMessage(example.message)
    setRouteContext(example.context)
    setRouteAllowedTools(example.tools)
  }, [selectedPackage])

  useEffect(() => {
    if (!skillParam || !packages.length) return
    const target = packages.find(item => item.name === skillParam)
    if (target) {
      setSelectedName(target.name)
      setQuery(target.name)
    }
  }, [packages, skillParam])

  useEffect(() => {
    let cancelled = false
    const loadCurrentDraftPackage = async () => {
      if (!selectedDraft?.name) {
        setSelectedDraftCurrentContent('')
        return
      }
      try {
        const content = await readAgentSkillPackageFile(selectedDraft.name, 'SKILL.md')
        if (!cancelled) setSelectedDraftCurrentContent(content.file?.content || '')
      } catch {
        if (!cancelled) setSelectedDraftCurrentContent('')
      }
    }
    loadCurrentDraftPackage()
    return () => {
      cancelled = true
    }
  }, [selectedDraft?.name])

  const handlePreviewRoute = async () => {
    setRouteLoading(true)
    setRouteError('')
    try {
      const data = await previewAgentSkillRoute({
        message: routeMessage,
        context: parseJsonObject(routeContext),
        allowed_tools: routeAllowedTools,
        target_skill_id: routeTargetSkill,
        max_skills: 8,
      })
      setRouteResult(data.routes || [])
      setRouteDiagnostic(data.diagnostic || {})
    } catch (err: any) {
      setRouteError(err?.message || '匹配测试失败，请检查上下文 JSON')
      setRouteResult([])
      setRouteDiagnostic({})
    } finally {
      setRouteLoading(false)
    }
  }

  const handleRouteTargetSkillChange = (name: string) => {
    const target = packages.find(item => item.name === name)
    setRouteTargetSkill(name)
    if (target) {
      const example = buildSkillRouteExample(target)
      setRouteMessage(example.message)
      setRouteContext(example.context)
      setRouteAllowedTools(example.tools)
      setSelectedName(target.name)
      setQuery(current => current || target.name)
    }
    setRouteResult([])
    setRouteDiagnostic({})
    setRouteError('')
  }

  const handleUseSelectedSkillExample = () => {
    const target = packages.find(item => item.name === routeTargetSkill) || selectedPackage
    const example = buildSkillRouteExample(target)
    setRouteMessage(example.message)
    setRouteContext(example.context)
    setRouteAllowedTools(example.tools)
    setRouteResult([])
    setRouteDiagnostic({})
    setRouteError('')
  }

  const handleAddRouteMessageAsKeyword = () => {
    const keyword = routeMessage.trim()
    if (!keyword) return
    const next = Array.from(new Set([...splitRuleText(ruleKeywords), keyword]))
    setRuleKeywords(next.join('\n'))
    message.success('已加入关键词编辑区，保存为草稿后才会生效')
  }

  const refreshDrafts = useCallback(async () => {
    const draftData = await listAgentSkillDrafts('pending')
    setDrafts(draftData.drafts || [])
  }, [])

  const handleImportDraftUrl = async () => {
    if (!draftUrl.trim()) {
      message.warning('请输入 SKILL.md 地址')
      return
    }
    setDraftLoading(true)
    try {
      const data = await importAgentSkillDraftUrl(draftUrl.trim())
      setDraftUrl('')
      setSelectedDraft(data.draft)
      await refreshDrafts()
      message.success('已导入为待审批草稿')
    } catch (err: any) {
      const diagnostics = err?.diagnostics || err?.data?.detail?.diagnostics || err?.response?.data?.detail?.diagnostics
      const hint = Array.isArray(diagnostics) && diagnostics.length > 0 ? diagnostics[0] : ''
      message.error(hint || err?.message || '导入失败')
    } finally {
      setDraftLoading(false)
    }
  }

  const handleCreateManualDraft = async () => {
    if (!draftContent.trim()) {
      message.warning('请粘贴 SKILL.md 内容')
      return
    }
    setDraftLoading(true)
    try {
      const data = await createAgentSkillDraft({ content: draftContent, source_type: 'manual' })
      setDraftContent('')
      setSelectedDraft(data.draft)
      await refreshDrafts()
      message.success('已创建待审批草稿')
    } catch (err: any) {
      message.error(err?.message || '创建草稿失败')
    } finally {
      setDraftLoading(false)
    }
  }

  const handleCreateRuleDraft = async () => {
    if (!selectedPackage) {
      message.warning('请选择一个 Skill')
      return
    }
    const baseContent = skillMdContent || (filePath === 'SKILL.md' ? fileContent : '')
    if (!baseContent.trim()) {
      message.warning('当前 Skill.md 还没有加载完成')
      return
    }
    const nextKeywords = splitRuleText(ruleKeywords)
    const nextContextKeys = splitRuleText(ruleContextKeys)
    const unknownTriggerTools = ruleTools.filter(tool => !knownToolNames.has(tool))
    const unknownRequiredTools = requiredTools.filter(tool => !knownToolNames.has(tool))
    if (unknownTriggerTools.length || unknownRequiredTools.length) {
      message.error(`工具不存在：${[...unknownTriggerTools, ...unknownRequiredTools].join('、')}`)
      return
    }
    if (!nextKeywords.length && !nextContextKeys.length && !ruleTools.length) {
      message.warning('至少保留一种触发方式：关键词、上下文 key 或工具')
      return
    }

    setRuleDraftLoading(true)
    try {
      const content = replaceSkillRouteRules(
        baseContent,
        {
          keywords: nextKeywords,
          context_keys: nextContextKeys,
          tools: ruleTools,
        },
        requiredTools,
      )
      const data = await createAgentSkillDraft({
        content,
        source_type: 'route_rule_edit',
        source_url: selectedPackage.source_path,
      })
      setSelectedDraft(data.draft)
      await refreshDrafts()
      message.success('已生成规则编辑草稿，批准后才会生效')
    } catch (err: any) {
      message.error(err?.message || '生成规则草稿失败')
    } finally {
      setRuleDraftLoading(false)
    }
  }

  const handleApproveDraft = async (draft: SkillDraftItem) => {
    setDraftLoading(true)
    try {
      await approveAgentSkillDraft(draft.id)
      await Promise.all([refreshDrafts(), loadIndex()])
      setSelectedDraft(null)
      if (draft.name === routeTargetSkill) {
        await handlePreviewRoute()
      }
      message.success('Skill 已启用')
    } catch (err: any) {
      message.error(err?.message || '批准失败')
    } finally {
      setDraftLoading(false)
    }
  }

  const handleRejectDraft = async (draft: SkillDraftItem) => {
    setDraftLoading(true)
    try {
      await rejectAgentSkillDraft(draft.id, 'Rejected from skill management panel')
      await refreshDrafts()
      setSelectedDraft(null)
      message.success('已拒绝草稿')
    } catch (err: any) {
      message.error(err?.message || '拒绝失败')
    } finally {
      setDraftLoading(false)
    }
  }

  const handleRejectDraftToEditor = async (draft: SkillDraftItem) => {
    const parsed = parseSkillRouteRules(draft.content || '')
    setSelectedName(draft.name)
    setQuery(draft.name)
    setRuleKeywords(parsed.keywords.join('\n'))
    setRuleContextKeys(parsed.context_keys.join('\n'))
    setRuleTools(parsed.tools)
    setRequiredTools(parsed.requires_tools)
    setRouteTargetSkill(draft.name)
    setRouteAllowedTools(parsed.tools)
    await handleRejectDraft(draft)
    message.info('已回填到路由规则编辑区，可继续修改后重新生成草稿')
  }

  const handleCreateBundle = async () => {
    if (!bundleName.trim()) {
      message.warning('请输入 Bundle 名称')
      return
    }
    if (bundleSkills.length === 0) {
      message.warning('请选择至少一个 Skill')
      return
    }
    setBundleLoading(true)
    try {
      const payload = {
        name: bundleName.trim(),
        description: bundleDescription.trim(),
        skills: bundleSkills,
        instruction: bundleInstruction.trim(),
      }
      if (editingBundleName) {
        await updateAgentSkillBundle(editingBundleName, payload)
      } else {
        await createAgentSkillBundle(payload)
      }
      setBundleName('')
      setBundleDescription('')
      setBundleInstruction('')
      setBundleSkills([])
      setEditingBundleName('')
      await loadIndex()
      message.success(editingBundleName ? 'Bundle 已更新' : 'Bundle 已创建')
    } catch (err: any) {
      const detail = err?.data?.detail || err?.response?.data?.detail
      message.error(detail?.message || err?.message || '保存 Bundle 失败')
    } finally {
      setBundleLoading(false)
    }
  }

  const handleEditBundle = (bundle: SkillBundleIndexItem) => {
    setEditingBundleName(bundle.name)
    setBundleName(bundle.name)
    setBundleDescription(bundle.description || '')
    setBundleInstruction(bundle.instruction || '')
    setBundleSkills(bundle.skills || [])
  }

  const handleCancelBundleEdit = () => {
    setEditingBundleName('')
    setBundleName('')
    setBundleDescription('')
    setBundleInstruction('')
    setBundleSkills([])
  }

  const handleDeleteBundle = async (bundle: SkillBundleIndexItem) => {
    if (bundle.source_type !== 'user') {
      message.warning('内置 Bundle 不能在页面删除')
      return
    }
    setBundleLoading(true)
    try {
      await deleteAgentSkillBundle(bundle.name)
      if (editingBundleName === bundle.name) handleCancelBundleEdit()
      await loadIndex()
      message.success('Bundle 已删除')
    } catch (err: any) {
      message.error(err?.message || '删除 Bundle 失败')
    } finally {
      setBundleLoading(false)
    }
  }

  const handleTestBundle = (bundle: SkillBundleIndexItem) => {
    const bundlePackages = bundle.skills
      .map(skill => packages.find(item => item.name === skill))
      .filter(Boolean) as SkillPackageIndexItem[]
    const firstExample = buildSkillRouteExample(bundlePackages[0])
    const mergedContext = Object.assign(
      {},
      ...bundlePackages.map(skill => parseJsonObject(buildSkillRouteExample(skill).context)),
    )
    setRouteMessage(`/${bundle.name} ${firstExample.message.replace(/^\/\S+\s*/, '').trim() || '测试这个工作流'}`)
    setRouteContext(JSON.stringify(mergedContext, null, 2))
    setRouteTargetSkill(bundle.skills[0] || '')
    setRouteAllowedTools(
      Array.from(new Set(
        bundle.skills.flatMap(skill => packages.find(item => item.name === skill)?.triggers?.tools || []),
      )),
    )
    message.info('已填入匹配测试，可点击“测试匹配”查看展开结果')
  }

  const totalUsage = useMemo(
    () => Object.values(skillMetrics).reduce((sum, item) => sum + (item.usage_count || 0), 0),
    [skillMetrics],
  )
  const enabledCount = useMemo(
    () => packages.filter(item => skillMetrics[item.name]).length,
    [packages, skillMetrics],
  )
  const writeCount = useMemo(
    () => packages.filter(item => item.risk === 'write').length,
    [packages],
  )
  const readCount = Math.max(packages.length - writeCount, 0)

  const panelStyle: CSSProperties = {
    background: THEME.bgCard,
    border: `1px solid ${THEME.border}`,
    borderRadius: THEME.radiusLG,
    boxShadow: THEME.shadowCard,
    overflow: 'hidden',
  }

  const mutedPanelStyle: CSSProperties = {
    background: THEME.bgElevated,
    border: `1px solid ${THEME.border}`,
    borderRadius: THEME.radiusMD,
  }

  const statItems = [
    { label: 'Skill 包', value: packages.length, hint: `${enabledCount} 个已同步` },
    { label: '待审批', value: drafts.length, hint: '远程导入先进入草稿' },
    { label: 'Bundle', value: bundles.length, hint: '可组合工作流' },
    { label: '调用记录', value: totalUsage, hint: `${readCount} read / ${writeCount} write` },
  ]

  return (
    <div className="skill-management-panel">
      <style>
        {`
          .skill-management-panel {
            max-width: 1580px;
            margin: 0 auto;
            color: ${THEME.textPrimary};
          }
          .skill-management-panel .ant-card-head {
            min-height: 56px;
            border-bottom-color: ${THEME.border};
          }
          .skill-management-panel .ant-card-head-title {
            font-weight: 700;
          }
          .skill-management-panel .ant-card-body {
            padding: 24px;
          }
          .skill-management-panel .ant-table {
            background: transparent;
          }
          .skill-management-panel .ant-table-thead > tr > th {
            background: ${THEME.bgElevated};
            color: ${THEME.textSecondary};
            border-bottom-color: ${THEME.border};
            font-size: 12px;
            font-weight: 700;
          }
          .skill-management-panel .ant-table-tbody > tr > td {
            border-bottom-color: ${THEME.borderLight};
            transition: background ${THEME.animationDuration} ${THEME.animationEasing};
          }
          .skill-management-panel .ant-table-tbody > tr:hover > td {
            background: ${THEME.primaryAlpha(0.07)} !important;
          }
          .skill-management-panel .ant-table-tbody > tr.skill-row-selected > td {
            background: ${THEME.primaryAlpha(0.12)} !important;
            border-bottom-color: ${THEME.primaryAlpha(0.24)};
          }
          .skill-management-panel .ant-tag {
            border-radius: ${THEME.radiusXS};
            font-weight: 500;
          }
          .skill-management-panel .ant-btn {
            border-radius: ${THEME.radiusSM};
          }
          .skill-management-panel .ant-input,
          .skill-management-panel .ant-select-selector,
          .skill-management-panel textarea.ant-input {
            border-radius: ${THEME.radiusSM} !important;
          }
          .skill-management-panel .skill-hero-layout {
            display: grid;
            grid-template-columns: minmax(280px, 1.4fr) minmax(360px, 1fr);
            gap: 24px;
            align-items: end;
          }
          .skill-management-panel .skill-stats-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
          }
          @media (max-width: 1280px) {
            .skill-management-panel .skill-hero-layout {
              grid-template-columns: 1fr;
            }
            .skill-management-panel .skill-stats-grid {
              grid-template-columns: repeat(4, minmax(130px, 1fr));
            }
          }
          @media (max-width: 760px) {
            .skill-management-panel .ant-card-body {
              padding: 16px;
            }
            .skill-management-panel .skill-stats-grid {
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }
          }
        `}
      </style>

      <section
        style={{
          ...panelStyle,
          padding: 24,
          marginBottom: 16,
          background: `linear-gradient(135deg, ${THEME.primaryAlpha(0.12)} 0%, ${THEME.bgCard} 42%, ${THEME.bgCard} 100%)`,
        }}
      >
        <div className="skill-hero-layout">
          <div>
            <Space size={10} style={{ marginBottom: 10 }}>
              <Tag color="cyan" style={{ marginInlineEnd: 0 }}>Agent Skills</Tag>
              <Text type="secondary">文件化能力编排</Text>
            </Space>
            <Title level={3} style={{ color: THEME.textPrimary, margin: 0, letterSpacing: 0 }}>
              Skill 包管理
            </Title>
            <Paragraph style={{ color: THEME.textSecondary, margin: '10px 0 0', maxWidth: 780, lineHeight: 1.7 }}>
              用 SKILL.md 固化高频工作流，内置项目工具保持默认可用，外部 Skill 先进入草稿审批，再写入用户目录并进入 Agent 路由。
            </Paragraph>
          </div>
          <div className="skill-stats-grid">
            {statItems.map(item => (
              <div key={item.label} style={{ ...mutedPanelStyle, padding: '14px 14px 12px' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>{item.label}</Text>
                <div style={{ color: THEME.textPrimary, fontSize: 24, fontWeight: 760, lineHeight: '32px' }}>{item.value}</div>
                <Text type="secondary" style={{ fontSize: 12 }}>{item.hint}</Text>
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
          <Button icon={<BranchesOutlined />} onClick={handlePreviewRoute} loading={routeLoading}>
            匹配测试
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadIndex} loading={loading}>
            刷新
          </Button>
        </div>
      </section>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={15}>
          <Card
            className="skill-list-card"
            title={
              <Space>
                <FileTextOutlined />
                <span>文件化 Skill</span>
                <Badge count={filteredPackages.length} style={{ backgroundColor: THEME.primary, boxShadow: 'none' }} />
              </Space>
            }
            extra={
              <Space wrap>
                <Input
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索名称、标签、触发词"
                  value={query}
                  onChange={event => setQuery(event.target.value)}
                  style={{ width: 240 }}
                />
                <Select value={category} options={categories} onChange={setCategory} style={{ width: 140 }} />
              </Space>
            }
            style={panelStyle}
          >
            {loading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : filteredPackages.length === 0 ? (
              <Empty description="没有匹配的 Skill 包" />
            ) : (
              <Table
                rowKey="name"
                className="skill-table"
                size="small"
                dataSource={filteredPackages}
                pagination={{ pageSize: 10, showSizeChanger: false, size: 'small' }}
                rowClassName={record => record.name === selectedName ? 'skill-row-selected' : ''}
                onRow={record => ({
                  onClick: () => setSelectedName(record.name),
                  style: { cursor: 'pointer' },
                })}
                columns={[
                  {
                    title: 'Skill',
                    dataIndex: 'title',
                    width: 260,
                    render: (_: string, record) => (
                      <Space direction="vertical" size={2}>
                        <Text strong style={{ color: THEME.textPrimary, fontSize: 14 }}>{record.title || record.name}</Text>
                        <Text code style={{ fontSize: 11, color: THEME.textSecondary }}>{record.name}</Text>
                      </Space>
                    ),
                  },
                  {
                    title: '分类',
                    dataIndex: 'category',
                    width: 120,
                    render: value => <Tag>{value}</Tag>,
                  },
                  {
                    title: '触发词',
                    dataIndex: ['triggers', 'keywords'],
                    render: (values: string[] = []) => (
                      <Space size={[4, 4]} wrap>
                        {values.slice(0, 5).map(value => <Tag key={value} color="blue">{value}</Tag>)}
                        {values.length > 5 && <Tag>+{values.length - 5}</Tag>}
                      </Space>
                    ),
                  },
                  {
                    title: '风险',
                    dataIndex: 'risk',
                    width: 90,
                    render: value => <Tag color={value === 'write' ? 'orange' : value === 'network' ? 'cyan' : 'green'}>{value}</Tag>,
                  },
                  {
                    title: '状态',
                    width: 110,
                    render: (_, record) => {
                      const metric = skillMetrics[record.name]
                      return <Tag color={metric ? 'green' : 'default'}>{metric ? '文件启用' : '待同步'}</Tag>
                    },
                  },
                  {
                    title: '使用',
                    width: 120,
                    render: (_, record) => {
                      const metric = skillMetrics[record.name]
                      const rate = metric?.success_rate != null ? `${Math.round(metric.success_rate * 100)}%` : '-'
                      return <Text style={{ color: THEME.textSecondary }}>{metric?.usage_count || 0} 次 / {rate}</Text>
                    },
                  },
                ]}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={9}>
          <Card
            title="当前 Skill"
            extra={
              selectedPackage && (
                <Button size="small" icon={<CodeOutlined />} onClick={() => setDrawerOpen(true)}>
                  查看全文
                </Button>
              )
            }
            style={{ ...panelStyle, marginBottom: 16 }}
          >
            {!selectedPackage ? (
              <Empty description="请选择一个 Skill" />
            ) : (
              <Space direction="vertical" size={0} style={{ width: '100%' }}>
                <div style={{ marginBottom: 14 }}>
                  <Space align="center" size={8} wrap>
                    <Text strong style={{ fontSize: 18, color: THEME.textPrimary, lineHeight: 1.3 }}>
                      {selectedPackage.title}
                    </Text>
                    <Tag color={selectedPackage.risk === 'write' ? 'orange' : selectedPackage.risk === 'network' ? 'cyan' : 'green'}>
                      {selectedPackage.risk} · 风险
                    </Tag>
                  </Space>
                  <Paragraph style={{ color: THEME.textSecondary, marginTop: 8, marginBottom: 0, lineHeight: 1.7 }}>
                    {selectedPackage.description}
                  </Paragraph>
                </div>

                <Descriptions
                  size="small"
                  column={2}
                  colon={false}
                  items={[
                    { key: 'type', label: '类型', children: <Tag>{selectedPackage.skill_type}</Tag> },
                    { key: 'ver', label: '版本', children: <Text>{selectedPackage.version}</Text> },
                    {
                      key: 'usage',
                      label: '使用',
                      children: (
                        <Text>
                          {skillMetrics[selectedPackage.name]?.usage_count || 0} 次
                          {' / '}
                          {skillMetrics[selectedPackage.name]?.success_rate != null
                            ? `${Math.round(skillMetrics[selectedPackage.name]!.success_rate * 100)}%`
                            : '-'}
                        </Text>
                      ),
                    },
                    {
                      key: 'state',
                      label: '状态',
                      children: (
                        <Tag color={skillMetrics[selectedPackage.name] ? 'green' : 'default'}>
                          {skillMetrics[selectedPackage.name] ? '已启用' : '待同步'}
                        </Tag>
                      ),
                    },
                  ]}
                />

                {(() => {
                  const keywordList = selectedPackage.triggers?.keywords || []
                  if (keywordList.length === 0) return null
                  return (
                    <div style={{ marginTop: 14 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>触发关键词</Text>
                      <div style={{ marginTop: 6 }}>
                        <Space size={[4, 4]} wrap>
                          {keywordList.map(value => <Tag key={value} color="blue">{value}</Tag>)}
                        </Space>
                      </div>
                    </div>
                  )
                })()}

                <Divider style={{ margin: '16px 0 12px' }} orientation="left" plain>
                  <Text type="secondary" style={{ fontSize: 12 }}>需要工具</Text>
                </Divider>
                <Space size={[4, 4]} wrap>
                  {(selectedPackage.requires_tools || []).map(tool => <Tag key={tool}>{tool}</Tag>)}
                  {(selectedPackage.requires_tools || []).length === 0 && <Text type="secondary">无强制工具</Text>}
                </Space>

                <Divider style={{ margin: '16px 0 4px' }} />

                <Collapse
                  ghost
                  defaultActiveKey={[]}
                  items={[
                    {
                      key: 'rules',
                      label: <Text strong style={{ color: THEME.textPrimary }}>路由规则</Text>,
                      children: (
                        <Space direction="vertical" size={10} style={{ width: '100%' }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            只生成待审批 SKILL.md 草稿，批准后才会覆盖用户 Skill；内置 Skill 会以用户副本方式启用。
                          </Text>
                          <TextArea
                            value={ruleKeywords}
                            onChange={event => setRuleKeywords(event.target.value)}
                            autoSize={{ minRows: 3, maxRows: 6 }}
                            placeholder="关键词，每行一个或用逗号分隔"
                          />
                          <TextArea
                            value={ruleContextKeys}
                            onChange={event => setRuleContextKeys(event.target.value)}
                            autoSize={{ minRows: 2, maxRows: 5 }}
                            placeholder="上下文 key，例如 project_id / character_id"
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            showSearch
                            value={ruleTools}
                            onChange={setRuleTools}
                            options={toolOptions}
                            placeholder="会触发该 Skill 的工具"
                            optionFilterProp="label"
                          />
                          <Select
                            mode="multiple"
                            allowClear
                            showSearch
                            value={requiredTools}
                            onChange={setRequiredTools}
                            options={toolOptions}
                            placeholder="执行该 Skill 通常需要的工具"
                            optionFilterProp="label"
                          />
                          <Button block type="primary" loading={ruleDraftLoading} onClick={handleCreateRuleDraft}>
                            保存为草稿
                          </Button>
                        </Space>
                      ),
                    },
                  ]}
                />

                <Divider style={{ margin: '16px 0 12px' }} orientation="left" plain>
                  <Text type="secondary" style={{ fontSize: 12 }}>包文件</Text>
                </Divider>
                {fileLoading ? (
                  <Skeleton active paragraph={{ rows: 2 }} />
                ) : (
                  <Space size={[4, 4]} wrap>
                    {files.map(item => (
                      <Button
                        key={item.path}
                        size="small"
                        onClick={() => loadPackageFile(selectedPackage.name, item.path)}
                        type={item.path === filePath ? 'primary' : 'default'}
                      >
                        {item.path}
                      </Button>
                    ))}
                  </Space>
                )}
              </Space>
            )}
          </Card>

          <Card
            title="匹配测试"
            extra={<Text type="secondary" style={{ fontSize: 12 }}>模拟用户消息会命中哪些 Skill</Text>}
            style={panelStyle}
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Select
                showSearch
                value={routeTargetSkill}
                onChange={handleRouteTargetSkillChange}
                options={packages.map(item => ({ value: item.name, label: `${item.title || item.name} (${item.name})` }))}
                placeholder="选择目标 Skill"
                optionFilterProp="label"
              />
              <Button size="small" onClick={handleUseSelectedSkillExample}>
                使用该 Skill 的测试样例
              </Button>
              <Input
                value={routeMessage}
                onChange={event => setRouteMessage(event.target.value)}
                placeholder="输入用户消息"
              />
              <TextArea
                value={routeContext}
                onChange={event => setRouteContext(event.target.value)}
                autoSize={{ minRows: 4, maxRows: 8 }}
                style={{ fontFamily: 'Consolas, Monaco, monospace' }}
              />
              <Select
                mode="multiple"
                allowClear
                showSearch
                value={routeAllowedTools}
                onChange={setRouteAllowedTools}
                options={toolOptions}
                placeholder="本次测试允许的工具"
                optionFilterProp="label"
              />
              <Button type="primary" icon={<BranchesOutlined />} onClick={handlePreviewRoute} loading={routeLoading}>
                测试匹配
              </Button>
              {routeError && <Alert type="error" message={routeError} showIcon />}
              {(routeDiagnostic?.target_skill_id || routeResult.length > 0) && (
                <Divider style={{ margin: '4px 0 8px' }} orientation="left" plain>
                  <Text type="secondary" style={{ fontSize: 12 }}>命中结果</Text>
                </Divider>
              )}
              {routeDiagnostic?.target_skill_id && (
                <Alert
                  type={routeDiagnostic.matched ? 'success' : 'warning'}
                  showIcon
                  message={routeDiagnostic.matched ? `目标 Skill 已命中：${routeDiagnostic.target_skill_id}` : `目标 Skill 未命中：${routeDiagnostic.target_skill_id}`}
                  description={
                    <Space direction="vertical" size={7} style={{ width: '100%' }}>
                      <Space wrap size={[4, 4]}>
                        {(routeDiagnostic.keyword_hits || []).map(item => <Tag key={`kw-hit-${item}`} color="blue">关键词 {item}</Tag>)}
                        {(routeDiagnostic.context_hits || []).map(item => <Tag key={`ctx-hit-${item}`} color="green">上下文 {item}</Tag>)}
                        {(routeDiagnostic.tool_hits || []).map(item => <Tag key={`tool-hit-${item}`} color="purple">工具 {item}</Tag>)}
                      </Space>
                      {!routeDiagnostic.matched && (
                        <Space direction="vertical" size={5} style={{ width: '100%' }}>
                          {(routeDiagnostic.missing_keywords || []).length > 0 && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              未命中关键词：{(routeDiagnostic.missing_keywords || []).slice(0, 8).join('、')}
                            </Text>
                          )}
                          {(routeDiagnostic.missing_context_keys || []).length > 0 && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              缺少上下文：{(routeDiagnostic.missing_context_keys || []).slice(0, 8).join('、')}
                            </Text>
                          )}
                          {(routeDiagnostic.unavailable_tools || []).length > 0 && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              未允许工具：{(routeDiagnostic.unavailable_tools || []).slice(0, 8).join('、')}
                            </Text>
                          )}
                        </Space>
                      )}
                      {(routeDiagnostic.suggestions || []).map(item => (
                        <Text key={item} type="secondary" style={{ fontSize: 12 }}>{item}</Text>
                      ))}
                      {!routeDiagnostic.matched && routeMessage.trim() && (
                        <Button size="small" onClick={handleAddRouteMessageAsKeyword}>
                          把本次消息加入关键词编辑区
                        </Button>
                      )}
                    </Space>
                  }
                />
              )}
              {routeResult.length > 0 && (
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  {routeResult.map(item => (
                    <div key={item.skill_id} style={{ padding: 12, borderRadius: THEME.radiusMD, border: `1px solid ${THEME.border}`, background: THEME.bgElevated }}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong>{item.skill_id}</Text>
                        <Tag color={item.source === 'package' ? 'blue' : item.source === 'slash' ? 'gold' : 'default'}>
                          {item.source}/{item.score}
                        </Tag>
                      </Space>
                      <div style={{ marginTop: 6 }}>
                        <Text type="secondary">{item.reason}</Text>
                      </div>
                    </div>
                  ))}
                </Space>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      <Card
        className="draft-review-card"
        title={
          <Space>
            <ImportOutlined />
            <span>Skill 草稿审批</span>
            <Badge count={drafts.length} style={{ backgroundColor: THEME.primary }} />
          </Space>
        }
        style={{ ...panelStyle, marginTop: 16 }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 14 }}
          message="远程 Skill 只会先导入为待审批草稿，批准后才会写入用户 Skill 目录并进入 Agent 路由。"
        />
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={10}>
            <Space direction="vertical" size={10} style={{ width: '100%', ...mutedPanelStyle, padding: 14 }}>
              <Input.Search
                value={draftUrl}
                onChange={event => setDraftUrl(event.target.value)}
                onSearch={handleImportDraftUrl}
                enterButton="导入 URL"
                loading={draftLoading}
                placeholder="GitHub 仓库、blob、raw 或 SKILL.md 地址"
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                支持 GitHub 仓库首页，例如 https://github.com/owner/repo，会自动尝试 raw SKILL.md。
              </Text>
              <TextArea
                value={draftContent}
                onChange={event => setDraftContent(event.target.value)}
                autoSize={{ minRows: 8, maxRows: 14 }}
                placeholder="或直接粘贴完整 SKILL.md"
                style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 12 }}
              />
              <Button icon={<ImportOutlined />} loading={draftLoading} onClick={handleCreateManualDraft}>
                创建草稿
              </Button>
            </Space>
          </Col>
          <Col xs={24} lg={14}>
            <Table
              rowKey="id"
              className="skill-table"
              size="small"
              dataSource={drafts}
              loading={draftLoading}
              pagination={{ pageSize: 5, showSizeChanger: false }}
              locale={{ emptyText: <Empty description="暂无待审批草稿" /> }}
              onRow={record => ({
                onClick: () => setSelectedDraft(record),
                style: { cursor: 'pointer' },
              })}
              columns={[
                {
                  title: '草稿',
                  dataIndex: 'title',
                  render: (_: string, record) => (
                    <Space direction="vertical" size={2}>
                      <Text strong>{record.title || record.name}</Text>
                      <Text code style={{ fontSize: 11 }}>{record.name}</Text>
                    </Space>
                  ),
                },
                {
                  title: '来源',
                  dataIndex: 'source_type',
                  width: 90,
                  render: value => <Tag color={value === 'url' ? 'cyan' : value === 'route_rule_edit' ? 'blue' : 'default'}>{value}</Tag>,
                },
                {
                  title: '目标',
                  dataIndex: 'target_path',
                  ellipsis: true,
                  render: value => <Text type="secondary">{value}</Text>,
                },
                {
                  title: '操作',
                  width: 150,
                  render: (_, record) => (
                    <Space>
                      <Button size="small" type="primary" onClick={event => { event.stopPropagation(); handleApproveDraft(record) }}>
                        批准
                      </Button>
                      <Button size="small" danger onClick={event => { event.stopPropagation(); handleRejectDraft(record) }}>
                        拒绝
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
            {selectedDraft && (
              <div style={{ marginTop: 12, padding: 14, borderRadius: THEME.radiusMD, border: `1px solid ${THEME.border}`, background: THEME.bgElevated }}>
                <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Text strong>{selectedDraft.title || selectedDraft.name}</Text>
                  <Space>
                    <Tag color={selectedDraft.review?.mode === 'update' ? 'orange' : 'green'}>
                      {selectedDraft.review?.mode === 'update' ? '更新' : '新建'}
                    </Tag>
                    <Tag>{selectedDraft.skill_type}</Tag>
                  </Space>
                </Space>
                <Paragraph style={{ color: THEME.textSecondary, marginBottom: 8 }}>
                  {selectedDraft.description}
                </Paragraph>
                {selectedDraftRouteDiff && (
                  <div style={{ marginBottom: 10, padding: 10, borderRadius: THEME.radiusSM, border: `1px solid ${THEME.borderLight}`, background: THEME.bgPage }}>
                    <Space direction="vertical" size={7} style={{ width: '100%' }}>
                      <Text strong style={{ fontSize: 13 }}>路由变更摘要</Text>
                      {([
                        ['keywords', '关键词'],
                        ['context_keys', '上下文'],
                        ['tools', '触发工具'],
                        ['requires_tools', '必需工具'],
                      ] as const).map(([field, label]) => {
                        const changes = selectedDraftRouteDiff.fields[field]
                        if (!changes.added.length && !changes.removed.length) return null
                        return (
                          <Space key={field} wrap size={[4, 4]}>
                            <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
                            {changes.added.map(item => <Tag key={`add-${field}-${item}`} color="green">+ {item}</Tag>)}
                            {changes.removed.map(item => <Tag key={`remove-${field}-${item}`} color="red">- {item}</Tag>)}
                          </Space>
                        )
                      })}
                    </Space>
                  </div>
                )}
                {selectedDraft.source_url && (
                  <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{selectedDraft.source_url}</Text>
                )}
                {selectedDraft.review?.diff && (
                  <TextArea
                    readOnly
                    value={selectedDraft.review.diff}
                    autoSize={{ minRows: 4, maxRows: 10 }}
                    style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 12, marginBottom: 8 }}
                  />
                )}
                <TextArea
                  readOnly
                  value={selectedDraft.content}
                  autoSize={{ minRows: 8, maxRows: 18 }}
                  style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 12 }}
                />
                <Space style={{ marginTop: 10 }}>
                  <Button type="primary" onClick={() => handleApproveDraft(selectedDraft)} loading={draftLoading}>
                    批准启用
                  </Button>
                  <Button onClick={() => handleRejectDraftToEditor(selectedDraft)} loading={draftLoading}>
                    回填编辑器
                  </Button>
                  <Button danger onClick={() => handleRejectDraft(selectedDraft)} loading={draftLoading}>
                    拒绝
                  </Button>
                </Space>
              </div>
            )}
          </Col>
        </Row>
      </Card>

      <Card
        title="工作流 Bundle"
        extra={<Text type="secondary" style={{ fontSize: 12 }}>内置组合和用户自定义组合都会参与斜杠激活</Text>}
        style={{ ...panelStyle, marginTop: 16 }}
      >
        <div style={{ ...mutedPanelStyle, padding: 14, marginBottom: 14 }}>
          <Row gutter={[10, 10]} align="middle">
            <Col xs={24} md={5}>
              <Input
                value={bundleName}
                onChange={event => setBundleName(event.target.value)}
                placeholder="bundle_name"
                disabled={Boolean(editingBundleName)}
              />
            </Col>
            <Col xs={24} md={7}>
              <Input
                value={bundleDescription}
                onChange={event => setBundleDescription(event.target.value)}
                placeholder="用途说明"
              />
            </Col>
            <Col xs={24} md={9}>
              <Select
                mode="multiple"
                value={bundleSkills}
                onChange={setBundleSkills}
                placeholder="选择要组合的 Skill"
                style={{ width: '100%' }}
                options={packages.map(item => ({ value: item.name, label: `${item.title || item.name} (${item.name})` }))}
              />
            </Col>
            <Col xs={24} md={3}>
              <Button type="primary" loading={bundleLoading} onClick={handleCreateBundle} block>
                {editingBundleName ? '更新' : '创建'}
              </Button>
            </Col>
            <Col xs={24}>
              <TextArea
                value={bundleInstruction}
                onChange={event => setBundleInstruction(event.target.value)}
                autoSize={{ minRows: 2, maxRows: 5 }}
                placeholder="Bundle 附加指令，可选。例如：先检查角色卡，再生成立绘提示词。"
              />
            </Col>
            {editingBundleName && (
              <Col xs={24}>
                <Space>
                  <Tag color="blue">正在编辑 /{editingBundleName}</Tag>
                  <Button size="small" onClick={handleCancelBundleEdit}>取消编辑</Button>
                </Space>
              </Col>
            )}
          </Row>
        </div>
        {bundles.length === 0 ? (
          <Empty description="暂无 Bundle" />
        ) : (
          <Row gutter={[12, 12]}>
            {bundles.map(bundle => (
              <Col xs={24} md={12} xl={8} key={bundle.name}>
                <div style={{ padding: 16, border: `1px solid ${THEME.border}`, borderRadius: THEME.radiusMD, background: THEME.bgElevated, minHeight: 150 }}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                      <Space wrap size={[4, 4]}>
                        <Text strong style={{ color: THEME.textPrimary }}>/{bundle.name}</Text>
                        <Tag color={bundle.source_type === 'user' ? 'blue' : 'default'}>{bundle.source_type || 'builtin'}</Tag>
                        {(bundle.missing_skills || []).length > 0 && <Tag color="error">缺失 {bundle.missing_skills?.length}</Tag>}
                      </Space>
                      <Space size={4}>
                        <Button size="small" onClick={() => handleTestBundle(bundle)}>测试</Button>
                        <Button size="small" disabled={bundle.source_type !== 'user'} onClick={() => handleEditBundle(bundle)}>编辑</Button>
                        <Popconfirm
                          title={`删除 /${bundle.name}？`}
                          description="只会删除用户 Bundle 文件，不会删除其中的 Skill。"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true, loading: bundleLoading }}
                          disabled={bundle.source_type !== 'user'}
                          onConfirm={() => handleDeleteBundle(bundle)}
                        >
                          <Button size="small" danger disabled={bundle.source_type !== 'user'}>删除</Button>
                        </Popconfirm>
                      </Space>
                    </Space>
                    <Text style={{ color: THEME.textSecondary }}>{bundle.description}</Text>
                    <Space size={[4, 4]} wrap>
                      {bundle.skills.map(skill => (
                        <Tag key={skill} color={(bundle.missing_skills || []).includes(skill) ? 'error' : 'default'}>{skill}</Tag>
                      ))}
                    </Space>
                    {bundle.instruction && (
                      <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{bundle.instruction}</Text>
                    )}
                  </Space>
                </div>
              </Col>
            ))}
          </Row>
        )}
      </Card>

      <Drawer
        title={selectedPackage ? `${selectedPackage.title} · ${filePath}` : 'Skill 文件'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={820}
      >
        <TextArea
          readOnly
          value={fileContent}
          autoSize={{ minRows: 28, maxRows: 42 }}
          style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 12 }}
        />
      </Drawer>
    </div>
  )
}

export default SkillManagementPanel
