## ADDED Requirements

### Requirement: 系统必须支持添加磁力链接任务

系统 SHALL 允许用户在下载页提交合法 magnet 链接，并创建对应的 torrent 下载任务。

#### Scenario: 添加 magnet 链接
- **WHEN** 用户提交合法 `magnet:?xt=urn:btih:` 链接
- **THEN** 后端创建 torrent 下载记录
- **AND** 返回 `download_id`、`torrent_hash` 和当前状态
- **AND** 任务初始状态为 `metadata` 或 `paused`

#### Scenario: 拒绝非法 magnet 链接
- **WHEN** 用户提交非 magnet 链接或缺少 btih 标识
- **THEN** 后端返回 400 错误
- **AND** 不创建下载任务

### Requirement: 系统必须支持上传种子文件

系统 SHALL 允许用户上传 `.torrent` 文件并创建下载任务。

#### Scenario: 上传 torrent 文件
- **WHEN** 用户上传合法 `.torrent` 文件
- **THEN** 后端保存种子文件到受控目录
- **AND** 调用下载引擎添加任务
- **AND** 返回任务标识和元数据状态

### Requirement: 系统必须支持 torrent 文件在线播放

系统 SHALL 允许用户在文件列表中直接预览已下载的视频文件，并通过流式接口在线播放。

#### Scenario: 打开视频预览
- **WHEN** 用户在 torrent 文件列表点击视频文件的播放
- **THEN** 前端打开在线播放器
- **AND** 播放器通过 torrent 文件流接口读取本地视频

#### Scenario: 文件级 Range 播放请求
- **WHEN** 浏览器请求 `/api/v1/torrents/{download_id}/files/{file_index}/stream` 并携带 `Range` 头
- **THEN** 后端返回 `206 Partial Content`
- **AND** 响应包含 `Content-Range` 和 `Accept-Ranges: bytes`
- **AND** 如果 qBittorrent 为未完成文件追加 `.!qB` 后缀，后端仍可定位本地临时文件

#### Scenario: 下载未完成
- **WHEN** 视频文件尚未完整下载
- **THEN** 前端显示当前下载进度
- **AND** 允许用户继续下载该文件

#### Scenario: 拒绝不合法上传
- **WHEN** 上传文件扩展名不是 `.torrent` 或文件超过限制
- **THEN** 后端拒绝请求
- **AND** 返回明确错误信息

### Requirement: 系统必须展示种子文件列表并允许选择下载文件

系统 SHALL 在获取种子元数据后展示文件列表，并允许用户选择需要下载的文件。

#### Scenario: 获取文件列表
- **WHEN** 种子元数据可用
- **THEN** 前端展示文件名、大小、文件类型和下载状态

#### Scenario: 选择文件下载
- **WHEN** 用户选择一个或多个文件并点击开始下载
- **THEN** 后端设置下载引擎中的文件优先级
- **AND** 未选择文件不应被下载或应被设置为最低优先级

### Requirement: 系统必须同步 torrent 下载进度

系统 SHALL 提供下载任务状态查询能力，包含进度、速度、大小和错误信息。

#### Scenario: 查询下载状态
- **WHEN** 前端查询 torrent 任务详情
- **THEN** 后端返回状态、百分比、下载速度、上传速度、总大小和已下载大小

#### Scenario: 下载失败
- **WHEN** 下载引擎返回错误或任务不可恢复
- **THEN** 后端将任务标记为 `failed`
- **AND** 前端展示错误信息

### Requirement: 下载完成的视频必须可进入素材库

系统 SHALL 将下载完成且可识别的视频文件导入素材库。

#### Scenario: 自动或手动导入视频资产
- **WHEN** torrent 任务中的选中文件下载完成
- **THEN** 后端为视频文件创建 `Asset` 记录
- **AND** `Asset.source_type` 为 `torrent`
- **AND** `Asset.platform` 为 `torrent`
- **AND** `Asset.status` 为 `READY`

#### Scenario: 跳转播放器
- **WHEN** 用户点击已导入视频的播放操作
- **THEN** 前端跳转到 `/player/assets/{assetId}`

### Requirement: 视频资产流接口必须支持 Range 请求

系统 SHALL 为视频资产播放接口支持 HTTP Range，以便浏览器播放大文件和拖动进度。

#### Scenario: Range 播放请求
- **WHEN** 浏览器请求 `/api/v1/assets/{asset_id}/stream` 并携带 `Range: bytes=start-end`
- **THEN** 后端返回 `206 Partial Content`
- **AND** 响应包含 `Content-Range` 和 `Accept-Ranges: bytes`

#### Scenario: 普通播放请求
- **WHEN** 请求未携带 Range 头
- **THEN** 后端仍可返回完整文件响应

### Requirement: torrent 引擎可选纯 Python 模式

系统 SHALL 支持不依赖外部下载器进程的 torrent 引擎模式，前提是安装 `libtorrent` Python bindings。

#### Scenario: 使用 libtorrent 模式
- **WHEN** 配置 `TORRENT_ENGINE=libtorrent`
- **THEN** 后端使用 Python `libtorrent` bindings 创建和管理 torrent 会话
- **AND** 不要求本机运行 qBittorrent 或 aria2

#### Scenario: libtorrent 后端重启恢复
- **WHEN** 后端重启导致内存中的 libtorrent handle 丢失
- **THEN** 后端可以根据数据库中的 magnet 链接或已保存 `.torrent` 文件重新挂载任务

### Requirement: 系统必须展示当前 torrent 引擎信息

系统 SHALL 提供当前 torrent 引擎摘要，帮助用户判断是否需要外部下载软件。

#### Scenario: 查看引擎信息
- **WHEN** 前端打开下载页
- **THEN** 后端返回当前引擎类型、下载目录、最大任务数和是否依赖外部应用
- **AND** 前端展示对应提示

### Requirement: torrent 下载必须受资源与路径限制

系统 SHALL 限制 torrent 下载目录、上传文件、任务并发和磁盘占用。

#### Scenario: 路径越界保护
- **WHEN** 下载完成文件路径解析后不位于配置的 torrent 下载根目录内
- **THEN** 后端拒绝导入素材库
- **AND** 记录安全错误

#### Scenario: 并发限制
- **WHEN** 活跃 torrent 下载任务数量达到配置上限
- **THEN** 新任务应保持暂停或被拒绝
- **AND** 前端展示限制原因
