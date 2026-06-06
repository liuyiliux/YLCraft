## ADDED Requirements

### Requirement: services/__init__.py 必须导出公共 API

`services/` 包 SHALL 包含 `__init__.py` 文件，且该文件 MUST 导出至少以下辅助工具或基础组件：

- `get_services_info()` — 返回所有已注册服务的元信息（名称、描述、入口路径）
- 或导出 `ServiceLocator` 类（如果存在）

#### Scenario: services 包可正常导入
- **WHEN** 执行 `from app.services import get_services_info`
- **THEN** 不抛出 `ModuleNotFoundError` 或 `ImportError`

#### Scenario: services 包是合法 Python 包
- **WHEN** Python 解释器加载 `app.services` 模块
- **THEN** `services/__init__.py` 被成功执行

### Requirement: services/__init__.py 不得包含业务实现

`services/__init__.py` SHALL NOT 包含任何业务逻辑实现（Service 类、爬虫逻辑、AI Backend 等）。该文件仅用于：
- 包级文档字符串
- 跨子包的工具函数或类
- 导入子包入口函数并重新导出

#### Scenario: __init__.py 不包含实现
- **WHEN** 检查 `services/__init__.py` 内容
- **THEN** 不存在超过 50 行的非文档、非注释代码
