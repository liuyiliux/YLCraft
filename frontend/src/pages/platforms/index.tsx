import { useState, useEffect } from 'react'
import { useTheme } from '../../constants/theme'
import {
  Card,
  Table,
  Button,
  Tag,
  message,
  Space,
  Typography,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Popconfirm,
  Alert,
  Tooltip,
  Descriptions,
} from 'antd'
import {
  GlobalOutlined,
  LinkOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ApiOutlined,
  KeyOutlined,
  FileTextOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  listPlatformConnections,
  createPlatformConnection,
  updatePlatformConnection,
  deletePlatformConnection,
  testPlatformConnection,
  getSupportedPlatforms,
} from '../../api'
import type { PlatformConnectionResponse } from '../../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

// 平台图标映射
const PLATFORM_ICONS: Record<string, React.ReactNode> = {
  xhs:        <FileTextOutlined style={{ color: '#fe2c55' }} />,
  douyin:     <i className="icon-video" style={{ color: '#000' }}>🎬</i>,
  kuaishou:   <i style={{ color: '#ff5000' }}>🎥</i>,
  bilibili:    <i style={{ color: '#00aeec' }}>📺</i>,
  weibo:      <i style={{ color: '#ff8200' }}>💬</i>,
  zhihu:      <i style={{ color: '#0066ff' }}>❓</i>,
  youtube:    <i style={{ color: '#ff0000' }}>▶️</i>,
  tiktok:     <i style={{ color: '#000' }}>♪</i>,
  openai:     <ApiOutlined style={{ color: '#10a37f' }} />,
  anthropic:  <ApiOutlined style={{ color: '#d4a0e7' }} />,
  minimax:    <ApiOutlined style={{ color: '#00d4ff' }} />,
}

export default function PlatformsPage() {
  const { theme } = useTheme()
  const [connections, setConnections] = useState<PlatformConnectionResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [supportedPlatforms, setSupportedPlatforms] = useState<any[]>([])
  const [authTypes, setAuthTypes] = useState<any[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [editingConn, setEditingConn] = useState<PlatformConnectionResponse | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [form] = Form.useForm()

  // 加载数据
  const loadData = async () => {
    setLoading(true)
    try {
      const [connRes, platformRes] = await Promise.all([
        listPlatformConnections(),
        getSupportedPlatforms(),
      ])
      setConnections(connRes.connections || [])
      setSupportedPlatforms(platformRes.platforms || [])
      setAuthTypes(platformRes.auth_types || [])
    } catch (e: any) {
      message.error('加载失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // 创建/编辑
  const handleSave = async (values: any) => {
    try {
      // 处理凭证数据
      let credentials = {}
      if (values.cookie_content) {
        credentials = { content: values.cookie_content }
      } else if (values.api_key) {
        credentials = { api_key: values.api_key }
      } else if (values.username && values.password) {
        credentials = { username: values.username, password: values.password }
      }

      if (editingConn) {
        await updatePlatformConnection(editingConn.id, {
          name: values.name,
          auth_type: values.auth_type,
          credentials,
          description: values.description,
        })
        message.success('更新成功')
      } else {
        await createPlatformConnection({
          platform: values.platform,
          name: values.name,
          auth_type: values.auth_type,
          credentials,
          description: values.description,
        })
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      loadData()
    } catch (e: any) {
      message.error('保存失败：' + (e?.response?.data?.detail || '未知错误'))
    }
  }

  // 删除
  const handleDelete = async (id: string) => {
    try {
      await deletePlatformConnection(id)
      message.success('删除成功')
      loadData()
    } catch (e: any) {
      message.error('删除失败：' + (e?.response?.data?.detail || '未知错误'))
    }
  }

  // 测试连接
  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await testPlatformConnection(id)
      if (result.success) {
        message.success('连接测试成功：' + result.message)
      } else {
        message.error('连接测试失败：' + result.message)
      }
      loadData()
    } catch (e: any) {
      message.error('测试失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setTestingId(null)
    }
  }

  // 打开创建弹窗
  const handleCreate = () => {
    setEditingConn(null)
    form.resetFields()
    form.setFieldsValue({ auth_type: 'cookie', status: 'unknown' })
    setModalVisible(true)
  }

  // 打开编辑弹窗
  const handleEdit = (conn: PlatformConnectionResponse) => {
    setEditingConn(conn)
    form.setFieldsValue({
      platform: conn.platform,
      name: conn.name,
      auth_type: conn.auth_type,
      description: conn.description,
    })
    setModalVisible(true)
  }

  // 表格列
  const columns = [
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 150,
      render: (platform: string) => {
        const p = supportedPlatforms.find(p => p.value === platform)
        return (
          <Space>
            {PLATFORM_ICONS[platform] || <GlobalOutlined />}
            <Text style={{ color: '#e0e0e0' }}>
              {p?.label || platform}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '连接名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <Text style={{ color: '#e0e0e0' }}>{text}</Text>,
    },
    {
      title: '认证类型',
      dataIndex: 'auth_type',
      key: 'auth_type',
      width: 120,
      render: (type: string) => {
        const t = authTypes.find(t => t.value === type)
        return <Tag>{t?.label || type}</Tag>
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string, record: PlatformConnectionResponse) => {
        if (status === 'active') {
          return (
            <Tag icon={<CheckCircleOutlined />} color="success">有效</Tag>
          )
        } else if (status === 'failed') {
          return (
            <Tooltip title={record.error_message}>
              <Tag icon={<CloseCircleOutlined />} color="error">失败</Tag>
            </Tooltip>
          )
        } else if (status === 'expired') {
          return <Tag color="warning">已过期</Tag>
        }
        return <Tag color="default">未测试</Tag>
      },
    },
    {
      title: '最后使用',
      dataIndex: 'last_used',
      key: 'last_used',
      width: 150,
      render: (time: string) => (
        <Text type="secondary">{time ? new Date(time).toLocaleString() : '从未使用'}</Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: PlatformConnectionResponse) => (
        <Space>
          <Tooltip title="测试连接">
            <Button
              type="text"
              size="small"
              icon={<ThunderboltOutlined />}
              loading={testingId === record.id}
              onClick={() => handleTest(record.id)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description="删除后无法恢复，确定要删除吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button type="text" size="small" icon={<DeleteOutlined />} danger />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1200 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        <LinkOutlined style={{ marginRight: 12 }} />
        平台连接器
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          统一管理各平台的凭证（Cookie / API Key / OAuth Token）
        </Text>
      </Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
        message="平台连接器说明"
        description={
          <Paragraph style={{ color: '#8b8ba8', marginBottom: 0 }}>
            配置各平台的凭证后，搜索、下载、发布等功能将自动使用对应凭证。
            支持 Cookie 认证（抖音/B站等）、API Key（AI 服务）、OAuth2.0（社交媒体发布）等。
          </Paragraph>
        }
      />

      {/* 统计卡片 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <Card style={{ background: theme.bgCard, border: theme.border, flex: 1, minWidth: 200 }}>
          <Statistic title="已配置平台" value={connections.length} />
        </Card>
        <Card style={{ background: theme.bgCard, border: theme.border, flex: 1, minWidth: 200 }}>
          <Statistic
            title="有效连接"
            value={connections.filter(c => c.status === 'active').length}
            valueStyle={{ color: '#52c41a' }}
          />
        </Card>
        <Card style={{ background: theme.bgCard, border: theme.border, flex: 1, minWidth: 200 }}>
          <Statistic
            title="连接失败"
            value={connections.filter(c => c.status === 'failed').length}
            valueStyle={{ color: '#ff4d4f' }}
          />
        </Card>
      </div>

      {/* 连接列表 */}
      <Card
        style={{ background: theme.bgCard, border: theme.border }}
        title={<Text style={{ color: '#fff' }}>平台连接列表</Text>}
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreate}
          >
            添加连接
          </Button>
        }
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={connections}
          loading={loading}
          pagination={{ pageSize: 10 }}
          style={{ color: '#e0e0e0' }}
        />
      </Card>

      {/* 创建/编辑弹窗 */}
      <Modal
        title={editingConn ? '编辑平台连接' : '添加平台连接'}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        width={600}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{ auth_type: 'cookie' }}
        >
          <Form.Item
            name="platform"
            label="平台"
            rules={[{ required: true, message: '请选择平台' }]}
          >
            <Select
              placeholder="选择平台"
              options={supportedPlatforms.map(p => ({
                value: p.value,
                label: (
                  <Space>
                    {PLATFORM_ICONS[p.value] || <GlobalOutlined />}
                    {p.label}
                  </Space>
                ),
              }))}
            />
          </Form.Item>

          <Form.Item
            name="name"
            label="连接名称"
            rules={[{ required: true, message: '请输入连接名称' }]}
          >
            <Input placeholder="例如：我的抖音账号" />
          </Form.Item>

          <Form.Item
            name="auth_type"
            label="认证类型"
            rules={[{ required: true, message: '请选择认证类型' }]}
          >
            <Select
              placeholder="选择认证类型"
              options={authTypes.map(t => ({
                value: t.value,
                label: t.label,
              }))}
              onChange={(value) => {
                // 根据认证类型显示不同表单
              }}
            />
          </Form.Item>

          {/* Cookie 认证 */}
          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.auth_type !== currentValues.auth_type
            }
          >
            {() => {
              const authType = form.getFieldValue('auth_type')
              if (authType === 'cookie') {
                return (
                  <Form.Item
                    name="cookie_content"
                    label="Cookie 内容"
                    rules={[{ required: true, message: '请输入 Cookie 内容' }]}
                  >
                    <TextArea
                      rows={6}
                      placeholder="粘贴 Cookie 内容（Netscape 格式）..."
                    />
                  </Form.Item>
                )
              } else if (authType === 'api_key') {
                return (
                  <Form.Item
                    name="api_key"
                    label="API Key"
                    rules={[{ required: true, message: '请输入 API Key' }]}
                  >
                    <Input.Password placeholder="输入 API Key..." />
                  </Form.Item>
                )
              } else if (authType === 'password') {
                return (
                  <>
                    <Form.Item
                      name="username"
                      label="用户名"
                      rules={[{ required: true, message: '请输入用户名' }]}
                    >
                      <Input placeholder="用户名..." />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      label="密码"
                      rules={[{ required: true, message: '请输入密码' }]}
                    >
                      <Input.Password placeholder="密码..." />
                    </Form.Item>
                  </>
                )
              }
              return null
            }}
          </Form.Item>

          <Form.Item name="description" label="备注说明">
            <TextArea rows={2} placeholder="可选：添加备注说明..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// 统计组件
function Statistic({ title, value, valueStyle }: { title: string; value: number; valueStyle?: any }) {
  return (
    <div>
      <Text style={{ color: '#8b8ba8', fontSize: 12 }}>{title}</Text>
      <div style={{ fontSize: 24, fontWeight: 600, color: '#fff', ...valueStyle }}>{value}</div>
    </div>
  )
}
