# 小说书源系统增强 - 任务清单

## 任务概览

| 阶段 | 任务数 | 预计工时 |
|------|--------|----------|
| Cookie 管理整合 | 4 | 2天 |
| 书源测试 API | 3 | 1天 |
| 新规则格式 | 5 | 3天 |
| 迁移兼容 | 2 | 1天 |
| **总计** | **14** | **7天** |

---

## 阶段一：Cookie 管理整合

### T1.1 创建书源 Cookie 模型

**描述**：创建 `BookSourceCookie` 数据库模型

**验收标准**：
- [x] 模型包含 `id`, `book_source_id`, `domain`, `cookie_content`, `description`, `is_active`, `expires_at` 字段
- [x] 继承 SQLModel
- [x] 正确设置表名和索引

**文件**：`backend/app/db/models/book_source_cookie.py`

---

### T1.2 创建书源 Cookie 服务

**描述**：实现书源 Cookie 的 CRUD 操作

**验收标准**：
- [x] 实现 `get_cookies_by_source(source_id)` - 获取书源的所有 Cookie
- [x] 实现 `get_cookie_for_url(url, source_id)` - 根据 URL 获取匹配的 Cookie
- [x] 实现 `create_cookie(cookie_data)` - 创建新 Cookie
- [x] 实现 `update_cookie(cookie_id, data)` - 更新 Cookie
- [x] 实现 `delete_cookie(cookie_id)` - 删除 Cookie

**文件**：`backend/app/services/novel/cookie_manager.py`

---

### T1.3 创建书源 Cookie API

**描述**：添加书源 Cookie 的 REST API 端点

**验收标准**：
- [x] `GET /api/v1/book-sources/{id}/cookies` - 获取 Cookie 列表
- [x] `POST /api/v1/book-sources/{id}/cookies` - 添加 Cookie
- [x] `PUT /api/v1/book-sources/{id}/cookies/{cookie_id}` - 更新 Cookie
- [x] `DELETE /api/v1/book-sources/{id}/cookies/{cookie_id}` - 删除 Cookie

**文件**：`backend/app/api/v1/book_sources.py`

---

### T1.4 更新书源管理器使用 Cookie

**描述**：修改 `BookSourceManager` 使用统一的 Cookie 管理

**验收标准**：
- [x] 在搜索时自动获取匹配的 Cookie
- [x] 在获取章节时自动获取匹配的 Cookie
- [x] Cookie 自动添加到请求头

**文件**：`backend/app/services/novel/book_source_manager.py`

---

## 阶段二：书源测试 API

### T2.1 创建测试服务

**描述**：实现书源测试服务

**验收标准**：
- [x] 实现 `test_url(url, source_id)` - 测试指定 URL
- [x] 返回原始 HTML、响应头、状态码
- [x] 自动检测规则类型
- [x] 应用规则解析并返回结果

**文件**：`backend/app/services/novel/test_manager.py`

---

### T2.2 创建测试 API

**描述**：添加书源测试 REST API

**验收标准**：
- [x] `GET /api/v1/book-sources/{id}/test` - 测试书源
- [x] 支持 `url` 参数指定测试地址
- [x] 支持 `rule_type` 参数指定规则类型
- [x] 支持 `show_raw` 参数控制是否返回原始 HTML

**文件**：`backend/app/api/v1/book_sources.py`

---

### T2.3 添加调试信息

**描述**：在测试结果中添加详细的调试信息

**验收标准**：
- [x] 返回使用的规则配置
- [x] 返回匹配的元素数量
- [x] 返回解析耗时
- [x] 返回 Cookie 使用情况

**文件**：`backend/app/services/novel/test_manager.py`

---

## 阶段三：新规则格式

### T3.1 创建新规则模型

**描述**：定义 YLCraft 书源规则的数据模型

**验收标准**：
- [x] 定义 `YLCraftRule` Pydantic 模型
- [x] 包含 `version`, `name`, `base_url`, `search`, `book_info`, `toc`, `content` 字段
- [x] 定义字段提取配置模型

**文件**：`backend/app/schemas/book_source.py`

---

### T3.2 创建规则解析器

**描述**：实现 YLCraft 规则解析器

**验收标准**：
- [x] 实现 `parse_search(html)` - 解析搜索结果
- [x] 实现 `parse_toc(html)` - 解析目录
- [x] 实现 `parse_content(html)` - 解析章节内容
- [x] 支持 `text`, `attr`, `html` 三种提取类型
- [x] 支持 `trim`, `prefix`, `suffix`, `max_length` 修饰符

**文件**：`backend/app/services/novel/rule_parser.py`

---

### T3.3 创建规则转换器

**描述**：实现 Legado → YLCraft 规则转换器

**验收标准**：
- [x] 实现 `convert_legado_to_ylcraft(legado_json)` - 转换主函数
- [x] 实现 `convert_selector(legado_selector)` - 选择器转换
- [x] 支持搜索规则转换
- [x] 支持目录规则转换
- [x] 支持内容规则转换
- [x] 标记不支持的 JS 规则

**文件**：`backend/app/services/novel/rule_converter.py`

---

### T3.4 更新书源导入功能

**描述**：修改书源导入支持自动转换

**验收标准**：
- [x] 导入时自动检测格式（Legado/YLCraft）
- [x] Legado 格式自动转换为 YLCraft 格式
- [x] 转换失败时给出明确错误信息
- [x] 保留原始格式备份

**文件**：`backend/app/services/novel/book_source_manager.py`

---

### T3.5 更新书源导出功能

**描述**：支持导出为不同格式

**验收标准**：
- [x] 支持导出为 YLCraft 格式
- [x] 支持导出为 Legado 格式（反向转换）
- [x] 导出时包含版本信息

**文件**：`backend/app/services/novel/book_source_manager.py`

---

## 阶段四：迁移与兼容

### T4.1 编写数据库迁移脚本

**描述**：创建 `book_source_cookies` 表的迁移脚本

**验收标准**：
- [x] 创建表结构
- [x] 创建索引
- [x] 支持回滚

**文件**：`backend/alembic/versions/xxx_add_book_source_cookies.py`

---

### T4.2 实现自动迁移

**描述**：启动时自动迁移现有书源

**验收标准**：
- [x] 检测现有书源格式
- [x] 自动转换为 YLCraft 格式
- [x] 添加格式版本标记
- [x] 记录迁移日志

**文件**：`backend/app/services/novel/migration_manager.py`

---

## 任务依赖关系

```
T1.1 ──► T1.2 ──► T1.3
          │
          └──► T1.4

T2.1 ──► T2.2 ──► T2.3

T3.1 ──► T3.2
          │
T3.1 ──► T3.3 ──► T3.4
                    │
                    └──► T3.5

T4.1
T4.2
```

## 里程碑

| 里程碑 | 完成条件 | 预计日期 |
|--------|----------|----------|
| M1: Cookie 管理完成 | T1.1-T1.4 全部完成 | D+2 |
| M2: 测试 API 完成 | T2.1-T2.3 全部完成 | D+3 |
| M3: 新规则格式完成 | T3.1-T3.5 全部完成 | D+6 |
| M4: 迁移完成 | T4.1-T4.2 全部完成 | D+7 |

## 验收标准汇总

| 模块 | 验收项 |
|------|--------|
| **Cookie 管理** | 书源可配置多个域名的 Cookie，请求时自动匹配 |
| **测试 API** | 可测试任意 URL，返回原始响应和解析结果 |
| **新规则格式** | 支持简洁的 YLCraft 格式，可从 Legado 自动转换 |
| **兼容性** | 现有书源自动迁移，支持双向导出 |
