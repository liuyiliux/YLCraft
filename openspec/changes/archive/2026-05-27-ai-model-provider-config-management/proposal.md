## Why

当前AI模型配置管理依赖硬编码的提供商列表和分散的配置，新增供应商时需要修改代码，且无法灵活配置各平台的默认URL、请求参数等。需要建立统一的AI Provider配置管理系统，支持动态管理默认配置，提升系统灵活性和可维护性。

## What Changes

- 新增AI Provider元数据管理表，存储各提供商的默认配置（URL、请求参数、模型列表等）
- 支持为不同供应商配置默认参数模板（temperature、max_tokens等）
- 提供API接口管理Provider配置，支持CRUD操作
- 前端配置界面支持新增/编辑供应商默认配置
- 实现SDK选择功能，支持不同API格式（OpenAI兼容、自定义等）

## Capabilities

### New Capabilities
- `provider-metadata-management`: AI提供商元数据管理，支持配置默认URL、请求参数、模型列表
- `provider-default-params`: 为不同供应商配置默认请求参数模板
- `provider-sdk-selection`: SDK选择功能，支持多种API格式

### Modified Capabilities
- 无

## Impact

- 修改 `backend/app/db/models/ai_connector.py`: 新增ProviderMetadata模型
- 修改 `backend/app/api/v1/ai_connectors.py`: 新增Provider配置管理API
- 修改 `frontend/src/pages/settings/index.tsx`: 新增Provider配置表单
- 新增数据库迁移脚本

## Business Value

- 运营人员可通过界面配置新供应商，无需开发介入
- 统一管理各平台的默认参数，提升配置一致性
- 支持灵活的API格式适配，降低接入新供应商的成本