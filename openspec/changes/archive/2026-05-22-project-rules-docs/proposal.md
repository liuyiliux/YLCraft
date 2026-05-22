## Why

YLCraft（逸流创作平台）是一个 AI 创作平台，目前已有模型配置、AI图片生成、B站视频搜索/下载、B站账号登录等功能模块。但项目缺少系统化的 AI 开发规则文档，导致 AI 助手在辅助开发时缺乏统一的上下文约束和规范指导。建立一套完整的项目规则文档将显著提升 AI 辅助开发的准确性和一致性。

## What Changes

- 在 `docs/rules/` 目录下创建 **6 个 AI 规则文档**，覆盖项目的核心开发规范
- 新增 `rules` 规范定义，为 AI 助手提供项目级别的上下文约束
- 文档涵盖：项目概述、后端规范、前端规范、代码风格、快速参考、数据库设计规则

## Capabilities

### New Capabilities
- `project-overview`: 项目概述 - 技术栈、目录结构、架构模式、已实现功能清单
- `backend-conventions`: 后端开发规范 - API 路由规范、服务层约定、配置管理、错误处理
- `frontend-conventions`: 前端开发规范 - 组件规范、状态管理、API 调用、路由结构
- `code-style`: 代码风格指南 - Python/TypeScript 命名规范、注释风格、文件组织
- `quick-reference`: 快速参考 - 常用命令、调试技巧、环境变量、关键路径映射
- `database-rules`: 数据库设计规则 - 模型定义规范、字段命名、迁移策略、索引原则

### Modified Capabilities
（无）

## Impact

- **新增文档**：`docs/rules/` 下 6 个 markdown 文件
- **AI 开发流程**：AI 助手在编码时可引用这些规则保持一致性
- **团队协作**：新成员可快速了解项目结构和规范
- **无破坏性变更**：纯文档添加，不影响现有代码
