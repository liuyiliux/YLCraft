## ADDED Requirements

### Requirement: xhs_parser 逻辑并入 platforms/xiaohongshu/parser.py

`services/xhs_parser/` 的核心解析逻辑 SHALL 迁移到 `services/platforms/xiaohongshu/parser.py`，作为 XiaohongshuClient 的内部模块。

#### Scenario: parser.py 承载 XhsParserService 逻辑

- **WHEN** 调用方需要解析小红书图文链接
- **THEN** `platforms/xiaohongshu/parser.py` 提供与原 `xhs_parser/service.py` 相同的能力
- **AND** `XhsNote` 数据模型可从 `platforms/xiaohongshu/parser.py` 导出

#### Scenario: 旧 xhs_parser 入口保留桥接

- **WHEN** 其他代码从 `app.services.xhs_parser` 导入 `get_xhs_parser` 或 `XhsNote`
- **THEN** 桥接层代码重导出 `platforms.xiaohongshu.parser` 中的对应符号
- **AND** 不破坏现有功能

#### Scenario: breaker/ 调用方保持兼容

- **WHEN** `breaker/__init__.py` 调用 `xhs_parser.parse(url)`
- **THEN** 通过桥接层转发到 `platforms/xiaohongshu/parser.py` 的实现
- **AND** 解析结果格式不变

### Requirement: platforms/xiaohongshu/ 对外统一入口

`services/platforms/xiaohongshu/__init__.py` SHALL 导出 XiaohongshuClient 和 parser 模块的公共符号。

#### Scenario: XiaohongshuClient 保持搜索+详情职责

- **WHEN** 调用方需要搜索小红书笔记或获取详情
- **THEN** 使用 `XiaohongshuClient` 的 `search()` 和 `get_detail()` 方法
- **AND** 不暴露 HTML 解析细节

#### Scenario: parser.py 是内部实现

- **WHEN** 外部代码尝试导入 `from app.services.platforms.xiaohongshu import parser`
- **THEN** 通过 `__init__.py` 可访问 parser 模块
- **AND** parser 模块不对外暴露内部类型

### Requirement: xhs_parser 目录最终删除

在桥接层稳定后，`services/xhs_parser/` 目录 SHALL 被删除。

#### Scenario: 确认无引用后删除

- **WHEN** 所有引用 `app.services.xhs_parser` 的代码已迁移到 `app.services.platforms.xiaohongshu`
- **THEN** 删除 `services/xhs_parser/` 整个目录
- **AND** 不影响系统功能
