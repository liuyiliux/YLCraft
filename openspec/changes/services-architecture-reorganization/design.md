## Context

`services/` 目录包含约30个领域包。AI领域（`services/ai/`）已完成重构，遵循"领域优先、Protocol > 继承、包自述API"原则。但其余模块存在以下结构性问题：

**当前问题一览**：

| 问题 | 位置 | 说明 |
|------|------|------|
| **P0**: `__init__.py` 仅含文档字符串 | `services/__init__.py` | 无实际导出，破坏包级导入一致性 |
| **P0**: 实现代码在 `__init__.py` | `breaker/__init__.py` | ~400行实现代码，应用逻辑应放 `service.py` |
| **P0**: 导出不完整 | `breaker/__init__.py` | 只导入了部分符号（通过 `service.py` 补全） |
| **P1**: `service.py` 仅做转发 | `breaker/service.py` | 自身无实现，纯转发自 `__init__.py` |
| **P1**: 包边界模糊 | `platforms/` vs `platform_connection/` | 前者管爬虫客户端，后者管凭证，职责重叠但未明确 |
| **P1**: 注释壳包 | 多处 | 部分 `__init__.py` 仅有注释无导出 |

**被影响模块**：breaker, platforms, platform_connection, image_editor, cookies

---

## Goals / Non-Goals

**Goals:**
- 修复所有 P0 结构问题（使 `services/` 成为合法 Python 包）
- 使每个 `__init__.py` 正确导出公共 API（不是转发）
- 将实现代码从 `__init__.py` 移到 `service.py`
- 明确 `platforms/` 与 `platform_connection/` 的边界

**Non-Goals:**
- 不重写任何业务逻辑代码
- 不改变任何公开 API 的函数签名
- 不移动任何文件的磁盘路径（仅修改 `__init__.py` 内容）
- 不新增功能或修改功能行为

---

## Decisions

### Decision 1: `breaker/` 结构重构

**选择**: 将 `breaker/__init__.py` 中的实现代码移入 `service.py`，`__init__.py` 仅做导出

**原因**:
- `__init__.py` 当前有约400行实现代码（dataclass + async 函数），违反"包自述API"原则
- `service.py` 纯做转发，实际逻辑在 `__init__.py`
- 正确模式应如 `services/ai/`：实现放 `service.py`，导出放 `__init__.py`

**替代方案**:
- 保持现状（拒绝）：违反架构指导原则
- 完全重构 breaker（拒绝）：工作量大，且 breaker 业务逻辑本身没问题

### Decision 2: `services/__init__.py` 补充导出

**选择**: 补充包级公共 API 导出

**原因**:
- 当前仅有文档字符串，无导出
- 补充导出不破坏现有代码（无现有依赖）
- 可导出一个 `ServiceLocator` 或直接导出各领域的主入口

### Decision 3: `platforms/` vs `platform_connection/` 边界明确

**选择**: 保持两者分离，明确职责划分

| 包 | 职责 | 边界 |
|----|------|------|
| `platform_connection/` | 凭证生命周期管理（创建/更新/删除凭证，PlatformConnection 表） | 管理"能不能访问" |
| `platforms/` | 平台 API 客户端（爬虫工厂，BasePlatformClient） | 管理"怎么访问" |

**原因**:
- 两者职责已较清晰，无需合并
- `platform_connection` 处理认证（Cookie/Token），`platforms` 处理具体 API 调用
- 只需文档化边界即可

### Decision 4: `image_editor/` 归属

**选择**: 保留为独立领域包（不做迁移）

**原因**:
- `image_editor` 有独立服务 `add_text_watermark`, `add_image_watermark`
- 不同于普通素材管理（`asset/`），它是"图片编辑"领域
- 虽然功能简单，但领域独立

---

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **导入路径变化破坏现有代码** | 所有修改仅在 `__init__.py` 层面，不移动任何 `.py` 文件；实现移入 `service.py` 时保持函数签名完全一致 |
| **breaker 模块导入顺序问题** | `breaker/__init__.py` 依赖 `ai.types` 等，确保 `ai` 先初始化；这已是现状，无新增风险 |
| **services 包级导出过多** | 只导出各领域的单例访问函数（如 `get_ai_service`），避免成为上帝文件 |

---

## Migration Plan

1. **Phase 1: 修复 `services/__init__.py`**
   - 创建 `services/__init__.py`，补充包级导出
   - 验证：`python -c "from app.services import X"` 不报错

2. **Phase 2: 重构 `breaker/`**
   - 将 `__init__.py` 中的 dataclass + 函数移入 `service.py`
   - 让 `__init__.py` 从 `service.py` 导入并重新导出
   - 验证：所有现有 import 语句仍可用

3. **Phase 3: 规范化其余 `__init__.py`**
   - 扫描所有 `services/*/__init__.py`
   - 对仅有注释的包，补充实际导出
   - 验证：每个包的 `__all__` 有意义内容

4. **Phase 4: 文档化边界**
   - 在 `platforms/` 和 `platform_connection/` 的 `__init__.py` 补充职责说明

---

## Open Questions

1. **是否需要 `services/` 包级导出？** 如果要导出所有子包的主入口，会形成强耦合。当前方案：只导出辅助工具类，具体服务让调用方从子包导入。

2. **`breaker/` 的 dataclass 是否移到 `types.py`？** 当前 `dataclass` 在 `__init__.py` 内聚，但如规模增大可考虑分离。暂不移动，保持现状。
