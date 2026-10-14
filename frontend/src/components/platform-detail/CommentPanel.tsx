/**
 * 评论列表（详情抽屉的「评论」页签）。
 *
 * ## 为什么单独一个文件
 *
 * 评论有自己的 加载 / 分页 / 501 / 429 三套状态，塞进抽屉会让
 * 那个文件难读。这里封装成一个自治组件，抽屉只负责挂上去。
 *
 * ## ⚠️ 三个状态必须**分开**显示（照「查询」页的做法）
 *
 * 用户看到的东西完全不同，混成一个"加载失败"等于什么都没说：
 *
 * | 状态 | 含义 | 用户能做什么 |
 * |------|------|------------|
 * | **空** | 真的没有评论 | 无（就是没人评论） |
 * | **501** | 平台**没实现**评论采集 | 无（换平台也没用） |
 * | **429** | 平台**拒绝了**（风控/人机验证） | **等一等 / 换网络有救** |
 *
 * 把 501 和 429 都写成"暂无评论"或"加载失败"，是本仓库
 * 明确记录过的坑（见 crawler 的注释）—— 会让用户以为永久失效，
 * 或者以为这条内容没人评论。
 *
 * ## ⚠️ 后端给的原因要**完整显示**
 *
 * 501/429 时后端返回的 `detail` 里写着**实测结论 + 具体做法**，
 * 那是用户唯一能做的事。所以要在面板里**原样铺开**，
 * 不能只 `message.error` 弹 3 秒就没了。
 */
import { useState, useEffect, useCallback } from 'react'
import { Space, Typography, Button, Avatar, Empty, Spin, Tag, message } from 'antd'
import {
  MessageOutlined, WarningOutlined, ReloadOutlined, LikeOutlined, UserOutlined,
} from '@ant-design/icons'
import { getComments } from '../../api'
import { useTheme } from '../../constants/theme'
import { formatNum, formatTime } from '../../utils/format'

const { Text } = Typography

export interface CommentPanelProps {
  platform: string
  itemId: string
  /** 可选：连接 id（B站等需要指定用哪个账号取）。 */
  connId?: string
  /**
   * **原帖显示的评论数**（X 的 `comments` 字段）。
   *
   * ⚠️ 这个数常常**大于**我们实际能取到的条数（X 只下发一批）——
   * 两者不一致时面板会**主动说明原因**，免得用户以为我们漏抓了。
   */
  expectedCount?: number
  /** 可选：打开原帖（子回复取不到时给用户一个出口）。 */
  onOpenOriginal?: () => void
}

export default function CommentPanel({
  platform, itemId, connId, expectedCount = 0, onOpenOriginal,
}: CommentPanelProps) {
  const { theme: THEME } = useTheme()

  const [comments, setComments] = useState<Array<Record<string, any>>>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  // 平台没实现（501）—— 显示后端给的原因
  const [unsupported, setUnsupported] = useState('')
  // 平台拒绝（429 / 风控）—— 显示原因 + 可重试
  const [blocked, setBlocked] = useState('')
  // 其他错误
  const [failed, setFailed] = useState('')

  const load = useCallback(
    async (targetPage: number) => {
      setLoading(true)
      try {
        const res: any = await getComments({
          platform,
          item_id: itemId,
          page: targetPage,
          page_size: 20,
          conn_id: connId,
        })
        if (res?.success) {
          const list = res.data?.comments || []
          setComments((prev) => (targetPage === 1 ? list : [...prev, ...list]))
          setTotal(res.data?.total || 0)
          setHasMore(Boolean(res.data?.has_more))
          // ⚠️ 成功后要清掉 501/429 状态 —— 否则风控解除了、
          //    评论也取到了，面板还挂着上次那句"平台侧拒绝"。
          setUnsupported('')
          setBlocked('')
          setFailed('')
          setPage(targetPage)
        } else {
          setFailed(String(res?.detail || res?.message || '获取评论失败'))
          if (targetPage === 1) setComments([])
        }
      } catch (err: any) {
        // ⚠️ 按状态码分流，**不要**都当成"加载失败"
        const status = err?.response?.status
        const detail = String(err?.response?.data?.detail || '')
        if (status === 501) {
          setBlocked('')
          setFailed('')
          setUnsupported(detail || '该平台暂不支持评论采集')
          setComments([])
        } else if (status === 429) {
          setUnsupported('')
          setFailed('')
          setBlocked(detail || '平台侧拒绝了这次请求（风控/人机验证），请稍后重试或更换网络')
        } else {
          setUnsupported('')
          setBlocked('')
          setFailed(detail || err?.message || '获取评论失败')
          message.error('获取评论失败')
        }
      } finally {
        setLoading(false)
        setLoaded(true)
      }
    },
    [platform, itemId, connId],
  )

  // 换内容时重置并拉第一页
  useEffect(() => {
    setComments([])
    setTotal(0)
    setPage(1)
    setHasMore(false)
    setLoaded(false)
    setUnsupported('')
    setBlocked('')
    setFailed('')
    if (itemId) void load(1)
  }, [itemId, load])

  // ---- 501：平台没实现 ----
  if (unsupported) {
    return (
      <div style={{ textAlign: 'center', padding: '28px 16px' }}>
        <MessageOutlined style={{ fontSize: 40, color: THEME.textSecondary, opacity: 0.4 }} />
        <div style={{ marginTop: 12, color: THEME.textPrimary, fontWeight: 600, fontSize: 14 }}>
          该平台暂不支持评论采集
        </div>
        <div style={{
          marginTop: 8, color: THEME.textSecondary, fontSize: 12, lineHeight: 1.6,
          whiteSpace: 'pre-wrap', maxWidth: 460, margin: '8px auto 0',
        }}>
          {unsupported}
        </div>
      </div>
    )
  }

  // ---- 429：平台拒绝（可重试）----
  if (blocked) {
    return (
      <div style={{ textAlign: 'center', padding: '28px 16px' }}>
        <WarningOutlined style={{ fontSize: 40, color: '#faad14', opacity: 0.75 }} />
        <div style={{ marginTop: 12, color: THEME.textPrimary, fontWeight: 600, fontSize: 14 }}>
          平台侧拒绝了这次请求
        </div>
        <div style={{
          marginTop: 8, color: THEME.textSecondary, fontSize: 12, lineHeight: 1.7,
          whiteSpace: 'pre-wrap', textAlign: 'left', maxWidth: 520,
          margin: '8px auto 0', background: 'rgba(250,173,20,0.06)',
          border: '1px solid rgba(250,173,20,0.25)',
          borderRadius: 6, padding: '10px 12px',
        }}>
          {blocked}
        </div>
        <div style={{ marginTop: 10 }}>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => load(1)}>
            重新加载
          </Button>
        </div>
      </div>
    )
  }

  if (loading && comments.length === 0) {
    return <div style={{ textAlign: 'center', padding: 30 }}><Spin /></div>
  }

  if (failed && comments.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '28px 16px' }}>
        <WarningOutlined style={{ fontSize: 36, color: '#ef4444', opacity: 0.7 }} />
        <div style={{ marginTop: 12, color: THEME.textPrimary, fontSize: 13 }}>
          {failed}
        </div>
        <div style={{ marginTop: 10 }}>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => load(1)}>
            重试
          </Button>
        </div>
      </div>
    )
  }

  if (loaded && comments.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
            这条内容还没有评论
          </Text>
        }
      />
    )
  }

  return (
    <div>
      {total > 0 && (
        <div style={{ marginBottom: 10 }}>
          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
            共 {formatNum(total)} 条评论
          </Text>
          {/* ⚠️ **如实说明"为什么对不上"**（2026-10-11 加）
          
              用户会看到：X 上写着「评论 41」，这里却只有 19 条。
              实测确认（tweet 2109218616248070654）：
              
                · X 的 TweetDetail **第一页就没有游标了**（`cursor=无`）——
                  即它**只下发这一批**，翻页翻不出更多
                · X 的计数（41）包含**二级回复**和它未下发的部分
              
              不解释的话，用户会以为**我们漏抓了**（这是我们最该避免的误解）。
              所以这里主动说明，并给「打开原文」这个出口。 */}
          {expectedCount > comments.length && (
            <div style={{ marginTop: 4 }}>
              <Text style={{ fontSize: 11, color: THEME.textSecondary }}>
                原帖显示 {formatNum(expectedCount)} 条，实际取到 {formatNum(comments.length)} 条
                —— X 只下发这一批（其余为二级回复或未公开）
              </Text>
              {onOpenOriginal && (
                <Text
                  onClick={onOpenOriginal}
                  style={{ fontSize: 11, marginLeft: 6, color: THEME.primary, cursor: 'pointer' }}
                >
                  去原站看
                </Text>
              )}
            </div>
          )}
        </div>
      )}

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {comments.map((c, i) => (
          <div
            key={String(c.id || i)}
            style={{
              display: 'flex', gap: 10, paddingBottom: 10,
              borderBottom: `1px solid ${THEME.border}`,
            }}
          >
            <Avatar
              size={32}
              src={c.avatar
                ? `/api/v1/proxy/image?url=${encodeURIComponent(c.avatar)}`
                : undefined}
              icon={<UserOutlined />}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <Space size={8} wrap>
                <Text strong style={{ fontSize: 13, color: THEME.textPrimary }}>
                  {c.author || '匿名'}
                </Text>
                {c.author_handle && (
                  <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                    @{String(c.author_handle).replace(/^@/, '')}
                  </Text>
                )}
                {c.create_time && (
                  <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                    {formatTime(c.create_time, platform)}
                  </Text>
                )}
              </Space>
              <div style={{
                marginTop: 4, fontSize: 13, color: THEME.textPrimary,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {c.content || '(无内容)'}
              </div>
              {/* 评论图片（X 的评论可能带图） */}
              {Array.isArray(c.images) && c.images.length > 0 && (
                <Space size={6} style={{ marginTop: 6 }} wrap>
                  {c.images.slice(0, 4).map((u: string, k: number) => (
                    <img
                      key={k}
                      src={`/api/v1/proxy/image?url=${encodeURIComponent(u)}&w=200`}
                      alt=""
                      style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 4 }}
                    />
                  ))}
                </Space>
              )}
              <Space size={10} style={{ marginTop: 4 }}>
                {Number(c.likes) > 0 && (
                  <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                    <LikeOutlined /> {formatNum(c.likes)}
                  </Text>
                )}
                {/* 「N 条回复」—— **点得开**（2026-10-11 加）
                    ⚠️ 以前只是个静态标签，用户反馈"点不进去"。
                       现在点它按 parent_id 拉子回复。

                    ⚠️ 探到 0 条也要说话（见 SubReplies 里的说明）：
                       X **不保证**把二级回复下发给我们 —— 实测
                       `reply_count=2` 的父评论只拿到 1 条，
                       `reply_count=1` 的两条**一条都拿不到**。 */}
                {Number(c.reply_count) > 0 && (
                  <SubReplies
                    platform={platform}
                    itemId={itemId}
                    commentId={String(c.id)}
                    count={Number(c.reply_count)}
                  />
                )}
              </Space>
            </div>
          </div>
        ))}
      </Space>

      {hasMore && (
        <div style={{ marginTop: 12, textAlign: 'center' }}>
          <Button
            size="small"
            loading={loading}
            onClick={() => load(page + 1)}
          >
            加载更多
          </Button>
        </div>
      )}

      {!hasMore && comments.length > 0 && (
        <div style={{ marginTop: 12, textAlign: 'center' }}>
          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>已到底</Text>
        </div>
      )}
    </div>
  )
}

/**
 * 「N 条回复」—— 点开看子回复。
 *
 * ## ⚠️ 必须处理「点了但一条都没有」的情况（实测会真的发生）
 *
 * X **不保证**把二级回复下发给我们。实测（tweet 2109218616248070654）：
 *
 * ```text
 *   reply_count=2  → 拿到 1 条
 *   reply_count=1  → 拿到 0 条
 *   reply_count=1  → 拿到 0 条
 * ```
 *
 * 所以**不能**只写"加载中 → 空白"：那看起来像**我们坏了**。
 * 要如实说"X 没有下发这些回复"——这是平台限制，不是功能故障。
 *
 * ⚠️ 也不会自动去 x.com 页面抓（那是另一条路，成本高），
 *    所以文案里给一个"去原站看"的出口。
 */
function SubReplies({
  platform, itemId, commentId, count,
}: {
  platform: string
  itemId: string
  commentId: string
  count: number
}) {
  const { theme: THEME } = useTheme()
  const [open, setOpen] = useState(false)
  const [list, setList] = useState<Array<Record<string, any>>>([])
  const [loading, setLoading] = useState(false)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [error, setError] = useState('')

  const toggle = async () => {
    // 收起
    if (open) {
      setOpen(false)
      return
    }
    setOpen(true)
    // 已经取过就不再请求（避免反复点反复打接口）
    if (loadedOnce || loading) return
    setLoading(true)
    setError('')
    try {
      const res: any = await getComments({
        platform,
        item_id: itemId,
        parent_id: commentId,
        page: 1,
        page_size: 50,
      })
      setList((res?.data?.comments || []) as Array<Record<string, any>>)
      setLoadedOnce(true)
    } catch (e: any) {
      const status = e?.response?.status
      const detail = String(e?.response?.data?.detail || '')
      // 501/429 与主列表同样要**分开说**
      if (status === 501) setError(detail || '该平台暂不支持子回复采集')
      else if (status === 429) setError(detail || '平台侧拒绝了这次请求，稍后再试')
      else setError(detail || e?.message || '子回复获取失败')
      setLoadedOnce(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Text
        onClick={toggle}
        style={{
          fontSize: 12, cursor: 'pointer',
          color: open ? THEME.primary : THEME.textSecondary,
        }}
      >
        {formatNum(count)} 条回复 {open ? '▾' : '▸'}
      </Text>

      {open && (
        <div style={{
          marginTop: 8, paddingLeft: 10, width: '100%',
          borderLeft: `2px solid ${THEME.border}`,
        }}>
          {loading && (
            <Text style={{ fontSize: 12, color: THEME.textSecondary }}>加载中…</Text>
          )}

          {!loading && error && (
            <Text style={{ fontSize: 12, color: '#faad14' }}>{error}</Text>
          )}

          {!loading && !error && list.length === 0 && loadedOnce && (
            // ⚠️ 如实说明：不是"没有回复"，是**平台没下发**
            <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
              X 没有提供这些回复（平台限制）—— 可点「打开原文」去原站查看
            </Text>
          )}

          {!loading && list.map((s, i) => (
            <div key={String(s.id || i)} style={{ marginTop: 8 }}>
              <Space size={8} wrap>
                <Text strong style={{ fontSize: 12, color: THEME.textPrimary }}>
                  {s.author || '匿名'}
                </Text>
                {s.author_handle && (
                  <Text style={{ fontSize: 11, color: THEME.textSecondary }}>
                    @{String(s.author_handle).replace(/^@/, '')}
                  </Text>
                )}
                {Number(s.likes) > 0 && (
                  <Text style={{ fontSize: 11, color: THEME.textSecondary }}>
                    <LikeOutlined /> {formatNum(s.likes)}
                  </Text>
                )}
              </Space>
              <div style={{
                fontSize: 12, color: THEME.textPrimary, marginTop: 2,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {s.content || '(无内容)'}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
