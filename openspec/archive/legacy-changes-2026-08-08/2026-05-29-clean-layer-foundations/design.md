## Context

AI 服务层重整（Phase 1-6）完成后，`services/llm/`、`services/image/`、`services/video_gen/`、`core/contracts/` 已删除。但代码库扫描发现还有 20+ 处结构性债务散布在其他模块中。本次变更聚焦清理这些基础层面的问题，为后续各领域包的整理铺平道路。

当前状态（基于 `docs/architecture/YLCraft-架构指导原则.md` 诊断）：
- P0: 2 处引用不存在的 `app.services.backend_registry` 模块
- P0: `services/__init__.py` 缺失
- P1: 2 个孤立顶层 `.py` 文件（`image_editor.py`, `ffmpeg_service.py`）
- P1: 3 个空目录（`services/video_gen/`, `core/contracts/`, `connectors/ai/`）
- P1: 11 个仅含注释的 `__init__.py`
- P2: `connectors/` vs `services/platforms/` 职责重叠待明确

## Goals / Non-Goals

**Goals:**
- 修复所有 broken imports，确保代码可正常 import
- 补充 `services/__init__.py`，使 `services/` 成为合法 Python 包
- 将孤立 `.py` 文件归入合适的领域包
- 为服务层所有包建立明确的 `__init__.py` 导出
- 清理所有空目录残留
- 明确 `connectors/` 和 `services/platforms/` 的职责边界

**Non-Goals:**
- 不深入重构各领域包的内部实现（如 breaker, clip, story 的内部逻辑）
- 不解决跨服务耦合问题（64 个交叉引用留待后续专项处理）
- 不修改业务逻辑

## Decisions

### D1: `image_editor.py` 归属

**选择**：独立为 `services/image_editor/` 包（`service.py` + `__init__.py`）

**原因**：图片编辑（加水印、裁剪、滤镜）是独立领域，非 AI Backend 子类型。它有自己的 API 路由（`api/v1/image_editor.py`），有自己的功能边界。按照"领域优先"原则，应作为一个独立包存在。

**备选方案**：
- 移入 `services/ai/` — 拒绝。图片编辑可能使用 AI 但自身不是 AI Backend
- 保持顶层 `.py` 文件 — 拒绝。违反原则 9（文件组织三不原则）

### D2: `ffmpeg_service.py` 归属

**选择**：移入已有包 `services/video/`，重命名为 `ffmpeg.py`

**原因**：FFmpeg 能力是视频处理的基础设施。`services/video/` 目录已存在（含 `parsers/` 子模块），是最自然的归属。函数重命名时保持原接口不变。

**备选方案**：
- 新建 `services/ffmpeg/` 包 — 过度拆分，仅一个文件不值得建包
- 移入 `services/clip/` — FFmpeg 不仅用于剪辑，视频解析也依赖它

### D3: Broken Import 修复方式

**选择**：`story/generator.py` 和 `api/v1/story.py` 中的 `from app.services.backend_registry import BackendManager` 改为 `from app.services.ai import get_ai_service`，使用 `get_ai_service()` 单例

**原因**：`BackendManager` 已不存在，AI 调用统一入口是 `services/ai/`。`story` 模块需要的是 AI 调用能力而非后端管理能力。

### D4: `__init__.py` 导出策略

**选择**：每个包的 `__init__.py` 必须导出其公共类/函数，格式为：
```python
"""简短说明"""
from .service import FooService
__all__ = ["FooService"]
```

**原因**：符合原则 2（公共 API 显式导出）和原则 10（导入路径稳定）。外部调用方使用包级导入而非深层穿透。

### D5: `connectors/` vs `services/platforms/` 职责划分

| 维度 | `connectors/` | `services/platforms/` |
|------|--------------|----------------------|
| 职责 | 平台 API 客户端（底层 HTTP 调用） | 平台业务路由（上层业务逻辑） |
| 使用者 | `services/platforms/` 等 | API 路由层 |
| 示例 | `BilibiliClient.get_user_videos()` | `platform/bilibili/routes.py` 的 REST 端点 |

两者是分层关系而非竞争关系。本次变更仅在代码注释中明确边界，不做物理目录调整。未来如果发现 `connectors/` 中的 platform client 在业务层有对应封装，应优先放入 `services/platforms/`。

## Risks / Trade-offs

- [Risk] 修改 `ffmpeg_service.py` 的 import 路径可能遗漏某处引用 → 先 `rg` 全量搜索所有引用位置再迁移
- [Risk] `story/generator.py` 的 `BackendManager` 用法可能涉及特有的 LLM 调用模式 → 迁移后需确认 `chat()` 接口兼容
- [Trade-off] `connectors/ai/` 空目录和 `connectors/base/ai_base.py` 的清理延后到 connector 层专项整理 → 本期只标记不删除
