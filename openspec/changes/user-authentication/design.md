# Design: User Authentication and Accounts

## Current state

- 无用户表、无登录、无会话。前端直连 `/api/v1/*`，不带凭据。
- 存在 `ExternalApiKey`（`external_api_keys` 表，迁移 020/021）：
  - `scope` ∈ `{read, write, generate}`，`quota` 次数配额（仅 `generate` 计入），每 Key 滑动窗口限流
  - 端点通过 `Depends(optional_external_api_key)` 挂载
  - `YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1` 时**强制要求**携带；关闭时**不强制携带，但携带即必须有效**（无效返回 401）
  - 已覆盖：生图/生视频/文本生成/图转 3D/素材上传/素材详情/日志/能力发现，以及任务读接口
- 已知限制：受保护清单包含前端在用的端点，而前端从不带 Key → 开启强制即界面 401。

## Target model

### 两类调用方

| 调用方 | 凭据 | 用途 |
|---|---|---|
| **人类用户** | 登录会话（Session / Bearer token） | 浏览器界面 |
| **外部 Agent** | `ExternalApiKey`（`ylk_...`） | 程序化调用 |

两者是**并列关系**，不是替代关系：

- `ExternalApiKey` 继续服务外部 Agent，语义与配额不变
- 登录会话用于人类用户，并作为"界面调用"的身份来源
- 端点应能同时识别两者；若未来开启强鉴权，满足**任一**即可通过

### User

```python
class User(SQLModel, table=True):
    id: str
    username: str          # 唯一
    password_hash: str     # 绝不存明文
    display_name: str
    is_active: bool
    created_at / updated_at
    last_login_at: str | None
```

- 密码哈希：使用 `passlib` / `argon2` 或 `bcrypt`；**禁止**自行实现或存明文
- 不存邮箱也可（首版单用户/少用户场景），但保留字段以便后续加找回密码

### 会话

优先选择：**服务端会话表**（`user_sessions`）+ HttpOnly Cookie。理由：可即时失效（登出/踢下线），比无状态 JWT 更适合本地/小团队部署。

若前端为纯静态且部署形态要求无状态，可退回到 JWT/LBearer，但需接受"签发后无法即时吊销"的代价，并在文档中写明。

### 归属

为目标资源增加 `owner_user_id`（可空，便于回填）：

- `creative_projects`
- `asset_nodes`（素材中枢）
- 任务类账本（`project_task_records` 等）

**回填策略**：既有数据在迁移时置为 NULL，或落到首个创建的"初始用户"。NULL 语义为"迁移前遗留数据"，界面与接口对 NULL 应**允许访问**（避免一次性锁死历史数据），但新数据必须带 owner。

### 依赖层

```python
current_user: Annotated[User | None, Depends(get_current_user_optional)]
```

- `get_current_user_optional`：未登录返回 None（用于可匿名访问的资源）
- `get_current_user`：未登录抛 401（用于受保护资源）
- 与 `optional_external_api_key` 组合：端点同时接受 `会话` 或 `ExternalApiKey`

## 安全约束

1. 密码只存哈希；日志与事件脱敏，**绝不记录**明文密码或 token
2. 登录失败限流（按用户名 + IP），防暴力破解
3. 登出必须使会话失效（服务端删除/标记）
4. Cookie：`HttpOnly` + `SameSite=Lax`（或 Strict）；公网部署时加 `Secure`
5. 会话过期与滑动续期策略需在文档中写明
6. 敏感接口（删除、重试、生成类）必须校验归属或至少要求已认证

## 迁移计划

1. 新增 `users` / `user_sessions` 表（Alembic）
2. 为资源加 `owner_user_id`（可空），**不立即回填**
3. 引入鉴权依赖，首版默认"允许匿名 + 已登录可写归属"（可通过开关收紧）
4. 前端加登录页与请求层凭据
5. 文档更新：架构文档、API Surface、外部 Agent API 指南（说明两类凭据）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 给既有端点加鉴权导致界面 401 | 界面不可用 | 首版默认允许匿名；开关逐步收紧；先在非破坏性端点试点 |
| 归属字段回填引发权限误判 | 历史数据访问不到 | 字段可空，NULL 视为遗留并允许访问 |
| 会话方案选错导致返工 | 安全或运维成本 | 首版服务端会话（可即时失效），文档记录 JWT 备选与代价 |
| 与 ExternalApiKey 语义冲突 | 两套凭据打架 | 明确"并列 + 任一通过"，并在文档中写清边界 |
