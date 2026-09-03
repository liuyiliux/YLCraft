/**
 * 世界地图工作台 · 独立入口（与 /novel-world 平级）。
 * 从 URL 读取 project_id / snapshot_id，让 WorldMapEditor 直接定位。
 * 与 /novel-world 共享同一 WorldMapEditor 实现（结构化数据为正典，AI 成图仅派生）。
 */
import { useSearchParams } from 'react-router-dom'
import WorldMapEditor from '../novel-world/components/WorldMapEditor'

export default function WorldMapPage() {
  const [searchParams] = useSearchParams()
  const projectId = searchParams.get('project_id')
  const snapshotId = searchParams.get('snapshot_id')
  return (
    <div style={{ padding: 24 }}>
      <WorldMapEditor projectId={projectId} snapshotId={snapshotId} />
    </div>
  )
}