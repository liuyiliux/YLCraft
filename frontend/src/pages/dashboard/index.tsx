/**
 * YLCraft — Dashboard 概览页面（深色主题）
 */

import { Card, Row, Col, Statistic, Progress, Space, Tag, Spin } from 'antd'
import {
  DashboardOutlined,
  ExperimentOutlined,
  ScissorOutlined,
  BookOutlined,
  PictureOutlined,
  VideoCameraOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FireOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useTheme } from '../../constants/theme'

// 任务统计类型
interface TaskStats {
  total: number
  completed: number
  pending: number
  running: number
  failed: number
  images: number
  videos: number
  characters: number
  stories: number
  today_count: number
  week_count: number
}

const API_BASE = '/api/v1'

export default function DashboardPage() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<TaskStats>({
    total: 0, completed: 0, pending: 0, running: 0, failed: 0,
    images: 0, videos: 0, characters: 0, stories: 0,
    today_count: 0, week_count: 0,
  })

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE}/tasks/stats`)
        const data = await res.json()
        if (data.success && data.stats) setStats(data.stats)
      } catch (e) { console.error('Failed to fetch stats:', e) }
      finally { setLoading(false) }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const handle = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handle)
    return () => window.removeEventListener('resize', handle)
  }, [])

  const featureCards = [
    { title: 'AI 图像生成', icon: <PictureOutlined />, desc: '文生图 / 图生图，支持多种风格', path: '/image-gen', color: '#7c3aed', gradient: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)', status: 'ready' },
    { title: 'AI 视频生成', icon: <VideoCameraOutlined />, desc: '文生视频 / 图生视频，自动配音', path: '/video-gen', color: '#ec4899', gradient: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)', status: 'ready' },
    { title: '爆款拆解', icon: <ExperimentOutlined />, desc: '分析视频文案结构与分镜', path: '/breaker', color: '#3b82f6', gradient: 'linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%)', status: 'ready' },
    { title: '视频剪辑', icon: <ScissorOutlined />, desc: 'CutClaw / NarratoAI / MoE', path: '/clip', color: '#10b981', gradient: 'linear-gradient(135deg, #10b981 0%, #34d399 100%)', status: 'ready' },
    { title: '短剧创作', icon: <BookOutlined />, desc: 'AI 生成角色立绘与分镜', path: '/story', color: '#f59e0b', gradient: 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)', status: 'beta' },
    { title: 'Live2D 工厂', icon: <FireOutlined />, desc: 'Live2D 全自动生产线（COSER）', path: '/live2d', color: '#8b5cf6', gradient: 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)', status: 'dev' },
  ]

  return (
    <div>
      {/* 欢迎卡片 */}
      <Card
        style={{
          marginBottom: 24,
          background: THEME.gradientWelcome,
          border: `1px solid ${THEME.border}`,
        }}
      >
        <Row align="middle" gutter={[24, 16]}>
          <Col flex="auto">
            <div style={{ fontSize: isMobile ? 20 : 28, fontWeight: 700, color: THEME.textPrimary, marginBottom: 8 }}>
              <FireOutlined style={{ color: THEME.coser, marginRight: 8 }} />
              欢迎使用 YLCraft
            </div>
            <div style={{ color: THEME.textSecondary, fontSize: isMobile ? 12 : 14 }}>
              AI 驱动的短视频创作平台，支持电商、摄影、短剧、COSER 四大场景
            </div>
          </Col>
          {!isMobile && (
            <Col>
              <Space size={24}>
                <Statistic
                  title={<span style={{ color: THEME.textSecondary }}>今日生成</span>}
                  value={stats.today_count || stats.total}
                  prefix={<PictureOutlined />}
                  valueStyle={{ color: '#7c3aed', fontWeight: 600 }}
                />
                <Statistic
                  title={<span style={{ color: THEME.textSecondary }}>本周完成</span>}
                  value={stats.completed}
                  prefix={<CheckCircleOutlined />}
                  valueStyle={{ color: '#10b981', fontWeight: 600 }}
                />
                <Statistic
                  title={<span style={{ color: THEME.textSecondary }}>进行中</span>}
                  value={stats.running + stats.pending}
                  prefix={<ClockCircleOutlined />}
                  valueStyle={{ color: '#f59e0b', fontWeight: 600 }}
                />
              </Space>
            </Col>
          )}
        </Row>
      </Card>

      {/* 功能卡片 */}
      <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 12, color: THEME.textPrimary }}>
        <DashboardOutlined style={{ marginRight: 8 }} />
        核心功能
      </div>
      <Row gutter={[16, 16]}>
        {featureCards.map(item => (
          <Col xs={24} sm={12} md={8} lg={8} key={item.path}>
            <Card
              hoverable
              onClick={() => item.status === 'ready' && navigate(item.path)}
              style={{
                background: THEME.bgCard,
                border: `1px solid ${THEME.border}`,
                borderRadius: 12,
                cursor: item.status === 'ready' ? 'pointer' : 'not-allowed',
                opacity: item.status === 'dev' ? 0.6 : 1,
              }}
              styles={{ body: { padding: 24 } }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                <div style={{ width: 56, height: 56, borderRadius: 12, background: item.gradient, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, color: '#fff', flexShrink: 0 }}>
                  {item.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: 16, color: THEME.textPrimary }}>{item.title}</span>
                    {item.status === 'beta' && <Tag color="orange">Beta</Tag>}
                    {item.status === 'dev' && <Tag color="blue">开发中</Tag>}
                  </div>
                  <div style={{ fontSize: 13, color: THEME.textSecondary }}>{item.desc}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 快速统计 */}
      <Row gutter={16} style={{ marginTop: 24 }}>
        <Col xs={24} md={12}>
          <Card
            title={<span style={{ color: THEME.textPrimary }}>📊 本周使用趋势</span>}
            style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
          >
            <div style={{ padding: '0 12px' }}>
              {[
                { label: '图像生成', value: stats.images, total: Math.max(stats.images, 10), color: '#7c3aed' },
                { label: '视频生成', value: stats.videos, total: Math.max(stats.videos, 5), color: '#ec4899' },
                { label: '角色创建', value: stats.characters, total: Math.max(stats.characters, 3), color: '#3b82f6' },
                { label: '短剧创作', value: stats.stories, total: Math.max(stats.stories, 2), color: '#10b981' },
              ].map(item => (
                <div key={item.label} style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ color: THEME.textSecondary, fontSize: 12 }}>{item.label}</span>
                    <span style={{ color: THEME.textPrimary, fontSize: 12 }}>{item.value}</span>
                  </div>
                  <Progress percent={item.total > 0 ? (item.value / item.total) * 100 : 0} showInfo={false} strokeColor={item.color} trailColor="rgba(255,255,255,0.06)" size="small" />
                </div>
              ))}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card
            title={<span style={{ color: THEME.textPrimary }}>⚡ 快捷操作</span>}
            style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
          >
            <Row gutter={[12, 12]}>
              {[
                { label: '生成图像', icon: <PictureOutlined />, path: '/image-gen', color: '#7c3aed' },
                { label: '生成视频', icon: <VideoCameraOutlined />, path: '/video-gen', color: '#ec4899' },
                { label: '下载素材', icon: <ThunderboltOutlined />, path: '/download', color: '#3b82f6' },
                { label: '查看任务', icon: <CheckCircleOutlined />, path: '/tasks', color: '#10b981' },
              ].map(item => (
                <Col span={12} key={item.path}>
                  <Card
                    hoverable
                    onClick={() => navigate(item.path)}
                    style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, textAlign: 'center' }}
                    styles={{ body: { padding: 16 } }}
                  >
                    <div style={{ fontSize: 24, color: item.color, marginBottom: 4 }}>{item.icon}</div>
                    <div style={{ color: THEME.textSecondary, fontSize: 12 }}>{item.label}</div>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
