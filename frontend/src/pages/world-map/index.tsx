/**
 * 世界地图工作台 · 独立入口（与 /novel-world 平级）。
 * 从 URL 读取 project_id / snapshot_id，让 WorldMapEditor 直接定位。
 * 与 /novel-world 共享同一 WorldMapEditor 实现（结构化数据为正典，AI 成图仅派生）。
 *
 * 页面层负责两件与主题/作用域有关的全局事项：
 * 1) 挂载 .worldmap-scope（样式令牌作用域，见 docs/design/world-map-workbench-style.md §3）；
 * 2) 用 ConfigProvider 把 antd 的主色/语义色/圆角对齐同一套令牌，避免组件各自写死 hex。
 */
import { useEffect, useState } from 'react'
import { ConfigProvider, theme as antdTheme } from 'antd'
import { useSearchParams } from 'react-router-dom'
import WorldMapEditor from '../novel-world/components/WorldMapEditor'
import '../../components/world/worldmap.css'

const THEME_KEY = 'worldmap-theme'

/** 工作台类页面默认提供深浅主题，偏好记忆到 localStorage。 */
function useWorkbenchTheme(): [string, (next: string) => void] {
  const [theme, setTheme] = useState<string>(() => localStorage.getItem(THEME_KEY) || 'light')
  useEffect(() => {
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])
  return [theme, setTheme]
}

export default function WorldMapPage() {
  const [searchParams] = useSearchParams()
  const projectId = searchParams.get('project_id')
  const snapshotId = searchParams.get('snapshot_id')
  const [theme, setTheme] = useWorkbenchTheme()
  const dark = theme === 'dark'

  return (
    <ConfigProvider
      theme={{
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: dark ? '#3c8cff' : '#1677ff',
          colorError: dark ? '#ff7a7c' : '#ff4d4f',
          colorSuccess: dark ? '#6bd04d' : '#52c41a',
          colorWarning: dark ? '#ffa940' : '#fa8c16',
          borderRadius: 6,
          fontSize: 13,
          controlHeight: 32,
        },
      }}
    >
      <div className="worldmap-scope" data-theme={theme} style={{ padding: 24, minHeight: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <button
            type="button"
            onClick={() => setTheme(dark ? 'light' : 'dark')}
            title={dark ? '切换到浅色' : '切换到深色'}
            style={{
              height: 28,
              padding: '0 10px',
              fontSize: 12,
              cursor: 'pointer',
              color: 'var(--p-fg)',
              background: 'var(--p-surface)',
              border: '1px solid var(--p-border)',
              borderRadius: 6,
            }}
          >
            {dark ? '浅色' : '深色'}
          </button>
        </div>
        <WorldMapEditor projectId={projectId} snapshotId={snapshotId} />
      </div>
    </ConfigProvider>
  )
}
