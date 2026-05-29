"""
YLCraft — AI 服务统一入口

本模块是 AI 相关功能的统一领域层，组织原则：
- backends/     → AI Backend 实现（LLM / Image / Video），每个类型一个子目录
- routes/       → FastAPI 路由
- service.py    → 服务编排层（AIService）
- connector_service.py → AI Connector CRUD 管理
- types.py      → AI 领域数据类型
- utils.py      → 工具函数
"""

from app.services.ai.service import AIService, get_ai_service

__all__ = ["AIService", "get_ai_service"]
