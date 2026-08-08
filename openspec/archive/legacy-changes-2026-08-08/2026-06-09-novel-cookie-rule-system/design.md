# 小说书源系统增强 - 详细设计

## 1. 架构概述

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Layer                               │
│  book_sources.py    novels.py     cookie_acquisition.py        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      Service Layer                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ CookieManager   │  │ BookSourceManager│  │ RuleConverter   │ │
│  │ (统一Cookie管理)│  │ (书源管理)      │  │ (规则转换)      │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
└───────────┼────────────────────┼─────────────────────┼─────────┘
            │                    │                     │
┌───────────▼────────────────────▼─────────────────────▼─────────┐
│                      Data Layer                                │
│  PlatformConnection    book_sources      book_source_cookies   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心组件职责

| 组件 | 职责 |
|------|------|
| **CookieManager** | 统一管理平台和书源 Cookie |
| **BookSourceManager** | 书源的增删改查和规则解析 |
| **RuleConverter** | Legado 格式 → YLCraft 格式转换 |

---

## 2. Cookie 管理整合设计

### 2.1 数据库表设计

#### 2.1.1 book_source_cookies 表

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | VARCHAR(36) | PRIMARY KEY | UUID |
| `book_source_id` | VARCHAR(36) | FOREIGN KEY | 关联书源 |
| `domain` | VARCHAR(255) | NOT NULL | 适用域名 |
| `cookie_content` | TEXT | | Netscape 格式 |
| `description` | VARCHAR(255) | | 描述信息 |
| `is_active` | BOOLEAN | DEFAULT TRUE | 是否启用 |
| `expires_at` | DATETIME | | 过期时间 |
| `created_at` | DATETIME | DEFAULT NOW | 创建时间 |
| `updated_at` | DATETIME | DEFAULT NOW | 更新时间 |

#### 2.1.2 索引设计

| 索引名 | 字段 | 类型 |
|--------|------|------|
| `idx_book_source_id` | book_source_id | 普通索引 |
| `idx_domain` | domain | 普通索引 |
| `idx_is_active` | is_active | 普通索引 |

### 2.2 数据模型

```python
# app/db/models/book_source_cookie.py
from sqlmodel import SQLModel, Field
from datetime import datetime

class BookSourceCookie(SQLModel, table=True):
    __tablename__ = "book_source_cookies"
    
    id: str = Field(primary_key=True)
    book_source_id: str = Field(foreign_key="book_sources.id")
    domain: str = Field(index=True)
    cookie_content: str = Field(default="")
    description: str = Field(default="")
    is_active: bool = Field(default=True)
    expires_at: datetime = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

### 2.3 Cookie 匹配流程

```
┌──────────────────────────────────────────────────────────────┐
│                    Cookie 匹配流程                          │
├──────────────────────────────────────────────────────────────┤
│                                                            │
│  请求 URL                                                   │
│      │                                                      │
│      ▼                                                      │
│  提取域名 (如: m.qidian.com)                                │
│      │                                                      │
│      ▼                                                      │
│  ┌──────────────────────────────────────┐                   │
│  │ 查找 book_source_cookies 表          │                   │
│  │ WHERE domain = 'm.qidian.com'        │                   │
│  │   AND is_active = TRUE               │                   │
│  └──────────────────────────────────────┘                   │
│      │                                                      │
│      ▼                                                      │
│  找到匹配的 Cookie?                                          │
│      │                                                      │
│   Yes │          │ No                                       │
│       ▼          ▼                                          │
│  使用该 Cookie  │ 查找通配域名 (.qidian.com)                 │
│  发送请求       │      │                                    │
│                │   Yes │          │ No                      │
│                │       ▼          ▼                         │
│                │   使用该 Cookie  │ 使用书源默认 Cookie      │
│                │   发送请求       │ 发送请求                  │
│                │                  │                          │
└──────────────────────────────────────────────────────────────┘
```

### 2.4 API 接口设计

#### 2.4.1 获取书源 Cookie 列表

**GET /api/v1/book-sources/{source_id}/cookies**

响应：
```json
{
"success": true,
"data": [
    {
    "id": "uuid",
    "domain": "m.qidian.com",
    "description": "起点VIP",
    "is_active": true,
    "expires_at": "2025-12-31T23:59:59",
    "cookie_count": 5
    }
]
}
```

#### 2.4.2 添加书源 Cookie

**POST /api/v1/book-sources/{source_id}/cookies**

请求：
```json
{
"domain": "m.qidian.com",
"cookie_content": "# Netscape HTTP Cookie File\n...",
"description": "起点VIP",
"expires_at": "2025-12-31T23:59:59"
}
```

响应：
```json
{
"success": true,
"data": {
    "id": "uuid",
    "domain": "m.qidian.com",
    "is_active": true
}
}
```

---

## 3. 书源测试 API 设计

### 3.1 API 接口

**GET /api/v1/book-sources/{source_id}/test**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | STRING | 是 | 测试目标 URL |
| `rule_type` | ENUM | 否 | search/toc/content（默认自动检测） |
| `show_raw` | BOOLEAN | 否 | 是否返回原始 HTML（默认 true） |

### 3.2 响应结构

```json
{
"success": true,
"data": {
    "url": "https://m.qidian.com/search?kw=test",
    "status_code": 200,
    "headers": {
    "Content-Type": "text/html; charset=utf-8",
    "Server": "nginx"
    },
    "response_time_ms": 1200,
    "raw_html": "<html>...</html>",
    "raw_html_truncated": false,
    "parsed_result": {
    "type": "search",
    "parse_success": true,
    "items": [
        {
        "title": "书名",
        "author": "作者",
        "url": "https://...",
        "cover": "https://..."
        }
    ],
    "total_items": 10
    },
    "debug_info": {
    "rule_used": {
        "selector": ".book-list div",
        "fields": {...}
    },
    "matched_elements": 10,
    "parse_time_ms": 50
    }
}
}
```

### 3.3 测试逻辑

```python
# 核心测试流程
async def test_book_source(source_id: str, url: str, rule_type: str = None):
    # 1. 获取书源配置
    source = get_source(source_id)
    
    # 2. 获取匹配的 Cookie
    cookie = get_cookie_for_url(url, source_id)
    
    # 3. 发送请求
    response = await fetch_url(url, cookie=cookie)
    
    # 4. 自动检测规则类型（可选）
    if not rule_type:
        rule_type = detect_rule_type(url, source)
    
    # 5. 应用规则解析
    parsed = parse_with_rule(response.text, source, rule_type)
    
    # 6. 返回结果
    return {
        "url": url,
        "status_code": response.status_code,
        "raw_html": response.text[:10000] if len(response.text) > 10000 else response.text,
        "parsed_result": parsed,
        "debug_info": {...}
    }
```

---

## 4. 新规则格式设计

### 4.1 YLCraft 规则格式规范

#### 4.1.1 完整规则结构

```json
{
"version": "1.0",
"name": "起点中文网",
"base_url": "https://m.qidian.com",
"search": {
    "url": "https://m.qidian.com/search?kw={{keyword}}&page={{page}}",
    "method": "GET",
    "headers": {
    "User-Agent": "Mozilla/5.0..."
    },
    "params": {
    "kw": "{{keyword}}",
    "page": "{{page}}"
    },
    "items": {
    "selector": "div.book-item",
    "limit": 50,
    "fields": {
        "title": {
        "selector": "h3.book-title",
        "type": "text",
        "trim": true
        },
        "author": {
        "selector": "span.author",
        "type": "text"
        },
        "url": {
        "selector": "a",
        "type": "attr",
        "attr": "href",
        "prefix": "https://m.qidian.com"
        },
        "cover": {
        "selector": "img.cover",
        "type": "attr",
        "attr": "src"
        },
        "desc": {
        "selector": "p.desc",
        "type": "text",
        "max_length": 200
        }
    }
    }
},
"book_info": {
    "fields": {
    "title": { "selector": "h1", "type": "text" },
    "author": { "selector": ".author", "type": "text" },
    "cover": { "selector": ".cover img", "type": "attr", "attr": "src" },
    "intro": { "selector": ".intro", "type": "text" },
    "toc_url": { "selector": "a.toc", "type": "attr", "attr": "href" }
    }
},
"toc": {
    "items": {
    "selector": "ul.chapter-list li",
    "fields": {
        "title": { "selector": "a", "type": "text" },
        "url": { "selector": "a", "type": "attr", "attr": "href" }
    }
    }
},
"content": {
    "selector": "div.read-content",
    "remove": [
    "script",
    "style",
    ".ad",
    ".copyright"
    ],
    "text_only": true,
    "join_with": "\n\n"
}
}
```

#### 4.1.2 字段类型说明

| 类型 | 说明 | 示例 |
|------|------|------|
| `text` | 提取文本内容 | `{type: "text"}` |
| `attr` | 提取属性值 | `{type: "attr", attr: "href"}` |
| `html` | 提取 HTML | `{type: "html"}` |

#### 4.1.3 字段修饰符

| 修饰符 | 类型 | 说明 |
|--------|------|------|
| `trim` | BOOLEAN | 是否去除首尾空格（默认 true） |
| `prefix` | STRING | 为结果添加前缀 |
| `suffix` | STRING | 为结果添加后缀 |
| `max_length` | INT | 最大长度截断 |

### 4.2 规则转换工具设计

#### 4.2.1 Legado → YLCraft 转换映射

| Legado 字段 | YLCraft 字段 | 转换规则 |
|-------------|--------------|----------|
| `ruleSearch.bookList` | `search.items.selector` | Legado 选择器 → CSS 选择器 |
| `ruleSearch.name` | `search.items.fields.title` | 提取类型设为 text |
| `ruleSearch.bookUrl` | `search.items.fields.url` | 提取类型设为 attr(href) |
| `ruleSearch.coverUrl` | `search.items.fields.cover` | 提取类型设为 attr(src) |
| `ruleToc.chapterList` | `toc.items.selector` | Legado 选择器 → CSS 选择器 |
| `ruleToc.chapterName` | `toc.items.fields.title` | 提取类型设为 text |
| `ruleToc.chapterUrl` | `toc.items.fields.url` | 提取类型设为 attr(href) |
| `ruleContent.content` | `content.selector` | Legado 选择器 → CSS 选择器 |
| `ruleContent.removeContent` | `content.remove` | 转为数组 |

#### 4.2.2 选择器转换规则

```python
def convert_selector(legado_selector: str) -> str:
    """将 Legado 选择器转换为标准 CSS 选择器"""
    # 1. 处理 tag.xxx → xxx
    selector = re.sub(r'^tag\.', '', legado_selector)
    
    # 2. 处理 class.xxx → .xxx
    selector = re.sub(r'class\.', '.', selector)
    
    # 3. 处理 id#xxx 或 id.xxx → #xxx
    selector = re.sub(r'id[#.]', '#', selector)
    
    # 4. 处理 @ 链语法（取最后一个选择器）
    if '@' in selector:
        parts = selector.split('@')
        selector = parts[-1]
    
    # 5. 移除索引语法（!N, .N）
    selector = re.sub(r'[.!]\d+$', '', selector)
    
    return selector
```

#### 4.2.3 转换流程

```
Legado 书源 JSON
    │
    ▼
解析 Legado 字段
    │
    ▼
选择器转换（Legado → CSS）
    │
    ▼
字段映射（ruleSearch → search）
    │
    ▼
特殊处理（JS 规则标记）
    │
    ▼
生成 YLCraft 格式
```

### 4.3 规则解析器设计

#### 4.3.1 解析器接口

```python
class RuleParser:
    """规则解析器基类"""
    
    def __init__(self, rule: dict):
        self.rule = rule
    
    def parse_search(self, html: str) -> list:
        """解析搜索结果"""
        pass
    
    def parse_toc(self, html: str) -> list:
        """解析目录"""
        pass
    
    def parse_content(self, html: str) -> str:
        """解析章节内容"""
        pass
```

#### 4.3.2 字段提取逻辑

```python
def extract_field(html: str, field_config: dict) -> str:
    """根据字段配置提取内容"""
    soup = BeautifulSoup(html, 'html.parser')
    
    selector = field_config['selector']
    field_type = field_config.get('type', 'text')
    
    element = soup.select_one(selector)
    if not element:
        return ""
    
    if field_type == 'text':
        result = element.get_text(strip=field_config.get('trim', True))
    elif field_type == 'attr':
        attr_name = field_config['attr']
        result = element.get(attr_name, "")
    elif field_type == 'html':
        result = str(element)
    
    # 应用修饰符
    if 'prefix' in field_config:
        result = field_config['prefix'] + result
    if 'suffix' in field_config:
        result = result + field_config['suffix']
    if 'max_length' in field_config:
        result = result[:field_config['max_length']]
    
    return result
```

---

## 5. 安全性设计

### 5.1 Cookie 安全

- **加密存储**：Cookie 内容使用 AES 加密存储
- **权限控制**：只有管理员和书源所有者可以访问 Cookie
- **日志审计**：记录 Cookie 访问日志

### 5.2 输入验证

- **URL 白名单**：只允许访问书源配置的域名
- **选择器安全**：防止 CSS 选择器注入
- **HTML 清理**：移除危险标签（script, iframe）

### 5.3 防止爬取攻击

- **请求频率限制**：每个书源每分钟最多请求 60 次
- **User-Agent 伪装**：模拟真实浏览器
- **请求间隔**：随机延迟 1-3 秒

---

## 6. 性能优化

### 6.1 缓存策略

- **Cookie 匹配结果缓存**：TTL 5 分钟
- **规则解析结果缓存**：TTL 1 小时
- **HTML 响应缓存**：TTL 10 分钟

### 6.2 异步处理

- **并发请求**：使用 asyncio 并发请求多个书源
- **非阻塞解析**：HTML 解析使用非阻塞方式

### 6.3 资源限制

- **HTML 大小限制**：最大 1MB
- **解析时间限制**：每个请求最大 30 秒
- **内存限制**：单个解析任务最大 512MB

---

## 7. 兼容性设计

### 7.1 双向兼容

```
┌─────────────────────────────────────────────────────────┐
│                    导入流程                             │
├─────────────────────────────────────────────────────────┤
│                                                        │
│  Legado 格式书源                                        │
│      │                                                  │
│      ▼                                                  │
│  RuleConverter 自动转换                                  │
│      │                                                  │
│      ▼                                                  │
│  YLCraft 格式（存储）                                    │
│                                                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    导出流程                             │
├─────────────────────────────────────────────────────────┤
│                                                        │
│  YLCraft 格式书源                                       │
│      │                                                  │
│      ▼                                                  │
│  RuleConverter 反向转换                                 │
│      │                                                  │
│      ▼                                                  │
│  Legado 格式（导出）                                    │
│                                                        │
└─────────────────────────────────────────────────────────┘
```

### 7.2 迁移策略

1. **自动迁移**：启动时自动将现有书源转换为新格式
2. **版本标记**：每个书源标记格式版本
3. **降级处理**：解析失败时尝试旧格式

---

## 8. 监控与日志

### 8.1 日志记录

| 日志类型 | 记录内容 |
|----------|----------|
| 请求日志 | URL、状态码、响应时间 |
| 解析日志 | 规则类型、匹配数量、耗时 |
| 错误日志 | 失败原因、堆栈信息 |
| 安全日志 | Cookie 访问、权限验证 |

### 8.2 监控指标

| 指标 | 说明 |
|------|------|
| 请求成功率 | 成功请求 / 总请求 |
| 平均响应时间 | 所有请求的平均耗时 |
| 解析成功率 | 成功解析 / 总解析 |
| Cookie 命中率 | 使用 Cookie 的请求比例 |

---

## 9. 部署与集成

### 9.1 数据库迁移

```sql
-- 创建 book_source_cookies 表
CREATE TABLE IF NOT EXISTS book_source_cookies (
    id VARCHAR(36) PRIMARY KEY,
    book_source_id VARCHAR(36) REFERENCES book_sources(id),
    domain VARCHAR(255) NOT NULL,
    cookie_content TEXT,
    description VARCHAR(255),
    is_active BOOLEAN DEFAULT 1,
    expires_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX idx_book_source_id ON book_source_cookies(book_source_id);
CREATE INDEX idx_domain ON book_source_cookies(domain);
CREATE INDEX idx_is_active ON book_source_cookies(is_active);
```

### 9.2 API 集成

新增端点：
- `GET /api/v1/book-sources/{id}/cookies` - 获取 Cookie 列表
- `POST /api/v1/book-sources/{id}/cookies` - 添加 Cookie
- `PUT /api/v1/book-sources/{id}/cookies/{cookie_id}` - 更新 Cookie
- `DELETE /api/v1/book-sources/{id}/cookies/{cookie_id}` - 删除 Cookie
- `GET /api/v1/book-sources/{id}/test` - 测试书源

---

## 10. 代码目录结构

```
backend/app/
├── api/v1/
│   └── book_sources.py          # 书源 API（新增 Cookie 和测试端点）
├── db/models/
│   └── book_source_cookie.py    # Cookie 模型（新增）
├── services/novel/
│   ├── book_source_manager.py   # 书源管理器（增强）
│   ├── cookie_manager.py        # Cookie 管理器（新增）
│   ├── rule_converter.py        # 规则转换器（新增）
│   └── rule_parser.py           # 规则解析器（新增）
```
