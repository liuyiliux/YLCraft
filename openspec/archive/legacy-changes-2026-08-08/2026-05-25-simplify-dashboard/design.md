# Design: 简化首页导航

## 页面结构 (重构后)

```
┌─ Hero ──────────────────────────────────────────┐
│  YLCraft | AI驱动的内容创作平台                   │
│  [开始创作]                                       │
└──────────────────────────────────────────────────┘

┌─ 核心功能 ───────────────────────────────────────┐
│  AI图像生成  AI视频生成  小说搜索   多平台下载     │
│  AI视频剪辑  爆款拆解   素材管理                   │
│                                                   │
│  ▸ 实验功能 (短剧创作 Beta · Live2D 开发中)        │
└──────────────────────────────────────────────────┘

┌─ 使用趋势 (全宽) ────────────────────────────────┐
│  图像生成 / 视频生成 / 角色创建 / 短剧创作         │
└──────────────────────────────────────────────────┘
```

## 卡片定义

```ts
const FEATURE_CARDS = [
  { title: 'AI 图像生成', icon: PictureOutlined,     path: '/image-gen',     status: 'ready' },
  { title: 'AI 视频生成', icon: VideoCameraOutlined, path: '/video-gen',     status: 'ready' },
  { title: '小说搜索',    icon: ReadOutlined,        path: '/novel-search',  status: 'ready' },  // 新增
  { title: '多平台下载',  icon: DownloadOutlined,    path: '/download',      status: 'ready' },
  { title: 'AI 视频剪辑', icon: ScissorOutlined,     path: '/clip',          status: 'ready' },
  { title: '爆款拆解',    icon: ExperimentOutlined,   path: '/breaker',       status: 'ready' },
  { title: '素材管理',    icon: FileAddOutlined,     path: '/assets',        status: 'ready' },
]

const BETA_CARDS = [
  { title: '短剧创作',    icon: BookOutlined,        path: '/story',    status: 'beta' },
  { title: 'Live2D 工厂', icon: FireOutlined,        path: '/live2d',   status: 'dev'  },
]
```

## 删除的 section

| Section | 内容 |
|---------|------|
| 快速操作 | AI生成、上传素材、去水印、一键发布 → 合并到核心功能 |
| 快捷入口 | 图像生成、视频生成、素材库、任务中心 → 纯重复 |

## Hero 简化

- Hero 只保留 "开始创作" (→ /image-gen)，去掉 "查看任务" 按钮
- 统计数字保留
