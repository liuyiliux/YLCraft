# Tasks

## Phase 1: 方案与基础设施

- [ ] 1. 确认下载引擎优先级：qBittorrent Web API 为默认，aria2 RPC 为可选后备。
- [ ] 2. 新增 torrent 配置读取逻辑：引擎类型、连接信息、下载目录、并发和容量限制。
- [ ] 3. 创建 `backend/app/services/torrent/` 包及统一 `TorrentEngine` 接口。
- [ ] 4. 实现 qBittorrent Web API 适配器的登录、添加任务、查询状态、文件列表和文件优先级控制。

## Phase 2: 后端 API 与持久化

- [ ] 5. 新增 `TorrentDownload` 数据模型和数据库初始化/迁移处理。
- [ ] 6. 创建 `backend/app/api/v1/torrents.py` 路由。
- [ ] 7. 实现 `POST /api/v1/torrents/magnet` 添加 magnet 链接。
- [ ] 8. 实现 `POST /api/v1/torrents/upload` 上传 `.torrent` 文件。
- [ ] 9. 实现任务详情、文件列表、选择文件、暂停、继续、删除 API。
- [ ] 10. 在 `backend/app/main.py` 注册 `/api/v1/torrents` 路由。

## Phase 3: 素材库与播放器集成

- [ ] 11. 实现下载完成文件识别：视频扩展名、MIME 类型、文件大小、ffprobe 元数据。
- [ ] 12. 将已完成视频文件写入 `Asset`，`source_type=torrent`、`platform=torrent`。
- [ ] 13. 实现 `POST /api/v1/torrents/{download_id}/import-assets`。
- [ ] 14. 为 `/api/v1/assets/{asset_id}/stream` 增加 HTTP Range 支持。
- [ ] 15. 验证 `/player/assets/:assetId` 可播放 torrent 入库后的 MP4 文件。

## Phase 4: 前端页面

- [ ] 16. 在 `frontend/src/api/index.ts` 新增 torrent API 方法。
- [ ] 17. 在 `frontend/src/pages/download/index.tsx` 增加“磁力/种子”模式切换。
- [ ] 18. 实现 magnet 输入和 `.torrent` 上传交互。
- [ ] 19. 实现种子文件列表、文件选择和开始下载交互。
- [ ] 20. 实现任务进度展示：状态、百分比、下载速度、上传速度、剩余时间。
- [ ] 21. 实现暂停、继续、删除、导入素材库和跳转播放操作。

## Phase 5: 安全、限制与异常处理

- [ ] 22. 校验所有下载文件路径必须位于配置的下载根目录内。
- [ ] 23. 限制 `.torrent` 上传大小、扩展名和 MIME 类型。
- [ ] 24. 增加最大并发任务和总容量限制。
- [ ] 25. 处理下载引擎未启动、登录失败、元数据超时、无可播放文件等错误状态。
- [ ] 26. 前端为不支持浏览器原生播放的格式显示清晰状态和后续转码入口占位。

## Phase 6: 验证

- [ ] 27. 后端单元测试：engine 适配器 mock、路径安全校验、Asset 入库。
- [ ] 28. API 测试：添加 magnet、查询文件、选择文件、暂停/继续、导入素材。
- [ ] 29. 前端构建验证：`npm run build`。
- [ ] 30. 手动端到端验证：添加 magnet -> 选择视频 -> 下载完成 -> 入素材库 -> 播放器播放。

