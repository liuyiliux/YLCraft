# YLCraft 通用 Agent 平台设计方案

## 一、目标定位

参考 **OpenClaw**（开源 AI Agent 框架）和 **Hermes Agent**（持久记忆 + 越用越聪明）的核心理念，为 YLCraft 构建一个**通用 Agent 平台**：

1. **独立 Agent 页面** — 类似 ChatGPT 的对话框，可调用平台所有功能
2. **持久记忆** — 记住用户偏好、项目上下文、历史交互
3. **工具注册机制** — 动态注册/发现工具，而非硬编码
4. **多步规划** — 复杂任务自动拆解成多步
5. **异步执行** — 后台任务，前端可查看进度
6. **"发送到 Agent"** — 其他页面可把上下文发给 Agent

---

## 二、核心架构

```
┌────────────────────────────────────────────────────────────────┐
│                        前端 Agent 页面                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │ 对话窗口   │  │ 工具调用日志│  │ 任务执行进度│               │
│  └────────────┘  └────────────┘  └────────────┘               │
│                                                                  │
│  [发送到 Agent] ← 其他页面的统一入口                              │
└────────────────────────────────────────────────────────────────┘
                              │
                     POST /api/v1/agent/chat
                              │
┌────────────────────────────────────────────────────────────────┐
│                      Agent Service                              │
│  ┌──────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ 工具注册表        │  │ 会话管理器      │  │ 记忆管理器   │  │
│  │ ToolRegistry     │  │ SessionManager │  │ MemoryManager│  │
│  └──────────────────┘  └────────────────┘  └──────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                    工具集 (Tool Suite)                  │    │
│  │  asset_tools | clip_tools | subtitle_tools | ...      │    │
│  └────────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
                              │
                     调用现有 YLCraft 服务
                              │
┌────────────────────────────────────────────────────────────────┐
│                  现有 YLCraft 服务层                            │
│  AssetService | SubtitleService | BGMService | CutClaw...     │
└────────────────────────────────────────────────────────────────┘
```

---

## 三、目录结构

```
backend/app/
├── services/
│   └── agent/
│       ├── __init__.py           # 模块导出
│       ├── service.py            # Agent 核心服务
│       ├── registry.py           # 工具注册表
│       ├── memory/
│       │   ├── __init__.py
│       │   └── manager.py        # 记忆管理器
│       ├── session/
│       │   ├── __init__.py
│       │   └── manager.py        # 会话管理器
│       └── tools/
│           ├── __init__.py
│           ├── base.py           # 工具基类
│           ├── asset_tools.py    # 素材库工具
│           ├── clip_tools.py     # 剪辑工具
│           ├── subtitle_tools.py # 字幕工具
│           └── utils.py          # 工具辅助函数

backend/app/api/v1/
├── agent.py                      # Agent API 路由

frontend/src/
├── pages/
│   └── agent/
│       ├── index.tsx             # Agent 主页面
│       ├── ChatWindow.tsx        # 对话窗口组件
│       ├── ToolCallLog.tsx       # 工具调用日志
│       ├── TaskProgress.tsx      # 任务进度
│       └── context/
│           └── AgentContext.tsx  # 发送到 Agent 上下文
├── api/
│   └── index.ts                  # Agent API 调用
```

---

## 四、核心数据结构

### 4.1 工具定义 (Tool)

```python
@dataclass
class Tool:
    name: str                           # 工具唯一标识
    description: str                    # 工具描述（供 LLM 理解何时调用）
    parameters: dict                    # JSON Schema 参数定义
    handler: Callable                   # 工具执行函数
    category: str = "general"           # 分类：asset/clip/subtitle/bgm/...
    examples: list[str] = []            # 使用示例
    requires_progress: bool = False     # 是否需要进度回调
```

### 4.2 会话定义 (Session)

```python
@dataclass
class AgentSession:
    id: str                            # 会话 ID
    user_id: str = "default"            # 用户 ID
    title: str                          # 会话标题（首条消息摘要）
    messages: list[dict]                # 对话历史
    tool_calls: list[dict]              # 工具调用记录
    context: dict = {}                  # 外部传入的上下文
    created_at: datetime
    updated_at: datetime
```

### 4.3 记忆定义 (Memory)

```python
@dataclass
class AgentMemory:
    user_id: str                        # 用户 ID
    preferences: dict = {}              # 用户偏好
    project_context: dict = {}           # 项目上下文
    interaction_history: list[dict]     # 交互历史摘要
    updated_at: datetime
```

---

## 五、工具注册机制

### 5.1 工具注册表 (ToolRegistry)

```python
class ToolRegistry:
    _tools: dict[str, Tool] = {}
    _categories: dict[str, list[str]] = {}

    @classmethod
    def register(cls, tool: Tool):
        cls._tools[tool.name] = tool
        cls._categories.setdefault(tool.category, []).append(tool.name)

    @classmethod
    def get_tool(cls, name: str) -> Optional[Tool]:
        return cls._tools.get(name)

    @classmethod
    def get_tools_by_category(cls, category: str) -> list[Tool]:
        names = cls._categories.get(category, [])
        return [cls._tools[n] for n in names]

    @classmethod
    def get_all_tools(cls) -> list[Tool]:
        return list(cls._tools.values())

    @classmethod
    def get_tool_schemas(cls) -> list[dict]:
        """生成 LLM 可见的工具 Schema"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for tool in cls._tools.values()
        ]
```

### 5.2 工具装饰器

```python
def register_tool(
    name: str,
    description: str,
    category: str = "general",
    examples: list[str] = None,
):
    def decorator(func):
        tool = Tool(
            name=name,
            description=description,
            parameters=_infer_params(func),
            handler=func,
            category=category,
            examples=examples or [],
        )
        ToolRegistry.register(tool)
        return func
    return decorator

# 使用示例
@register_tool(
    name="search_assets",
    description="搜索素材库中的视频、图片、音频等资产",
    category="asset",
    examples=["搜索搞笑猫咪视频", "找找有没有美食素材"],
)
async def search_assets(query: str, asset_type: str = None, limit: int = 10):
    ...
```

---

## 六、工具集设计

### 6.1 素材库工具

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `search_assets` | 搜索素材库 | query, asset_type?, tags?, limit? |
| `get_asset_detail` | 获取资产详情 | asset_id |
| `download_asset` | 下载资产文件 | asset_id |
| `add_asset_tag` | 添加标签 | asset_id, tag |

### 6.2 剪辑工具

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `start_cutclaw_clip` | 启动 CutClaw Agent 剪辑 | video_path, instruction |
| `start_narrato_clip` | 启动 NarratoAI 剪辑 | video_path, target_duration?, num_clips? |
| `start_moe_clip` | 启动 MoE 多专家剪辑 | video_path, target_duration? |
| `get_clip_task_status` | 查询剪辑任务状态 | task_id |

### 6.3 字幕工具

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `extract_subtitle` | 提取视频字幕 | video_path, language?, format? |
| `get_subtitle_styles` | 获取字幕样式列表 | - |

### 6.4 BGM 工具

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `list_bgm_tracks` | 列出 BGM 曲目 | genre?, mood?, search? |
| `add_bgm_to_video` | 为视频添加 BGM | video_path, bgm_id, fade_in?, fade_out? |

### 6.5 爆款拆解工具

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `analyze_viral_content` | 分析爆款内容 | url |
| `generate_script` | 生成仿写脚本 | reference_url, topic |

---

## 七、API 设计

### 7.1 对话 API

```
POST /api/v1/agent/chat
  Body: { session_id?, message, context? }
  Response: { success, session_id, response, tool_calls?, task_id? }

GET /api/v1/agent/sessions
  Response: { sessions: [...] }

GET /api/v1/agent/sessions/{session_id}
  Response: { session, messages, tool_calls }

DELETE /api/v1/agent/sessions/{session_id}
  Response: { success }
```

### 7.2 任务 API

```
POST /api/v1/agent/send
  Body: { source_page, context_data }
  Response: { success, session_id, redirect_to_agent }

GET /api/v1/agent/tasks/{task_id}
  Response: { task_id, status, progress, result }
```

### 7.3 工具管理 API

```
GET /api/v1/agent/tools
  Response: { tools: [...], categories: [...] }
```

---

## 八、前端组件设计

### 8.1 Agent 页面布局

```
┌─────────────────────────────────────────────────────────┐
│ Agent — YLCraft 智能助手                         [历史] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │            对话区域 (ChatWindow)                 │   │
│  │                                                  │   │
│  │  🤖 Agent: 你好！有什么可以帮你的？              │   │
│  │                                                  │   │
│  │  👤 用户: 帮我找一个搞笑猫咪视频，提取字幕        │   │
│  │                                                  │   │
│  │  🔧 工具调用日志 (ToolCallLog)                  │   │
│  │   └ search_assets("搞笑猫咪视频") → 3个结果      │   │
│  │   └ extract_subtitle("xxx.mp4") → 完成          │   │
│  │                                                  │   │
│  │  🤖 Agent: 找到了！以下是结果...                 │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  📎 附件: [视频缩略图] [字幕文件]      [下载]    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ [输入框: 说你想做什么...]                    [发送]│   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.2 发送到 Agent

在其他页面添加「发送到 Agent」按钮：

```tsx
// AgentContext 提供全局 sendToAgent 方法
import { useAgent } from '@/context/AgentContext'

function AssetPage() {
  const { sendToAgent } = useAgent()

  const handleSendToAgent = () => {
    sendToAgent({
      source: 'assets',
      action: 'analyze',
      data: {
        selectedAssets: [asset1, asset2],
        userIntent: '分析这些视频的内容和风格'
      }
    })
  }

  return (
    <Button onClick={handleSendToAgent}>
      发送到 Agent
    </Button>
  )
}
```

---

## 九、实施计划

### Phase 1: 核心框架 (MVP)
1. **ToolRegistry** — 工具注册表 + 装饰器
2. **基础工具** — 素材库搜索、剪辑任务查询
3. **AgentService** — 核心 Agent 循环
4. **Agent API** — /chat, /sessions
5. **前端页面** — 对话窗口 + 工具调用日志

### Phase 2: 工具扩展
6. **字幕工具** — 提取、样式
7. **BGM 工具** — 列表、混音
8. **爆款拆解工具** — 链接分析、脚本生成
9. **进度任务** — 异步任务 + 进度展示

### Phase 3: 记忆系统
10. **SessionManager** — 会话持久化
11. **MemoryManager** — 用户偏好、项目上下文
12. **历史会话** — 会话列表、切换

### Phase 4: 高级功能
13. **多步规划** — 任务拆解 + 执行计划
14. **发送到 Agent** — 全局上下文传递
15. **记忆进化** — 基于交互历史优化响应

---

## 十、关键文件清单

### 新建文件

**后端：**
- `backend/app/services/agent/__init__.py`
- `backend/app/services/agent/service.py` — Agent 核心
- `backend/app/services/agent/registry.py` — 工具注册表
- `backend/app/services/agent/memory/manager.py` — 记忆管理
- `backend/app/services/agent/session/manager.py` — 会话管理
- `backend/app/services/agent/tools/base.py` — 工具基类
- `backend/app/services/agent/tools/asset_tools.py` — 素材库工具
- `backend/app/services/agent/tools/clip_tools.py` — 剪辑工具
- `backend/app/services/agent/tools/subtitle_tools.py` — 字幕工具
- `backend/app/services/agent/tools/bgm_tools.py` — BGM 工具
- `backend/app/services/agent/tools/breaker_tools.py` — 爆款拆解工具
- `backend/app/api/v1/agent.py` — API 路由

**前端：**
- `frontend/src/pages/agent/index.tsx` — Agent 主页面
- `frontend/src/pages/agent/ChatWindow.tsx` — 对话窗口
- `frontend/src/pages/agent/ToolCallLog.tsx` — 工具日志
- `frontend/src/pages/agent/SessionList.tsx` — 会话列表
- `frontend/src/context/AgentContext.tsx` — Agent 全局上下文
- `frontend/src/api/index.ts` — 新增 Agent API 调用

### 修改文件
- `frontend/src/App.tsx` — 添加 /agent 路由
- `frontend/src/components/layout/AppLayout.tsx` — 添加「智能体」菜单项
- `backend/app/main.py` — 注册 Agent 路由

---

## 十一、技术要点

1. **工具 Schema 生成** — ToolRegistry 自动生成 LLM 可见的 function calling schema
2. **异步任务** — 使用现有 TaskQueue，Agent 调用工具时返回 task_id
3. **流式响应** — 使用 Server-Sent Events (SSE) 实现打字机效果
4. **会话存储** — SQLite (与现有数据库共用)
5. **记忆存储** — JSON 文件或 SQLite 持久化

---

## 十二、预期效果

- 用户可以在 Agent 页面用自然语言完成复杂任务
- 其他页面可以「发送到 Agent」继续处理
- Agent 会记住用户偏好和项目上下文
- 复杂任务自动拆解成多步执行
- 后台任务可查看进度
