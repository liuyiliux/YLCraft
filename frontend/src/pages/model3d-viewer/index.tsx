import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Spin } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { getAsset } from '../../api'
import { Model3DViewer } from '../../components/asset-hub/Model3DViewer'

export default function Model3DViewerPage() {
  const { assetId } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!assetId) return
    setLoading(true)
    getAsset(assetId)
      .then((res: any) => {
        if (res?.success && res.data) setDetail(res.data)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [assetId])

  const modelFiles = Array.isArray(detail?.files) ? detail.files : []
  const objFile = modelFiles.find((f: any) => String(f.name || '').toLowerCase().endsWith('.obj'))
  const mtlFile = modelFiles.find((f: any) => String(f.name || '').toLowerCase().endsWith('.mtl'))
  const modelUrl = objFile ? objFile.url : `/api/v1/assets/${assetId}/download`
  const mtlUrl = mtlFile ? mtlFile.url : undefined

  return (
    <div style={{ position: 'relative', height: '100vh', width: '100vw', background: '#0b0b0d', overflow: 'hidden' }}>
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 140 }}>
          <Spin size="large" />
        </div>
      ) : detail ? (
        <Model3DViewer modelUrl={modelUrl} mtlUrl={mtlUrl} height="100vh" />
      ) : (
        <div style={{ padding: 48, color: '#8b8ba8' }}>资产不存在或已删除</div>
      )}

      <div style={{
        position: 'absolute',
        top: 16,
        left: 16,
        zIndex: 20,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(-1)}
          style={{ background: 'rgba(0,0,0,0.6)', color: '#e4e4e7', border: 'none' }}
        >
          返回
        </Button>
        <span style={{ color: '#e4e4e7', fontSize: 15, fontWeight: 600, textShadow: '0 1px 4px rgba(0,0,0,0.8)' }}>
          {detail?.title || '3D 模型预览'}
        </span>
      </div>
    </div>
  )
}
