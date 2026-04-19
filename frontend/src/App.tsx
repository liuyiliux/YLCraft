import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/layout/AppLayout'
import DashboardPage from './pages/dashboard'
import DownloadPage from './pages/download'
import BreakerPage from './pages/breaker'
import ClipLabPage from './pages/clip'
import StoryPage from './pages/story'
import TasksPage from './pages/tasks'
import SettingsPage from './pages/settings'
import AssetsPage from './pages/assets'
import CharactersPage from './pages/characters'

const theme = {
  token: {
    colorPrimary: '#00d4ff',
    colorBgBase: '#f0f2f5',
    colorBgContainer: '#ffffff',
    colorText: '#1a1a2e',
    colorTextSecondary: '#8b8ba8',
    colorBorder: 'rgba(0,0,0,0.1)',
    borderRadius: 8,
    fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      headerBg: '#ffffff',
      bodyBg: '#f0f2f5',
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(0,212,255,0.12)',
      darkItemHoverBg: 'rgba(0,0,0,0.04)',
      darkItemColor: '#666',
      darkItemSelectedColor: '#00d4ff',
      itemBg: 'transparent',
      itemSelectedBg: 'rgba(0,212,255,0.12)',
      itemHoverBg: 'rgba(0,0,0,0.04)',
      itemColor: '#666',
      itemSelectedColor: '#00d4ff',
    },
    Card: {
      colorBgContainer: '#ffffff',
    },
    Input: {
      colorBgContainer: '#ffffff',
      colorBorder: 'rgba(0,0,0,0.15)',
    },
    Button: {
      colorPrimary: '#00d4ff',
      colorPrimaryHover: '#00bce6',
    },
  },
}

export default function App() {
  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="download" element={<DownloadPage />} />
              <Route path="assets" element={<AssetsPage />} />
              <Route path="characters" element={<CharactersPage />} />
              <Route path="breaker" element={<BreakerPage />} />
              <Route path="clip" element={<ClipLabPage />} />
              <Route path="story" element={<StoryPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}
