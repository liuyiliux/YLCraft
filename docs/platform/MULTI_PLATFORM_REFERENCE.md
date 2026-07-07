# 多平台自媒体项目参考文档

本文档整理了优秀的开源多平台自媒体项目，为 YLCraft 的多平台架构设计提供参考。

---

## 一、数据采集与分析平台

### 1. **MediaCrawler** ⭐ 16.4k Stars
**GitHub**: https://github.com/NanmiCoder/MediaCrawler

**项目简介**：
多平台自媒体数据采集工具，支持小红书、抖音、快手、B站、微博、贴吧、知乎等主流平台的公开信息抓取。采用 Playwright 自动化技术，无需复杂的 JS 逆向。

**技术架构**：
```
前端 (Vue/Node) 
    ↓
后端 API (Python/FastAPI)
    ↓
平台适配层 (Playwright自动化)
    ↓
数据存储层 (MySQL/SQLite/CSV/JSON)
```

**核心特性**：
| 功能 | B站 | 抖音 | 小红书 | 快手 | 微博 |
|------|------|------|--------|------|------|
| 关键词搜索 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 指定内容采集 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 评论爬取 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 用户主页 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 登录缓存 | ✅ | ✅ | ✅ | ✅ | ✅ |

**技术亮点**：
- 🎯 **零逆向技术**：基于 Playwright 保存登录态，避免复杂加密分析
- 🚀 **异步高效**：基于 asyncio 的高并发采集
- 🔄 **自动重试**：错误恢复和断点续爬
- 🌐 **代理支持**：自动代理池支持

**数据处理**：
- 多格式存储：SQLite、MySQL、CSV、JSON
- 自动数据清洗和去重
- 生成评论关键词词云
- 灵活的数据导出

**模块化设计**：
```
media_platform/      # 平台适配层
├── bilibili/       # B站实现
├── douyin/         # 抖音实现
├── xiaohongshu/    # 小红书实现
├── kuaishou/       # 快手实现
└── base.py         # 统一基类
```

---

### 2. **BiliOB 观测者** ⭐ 2.3k Stars
**GitHub**: https://github.com/NanmiCoder/BiliOB

**项目简介**：
观测 B站 UP 主及视频数据变化，并予以分析的 Web 应用程序。通过定时抓取 B站公开数据，构建包含粉丝数、视频播放量、弹幕数、评论情感等多维度指标的分析体系。

**核心功能**：
1. **综合数据看板**
   - 稿件基础数据统计（播放、点赞、收藏等）
   - 观众互动趋势分析
   - 粉丝增长关联分析
   - 多稿件横向对比
2. **定时数据追踪**
   - 自定义采样间隔（默认每小时）
   - 历史数据对比
   - 趋势预测分析
3. **粉丝增长分析**
   - 日/周/月增长曲线
   - 增长拐点标注
   - 与发布时间关联

**技术栈**：
- 后端：Python (FastAPI/Scrapy)
- 前端：Vue.js
- 数据库：MySQL + Redis
- 定时任务：Celery

**应用场景**：
- UP 主成长轨迹分析
- 视频内容效果对比
- 竞品数据监测

---

### 3. **BiliIns** ⭐ 300+ Stars
**Gitee**: https://gitee.com/ZerMi/BiliIns

**项目简介**：
哔哩哔哩创作者内容数据分析平台，为 UP 主提供全面、深入的内容数据分析。

**核心功能**：
| 模块 | 指标项 |
|------|--------|
| 基础数据 | 播放量、点赞、投币、收藏 |
| 观众分析 | 点赞率、投币率、互动率 |
| 互动分析 | 评论风向、评论影响 |

**特色功能**：
1. 🤖 **AI 评论分析**
   - 评论情感极性分析
   - 高频关键词提取
   - 弹幕内容聚类
   - 评论风向分析
2. 📊 **历史稿件对比**
   - 多稿件横向对比
   - 趋势变化追踪
3. 📈 **可视化报表**
   - 数据仪表盘
   - 导出 PDF/Excel（大饼）

---

### 4. **Visual_MediaCrawler** 
**GitHub**: https://github.com/persist-1/Visual_MediaCrawler

**项目简介**：
基于 MediaCrawler 的可视化自媒体平台爬虫，前后端分离的媒体数据采集平台。

**技术架构**：
```
前端 (React/Node)
    ↓
后端 API (Python/FastAPI)
    ↓
平台适配层
    ↓
数据存储 (SQLite)
```

**目录结构**：
```
api/              # 后端 API 层
base/             # 基础类定义
config/           # 配置管理
constant/         # 常量定义
frontend/         # 前端界面
libs/             # 第三方库封装
media_platform/   # 平台适配（和 MediaCrawler 保持一致）
storage/          # 存储抽象
```

---

## 二、多平台内容发布工具

### 5. **Social-Auto-Upload (SAU)** ⭐ 5.2k Stars
**GitHub**: https://github.com/dreammis/social-auto-upload

**项目简介**：
专为内容创作者和运营团队设计的开源自动化工具，支持一键将视频发布到抖音、Bilibili、小红书、快手、视频号、TikTok 等主流社交媒体平台。

**核心价值**：
⚡ 一键多平台发布 · 智能定时调度 · 零 API 依赖

**解决的行业痛点**：

| 传统痛点 | SAU 解决方案 |
|---------|-------------|
| 手动逐个平台上传 | 批量一键发布到 6+ 平台 |
| 发布时间难以统一 | 精准定时发布功能 |
| 平台 API 限制频繁变更 | 浏览器自动化模拟真实用户操作 |
| 多账号管理复杂 | Cookie 持久化与多账号切换支持 |
| 海外平台访问困难 | 内置代理支持（TikTok 等） |

**支持平台**：
- 🇨🇳 国内：抖音、视频号、B站、小红书、快手、百家号
- 🌍 海外：TikTok、Instagram、Facebook

**核心功能**：
1. **多平台支持**
   - 统一的 Cookie 管理
   - 多账号轮换
   - 代理配置
2. **智能调度系统**
   - 定时发布（Cron 表达式）
   - 队列管理
   - 失败重试
3. **内容优化**
   - 自动元数据生成
   - 封面图智能匹配
   - 描述模板化

**技术架构**：
```
Web UI (Vue)
    ↓
后端服务 (Python/FastAPI)
    ↓
平台上传器 (Playwright)
    ↓
各平台
```

**上传器架构**：
```
uploader/
├── base.py              # 统一基类
├── douyin_uploader.py    # 抖音
├── bilibili_uploader.py  # B站
├── xiaohongshu_uploader.py # 小红书
└── multiplatform_uploader.py # 多平台协调器
```

---

### 6. **自媒体发布平台 (MPP)** ⭐ 1.5k Stars
**GitHub**: https://github.com/andgwhat/MediaPublishPlatform

**项目简介**：
基于 SAU 的二次开发项目，扩展了更多平台支持，统一了各平台的登录和验证流程。

**新增功能**：
- ✅ 新增平台：TikTok、Instagram、Facebook、B站、百家号
- ✅ 统一登录验证流程
- ✅ 统一发布流程
- ✅ 一键发布功能
- ✅ 发布记录管理

**技术改进**：
```python
# 统一基类架构
class BaseUploader:
    def __init__(self):
        self.platform = None
        self.cookie_manager = CookieManager()
        
    async def upload(self, video_path, description, schedule_time=None):
        """统一上传接口"""
        pass
    
    async def batch_upload(self, tasks):
        """批量上传"""
        pass
```

**平台配置文件**：
```python
# platform_configs.py
PLATFORM_CONFIGS = {
    'bilibili': {
        'name': 'Bilibili',
        'enabled': True,
        'upload_url': '...',
        'cookie_required': True,
    },
    'douyin': {
        'name': '抖音',
        'enabled': True,
        'upload_url': '...',
        'cookie_required': True,
    },
}
```

---

## 三、通用内容管理系统

### 7. **MediaCMS** ⭐ 2.1k Stars
**GitHub**: https://github.com/mediacms-io/mediacms

**项目简介**：
现代、功能齐全的开源视频和媒体 CMS，使用 Python/Django 和 React 构建，配备 REST API。

**技术栈**：
- 后端：Django (Python)
- 前端：React
- 数据库：PostgreSQL
- 视频处理：FFmpeg、Bento4
- 后台任务：Celery

**核心特性**：
| 特性 | 说明 |
|------|------|
| 多媒体支持 | 视频、音频、图片、PDF |
| 自定义播放器 | video.js，支持多分辨率 |
| API 优先 | Swagger 文档化的 REST API |
| 高级搜索 | 实时搜索功能 |
| 分段上传 | 支持大文件上传 |
| 多语言字幕 | 支持字幕管理 |

**部署方式**：
- Docker 部署
- 手动安装
- 云平台部署

---

### 8. **TinaCMS**
**官网**: https://tinacms.org/

**项目简介**：
完全开源的无头 CMS，支持 Markdown 和可视化编辑，基于 Git 的内容管理解决方案。

**技术栈**：
- TypeScript
- React
- GraphQL
- Markdown/MDX

**核心特性**：
| 特性 | 实现 |
|------|------|
| 内容管理 | Markdown/MDX 支持 |
| 可视化编辑 | 实时预览编辑 |
| 版本控制 | Git 集成 |
| API 架构 | GraphQL API |
| 扩展性 | 插件系统 |

---

## 四、架构设计模式总结

### 4.1 多平台适配模式

#### 统一接口模式
```python
# 平台适配基类
class BasePlatformAdapter:
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.api_client = None
        
    async def get_user_info(self, user_id: str) -> UserInfo:
        """获取用户信息"""
        pass
    
    async def get_videos(self, user_id: str, page: int) -> List[Video]:
        """获取视频列表"""
        pass
    
    async def get_favorites(self, user_id: str) -> List[Favorite]:
        """获取收藏夹"""
        pass

# 具体平台实现
class BilibiliAdapter(BasePlatformAdapter):
    platform = 'bilibili'
    
class DouyinAdapter(BasePlatformAdapter):
    platform = 'douyin'
```

#### 策略模式
```python
# 数据采集策略
class DataCollectionStrategy(ABC):
    @abstractmethod
    async def collect(self, config: Config) -> Data:
        pass

class APIStrategy(DataCollectionStrategy):
    async def collect(self, config):
        # 基于 API 采集
        pass

class PlaywrightStrategy(DataCollectionStrategy):
    async def collect(self, config):
        # 基于浏览器自动化采集
        pass
```

### 4.2 数据存储模式

#### 统一数据模型
```python
# 统一数据结构
@dataclass
class UnifiedVideo:
    platform: str
    video_id: str
    title: str
    author: str
    author_id: str
    publish_time: datetime
    stats: VideoStats
    
@dataclass
class VideoStats:
    views: int
    likes: int
    coins: int
    favorites: int
    comments: int
    shares: int
```

#### 多存储后端
```python
class StorageFactory:
    @staticmethod
    def create_storage(storage_type: str) -> Storage:
        if storage_type == 'sqlite':
            return SQLiteStorage()
        elif storage_type == 'mysql':
            return MySQLStorage()
        elif storage_type == 'csv':
            return CSVStorage()
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
```

### 4.3 认证管理模式

#### Cookie 管理器
```python
class CookieManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        
    async def get_cookie(self, platform: str, user_id: str) -> str:
        """获取 Cookie"""
        pass
    
    async def save_cookie(self, platform: str, user_id: str, cookie: str):
        """保存 Cookie"""
        pass
    
    async def refresh_cookie(self, platform: str, user_id: str):
        """刷新 Cookie"""
        pass
```

#### 多账号管理
```python
class AccountManager:
    def __init__(self):
        self.accounts = {}  # platform -> [Account]
        
    async def add_account(self, platform: str, account: Account):
        pass
    
    async def get_available_account(self, platform: str) -> Account:
        """获取可用账号（轮询）"""
        pass
    
    async def mark_account_busy(self, account: Account):
        """标记账号为忙碌"""
        pass
```

### 4.4 任务调度模式

#### 定时任务
```python
class TaskScheduler:
    def __init__(self):
        self.tasks = {}
        
    def schedule(self, name: str, func: Callable, cron_expr: str):
        """调度定时任务"""
        pass
    
    async def execute_now(self, task_name: str, *args, **kwargs):
        """立即执行任务"""
        pass
```

#### 队列管理
```python
class TaskQueue:
    def __init__(self, max_concurrent: int = 5):
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
    async def add_task(self, task: Task):
        await self.queue.put(task)
        
    async def process(self):
        while True:
            task = await self.queue.get()
            async with self.semaphore:
                await self.execute_task(task)
```

---

## 五、推荐的最佳实践

### 5.1 YLCraft 可借鉴的架构

基于以上优秀项目，建议 YLCraft 采用以下架构：

```
┌─────────────────────────────────────────┐
│           前端界面 (React)               │
├─────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐       │
│  │ UP主分析    │  │ 账号中心    │       │
│  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────┤
│           API 网关 (FastAPI)             │
├─────────────────────────────────────────┤
│  ┌─────────────────────────────────┐   │
│  │        平台服务层                 │   │
│  │  ┌───────┐ ┌───────┐ ┌───────┐ │   │
│  │  │ B站   │ │ 抖音  │ │ 小红书│ │   │
│  │  └───────┘ └───────┘ └───────┘ │   │
│  └─────────────────────────────────┘   │
├─────────────────────────────────────────┤
│  ┌─────────────────────────────────┐   │
│  │        平台适配层                 │   │
│  │  ┌─────────┐ ┌─────────┐       │   │
│  │  │ API适配 │ │自动化适配│       │   │
│  │  └─────────┘ └─────────┘       │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 5.2 核心模块划分

| 模块 | 职责 | 优先级 |
|------|------|--------|
| **platform-adapter** | 统一平台接口 | ⭐⭐⭐ 高 |
| **data-collector** | 数据采集（API/自动化） | ⭐⭐⭐ 高 |
| **data-analyzer** | 数据分析（趋势、对比） | ⭐⭐ 中 |
| **account-manager** | 账号管理（Cookie、Token） | ⭐⭐⭐ 高 |
| **scheduler** | 定时任务调度 | ⭐⭐ 中 |
| **storage** | 多后端存储 | ⭐⭐ 中 |

### 5.3 数据流设计

```
用户操作
    ↓
前端请求
    ↓
API 网关（认证、限流）
    ↓
业务逻辑层（数据处理）
    ↓
平台适配层（统一接口）
    ↓
平台实现（B站、抖音、小红书...）
    ↓
数据存储（MySQL/Redis）
    ↓
响应返回
```

---

## 六、项目对比表

| 项目 | 类型 | 平台数 | 技术栈 | 数据分析 | 发布功能 | 开源协议 |
|------|------|--------|--------|----------|----------|----------|
| MediaCrawler | 数据采集 | 7+ | Python/Vue | ❌ | ❌ | MIT |
| BiliOB | 数据分析 | 1 | Python/Vue | ✅ | ❌ | GPL |
| BiliIns | 数据分析 | 1 | Python | ✅ | ❌ | 需授权 |
| SAU | 内容发布 | 6+ | Python/Vue | ❌ | ✅ | MIT |
| MPP | 内容发布 | 9+ | Python/Vue | ❌ | ✅ | MIT |
| MediaCMS | CMS | - | Django/React | ❌ | ✅ | AGPL |
| YLCraft | 综合平台 | 计划 5+ | FastAPI/React | ⭐⭐ | 计划 | MIT |

---

## 七、参考资料

1. **MediaCrawler**: https://github.com/NanmiCoder/MediaCrawler
2. **BiliOB**: https://github.com/NanmiCoder/BiliOB
3. **BiliIns**: https://gitee.com/ZerMi/BiliIns
4. **Social-Auto-Upload**: https://github.com/dreammis/social-auto-upload
5. **MediaPublishPlatform**: https://github.com/andgwhat/MediaPublishPlatform
6. **Visual_MediaCrawler**: https://github.com/persist-1/Visual_MediaCrawler
7. **MediaCMS**: https://github.com/mediacms-io/mediacms
8. **TinaCMS**: https://tinacms.org/

---

## 八、行动计划

基于以上分析，YLCraft 多平台模块的实施建议：

### Phase 1: 基础建设（当前）
- [x] B站平台适配（已完成）
- [ ] 统一平台接口设计
- [ ] 账号管理系统

### Phase 2: 扩展平台
- [ ] 抖音平台适配
- [ ] 小红书平台适配
- [ ] 数据存储抽象

### Phase 3: 数据分析
- [ ] 数据看板
- [ ] 趋势分析
- [ ] 对比分析

### Phase 4: 高级功能
- [ ] 定时任务
- [ ] 数据导出
- [ ] AI 分析

---

*文档最后更新：2026-05-19*
*维护者：YLCraft Team*
