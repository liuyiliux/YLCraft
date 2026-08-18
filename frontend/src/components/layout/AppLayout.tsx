import { Layout, Menu, Drawer, Button, Tag } from 'antd'
import type { MenuProps } from 'antd'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useTheme } from '../../constants/theme'
import ThemeToggle from '../ThemeToggle'
import {
  DashboardOutlined,
  BookOutlined,
  SettingOutlined,
  FolderOpenOutlined,
  PictureOutlined,
  UnorderedListOutlined,
  DatabaseOutlined,
  BranchesOutlined,
  EditOutlined,
  FireOutlined,
  MenuOutlined,
  SearchOutlined,
  SendOutlined,
  ReadOutlined,
  KeyOutlined,
} from '@ant-design/icons'

const { Content, Header } = Layout

function navLabel(text: string, status?: '实验' | '辅助') {
  if (!status) return text
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <span>{text}</span>
      <Tag
        color={status === '实验' ? 'orange' : 'default'}
        style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '18px' }}
      >
        {status}
      </Tag>
    </span>
  )
}

const MAIN_NAV: MenuProps['items'] = [
  { key: '/story', icon: <BookOutlined />, label: '创作项目' },
  { key: '/canvas', icon: <BranchesOutlined />, label: '创作画布' },
  { key: '/assets', icon: <FolderOpenOutlined />, label: '素材库' },
  { key: '/download', icon: <SearchOutlined />, label: '下载' },
  { key: '/novel-bookshelf', icon: <ReadOutlined />, label: '小说' },
  { key: '/image-gen', icon: <PictureOutlined />, label: 'AI 图片' },
  { key: '/tasks', icon: <UnorderedListOutlined />, label: '任务中心' },
]

const BOTTOM_NAV: MenuProps['items'] = [
  { key: '/accounts', icon: <KeyOutlined />, label: '账号中心' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

const menuItems: MenuProps['items'] = [
  { key: '/', icon: <DashboardOutlined />, label: navLabel('概览', '辅助') },
  ...MAIN_NAV,
  { type: 'divider' as const },
  {
    key: 'g-acquisition',
    icon: <SearchOutlined />,
    label: '内容采集',
    children: [
      { key: '/crawler', label: navLabel('内容搜索', '实验') },
      { key: '/breaker', label: navLabel('爆款拆解', '实验') },
      { key: '/up-analytics', label: navLabel('UP主分析', '实验') },
      { key: '/my-data', label: navLabel('我的数据', '实验') },
      { key: '/inspiration', label: navLabel('灵感广场', '实验') },
    ],
  },
  {
    key: 'g-creation',
    icon: <PictureOutlined />,
    label: 'AI 创作',
    children: [
      { key: '/multi-platform-gen', label: navLabel('多平台生图', '实验') },
      { key: '/video-gen', label: navLabel('视频生成', '实验') },
      { key: '/model-3d', label: navLabel('图生 3D', '实验') },
      { key: '/prompt-library', icon: <DatabaseOutlined />, label: 'Prompt 参考库' },
      { key: '/platform-templates', label: navLabel('平台模板', '辅助') },
      { key: '/comfyui', label: navLabel('ComfyUI', '实验') },
      { key: '/agent', label: navLabel('智能体', '实验') },
    ],
  },
  {
    key: 'g-editing',
    icon: <EditOutlined />,
    label: '编辑制作',
    children: [
      { key: '/image-editor', label: navLabel('图片编辑', '实验') },
      { key: '/clip-ops', label: navLabel('视频剪辑', '实验') },
      { key: '/clip', label: navLabel('AI 剪辑', '实验') },
      { key: '/subtitle', label: navLabel('字幕提取', '实验') },
      { key: '/bgm', label: navLabel('BGM 配乐', '实验') },
      { key: '/live2d', label: navLabel('Live2D 工厂', '实验') },
    ],
  },
  {
    key: 'g-story',
    icon: <BookOutlined />,
    label: '创作项目',
    children: [
      { key: '/characters', label: '角色管理' },
    ],
  },
  {
    key: 'g-reader',
    icon: <ReadOutlined />,
    label: '阅读中心',
    children: [
      { key: '/reader', label: navLabel('本地阅读', '辅助') },
      { key: '/novel-search', label: '小说搜索' },
      { key: '/book-source', label: navLabel('书源管理', '辅助') },
    ],
  },
  {
    key: 'g-publishing',
    icon: <SendOutlined />,
    label: '发布运营',
    children: [
      { key: '/publish', label: navLabel('一键发布', '实验') },
    ],
  },
  { type: 'divider' as const },
  ...BOTTOM_NAV,
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
      {/* ========== Desktop Top Navigation ========== */}
      {!isMobile && (
        <Header
          style={{
            background: THEME.bgCard,
            borderBottom: `1px solid ${THEME.border}`,
            height: 52,
            lineHeight: '52px',
            padding: '0 16px',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            position: 'sticky',
            top: 0,
            zIndex: 100,
          }}
        >
          {/* Logo */}
          <div
            onClick={() => navigate('/')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexShrink: 0,
              cursor: 'pointer',
              paddingRight: 8,
            }}
          >
            <FireOutlined style={{ fontSize: 20, color: THEME.coser }} />
            <span style={{ fontSize: 15, fontWeight: 700, color: THEME.textPrimary, letterSpacing: 1 }}>
              YL<span style={{ color: THEME.primary }}>Craft</span>
            </span>
          </div>

          {/* Horizontal main menu — overflow folds into ellipsis automatically */}
          <Menu
            mode="horizontal"
            theme={themeId === 'dawn' ? 'light' : 'dark'}
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={handleMenuClick}
            style={{ flex: 1, minWidth: 0, border: 'none', background: 'transparent', lineHeight: '50px' }}
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
            <ThemeToggle />
            <a href="/docs" style={{ color: THEME.textSecondary, fontSize: 13 }}>文档</a>
            <a href="/api" style={{ color: THEME.textSecondary, fontSize: 13 }}>API</a>
          </div>
        </Header>
      )}

      {/* ========== Main Content Area ========== */}
      <Layout style={{ minHeight: '100vh' }}>
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
            padding: isMobile ? 12 : 16,
            background: THEME.bgPage,
            minHeight: isMobile ? 'calc(100vh - 52px)' : 'calc(100vh - 52px)',
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
