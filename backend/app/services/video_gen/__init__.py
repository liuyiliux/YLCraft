"""
YLCraft — 视频生成 Backend 实现层

导出的 Backend 类：
- MinimaxVideoBackend：MiniMax 视频生成 API（图生视频 / 文生视频）
- FFmpegRenderBackend：FFmpeg 视频剪辑/合成/渲染
"""

from app.services.video_gen.minimax import MinimaxVideoBackend

__all__ = ["MinimaxVideoBackend"]
