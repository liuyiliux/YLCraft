## Requirements

### Requirement: 模型定义规范
SQLModel 数据模型 SHALL 遵循以下约定：
- 所有模型继承自 `SQLModel`，基表指定 `table=True`
- 使用类型注解定义字段，支持 `Optional[T]` 表示可空
- 主键使用 `Field(default=None, primary_key=True)`
- 时间字段使用 `datetime` 类型，默认 `func.now()`
- 字段长度限制使用 `Field(max_length=N)`
- 枚举字段使用 `Literal[str]` 或自定义 Enum

```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class VideoTask(SQLModel, table=True):
    """视频下载任务"""
    id: Optional[int] = Field(default=None, primary_key=True)
    url: str = Field(index=True)                     # B站视频URL
    title: str = Field(max_length=500)               # 视频标题
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    progress: float = Field(default=0.0)             # 0.0 ~ 100.0
    file_path: Optional[str] = None                  # 下载文件路径
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = Field(max_length=1000, default=None)
```

#### Scenario: 定义新的数据模型
- **WHEN** 需要新增数据库表
- **THEN** SHALL 在 `backend/app/db/models/` 下创建模型文件，遵循上述字段约定

### Requirement: 字段命名规范
数据库字段命名 SHALL 遵循以下规则：
- 列名使用 **snake_case**（SQLModel 默认行为）
- 布尔字段使用 `is_` 前缀（如 `is_active`, `is_deleted`）
- 时间字段使用 `_at` 后缀（如 `created_at`, `updated_at`, `deleted_at`）
- 外键引用使用 `_id` 后缀（如 `user_id`, `provider_id`）
- JSON/字典字段使用 `_data` 或 `_config` 后缀
- 避免使用 SQL 保留字作为列名

| 命令模式 | 适用场景 | 示例 |
|----------|---------|------|
| `created_at` / `updated_at` | 时间戳 | `created_at: datetime` |
| `is_xxx` | 布尔标志 | `is_active: bool` |
| `xxx_id` | 外键关联 | `provider_id: int` |
| `xxx_count` | 计数器 | `download_count: int` |
| `xxx_url` | URL 地址 | `cover_url: str` |
| `xxx_path` | 文件路径 | `file_path: str` |
| `error_message` | 错误信息 | `error_message: Optional[str]` |

#### Scenario: 命名字段
- **WHEN** 为模型添加新字段
- **THEN** SHALL 选择合适的命名模式，保持与已有模型的一致性

### Requirement: 索引设计原则
索引 SHALL 按需创建，遵循以下原则：
- **主键**：自动创建，无需手动指定
- **高频查询字段**：使用 `Field(index=True)` 创建普通索引
- **唯一约束**：使用 `Field(unique=True)`
- **组合索引**：在模型类上使用 `__table_args__` 定义
- **外键关系**：关联字段通常需要索引

```python
class ProviderConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider_type: str = Field(index=True)           # 按类型查询频繁
    provider_name: str = Field(unique=True, index=True)  # 名称唯一且常查
    is_active: bool = Field(default=True, index=True)    # 过滤活跃项
    
    # 组合索引示例
    __table_args__ = (
        Index("ix_provider_type_active", "provider_type", "is_active"),
    )
```

#### Scenario: 设计索引策略
- **WHEN** 新建模型或优化查询性能
- **THEN** SHALL 分析查询模式，为高频 WHERE/ORDER BY/GROUP BY 字段添加索引

### Requirement: 数据迁移策略
数据库 Schema 变更 SHALL 遵循以下原则：
- 当前使用 SQLite，无正式迁移工具（如 Alembic）
- 开发阶段可直接删除 `ylcraft.db` 重建
- 生产环境中需编写向后兼容的 ALTER 语句
- 新增字段使用 `Optional[T]` 并设置 `default=None` 保证兼容
- 禁止在生产环境删除或重命名已有列

```python
# 向后兼容的新增字段示例
class VideoTask(SQLModel, table=True):
    # ... 已有字段 ...
    
    # 新增字段：可选 + 默认None → 不影响已有数据
    subtitle_path: Optional[str] = Field(default=None)
    thumbnail_path: Optional[str] = Field(default=None)
```

#### Scenario: 修改数据模型
- **WHEN** 需要修改已有的表结构
- **THEN** SHALL 评估影响范围，新增字段必须兼容旧数据，删除字段需特别谨慎

### Requirement: 数据库会话使用规范
数据库会话的使用 SHALL 遵循以下安全原则：
- **路由层**：通过 `Depends(get_async_session)` 注入，自动管理生命周期
- **服务层**：通过构造函数接收 session 参数，不自行创建
- **批量操作**：大事务使用 `begin_nested()` 或分批提交
- **只读查询**：优先使用 `select().where()` 而非原始 SQL
- **写操作**：显式 `session.add()` + `session.commit()` + `session.refresh()`

```python
# 安全的写入模式
async def create_task(self, data: TaskCreate) -> Task:
    task = Task.model_validate(data)
    session.add(task)
    await session.commit()
    await session.refresh(task)   # 获取数据库生成的值（如自增ID）
    return task

# 安全的批量写入
async def batch_create(self, items: list[Item]) -> None:
    async with session.begin():  # 自动 commit/rollback
        for item in items:
            session.add(Item(**item))
```

#### Scenario: 执行数据库操作
- **WHEN** 进行任何 CRUD 操作
- **THEN** SHALL 使用注入的 session，正确处理事务边界，避免 session 泄漏

### Requirement: 敏感数据存储规则
敏感数据 SHALL 按以下安全等级处理：
- **API Key / Token**：使用 `ApiKeyStore` 加密存储，明文不出现在数据库中
- **Cookie**：加密存储在 `cookies` 表，字段 `encrypted_data`
- **密码**：bcrypt 哈希存储（如有用户系统）
- **普通配置**：可明文存储，但不得包含密钥

```python
# API Key 存储示例（使用 ApiKeyStore）
from app.core.config import ApiKeyStore

key_store = ApiKeyStore()
await key_store.set_key("openai", "sk-xxxxx")  # 自动加密存储
raw_key = await key_store.get_key("openai")     # 解密读取
```

#### Scenario: 存储敏感数据
- **WHEN** 需要持久化密钥、Token、Cookie 等敏感信息
- **THEN** SHALL 使用加密存储方案，禁止明文写入数据库或配置文件
