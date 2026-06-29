# Tasks

## Phase 1: 方案与基础设施

- [x] 1. 确认下载引擎优先级：qBittorrent Web API 为默认。
- [x] 2. 新增 torrent 配置读取逻辑：引擎类型、连接信息、下载目录、并发和容量限制。
- [x] 3. 创建 `backend/app/services/torrent/` 包及统一 `TorrentEngine` 接口。
- [x] 4. 实现 qBittorrent Web API 适配器的登录、添加任务、查询状态、文件列表和文件优先级控制。
- [x] 5. 增加可选 `libtorrent` Python 引擎入口，支持无外部软件下载模式。
- [x] 5.1. 增强 `libtorrent` 引擎兼容性，并支持后端重启后按数据库记录重新挂载任务。

## Phase 2: 后端 API 与持久化

- [x] 6. 新增 `TorrentDownload` 数据模型和数据库初始化/迁移处理。
- [x] 7. 创建 `backend/app/api/v1/torrents.py` 路由。
- [x] 8. 实现 `POST /api/v1/torrents/magnet` 添加 magnet 链接。
- [x] 9. 实现 `POST /api/v1/torrents/upload` 上传 `.torrent` 文件。
- [x] 10. 实现任务详情、文件列表、选择文件、暂停、继续、删除 API。
- [x] 11. 在 `backend/app/main.py` 注册 `/api/v1/torrents` 路由。
- [x] 12. 实现 `GET /api/v1/torrents/{download_id}/files/{file_index}/stream` 文件级在线播放接口。

## Phase 3: 素材库与播放器集成

- [x] 13. 实现下载完成文件识别：视频扩展名、MIME 类型、文件大小、ffprobe 元数据。
- [x] 14. 将已完成视频文件写入 `Asset`，`source_type=torrent`、`platform=torrent`。
- [x] 15. 实现 `POST /api/v1/torrents/{download_id}/import-assets`。
- [x] 16. 为 `/api/v1/assets/{asset_id}/stream` 增加 HTTP Range 支持。
- [x] 17. 验证 `/player/assets/:assetId` 可播放 torrent 入库后的 MP4 文件。

## Phase 4: 前端页面

- [x] 18. 在 `frontend/src/api/index.ts` 新增 torrent API 方法。
- [x] 19. 在 `frontend/src/pages/download/index.tsx` 增加“磁力/种子”入口。
- [x] 20. 实现 magnet 输入和 `.torrent` 上传交互。
- [x] 21. 实现种子文件列表、文件选择和开始下载交互。
- [x] 22. 实现任务进度展示：状态、百分比、下载速度、上传速度。
- [x] 23. 实现暂停、继续、删除、导入素材库和跳转播放操作。
- [x] 24. 实现文件列表中的在线播放弹窗与继续下载操作。
- [x] 24.1. 前端展示当前 torrent 引擎、下载目录、最大任务数和外部软件依赖提示。
- [x] 24.2. 文件列表视频行支持一键“边下边播”：自动选中文件、启动下载并等待本地片段可预览后打开播放器。

## Phase 5: 安全、限制与异常处理

- [x] 25. 校验所有下载文件路径必须位于配置的下载根目录内。
- [x] 26. 限制 `.torrent` 上传大小、扩展名和 MIME 类型。
- [x] 27. 增加最大并发任务限制。
- [x] 28. 处理下载引擎未启动、登录失败、元数据未就绪、无可播放文件等错误状态。
- [x] 29. 前端为下载未完成和浏览器原生播放受限场景显示清晰提示。
- [x] 29.1. 兼容 qBittorrent 未完成文件 `.!qB` 后缀，并支持浏览器 suffix Range 请求。

## Phase 6: 验证

- [x] 30. 后端单元测试：engine 适配器 mock、路径安全校验、Asset 入库。
- [x] 30.1. 后端单元测试：torrent 文件流 Range/suffix Range、qBittorrent `.!qB` 临时文件、播放路径安全校验。
- [x] 31. API 测试：添加 magnet、上传 `.torrent`、查询文件、选择文件、暂停/继续、导入素材、文件流播放。
- [x] 32. 前端构建验证：`npm run build`。
- [x] 33. 端到端自动化验证：添加 magnet -> 选择视频 -> 文件流播放 -> 入素材库 -> 播放器资产流播放。
