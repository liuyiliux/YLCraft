/**
 * YLCraft — Dashboard 概览页面
 */

import { Card, Row, Col, Statistic, Progress, Space, Tag } from 'antd'
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

export default function DashboardPage() {
  const navigate = useNavigate()

  const featureCards = [
    {
      title: 'AI 图像生成',
      icon: <PictureOutlined />,
      desc: '文生图 / 图生图，支持多种风格',
      path: '/image-gen',
      color: '#7c3aed',
      gradient: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
      status: 'ready',
    },
    {
      title: 'AI 视频生成',
      icon: <VideoCameraOutlined />,
      desc: '文生视频 / 图生视频，自动配音',
      path: '/video-gen',
      color: '#ec4899',
      gradient: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
      status: 'ready',
    },
    {
      title: '爆款拆解',
      icon: <ExperimentOutlined />,
      desc: '分析视频文案结构与分镜',
      path: '/breaker',
      color: '#3b82f6',
      gradient: 'linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%)',
      status: 'ready',
    },
    {
      title: '视频剪辑',
      icon: <ScissorOutlined />,
      desc: 'CutClaw / NarratoAI / MoE',
      path: '/clip',
      color: '#10b981',
      gradient: 'linear-gradient(135deg, #10b981 0%, #34d399 100%)',
      status: 'ready',
    },
    {
      title: '短剧创作',
      icon: <BookOutlined />,
      desc: 'AI 生成角色立绘与分镜',
      path: '/story',
      color: '#f59e0b',
      gradient: 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)',
      status: 'beta',
    },
    {
      title: 'Live 2D 工厂',
      icon: <FireOutlined />,
      desc: 'Live 2D 全自动生产线（COSER）',
      path: '/live2d',
      color: '#8b5cf6',
      gradient: 'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)',
      status: 'dev',
    },
  ]

  return (
    <div>
      {/* 欢迎卡片 */}
      <Card
        style={{
          marginBottom: 24,
          background: 'linear-gradient(135deg, #1a1a2e 0%, #2d2d4a 100%)',
          border: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        <Row align="middle" gutter={24}>
          <Col flex="auto">
            <div style={{ fontSize: 28, fontWeight: 700, color: '#ffffff', marginBottom: 8 }}>
              <FireOutlined style={{ color: '#ec4899', marginRight: 12 }} />
              欢迎使用 YLCraft
            </div>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>
              AI 驱动的短视频创作平台，支持电商、摄影、短剧、COSER 四大场景
            </div>
          </Col>
          <Col>
            <Space size={24}>
              <Statistic
                title={<span style={{ color: 'rgba(255,255,255,0.5)' }}>今日生成</span>}
                value={128}
                prefix={<PictureOutlined />}
                valueStyle={{ color: '#7c3aed', fontWeight: 600 }}
              />
              <Statistic
                title={<span style={{ color: 'rgba(255,255,255,0.5)' }}>本周完成</span>}
                value={892}
                prefix={<CheckCircleOutlined />}
                valueStyle={{ color: '#10b981', fontWeight: 600 }}
              />
              <Statistic
                title={<span style={{ color: 'rgba(255,255,255,0.5)' }}>进行中</span>}
                value={5}
                prefix={<ClockCircleOutlined />}
                valueStyle={{ color: '#f59e0b', fontWeight: 600 }}
              />
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 功能卡片 */}
      <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 12, color: '#e2e8f0' }}>
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
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: 12,
                cursor: item.status === 'ready' ? 'pointer' : 'not-allowed',
                opacity: item.status === 'dev' ? 0.6 : 1,
              }}
              styles={{
                body: { padding: 24 },
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                <div
                  style={{
                    width: 56,
                    height: 56,
                    borderRadius: 12,
                    background: item.gradient,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 24,
                    color: '#fff',
                    flexShrink: 0,
                  }}
                >
                  {item.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: 16, color: '#e2e8f0' }}>
                      {item.title}
                    </span>
                    {item.status === 'beta' && <Tag color="orange">Beta</Tag>}
                    {item.status === 'dev' && <Tag color="blue">开发中</Tag>}
                  </div>
                  <div style={{ fontSize: 13, color: '#8b8ba8' }}>
                    {item.desc}
                  </div>
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
            title={<span style={{ color: '#e2e8f0' }}>📊 本周使用趋势</span>}
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <div style={{ padding: '0 12px' }}>
              {[
                { label: '图像生成', value: 456, total: 500, color: '#7c3aed' },
                { label: '视频生成', value: 123, total: 200, color: '#ec4899' },
                { label: '爆款拆解', value: 89, total: 100, color: '#3b82f6' },
                { label: '视频剪辑', value: 234, total: 300, color: '#10b981' },
              ].map(item => (
                <div key={item.label} style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ color: '#8b8ba8', fontSize: 12 }}>{item.label}</span>
                    <span style={{ color: '#e2e8f0', fontSize: 12 }}>{item.value} / {item.total}</span>
                  </div>
                  <Progress
                    percent={(item.value / item.total) * 100}
                    showInfo={false}
                    strokeColor={item.color}
                    trailColor="rgba(255,255,255,0.1)"
                    size="small"
                  />
                </div>
              ))}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card
            title={<span style={{ color: '#e2e8f0' }}>⚡ 快捷操作</span>}
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
            }}
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
                    style={{
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid rgba(255,255,255,0.06)',
                      textAlign: 'center',
                    }}
                    styles={{ body: { padding: 16 } }}
                  >
                    <div style={{ fontSize: 24, color: item.color, marginBottom: 4 }}>
                      {item.icon}
                    </div>
                    <div style={{ color: '#8b8ba8', fontSize: 12 }}>{item.label}</div>
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
