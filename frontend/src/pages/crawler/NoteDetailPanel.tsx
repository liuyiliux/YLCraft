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
          <div style={{ marginTop: 16, display: 'flex', gap: 16, alignItems: 'center' }}>
            <Text>👍 {detail.likes || 0}</Text>
            <Text>💬 {detail.comments || 0}</Text>
            <Text>🔗 {detail.shares || 0}</Text>
            <Text>⭐ {detail.collects || 0}</Text>
            <Text style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              <svg width="14" height="14" viewBox="0 0 28 28" fill="currentColor"><path fillRule="evenodd" clipRule="evenodd" d="M14.045 25.5454C7.69377 25.5454 2.54504 20.3967 2.54504 14.0454C2.54504 7.69413 7.69377 2.54541 14.045 2.54541C20.3963 2.54541 25.545 7.69413 25.545 14.0454C25.545 17.0954 24.3334 20.0205 22.1768 22.1771C20.0201 24.3338 17.095 25.5454 14.045 25.5454ZM9.66202 6.81624H18.2761C18.825 6.81624 19.27 7.22183 19.27 7.72216C19.27 8.22248 18.825 8.62807 18.2761 8.62807H14.95V10.2903C17.989 10.4444 20.3766 12.9487 20.3855 15.9916V17.1995C20.3854 17.6997 19.9799 18.1052 19.4796 18.1052C18.9793 18.1052 18.5738 17.6997 18.5737 17.1995V15.9916C18.5667 13.9478 16.9882 12.2535 14.95 12.1022V20.5574C14.95 21.0577 14.5444 21.4633 14.0441 21.4633C13.5437 21.4633 13.1382 21.0577 13.1382 20.5574V12.1022C11.1 12.2535 9.52148 13.9478 9.51448 15.9916V17.1995C9.5144 17.6997 9.10883 18.1052 8.60856 18.1052C8.1083 18.1052 7.70273 17.6997 7.70265 17.1995V15.9916C7.71158 12.9487 10.0992 10.4444 13.1382 10.2903V8.62807H9.66202C9.11309 8.62807 8.66809 8.22248 8.66809 7.72216C8.66809 7.22183 9.11309 6.81624 9.66202 6.81624Z" /></svg>
              {detail.coins || 0}
            </Text>
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
