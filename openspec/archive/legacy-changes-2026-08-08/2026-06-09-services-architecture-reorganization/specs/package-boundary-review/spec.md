## ADDED Requirements

### Requirement: platforms/ 与 platform_connection/ 职责边界明确

两个包的 `__init__.py` MUST 包含文档字符串，明确说明各自职责：

| 包 | 职责描述 |
|----|----------|
| `platform_connection/` | 管理各平台的凭证生命周期（Cookie/API Key/OAuth Token），唯一凭证存储位置为 `PlatformConnection` 表 |
| `platforms/` | 提供各平台 API 客户端（爬虫工厂），封装具体平台的数据获取逻辑 |

#### Scenario: platform_connection 职责明确
- **WHEN** 查看 `services/platform_connection/__init__.py`
- **THEN** 文档字符串包含"凭证"、"Cookie"、"API Key"、"PlatformConnection 表"等关键词

#### Scenario: platforms 职责明确
- **WHEN** 查看 `services/platforms/__init__.py`
- **THEN** 文档字符串包含"平台客户端"、"爬虫工厂"、"BasePlatformClient"等关键词

### Requirement: platforms/ 与 platform_connection/ 不得相互导入业务逻辑

`platform_connection/` SHALL NOT 导入 `platforms/` 中任何平台特定客户端；反之亦然。两包仅通过以下方式交互：
- 运行时：`platforms/` 的客户端从 `platform_connection/` 获取凭证
- 类型引用：共享的数据模型可引用 `PlatformConnection` 类型

#### Scenario: 无循环依赖
- **WHEN** 执行 `python -c "from app.services.platforms import BasePlatformClient; from app.services.platform_connection import PlatformConnectionService"`
- **THEN** 不抛出 `ImportError` 或 `CircularImportError`

### Requirement: platform_connection/ 不得依赖 platforms/ 的客户端

`platform_connection/` SHALL NOT 在业务逻辑中直接实例化或调用 `platforms/` 下的任何客户端类。

#### Scenario: platform_connection 独立于 platforms
- **WHEN** 检查 `services/platform_connection/` 中所有 `.py` 文件的 import 语句
- **THEN** 不存在 `from app.services.platforms.` 开头的导入
