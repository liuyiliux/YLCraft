"""预演动作资产：逐帧求值、种子数据的生理约束、清单接口契约。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import previs as previs_api
from app.db.models.previs import PrevisMotionAsset
from app.services.previs.motion import (
    HUMAN_PARAM_CHANNELS,
    HUMAN_PARAM_LIMITS,
    TRANSFORM_CHANNELS,
    channel_limit_reason,
    pose_field_reasons,
    recommended_speed_mps,
    resolve_frame,
    sample_channel,
    sample_channels,
    violates_sign_rule,
)
from app.services.previs.motion_seed import assert_channels_known, seed_motion_specs
from app.services.previs.motion_service import seed_default_motions


@pytest.fixture()
def motion_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'motions.db'}")
    PrevisMotionAsset.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(previs_api, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def seeded_factory(motion_session_factory):
    with motion_session_factory() as session:
        seed_default_motions(session)
    return motion_session_factory


@pytest.fixture()
def motion_client(seeded_factory):
    app = FastAPI()
    app.include_router(previs_api.router, prefix="/api/v1/previs")
    return TestClient(app)


class TestFrameResolution:
    def test_negative_frame_clamps_to_zero(self):
        assert resolve_frame(-5, frame_count=24, loopable=True) == 0

    def test_non_loopable_holds_last_frame(self):
        # 一次性的动作（坐下 / 指向）停在结束姿态才合理，不能回到起点
        assert resolve_frame(999, frame_count=36, loopable=False) == 36
        assert resolve_frame(36, frame_count=36, loopable=False) == 36

    def test_loopable_wraps(self):
        assert resolve_frame(24, frame_count=24, loopable=True) == 0
        assert resolve_frame(25, frame_count=24, loopable=True) == 1
        assert resolve_frame(23, frame_count=24, loopable=True) == 23

    def test_zero_frame_count_is_passthrough(self):
        assert resolve_frame(7, frame_count=0, loopable=True) == 7


class TestChannelSampling:
    def test_hold_before_first_and_after_last(self):
        keys = [[0, 10], [10, 20]]
        assert sample_channel(keys, -3) == 10
        assert sample_channel(keys, 99) == 20

    def test_midpoint_interpolates_linearly(self):
        assert sample_channel([[0, 0], [10, 20]], 5) == 10

    def test_single_key_is_constant(self):
        assert sample_channel([[4, 7]], 0) == 7
        assert sample_channel([[4, 7]], 100) == 7

    def test_unsorted_keys_are_sorted(self):
        assert sample_channel([[10, 20], [0, 0]], 5) == 10

    def test_malformed_entries_are_dropped_individually(self):
        keys = [[0, 0], "bad", [3], [10, 20], [5, "x"]]
        assert sample_channel(keys, 10) == 20

    def test_booleans_are_rejected(self):
        # Python 里 True 是 int 的实例：不挡的话 True 会静默变成第 1 帧的 1.0
        assert sample_channel([[True, 1]], 1) is None
        assert sample_channel([[0, True]], 1) is None

    def test_no_usable_key_returns_none(self):
        assert sample_channel([], 0) is None
        assert sample_channel("nope", 0) is None


class TestMotionSampling:
    def test_absent_channels_are_omitted_not_zeroed(self):
        payload = {"channels": {"leftElbow": [[0, -10]]}}
        sampled = sample_channels(payload, 0, frame_count=10, loopable=False)
        # 关键：没描述腿就不许把腿填成 0——否则一条只动手臂的动作会把腿拉直
        assert sampled == {"leftElbow": -10}

    def test_bad_payload_yields_empty(self):
        assert sample_channels(None, 0, frame_count=10, loopable=False) == {}
        assert sample_channels({"channels": []}, 0, frame_count=10, loopable=False) == {}

    def test_loopable_sampling_wraps(self):
        payload = {"channels": {"position.0": [[0, 0], [24, 2]]}}
        assert sample_channels(payload, 24, frame_count=24, loopable=True)["position.0"] == 0
        assert sample_channels(payload, 12, frame_count=24, loopable=True)["position.0"] == 1


class TestSeedData:
    def test_all_specs_use_known_channels(self):
        for spec in seed_motion_specs():
            assert_channels_known(spec)

    def test_unknown_channel_is_rejected(self):
        spec = {"slug": "bad", "carrier": "params", "payload": {"channels": {"leftTail": [[0, 1]]}}}
        with pytest.raises(ValueError):
            assert_channels_known(spec)

    def test_params_and_transform_use_their_own_channel_vocabulary(self):
        for spec in seed_motion_specs():
            channels = set(spec["payload"]["channels"])
            allowed = HUMAN_PARAM_CHANNELS if spec["carrier"] == "params" else TRANSFORM_CHANNELS
            assert channels <= set(allowed)
            assert channels, spec["slug"]

    def test_frame_count_matches_duration_and_fps(self):
        for spec in seed_motion_specs():
            assert spec["frame_count"] == round(spec["duration_seconds"] * spec["fps"]), spec["slug"]

    def test_loopable_motions_start_and_end_equal(self):
        """循环回绕不能跳变：首尾不同值会让角色在回绕的那一帧抽一下。"""
        for spec in seed_motion_specs():
            if not spec["loopable"]:
                continue
            frame_count = spec["frame_count"]
            first = sample_channels(spec["payload"], 0, frame_count=frame_count, loopable=True)
            last = sample_channels(spec["payload"], frame_count, frame_count=frame_count, loopable=True)
            for channel, value in first.items():
                assert abs(value - last[channel]) < 1e-6, f"{spec['slug']}.{channel} 首尾不等"

    def test_sign_rules_hold_for_every_sampled_frame(self):
        """肘不能反折、膝不能反折——参数级就挡住，不必等渲染出来才发现。"""
        for spec in seed_motion_specs():
            if spec["carrier"] != "params":
                continue
            for frame in range(spec["frame_count"] + 1):
                sampled = sample_channels(
                    spec["payload"], frame, frame_count=spec["frame_count"], loopable=spec["loopable"]
                )
                for channel, value in sampled.items():
                    assert not violates_sign_rule(channel, value), f"{spec['slug']}.{channel}@{frame} = {value}"

    def test_walk_speed_matches_a_human_pace(self):
        walk = next(spec for spec in seed_motion_specs() if spec["slug"] == "walk")
        speed = recommended_speed_mps(walk["payload"], walk["duration_seconds"])
        # 0.65m 步幅 × 2 步 ÷ 1 秒 = 1.3 m/s，真人常速 1.2–1.4
        assert speed == pytest.approx(1.3)

    def test_speed_needs_both_stride_and_duration(self):
        assert recommended_speed_mps({"stride_meters": 0.65}, 0) is None
        assert recommended_speed_mps({"channels": {}}, 1.0) is None
        assert recommended_speed_mps({"stride_meters": 0.65, "steps_per_cycle": 0}, 1.0) is None


class TestChannelLimits:
    """通道限位（`HUMAN_PARAM_LIMITS`）的覆盖与拒绝原因。

    为什么单独一组：限位表与前端 `HumanProxyLimits` 是两份实现，最容易出的错是
    **新增了一个通道却忘了给它加限位**——表现是该通道静默不受校验，而不会报任何错。
    """

    def test_every_channel_has_a_limit(self):
        for channel in HUMAN_PARAM_CHANNELS:
            assert channel in HUMAN_PARAM_LIMITS, f"{channel} 缺限位"
            low, high = HUMAN_PARAM_LIMITS[channel]
            assert low < high, channel

    def test_sign_violation_names_the_physiological_rule(self):
        # 肘向前屈、膝向后收：越界方向**就是**反折方向，原因要点名规则
        assert "生理约束" in (channel_limit_reason("leftElbow", 40) or "")
        assert "生理约束" in (channel_limit_reason("rightKnee", -20) or "")

    def test_far_out_of_range_reports_the_range_not_the_rule(self):
        # 膝的上限是 140：说成"反折"会把人引到错误方向（它离 0 很远）
        assert "超出范围" in (channel_limit_reason("leftKnee", 999) or "")

    def test_accepts_legal_values_and_rejects_nonsense(self):
        assert channel_limit_reason("torso.0", 30) is None
        assert channel_limit_reason("bodyOffsetY", -0.165) is None
        assert "未知的姿势通道" in (channel_limit_reason("leftTail.0", 1) or "")
        assert channel_limit_reason("leftKnee", "20")
        # 布尔值不当 1.0（与 `_clean_keys` 同一条理由：Python 里 True 是 int 的实例）
        assert channel_limit_reason("leftKnee", True)

    def test_field_shaped_pose_uses_field_names_not_channels(self):
        """`poseJoints` 是**按字段**的（前端形状）：拿字段名当通道名校验会连正常姿势都拒。"""
        reasons = pose_field_reasons({"leftShoulder": [-55, 0, 6], "leftElbow": -78})
        assert reasons == [], reasons
        assert len(pose_field_reasons({"leftShoulder": [999, 0, 0]})) == 1
        assert "未知的姿势字段" in (pose_field_reasons({"leftTail": 1})[0] or "")
        # 三元组字段缺轴也要报出来，而不是静默放行
        assert any("三个数值" in reason for reason in pose_field_reasons({"torso": [10]}))


class TestSeeding:
    def test_seed_is_idempotent(self, motion_session_factory):
        specs = seed_motion_specs()
        with motion_session_factory() as session:
            first = seed_default_motions(session)
        with motion_session_factory() as session:
            second = seed_default_motions(session)
        assert first == {"created": len(specs), "updated": 0}
        assert second == {"created": 0, "updated": len(specs)}

    def test_seed_keeps_stable_ids(self, motion_session_factory):
        """场景里存的是动作引用：重灌种子不能让引用失效。"""
        with motion_session_factory() as session:
            seed_default_motions(session)
        with motion_session_factory() as session:
            seed_default_motions(session)
            walk = session.get(PrevisMotionAsset, "motion-walk")
            assert walk is not None
            assert walk.slug == "walk"


class TestMotionApi:
    def test_lists_all_seeds(self, motion_client):
        response = motion_client.get("/api/v1/previs/motions")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["total"] == len(seed_motion_specs())
        slugs = {item["slug"] for item in body["motions"]}
        assert {"idle", "walk", "run", "wave", "sit", "point"} <= slugs

    def test_payload_is_hidden_by_default(self, motion_client):
        default = motion_client.get("/api/v1/previs/motions").json()["motions"]
        assert all("payload" not in item for item in default)
        # 但通道清单要给出来，否则调用方无法判断这条动作驱动了哪些通道
        walk = next(item for item in default if item["slug"] == "walk")
        assert "leftKnee" in walk["channels"]

        with_payload = motion_client.get(
            "/api/v1/previs/motions", params={"include_payload": "true"}
        ).json()["motions"]
        assert all("payload" in item for item in with_payload)

    def test_filter_by_carrier(self, motion_client):
        params_only = motion_client.get("/api/v1/previs/motions", params={"carrier": "params"}).json()
        transform_only = motion_client.get("/api/v1/previs/motions", params={"carrier": "transform"}).json()
        assert all(item["carrier"] == "params" for item in params_only["motions"])
        assert all(item["carrier"] == "transform" for item in transform_only["motions"])
        assert params_only["total"] + transform_only["total"] == len(seed_motion_specs())

    def test_generic_transform_motion_is_offered_for_rigless_objects(self, motion_client):
        body = motion_client.get("/api/v1/previs/motions", params={"tag": "位移"}).json()
        slugs = {item["slug"] for item in body["motions"]}
        assert "move-forward-2m" in slugs

    def test_filter_by_tag_without_match_returns_empty(self, motion_client):
        body = motion_client.get("/api/v1/previs/motions", params={"tag": "不存在的标签"}).json()
        assert body == {"success": True, "motions": [], "total": 0}

    def test_recorded_license_is_reported(self, motion_client):
        item = motion_client.get("/api/v1/previs/motions").json()["motions"][0]
        assert item["license_status"] == "recorded"
        assert item["origin"]

    def test_missing_license_is_reported_as_unverified(self, motion_client, seeded_factory):
        with seeded_factory() as session:
            session.add(
                PrevisMotionAsset(id="motion-third-party", slug="third-party", name="外部动作", carrier="params")
            )
            session.commit()
        body = motion_client.get("/api/v1/previs/motions", params={"carrier": "params"}).json()
        item = next(entry for entry in body["motions"] if entry["slug"] == "third-party")
        # 未记录许可 ≠ 不能商用，但绝不能显示成"已授权"
        assert item["license_status"] == "unverified"
        assert item["license"] is None
