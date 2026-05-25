/**
 * YLCraft — 自媒体平台概览页
 * 去重重构：每个路由只出现 1 次，补小说入口
 */
import { Card, Row, Col, Statistic, Progress, Tag, Button, Space, Typography, Collapse } from 'antd'
import type { StatisticProps } from 'antd'
import {
  DashboardOutlined,
  ExperimentOutlined,
  ScissorOutlined,
  BookOutlined,
  PictureOutlined,
  VideoCameraOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FireOutlined,
  ArrowRightOutlined,
  RocketOutlined,
  HistoryOutlined,
  FileAddOutlined,
  DownloadOutlined,
  ReadOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useTheme } from '../../constants/theme'

const { Text } = Typography

interface TaskStats {
  total: number; completed: number; pending: number; running: number; failed: number
  images: number; videos: number; characters: number; stories: number
  today_count: number; week_count: number
}

const API_BASE = '/api/v1'

const FEATURE_CARDS = [
  { title: 'AI 图像生成', icon: <PictureOutlined />,       desc: '文生图 / 图生图',       path: '/image-gen',    gradient: 'linear-gradient(135deg, #7c3aed, #a855f7)',  status: 'ready' as const },
  { title: 'AI 视频生成', icon: <VideoCameraOutlined />,   desc: '文生视频 / 图生视频',   path: '/video-gen',    gradient: 'linear-gradient(135deg, #ec4899, #f472b6)',  status: 'ready' as const },
  { title: '小说搜索',    icon: <ReadOutlined />,          desc: '多源搜索与书架',        path: '/novel-search', gradient: 'linear-gradient(135deg, #f59e0b, #fbbf24)',  status: 'ready' as const },
  { title: '多平台下载',  icon: <DownloadOutlined />,      desc: 'B站 / 抖音 / Twitter',  path: '/download',     gradient: 'linear-gradient(135deg, #3b82f6, #60a5fa)',  status: 'ready' as const },
  { title: 'AI 视频剪辑', icon: <ScissorOutlined />,       desc: 'CutClaw / NarratoAI',   path: '/clip',         gradient: 'linear-gradient(135deg, #10b981, #34d399)',  status: 'ready' as const },
  { title: '爆款拆解',    icon: <ExperimentOutlined />,    desc: '文案 / 分镜分析',        path: '/breaker',      gradient: 'linear-gradient(135deg, #6366f1, #818cf8)',  status: 'ready' as const },
  { title: '素材管理',    icon: <FileAddOutlined />,       desc: '统一素材库',             path: '/assets',       gradient: 'linear-gradient(135deg, #06b6d4, #22d3ee)', status: 'ready' as const },
]

const BETA_CARDS = [
  { title: '短剧创作',    icon: <BookOutlined />,          desc: '角色立绘与分镜',         path: '/story',        gradient: 'linear-gradient(135deg, #fb923c, #fbbf24)',  status: 'beta' as const },
  { title: 'Live2D 工厂', icon: <FireOutlined />,          desc: 'COSER 全自动生产线',     path: '/live2d',       gradient: 'linear-gradient(135deg, #a78bfa, #c4b5fd)',  status: 'dev' as const },
]

const TREND_DATA = [
  { label: '图像生成', key: 'images', color: '#7c3aed' },
  { label: '视频生成', key: 'videos', color: '#ec4899' },
  { label: '角色创建', key: 'characters', color: '#3b82f6' },
  { label: '短剧创作', key: 'stories', color: '#10b981' },
]

export default function DashboardPage() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
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
    }
    fetchStats()
    const timer = setInterval(fetchStats, 30000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const handle = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handle)
    return () => window.removeEventListener('resize', handle)
  }, [])

  const statItems: StatisticProps[] = [
    { title: <span style={{ color: THEME.textSecondary, fontSize: 12 }}>今日生成</span>, value: stats.today_count || stats.total, prefix: <PictureOutlined />, valueStyle: { color: '#7c3aed', fontWeight: 600 } },
    { title: <span style={{ color: THEME.textSecondary, fontSize: 12 }}>本周完成</span>, value: stats.week_count || stats.completed, prefix: <CheckCircleOutlined />, valueStyle: { color: '#10b981', fontWeight: 600 } },
    { title: <span style={{ color: THEME.textSecondary, fontSize: 12 }}>进行中</span>, value: stats.running + stats.pending, prefix: <ClockCircleOutlined />, valueStyle: { color: '#f59e0b', fontWeight: 600 } },
  ]

  return (
    <div>
      {/* ===== Section 1: Hero ===== */}
      <Card
        style={{
          marginBottom: 20,
          background: THEME.gradientWelcome,
          border: `1px solid ${THEME.border}`,
          borderRadius: 12,
        }}
        styles={{ body: { padding: isMobile ? 16 : 24 } }}
      >
        <Row align="middle" gutter={[16, 12]}>
          <Col flex="auto">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: isMobile ? 20 : 24, fontWeight: 700, color: THEME.textPrimary }}>
                <FireOutlined style={{ color: THEME.coser, marginRight: 8 }} />
                YL<span style={{ color: THEME.primary }}>Craft</span>
              </div>
              <div style={{ color: THEME.textSecondary, fontSize: 14, lineHeight: 1.5, maxWidth: 480 }}>
                AI 驱动的自媒体创作平台 — 支持内容创作、素材管理、多平台发布一站式完成
              </div>
              <div style={{ marginTop: 4 }}>
                <Button type="primary" icon={<RocketOutlined />} onClick={() => navigate('/image-gen')} style={{ background: THEME.gradientCreative, border: 'none', fontWeight: 600, borderRadius: 8 }}>
                  开始创作
                </Button>
              </div>
            </div>
          </Col>
          {!isMobile && (
            <Col>
              <Space size={20} style={{ background: THEME.bgCard, padding: '16px 20px', borderRadius: 10, border: `1px solid ${THEME.border}` }}>
                {statItems.map((stat, i) => <Statistic key={i} {...stat} />)}
              </Space>
            </Col>
          )}
        </Row>
      </Card>

      {/* ===== Section 2: 核心功能 ===== */}
      <div style={{ marginBottom: 12 }}>
        <Space size={8} style={{ marginBottom: 12 }}>
          <DashboardOutlined style={{ color: THEME.primary }} />
          <span style={{ color: THEME.textPrimary, fontWeight: 600, fontSize: 16 }}>核心功能</span>
        </Space>
        <Row gutter={[12, 12]}>
          {FEATURE_CARDS.map(item => (
            <Col xs={24} sm={12} md={8} lg={24 / 7} key={item.path}>
              <Card
                hoverable
                onClick={() => navigate(item.path)}
                style={{
                  background: THEME.bgCard,
                  border: `1px solid ${THEME.border}`,
                  borderRadius: 12,
                  cursor: 'pointer',
                }}
                styles={{ body: { padding: 20 } }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: item.gradient, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: '#fff', flexShrink: 0 }}>
                    {item.icon}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, color: THEME.textPrimary, marginBottom: 2 }}>{item.title}</div>
                    <div style={{ fontSize: 12, color: THEME.textSecondary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.desc}</div>
                  </div>
                  <ArrowRightOutlined style={{ color: THEME.textSecondary, fontSize: 12, flexShrink: 0, alignSelf: 'center' }} />
                </div>
              </Card>
            </Col>
          ))}
        </Row>

        {/* 实验功能 (Beta / 开发中) */}
        <Collapse
          ghost
          size="small"
          items={[{
            key: 'experimental',
            label: <span style={{ color: THEME.textSecondary, fontSize: 13 }}>实验功能（{BETA_CARDS.length} 项）</span>,
            children: (
              <Row gutter={[12, 12]}>
                {BETA_CARDS.map(item => (
                  <Col xs={24} sm={12} key={item.path}>
                    <Card
                      onClick={() => item.status === 'beta' && navigate(item.path)}
                      style={{
                        background: THEME.bgCard,
                        border: `1px solid ${THEME.border}`,
                        borderRadius: 12,
                        cursor: item.status === 'beta' ? 'pointer' : 'not-allowed',
                        opacity: 0.65,
                      }}
                      styles={{ body: { padding: 16 } }}
                    >
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                        <div style={{ width: 40, height: 40, borderRadius: 10, background: item.gradient, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: '#fff', flexShrink: 0 }}>
                          {item.icon}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                            <span style={{ fontWeight: 600, fontSize: 14, color: THEME.textPrimary }}>{item.title}</span>
                            {item.status === 'beta' && <Tag color="orange" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>Beta</Tag>}
                            {item.status === 'dev' && <Tag color="default" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>开发中</Tag>}
                          </div>
                          <div style={{ fontSize: 12, color: THEME.textSecondary }}>{item.desc}</div>
                        </div>
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            ),
          }]}
        />
      </div>

      {/* ===== Section 3: 使用趋势 (全宽) ===== */}
      <Card
        title={<Space size={8}><HistoryOutlined style={{ color: THEME.primary }} /><span style={{ color: THEME.textPrimary, fontWeight: 600 }}>使用趋势</span></Space>}
        style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}
        styles={{ body: { padding: 20 } }}
      >
        <Row gutter={[24, 12]}>
          {TREND_DATA.map(item => {
            const val = stats[item.key as keyof TaskStats] as number || 0
            const total = Math.max(val, 10)
            return (
              <Col xs={12} md={6} key={item.key}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ color: THEME.textPrimary, fontSize: 22, fontWeight: 700 }}>{val}</div>
                  <div style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 8 }}>{item.label}</div>
                  <Progress percent={Math.round((val / total) * 100)} showInfo={false} strokeColor={item.color} trailColor="rgba(255,255,255,0.06)" size="small" />
                </div>
              </Col>
            )
          })}
        </Row>
      </Card>
    </div>
  )
}
