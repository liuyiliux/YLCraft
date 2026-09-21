"""分镜格 → 预演初稿的聚焦测试（design D8 / tasks 4.1–4.4）。

分四层：
    A. 翻译：完整格、缺字段、无人物、英文档位、构图偏移、机位复用
    B. 边界：不翻译的字段只出提示、道具匹配不到只出提示、路径坐标才打关键帧
    C. 可执行性：初稿产出的**每一条**操作都要能通过受限操作校验并落库
    D. 接口：未绑定分镜 400、场景不存在 404、生成过程不写任何数据
"""

from __future__ import annotations

import contextlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import previs as previs_api
from app.db.models.creative_project import ProjectContent
from app.db.models.previs import PrevisMotionAsset, PrevisSceneDocument
from app.services import previs as ops
from app.services.previs import draft_service
from app.services.previs.draft import build_previs_draft, load_storyboard_panel


def _panel(**overrides) -> dict:
    base = {
        "panel_number": 3,
        "characters": ["萧然", "苏棠"],
        "blocking": "萧然站在画面左侧，苏棠站在右侧靠近前景",
        "shot_size": "中景",
        "camera_angle": "平视",
        "composition": "居中",
        "duration_seconds": 4,
        "props": [],
        "action": "两人对峙",
    }
    base.update(overrides)
    return base


def _nodes(draft: dict, kind: str) -> list[dict]:
    return [
        item["payload"]["node"] for item in draft["operations"]
        if item["type"] == "add_node" and item["payload"]["node"]["kind"] == kind
    ]


def _fields(draft: dict) -> set[str]:
    return {str(item["field"]) for item in draft["defaults"]}


# ---------------------------------------------------------------- A. 翻译

def test_complete_panel_translates_people_camera_and_duration():
    draft = build_previs_draft({"fps": 24}, _panel())

    heroes = _nodes(draft, "human_proxy")
    assert [node["name"] for node in heroes] == ["萧然", "苏棠"]
    assert all(node["metadata"]["pose"] == "stand" for node in heroes)
    assert all(node["id"].startswith("draft-p3-hero-") for node in heroes), "新建节点必须自带稳定 ID"

    camera = [item for item in draft["operations"] if item["type"] == "add_camera"]
    assert len(camera) == 1
    # 中景 = 4m / 35mm；场景里没有机位，所以是新建而不是改现有的
    assert camera[0]["payload"]["focalLength"] == 35
    # 机位相对**群体中心**后退 4m（中心 z = 0.3：苏棠在前景 +0.6，萧然在原点）
    assert camera[0]["payload"]["position"][2] == pytest.approx((0.0 + 0.6) / 2 + 4.0, abs=0.05)
    assert camera[0]["payload"]["fov"] == pytest.approx(54.43, abs=0.05)

    duration = [item for item in draft["operations"] if item["type"] == "set_duration"]
    assert duration[0]["payload"]["frames"] == 96  # 4 秒 × 24fps
    assert "duration_seconds" not in _fields(draft), "分镜写了时长就不该出现在默认值清单里"
    assert "shot_size" not in _fields(draft)
    assert "camera_angle" not in _fields(draft)
    # 身高是分镜格根本没有的字段，必须显式列为默认
    assert "height" in _fields(draft)
    assert "location" not in draft["summary"]  # location 不参与计算，只出提示


def test_blocking_direction_words_place_people_on_both_axes():
    draft = build_previs_draft({}, _panel())
    heroes = _nodes(draft, "human_proxy")
    xiao = heroes[0]["transform"]["position"]
    su = heroes[1]["transform"]["position"]

    # 左 → x 负；右 + 前景 → x 正、z 正（两个轴各自匹配，不是取一个"最长命中"）
    assert xiao[0] < 0 and xiao[2] == 0
    assert su[0] > 0 and su[2] > 0
    # 窗口遇到下一个名字就截断：萧然不该吃到"苏棠站在右侧"里的"右"
    assert xiao[0] == pytest.approx(-0.8)
    assert su == pytest.approx([0.8, 0.0, 0.6])


def test_missing_fields_fall_back_and_are_listed_in_defaults():
    draft = build_previs_draft({}, {"panel_number": 7})
    assert _fields(draft) >= {
        "characters", "height", "blocking", "shot_size", "camera_angle", "composition", "duration_seconds",
    }
    # 3 秒兜底：既没有 characters 也没有 shot_size，走"其他景别"的 4 秒档
    summary = draft["summary"]
    assert summary["shot_size"] == "中景"
    assert summary["camera_angle"] == "平视"
    assert summary["duration_seconds"] == 4
    assert summary["human_proxy_count"] == 1
    assert any("没有写明人物" in item for item in draft["warnings"])


def test_panel_without_characters_places_one_proxy_and_warns():
    draft = build_previs_draft({}, _panel(characters=[]))
    assert len(_nodes(draft, "human_proxy")) == 1
    assert any("没有写明人物" in item for item in draft["warnings"])
    # 没有人物信息也不该报错——初稿是"可编辑的起点"，不是校验器
    assert draft["operations"]


def test_lengthy_shot_and_angle_ladders_are_ordered_by_specificity():
    # "medium close-up" 里同时含 medium 与 close：取最长命中 → 近景（50mm），
    # 若按声明顺序匹配会落到中景，画面上只表现为"机位比想象远一点"，很难发现
    close = build_previs_draft({}, _panel(shot_size="medium close-up"))
    assert close["summary"]["shot_size"] == "近景"
    assert close["summary"]["focal_length"] == 50

    wide = build_previs_draft({}, _panel(shot_size="wide shot", camera_angle="slightly low angle"))
    assert wide["summary"]["shot_size"] == "远景"
    assert wide["summary"]["camera_angle"] == "仰视"
    # 仰视 → 机位低于眼睛高度
    assert wide["summary"]["camera_position"][1] < 1.58


def test_composition_moves_the_look_at_point_not_the_camera():
    centered = build_previs_draft({}, _panel(composition="居中"))
    thirds = build_previs_draft({}, _panel(composition="左三分"))
    centered_target = next(item for item in centered["operations"] if item["type"] == "add_camera")["payload"]["target"]
    thirds_target = next(item for item in thirds["operations"] if item["type"] == "add_camera")["payload"]["target"]
    # 机位代表"从哪拍"，构图代表"主体落在画面哪里"，所以构图不该动机位
    assert centered_target[0] == pytest.approx(0.0, abs=1e-6)
    assert thirds_target[0] < -0.1
    assert "composition" not in _fields(thirds)


def test_existing_camera_is_updated_instead_of_adding_one():
    scene = {"fps": 24, "activeCameraId": "cam-9", "cameras": [{"id": "cam-9", "name": "机位 9", "fov": 50}]}
    draft = build_previs_draft(scene, _panel())
    assert not [item for item in draft["operations"] if item["type"] == "add_camera"]
    set_camera = [item for item in draft["operations"] if item["type"] == "set_camera"]
    assert set_camera[0]["targetId"] == "cam-9"


def test_over_the_shoulder_rotates_the_camera_azimuth():
    front = build_previs_draft({}, _panel(camera_hint="平视"))
    ots = build_previs_draft({}, _panel(camera_hint="over-the-shoulder"))
    assert front["summary"]["camera_azimuth"] == "正面"
    assert ots["summary"]["camera_azimuth"] == "过肩"
    front_pos = front["summary"]["camera_position"]
    ots_pos = ots["summary"]["camera_position"]
    assert ots_pos[0] > front_pos[0]  # 方位转了 35°，机位横向让开


# ---------------------------------------------------------------- B. 边界

def test_props_are_placed_only_when_matched():
    panel = _panel(props=["长桌", "不存在的道具"])
    draft = build_previs_draft(
        {}, panel,
        prop_assets={"长桌": {"asset_id": "asset-9", "name": "长桌模型", "model_url": "/api/v1/assets/asset-9/files/a.glb"}},
    )
    models = _nodes(draft, "asset_model")
    assert len(models) == 1
    assert models[0]["assetId"] == "asset-9"
    assert models[0]["metadata"]["modelUrl"].endswith("a.glb")
    assert any("不存在的道具" in item for item in draft["warnings"])
    # 位置的尺寸不做解析（素材库模型以自带包围盒为准），因此要显式记为占位
    assert "props:长桌" in _fields(draft)


def test_untranslatable_fields_produce_warnings_instead_of_invented_keyframes():
    panel = _panel(movement_path="从门口走到床边", camera_motion="推近", location="宴会厅")
    draft = build_previs_draft({}, panel)
    assert not [item for item in draft["operations"] if item["type"] == "add_keyframe"]
    reasons = " ".join(draft["warnings"])
    assert "movement_path" in reasons
    assert "推近" in reasons and "运镜模板" in reasons  # 指路到既有能力，而不是只说"不支持"
    assert "宴会厅" in reasons
    assert {"movement_path", "camera_motion", "location"} <= _fields(draft)


def test_movement_path_coordinates_become_position_keyframes():
    panel = _panel(movement_path=[[0, 0, 0], [2.5, 0, -1.0]])
    draft = build_previs_draft({}, panel)
    keys = [item for item in draft["operations"] if item["type"] == "add_keyframe"]
    assert [item["payload"]["property"] for item in keys] == ["position", "position"]
    assert [item["payload"]["frame"] for item in keys] == [0, 96]
    hero_id = _nodes(draft, "human_proxy")[0]["id"]
    assert {item["targetId"] for item in keys} == {hero_id}, "关键帧要挂在同批新建的那个人身上"
    # 坐标是相对该角色站位的偏移
    assert keys[0]["payload"]["value"][0] == pytest.approx(-0.8 + 0.0, abs=1e-3)
    assert keys[1]["payload"]["value"][0] == pytest.approx(-0.8 + 2.5, abs=1e-3)


def test_load_storyboard_panel_only_accepts_storyboard_content():
    content = ProjectContent(id="c1", project_id="p1", content_type="storyboard",
                             data_json='{"panels": [{"panel_number": 2}]}')
    assert load_storyboard_panel(content, 2) == {"panel_number": 2}
    assert load_storyboard_panel(content, 9) is None
    other = ProjectContent(id="c2", project_id="p1", content_type="script", data_json="{}")
    assert load_storyboard_panel(other, 1) is None
    assert load_storyboard_panel(None, 1) is None


def test_action_text_translates_into_poses_and_motions():
    """分镜的 `action` 必须落到姿势/动作上——"端着托盘"摆成站立，等于没看分镜。"""
    # 端托盘：动作库里没有 → 用自定义关节角度（双臂前抬屈肘），且要能过受限校验
    tray = build_previs_draft({}, _panel(action="萧然端着托盘走过"))
    tray_node = _nodes(tray, "human_proxy")[0]
    joints = tray_node["metadata"].get("poseJoints")
    assert joints and joints["leftElbow"] == -78 and joints["rightElbow"] == -78
    assert tray_node["metadata"]["pose"] == "stand"
    accepted, rejected = ops.validate_operations({}, tray["operations"], expected_revision=1, current_revision=1)
    assert rejected == []

    # 动作库里有的走 assign_motion（会动），而不是摆一个静态姿势
    wave = build_previs_draft({}, _panel(characters=["苏棠"], action="苏棠挥手"))
    motions = [item for item in wave["operations"] if item["type"] == "assign_motion"]
    assert motions[0]["payload"]["motion"] == "motion:wave"
    assert motions[0]["targetId"] == "draft-p3-hero-1"

    # 名字出现在动作里的人才有姿势；没出现的保持站立并记为默认
    two = build_previs_draft({}, _panel(action="萧然端着托盘，苏棠站在旁边"))
    poses = {item["payload"]["node"]["name"]: item["payload"]["node"]["metadata"] for item in two["operations"] if item["type"] == "add_node"}
    assert "poseJoints" in poses["萧然"]
    assert "poseJoints" not in poses["苏棠"]
    assert "action:苏棠" in _fields(two)


# ---------------------------------------------------------------- C. 可执行性

def test_every_draft_operation_passes_validation_and_applies():
    """初稿必须是**可执行**的：产出的每一条操作都要能过受限操作校验并落库。

    这条测试挡住最致命的一类问题——初稿看起来热闹，却一条都落不了库
    （例如给同批新建的节点打关键帧时目标还不存在、或动作引用拼错）。
    """
    scene = {"fps": 24, "durationFrames": 96, "nodes": [], "cameras": [], "keyframes": []}
    panel = _panel(movement_path=[[0, 0, 0], [1.5, 0, 0.5]], props=["长桌"])
    draft = build_previs_draft(
        scene, panel,
        prop_assets={"长桌": {"asset_id": "asset-9", "name": "长桌模型", "model_url": "/m.glb"}},
    )

    accepted, rejected = ops.validate_operations(
        scene, draft["operations"], expected_revision=1, current_revision=1,
        motion_carriers={},
    )
    assert rejected == [], rejected
    next_scene, applied = ops.apply_operations(scene, accepted)

    assert len(applied) == len(draft["operations"])
    assert len([node for node in next_scene["nodes"] if node["kind"] == "human_proxy"]) == 2
    assert len([node for node in next_scene["nodes"] if node["kind"] == "asset_model"]) == 1
    assert len(next_scene["cameras"]) == 1
    assert next_scene["activeCameraId"] == "draft-p3-camera", "新建机位应成为活动机位（截图与导出依赖它）"
    assert next_scene["durationFrames"] == 96
    assert len(next_scene["keyframes"]) == 2
    # 落库后的场景仍然自洽：机位的焦距与 fov 互相能推出来
    camera = next_scene["cameras"][0]
    assert camera["focalLength"] == 35
    assert camera["fov"] == pytest.approx(54.43, abs=0.05)


def test_draft_does_not_mutate_its_inputs():
    scene = {"fps": 24, "nodes": [], "cameras": [], "keyframes": []}
    panel = _panel()
    import copy

    scene_before, panel_before = copy.deepcopy(scene), copy.deepcopy(panel)
    build_previs_draft(scene, panel)
    assert scene == scene_before
    assert panel == panel_before


# ---------------------------------------------------------------- D. 接口

@pytest.fixture()
def draft_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'draft.db'}")
    PrevisSceneDocument.__table__.create(engine)
    ProjectContent.__table__.create(engine)
    # 初稿管线会读动作清单做自检（草案里的 `assign_motion` 要判断"动作是否存在、载体是否匹配"），
    # 因此这张表也得建：不建的话是**夹具缺陷**（管线抛 no such table），不是产品代码的问题。
    PrevisMotionAsset.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)
    # 两处都要钉：接口层自己（其它端点）与初稿管线所在的 `draft_service`
    # （接口与 Agent 工具共用那条管线，所以会话工厂在服务模块里）
    monkeypatch.setattr(previs_api, "SessionLocal", factory)
    monkeypatch.setattr(draft_service, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def draft_client(draft_session_factory):
    app = FastAPI()
    app.include_router(previs_api.router, prefix="/api/v1/previs")
    return TestClient(app)


def _insert_bound_scene(factory, *, content_id: str = "content-1", panel_number: int = 1, scene: dict | None = None) -> str:
    with factory() as session:
        session.add(ProjectContent(
            id=content_id,
            project_id="project-1",
            content_type="storyboard",
            data_json='{"panels": [{"panel_number": %d, "characters": ["萧然"], "shot_size": "特写", '
                      '"camera_angle": "平视", "duration_seconds": 3}]}' % panel_number,
        ))
        row = PrevisSceneDocument(
            id="scene-1",
            project_id="project-1",
            storyboard_content_id=content_id,
            panel_number=panel_number,
            title="第 1 镜预演",
            scene_json=scene if scene is not None else {"fps": 24, "nodes": [], "cameras": [], "keyframes": []},
            revision=1,
        )
        session.add(row)
        session.commit()
    return "scene-1"


def test_draft_endpoint_returns_operations_without_writing(draft_client, draft_session_factory):
    scene_id = _insert_bound_scene(draft_session_factory)
    with draft_session_factory() as session:
        before = session.get(PrevisSceneDocument, scene_id)
        before_revision, before_updated, before_json = before.revision, before.updated_at, dict(before.scene_json)

    response = draft_client.post(f"/api/v1/previs/scenes/{scene_id}/draft")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["read_only"] is True
    assert body["panel_number"] == 1
    assert body["operations"] and body["summary"]["shot_size"] == "特写"
    assert body["summary"]["duration_frames"] == 72  # 特写 3 秒 × 24fps
    for key in ("defaults", "warnings"):
        assert key in body

    # 幽灵预览要渲染"落库后会变成什么样"，所以接口顺带把草案应用一遍返回 proposed_scene——
    # 客户端不再实现一份应用逻辑（两份实现必然漂移）
    assert body["rejected"] == []
    assert body["scene_revision"] == 1
    proposed = body["proposed_scene"]
    assert len(proposed["nodes"]) == 1 and proposed["nodes"][0]["kind"] == "human_proxy"
    assert len(proposed["cameras"]) == 1
    assert proposed["durationFrames"] == 72

    # 只读：场景一字未动（初稿要不要落库由"预览 → 人工确认 → CAS 落库"那条链路决定）
    with draft_session_factory() as session:
        after = session.get(PrevisSceneDocument, scene_id)
        assert after.revision == before_revision
        assert after.updated_at == before_updated
        assert dict(after.scene_json) == before_json


def test_draft_endpoint_rejects_scenes_without_a_bound_panel(draft_client, draft_session_factory):
    with draft_session_factory() as session:
        session.add(ProjectContent(id="content-1", project_id="project-1", content_type="storyboard",
                                   data_json='{"panels": []}'))
        session.add(PrevisSceneDocument(id="scene-free", title="独立场景",
                                       scene_json={"fps": 24, "nodes": [], "cameras": [], "keyframes": []},
                                       revision=1))
        session.commit()
    response = draft_client.post("/api/v1/previs/scenes/scene-free/draft")
    assert response.status_code == 400
    assert "未绑定项目分镜面板" in response.json()["detail"]


def test_draft_endpoint_reports_a_missing_panel(draft_client, draft_session_factory):
    scene_id = _insert_bound_scene(draft_session_factory, panel_number=1)
    with draft_session_factory() as session:
        content = session.get(ProjectContent, "content-1")
        content.data_json = '{"panels": [{"panel_number": 5}]}'
        session.add(content)
        session.commit()
    response = draft_client.post(f"/api/v1/previs/scenes/{scene_id}/draft")
    assert response.status_code == 404
    assert "第 1 格" in response.json()["detail"]


def test_draft_endpoint_404_for_unknown_scene(draft_client):
    response = draft_client.post("/api/v1/previs/scenes/nope/draft")
    assert response.status_code == 404
