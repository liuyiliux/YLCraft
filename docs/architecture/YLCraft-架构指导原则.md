# YLCraft 架构指导原则

> **定位**：全项目通用的架构设计手册，作为所有重构和新增代码的判断依据。
> **适用对象**：任何参与 YLCraft 后端开发的开发者或 AI Agent。
> **最后更新**：2026-05-29
> **版本**：v1.0

---

## 一、核心原则

### 原则 1：领域优先，而非技术分层

**规则**：按业务领域组织代码，不按技术角色（model/view/controller）分层。

```
✅ 正确的组织方式（领域驱动）:
  services/ai/          # AI 领域：Backend + 类型 + 编排 + 业务
  services/comfyui/     # ComfyUI 领域：客户端 + 连接池 + 工作流
  services/breaker/     # 爆款拆解领域
  services/asset/       # 素材资产管理领域

❌ 错误的反模式（技术分层）:
  services/models/      # 所有模型放一起
  services/controllers/ # 所有控制器放一起
  services/utils/       # 所有工具函数放一起
```

**判断标准**：如果要改一个功能，能否在一个目录内完成 80% 的工作？能 → 组织正确；不能 → 边界模糊。

---

### 原则 2：每个包自描述自己的公共 API

**规则**：每个 Python 包的 `__init__.py` 必须明确导出公共接口，不能是空文件或纯注释。

```python
# ✅ 正确：明确导出
"""YLCraft — AI 服务统一入口"""
from app.services.ai.service import AIService, get_ai_service
__all__ = ["AIService", "get_ai_service"]

# ❌ 错误：空壳
"""YLCraft — Image Backend 实现层"""  # 没有导出任何东西
```

**反模式清单**（需要修复）：
- 仅含注释的 `__init__.py`
- 空的 `__init__.py`
- `from .submodule import *`（失去显式控制）

---

### 原则 3：类型只有一个归宿

**规则**：每个领域的数据类型定义在一个文件中，不允许在不同位置定义同名或同义类型。

```
✅ 正确:
  services/ai/types.py    # AI 所有类型：枚举、DataClass、Protocol、工具函数

❌ 错误（已清理）:
  core/contracts/types.py   # 与 ai/types.py 重复的类型定义
  services/image/base.py    # 另一套 BaseImageBackend
  services/video_gen/base.py # 另一套 BaseVideoBackend
```

**检查方法**：搜索同名的 class/dataclass 定义，确认只有一处定义。

---

### 原则 4：Protocol 优于继承

**规则**：跨包接口使用 `typing.Protocol`（鸭子类型），不使用 ABC 继承体系。继承只在同一个领域包内部使用。

```python
# ✅ Protocol：调用方只关心"能做什么"，不关心"是什么"
class ImageBackend(Protocol):
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...

# AI Backend 实现各自独立构造，无需统一基类
class GeminiImageBackend:        # 无继承
    def __init__(self, connector): ...
class ComfyUIImageBackend:       # 无继承
    def __init__(self, config): ...

# ❌ ABC：强制继承，初始化参数差异导致 super().__init__() 困难
class BaseImageBackend(ABC):     # 子类必须接受 (name, model, api_key, ...)
    def __init__(self, name, model, api_key, api_base, cost):
        ...
```

**例外**：同一领域包内部可以使用模板方法模式（如 `video/base.py` 中的 `BaseVideoBackend`），但不能跨包继承。

---

### 原则 5：三个明确层次

**规则**：代码按调用关系分为三个层次，不允许跨层反向依赖。

```
┌──────────────────────────────────────────────┐
│  Layer 1: API 路由层 (api/v1/)                │
│  职责：HTTP 请求解析、参数验证、响应构造       │
│  不包含：业务逻辑、数据库操作                  │
├──────────────────────────────────────────────┤
│  Layer 2: 业务服务层 (services/xxx/)           │
│  职责：业务流程编排、调用 AI/数据库/外部服务    │
│  不包含：HTTP 协议相关内容                     │
├──────────────────────────────────────────────┤
│  Layer 3: 基础设施层 (核心能力)                │
│  services/ai/backends/    # AI Backend 实现   │
│  db/                      # 数据库模型 + 连接   │
│  connectors/              # 外部平台客户端      │
├──────────────────────────────────────────────┤
│  横向共享：core/           # 配置、中间件、横切  │
└──────────────────────────────────────────────┘
```

**依赖规则**：
- Layer 1 → Layer 2 ✅
- Layer 2 → Layer 3 ✅
- Layer 3 → Layer 1 ❌（基础设施层不能依赖 API 层）
- Layer 3 → Layer 2 ❌（基础设施层不能依赖业务服务层）
- Layer 2 ↔ Layer 2 ⚠️（跨服务依赖需明确文档化，尽量用事件/接口解耦）

---

### 原则 6：不兼容，直接删

**规则**：重构时不做兼容层、不保留旧代码、不留废弃标记。旧路径直接删除，调用方同步更新。

```python
# ✅ 正确做法
# 旧: from app.services.llm.manager import get_manager  → 直接改
# 新: from app.services.ai import get_ai_service
# 旧文件: services/llm/manager.py → 直接删除

# ❌ 错误做法
# 保留 manager.py 加一行: get_manager = get_ai_service  # 兼容层
# 在旧文件上加 # DEPRECATED 注释但保留文件
```

**原因**：兼容层是技术债务放大器。今天 1 行兼容代码，三个月后变成 10 行边界条件。

---

### 原则 7：空目录和孤立文件必须清理

**规则**：
- 空目录 → 立即删除（含 `__pycache__`）
- 目录仅剩 `__init__.py` → 确认无外部引用后删除整个目录
- 顶层孤立的 `.py` 文件 → 移入合适的领域包

```
当前待清理项:
  ✗ services/video_gen/         # 空目录（无任何文件）
  ✗ core/contracts/             # 空目录（无任何文件）
  ✗ connectors/ai/              # 空目录（无任何文件）
  ✗ services/image_editor.py    # 孤立文件，应归入 services/ai/ 或独立包
  ✗ services/ffmpeg_service.py  # 孤立文件，应归入 services/video/ 或 services/clip/
```

---

### 原则 8：注册模式统一

**规则**：所有需要"按名称查找实现"的场景，使用统一的 Registry + Router 模式。

```
Registry（注册中心）         Router（路由器）
    启动时一次性加载           每次请求时选择
    · 从 DB/YAML 读取配置      · 按名称/模型/能力匹配
    · 实例化所有 Backend       · 健康检查 + 自动降级
    · 按 key 分组存储          · 返回最佳匹配结果
```

**不要**：在每个 API 端点里写 `if provider == "gemini": ... elif provider == "openai": ...` 的分支判断。

---

### 原则 9：文件组织三不原则

| 不要 | 因为 |
|------|------|
| 不要把不同领域的代码放同一文件 | 违反领域优先原则 |
| 不要把同一领域的代码拆到不同目录 | 违反内聚原则（如旧的 llm/image/video_gen 分裂） |
| 不要让一个文件超过 500 行 | 超过 500 行说明承担了过多职责 |

**判断标准**：一个文件能不能在 30 秒内向新加入的开发者解释清楚它负责什么？

---

### 原则 10：导入路径稳定

**规则**：公开 API 通过包的 `__init__.py` 导出，外部调用方使用包级导入，不穿透到内部模块。

```python
# ✅ 推荐：包级导入
from app.services.ai import get_ai_service, AIService
from app.services.comfyui import ComfyUIImageBackend

# ⚠️ 可接受但脆弱：深层导入（内部重构会破坏）
from app.services.ai.backends.image.gemini import GeminiImageBackend

# ❌ 禁止：穿透多个包的内部实现
from app.services.ai.backends.image.gemini import _parse_response
```

**原因**：包级导入是稳定接口，内部路径变化时只需要改 `__init__.py`。

---

## 二、目录结构规范

### 2.1 backend/app/ 顶层划分

| 目录 | 作用 | 可以放什么 |
|------|------|-----------|
| `api/` | HTTP 路由层 | 路由文件、请求/响应 Schema、依赖注入 |
| `services/` | 业务服务层 | 领域服务包，每个领域一个子目录 |
| `core/` | 基础设施层 | 配置、中间件、WS 广播、安全 |
| `db/` | 数据层 | ORM 模型、数据库连接、迁移 |
| `connectors/` | 外部连接器 | 平台 API 客户端、第三方集成 |

### 2.2 services/ 下领域包的标准结构

```
services/{domain}/
├── __init__.py       # 公共 API 导出（必须有实际导出）
├── service.py        # 核心业务逻辑（可选）
├── types.py          # 领域专属类型（可选，当前领域专有）
├── backends/         # 如有多种实现（如 AI）
│   ├── registry.py
│   ├── router.py
│   └── ...
└── tools/            # 工具的专用工具函数（可选）
```

### 2.3 不用建子包的情况

| 情况 | 处理 |
|------|------|
| 只有 1 个 service 文件 | 直接放领域根目录，不建多层 |
| 3 个以下文件 | 保持扁平，不需要 `api/` `models/` 子目录 |
| 纯数据定义 | 放在 `types.py`，不单独建 `models.py`（除非是 DB 模型） |

---

## 三、重构检查清单

在对任何模块做结构整理前，按以下清单逐项确认：

- [ ] **引用全貌**：用 `rg "from app\.services\.{module}"` 搜索所有引用位置
- [ ] **是否有重复定义**：搜索同名类/函数是否在多处定义
- [ ] **空的 __init__.py**：每个 `__init__.py` 都应有实际导出
- [ ] **空目录**：检查是否有仅含 `__pycache__` 的目录
- [ ] **孤立文件**：顶层 `.py` 文件是否有更合适的归属
- [ ] **broken imports**：搜索不存在的模块引用（如 `from app.services.backend_registry import ...`）
- [ ] **跨层依赖**：基础设施层是否反向依赖了 API 层或业务层
- [ ] **文件长度**：是否有超过 500 行的文件
- [ ] **不需要兼容层**：重构后旧代码直接删除，不保留

---

## 四、当前技术债务（2026-05-29）

扫描发现的结构性问题，按优先级排列：

### P0：会导致运行时错误

| # | 问题 | 位置 |
|---|------|------|
| 1 | `from app.services.backend_registry import BackendManager` — 模块不存在 | `services/story/generator.py`, `api/v1/story.py` |
| 2 | `services/__init__.py` 缺失 | `services/` 目录 |

### P1：包边界混乱

| # | 问题 | 位置 |
|---|------|------|
| 3 | `image_editor.py` 和 `ffmpeg_service.py` 是孤立顶层文件 | `services/` 根目录 |
| 4 | 11 个 `__init__.py` 仅含注释，无实际导出 | 见扫描报告 |
| 5 | `services/video_gen/` 空目录 | 残留 |
| 6 | `core/contracts/` 空目录 | 残留 |
| 7 | `connectors/ai/` 空目录 | 残留 |

### P2：代码质量问题

| # | 问题 | 说明 |
|---|------|------|
| 8 | 64 个 services 文件互有交叉引用 | 依赖关系需要梳理 |
| 9 | `connectors/` 和 `services/platforms/` 两套平台集成体系 | 职责重叠，需明确划分 |

---

## 五、反面模式速查

以下模式一旦出现，立即标记为技术债务：

| 模式 | 示例 | 危害 |
|------|------|------|
| **上帝文件** | 一个 .py 超过 800 行 | 无法定位、测试困难 |
| **幽灵目录** | 空目录或仅含空 `__init__.py` | 误导开发者、污染 import 路径 |
| **僵尸导入** | `import X` 但 X 不存在 | 运行时崩溃 |
| **平行宇宙** | 两套代码做同一件事 | 如旧的 llm/ + image/ + video_gen/ |
| **反向依赖** | 底层模块 import 上层 | 循环引用风险 |
| **兼容层** | `old_func = new_func` | 技术债务放大器 |
| **深层穿透** | `from a.b.c.d import Class`，跨 4 层包 | 接口不稳定 |
| **__init__.py 黑洞** | `__init__.py` 只有注释 | API 边界不可见 |

---

*本文档是 YLCraft 架构演进的指导手册，应作为所有代码审查和重构决策的第一参考。每完成一轮架构整理后，更新第四章的技术债务清单。*
