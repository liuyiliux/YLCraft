# User Authentication and Accounts

YLCraft 目前没有用户身份。浏览器页面调用 API 时不带任何凭据；系统里唯一的凭据体系是 `ExternalApiKey`，它是为**外部程序/Agent**设计的，不是给人用的。

## Why

这带来三个具体问题：

1. **没有归属**：无法区分某个项目、素材、任务是谁创建的，也就没有所有权与租户隔离。当前是单机本地工具尚可接受，但任何"多人/公网"形态都无从支持。
2. **`ExternalApiKey` 无法对浏览器界面启用**（已实测确认）：`frontend/src` 中**没有任何** `Authorization` / `Bearer` / `externalApiKey` 相关代码，界面请求从不带 Key；而受保护端点清单里已经包含界面在用的端点（如 `GET /assets/{asset_id}`、任务读接口）。因此把 `YLCRAFT_EXTERNAL_API_REQUIRE_KEY` 置 1，**界面本身会先返回 401**，外部 Agent 还没接进来就已经坏了。
3. **无法约束危险操作**：删除任务、取消、重试、以及各类消耗额度的生成动作，目前对任何能访问到 API 的人都是开放的。

## What Changes

| 层 | 变更 |
|---|---|
| Backend | 新增 `User` 模型与迁移；密码哈希存储；登录/登出/当前用户接口；会话或令牌校验依赖 |
| Backend | 为项目、素材、任务等建立归属字段与回填策略，使所有权可表达 |
| Backend | 明确"人类会话"与"外部 Agent Key"两类调用方的关系，并让端点能同时识别 |
| Frontend | 登录页、会话保持、未登录跳转；请求层统一携带会话凭据 |
| 安全 | 密码强度与哈希、失败限流、登出失效、敏感字段脱敏 |

## Non-goals

- 不做第三方登录（OAuth / 微信 / GitHub），首版仅本地账号密码
- 不做多租户 SaaS 计费与配额商业化
- 不做细粒度 RBAC（角色/权限矩阵），首版只有"资源归属者"这一层判断
- 不引入注册验证码、找回密码邮件等依赖外部服务的能力（除非后续需要）
- 不改变供应商凭证的保管方式：供应商 API Key / SecretId / SecretKey 仍由服务端连接器统一保管，用户与 Agent 都不接触

## Impact

- Backend：`backend/app/db/models/`、`backend/app/api/v1/`（新增 auth 路由与依赖）、Alembic 迁移
- Frontend：`frontend/src/`（登录页、请求层、路由守卫）
- 文档：`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、`docs/guides/external-agent-api.md`（需说明两类凭据的关系）、`docs/architecture/API_SURFACE.md`
- 兼容性：既有 `ExternalApiKey` 机制**保留**并继续服务外部 Agent；新增登录不应破坏它
