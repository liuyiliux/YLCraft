/**
 * YLCraft — 高级搜索面板组件
 * 
 * 支持：
 * - 文本搜索
 * - 标签过滤
 * - 资产类型过滤
 * - 质量评分过滤
 * - 向量权重配置
 * - 混合搜索
 */

import { useState, useCallback } from 'react'
import { Input, Select, Slider, Tag, Button, Card, Space, Divider, Radio } from 'antd'
import { SearchOutlined, FilterOutlined, SettingOutlined, CloseOutlined, HistoryOutlined, StarOutlined } from '@ant-design/icons'
import { TagSelector } from './TagSelector'

export interface SearchParams {
  query: string
  tagIds: string[]
  assetTypes: string[]
  minQuality: number
  vectorWeight: number
  textWeight: number
  mode: 'fuzzy' | 'hybrid'
}

interface SearchPanelProps {
  onSearch?: (params: SearchParams) => void
  defaultParams?: Partial<SearchParams>
  searchHistory?: string[]
  onHistoryClick?: (keyword: string) => void
}

const ASSET_TYPES = [
  { value: 'IMAGE', label: '图片' },
  { value: 'VIDEO', label: '视频' },
  { value: 'AUDIO', label: '音频' },
  { value: 'TEXT', label: '文本' },
  { value: 'MODEL', label: '模型' },
  { value: 'CHARACTER', label: '角色' },
  { value: '3D_MODEL', label: '3D模型' },
]

export function SearchPanel({ onSearch, defaultParams, searchHistory = [], onHistoryClick }: SearchPanelProps) {
  const [query, setQuery] = useState(defaultParams?.query || '')
  const [tagIds, setTagIds] = useState(defaultParams?.tagIds || [])
  const [assetTypes, setAssetTypes] = useState(defaultParams?.assetTypes || [])
  const [minQuality, setMinQuality] = useState(defaultParams?.minQuality || 0)
  const [vectorWeight, setVectorWeight] = useState(defaultParams?.vectorWeight || 70)
  const [textWeight, setTextWeight] = useState(defaultParams?.textWeight || 30)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [searchMode, setSearchMode] = useState<'fuzzy' | 'hybrid'>(defaultParams?.mode || 'fuzzy')

  const handleSearch = useCallback(() => {
    onSearch?.({
      query,
      tagIds,
      assetTypes,
      minQuality,
      vectorWeight: vectorWeight / 100,
      textWeight: textWeight / 100,
      mode: searchMode,
    })
  }, [query, tagIds, assetTypes, minQuality, vectorWeight, textWeight, searchMode, onSearch])

  const handleClear = useCallback(() => {
    setQuery('')
    setTagIds([])
    setAssetTypes([])
    setMinQuality(0)
    setVectorWeight(70)
    setTextWeight(30)
  }, [])

  const handleHistoryClickLocal = useCallback((keyword: string) => {
    setQuery(keyword)
    if (onHistoryClick) {
      onHistoryClick(keyword)
    } else {
      onSearch?.({
        query: keyword,
        tagIds,
        assetTypes,
        minQuality,
        vectorWeight: vectorWeight / 100,
        textWeight: textWeight / 100,
        mode: searchMode,
      })
    }
  }, [tagIds, assetTypes, minQuality, vectorWeight, textWeight, searchMode, onSearch, onHistoryClick])

  const updateWeights = useCallback((newVectorWeight: number) => {
    setVectorWeight(newVectorWeight)
    setTextWeight(100 - newVectorWeight)
  }, [])

  return (
    <Card
      style={{ 
        backgroundColor: 'var(--bgCard)',
        border: '1px solid var(--border)',
      }}
    >
      {/* 搜索框 */}
      <div style={{ display: 'flex', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <Input
            size="large"
            placeholder="搜索资产..."
            prefix={<SearchOutlined />}
            suffix={
              query && (
                <Button type="text" onClick={handleClear}>
                  <CloseOutlined />
                </Button>
              )
            }
            value={query}
            onChange={e => setQuery(e.target.value)}
            onPressEnter={handleSearch}
            style={{ backgroundColor: 'var(--bgInput)' }}
          />
        </div>
        <Button
          type="primary"
          size="large"
          onClick={handleSearch}
          icon={<SearchOutlined />}
        >
          搜索
        </Button>
      </div>

      {/* 搜索历史 */}
      {searchHistory.length > 0 && !query && (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <HistoryOutlined style={{ color: '#8b8ba8' }} />
            <span style={{ color: '#8b8ba8', fontSize: 12 }}>搜索历史</span>
          </div>
          <Space wrap>
            {searchHistory.map((keyword, index) => (
              <Button
                key={index}
                type="text"
                onClick={() => handleHistoryClickLocal(keyword)}
              >
                {keyword}
              </Button>
            ))}
          </Space>
        </div>
      )}

      {/* 搜索模式 + 高级选项 */}
      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
        <Radio.Group
          value={searchMode}
          onChange={e => setSearchMode(e.target.value)}
          size="small"
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="fuzzy">模糊搜索</Radio.Button>
          <Radio.Button value="hybrid">混合搜索</Radio.Button>
        </Radio.Group>
        <Button
          type="text"
          onClick={() => setShowAdvanced(!showAdvanced)}
          icon={<SettingOutlined />}
          size="small"
        >
          {showAdvanced ? '收起高级选项' : '展开高级选项'}
        </Button>
      </div>

      {/* 高级选项 */}
      {showAdvanced && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            {/* 标签过滤 */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <FilterOutlined style={{ color: '#8b8ba8' }} />
                <span style={{ color: '#8b8ba8', fontSize: 12 }}>标签过滤</span>
              </div>
              <TagSelector
                value={tagIds}
                onChange={setTagIds}
                placeholder="选择标签..."
              />
            </div>

            {/* 资产类型 */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <FilterOutlined style={{ color: '#8b8ba8' }} />
                <span style={{ color: '#8b8ba8', fontSize: 12 }}>资产类型</span>
              </div>
              <Select
                mode="multiple"
                value={assetTypes}
                onChange={setAssetTypes}
                placeholder="选择类型..."
                style={{ width: '100%' }}
                dropdownStyle={{ backgroundColor: 'var(--bgCard)' }}
              >
                {ASSET_TYPES.map(type => (
                  <Select.Option key={type.value} value={type.value}>
                    {type.label}
                  </Select.Option>
                ))}
              </Select>
            </div>
          </div>

          <Divider />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            {/* 质量评分 */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <StarOutlined style={{ color: '#faad14' }} />
                <span style={{ color: '#8b8ba8', fontSize: 12 }}>最低质量评分</span>
                <span style={{ color: '#00d4ff', fontSize: 12 }}>{minQuality / 10}</span>
              </div>
              <Slider
                min={0}
                max={10}
                step={0.5}
                value={minQuality}
                onChange={setMinQuality}
                marks={{
                  0: '0',
                  5: '0.5',
                  10: '1.0',
                }}
              />
            </div>

            {/* 权重配置 */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <SettingOutlined style={{ color: '#8b8ba8' }} />
                <span style={{ color: '#8b8ba8', fontSize: 12 }}>搜索权重</span>
              </div>
              <div style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ color: '#722ed1', fontSize: 12 }}>向量搜索 {vectorWeight}%</span>
                  <span style={{ color: '#1890ff', fontSize: 12 }}>文本搜索 {textWeight}%</span>
                </div>
                <Slider
                  min={0}
                  max={100}
                  value={vectorWeight}
                  onChange={updateWeights}
                  marks={{
                    0: '0%',
                    50: '50%',
                    100: '100%',
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
