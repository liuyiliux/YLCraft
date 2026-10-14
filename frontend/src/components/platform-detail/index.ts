/**
 * 多平台内容详情/媒体展示的**公共组件**（非 B站）。
 *
 * ## 谁用
 *
 *   · 「查询」页（内容搜索）—— 后续替换它自带的 1237 行详情抽屉
 *   · 「我的数据」我的作品 / 我的点赞
 *
 * ## ⚠️ B站不在这里
 *
 * B站有弹幕/字幕/评论/分P 等专属能力，走
 * `components/bilibili/VideoDetailDrawer`，**是单独一套**。
 * 用户明确说过："b站是单独做的和其他平台不一样"。
 */
export { default as PlatformDetailDrawer } from './PlatformDetailDrawer'
export { default as PlatformMediaView, proxyImage, proxyVideo, resolveMedia } from './PlatformMediaView'
export { default as CommentPanel } from './CommentPanel'
