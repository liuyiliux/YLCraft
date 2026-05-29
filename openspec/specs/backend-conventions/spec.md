## Requirements

### Requirement: API 路由注册规范
后端 API 路由 SHALL 遵循以下约定：
- 所有路由位于 `backend/app/api/v1/` 目录下
- 使用 `APIRouter` 按功能模块组织 router 文件
- 路由前缀格式：`/api/v1/{module}`（如 `/api/v1/models`、`/api/v1/images`）
- Router 在 `backend/app/main.py` 中通过 `include_router` 注册

```python
# 正确示例
router = APIRouter(prefix="/api/v1/images", tags=["图片生成"])

@router.post("/generate")
async def generate_image(req: ImageGenerateRequest): ...
```

#### Scenario: 新增 API 路由
- **WHEN** 需要添加新的 API 端点
- **THEN** SHALL 在 `api/v1/` 下创建或选择对应模块的 router 文件，并在 main.py 中注册

### Requirement: 服务层架构约定
业务逻辑 SHALL 放置于 `backend/app/services/` 下的对应领域目录中，遵循以下领域优先组织原则：

- 每个领域包 SHALL 是 `services/{domain}/` 形式的子目录，含 `__init__.py` 并导出公共 API
- 服务类使用 `Service` 后缀命名（如 `AIService`、`BreakerService`），但非服务层的 Backend 类不强制此后缀
- 服务层负责业务编排，SHALL NOT 直接操作 HTTP 请求/响应对象
- 跨服务调用 SHALL 通过包级导入完成（`from app.services.ai import get_ai_service`）
- 每个包的 `__init__.py` MUST 导出公共接口，外部调用方 SHALL NOT 穿透到内部模块路径
- AI 相关功能 SHALL 统一通过 `services/ai/` 入口调用（`get_ai_service()` 全局单例），不再使用已删除的 `services/llm/manager.py` 中的 `get_manager()`
- 孤立顶层 `.py` 文件 SHALL NOT 存在于 `services/` 根目录下

```python
# 正确的服务层结构（领域包）
services/ai/
  __init__.py        # 导出 AIService, get_ai_service
  service.py          # AIService 编排类
  types.py            # AI 领域专属类型
  backends/           # AI Backend 实现
    llm/ image/ video/

# 正确的调用方式
from app.services.ai import get_ai_service
service = get_ai_service()
```

#### Scenario: 编写新服务
- **WHEN** 需要新增业务逻辑
- **THEN** SHALL 在 services/ 下创建领域包（含 `__init__.py` 导出），遵循领域优先组织原则

#### Scenario: 检查包边界
- **WHEN** 审查 services/ 目录结构
- **THEN** MUST 确认没有顶层孤立 `.py` 文件、没有仅含注释的 `__init__.py`、没有空目录残留

### Requirement: 配置管理系统
所有可配置项 SHALL 通过统一配置系统管理：
- **Provider 配置**：`backend/config/providers.yaml` — 定义模型、端点、默认参数
- **API Key**：通过 `ApiKeyStore` 类管理，优先从数据库读取，支持 `${ENV_VAR}`
- **系统设置**：`backend/app/data/settings.json` — 下载路径、存储类型等
- **核心配置类**：`backend/app/core/config.py` 的 `ProvidersConfig`

```yaml
# providers.yaml 结构示例
providers:
  openai:
    type: llm
    models:
      - id: gpt-4o
        name: GPT-4o
    base_url: https://api.openai.com/v1
```

#### Scenario: 读取/修改配置
- **WHEN** 需要获取 Provider 或 API Key
- **THEN** SHALL 使用 `ProvidersConfig` 和 `ApiKeyStore` 类，不得硬编码或直接读文件

### Requirement: 错误处理规范
错误处理 SHALL 遵循统一约定：
- 业务错误使用自定义异常类（继承自 `Exception`）
- HTTP 错误使用 FastAPI 的 `HTTPException`，附带标准状态码
- 异步操作失败 SHALL 提供有意义的错误消息和日志
- 外部服务调用失败 SHALL 包含原始错误上下文

```python
# 错误处理示例
class ImageGenerationError(Exception):
    """图片生成业务异常"""
    pass

# 在路由中使用
try:
    result = await image_service.generate(request)
except ImageGenerationError as e:
    logger.error(f"图片生成失败: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

#### Scenario: 处理业务异常
- **WHEN** 服务层出现预期内的业务错误
- **THEN** SHALL 抛出自定义异常并由路由层转换为合适的 HTTP 响应

### Requirement: 数据库会话管理
数据库访问 SHALL 遵循以下会话管理模式：
- 使用 `get_session()` / `get_async_session()` 依赖注入获取会话
- 会话生命周期由 FastAPI 的 `Depends` 管理
- 写操作完成后显式 `commit`，读操作使用自动事务
- 批量操作考虑使用 `run_sync` 或原生 SQL 提升性能

```python
@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_async_session)):
    items = await session.exec(select(Item).where(Item.active == True))
    return items.all()
```

#### Scenario: 操作数据库
- **WHEN** 需要在路由或服务中访问数据库
- **THEN** SHALL 通过 Depends 注入 session 参数，不在函数内部创建新会话
