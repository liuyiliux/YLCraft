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

from app.db.models.previs import PrevisMotionAsset, PrevisSceneDocument
from app.services import previs as ops
from app.services.agent import profile as agent_profile
from app.services.agent.tools import previs_tools


@pytest.fixture
def scene_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    PrevisSceneDocument.__table__.create(engine)
    # 工具层要读动作清单来校验"动作引用是否存在、载体是否匹配"（`motion_service.motion_carriers`），
    # 因此这张表也得建：不建的话工具会抛 `no such table`，而那是**夹具的缺陷**，不是产品代码的问题。
    PrevisMotionAsset.__table__.create(engine)
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
            # 语义操作（身高 / 姿势 / 动作）的目标：必须是 kind=human_proxy 的节点
            {"id": "hero", "kind": "human_proxy", "name": "人形占位",
             "transform": {"position": [0, 0, 1], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]},
             "locked": False, "metadata": {"height": 1.7, "pose": "stand"}},
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


# ---------------------------------------------------------------- F. 语义操作与参数校验（tasks 3.1–3.5）

def _hero(scene: dict) -> dict:
    return next(item for item in scene["nodes"] if item["id"] == "hero")


def test_add_node_rejects_unknown_kind_instead_of_storing_it():
    """幻觉出来的节点种类必须当场拒掉。

    落库后再被前端 `normalizeSceneData` 丢弃的话，结果是"落库成功但节点消失"——
    两边都会以为是对面的问题，排查成本远高于一次比较。
    """
    accepted, rejected = ops.validate_operations(
        _scene(),
        [_op("add_node", payload={"node": {"kind": "dragon", "name": "龙"}})],
        expected_revision=1, current_revision=1,
    )
    assert accepted == []
    assert "未知的节点种类" in rejected[0]["reason"]
    # 拒绝原因要带上可用值，否则调用方只能去翻代码
    assert "human_proxy" in rejected[0]["reason"]


def test_add_node_enforces_metadata_ranges_for_every_kind():
    cases: list[tuple[dict, str]] = [
        ({"height": 9}, "超出范围"),
        ({"height": "高高的"}, "需要一个数值"),
        ({"pose": "狂奔"}, "未知的姿势"),
        ({"poseJoints": {"leftKnee": -20}}, "生理约束"),
        ({"poseJoints": {"leftKnee": 999}}, "超出范围"),
        ({"poseJoints": {"leftShoulder": [999, 0, 0]}}, "超出范围"),
        ({"poseJoints": {"leftTail": 10}}, "未知的姿势字段"),
        ({"animationClip": "walk"}, "必须形如"),
        ({"animationClip": "motion:nope"}, "动作不存在"),
    ]
    for metadata, expected in cases:
        accepted, rejected = ops.validate_operations(
            _scene(),
            [_op("add_node", payload={"node": {"kind": "human_proxy", "name": "甲", "metadata": metadata}})],
            expected_revision=1, current_revision=1,
            motion_carriers={"walk": "params"},
        )
        assert accepted == [], metadata
        assert expected in rejected[0]["reason"], (metadata, rejected[0]["reason"])

    # 几何体与灯光的种类同样受白名单约束
    for node, expected in (
        ({"kind": "primitive", "name": "体", "metadata": {"primitive": "torus"}}, "未知的几何体种类"),
        ({"kind": "light", "name": "灯", "metadata": {"light": "neon"}}, "未知的灯光种类"),
        ({"kind": "asset_model", "name": "模型"}, "需要 assetId"),
    ):
        rejected = ops.validate_operations(
            _scene(), [_op("add_node", payload={"node": node})], expected_revision=1, current_revision=1
        )[1]
        assert expected in rejected[0]["reason"], node


def test_add_node_accepts_a_valid_human_proxy_and_writes_it():
    accepted, rejected = ops.validate_operations(
        _scene(),
        [_op("add_node", payload={"node": {
            "kind": "human_proxy", "name": "甲",
            "metadata": {"height": 1.85, "pose": "sit", "animationClip": "motion:walk"},
        }})],
        expected_revision=1, current_revision=1, motion_carriers={"walk": "params"},
    )
    assert rejected == []
    next_scene, _ = ops.apply_operations(_scene(), accepted)
    added = next_scene["nodes"][-1]
    assert added["metadata"]["height"] == 1.85
    assert added["metadata"]["animationClip"] == "motion:walk"
    assert added["id"], "缺 id 时应自动补一个稳定 ID"


def test_motion_reference_is_rejected_when_the_catalog_is_unavailable():
    """校验不了就拒绝，而不是放过——这与 `capture_reference` 的处理同一条原则。"""
    rejected = ops.validate_operations(
        _scene(),
        [_op("add_node", payload={"node": {"kind": "human_proxy", "metadata": {"animationClip": "motion:walk"}}})],
        expected_revision=1, current_revision=1, motion_carriers=None,
    )[1]
    assert "动作清单当前不可用" in rejected[0]["reason"]


def test_motion_carrier_must_match_the_human_proxy():
    """`transform` / `bone` 动作驱动不了人形占位：给的理由要说明"为什么不行"。"""
    rejected = ops.validate_operations(
        _scene(),
        [_op("assign_motion", "hero", {"motion": "motion:turn-around"})],
        expected_revision=1, current_revision=1, motion_carriers={"turn-around": "transform"},
    )[1]
    assert "不能驱动人形占位" in rejected[0]["reason"]


def test_semantic_operations_only_touch_human_proxies():
    accepted, rejected = ops.validate_operations(
        _scene(),
        [
            _op("set_human_proxy", "actor", {"height": 1.8}),
            _op("assign_motion", "cam-1", {"motion": "motion:walk"}),
        ],
        expected_revision=1, current_revision=1, motion_carriers={"walk": "params"},
    )
    assert accepted == []
    assert "只能作用于人形占位节点" in rejected[0]["reason"]
    assert "只能作用于节点" in rejected[1]["reason"]


def test_set_human_proxy_writes_metadata_without_touching_the_source_scene():
    scene = _scene()
    accepted, rejected = ops.validate_operations(
        scene, [_op("set_human_proxy", "hero", {"height": 1.85, "pose": "sit"})],
        expected_revision=1, current_revision=1,
    )
    assert rejected == []
    next_scene, applied = ops.apply_operations(scene, accepted)
    assert _hero(next_scene)["metadata"]["height"] == 1.85
    assert _hero(next_scene)["metadata"]["pose"] == "sit"
    assert applied[0]["summary"]
    # 纯计算：原场景不被就地修改
    assert _hero(scene)["metadata"] == {"height": 1.7, "pose": "stand"}


def test_setting_a_pose_clears_custom_joints():
    """与前端一致：**选预设 = 放弃自定义关节角度**。

    前端 `resolveHumanProxyPose` 是"自定义按字段覆盖预设"，不清掉自定义值会出现
    "设了姿势却没变化"——这类不一致在两边各写一遍时最容易漏。
    """
    scene = _scene()
    _hero(scene)["metadata"]["poseJoints"] = {"leftKnee": 40}
    accepted, _ = ops.validate_operations(
        scene, [_op("set_human_proxy", "hero", {"pose": "sit"})], expected_revision=1, current_revision=1,
    )
    next_scene, _ = ops.apply_operations(scene, accepted)
    assert _hero(next_scene)["metadata"]["pose"] == "sit"
    assert "poseJoints" not in _hero(next_scene)["metadata"]


def test_set_human_proxy_rejects_motion_and_points_to_assign_motion():
    """身高/姿势与动作分成两个操作，避免"两条路做同一件事"（改一边忘一边）。"""
    rejected = ops.validate_operations(
        _scene(),
        [_op("set_human_proxy", "hero", {"height": 1.8, "motion": "motion:walk"})],
        expected_revision=1, current_revision=1, motion_carriers={"walk": "params"},
    )[1]
    assert "assign_motion" in rejected[0]["reason"]


def test_assign_motion_writes_and_clears_the_static_reference():
    scene = _scene()
    accepted, rejected = ops.validate_operations(
        scene, [_op("assign_motion", "hero", {"motion": "motion:walk"})],
        expected_revision=1, current_revision=1, motion_carriers={"walk": "params"},
    )
    assert rejected == []
    next_scene, _ = ops.apply_operations(scene, accepted)
    assert _hero(next_scene)["metadata"]["animationClip"] == "motion:walk"

    accepted, rejected = ops.validate_operations(
        next_scene, [_op("assign_motion", "hero", {"motion": ""})],
        expected_revision=2, current_revision=2, motion_carriers={"walk": "params"},
    )
    assert rejected == []
    cleared, _ = ops.apply_operations(next_scene, accepted)
    assert _hero(cleared)["metadata"]["animationClip"] == ""


def test_mixed_batch_keeps_the_valid_operation_and_leaves_the_rejected_target_untouched():
    """3.3 的核心要求：逐条拒绝，合法项照常生效，被拒目标保持原状态。"""
    scene = _scene()
    accepted, rejected = ops.validate_operations(
        scene,
        [
            _op("set_human_proxy", "hero", {"height": 9}),              # 非法
            _op("update_transform", "actor", {"position": [2, 0, 0]}),  # 合法
        ],
        expected_revision=1, current_revision=1,
    )
    assert len(accepted) == 1 and len(rejected) == 1
    next_scene, applied = ops.apply_operations(scene, accepted)
    assert applied[0]["target_id"] == "actor"
    assert _hero(next_scene)["metadata"] == {"height": 1.7, "pose": "stand"}


def test_semantic_operations_are_blocked_on_locked_nodes():
    scene = _scene()
    _hero(scene)["locked"] = True
    rejected = ops.validate_operations(
        scene, [_op("assign_motion", "hero", {"motion": "motion:walk"})],
        expected_revision=1, current_revision=1, motion_carriers={"walk": "params"},
    )[1]
    assert "已锁定" in rejected[0]["reason"]


def test_diff_expresses_pose_motion_and_height_changes():
    """3.5：预览要能看出"姿势/动作/身高"改了什么，而不是只给一句摘要。"""
    scene = _scene()
    accepted, _ = ops.validate_operations(
        scene,
        [
            _op("set_human_proxy", "hero", {"height": 1.85, "pose": "sit"}),
            _op("assign_motion", "hero", {"motion": "motion:walk"}),
        ],
        expected_revision=1, current_revision=1, motion_carriers={"walk": "params"},
    )
    diff = ops.diff_operations(scene, accepted)
    pose_entry = next(item for item in diff if item["type"] == "set_human_proxy")
    assert pose_entry["before"] == {"height": 1.7, "pose": "stand"}
    assert pose_entry["after"] == {"height": 1.85, "pose": "sit"}
    motion_entry = next(item for item in diff if item["type"] == "assign_motion")
    assert motion_entry["before"]["motion"] == ""
    assert motion_entry["after"]["motion"] == "motion:walk"


def test_add_node_diff_includes_metadata():
    """新建节点的预览必须带 metadata——身高/姿势/动作都住在它里面。"""
    accepted, _ = ops.validate_operations(
        _scene(),
        [_op("add_node", payload={"node": {"kind": "human_proxy", "name": "乙", "metadata": {"pose": "sit"}}})],
        expected_revision=1, current_revision=1,
    )
    entry = ops.diff_operations(_scene(), accepted)[0]
    assert entry["before"] is None
    assert entry["after"]["metadata"]["pose"] == "sit"


def test_scene_brief_reports_the_human_proxy_state():
    """3.4：摘要缺了姿势/动作/身高，Agent 只能猜"现在什么样"，于是提出无效改动。"""
    from app.services.agent.context_pack import _previs_scene_brief

    scene = _scene()
    _hero(scene)["metadata"] = {"height": 1.85, "pose": "sit", "animationClip": "motion:walk"}
    row = PrevisSceneDocument(id="scene-1", title="预演", revision=4, scene_json=scene)
    brief = _previs_scene_brief(row)
    assert brief["human_proxies"] == [
        {"node_id": "hero", "name": "人形占位", "height": 1.85, "pose": "sit",
         "motion": "motion:walk", "custom_pose": False},
    ]
    assert brief["human_proxies_truncated"] is False


def test_apply_tool_assigns_motion_end_to_end(scene_session, monkeypatch):
    """工具层把动作清单查出来喂给纯校验函数——这条链路要真的通。"""
    _insert_motion(scene_session, "walk")
    row = _insert_scene(scene_session, _scene(), revision=1)
    monkeypatch.setattr(previs_tools, "SessionLocal", lambda: _SharedSession(scene_session))
    operation = _op("assign_motion", "hero", {"motion": "motion:walk"})

    preview = _run(previs_tools.previs_preview_operations(
        scene_id=row.id, operations=[operation], expected_revision=1,
    ))
    assert preview["valid"] is True
    assert preview["diff"][0]["after"]["motion"] == "motion:walk"

    result = _run(previs_tools.previs_apply_operations(
        scene_id=row.id, operations=[operation], expected_revision=1,
    ))
    assert result["success"] is True
    assert result["applied_count"] == 1

    scene_session.refresh(row)
    assert _hero(row.scene_json)["metadata"]["animationClip"] == "motion:walk"
    # 操作历史里记的是一句人话，不是机器日志
    assert "动作" in row.scene_json["operations"][-1]["summary"]


# ---------------------------------------------------------------- 辅助

def _insert_motion(session: Session, slug: str, carrier: str = "params", *, active: bool = True) -> PrevisMotionAsset:
    row = PrevisMotionAsset(
        id=f"motion-{slug}", slug=slug, name=slug, carrier=carrier,
        duration_seconds=1.0, fps=24, frame_count=24, loopable=True,
        payload_json={"channels": {}}, origin="测试", license="测试", is_active=active,
    )
    session.add(row)
    session.commit()
    return row

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
