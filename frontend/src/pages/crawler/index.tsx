import { useState, useEffect } from 'react'
import {
  Card,
  Input,
  Button,
  Select,
  Table,
  Tag,
  message,
  Spin,
  Space,
  Row,
  Col,
  Typography,
  Alert,
  Tooltip,
  Modal,
  Image,
} from 'antd'
import {
  SearchOutlined,
  DownloadOutlined,
  BookOutlined,
  VideoCameraOutlined,
  PlayCircleOutlined,
  MessageOutlined,
  QuestionCircleOutlined,
  GlobalOutlined,
  ImportOutlined,
  EyeOutlined,
  TwitterOutlined,
  YoutubeOutlined,
} from '@ant-design/icons'
import { searchCrawler, importCrawler, getCrawlerPlatforms, getCrawlerOptions } from '../../api'
import type { CrawlerResult } from '../../api'

const { Text, Title, Paragraph } = Typography

// 平台图标映射
const PLATFORM_ICONS: Record<string, React.ReactNode> = {
  // 国内平台
  xhs: <BookOutlined style={{ color: '#fe2c55' }} />,
  dy: <VideoCameraOutlined style={{ color: '#000000' }} />,
  ks: <PlayCircleOutlined style={{ color: '#ff5000' }} />,
  bili: <PlayCircleOutlined style={{ color: '#00aeec' }} />,
  wb: <MessageOutlined style={{ color: '#ff8200' }} />,
  zhihu: <QuestionCircleOutlined style={{ color: '#0066ff' }} />,
  // 国际平台
  twitter: <TwitterOutlined style={{ color: '#1DA1F2' }} />,
  tiktok: <PlayCircleOutlined style={{ color: '#ff0050' }} />,
  instagram: <PlayCircleOutlined style={{ color: '#E4405F' }} />,
  threads: <GlobalOutlined style={{ color: '#000000' }} />,
  youtube: <YoutubeOutlined style={{ color: '#FF0000' }} />,
}

// 平台颜色映射
const PLATFORM_COLORS: Record<string, string> = {
  // 国内平台
  xhs: '#fe2c55',
  dy: '#000000',
  ks: '#ff5000',
  bili: '#00aeec',
  wb: '#ff8200',
  zhihu: '#0066ff',
  // 国际平台
  twitter: '#1DA1F2',
  tiktok: '#ff0050',
  instagram: '#E4405F',
  threads: '#000000',
  youtube: '#FF0000',
}

export default function CrawlerPage() {
  const [platform, setPlatform] = useState<string>('bili')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<CrawlerResult[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [selectedRows, setSelectedRows] = useState<CrawlerResult[]>([])
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [total, setTotal] = useState(0)
  const [using, setUsing] = useState('')
  const [platforms, setPlatforms] = useState<any[]>([])
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')

  // 加载平台列表
  useEffect(() => {
    loadPlatforms()
  }, [])

  const loadPlatforms = async () => {
    try {
      const data = await getCrawlerPlatforms()
      setPlatforms(data.platforms || [])
    } catch (e) {
      // 使用默认平台
      setPlatforms([
        // 国内平台
        { value: 'xhs', label: '小红书', icon: 'book' },
        { value: 'dy', label: '抖音', icon: 'video' },
        { value: 'ks', label: '快手', icon: 'play-circle' },
        { value: 'bili', label: 'B站', icon: 'play-circle' },
        { value: 'wb', label: '微博', icon: 'message' },
        { value: 'zhihu', label: '知乎', icon: 'question-circle' },
        // 国际平台
        { value: 'twitter', label: 'Twitter/X', icon: 'twitter' },
        { value: 'tiktok', label: 'TikTok', icon: 'play-circle' },
        { value: 'instagram', label: 'Instagram', icon: 'play-circle' },
        { value: 'threads', label: 'Threads', icon: 'global' },
        { value: 'youtube', label: 'YouTube', icon: 'youtube' },
      ])
    }
  }

  const handleSearch = async () => {
    if (!keyword.trim()) {
      message.warning('请输入搜索关键词')
      return
    }

    setLoading(true)
    setError('')
    setResults([])
    setSelectedRowKeys([])
    setSelectedRows([])

    try {
      const data = await searchCrawler({
        platform,
        keyword: keyword.trim(),
        max_results: 20,
      })
      setResults(data.results || [])
      setTotal(data.total || 0)
      setUsing(data.using || '')
      message.success(`找到 ${data.total || 0} 条结果`)
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || '搜索失败，请检查后端服务'
      setError(errorMsg)
      message.error(errorMsg)
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    if (selectedRows.length === 0) {
      message.warning('请先选择要导入的素材')
      return
    }

    setImporting(true)
    try {
      const data = await importCrawler({
        results: selectedRows.map(r => ({
          id: r.id,
          platform: r.platform,
          title: r.title,
          desc: r.desc,
          cover: r.cover,
          video_url: r.video_url,
          author: r.author,
          url: r.url,
        })),
      })
      message.success(`成功导入 ${data.imported_count || 0} 条素材到素材库`)
      setSelectedRowKeys([])
      setSelectedRows([])
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || '导入失败'
      message.error(errorMsg)
    } finally {
      setImporting(false)
    }
  }

  const handlePreview = (url: string) => {
    if (!url) return
    setPreviewUrl(url)
    setPreviewVisible(true)
  }

  // 表格列定义
  const columns = [
    {
      title: '封面',
      dataIndex: 'cover',
      key: 'cover',
      width: 120,
      render: (cover: string, record: CrawlerResult) => (
        cover ? (
          <Image
            src={cover}
            alt={record.title}
            width={80}
            height={60}
            style={{ objectFit: 'cover', borderRadius: 4 }}
            fallback="data:image/png;base64,..."
          />
        ) : (
          <div style={{
            width: 80,
            height: 60,
            background: '#1a1a2e',
            borderRadius: 4,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <VideoCameraOutlined style={{ fontSize: 20, color: '#4a4a6a' }} />
          </div>
        )
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text: string, record: CrawlerResult) => (
        <Tooltip title={text}>
          <a
            href={record.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#e0e0e0' }}
          >
            {text || '无标题'}
          </a>
        </Tooltip>
      ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      width: 100,
      render: (platform: string) => (
        <Tag
          icon={PLATFORM_ICONS[platform]}
          style={{
            borderColor: PLATFORM_COLORS[platform] || '#8b8ba8',
            color: PLATFORM_COLORS[platform] || '#8b8ba8',
          }}
        >
          {platform}
        </Tag>
      ),
    },
    {
      title: '作者',
      dataIndex: 'author',
      key: 'author',
      width: 120,
      ellipsis: true,
    },
    {
      title: '数据',
      key: 'stats',
      width: 150,
      render: (_: any, record: CrawlerResult) => (
        <Space size="small">
          <Text style={{ color: '#8b8ba8', fontSize: 12 }}>
            ❤️ {record.likes || 0}
          </Text>
          <Text style={{ color: '#8b8ba8', fontSize: 12 }}>
            💬 {record.comments || 0}
          </Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: any, record: CrawlerResult) => (
        <Space>
          {record.cover && (
            <Tooltip title="预览封面">
              <Button
                type="text"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => handlePreview(record.cover)}
              />
            </Tooltip>
          )}
          {record.url && (
            <Tooltip title="打开原链接">
              <Button
                type="text"
                size="small"
                icon={<GlobalOutlined />}
                href={record.url}
                target="_blank"
              />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1200 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        🕷️ 素材采集
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          搜索国内外平台视频/图文素材，支持批量导入素材库
        </Text>
      </Title>

      {/* 搜索卡片 */}
      <Card style={{
        background: '#1a1a2e',
        marginBottom: 24,
        border: '1px solid rgba(255,255,255,0.08)',
      }}>
        <Row gutter={12} align="middle">
          <Col span={6}>
            <Select
              value={platform}
              onChange={setPlatform}
              style={{ width: '100%' }}
              options={platforms.map(p => ({
                value: p.value,
                label: (
                  <Space>
                    {PLATFORM_ICONS[p.value]}
                    {p.label}
                  </Space>
                ),
              }))}
            />
          </Col>
          <Col span={14}>
            <Input
              size="large"
              placeholder="输入关键词搜索素材..."
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onPressEnter={handleSearch}
              prefix={<SearchOutlined style={{ color: '#8b8ba8' }} />}
              style={{ background: '#12122a' }}
            />
          </Col>
          <Col span={4}>
            <Button
              type="primary"
              size="large"
              icon={<SearchOutlined />}
              onClick={handleSearch}
              loading={loading}
              style={{ width: '100%', height: 44 }}
            >
              搜索
            </Button>
          </Col>
        </Row>

        {/* 快捷关键词 */}
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' as const }}>
          {[
            // 国内
            'AI教程', '短剧片段', '美食探店', '穿搭分享', '数码评测',
            // 国际
            'vlog', 'tutorial', 'food', 'travel', 'fashion'
          ].map(k => (
            <Tag
              key={k}
              style={{
                cursor: 'pointer',
                borderColor: keyword === k ? '#00d4ff' : 'rgba(255,255,255,0.15)',
                color: keyword === k ? '#00d4ff' : '#8b8ba8',
                background: keyword === k ? 'rgba(0,212,255,0.08)' : 'transparent',
              }}
              onClick={() => {
                setKeyword(k)
              }}
            >
              {k}
            </Tag>
          ))}
        </div>
      </Card>

      {/* 错误提示 */}
      {error && (
        <Alert
          type="error"
          message={error}
          style={{ marginBottom: 16 }}
          showIcon
          closable
          onClose={() => setError('')}
        />
      )}

      {/* 搜索结果 */}
      {results.length > 0 && (
        <Card style={{
          background: '#1a1a2e',
          border: '1px solid rgba(255,255,255,0.08)',
        }}
        title={
          <Space>
            <Text style={{ color: '#fff' }}>
              搜索结果 ({total})
            </Text>
            {using && (
              <Tag color="blue">使用: {using}</Tag>
            )}
          </Space>
        }
        extra={
          <Space>
            <Text style={{ color: '#8b8ba8' }}>
              已选 {selectedRows.length} 项
            </Text>
            <Button
              type="primary"
              icon={<ImportOutlined />}
              onClick={handleImport}
              loading={importing}
              disabled={selectedRows.length === 0}
            >
              导入到素材库 ({selectedRows.length})
            </Button>
          </Space>
        }
        >
          <Table
            rowKey="id"
            columns={columns}
            dataSource={results}
            loading={loading}
            pagination={{ pageSize: 10, showTotal: (total: number) => `共 ${total} 条` }}
            rowSelection={{
              selectedRowKeys,
              onChange: (keys: React.Key[], rows: CrawlerResult[]) => {
                setSelectedRowKeys(keys)
                setSelectedRows(rows)
              },
            }}
            style={{ color: '#e0e0e0' }}
            scroll={{ x: 800 }}
          />
        </Card>
      )}

      {/* 空状态 */}
      {!loading && results.length === 0 && !error && (
        <Card style={{
          background: '#1a1a2e',
          border: '1px solid rgba(255,255,255,0.08)',
          textAlign: 'center',
          padding: '60px 0',
        }}>
          <SearchOutlined style={{ fontSize: 48, color: '#4a4a6a', marginBottom: 16 }} />
          <Title level={4} style={{ color: '#8b8ba8' }}>
            输入关键词开始搜索
          </Title>
          <Text style={{ color: '#4a4a6a' }}>
            支持搜索国内外平台的视频和图文素材：抖音、小红书、B站、快手、微博、知乎、Twitter、TikTok、Instagram、YouTube 等
          </Text>
        </Card>
      )}

      {/* 封面预览 */}
      <Modal
        open={previewVisible}
        footer={null}
        onCancel={() => setPreviewVisible(false)}
        width={800}
      >
        <img src={previewUrl} alt="封面预览" style={{ width: '100%' }} />
      </Modal>
    </div>
  )
}
