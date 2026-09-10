/**
 * 写作风格档案工作台。
 *
 * 与后端同一套服务层：提取只出草稿，审核、激活、绑定是分离的步骤，
 * 每一步都要人工确认——界面刻意不提供"一键生效"。
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tabs,
  Typography,
  Upload,
  message,
} from 'antd'
import { useTheme } from '../../constants/theme'
import {
  activateWritingStyleProfile,
  archiveWritingStyleProfile,
  bindProjectWritingStyle,
  exportWritingStyleMarkdown,
  extractWritingStyleFromSource,
  getWritingStyleProfile,
  importWritingStyleMarkdown,
  listCreativeProjects,
  listProfileBoundProjects,
  listProjectWritingStyles,
  listWritingStyleProfiles,
  reviewProseStyleDeviation,
  reviewWritingStyleProfile,
  unbindProjectWritingStyle,
} from '../../api'
import { listSnapshots, importTxt } from '../../api/novelSource'

const { Paragraph, Text } = Typography

const STATUS_COLOR: Record<string, string> = {
  draft: 'default',
  reviewed: 'blue',
  active: 'green',
  archived: 'warning',
}

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  reviewed: '已审核',
  active: '已激活',
  archived: '已归档',
}

interface ProfileRow {
  id: string
  name: string
  status: string
  source_type: string
  version: number
  description?: string
  source_snapshot_id?: string | null
  updated_at?: string
}

function parseList(payload: any): ProfileRow[] {
  const rows = payload?.data ?? payload?.profiles ?? []
  return Array.isArray(rows) ? rows : []
}

export default function WritingStylesPage() {
  const { theme } = useTheme()
  const [rows, setRows] = useState<ProfileRow[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [detail, setDetail] = useState<any>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const [snapshots, setSnapshots] = useState<any[]>([])
  const [projects, setProjects] = useState<any[]>([])
  const [extractOpen, setExtractOpen] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [uploadingTxt, setUploadingTxt] = useState(false)
  const [llmBackends, setLlmBackends] = useState<any[]>([])
  const [extractForm] = Form.useForm()
  const [importForm] = Form.useForm()
  const extractProvider = Form.useWatch('provider', extractForm)

  const [deviationText, setDeviationText] = useState('')
  const [deviationProject, setDeviationProject] = useState<string>('')
  const [deviation, setDeviation] = useState<any>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const payload = await listWritingStyleProfiles(statusFilter ? { status: statusFilter } : {})
      setRows(parseList(payload))
    } catch (error: any) {
      message.error(error?.message || '加载风格档案失败')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    refresh()
    // 来源快照与项目只在打开弹窗时需要，预先加载一次即可。
    Promise.all([
      listSnapshots().catch(() => []),
      listCreativeProjects({ limit: 100 }).catch(() => ({ data: [] })),
    ]).then(([snapPayload, projectPayload]: [any, any]) => {
      setSnapshots(Array.isArray(snapPayload) ? snapPayload : snapPayload?.data || [])
      setProjects(projectPayload?.data || [])
    })
  }, [refresh])

  const openDetail = async (id: string) => {
    try {
      const payload = await getWritingStyleProfile(id)
      setDetail(payload?.data ?? payload)
      setDetailOpen(true)
    } catch (error: any) {
      message.error(error?.message || '读取档案失败')
    }
  }

  const runAction = async (id: string, kind: 'review' | 'activate' | 'archive') => {
    try {
      if (kind === 'review') await reviewWritingStyleProfile(id)
      if (kind === 'activate') await activateWritingStyleProfile(id)
      if (kind === 'archive') await archiveWritingStyleProfile(id)
      const labels = { review: '已提交审核', activate: '已激活', archive: '已归档' }
      message.success(labels[kind])
      refresh()
      if (detail?.id === id) {
        const payload = await getWritingStyleProfile(id)
        setDetail(payload?.data ?? payload)
      }
    } catch (error: any) {
      message.error(error?.message || '操作失败')
    }
  }

  // 本地 TXT 小说一步到位：先转成来源快照，填进下拉，用户点「提取」即可。
  const handleTxtUpload = async (file: File) => {
    setUploadingTxt(true)
    try {
      const created = await importTxt(file, {
        title: file.name.replace(/\.(txt|text|md)$/i, ''),
      })
      setSnapshots((prev) => [created, ...(prev || [])])
      extractForm.setFieldsValue({ snapshot_id: created.id })
      message.success(
        `《${created.title || '未命名'}》已导入为来源快照，点「提取（产出草稿）」继续`
      )
    } catch (error: any) {
      message.error(error?.message || 'TXT 导入失败')
    } finally {
      setUploadingTxt(false)
    }
    return false // 阻止 antd Upload 自动上传
  }

  // 提取弹窗的 Provider/模型下拉：从 AI 连接器配置读可用的 LLM，不再让用户手填。
  useEffect(() => {
    fetch('/api/v1/ai/connectors?provider_type=llm&active_only=true')
      .then((res) => res.json())
      .then((result) => setLlmBackends(result?.connectors || result?.data || result?.items || []))
      .catch(() => setLlmBackends([]))
  }, [])

  // 打开弹窗时预填第一个可用供应商与其默认模型。
  useEffect(() => {
    if (extractOpen && llmBackends.length && !extractForm.getFieldValue('provider')) {
      const first = llmBackends[0]
      extractForm.setFieldsValue({
        provider: first.name || first.provider || '',
        model:
          first.default_model || first.model || first.available_models?.[0] || undefined,
      })
    }
  }, [extractOpen, llmBackends, extractForm])

  const submitExtract = async () => {
    if (extracting) return
    const values = await extractForm.validateFields()
    setExtracting(true)
    try {
      const payload = await extractWritingStyleFromSource({
        snapshot_id: values.snapshot_id,
        name: values.name || '',
        provider: values.provider || '',
        model: values.model || '',
      })
      message.success('已生成风格草稿（draft），审核后才能激活')
      setExtractOpen(false)
      extractForm.resetFields()
      refresh()
      const created = payload?.data ?? payload
      if (created?.id) openDetail(created.id)
    } catch (error: any) {
      message.error(error?.message || '提取失败')
    } finally {
      // 提取是同步长任务（后端等 LLM 跑完才返回），不锁住按钮就能并发触发多次。
      setExtracting(false)
    }
  }

  const submitImport = async () => {
    const values = await importForm.validateFields()
    try {
      const payload = await importWritingStyleMarkdown({
        markdown: values.markdown,
        name: values.name || '',
        source_terms: (values.source_terms || '').split(/[、,，]/).map((t: string) => t.trim()).filter(Boolean),
      })
      message.success('已导入为草稿（draft），审核后才能激活')
      setImportOpen(false)
      importForm.resetFields()
      refresh()
      const created = payload?.data ?? payload
      if (created?.id) openDetail(created.id)
    } catch (error: any) {
      message.error(error?.message || '导入失败')
    }
  }

  const exportMarkdown = async (id: string) => {
    try {
      const payload = await exportWritingStyleMarkdown(id)
      const markdown = payload?.markdown ?? ''
      await navigator.clipboard?.writeText(markdown)
      message.success('Markdown 已复制到剪贴板')
    } catch (error: any) {
      message.error(error?.message || '导出失败')
    }
  }

  const runDeviation = async () => {
    if (!deviationProject || !deviationText.trim()) {
      message.warning('请选择项目并粘贴要审阅的正文')
      return
    }
    try {
      const payload = await reviewProseStyleDeviation({
        project_id: deviationProject,
        text: deviationText,
      })
      setDeviation(payload)
    } catch (error: any) {
      message.error(error?.message || '审阅失败')
    }
  }

  const columns = useMemo(
    () => [
      { title: '名称', dataIndex: 'name', key: 'name' },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (status: string) => (
          <Tag color={STATUS_COLOR[status] || 'default'}>{STATUS_LABEL[status] || status}</Tag>
        ),
      },
      { title: '来源类型', dataIndex: 'source_type', key: 'source_type', width: 160 },
      { title: '版本', dataIndex: 'version', key: 'version', width: 70 },
      {
        title: '操作',
        key: 'actions',
        width: 300,
        render: (_: any, row: ProfileRow) => (
          <Space size="small" wrap>
            <Button size="small" onClick={() => openDetail(row.id)}>
              详情
            </Button>
            <Button
              size="small"
              disabled={row.status !== 'draft'}
              onClick={() => runAction(row.id, 'review')}
            >
              审核
            </Button>
            <Button
              size="small"
              type="primary"
              disabled={row.status !== 'reviewed'}
              onClick={() => runAction(row.id, 'activate')}
            >
              激活
            </Button>
            <Button size="small" onClick={() => exportMarkdown(row.id)}>
              导出
            </Button>
          </Space>
        ),
      },
    ],
    [detail]
  )

  return (
    <div style={{ padding: 24, color: theme.textPrimary }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Card
          title="写作风格档案"
          extra={
            <Space wrap>
              <Select
                allowClear
                placeholder="状态筛选"
                style={{ width: 140 }}
                value={statusFilter || undefined}
                onChange={(value) => setStatusFilter(value || '')}
                options={[
                  { label: '草稿', value: 'draft' },
                  { label: '已审核', value: 'reviewed' },
                  { label: '已激活', value: 'active' },
                  { label: '已归档', value: 'archived' },
                ]}
              />
              <Button onClick={refresh}>刷新</Button>
              <Button onClick={() => setImportOpen(true)}>导入 Markdown</Button>
              <Button type="primary" onClick={() => setExtractOpen(true)}>
                从来源提取
              </Button>
            </Space>
          }
        >
          <Text type="secondary">
            风格只描述“怎么写”的抽象表达机制，不承载剧情与设定。提取出来的恒为草稿，
            必须审核、激活后再绑定到项目才会影响写作。
          </Text>
          <Table
            style={{ marginTop: 12 }}
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={rows}
            columns={columns}
            locale={{ emptyText: <Empty description="还没有风格档案，先从来源提取或导入 Markdown" /> }}
          />
        </Card>

        <Card title="正文偏差审阅（只报告，不改正文）">
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Space wrap>
              <Select
                placeholder="选择项目"
                style={{ width: 240 }}
                value={deviationProject || undefined}
                onChange={setDeviationProject}
                options={projects.map((item: any) => ({ label: item.title || item.id, value: item.id }))}
              />
              <Button onClick={runDeviation}>审阅偏差</Button>
            </Space>
            <Input.TextArea
              rows={4}
              value={deviationText}
              onChange={(e) => setDeviationText(e.target.value)}
              placeholder="粘贴要审阅的正文"
            />
            {deviation && (
              <div>
                {deviation.bound === false ? (
                  <Text type="secondary">{deviation.message || '该项目没有已激活的风格档案'}</Text>
                ) : (
                  (deviation.reports || []).map((report: any) => (
                    <Card key={report.profile_id} size="small" style={{ marginBottom: 8 }}>
                      <Descriptions size="small" column={1} title={report.profile_name}>
                        {report.metrics?.map((metric: any) => (
                          <Descriptions.Item
                            key={metric.metric}
                            label={`${metric.metric}${
                              metric.severity === 'unknown' ? '' : `（${metric.severity}）`
                            }`}
                          >
                            实测 {metric.actual}
                            {metric.expected ? ` / 基线 ${metric.expected}` : ' / 无基线'}
                            {metric.deviation_ratio !== null &&
                            metric.deviation_ratio !== undefined
                              ? ` · 偏差 ${metric.deviation_ratio}`
                              : ''}
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                      {report.constraints?.length > 0 && (
                        <Paragraph style={{ marginBottom: 0 }}>
                          <Text type="secondary">需人工核对的约束：</Text>
                          {report.constraints.join('；')}
                        </Paragraph>
                      )}
                    </Card>
                  ))
                )}
              </div>
            )}
          </Space>
        </Card>
      </Space>

      <Modal
        title="从来源快照提取风格草稿"
        open={extractOpen}
        onCancel={() => {
          if (!extracting) setExtractOpen(false)
        }}
        onOk={submitExtract}
        okText={extracting ? '提取中…' : '提取（产出草稿）'}
        confirmLoading={extracting}
        cancelButtonProps={{ disabled: extracting }}
        closable={!extracting}
        maskClosable={!extracting}
      >
        <Form form={extractForm} layout="vertical">
          <Form.Item
            name="snapshot_id"
            label="来源快照"
            rules={[{ required: true, message: '请选择来源快照或上传 TXT' }]}
          >
            <Select
              placeholder="选择已导入的小说来源"
              options={snapshots.map((item: any) => ({
                label: `${item.title || '未命名'}（${item.source_kind || 'txt'} · ${item.chapter_count || 0} 章）`,
                value: item.id,
              }))}
            />
          </Form.Item>
          <Upload accept=".txt,.text,.md" showUploadList={false} beforeUpload={handleTxtUpload}>
            <Button loading={uploadingTxt}>没有？上传本地 TXT 小说，自动转为来源快照</Button>
          </Upload>
          <Form.Item name="name" label="档案名称">
            <Input placeholder="留空则按来源标题自动生成" />
          </Form.Item>
          <Space>
            <Form.Item name="provider" label="Provider">
              <Select
                placeholder="选择供应商"
                allowClear
                showSearch
                style={{ width: 200 }}
                options={llmBackends.map((item: any) => ({
                  value: item.name || item.provider,
                  label: item.provider_label || item.name || item.provider,
                }))}
                onChange={(value) => {
                  // 切换供应商时模型跟着换成该供应商的默认/可用模型。
                  const backend = llmBackends.find(
                    (item: any) => (item.name || item.provider) === value
                  )
                  extractForm.setFieldsValue({
                    model:
                      backend?.default_model ||
                      backend?.model ||
                      backend?.available_models?.[0] ||
                      undefined,
                  })
                }}
              />
            </Form.Item>
            <Form.Item name="model" label="模型">
              <Select
                placeholder={extractProvider ? '选择模型' : '先选 Provider'}
                allowClear
                showSearch
                style={{ width: 240 }}
                options={(() => {
                  const backend = llmBackends.find(
                    (item: any) => (item.name || item.provider) === extractProvider
                  )
                  // 多数连接器没配 available_models，只有 default_model——并入选项，别让下拉空着。
                  const models = Array.from(
                    new Set(
                      [
                        ...(backend?.available_models || []),
                        backend?.default_model,
                        backend?.model,
                      ].filter(Boolean)
                    )
                  )
                  return models.map((model) => ({ value: model, label: model }))
                })()}
              />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      <Modal
        title="导入 Markdown Skill 草稿"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={submitImport}
        okText="导入（产出草稿）"
        width={720}
      >
        <Form form={importForm} layout="vertical">
          <Form.Item name="name" label="档案名称">
            <Input placeholder="留空则用 Markdown 中的 name" />
          </Form.Item>
          <Form.Item name="source_terms" label="来源专名（用于污染检查，顿号分隔）">
            <Input placeholder="如：活着、余华" />
          </Form.Item>
          <Form.Item
            name="markdown"
            label="Markdown 内容"
            rules={[{ required: true, message: '请粘贴 Markdown' }]}
          >
            <Input.TextArea rows={10} placeholder="粘贴风格档案 Markdown" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="风格档案详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailOpen(false)}>
            关闭
          </Button>,
          <Button
            key="archive"
            disabled={detail?.status === 'archived'}
            onClick={() => detail && runAction(detail.id, 'archive')}
          >
            归档
          </Button>,
        ]}
        width={860}
      >
        {detail && <ProfileDetail profile={detail} projects={projects} />}
      </Modal>
    </div>
  )
}

function BindingPanel({ profile, projects }: { profile: any; projects: any[] }) {
  const [projectId, setProjectId] = useState<string>('')
  const [intensity, setIntensity] = useState<string>('balanced')
  const [stageScope, setStageScope] = useState<string[]>([])
  const [priority, setPriority] = useState<number>(100)
  const [bound, setBound] = useState<any[]>([])
  const [boundProjects, setBoundProjects] = useState<any[]>([])
  const [busy, setBusy] = useState(false)

  const loadBound = useCallback(async (pid: string) => {
    if (!pid) {
      setBound([])
      return
    }
    try {
      const payload = await listProjectWritingStyles(pid)
      setBound(payload?.data || payload || [])
    } catch {
      setBound([])
    }
  }, [])

  useEffect(() => {
    loadBound(projectId)
  }, [projectId, loadBound])

  // 反向视角：这个档案被绑到了哪些项目（解绑或归档前看影响范围）。
  const refreshBoundProjects = useCallback(async () => {
    if (!profile?.id) return
    try {
      const payload = await listProfileBoundProjects(profile.id)
      setBoundProjects(payload?.data || [])
    } catch {
      setBoundProjects([])
    }
  }, [profile?.id])

  useEffect(() => {
    refreshBoundProjects()
  }, [refreshBoundProjects])

  const isBound = bound.some((item: any) => item.id === profile.id)

  const doBind = async () => {
    if (!projectId) {
      message.warning('先选择项目')
      return
    }
    setBusy(true)
    try {
      await bindProjectWritingStyle(projectId, {
        profile_id: profile.id,
        intensity,
        stage_scope: stageScope,
        priority,
      })
      message.success('已绑定到项目')
      await loadBound(projectId)
      await refreshBoundProjects()
    } catch (error: any) {
      message.error(error?.message || '绑定失败')
    } finally {
      setBusy(false)
    }
  }

  const doUnbind = async () => {
    setBusy(true)
    try {
      await unbindProjectWritingStyle(projectId, profile.id)
      message.success('已解绑')
      await loadBound(projectId)
      await refreshBoundProjects()
    } catch (error: any) {
      message.error(error?.message || '解绑失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Text type="secondary">
        绑定后该风格才会影响项目写作：只作为 Context Pack T6 注入，不覆盖正典、动态状态与正文。
      </Text>
      <Space wrap>
        <Select
          placeholder="选择项目"
          style={{ width: 240 }}
          value={projectId || undefined}
          onChange={setProjectId}
          options={projects.map((item: any) => ({ label: item.title || item.id, value: item.id }))}
        />
        <Select
          value={intensity}
          onChange={setIntensity}
          style={{ width: 120 }}
          options={[
            { label: '轻微', value: 'subtle' },
            { label: '适中', value: 'balanced' },
            { label: '强烈', value: 'strong' },
          ]}
        />
        <Select
          mode="tags"
          placeholder="生效阶段（可留空表示全阶段）"
          style={{ width: 260 }}
          value={stageScope}
          onChange={setStageScope}
        />
      </Space>
      <Space wrap>
        <Button type="primary" loading={busy} disabled={isBound} onClick={doBind}>
          {isBound ? '已绑定' : '绑定到项目'}
        </Button>
        <Button danger loading={busy} disabled={!isBound} onClick={doUnbind}>
          解绑
        </Button>
      </Space>
      <div>
        <Text strong>已绑定到：</Text>
        {boundProjects.length === 0 ? (
          <div>
            <Text type="secondary">暂无项目使用该风格</Text>
          </div>
        ) : (
          boundProjects.map((row: any) => (
            <div
              key={row.project_id}
              style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}
            >
              <Tag color={row.enabled ? 'green' : 'default'}>
                {row.project_title || row.project_id}
              </Tag>
              <Text type="secondary">
                {row.intensity}
                {row.stage_scope?.length ? ` · ${row.stage_scope.join('、')}` : ' · 全阶段'}
              </Text>
              <Button
                size="small"
                danger
                disabled={busy}
                onClick={async () => {
                  try {
                    await unbindProjectWritingStyle(row.project_id, profile.id)
                    message.success('已解绑')
                    await loadBound(projectId)
                    await refreshBoundProjects()
                  } catch (error: any) {
                    message.error(error?.message || '解绑失败')
                  }
                }}
              >
                解绑
              </Button>
            </div>
          ))
        )}
      </div>
      {projectId && (
        <div>
          <Text strong>该项目当前生效的风格：</Text>
          {bound.length === 0 ? (
            <div>
              <Text type="secondary">暂无（只有已激活的档案会生效）</Text>
            </div>
          ) : (
            bound.map((item: any) => (
              <div key={item.id}>
                <Tag color={item.id === profile.id ? 'green' : 'default'}>
                  {item.name} · {item.intensity}
                </Tag>
                {item.stage_scope?.length ? (
                  <Text type="secondary">阶段：{item.stage_scope.join('、')}</Text>
                ) : null}
              </div>
            ))
          )}
        </div>
      )}
    </Space>
  )
}

function ProfileDetail({ profile, projects }: { profile: any; projects: any[] }) {
  const dimensions = profile.profile?.dimensions || profile.dimensions || {}
  const provenance = profile.provenance || {}
  const check = provenance.material_check
  const items = [
    {
      key: 'dimensions',
      label: `表达机制（${Object.keys(dimensions).length}）`,
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          {Object.entries(dimensions).map(([name, value]: [string, any]) => (
            <Card key={name} size="small" title={name}>
              <div>{value.value || '-'}</div>
              {value.evidence_summary && (
                <Text type="secondary">依据：{value.evidence_summary}</Text>
              )}
              {value.confidence ? (
                <div>
                  <Text type="secondary">置信度：{value.confidence}</Text>
                </div>
              ) : null}
            </Card>
          ))}
          {Object.keys(dimensions).length === 0 && <Text type="secondary">暂无维度</Text>}
        </Space>
      ),
    },
    {
      key: 'constraints',
      label: '约束与示例',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text strong>新造示例：</Text>
            {(profile.profile?.new_examples || []).join(' / ') || '-'}
          </div>
          <div>
            <Text strong>反模板约束：</Text>
            {(profile.profile?.anti_template_constraints || []).join(' / ') || '-'}
          </div>
          <div>
            <Text strong>禁止带出的来源特征：</Text>
            {(profile.profile?.prohibited_source_material || []).join(' / ') || '-'}
          </div>
        </Space>
      ),
    },
    {
      key: 'binding',
      label: '项目绑定',
      children: <BindingPanel profile={profile} projects={projects} />,
    },
    {
      key: 'provenance',
      label: '溯源与检查',
      children: (
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="状态">{STATUS_LABEL[profile.status] || profile.status}</Descriptions.Item>
          <Descriptions.Item label="来源类型">{profile.source_type}</Descriptions.Item>
          <Descriptions.Item label="来源快照">{profile.source_snapshot_id || '-'}</Descriptions.Item>
          <Descriptions.Item label="样本字数">{provenance.sample_chars ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="材料检查">
            {check ? (
              check.ok ? (
                <Tag color="green">无来源材料泄漏</Tag>
              ) : (
                <Tag color="red">存在违规，需改写后才能审核</Tag>
              )
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="校验和">
            <Text code>{profile.checksum}</Text>
          </Descriptions.Item>
        </Descriptions>
      ),
    },
  ]
  return <Tabs items={items} />
}
