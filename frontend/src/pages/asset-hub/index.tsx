/**
 * YLCraft - 资产中枢 v3 页面
 */

import { useState, useEffect } from 'react'
import {
  Layout,
  Card,
  Row,
  Col,
  Tabs,
  Typography,
  Space,
  Button,
  Select,
  Input,
  Empty,
  message,
} from 'antd'
import {
  SearchOutlined,
  FolderOpenOutlined,
  BranchesOutlined,
  HistoryOutlined,
  TagsOutlined,
  BoxPlotOutlined,
} from '@ant-design/icons'
import {
  TagTree,
  TagSelector,
  TagSuggestionPanel,
  Model3DViewer,
  SearchPanel,
  AssetGrid,
  LineageGraph,
  AssetVersionManager,
} from '../../components/asset-hub'
import {
  hybridSearch,
  getTagTree,
  listTags,
} from '../../api'

const { Content, Sider } = Layout
const { Title, Text } = Typography
const { Search } = Input

// 模拟资产数据
const MOCK_ASSETS = [
  {
    id: 'asset-1',
    name: '赛博朋克城市夜景',
    asset_type: 'IMAGE',
    thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20city%20night%20scene&image_size=square',
    quality_score: 0.92,
    tags: ['赛博朋克', '城市', '夜景', 'AI生成'],
    created_at: '2024-01-20 14:30:00',
    view_count: 125,
    size: '2.3 MB',
  },
  {
    id: 'asset-2',
    name: '机械姬角色设计',
    asset_type: 'IMAGE',
    thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20female%20android%20character&image_size=square',
    quality_score: 0.88,
    tags: ['角色设计', '机械', '科幻', 'AI生成'],
    created_at: '2024-01-19 09:15:00',
    view_count: 89,
    size: '3.1 MB',
  },
  {
    id: 'asset-3',
    name: '霓虹街道延时摄影',
    asset_type: 'VIDEO',
    thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=tokyo%20neon%20street%20time%20lapse&image_size=square',
    quality_score: 0.95,
    tags: ['街道', '霓虹', '延时摄影'],
    created_at: '2024-01-18 16:45:00',
    view_count: 234,
    size: '45.6 MB',
  },
  {
    id: 'asset-4',
    name: '未来主义建筑',
    asset_type: 'IMAGE',
    thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=futuristic%20architecture%20building&image_size=square',
    quality_score: 0.85,
    tags: ['建筑', '未来主义', '设计'],
    created_at: '2024-01-17 11:20:00',
    view_count: 67,
    size: '1.8 MB',
  },
  {
    id: 'asset-5',
    name: '赛博朋克城市夜景',
    asset_type: 'IMAGE',
    thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20city%20night%20scene&image_size=square',
    quality_score: 0.92,
    tags: ['赛博朋克', '城市', '夜景', 'AI生成'],
    created_at: '2024-01-20 14:30:00',
    view_count: 125,
    size: '2.3 MB',
  },
  {
    id: 'asset-6',
    name: '机械姬角色设计',
    asset_type: 'IMAGE',
    thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20female%20android%20character&image_size=square',
    quality_score: 0.88,
    tags: ['角色设计', '机械', '科幻', 'AI生成'],
    created_at: '2024-01-19 09:15:00',
    view_count: 89,
    size: '3.1 MB',
  },
]

export default function AssetHubPage() {
  const [activeTab, setActiveTab] = useState('search')
  const [loading, setLoading] = useState(false)
  const [assets, setAssets] = useState(MOCK_ASSETS)
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null)
  const [searchParams, setSearchParams] = useState<any>({
    query: '',
    assetType: '',
    qualityScore: null,
    tagFilters: [],
    vectorWeight: 0.7,
    textWeight: 0.3,
  })
  const [tagTree, setTagTree] = useState<any[]>([])
  const [tags, setTags] = useState<any[]>([])

  // 加载标签数据
  useEffect(() => {
    loadTagData()
  }, [])

  const loadTagData = async () => {
    try {
      const [treeRes, listRes] = await Promise.all([
        getTagTree(),
        listTags(),
      ])
      if (treeRes.success) setTagTree(treeRes.data || [])
      if (listRes.success) setTags(listRes.data || [])
    } catch (error) {
      console.error('加载标签数据失败', error)
    }
  }

  const handleSearch = async (params: any) => {
    setSearchParams(params)
    setLoading(true)
    try {
      // 这里应该调用真实的搜索 API
      // const res = await hybridSearch(params)
      // if (res.success) {
      //   setAssets(res.data)
      // }
      
      // 模拟搜索结果
      await new Promise(resolve => setTimeout(resolve, 500))
      setAssets(MOCK_ASSETS)
      message.success('搜索完成')
    } catch (error) {
      message.error('搜索失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAssetClick = (asset: any) => {
    setSelectedAsset(asset.id)
  }

  const handleTagSelect = (tagIds: string[]) => {
    console.log('选中标签:', tagIds)
  }

  return (
    <Layout style={{ height: '100%' }}>
      {/* 左侧侧边栏 - 标签树 */}
      <Sider width={280} theme="light" style={{ borderRight: '1px solid var(--border)' }}>
        <div style={{ padding: 16 }}>
          <Title level={5} style={{ marginBottom: 16 }}>
            <TagsOutlined style={{ marginRight: 8 }} />
            标签管理
          </Title>
          <TagTree
            searchable={true}
            showCheckbox={true}
            onTagClick={(tag) => {
              console.log('点击标签:', tag)
              handleSearch({
                ...searchParams,
                tagFilters: [tag.id],
              })
            }}
          />
        </div>
      </Sider>

      {/* 主内容区 */}
      <Content style={{ padding: 16, overflow: 'auto' }}>
        <Card>
          <Tabs 
            activeKey={activeTab} 
            onChange={setActiveTab}
            items={[
              {
                key: 'search',
                label: (
                  <span>
                    <SearchOutlined />
                    搜索与浏览
                  </span>
                ),
                children: (
                  <Row gutter={16}>
                    <Col span={24}>
                      <SearchPanel
                        defaultParams={{
                          query: '',
                          tagIds: [],
                          assetTypes: [],
                          minQuality: 0,
                          vectorWeight: 0.7,
                          textWeight: 0.3,
                        }}
                        onSearch={handleSearch}
                      />
                    </Col>
                    <Col span={24} style={{ marginTop: 16 }}>
                      <AssetGrid
                        assets={assets as any}
                        loading={loading}
                        total={assets.length}
                        pageSize={12}
                        currentPage={1}
                        onPageChange={(page, pageSize) => {
                          console.log('翻页:', page, pageSize)
                        }}
                        onAssetClick={handleAssetClick}
                      />
                    </Col>
                  </Row>
                ),
              },
              {
                key: 'lineage',
                label: (
                  <span>
                    <BranchesOutlined />
                    谱系与溯源
                  </span>
                ),
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Card title="选择资产查看谱系">
                      <Select
                        style={{ width: 300 }}
                        placeholder="选择一个资产"
                        options={assets.map(a => ({ value: a.id, label: a.name }))}
                        value={selectedAsset}
                        onChange={setSelectedAsset}
                        allowClear
                      />
                    </Card>
                    <LineageGraph assetId={selectedAsset || undefined} />
                  </Space>
                ),
              },
              {
                key: 'versions',
                label: (
                  <span>
                    <HistoryOutlined />
                    版本管理
                  </span>
                ),
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Card title="选择资产查看版本">
                      <Select
                        style={{ width: 300 }}
                        placeholder="选择一个资产"
                        options={assets.map(a => ({ value: a.id, label: a.name }))}
                        value={selectedAsset}
                        onChange={setSelectedAsset}
                        allowClear
                      />
                    </Card>
                    <AssetVersionManager assetId={selectedAsset || undefined} />
                  </Space>
                ),
              },
              {
                key: 'tags',
                label: (
                  <span>
                    <FolderOpenOutlined />
                    标签与分类
                  </span>
                ),
                children: (
                  <Row gutter={16}>
                    <Col span={12}>
                      <Card title="标签选择器">
                        <TagSelector
                          value={[]}
                          onChange={handleTagSelect}
                          showCreate={true}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card title="AI 标签建议">
                        <TagSuggestionPanel
                          assetId={selectedAsset || undefined}
                          onApplyTags={(tagIds) => {
                            message.success(`确认 ${tagIds.length} 个标签`)
                          }}
                        />
                      </Card>
                    </Col>
                  </Row>
                ),
              },
              {
                key: '3d',
                label: (
                  <span>
                    <BoxPlotOutlined />
                    3D 预览
                  </span>
                ),
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Card title="选择 3D 模型">
                      <Select
                        style={{ width: 300 }}
                        placeholder="选择一个 3D 模型"
                        options={assets
                          .filter(a => a.asset_type === '3D_MODEL')
                          .map(a => ({ value: a.id, label: a.name }))}
                        value={selectedAsset}
                        onChange={setSelectedAsset}
                        allowClear
                      />
                    </Card>
                    <Model3DViewer
                      modelUrl={selectedAsset ? 'https://modelviewer.dev/shared-assets/models/Astronaut.glb' : undefined}
                      autoRotate={true}
                      showGrid={true}
                      showEnvironment={true}
                    />
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Content>
    </Layout>
  )
}
