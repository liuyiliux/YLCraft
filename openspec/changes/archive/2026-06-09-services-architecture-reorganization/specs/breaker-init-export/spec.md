## ADDED Requirements

### Requirement: breaker/__init__.py 仅做导出，实现放 service.py

`breaker/` 包 SHALL 将所有实现代码（dataclass、async 函数）移至 `service.py`。`__init__.py` MUST 仅包含：
- 包级文档字符串
- `from .service import *` 语句
- `__all__` 列表

#### Scenario: breaker 实现代码在 service.py
- **WHEN** 检查 `breaker/service.py` 是否包含 `BreakdownResult`、`BreakTask`、`AnalysisStatus` 等类定义
- **THEN** 所有数据类（dataclass）和异步业务函数（如 `create_task`、`run_analysis`）在 `service.py` 中定义

#### Scenario: breaker/__init__.py 仅为导出层
- **WHEN** 检查 `breaker/__init__.py`
- **THEN** 该文件不包含超过 5 行的非文档实现代码

### Requirement: breaker/service.py 导出与 __init__.py 兼容

重构后，`from app.services.breaker import X` 和 `from app.services.breaker.service import X` MUST 返回相同的导出符号。

#### Scenario: 两种导入路径等价
- **WHEN** 比较 `from app.services.breaker import *` 和 `from app.services.breaker.service import *`
- **THEN** 两者的 `__all__` 列表完全一致

### Requirement: breaker 现有导入不破坏

重构 SHALL NOT 改变以下任何导入路径的行为：

| 导入路径 | 必须可用 |
|----------|----------|
| `from app.services.breaker import create_task` | 是 |
| `from app.services.breaker import AnalysisStatus` | 是 |
| `from app.services.breaker.service import parse_video_url` | 是 |

#### Scenario: 现有 API 导入仍可用
- **WHEN** 执行任何现有导入语句（见上表）
- **THEN** 不抛出 `ImportError`
