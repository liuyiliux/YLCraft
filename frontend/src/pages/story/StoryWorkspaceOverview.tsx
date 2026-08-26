import React from 'react'
import { Button, Empty, Space, Tag, Tooltip, Typography } from 'antd'
import {
  ArrowRightOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
  PictureOutlined,
} from '@ant-design/icons'
import type { ThemeColors } from '../../constants/theme'

const { Text, Title } = Typography

export type StoryWorkspaceStage = {
  key: string
  tab: string
  label: string
  hint: string
  complete: number
  total: number
}

export type StoryWorkspaceChapter = {
  chapter_number: number
  title?: string
  summary?: string
  status?: string
}

type Props = {
  theme: ThemeColors
  projectTitle: string
  projectType: string
  currentStage: string
  idea?: string
  chapters: StoryWorkspaceChapter[]
  stages: StoryWorkspaceStage[]
  activeChapterNumber: number
  hasOutline: boolean
  hasBible: boolean
  hasChapterPlan: boolean
  assetCount: number
  unresolvedContinuityCount: number
  onOpenSection: (tab: string) => void
  onOpenChapter: (chapterNumber: number, tab?: string) => void
  onContinue: () => void
  productionFamily?: 'narrative' | 'content_package'
  packageType?: string | null
  packageData?: Record<string, any> | null
}

const sectionIcons: Record<string, React.ReactNode> = {
  outline: <ThunderboltOutlined />,
  'project-bible': <BranchesOutlined />,
  chapters: <FileTextOutlined />,
  canvas: <BranchesOutlined />,
  assets: <FolderOpenOutlined />,
}

const packageTypeLabels: Record<string, string> = {
  page_book: '绘本 / 漫画页',
  knowledge_cards: '科普知识卡',
  article_package: '公众号文章包',
  social_carousel: '小红书轮播',
  shot_list: '短视频镜头表',
  single_media: '单图 / 单镜头',
}

function chapterReadiness(chapter: StoryWorkspaceChapter, index: number, activeChapterNumber: number) {
  if (chapter.chapter_number === activeChapterNumber) return { label: '进行中', color: 'processing' }
  if (chapter.status === 'locked' || chapter.status === 'confirmed') return { label: '已确认', color: 'success' }
  if (index > activeChapterNumber) return { label: '待开始', color: 'default' }
  return { label: '待制作', color: 'warning' }
}

export default function StoryWorkspaceOverview({
  theme,
  projectTitle,
  projectType,
  currentStage,
  idea,
  chapters,
  stages,
  activeChapterNumber,
  hasOutline,
  hasBible,
  hasChapterPlan,
  assetCount,
  unresolvedContinuityCount,
  onOpenSection,
  onOpenChapter,
  onContinue,
  productionFamily = 'narrative',
  packageType,
  packageData,
}: Props) {
  const [decisionEvidenceOpen, setDecisionEvidenceOpen] = React.useState(false)
  const isContentPackage = productionFamily === 'content_package'
  const packageItems = Array.isArray(packageData?.items) ? packageData.items : []
  const packageTitle = String(packageData?.title || projectTitle)
  const packageTopic = String(packageData?.topic || idea || '')
  const packageBrief = String(packageData?.brief || '一次生成内容卡片、图片提示词，再按需批量生成媒体。')
  const isKnowledgeCards = packageType === 'knowledge_cards'
  const knowledgeItems = isKnowledgeCards ? packageItems.filter((item: any) => item?.fact || item?.source || item?.source_url) : []
  const packageStatus = packageData?.status === 'failed' ? '上次生成失败，可重新开始' : packageItems.length ? `${packageItems.length} 个内容单元` : '尚未生成内容包'

  if (isContentPackage) {
    return (
      <div className="story-overview" style={{ padding: '22px 22px 8px' }}>
        <section className="story-overview__hero" style={{ borderBottom: `1px solid ${theme.border}`, paddingBottom: 20 }}>
          <div style={{ minWidth: 0 }}>
            <Space size={8} wrap>
              <Tag color="cyan">{packageTypeLabels[packageType || ''] || '内容包'}</Tag>
              <Text type="secondary">轻量工作流</Text>
            </Space>
            <Title level={2} style={{ margin: '9px 0 4px', fontSize: 24 }}>{packageTitle}</Title>
            <Text type="secondary" ellipsis={{ tooltip: packageTopic }} style={{ display: 'block', maxWidth: 760 }}>
              {packageTopic || '输入一个主题，生成可编辑的页面、知识卡或平台内容。'}
            </Text>
          </div>
          <div className="story-overview__resume">
            <div>
              <Text type="secondary">内容包状态</Text>
              <Text strong style={{ display: 'block', marginTop: 3 }}>{packageStatus}</Text>
            </div>
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={onContinue}>
              {packageItems.length ? '继续编辑内容包' : '一次生成内容包'}
            </Button>
          </div>
        </section>

        <section className="story-overview__decision" aria-label="内容包说明">
          <div>
            <Text strong>不需要先写正文或项目圣经</Text>
            <Text type="secondary" style={{ display: 'block', marginTop: 2 }}>{packageBrief}</Text>
          </div>
          <Tag icon={<PictureOutlined />} color="processing">提示词可单独生成图片</Tag>
        </section>

        <section className="story-overview__setup" aria-label="内容包状态">
          {[
            { label: '主题输入', description: packageTopic ? '已提供主题或来源' : '等待主题', ready: Boolean(packageTopic) },
            { label: '内容单元', description: packageItems.length ? `${packageItems.length} 个页面 / 卡片 / 镜头` : '生成后可逐项编辑', ready: packageItems.length > 0 },
            { label: '图片提示词', description: packageItems.some((item: any) => item?.image_prompt) ? '已生成，可批量生图' : '随内容包一起生成', ready: packageItems.some((item: any) => item?.image_prompt) },
            ...(isKnowledgeCards ? [{ label: '事实来源', description: knowledgeItems.length === packageItems.length && packageItems.length > 0 ? '每张卡都有事实或来源' : '仍有卡片缺少事实来源', ready: knowledgeItems.length === packageItems.length && packageItems.length > 0 }] : []),
            { label: '输出适配', description: '可导出素材包或适配平台', ready: Array.isArray(packageData?.outputs) && packageData.outputs.length > 0 },
          ].map((item) => (
            <div key={item.label} className="story-overview__setup-item" style={{ cursor: 'default' }}>
              <span><PictureOutlined /></span>
              <span><Text strong>{item.label}</Text><Text type="secondary">{item.description}</Text></span>
              {item.ready ? <CheckCircleOutlined style={{ color: theme.primary }} /> : <Text type="secondary">待生成</Text>}
            </div>
          ))}
        </section>

        {packageItems.length ? (
          <section className="story-overview__queue" aria-label="内容单元预览">
            <div className="story-overview__queue-header"><Text strong>内容单元</Text><Text type="secondary">每个单元可独立编辑和重试</Text></div>
            {packageItems.slice(0, 8).map((item: any, index: number) => (
              <div key={String(item?.id || item?.item_id || index)} className="story-overview__queue-row" style={{ cursor: 'default' }}>
                <span className="story-overview__chapter-number">{String(item?.index || index + 1).padStart(2, '0')}</span>
                <span className="story-overview__chapter-copy"><Text strong>{item?.title || `内容单元 ${index + 1}`}</Text><Text type="secondary" ellipsis>{item?.text || item?.fact || item?.image_prompt || '尚未填写内容'}</Text></span>
                <Tag color={item?.status === 'failed' ? 'error' : item?.status === 'succeeded' ? 'success' : 'default'}>{item?.status || '草稿'}</Tag>
              </div>
            ))}
          </section>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有内容单元，点击上方按钮开始一次生成" />
        )}
      </div>
    )
  }

  const activeChapter = chapters.find((chapter) => chapter.chapter_number === activeChapterNumber) || chapters[0]
  const nextStage = stages.find((stage) => stage.complete < stage.total) || stages[stages.length - 1]
  const setupItems = [
    { tab: 'outline', label: '故事蓝图', ready: hasOutline, description: '主题、人物与故事主线' },
    { tab: 'project-bible', label: '项目圣经', ready: hasBible, description: '世界规则、风格与长期事实' },
    { tab: 'chapters', label: '章节规划', ready: hasChapterPlan, description: '全书节奏与章节目标' },
    { tab: 'assets', label: '角色与参考', ready: assetCount > 0, description: `${assetCount} 个关联素材` },
  ]

  return (
    <div className="story-overview" style={{ padding: '22px 22px 8px' }}>
      <section className="story-overview__hero" style={{ borderBottom: `1px solid ${theme.border}`, paddingBottom: 20 }}>
        <div style={{ minWidth: 0 }}>
          <Space size={8} wrap>
            <Tag color="processing">{projectType}</Tag>
            <Text type="secondary">{currentStage}</Text>
          </Space>
          <Title level={2} style={{ margin: '9px 0 4px', fontSize: 24 }}>{projectTitle}</Title>
          <Text type="secondary" ellipsis={{ tooltip: idea }} style={{ display: 'block', maxWidth: 760 }}>
            {idea || '先建立故事蓝图，再进入章节制作。'}
          </Text>
        </div>
        <div className="story-overview__resume">
          <div>
            <Text type="secondary">继续制作</Text>
            <Text strong style={{ display: 'block', marginTop: 3 }}>
              {activeChapter ? `第 ${activeChapter.chapter_number} 章${activeChapter.title ? ` · ${activeChapter.title}` : ''}` : '先完成全书章节规划'}
            </Text>
          </div>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={onContinue}>
            {activeChapter ? '进入工作室' : hasOutline ? '规划章节' : '建立蓝图'}
          </Button>
        </div>
      </section>

      <section className="story-overview__decision" aria-label="下一步建议">
        <div>
          <Text strong>下一步</Text>
          <Text type="secondary" style={{ display: 'block', marginTop: 2 }}>
            {nextStage?.complete < nextStage?.total
              ? `${nextStage.label}尚未完成，完成后可继续后续制作。`
              : '全部主要阶段已有产出，可进入单章审校或交付。'}
          </Text>
        </div>
        <Button
          type="link"
          icon={<ArrowRightOutlined />}
          onClick={() => setDecisionEvidenceOpen((open) => !open)}
          aria-expanded={decisionEvidenceOpen}
        >
          {decisionEvidenceOpen ? '收起依据' : '查看依据'}
        </Button>
      </section>

      {decisionEvidenceOpen ? (
        <section className="story-overview__decision-evidence" aria-label="下一步建议依据">
          <Text strong>建议依据</Text>
          <Text type="secondary">
            {nextStage ? `${nextStage.label}当前完成 ${nextStage.complete}/${nextStage.total}。` : '项目主要阶段已具备产出。'}
            {activeChapter ? ` 当前工作章节为第 ${activeChapter.chapter_number} 章。` : ' 章节规划尚未建立。'}
            {unresolvedContinuityCount ? ` 另有 ${unresolvedContinuityCount} 项连续性事项待确认。` : ''}
          </Text>
        </section>
      ) : null}

      {unresolvedContinuityCount > 0 ? (
        <section className="story-overview__continuity" style={{ borderColor: theme.warning || '#d89614' }}>
          <Text strong>有 {unresolvedContinuityCount} 项连续性事项待确认</Text>
          <Button size="small" type="link" onClick={() => onOpenChapter(activeChapterNumber, 'writer-room')}>进入审校</Button>
        </section>
      ) : null}

      <section className="story-overview__setup" aria-label="项目资料">
        {setupItems.map((item) => (
          <button key={item.tab} type="button" className="story-overview__setup-item" onClick={() => onOpenSection(item.tab)}>
            <span>{sectionIcons[item.tab]}</span>
            <span><Text strong>{item.label}</Text><Text type="secondary">{item.description}</Text></span>
            {item.ready ? <CheckCircleOutlined style={{ color: theme.primary }} /> : <Text type="secondary">待补充</Text>}
          </button>
        ))}
      </section>

      <section className="story-overview__queue" aria-label="章节生产队列">
        <div className="story-overview__queue-header"><Text strong>章节生产队列</Text><Text type="secondary">点击进入单章工作室</Text></div>
        {chapters.length ? chapters.map((chapter, index) => {
          const readiness = chapterReadiness(chapter, index, activeChapterNumber)
          return (
            <button key={chapter.chapter_number} type="button" className="story-overview__queue-row" onClick={() => onOpenChapter(chapter.chapter_number)}>
              <span className="story-overview__chapter-number">{String(chapter.chapter_number).padStart(2, '0')}</span>
              <span className="story-overview__chapter-copy"><Text strong>{chapter.title || `第 ${chapter.chapter_number} 章`}</Text><Text type="secondary" ellipsis>{chapter.summary || '尚未填写本章目标'}</Text></span>
              <Tooltip title={readiness.label}><Tag color={readiness.color}>{readiness.label}</Tag></Tooltip>
              <ArrowRightOutlined />
            </button>
          )
        }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先建立章节规划，生产队列会在这里出现" />}
      </section>
    </div>
  )
}
