"""Connectors Module - Base Classes (Social Media only)"""
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
]
