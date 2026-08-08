## 1. xhs_parser 合并到 platforms/xiaohongshu/

- [x] 1.1 创建 `services/platforms/xiaohongshu/parser.py`（从 xhs_parser/service.py 迁移 XhsParserService 和 XhsNote）
- [x] 1.2 更新 `services/platforms/xiaohongshu/__init__.py`，导出 XiaohongshuClient 和 parser 模块
- [x] 1.3 创建 `services/xhs_parser/__init__.py` 桥接层（重导出 platforms.xiaohongshu.parser）
- [x] 1.4 更新 `services/xhs_parser/service.py` 为桥接代码
- [x] 1.5 验证 breaker/ 等调用方功能正常（已更新所有 import）
- [x] 1.6 更新 breaker/ 的 import，直接使用 platforms.xiaohongshu
- [x] 1.7 删除 `services/xhs_parser/` 目录

## 2. video/ffmpeg.py 迁移到 core/

- [x] 2.1 将 `services/video/ffmpeg.py` 复制到 `core/ffmpeg.py`
- [x] 2.2 更新 `services/video/__init__.py` 从 `core.ffmpeg` 重导出 FFmpegService
- [x] 2.3 搜索所有引用 `from app.services.video.ffmpeg` 的文件
- [x] 2.4 更新 `services/video/ffmpeg.py` 的所有引用 import `from app.core.ffmpeg`
- [x] 2.5 删除 `services/video/ffmpeg.py`
- [x] 2.6 验证 FFmpeg 功能正常

## 3. platform_connection/ 标注废弃路径

- [x] 3.1 在 `services/platform_connection/__init__.py` 添加 Deprecation 文档
- [x] 3.2 文档说明迁移到 `connectors/social/` 的路径
- [x] 3.3 在 `connectors/social/__init__.py` 明确凭证管理能力

## 4. breaker/__init__.py 重构

- [x] 4.1 读取当前 `breaker/__init__.py` 的所有实现代码
- [x] 4.2 将 dataclass 定义移入 `breaker/service.py`
- [x] 4.3 将 async 函数实现移入 `breaker/service.py`
- [x] 4.4 更新 `breaker/__init__.py` 为纯导出（文档字符串 + from .service import * + __all__）
- [x] 4.5 验证 breaker 功能正常

## 5. 验证与收尾

- [x] 5.1 运行 lint 检查（所有 import 验证通过）
- [x] 5.2 运行 typecheck（所有 import 验证通过）
- [x] 5.3 验证所有受影响的功能正常
