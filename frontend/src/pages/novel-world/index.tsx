import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Input,
  message,
  Modal,
  Radio,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import {
  CheckOutlined,
  FileTextOutlined,
  InboxOutlined,
  RobotOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  applyRun,
  decideCandidates,
  deriveProject,
  detectContradictions,
  extractWorld,
  getExtractionRun,
  getSnapshot,
  importTxt,
  indexChunks,
  listCandidates,
  listSnapshots,
  planDomains,
  reconcileRun,
  searchChunks,
  syncChapters,
  type ApplyResult,
  type ChunkIndexResult,
  type ChunkSearchResult,
  type ContradictionReport,
  type DerivationKind,
  type DomainPlan,
  type ExtractResult,
  type NovelSourceSnapshot,
  type ReconcileReport,
  type WorldCandidate,
} from '../../api/novelSource'
import { listConnectors } from '../../api'
import EvidenceList from '../../components/world/EvidenceList'

const { Title, Text, Paragraph } = Typography

const STATUS_LABEL: Record<string, string> = {
  detected: '存在',
  not_detected: '不存在',
  uncertain: '不确定',
  user_requested: '用户指定',
}

const STATUS_COLOR: Record<string, string> = {
  detected: 'green',
  not_detected: 'default',
  uncertain: 'orange',
  user_requested: 'blue',
}

const ORIGIN_LABEL: Record<string, string> = {
  original: '原文陈述',
  ai_inferred: '模型推断',
  ai_draft: 'AI 创作',
  // 证据逐字命中项目大纲，而不是某部真实作品：不能显示成「原文陈述」。
  outline: '来自大纲',
}

const CHAPTER_HEADING = /^\s*第[0-9零一二两三四五六七八九十百千万]+[章节卷回][^\n]*$/

function splitChapters(text: string): { title: string; content: string }[] {
  const lines = text.split(/\r?\n/)
  const chapters: { title: string; content: string[] }[] = []
  let current: { title: string; content: string[] } | null = null
  for (const line of lines) {
    if (CHAPTER_HEADING.test(line)) {
      if (current) chapters.push(current)
      current = { title: line.trim(), content: [] }
    } else if (current) {
      current.content.push(line)
    }
  }
  if (current) chapters.push(current)
  const parsed = chapters.map((item) => ({ title: item.title, content: item.content.join('\n').trim() }))
  const withContent = parsed.filter((item) => item.content)
  if (withContent.length) return withContent
  const trimmed = text.trim()
  return trimmed ? [{ title: '新章节', content: trimmed }] : []
}

export default function NovelWorldPage() {
  const [snapshots, setSnapshots] = useState<NovelSourceSnapshot[]>([])
  const [snapshot, setSnapshot] = useState<NovelSourceSnapshot | null>(null)
  const [importing, setImporting] = useState(false)
  const [plan, setPlan] = useState<DomainPlan | null>(null)
  const [planning, setPlanning] = useState(false)
  const [enabled, setEnabled] = useState<string[]>([])
  const [extracting, setExtracting] = useState(false)
  const [extractResult, setExtractResult] = useState<ExtractResult | null>(null)
  const [candidates, setCandidates] = useState<WorldCandidate[]>([])
  const [deciding, setDeciding] = useState(false)
  const [applyResult, setApplyResult] = useState<ApplyResult | null>(null)
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [model, setModel] = useState('')
  // LLM 连接器（与立绘同源：/ai/connectors?provider_type=llm）
  const [provider, setProvider] = useState('')
  const [llmBackends, setLlmBackends] = useState<any[]>([])

  const [indexing, setIndexing] = useState(false)
  const [indexResult, setIndexResult] = useState<ChunkIndexResult | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<ChunkSearchResult[]>([])

  const [reconcile, setReconcile] = useState<ReconcileReport | null>(null)
  const [reconciling, setReconciling] = useState(false)
  const [contradictions, setContradictions] = useState<ContradictionReport | null>(null)
  const [detecting, setDetecting] = useState(false)

  const [derivationKind, setDerivationKind] = useState<DerivationKind>('continuation')
  const [deriving, setDeriving] = useState(false)

  const [syncOpen, setSyncOpen] = useState(false)
  const [syncText, setSyncText] = useState('')
  const [syncing, setSyncing] = useState(false)

  const refreshSnapshots = async () => {
    const items = await listSnapshots()
    setSnapshots(items)
    if (items.length && !snapshot) {
      await selectSnapshot(items[0].id)
    }
  }

  const selectSnapshot = async (id: string) => {
    const detail = await getSnapshot(id)
    setSnapshot(detail)
    setPlan(null)
    setExtractResult(null)
    setCandidates([])
    setApplyResult(null)
    setEnabled([])
    setReconcile(null)
    setContradictions(null)
  }

  // 支持从其它入口带上下文进入：?snapshot_id=xxx&run_id=xxx&project_id=xxx 自动加载。
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const snapshotId = params.get('snapshot_id')
    const runId = params.get('run_id')
    const projectId = params.get('project_id')
    refreshSnapshots().then(async () => {
      if (snapshotId) {
        await selectSnapshot(snapshotId)
      }
      if (runId) {
        try {
          const run = await getExtractionRun(runId)
          if (run.snapshot_id && run.snapshot_id !== snapshotId) {
            await selectSnapshot(run.snapshot_id)
          }
          setExtractResult(run)
          await loadCandidates(runId)
          await loadReconcile(runId)
        } catch (error) {
          message.error((error as Error).message)
        }
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    listConnectors({ provider_type: 'llm', active_only: true })
      .then((resp: any) => {
        const items = (resp?.connectors || resp?.data || resp?.items || []) as any[]
        setLlmBackends(items)
        const first = items[0]
        if (first && !provider) {
          setProvider(first.name || first.provider || '')
          setModel(first.default_model || first.model || first.available_models?.[0] || '')
        }
      })
      .catch(() => setLlmBackends([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const doImport = async (file: File, sourceStatus: string) => {
    setImporting(true)
    try {
      const created = await importTxt(file, {
        title: file.name.replace(/\.[^.]+$/, ''),
        sourceStatus,
      })
      message.success('导入成功，已生成来源快照')
      await refreshSnapshots()
      await selectSnapshot(created.id)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setImporting(false)
    }
  }

  const doPlan = async () => {
    if (!snapshot) return
    setPlanning(true)
    try {
      const result = await planDomains(snapshot.id, {
        provider: provider || undefined,
        model: model || undefined,
      })
      setPlan(result)
      setEnabled(result.recommended)
      setExtractResult(null)
      setCandidates([])
      setApplyResult(null)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setPlanning(false)
    }
  }

  const doExtract = async () => {
    if (!snapshot) return
    setExtracting(true)
    try {
      const result = await extractWorld(snapshot.id, {
        domains: enabled,
        domain_plan: plan?.domains,
        provider: provider || undefined,
        model: model || undefined,
      })
      setExtractResult(result)
      await loadCandidates(result.run_id)
      await loadReconcile(result.run_id)
      if (result.status === 'failed') {
        message.error('提取失败，请查看域状态')
      } else if (result.status === 'partial') {
        message.warning('部分域提取失败，其余候选已保留')
      } else {
        message.success(`提取完成，共 ${result.candidate_count} 条候选`)
      }
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setExtracting(false)
    }
  }

  const loadCandidates = async (runId: string) => {
    setLoadingCandidates(true)
    try {
      setCandidates(await listCandidates(runId))
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setLoadingCandidates(false)
    }
  }

  const loadReconcile = async (runId: string) => {
    setReconciling(true)
    try {
      setReconcile(await reconcileRun(runId))
    } catch (error) {
      // 调和是只读提示，失败不应阻塞候选审阅。
      setReconcile(null)
    } finally {
      setReconciling(false)
    }
  }

  const doDetect = async () => {
    if (!extractResult) return
    setDetecting(true)
    try {
      setContradictions(
        await detectContradictions(extractResult.run_id, {
          provider: provider || undefined,
          model: model || undefined,
        }),
      )
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setDetecting(false)
    }
  }

  const pending = candidates.filter((item) => item.status === 'pending')
  const [decisions, setDecisions] = useState<Record<string, 'accept' | 'ignore'>>({})

  const doDecide = async () => {
    if (!extractResult) return
    setDeciding(true)
    try {
      const payload = pending.map((item) => ({
        candidate_id: item.id,
        action: decisions[item.id] ?? 'accept',
      }))
      await decideCandidates(extractResult.run_id, payload)
      message.success('决策已保存')
      await loadCandidates(extractResult.run_id)
      setDecisions({})
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setDeciding(false)
    }
  }

  const doApply = async () => {
    if (!extractResult) return
    try {
      const result = await applyRun(extractResult.run_id)
      setApplyResult(result)
      message.success(`已写入项目：角色 ${result.characters_written} 个，世界事实 ${result.world_assets_written} 条`)
      await refreshSnapshots()
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const doIndex = async () => {
    if (!snapshot) return
    setIndexing(true)
    setIndexResult(null)
    try {
      const result = await indexChunks(snapshot.id, {
        provider: provider || undefined,
        model: model || undefined,
      })
      setIndexResult(result)
      message.success(`索引完成：${result.indexed}/${result.total} 块已向量化`)
      await selectSnapshot(snapshot.id)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setIndexing(false)
    }
  }

  const doSearch = async () => {
    if (!snapshot || !searchQuery.trim()) return
    setSearching(true)
    try {
      const results = await searchChunks(snapshot.id, { query: searchQuery.trim(), top_k: 10 })
      setSearchResults(results)
      if (!results.length) {
        message.info('未检索到相关文本块')
      }
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const doDerive = async () => {
    if (!snapshot) return
    setDeriving(true)
    try {
      const result = await deriveProject(snapshot.id, { derivation_kind: derivationKind })
      const label = { adaptation: '改编', continuation: '续写', fan_work: '同人' }[result.derivation_kind]
      message.success(
        `已创建${label}项目：带入原作事实 ${result.source_canon_assets} 条、角色 ${result.characters_linked} 个`,
      )
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setDeriving(false)
    }
  }

  const doSync = async () => {
    if (!snapshot) return
    const chapters = splitChapters(syncText)
    if (!chapters.length) {
      message.warning('请粘贴新章节内容')
      return
    }
    setSyncing(true)
    try {
      const updated = await syncChapters(snapshot.id, chapters)
      message.success(`已追加，当前共 ${updated.chapter_count} 章`)
      setSyncOpen(false)
      setSyncText('')
      await selectSnapshot(snapshot.id)
      await refreshSnapshots()
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setSyncing(false)
    }
  }

  const domainsByGroup = useMemo(() => {
    const rows = (plan?.domains ?? []).map((item) => ({ ...item, key: item.domain }))
    return {
      extractable: rows.filter((item) => item.extractable),
      detectOnly: rows.filter((item) => !item.extractable),
    }
  }, [plan])

  const candidateColumns: ColumnsType<WorldCandidate> = [
    ...(extractResult?.mode === 'delta'
      ? [
          {
            title: '本次',
            key: 'this_run',
            width: 70,
            render: (_: unknown, record: WorldCandidate) =>
              record.run_id === extractResult.run_id ? (
                <Tag color="green">新增</Tag>
              ) : record.last_run_id === extractResult.run_id ? (
                <Tag color="blue">更新</Tag>
              ) : null,
          },
        ]
      : []),
    { title: '名称', dataIndex: 'entity_name', key: 'entity_name' },
    {
      title: '来源',
      dataIndex: 'origin',
      key: 'origin',
      render: (value: string) => {
        const label = ORIGIN_LABEL[value] ?? value
        if (value === 'outline') {
          return (
            <Tooltip title="证据逐字命中你的项目大纲：可回溯，但不是某部真实作品的原文">
              <Tag color="blue">{label}</Tag>
            </Tooltip>
          )
        }
        return <Tag color={value === 'original' ? 'green' : 'orange'}>{label}</Tag>
      },
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 100,
      render: (value: number) => `${Math.round(value * 100)}%`,
    },
    { title: '证据', dataIndex: 'evidence', key: 'evidence', width: 80, render: (v: unknown[]) => `${v?.length ?? 0} 条` },
    {
      title: '摘要',
      dataIndex: 'payload',
      key: 'summary',
      render: (payload: WorldCandidate['payload']) => (
        <Text type="secondary" ellipsis style={{ maxWidth: 360 }}>
          {payload?.summary ?? ''}
        </Text>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={3} style={{ marginBottom: 4 }}>
        小说世界提取
      </Title>
      <Paragraph type="secondary">
        来源快照 → 模块判断 → 提取 → 证据预览 → 确认写入项目。原作始终只读。
      </Paragraph>

      <Steps
        size="small"
        current={snapshot ? (plan ? (extractResult ? 3 : 2) : 1) : 0}
        items={[
          { title: '导入来源', icon: <FileTextOutlined /> },
          { title: '模块判断', icon: <SearchOutlined /> },
          { title: '提取候选', icon: <RobotOutlined /> },
          { title: '审阅写入', icon: <CheckOutlined /> },
        ]}
        style={{ marginBottom: 24 }}
      />

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <aside style={{ width: 280, flexShrink: 0 }}>
          <Card
            size="small"
            title="1. 来源快照"
            style={{ marginBottom: 16 }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              <Select
                placeholder="选择已有来源快照"
                style={{ width: '100%' }}
                value={snapshot?.id}
                onChange={selectSnapshot}
                onDropdownVisibleChange={(open) => {
                  if (open) refreshSnapshots()
                }}
                options={snapshots.map((item) => ({
                  value: item.id,
                  label: `${item.title}（${item.chapter_count} 章 · ${item.source_kind === 'txt' ? 'TXT' : '书架'}）`,
                }))}
              />
              <Space wrap>
                <Upload
                  showUploadList={false}
                  accept=".txt,.text,.md"
                  customRequest={({ file }) => {
                    doImport(file as File, 'unknown')
                  }}
                >
                  <Button size="small" icon={<InboxOutlined />} loading={importing}>
                    上传 TXT
                  </Button>
                </Upload>
                <Button size="small" onClick={refreshSnapshots}>
                  刷新
                </Button>
              </Space>
              {snapshot && (
                <div style={{ fontSize: 12, color: '#595959', lineHeight: 1.8 }}>
                  <div style={{ color: '#1f2329', fontWeight: 600 }}>{snapshot.title}</div>
                  <div>
                    {snapshot.author || '未知'} · {snapshot.chapter_count} 章 · {snapshot.char_count} 字 ·{' '}
                    {snapshot.source_status === 'completed'
                      ? '完本'
                      : snapshot.source_status === 'serial'
                        ? '连载'
                        : '未知'}{' '}
                    · {snapshot.encoding}
                  </div>
                  <div>
                    索引：
                    {snapshot.indexing_status === 'indexed'
                      ? '已建立'
                      : snapshot.indexing_status === 'pending'
                        ? '未开始'
                        : snapshot.indexing_status === 'skipped'
                          ? '已跳过'
                          : snapshot.indexing_status}
                    <Button
                      type="link"
                      size="small"
                      loading={indexing}
                      onClick={doIndex}
                      style={{ padding: 0, marginLeft: 6 }}
                    >
                      建立索引
                    </Button>
                  </div>
                </div>
              )}
              {snapshot?.source_status === 'completed' && (
                <div style={{ fontSize: 12, color: '#8c8c8c' }}>
                  完本来源可开派生项目：原作已确认事实与角色作为只读参考层带入，新写入与原作分层。
                  <Space wrap style={{ marginTop: 6 }}>
                    <Select
                      size="small"
                      style={{ width: 110 }}
                      value={derivationKind}
                      onChange={(value: DerivationKind) => setDerivationKind(value)}
                      options={[
                        { value: 'continuation', label: '续写项目' },
                        { value: 'adaptation', label: '改编项目' },
                        { value: 'fan_work', label: '同人项目' },
                      ]}
                    />
                    <Button size="small" loading={deriving} onClick={doDerive}>
                      创建派生项目
                    </Button>
                  </Space>
                </div>
              )}
              {snapshot?.source_status === 'serial' && (
                <div style={{ fontSize: 12, color: '#8c8c8c' }}>
                  连载来源可追加新章节；已导入章节与既有证据锚点保持不变。
                  <div style={{ marginTop: 6 }}>
                    <Button size="small" onClick={() => setSyncOpen(true)}>
                      追加章节
                    </Button>
                  </div>
                </div>
              )}
            </Space>
          </Card>
          <Card
            title="2. 模块判断"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" disabled={!snapshot} loading={planning} onClick={doPlan}>
            AI 判断模块
          </Button>
        }
      >
        {!plan ? (
          <Empty description="先导入来源，再让 AI 逐模块判断是否存在可提取内容" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            <Alert
              type="info"
              showIcon
              message="每个模块独立判断，逐个勾选要提取的模块（悬停状态看理由）。"
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {domainsByGroup.extractable.map((item) => (
                <div key={item.domain} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Checkbox
                    checked={enabled.includes(item.domain)}
                    onChange={(e) =>
                      setEnabled((prev) =>
                        e.target.checked
                          ? [...prev, item.domain]
                          : prev.filter((id) => id !== item.domain),
                      )
                    }
                  />
                  <Text style={{ fontSize: 12, flex: 1 }}>{item.label}</Text>
                  <Tooltip title={item.reason}>
                    <Tag color={STATUS_COLOR[item.status]} style={{ marginInlineEnd: 0 }}>
                      {STATUS_LABEL[item.status] ?? item.status}
                    </Tag>
                  </Tooltip>
                </div>
              ))}
            </div>
            {domainsByGroup.detectOnly.length > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                仅检测、暂不提取：{domainsByGroup.detectOnly.map((item) => item.label).join('、')}
              </Text>
            )}
            <Divider style={{ margin: '4px 0' }} />
            <Text strong style={{ fontSize: 12 }}>
              AI 选择
            </Text>
            <Select
              size="small"
              style={{ width: '100%' }}
              placeholder="LLM 供应商"
              value={provider || undefined}
              onChange={(value) => {
                setProvider(value)
                const backend = llmBackends.find(
                  (item: any) => (item.name || item.provider) === value,
                )
                setModel(
                  backend?.default_model || backend?.model || backend?.available_models?.[0] || '',
                )
              }}
              options={llmBackends.map((item: any) => ({
                value: item.name || item.provider,
                label: item.provider_label || item.name || item.provider,
              }))}
            />
            <Select
              size="small"
              style={{ width: '100%' }}
              placeholder="模型（留空用默认）"
              value={model || undefined}
              onChange={setModel}
              allowClear
              options={Array.from(
                new Set(
                  (() => {
                    const backend = llmBackends.find(
                      (item: any) => (item.name || item.provider) === provider,
                    )
                    return backend?.available_models?.length
                      ? backend.available_models
                      : [backend?.default_model || backend?.model || '']
                  })().filter(Boolean) as string[],
                ),
              ).map((value) => ({ value, label: value }))}
            />
            <Button type="primary" block disabled={!enabled.length} loading={extracting} onClick={doExtract}>
              提取所选模块{enabled.length ? `（${enabled.length}）` : ''}
            </Button>
          </Space>
        )}
      </Card>
      </aside>

      <div style={{ flex: 1, minWidth: 0 }}>
      <Card
        title="检索原文证据"
        style={{ marginBottom: 16 }}
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            向量索引会提升长文本召回；无索引时自动回退精确检索
          </Text>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Input
              style={{ width: 320 }}
              placeholder="输入关键词或语义查询，如「主角第一次觉醒」"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={doSearch}
            />
            <Button type="primary" icon={<SearchOutlined />} loading={searching} disabled={!snapshot || !searchQuery.trim()} onClick={doSearch}>
              检索证据
            </Button>
          </Space>
          {searchResults.length > 0 && (
            <Table
              size="small"
              rowKey="chunk_id"
              pagination={false}
              dataSource={searchResults}
              columns={[
                {
                  title: '块',
                  dataIndex: 'chunk_ordinal',
                  key: 'chunk_ordinal',
                  width: 60,
                  render: (value: number) => `#${value}`,
                },
                {
                  title: '召回',
                  dataIndex: 'retrieval',
                  key: 'retrieval',
                  width: 80,
                  render: (value: string) => (
                    <Tag color={value === 'hybrid' ? 'blue' : 'default'}>
                      {value === 'hybrid' ? '混合' : '精确'}
                    </Tag>
                  ),
                },
                {
                  title: '得分',
                  dataIndex: 'score',
                  key: 'score',
                  width: 80,
                  render: (value: number) => `${(value * 100).toFixed(1)}%`,
                },
                {
                  title: '原文',
                  dataIndex: 'content',
                  key: 'content',
                  render: (value: string, record: ChunkSearchResult) => (
                    <Text type="secondary" ellipsis style={{ maxWidth: 480 }}>
                      {value || `块 ${record.chunk_ordinal}`}
                    </Text>
                  ),
                },
                {
                  title: '偏移',
                  key: 'offset',
                  width: 120,
                  render: (_, record: ChunkSearchResult) => `${record.start_offset}-${record.end_offset}`,
                },
              ]}
            />
          )}
        </Space>
      </Card>

      {extractResult && (
        <Card
          title={`3. 候选预览（${extractResult.status}）`}
          style={{ marginBottom: 16 }}
          extra={
            <Tag color={extractResult.status === 'success' ? 'green' : extractResult.status === 'partial' ? 'orange' : 'red'}>
              {extractResult.status}
            </Tag>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            {extractResult.failures.length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="部分域失败"
                description={extractResult.failures.map((f) => `${f.domain}: ${f.error}`).join('；')}
              />
            )}
            {extractResult.mode === 'delta' && (
              <Alert
                type="info"
                showIcon
                message={`增量提取：本次新增 ${extractResult.candidate_count} 条候选，更新 ${extractResult.updated_count} 条既有候选的证据`}
              />
            )}
            {reconcile && (
              <>
                <Alert
                  type={reconcile.conflict_count ? 'warning' : 'success'}
                  showIcon
                  message={
                    reconcile.conflict_count
                      ? `检测到 ${reconcile.conflict_count} 处需要复核的冲突`
                      : '未检测到跨模块冲突'
                  }
                  description="调和只给出提示，不会自动合并候选；请逐条确认后再写入项目。"
                  action={
                    <Button
                      size="small"
                      loading={reconciling}
                      onClick={() => extractResult && loadReconcile(extractResult.run_id)}
                    >
                      重新检查
                    </Button>
                  }
                />
                {reconcile.duplicate_groups.length > 0 && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 0 }}
                    message="语义判断重复组"
                    description={
                      contradictions ? (
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          {contradictions.groups.map((group, index) => {
                            const verdict = group.verdict
                            const label =
                              verdict === 'consistent'
                                ? '同一实体'
                                : verdict === 'conflicting'
                                  ? '描述矛盾'
                                  : '不同实体'
                            const color =
                              verdict === 'conflicting'
                                ? 'red'
                                : verdict === 'consistent'
                                  ? 'green'
                                  : 'default'
                            return (
                              <div key={index}>
                                <Tag color={color}>{label}</Tag>
                                <Text>{group.candidates.map((row) => row.entity_name).join(' / ')}</Text>
                                {group.reason ? (
                                  <Text type="secondary">：{group.reason}</Text>
                                ) : null}
                              </div>
                            )
                          })}
                        </Space>
                      ) : (
                        '调用模型判断这些重复组是同一实体、描述矛盾还是不同实体（会产生一次模型调用）。'
                      )
                    }
                    action={
                      <Button size="small" loading={detecting} onClick={doDetect}>
                        {contradictions ? '重新判断' : '判断'}
                      </Button>
                    }
                  />
                )}
                {reconcile.duplicate_groups.map((group) => (
                  <Alert
                    key={group.candidates.map((row) => row.id).join('-')}
                    type="warning"
                    style={{ marginBottom: 0 }}
                    message={
                      <Space wrap size={4}>
                        {group.candidates.map((row) => (
                          <Tag key={row.id} color="orange">
                            {row.domain_label}·{row.entity_name}
                          </Tag>
                        ))}
                      </Space>
                    }
                    description={group.reason}
                  />
                ))}
                {reconcile.evidence_overlaps.map((item) => (
                  <Alert
                    key={`${item.chunk_id}-${item.start_offset}`}
                    type="info"
                    style={{ marginBottom: 0 }}
                    message={`证据重叠：${item.candidates.map((row) => row.entity_name).join(' / ')}`}
                    description={`「${item.quote}」——${item.reason}`}
                  />
                ))}
                {reconcile.timeline.length > 0 && (
                  <Alert
                    type="info"
                    style={{ marginBottom: 0 }}
                    message="历史事件时序（按相对时间排序）"
                    description={
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        {reconcile.timeline.map((item) => (
                          <Text key={item.candidate_id} type="secondary" style={{ fontSize: 12 }}>
                            {item.entity_name}：{item.raw || '未填写时间'}
                            {item.parsed.kind === 'relative'
                              ? '（已解析，可排序）'
                              : '（无法解析，需人工核对）'}
                          </Text>
                        ))}
                      </Space>
                    }
                  />
                )}
              </>
            )}
            <Collapse
              items={extractResult.domains.map((item) => ({
                key: item.domain,
                label: `${item.label}（${item.items} 条）`,
                children: (
                  <Table
                    size="small"
                    rowKey="id"
                    pagination={false}
                    loading={loadingCandidates}
                    dataSource={candidates.filter((c) => c.domain === item.domain)}
                    columns={[
                      ...candidateColumns,
                      {
                        title: '决策',
                        key: 'decision',
                        width: 170,
                        render: (_, record) =>
                          record.status !== 'pending' ? (
                            <Tag color={record.status === 'accepted' ? 'green' : 'default'}>
                              {record.status === 'accepted' ? '已接受' : '已忽略'}
                            </Tag>
                          ) : (
                            <Radio.Group
                              size="small"
                              value={decisions[record.id] ?? 'accept'}
                              onChange={(e) =>
                                setDecisions((prev) => ({ ...prev, [record.id]: e.target.value }))
                              }
                            >
                              <Radio.Button value="accept">接受</Radio.Button>
                              <Radio.Button value="ignore">忽略</Radio.Button>
                            </Radio.Group>
                          ),
                      },
                    ]}
                    expandable={{
                      expandedRowRender: (record) => (
                        <EvidenceList items={record.evidence} variant="alert" />
                      ),
                    }}
                  />
                ),
              }))}
            />
            <Space>
              <Button disabled={!pending.length} loading={deciding} onClick={doDecide}>
                保存决策
              </Button>
              <Button type="primary" disabled={!pending.length} loading={deciding} onClick={doDecide}>
                全部接受
              </Button>
            </Space>
            {applyResult && (
              <Alert
                type="success"
                showIcon
                message={`已写入项目 ${applyResult.project_id}`}
                description={`角色 ${applyResult.characters_written} 个，世界事实 ${applyResult.world_assets_written} 条`}
              />
            )}
          </Space>
        </Card>
      )}

      {extractResult && (
        <Card title="4. 确认写入">
          <Space>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              disabled={deciding}
              onClick={async () => {
                if (!extractResult) return
                // 先把全部待确认候选接受，再统一写入，保证“一键闭环”。
                const payload = pending.map((item) => ({ candidate_id: item.id, action: 'accept' as const }))
                if (payload.length) {
                  await decideCandidates(extractResult.run_id, payload)
                  await loadCandidates(extractResult.run_id)
                }
                await doApply()
              }}
            >
              确认写入项目
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              角色进入角色库并建立项目关联；地点、势力、历史事件写入锁定的世界事实卡。
            </Text>
          </Space>
        </Card>
      )}

      <Modal
        title="追加连载章节"
        open={syncOpen}
        onOk={doSync}
        okText="追加"
        confirmLoading={syncing}
        onCancel={() => {
          setSyncOpen(false)
          setSyncText('')
        }}
        width={640}
      >
        <Text type="secondary" style={{ fontSize: 12 }}>
          粘贴新章节原文，按「第X章」标题行自动拆分；没有标题行时整段作为单章追加。
        </Text>
        <Input.TextArea
          rows={12}
          style={{ marginTop: 12 }}
          value={syncText}
          onChange={(e) => setSyncText(e.target.value)}
          placeholder={'第二章 旧账\n沈青砚在灯下翻账册……\n\n第三章 雪原\n……'}
        />
      </Modal>
        </div>
      </div>
    </div>
  )
}
