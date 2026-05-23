/**
 * YLCraft — 标签自动建议面板
 * 
 * 基于 AI 分析资产内容，自动推荐标签
 */

import { useState, useEffect, useCallback } from 'react'
import { Card, Tag, Button, Progress, Empty, Spin } from 'antd'
import { ThunderboltOutlined, CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons'

interface SuggestedTag {
  id?: string
  name: string
  category: string
  confidence: number
  source: 'ai' | 'manual' | 'system'
}

interface TagSuggestionPanelProps {
  assetId?: string
  onApplyTags?: (tags: string[]) => void
}

export function TagSuggestionPanel({ assetId, onApplyTags }: TagSuggestionPanelProps) {
  const [suggestions, setSuggestions] = useState<SuggestedTag[]>([])
  const [loading, setLoading] = useState(false)
  const [appliedTags, setAppliedTags] = useState<Set<string>>(new Set())
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set())

  // 模拟 AI 标签建议
  const fetchSuggestions = useCallback(async () => {
    setLoading(true)
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    const mockSuggestions: SuggestedTag[] = [
      { name: '人物', category: '类型', confidence: 0.95, source: 'ai' },
      { name: '古风', category: '风格', confidence: 0.88, source: 'ai' },
      { name: '插画', category: '类型', confidence: 0.82, source: 'ai' },
      { name: '唯美', category: '风格', confidence: 0.78, source: 'ai' },
      { name: '女性角色', category: '人物', confidence: 0.75, source: 'ai' },
      { name: '汉服', category: '服饰', confidence: 0.72, source: 'ai' },
      { name: '古风建筑', category: '场景', confidence: 0.68, source: 'ai' },
      { name: '水墨', category: '风格', confidence: 0.65, source: 'ai' },
    ]
    
    setSuggestions(mockSuggestions)
    setLoading(false)
  }, [])

  useEffect(() => {
    if (assetId) {
      fetchSuggestions()
    }
  }, [assetId, fetchSuggestions])

  const toggleTag = useCallback((tagName: string) => {
    setSelectedTags(prev => {
      const next = new Set(prev)
      if (next.has(tagName)) {
        next.delete(tagName)
      } else {
        next.add(tagName)
      }
      return next
    })
  }, [])

  const applyAllSelected = useCallback(() => {
    const selected = Array.from(selectedTags)
    if (selected.length > 0) {
      onApplyTags?.(selected)
      setAppliedTags(prev => new Set([...prev, ...selected]))
      setSelectedTags(new Set())
    }
  }, [selectedTags, onApplyTags])

  const applySingleTag = useCallback((tagName: string) => {
    onApplyTags?.([tagName])
    setAppliedTags(prev => new Set([...prev, tagName]))
    setSelectedTags(prev => {
      const next = new Set(prev)
      next.delete(tagName)
      return next
    })
  }, [onApplyTags])

  const getCategoryColor = (category: string): string => {
    const colors: Record<string, string> = {
      '类型': '#00d4ff',
      '风格': '#722ed1',
      '人物': '#ff4d6a',
      '服饰': '#52c41a',
      '场景': '#faad14',
      '系统': '#8b8ba8',
    }
    return colors[category] || '#8b8ba8'
  }

  const getSourceBadge = (source: string) => {
    const badges = {
      ai: { text: 'AI', color: 'purple' },
      manual: { text: '手动', color: 'blue' },
      system: { text: '系统', color: 'default' },
    }
    return badges[source as keyof typeof badges] || badges.system
  }

  if (loading) {
    return (
      <Card title="AI 标签建议" extra={<ReloadOutlined spin />}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Spin size="large" tip="AI 正在分析..." />
        </div>
      </Card>
    )
  }

  if (!assetId) {
    return (
      <Card title="AI 标签建议">
        <Empty description="请选择一个资产以获取标签建议" />
      </Card>
    )
  }

  return (
    <Card 
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ThunderboltOutlined style={{ color: '#faad14' }} />
          AI 标签建议
        </div>
      }
      extra={
        <Button 
          type="text" 
          icon={<ReloadOutlined />}
          onClick={fetchSuggestions}
        >
          刷新
        </Button>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {suggestions.map((tag, index) => {
          const isApplied = appliedTags.has(tag.name)
          const isSelected = selectedTags.has(tag.name)
          const sourceBadge = getSourceBadge(tag.source)
          
          return (
            <div
              key={`${tag.name}-${index}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: 12,
                backgroundColor: isSelected ? 'rgba(0, 212, 255, 0.1)' : 'transparent',
                borderRadius: 8,
                border: `1px solid ${isSelected ? 'rgba(0, 212, 255, 0.3)' : 'transparent'}`,
                transition: 'all 0.2s',
              }}
            >
              <button
                type="button"
                onClick={() => toggleTag(tag.name)}
                disabled={isApplied}
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  border: `2px solid ${isApplied ? '#52c41a' : isSelected ? '#00d4ff' : '#8b8ba8'}`,
                  backgroundColor: isApplied ? '#52c41a' : isSelected ? '#00d4ff' : 'transparent',
                  cursor: isApplied ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {isApplied && <CheckOutlined style={{ color: '#fff', fontSize: 12 }} />}
              </button>

              <Tag color={getCategoryColor(tag.category)} style={{ fontSize: 13 }}>
                {tag.name}
              </Tag>

              <span style={{ color: '#8b8ba8', fontSize: 12 }}>
                {tag.category}
              </span>

              <div style={{ flex: 1 }}>
                <Progress
                  percent={Math.round(tag.confidence * 100)}
                  size="small"
                  strokeColor={{
                    '0%': '#52c41a',
                    '100%': '#00d4ff',
                  }}
                  showInfo={false}
                />
              </div>

              <span style={{ color: '#8b8ba8', fontSize: 12 }}>
                {Math.round(tag.confidence * 100)}%
              </span>

              <Tag color={sourceBadge.color} style={{ fontSize: 10 }}>
                {sourceBadge.text}
              </Tag>

              {!isApplied && (
                <Button
                  type="link"
                  size="small"
                  onClick={() => applySingleTag(tag.name)}
                >
                  应用
                </Button>
              )}

              {isApplied && (
                <span style={{ color: '#52c41a', fontSize: 12 }}>
                  <CheckOutlined /> 已应用
                </span>
              )}
            </div>
          )
        })}
      </div>

      {selectedTags.size > 0 && (
        <div style={{ 
          marginTop: 16, 
          paddingTop: 16, 
          borderTop: '1px solid rgba(255,255,255,0.08)',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 8,
        }}>
          <Button
            type="text"
            icon={<CloseOutlined />}
            onClick={() => setSelectedTags(new Set())}
          >
            清除选择
          </Button>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            onClick={applyAllSelected}
          >
            应用选中 ({selectedTags.size})
          </Button>
        </div>
      )}
    </Card>
  )
}
