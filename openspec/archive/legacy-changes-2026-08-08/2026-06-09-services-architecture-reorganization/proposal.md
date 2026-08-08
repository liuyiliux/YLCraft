## Why

`services/` 目录下存在多个结构性问题，阻碍开发效率与代码可维护性：

1. **包导出不一致**：`services/__init__.py` 与 `breaker/__init__.py` 仅含注释/文档字符串，无实际导出
2. **孤立文件**：`image_editor/` 本可归入 `asset/` 或独立领域，却单独存在
3. **包边界模糊**：部分服务职责重叠（如 `platforms/` vs `platform_connection/`）
4. **平台目录膨胀**：`platforms/` 下按平台划分，但各平台间存在重复代码模式

AI 领域已完成重构（`services/ai/` 统一），其余模块应遵循相同原则梳理。

## What Changes

1. **修复 P0 问题**
   - 补充 `services/__init__.py` 的实际导出
   - 补充 `breaker/__init__.py` 的实际导出

2. **包边界整理**
   - `platforms/` 与 `platform_connection/` 职责合并或明确划分
   - `image_editor/` 归属决策（归入 `asset/` 或保留为独立领域）

3. **__init__.py 规范化**
   - 检查所有 `services/` 子包的 `__init__.py`，确保有实际导出
   - 消除"注释壳"包

4. **规范落地**
   - 将架构指导原则（`YLCraft-架构指导原则.md`）中的规则转化为可执行规范
   - 确保新增代码遵循领域优先、Protocol > 继承、包自述API等原则

## Capabilities

### New Capabilities

- `services-init-export`: 修复 `services/__init__.py` 的公共 API 导出
- `breaker-init-export`: 修复 `breaker/__init__.py` 的公共 API 导出
- `package-boundary-review`: 审查并明确 `platforms/` 与 `platform_connection/` 的边界

### Modified Capabilities

- `package-boundaries`: 已有规范，本次为执行落地（补充更多场景判定）

## Impact

- **涉及包**: `services/`, `services/breaker/`, `services/platforms/`, `services/platform_connection/`, `services/image_editor/`
- **API 变更**: 部分 `__init__.py` 的导出可能变化（但应向前兼容）
- **测试**: 无需新增测试，确保现有 import 不破坏即可
