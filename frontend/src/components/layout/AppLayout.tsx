import { Layout, Menu, Drawer, Button } from 'antd'
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
  FallOutlined,
} from '@ant-design/icons'

const { Sider, Content, Header } = Layout

// --- 公共模块（不折叠）---
const publicItems: MenuProps['items'] = [
  { key: '/', icon: <DashboardOutlined />, label: '概览' },
  { key: '/assets', icon: <FolderOpenOutlined />, label: '素材库' },
  { key: '/tasks', icon: <ThunderboltOutlined />, label: '任务管理' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

// --- 完整菜单（含 SubMenu 分组，可折叠）---
const menuItems: MenuProps['items'] = [
  ...publicItems,
  { type: 'divider' as const },
  // 爆款拆解（电商 / 摄影）
  {
    key: 'g-breaker',
    icon: <ExperimentOutlined />,
    label: '爆款拆解',
    children: [
      { key: '/breaker', label: '爆款拆解' },
      { key: '/crawler', label: '素材采集' },
      { key: '/download', label: '去水印下载' },
      { key: '/platforms', label: '平台管理' },
    ],
  },
  // 剪辑工具
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
  // Story Maker（短剧）
  {
    key: 'g-story',
    icon: <BookOutlined />,
    label: '短剧创作',
    children: [
      { key: '/story', label: '短剧创作' },
      { key: '/characters', label: '角色管理' },
    ],
  },
  // Live 2D 工厂（COSER）
  {
    key: 'g-live2d',
    icon: <AppstoreOutlined />,
    label: 'Live 2D 工厂',
    children: [
      { key: '/live2d', label: 'Live 2D 工厂' },
      { key: '/publish', label: '一键发布' },
    ],
  },
  { type: 'divider' as const },
  // AI 生成
  {
    key: 'g-ai',
    icon: <PictureOutlined />,
    label: 'AI 生成',
    children: [
      { key: '/image-gen', label: '图像生成' },
      { key: '/video-gen', label: '视频生成' },
      { key: '/comfyui', label: 'ComfyUI' },
      { key: '/agent', label: '智能体' },
    ],
  },
]

// Mobile breakpoint: < 768px
const MOBILE_BREAKPOINT = 768

// 从菜单 items 中递归查找匹配的路径 key
function findSelectedKey(
  items: MenuProps['items'],
  pathname: string
): string {
  if (!items) return '/'
  for (const item of items) {
    if (!item || !('key' in item)) continue
    const k = item.key as string
    // 子菜单（group key 以 g- 开头或无 icon 且有 children）
    if ('children' in item && item.children) {
      const found = findSelectedKey(item.children, pathname)
      if (found !== '/') return found
    } else if (k.startsWith('/')) {
      if (k === '/' ? pathname === '/' : pathname.startsWith(k)) {
        return k
      }
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

  return (
    <Layout style={{ minHeight: '100vh', background: THEME.bgPage }}>
      {/* Header */}
      <Header style={{
        background: THEME.bgCard,
        padding: isMobile ? '0 16px' : '0 24px',
        display: 'flex',
        alignItems: 'center',
        boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
        borderBottom: `1px solid ${THEME.border}`,
        position: 'sticky',
        top: 0,
        zIndex: 100,
        height: isMobile ? 52 : 64,
        lineHeight: `${isMobile ? 52 : 64}px`,
      }}>
        {isMobile && (
          <Button
            type="text"
            icon={<MenuOutlined style={{ color: THEME.textPrimary, fontSize: 18 }} />}
            onClick={() => setDrawerOpen(true)}
            style={{ marginRight: 12, flexShrink: 0 }}
          />
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <FireOutlined style={{ fontSize: isMobile ? 20 : 24, color: THEME.coser }} />
          <span style={{
            fontSize: isMobile ? 16 : 20,
            fontWeight: 700,
            color: THEME.textPrimary,
            letterSpacing: 2,
            whiteSpace: 'nowrap',
          }}>
            YL<span style={{ color: THEME.primary }}>Craft</span>
          </span>
          {!isMobile && (
            <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: 12, marginLeft: 8 }}>
              AI 视频创作平台
            </span>
          )}
        </div>
        {!isMobile && (
          <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 16 }}>
            <ThemeToggle />
            <a href="/docs" style={{ color: THEME.textSecondary, fontSize: 13 }}>文档</a>
            <a href="/api" style={{ color: THEME.textSecondary, fontSize: 13 }}>API</a>
          </div>
        )}
      </Header>

      {/* Desktop Sider */}
      {!isMobile && (
        <Layout>
          <Sider
            width={220}
            style={{
              background: THEME.bgCard,
              borderRight: `1px solid ${THEME.border}`,
              height: 'calc(100vh - 64px)',
              position: 'sticky',
              top: 64,
              overflow: 'auto',
            }}
          >
            <Menu
              mode="inline"
              theme={themeId === 'dawn' ? 'light' : 'dark'}
              selectedKeys={[selectedKey]}
              items={menuItems}
              onClick={handleMenuClick}
              style={{
                background: THEME.bgCard,
                border: 'none',
                marginTop: 8,
              }}
              className="app-sider-menu"
            />
          </Sider>

          <Content style={{
            padding: 24,
            background: THEME.bgPage,
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
          background: THEME.bgPage,
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