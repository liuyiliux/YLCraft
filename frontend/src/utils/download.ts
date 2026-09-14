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
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
