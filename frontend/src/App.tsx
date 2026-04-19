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
    colorBgBase: '#0f0f1a',
    colorBgContainer: '#1a1a2e',
    colorText: '#e8e8f0',
    colorTextSecondary: '#8b8ba8',
    colorBorder: 'rgba(255,255,255,0.1)',
    borderRadius: 8,
    fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#1a1a2e',
      headerBg: '#1a1a2e',
      bodyBg: '#0f0f1a',
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(0,212,255,0.12)',
      darkItemHoverBg: 'rgba(255,255,255,0.06)',
      darkItemColor: '#8b8ba8',
      darkItemSelectedColor: '#00d4ff',
    },
    Card: {
      colorBgContainer: '#1a1a2e',
    },
    Input: {
      colorBgContainer: '#12122a',
      colorBorder: 'rgba(255,255,255,0.15)',
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
