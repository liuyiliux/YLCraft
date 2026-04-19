import { Layout, Menu } from 'antd'
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
} from '@ant-design/icons'

const { Sider, Content, Header } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '概览' },
  { key: '/download', icon: <CloudDownloadOutlined />, label: '去水印下载' },
  { key: '/assets', icon: <FolderOpenOutlined />, label: '素材库' },
  { key: '/characters', icon: <TeamOutlined />, label: '角色管理' },
  { key: '/breaker', icon: <ExperimentOutlined />, label: '爆款拆解' },
  { key: '/clip', icon: <ScissorOutlined />, label: '视频剪辑' },
  { key: '/story', icon: <BookOutlined />, label: '短剧创作' },
  { key: '/tasks', icon: <ThunderboltOutlined />, label: '任务管理' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = menuItems.find(item =>
    location.pathname === item.key ||
    (item.key !== '/' && location.pathname.startsWith(item.key))
  )?.key || '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: '#fff', letterSpacing: 2 }}>
            YL<span style={{ color: '#00d4ff' }}>Craft</span>
          </span>
          <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>
            AI 视频创作平台
          </span>
        </div>
      </Header>

      <Layout>
        <Sider
          width={200}
          style={{
            background: '#1a1a2e',
            borderRight: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{
              background: 'transparent',
              border: 'none',
              marginTop: 8,
            }}
            theme="dark"
          />
        </Sider>

        <Content style={{ padding: 24, background: '#0f0f1a', minHeight: 'calc(100vh - 64px)' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
