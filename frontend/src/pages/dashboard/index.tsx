/**
 * YLCraft — Dashboard 概览页面
 */

import { Card, Row, Col, Statistic } from 'antd'
import {
  DashboardOutlined,
  ExperimentOutlined,
  ScissorOutlined,
  BookOutlined,
} from '@ant-design/icons'

export default function DashboardPage() {
  return (
    <div>
      <Card
        title={
          <span>
            <DashboardOutlined style={{ marginRight: 8 }} />
            概览
          </span>
        }
      >
        <Row gutter={16}>
          {[
            { title: '爆款拆解', icon: <ExperimentOutlined />, desc: '分析视频文案结构与分镜', path: '/breaker' },
            { title: '视频剪辑', icon: <ScissorOutlined />, desc: 'CutClaw / NarratoAI / MoE', path: '/clip' },
            { title: '短剧创作', icon: <BookOutlined />, desc: 'AI 生成角色立绘与分镜', path: '/story' },
          ].map(item => (
            <Col xs={24} sm={8} key={item.title}>
              <Card hoverable style={{ textAlign: 'center', marginBottom: 8 }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>{item.icon}</div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{item.title}</div>
                <div style={{ fontSize: 12, color: '#8b8ba8' }}>{item.desc}</div>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  )
}
