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

## 外部 Agent API Key（鉴权）

当前开发环境的 CORS 允许浏览器联调，**不等于公网 Agent 鉴权**。要开放给外部 Agent，使用平台级 API Key 识别调用方。

### 两类调用方：各自用哪种凭据（规划中，尚未启用）

平台有**两类调用方**，凭据不同、不可混用；服务端按"**任一通过**"判定（详见 `openspec/changes/user-authentication/design.md`）：

| 调用方 | 用哪种凭据 | 用途 | 状态 |
| --- | --- | --- | --- |
| **人类用户** | **登录会话**（服务端会话表 + `HttpOnly` Cookie；备选 Bearer/JWT 见 design 的代价说明） | 浏览器界面 | **规划中**：本仓库当前**尚未启用**登录，界面请求不带会话凭据 |
| **外部 Agent** | 平台级 **`ylk_...` API Key**（`Authorization: Bearer`） | 程序化调用 | 已可用（见上一节）；语义与配额不变 |

三条边界，现在就要按此理解与调用：

1. **平台凭证 ≠ 供应商凭证**：`ylk_` Key 只用于识别调用方，不替代也不得携带供应商的 API Key / SecretId / SecretKey / Cookie / Token（后者只存在于平台设置页与服务端连接器里）；
2. **两类凭据不互相替代**：界面会话不能被外部 Agent 复用，`ylk_` Key 也不代表某个具体用户；**归属**（谁创建的项目/资产）以会话或 Key 记录的主体为准，迁移前的历史数据 `owner_user_id` 为空并**仍允许访问**；
3. **开放公网的前置条件**（未完成前不要把服务暴露到公网）：登录与会话可用、破坏性与消耗型操作（删除任务、取消、重试、生成类）要求认证、登录失败限流与审计日志就位——这些是 `user-authentication` 的未完成项，本文档在此只声明边界，**不声明已具备**。

> 平台级访问凭证用于识别调用方，**不等于也不得替代供应商凭证**。外部 Agent 不读取、不保存、不传入供应商 API Key / SecretId / SecretKey / Cookie / Token / 对象存储凭证。API 返回和事件日志会脱敏，不应把连接器密钥放进模型上下文。

### 管理 Key

| 操作 | API |
| --- | --- |
| 列出 | `GET /api/v1/external-api-keys` |
| 生成 | `POST /api/v1/external-api-keys` |
| 撤销 | `DELETE /api/v1/external-api-keys/{key_id}` |

请求体字段：`name`（默认 `外部 Agent`）、`scope`、`quota`（次数配额上限，`0` 表示不限）。

- **`scope` 取值**：`read` / `write` / `generate`（其它值返回 422）
- token 形如 `ylk_...`，**明文只在创建时返回一次**（响应 `api_key` 字段），之后只存 `key_hash` 与 `key_prefix`，无法再次取回
- 撤销是把 `active` 置 false，不物理删除

### 调用方式

```bash
curl -X POST http://<host>/api/v1/images/generate \
  -H "Authorization: Bearer ylk_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"一只陶土茶壶，米白釉面","size":"1024x1024"}'
```

### 开关

- 环境变量 **`YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1`** 时，挂了校验的端点**强制要求**携带 Key
- **默认关闭**：不设该变量时，端点**不强制要求**携带 Key；但**一旦携带，必须是有效且启用的 Key**（无效/停用会返回 401）

实测行为对照：

| 场景 | 结果 |
| --- | --- |
| 开关关 + 不带 Key | 200（与未启用鉴权时一致） |
| 开关关 + 带**无效** Key | **401**「无效或已停用的外部 API Key」 |
| 开关关 + 带**有效** Key | 200 |
| 开关开 + 不带 Key | **401**「需要外部 API Key」 |

### 作用域、配额与限流

| 机制 | 行为 |
| --- | --- |
| 速率限制 | 每个 Key 独立滑动窗口，超限返回 **429** |
| 次数配额 | 仅 `scope=generate` 的 Key 计入；每次消耗型调用 `quota_used` 递增，达上限返回 **403** |
| 无效/停用 | 返回 **401** |
| 缺少 Key（开关打开时） | 返回 **401** |

### 已覆盖的端点

`POST /images/generate`、`POST /videos/generate`、`POST /llm/chat`、`POST /model-3d/generate`、
`POST /assets/upload`、`GET /assets/{asset_id}`、`GET /logs`、`GET /ai/capabilities`，
以及任务读接口 `GET /tasks`、`GET /tasks/stats`、`GET /tasks/{task_id}`。

### 明确不在覆盖范围的端点（含内容包）

鉴权是**逐路由声明**的（`Depends(require_external_api_key(...))`），当前只有上表对应的 9 个路由声明了它。**创作项目路由 `backend/app/api/v1/creative_projects.py` 未声明**，因此：

- 内容包、生产方案、导演计划、章节/正文/剧本/分镜等**创作项目端点不在带 Key 的外部契约内**——既不校验 Key，也不计入 `scope` 与 `generate` 配额，事件日志不按外部 Key 归属。
- 外部 Agent 在**本机部署**下仍可调用它们（无 Key 门槛），但应按「本机内部 API」对待，**不要依赖其公网可用性**：一旦以公网形态暴露，这些端点需要与生图/生视频同等的 Key + 作用域 + 配额处理。
- 若要让外部 Agent 真正驱动内容包（规划 → 条目编辑 → 平台输出），应先把 `creative_projects.py` 纳入鉴权覆盖并定义作用域（读/写/生成），再对外声明。

### ⚠️ 已知限制（启用公网模式前必须解决）

**前端不带任何 Key**（`frontend/src` 中无 `Authorization` / `Bearer` / `externalApiKey` 相关代码），而受保护列表里已包含前端在用的端点（如 `GET /assets/{asset_id}`、任务读接口）。

因此：**一旦设置 `YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1`，浏览器界面调用这些端点会得到 401，界面本身会先坏掉。**

启用公网模式前，需要先二选一：

1. 给前端增加 Key 注入（设置页填写 Key，请求统一带 `Authorization`）；或
2. 为本地/浏览器会话增加豁免策略

在此之前，**该开关仅适用于纯外部 Agent 调用、不使用浏览器界面的部署形态。**

## Skill 同步规则

平台新增能力或修改 HTTP API 时，维护者必须在同一轮检查并更新受影响的 API-facing Skill、流程参考和调用脚本，至少覆盖 `.agents/skills/ylcraft-creative-workflow/`。Skill 以能力发现和稳定 API 契约为准，不复制设置页中的供应商配置，也不包含任何密钥。
