import { Layout, Menu, Drawer, Button, Space } from 'antd'
import type { MenuProps } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useTheme } from '../../constants/theme'
import ThemeToggle from '../ThemeToggle'
import {
  DashboardOutlined,
  ScissorOutlined,
  BookOutlined,
  ThunderboltOutlined,
  SettingOutlined,
  CloudDownloadOutlined,
  FolderOpenOutlined,
  PictureOutlined,
  EditOutlined,
  VideoCameraOutlined,
  FireOutlined,
  MenuOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  CustomerServiceOutlined,
  RobotOutlined,
  ExperimentOutlined,
  SearchOutlined,
  LinkOutlined,
  SendOutlined,
  TeamOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ReadOutlined,
} from '@ant-design/icons'

const { Sider, Content, Header } = Layout

const MAIN_NAV: MenuProps['items'] = [
  { key: '/', icon: <DashboardOutlined />, label: '概览' },
  { key: '/assets', icon: <FolderOpenOutlined />, label: '素材库' },
  { key: '/tasks', icon: <ThunderboltOutlined />, label: '任务管理' },
]

const BOTTOM_NAV: MenuProps['items'] = [
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

const menuItems: MenuProps['items'] = [
  ...MAIN_NAV,
  { type: 'divider' as const },
  {
    key: 'g-creation',
    icon: <PictureOutlined />,
    label: 'AI 创作',
    children: [
      { key: '/image-gen', label: '图像生成' },
      { key: '/video-gen', label: '视频生成' },
      { key: '/comfyui', label: 'ComfyUI' },
      { key: '/agent', label: '智能体' },
      { key: '/image-editor', label: '图片编辑' },
    ],
  },
  {
    key: 'g-breaker',
    icon: <ExperimentOutlined />,
    label: '爆款拆解',
    children: [
      { key: '/breaker', label: '爆款拆解' },
      { key: '/crawler', label: '素材采集' },
      { key: '/download', label: '去水印下载' },
      { key: '/platforms', label: '平台管理' },
      { key: '/publish', label: '一键发布' },
    ],
  },
  {
    key: 'g-clip',
    icon: <ScissorOutlined />,
    label: '剪辑工具',
    children: [
      { key: '/clip-ops', label: '视频剪辑' },
      { key: '/clip', label: 'AI 剪辑' },
      { key: '/subtitle', label: '字幕提取' },
      { key: '/bgm', label: 'BGM 配乐' },
    ],
  },
  {
    key: 'g-story',
    icon: <BookOutlined />,
    label: '短剧创作',
    children: [
      { key: '/story', label: '短剧创作' },
      { key: '/characters', label: '角色管理' },
    ],
  },
  {
    key: 'g-novel',
    icon: <ReadOutlined />,
    label: '小说阅读',
    children: [
      { key: '/novel-search', label: '搜索下载' },
      { key: '/novel-bookshelf', label: '我的书架' },
      { key: '/book-source', label: '书源管理' },
    ],
  },
  {
    key: 'g-live2d',
    icon: <AppstoreOutlined />,
    label: 'Live2D 工厂',
    children: [
      { key: '/live2d', label: 'Live2D 工厂' },
    ],
  },
]

const MOBILE_BREAKPOINT = 768

function findSelectedKey(items: MenuProps['items'], pathname: string): string {
  if (!items) return '/'
  for (const item of items) {
    if (!item || !('key' in item)) continue
    const k = item.key as string
    if ('children' in item && item.children) {
      const found = findSelectedKey(item.children, pathname)
      if (found !== '/') return found
    } else if (k.startsWith('/')) {
      if (k === '/' ? pathname === '/' : pathname.startsWith(k)) return k
    }
  }
  return '/'
}

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { theme: THEME, themeId } = useTheme()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(window.innerWidth < MOBILE_BREAKPOINT)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)
      if (!mobile) setDrawerOpen(false)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const selectedKey = findSelectedKey(menuItems, location.pathname)

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key.startsWith('/')) {
      navigate(key)
      setDrawerOpen(false)
    }
  }

  const siderWidth = collapsed ? 60 : 220

  return (
    <Layout style={{ minHeight: '100vh', background: THEME.bgPage }}>
      {/* ========== Desktop Sidebar ========== */}
      {!isMobile && (
        <Sider
          width={siderWidth}
          collapsedWidth={60}
          collapsible
          collapsed={collapsed}
          trigger={null}
          theme={themeId === 'dawn' ? 'light' : 'dark'}
          style={{
            position: 'fixed',
            left: 0,
            top: 0,
            height: '100vh',
            background: THEME.bgCard,
            borderRight: `1px solid ${THEME.border}`,
            zIndex: 100,
            overflow: 'hidden',
            transition: 'width 0.2s',
          }}
        >
          {/* Logo */}
          <div
            onClick={() => navigate('/')}
            style={{
              height: 64,
              display: 'flex',
              alignItems: 'center',
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? 0 : '0 16px',
              gap: 8,
              borderBottom: `1px solid ${THEME.border}`,
              cursor: 'pointer',
            }}
          >
            <FireOutlined style={{ fontSize: 22, color: THEME.coser, flexShrink: 0 }} />
            {!collapsed && (
              <span style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary, letterSpacing: 1 }}>
                YL<span style={{ color: THEME.primary }}>Craft</span>
              </span>
            )}
          </div>

          {/* Main menu — scrollable */}
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
            <Menu
              mode="inline"
              theme={themeId === 'dawn' ? 'light' : 'dark'}
              selectedKeys={[selectedKey]}
              items={menuItems}
              onClick={handleMenuClick}
              inlineCollapsed={collapsed}
              style={{ background: 'transparent', border: 'none' }}
            />
          </div>

          {/* Bottom menu */}
          <div style={{ borderTop: `1px solid ${THEME.border}`, flexShrink: 0 }}>
            <Menu
              mode="inline"
              theme={themeId === 'dawn' ? 'light' : 'dark'}
              selectedKeys={[selectedKey]}
              items={BOTTOM_NAV}
              onClick={handleMenuClick}
              inlineCollapsed={collapsed}
              style={{ background: 'transparent', border: 'none' }}
            />
            {/* Fold button */}
            <div
              onClick={() => setCollapsed(!collapsed)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: collapsed ? 'center' : 'flex-end',
                padding: collapsed ? '10px 0' : '10px 16px',
                cursor: 'pointer',
                color: THEME.textSecondary,
                borderTop: `1px solid ${THEME.border}`,
              }}
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </div>
          </div>
        </Sider>
      )}

      {/* ========== Main Content Area ========== */}
      <Layout style={{ marginLeft: isMobile ? 0 : siderWidth, transition: 'margin-left 0.2s', minHeight: '100vh' }}>
        {/* Header — minimalist */}
        {!isMobile && (
          <Header
            style={{
              background: THEME.bgCard,
              borderBottom: `1px solid ${THEME.border}`,
              height: 56,
              lineHeight: '56px',
              padding: '0 24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 12,
              position: 'sticky',
              top: 0,
              zIndex: 50,
            }}
          >
            <ThemeToggle />
            <a href="/docs" style={{ color: THEME.textSecondary, fontSize: 13 }}>文档</a>
            <a href="/api" style={{ color: THEME.textSecondary, fontSize: 13 }}>API</a>
          </Header>
        )}

        {/* Mobile Header */}
        {isMobile && (
          <Header
            style={{
              background: THEME.bgCard,
              borderBottom: `1px solid ${THEME.border}`,
              height: 52,
              lineHeight: '52px',
              padding: '0 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              position: 'sticky',
              top: 0,
              zIndex: 50,
            }}
          >
            <Button
              type="text"
              icon={<MenuOutlined style={{ color: THEME.textPrimary, fontSize: 18 }} />}
              onClick={() => setDrawerOpen(true)}
              style={{ flexShrink: 0 }}
            />
            <FireOutlined style={{ fontSize: 18, color: THEME.coser }} />
            <span style={{ fontSize: 16, fontWeight: 700, color: THEME.textPrimary }}>
              YL<span style={{ color: THEME.primary }}>Craft</span>
            </span>
          </Header>
        )}

        {/* Page Content */}
        <Content
          style={{
            padding: isMobile ? 12 : 24,
            background: THEME.bgPage,
            minHeight: isMobile ? 'calc(100vh - 52px)' : 'calc(100vh - 56px)',
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>

      {/* ========== Mobile Drawer Menu ========== */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <FireOutlined style={{ fontSize: 20, color: THEME.coser }} />
            <span style={{ fontSize: 18, fontWeight: 700, color: THEME.textPrimary, letterSpacing: 2 }}>
              YL<span style={{ color: THEME.primary }}>Craft</span>
            </span>
          </div>
        }
        placement="left"
        onClose={() => setDrawerOpen(false)}
        open={drawerOpen}
        width={260}
        styles={{
          body: { padding: 0, background: THEME.bgCard },
          header: {
            background: THEME.bgCard,
            borderBottom: `1px solid ${THEME.border}`,
          },
        }}
      >
        <Menu
          mode="inline"
          theme={themeId === 'dawn' ? 'light' : 'dark'}
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ background: 'transparent', border: 'none', marginTop: 8 }}
        />
      </Drawer>
    </Layout>
  )
}
