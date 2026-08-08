## ADDED Requirements

### Requirement: breaker/__init__.py 仅做导出

`services/breaker/__init__.py` SHALL 仅包含：
- 包级文档字符串
- `from .service import *` 语句
- `__all__` 列表

所有实现代码（dataclass、async 函数） SHALL 移至 `service.py`。

#### Scenario: __init__.py 仅做导出

- **WHEN** 开发者阅读 `breaker/__init__.py`
- **THEN** 仅包含文档字符串、import 语句和 `__all__` 列表
- **AND** 无任何实现代码

#### Scenario: 实现代码在 service.py

- **WHEN** 开发者需要修改 breaker 的业务逻辑
- **THEN** 应修改 `breaker/service.py`
- **AND** `service.py` 包含所有 dataclass 和 async 函数实现

### Requirement: breaker/service.py 包含所有实现

`services/breaker/service.py` SHALL 包含：
- 所有 dataclass 定义（如 `BreakTask`、`BreakResult` 等）
- 所有 async 函数实现
- 业务逻辑编排

#### Scenario: service.py 是实现层

- **WHEN** breaker 执行爆款拆解任务
- **THEN** 逻辑在 `service.py` 中执行
- **AND** `__init__.py` 仅做转发

### Requirement: 导出符号保持不变

`__all__` 列表 SHALL 导出与重构前相同的公共符号。

#### Scenario: 向后兼容

- **WHEN** 其他代码 `from app.services.breaker import X`
- **THEN** 导出的符号与重构前相同
- **AND** 不破坏现有 import
