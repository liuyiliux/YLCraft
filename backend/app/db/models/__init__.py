from app.db.models.asset import Asset, AssetCollection, AssetTag
from app.db.models.character import Character, CharacterStoryLink, CharacterSourceType, CharacterRole
from app.db.models.story import Story, StoryCharacterPortrait, StoryStatus, StoryStyle
from app.db.models.live2d import Live2DModel, Live2DBone, Live2DMotion, Live2DModelStatus
from app.db.models.api_key import ApiKey, ApiKeyStatus, ApiKeyCategory
from app.db.models.agent import (
    AgentSession, AgentSessionCreate, AgentSessionRead,
    AgentMemory, AgentMemoryCreate, AgentMemoryRead,
    AgentSkill, AgentSkillCreate, AgentSkillRead,
    AgentToolCall, AgentToolCallBase,
)
# =============================================================================
# 平台连接器（已拆分）
# =============================================================================
# 旧版（保持兼容，但推荐使用新版）
from app.db.models.platform_connection import (
    PlatformConnection,
    PlatformConnectionCreate,
    PlatformConnectionUpdate,
    PlatformConnectionResponse,
    PlatformType,
    AuthType,
    ConnectionStatus,
)

# 新版（推荐使用）
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
)

# 社交媒体连接器
from app.db.models.social_media_connector import (
    SocialMediaConnector,
    SocialMediaConnectorCreate,
    SocialMediaConnectorUpdate,
    SocialMediaConnectorResponse,
    SocialAuthType,
    SocialConnectionStatus,
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

# 平台 Cookie 配置
from app.db.models.platform_cookie import (
    PlatformCookie,
    PlatformCookieCreate,
    PlatformCookieUpdate,
)

# 系统设置
from app.db.models.system_setting import SystemSetting, SystemSettingCreate, SystemSettingUpdate, DEFAULT_STORAGE_SETTINGS
