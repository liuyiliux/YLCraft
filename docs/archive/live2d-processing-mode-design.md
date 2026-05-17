# Live2D工厂 - 处理模式切换设计方案

## 1. 目标
为每个处理环节（抠图、风格转换、图像分割）提供**本地模型**和**云端API**两种处理方式，用户可灵活切换。

## 2. 处理模式枚举

```python
class ProcessingMode(str, Enum):
    LOCAL = "local"    # 本地模型（省钱，隐私性好）
    API = "api"        # 云端API（高质量，快速）
```

## 3. 配置层级（优先级从高到低）

### 3.1 请求级别（最高优先级）
每次API请求时通过`mode`参数指定：
```
POST /api/v1/live2d/{id}/rembg?mode=api
POST /api/v1/live2d/{id}/style-transfer?mode=local
```

### 3.2 模型级别配置
在`Live2DModel`表中添加`processing_config`字段（JSON）：
```json
{
  "rembg": "local",           // 抠图使用本地
  "style_transfer": "api",   // 风格转换使用API
  "segmentation": "local"     // 分割使用本地
}
```

### 3.3 全局默认配置（最低优先级）
配置文件`config/live2d.json`：
```json
{
  "default_processing_mode": "local",
  "api_keys": {
    "remove_bg": "xxx",      // Remove.bg API
    "replicate": "xxx",      // Replicate API（SD）
    "huggingface": "xxx"     // Hugging Face Inference API
  }
}
```

## 4. 各环节API方案

### 4.1 抠图（Rembg）
| 模式 | 方案 | 优点 | 缺点 |
|------|------|------|------|
| 本地 | RMBG-1.4 (rembg) | 免费、隐私 | 需要下载模型 |
| API | Remove.bg API | 高质量、快速 | 需要API Key、按次收费 |

**API调用示例**：
```python
import requests

response = requests.post(
    "https://api.remove.bg/v1.0/removebg",
    headers={"X-Api-Key": "YOUR_API_KEY"},
    files={"image_file": open("image.jpg", "rb")},
    data={"size": "auto"}
)
```

### 4.2 风格转换（Style Transfer）
| 模式 | 方案 | 优点 | 缺点 |
|------|------|------|------|
| 本地 | AnimeGANv2/v3 | 免费、快速 | 质量一般 |
| 本地 | SD + ControlNet | 高质量 | 需要强GPU |
| API | Replicate (SD) | 高质量、无需GPU | 按次收费 |
| API | Hugging Face Inference API | 多种模型可选 | 需要API Key |

**API调用示例（Replicate）**：
```python
import requests

response = requests.post(
    "https://api.replicate.com/v1/predictions",
    headers={
        "Authorization": f"Token {API_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "version": "stability-ai/sdxl:...",
        "input": {
            "prompt": "anime style, high quality",
            "image": "https://...",
        }
    }
)
```

### 4.3 图像分割（Segmentation）
| 模式 | 方案 | 优点 | 缺点 |
|------|------|------|------|
| 本地 | BiRefNet | 高质量人像分割 | 需要GPU |
| 本地 | U-2-Net | 通用分割 | 质量一般 |
| API | Remove.bg API（精细边缘） | 高质量 | 收费 |
| API | Hugging Face Inference API | 免费额度 | 需要网络连接 |

**API调用示例（Hugging Face）**：
```python
import requests

response = requests.post(
    "https://api-inference.huggingface.co/models/ZigBread/BiRefNet",
    headers={"Authorization": f"Bearer {HF_TOKEN}"},
    data=open("image.jpg", "rb").read()
)
```

## 5. 实现步骤

### Step 1: 创建配置管理模块
- `backend/app/core/config.py` - 配置管理
- `backend/config/live2d.json` - 配置文件

### Step 2: 修改数据模型
- `Live2DModel`添加`processing_config`字段

### Step 3: 修改服务代码
- `rembg.py` - 添加API调用方法
- `style_transfer.py` - 添加API调用方法
- `segmentation.py` - 添加API调用方法

### Step 4: 更新API端点
- 添加`mode`查询参数
- 读取配置优先级
- 调用对应服务方法

### Step 5: 更新前端界面
- 添加模式切换开关
- 显示当前使用的方式
- 保存用户偏好

## 6. 文件清单

### 新增文件
- `backend/app/core/config.py` - 配置管理
- `backend/config/live2d.json` - 配置文件
- `backend/app/services/live2d/api_client.py` - API调用封装

### 修改文件
- `backend/app/db/models/live2d.py` - 添加processing_config字段
- `backend/app/services/live2d/rembg.py` - 添加API模式
- `backend/app/services/live2d/style_transfer.py` - 添加API模式
- `backend/app/services/live2d/segmentation.py` - 添加API模式
- `backend/app/api/v1/live2d.py` - 添加mode参数
- `frontend/src/pages/live2d/index.tsx` - 添加切换控件

## 7. 时间估算
- Step 1-2: 1小时
- Step 3: 2小时
- Step 4-5: 1.5小时
- 测试: 0.5小时
**总计: 5小时**
