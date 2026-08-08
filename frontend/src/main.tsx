import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[YLCraft] Unhandled render error', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <main style={{ minHeight: '100vh', padding: 32, background: '#09090b', color: '#f4f4f5' }}>
          <h1 style={{ margin: 0, fontSize: 20 }}>页面加载失败</h1>
          <p style={{ color: '#a1a1aa' }}>请刷新页面重试。错误已记录到浏览器控制台。</p>
          <pre style={{ whiteSpace: 'pre-wrap', color: '#fca5a5' }}>{this.state.error.message}</pre>
        </main>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </React.StrictMode>,
)
