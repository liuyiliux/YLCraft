import { Layout, Menu, Drawer, Button } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useState, useEffect } from 'react'
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
  MenuOutlined,
} from '@ant-design/icons'

const { Sider, Content, Header } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '概览' },
  { type: 'divider' as const },
  { key: '/image-gen', icon: <PictureOutlined />, label: '图像生成' },
  { key: '/video-gen', icon: <VideoCameraOutlined />, label: '视频生成' },
  { type: 'divider' as const },
  { key: '/breaker', icon: <ExperimentOutlined />, label: '爆款拆解' },
  { key: '/clip-ops', icon: <ScissorOutlined />, label: '视频剪辑' },
  { key: '/clip', icon: <ScissorOutlined />, label: 'Clip Lab' },
  { key: '/story', icon: <BookOutlined />, label: '短剧创作' },
  { type: 'divider' as const },
  { key: '/download', icon: <CloudDownloadOutlined />, label: '去水印下载' },
  { key: '/assets', icon: <FolderOpenOutlined />, label: '素材库' },
  { key: '/characters', icon: <TeamOutlined />, label: '角色管理' },
  { type: 'divider' as const },
  { key: '/tasks', icon: <ThunderboltOutlined />, label: '任务管理' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

// Mobile breakpoint: < 768px
const MOBILE_BREAKPOINT = 768

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(window.innerWidth < MOBILE_BREAKPOINT)

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)
      if (!mobile) setDrawerOpen(false)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const selectedKey = menuItems
    .filter(item => item.key && item.key.startsWith('/'))
    .find(item =>
      location.pathname === item.key ||
      (item.key !== '/' && location.pathname.startsWith(item.key))
    )?.key || '/'

  const handleMenuClick = (key: string) => {
    navigate(key)
    setDrawerOpen(false)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* Header */}
      <Header style={{
        background: 'linear-gradient(135deg, #1a1a2e 0%, #2d2d4a 100%)',
        padding: isMobile ? '0 16px' : '0 24px',
        display: 'flex',
        alignItems: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        position: 'sticky',
        top: 0,
        zIndex: 100,
        height: isMobile ? 52 : 64,
        lineHeight: `${isMobile ? 52 : 64}px`,
      }}>
        {isMobile && (
          <Button
            type="text"
            icon={<MenuOutlined style={{ color: '#fff', fontSize: 18 }} />}
            onClick={() => setDrawerOpen(true)}
            style={{ marginRight: 12, flexShrink: 0 }}
          />
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <FireOutlined style={{ fontSize: isMobile ? 20 : 24, color: '#ec4899' }} />
          <span style={{
            fontSize: isMobile ? 16 : 20,
            fontWeight: 700,
            color: '#ffffff',
            letterSpacing: 2,
            whiteSpace: 'nowrap',
          }}>
            YL<span style={{ color: '#00d4ff' }}>Craft</span>
          </span>
          {!isMobile && (
            <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, marginLeft: 8 }}>
              AI 视频创作平台
            </span>
          )}
        </div>
        {!isMobile && (
          <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 16 }}>
            <a href="/docs" style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>文档</a>
            <a href="/api" style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>API</a>
          </div>
        )}
      </Header>

      {/* Desktop Sider */}
      {!isMobile && (
        <Layout>
          <Sider
            width={220}
            style={{
              background: '#1a1a2e',
              borderRight: '1px solid rgba(255,255,255,0.06)',
              height: 'calc(100vh - 64px)',
              position: 'sticky',
              top: 64,
              overflow: 'auto',
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
            padding: isMobile ? 12 : 24,
            background: 'linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%)',
            minHeight: 'calc(100vh - 64px)',
            overflow: 'auto',
          }}>
            <Outlet />
          </Content>
        </Layout>
      )}

      {/* Mobile Content */}
      {isMobile && (
        <Content style={{
          padding: 12,
          background: 'linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%)',
          minHeight: 'calc(100vh - 52px)',
          overflow: 'auto',
        }}>
          <Outlet />
        </Content>
      )}

      {/* Mobile Drawer Menu */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <FireOutlined style={{ fontSize: 20, color: '#ec4899' }} />
            <span style={{ fontSize: 18, fontWeight: 700, color: '#fff', letterSpacing: 2 }}>
              YL<span style={{ color: '#00d4ff' }}>Craft</span>
            </span>
          </div>
        }
        placement="left"
        onClose={() => setDrawerOpen(false)}
        open={drawerOpen}
        width={260}
        styles={{
          body: { padding: 0, background: '#1a1a2e' },
          header: {
            background: 'linear-gradient(135deg, #1a1a2e 0%, #2d2d4a 100%)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          },
        }}
      >
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => handleMenuClick(key)}
          style={{
            background: 'transparent',
            border: 'none',
            marginTop: 8,
          }}
        />
      </Drawer>
    </Layout>
  )
}
