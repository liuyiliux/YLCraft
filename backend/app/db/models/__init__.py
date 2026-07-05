from app.db.models.torrent import TorrentDownload
from app.db.models.creative_project import (
    CreativeProject,
    CreativeProjectStatus,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
)
from app.db.models.asset_hub import (
    AssetNode, AssetVersion, AssetRepresentation,
    AssetEmbedding, AssetRelation,
    AssetType, RelationType,
    Tag, AssetTagLink,
    AIModel,
)
from app.db.models.character import Character, CharacterStoryLink, CharacterSourceType, CharacterRole
from app.db.models.story import Story, StoryCharacterPortrait, StoryStatus, StoryStyle
from app.db.models.live2d import Live2DModel, Live2DBone, Live2DMotion, Live2DModelStatus
from app.db.models.api_key import ApiKey, ApiKeyStatus, ApiKeyCategory
from app.db.models.agent import (
    AgentSession, AgentSessionCreate, AgentSessionRead,
    AgentThread, AgentThreadBase,
    AgentMessage, AgentMessageBase,
    AgentContextSnapshot, AgentContextSnapshotBase,
    AgentMemory, AgentMemoryCreate, AgentMemoryRead,
    AgentSkill, AgentSkillCreate, AgentSkillRead,
    AgentToolCall, AgentToolCallBase,
    AgentRun, AgentRunBase, AgentRunStep, AgentRunStepBase,
    AgentMemorySnapshot, AgentMemorySnapshotBase,
    AgentProfile, AgentProfileCreate, AgentProfileRead,
)

# =============================================================================
# 平台连接器（统一凭证架构 — 唯一凭证存储）
# =============================================================================
from app.db.models.platform_connection import (
    PlatformConnection,
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionResponse,
    PlatformType,
    AuthType,
    ConnectionStatus,
    AcquisitionMethod,
)

# 平台元数据
from app.db.models.platform import (
    SocialMediaPlatform,
    AIProvider,
    StoragePlatform,
    PlatformType as NewPlatformType,
    SOCIAL_MEDIA_METADATA,
    AI_PROVIDER_METADATA,
    STORAGE_METADATA,
)

# AI 连接器
from app.db.models.ai_connector import (
    AIConnector,
    AIConnectorCreate,
    AIConnectorUpdate,
    AIConnectorResponse,
    AIUsageLog,
    AIProviderMetadata,
    AIProviderMetadataCreate,
    AIProviderMetadataUpdate,
    AIProviderMetadataResponse,
)

# ComfyUI 相关模型
from app.db.models.comfyui import (
    WorkflowTemplate,
    WorkflowPreset,
    ComfyUITask,
    ComfyUINode,
    WorkflowCategory,
    TaskStatus,
    TaskPriority,
)

# 系统设置
from app.db.models.system_setting import SystemSetting, SystemSettingCreate, SystemSettingUpdate, DEFAULT_STORAGE_SETTINGS

# 小说章节模型
from app.db.models.novel import NovelChapter

# 书源模型（阅读App兼容）
from app.db.models.book_source import BookSource
from app.db.models.book_source_cookie import BookSourceCookie

# 平台生成模板
from app.db.models.platform_template import PlatformTemplate

# 微信公众号下载
from app.db.models.wechat_mp import (
    WechatMPDownload,
    WechatMPDownloadCreate,
    WechatMPDownloadResponse,
)

# 向量库模型
from app.db.models.vector import VectorDocument, VectorIndex
