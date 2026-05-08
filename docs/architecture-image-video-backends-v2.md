# YLCraft 图像/视频生成后端架构设计 v2.0

> **版本**：v2.0  
> **状态**：设计阶段  
> **最后更新**：2026-05-06  
> **参考项目**：Pixelle-Video（ComfyUI 工作流）、yiliu（通用 API 配置驱动）  
> **前置文档**：`DESIGN.md` 第十一章

---

## 一、当前状态分析

### 1.1 现有实现

```
ImageBackend (Protocol)
  └── MiniMaxImageBackend  ✅ 已实现

VideoBackend (Protocol)
  └── MiniMaxVideoBackend  ✅ 已实现
```

**配置方式**：YAML 文件（`backend/config/providers.yaml`）

### 1.2 存在问题

| 问题 | 说明 |
|------|------|
| **Provider 单一** | 只支持 MiniMax，不支持 GPT-Image2、即梦、Bananapro 等流行模型 |
| **无 ComfyUI 支持** | 用户可能有本地 ComfyUI 或 RunningHub 工作流，无法使用 |
| **配置不够灵活** | YAML 静态配置，不支持用户自定义 API Key |
| **OpenAI 兼容 API 未抽象** | GPT/MiniMax/即梦等 OpenAI 兼容 API 应该可以通用实现 |

---

## 二、目标架构

### 2.1 核心设计思路

**OpenAI 类型 API 调用** 和 **ComfyUI 工作流调用** 是两种分开的方式，不应该统一：

```
ImageBackend (Protocol)
  ├── GenericImageBackend      ← 配置驱动，支持所有 OpenAI 兼容 API
  │     (参考 yiliu 的 GenericImageProvider)
  │     一个配置文件 = 一个 Provider
  │     支持：GPT-Image2 / 即梦 / Bananapro / MiniMax / ...
  │
  ├── ComfyUIImageBackend     ← ComfyUI 工作流
  │     (参考 Pixelle-Video 的 MediaService + ComfyKit)
  │     支持：本地 ComfyUI / RunningHub
  │
  └── (不再需要单独的 MiniMaxImageBackend)

VideoBackend (Protocol)
  ├── GenericVideoBackend      ← 配置驱动，支持所有 OpenAI 兼容视频 API
  ├── ComfyUIVideoBackend     ← ComfyUI 工作流（视频生成）
  └── (不再需要单独的 MiniMaxVideoBackend)
```

### 2.2 两种 Backend 的调用方式对比

| 特性 | GenericImageBackend | ComfyUIImageBackend |
|------|---------------------|----------------------|
| **调用方式** | HTTP REST API | ComfyUI 工作流 JSON |
| **配置驱动** | ✅ request_template + response_config | ❌ 需要写 Python 代码 |
| **新增 Provider** | 只需写 YAML/DB 配置 | 需要写 workflow JSON + 可能的适配代码 |
| **适用场景** | GPT-Image2、即梦、Bananapro 等 API | 本地 ComfyUI、RunningHub 云服务 |
| **参考项目** | yiliu（GenericImageProvider） | Pixelle-Video（MediaService） |

---

## 三、GenericImageBackend 设计（配置驱动）

### 3.1 核心思路（参考 yiliu）

**一个配置文件 = 一个 Provider**，无需写代码：

```yaml
# providers.yaml 或数据库记录
providers:
  gpt-image2:
    type: generic_image
    display_name: "GPT-Image2 (DALL-E 3)"
    base_url: "https://api.openai.com/v1/images/generations"
    api_key: "${OPENAI_API_KEY}"
    request_template: |
      {
        "model": "dall-e-3",
        "prompt": "{{ prompt }}",
        "size": "{{ size }}",
        "n": {{ n }},
        "quality": "{{ quality | default('standard') }}"
      }
    response_config:
      images_path: "$.data[*].url"
      error_path: "$.error.message"
    supported_sizes:
      - "1024x1024"
      - "1792x1024"
      - "1024x1792"
    default_params:
      n: 1
      quality: "standard"

  jimeng:  # 即梦（假设 OpenAI 兼容）
    type: generic_image
    display_name: "即梦 Jimeng 2.0"
    base_url: "https://api.jimeng.com/v1/images/generations"
    api_key: "${JIMENG_API_KEY}"
    request_template: |
      {
        "model": "jimeng-2.0",
        "prompt": "{{ prompt }}",
        "negative_prompt": "{{ negative_prompt | default('') }}",
        "size": "{{ size }}"
      }
    response_config:
      images_path: "$.data.images[*].url"

  minimax:  # MiniMax（如果兼容 OpenAI 格式）
    type: generic_image
    display_name: "MiniMax Seedance 2.0"
    base_url: "https://api.minimax.chat/v1/images/generations"
    api_key: "${MINIMAX_API_KEY}"
    request_template: |
      {
        "model": "seedance-2.0",
        "prompt": "{{ prompt }}",
        "size": "{{ size }}"
      }
    response_config:
      images_path: "$.data[*].url"
```

### 3.2 配置字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `type` | 固定为 `generic_image` | `generic_image` |
| `display_name` | 前端展示名称 | `GPT-Image2 (DALL-E 3)` |
| `base_url` | API 端点 | `https://api.openai.com/v1/images/generations` |
| `api_key` | API Key（支持环境变量） | `${OPENAI_API_KEY}` |
| `request_template` | Jinja2 模板，渲染为请求体 | 见上 |
| `response_config.images_path` | JSONPath，从响应提取图像 URL | `$.data[*].url` |
| `response_config.error_path` | JSONPath，从响应提取错误信息 | `$.error.message` |
| `supported_sizes` | 支持的尺寸列表 | `["1024x1024", "1792x1024"]` |
| `default_params` | 默认参数 | `{ n: 1, quality: "standard" }` |
| `parameter_transforms` | 参数转换规则（可选） | 见下方 |

### 3.3 参数转换示例

某些 API 的参数是自定义的，可以用 `parameter_transforms` 转换：

```yaml
parameter_transforms:
  size: "{{ size | replace('x', '*') }}"  # 1024x1024 → 1024*1024
  n: "{{ n | int }}"  # 确保是整数
```

---

## 四、ComfyUIImageBackend 设计（工作流驱动）

### 4.1 核心思路（参考 Pixelle-Video）

通过 **ComfyKit** 统一调用本地 ComfyUI 和 RunningHub：

```python
# services/image/comfyui_backend.py

class ComfyUIImageBackend:
    """
    ComfyUI 图像生成 Backend
    通过 ComfyKit 统一调用本地 ComfyUI / RunningHub
    """
    
    def __init__(self, config: dict):
        """
        Args:
            config: {
                "comfyui_url": "http://127.0.0.1:8188",
                "runninghub_api_key": "...",  # 可选
                "workflow": "workflows/selfhost/flux.json",  # 工作流文件路径
            }
        """
        self.kit = ComfyKit(
            comfyui_url=config.get("comfyui_url"),
            runninghub_api_key=config.get("runninghub_api_key")
        )
        self.workflow_path = config["workflow"]
    
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        # 1. 加载 workflow JSON
        with open(self.workflow_path, 'r') as f:
            workflow = json.load(f)
        
        # 2. 填充参数（根据 workflow 的 API 节点）
        #    这里需要针对具体 workflow 写适配代码
        workflow["prompt"]["3"]["inputs"]["text"] = req.prompt
        workflow["prompt"]["5"]["inputs"]["width"] = req.width
        workflow["prompt"]["5"]["inputs"]["height"] = req.height
        
        # 3. 提交到 ComfyUI / RunningHub
        result = await self.kit.execute(workflow, {})
        
        # 4. 返回结果
        return ImageGenerationResult(
            success=True,
            url=result.images[0],
            provider="comfyui",
            model=self.workflow_path
        )
```

### 4.2 Workflow 文件格式

**本地 ComfyUI**（`workflows/selfhost/flux.json`）：
- 标准 ComfyUI workflow JSON
- 不包含 `"source"` 字段

**RunningHub**（`workflows/runninghub/flux.json`）：
```json
{
  "source": "runninghub",
  "workflow_id": "123456",
  "workflow": { ... }  // 可选：内嵌 workflow JSON
}
```

### 4.3 配置示例

```yaml
providers:
  comfyui-flux:
    type: comfyui_image
    display_name: "ComfyUI FLUX (本地)"
    comfyui_url: "http://127.0.0.1:8188"
    workflow: "workflows/selfhost/flux.json"

  runninghub-sdxl:
    type: comfyui_image
    display_name: "RunningHub SDXL (云端)"
    runninghub_api_key: "${RUNNINGHUB_API_KEY}"
    workflow: "workflows/runninghub/sdxl.json"
```

---

## 五、配置方式选型：YAML vs 数据库

### 5.1 当前方式：YAML

**优点**：
- 简单，适合开发和单机部署
- 版本控制友好（可提交到 Git）

**缺点**：
- 不支持多用户各自配置 API Key
- 修改需要重启服务
- 不适合 SaaS 化

### 5.2 推荐方式：数据库

**数据表设计**：

```sql
CREATE TABLE provider_configs (
    id UUID PRIMARY KEY,
    user_id UUID,  -- 如果是多用户，关联用户
    provider_key VARCHAR(50) NOT NULL,  -- "gpt-image2"
    provider_type VARCHAR(20) NOT NULL,  -- "generic_image" | "comfyui_image"
    display_name VARCHAR(100),
    config_json JSON NOT NULL,  -- 完整的配置（包含 base_url、request_template 等）
    is_default BOOLEAN DEFAULT FALSE,  -- 是否为默认 Provider
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider_key)
);
```

**前端管理界面**：
- 用户可配置自己的 API Key
- 可启用/禁用某个 Provider
- 可设置默认 Provider

### 5.3 混合方案（推荐）

```
开发环境 → YAML 配置（方便调试）
生产环境 → 数据库配置（支持多用户）
```

在 `config.yaml` 中切换：

```yaml
provider_config_source: "yaml"  # 或 "database"
```

---

## 六、实现计划

### Phase 1：GenericImageBackend（1-2 天）

1. **实现 `GenericImageBackend` 类**
   - 参考 `yiliu/backend/src/providers/generic_image_provider.py`
   - 支持 `request_template`（Jinja2）+ `response_config`（JSONPath）
   
2. **修改 `BackendManager`**
   - 根据 `type` 字段实例化对应的 Backend
   - `generic_image` → `GenericImageBackend`
   - `comfyui_image` → `ComfyUIImageBackend`（Phase 2 实现）
   
3. **迁移配置**
   - 将 `providers.yaml` 中的 `minimax` 改为 `generic_image` 类型
   - 添加 `gpt-image2`、`jimeng` 等 Provider 配置

### Phase 2：ComfyUIImageBackend（1 天）

1. **安装 ComfyKit**
   ```bash
   pip install comfykit
   ```
   
2. **实现 `ComfyUIImageBackend` 类**
   - 参考 Pixelle-Video 的 `MediaService`
   - 支持本地 ComfyUI + RunningHub
   
3. **添加 workflow 文件**
   - `workflows/selfhost/flux.json`
   - `workflows/runninghub/flux.json`

### Phase 3：数据库配置迁移（可选，1 天）

1. **创建 `provider_configs` 表**
2. **实现配置加载逻辑**
   - `BackendManager` 从数据库加载配置
   - 支持热更新（定时轮询或 WebSocket 推送）
   
3. **前端管理页面**
   - `/settings/providers` 页面
   - 用户可配置 API Key、启用/禁用 Provider

---

## 七、文件结构

```
backend/
├── app/
│   ├── services/
│   │   ├── image/
│   │   │   ├── base.py              # ImageBackend Protocol
│   │   │   ├── generic_backend.py  # GenericImageBackend（新增）
│   │   │   ├── comfyui_backend.py # ComfyUIImageBackend（新增）
│   │   │   └── minimax.py        # MiniMaxImageBackend（保留，或迁移到 generic）
│   │   │
│   │   ├── video/
│   │   │   ├── base.py              # VideoBackend Protocol
│   │   │   ├── generic_backend.py  # GenericVideoBackend（新增）
│   │   │   ├── comfyui_backend.py # ComfyUIVideoBackend（新增）
│   │   │   └── minimax.py        # MiniMaxVideoBackend（保留）
│   │   │
│   │   └── backend_manager.py     # 修改：根据 type 实例化 Backend
│   │
│   ├── api/v1/
│   │   └── providers.py           # 修改：返回数据库中的 Provider 列表
│   │
│   └── db/
│       └── models/
│           └── provider_config.py  # 新增：provider_configs 表模型（可选）
│
├── config/
│   └── providers.yaml            # 保留：开发环境配置
│
└── workflows/                    # 新增：ComfyUI workflow 文件
    ├── selfhost/
    │   └── flux.json
    └── runninghub/
        └── flux.json
```

---

## 八、关键决策

### 决策 1：是否保留 MiniMaxImageBackend？

**选择**：保留，但改为使用 `GenericImageBackend` 配置驱动。

**原因**：
- 如果 MiniMax API 兼容 OpenAI 格式，只需写配置
- 如果不兼容，再保留 `MiniMaxImageBackend` 作为特例

### 决策 2：配置方式选 YAML 还是数据库？

**选择**：**先 YAML，后数据库**。

**原因**：
- YAML 快速验证架构可行性
- 数据库需要设计前端管理界面，工作量更大
- 可以在 Phase 3 再迁移

### 决策 3：ComfyUIImageBackend 是否一定要用 ComfyKit？

**选择**：**是**，参考 Pixelle-Video。

**原因**：
- ComfyKit 已经处理了本地 ComfyUI 和 RunningHub 的差异
- 自己实现需要写大量适配代码

---

## 九、参考资料

| 项目 | 参考内容 | 路径 |
|------|---------|------|
| **yiliu** | `GenericImageProvider` 配置驱动实现 | `F:/workspace/图文/yiliu/backend/src/providers/generic_image_provider.py` |
| **Pixelle-Video** | `MediaService` + ComfyKit 调用 | `F:/PycharmProjects/YLCraft-refs/Pixelle-Video/pixelle_video/services/media.py` |
| **Pixelle-Video** | `ComfyBaseService` 基类 | `F:/PycharmProjects/YLCraft-refs/Pixelle-Video/pixelle_video/services/comfy_base_service.py` |
| **YLCraft DESIGN.md** | 当前架构设计 | `F:/PycharmProjects/YLCraft/DESIGN.md` 第十一章 |

---

*本文档为 YLCraft v2.0 图像/视频生成后端架构设计，确认后可作为开发基准。*
