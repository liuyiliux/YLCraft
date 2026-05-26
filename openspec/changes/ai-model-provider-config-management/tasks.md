## 1. 数据库层实现

- [x] 1.1 在 `backend/app/db/models/ai_connector.py` 中新增 `AIProviderMetadata` 模型
- [x] 1.2 创建数据库迁移脚本，新增 `ai_provider_metadata` 表
- [x] 1.3 初始化默认 Provider 数据（OpenAI、SiliconFlow、Gemini）

## 2. 后端 API 实现

- [x] 2.1 在 `backend/app/api/v1/ai_connectors.py` 中新增 Provider 管理路由
- [x] 2.2 实现 GET /api/v1/providers 接口（获取所有 Provider）
- [x] 2.3 实现 GET /api/v1/providers/{provider_id} 接口（获取单个 Provider）
- [x] 2.4 实现 POST /api/v1/providers 接口（创建新 Provider）
- [x] 2.5 实现 PUT /api/v1/providers/{provider_id} 接口（更新 Provider）
- [x] 2.6 实现 DELETE /api/v1/providers/{provider_id} 接口（删除 Provider）
- [x] 2.7 添加参数验证和错误处理

## 3. 前端界面实现

- [x] 3.1 在 `frontend/src/pages/settings/index.tsx` 中新增 Provider 管理面板
- [x] 3.2 实现 Provider 列表展示组件
- [x] 3.3 实现 Provider 新增/编辑表单（包含 SDK 选择、默认参数配置）
- [x] 3.4 实现 Provider 删除确认对话框
- [x] 3.5 集成 API 调用逻辑

## 4. 配置继承机制

- [x] 4.1 实现获取 Provider 默认配置的 API 端点
- [x] 4.2 在 AIConnector 表单中添加"继承默认配置"按钮
- [x] 4.3 实现默认参数自动填充逻辑

## 5. 测试与验证

- [x] 5.1 数据库迁移执行成功
- [x] 5.2 后端 API 接口正常响应
- [x] 5.3 前端界面正常展示
- [x] 5.4 配置继承功能正常工作
