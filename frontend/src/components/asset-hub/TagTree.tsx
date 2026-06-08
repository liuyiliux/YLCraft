/**
 * YLCraft — 标签树组件
 * 
 * 基于 Ant Design Tree 实现的懒加载标签树，支持：
 * - 懒加载子节点
 * - 多选模式
 * - 搜索过滤
 * - 自定义图标和样式
 */

import { useState, useCallback, useEffect } from 'react'
import { Tree, Input, Spin } from 'antd'
import {
  FolderOutlined,
  FolderOpenOutlined,
  TagOutlined,
  SearchOutlined
} from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import { getTagTree, getTagChildren } from '../../api'

interface TagItem {
  id: string
  name: string
  parent_id: string | null
  level: number
  path: string
  color: string | null
  category: string | null
  asset_count: number
  children?: TagItem[]
}

interface TagTreeProps {
  selectedKeys?: string[]
  checkedKeys?: string[]
  onSelect?: (keys: string[], info: { node: DataNode }) => void
  onCheck?: (checkedKeys: string[], info: { node: DataNode }) => void
  showCheckbox?: boolean
  searchable?: boolean
  onTagClick?: (tag: TagItem) => void
}

export function TagTree({
  selectedKeys = [],
  checkedKeys = [],
  onSelect,
  onCheck,
  showCheckbox = false,
  searchable = true,
  onTagClick,
}: TagTreeProps) {
  const [treeData, setTreeData] = useState<DataNode[]>([])
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [searchValue, setSearchValue] = useState('')
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [tagMap, setTagMap] = useState<Record<string, TagItem>>({})

  // 从 API 加载标签数据
  const fetchTags = useCallback(async (parentId?: string): Promise<TagItem[]> => {
    try {
      if (parentId) {
        const res = await getTagChildren(parentId)
        const children = res?.data || res || []
        const items: TagItem[] = children.map((t: any) => {
          const tag: TagItem = {
            id: t.id, name: t.name,
            parent_id: t.parent_id || null,
            level: t.level || 0,
            path: t.path || '',
            color: t.color || null,
            category: t.category || null,
            asset_count: t.asset_count || 0,
          }
          setTagMap(prev => ({ ...prev, [tag.id]: tag }))
          return tag
        })
        return items
      } else {
        const res = await getTagTree()
        const tags = res?.data || res || []
        const items: TagItem[] = (Array.isArray(tags) ? tags : []).map((t: any) => {
          const tag: TagItem = {
            id: t.id, name: t.name,
            parent_id: t.parent_id || null,
            level: t.level || 0,
            path: t.path || '',
            color: t.color || null,
            category: t.category || null,
            asset_count: t.asset_count || 0,
            children: t.children,
          }
          setTagMap(prev => ({ ...prev, [tag.id]: tag }))
          return tag
        })
        return items
      }
    } catch {
      return []
    }
  }, [])

  // 初始化加载顶层标签
  useEffect(() => {
    setLoading(true)
    fetchTags().then(tags => {
      setTreeData(tags.map(tagToTreeNode))
    }).finally(() => setLoading(false))
  }, [fetchTags])

  const tagToTreeNode = (tag: TagItem): DataNode => {
    const hasChildren = !!(tag.children && tag.children.length > 0) || tag.asset_count > 0
    const childrenList = tag.children || undefined
    return {
      title: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
          <span
            style={{
              display: 'inline-block',
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: tag.color || '#8b8ba8'
            }}
          />
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {tag.name}
          </span>
          <span style={{ color: '#8b8ba8', fontSize: 12 }}>
            {tag.asset_count}
          </span>
        </div>
      ),
      key: tag.id,
      icon: hasChildren ? <FolderOutlined /> : <TagOutlined />,
      isLeaf: !hasChildren,
      children: childrenList ? childrenList.map(tagToTreeNode) : (hasChildren ? [] : undefined),
    }
  }

  const onLoadData = useCallback(async (node: DataNode) => {
    if (loadingKeys.has(node.key as string)) return
    
    setLoadingKeys(prev => new Set([...prev, node.key as string]))
    
    const children = await fetchTags(node.key as string)
    
    setTreeData(prev => updateTreeData(prev, node.key as string, children))
    setLoadingKeys(prev => {
      const next = new Set(prev)
      next.delete(node.key as string)
      return next
    })
    // 展开当前节点
    setExpandedKeys(prev => {
      const key = node.key as string
      if (!prev.includes(key)) {
        return [...prev, key]
      }
      return prev
    })
  }, [fetchTags, loadingKeys])

  const updateTreeData = (
    data: DataNode[],
    key: string,
    children: TagItem[]
  ): DataNode[] => {
    return data.map(node => {
      if (node.key === key) {
        return {
          ...node,
          icon: <FolderOpenOutlined />,
          children: children.map(tagToTreeNode),
        }
      }
      if (node.children) {
        return { ...node, children: updateTreeData(node.children, key, children) }
      }
      return node
    })
  }

  const filterTree = (data: DataNode[], keyword: string): DataNode[] => {
    if (!keyword) return data
    
    const lowerKeyword = keyword.toLowerCase()
    return data
      .map(node => {
        const title = typeof node.title === 'string' ? node.title : ''
        const matches = title.toLowerCase().includes(lowerKeyword)
        
        if (matches) return node
        
        if (node.children) {
          const filteredChildren = filterTree(node.children, keyword)
          return filteredChildren.length > 0 ? { ...node, children: filteredChildren } : null
        }
        return null
      })
      .filter(Boolean) as DataNode[]
  }

  const handleSelect = useCallback((keys: string[], info) => {
    setExpandedKeys(prev => {
      const key = info.node.key as string
      if (prev.includes(key)) {
        return prev.filter(k => k !== key)
      }
      return [...prev, key]
    })
    onSelect?.(keys, info)
  }, [onSelect])

  const renderTreeIcon = (props: { expanded?: boolean; isLeaf?: boolean }) => {
    if (props.isLeaf) {
      return <TagOutlined style={{ color: '#8b8ba8' }} />
    }
    return props.expanded 
      ? <FolderOpenOutlined style={{ color: '#00d4ff' }} /> 
      : <FolderOutlined style={{ color: '#8b8ba8' }} />
  }

  const filteredData = filterTree(treeData, searchValue)

  return (
    <div className="tag-tree">
      {searchable && (
        <div style={{ padding: 12, borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <Input
            placeholder="搜索标签..."
            prefix={<SearchOutlined />}
            value={searchValue}
            onChange={e => setSearchValue(e.target.value)}
            style={{ backgroundColor: 'rgba(255,255,255,0.05)', border: 'none' }}
          />
        </div>
      )}
      
      <Tree
        treeData={filteredData}
        expandedKeys={expandedKeys}
        selectedKeys={selectedKeys}
        checkedKeys={checkedKeys}
        onSelect={handleSelect}
        onCheck={onCheck}
        showLine
        checkable={showCheckbox}
        loadData={onLoadData}
        icon={renderTreeIcon}
        onDoubleClick={onTagClick ? (_, info: any) => {
          const key = info.node.key as string
          const tag = tagMap[key]
          if (tag) onTagClick(tag)
        } : undefined}
        style={{ padding: 12 }}
      />
      {loading && (
        <div style={{ textAlign: 'center', padding: 12 }}>
          <Spin size="small" />
        </div>
      )}
    </div>
  )
}
