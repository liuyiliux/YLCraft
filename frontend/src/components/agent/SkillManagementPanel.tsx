import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Input,
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
  createAgentSkillDraft,
  importAgentSkillDraftUrl,
  listAgentSkills,
  listAgentSkillDrafts,
  listAgentSkillPackageFiles,
  listAgentSkillPackageIndex,
  previewAgentSkillRoute,
  readAgentSkillPackageFile,
  rejectAgentSkillDraft,
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
  instruction: string
  source_path: string
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

export function SkillManagementPanel() {
  const { theme: THEME } = useTheme()
  const { message } = AntApp.useApp()
  const [loading, setLoading] = useState(false)
  const [packages, setPackages] = useState<SkillPackageIndexItem[]>([])
  const [bundles, setBundles] = useState<SkillBundleIndexItem[]>([])
  const [skillMetrics, setSkillMetrics] = useState<Record<string, AgentSkillMetric>>({})
  const [selectedName, setSelectedName] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [fileLoading, setFileLoading] = useState(false)
  const [files, setFiles] = useState<SkillPackageFileItem[]>([])
  const [fileContent, setFileContent] = useState('')
  const [filePath, setFilePath] = useState('SKILL.md')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [routeMessage, setRouteMessage] = useState('帮我给角色生成表情包和动作姿势')
  const [routeContext, setRouteContext] = useState('{\n  "character_id": "char-1"\n}')
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeResult, setRouteResult] = useState<RoutePreviewItem[]>([])
  const [routeError, setRouteError] = useState('')
  const [drafts, setDrafts] = useState<SkillDraftItem[]>([])
  const [draftUrl, setDraftUrl] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const [draftLoading, setDraftLoading] = useState(false)
  const [selectedDraft, setSelectedDraft] = useState<SkillDraftItem | null>(null)

  const selectedPackage = useMemo(
    () => packages.find(item => item.name === selectedName) || null,
    [packages, selectedName],
  )

  const categories = useMemo(() => {
    const values = Array.from(new Set(packages.map(item => item.category).filter(Boolean))).sort()
    return [{ value: 'all', label: '全部分类' }, ...values.map(value => ({ value, label: value }))]
  }, [packages])

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
      const draftData = await listAgentSkillDrafts('pending')
      const nextPackages = data.packages || []
      setPackages(nextPackages)
      setBundles(data.bundles || [])
      setDrafts(draftData.drafts || [])
      setSkillMetrics(
        Object.fromEntries((skills || []).map((item: AgentSkillMetric) => [item.name, item])),
      )
      setSelectedName(current => current || nextPackages[0]?.name || '')
    } catch (err: any) {
      message.error(err?.message || '加载 Skill 包失败')
    } finally {
      setLoading(false)
    }
  }, [message])

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

  const handlePreviewRoute = async () => {
    setRouteLoading(true)
    setRouteError('')
    try {
      const data = await previewAgentSkillRoute({
        message: routeMessage,
        context: parseJsonObject(routeContext),
        max_skills: 8,
      })
      setRouteResult(data.routes || [])
    } catch (err: any) {
      setRouteError(err?.message || '路由预览失败，请检查上下文 JSON')
      setRouteResult([])
    } finally {
      setRouteLoading(false)
    }
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
      message.error(err?.message || '导入失败')
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

  const handleApproveDraft = async (draft: SkillDraftItem) => {
    setDraftLoading(true)
    try {
      await approveAgentSkillDraft(draft.id)
      await Promise.all([refreshDrafts(), loadIndex()])
      setSelectedDraft(null)
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

  const metricStyle: CSSProperties = {
    padding: '12px 14px',
    borderRadius: 8,
    background: THEME.bgElevated,
    border: `1px solid ${THEME.border}`,
    minHeight: 72,
  }

  return (
    <div>
      <Card
        style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginBottom: 16 }}
        styles={{ body: { padding: 18 } }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <Title level={5} style={{ color: THEME.textPrimary, marginBottom: 6 }}>
              Agent Skill 包管理
            </Title>
            <Paragraph style={{ color: THEME.textSecondary, marginBottom: 0, maxWidth: 760 }}>
              项目工具负责执行动作，Skill 包负责定义何时使用、如何组合和如何验收。默认包来自后端文件系统，支持斜杠激活和工作流 bundle。
            </Paragraph>
          </div>
          <Space>
            <Button icon={<BranchesOutlined />} onClick={handlePreviewRoute} loading={routeLoading}>
              预览路由
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadIndex} loading={loading}>
              刷新
            </Button>
          </Space>
        </div>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={15}>
          <Card
            title={
              <Space>
                <FileTextOutlined />
                <span>文件化 Skill</span>
                <Badge count={filteredPackages.length} style={{ backgroundColor: THEME.primary }} />
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
            style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
          >
            {loading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : filteredPackages.length === 0 ? (
              <Empty description="没有匹配的 Skill 包" />
            ) : (
              <Table
                rowKey="name"
                size="small"
                dataSource={filteredPackages}
                pagination={{ pageSize: 10, showSizeChanger: false }}
                rowClassName={record => record.name === selectedName ? 'ant-table-row-selected' : ''}
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
                        <Text strong style={{ color: THEME.textPrimary }}>{record.title || record.name}</Text>
                        <Text code style={{ fontSize: 11 }}>{record.name}</Text>
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
                      return <Tag color={metric?.is_builtin ? 'green' : 'default'}>{metric ? '文件启用' : '待同步'}</Tag>
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
            style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginBottom: 16 }}
          >
            {!selectedPackage ? (
              <Empty description="请选择一个 Skill" />
            ) : (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <div>
                  <Text strong style={{ color: THEME.textPrimary }}>{selectedPackage.title}</Text>
                  <Paragraph style={{ color: THEME.textSecondary, marginTop: 6, marginBottom: 0 }}>
                    {selectedPackage.description}
                  </Paragraph>
                </div>
                <Row gutter={[8, 8]}>
                  <Col span={8}><div style={metricStyle}><Text type="secondary">类型</Text><div><Tag>{selectedPackage.skill_type}</Tag></div></div></Col>
                  <Col span={8}><div style={metricStyle}><Text type="secondary">版本</Text><div><Text>{selectedPackage.version}</Text></div></div></Col>
                  <Col span={8}><div style={metricStyle}><Text type="secondary">使用</Text><div><Text>{skillMetrics[selectedPackage.name]?.usage_count || 0} 次</Text></div></div></Col>
                </Row>
                <div>
                  <Text type="secondary">需要工具</Text>
                  <div style={{ marginTop: 6 }}>
                    <Space size={[4, 4]} wrap>
                      {(selectedPackage.requires_tools || []).map(tool => <Tag key={tool}>{tool}</Tag>)}
                      {(selectedPackage.requires_tools || []).length === 0 && <Text type="secondary">无强制工具</Text>}
                    </Space>
                  </div>
                </div>
                <div>
                  <Text type="secondary">包文件</Text>
                  <div style={{ marginTop: 6 }}>
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
                  </div>
                </div>
              </Space>
            )}
          </Card>

          <Card title="路由预览" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
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
              <Button type="primary" icon={<BranchesOutlined />} onClick={handlePreviewRoute} loading={routeLoading}>
                预览匹配
              </Button>
              {routeError && <Alert type="error" message={routeError} showIcon />}
              {routeResult.length > 0 && (
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  {routeResult.map(item => (
                    <div key={item.skill_id} style={{ padding: 10, borderRadius: 8, border: `1px solid ${THEME.border}`, background: THEME.bgElevated }}>
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
        title={
          <Space>
            <ImportOutlined />
            <span>Skill 草稿审批</span>
            <Badge count={drafts.length} style={{ backgroundColor: THEME.primary }} />
          </Space>
        }
        style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginTop: 16 }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 14 }}
          message="远程 Skill 只会先导入为待审批草稿，批准后才会写入用户 Skill 目录并进入 Agent 路由。"
        />
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={10}>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Input.Search
                value={draftUrl}
                onChange={event => setDraftUrl(event.target.value)}
                onSearch={handleImportDraftUrl}
                enterButton="导入 URL"
                loading={draftLoading}
                placeholder="https://.../SKILL.md"
              />
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
                  render: value => <Tag color={value === 'url' ? 'cyan' : 'default'}>{value}</Tag>,
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
              <div style={{ marginTop: 12, padding: 12, borderRadius: 8, border: `1px solid ${THEME.border}`, background: THEME.bgElevated }}>
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
              </div>
            )}
          </Col>
        </Row>
      </Card>

      <Card
        title="工作流 Bundle"
        style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginTop: 16 }}
      >
        {bundles.length === 0 ? (
          <Empty description="暂无 Bundle" />
        ) : (
          <Row gutter={[12, 12]}>
            {bundles.map(bundle => (
              <Col xs={24} md={12} xl={8} key={bundle.name}>
                <div style={{ padding: 14, border: `1px solid ${THEME.border}`, borderRadius: 8, background: THEME.bgElevated, minHeight: 150 }}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Text strong style={{ color: THEME.textPrimary }}>/{bundle.name}</Text>
                    <Text style={{ color: THEME.textSecondary }}>{bundle.description}</Text>
                    <Space size={[4, 4]} wrap>
                      {bundle.skills.map(skill => <Tag key={skill}>{skill}</Tag>)}
                    </Space>
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
