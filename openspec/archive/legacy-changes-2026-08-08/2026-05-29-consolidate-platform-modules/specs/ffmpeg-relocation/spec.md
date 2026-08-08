## ADDED Requirements

### Requirement: FFmpeg 封装迁移到 core/ffmpeg.py

`services/video/ffmpeg.py` SHALL 迁移到 `core/ffmpeg.py`，作为视频处理基础设施。

#### Scenario: core/ffmpeg.py 包含 FFmpegService

- **WHEN** 需要使用 FFmpeg 进行视频处理
- **THEN** 从 `core.ffmpeg` 导入 `FFmpegService`
- **AND** 功能与原 `services/video/ffmpeg.py` 完全一致

#### Scenario: video/__init__.py 转发导出

- **WHEN** 代码从 `services.video` 导入 `FFmpegService`
- **THEN** `services/video/__init__.py` 从 `core.ffmpeg` 重导出
- **AND** 现有 import 路径保持兼容

#### Scenario: 更新所有引用

- **WHEN** 其他代码引用 `from app.services.video.ffmpeg import FFmpegService`
- **THEN** 这些 import 语句 SHALL 更新为 `from app.core.ffmpeg import FFmpegService`
- **AND** 搜索 `services/video/ffmpeg.py` 无任何外部引用后可删除原文件

### Requirement: core/ 目录结构保持一致

`core/ffmpeg.py` SHALL 与 `core/config.py`、`core/task_queue.py` 等基础设施文件同属一层级。

#### Scenario: core/ 是基础设施层

- **WHEN** 开发者需要添加新的基础设施组件
- **THEN** 应将组件放在 `core/` 目录
- **AND** 不应将业务逻辑放入 `core/`
