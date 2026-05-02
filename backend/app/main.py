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
    try:
        init_manager(str(config_path))
        logger.info("BackendManager initialized")
    except FileNotFoundError:
        # 配置文件不存在，使用空配置初始化
        init_manager(None)
        logger.warning(f"providers.yaml not found at {config_path}, using defaults")

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
        app.include_router(tasks.router, prefix="/api/v1", tags=["Tasks"])
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

_register_routes()
