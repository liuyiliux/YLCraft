/**
 * 平台模板管理页
 * 支持查看、编辑、删除平台生成模板
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
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

export default function PlatformTemplatesPage() {
  const { theme: T } = useTheme()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<PlatformTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<PlatformTemplate | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [form] = Form.useForm()

  const loadTemplates = async () => {
    setLoading(true)
    try {
      const res = await getPlatformTemplates()
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
    loadTemplates()
  }, [])

  const handleEdit = (template: PlatformTemplate) => {
    setEditingTemplate(template)
    form.setFieldsValue({
      name: template.name,
      platform: template.platform,
      outline_template: template.outline_template,
      image_template: template.image_template,
      page_structure: JSON.stringify(template.page_structure || {}, null, 2),
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
      page_structure: '{\n  "default_pages": [\n    {"type": "封面", "hint": ""},\n    {"type": "内容", "hint": ""},\n    {"type": "总结", "hint": ""}\n  ]\n}',
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

      const saveData: any = { ...values }
      if (pageStructure !== null) {
        saveData.page_structure = pageStructure
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
        <Text style={{ color: T.textTertiary, fontSize: 13, fontFamily: 'monospace' }}>
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
              transition: `all ${T.transitionDuration} ${T.transitionEasing}`,
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
              transition: `all ${T.transitionDuration} ${T.transitionEasing}`,
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
                transition: `all ${T.transitionDuration} ${T.transitionEasing}`,
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
              配置多平台生图的平台提示词模板
            </Text>
          </div>
          <Space>
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
                transition: `all ${T.transitionDuration} ${T.transitionEasing}`,
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
          </Space>
        </Row>
      </div>

      {/* Table Card */}
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
                    暂无平台模板
                  </Text>
                  <Text style={{ color: T.textTertiary, fontSize: 12 }}>
                    请先在系统中初始化平台模板数据
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
              <Form.Item name="platform" label="平台标识" rules={[{ required: true }]}>
                <Select options={PLATFORM_OPTIONS} disabled size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="平台名称" rules={[{ required: true }]}>
                <Input placeholder="如：小红书" size="large" />
              </Form.Item>
            </Col>
          </Row>

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
            extra='定义平台默认页面类型和顺序，驱动空白大纲创建。格式：{"default_pages":[{"type":"封面","hint":"提示"},...]}'
          >
            <TextArea
              rows={6}
              placeholder='{"default_pages":[{"type":"封面","hint":"..."},{"type":"内容","hint":"..."},{"type":"总结","hint":"..."}]}'
              style={{ borderRadius: T.radiusLG, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item name="outline_template" label="大纲模板" rules={[{ required: true }]}>
            <TextArea
              rows={4}
              placeholder="LLM 大纲模板，变量：{topic} {page_structure}"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="image_template" label="生图模板" rules={[{ required: true }]}>
            <TextArea
              rows={4}
              placeholder="生图提示词模板，变量：{page_content}{page_type}{topic}{full_outline}"
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
              <Form.Item name="platform" label="平台标识" rules={[{ required: true, message: '输入平台标识' }]}>
                <Input placeholder="如：xiaohongshu、bilibili" size="large" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="平台名称" rules={[{ required: true, message: '输入平台名称' }]}>
                <Input placeholder="如：小红书、B站" size="large" />
              </Form.Item>
            </Col>
          </Row>

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
            extra='定义平台默认页面类型和顺序，驱动空白大纲创建。'
          >
            <TextArea
              rows={6}
              placeholder='{"default_pages":[{"type":"封面","hint":"..."},{"type":"内容","hint":"..."},{"type":"总结","hint":"..."}]}'
              style={{ borderRadius: T.radiusLG, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Form.Item name="outline_template" label="大纲模板" rules={[{ required: true, message: '输入大纲模板' }]}>
            <TextArea
              rows={4}
              placeholder="LLM 大纲模板，变量：{topic} {page_structure}"
              style={{ borderRadius: T.radiusLG, resize: 'vertical' }}
            />
          </Form.Item>

          <Form.Item name="image_template" label="生图模板" rules={[{ required: true, message: '输入生图模板' }]}>
            <TextArea
              rows={4}
              placeholder="生图提示词模板，变量：{page_content}{page_type}{topic}{full_outline}"
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
          transition: background-color ${T.transitionDuration} ${T.transitionEasing};
        }
        .platform-template-row:hover {
          background-color: ${T.bgHover} !important;
        }
        .platform-template-row td {
          transition: border-color ${T.transitionDuration} ${T.transitionEasing};
        }
      `}</style>
    </div>
  )
}
