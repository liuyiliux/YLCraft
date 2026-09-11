/**
 * 创作项目工作台：components/storyboard.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { InlineImageResult } from './storyboard-parts'
import { comicPreviewGridStyle, comicPreviewPageStyle, panelStyle, readerLayoutStyle, readerPanelStyle, readerTextStyle, readerTocButtonActiveStyle, readerTocButtonStyle, readerTocListStyle, readerTocStyle } from '../styles'
import { ImagePromptContext, InlineGeneratedImage, ProjectContent } from '../types'
import { buildNovelChapterMarkdown, compactNovelReaderText, downloadTextFile, imageContextKey, latestProjectContentsByChapter, sortProjectContentsForReading, textForNovelBody } from '../utils'
import { CopyOutlined } from '@ant-design/icons'
import { Button, Empty, Space, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'

const { Text, Title, Paragraph } = Typography

export function ScriptTab({
  novelBodies,
  comicPages,
  chapterPlan,
  onSendImagePrompt,
  inlineImages,
  inlineImageLoadingKey,
  projectTitle = '',
}: {
  novelBodies: ProjectContent[]
  comicPages: ProjectContent[]
  chapterPlan?: any
  onSendImagePrompt: (prompt: string, context?: ImagePromptContext) => void
  inlineImages: Record<string, InlineGeneratedImage>
  inlineImageLoadingKey: string | null
  projectTitle?: string
}) {
  const sortedNovelBodies = useMemo(() => latestProjectContentsByChapter(novelBodies), [novelBodies])
  const sortedComicPages = useMemo(() => sortProjectContentsForReading(comicPages), [comicPages])
  const [activeReaderId, setActiveReaderId] = useState<string>('')
  const renderInlineImage = (context: ImagePromptContext) => {
    const key = imageContextKey(context)
    return <InlineImageResult image={inlineImages[key]} loading={inlineImageLoadingKey === key} />
  }
  const activeReaderBody =
    sortedNovelBodies.find((body) => body.id === activeReaderId) ||
    sortedNovelBodies[0]
  const activeReaderIndex = activeReaderBody
    ? sortedNovelBodies.findIndex((body) => body.id === activeReaderBody.id)
    : -1
  const plannedChapterCount = Number(chapterPlan?.chapter_count || 0)
  const actualPlanChapterCount = Array.isArray(chapterPlan?.chapters) ? chapterPlan.chapters.length : 0
  const allNovelMarkdown = sortedNovelBodies.map(buildNovelChapterMarkdown).join('\n\n')
  // 文件名优先使用当前项目名（从父组件传下来），去除文件名非法字符
  const safeProjectTitle = (projectTitle || '').trim().replace(/[\\/:*?"<>|]/g, '_')
  const exportTitle = safeProjectTitle || (sortedNovelBodies[0]?.title ? 'creative-project-novel' : 'novel')

  useEffect(() => {
    if (!sortedNovelBodies.length) {
      setActiveReaderId('')
      return
    }
    if (!sortedNovelBodies.some((body) => body.id === activeReaderId)) {
      setActiveReaderId(sortedNovelBodies[0].id)
    }
  }, [activeReaderId, sortedNovelBodies])

  if (!sortedNovelBodies.length && !comicPages.length) {
    return (
      <Space direction="vertical" size={12} style={{ width: '100%', alignItems: 'center', padding: 40 }}>
        <Empty description="还没有可阅读的正文或漫画页，请先在单话工作台生成正文/漫画页" />
      </Space>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Tabs
        items={[
          {
            key: 'reader',
            label: `正文阅读 ${sortedNovelBodies.length ? `(${sortedNovelBodies.length})` : ''}`,
            children: sortedNovelBodies.length ? (
              <div style={readerLayoutStyle}>
                <aside style={readerTocStyle}>
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Text strong>章节目录</Text>
                      <Tag color="green">{sortedNovelBodies.length} 章正文</Tag>
                    </Space>
                    {plannedChapterCount && plannedChapterCount !== actualPlanChapterCount ? (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        规划标记 {plannedChapterCount} 章，实际规划 {actualPlanChapterCount || sortedNovelBodies.length} 章。
                      </Text>
                    ) : null}
                    <div style={readerTocListStyle}>
                      {sortedNovelBodies.map((body) => {
                        const isActive = body.id === activeReaderBody?.id
                        const chapterNumber = body.chapter_number || body.episode_number || '-'
                        return (
                          <button
                            key={body.id}
                            type="button"
                            onClick={() => setActiveReaderId(body.id)}
                            style={{
                              ...readerTocButtonStyle,
                              ...(isActive ? readerTocButtonActiveStyle : null),
                            }}
                            title={body.title}
                          >
                            <span>第 {chapterNumber} 章</span>
                            <strong>{body.title}</strong>
                          </button>
                        )
                      })}
                    </div>
                    <Button
                      block
                      onClick={() => downloadTextFile(`${exportTitle}.md`, allNovelMarkdown)}
                    >
                      导出全文
                    </Button>
                  </Space>
                </aside>
                <article style={readerPanelStyle}>
                  {activeReaderBody ? (
                    <Space direction="vertical" size={14} style={{ width: '100%' }}>
                      <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                        <div>
                          <Title level={4} style={{ margin: 0 }}>
                            {activeReaderBody.title}
                          </Title>
                          <Text type="secondary">
                            第 {activeReaderBody.chapter_number || '-'} 章 · v{activeReaderBody.version} · {textForNovelBody(activeReaderBody).length} 字
                          </Text>
                        </div>
                        <Space wrap>
                          <Button
                            disabled={activeReaderIndex <= 0}
                            onClick={() => setActiveReaderId(sortedNovelBodies[activeReaderIndex - 1]?.id)}
                          >
                            上一章
                          </Button>
                          <Button
                            disabled={activeReaderIndex < 0 || activeReaderIndex >= sortedNovelBodies.length - 1}
                            onClick={() => setActiveReaderId(sortedNovelBodies[activeReaderIndex + 1]?.id)}
                          >
                            下一章
                          </Button>
                          <Button
                            onClick={() =>
                              downloadTextFile(
                                `chapter-${activeReaderBody.chapter_number || activeReaderIndex + 1}.md`,
                                buildNovelChapterMarkdown(activeReaderBody),
                              )
                            }
                          >
                            导出本章
                          </Button>
                          <Tooltip title="复制当前章节正文">
                            <Button
                              icon={<CopyOutlined />}
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(compactNovelReaderText(textForNovelBody(activeReaderBody)))
                                  message.success('本章正文已复制')
                                } catch {
                                  message.error('复制失败，请检查浏览器剪贴板权限')
                                }
                              }}
                            >
                              复制本章
                            </Button>
                          </Tooltip>
                        </Space>
                      </Space>
                      <Paragraph style={readerTextStyle}>{compactNovelReaderText(textForNovelBody(activeReaderBody))}</Paragraph>
                    </Space>
                  ) : (
                    <Empty description="还没有正文，请先在单话工作台生成正文" />
                  )}
                </article>
              </div>
            ) : (
              <Empty description="还没有正文，请先在单话工作台生成正文" />
            ),
          },
          {
            key: 'comic',
            label: `漫画预览 ${comicPages.length ? `(${comicPages.length})` : ''}`,
            children: comicPages.length ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {sortedComicPages.map((comic) => (
                  <div key={comic.id} style={panelStyle}>
                    <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }} align="start">
                      <div>
                        <Text strong>{comic.title}</Text>
                        <div>
                          <Text type="secondary">
                            第 {comic.chapter_number || '-'} 章 · {comic.data?.page_count || comic.data?.pages?.length || 0} 页 · v{comic.version}
                          </Text>
                        </div>
                      </div>
                    </Space>
                    <div style={comicPreviewGridStyle}>
                      {(comic.data?.pages || []).map((page: any, index: number) => (
                        <div key={page.page_number} style={comicPreviewPageStyle}>
                          <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                            <Text strong>第 {page.page_number} 页</Text>
                            {page.image_prompt && (
                              <Button
                                size="small"
                                onClick={() =>
                                  onSendImagePrompt(page.image_prompt, {
                                    contentId: comic.id,
                                    sourceType: 'comic_page',
                                    sourceIndex: page.page_number || index + 1,
                                    sourceTitle: page.title || `第 ${index + 1} 页`,
                                    chapterNumber: comic.chapter_number,
                                    referenceAssetIds: page.reference_asset_ids || [],
                                    characterIds: page.character_ids || [],
                                    portraitNodeIds: page.portrait_node_ids || [],
                                    portraitVersionIds: page.portrait_version_ids || [],
                                  })
                                }
                              >
                                生图
                              </Button>
                            )}
                          </Space>
                          {page.title ? <Text type="secondary">{page.title}</Text> : null}
                          <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>
                            {page.content}
                          </Paragraph>
                          {renderInlineImage({
                            contentId: comic.id,
                            sourceType: 'comic_page',
                            sourceIndex: page.page_number || index + 1,
                            chapterNumber: comic.chapter_number,
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </Space>
            ) : (
              <Empty description="还没有漫画页，请先在单话工作台生成漫画页" />
            ),
          },
        ]}
      />
    </Space>
  )
}

