from __future__ import annotations

from app.api.v1 import logs as logs_api
from app.api.v1.logs import _parse_runtime_line


def test_runtime_log_parser_exposes_filterable_module_name():
    line = _parse_runtime_line(
        "2026-08-23 18:12:43,702 INFO ylcraft.ai.service: provider request completed"
    )

    assert line.level == "INFO"
    assert line.name == "ylcraft.ai.service"
    assert line.module_key == "ai_text"
    assert line.module == "AI文本"
    assert line.message == "provider request completed"


def test_runtime_log_parser_keeps_external_logger_as_module():
    line = _parse_runtime_line("2026-08-23 18:12:48,611 INFO httpx: HTTP Request: 200 OK")

    assert line.module_key == "http"
    assert line.module == "外部接口"


def test_runtime_log_parser_does_not_treat_template_json_as_logger():
    line = logs_api._parse_runtime_line('  "prompt": "{{ prompt }}",')
    assert line.module_key == "system"
    assert line.module == "系统"


def test_runtime_log_parser_covers_architecture_modules():
    cases = {
        "2026-08-23 18:12:48,611 INFO ylcraft.live2d: step completed": "Live2D工厂",
        "2026-08-23 18:12:48,611 INFO ylcraft.download: file saved": "下载中心",
        "2026-08-23 18:12:48,611 INFO ylcraft.creator_data: report loaded": "创作者数据中心",
        "2026-08-23 18:12:48,611 INFO ylcraft.cutclaw: task done": "AI剪辑",
        "2026-08-23 18:12:48,611 INFO ylcraft.asset_hub: asset linked": "素材库-资产中枢",
    }
    for raw, label in cases.items():
        assert _parse_runtime_line(raw).module == label
