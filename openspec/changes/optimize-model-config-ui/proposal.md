## Why

当前 AI 模型配置界面存在过度设计问题：用户在选择 LLM 类型时也会看到复杂的请求模板配置，而实际上 OpenAI、Gemini 等主流服务商都使用标准 API 格式，不需要自定义模板。同时缺少预设配置，用户每次添加新模型都需要手动填写大量配置信息，影响使用体验。

## What Changes

- 添加服务商+类型组合的预设配置系统，支持 OpenAI、硅基流动、Gemini 等主流服务商
- 优化高级配置显示逻辑：LLM 类型不显示请求模板配置，Image/Video 类型默认折叠隐藏
- 添加"应用推荐配置"按钮，一键填充预设配置
- 根据服务商和类型自动填充对应的配置（包括 request_template、response_config 等）

## Capabilities

### New Capabilities
- `provider-presets`: 服务商预设配置系统，按 provider+type 组合提供默认配置
- `auto-fill-config`: 选择服务商和类型后自动填充配置的能力
- `advanced-config-collapse`: 高级配置折叠显示功能

### Modified Capabilities
- `ai-model-config`: 修改模型配置界面的用户体验

## Impact

- 修改文件：`frontend/src/pages/settings/index.tsx`
- 添加预设配置数据结构和自动填充逻辑
- 不影响后端 API，仅前端界面优化