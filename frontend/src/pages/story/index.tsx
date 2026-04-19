/**
 * YLCraft — Story Maker 页面
 *
 * AI 短剧漫剧生成：
 * - 输入提示词 → 生成角色立绘 + 分镜脚本
 * - 支持短剧 / 漫剧两种风格
 */

import { Card, Input, Select, Button, message, Spin } from 'antd'
import { BookOutlined } from '@ant-design/icons'
import { useState } from 'react'

const { TextArea } = Input

export default function StoryMakerPage() {
  const [prompt, setPrompt] = useState('')
  const [style, setStyle] = useState('short_drama')
  const [loading, setLoading] = useState(false)

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入创作提示词')
      return
    }
    setLoading(true)
    // TODO: 调用 story API
    setTimeout(() => {
      setLoading(false)
      message.info('Story Maker 正在开发中...')
    }, 1000)
  }

  return (
    <div>
      <Card
        title={
          <span>
            <BookOutlined style={{ marginRight: 8 }} />
            Story Maker — AI 短剧漫剧创作
          </span>
        }
      >
        <Card type="inner" title="创作提示词">
          <TextArea
            rows={4}
            placeholder="描述你的故事场景... 例如：「一个年轻女孩在古镇街边卖艺，意外走红成为网红」
            类型：都市言情 / 古装玄幻 / 搞笑段子 / 悬疑反转"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            style={{ marginBottom: 16 }}
          />
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <Select
              value={style}
              onChange={setStyle}
              options={[
                { label: '短剧', value: 'short_drama' },
                { label: '漫剧', value: 'manga' },
              ]}
              style={{ width: 140 }}
            />
            <Button type="primary" onClick={handleGenerate} loading={loading}>
              开始创作
            </Button>
          </div>
        </Card>

        <Card type="inner" title="生成结果" style={{ marginTop: 16 }}>
          <p style={{ color: '#8b8ba8' }}>
            生成结果将显示在这里，包括：
          </p>
          <ul style={{ color: '#8b8ba8', marginTop: 8 }}>
            <li>角色立绘（AI 生成图片）</li>
            <li>分镜脚本（场景描述 + 对话 + 镜头语言）</li>
            <li>配乐建议</li>
            <li>视频/图片素材自动匹配</li>
          </ul>
          <p style={{ color: '#8b8ba8', marginTop: 16 }}>
            该模块正在开发中，敬请期待...
          </p>
        </Card>
      </Card>
    </div>
  )
}
