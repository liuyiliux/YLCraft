"""`Model3DService.extract_metadata` 的骨骼/动画契约测试（tasks #16 验收）。

为什么值得单独测：素材库的「已绑骨 / 带动画」徽标、`has_bones` / `has_animations`
判定，全都建立在这份元数据上。而它曾经把 `len(skins)`（皮肤**套数**）当成骨骼数——
vanguard.glb 有 2 套 skin、49 根骨骼，报告却写「2 根骨骼」。布尔判定没露馅，
但落库的数字是错的，一旦有人在界面上显示「骨骼 N 根」，就会得出
「这个绑定只有 2 根骨」这种完全相反的结论。

这里用手造的最小 glTF/GLB 固定住口径，不依赖任何外部模型文件。
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from app.services.model3d.service import Model3DService


def _rigged_payload() -> dict:
    """2 套 skin（joints 有重叠）+ 1 段动画 + 1 个网格。"""
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "skin": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [
            {"count": 12, "type": "VEC3", "componentType": 5126},
            {"count": 30, "type": "SCALAR", "componentType": 5123},
            # 动画采样器的时间轴：0–2 秒
            {"count": 2, "type": "SCALAR", "componentType": 5126, "min": [0.0], "max": [2.0]},
        ],
        "skins": [{"joints": [0, 1, 2]}, {"joints": [2, 3]}],
        "animations": [
            {"name": "Idle", "channels": [{"sampler": 0}], "samplers": [{"input": 2}]},
        ],
        "materials": [{}],
        "textures": [{}],
    }


def _make_glb(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    body += b" " * ((4 - len(body) % 4) % 4)
    header = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(body))
    return header + struct.pack("<I", len(body)) + b"JSON" + body


@pytest.mark.asyncio
async def test_bones_count_joints_not_skins(tmp_path: Path):
    """骨骼数按骨架 joints 计，多套 skin 共用骨骼时按并集去重。"""
    target = tmp_path / "rigged.glb"
    target.write_bytes(_make_glb(_rigged_payload()))

    info = await Model3DService(None).extract_metadata(str(target))

    assert info["skins"] == 2
    assert info["bones"] == 4, "joints 并集 {0,1,2,3} = 4，而不是 skins 的 2"


@pytest.mark.asyncio
async def test_animation_details_expose_channels_and_range(tmp_path: Path):
    target = tmp_path / "rigged.glb"
    target.write_bytes(_make_glb(_rigged_payload()))

    info = await Model3DService(None).extract_metadata(str(target))

    # `animations` 保持名称列表：既有调用方靠它做布尔判定
    assert info["animations"] == ["Idle"]
    assert info["animation_count"] == 1
    detail = info["animation_details"][0]
    assert detail["name"] == "Idle"
    assert detail["channels"] == 1
    assert detail["start"] == 0.0
    assert detail["end"] == 2.0


@pytest.mark.asyncio
async def test_gltf_extracts_same_facts_as_glb(tmp_path: Path):
    """`.gltf` 与 `.glb` 必须同一口径——以前 .gltf 分支根本不提骨骼，
    导致 GLTF 模型永远打不上「已绑骨」标签。"""
    payload = _rigged_payload()
    glb_path = tmp_path / "rigged.glb"
    gltf_path = tmp_path / "rigged.gltf"
    glb_path.write_bytes(_make_glb(payload))
    gltf_path.write_text(json.dumps(payload), encoding="utf-8")

    service = Model3DService(None)
    glb_info = await service.extract_metadata(str(glb_path))
    gltf_info = await service.extract_metadata(str(gltf_path))

    for key in ("bones", "skins", "vertices", "faces", "animations", "animation_count"):
        assert glb_info[key] == gltf_info[key], f"{key} 在两种格式下不一致"
    assert gltf_info["bones"] == 4


@pytest.mark.asyncio
async def test_static_model_reports_zero_bones(tmp_path: Path):
    """静态高模（图生 3D 的产物）：骨骼 0、无动画，判定必须是 False。"""
    payload = _rigged_payload()
    payload.pop("skins")
    payload.pop("animations")
    target = tmp_path / "static.glb"
    target.write_bytes(_make_glb(payload))

    info = await Model3DService(None).extract_metadata(str(target))

    assert info["bones"] == 0
    assert info["skins"] == 0
    assert "animations" not in info
    assert bool(info["bones"]) is False
    assert bool(info.get("animations")) is False


@pytest.mark.asyncio
async def test_mesh_counts(tmp_path: Path):
    target = tmp_path / "rigged.glb"
    target.write_bytes(_make_glb(_rigged_payload()))

    info = await Model3DService(None).extract_metadata(str(target))

    assert info["mesh_count"] == 1
    assert info["vertices"] == 12   # POSITION accessor count
    assert info["faces"] == 10      # 30 个索引 / 3


def _skinned_payload(bone_names: list[str]) -> dict:
    nodes = [{"name": name} for name in bone_names]
    return {
        "asset": {"version": "2.0"},
        "nodes": nodes,
        "skins": [{"joints": list(range(len(nodes)))}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"count": 3, "type": "VEC3", "componentType": 5126}],
    }


@pytest.mark.asyncio
async def test_bone_names_read_skin_joints(tmp_path: Path):
    target = tmp_path / "skinned.glb"
    target.write_bytes(_make_glb(_skinned_payload(["Hips", "Spine", "Head"])))

    assert Model3DService.bone_names(str(target)) == ["Hips", "Spine", "Head"]


@pytest.mark.asyncio
async def test_mixamo_detection(tmp_path: Path):
    mixamo = tmp_path / "mixamo.glb"
    mixamo.write_bytes(_make_glb(_skinned_payload(["mixamorig:Hips", "mixamorig:Head"])))
    assert Model3DService.is_mixamo_skeleton(str(mixamo)) is True

    other = tmp_path / "other.glb"
    other.write_bytes(_make_glb(_skinned_payload(["torso_joint_1", "neck_joint_1"])))
    assert Model3DService.is_mixamo_skeleton(str(other)) is False


@pytest.mark.asyncio
async def test_mixamo_detection_rejects_skeletonless_model(tmp_path: Path):
    """没有骨架的模型不能因为"空列表全部通过"被误判成 Mixamo。"""
    plain = tmp_path / "plain.glb"
    plain.write_bytes(_make_glb({"asset": {"version": "2.0"}, "meshes": []}))
    assert Model3DService.is_mixamo_skeleton(str(plain)) is False

    assert Model3DService.is_mixamo_skeleton(str(tmp_path / "missing.glb")) is False
