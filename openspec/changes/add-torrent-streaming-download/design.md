# Design: 磁力链接/种子下载与在线播放

## Architecture

优先采用外部下载引擎模式：

```text
Frontend /download
  -> /api/v1/torrents
    -> TorrentService
      -> qBittorrent Web API 或 aria2 RPC
      -> backend/downloads/torrents
      -> AssetService
        -> assets 表
          -> /player/assets/:assetId
            -> /api/v1/assets/:id/stream
```

理由：

- qBittorrent/aria2 已经解决 BT 协议、DHT、限速、暂停恢复、文件优先级等复杂问题。
- FastAPI 后端只负责鉴权、任务映射、进度查询、入库和播放接口，维护成本更低。
- Windows 本地开发环境更容易部署 qBittorrent Web UI 或 aria2。

## Backend modules

### `app/services/torrent/`

建议文件结构：

```text
services/torrent/
├── __init__.py
├── models.py
├── service.py
├── engine.py
├── qbittorrent.py
├── aria2.py
└── media.py
```

职责：

- `engine.py` 定义统一接口：添加任务、获取文件列表、设置文件优先级、暂停、继续、删除、查询状态。
- `qbittorrent.py` 实现 qBittorrent Web API 适配器。
- `aria2.py` 作为可选后备适配器。
- `service.py` 负责业务编排、任务状态落库、下载完成后的素材入库。
- `media.py` 负责识别可播放视频、探测媒体信息、生成 MIME 类型。

### Engine interface

```python
class TorrentEngine:
    async def add_magnet(self, magnet: str, save_path: str) -> TorrentHandle: ...
    async def add_torrent_file(self, file_path: str, save_path: str) -> TorrentHandle: ...
    async def list_files(self, torrent_hash: str) -> list[TorrentFileInfo]: ...
    async def set_file_priority(self, torrent_hash: str, file_indexes: list[int]) -> None: ...
    async def get_status(self, torrent_hash: str) -> TorrentStatus: ...
    async def pause(self, torrent_hash: str) -> None: ...
    async def resume(self, torrent_hash: str) -> None: ...
    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None: ...
```

## Data model

### Torrent task

可以新增 SQLModel 表，也可以先使用现有任务中心的 payload。推荐新增表，保证服务重启后任务可恢复：

```python
class TorrentDownload(SQLModel, table=True):
    __tablename__ = "torrent_downloads"

    id: str
    engine: str = "qbittorrent"
    torrent_hash: str
    name: str
    source: str               # magnet 或 uploaded_torrent
    source_uri: str           # magnet 链接或上传文件路径
    save_path: str
    status: str               # metadata/downloading/paused/done/failed/deleted
    progress: int
    download_speed: int
    upload_speed: int
    total_size: int
    selected_files_json: str
    asset_ids_json: str
    error_message: str
    created_at: datetime
    updated_at: datetime
```

### Asset integration

下载完成的视频资产：

- `Asset.type = "VIDEO"`
- `Asset.platform = "torrent"`
- `Asset.source_type = "torrent"`
- `Asset.source_url = magnet 或 torrent:{hash}`
- `Asset.file_path = 本地视频路径`
- `Asset.status = "READY"`
- `Asset.metadata_json` 包含：
  - `torrent_hash`
  - `torrent_name`
  - `file_index`
  - `download_id`
  - `original_file_name`

## API design

Base path: `/api/v1/torrents`

| Method | Path | Description |
|---|---|---|
| `POST` | `/magnet` | 添加 magnet 链接并开始获取元数据 |
| `POST` | `/upload` | 上传 `.torrent` 文件 |
| `GET` | `/{download_id}` | 查询任务详情 |
| `GET` | `/{download_id}/files` | 查询种子文件列表 |
| `POST` | `/{download_id}/select-files` | 选择需要下载的文件 |
| `POST` | `/{download_id}/pause` | 暂停任务 |
| `POST` | `/{download_id}/resume` | 继续任务 |
| `DELETE` | `/{download_id}` | 删除任务，可选删除文件 |
| `POST` | `/{download_id}/import-assets` | 将已完成文件导入素材库 |

### Request/response examples

`POST /api/v1/torrents/magnet`

```json
{
  "magnet": "magnet:?xt=urn:btih:...",
  "start_paused": true
}
```

Response:

```json
{
  "success": true,
  "download_id": "abc123",
  "torrent_hash": "...",
  "status": "metadata"
}
```

`POST /api/v1/torrents/{download_id}/select-files`

```json
{
  "file_indexes": [0, 2],
  "start": true
}
```

## Streaming design

`GET /api/v1/assets/{asset_id}/stream` 应支持：

- `Range: bytes=start-end`
- `206 Partial Content`
- `Content-Range`
- `Accept-Ranges: bytes`
- 浏览器直接拖动播放进度

初期仍以原文件直出为主：

- `mp4/h264/aac` 直接播放。
- `mkv/hevc/ass` 可能无法被浏览器原生播放，前端显示“需要转码”状态。
- 后续新增 HLS 转码队列：`/api/v1/assets/{id}/hls/master.m3u8`。

## Frontend design

在现有 `DownloadPage` 内增加模式切换：

- `链接解析`
- `磁力/种子`

磁力/种子模式包含：

- magnet 输入框
- `.torrent` 上传按钮
- 元数据加载状态
- 文件列表表格：文件名、大小、类型、优先级、是否下载
- 任务进度：下载速度、上传速度、连接数、剩余时间
- 操作：暂停、继续、删除、打开播放

不新增一级菜单，继续复用 `/download`。

## Security and resource controls

- 只允许保存到配置的 torrent 下载根目录。
- 所有文件路径必须 `resolve()` 后校验在下载根目录内。
- 上传 `.torrent` 限制文件大小和扩展名。
- 默认不自动开始下载，先获取元数据并让用户选择文件。
- 限制最大并发任务、单任务最大体积、总缓存上限。
- 删除任务时默认不删除文件，必须显式选择。
- 不提供公开搜索与聚合入口。

## Configuration

新增设置项：

```env
TORRENT_ENGINE=qbittorrent
QBITTORRENT_URL=http://127.0.0.1:8080
QBITTORRENT_USERNAME=admin
QBITTORRENT_PASSWORD=adminadmin
TORRENT_DOWNLOAD_DIR=backend/downloads/torrents
TORRENT_MAX_ACTIVE=3
TORRENT_MAX_TOTAL_BYTES=0
```

这些配置也可后续接入现有系统设置页。

