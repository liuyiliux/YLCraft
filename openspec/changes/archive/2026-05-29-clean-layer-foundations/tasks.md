## 1. P0: Fix Broken Imports

- [x] 1.1 Search all references to `backend_registry` across the codebase
- [x] 1.2 Fix `services/story/generator.py`: replace `from app.services.backend_registry import BackendManager` with `from app.services.ai import get_ai_service` and update usage to `get_ai_service()`
- [x] 1.3 Fix `api/v1/story.py`: same replacement as 1.2
- [x] 1.4 Verify: run `python -c "import app.services.story.generator"` to confirm no ImportError

## 2. P0: Create services/__init__.py

- [x] 2.1 Create `services/__init__.py` with package docstring `"""YLCraft — 业务服务层"""`
- [x] 2.2 Verify: run `python -c "from app.services import ai"` to confirm services is a valid package ✅

## 3. P1: Relocate Orphan Files

- [x] 3.1 Search all references to `from app.services.image_editor import` across codebase
- [x] 3.2 Search all references to `from app.services.ffmpeg_service import` across codebase
- [x] 3.3 Create `services/image_editor/` package: move `image_editor.py` → `services/image_editor/service.py`, create `__init__.py` with proper exports
- [x] 3.4 Update all import paths for image_editor (import stays same via `__init__.py` re-export)
- [x] 3.5 Move `services/ffmpeg_service.py` → `services/video/ffmpeg.py`
- [x] 3.6 Update all import paths for ffmpeg_service across codebase (3 files: clip_ops.py, subtitles.py, bgm.py)
- [x] 3.7 Delete original orphan files after migration confirmed

## 4. P1: Establish Package Boundaries (__init__.py exports)

- [x] 4.1 Audit all 11 empty/comment-only `__init__.py` files and determine the public API for each
- [x] 4.2 Fix `services/agent/memory/__init__.py`: export MemoryManager
- [x] 4.3 Fix `services/agent/session/__init__.py`: export SessionManager
- [x] 4.4 Fix `services/ai/backends/llm/__init__.py`: export OpenAISDKLLMBackend, GenericLLMBackend
- [x] 4.5 Fix `services/ai/backends/image/__init__.py`: export GeminiImageBackend, OpenAISDKImageBackend, GenericImageBackend
- [x] 4.6 Fix `services/ai/backends/video/__init__.py`: export BaseVideoBackend, MinimaxVideoBackend
- [x] 4.7 Fix `services/ai/routes/__init__.py`: update docstring
- [x] 4.8 Fix `services/download/platforms/__init__.py`: export BilibiliDownloader, DouyinDownloader, TwitterDownloader
- [x] 4.9 Fix `services/auto_tagging/__init__.py`: export AutoTaggingService
- [x] 4.10 Fix `api/__init__.py`: update docstring
- [x] 4.11 Fix `api/v1/__init__.py`: update docstring
- [x] 4.12 Fix `core/__init__.py`: export ProvidersConfig, get_settings, get_ffmpeg_path

## 5. P1: Clean Empty Directories

- [x] 5.1 Delete `services/video_gen/` (empty directory, all content migrated to `services/ai/backends/video/`)
- [x] 5.2 Delete `core/contracts/` (empty directory, all types migrated to `services/ai/types.py`)
- [x] 5.3 Delete `connectors/ai/` (empty directory, no ai connectors implemented yet)

## 6. P1: Connector Layer Documentation

- [x] 6.1 Add docstring to `connectors/__init__.py` explaining the boundary: connectors are low-level API clients; platform business logic goes to `services/platforms/`
- [x] 6.2 Mark `connectors/base/ai_base.py` (already deleted via git) — verified no residual `__pycache__` (cleaned)

## 7. Final Verification

- [x] 7.1 Run `python -c "from app.services import ai"` ✅ no import errors
- [x] 7.2 Search for `from app.services.backend_registry` ✅ zero matches
- [x] 7.3 Search for `from app.services.image_editor import` ✅ paths valid (re-export preserved)
- [x] 7.4 Search for `from app.services.ffmpeg_service import` ✅ zero matches (all migrated to `services/video/`)
- [x] 7.5 Confirm no top-level `.py` files remain in `services/` root ✅ only `__init__.py`
- [x] 7.6 Confirm `services/video_gen/`, `core/contracts/`, `connectors/ai/` are deleted ✅
