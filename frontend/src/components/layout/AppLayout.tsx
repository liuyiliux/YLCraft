import { Layout, Menu, Divider } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import {
  DashboardOutlined,
  ExperimentOutlined,
  ScissorOutlined,
  BookOutlined,
  ThunderboltOutlined,
  SettingOutlined,
  CloudDownloadOutlined,
  FolderOpenOutlined,
  TeamOutlined,
  PictureOutlined,
  VideoCameraOutlined,
  FireOutlined,
} from '@ant-design/icons'

const { Sider, Content, Header } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '概览' },
  { type: 'divider' },
  { key: 'group-ai', type: 'group', label: 'AI 生成' },
  { key: '/image-gen', icon: <PictureOutlined />, label: '图像生成' },
  { key: '/video-gen', icon: <VideoCameraOutlined />, label: '视频生成' },
  { type: 'divider' },
  { key: 'group-create', type: 'group', label: '创作工具' },
  { key: '/breaker', icon: <ExperimentOutlined />, label: '爆款拆解' },
  { key: '/clip-ops', icon: <ScissorOutlined />, label: '视频剪辑' },
  { key: '/clip', icon: <ScissorOutlined />, label: 'Clip Lab' },
  { key: '/story', icon: <BookOutlined />, label: '短剧创作' },
  { type: 'divider' },
  { key: 'group-asset', type: 'group', label: '资产管理' },
  { key: '/download', icon: <CloudDownloadOutlined />, label: '去水印下载' },
  { key: '/assets', icon: <FolderOpenOutlined />, label: '素材库' },
  { key: '/characters', icon: <TeamOutlined />, label: '角色管理' },
  { type: 'divider' },
  { key: 'group-sys', type: 'group', label: '系统' },
  { key: '/tasks', icon: <ThunderboltOutlined />, label: '任务管理' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = menuItems
    .filter(item => item.key && item.key.startsWith('/'))
    .find(item =>
      location.pathname === item.key ||
      (item.key !== '/' && location.pathname.startsWith(item.key))
    )?.key || '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{
        background: 'linear-gradient(135deg, #1a1a2e 0%, #2d2d4a 100%)',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <FireOutlined style={{ fontSize: 24, color: '#ec4899' }} />
          <span style={{ fontSize: 20, fontWeight: 700, color: '#ffffff', letterSpacing: 2 }}>
            YL<span style={{ color: '#00d4ff' }}>Craft</span>
          </span>
          <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, marginLeft: 8 }}>
            AI 视频创作平台
          </span>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <a href="/docs" style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>文档</a>
          <a href="/api" style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>API</a>
        </div>
      </Header>

      <Layout>
        <Sider
          width={220}
          style={{
            background: '#1a1a2e',
            borderRight: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <Menu
            mode="inline"
            theme="dark"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{
              background: 'transparent',
              border: 'none',
              marginTop: 8,
            }}
          />
        </Sider>

        <Content style={{
          padding: 24,
          background: 'linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%)',
          minHeight: 'calc(100vh - 64px)',
          overflow: 'auto',
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
