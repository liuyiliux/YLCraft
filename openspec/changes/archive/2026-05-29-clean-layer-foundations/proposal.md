## Why

AI 服务层重整完成后，代码库中仍存在 20+ 处结构性债务：P0 级别的 broken imports 会导致运行时崩溃，P1 级别的孤立文件/空目录/空 `__init__.py` 模糊了包边界。这次变更系统性清理 services/ 层的基础结构问题，使其符合 `docs/architecture/YLCraft-架构指导原则.md` 中定义的 10 条原则。

## What Changes

- **修复 Broken Imports（P0）**：`story/generator.py` 和 `api/v1/story.py` 中引用不存在的 `app.services.backend_registry`，改为正确的 `services/ai/` 入口
- **补充 services/__init__.py（P0）**：`services/` 目录缺少 `__init__.py`，不是一个合法的 Python 包
- **归位孤立文件（P1）**：`services/image_editor.py` 和 `services/ffmpeg_service.py` 作为顶层 `.py` 文件，违反领域优先原则
- **建立包边界（P1）**：11 个 `__init__.py` 仅含注释无导出，需明确公共 API
- **清理空目录（P1）**：`services/video_gen/`、`core/contracts/`、`connectors/ai/` 三个空目录残留
- **统一 connector 层**：`connectors/` 和 `services/platforms/` 功能重叠，明确划分职责

## Capabilities

### New Capabilities
- `broken-imports`: 修复所有引用不存在模块的导入语句，确保代码可以正常 import
- `orphan-files`: 将 services/ 下的孤立顶层 .py 文件归入合适的领域包
- `package-boundaries`: 为所有包建立清晰的 `__init__.py` 公共 API 导出

### Modified Capabilities
- `backend-conventions`: 明确 services/ 目录下文件组织的领域优先原则（原规范偏重 DB/API 层）

## Impact

- Affected code: `services/story/generator.py`, `api/v1/story.py`, `services/__init__.py`, `services/image_editor.py`, `services/ffmpeg_service.py`, 11 个 `__init__.py`, `connectors/` 目录
- Breaking: `from app.services.backend_registry import BackendManager` → 改为正确路径（它本来就不存在，实质上是修复而非破坏）
- Risk: 低。所有变更都是结构整理，不涉及业务逻辑修改
