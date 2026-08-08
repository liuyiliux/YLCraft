## Context

### 当前状态

`services/` 目录存在以下结构性问题：

**问题1：xhs_parser 与 platforms/xiaohongshu/ 边界模糊**
- `xhs_parser/` 使用 requests + BeautifulSoup 解析小红书图文（HTML方式）
- `platforms/xiaohongshu/` 使用 httpx 调用小红书 API（API方式）
- 两者功能重叠但分离，breaker/ 等调用方需区分导入路径

**问题2：video/ffmpeg.py 位置不当**
- FFmpeg 封装是视频处理基础设施
- 当前放在 `services/video/ffmpeg.py`，但 core/ 才是基础设施层

**问题3：platform_connection/ 标注旧版但仍在用**
- `platform_connection/` 在 `docs/01-项目概述.md` 标注为"旧版"
- `connectors/social/` 是"新版"目标方向
- 但 platform_connection/ 被 platforms/、download/、crawler/ 广泛依赖

**问题4：breaker/__init__.py 职责膨胀**
- `__init__.py` 包含 ~400 行实现代码（dataclass + async 函数）
- 违反"包自述 API"原则

### 约束

- 必须向前兼容：旧 import 路径暂保留（桥接层）
- breaker/ 等调用方不能立即全部改写
- 数据库迁移不使用（仅文件操作）

## Goals / Non-Goals

**Goals:**
- 统一 xhs_parser 到 platforms/xiaohongshu/，对内清晰、对外统一入口
- 将 FFmpeg 基础设施迁移到 core/
- 为 platform_connection/ 到 connectors/social/ 的迁移提供明确路径
- 重构 breaker/__init__.py，回归"包自述 API"原则

**Non-Goals:**
- 不在本次删除 platform_connection/（保留 + 文档）
- 不迁移 connectors/social/ 的现有功能
- 不修改 services/ai/（已重构完成）
- 不修改数据库 schema

## Decisions

### Decision 1: xhs_parser 合并路径选择路径B

**选择**: 将 xhs_parser 逻辑迁移到 `platforms/xiaohongshu/parser.py`，而非直接合并到 `XiaohongshuClient`

**原因**:
- 路径A（直接合并到 Client）：Client 职责膨胀（搜索+详情+HTML解析混在一起）
- 路径B（parser.py 内部承载）：XiaohongshuClient 保持"搜索+详情 API"职责，parser.py 封装 HTML 解析
- 路径B 更符合"每个包自述 API"原则，且对 breaker/ 等调用方破坏性最小

**结构变化**:
```
services/platforms/xiaohongshu/
├── __init__.py       → 导出 XiaohongshuClient
├── client.py         → 搜索+详情（API模式）
├── parser.py         → HTML解析 ← xhs_parser 逻辑并入此处
├── search.py         → 搜索实现
├── note.py           → 详情实现（API）
└── apis.py           → API端点定义

services/xhs_parser/  → 桥接层（最终删除）:
├── __init__.py       → from platforms.xiaohongshu.parser import ...
└── service.py        → 桥接代码
```

### Decision 2: FFmpeg 迁移到 core/

**选择**: 将 `services/video/ffmpeg.py` 迁移到 `core/ffmpeg.py`

**原因**:
- FFmpeg 封装是视频处理的基础设施，不属于任何业务领域
- core/ 目录存放 config/task_queue/ws_manager 等基础设施
- video/ 目录应只负责视频解析/下载等业务逻辑

### Decision 3: platform_connection/ 保留 + 标注迁移路径

**选择**: 保留 platform_connection/，在 __init__.py 添加 deprecation 文档

**原因**:
- platform_connection/ 被广泛依赖，立即删除破坏性大
- connectors/social/ 是"新版"目标方向，但凭证管理逻辑尚未完全迁移
- 采用渐进式迁移：阶段1文档 → 阶段2新增能力 → 阶段3迁移调用方 → 阶段4废弃

### Decision 4: breaker/__init__.py 重构

**选择**: 将 __init__.py 中的实现代码移入 service.py，__init__.py 仅做导出

**原因**:
- 与 services/ai/ 的模式保持一致（service.py 做实现，__init__.py 做导出）
- 符合"包自述 API"原则

## Risks / Trade-offs

| 风险 | 描述 | 缓解 |
|------|------|------|
| breaker/ 兼容性问题 | xhs_parser 桥接层可能影响 breaker/ 调用 | 分阶段迁移，先保留旧入口 |
| FFmpeg 引用广泛 | video/ffmpeg.py 可能被多处引用 | 更新所有 import 语句 |
| platform_connection/ 长期存在 | 旧代码可能永远不迁移 | 文档明确废弃时间线 |

## Migration Plan

### Phase 1: xhs_parser 合并
1. 创建 `platforms/xiaohongshu/parser.py`（从 xhs_parser/service.py 迁移逻辑）
2. 创建 `xhs_parser/` 桥接层
3. breaker/ 等调用方暂时不改
4. 验证功能正常后，更新 breaker/ import
5. 删除 xhs_parser/

### Phase 2: FFmpeg 迁移
1. 将 `services/video/ffmpeg.py` 复制到 `core/ffmpeg.py`
2. 更新 `services/video/__init__.py` 导出（从 core 导入）
3. 更新所有引用 video/ffmpeg 的 import
4. 删除 `services/video/ffmpeg.py`

### Phase 3: platform_connection/ 标注
1. 在 `platform_connection/__init__.py` 添加 deprecation 文档
2. 在 `connectors/social/` 中明确凭证管理能力

### Phase 4: breaker/__init__.py 重构
1. 将 __init__.py 实现代码移入 service.py
2. __init__.py 仅保留导出语句

## Open Questions

1. **xhs_parser 桥接层保留多久？** 建议 1 个月，之后可安全删除
2. **FFmpeg 在 core/ 的最终位置？** `core/ffmpeg.py`（与 config/task_queue 同级）
3. **platform_connection/ 废弃时间线？** 待君确认，建议 3 个月
