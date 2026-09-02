/**
 * 平台模板管理页
 * 支持查看、编辑、删除平台生成模板
 */
import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Card,
  Table,
  Button,
  Switch,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Space,
  Popconfirm,
  message,
  Typography,
  Row,
  Col,
  Empty,
  Skeleton,
  Tabs,
} from 'antd'
import {
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  PlusOutlined,
  AppstoreOutlined,
  InboxOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import WorldBuildingTemplates from './WorldBuildingTemplates'
import {
  getPlatformTemplates,
  createPlatformTemplate,
  updatePlatformTemplate,
  deletePlatformTemplate,
  type PlatformTemplate,
} from '../../api'

const { Title, Text } = Typography
const { TextArea } = Input

const PLATFORM_OPTIONS = [
  { value: 'xiaohongshu', label: '小红书' },
  { value: 'douyin', label: '抖音' },
  { value: 'wechat', label: '微信' },
  { value: 'toutiao', label: '头条' },
  { value: 'bilibili', label: 'B站' },
  { value: 'weibo', label: '微博' },
]

const PLATFORM_TAG_COLORS: Record<string, string> = {
  xiaohongshu: '#ff2442',
  douyin: '#000000',
  wechat: '#07c160',
  toutiao: '#ed4040',
  bilibili: '#00a1d6',
  weibo: '#e6162d',
}

const SIZE_OPTIONS = [
  { value: '1024x1024', label: '1024x1024 (1:1)' },
  { value: '768x1024', label: '768x1024 (3:4)' },
  { value: '1024x768', label: '1024x768 (4:3)' },
  { value: '720x1280', label: '720x1280 (9:16)' },
  { value: '1080x1920', label: '1080x1920 (9:16)' },
  { value: '1280x720', label: '1280x720 (16:9)' },
]

const SCOPE_OPTIONS = [
  { value: 'image_platform', label: '多平台生图' },
  { value: 'creative_project', label: '创作项目 Prompt' },
  { value: 'video_prompt', label: '视频提示词' },
]

const PROMPT_TAB_OPTIONS = [
  { value: 'image_platform', label: '多平台生图' },
  { value: 'creative_project', label: '创作项目 Prompt' },
  { value: 'video_prompt', label: '视频提示词' },
  { value: 'prompt_reference', label: '图片 Prompt 参考' },
  { value: 'world_building', label: '世界构建' },
]

const STAGE_OPTIONS = [
  { value: 'platform', label: '平台' },
  { value: 'outline', label: '故事大纲' },
  { value: 'chapter_plan', label: '章节规划' },
  { value: 'script', label: '短剧脚本' },
  { value: 'storyboard', label: '分镜草稿' },
]

export default function PlatformTemplatesPage() {
  const { theme: T } = useTheme()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeScope, setActiveScope] = useState(searchParams.get('scope') || 'image_platform')
  const [templates, setTemplates] = useState<PlatformTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<PlatformTemplate | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [form] = Form.useForm()

  const loadTemplates = async () => {
    if (activeScope === 'world_building') return // 世界构建模板走独立面板
    setLoading(true)
    try {
      const res = await getPlatformTemplates({ template_scope: activeScope })
      if (res.success) {
        setTemplates(res.templates || [])
      } else {
        message.error(res.error || '加载失败')
      }
    } catch (e: any) {
      message.error('加载失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setSearchParams({ scope: activeScope })
    if (activeScope === 'world_building') return
    loadTemplates()
  }, [activeScope])

  const handleEdit = (template: PlatformTemplate) => {
    setEditingTemplate(template)
    form.setFieldsValue({
      name: template.name,
      platform: template.platform,
      template_scope: template.template_scope || 'image_platform',
      template_stage: template.template_stage || 'platform',
      description: template.description || '',
      system_template: template.system_template || '',
      outline_template: template.outline_template,
      image_template: template.image_template,
      page_structure: JSON.stringify(template.page_structure || {}, null, 2),
      variables: JSON.stringify(template.variables || {}, null, 2),
      video_template: template.video_template || '',
      default_size: template.default_size,
      is_active: template.is_active,
      sort_order: template.sort_order,
    })
    setEditModalOpen(true)
  }

  const handleCreate = () => {
    setEditingTemplate(null)
    form.resetFields()
    form.setFieldsValue({
      is_active: true,
      sort_order: templates.length,
      default_size: '1024x1024',
      template_scope: activeScope,
      template_stage: activeScope === 'creative_project' ? 'outline' : 'platform',
      page_structure: activeScope === 'creative_project'
        ? '{}'
        : '{\n  "default_pages": [\n    {"type": "封面", "hint": ""},\n    {"type": "内容", "hint": ""},\n    {"type": "总结", "hint": ""}\n  ]\n}',
      variables: '{}',
      system_template: activeScope === 'creative_project'
        ? '你是资深网文主编、漫画脚本统筹和长篇连载策划。\n你必须输出严格 JSON，不要输出 Markdown、解释、代码块或 JSON 以外的文字。\n规划要服务后续逐话正文创作和漫画分镜生成，必须具体、可执行、前后连续。'
        : '',
      image_template: '',
    })
    setCreateModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    try {
      const res = await deletePlatformTemplate(id)
      if (res.success) {
        message.success('删除成功')
        loadTemplates()
      } else {
        message.error(res.error || '删除失败')
      }
    } catch (e: any) {
      message.error('删除失败: ' + e.message)
    }
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()

      // 解析 page_structure JSON
      let pageStructure = null
      if (values.page_structure && typeof values.page_structure === 'string' && values.page_structure.trim()) {
        try {
          pageStructure = JSON.parse(values.page_structure)
        } catch {
          message.error('页面结构 JSON 格式错误')
          return
        }
      }

      let variables = null
      if (values.variables && typeof values.variables === 'string' && values.variables.trim()) {
        try {
          variables = JSON.parse(values.variables)
        } catch {
          message.error('变量说明 JSON 格式错误')
          return
        }
      }

      const saveData: any = { ...values }
      if (pageStructure !== null) {
        saveData.page_structure = pageStructure
      }
      if (variables !== null) {
        saveData.variables = variables
      }

      if (editingTemplate) {
        // 更新
        const res = await updatePlatformTemplate(editingTemplate.id, saveData)
        if (res.success) {
          message.success('更新成功')
          setEditModalOpen(false)
          loadTemplates()
        } else {
          message.error(res.error || '更新失败')
        }
      } else {
        // 新建
        const res = await createPlatformTemplate(saveData)
        if (res.success) {
          message.success('创建成功')
          setCreateModalOpen(false)
          loadTemplates()
        } else {
          message.error(res.error || '创建失败')
        }
      }
    } catch (e: any) {
      message.error('保存失败: ' + e.message)
    }
  }

  const columns = [
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 130,
      render: (val: string) => {
        const opt = PLATFORM_OPTIONS.find(o => o.value === val)
        const color = PLATFORM_TAG_COLORS[val] || T.primary
        return (
          <Tag
            style={{
              borderRadius: T.radiusSM,
              borderColor: `${color}30`,
              color: color,
              background: `${color}08`,
              fontWeight: 500,
              fontSize: 13,
              padding: '2px 10px',
            }}
          >
            {opt?.label || val}
          </Tag>
        )
      },
    },
    {
      title: '用途',
      dataIndex: 'template_scope',
      key: 'template_scope',
      width: 130,
      render: (val: string) => (
        <Tag color={val === 'creative_project' ? 'purple' : 'blue'}>
          {SCOPE_OPTIONS.find((item) => item.value === val)?.label || val || '多平台生图'}
        </Tag>
      ),
    },
    {
      title: '阶段',
      dataIndex: 'template_stage',
      key: 'template_stage',
      width: 120,
      render: (val: string) => (
        <Text style={{ color: T.textSecondary, fontSize: 13 }}>
          {STAGE_OPTIONS.find((item) => item.value === val)?.label || val || '平台'}
        </Text>
      ),
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (val: string) => (
        <Text style={{ fontWeight: 500, color: T.textPrimary, fontSize: 14 }}>
          {val}
        </Text>
      ),
    },
    {
      title: '默认尺寸',
      dataIndex: 'default_size',
      key: 'default_size',
      width: 160,
      render: (val: string) => (
        <Text style={{ color: T.textSecondary, fontSize: 13, fontFamily: 'monospace' }}>
          {val}
        </Text>
      ),
    },
    {
      title: '排序',
      dataIndex: 'sort_order',
      key: 'sort_order',
      width: 80,
      align: 'center' as const,
      render: (val: number) => (
        <Text style={{ color: T.textSecondary, fontSize: 13, fontFamily: 'monospace' }}>
          {val}
        </Text>
      ),
    },
    {
      title: '默认页数',
      key: 'page_count',
      width: 90,
      align: 'center' as const,
      render: (_: any, record: PlatformTemplate) => {
        const count = record.page_structure?.default_pages?.length || 0
        return (
          <Text style={{ color: T.textSecondary, fontSize: 13, fontFamily: 'monospace', fontWeight: 500 }}>
            {count > 0 ? `${count} 页` : '-'}
          </Text>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      align: 'center' as const,
      render: (val: boolean) => (
        <Tag
          style={{
            borderRadius: T.radiusSM,
            border: 'none',
            background: val ? `${T.success}12` : `${T.textDisabled}15`,
            color: val ? T.success : T.textDisabled,
            fontWeight: 500,
            fontSize: 12,
            padding: '3px 10px',
          }}
        >
          {val ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      align: 'center' as const,
      render: (_: any, record: PlatformTemplate) => (
        <Space size={4}>
          <Button
            type="text"
            size="small"
            icon={<ThunderboltOutlined />}
            title="去生成"
            style={{
              color: T.textSecondary,
              borderRadius: T.radiusSM,
              width: 32,
              height: 32,
              transition: `all ${T.animationDuration} ${T.animationEasing}`,
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.color = T.success
              ;(e.currentTarget as HTMLElement).style.background = `${T.success}10`
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.color = T.textSecondary
              ;(e.currentTarget as HTMLElement).style.background = 'transparent'
            }}
            onClick={() => navigate(`/multi-platform-gen?platform=${record.platform}`)}
            disabled={record.template_scope === 'creative_project'}
          />
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            style={{
              color: T.textSecondary,
              borderRadius: T.radiusSM,
              width: 32,
              height: 32,
              transition: `all ${T.animationDuration} ${T.animationEasing}`,
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.color = T.primary
              ;(e.currentTarget as HTMLElement).style.background = `${T.primary}10`
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.color = T.textSecondary
              ;(e.currentTarget as HTMLElement).style.background = 'transparent'
            }}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title="确定删除该模板？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              style={{
                borderRadius: T.radiusSM,
                width: 32,
                height: 32,
                transition: `all ${T.animationDuration} ${T.animationEasing}`,
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.background = `${T.error}10`
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.background = 'transparent'
              }}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 32, maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <Row justify="space-between" align="middle">
          <div>
            <Title
              level={4}
              style={{
                margin: 0,
                color: T.textPrimary,
                fontWeight: 600,
                letterSpacing: '-0.02em',
              }}
            >
              <AppstoreOutlined style={{ marginRight: 10, color: T.primary, fontSize: 20 }} />
              平台模板管理
            </Title>
            <Text
              style={{
                color: T.textSecondary,
                fontSize: 13,
                marginTop: 4,
                display: 'block',
              }}
            >
              {activeScope === 'world_building'
                ? '管理 AI 世界构建模板：内置种子只读，项目模板可查看/编辑，支持 AI 起草后保存'
                : '配置多平台生图、视频提示词，以及创作项目的大纲、章节、脚本和分镜 Prompt'}
            </Text>
          </div>
          <Space>
            <Button onClick={() => navigate('/prompt-library')}>图片 Prompt 参考库</Button>
            {activeScope === 'world_building' ? (
              <Button type="primary" onClick={() => setActiveScope('creative_project')}>
                返回创作项目 Prompt
              </Button>
            ) : (
              <>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={handleCreate}
                  style={{
                    borderRadius: T.radiusLG,
                    fontWeight: 500,
                  }}
                >
                  新建
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={loadTemplates}
                  loading={loading}
                  style={{
                    borderRadius: T.radiusLG,
                    borderColor: T.border,
                    color: T.textSecondary,
                    fontWeight: 500,
                    transition: `all ${T.animationDuration} ${T.animationEasing}`,
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLElement).style.borderColor = T.primary
                    ;(e.currentTarget as HTMLElement).style.color = T.primary
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLElement).style.borderColor = T.border
                    ;(e.currentTarget as HTMLElement).style.color = T.textSecondary
                  }}
                >
                  刷新
                </Button>
              </>
            )}
          </Space>
        </Row>
      </div>

      <Tabs
        activeKey={activeScope}
        onChange={(key) => {
          if (key === 'prompt_reference') {
            navigate('/prompt-library')
            return
          }
          setActiveScope(key)
        }}
        items={PROMPT_TAB_OPTIONS.map((item) => ({ key: item.value, label: item.label }))}
        style={{ marginBottom: 12 }}
      />

      {/* Table Card：世界构建模板按项目管理，其余为平台/创作 Prompt 模板 */}
      {activeScope === 'world_building' ? (
        <WorldBuildingTemplates />
      ) : (
        <Card
          style={{
            background: T.bgCard,
            border: `1px solid ${T.border}`,
            borderRadius: T.radiusXL,
            boxShadow: T.shadowCard,
            overflow: 'hidden',
          }}
          styles={{ body: { padding: 0 } }}
        >
        {loading && templates.length === 0 ? (
          <div style={{ padding: 24 }}>
            <Skeleton active paragraph={{ rows: 6 }} />
          </div>
        ) : templates.length === 0 ? (
          <div style={{ padding: 64 }}>
            <Empty
              image={<InboxOutlined style={{ fontSize: 56, color: T.textDisabled }} />}
              description={
                <div>
                  <Text style={{ color: T.textSecondary, fontSize: 14, display: 'block', marginBottom: 4 }}>
                    暂无模板
                  </Text>
                  <Text style={{ color: T.textSecondary, fontSize: 12 }}>
                    {activeScope === 'video_prompt'
                      ? '可点击“新建”手工创建，或在成功视频任务中保存为视频提示词模板。'
                      : '可点击“新建”创建模板；内置预设会在后端启动时同步到数据库。'}
                  </Text>
                </div>
              }
            />
          </div>
        ) : (
          <Table
            dataSource={templates}
            columns={columns}
            rowKey="id"
            loading={loading}
            pagination={false}
            size="middle"
            style={{ background: 'transparent' }}
            rowClassName={() => 'platform-template-row'}
          />
        )}
      </Card>
      )}

      {/* Edit Modal */}
      <Modal
        title={
          <span style={{ fontWeight: 600, fontSize: 16, color: T.textPrimary }}>
            编辑平台模板
          </span>
        }
        open={editModalOpen}
        onOk={handleSave}
        onCancel={() => setEditModalOpen(false)}
        width={720}
        okText="保存"
        cancelText="取消"
        styles={{
          header: { borderBottom: `1px solid ${T.border}`, padding: '16px 24px' },
          body: { padding: '24px' },
          footer: { borderTop: `1px solid ${T.border}`, padding: '12px 24px' },
        }}
      >
        <Form form={form} layout="vertical">
          <Row gutter={20}>
            <Col span={12}>
              <Form.Item name="platform" label="模板标识" rules={[{ required: true }]}>
                <Input disabled size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="模板名称" rules={[{ required: true }]}>
                <Input placeholder="如：小红书、创作项目：故事大纲" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={20}>
            <Col span={12}>
              <Form.Item name="template_scope" label="模板用途" rules={[{ required: true }]}>
                <Select options={SCOPE_OPTIONS} size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="template_stage" label="模板阶段" rules={[{ required: true }]}>
                <Select options={STAGE_OPTIONS} size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="description" label="说明">
            <Input placeholder="说明这个模板适合什么生成阶段、输出标准或风格要求" size="large" />
          </Form.Item>

          <Row gutter={20}>
            <Col span={12}>
              <Form.Item name="default_size" label="默认尺寸" rules={[{ required: true }]}>
                <Select options={SIZE_OPTIONS} size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sort_order" label="排序">
                <Input type="number" placeholder="0" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <Switch
              style={{
                backgroundColor: T.textDisabled,
              }}
            />
          </Form.Item>

          <Form.Item
            name="page_structure"
            label="页面结构（JSON）"
            extra='平台模板用于定义默认页面类型；创作项目模板可留空。'
          >
            <TextArea
              rows={6}
              placeholder='{"default_pages":[{"type":"封面","hint":"..."},{"type":"内容","hint":"..."},{"type":"总结","hint":"..."}]}'
              style={{ borderRadius: T.radiusLG, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item
            name="variables"
            label="变量说明（JSON）"
            extra='记录模板可用变量，方便后续调 Prompt。例如 {"outline_json":"故事大纲 JSON"}'
          >
            <TextArea
              rows={4}
              placeholder='{"topic":"用户主题","outline_json":"故事大纲 JSON"}'
              style={{ borderRadius: T.radiusLG, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item
            name="system_template"
            label="System Prompt"
            extra="创作项目生成时会作为 role=system 发送；为空则使用后端默认值。可使用与主要 Prompt 相同的变量。"
          >
            <TextArea
              rows={4}
              placeholder="如：你是资深网文主编、漫画脚本统筹和长篇连载策划。你必须输出严格 JSON..."
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="outline_template" label="主要 Prompt 模板" rules={[{ required: true }]}>
            <TextArea
              rows={8}
              placeholder="主要 Prompt 模板。平台模板变量：{topic} {page_structure}；创作模板变量按阶段不同，如 {idea} {outline_json} {chapter_count}"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="image_template" label="生图模板">
            <TextArea
              rows={4}
              placeholder="多平台生图使用。创作项目 Prompt 模板通常可留空。变量：{page_content}{page_type}{topic}{full_outline}"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="video_template" label="视频模板（可选）">
            <TextArea
              rows={3}
              placeholder="视频生成模板（可选）"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Create Modal */}
      <Modal
        title={
          <span style={{ fontWeight: 600, fontSize: 16, color: T.textPrimary }}>
            新建平台模板
          </span>
        }
        open={createModalOpen}
        onOk={handleSave}
        onCancel={() => setCreateModalOpen(false)}
        width={720}
        okText="创建"
        cancelText="取消"
        styles={{
          header: { borderBottom: `1px solid ${T.border}`, padding: '16px 24px' },
          body: { padding: '24px' },
          footer: { borderTop: `1px solid ${T.border}`, padding: '12px 24px' },
        }}
      >
        <Form form={form} layout="vertical">
          <Row gutter={20}>
            <Col span={12}>
              <Form.Item name="platform" label="模板标识" rules={[{ required: true, message: '输入模板标识' }]}>
                <Input
                  placeholder={activeScope === 'creative_project' ? '如：creative_outline_custom' : '如：xiaohongshu、bilibili'}
                  size="large"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '输入模板名称' }]}>
                <Input placeholder="如：小红书、故事大纲 Pro" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={20}>
            <Col span={12}>
              <Form.Item name="template_scope" label="模板用途" rules={[{ required: true }]}>
                <Select options={SCOPE_OPTIONS} size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="template_stage" label="模板阶段" rules={[{ required: true }]}>
                <Select options={STAGE_OPTIONS} size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="description" label="说明">
            <Input placeholder="说明这个模板适合什么生成阶段、输出标准或风格要求" size="large" />
          </Form.Item>

          <Row gutter={20}>
            <Col span={12}>
              <Form.Item name="default_size" label="默认尺寸" rules={[{ required: true }]}>
                <Select options={SIZE_OPTIONS} size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sort_order" label="排序">
                <Input type="number" placeholder="0" size="large" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <Switch style={{ backgroundColor: T.textDisabled }} />
          </Form.Item>

          <Form.Item
            name="page_structure"
            label="页面结构（JSON）"
            extra='平台模板用于定义默认页面类型；创作项目模板可留空。'
          >
            <TextArea
              rows={6}
              placeholder='{"default_pages":[{"type":"封面","hint":"..."},{"type":"内容","hint":"..."},{"type":"总结","hint":"..."}]}'
              style={{ borderRadius: T.radiusLG, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item
            name="variables"
            label="变量说明（JSON）"
            extra='记录模板可用变量，方便后续调 Prompt。'
          >
            <TextArea
              rows={4}
              placeholder='{"idea":"用户创意","outline_json":"故事大纲 JSON"}'
              style={{ borderRadius: T.radiusLG, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item
            name="system_template"
            label="System Prompt"
            extra="创作项目生成时会作为 role=system 发送；为空则使用后端默认值。可使用与主要 Prompt 相同的变量。"
          >
            <TextArea
              rows={4}
              placeholder="如：你是资深网文主编、漫画脚本统筹和长篇连载策划。你必须输出严格 JSON..."
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="outline_template" label="主要 Prompt 模板" rules={[{ required: true, message: '输入主要 Prompt 模板' }]}>
            <TextArea
              rows={8}
              placeholder="主要 Prompt 模板。平台模板变量：{topic} {page_structure}；创作模板变量按阶段不同，如 {idea} {outline_json} {chapter_count}"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="image_template" label="生图模板">
            <TextArea
              rows={4}
              placeholder="多平台生图使用。创作项目 Prompt 模板通常可留空。变量：{page_content}{page_type}{topic}{full_outline}"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="video_template" label="视频模板（可选）">
            <TextArea
              rows={3}
              placeholder="视频生成模板（可选）"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Global row hover styles */}
      <style>{`
        .platform-template-row {
          transition: background-color ${T.animationDuration} ${T.animationEasing};
        }
        .platform-template-row:hover {
          background-color: ${T.bgHover} !important;
        }
        .platform-template-row td {
          transition: border-color ${T.animationDuration} ${T.animationEasing};
        }
      `}</style>
    </div>
  )
}
