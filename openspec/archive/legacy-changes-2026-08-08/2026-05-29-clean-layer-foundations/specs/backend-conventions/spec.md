## MODIFIED Requirements

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
