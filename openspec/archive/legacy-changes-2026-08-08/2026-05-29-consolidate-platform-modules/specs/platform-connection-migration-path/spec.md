## ADDED Requirements

### Requirement: platform_connection/ 标注废弃路径

`services/platform_connection/__init__.py` SHALL 包含 deprecation 文档，明确说明：
1. 本模块为旧版，推荐迁移到 `connectors/social/`
2. 迁移阶段说明

#### Scenario: 添加 Deprecation 文档

- **WHEN** 开发者阅读 `platform_connection/__init__.py`
- **THEN** 文档字符串明确说明本模块是旧版
- **AND** 文档包含指向 `connectors/social/` 的迁移指引

### Requirement: connectors/social/ 明确凭证管理能力

`connectors/social/` SHALL 在 `__init__.py` 中明确说明其凭证管理职责。

#### Scenario: connectors/social/ 作为凭证管理目标

- **WHEN** 开发者需要管理平台凭证（Cookie/API Key/OAuth Token）
- **THEN** 推荐使用 `connectors/social/` 中的连接器
- **AND** 每个平台连接器（如 XiaoHongShuConnector）管理自己的凭证

### Requirement: platform_connection 到 connectors/social 迁移阶段

迁移 SHALL 分为以下阶段：

#### Phase 1: 文档阶段（本次）

- `platform_connection/__init__.py` 添加 deprecation 文档
- 明确 `connectors/social/` 为目标方向

#### Phase 2: 能力补充

- 在 `connectors/social/` 中补充缺失的凭证管理能力
- 确保 `connectors/social/` 可完全替代 `platform_connection/`

#### Phase 3: 调用方迁移

- 将 `platforms/`、`download/`、`crawler/` 等调用方迁移到 `connectors/social/`
- 保持 `platform_connection/` 兼容

#### Phase 4: 废弃

- 删除 `platform_connection/` 目录
- 更新所有相关文档
