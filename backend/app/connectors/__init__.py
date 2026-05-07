"""Connectors Module - Connector Implementations and Factories"""

from app.connectors.factory import (
    SocialConnectorFactory,
    AIConnectorFactory,
    SocialConnectorInfo,
    AIConnectorInfo,
    register_social_connector,
    register_ai_connector,
)

from app.connectors.registry import (
    ConnectorRegistry,
    get_social_connector,
    get_ai_connector,
    init_connectors,
)

__all__ = [
    # Factory
    "SocialConnectorFactory",
    "AIConnectorFactory",
    "SocialConnectorInfo",
    "AIConnectorInfo",
    "register_social_connector",
    "register_ai_connector",
    # Registry
    "ConnectorRegistry",
    "get_social_connector",
    "get_ai_connector",
    "init_connectors",
]
