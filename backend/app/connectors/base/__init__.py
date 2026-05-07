"""Connectors Module - Base Classes"""
from app.connectors.base.social_base import (
    ContentType,
    MediaFormat,
    MediaAttachment,
    PostContent,
    PostResult,
    AccountInfo,
    ContentMetrics,
    ISocialMediaConnector,
    ISocialMediaConnectorFactory,
)

from app.connectors.base.ai_base import (
    AIModelType,
    TextMessage,
    ChatRequest,
    ChatResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    TTSRequest,
    TTSResponse,
    UsageStats,
    IAIConnector,
    IAIConnectorFactory,
)

__all__ = [
    # Social Media
    "ContentType",
    "MediaFormat",
    "MediaAttachment",
    "PostContent",
    "PostResult",
    "AccountInfo",
    "ContentMetrics",
    "ISocialMediaConnector",
    "ISocialMediaConnectorFactory",
    # AI
    "AIModelType",
    "TextMessage",
    "ChatRequest",
    "ChatResponse",
    "ImageGenerationRequest",
    "ImageGenerationResponse",
    "VideoGenerationRequest",
    "VideoGenerationResponse",
    "TTSRequest",
    "TTSResponse",
    "UsageStats",
    "IAIConnector",
    "IAIConnectorFactory",
]
