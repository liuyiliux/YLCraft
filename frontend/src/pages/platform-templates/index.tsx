/**
 * 平台模板管理页
 * 支持查看、编辑、删除平台生成模板
 */
import { useState, useEffect } from 'react'
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
} from 'antd'
import {
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  getPlatformTemplates,
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

const SIZE_OPTIONS = [
  { value: '1024x1024', label: '1024x1024 (1:1)' },
  { value: '768x1024', label: '768x1024 (3:4)' },
  { value: '1024x768', label: '1024x768 (4:3)' },
  { value: '720x1280', label: '720x1280 (9:16)' },
  { value: '1080x1920', label: '1080x1920 (9:16)' },
  { value: '1280x720', label: '1280x720 (16:9)' },
]

export default function PlatformTemplatesPage() {
  const { theme: THEME } = useTheme()
  const [templates, setTemplates] = useState<PlatformTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<PlatformTemplate | null>(null)
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
      video_template: template.video_template || '',
      default_size: template.default_size,
      is_active: template.is_active,
      sort_order: template.sort_order,
    })
    setEditModalOpen(true)
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
      if (!editingTemplate) return

      const res = await updatePlatformTemplate(editingTemplate.id, values)
      if (res.success) {
        message.success('更新成功')
        setEditModalOpen(false)
        loadTemplates()
      } else {
        message.error(res.error || '更新失败')
      }
    } catch (e: any) {
      message.error('更新失败: ' + e.message)
    }
  }

  const columns = [
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 120,
      render: (val: string) => {
        const opt = PLATFORM_OPTIONS.find(o => o.value === val)
        return <Tag color="blue">{opt?.label || val}</Tag>
      },
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 120,
    },
    {
      title: '默认尺寸',
      dataIndex: 'default_size',
      key: 'default_size',
      width: 120,
    },
    {
      title: '排序',
      dataIndex: 'sort_order',
      key: 'sort_order',
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (val: boolean) => (
        <Tag color={val ? 'green' : 'red'}>{val ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: PlatformTemplate) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title="确定删除该模板？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card
        style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}
        styles={{ body: { padding: 24 } }}
      >
        <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
          <div>
            <Title level={4} style={{ margin: 0, color: THEME.textPrimary }}>
              平台模板管理
            </Title>
            <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>
              配置多平台生图的平台提示词模板
            </Text>
          </div>
          <Button icon={<ReloadOutlined />} onClick={loadTemplates} loading={loading}>
            刷新
          </Button>
        </Row>

        <Table
          dataSource={templates}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          size="small"
          style={{
            background: THEME.bgElevated,
            borderRadius: 8,
          }}
        />
      </Card>

      <Modal
        title="编辑平台模板"
        open={editModalOpen}
        onOk={handleSave}
        onCancel={() => setEditModalOpen(false)}
        width={720}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="platform" label="平台标识" rules={[{ required: true }]}>
                <Select options={PLATFORM_OPTIONS} disabled />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="平台名称" rules={[{ required: true }]}>
                <Input placeholder="如：小红书" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="default_size" label="默认尺寸" rules={[{ required: true }]}>
                <Select options={SIZE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="sort_order" label="排序">
                <Input type="number" placeholder="0" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item name="outline_template" label="大纲模板" rules={[{ required: true }]}>
            <TextArea
              rows={4}
              placeholder="LLM 大纲模板，变量：{topic}"
            />
          </Form.Item>

          <Form.Item name="image_template" label="生图模板" rules={[{ required: true }]}>
            <TextArea
              rows={4}
              placeholder="生图提示词模板，变量：{page_content}{page_type}{topic}{full_outline}"
            />
          </Form.Item>

          <Form.Item name="video_template" label="视频模板（可选）">
            <TextArea rows={3} placeholder="视频生成模板（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
