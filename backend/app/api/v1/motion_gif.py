"""动图（motion GIF）API。

**API 层只做参数转换、权限与错误映射**，业务语义在
`services/image/motion_gif_service.py`。三段式：

- ``POST /motion-gif/generate``    ① 生成多格图候选（**花钱**，调图像模型）
- ``POST /motion-gif/slice-preview`` ② 切帧预览（免费）
- ``POST /motion-gif/compose``      ③ 合成 GIF/WebP/MP4（免费，不调模型）

②③ 不调用任何模型，所以反复调整不花钱——这是把切帧从生成里拆出来的原因。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.resource_auth import principal_owner_user_id
from app.core.user_auth import AuthenticatedPrincipal, get_authenticated_principal
from app.db.database import get_session
from app.services.image import motion_gif_service, motion_prompt, slicing

logger = logging.getLogger("ylcraft.images.motion_gif")

router = APIRouter()


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class SliceRefModel(BaseModel):
    """一格的来源。``kind`` 决定其余字段怎么读。

    用「来源」而不是数组下标表达顺序：用户删掉第 3 格再补一张自己的图之后，
    用户要核对的是「第 5 格来自原图第几格」，下标会随操作漂移。
    """

    kind: Literal["origin", "upload", "region"] = "origin"
    index: Optional[int] = None
    box: Optional[list[int]] = Field(default=None, description="自由裁切区域 (left, top, right, bottom)")
    #: 这一格的**像素级微调**（亮度/对比度/饱和度/色相/旋转），不调模型、不花钱。
    #: 用来抹掉"某格偏亮/偏色"导致的动图闪烁。越界值后端会夹回合法范围。
    adjust: Optional[dict[str, float]] = None


class GridEdgesModel(BaseModel):
    """用户拖过的分割线（**归一化** 0..1）。

    为什么归一化不用像素：换一张分辨率不同的多格图时同样的拖法能直接复用。
    长度应是 ``cols+1`` / ``rows+1``；少给、越界、非递增都由后端修正。
    """

    xs: Optional[list[float]] = None
    ys: Optional[list[float]] = None


class MotionGifGenerateRequest(BaseModel):
    """① 生成多格图候选。"""

    prompt: str
    motion_kind: Literal["orbit", "character", "speed", "expression"] = "orbit"
    grid_layout: Literal["4x4", "2x4", "1x4"] = "2x4"
    prompt_lang: Literal["zh", "en"] = "en"
    subject: str = ""
    #: 被用户关掉的系统提示词块 id。
    disabled_block_ids: list[str] = Field(default_factory=list)
    #: 提示词已由 AI 优化 —— 此时**不再追加**系统块（避免与优化结果重复/冲突）。
    optimized: bool = False
    #: 候选张数。与页面「批量数量」联动。
    count: int = Field(default=1, ge=1, le=4)
    provider: Optional[str] = None
    model: Optional[str] = None
    size: Optional[str] = "2048x2048"
    reference_asset_ids: Optional[list[str]] = None
    reference_images: Optional[list[str]] = None
    negative_prompt: Optional[str] = None
    project_id: Optional[str] = None
    content_id: Optional[str] = None


class MotionGifSlicePreviewRequest(BaseModel):
    """② 切帧预览（只切不合成，不花钱）。"""

    sheet_path: str = Field(description="多格图本地路径（相对项目根或绝对）")
    rows: int = Field(ge=1, le=8)
    cols: int = Field(ge=1, le=8)
    order: Optional[list[SliceRefModel]] = None
    #: 把每帧主体平移居中。必须与合成用同一个开关，否则**预览 ≠ 成品**。
    align_subject: bool = True
    #: 裁掉每格主体之外的留白。默认关（裁了会把主体切坏）。
    trim: bool = False
    #: 用户拖过的分割线。None = 均匀切分。
    grid_edges: Optional[GridEdgesModel] = None


class MotionGifComposeRequest(BaseModel):
    """③ 合成（不调模型，不花钱）。"""

    sheet_path: str = Field(description="多格图本地路径")
    rows: int = Field(ge=1, le=8)
    cols: int = Field(ge=1, le=8)
    order: list[SliceRefModel] = Field(min_length=1)
    loop: Literal["pingpong", "cycle", "none"] = "pingpong"
    size: int = Field(default=480, ge=64, le=2048)
    frame_ms: int = Field(default=70, ge=20, le=2000)
    timing: Literal["ramp", "even", "none"] = "ramp"
    max_kb: int = Field(default=3000, ge=0, le=20000)
    colors: int = Field(default=255, ge=8, le=256)
    resample: Literal["lanczos", "nearest"] = "lanczos"
    dither: bool = True
    transparent: bool = False
    write_webp: bool = True
    write_mp4: bool = False
    fps: int = Field(default=25, ge=1, le=60)
    #: 把每帧主体**平移居中**。关掉则保留各帧原始位置（背景不补边，
    #: 但主体可能上下跳动）。默认开 ——「主体不动」比「背景轻微变形」更符合预期。
    align_subject: bool = True
    #: 裁掉每格主体之外的留白。默认关（裁了会把主体切坏）。
    trim: bool = False
    #: 用户拖过的分割线。None = 均匀切分。
    grid_edges: Optional[GridEdgesModel] = None
    #: 是否存出每帧小图（供前端切帧面板显示真实像素）。本地文件操作，不花钱。
    save_frames: bool = True


class MotionGifOptionsResponse(BaseModel):
    """可选项与默认值，供前端渲染控件。"""

    success: bool = True
    motion_kinds: list[dict[str, Any]] = Field(default_factory=list)
    grid_layouts: list[dict[str, Any]] = Field(default_factory=list)
    loop_modes: list[dict[str, Any]] = Field(default_factory=list)
    prompt_limit_chars: int = motion_prompt.PROMPT_CHAR_LIMIT


class MotionPromptPreviewRequest(BaseModel):
    """预览真正会发送的完整提示词（不调模型、不花钱）。"""

    prompt: str = ""
    motion_kind: Literal["orbit", "character", "speed", "expression"] = "orbit"
    grid_layout: Literal["4x4", "2x4", "1x4"] = "2x4"
    prompt_lang: Literal["zh", "en"] = "en"
    subject: str = ""
    disabled_block_ids: list[str] = Field(default_factory=list)
    #: 用户**改过**的提示词块：`{块id: 新文本}`。
    #: 空串 = 关掉这一段；没出现的 id = 用默认文本。
    block_overrides: dict[str, str] = Field(default_factory=dict)
    optimized: bool = False


class MotionPromptPreviewResponse(BaseModel):
    success: bool = True
    #: 拼装后的完整提示词（与生成走同一函数，保证「看到什么就发什么」）。
    prompt: str = ""
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    #: 被用户关掉的块 id。
    system_added: list[str] = Field(default_factory=list)
    total_chars: int = 0
    exceeds_limit: bool = False
    #: 每段的**默认文本**，供前端「恢复默认」用（改过之后仍要能还原）。
    default_texts: dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None


class MotionGifComposeResponse(BaseModel):
    success: bool = True
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class MotionGifSaveRequest(BaseModel):
    """把合成好的动图存入素材库。"""

    sheet_path: str
    rows: int = Field(ge=1, le=8)
    cols: int = Field(ge=1, le=8)
    order: list[SliceRefModel] = Field(min_length=1)
    loop: Literal["pingpong", "cycle", "none"] = "pingpong"
    size: int = Field(default=480, ge=64, le=2048)
    frame_ms: int = Field(default=70, ge=20, le=2000)
    timing: Literal["ramp", "even", "none"] = "ramp"
    max_kb: int = Field(default=3000, ge=0, le=20000)
    colors: int = Field(default=255, ge=8, le=256)
    resample: Literal["lanczos", "nearest"] = "lanczos"
    dither: bool = True
    transparent: bool = False
    write_webp: bool = True
    write_mp4: bool = False
    fps: int = Field(default=25, ge=1, le=60)
    align_subject: bool = True
    trim: bool = False
    grid_edges: Optional[GridEdgesModel] = None
    #: 是否存出每帧小图（供前端切帧面板显示真实像素）。本地文件操作，不花钱。
    #: ⚠️ 与 `MotionGifComposeRequest` 保持一致 —— 少了它，
    #: `save` 端点会因 `req.save_frames` 取不到而 AttributeError（500）。
    save_frames: bool = True

    name: str = ""
    prompt: str = ""
    provider: str = ""
    model: str = ""
    motion_kind: str = ""
    #: 已存在的动图节点 —— 传了则**追加新版本**（改了切帧重新合成），不建新节点。
    node_id: str = ""
    project_id: str = ""
    content_id: str = ""


class MotionGifSaveResponse(BaseModel):
    success: bool = True
    node_id: str = ""
    version_id: str = ""
    version_number: int = 0
    slice_config: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _service() -> motion_gif_service.MotionGifService:
    return motion_gif_service.MotionGifService()


def _to_slice_refs(
    models: list[SliceRefModel],
) -> list[slicing.SliceRef]:
    out: list[slicing.SliceRef] = []
    for item in models:
        source: dict[str, Any] = {"kind": item.kind}
        if item.kind == "region":
            box = tuple(item.box or ())
            if len(box) != 4:
                raise ValueError("自选区域必须提供 (left, top, right, bottom)")
            source["box"] = [int(v) for v in box]
        else:
            if item.index is None:
                raise ValueError(f"{item.kind} 来源必须提供 index")
            source["index"] = int(item.index)
        if item.adjust:
            source["adjust"] = {
                k: float(v) for k, v in item.adjust.items() if v is not None
            }
        out.append(slicing.SliceRef(source))
    return out


def _to_sheet_grid(
    rows: int,
    cols: int,
    edges: GridEdgesModel | None,
) -> slicing.SheetGrid | None:
    """把请求里的分割线变成网格；没拖过（None 或与均匀一致）返回 None。"""
    if edges is None:
        return None
    if edges.xs is None and edges.ys is None:
        return None
    grid = slicing.SheetGrid.from_edges(rows, cols, edges.xs, edges.ys)
    return None if grid.is_uniform() else grid


def _resolve_sheet_path(raw: str) -> Path:
    """把请求里的路径还原成本机绝对路径。

    数据库里存的是**相对项目根**的路径（多机器共享同一数据库、文件各自本地），
    所以必须经解析器还原，不能直接 `Path(raw)`。解析器同时做允许目录校验，
    避免任意路径读文件。
    """
    from app.services.asset_file_resolver import resolve_asset_file

    resolved = resolve_asset_file(raw)
    if resolved is None:
        raise FileNotFoundError(f"多格图不存在或不在允许的目录内：{raw}")
    return resolved


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get(
    "/motion-gif/options",
    response_model=MotionGifOptionsResponse,
    summary="动图可选项（动效类型 / 格子排布 / 循环方式）",
)
async def get_motion_gif_options():
    """返回四类动效、三种排布与循环方式，含推荐默认值与实测稳定性标注。"""
    return MotionGifOptionsResponse(
        motion_kinds=[
            {
                "key": spec.key,
                "label": spec.label,
                "motion": spec.motion,
                "usage": spec.usage,
                "prefer_reference": spec.prefer_reference,
                "stability": spec.stability,
                "default_loop": spec.default_loop,
            }
            for spec in motion_prompt.MOTION_KINDS
        ],
        grid_layouts=[
            {
                "key": spec.key,
                "label": spec.label,
                "rows": spec.rows,
                "cols": spec.cols,
                "cells": spec.cells,
                "note": spec.note,
                "recommended": spec.recommended,
            }
            for spec in motion_prompt.GRID_LAYOUTS
        ],
        loop_modes=[
            {"key": "pingpong", "label": "来回播放", "note": "正放完再倒放，环绕类接缝最自然"},
            {"key": "cycle", "label": "首尾相接", "note": "需要最后一格回到第一格，表情/动作类适用"},
            {"key": "none", "label": "正放一次", "note": "不循环"},
        ],
    )


@router.post(
    "/motion-gif/prompt-preview",
    response_model=MotionPromptPreviewResponse,
    summary="预览真正会发送的完整动图提示词",
)
async def preview_motion_prompt(req: MotionPromptPreviewRequest):
    """与生成共用 `compose_prompt`，保证预览与实际发送一致。

    分块返回并标出系统追加的段，用户可逐段改/关；`optimized=True` 时
    **不追加**任何系统块——AI 优化结果已按该动效写法写全，再追加会重复甚至冲突。
    """
    svc = _service()
    try:
        # 默认块（未套用户改动）—— 既用于展示，也作为「恢复默认」的还原来源。
        default_blocks = svc.build_blocks(
            kind=req.motion_kind,
            layout=req.grid_layout,
            lang=req.prompt_lang,
            subject=req.subject,
        )
        # 套上用户改动后再拼：**与生成走同一个入口**（`blocks_to_prompt`），
        # 否则会出现"预览改了、生成没改"的漂移 —— 这正是上次动图规则
        # 根本没发出去的那类 bug。
        full = svc.compose_prompt(
            user_prompt=req.prompt,
            kind=req.motion_kind,
            layout=req.grid_layout,
            lang=req.prompt_lang,
            subject=req.subject,
            disabled_ids=req.disabled_block_ids,
            overrides=req.block_overrides,
            optimized=req.optimized,
        )
        applied = motion_prompt.apply_block_overrides(default_blocks, req.block_overrides)
    except ValueError as exc:
        # 参数写错属于 400，不该被当成"生成失败"
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    skipped = set(req.disabled_block_ids)
    # 空串的 override 等价于关掉，也要算进"已关"。
    skipped |= {k for k, v in (req.block_overrides or {}).items() if not str(v).strip()}
    added = [b.id for b in default_blocks if b.id not in skipped] if not req.optimized else []
    return MotionPromptPreviewResponse(
        prompt=full,
        blocks=[
            {
                "id": b.id,
                "title": b.title,
                "why": b.why,
                "text": b.text,
                "enabled": b.id not in skipped,
                # 这一段是否被用户改过（前端据此显示「已改」）
                "edited": bool((req.block_overrides or {}).get(b.id))
                and str((req.block_overrides or {}).get(b.id)).strip()
                != next((d.text for d in default_blocks if d.id == b.id), b.text),
            }
            for b in applied
        ],
        default_texts={b.id: b.text for b in default_blocks},
        system_added=added,
        total_chars=len(full),
        exceeds_limit=motion_prompt.exceeds_limit(full),
    )


@router.post(
    "/motion-gif/slice-preview",
    summary="切帧预览（只切不合成，不花钱）",
)
async def preview_slice(
    req: MotionGifSlicePreviewRequest,
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
):
    """把已有多格图按 rows×cols 切开并统一裁切，返回**每格来源、尺寸与小图 URL**。

    这是**纯本地像素处理**，不调用模型、不产生费用。供前端渲染切帧面板。

    小图 URL 是关键：只回尺寸和来源标签时，面板上就是 8 个黑框，用户没法判断
    切得对不对、主体有没有对齐，只能盲合成一次再看成品。
    """
    svc = _service()
    try:
        sheet_path = _resolve_sheet_path(req.sheet_path)
        refs = _to_slice_refs(req.order) if req.order else None
        owner = principal_owner_user_id(principal)
        output_dir = (
            svc.work_dir
            / (owner or "anonymous")
            / f"sheet-{hashlib.sha1(str(sheet_path).encode('utf-8')).hexdigest()[:10]}"
        )
        result = svc.slice_preview(
            sheet_path=sheet_path,
            rows=req.rows,
            cols=req.cols,
            order=refs,
            output_dir=output_dir,
            align_subject=req.align_subject,
            trim=req.trim,
            grid=_to_sheet_grid(req.rows, req.cols, req.grid_edges),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **result}


@router.post(
    "/motion-gif/compose",
    response_model=MotionGifComposeResponse,
    summary="合成动图 GIF / WebP / MP4（不调模型，不花钱）",
)
async def compose_motion_gif(
    req: MotionGifComposeRequest,
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    session: Session = Depends(get_session),
):
    """把已有多格图合成为动图。

    **不调用任何图像模型**，所以反复调切法/顺序都不花钱。用户合成满意后
    再决定是否「存入素材库」。

    Args:
        req: 合成参数（切法、循环、尺寸、帧率等）。
        principal: 认证主体。
        session: 数据库会话（当前仅用于身份与后续入库，本步骤不落库）。

    Returns:
        产物路径与摘要；``success=False`` 时 ``error`` 说明原因。
    """
    del session  # 合成是纯本地处理，不落库；保留依赖以便后续入库复用同一签名
    svc = _service()
    try:
        sheet_path = _resolve_sheet_path(req.sheet_path)
        refs = _to_slice_refs(req.order)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    owner = principal_owner_user_id(principal)
    output_dir = svc.work_dir / (owner or "anonymous") / f"sheet-{abs(hash(req.sheet_path)) & 0xFFFFFFFF:08x}"

    try:
        result = await svc.compose(
            sheet_path=sheet_path,
            rows=req.rows,
            cols=req.cols,
            order=refs,
            uploads=None,
            output_dir=output_dir,
            loop=req.loop,
            size=req.size,
            frame_ms=req.frame_ms,
            timing=req.timing,
            max_kb=req.max_kb,
            colors=req.colors,
            resample=req.resample,
            dither=req.dither,
            transparent=req.transparent,
            write_webp=req.write_webp,
            write_mp4=req.write_mp4,
            fps=req.fps,
            align_subject=req.align_subject,
            trim=req.trim,
            save_frames=req.save_frames,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # 切帧参数写错（空 order、格号越界、单格过小）属于请求问题，回 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 合成失败要能整单返回而不是 500 掉栈
        logger.exception("[motion-gif] compose failed")
        return MotionGifComposeResponse(success=False, error=f"合成失败：{exc}")

    payload = result.to_payload()
    payload["output_dir"] = str(output_dir)
    return MotionGifComposeResponse(success=True, output=payload)


# ---------------------------------------------------------------------------
# 上传补位 + 存库
# ---------------------------------------------------------------------------

#: 上传补位图的存放目录（相对 backend/storage）。
UPLOAD_SUBDIR = "motion_gifs/_uploads"

#: 单张上传图的大小上限。切帧只用它当一格，太大的图没有意义。
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_ALLOWED_UPLOAD_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@router.post(
    "/motion-gif/upload-frame",
    summary="上传一张图片作为切帧补位（不调模型，不花钱）",
)
async def upload_motion_frame(
    file: UploadFile = File(...),
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
):
    """上传补位图，返回它的**上传序号**（前端把序号写进 order 的 SliceRef）。

    为什么需要它：多格图是**一次性画出来的**，单独重画一格必然对不上（光照/角度/
    笔触都会变）。让用户自己传图，一致性由用户自己保证 —— 这是唯一可靠的办法。

    产物存 ``backend/storage/motion_gifs/_uploads/<owner>/<序号>_<随机>.<ext>``，
    按 owner 分目录，避免多机共享数据库时互相覆盖。
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式：{suffix or '(无后缀)'}；只接受 {', '.join(sorted(_ALLOWED_UPLOAD_SUFFIXES))}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传的文件是空的")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"图片过大（{len(data) / 1024 / 1024:.1f}MB），上限 {MAX_UPLOAD_BYTES // 1024 // 1024}MB",
        )

    from app.services.asset_file_resolver import to_asset_download_url, to_storage_path

    owner = principal_owner_user_id(principal) or "anonymous"
    upload_dir = Path(__file__).resolve().parents[2] / "storage" / UPLOAD_SUBDIR / owner
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 序号取当前目录里已有的最大编号 +1，前端据此构造 SliceRef.index
    existing = [
        int(p.name.split("_", 1)[0])
        for p in upload_dir.glob("*.png")
        if p.name.split("_", 1)[0].isdigit()
    ]
    index = (max(existing) + 1) if existing else 1

    stored_name = f"{index}_{uuid.uuid4().hex[:8]}{suffix}"
    target = upload_dir / stored_name
    target.write_bytes(data)
    logger.info("[motion-gif] frame uploaded: owner=%s index=%s size=%d", owner, index, len(data))

    return {
        "success": True,
        "index": index,
        "filename": stored_name,
        "file_path": to_storage_path(target),
        "url": to_asset_download_url(target),
        "file_size": len(data),
    }


@router.post(
    "/motion-gif/save",
    summary="把合成好的动图存入素材库（一个节点 + 多版本）",
)
async def save_motion_gif(
    req: MotionGifSaveRequest,
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
    session: Session = Depends(get_session),
):
    """把 GIF/WebP/MP4/多格图写进 Asset Hub。

    - **一个动图 = 一个 AssetNode**，列表里只占一行；详情里展开版本与格式。
    - 多格图作为同一版本下的一个 representation（``format="framesheet"``），
      不是独立节点 —— 它既是「改切帧重出」的依据，也应能被其它功能按 format 取用。
    - **切帧配置必须一起存**：没有它就无法复现上次的切法，"改切帧出新版本"无从谈起。
    - 传 ``node_id`` 则追加新版本（用户改了切帧重新合成）；不传则新建节点。
    """
    svc = _service()
    try:
        sheet_path = _resolve_sheet_path(req.sheet_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    grid = _to_sheet_grid(req.rows, req.cols, req.grid_edges)

    try:
        refs = _to_slice_refs(req.order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 合成产物目录由 sheet 唯一确定：同一张多格图重合成就覆盖同一处
    stamp = hashlib.sha1(str(sheet_path).encode("utf-8")).hexdigest()[:10]
    owner = principal_owner_user_id(principal)
    output_dir = svc.work_dir / (owner or "anonymous") / f"sheet-{stamp}"

    try:
        result = await svc.compose(
            sheet_path=sheet_path,
            rows=req.rows,
            cols=req.cols,
            order=refs,
            uploads=await _load_uploads(session, req.order, output_dir),
            output_dir=output_dir,
            loop=req.loop,
            size=req.size,
            frame_ms=req.frame_ms,
            timing=req.timing,
            max_kb=req.max_kb,
            colors=req.colors,
            resample=req.resample,
            dither=req.dither,
            transparent=req.transparent,
            write_webp=req.write_webp,
            write_mp4=req.write_mp4,
            fps=req.fps,
            align_subject=req.align_subject,
            trim=req.trim,
            save_frames=req.save_frames,
            grid=grid,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[motion-gif] save compose failed")
        return MotionGifSaveResponse(success=False, error=f"合成失败：{exc}")

    representations = svc.representations(result)
    if not representations or not result.gif_path:
        return MotionGifSaveResponse(success=False, error="合成产物为空，无法入库")

    slice_config = {
        "rows": req.rows,
        "cols": req.cols,
        "cells": len(refs),
        "order": [r.source for r in refs],
        "order_labels": slicing.describe_order(refs),
        "upload_indexes": [r.source.get("index") for r in refs if r.kind == "upload"],
        # 分割线也要存：只存行列的话，用户拖过的九宫格下次打开就丢了
        "grid_edges": (
            {"xs": list(grid.xs), "ys": list(grid.ys)} if grid is not None else None
        ),
        "loop": req.loop,
        "size": req.size,
        "frame_ms": req.frame_ms,
        "timing": req.timing,
        "max_kb": req.max_kb,
        "colors": req.colors,
        "transparent": req.transparent,
        "output_size": list(result.output_size),
        "frames": result.frames,
    }

    try:
        from app.db.database import get_async_session
        from app.services.asset_hub import AssetHubFacade

        async with get_async_session() as db_session:
            created = await AssetHubFacade(db_session).create_motion_gif(
                name=req.name or (req.prompt[:40] or "动图"),
                primary_file_path=str(result.gif_path),
                representations=representations,
                prompt=req.prompt,
                provider=req.provider,
                model=req.model,
                slice_config=slice_config,
                source_node_id=req.node_id,
                lineage={
                    "sheet_path": req.sheet_path,
                    "project_id": req.project_id,
                    "content_id": req.content_id,
                    "motion_kind": req.motion_kind,
                    "grid_layout": f"{req.rows}x{req.cols}",
                },
                owner_user_id=owner,
            )
    except Exception as exc:  # noqa: BLE001 - 合成已成功，入库失败要能说清而不是 500
        logger.exception("[motion-gif] asset hub save failed")
        return MotionGifSaveResponse(
            success=False,
            error=f"合成已成功，但入库失败：{exc}",
            output=result.to_payload(),
        )

    payload = result.to_payload()
    payload["output_dir"] = str(output_dir)
    return MotionGifSaveResponse(
        success=True,
        node_id=created.node_id,
        version_id=created.version_id,
        version_number=created.version_number,
        slice_config=slice_config,
        output=payload,
    )


async def _load_uploads(
    session: Session,
    order: list[SliceRefModel],
    output_dir: Path,
) -> dict[int, Image.Image] | None:
    """按 order 里的 upload index 把上传图读成像素。

    只读**真正被引用**的那些：order 里没有的上传图不参与合成（用户可能先传了
    又删掉），也避免把别人的上传目录整个读进来。
    """
    indexes = {
        int(m.index)
        for m in order
        if m.kind == "upload" and m.index is not None
    }
    if not indexes:
        return None

    from app.services.asset_file_resolver import resolve_asset_file

    uploads: dict[int, Image.Image] = {}
    upload_root = Path(__file__).resolve().parents[2] / "storage" / UPLOAD_SUBDIR
    for index in sorted(indexes):
        candidates = sorted(upload_root.glob(f"*/{index}_*"))
        if not candidates:
            raise ValueError(f"上传图 #{index} 找不到，可能已被清理")
        resolved = resolve_asset_file(str(candidates[0]))
        if resolved is None:
            raise ValueError(f"上传图 #{index} 不在允许的目录内")
        uploads[index] = Image.open(resolved).convert("RGB")
    return uploads
