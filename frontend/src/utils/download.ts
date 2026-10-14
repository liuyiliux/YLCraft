/**
 * 浏览器端文件下载的共享工具。
 *
 * `downloadTextFile` 原先定义在 `pages/story/utils.ts`，但它与 Story 页面毫无关系——
 * 内容包平台输出的「导出 JSON」「下载素材包文件」都要用它。共享组件不应反向依赖页面模块
 * （`components/* → pages/*` 是错误方向），因此下沉到这里；`pages/story/utils.ts` 保留
 * 同名 re-export，既有 4 处调用无需改动。
 */

/** 触发一次文本文件下载（默认按 Markdown 处理，浏览器据 `download` 属性命名）。 */
export function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  saveBlobAs(filename, blob)
}

/**
 * 触发一次**二进制**文件下载（视频 / 图片 / 任意 blob）。
 *
 * ## ⚠️ 关键：`a.download` 只对**同源 blob:** 生效（2026-10-11）
 *
 * `downloadTextFile` 走这里是因为同一条教训：
 *
 *   · `a.href = '/api/v1/proxy/video?url=...'` + `a.download = 'x.mp4'`
 *     → 那个地址没有 `Content-Disposition`，浏览器按"导航到媒体"处理，
 *       于是**跳到播放页**，`download` 属性形同虚设。
 *   · `a.href = URL.createObjectURL(blob)`（同源 `blob:`）+ `download`
 *     → 浏览器**认** `download`，直接存文件，不跳页。
 *
 * ⇒ 想"下载"就必须先拿到 blob。
 *
 * ## ⚠️ 但「内容下载」**不要**走这条路
 *
 * 视频/图集的下载请**跳独立下载页**（`/download?url=<原文链接>`）——
 * 那里有清晰度选择、进度、断点续传、导入素材库，且与「查询」页行为一致。
 * 前一版在点赞面板自己 fetch blob 存文件，结果和查询页**不一致**
 * （用户指出："还有调到单独下载页面的"）。
 *
 * 这个函数保留给**已有的本地 blob**（如文本导出）用。
 */
export function saveBlobAs(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // ⚠️ 必须 revoke，否则 blob 一直占内存（大文件很可观）。
  //    不能立刻 revoke —— click() 是同步的，太快会让部分浏览器
  //    来不及开始下载。让它先跑完这一轮。
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
