# Proposal: 微信公众号文章下载

## What

借鉴 [EasyWechatDownload](https://github.com/yangbuyiya/EasyWechatDownload) 的"公众号平台模式"，在 YLCraft 中新增微信公众号文章下载功能。核心功能：

1. **公众号账号管理** — 复用账号中心，新增"微信公众号"平台，支持扫码登录
2. **公众号文章搜索** — 复用内容搜索页，新增"微信公众号"tab，搜索公众号 + 拉取历史文章列表
3. **公众号文章下载** — 复用去水印下载页，支持粘贴公众号文章链接直接解析下载
4. **文章入素材库** — 搜索结果可勾选导入素材库，下载完成后自动写入素材库
5. **代理功能公共服务化** — 将代理逻辑抽成公共模块，供爬虫/下载功能复用
6. **EPUB 电子书公共组件** — 新建可复用组件，素材库中选文章文件夹一键生成 EPUB

## Why

- 创作者需要采集微信公众号文章作为创作素材
- 现有内容搜索和去水印下载已覆盖多平台（B站/抖音/小红书/Twitter 等），唯独缺少微信公众号
- 代理功能散落在各处，需要统一管理
- EPUB 生成是可复用的通用能力，不应耦合在某个页面中

## What changes

| 层 | 新增 | 修改 |
|---|------|------|
| **DB** | `wechat_mp_downloads` 表 — 下载任务记录 | — |
| **Backend** | `app/services/wechat_mp/` — 微信公众号服务 | `app/api/v1/platforms.py` — 新增 wechat_mp 平台支持 |
| **Backend** | `app/api/v1/wechat_mp.py` — 公众号 API 路由 | `app/api/v1/crawler.py` — 新增 wechat_mp 搜索类型 |
| **Backend** | `app/services/proxy/` — 代理公共服务 | `app/api/v1/download.py` — 扩展公众号文章解析 |
| **Backend** | `app/api/v1/ebook.py` — EPUB 生成 API | — |
| **Frontend** | `components/ebook/EpubCreatorModal.tsx` — 公共 EPUB 组件 | `pages/accounts/index.tsx` — 新增微信公众平台卡片 |
| **Frontend** | — | `pages/crawler/index.tsx` — 新增微信公众号 tab |
| **Frontend** | — | `pages/download/index.tsx` — 支持公众号文章链接 |

## 不新增一级菜单

所有功能融入现有菜单结构：
- 账号管理 → **账号中心** (`/accounts`)
- 搜索公众号文章 → **内容搜索** (`/crawler`)
- 下载单篇文章 → **去水印下载** (`/download`)
- 文章入素材库 → 搜索结果导入 + 下载自动写入
- EPUB 生成 → 素材库/下载页内嵌调用
