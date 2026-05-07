"""
YLCraft — FastAPI 入口

启动方式：
    cd backend
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.services.llm.manager import init_manager
from app.core.task_queue import get_task_queue
from app.db.database import SessionLocal  # 新增：导入数据库 session

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ylcraft")


# =============================================================================
# 生命周期管理
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的生命周期管理"""
    # 启动时初始化 BackendManager
    config_path = Path(__file__).parent.parent / "config" / "providers.yaml"
    
    # 创建数据库 session
    db_session = SessionLocal()
    
    try:
        # 传入 session，优先从数据库加载
        init_manager(str(config_path), session=db_session)
        logger.info("BackendManager initialized (with database session)")
    except Exception as e:
        logger.warning(f"BackendManager initialization failed: {e}, trying YAML only")
        try:
            init_manager(str(config_path), session=None)
            logger.info("BackendManager initialized (YAML only)")
        except FileNotFoundError:
            # 配置文件不存在，使用空配置初始化
            init_manager(None, session=db_session)
            logger.warning(f"providers.yaml not found at {config_path}, using database only")
    
    # 初始化任务队列（自动检测 Redis 可用性）
    from app.core.task_queue import get_queue_mode
    queue = get_task_queue()
    mode = get_queue_mode()
    
    if mode == "redis":
        try:
            redis_client = await queue._get_redis()
            await redis_client.ping()
            logger.info("Task queue: Redis mode (connected)")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, falling back to memory mode")
            from app.core.task_queue import init_task_queue
            init_task_queue(use_redis=False)
            logger.info("Task queue: Memory mode (fallback)")
    else:
        logger.info("Task queue: Memory mode (no Redis configured)")
    
    # 初始化数据库（创建所有表）
    from app.db.database import init_db
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    logger.info("Database initialized")
    
    # 初始化平台连接器（自动注册所有连接器）
    try:
        from app.connectors import init_connectors
        init_connectors()
        logger.info("Connectors initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize connectors: {e}")

    yield

    # 关闭时清理资源
    logger.info("Shutting down YLCraft...")
    try:
        await queue.close()
        logger.info("Task queue closed")
    except Exception:
        pass


# =============================================================================
# FastAPI 实例
# =============================================================================

app = FastAPI(
    title="YLCraft API",
    description="AI 视频创作平台 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（开发环境允许前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 根路由
# =============================================================================

@app.get("/", tags=["root"])
async def root():
    return {
        "name": "YLCraft",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["root"])
async def health():
    """健康检查"""
    return {"status": "ok"}


# =============================================================================
# 注册 API 路由
# =============================================================================

def _register_routes():
    """延迟导入并注册所有路由，避免循环导入"""
    from fastapi import APIRouter

    # Provider 管理路由
    try:
        from app.api.v1 import providers
        app.include_router(providers.router, prefix="/api/v1/providers", tags=["Providers"])
    except Exception as e:
        logger.warning(f"Could not load providers router: {e}")

    # LLM 路由
    try:
        from app.api.v1 import llm
        app.include_router(llm.router, prefix="/api/v1/llm", tags=["LLM"])
    except Exception as e:
        logger.warning(f"Could not load llm router: {e}")

    # 图像生成路由
    try:
        from app.api.v1 import images
        app.include_router(images.router, prefix="/api/v1/images", tags=["Images"])
    except Exception as e:
        logger.warning(f"Could not load images router: {e}")

    # 视频生成路由
    try:
        from app.api.v1 import videos
        app.include_router(videos.router, prefix="/api/v1/videos", tags=["Videos"])
    except Exception as e:
        logger.warning(f"Could not load videos router: {e}")

    try:
        from app.api.v1 import tts
        app.include_router(tts.router, prefix="/api/v1/tts", tags=["TTS"])
    except Exception as e:
        logger.warning(f"Could not load tts router: {e}")

    try:
        from app.api.v1 import breaker
        app.include_router(breaker.router, prefix="/api/v1/breaker", tags=["Breaker"])
    except Exception as e:
        logger.warning(f"Could not load breaker router: {e}")

    # 视频下载解析路由
    try:
        from app.api.v1 import download
        app.include_router(download.router, prefix="/api/v1/download", tags=["Download"])
    except Exception as e:
        logger.warning(f"Could not load download router: {e}")

    try:
        from app.api.v1 import cutclaw
        app.include_router(cutclaw.router, prefix="/api/v1/clip/cutclaw", tags=["Clip — CutClaw"])
    except Exception as e:
        logger.warning(f"Could not load cutclaw router: {e}")

    try:
        from app.api.v1 import clip
        app.include_router(clip.router, prefix="/api/v1/clip", tags=["Clip — NarratoAI / MoE"])
    except Exception as e:
        logger.warning(f"Could not load clip router: {e}")

    try:
        from app.api.v1 import story
        app.include_router(story.router, prefix="/api/v1/story", tags=["Story Maker"])
    except Exception as e:
        logger.warning(f"Could not load story router: {e}")

    # 任务管理路由
    try:
        from app.api.v1 import tasks
        app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
    except Exception as e:
        logger.warning(f"Could not load tasks router: {e}")

    # 系统设置路由
    try:
        from app.api.v1 import settings
        app.include_router(settings.router, prefix="/api/v1/settings", tags=["Settings"])
    except Exception as e:
        logger.warning(f"Could not load settings router: {e}")

    # 素材资产库路由
    try:
        from app.api.v1 import assets
        app.include_router(assets.router, prefix="/api/v1/assets", tags=["Assets"])
    except Exception as e:
        logger.warning(f"Could not load assets router: {e}")

    # 角色管理路由
    try:
        from app.api.v1 import characters
        app.include_router(characters.router, prefix="/api/v1/characters", tags=["Characters"])
    except Exception as e:
        logger.warning(f"Could not load characters router: {e}")

    # Live2D 工厂路由
    try:
        from app.api.v1 import live2d
        app.include_router(live2d.router, prefix="/api/v1/live2d", tags=["Live2D Factory"])
    except Exception as e:
        logger.warning(f"Could not load live2d router: {e}")

    # Live2D 工厂路由
    try:
        from app.api.v1 import live2d
        app.include_router(live2d.router, prefix="/api/v1/live2d", tags=["Live2D Factory"])
    except Exception as e:
        logger.warning(f"Could not load live2d router: {e}")

    # ComfyUI 管理路由
    try:
        from app.api.v1 import comfyui
        app.include_router(comfyui.router, prefix="/api/v1/comfyui", tags=["ComfyUI"])
    except Exception as e:
        logger.warning(f"Could not load comfyui router: {e}")

    # Cookie 管理路由
    try:
        from app.api.v1 import cookies
        app.include_router(cookies.router, prefix="/api/v1/cookies", tags=["Cookies"])
    except Exception as e:
        logger.warning(f"Could not load cookies router: {e}")

    # 视频剪辑操作路由
    try:
        from app.api.v1 import clip_ops
        app.include_router(clip_ops.router, prefix="/api/v1/clip-ops", tags=["Clip Operations"])
    except Exception as e:
        logger.warning(f"Could not load clip_ops router: {e}")

    # WebSocket 实时推送路由
    try:
        from app.api.v1 import ws
        app.include_router(ws.router, prefix="/api/v1/ws", tags=["WebSocket"])
    except Exception as e:
        logger.warning(f"Could not load ws router: {e}")

    # 字幕管理路由
    try:
        from app.api.v1 import subtitles
        app.include_router(subtitles.router, prefix="/api/v1/subtitles", tags=["Subtitles"])
    except Exception as e:
        logger.warning(f"Could not load subtitles router: {e}")

    # BGM 配乐路由
    try:
        from app.api.v1 import bgm
        app.include_router(bgm.router, prefix="/api/v1/bgm", tags=["BGM"])
    except Exception as e:
        logger.warning(f"Could not load bgm router: {e}")

    # Agent 智能助手路由
    try:
        from app.api.v1 import agent
        app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])
    except Exception as e:
        logger.warning(f"Could not load agent router: {e}")

    # 素材采集路由（MediaCrawler 集成）
    try:
        from app.api.v1 import crawler
        app.include_router(crawler.router, prefix="/api/v1/crawler", tags=["Crawler"])
    except Exception as e:
        logger.warning(f"Could not load crawler router: {e}")

    # 平台连接器路由（已拆分，保留旧版兼容）
    try:
        from app.api.v1 import platforms
        app.include_router(platforms.router, prefix="/api/v1/platforms", tags=["Platform Connections (Legacy)"])
    except Exception as e:
        logger.warning(f"Could not load platforms router: {e}")

    # AI 连接器路由（新版）
    try:
        from app.api.v1 import ai_connectors
        app.include_router(ai_connectors.router, prefix="/api/v1/ai", tags=["AI Connectors"])
    except Exception as e:
        logger.warning(f"Could not load ai_connectors router: {e}")

    # 社交媒体连接器路由（新版）
    try:
        from app.api.v1 import social_media
        app.include_router(social_media.router, prefix="/api/v1/social", tags=["Social Media Connectors"])
    except Exception as e:
        logger.warning(f"Could not load social_media router: {e}")

_register_routes()


# =============================================================================
# 静态文件服务（上传目录）
# =============================================================================

from pathlib import Path

# 确保 uploads 目录存在
uploads_dir = Path(__file__).parent.parent / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)

# 挂载 uploads 目录为静态文件目录
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
