"""3D 预演台受限操作的聚焦测试（design §5.3 / #18）。

分五层验证，重点是**拒绝的边界**而不是"能改"：
    A. 纯校验：revision 过期整批作废、锁定不可改、目标不存在、截图操作明确拒绝
    B. 落库：变换/机位/关键帧确实改到，且 fov 与焦距保持自洽
    C. 差异预览：改前/改后准确
    D. 工具：只读预览不改数据、落库走 CAS 且递增 revision、过期整批拒绝
    E. 授权：只有该有的 profile 拿得到这两个工具
"""

from __future__ import annotations

import copy
import uuid

import pytest
from sqlmodel import Session, create_engine
from sqlalchemy.pool import StaticPool

from app.db.models.previs import PrevisSceneDocument
from app.services import previs as ops
from app.services.agent import profile as agent_profile
from app.services.agent.tools import previs_tools


@pytest.fixture
def scene_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PrevisSceneDocument.__table__.create(engine)
    with Session(engine) as session:
        yield session


class _SharedSession:
    """把既有 session 包成可被 `with SessionLocal() as session` 使用、且**退出时不关闭**的对象。

    工具内部是 `with SessionLocal() as session:` —— 若直接把共享 session 交给它，
    退出时会关掉这个 session，后面的断言就再也读不到数据了。
    """

    def __init__(self, session: Session):
        self.session = session

    def __enter__(self) -> Session:
        return self.session

    def __exit__(self, *args) -> bool:
        return False


def _scene(**overrides) -> dict:
    base = {
        "durationFrames": 96,
        "activeCameraId": "cam-1",
        "nodes": [
            {"id": "actor", "name": "主演", "transform": {"position": [0, 0, 0], "rotation": [0, 0, 0, 1],
                                                          "scale": [1, 1, 1]}, "locked": False, "metadata": {}},
            {"id": "locked-prop", "name": "锁定的道具", "transform": {"position": [1, 0, 0], "rotation": [0, 0, 0, 1],
                                                                     "scale": [1, 1, 1]}, "locked": True,
             "metadata": {}},
        ],
        "cameras": [
            {"id": "cam-1", "name": "机位 1", "transform": {"position": [4, 3, 6], "rotation": [0, 0, 0, 1]},
             "target": [0, 0.8, 0], "fov": 54.4, "focalLength": 35, "sensorFormat": "full_frame", "locked": False},
        ],
        "keyframes": [],
        "operations": [],
        "settings": {},
    }
    base.update(overrides)
    return base


def _op(op_type: str, target_id: str = "", payload: dict | None = None) -> dict:
    return {"type": op_type, "targetId": target_id, "payload": payload or {}}


# ---------------------------------------------------------------- A. 纯校验

def test_revision_mismatch_rejects_the_whole_batch():
    """revision 过期时整批作废，而不是挑能用的执行。

    挑几条执行会拼出一个谁都没预料的中间态——比全部拒绝危险得多。
    """
    accepted, rejected = ops.validate_operations(
        _scene(),
        [
            _op("update_transform", "actor", {"position": [1, 0, 0]}),
            _op("update_transform", "locked-prop", {"position": [9, 0, 0]}),
        ],
        expected_revision=1,
        current_revision=4,
    )
    assert accepted == []
    assert len(rejected) == 2
    # 两条都要说清是 revision 的问题，而不是各报各的
    assert all("场景已被修改" in item["reason"] for item in rejected)
    assert rejected[0]["reason"].count("1") >= 1 and "4" in rejected[0]["reason"]


def test_locked_nodes_and_cameras_cannot_be_updated():
    scene = _scene()
    accepted, rejected = ops.validate_operations(
        scene,
        [
            _op("update_transform", "locked-prop", {"position": [9, 0, 0]}),
            _op("update_transform", "actor", {"position": [2, 0, 0]}),
        ],
        expected_revision=1,
        current_revision=1,
    )
    assert len(accepted) == 1 and accepted[0]["targetId"] == "actor"
    assert len(rejected) == 1
    assert rejected[0]["target_id"] == "locked-prop"
    assert "已锁定" in rejected[0]["reason"]


def test_unknown_target_and_unknown_type_are_rejected():
    accepted, rejected = ops.validate_operations(
        _scene(),
        [
            _op("update_transform", "ghost", {"position": [1, 0, 0]}),
            _op("teleport_everything"),
        ],
        expected_revision=1,
        current_revision=1,
    )
    assert accepted == []
    assert "不存在" in rejected[0]["reason"]
    assert "未知操作类型" in rejected[1]["reason"]


def test_capture_reference_is_rejected_with_a_reason_not_silently_accepted():
    """截图必须由客户端发起，工具做不到就明说——静默接受一个做不到的事更糟。"""
    accepted, rejected = ops.validate_operations(
        _scene(), [_op("capture_reference")], expected_revision=1, current_revision=1
    )
    assert accepted == []
    assert "客户端发起" in rejected[0]["reason"]


# ---------------------------------------------------------------- B. 落库

def test_apply_updates_only_the_targeted_node():
    scene = _scene()
    accepted, rejected = ops.validate_operations(
        scene, [_op("update_transform", "actor", {"position": [3, 1, 2]})],
        expected_revision=1, current_revision=1,
    )
    assert rejected == []
    next_scene, applied = ops.apply_operations(scene, accepted)

    actor = next(item for item in next_scene["nodes"] if item["id"] == "actor")
    prop = next(item for item in next_scene["nodes"] if item["id"] == "locked-prop")
    assert actor["transform"]["position"] == [3, 1, 2]
    # 未点名的节点不能被动到
    assert prop["transform"]["position"] == [1, 0, 0]
    assert len(applied) == 1


def test_apply_camera_fov_keeps_focal_length_consistent():
    """改 fov 必须同步焦距。

    否则前端 `normalizeCamera` 载入时会按旧焦距把 fov 重算回去，这次改动等于白做。
    """
    scene = _scene()
    accepted, rejected = ops.validate_operations(scene, [_op("set_camera", "cam-1", {"fov": 23.9})],
                                                 expected_revision=1, current_revision=1)
    assert rejected == []
    next_scene, _ = ops.apply_operations(scene, accepted)
    camera = next_scene["cameras"][0]
    assert camera["fov"] == 23.9
    # 23.9° 全画幅 ≈ 85mm（前端 optics.ts 用的是同一个公式）
    assert camera["focalLength"] == pytest.approx(85, abs=0.5)
    assert camera["sensorFormat"] == "full_frame"


def test_apply_adds_and_removes_keyframes():
    scene = _scene()
    add = _op("add_keyframe", "actor", {"property": "position", "frame": 24, "value": [1, 2, 3]})
    accepted, rejected = ops.validate_operations(scene, [add], expected_revision=1, current_revision=1)
    assert rejected == []
    next_scene, _ = ops.apply_operations(scene, accepted)
    assert len(next_scene["keyframes"]) == 1
    keyframe = next_scene["keyframes"][0]
    assert keyframe["property"] == "position" and keyframe["frame"] == 24
    # 旋转缺省 slerp、动画 clip 缺省 step，与前端 interpolationFor 一致
    assert keyframe["interpolation"] == "linear"

    rot = _op("add_keyframe", "actor", {"property": "rotation", "frame": 12, "value": [0, 0, 0, 1]})
    accepted, _ = ops.validate_operations(next_scene, [rot], expected_revision=2, current_revision=2)
    next_scene, _ = ops.apply_operations(next_scene, accepted)
    rotation_key = next(item for item in next_scene["keyframes"] if item["property"] == "rotation")
    assert rotation_key["interpolation"] == "slerp"

    remove = _op("remove_keyframe", "actor", {"property": "position", "frame": 24})
    accepted, rejected = ops.validate_operations(next_scene, [remove], expected_revision=3, current_revision=3)
    assert rejected == []
    next_scene, _ = ops.apply_operations(next_scene, accepted)
    assert [item["property"] for item in next_scene["keyframes"]] == ["rotation"]


def test_apply_does_not_mutate_the_input_scene():
    scene = _scene()
    snapshot = copy.deepcopy(scene)
    accepted, _ = ops.validate_operations(
        scene, [_op("update_transform", "actor", {"position": [5, 0, 0]})],
        expected_revision=1, current_revision=1,
    )
    ops.apply_operations(scene, accepted)
    assert scene == snapshot, "apply_operations 不该就地修改传入的场景"


# ---------------------------------------------------------------- C. 差异预览

def test_diff_reports_before_and_after_only_for_changed_fields():
    scene = _scene()
    accepted, _ = ops.validate_operations(
        scene, [_op("update_transform", "actor", {"position": [0, 0, 0], "scale": None})],
        expected_revision=1, current_revision=1,
    )
    diff = ops.diff_operations(scene, accepted)
    assert len(diff) == 1
    entry = diff[0]
    assert entry["target_id"] == "actor"
    assert entry["before"]["position"] == [0, 0, 0]
    # 只带被改动的字段，避免把整份场景塞进预览
    assert "rotation" not in entry["before"]


def test_diff_for_set_camera_includes_derived_focal_length():
    scene = _scene()
    accepted, _ = ops.validate_operations(scene, [_op("set_camera", "cam-1", {"fov": 39.6})],
                                         expected_revision=1, current_revision=1)
    entry = ops.diff_operations(scene, accepted)[0]
    # 预览要提前告诉用户"焦距也会跟着变"，否则确认后才发现会很意外
    assert entry["after"]["focalLength"] == pytest.approx(50, abs=0.5)
    assert entry["before"]["focalLength"] == 35


# ---------------------------------------------------------------- D. 工具层

def test_preview_tool_is_read_only(scene_session, monkeypatch):
    """预览不得改动任何东西——它是给人工确认看的，不是试探性执行。"""
    row = _insert_scene(scene_session, _scene(), revision=3)
    monkeypatch.setattr(previs_tools, "SessionLocal", lambda: _SharedSession(scene_session))

    result = _run(previs_tools.previs_preview_operations(
        scene_id=row.id,
        operations=[_op("update_transform", "actor", {"position": [7, 0, 0]})],
        expected_revision=3,
    ))
    assert result["success"] is True
    assert result["valid"] is True
    assert result["accepted_count"] == 1
    assert result["diff"][0]["after"]["position"] == [7, 0, 0]

    scene_session.refresh(row)
    # 场景未动：revision 与节点都保持原样
    assert row.revision == 3
    assert row.scene_json["nodes"][0]["transform"]["position"] == [0, 0, 0]


def test_apply_tool_increments_revision_and_records_history(scene_session, monkeypatch):
    row = _insert_scene(scene_session, _scene(), revision=2)
    monkeypatch.setattr(previs_tools, "SessionLocal", lambda: _SharedSession(scene_session))

    result = _run(previs_tools.previs_apply_operations(
        scene_id=row.id,
        operations=[_op("update_transform", "actor", {"position": [4, 0, 0]})],
        expected_revision=2,
    ))
    assert result["success"] is True
    assert result["previous_revision"] == 2
    assert result["revision"] == 3
    assert result["applied_count"] == 1

    scene_session.refresh(row)
    assert row.revision == 3
    assert row.scene_json["nodes"][0]["transform"]["position"] == [4, 0, 0]
    # 操作历史随场景持久化（design 要求可撤销性不能只存在浏览器里）
    history = row.scene_json["operations"]
    assert len(history) == 1
    assert history[0]["type"] == "update_transform"
    assert history[0]["targetId"] == "actor"
    assert history[0]["summary"]


def test_apply_tool_rejects_stale_revision_without_touching_the_scene(scene_session, monkeypatch):
    """过期 Agent 不得覆盖人工编辑：整批拒绝，且场景一字不动。"""
    before = _scene()
    row = _insert_scene(scene_session, before, revision=7)
    monkeypatch.setattr(previs_tools, "SessionLocal", lambda: _SharedSession(scene_session))

    result = _run(previs_tools.previs_apply_operations(
        scene_id=row.id,
        operations=[_op("update_transform", "actor", {"position": [9, 9, 9]})],
        expected_revision=5,     # 过期
    ))
    assert result["success"] is False
    assert result["applied_count"] == 0
    assert "场景已被修改" in result["rejected"][0]["reason"]

    scene_session.refresh(row)
    assert row.revision == 7
    assert row.scene_json == before, "被拒的批次不得对场景产生任何副作用"


def test_apply_tool_revalidates_after_preview(scene_session, monkeypatch):
    """预览通过不代表落库时仍通过——两次之间场景可能已被人工改动。"""
    row = _insert_scene(scene_session, _scene(), revision=1)
    monkeypatch.setattr(previs_tools, "SessionLocal", lambda: _SharedSession(scene_session))

    preview = _run(previs_tools.previs_preview_operations(
        scene_id=row.id,
        operations=[_op("update_transform", "locked-prop", {"position": [9, 0, 0]})],
        expected_revision=1,
    ))
    # 锁定的目标在校验阶段就被拦下，预览里就该显示"不可执行"
    assert preview["accepted_count"] == 0
    assert "已锁定" in preview["rejected"][0]["reason"]

    result = _run(previs_tools.previs_apply_operations(
        scene_id=row.id,
        operations=[_op("update_transform", "locked-prop", {"position": [9, 0, 0]})],
        expected_revision=1,
    ))
    assert result["success"] is False
    scene_session.refresh(row)
    assert row.revision == 1


# ---------------------------------------------------------------- E. 授权

def test_previs_tools_are_authorized_only_for_director_profiles():
    """授权是硬约束：**注册了但未授权等于不可用**。"""
    profiles = {item["id"]: (item.get("allowed_tools") or []) for item in agent_profile.DEFAULT_AGENT_PROFILES}
    assert "previs_preview_operations" in profiles["creative-director"]
    assert "previs_apply_operations" in profiles["creative-director"]
    # 分镜导演拥有预演：预演就是分镜的空间层
    assert "previs_preview_operations" in profiles["storyboard-director"]
    assert "previs_apply_operations" in profiles["storyboard-director"]
    # 审稿与角色设计不应拿到场景写操作
    assert "previs_apply_operations" not in profiles["quality-reviewer"]
    assert "previs_apply_operations" not in profiles["character-designer"]


# ---------------------------------------------------------------- 辅助

def _insert_scene(session: Session, scene: dict, revision: int = 1) -> PrevisSceneDocument:
    row = PrevisSceneDocument(
        id=uuid.uuid4().hex,
        project_id=uuid.uuid4().hex,
        title="预演操作测试",
        scene_json=scene,
        revision=revision,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _run(coro):
    """同步跑一个 async 工具（测试环境无事件循环）。"""
    import asyncio

    return asyncio.run(coro)
