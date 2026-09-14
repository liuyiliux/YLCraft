/**
 * 内容包平台输出列表（适配器产物的展示与导出）。
 *
 * 提取自内容包工作台的内联区块。它描述的是**适配器输出**这一通用契约
 * （`adapter_type` / `label` / `status` / `payload` / `source_*` / `error` / `warnings`），
 * 与具体是绘本还是科普卡无关，因此放在 `components/content-package` 供其它入口复用
 * （`/multi-platform-gen` 等）。
 *
 * 保留原有语义：
 *   - 状态三态映射：`ready`→已生成（绿）、`stale`→已过期（橙）、其余→失败（红）。
 *     刻意不把未知状态当成功——适配器失败时 `status='failed'`，而"未产出"根本不会出现在列表里。
 *   - 摘要按 payload 形态取其一（卡片数 / 镜头数 / 页数 / 文件数），没有已知形态就不显示。
 *   - **过期信息展示的是 `status` + `stale_reason` 之外的用户可见线索**：这里只读状态，
 *     不改状态——过期判定属服务端职责（见 `mark_outputs_stale`）。
 */
import { Button, Space, Tag, Typography } from 'antd'
import { useTheme } from '../../constants/theme'
import { downloadTextFile } from '../../utils/download'

const { Text } = Typography

export interface PackageOutputListProps {
  outputs: any[]
  /** 仅供导出文件名使用；缺失时退化为 'content-package' */
  packageType?: string
}

export default function PackageOutputList({ outputs, packageType }: PackageOutputListProps) {
  const { theme } = useTheme()

  if (!outputs.length) {
    return <Text type="secondary" style={{ fontSize: 12 }}>还没有平台输出，点上面的按钮生成。</Text>
  }

  return (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      {outputs.map((output: any) => {
        const status = String(output?.status || '')
        const statusLabel = status === 'ready' ? '已生成' : status === 'stale' ? '已过期' : '失败'
        const statusColor = status === 'ready' ? 'green' : status === 'stale' ? 'orange' : 'red'
        const payload = output?.payload || {}
        const summary = payload.cards?.length ? `${payload.cards.length} 张卡片`
          : payload.shots?.length ? `${payload.shots.length} 个镜头`
            : payload.pages?.length ? `${payload.pages.length} 页`
              : payload.files?.length ? `${payload.files.length} 个文件`
                : ''
        return (
          <div
            key={String(output?.adapter_type)}
            style={{ border: `1px solid ${theme.borderLight}`, borderRadius: 6, padding: '8px 10px' }}
          >
            <Space wrap size={6}>
              <Text strong style={{ fontSize: 13 }}>{output?.label || output?.adapter_type}</Text>
              <Tag color={statusColor}>{statusLabel}</Tag>
              {summary ? <Text type="secondary" style={{ fontSize: 12 }}>{summary}</Text> : null}
              <Button
                size="small"
                type="link"
                onClick={() =>
                  downloadTextFile(
                    `${packageType || 'content-package'}-${output?.adapter_type}.json`,
                    JSON.stringify(payload, null, 2),
                  )}
              >
                导出 JSON
              </Button>
              {/* 素材包是"带走的"产物：每个文件单独可下载 */}
              {Array.isArray(payload.files)
                ? payload.files.map((file: any) => (
                  <Button
                    key={String(file?.path)}
                    size="small"
                    type="link"
                    onClick={() => downloadTextFile(String(file?.path || 'file.txt'), String(file?.content || ''))}
                  >
                    {file?.path}
                  </Button>
                ))
                : null}
            </Space>
            {output?.error ? (
              <Text type="danger" style={{ fontSize: 12, display: 'block' }}>{output.error}</Text>
            ) : null}
            {(output?.warnings || []).map((warning: string) => (
              <Text key={warning} type="secondary" style={{ fontSize: 12, display: 'block' }}>{warning}</Text>
            ))}
          </div>
        )
      })}
    </Space>
  )
}
