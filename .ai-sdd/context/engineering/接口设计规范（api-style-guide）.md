# 接口设计规范（YLCraft）

来源：本项目现有路由与文档同步流程。最后更新：2026-09-11。

## 1. 落点与命名

| 约定 | 说明 |
|---|---|
| 前缀 | 统一 `/api/v1/<domain>`（如 `/api/v1/images`、`/api/v1/tasks`、`/api/v1/novels`） |
| 路由文件 | `backend/app/api/v1/<domain>.py`；业务逻辑放 `backend/app/services/<domain>/`，端点保持薄 |
| 前端调用 | 统一在 `frontend/src/api/index.ts` 导出（该文件较大，新增按领域就近放置，不做无关重构） |
| 请求/响应模型 | Pydantic `BaseModel`；响应统一带 `success` 字段，业务失败用 `success=false + error`（HTTP 层只用于输入/权限/不存在/冲突类错误） |
| 错误语义 | 参数/输入问题 → 400；不存在 → 404；状态冲突（如"只有失败事件可重发"）→ 409；服务未初始化 → 503 |

## 2. 任务与长耗时接口

- 长耗时生成类接口在**异步路径**返回 `task_id`，由前端轮询；同步路径直接返回结果。
- 任务相关接口在 `/api/v1/tasks`：列表（轻量）、详情（含 `diagnostics` + `events`）、`cancel`、`retry`、`delete`。
- 任务化必须配合任务账本与持久化白名单，见 `.ai-sdd/context/data/枚举值字典（enum-dictionary）.md`。

## 3. 事件与日志接口

| 接口 | 用途 |
|---|---|
| `GET /api/v1/logs` | 事件流筛选分页（scene / task_type / status / level / project_id / ref_id） |
| `GET /api/v1/logs/{id}` | 事件详情（含 request/response 摘要与 retry_payload） |
| `POST /api/v1/logs/{id}/retry` | 失败事件重发（仅 failed 且带 retry_payload） |
| `GET /api/v1/logs/{id}/generation` | 按事件取完整 LLM 生成日志 |
| `GET /api/v1/logs/runtime` | 读取滚动文件日志（支持 level/关键词/before 游标） |

## 4. 文档同步（强制）

新增/修改/删除接口后必须执行：

```bash
cd F:/PycharmProjects/YLCraft
backend/venv_win/Scripts/python.exe tools/generate_api_surface.py
```

它会重写 `docs/architecture/API_SURFACE.md` 与 `docs/architecture/api_surface.json`（含全部端点与行号）。
手改这两个文件会在下次生成时被覆盖。

## 5. 鉴权与外部调用

- 外部 Agent 走 `/api/v1/ai/capabilities` 发现能力，凭证仅由平台侧连接器管理，不接受调用方传入 Key。
- `optional_external_api_key` 用于外部 API Key 可选的端点；内部直接函数调用时须显式传 `None`（见设计约束 §3）。
