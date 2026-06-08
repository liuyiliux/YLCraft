# YLCraft 公共播放器设计

> 目标：把普通视频、B 站付费课程章节、后续知识库命中定位播放统一到一个播放器体系里，避免每个页面各写一套播放、字幕、弹幕、选集逻辑。

## 1. 当前落点

### 前端

- 公共播放器组件：`frontend/src/components/video/AssetVideoPlayer.tsx`
- 独立播放器页面：`frontend/src/pages/player/index.tsx`
- 素材详情内嵌播放入口：`frontend/src/pages/assets/index.tsx`
- 路由入口：`/player/assets/:assetId`

### 后端

- 普通资产流播放：`/api/v1/assets/{asset_id}/stream`
- 普通资产字幕：`/api/v1/assets/{asset_id}/sidecars/subtitles/{subtitle_index}.vtt`
- 普通资产弹幕：`/api/v1/assets/{asset_id}/sidecars/danmaku`
- 课程章节流播放：`/api/v1/assets/{asset_id}/course-episodes/{episode_index}/stream`
- 课程章节字幕：`/api/v1/assets/{asset_id}/course-episodes/{episode_index}/sidecars/subtitles/{subtitle_index}.vtt`
- 课程章节弹幕：`/api/v1/assets/{asset_id}/course-episodes/{episode_index}/sidecars/danmaku`

## 2. 设计原则

1. 一个视频播放能力只维护一套。

   播放器只关心 `videoSrc`、`poster`、`subtitles`、`danmaku`、`startTime`、`highlights` 等标准输入，不关心素材来自 B 站、课程、Telegram 还是后续知识库。

2. 页面负责“选哪个资源”，播放器负责“怎么播放”。

   课程选集、知识库定位、资产详情跳转都在页面层组织 URL 和数据；播放器组件内部不直接查资产、不直接查课程列表。

3. 字幕和弹幕作为 sidecar 资源处理。

   视频主文件、字幕、弹幕都挂在同一个资产或课程章节 metadata 下。播放器通过后端 sidecar API 加载，不直接读取本地路径。

4. 独立播放器页面是长期入口。

   详情页可以内嵌播放，但真正适合做课程选集、知识库命中定位、后续播放笔记/片段管理的是 `/player/assets/:assetId`。

## 3. 组件边界

### `AssetVideoPlayer`

职责：

- 渲染 `<video>`
- 控制字幕开关
- 控制弹幕开关
- 控制弹幕速度和字号
- 控制自定义全屏
- 支持从指定时间开始播放
- 支持播放进度回调
- 支持命中片段高亮

输入建议：

```ts
interface AssetVideoPlayerProps {
  videoSrc: string
  poster?: string
  title?: string
  subtitles?: Array<{
    label: string
    src: string
    language?: string
    default?: boolean
  }>
  danmaku?: {
    src: string
    format?: 'json'
  } | null
  autoPlay?: boolean
  maxHeight?: number
  startTime?: number
  highlights?: Array<{ start: number; end?: number; label?: string }>
  onTimeChange?: (time: number) => void
}
```

不应该放进播放器组件的职责：

- 资产详情查询
- 课程章节列表查询
- 下载状态判断
- 平台差异解析
- 知识库搜索
- 向量召回

这些应由页面层或服务层完成，然后转成播放器标准输入。

### `PlayerPage`

职责：

- 根据 `assetId` 加载资产
- 根据 URL query 决定播放普通资产还是课程章节
- 生成 `videoSrc`
- 生成字幕 tracks
- 生成弹幕 track
- 展示右侧信息栏
- 展示课程章节列表
- 支持选集切换
- 支持知识库命中参数

当前 URL 约定：

- `/player/assets/:assetId`
- `/player/assets/:assetId?episode=3`
- `/player/assets/:assetId?t=123.4`
- `/player/assets/:assetId?start=120&end=135&q=关键词`
- `/player/assets/:assetId?episode=3&start=120&end=135&q=关键词`

## 4. 课程播放列表

课程本质上还是一个资产，但 `metadata.episodes` 里保存章节：

```json
{
  "episodes": [
    {
      "index": 1,
      "ep_id": 123,
      "title": "章节标题",
      "status": "ready",
      "file_path": "...",
      "subtitle_paths": ["..."],
      "danmaku_path": "..."
    }
  ]
}
```

播放时页面层根据 `episode` query 找到章节：

- 有 `episode`：播放对应课程章节
- 没有 `episode` 且有章节：默认播放第一集
- 普通视频：播放资产主文件

章节切换只改 URL query，不重写播放器内部状态：

```ts
params.set('episode', String(nextEpisodeIndex))
navigate(`/player/assets/${assetId}?${params.toString()}`)
```

这样后续知识库命中也可以直接定位到某个章节某个时间点。

## 5. 字幕和弹幕模型

### 字幕

播放器只吃 WebVTT track。后端负责把 SRT 转成 VTT：

- `.vtt`：原样返回
- `.srt`：替换时间轴逗号为点，并补 `WEBVTT`

好处：

- 前端不需要关心字幕格式差异
- `<track>` 原生支持
- 后续不同平台只要落成 `subtitle_paths` 即可

### 弹幕

播放器当前支持 JSON 弹幕。推荐统一格式：

```json
[
  {
    "time": 12.3,
    "text": "这条弹幕内容",
    "color": "#ffffff"
  }
]
```

兼容字段：

- 时间：`time`、`progress`、`ts`、`timeline`
- 文本：`text`、`content`、`msg`、`message`

平台差异应在下载/解析层抹平：

- B 站 XML/JSON 转统一 JSON
- 其他平台如果有弹幕/评论时间轴，也转统一 JSON
- 没有弹幕的平台不返回 `danmaku_path`

## 6. 知识库定位播放扩展

后续做向量知识库时，推荐把“命中结果”映射到播放器 URL：

```ts
{
  asset_id: string
  episode_index?: number
  start: number
  end?: number
  text: string
}
```

跳转规则：

- 普通视频：`/player/assets/{asset_id}?start=120&end=135&q=命中文本`
- 课程章节：`/player/assets/{asset_id}?episode=3&start=120&end=135&q=命中文本`

播放器页面拿到参数后：

- `start` 传给 `AssetVideoPlayer.startTime`
- `start/end/q` 转成 `highlights`
- 右侧信息栏展示命中文本

这样知识库不需要知道播放器内部结构，只需要生成标准播放 URL。

## 7. 全屏设计

播放器必须使用“容器全屏”，不要依赖浏览器原生 video 全屏。

原因：

- 原生 video 全屏通常只全屏 `<video>` 自身
- 自定义字幕/弹幕/按钮浮层可能不会进入全屏
- Ant Design 的弹层如果挂到 `body`，全屏后也不可见

当前策略：

- 使用 `container.requestFullscreen()`
- 原生 video 控件加 `controlsList="nofullscreen"`
- Chrome/Edge 下通过 CSS 隐藏原生全屏按钮：

```css
.ylcraft-video-player::-webkit-media-controls-fullscreen-button {
  display: none;
}
```

Ant Design 弹层必须挂到播放器容器：

```ts
const getPopupContainer = () => containerRef.current || document.body
```

然后传给 `Popover`。

## 8. 弹幕渲染设计

弹幕运动不要由 React 每帧计算位置。

错误方式：

```ts
left = 100 - progress * 100
transform = translateX(...)
```

如果 `progress` 来自 `video.onTimeUpdate`，会出现一秒几次的跳动；如果来自 RAF，又会导致频繁 React render。

当前策略：

- React 只负责筛选“当前应该出现的弹幕”
- CSS animation 负责弹幕从右到左匀速移动
- 每条弹幕挂载时只计算一次初始负延迟

关键点：

- `video.onTimeUpdate` 频率低，不能当动画时钟
- `requestAnimationFrame` 可以用于同步当前播放时间，但不能每帧改弹幕动画参数
- `animationDelay` 如果随 `currentTime` 每帧变化，会导致 CSS 动画不断重启
- 需要把每条弹幕拆成子组件，用 `useRef` 固定首次计算的 elapsed

当前弹幕调节：

- 默认横跨时间：`8s`
- 速度：`0.5x - 2x`
- 实际动画时长：`8 / speed`
- 字号：`12px - 28px`

## 9. 已遇到的坑

### 9.1 原生全屏和自定义全屏冲突

现象：

- 画面上出现两个全屏按钮
- 点原生全屏后，自定义按钮、弹幕、设置层可能不显示

结论：

- 公共播放器只保留容器全屏作为主入口
- 原生 video 全屏按钮尽量隐藏

### 9.2 全屏下 Popover 点不出来

现象：

- 非全屏能打开弹幕设置
- 全屏后点击设置没有弹层

原因：

- AntD 弹层默认挂到 `document.body`
- 浏览器全屏时只显示全屏元素子树

修复：

- `Popover.getPopupContainer` 返回播放器容器

### 9.3 弹幕一帧帧跳动

现象：

- 弹幕横向移动像几帧几帧刷新

原因：

- 位置绑定到 `video.onTimeUpdate`
- `timeupdate` 不是逐帧事件

修复：

- 移动交给 CSS animation
- React 只负责挂载/卸载

### 9.4 播放中弹幕滑半秒又回原点

现象：

- 暂停时看起来正常
- 播放时弹幕滑动后反复回到起点

原因：

- `requestAnimationFrame` 高频更新 `currentTime`
- JSX 里每帧重新计算 `animationDelay`
- CSS 认为动画参数变化，反复重启动画

修复：

- 拆出 `DanmakuBullet`
- 用 `useRef` 只记录首次 `elapsed`
- 后续 render 不再改变这条弹幕的初始延迟

### 9.5 字幕格式不能交给前端猜

现象：

- 不同下载来源可能拿到 SRT/VTT

结论：

- 后端 sidecar 接口统一输出 `text/vtt`
- 前端只使用 `<track kind="subtitles">`

### 9.6 本地路径不能直接暴露给前端

原因：

- 浏览器不能直接读取服务端本地路径
- 暴露绝对路径也不安全、不稳定

结论：

- metadata 里可以保存本地路径
- 前端只访问 `/api/v1/assets/.../sidecars/...`

## 10. 后续建议

1. 把弹幕设置持久化到 localStorage。

   用户调过速度、字号后，下次播放器自动恢复。

2. 增加弹幕密度和透明度。

   后续弹幕多的时候，只控制速度和字号不够，需要密度限制、同屏最大数量、透明度。

3. 增加播放器状态 URL 同步。

   例如当前播放到 180 秒时，可以复制链接 `/player/assets/:id?t=180`。

4. 课程选集支持上一集/下一集快捷按钮。

   当前右侧列表能选集，后续可以在播放器控制层增加章节切换。

5. 知识库结果进入播放器后，右侧显示命中列表。

   不只是一个 `q`，而是同一视频的多个命中片段，点击后 seek 到对应时间。

6. 将不同平台 sidecar 下载统一成公共服务。

   B 站、Telegram、普通解析下载最终都落到统一 metadata 字段：`subtitle_paths`、`danmaku_path`。

7. 弹幕引擎可进一步组件化。

   当前弹幕逻辑在 `AssetVideoPlayer` 内。等能力变多后，可以拆成 `DanmakuOverlay`，专门处理轨道、碰撞、密度、透明度、暂停同步等。
