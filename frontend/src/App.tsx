import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { ThemeProvider, useTheme } from './constants/theme'
import AppLayout from './components/layout/AppLayout'
import DashboardPage from './pages/dashboard'
import DownloadPage from './pages/download'
import BreakerPage from './pages/breaker'
import ClipLabPage from './pages/clip'
import StoryPage from './pages/story'
import TasksPage from './pages/tasks'
import SettingsPage from './pages/settings'
import AssetsPage from './pages/assets'
import AssetHubPage from './pages/asset-hub'
import CharactersPage from './pages/characters'
import ImageGenPage from './pages/image-gen'
import VideoGenPage from './pages/video-gen'
import ClipOpsPage from './pages/clip-ops'
import Live2DPage from './pages/live2d'
import SubtitlePage from './pages/subtitle'
import BGMPage from './pages/bgm'
import AgentPage from './pages/agent'
import AccountsPage from './pages/accounts'
import PublishPage from './pages/publish'
import CrawlerPage from './pages/crawler'
import UpAnalyticsPage from './pages/up-analytics'
import MyDataPage from './pages/my-data'
import ComfyUIPage from './pages/comfyui'
import ImageEditorPage from './pages/image-editor'
import NovelSearchPage from './pages/novel-search'
import NovelBookshelfPage from './pages/novel-bookshelf'
import NovelReaderPage from './pages/novel-reader'
import BookSourcePage from './pages/book-source'

/** 包裹层：读取当前主题并传给 Ant Design ConfigProvider */
function AntdThemeWrapper({ children }: { children: React.ReactNode }) {
  const { themeDef } = useTheme()

  return (
    <ConfigProvider
      theme={{
        token: themeDef.antdToken,
        components: themeDef.antdComponents,
      }}
      locale={zhCN}
    >
      <AntApp>{children}</AntApp>
    </ConfigProvider>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AntdThemeWrapper>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="download" element={<DownloadPage />} />
              <Route path="assets" element={<AssetsPage />} />
              <Route path="asset-hub" element={<AssetHubPage />} />
              <Route path="characters" element={<CharactersPage />} />
              <Route path="breaker" element={<BreakerPage />} />
              <Route path="clip" element={<ClipLabPage />} />
              <Route path="story" element={<StoryPage />} />
              <Route path="image-gen" element={<ImageGenPage />} />
              <Route path="video-gen" element={<VideoGenPage />} />
              <Route path="comfyui" element={<ComfyUIPage />} />
              <Route path="clip-ops" element={<ClipOpsPage />} />
              <Route path="live2d" element={<Live2DPage />} />
              <Route path="subtitle" element={<SubtitlePage />} />
              <Route path="bgm" element={<BGMPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="agent" element={<AgentPage />} />
              <Route path="accounts" element={<AccountsPage />} />
              <Route path="publish" element={<PublishPage />} />
              <Route path="crawler" element={<CrawlerPage />} />
              <Route path="up-analytics" element={<UpAnalyticsPage />} />
              <Route path="my-data" element={<MyDataPage />} />
              <Route path="image-editor" element={<ImageEditorPage />} />
              <Route path="novel-search" element={<NovelSearchPage />} />
              <Route path="novel-bookshelf" element={<NovelBookshelfPage />} />
              <Route path="novel-reader/:id" element={<NovelReaderPage />} />
              <Route path="book-source" element={<BookSourcePage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AntdThemeWrapper>
    </ThemeProvider>
  )
}
