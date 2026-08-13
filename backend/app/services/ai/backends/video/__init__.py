"""YLCraft — Video Backend 实现"""
from app.services.ai.backends.video.base import BaseVideoBackend
from app.services.ai.backends.video.generic import GenericVideoBackend
from app.services.ai.backends.video.minimax import MinimaxVideoBackend

__all__ = ["BaseVideoBackend", "GenericVideoBackend", "MinimaxVideoBackend"]
