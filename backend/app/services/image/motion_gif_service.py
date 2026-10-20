"""动图（motion GIF）编排服务：把三段式流程串起来。

API 层保持薄（见架构文档「API 层不要承载复杂业务」），这里收口业务语义：

- **候选（花钱）**：生成多格图，每张都是一张 AssetNode 资产
- **切帧（免费）**：只对已有多格图重排/重切，**不调用模型**
- **合成（免费）**：合成 GIF/WebP/MP4

一个动图 = **一个 AssetNode**（列表里只占一行），多版本记切帧配置，
多格图作为附属 representation 供「改切帧」重出。
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

from app.services.asset_file_resolver import to_asset_download_url, to_storage_path
from app.services.image import motion_gif, motion_prompt, slicing

logger = logging.getLogger("ylcraft.motion_gif.service")

#: 动图产物目录名（挂在 backend/storage 下，与 images/ 等同级）。
MOTION_GIF_DIR = "motion_gifs"

#: 单个动图产物目录里保留的源图文件名，便于人工辨认与「改切帧」重出。
FRAMESHEET_NAME = "framesheet.png"

#: ``app/services/image/motion_gif_service.py`` → backend/。
_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _preview_fingerprint(
    frames: Sequence[Image.Image],
    refs: Sequence[slicing.SliceRef],
) -> str:
    """给切帧预览小图算一个**内容指纹**（用于 URL 缓存失效）。

    为什么不用时间戳：相同切法应当得到相同 URL，否则每次刷新都让缓存失效，
    同一张图来回切会堆一堆无用请求。

    为什么不用文件 mtime/size：预览目录是**原地覆写**的，
    size 有机会相同（同尺寸不同取景），mtime 会让相同切法也变。

    ⚠️ **指纹必须覆盖"会改变像素的一切"**，否则改了就看不到变化。
    踩过的坑（用户实测："调帧以后预览怎么生效"）：

    第一版只取"每帧尺寸 + 来源标识"，**漏了 `adjust`（亮度/对比度/色相…）**。
    而调色**不改变尺寸** —— 于是调完亮度，指纹一个字没变、URL 完全相同，
    浏览器继续用旧图：**用户看不到任何变化**（后端其实已经重新切好了）。

    现在把 `adjust` 也编进指纹。任何影响像素的输入都要在这里体现。
    """
    parts: list[str] = []
    for f, r in zip(frames, refs):
        adjust = r.source.get("adjust") or {}
        # 排序后拼接：字典顺序不该影响指纹
        adj = ",".join(f"{k}={adjust[k]}" for k in sorted(adjust)) if adjust else ""
        origin = r.source.get("index") or r.source.get("box") or ""
        parts.append(f"{f.width}x{f.height}:{r.kind}:{origin}:{adj}")
    if not parts:
        return ""
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


@dataclass
class MotionGifCandidate:
    """一张候选多格图。

    候选**全部保留**：同一提示词出多张质量差异很大，用户常要挑；
    没选中的之后还能换回来重切，不该被丢掉。
    """

    node_id: str
    version_id: str
    index: int
    rows: int
    cols: int
    cell_size: tuple[int, int]
    file_path: Path

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "version_id": self.version_id,
            "index": self.index,
            "rows": self.rows,
            "cols": self.cols,
            "cells": self.rows * self.cols,
            "cell_size": list(self.cell_size),
            "url": to_asset_download_url(self.file_path),
            "thumbnail_url": to_asset_download_url(self.file_path),
        }


class MotionGifService:
    """动图三段式流程的业务编排。

    刻意**不持有数据库会话**：会话由 API 层传入或按需创建，避免长任务期间
    连接被占住（合成在本地 CPU 上跑，耗时可能到分钟级）。
    """

    def __init__(self, work_dir: Path | None = None) -> None:
        self._work_dir = work_dir or (_BACKEND_DIR / "storage" / MOTION_GIF_DIR)

    @property
    def work_dir(self) -> Path:
        return self._work_dir

    # -- 提示词 ------------------------------------------------------------

    def build_blocks(
        self,
        *,
        kind: str,
        layout: str,
        lang: str,
        subject: str = "",
    ) -> list[motion_prompt.PromptBlock]:
        """系统追加提示词块（分块返回，供前端展示/编辑/关闭）。"""
        if lang == "en":
            return motion_prompt.build_prompt_blocks_en(
                kind=kind,  # type: ignore[arg-type]
                layout=layout,  # type: ignore[arg-type]
                subject=subject,
            )
        return motion_prompt.build_prompt_blocks(
            kind=kind,  # type: ignore[arg-type]
            layout=layout,  # type: ignore[arg-type]
            lang="zh",  # type: ignore[arg-type]
            subject=subject,
        )

    def compose_prompt(
        self,
        *,
        user_prompt: str,
        kind: str,
        layout: str,
        lang: str,
        subject: str = "",
        disabled_ids: Sequence[str] = (),
        overrides: dict[str, str] | None = None,
        optimized: bool = False,
    ) -> str:
        """拼出真正会发送的提示词。**预览与生成必须共用它。**

        `overrides` 是用户改过的块文本（`{id: 新文本}`，空串 = 关掉）。
        直接走 `blocks_to_prompt`，把"套用改动 + 拼接"收在一次调用里 ——
        分开写容易漏掉其中一步，那就会出现"预览改了、生成没改"的漂移。
        """
        blocks = self.build_blocks(kind=kind, layout=layout, lang=lang, subject=subject)
        return motion_prompt.blocks_to_prompt(
            user_prompt=user_prompt,
            blocks=blocks,
            disabled_ids=disabled_ids,
            overrides=overrides,
            optimized=optimized,
        )

    # -- 合成 --------------------------------------------------------------

    async def compose(
        self,
        *,
        sheet_path: Path,
        rows: int,
        cols: int,
        order: Sequence[slicing.SliceRef],
        uploads: dict[int, Image.Image] | None,
        output_dir: Path,
        loop: str = "pingpong",
        size: int = 480,
        frame_ms: int = 70,
        timing: str = "ramp",
        max_kb: int = 3000,
        colors: int = 255,
        resample: str = "lanczos",
        dither: bool = True,
        transparent: bool = False,
        write_webp: bool = True,
        write_mp4: bool = False,
        fps: int = 25,
        align_subject: bool = True,
        trim: bool = False,
        save_frames: bool = False,
        grid: slicing.SheetGrid | None = None,
    ) -> motion_gif.MotionGifResult:
        """把已有多格图合成为动图（**不调用模型**）。

        Raises:
            ValueError: order 为空或引用了不存在的格号（属于请求写错，应回 400）。
            FileNotFoundError: 源多格图不存在。
        """
        if not order:
            raise ValueError("切帧顺序为空：至少要有一帧")
        if not sheet_path.exists():
            raise FileNotFoundError(f"多格图不存在：{sheet_path}")

        sheet = Image.open(sheet_path).convert("RGB")
        options = motion_gif.MotionGifOptions(
            rows=rows,
            cols=cols,
            order=tuple(order),
            loop=loop,  # type: ignore[arg-type]
            size=size,
            frame_ms=frame_ms,
            timing=timing,  # type: ignore[arg-type]
            max_kb=max_kb,
            colors=colors,
            resample=resample,  # type: ignore[arg-type]
            dither=dither,
            transparent=transparent,
            fps=fps,
            align_subject=align_subject,
            trim=trim,
            grid=grid,
        )
        result = await motion_gif.compose_motion_gif(
            sheet=sheet,
            uploads=uploads,
            options=options,
            output_dir=output_dir,
            write_webp=write_webp,
            write_mp4=write_mp4,
        )
        if save_frames:
            result.frame_paths = self._save_preview_frames(
                sheet_path=sheet_path,
                rows=rows,
                cols=cols,
                order=order,
                uploads=uploads,
                output_dir=output_dir,
                align_subject=align_subject,
                trim=trim,
                grid=grid,
            )
        return result

    def _save_preview_frames(
        self,
        *,
        sheet_path: Path,
        rows: int,
        cols: int,
        order: Sequence[slicing.SliceRef],
        uploads: dict[int, Image.Image] | None,
        output_dir: Path,
        align_subject: bool,
        trim: bool = False,
        grid: slicing.SheetGrid | None = None,
    ) -> list[str]:
        """把切好的每帧存成小图，供前端在切帧面板里**看到真实像素**。

        为什么必须有：只回尺寸与来源标签时，用户点开切帧面板看到 8 个黑框，
        根本判断不出切得对不对、主体有没有对齐 —— 只能盲合成一次再看成品。
        存成 PNG 是本地文件操作，不花钱。
        """
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        sheet = Image.open(sheet_path).convert("RGB")
        frames = slicing.resolve_frames(sheet, rows, cols, order, uploads, grid=grid)
        frames = slicing.apply_global_crop(frames, enabled=trim)
        if align_subject:
            frames = slicing.align_frames_by_content(frames)

        paths: list[str] = []
        # 缩到长边 240：面板格子本来就小，存大图只是浪费磁盘和带宽
        long_edge = min(240, max(frames[0].size))
        for index, frame in enumerate(frames, 1):
            target = frames_dir / f"frame_{index:02d}.png"
            frame.resize(
                (
                    max(1, round(frame.width * long_edge / max(frame.size))),
                    max(1, round(frame.height * long_edge / max(frame.size))),
                ),
                Image.LANCZOS,
            ).save(target, format="PNG")
            paths.append(to_asset_download_url(target))
        return paths

    # -- 切帧预览 ----------------------------------------------------------

    def slice_preview(
        self,
        *,
        sheet_path: Path,
        rows: int,
        cols: int,
        order: Sequence[slicing.SliceRef] | None = None,
        uploads: dict[int, Image.Image] | None = None,
        output_dir: Path | None = None,
        align_subject: bool = True,
        trim: bool = False,
        grid: slicing.SheetGrid | None = None,
    ) -> dict[str, Any]:
        """只切不合成，供前端渲染切帧面板。

        返回每格的**来源标签、尺寸与小图 URL**。小图是关键：只回尺寸和标签时，
        面板上就是 8 个黑框，用户没法判断切得对不对、主体有没有对齐，
        只能盲合成一次再看成品。

        ``output_dir`` 给定时才存小图（本地文件操作，不花钱）。

        ``uploads`` 可选：``order`` 里引用了上传图时必须一并传入，否则按
        "引用的上传图不存在"报错——**不用静默退回原图**，那会让面板显示的格
        与真正合成的格对不上。
        """
        sheet = Image.open(sheet_path).convert("RGB")
        total = rows * cols
        refs = list(order) if order else slicing.origin_refs(total)
        refs = slicing.drop_missing_origin(refs, total)
        frames = slicing.resolve_frames(sheet, rows, cols, refs, uploads, grid=grid)
        frames = slicing.apply_global_crop(frames, enabled=trim)
        if align_subject:
            frames = slicing.align_frames_by_content(frames)

        frame_urls: list[str] = []
        if output_dir is not None:
            frame_urls = [
                to_asset_download_url(p) for p in self._write_frame_files(frames, output_dir)
            ]

        base_grid = slicing.SheetGrid.uniform(rows, cols)
        # ⚠️ **必须给 URL 加内容指纹**，否则改了切法页面也不会变。
        #
        # 预览目录是按**多格图路径**派生的（`sheet-<hash>`），所以每次切帧都写
        # **同一个 `frame_02.png`** —— URL 一个字都不变。浏览器（和 React）
        # 完全有理由继续用旧位图，于是"确认切法后下面的帧没反应"。
        # 实测：接口返回 177×63，页面上仍是旧的 120×120；**刷新一次才对**。
        #
        # 指纹取**各帧实际尺寸 + 顺序**的组合：切法一变指纹就变，URL 随之改变，
        # 浏览器必然重新加载。不用时间戳，是为了让相同切法得到相同 URL
        # （避免无意义的缓存失效，也让同一张图反复切时不堆缓存）。
        fingerprint = _preview_fingerprint(frames, refs)
        if fingerprint:
            frame_urls = [f"{u}{'&' if '?' in u else '?'}v={fingerprint}" for u in frame_urls]

        return {
            "rows": rows,
            "cols": cols,
            "expected_cells": total,
            "resolved_cells": len(refs),
            "cell_size": list(frames[0].size) if frames else [0, 0],
            "frame_urls": frame_urls,
            # 回传实际用的分割线：前端刷新后能还原用户拖过的网格
            "grid_edges": {"xs": list(grid.xs if grid else base_grid.xs),
                           "ys": list(grid.ys if grid else base_grid.ys)},
            "custom_grid": bool(grid and not grid.is_uniform()),
            "cells": [
                {
                    "position": index + 1,
                    "source": ref.source,
                    "label": ref.label(),
                    "size": list(frame.size),
                }
                for index, (ref, frame) in enumerate(zip(refs, frames))
            ],
            "order_labels": slicing.describe_order(refs),
        }

    def _write_frame_files(self, frames: Sequence[Image.Image], output_dir: Path) -> list[Path]:
        """把每帧存成小图，**保持各帧相对宽高**，返回本地路径。

        ⚠️ 不能给所有帧套同一个长边。原来写成 `long_edge = min(240, ...)` 并让
        每帧都缩到"长边 = 那个值"，于是**宽度差异被缩放抹平**：
        378px 宽的格和 134px 宽的格都变成 240 高、看起来一样宽。
        用户拖窄了一列、确认后却"看不出变化"（切片其实是对的），根因就在这里。

        改为按**同一个缩放系数**缩（而不是同一个长边）：
        最宽的那帧压到 240，其余帧按同比例缩 —— 宽的就宽、窄的就窄，
        面板上一眼能看出哪一列被拖窄了。
        """
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        out: list[Path] = []
        if not frames:
            return out
        max_side = max(max(f.size) for f in frames)
        # 统一缩放系数：所有帧用同一个 scale，相对宽度才保得住
        scale = min(1.0, 240 / max_side)
        for index, frame in enumerate(frames, 1):
            target = frames_dir / f"frame_{index:02d}.png"
            if scale < 1.0:
                size = (
                    max(1, round(frame.width * scale)),
                    max(1, round(frame.height * scale)),
                )
                frame.resize(size, Image.LANCZOS).save(target, format="PNG")
            else:
                frame.save(target, format="PNG")
            out.append(target)
        return out

    # -- 产物路径 ----------------------------------------------------------

    def output_dir(self, node_id: str, version_id: str) -> Path:
        return self._work_dir / node_id / version_id

    def framesheet_path(self, node_id: str, version_id: str) -> Path:
        return self.output_dir(node_id, version_id) / FRAMESHEET_NAME

    def representations(
        self, result: motion_gif.MotionGifResult
    ) -> list[dict[str, Any]]:
        """把合成产物整理成待写入 Asset Hub 的 representation 列表。

        **多格图也在列**（``format="framesheet"``）：它既是「改切帧」重出的依据，
        也是可被其它功能按 format 取用的素材（用户要的「多方位数据」）。
        """
        out: list[dict[str, Any]] = []
        for fmt, path, mime in (
            ("gif", result.gif_path, "image/gif"),
            ("webp", result.webp_path, "image/webp"),
            ("mp4", result.mp4_path, "video/mp4"),
        ):
            if path and Path(path).exists():
                out.append(
                    {
                        "format": fmt,
                        "mime_type": mime,
                        "file_path": to_storage_path(Path(path)),
                        "file_size": Path(path).stat().st_size,
                    }
                )
        framesheet = Path(result.gif_path).parent / FRAMESHEET_NAME if result.gif_path else None
        if framesheet and framesheet.exists():
            out.append(
                {
                    "format": "framesheet",
                    "mime_type": "image/png",
                    "file_path": to_storage_path(framesheet),
                    "file_size": framesheet.stat().st_size,
                }
            )
        return out

    def cleanup(self, output_dir: Path) -> None:
        """删除某个版本的产物目录（重新生成前清场）。"""
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
