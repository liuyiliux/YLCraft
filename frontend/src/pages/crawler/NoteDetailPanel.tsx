/**
 * YLCraft — 笔记详情面板（无水印）
 * 展示笔记的详细信息，包括无水印图片和视频
 */

import { useState } from 'react'
import { Card, Spin, Alert, Button, Typography, Space, message } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { NoteDetail } from '../../api'

const { Title, Text, Paragraph } = Typography

interface NoteDetailPanelProps {
  platform: string
  noteId: string
  connId?: string
}

export default function NoteDetailPanel({ platform, noteId, connId }: NoteDetailPanelProps) {
  const [detail, setDetail] = useState<NoteDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchDetail = async () => {
    setLoading(true)
    setError(null)
    try {
      // 调用后端 API 获取笔记详情
      const params = new URLSearchParams({
        platform,
        note_id: noteId,
        ...(connId ? { conn_id: connId } : {}),
      })
      
      const res = await fetch(`/api/v1/crawler/note-detail?${params}`)
      const data = await res.json()
      
      if (data.success && data.data) {
        setDetail(data.data)
        message.success('获取笔记详情成功')
      } else {
        throw new Error(data.message || '获取失败')
      }
    } catch (e: any) {
      setError(e.message || '获取失败')
      message.error('获取笔记详情失败')
    } finally {
      setLoading(false)
    }
  }

  const downloadNoWatermark = async () => {
    if (!detail) return
    
    try {
      const params = {
        platform,
        note_ids: [noteId],
      }
      
      const res = await fetch('/api/v1/crawler/fetch-no-watermark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      const data = await res.json()
      
      if (data.success) {
        message.success('开始下载无水印资源')
        // 这里可以触发下载
        console.log('No watermark resources:', data.results)
      } else {
        throw new Error(data.message || '下载失败')
      }
    } catch (e: any) {
      message.error('下载失败：' + e.message)
    }
  }

  return (
    <Card
      title="笔记详情（无水印）"
      extra={
        <Space>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={downloadNoWatermark}
            disabled={!detail}
          >
            下载无水印资源
          </Button>
          <Button onClick={fetchDetail} loading={loading}>
            获取详情
          </Button>
        </Space>
      }
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Spin size="large" />
          <p>正在获取笔记详情...</p>
        </div>
      )}

      {error && (
        <Alert type="error" showIcon message="获取失败" description={error} />
      )}

      {detail && (
        <div>
          <Title level={4}>{detail.title}</Title>
          <Paragraph>{detail.desc}</Paragraph>

          {/* 无水印图片 */}
          {detail.images && detail.images.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>无水印图片：</Text>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                {detail.images.map((url: string, idx: number) => (
                  <img
                    key={idx}
                    src={url}
                    alt={`图片 ${idx + 1}`}
                    style={{ width: 200, height: 'auto', objectFit: 'cover', borderRadius: 4 }}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 无水印视频 */}
          {detail.video && (
            <div style={{ marginTop: 16 }}>
              <Text strong>无水印视频：</Text>
              <div style={{ marginTop: 8 }}>
                <video
                  src={detail.video}
                  controls
                  style={{ width: '100%', maxWidth: 600 }}
                />
              </div>
            </div>
          )}

          {/* 统计信息 */}
          <div style={{ marginTop: 16, display: 'flex', gap: 16 }}>
            <Text>👍 {detail.likes || 0}</Text>
            <Text>💬 {detail.comments || 0}</Text>
            <Text>🔗 {detail.shares || 0}</Text>
            <Text>⭐ {detail.collect_count || 0}</Text>
          </div>

          {/* 标签 */}
          {detail.tags && detail.tags.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>标签：</Text>
              <div style={{ marginTop: 4 }}>
                {detail.tags.map((tag: string, idx: number) => (
                  <span
                    key={idx}
                    style={{
                      display: 'inline-block',
                      background: '#f0f0f0',
                      padding: '2px 8px',
                      borderRadius: 4,
                      marginRight: 4,
                      fontSize: 12,
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 作者信息 */}
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">作者：{detail.author}</Text>
            <br />
            <Text type="secondary">发布时间：{detail.create_time}</Text>
          </div>
        </div>
      )}

      {!loading && !detail && !error && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
          <p>点击"获取详情"按钮查看笔记详情</p>
        </div>
      )}
    </Card>
  )
}
