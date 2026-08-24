# 外部 Agent API

YLCraft 的文本、图片、视频、3D 和素材中枢能力可以被外部智能体接手。浏览器页面和 Agent Center 不是唯一入口；外部 Agent 应通过稳定 ID 和任务接口完成同一条创作闭环。

外部 Agent 只调用平台 API。供应商 API Key、SecretId、SecretKey、Cookie、Token 和对象存储凭证由平台设置页与服务端连接器统一保管；外部 Agent 不读取、不保存、不传入这些值，也不需要为每个模型单独配置凭证。

## 当前能力入口

| 目标 | API | 说明 |
| --- | --- | --- |
| 查询模型与能力 | `GET /api/v1/ai/capabilities?available_only=true` | 返回已配置的 LLM、生图、视频、TTS、STT、Embedding 连接器和模型能力；不返回密钥。 |
| 查询连接器详情 | `GET /api/v1/ai/connectors` | 管理侧连接器列表，外部 Agent 优先使用能力接口。 |
| 上传素材 | `POST /api/v1/assets/upload` | 上传图片、视频、音频、文本和支持的 3D 文件，得到 Asset Hub 资产 ID。 |
| 生图 | `POST /api/v1/images/generate` | 支持 provider/model、参考素材、项目上下文和任务追踪。 |
| 生视频 | `POST /api/v1/videos/generate` | 支持文生视频、首帧/参考图、项目上下文和异步任务。 |
| 图转 3D | `POST /api/v1/model-3d/generate` | 使用已配置的 3D 连接器和模型。 |
| 文本生成 | `POST /api/v1/llm/chat` | 同步响应，同时写入文本事件日志。 |
| 任务详情 | `GET /api/v1/tasks/{task_id}` | 查询状态、进度、诊断和事件。 |
| 事件日志 | `GET /api/v1/logs` | 查询成功、失败、供应商、模型、请求摘要和重试链。 |
| 素材详情 | `GET /api/v1/assets/{asset_id}` | 读取 Asset Hub 元数据、版本和来源。 |

## 推荐闭环

```text
查询 /ai/capabilities
  → 选择 provider + model
  → /assets/upload 上传参考图
  → /images/generate 或 /videos/generate
  → 轮询 /tasks/{task_id}
  → 读取 /logs 和 /assets/{asset_id}
  → 继续项目、画布或平台适配
```

生成请求应尽量带上：

```json
{
  "project_id": "optional-project-id",
  "content_id": "optional-content-id",
  "production_profile": "storybook",
  "source_type": "storyboard",
  "source_index": "3",
  "source_title": "第三页：古堡走廊"
}
```

## 安全边界

当前开发环境的 CORS 允许浏览器联调，不等于公网 Agent 鉴权。正式开放给外部 Agent 前必须补充平台级 API Key/OAuth、作用域、租户隔离、速率限制、用量/费用限制和消耗型操作确认。平台级访问凭证用于识别调用方，不等于也不得替代供应商凭证；API 返回和事件日志会脱敏，不应把连接器密钥放进模型上下文。

## Skill 同步规则

平台新增能力或修改 HTTP API 时，维护者必须在同一轮检查并更新受影响的 API-facing Skill、流程参考和调用脚本，至少覆盖 `.agents/skills/ylcraft-creative-workflow/`。Skill 以能力发现和稳定 API 契约为准，不复制设置页中的供应商配置，也不包含任何密钥。
