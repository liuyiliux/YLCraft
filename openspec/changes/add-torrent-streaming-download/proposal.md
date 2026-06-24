# Proposal: 磁力链接/种子下载与在线播放

## What

在 YLCraft 中新增磁力链接与 `.torrent` 种子下载能力，并将下载完成的视频文件自动纳入素材库，复用现有播放器进行在线播放。

核心能力：

1. **磁力/种子任务管理** - 支持添加 magnet 链接、上传 `.torrent` 文件、暂停、继续、删除、查看进度。
2. **种子文件列表解析** - 获取种子内文件列表，允许用户选择需要下载的视频文件。
3. **下载后入素材库** - 下载完成后创建或更新 `Asset` 记录，标记来源为 `torrent`。
4. **在线播放** - 复用 `/player/assets/:assetId`，通过素材流接口播放本地视频。
5. **大文件流式播放优化** - 为视频资产流接口补充 HTTP Range 支持，提升拖动进度条和大文件播放体验。
6. **安全与资源控制** - 限制下载目录、文件路径、任务数量、磁盘占用和允许的来源，避免被当作开放下载代理。

## Why

- 项目已经具备下载页、素材库、任务中心和播放器，新增 BT 下载能自然接入现有内容生产流程。
- 创作者可能需要管理较大的本地视频素材包，磁力/种子比普通直链更适合批量文件分发。
- 当前播放器已有资产播放入口，但普通视频流接口仍需要为大文件场景增强 Range 支持。

## What changes

| 层 | 新增 | 修改 |
|---|---|---|
| Backend | `app/services/torrent/` 下载引擎适配层 | `requirements.txt` 增加 qBittorrent Web API 客户端或 HTTP 调用依赖 |
| Backend | `app/api/v1/torrents.py` 种子任务 API | `app/main.py` 注册 `/api/v1/torrents` |
| Backend | `TorrentTask` / `TorrentFile` 数据模型或持久化结构 | `AssetService` 增加 torrent 入库辅助方法 |
| Backend | qBittorrent/aria2 配置项 | `settings` 增加下载目录、磁盘上限、最大并发 |
| Backend | Range-aware 视频流工具 | `api/v1/assets.py` 的 `/stream` 接口支持 Range |
| Frontend | 下载页内新增“磁力/种子”模式 | `pages/download/index.tsx` 增加任务列表、文件选择和播放入口 |
| Frontend | `api/index.ts` 新增 torrent API | `PlayerPage` 继续复用现有资产播放逻辑 |

## Non-goals

- 不内置公开磁力搜索、排行、资源站聚合或内容推荐。
- 不绕过 DRM、付费墙或访问控制。
- MVP 不要求所有媒体格式边下边转码；先支持下载完成后播放，随后再扩展 HLS/转码。
- MVP 不要求内嵌 BT 引擎，优先集成本机 qBittorrent Web API 或 aria2 RPC。

## User flow

1. 用户进入 `/download`，切换到“磁力/种子”模式。
2. 用户粘贴 magnet 链接或上传 `.torrent` 文件。
3. 后端创建 torrent 任务并获取元数据。
4. 前端展示文件列表，用户选择一个或多个视频文件下载。
5. 后端调度下载并通过任务状态/API 轮询或 WebSocket 推送进度。
6. 下载完成后，后端创建 `Asset` 记录。
7. 用户点击“播放”，跳转 `/player/assets/:assetId`。

