/**
 * YLCraft — 小说阅读器页面
 *
 * 左侧：章节目录
 * 右侧：阅读区域
 * 底部：阅读设置
 */

import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Button,
  Slider,
  Select,
  Space,
  Typography,
  Tooltip,
  message,
} from 'antd'
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import {
  getAsset,
  updateAsset,
} from '../../api'

const { Title, Text, Paragraph } = Typography

export default function NovelReaderPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  
  const [asset, setAsset] = useState<any>(null)
  const [chapters, setChapters] = useState<any[]>([])
  const [currentChapter, setCurrentChapter] = useState(0)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [tocVisible, setTocVisible] = useState(true)
  
  // 阅读设置
  const [fontSize, setFontSize] = useState(16)
  const [bgColor, setBgColor] = useState('#fff')
  const [fontFamily, setFontFamily] = useState('"Microsoft YaHei", sans-serif')
  
  const contentRef = useRef<HTMLDivElement>(null)

  // 加载小说详情
  useEffect(() => {
    const loadAsset = async () => {
      try {
        const res = await getAsset(id!)
        if (res.success) {
          setAsset(res.data)
          // TODO: 加载章节列表
          // 目前先使用 metadata 中的信息
        }
      } catch (e: any) {
        message.error('加载小说失败: ' + e.message)
      }
    }
    loadAsset()
  }, [id])

  // 加载章节内容
  const loadChapter = async (chapterIdx: number) => {
    setLoading(true)
    try {
      // TODO: 从本地文件加载章节内容
      // 目前使用模拟内容
      setContent(`第 ${chapterIdx + 1} 章\n\n这是章节内容...\n\n（待实现：从本地文件加载）`)
      setCurrentChapter(chapterIdx)
      
      // 保存阅读进度
      if (asset) {
        const meta = asset.metadata || {}
        meta.last_read_chapter = chapterIdx
        await updateAsset(id!, { metadata: meta })
      }
    } catch (e: any) {
      message.error('加载章节失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 上一章
  const goPrevChapter = () => {
    if (currentChapter > 0) {
      loadChapter(currentChapter - 1)
    }
  }

  // 下一章
  const goNextChapter = () => {
    if (currentChapter < chapters.length - 1) {
      loadChapter(currentChapter + 1)
    }
  }

  // 键盘快捷键
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') goPrevChapter()
      if (e.key === 'ArrowRight') goNextChapter()
      if (e.key === ' ' && contentRef.current) {
        e.preventDefault()
        contentRef.current.scrollBy({ top: window.innerHeight * 0.8, behavior: 'smooth' })
      }
      if (e.key === 't' || e.key === 'T') {
        setTocVisible(v => !v)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [currentChapter, chapters])

  if (!asset) {
    return <div style={{ padding: 24 }}>加载中...</div>
  }

  const bgOptions = [
    { label: '白色', value: '#fff' },
    { label: '米色', value: '#f5f5dc' },
    { label: '绿色', value: '#c7edcc' },
    { label: '黑色', value: '#1a1a1a' },
  ]

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* 顶部工具栏 */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 16 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/novel-bookshelf')}
        >
          书架
        </Button>
        <div style={{ flex: 1 }}>
          <Text strong>{asset.title}</Text>
          {chapters.length > 0 && (
            <Text type="secondary" style={{ marginLeft: 8 }}>
              {chapters[currentChapter]?.title || `第 ${currentChapter + 1} 章`}
            </Text>
          )}
        </div>
        <Button
          type="text"
          icon={tocVisible ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />}
          onClick={() => setTocVisible(v => !v)}
        >
          目录
        </Button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 左侧：章节目录 */}
        {tocVisible && (
          <div style={{ width: 280, borderRight: '1px solid #f0f0f0', overflow: 'auto', padding: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>目录</div>
            {chapters.map((ch, idx) => (
              <div
                key={idx}
                onClick={() => loadChapter(idx)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  background: idx === currentChapter ? '#e6f7ff' : 'transparent',
                  borderRadius: 4,
                  fontSize: 13,
                }}
              >
                {ch.title || `第 ${idx + 1} 章`}
              </div>
            ))}
            {chapters.length === 0 && (
              <div style={{ padding: 16, color: '#999' }}>
                暂无章节信息（待实现）
              </div>
            )}
          </div>
        )}

        {/* 右侧：阅读区域 */}
        <div
          ref={contentRef}
          style={{
            flex: 1,
            overflow: 'auto',
            padding: 24,
            background: bgColor,
            color: bgColor === '#1a1a1a' ? '#ccc' : '#333',
          }}
        >
          <div
            style={{
              maxWidth: 800,
              margin: '0 auto',
              fontSize,
              fontFamily,
              lineHeight: 1.8,
              whiteSpace: 'pre-wrap',
            }}
          >
            {loading ? (
              <div style={{ textAlign: 'center', padding: 48 }}>加载中...</div>
            ) : (
              content || '请选择章节开始阅读'
            )}
          </div>

          {/* 翻页按钮 */}
          <div style={{ maxWidth: 800, margin: '24px auto 0', display: 'flex', justifyContent: 'space-between' }}>
            <Button disabled={currentChapter <= 0} onClick={goPrevChapter}>
              上一章
            </Button>
            <Button disabled={currentChapter >= chapters.length - 1} onClick={goNextChapter}>
              下一章
            </Button>
          </div>
        </div>
      </div>

      {/* 底部：阅读设置 */}
      <div style={{ padding: '8px 16px', borderTop: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 24 }}>
        <Space>
          <span>字体大小：</span>
          <Slider
            min={12}
            max={24}
            value={fontSize}
            onChange={setFontSize}
            style={{ width: 120 }}
          />
          <span>{fontSize}px</span>
        </Space>
        <Space>
          <span>背景：</span>
          <Select
            value={bgColor}
            onChange={setBgColor}
            options={bgOptions}
            style={{ width: 100 }}
          />
        </Space>
        <Space>
          <span>字体：</span>
          <Select
            value={fontFamily}
            onChange={setFontFamily}
            options={[
              { label: '微软雅黑', value: '"Microsoft YaHei", sans-serif' },
              { label: '宋体', value: 'SimSun, serif' },
              { label: '楷体', value: 'KaiTi, serif' },
            ]}
            style={{ width: 120 }}
          />
        </Space>
        <div style={{ marginLeft: 'auto', color: '#999', fontSize: 12 }}>
          快捷键：← 上一章 → 下一章 T 显示/隐藏目录 Space 翻页
        </div>
      </div>
    </div>
  )
}
