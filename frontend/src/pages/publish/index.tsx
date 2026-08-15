import { useState, useEffect } from 'react'
import { useTheme } from '../../constants/theme'
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  Tag,
  message,
  Space,
  Typography,
  Upload,
  Slider,
  Switch,
  Divider,
  Alert,
  List,
  Spin,
  Modal,
} from 'antd'
import {
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  FileTextOutlined,
  VideoCameraOutlined,
  PictureOutlined,
  GlobalOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import {
  listPlatformConnections,
  getSupportedPlatforms,
  publishToPlatform,
} from '../../api'
import type { PlatformConnectionResponse } from '../../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

export default function PublishPage() {
  const { theme } = useTheme()
  const [connections, setConnections] = useState<PlatformConnectionResponse[]>([])
  const [supportedPlatforms, setSupportedPlatforms] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [selectedConn, setSelectedConn] = useState<string>('')
  const [target, setTarget] = useState({ book_id: '', volume_id: '', volume_name: '', item_id: '' })
  const [preflighting, setPreflighting] = useState(false)
  const [preflightMessage, setPreflightMessage] = useState('')

  // 表单状态
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [contentType, setContentType] = useState<'video' | 'image' | 'text' | 'article'>('video')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [mediaFiles, setMediaFiles] = useState<{ path: string; type: string }[]>([])

  // 发布结果
  const [publishResults, setPublishResults] = useState<
    { connId: string; platform: string; success: boolean; message: string; postUrl?: string }[]
  >([])

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
    } catch (e: any) {
      message.error('加载失败：' + (e?.response?.data?.detail || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // 添加标签
  const addTag = () => {
    if (tagInput && !tags.includes(tagInput)) {
      setTags([...tags, tagInput])
      setTagInput('')
    }
  }

  // 删除标签
  const removeTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag))
  }

  // 添加媒体文件
  const addMediaFile = () => {
    // 简化版：直接输入文件路径
    const path = prompt('请输入文件路径：')
    if (path) {
      const ext = path.split('.').pop()?.toLowerCase() || ''
      const type = ['mp4', 'avi', 'mov'].includes(ext) ? 'video' : 'image'
      setMediaFiles([...mediaFiles, { path, type: ext }])
    }
  }

  // 删除媒体文件
  const removeMediaFile = (index: number) => {
    setMediaFiles(mediaFiles.filter((_, i) => i !== index))
  }

  // 发布
  const handlePublish = async () => {
    if (!selectedConn) {
      message.warning('请先选择平台连接')
      return
    }

    if (!title.trim()) {
      message.warning('请输入标题')
      return
    }

    if (!body.trim()) {
      message.warning('请输入章节正文')
      return
    }

    if (!target.book_id.trim() || !target.volume_id.trim() || !target.item_id.trim()) {
      message.warning('请填写书籍、卷和已创建的章节目标 ID')
      return
    }

    setPublishing(true)
    setPublishResults([])

    try {
      const result = await publishToPlatform(selectedConn, { title, body, content_type: 'article', target })

      const conn = connections.find(c => c.id === selectedConn)
      const platform = supportedPlatforms.find(p => p.value === conn?.platform)

      setPublishResults([
        {
          connId: selectedConn,
          platform: platform?.label || conn?.platform || '',
          success: result.success,
          message: result.error || (result.success ? '发布成功！' : '发布失败'),
          postUrl: result.post_url,
        },
      ])

      if (result.success) {
        message.success('发布成功！')
      } else {
        message.error('发布失败：' + (result.error || '未知错误'))
      }
    } catch (e: any) {
      message.error('发布失败：' + (e?.response?.data?.detail || '未知错误'))
      setPublishResults([
        {
          connId: selectedConn,
          platform: '',
          success: false,
          message: e?.response?.data?.detail || '发布失败',
        },
      ])
    } finally {
      setPublishing(false)
    }
  }

  const handlePreflight = async () => {
    if (!selectedConn || !title.trim() || !body.trim()) {
      message.warning('请先选择连接并填写章节标题和正文')
      return
    }
    if (!target.book_id.trim() || !target.volume_id.trim() || !target.item_id.trim()) {
      message.warning('请填写书籍、卷和已创建的章节目标 ID')
      return
    }
    setPreflighting(true)
    setPreflightMessage('')
    try {
      const result: any = await publishToPlatform(selectedConn, { title, body, content_type: 'article', target, dry_run: true })
      if (result.success) {
        setPreflightMessage('本地预检通过：正文、登录态配置和远端章节目标已具备。预检不会向平台发送内容。')
        message.success('预检通过')
      }
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || '预检失败'
      setPreflightMessage(detail)
      message.error(detail)
    } finally {
      setPreflighting(false)
    }
  }

  // 获取平台支持的发布类型
  const getPlatformContentTypes = (platform: string) => {
    const p = supportedPlatforms.find(p => p.value === platform)
    if (!p) return []

    const types = []
    if (platform === 'fanqie') {
      types.push({ value: 'article', label: '章节草稿', icon: <FileTextOutlined /> })
    }
    return types
  }

  return (
    <div style={{ maxWidth: 1200 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        <SendOutlined style={{ marginRight: 12 }} />
        番茄章节草稿
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          将已完成正文保存到指定的番茄章节草稿
        </Text>
      </Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
        message="保存范围"
        description={
          <Paragraph style={{ color: '#8b8ba8', marginBottom: 0 }}>
            当前页面只开放已验证的番茄章节草稿保存。请先在番茄后台创建书籍、卷和章节，再填入对应目标 ID；这里不会伪装成视频或图文的一键发布。
          </Paragraph>
        }
      />

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        {/* 左侧：发布表单 */}
        <Card
          style={{
            background: theme.bgCard,
            border: theme.border,
            flex: 2,
            minWidth: 500,
          }}
          title={<Text style={{ color: theme.textPrimary }}>发布内容</Text>}
        >
          <Form layout="vertical" style={{ color: theme.textPrimary }}>
            {/* 选择平台 */}
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>选择平台连接</Text>}>
              <Select
                value={selectedConn || undefined}
                onChange={setSelectedConn}
                placeholder="请选择已配置的平台连接"
                style={{ width: '100%' }}
              >
                {connections
                  .filter(c => c.status === 'active' && c.platform === 'fanqie')
                  .map(c => {
                    const platform = supportedPlatforms.find(p => p.value === c.platform)
                    return (
                      <Select.Option key={c.id} value={c.id}>
                        {platform?.label || c.platform} - {c.name}
                        {c.status === 'active' && (
                          <CheckCircleOutlined style={{ color: '#52c41a', marginLeft: 8 }} />
                        )}
                      </Select.Option>
                    )
                  })}
              </Select>
              {connections.filter(c => c.status === 'active').length === 0 && (
                <Alert
                  type="warning"
                  message="暂无可用的番茄连接"
                  description="请先在「账号中心」配置并验证番茄 Cookie"
                  style={{ marginTop: 8 }}
                />
              )}
            </Form.Item>

            {/* 内容类型 */}
            {selectedConn && (
              <Form.Item label={<Text style={{ color: theme.textPrimary }}>内容类型</Text>}>
                <Space>
                  {getPlatformContentTypes(
                    connections.find(c => c.id === selectedConn)?.platform || ''
                  ).map(t => (
                    <Button
                      key={t.value}
                      type={contentType === t.value ? 'primary' : 'default'}
                      icon={t.icon}
                      onClick={() => setContentType(t.value as any)}
                    >
                      {t.label}
                    </Button>
                  ))}
                </Space>
              </Form.Item>
            )}

            {/* 标题 */}
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>标题</Text>}>
              <Input
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="请输入章节标题（最多100字）"
                maxLength={100}
                showCount
              />
            </Form.Item>

            {/* 正文 */}
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>章节正文</Text>}>
              <TextArea
                value={body}
                onChange={e => setBody(e.target.value)}
                placeholder="请输入要保存到番茄草稿的章节正文..."
                rows={6}
                maxLength={2000}
                showCount
              />
            </Form.Item>

            <Divider orientation="left">番茄草稿目标</Divider>
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>书籍 ID</Text>} required>
              <Input value={target.book_id} onChange={event => setTarget(current => ({ ...current, book_id: event.target.value }))} placeholder="在番茄后台创建后填入" />
            </Form.Item>
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>卷 ID</Text>} required>
              <Input value={target.volume_id} onChange={event => setTarget(current => ({ ...current, volume_id: event.target.value }))} placeholder="在番茄后台创建后填入" />
            </Form.Item>
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>卷名称（可选）</Text>}>
              <Input value={target.volume_name} onChange={event => setTarget(current => ({ ...current, volume_name: event.target.value }))} />
            </Form.Item>
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>章节 item ID</Text>} required>
              <Input value={target.item_id} onChange={event => setTarget(current => ({ ...current, item_id: event.target.value }))} placeholder="必须是番茄后台已创建的章节" />
            </Form.Item>
            {preflightMessage && <Alert type={preflightMessage.startsWith('本地预检通过') ? 'success' : 'error'} showIcon message={preflightMessage} style={{ marginBottom: 16 }} />}

            {/* 发布按钮 */}
            <Divider />
            <Form.Item>
              <Space direction="vertical" style={{ width: '100%' }} size={10}>
                <Button icon={<CheckCircleOutlined />} onClick={handlePreflight} loading={preflighting} block>预检草稿目标</Button>
                <Button type="primary" size="large" icon={<SendOutlined />} onClick={handlePublish} loading={publishing} disabled={!selectedConn || !title.trim() || !body.trim()} style={{ width: '100%', height: 48 }}>
                  保存到番茄草稿
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>

        {/* 右侧：发布结果 */}
        <Card
          style={{
            background: theme.bgCard,
            border: '1px solid ' + theme.border,
            flex: 1,
            minWidth: 300,
          }}
          title={<Text style={{ color: theme.textPrimary }}>发布结果</Text>}
        >
          {publishing ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin size="large" />
              <p style={{ color: theme.textSecondary, marginTop: 16 }}>正在发布中...</p>
            </div>
          ) : publishResults.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <SendOutlined style={{ fontSize: 48, color: theme.textSecondary }} />
              <p style={{ color: theme.textSecondary, marginTop: 16 }}>
                填写左侧表单并点击发布
              </p>
            </div>
          ) : (
            <List
              dataSource={publishResults}
              renderItem={item => (
                <List.Item>
                  <List.Item.Meta
                    avatar={
                      item.success ? (
                        <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 24 }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 24 }} />
                      )
                    }
                    title={
                      <Text style={{ color: '#e0e0e0' }}>
                        {item.platform} - {item.success ? '发布成功' : '发布失败'}
                      </Text>
                    }
                    description={
                      <div>
                        <Text type="secondary">{item.message}</Text>
                        {item.postUrl && (
                          <div>
                            <a href={item.postUrl} target="_blank" rel="noreferrer">
                              查看发布内容
                            </a>
                          </div>
                        )}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      </div>
    </div>
  )
}
