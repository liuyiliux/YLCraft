## Why

`services/` 目录下存在平台模块边界模糊、职责重叠的问题：

1. **xhs_parser** 与 **platforms/xiaohongshu/** 功能重叠但分离，调用方（breaker/）需区分导入
2. **video/ffmpeg.py** 是视频处理基础设施，却放在 services/ 而非 core/，违反技术分层
3. **platform_connection/** 标注为"旧版"但仍被广泛依赖，需要明确的迁移路径到 connectors/social/
4. **breaker/__init__.py** 包含 ~400 行实现代码，违反"包自述 API"原则

本次整合使平台模块边界清晰、职责归一。

## What Changes

1. **xhs_parser 合并到 platforms/xiaohongshu/parser.py（路径B）**
   - 将 xhs_parser/service.py 的 XhsParserService 逻辑迁移到 platforms/xiaohongshu/parser.py
   - 旧 xhs_parser/ 保留桥接层（兼容旧入口），最终删除
   - breaker/ 等调用方保持兼容，逐步迁移到 platforms.xiaohongshu

2. **video/ffmpeg.py 迁移到 core/ffmpeg.py**
   - FFmpeg 封装是视频处理基础设施，应在 core/ 而非 services/
   - 更新所有引用 video/ffmpeg 的 import 语句

3. **platform_connection/ 迁移路径标注**
   - 在 platform_connection/__init__.py 添加 deprecation 文档
   - 明确 connectors/social/ 是目标迁移方向
   - 阶段1：保留 + 文档；阶段2-4：后续执行

4. **breaker/__init__.py 重构**
   - 将 __init__.py 中的实现代码移入 service.py
   - __init__.py 仅做导出，保持"包自述 API"原则

## Capabilities

### New Capabilities

- **xhs-parser-unification**: 将 xhs_parser 逻辑并入 platforms/xiaohongshu/parser.py，保持 XiaohongshuClient 职责清晰
- **ffmpeg-relocation**: 将 video/ffmpeg.py 迁移到 core/ffmpeg.py，确立基础设施定位
- **platform-connection-migration-path**: 为 platform_connection/ 到 connectors/social/ 的迁移提供文档指引
- **breaker-init-refactor**: 重构 breaker/__init__.py，实现与 service.py 的职责分离

## Impact

- **涉及目录**:
  - `services/xhs_parser/` → 最终删除，桥接层过渡
  - `services/platforms/xiaohongshu/` → 新增 parser.py
  - `services/video/ffmpeg.py` → 迁移到 `core/ffmpeg.py`
  - `services/breaker/__init__.py` → 重构为纯导出
  - `services/platform_connection/` → 添加 deprecation 文档
  - `connectors/social/` → 明确为凭证管理目标方向

- **API 变更**: 向前兼容，旧 import 路径暂保留（桥接层）
- **测试**: 无需新增测试，确保现有 import 不破坏即可
