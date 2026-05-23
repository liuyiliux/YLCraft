/**
 * YLCraft — 资产版本管理组件
 * 
 * 支持：
 * - 版本列表展示
 * - 版本对比
 * - 版本回滚
 * - 版本标签管理
 */

import { useState, useCallback, useEffect } from 'react'
import { Card, Button, Tag, Tooltip, Dropdown, Menu, Badge } from 'antd'
import { 
  BranchesOutlined, 
  CheckOutlined, 
  ClockCircleOutlined,
  LeftOutlined,
  EyeOutlined,
  DownloadOutlined,
  TagsOutlined,
  MoreOutlined,
  RightOutlined,
} from '@ant-design/icons'

interface AssetVersion {
  id: string
  version_number: string
  created_at: string
  description: string
  is_current: boolean
  tags: string[]
  thumbnail_url?: string
}

interface AssetVersionManagerProps {
  assetId?: string
}

export function AssetVersionManager({ assetId }: AssetVersionManagerProps) {
  const [versions, setVersions] = useState<AssetVersion[]>([])
  const [selectedVersions, setSelectedVersions] = useState<string[]>([])
  const [compareMode, setCompareMode] = useState(false)

  // 模拟版本数据
  useEffect(() => {
    if (!assetId) return

    const mockVersions: AssetVersion[] = [
      {
        id: 'v1',
        version_number: 'v1.0.0',
        created_at: '2024-01-15 14:30:00',
        description: '初始版本',
        is_current: false,
        tags: ['production'],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text_to_image?prompt=cyberpunk%20city%20night%20scene&image_size=square',
      },
      {
        id: 'v2',
        version_number: 'v1.1.0',
        created_at: '2024-01-16 09:15:00',
        description: '优化了光照效果',
        is_current: false,
        tags: ['staging'],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text_to_image?prompt=cyberpunk%20city%20with%20neon%20lights&image_size=square',
      },
      {
        id: 'v3',
        version_number: 'v1.2.0',
        created_at: '2024-01-17 16:45:00',
        description: '添加了动态云层',
        is_current: true,
        tags: ['latest', 'production'],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text_to_image?prompt=cyberpunk%20city%20with%20clouds%20and%20neon&image_size=square',
      },
      {
        id: 'v4',
        version_number: 'v1.2.1',
        created_at: '2024-01-18 11:20:00',
        description: '修复了建筑细节',
        is_current: false,
        tags: [],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text_to_image?prompt=cyberpunk%20city%20detailed%20buildings&image_size=square',
      },
    ]

    setVersions(mockVersions)
  }, [assetId])

  const handleSelectVersion = useCallback((versionId: string) => {
    if (compareMode) {
      setSelectedVersions(prev => {
        if (prev.includes(versionId)) {
          if (prev.length <= 1) {
            return prev.filter(id => id !== versionId)
          }
          return prev.filter(id => id !== versionId)
        } else if (prev.length < 2) {
          return [...prev, versionId]
        }
        return prev
      })
    }
  }, [compareMode])

  const handleToggleCompareMode = useCallback(() => {
    setCompareMode(prev => !prev)
    if (compareMode) {
      setSelectedVersions([])
    }
  }, [compareMode])

  const handleRollback = useCallback((versionId: string) => {
    setVersions(prev =>
      prev.map(v => ({
        ...v,
        is_current: v.id === versionId,
      }))
    )
  }, [])

  const handleAddTag = useCallback((versionId: string, tag: string) => {
    setVersions(prev =>
      prev.map(v =>
        v.id === versionId && !v.tags.includes(tag)
          ? { ...v, tags: [...v.tags, tag] }
          : v
      )
    )
  }, [])

  const handleRemoveTag = useCallback((versionId: string, tag: string) => {
    setVersions(prev =>
      prev.map(v =>
        v.id === versionId
          ? { ...v, tags: v.tags.filter(t => t !== tag) }
          : v
      )
    )
  }, [])

  const renderVersionCard = (version: AssetVersion) => {
    const isSelected = selectedVersions.includes(version.id)

    return (
      <Card
        key={version.id}
        style={{
          borderLeft: version.is_current ? '3px solid #00d4ff' : '3px solid transparent',
          cursor: compareMode ? 'pointer' : 'default',
          opacity: compareMode && !isSelected ? 0.5 : 1,
        }}
        bodyStyle={{ padding: 16 }}
      >
        <div style={{ display: 'flex', gap: 16 }}>
          {/* 缩略图 */}
          <div style={{ flexShrink: 0 }}>
            {version.thumbnail_url ? (
              <img
                src={version.thumbnail_url}
                alt={`Version ${version.version_number}`}
                style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 8 }}
              />
            ) : (
              <div style={{
                width: 80,
                height: 80,
                backgroundColor: 'var(--bgElevated)',
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <BranchesOutlined style={{ fontSize: 24, color: '#8b8ba8' }} />
              </div>
            )}
            {compareMode && (
              <div
                style={{
                  marginTop: 8,
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  border: '2px solid',
                  borderColor: isSelected ? '#00d4ff' : '#8b8ba8',
                  backgroundColor: isSelected ? '#00d4ff' : 'transparent',
                  marginLeft: 'auto',
                  marginRight: 'auto',
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  handleSelectVersion(version.id)
                }}
              >
                {isSelected && <CheckOutlined style={{ color: '#fff', fontSize: 12, marginLeft: 3 }} />}
              </div>
            )}
          </div>

          {/* 信息 */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <h4 style={{ margin: 0, fontSize: 14, color: 'var(--textPrimary)' }}>
                {version.version_number}
              </h4>
              {version.is_current && (
                <Badge status="processing" text="当前版本" />
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, color: '#8b8ba8', fontSize: 12 }}>
              <ClockCircleOutlined />
              <span>{version.created_at}</span>
            </div>

            <p style={{ margin: '8px 0', fontSize: 13, color: 'var(--textSecondary)' }}>
              {version.description}
            </p>

            {/* 标签 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              {version.tags.map(tag => (
                <Tag
                  key={tag}
                  closable
                  onClose={() => handleRemoveTag(version.id, tag)}
                  style={{ fontSize: 11 }}
                >
                  {tag}
                </Tag>
              ))}
              <Dropdown
                overlay={
                  <Menu>
                    <Menu.Item onClick={() => handleAddTag(version.id, 'production')}>
                      production
                    </Menu.Item>
                    <Menu.Item onClick={() => handleAddTag(version.id, 'staging')}>
                      staging
                    </Menu.Item>
                    <Menu.Item onClick={() => handleAddTag(version.id, 'latest')}>
                      latest
                    </Menu.Item>
                    <Menu.Item onClick={() => handleAddTag(version.id, 'archive')}>
                      archive
                    </Menu.Item>
                  </Menu>
                }
              >
                <Button type="text" icon={<TagsOutlined />} size="small" />
              </Dropdown>
            </div>
          </div>

          {/* 操作 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Tooltip title="预览">
              <Button type="text" icon={<EyeOutlined />} size="small" />
            </Tooltip>
            <Tooltip title="下载">
              <Button type="text" icon={<DownloadOutlined />} size="small" />
            </Tooltip>
            {!version.is_current && (
              <Tooltip title="回滚到此版本">
                <Button
                  type="text"
                  icon={<LeftOutlined />}
                  size="small"
                  onClick={() => handleRollback(version.id)}
                />
              </Tooltip>
            )}
            <Dropdown
              overlay={
                <Menu>
                  <Menu.Item>复制版本号</Menu.Item>
                  <Menu.Item>查看变更日志</Menu.Item>
                  <Menu.Item>删除版本</Menu.Item>
                </Menu>
              }
            >
              <Button type="text" icon={<MoreOutlined />} size="small" />
            </Dropdown>
          </div>
        </div>
      </Card>
    )
  }

  const renderCompareView = () => {
    if (selectedVersions.length < 2) {
      return (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <BranchesOutlined style={{ fontSize: 48, color: '#8b8ba8' }} />
          <p style={{ color: '#8b8ba8', marginTop: 16 }}>
            请选择两个版本进行对比
          </p>
        </div>
      )
    }

    const version1 = versions.find(v => v.id === selectedVersions[0])
    const version2 = versions.find(v => v.id === selectedVersions[1])

    if (!version1 || !version2) return null

    return (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card title={version1.version_number}>
          {version1.thumbnail_url && (
            <img
              src={version1.thumbnail_url}
              alt={version1.version_number}
              style={{ width: '100%', height: 200, objectFit: 'cover', borderRadius: 8 }}
            />
          )}
          <p style={{ marginTop: 16, color: '#8b8ba8' }}>{version1.description}</p>
          <p style={{ color: '#8b8ba8', fontSize: 12 }}>{version1.created_at}</p>
        </Card>
        <Card title={version2.version_number}>
          {version2.thumbnail_url && (
            <img
              src={version2.thumbnail_url}
              alt={version2.version_number}
              style={{ width: '100%', height: 200, objectFit: 'cover', borderRadius: 8 }}
            />
          )}
          <p style={{ marginTop: 16, color: '#8b8ba8' }}>{version2.description}</p>
          <p style={{ color: '#8b8ba8', fontSize: 12 }}>{version2.created_at}</p>
        </Card>
      </div>
    )
  }

  if (!assetId) {
    return (
      <Card title="版本管理">
        <div style={{ padding: 40, textAlign: 'center' }}>
          <BranchesOutlined style={{ fontSize: 48, color: '#8b8ba8' }} />
          <p style={{ color: '#8b8ba8', marginTop: 16 }}>请选择一个资产查看版本历史</p>
        </div>
      </Card>
    )
  }

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BranchesOutlined />
          版本管理
          <span style={{ color: '#8b8ba8', fontSize: 14 }}>
            ({versions.length} 个版本)
          </span>
        </div>
      }
      extra={
        <Button
          type={compareMode ? 'primary' : 'default'}
          onClick={handleToggleCompareMode}
        >
          {compareMode ? '退出对比' : '版本对比'}
        </Button>
      }
    >
      {compareMode ? (
        renderCompareView()
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {versions.map((version, index) => (
            <div key={version.id} style={{ display: 'flex', gap: 12 }}>
              {/* 版本线 */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 24 }}>
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    backgroundColor: version.is_current ? '#00d4ff' : '#8b8ba8',
                    border: '2px solid white',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                  }}
                />
                {index < versions.length - 1 && (
                  <div
                    style={{
                      width: 2,
                      flex: 1,
                      backgroundColor: '#e8e8e8',
                      marginTop: 4,
                    }}
                  />
                )}
              </div>

              {/* 版本卡片 */}
              <div style={{ flex: 1 }}>
                {renderVersionCard(version)}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
