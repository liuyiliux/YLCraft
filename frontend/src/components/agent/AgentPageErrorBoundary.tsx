import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react'
import { Button, Result } from 'antd'

interface AgentPageErrorBoundaryProps {
  children: ReactNode
}

interface AgentPageErrorBoundaryState {
  error: Error | null
  retryKey: number
}

export default class AgentPageErrorBoundary extends Component<
  AgentPageErrorBoundaryProps,
  AgentPageErrorBoundaryState
> {
  state: AgentPageErrorBoundaryState = {
    error: null,
    retryKey: 0,
  }

  static getDerivedStateFromError(error: Error): Partial<AgentPageErrorBoundaryState> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Agent workspace render failed', error, info)
  }

  private retry = () => {
    this.setState(state => ({ error: null, retryKey: state.retryKey + 1 }))
  }

  render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title="智能体工作台暂时无法显示"
          subTitle="对话数据仍保存在后端。你可以重新加载工作台，或刷新页面后继续当前对话。"
          extra={[
            <Button type="primary" key="retry" onClick={this.retry}>
              重新加载工作台
            </Button>,
            <Button key="refresh" onClick={() => window.location.reload()}>
              刷新页面
            </Button>,
          ]}
        />
      )
    }

    return <Fragment key={this.state.retryKey}>{this.props.children}</Fragment>
  }
}
