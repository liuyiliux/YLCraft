# 小说书源系统增强方案

## 1. 需求背景

当前小说模块存在以下问题：

### 1.1 Cookie 管理分散
- **现状**：平台 Cookie 存储在 `PlatformConnection` 表，书源 Cookie 存储在 `book_sources` 表
- **问题**：管理分散，用户需要在不同地方配置 Cookie，体验不佳

### 1.2 书源测试功能缺失
- **现状**：没有专门的书源测试接口，调试规则困难
- **问题**：无法查看原始响应，难以判断规则是否正确

### 1.3 规则格式依赖移动端
- **现状**：直接使用 Legado 移动端书源格式
- **问题**：移动端格式复杂，部分 JS 规则无法在服务端执行

---

## 2. 目标

1. **统一 Cookie 管理**：书源 Cookie 与平台 Cookie 统一管理，支持自动匹配
2. **书源测试 API**：提供测试接口，返回原始响应 + 解析结果
3. **新规则格式设计**：设计简洁的书源规则格式，支持从移动端格式自动转换

---

## 3. 方案设计

### 3.1 Cookie 管理整合

#### 3.1.1 数据模型设计

**新增表：`book_source_cookies`**（书源 Cookie 关联表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `book_source_id` | UUID | 关联书源 ID |
| `domain` | VARCHAR(255) | Cookie 适用域名 |
| `cookie_content` | TEXT | Netscape 格式 Cookie |
| `description` | VARCHAR(255) | Cookie 描述（如：起点VIP） |
| `is_active` | BOOLEAN | 是否启用 |
| `expires_at` | DATETIME | 过期时间 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

#### 3.1.2 Cookie 匹配策略

```
请求 URL → 提取域名 → 查找匹配的书源 Cookie → 使用该 Cookie 请求
```

优先级：
1. 精确域名匹配（如 `m.qidian.com`）
2. 通配域名匹配（如 `.qidian.com`）
3. 书源默认 Cookie

#### 3.1.3 API 设计

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/book-sources/{id}/cookies` | GET | 获取书源的 Cookie 列表 |
| `/api/v1/book-sources/{id}/cookies` | POST | 添加书源 Cookie |
| `/api/v1/book-sources/{id}/cookies/{cookie_id}` | PUT | 更新书源 Cookie |
| `/api/v1/book-sources/{id}/cookies/{cookie_id}` | DELETE | 删除书源 Cookie |

---

### 3.2 书源测试 API

#### 3.2.1 API 设计

**GET /api/v1/book-sources/{id}/test**

请求参数：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | STRING | 是 | 测试目标 URL |
| `rule_type` | ENUM | 否 | 规则类型：search/toc/content（默认自动检测） |

响应结构：
```json
{
"success": true,
"data": {
    "url": "https://m.qidian.com/search",
    "status_code": 200,
    "headers": { ... },
    "response_time": 1200,
    "raw_html": "<html>...</html>",
    "parsed_result": {
    "type": "search",
    "items": [...],
    "parse_success": true
    },
    "debug_info": {
    "rule_used": {...},
    "matched_elements": 10
    }
}
}
```

#### 3.2.2 测试流程

```
用户请求 → 发送 HTTP 请求 → 获取原始响应 → 应用规则解析 → 返回完整结果
```

---

### 3.3 新规则格式设计

#### 3.3.1 YLCraft 书源规则格式（v1.0）

```json
{
"version": "1.0",
"name": "起点中文网",
"base_url": "https://m.qidian.com",
"search": {
    "url": "https://m.qidian.com/search?kw={{keyword}}&page={{page}}",
    "method": "GET",
    "headers": {},
    "items": {
    "selector": "div.book-item",
    "fields": {
        "title": { "selector": "h3", "type": "text" },
        "author": { "selector": ".author", "type": "text" },
        "url": { "selector": "a", "type": "attr", "attr": "href" },
        "cover": { "selector": "img", "type": "attr", "attr": "src" }
    }
    }
},
"toc": {
    "url": "{{book_url}}",
    "items": {
    "selector": "ul.chapter-list li",
    "fields": {
        "title": { "selector": "a", "type": "text" },
        "url": { "selector": "a", "type": "attr", "attr": "href" }
    }
    }
},
"content": {
    "selector": "div.content",
    "remove": ["script", "style", ".ads"],
    "text_only": true
}
}
```

#### 3.3.2 规则字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | STRING | 规则版本 |
| `name` | STRING | 书源名称 |
| `base_url` | STRING | 基础 URL |
| `search.items.selector` | STRING | 列表项选择器 |
| `search.items.fields.*.selector` | STRING | 字段选择器 |
| `search.items.fields.*.type` | ENUM | 提取类型：text/attr/html |
| `search.items.fields.*.attr` | STRING | 属性名（type=attr 时必填） |
| `content.remove` | LIST | 需要移除的选择器 |
| `content.text_only` | BOOLEAN | 是否只提取文本 |

#### 3.3.3 移动端格式转换工具

**转换策略**：
1. **选择器转换**：Legado 选择器 → CSS 选择器
2. **规则映射**：Legado 规则字段 → YLCraft 规则字段
3. **JS 规则处理**：不支持的 JS 规则标记为需要手动调整

**转换示例**：
```python
# Legado 规则
{
"ruleSearch": {
    "bookList": "class.book-list@tag.div",
    "name": "tag.h3@text",
    "bookUrl": "tag.a@href"
}
}

# 转换后 YLCraft 规则
{
"search": {
    "items": {
    "selector": ".book-list div",
    "fields": {
        "title": { "selector": "h3", "type": "text" },
        "url": { "selector": "a", "type": "attr", "attr": "href" }
    }
    }
}
}
```

---

## 4. 实现计划

### 4.1 阶段一：Cookie 管理整合（1-2天）
- 创建 `book_source_cookies` 表模型
- 实现 Cookie 匹配服务
- 添加书源 Cookie API

### 4.2 阶段二：书源测试 API（1天）
- 实现测试接口
- 添加调试信息返回

### 4.3 阶段三：新规则格式（2-3天）
- 设计并实现新规则解析器
- 实现移动端格式转换工具
- 更新书源导入/导出功能

### 4.4 阶段四：迁移与兼容（1天）
- 现有书源自动转换为新格式
- 保持对移动端格式的兼容支持

---

## 5. 预期收益

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| Cookie 管理 | 分散在两个表 | 统一管理 |
| 书源调试 | 困难，无测试接口 | 完整测试工具 |
| 规则复杂度 | 复杂的 Legado 格式 | 简洁的 YLCraft 格式 |
| JS 规则支持 | 有限支持 | 无需 JS，纯 CSS 选择器 |

---

## 6. 风险评估

| 风险 | 描述 | 应对措施 |
|------|------|----------|
| 规则兼容性 | 新格式与旧格式冲突 | 保持双向兼容，自动转换 |
| Cookie 安全 | Cookie 明文存储 | 使用加密存储 |
| 性能影响 | 增加 Cookie 匹配逻辑 | 缓存匹配结果 |

---

## 7. 后续计划

1. **规则市场**：支持规则分享和社区贡献
2. **规则验证器**：在线规则编辑和实时预览
3. **Cookie 自动获取**：支持 Playwright 自动获取书源 Cookie
