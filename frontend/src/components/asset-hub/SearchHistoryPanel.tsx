/**
 * YLCraft — 搜索历史和收藏组件
 * 
 * 支持：
 * - 本地搜索历史记录
 * - 搜索条件收藏
 * - 历史记录管理
 */

import { useState, useEffect, useCallback } from 'react'
import { Card, Button, Tag, List, Empty, Popconfirm, Input, message } from 'antd'
import { 
  HistoryOutlined, 
  StarOutlined,
  DeleteOutlined,
  SearchOutlined,
  PlusOutlined,
  CloseOutlined,
  EditOutlined,
} from '@ant-design/icons'

interface SearchHistory {
  id: string
  query: string
  timestamp: number
  filters?: {
    assetType?: string
    tagFilters?: string[]
    minQuality?: number
  }
}

interface SearchFavorite {
  id: string
  name: string
  query: string
  filters?: {
    assetType?: string
    tagFilters?: string[]
    minQuality?: number
    vectorWeight?: number
    textWeight?: number
  }
  createdAt: number
}

interface SearchHistoryPanelProps {
  onSearch?: (query: string, filters?: SearchHistory['filters']) => void
  maxHistoryItems?: number
}

const STORAGE_KEY = {
  history: 'ylcraft_search_history',
  favorites: 'ylcraft_search_favorites',
}

export function SearchHistoryPanel({ 
  onSearch,
  maxHistoryItems = 20 
}: SearchHistoryPanelProps) {
  const [history, setHistory] = useState<SearchHistory[]>([])
  const [favorites, setFavorites] = useState<SearchFavorite[]>([])
  const [editingFavorite, setEditingFavorite] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')

  // 加载历史记录
  useEffect(() => {
    const savedHistory = localStorage.getItem(STORAGE_KEY.history)
    if (savedHistory) {
      try {
        setHistory(JSON.parse(savedHistory))
      } catch (e) {
        console.error('Failed to parse search history:', e)
      }
    }

    const savedFavorites = localStorage.getItem(STORAGE_KEY.favorites)
    if (savedFavorites) {
      try {
        setFavorites(JSON.parse(savedFavorites))
      } catch (e) {
        console.error('Failed to parse search favorites:', e)
      }
    }
  }, [])

  // 保存历史记录
  const saveHistory = useCallback((newHistory: SearchHistory[]) => {
    setHistory(newHistory)
    localStorage.setItem(STORAGE_KEY.history, JSON.stringify(newHistory))
  }, [])

  // 保存收藏
  const saveFavorites = useCallback((newFavorites: SearchFavorite[]) => {
    setFavorites(newFavorites)
    localStorage.setItem(STORAGE_KEY.favorites, JSON.stringify(newFavorites))
  }, [])

  // 添加搜索历史
  const addToHistory = useCallback((query: string, filters?: SearchHistory['filters']) => {
    const newHistory: SearchHistory = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      query,
      timestamp: Date.now(),
      filters,
    }

    // 去重：新搜索移到最前面
    const filteredHistory = history.filter(h => h.query !== query)
    const updatedHistory = [newHistory, ...filteredHistory].slice(0, maxHistoryItems)
    saveHistory(updatedHistory)
  }, [history, maxHistoryItems, saveHistory])

  // 删除单条历史
  const deleteHistory = useCallback((id: string) => {
    const updatedHistory = history.filter(h => h.id !== id)
    saveHistory(updatedHistory)
    message.success('已删除历史记录')
  }, [history, saveHistory])

  // 清空所有历史
  const clearAllHistory = useCallback(() => {
    saveHistory([])
    message.success('已清空所有历史记录')
  }, [saveHistory])

  // 添加到收藏
  const addToFavorites = useCallback((query: string, name?: string, filters?: SearchFavorite['filters']) => {
    const newFavorite: SearchFavorite = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name: name || query,
      query,
      filters,
      createdAt: Date.now(),
    }

    setFavorites(prev => {
      const updated = [newFavorite, ...prev]
      saveFavorites(updated)
      return updated
    })
    message.success('已添加到收藏')
  }, [saveFavorites])

  // 删除收藏
  const deleteFavorite = useCallback((id: string) => {
    setFavorites(prev => {
      const updated = prev.filter(f => f.id !== id)
      saveFavorites(updated)
      return updated
    })
    message.success('已删除收藏')
  }, [saveFavorites])

  // 更新收藏名称
  const updateFavoriteName = useCallback((id: string, newName: string) => {
    setFavorites(prev => {
      const updated = prev.map(f => 
        f.id === id ? { ...f, name: newName } : f
      )
      saveFavorites(updated)
      return updated
    })
    setEditingFavorite(null)
    setEditingName('')
    message.success('已更新收藏名称')
  }, [saveFavorites])

  // 格式化时间
  const formatTime = (timestamp: number) => {
    const now = Date.now()
    const diff = now - timestamp
    
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
    if (diff < 604800000) return `${Math.floor(diff / 86400000)} 天前`
    
    return new Date(timestamp).toLocaleDateString('zh-CN')
  }

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      {/* 搜索历史 */}
      <Card 
        title={
          <span>
            <HistoryOutlined style={{ marginRight: 8 }} />
            搜索历史
          </span>
        }
        size="small"
        style={{ flex: 1 }}
        extra={
          history.length > 0 && (
            <Button 
              type="link" 
              size="small" 
              danger
              onClick={clearAllHistory}
            >
              清空
            </Button>
          )
        }
      >
        {history.length === 0 ? (
          <Empty description="暂无搜索历史" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            size="small"
            dataSource={history.slice(0, 10)}
            renderItem={item => (
              <List.Item
                key={item.id}
                actions={[
                  <Button 
                    key="delete" 
                    type="text" 
                    size="small" 
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => deleteHistory(item.id)}
                  />,
                  <Button 
                    key="favorite" 
                    type="text" 
                    size="small"
                    icon={<StarOutlined />}
                    onClick={() => addToFavorites(item.query, undefined, item.filters)}
                  />,
                ]}
              >
                <List.Item.Meta
                  avatar={<SearchOutlined style={{ color: '#8b8ba8' }} />}
                  title={
                    <span 
                      style={{ cursor: 'pointer' }}
                      onClick={() => onSearch?.(item.query, item.filters)}
                    >
                      {item.query || '(空搜索)'}
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 11, color: '#8b8ba8' }}>
                      {formatTime(item.timestamp)}
                      {item.filters?.assetType && (
                        <Tag style={{ marginLeft: 8, fontSize: 10 }}>
                          {item.filters.assetType}
                        </Tag>
                      )}
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 搜索收藏 */}
      <Card 
        title={
          <span>
            <StarOutlined style={{ color: '#faad14', marginRight: 8 }} />
            收藏的搜索
          </span>
        }
        size="small"
        style={{ flex: 1 }}
      >
        {favorites.length === 0 ? (
          <Empty description="暂无收藏" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            size="small"
            dataSource={favorites}
            renderItem={item => (
              <List.Item
                key={item.id}
                actions={[
                  editingFavorite === item.id ? (
                    <>
                      <Input
                        size="small"
                        value={editingName}
                        onChange={e => setEditingName(e.target.value)}
                        onPressEnter={() => updateFavoriteName(item.id, editingName)}
                        style={{ width: 100 }}
                        autoFocus
                      />
                      <Button 
                        type="text" 
                        size="small" 
                        onClick={() => updateFavoriteName(item.id, editingName)}
                      >
                        保存
                      </Button>
                    </>
                  ) : (
                    <Button 
                      key="edit" 
                      type="text" 
                      size="small" 
                      icon={<EditOutlined />}
                      onClick={() => {
                        setEditingFavorite(item.id)
                        setEditingName(item.name)
                      }}
                    />
                  ),
                  <Popconfirm
                    key="delete"
                    title="确定删除此收藏？"
                    onConfirm={() => deleteFavorite(item.id)}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button 
                      type="text" 
                      size="small" 
                      danger
                      icon={<DeleteOutlined />}
                    />
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  avatar={<StarOutlined style={{ color: '#faad14' }} />}
                  title={
                    <span 
                      style={{ cursor: 'pointer' }}
                      onClick={() => onSearch?.(item.query, item.filters)}
                    >
                      {item.name}
                    </span>
                  }
                  description={
                    <span style={{ fontSize: 11, color: '#8b8ba8' }}>
                      {item.query}
                      {item.filters?.assetType && (
                        <Tag style={{ marginLeft: 8, fontSize: 10 }}>
                          {item.filters.assetType}
                        </Tag>
                      )}
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>
  )
}

// 导出工具函数供外部使用
export const searchHistoryUtils = {
  addHistory: (query: string, filters?: SearchHistory['filters']) => {
    const savedHistory = localStorage.getItem(STORAGE_KEY.history)
    const history: SearchHistory[] = savedHistory ? JSON.parse(savedHistory) : []
    
    const newHistory: SearchHistory = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      query,
      timestamp: Date.now(),
      filters,
    }
    
    const filteredHistory = history.filter(h => h.query !== query)
    const updatedHistory = [newHistory, ...filteredHistory].slice(0, 20)
    localStorage.setItem(STORAGE_KEY.history, JSON.stringify(updatedHistory))
  },

  getHistory: (): SearchHistory[] => {
    const savedHistory = localStorage.getItem(STORAGE_KEY.history)
    return savedHistory ? JSON.parse(savedHistory) : []
  },

  clearHistory: () => {
    localStorage.removeItem(STORAGE_KEY.history)
  },

  addFavorite: (name: string, query: string, filters?: SearchFavorite['filters']) => {
    const savedFavorites = localStorage.getItem(STORAGE_KEY.favorites)
    const favorites: SearchFavorite[] = savedFavorites ? JSON.parse(savedFavorites) : []
    
    const newFavorite: SearchFavorite = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name,
      query,
      filters,
      createdAt: Date.now(),
    }
    
    const updatedFavorites = [newFavorite, ...favorites]
    localStorage.setItem(STORAGE_KEY.favorites, JSON.stringify(updatedFavorites))
  },

  getFavorites: (): SearchFavorite[] => {
    const savedFavorites = localStorage.getItem(STORAGE_KEY.favorites)
    return savedFavorites ? JSON.parse(savedFavorites) : []
  },

  removeFavorite: (id: string) => {
    const savedFavorites = localStorage.getItem(STORAGE_KEY.favorites)
    const favorites: SearchFavorite[] = savedFavorites ? JSON.parse(savedFavorites) : []
    const updatedFavorites = favorites.filter(f => f.id !== id)
    localStorage.setItem(STORAGE_KEY.favorites, JSON.stringify(updatedFavorites))
  },
}
