# Design: 多平台生图模式

## 流程

```
用户输入 topic → [选择平台] → LLM 生成大纲 → 用户编辑 → 批量生图 → 按平台展示
```

## DB 模型

```python
class PlatformTemplate(SQLModel, table=True):
    __tablename__ = "platform_templates"
    id: UUID = pk
    platform: str (unique)       # xiaohongshu/douyin/wechat/toutiao
    name: str                     # 小红书/抖音/微信/头条
    outline_template: str         # LLM 大纲模板 {topic}
    image_template: str           # 生图提示词模板 {page_content}{page_type}
    video_template: Optional[str] # 视频模板
    default_size: str             # 768x1024 / 1080x1920
    is_active: bool
    sort_order: int
    created_at / updated_at
```

## API

### POST /images/generate-outline
```
Input:  { topic, platforms: ["xiaohongshu","douyin"] }
Output: {
  outline: {
    xiaohongshu: {
      title, description,
      pages: [{ type:"封面"|"内容"|"总结", prompt }]
    },
    douyin: { ... }
  }
}
```

### POST /images/generate-batch
复用现有 `BackendManager.generate_image()`，逐页并行调用。
```
Input:  { pages: [ { prompt, platform, size, provider, model, n } ] }
Output: { results: [ { platform, images: [urls] } ] }
```

### GET /images/platform-templates
```
Output: [ { id, platform, name, default_size, is_active } ]
```

## 前端

image-gen 页新增"多平台生图"Tab：topic 输入 → 平台多选 → 大纲展示/编辑 → 批量生成 → 按平台分组结果

## 预置平台数据

小红书(douyin)/抖音(xiaohongshu)/微信(wechat)/头条(toutiao) + 测试模板
