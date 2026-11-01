"""可用模型列表与默认模型保持一致（2026-10-31 Agnes Video 2.0 下线事故的回归测试）。

事故：只把连接器的「默认模型」改成 agnes-video-2.5-flash，available_models 里还留着
["agnes-video-v2.0"]；视频工作台用 available_models[0] 当默认值，于是页面继续显示
并真正发送 agnes-video-v2.0，供应商返回 model_not_found。
"""

from app.services.ai_connector.service import sync_default_model_into_available_models


def test_stale_model_is_pushed_behind_the_new_default():
    assert sync_default_model_into_available_models(
        ["agnes-video-v2.0"], "agnes-video-2.5-flash"
    ) == ["agnes-video-2.5-flash", "agnes-video-v2.0"]


def test_existing_entry_is_moved_to_the_front_without_duplicating():
    assert sync_default_model_into_available_models(["a", "b", "c"], "b") == ["b", "a", "c"]


def test_list_already_led_by_the_default_model_is_untouched():
    assert sync_default_model_into_available_models(["m", "n"], "m") == ["m", "n"]


def test_empty_inputs_are_returned_unchanged():
    assert sync_default_model_into_available_models([], "m") == []
    # 没有默认模型时保持原列表，不做任何推断。
    assert sync_default_model_into_available_models(["a"], "") == ["a"]


def test_blank_entries_do_not_break_ordering():
    assert sync_default_model_into_available_models(["", "a", "  "], "a") == ["a"]
