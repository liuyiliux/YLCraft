/**
 * 世界构建模板（按创作项目管理，平台模板管理页「世界构建」Tab）：
 * - 内置种子模板：只读；点「编辑」会在保存时复制为该项目的私有模板。
 * - 项目私有模板：新建 / 查看编辑 / 删除 / 设为默认。
 * - AI 起草：按项目已启用设定模块与补充要求生成草案（不落库），确认后再保存。
 * 与 /story「AI 细化本模块」弹窗共用同一套接口与契约。
 */
import { useEffect, useState } from 'react'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Button,
  Card,
  Empty,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useTheme } from '../../constants/theme'
import { listCreativeProjects } from '../../api'
import {
  WorldBuildingTemplate,
  deleteWorldTemplate,
  draftWorldTemplate,
  listWorldTemplates,
  upsertWorldTemplate,
} from '../../api/novelSource'

const { Text } = Typography
const { TextArea } = Input

interface ProjectOption {
  id: string
  title: string
}

function layerSummary(layers: string[]) {
  return (layers || []).join(' → ')
}

function promptSummary(prompts: Record<string, string>, key: string) {
  const value = (prompts || {})[key] || ''
  const compact = value.replace(/\s+/g, ' ').trim()
  return compact || ''
}

export default function WorldBuildingTemplates() {
  const { theme: T } = useTheme()
  const [projects, setProjects] = useState<ProjectOption[]>([])
  const [projectId, setProjectId] = useState('')
  const [templates, setTemplates] = useState<WorldBuildingTemplate[]>([])
  const [loading, setLoading] = useState(false)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<WorldBuildingTemplate | null>(null)
  const [name, setName] = useState('')
  const [layersText, setLayersText] = useState('')
  const [promptDomain, setPromptDomain] = useState('')
  const [promptEntity, setPromptEntity] = useState('')
  const [isDefault, setIsDefault] = useState(false)
  const [draftHint, setDraftHint] = useState('')
  const [draftNote, setDraftNote] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    listCreativeProjects({ limit: 80 })
      .then((resp: any) => {
        const list = ((resp?.data || []) as ProjectOption[]).filter(
          (item) => item?.id && item?.title,
        )
        setProjects(list)
        if (list.length && !projectId) {
          setProjectId(list[0].id)
        }
      })
      .catch(() => {
        /* 项目列表加载失败不阻塞页面 */
      })
    // 只在挂载时取一次项目列表
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadTemplates = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const data = await listWorldTemplates(projectId)
      setTemplates(data.templates || [])
    } catch (error: any) {
      message.error(error?.message || '模板加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTemplates()
    // 项目切换后重新加载该项目的模板
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const openNew = () => {
    if (!projectId) {
      message.warning('请先选择创作项目')
      return
    }
    setEditing(null)
    setName('')
    setLayersText('')
    setPromptDomain('')
    setPromptEntity('')
    setIsDefault(false)
    setDraftNote('')
    setDraftHint('')
    setEditorOpen(true)
  }

  const openEdit = (row: WorldBuildingTemplate) => {
    setName(row.name)
    setLayersText(layerSummary(row.layers))
    setPromptDomain(promptSummary(row.prompts, 'expand_domain'))
    setPromptEntity(promptSummary(row.prompts, 'expand_entity'))
    setIsDefault(row.is_default)
    setDraftNote(row.is_builtin ? '内置模板只读：保存时会复制为该项目模板。' : '')
    setDraftHint('')
    setEditing(row)
    setEditorOpen(true)
  }

  const handleDraft = async () => {
    if (!projectId) {
      message.warning('请先选择创作项目')
      return
    }
    setDrafting(true)
    setDraftNote('')
    try {
      const draft = await draftWorldTemplate(projectId, {
        hint: draftHint.trim() || undefined,
      })
      setName(draft.name)
      setLayersText(layerSummary(draft.layers))
      setPromptDomain(draft.prompts?.expand_domain || '')
      setPromptEntity(draft.prompts?.expand_entity || '')
      setDraftNote(draft.note || '已生成草案（未保存），可微调后保存')
      message.success(`已生成草案「${draft.name}」（未保存）`)
    } catch (error: any) {
      message.error(error?.message || '起草模板失败')
    } finally {
      setDrafting(false)
    }
  }

  const handleSave = async () => {
    if (!projectId) return
    const layers = layersText
      .split(/[、,，>/]+/)
      .map((item) => item.trim())
      .filter(Boolean)
    if (!name.trim()) {
      message.warning('请填写模板名称')
      return
    }
    if (!layers.length) {
      message.warning('请填写层次策略，用 > 分隔，如：世界 > 大陆 > 国家 > 城市')
      return
    }
    const prompts: Record<string, string> = {}
    if (promptDomain.trim()) prompts.expand_domain = promptDomain.trim()
    if (promptEntity.trim()) prompts.expand_entity = promptEntity.trim()
    // 内置模板不可改，保存自动复制为项目私有模板（不带 template_id 即新建）。
    const copyBuiltin = Boolean(editing?.is_builtin)
    setSaving(true)
    try {
      const saved = await upsertWorldTemplate(projectId, {
        template_id: editing && !copyBuiltin ? editing.id : undefined,
        name: name.trim(),
        layers,
        prompts: Object.keys(prompts).length ? prompts : undefined,
        is_default: isDefault,
      })
      message.success(
        copyBuiltin ? `已复制为项目模板「${saved.name}」` : `已保存模板「${saved.name}」`,
      )
      setEditorOpen(false)
      await loadTemplates()
    } catch (error: any) {
      message.error(error?.message || '保存模板失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (row: WorldBuildingTemplate) => {
    if (!projectId) return
    try {
      await deleteWorldTemplate(projectId, row.id)
      message.success(`已删除模板「${row.name}」`)
      await loadTemplates()
    } catch (error: any) {
      message.error(error?.message || '删除模板失败')
    }
  }

  const columns = [
    {
      title: '模板',
      dataIndex: 'name',
      key: 'name',
      render: (_: string, row: WorldBuildingTemplate) => (
        <Space size={6}>
          <Text strong style={{ fontSize: 13 }}>
            {row.name}
          </Text>
          {row.is_builtin && (
            <Tag color="default" style={{ fontSize: 11, lineHeight: '18px' }}>
              内置
            </Tag>
          )}
          {row.is_default && (
            <Tag color="gold" style={{ fontSize: 11, lineHeight: '18px' }}>
              默认
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: '层次策略',
      dataIndex: 'layers',
      key: 'layers',
      width: 320,
      render: (layers: string[]) =>
        layers?.length ? (
          <Text style={{ fontSize: 12 }}>{layerSummary(layers)}</Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            未定义
          </Text>
        ),
    },
    {
      title: '模块细化提示词',
      key: 'prompt_domain',
      width: 220,
      render: (_: unknown, row: WorldBuildingTemplate) =>
        promptSummary(row.prompts, 'expand_domain') ? (
          <Text
            type="secondary"
            style={{ fontSize: 12 }}
            title={promptSummary(row.prompts, 'expand_domain')}
          >
            {promptSummary(row.prompts, 'expand_domain').slice(0, 32)}…
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            用默认
          </Text>
        ),
    },
    {
      title: '实体补字段提示词',
      key: 'prompt_entity',
      width: 220,
      render: (_: unknown, row: WorldBuildingTemplate) =>
        promptSummary(row.prompts, 'expand_entity') ? (
          <Text
            type="secondary"
            style={{ fontSize: 12 }}
            title={promptSummary(row.prompts, 'expand_entity')}
          >
            {promptSummary(row.prompts, 'expand_entity').slice(0, 32)}…
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            用默认
          </Text>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, row: WorldBuildingTemplate) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(row)}
            disabled={!projectId}
          >
            {row.is_builtin ? '复制编辑' : '查看/编辑'}
          </Button>
          {!row.is_builtin && (
            <Popconfirm
              title={`删除模板「${row.name}」？`}
              okText="删除"
              cancelText="取消"
              onConfirm={() => handleDelete(row)}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={!projectId} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      style={{
        background: T.bgCard,
        border: `1px solid ${T.border}`,
        borderRadius: T.radiusXL,
        boxShadow: T.shadowCard,
      }}
      styles={{ body: { padding: 16 } }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          世界构建模板 = 层次策略（layers）+ 每档提示词（expand_domain / expand_entity），
          供「AI 细化本模块」与实体补字段时使用；内置种子只读，可复制为项目模板。
        </Text>
        <Space wrap>
          <Select
            showSearch
            allowClear
            style={{ minWidth: 280 }}
            value={projectId || undefined}
            placeholder="选择创作项目"
            optionFilterProp="label"
            options={projects.map((item) => ({ value: item.id, label: item.title }))}
            onChange={(value) => setProjectId(value || '')}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openNew} disabled={!projectId}>
            新建模板
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadTemplates} loading={loading}>
            刷新
          </Button>
        </Space>
        <Table
          rowKey="id"
          size="small"
          dataSource={templates}
          columns={columns as any}
          loading={loading}
          pagination={false}
          locale={{
            emptyText: projectId ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无模板，点「新建模板」创建" />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请先选择创作项目" />
            ),
          }}
        />
      </Space>

      <Modal
        title={
          <span style={{ fontWeight: 600, fontSize: 16, color: T.textPrimary }}>
            {editing?.is_builtin
              ? `复制内置模板「${editing.name}」到项目`
              : editing
                ? `编辑模板 · ${editing.name}`
                : '新建世界构建模板'}
          </span>
        }
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setEditorOpen(false)} disabled={saving}>
            取消
          </Button>,
          <Button
            key="save"
            type="primary"
            loading={saving}
            disabled={!projectId}
            onClick={handleSave}
          >
            保存
          </Button>,
        ]}
        width={620}
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space wrap style={{ width: '100%' }}>
            <Input
              style={{ width: 260 }}
              placeholder="模板名称，如：位面→大陆层级"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button
              loading={drafting}
              onClick={handleDraft}
              icon={<ThunderboltOutlined />}
              disabled={!projectId}
            >
              AI 起草
            </Button>
          </Space>
          <Input.TextArea
            rows={2}
            placeholder="起草补充要求（可选，用于 AI 起草）：如「仙侠世界观，境界按 炼气→筑基→金丹 细分」"
            value={draftHint}
            onChange={(e) => setDraftHint(e.target.value)}
          />
          {draftNote && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {draftNote}
            </Text>
          )}
          <Input
            placeholder="层次策略，用 > 分隔，如：世界 > 大陆 > 国家 > 地点"
            value={layersText}
            onChange={(e) => setLayersText(e.target.value)}
          />
          <Input.TextArea
            rows={3}
            placeholder="模块细化提示词（expand_domain，可选），支持 {domain} {layers} {known} {hint} 占位"
            value={promptDomain}
            onChange={(e) => setPromptDomain(e.target.value)}
          />
          <Input.TextArea
            rows={3}
            placeholder="实体补字段提示词（expand_entity，可选），支持 {entity} {domain} {layers} {known} {fields} 占位"
            value={promptEntity}
            onChange={(e) => setPromptEntity(e.target.value)}
          />
          <Space>
            <Text style={{ fontSize: 13 }}>设为该项目默认模板</Text>
            <Switch checked={isDefault} onChange={setIsDefault} />
          </Space>
        </Space>
      </Modal>
    </Card>
  )
}
