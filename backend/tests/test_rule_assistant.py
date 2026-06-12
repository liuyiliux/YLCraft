import json

from app.services.rule_assistant.plugins.book_source import BookSourceRuleRepairPlugin
from app.services.rule_assistant.service import _build_json_repair_messages
from app.services.rule_assistant.types import RuleAssistantContext


def test_book_source_plugin_detects_content_selector_candidates():
    html = """
    <html>
      <head><title>Chapter 2</title></head>
      <body>
        <main>
          <h1>Chapter 2</h1>
          <p>First paragraph.</p>
          <p>Second paragraph.</p>
        </main>
      </body>
    </html>
    """
    plugin = BookSourceRuleRepairPlugin()
    context = RuleAssistantContext(
        domain="book_source",
        rule_type="content",
        rule_format="legado",
        raw_html=html,
    )

    analysis = plugin.analyze(context)
    selectors = {item["selector"] for item in analysis["selector_candidates"]}

    assert "main" in selectors
    assert analysis["page_meta"]["title"] == "Chapter 2"


def test_book_source_plugin_parses_and_validates_legado_patch():
    html = """
    <html><body><main><p>Chapter body.</p></main></body></html>
    """
    plugin = BookSourceRuleRepairPlugin()
    context = RuleAssistantContext(
        domain="book_source",
        rule_type="content",
        rule_format="legado",
        raw_html=html,
    )
    response = json.dumps(
        {
            "summary": "use main",
            "patches": [
                {
                    "target": "rule_content",
                    "format": "legado",
                    "value": {"content": "main"},
                    "reason": "main contains the chapter text",
                    "confidence": 0.9,
                }
            ],
            "test_plan": ["rerun content test"],
        }
    )

    result = plugin.parse_response(response)
    result = plugin.validate_patches(context, result)

    assert result.success is True
    assert result.patches[0].target == "rule_content"
    assert result.patches[0].mode == "merge"
    assert result.patches[0].validation["matched_elements"] == 1


def test_json_repair_messages_include_previous_response_and_schema():
    messages = _build_json_repair_messages("建议把正文选择器改为 main")

    assert messages[0].role == "system"
    assert "strict JSON" in messages[0].content
    assert "建议把正文选择器改为 main" in messages[1].content
    assert '"patches"' in messages[1].content
    assert '"mode"' in messages[1].content
