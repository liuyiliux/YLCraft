## ADDED Requirements

### Requirement: 孤立顶层 .py 文件必须归入领域包
`services/` 目录下 SHALL 不保留顶层独立的 `.py` 文件。每个 `.py` 文件 MUST 归属于一个明确的领域包子目录，该子目录 MUST 包含 `__init__.py` 并导出公共 API。

#### Scenario: 孤立工具文件的归属
- **WHEN** 发现 `services/image_editor.py` 作为顶层孤立文件存在
- **THEN** 它 MUST 被移入 `services/image_editor/` 包（含 `__init__.py` 导出），因为图片编辑是独立领域

#### Scenario: 孤立基础设施文件的归属
- **WHEN** 发现 `services/ffmpeg_service.py` 作为顶层孤立文件存在
- **THEN** 它 MUST 被移入 `services/video/` 包并更名为 `ffmpeg.py`，因为 FFmpeg 是视频处理基础设施

#### Scenario: 先搜索再迁移
- **WHEN** 需要迁移一个孤立文件
- **THEN** 必须先搜索所有引用该文件的 import 语句，迁移后更新所有引用路径
