## Requirements

### Requirement: 每个 Python 包的 __init__.py 必须导出公共 API
`services/` 下每个子包的 `__init__.py` MUST 包含至少一个实际的 `from .module import Symbol` 语句和对应的 `__all__` 列表。空文件或纯注释的 `__init__.py` SHALL NOT 存在。

#### Scenario: 空 __init__.py 的清理
- **WHEN** 发现 `__init__.py` 仅包含注释或文档字符串（如 `"""YLCraft — Image Backend 实现"""` 且无任何导出）
- **THEN** MUST 补充至少导入该包的核心 Service 类或核心函数

#### Scenario: 公共 API 的最小导出
- **WHEN** 一个包对外只提供一个 Service 类作为入口
- **THEN** `__init__.py` SHALL 包含 `from .service import FooService` 和 `__all__ = ["FooService"]`

### Requirement: 空目录必须删除
任何不含 `.py` 文件（`__pycache__` 除外）的空子目录 SHALL 被删除。仅在 `__init__.py` 文件被删除后才可删除空目录。

#### Scenario: 空目录的清理
- **WHEN** 发现 `services/video_gen/`、`core/contracts/`、`connectors/ai/` 为空目录
- **THEN** MUST 删除这些目录及其 `__pycache__` 残留

### Requirement: services/ 必须是合法 Python 包
`services/` 目录 MUST 包含 `__init__.py` 文件，使其成为一个合法的 Python 包。该文件 MAY 为空但 SHOULD 包含包级文档字符串。

#### Scenario: services/__init__.py 缺失
- **WHEN** `services/__init__.py` 不存在
- **THEN** MUST 创建该文件，内容为包级文档字符串 `"""YLCraft — 业务服务层"""`
