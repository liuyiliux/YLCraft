/**
 * 下载本地资产（素材库/生成产物）。
 *
 * **为什么不能只 `window.open(assetFileUrl(path))`**：那个 URL 默认
 * `inline=true`，后端就只回一个普通响应，浏览器**在标签页里预览**它，而不是下载。
 * 用户点「下载」结果开了新页 —— 反馈的原话就是"是新页面打开"。
 *
 * 后端其实早支持 `?inline=false`（会带 `Content-Disposition: attachment`），
 * 但前端**从来没传过这个参数**。这里补上，并同时取 blob 后用 `<a download>`
 * 触发保存：前者让服务端也认定这是下载，后者能给出正确的文件名
 * （否则会落到浏览器默认的 `download` 这个名字）。
 *
 * 用 fetch 而不是直接 `<a href download>`：跨源时 `download` 属性会被忽略。
 * 本站 `/api` 经代理虽是同源，但换成直连后端地址就不保证了 —— 两步都做，谁生效算谁。
 *
 * ⚠️ 这个函数原来内联在 `image-gen/index.tsx` 里。独立出 `/motion` 页后
 * 两边都要用，所以抽到公共位置 —— 再抄一份就是"同一件事两个实现"的老毛病。
 */

import { message } from 'antd'

/** 拼接本地资产的下载地址（带 `inline=false`，确保是下载而不是预览）。 */
export function assetDownloadUrl(path: string, revision?: string): string {
  // `v=` 版本指纹：同路径文件被覆写后（动图重新合成就是原地覆写），
  // 没有它浏览器/代理会继续用旧副本 —— 用户点了下载却拿到上一次的文件。
  const v = revision ? `&v=${encodeURIComponent(revision)}` : ''
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}&inline=false${v}`
}

/** 拼接本地资产的预览地址（`inline=true`，给 `<img>` 用）。 */
export function assetPreviewUrl(path?: string | null, revision?: string): string {
  if (!path) return ''
  if (/^(https?:|data:|blob:|\/api\/)/i.test(path)) return path
  const v = revision ? `&v=${encodeURIComponent(revision)}` : ''
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}${v}`
}

export async function downloadAssetFile(
  path: string | null | undefined,
  fallbackName: string,
  revision?: string,
): Promise<void> {
  if (!path) {
    message.warning('没有可下载的文件')
    return
  }
  const url = assetDownloadUrl(path, revision)
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const name = path.split(/[\\/]/).pop() || fallbackName
    const href = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = href
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
    // 立刻 revoke 会让部分浏览器来不及取数据
    setTimeout(() => URL.revokeObjectURL(href), 10000)
    message.success(`已下载 ${name}`)
  } catch (e: any) {
    // blob 拿不到就退回最朴素的方式：让浏览器自己处理 attachment
    message.warning(`下载失败，改用浏览器默认方式：${e?.message || e}`)
    window.open(url)
  }
}
