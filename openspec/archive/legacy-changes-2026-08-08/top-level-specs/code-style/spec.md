## Requirements

### Requirement: Python 命名风格规范
Python 代码 SHALL 遵循 PEP 8 命名约定，并额外遵守以下项目特定规则：

| 类型 | 约定 | 示例 |
|------|------|------|
| 类名 | PascalCase | `ImageService`, `VideoDownloadTask` |
| 函数/方法 | snake_case | `generate_image()`, `parse_cookie()` |
| 变量 | snake_case | `api_key`, `db_session` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` |
| 私有成员 | 单下划线前缀 | `_cache`, `_validate_token()` |
| 文件名 | snake_case | `image_service.py`, `cookie_store.py` |
| 模块目录名 | snake_case | `platform_connection/`, `social_media_connector/` |

#### Scenario: Python 代码命名
- **WHEN** 编写或修改 Python 代码
- **THEN** SHALL 严格遵循上表命名约定，保持全项目一致

### Requirement: TypeScript 命名风格规范
TypeScript 代码 SHALL 遵循以下命名约定：

| 类型 | 约定 | 示例 |
|------|------|------|
| 组件 | PascalCase | `ImageGen.tsx`, `VideoPlayer.tsx` |
| 接口/类型 | PascalCase | `ImageGenerateParams`, `ApiResponse<T>` |
| 枚举 | PascalCase | `TaskStatus`, `ProcessingMode` |
| 函数/变量 | camelCase | `handleSubmit`, `isLoading` |
| 常量 | UPPER_SNAKE_CASE | `API_BASE_URL`, `MAX_FILE_SIZE` |
| CSS 类名 | kebab-case | `image-preview`, `video-list-item` |
| 文件/目录 | kebab-case | `image-gen/`, `api-client.ts` |
| Hook | use 前缀 + camelCase | `useWebSocket`, `useVideoTask` |

#### Scenario: TypeScript 代码命名
- **WHEN** 编写或修改 TypeScript/TSX 代码
- **THEN** SHALL 严格遵循上表命名约定，保持前后端风格各自一致

### Requirement: 注释与文档字符串规范
注释 SHALL 遵循以下规范：
- **Python**：公共类和函数必须有 docstring（Google 风格或 NumPy 风格）
- **TypeScript**：复杂函数使用 JSDoc 注释，接口属性使用行内注释说明
- **TODO/FIXME/HACK**：必须标注作者或原因，格式为 `TODO(原因)` 或 `FIXME(原因)`
- **禁止**：无意义的注释（如 `i++ // i加1`）

```python
# Python docstring 示例
class ImageService:
    """图片生成服务。
    
    负责 ComfyUI 工作流的调度和结果处理。
    
    Args:
        db_session: 异步数据库会话
        config: Provider 配置实例
    """
    
    async def generate(self, prompt: str, model_id: str) -> ImageResult:
        """生成单张图片。
        
        Args:
            prompt: 用户输入的正向提示词
            model_id: 要使用的模型 ID
            
        Returns:
            ImageResult: 包含图片 URL 和元数据
            
        Raises:
            ImageGenerationError: 当 ComfyUI 返回错误时
        """
```

```typescript
// TypeScript JSDoc 示例
interface ImageGenerateParams {
  /** 正向提示词，支持权重语法如 (word:1.2) */
  prompt: string;
  /** 负向提示词 */
  negativePrompt?: string;
  /** 生成尺寸，默认 1024x1024 */
  size?: [number, number];
}

/** 提交图片生成任务 */
async function submitImageTask(params: ImageGenerateParams): Promise<TaskId> { ... }
```

#### Scenario: 为代码添加注释
- **WHEN** 编写公共 API 或复杂逻辑
- **THEN** SHALL 添加规范的 docstring/JSDoc，解释意图而非复述代码

### Requirement: 文件组织规范
文件内部结构 SHALL 遵循一致的顺序：

**Python 文件头部顺序：**
1. 模块 docstring
2. 标准库导入（按字母序）
3. 第三方库导入（按字母序）
4. 项目内导入（相对导入或绝对导入）
5. 模块级常量
6. 类/函数定义（先公开后私有）

**TypeScript 文件头部顺序：**
1. 文件注释（如有）
2. React 导入 (`react`, `react-dom`)
3. 第三方库导入 (`antd`, `axios`)
4. 项目内导入（`@/xxx` 别名）
5. 类型定义
6. 组件/函数定义

#### Scenario: 组织文件内容
- **WHEN** 创建或重构源文件
- **THEN** SHALL 按上述顺序组织 import 和定义，保持文件整洁

### Requirement: 类型安全规范
代码 SHALL 最大化类型安全：
- **Python**：所有函数参数和返回值必须有类型注解；使用 `from __future__ import annotations`
- **TypeScript**：禁用 `any` 类型（除非处理不可知的第三方数据）；优先使用 `interface` 而非 `type alias` 定义对象结构
- **边界场景**：JSON 解析等动态数据处使用 `model_validate` 或 `TypeGuard`

```python
# Python 类型注解示例
from typing import Optional, List

async def search_videos(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    order: str = "pubdate"
) -> SearchResult[VideoItem]:
    """搜索 B 站视频。"""
    ...

# 禁止
def process(data):  # 缺少类型注解！
    ...
```

```typescript
// TypeScript 类型安全示例
// 正确 ✅
interface VideoItem {
  bvid: string;
  title: string;
  duration: number;
}

// 禁止 ❌
const result: any = await fetchData();
console.log(result.foo.bar); // 无类型检查
```

#### Scenario: 编写类型安全的代码
- **WHEN** 编写新的函数、组件或数据结构
- **THEN** SHALL 为所有变量、参数、返回值提供完整的类型声明
