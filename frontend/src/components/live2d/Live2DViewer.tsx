/**
 * YLCraft — Live2D WebGL 预览组件
 *
 * 基于 Canvas 2D 的轻量级 Live2D 预览
 * 支持：表情切换、视线跟踪、眨眼动画
 */

import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Card, Slider, Select, Space, Typography, Spin, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

const { Text } = Typography

interface BoneTransform {
  x: number
  y: number
  angle: number
  scale_x: number
  scale_y: number
}

interface Live2DViewerProps {
  modelId: string
  imageUrl: string
  riggingState?: any
  currentExpression?: string
  eyeTrackingX?: number
  eyeTrackingY?: number
  onExpressionChange?: (expression: string) => void
  onEyeTrackingChange?: (x: number, y: number) => void
}

const EXPRESSIONS = [
  { value: 'neutral', label: '😶 默认' },
  { value: 'happy', label: '😊 开心' },
  { value: 'sad', label: '😢 难过' },
  { value: 'angry', label: '😠 生气' },
  { value: 'surprised', label: '😲 惊讶' },
  { value: 'loved', label: '😍 喜欢' },
  { value: 'focused', label: '🤔 专注' },
]

// 表情配置
const EXPRESSION_CONFIG: Record<string, { mouthScale: number; eyebrowAngle: number; eyeScale: number }> = {
  neutral: { mouthScale: 0.1, eyebrowAngle: 0, eyeScale: 1.0 },
  happy: { mouthScale: 0.4, eyebrowAngle: -5, eyeScale: 1.0 },
  sad: { mouthScale: 0.05, eyebrowAngle: -15, eyeScale: 0.9 },
  angry: { mouthScale: 0.1, eyebrowAngle: 20, eyeScale: 1.0 },
  surprised: { mouthScale: 0.5, eyebrowAngle: 0, eyeScale: 1.3 },
  loved: { mouthScale: 0.25, eyebrowAngle: -8, eyeScale: 1.1 },
  focused: { mouthScale: 0.1, eyebrowAngle: 0, eyeScale: 0.85 },
}

export const Live2DViewer: React.FC<Live2DViewerProps> = ({
  modelId,
  imageUrl,
  riggingState,
  currentExpression = 'neutral',
  eyeTrackingX = 0,
  eyeTrackingY = 0,
  onExpressionChange,
  onEyeTrackingChange,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animationRef = useRef<number>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 动画状态
  const [blinkLevel, setBlinkLevel] = useState(0)
  const [breathOffset, setBreathOffset] = useState(0)

  // 加载图片
  const loadImage = useCallback(() => {
    return new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('图片加载失败'))
      img.src = imageUrl
    })
  }, [imageUrl])

  // 绘制函数
  const draw = useCallback(async (ctx: CanvasRenderingContext2D, width: number, height: number) => {
    try {
      const img = await loadImage()

      // 清除画布
      ctx.clearRect(0, 0, width, height)

      // 获取表情配置
      const expConfig = EXPRESSION_CONFIG[currentExpression] || EXPRESSION_CONFIG.neutral

      // 保存状态
      ctx.save()

      // 应用呼吸动画
      const breathY = Math.sin(breathOffset) * 2
      ctx.translate(0, breathY)

      // 计算居中
      const scale = Math.min(width / img.width, height / img.height) * 0.8
      const drawWidth = img.width * scale
      const drawHeight = img.height * scale
      const drawX = (width - drawWidth) / 2
      const drawY = (height - drawHeight) / 2

      // 绘制主体
      ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight)

      // 绘制视线跟随指示器（简单圆点）
      if (riggingState) {
        const centerX = drawX + drawWidth * 0.5
        const centerY = drawY + drawHeight * 0.35

        // 视线偏移
        const lookX = eyeTrackingX * 10
        const lookY = eyeTrackingY * 5

        // 绘制左眼指示器
        ctx.beginPath()
        ctx.arc(centerX - drawWidth * 0.12 + lookX, centerY + lookY, 3, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255, 100, 100, 0.8)'
        ctx.fill()

        // 绘制右眼指示器
        ctx.beginPath()
        ctx.arc(centerX + drawWidth * 0.12 + lookX, centerY + lookY, 3, 0, Math.PI * 2)
        ctx.fill()

        // 应用眨眼效果
        if (blinkLevel > 0) {
          ctx.fillStyle = 'rgba(255, 255, 255, 0.3)'
          ctx.fillRect(centerX - drawWidth * 0.18, centerY - 5, drawWidth * 0.36, blinkLevel * 15)
        }

        // 绘制嘴巴指示器（根据表情）
        const mouthY = centerY + drawHeight * 0.18
        ctx.beginPath()
        ctx.ellipse(
          centerX,
          mouthY,
          drawWidth * 0.08 * expConfig.mouthScale * 10,
          drawHeight * 0.03 * expConfig.mouthScale * 10,
          0, 0, Math.PI * 2
        )
        ctx.fillStyle = 'rgba(200, 100, 100, 0.6)'
        ctx.fill()

        // 绘制眉毛指示器
        const eyebrowY = centerY - drawHeight * 0.12
        ctx.strokeStyle = 'rgba(100, 100, 100, 0.5)'
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(centerX - drawWidth * 0.18, eyebrowY)
        ctx.lineTo(centerX - drawWidth * 0.05, eyebrowY - expConfig.eyebrowAngle * 0.5)
        ctx.stroke()
        ctx.beginPath()
        ctx.moveTo(centerX + drawWidth * 0.18, eyebrowY)
        ctx.lineTo(centerX + drawWidth * 0.05, eyebrowY - expConfig.eyebrowAngle * 0.5)
        ctx.stroke()
      }

      // 恢复状态
      ctx.restore()
    } catch (err) {
      console.error('绘制失败:', err)
      setError('绘制失败')
    }
  }, [loadImage, currentExpression, eyeTrackingX, eyeTrackingY, blinkLevel, breathOffset, riggingState])

  // 动画循环
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 设置画布大小
    const resize = () => {
      const rect = container.getBoundingClientRect()
      canvas.width = rect.width
      canvas.height = rect.height
    }
    resize()
    window.addEventListener('resize', resize)

    // 动画状态
    let lastBlinkTime = 0
    let isBlinking = false
    let blinkStart = 0
    const blinkDuration = 150 // ms

    // 呼吸动画
    let breathTime = 0

    const animate = (timestamp: number) => {
      // 更新呼吸动画
      breathTime += 0.02
      setBreathOffset(breathTime)

      // 更新眨眼动画
      if (!isBlinking && timestamp - lastBlinkTime > 3000 + Math.random() * 2000) {
        isBlinking = true
        blinkStart = timestamp
        lastBlinkTime = timestamp
      }

      if (isBlinking) {
        const elapsed = timestamp - blinkStart
        if (elapsed < blinkDuration / 2) {
          setBlinkLevel(elapsed / (blinkDuration / 2))
        } else if (elapsed < blinkDuration) {
          setBlinkLevel(1 - (elapsed - blinkDuration / 2) / (blinkDuration / 2))
        } else {
          setBlinkLevel(0)
          isBlinking = false
        }
      }

      // 绘制
      draw(ctx, canvas.width, canvas.height)

      animationRef.current = requestAnimationFrame(animate)
    }

    setLoading(false)
    animationRef.current = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('resize', resize)
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [draw])

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%' }}>
      {/* 画布区域 */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
          borderRadius: 8,
          position: 'relative',
          minHeight: 300,
        }}
      >
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin size="large" />
          </div>
        )}
        {error && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Text type="danger">{error}</Text>
          </div>
        )}
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: '100%', display: 'block' }}
        />
        <div style={{ position: 'absolute', bottom: 8, right: 8 }}>
          <Space>
            <Text type="secondary" style={{ fontSize: 10 }}>
              {riggingState ? '已绑骨' : '未绑骨'}
            </Text>
          </Space>
        </div>
      </div>

      {/* 控制面板 */}
      <Card size="small" style={{ width: 240 }} title="实时控制">
        {/* 表情选择 */}
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>表情</Text>
          <Select
            value={currentExpression}
            onChange={onExpressionChange}
            style={{ width: '100%', marginTop: 4 }}
            options={EXPRESSIONS}
          />
        </div>

        {/* 视线跟踪 */}
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>视线 X: {eyeTrackingX.toFixed(2)}</Text>
          <Slider
            min={-1}
            max={1}
            step={0.01}
            value={eyeTrackingX}
            onChange={(v) => onEyeTrackingChange?.(v, eyeTrackingY)}
            tooltip={{ formatter: (v) => v?.toFixed(2) }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>视线 Y: {eyeTrackingY.toFixed(2)}</Text>
          <Slider
            min={-1}
            max={1}
            step={0.01}
            value={eyeTrackingY}
            onChange={(v) => onEyeTrackingChange?.(eyeTrackingX, v)}
            tooltip={{ formatter: (v) => v?.toFixed(2) }}
          />
        </div>

        {/* 眨眼状态 */}
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>眨眼状态</Text>
          <div style={{ marginTop: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  background: blinkLevel > 0 ? '#52c41a' : '#d9d9d9',
                  transition: 'background 0.1s',
                }}
              />
              <Text style={{ fontSize: 11 }}>{blinkLevel > 0 ? '眨眼中' : '睁眼'}</Text>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

export default Live2DViewer
