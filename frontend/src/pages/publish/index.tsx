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

    if (contentType === 'video' && mediaFiles.length === 0) {
      message.warning('视频发布需要上传视频文件')
      return
    }

    setPublishing(true)
    setPublishResults([])

    try {
      const result = await publishToPlatform(selectedConn, {
        title,
        body,
        content_type: contentType,
        tags,
        media: mediaFiles.map(f => ({ file_path: f.path, media_type: f.type })),
      })

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

  // 获取平台支持的发布类型
  const getPlatformContentTypes = (platform: string) => {
    const p = supportedPlatforms.find(p => p.value === platform)
    if (!p) return []

    const types = []
    if (p.supports_publishing) {
      types.push({ value: 'video', label: '视频', icon: <VideoCameraOutlined /> })
      types.push({ value: 'text', label: '纯文本', icon: <FileTextOutlined /> })
      types.push({ value: 'image', label: '图文', icon: <PictureOutlined /> })
      if (platform === 'bilibili') {
        types.push({ value: 'article', label: '专栏文章', icon: <FileTextOutlined /> })
      }
    }
    return types
  }

  return (
    <div style={{ maxWidth: 1200 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        <SendOutlined style={{ marginRight: 12 }} />
        内容发布
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          一键发布到多个社交平台
        </Text>
      </Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
        message="发布说明"
        description={
          <Paragraph style={{ color: '#8b8ba8', marginBottom: 0 }}>
            选择已配置的平台连接，填写内容信息，即可快速发布到对应平台。
            支持视频、图文、纯文本、专栏文章等多种内容类型。
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
                  .filter(c => c.status === 'active')
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
                  message="暂无活跃连接"
                  description="请先在「平台管理」页面配置平台连接"
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
                placeholder="请输入标题（最多100字）"
                maxLength={100}
                showCount
              />
            </Form.Item>

            {/* 正文 */}
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>正文内容</Text>}>
              <TextArea
                value={body}
                onChange={e => setBody(e.target.value)}
                placeholder="请输入正文内容..."
                rows={6}
                maxLength={2000}
                showCount
              />
            </Form.Item>

            {/* 标签 */}
            <Form.Item label={<Text style={{ color: theme.textPrimary }}>标签</Text>}>
              <Space wrap>
                {tags.map(tag => (
                  <Tag
                    key={tag}
                    closable
                    onClose={() => removeTag(tag)}
                    style={{ color: '#e0e0e0' }}
                  >
                    #{tag}
                  </Tag>
                ))}
                <Input
                  value={tagInput}
                  onChange={e => setTagInput(e.target.value)}
                  placeholder="输入标签"
                  style={{ width: 120 }}
                  onPressEnter={addTag}
                />
                <Button type="dashed" icon={<PlusOutlined />} onClick={addTag}>
                  添加
                </Button>
              </Space>
            </Form.Item>

            {/* 媒体文件 */}
            {(contentType === 'video' || contentType === 'image') && (
              <Form.Item label={<Text style={{ color: theme.textPrimary }}>媒体文件</Text>}>
                <List
                  size="small"
                  dataSource={mediaFiles}
                  renderItem={(file, index) => (
                    <List.Item
                      actions={[
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => removeMediaFile(index)}
                        />,
                      ]}
                    >
                      <Text style={{ color: '#e0e0e0' }}>
                        {file.path} ({file.type})
                      </Text>
                    </List.Item>
                  )}
                />
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={addMediaFile}
                  style={{ marginTop: 8, width: '100%' }}
                >
                  添加文件
                </Button>
                <Text type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
                  {contentType === 'video'
                    ? '支持 MP4, AVI, MOV 格式，最多1个视频'
                    : '支持 JPG, PNG 格式，最多9张图片'}
                </Text>
              </Form.Item>
            )}

            {/* 发布按钮 */}
            <Divider />
            <Form.Item>
              <Button
                type="primary"
                size="large"
                icon={<SendOutlined />}
                onClick={handlePublish}
                loading={publishing}
                disabled={!selectedConn || !title.trim()}
                style={{ width: '100%', height: 48 }}
              >
                发布到平台
              </Button>
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
