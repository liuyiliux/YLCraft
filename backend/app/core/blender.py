"""
YLCraft — Blender 命令行服务

提供 3D 模型的格式转换、减面、剥离骨骼与预览图渲染。

与 `core/ffmpeg.py` 同一范式：把命令行工具包装成服务，长耗时操作交给任务中心
异步执行，而不是在请求里干等。这两件事原本在 `Model3DService` 里是 TODO 占位
（`3d-rigging-digital-human` #15），全仓也没有别的 3D 处理实现可复用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ylcraft.core.blender")

#: 无头脚本目录
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "services" / "model3d" / "blender_scripts"


def discover_blender() -> str:
    """定位 Blender 可执行文件。

    顺序：环境变量 `BLENDER_PATH` → Windows / macOS / Linux 的常见安装位置
    → PATH 里的 `blender`。找不到时返回 `"blender"`，由调用时的失败信息来暴露
    问题（而不是在这里静默吞掉）。
    """
    configured = (os.getenv("BLENDER_PATH") or "").strip()
    if configured:
        return configured

    program_files = os.getenv("ProgramFiles", "")
    candidates: list[Path] = []
    if program_files:
        foundation = Path(program_files) / "Blender Foundation"
        if foundation.is_dir():
            candidates.extend(sorted(foundation.glob("Blender */blender.exe")))
    candidates.extend([
        Path("/Applications/Blender.app/Contents/MacOS/Blender"),
        Path("/usr/bin/blender"),
        Path("/usr/local/bin/blender"),
        Path("/snap/bin/blender"),
    ])

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("blender")
    return found or "blender"


class BlenderService:
    """Blender 无头批处理服务。"""

    def __init__(self, blender_path: Optional[str] = None):
        self.blender = blender_path or discover_blender()

    # -------------------------------------------------------------------------
    # 基础执行
    # -------------------------------------------------------------------------

    def _script(self, name: str) -> Path:
        return SCRIPTS_DIR / name

    async def _run(self, script: str, args: list[str], timeout: int = 1800) -> str:
        """后台执行一个无头脚本，返回合并输出。"""
        command = [
            self.blender,
            "--background",
            "--python", str(self._script(script)),
            "--",
            *args,
        ]
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = f"{result.stdout or ''}{result.stderr or ''}"
        if result.returncode != 0 or "YLCRAFT_OK" not in output:
            raise RuntimeError(f"Blender {script} 失败（退出码 {result.returncode}）：{output[-800:]}")
        return output

    async def is_available(self) -> bool:
        """Blender 是否可用（未安装时功能应显式降级，而不是假装成功）。"""
        if not self.blender or self.blender == "blender" and not shutil.which("blender"):
            return False
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [self.blender, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    async def version(self) -> str:
        result = await asyncio.to_thread(
            subprocess.run,
            [self.blender, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        match = re.search(r"Blender\s+([\d.]+)", result.stdout or "")
        return match.group(1) if match else ""

    # -------------------------------------------------------------------------
    # 能力
    # -------------------------------------------------------------------------

    async def convert_format(
        self,
        source: Path,
        output_path: Path,
        strip_armature: bool = False,
        ratio: float = 0.0,
        bone_map: Optional[dict] = None,
    ) -> Path:
        """转换模型格式，可选剥离骨骼、减面、按映射给骨骼改名。

        Args:
            source: 源模型（glb/gltf/fbx/obj）
            output_path: 目标文件，扩展名决定目标格式
            strip_armature: 是否剥离骨骼（送自动绑骨前需要——输入应当是没有绑过的网格）
            ratio: >0 时按该比例减面（0.3 = 保留 30%）。绑骨有 60MB 上限，
                而图生 3D 默认出 50 万面高模，减面是必需的预处理。
            bone_map: 骨骼改名映射（原骨骼名 → Mixamo 标准名），用于把模型接进通用动作库
        """
        args = [str(source), str(output_path)]
        if strip_armature:
            args.append("--strip-armature")
        if ratio and ratio > 0:
            args.extend(["--ratio", str(ratio)])
        # 映射表走临时文件而不是命令行参数：一张 19 根骨骼的表塞进命令行没问题，
        # 但手指骨俱全的角色能有六七十条，Windows 的命令行长度限制会把它截断。
        map_file: Optional[str] = None
        if bone_map:
            import json as _json
            import tempfile

            handle, map_file = tempfile.mkstemp(prefix="ylcraft-bonemap-", suffix=".json")
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                _json.dump(bone_map, stream, ensure_ascii=False)
            args.extend(["--bone-map", map_file])
        try:
            await self._run("convert.py", args)
        finally:
            if map_file:
                try:
                    Path(map_file).unlink()
                except OSError:
                    pass
        logger.info(
            "Blender converted %s -> %s (strip=%s ratio=%s bones=%s)",
            source, output_path, strip_armature, ratio, len(bone_map or {}),
        )
        return output_path

    async def skeleton_report(self, source: Path, output_path: Path) -> Path:
        """导出骨骼树（名字/父级/位置）+ **自动推断的 Mixamo 对应关系**。

        这是把非 Mixamo 谱系模型接进"通用动作库"的第一步：先看清有什么骨头、
        谁是谁的孩子，才能谈改名。推断结果需要人工过一眼左右手性后再使用。
        """
        await self._run("skeleton_report.py", [str(source), str(output_path)])
        return output_path

    async def retarget_bake(
        self,
        target: Path,
        source: Path,
        clip: str,
        output_path: Path,
    ) -> str:
        """把源模型的一段动作烘焙到目标骨架上。

        前提：两边骨骼名已统一（Mixamo 标准名或同名骨架）。Blender 的 Action 按
        骨骼名寻址，所以"名字一致"是唯一的硬要求——这也是为什么流程是
        「先 skeleton_report 推断 → convert --bone-map 改名 → 再 bake」。

        返回值是脚本的诊断行（含共用骨骼数、保留/丢弃的曲线数），便于排查
        "挂上了但模型不动"这类问题。
        """
        output = await self._run(
            "retarget_bake.py", [str(target), str(source), clip, str(output_path)]
        )
        diagnostic = next(
            (line for line in output.splitlines() if "YLCRAFT_RETARGET" in line), ""
        )
        logger.info("Blender retarget: %s", diagnostic or "（无诊断输出）")
        return diagnostic

    async def upright(self, source: Path, output_path: Path) -> tuple[bool, str]:
        """扶正绑定姿势（rest pose），返回 `(是否已扶正, 诊断行)`。

        有些模型的 rest pose 是**躺着**的，靠自带动画把自己扶起来（实测 Khronos 的
        BrainStem：rest 高度 2.00 / 动画中 2.78）。这类模型直接套别人的动作会当场
        躺平——骨骼按新动作摆位，网格却被拽回那个躺着的骨架。所以扶正是套动作前的
        必要准备，由脚本自己按阈值判断，正常站姿的模型不会被碰。

        **无需扶正时脚本不会写出输出文件**，调用方应继续用原文件——若这里无条件，
        返回输出路径，会得到一个"说写了其实不存在"的路径。
        """
        output = await self._run("upright.py", [str(source), str(output_path)])
        line = next(
            (item for item in output.splitlines() if "YLCRAFT_UPRIGHT need=" in item), ""
        )
        needed = "need=1" in line
        logger.info("Blender upright: %s", line or "（无诊断输出）")
        return needed, line

    async def generate_preview(
        self,
        source: Path,
        output_path: Path,
        resolution: int = 512,
    ) -> Path:
        """渲染一张预览图（透明背景 PNG）。"""
        await self._run("preview.py", [str(source), str(output_path), "--resolution", str(resolution)])
        logger.info("Blender preview rendered: %s", output_path)
        return output_path


_blender_service: Optional[BlenderService] = None


def get_blender_service() -> BlenderService:
    """获取 Blender 服务实例"""
    global _blender_service
    if _blender_service is None:
        _blender_service = BlenderService()
    return _blender_service
