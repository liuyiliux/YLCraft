"""
YLCraft — 平台类型定义

架构拆分后的三类平台：
1. SocialMediaPlatform — 自媒体平台（内容发布）
2. AIProvider — AI 服务提供商（模型调用）
3. StoragePlatform — 存储/发布平台
"""

from __future__ import annotations
import enum


# =============================================================================
# 自媒体平台 — 用于内容发布和社交账号管理
# =============================================================================

class SocialMediaPlatform(str, enum.Enum):
    """自媒体/社交媒体平台"""
    XHS = "xhs"            # 小红书
    DOUYIN = "douyin"       # 抖音
    KUAISHOU = "kuaishou"   # 快手
    BILIBILI = "bilibili"   # B站
    WEIBO = "weibo"         # 微博
    ZHIHU = "zhihu"         # 知乎
    YOUTUBE = "youtube"     # YouTube
    TIKTOK = "tiktok"       # TikTok
    REDDIT = "reddit"       # Reddit
    TWITTER = "twitter"     # Twitter/X
    INSTAGRAM = "instagram" # Instagram
    FACEBOOK = "facebook"   # Facebook
    PINTEREST = "pinterest" # Pinterest
    QUORA = "quora"         # Quora
    LINKEDIN = "linkedin"   # LinkedIn


# =============================================================================
# AI 服务提供商 — 用于大模型和 AI 能力调用
# =============================================================================

class AIProvider(str, enum.Enum):
    """AI 服务提供商"""
    # OpenAI 系列
    OPENAI = "openai"                    # OpenAI (GPT-4, DALL-E, Whisper)
    AZURE_OPENAI = "azure_openai"        # Azure OpenAI

    # Anthropic 系列
    ANTHROPIC = "anthropic"               # Anthropic (Claude)

    # Google 系列
    GOOGLE = "google"                     # Google (Gemini, PaLM)
    GOOGLE_AI_STUDIO = "google_ai_studio" # Google AI Studio

    # 国内大模型
    MINIMAX = "minimax"                   # MiniMax (海螺AI)
    ZHIPU = "zhipu"                       # 智谱AI (GLM)
    DEEPSEEK = "deepseek"                 # DeepSeek
    QWEN = "qwen"                         # 通义千问
    BAIDU = "baidu"                       # 百度文心
    WENXIN = "wenxin"                     # 文心一言
    SPARK = "spark"                       # 讯飞星火
    TIANYU = "tianyu"                     # 天予AI
    YI = "yi"                             # 零一万物
    STEP = "step"                         # 阶跃星辰
    MILAGE = "milage"                     # 秘塔AI

    # 开源模型
    OLLAMA = "ollama"                     # Ollama (本地模型)
    LM_STUDIO = "lm_studio"              # LM Studio (本地模型)
    GROQ = "groq"                         # Groq (高速推理)

    # 其他 AI 服务
    COHERE = "cohere"                     # Cohere
    MISTRAL = "mistral"                   # Mistral AI
    ANTHROPIC_CLAUDE = "anthropic_claude" # Claude 独立部署


# =============================================================================
# 存储/发布平台 — 用于文件存储和自动化发布
# =============================================================================

class StoragePlatform(str, enum.Enum):
    """存储和发布平台"""
    WEBDAV = "webdav"        # WebDAV (坚果云等)
    S3 = "s3"                # AWS S3 / 兼容存储
    FTP = "ftp"              # FTP 服务器
    SFTP = "sftp"            # SFTP 服务器
    ALI_YUN = "aliyun"       # 阿里云 OSS
    TENCENT_COS = "tencent_cos"  # 腾讯云 COS
    QINIU = "qiniu"          # 七牛云存储


# =============================================================================
# 便捷的聚合类型
# =============================================================================

# 所有平台类型的联合类型
PlatformType = SocialMediaPlatform | AIProvider | StoragePlatform


# =============================================================================
# 平台元数据定义
# =============================================================================

SOCIAL_MEDIA_METADATA = {
    "xhs": {"name": "小红书", "color": "#fe2c55", "category": "social"},
    "douyin": {"name": "抖音", "color": "#000000", "category": "social"},
    "kuaishou": {"name": "快手", "color": "#ff5000", "category": "social"},
    "bilibili": {"name": "B站", "color": "#00aeec", "category": "social"},
    "weibo": {"name": "微博", "color": "#ff8200", "category": "social"},
    "zhihu": {"name": "知乎", "color": "#0066ff", "category": "social"},
    "youtube": {"name": "YouTube", "color": "#ff0000", "category": "social"},
    "tiktok": {"name": "TikTok", "color": "#000000", "category": "social"},
}

AI_PROVIDER_METADATA = {
    "openai": {"name": "OpenAI", "color": "#10a37f", "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "dall-e-3"]},
    "anthropic": {"name": "Anthropic", "color": "#d4a0e7", "models": ["claude-3-5-sonnet", "claude-3-opus"]},
    "minimax": {"name": "MiniMax", "color": "#00d4ff", "models": ["abab-6", "video-01"]},
    "zhipu": {"name": "智谱AI", "color": "#7fb3ff", "models": ["glm-4", "cogview-3"]},
    "deepseek": {"name": "DeepSeek", "color": "#6b8afd", "models": ["deepseek-chat", "deepseek-coder"]},
    "qwen": {"name": "通义千问", "color": "#1fa2ff", "models": ["qwen-turbo", "qwen-max"]},
    "baidu": {"name": "百度文心", "color": "#2932e1", "models": ["ernie-4.0", "ernie-3.5"]},
    "google": {"name": "Google", "color": "#4285f4", "models": ["gemini-pro", "gemini-ultra"]},
    "ollama": {"name": "Ollama", "color": "#4db6ac", "models": ["llama3", "mistral", "qwen2"]},
}

STORAGE_METADATA = {
    "webdav": {"name": "WebDAV", "color": "#607d8b"},
    "s3": {"name": "AWS S3", "color": "#ff9900"},
    "ftp": {"name": "FTP", "color": "#4caf50"},
    "aliyun": {"name": "阿里云OSS", "color": "#ff6a00"},
    "tencent_cos": {"name": "腾讯云COS", "color": "#00aeec"},
}


# =============================================================================
# 兼容性别名（用于过渡期）
# =============================================================================

# 为了向后兼容，保留旧的 PlatformType 引用
# 警告：这些将在后续版本中移除
import warnings
import functools

def _deprecated_enum_wrapper(enum_class, old_name):
    """创建已废弃枚举类的包装器"""
    @classmethod
    @functools.wraps(enum_class.value)
    def from_value(cls, value):
        warnings.warn(
            f"PlatformType is deprecated, use SocialMediaPlatform, AIProvider, or StoragePlatform",
            DeprecationWarning,
            stacklevel=2
        )
        # 尝试在所有新枚举中查找
        for e in [SocialMediaPlatform, AIProvider, StoragePlatform]:
            try:
                return e(value)
            except ValueError:
                continue
        raise ValueError(f"Unknown platform: {value}")
    return from_value
