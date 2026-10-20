/**
 * 动图工作台（`/motion`）。
 *
 * **为什么独立成页**：切帧 + 合成是**与生成无关**的能力 ——
 * 后端 `slice-preview` / `compose` 都不需要动效类型，也不需要"刚生成过"。
 * 实测确认四类动效只差提示词里的一个段落（`task`/`continuity`/`locked`/`output`
 * 四类完全相同），也就是说 **动效类型属于"生成"，不属于"切图"**。
 *
 * 把这套东西挂在生图页里，结果是两边都变脏：生图页 2874 行、动图逻辑散在 14 处，
 * 而"想重切一张早就生成好的图"还要先绕去生图页。
 * 拆开之后：**生图页只管生成，这里只管加工**。
 *
 * **这里没有动效类型** —— 不是漏了，是它确实用不上（见上）。
 *
 * **不花钱**：切帧、拖分割线、每帧调色、合成，全部是本地像素处理，
 * 不调用任何模型。只有"去生图页生成新图"才花钱，那是另一个页面的事。
 */

import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Alert, Button, Empty, Segmented, Space, Tag, Tooltip, Typography } from 'antd'
import {
  DownloadOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { MotionSheetSourcePanel } from '../../components/motion-gif/MotionSheetSourcePanel'
import { MotionGifSlicePanel } from '../../components/motion-gif/MotionGifSlicePanel'
import { useMotionGifWorkflow, MOTION_OUTPUT_SIZE } from '../../components/motion-gif/useMotionGifWorkflow'
import { downloadAssetFile, assetPreviewUrl } from '../../utils/downloadAsset'

const { Text, Title } = Typography

/** 步骤指示 —— 让"我在第几步"一眼可见，而不是靠猜。 */
function StepBar({ current }: { current: number }) {
  const { theme: THEME } = useTheme()
  const steps = ['选图', '切帧', '合成']
  return (
    <Space size={4} wrap>
      {steps.map((label, i) => {
        const active = i === current
        const done = i < current
        return (
          <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 18,
                height: 18,
                borderRadius: '50%',
                fontSize: 11,
                fontWeight: 600,
                background: active || done ? THEME.primary : 'transparent',
                color: active || done ? '#fff' : THEME.textSecondary,
                border: `1px solid ${active || done ? THEME.primary : THEME.borderLight}`,
              }}
            >
              {i + 1}
            </span>
            <span
              style={{
                fontSize: 12,
                color: active ? THEME.textPrimary : THEME.textSecondary,
                fontWeight: active ? 600 : 400,
              }}
            >
              {label}
            </span>
            {i < steps.length - 1 && (
              <span style={{ color: THEME.borderLight, margin: '0 4px' }}>/</span>
            )}
          </span>
        )
      })}
    </Space>
  )
}

export default function MotionPage() {
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()
  const projectId = searchParams.get('project_id') || ''
  const contentId = searchParams.get('content_id') || ''
  const prompt = searchParams.get('prompt') || ''

  const motion = useMotionGifWorkflow({
    prompt,
    projectId,
    contentId,
    returnTo: '/motion',
  })

  const hasSheet = Boolean(motion.sheetPath)
  const hasFrames = motion.order.length > 0
  const step = motion.output ? 2 : hasFrames ? 1 : 0

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '20px 24px 64px' }}>
      {/* 顶部：标题 + 步骤 + 主操作。主操作放右上角，不再埋到页面底部。 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 16,
          flexWrap: 'wrap',
          marginBottom: 4,
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0, color: THEME.textPrimary }}>
            动图工作台
          </Title>
          <Text style={{ fontSize: 12.5, color: THEME.textSecondary }}>
            把一张多格图切成帧、拼成 GIF / WebP / MP4。全程本地处理，不调用模型。
          </Text>
        </div>
        <Space>
          {motion.output && (
            <>
              <Button
                icon={<DownloadOutlined />}
                onClick={() =>
                  downloadAssetFile(motion.output!.gif_path, 'animation.gif', motion.output!.revision)
                }
              >
                GIF
              </Button>
              {motion.output.webp_path && (
                <Button
                  icon={<DownloadOutlined />}
                  onClick={() =>
                    downloadAssetFile(motion.output!.webp_path, 'animation.webp', motion.output!.revision)
                  }
                >
                  WebP
                </Button>
              )}
              <Button
                type="primary"
                icon={<InboxOutlined />}
                loading={motion.saving}
                onClick={motion.save}
              >
                存入素材库
              </Button>
            </>
          )}
        </Space>
      </div>

      <div style={{ margin: '10px 0 18px' }}>
        <StepBar current={step} />
      </div>

      {/* ① 选图 —— 只留"素材库 / 上传"两个入口。生成归生图页，这里不做。 */}
      <section style={{ marginBottom: 22 }}>
        <MotionSheetSourcePanel
          sheetPath={motion.sheetPath}
          onSheetChange={motion.chooseSheet}
          rows={motion.activeShape.rows}
          cols={motion.activeShape.cols}
          onShapeChange={motion.changeShape}
        />
      </section>

      {!hasSheet ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span style={{ fontSize: 12.5, color: THEME.textSecondary }}>
              先选一张多格图。没有？去
              <a href="/image-gen" style={{ margin: '0 3px' }}>
                AI 图片
              </a>
              生成，或直接从素材库选现成的。
            </span>
          }
          style={{ marginTop: 40 }}
        />
      ) : (
        <>
          {/* ② 切帧（含手动切格 / 每帧微调） */}
          <section style={{ marginBottom: 18 }}>
            <MotionGifSlicePanel
              cells={motion.activeShape.rows * motion.activeShape.cols}
              cols={motion.activeShape.cols}
              order={motion.order}
              onOrderChange={motion.setOrder}
              frameUrls={motion.frameUrls}
              loop={motion.loop}
              onLoopChange={motion.setLoop}
              loopOptions={motion.loopOptions}
              alignSubject={motion.alignSubject}
              onAlignSubjectChange={motion.setAlignSubject}
              trim={motion.trim}
              onTrimChange={motion.setTrim}
              composed={Boolean(motion.output)}
              composing={motion.composing}
              onCompose={motion.compose}
              disabled={!hasFrames}
              sheetUrl={motion.sheetPreview}
              rows={motion.activeShape.rows}
              gridEdges={motion.gridEdges}
              onGridEdgesChange={motion.setGridEdges}
              onOpenEditor={motion.openFrameInEditor}
            />
          </section>

          {/* ③ 成品 */}
          {motion.output && (
            <section
              style={{
                borderTop: `1px solid ${THEME.borderLight}`,
                paddingTop: 16,
              }}
            >
              <Space
                style={{ width: '100%', justifyContent: 'space-between', marginBottom: 10 }}
                align="center"
              >
                <Space size={6}>
                  <Text strong style={{ fontSize: 13 }}>
                    成品
                  </Text>
                  <Tag style={{ margin: 0 }}>{motion.output.frames} 帧</Tag>
                  <Tag style={{ margin: 0 }}>{MOTION_OUTPUT_SIZE}px 长边</Tag>
                </Space>
                <Text style={{ fontSize: 11.5, color: THEME.textSecondary }}>
                  {motion.versionNumber > 1 ? `素材库 v${motion.versionNumber}` : ''}
                </Text>
              </Space>

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  padding: 12,
                  background: THEME.bgElevated,
                  borderRadius: THEME.radiusSM,
                }}
              >
                {motion.output.gif_path && (
                  <img
                    /*
                     * `?v=<revision>`：产物是**原地覆写**同一个 animation.gif，
                     * 不带版本指纹的话，改了循环方式重新合成，预览还是旧图
                     * （用户实测："我修改循环或者改了帧重新合成，预览这里没变"）。
                     */
                    src={assetPreviewUrl(motion.output.gif_path, motion.output.revision)}
                    alt="动图成品预览"
                    style={{ maxWidth: '100%', maxHeight: 360, display: 'block' }}
                  />
                )}
              </div>

              {/* 体积对比：GIF 与 WebP 放一行，用户一眼看出该用哪个 */}
              <div
                style={{
                  display: 'flex',
                  gap: 16,
                  marginTop: 10,
                  fontSize: 12,
                  color: THEME.textSecondary,
                  flexWrap: 'wrap',
                }}
              >
                <span>
                  GIF <b style={{ color: THEME.textPrimary }}>{Math.round(motion.output.gif_kb)} KB</b>
                  <span style={{ marginLeft: 4 }}>微信、详情页通用</span>
                </span>
                {motion.output.webp_path && (
                  <span>
                    WebP <b style={{ color: THEME.textPrimary }}>{Math.round(motion.output.webp_kb)} KB</b>
                    <span style={{ marginLeft: 4 }}>更小更清晰，推荐</span>
                  </span>
                )}
              </div>

              <Space style={{ marginTop: 12 }}>
                <Button icon={<ReloadOutlined />} onClick={motion.compose} loading={motion.composing}>
                  重新合成
                </Button>
                <Text style={{ fontSize: 11.5, color: THEME.textSecondary }}>
                  改完切法再合成一次，不花钱
                </Text>
              </Space>
            </section>
          )}
        </>
      )}
    </div>
  )
}
