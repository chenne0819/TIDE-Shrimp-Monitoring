from copy import deepcopy

from app.assistant.providers import _inputs


def test_nested_optional_defaults_become_required_but_nullable_in_provider_schema():
    schema = {"type": "object", "properties": {
        "reply": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        "rows": {"type": "array", "default": [], "items": {"$ref": "#/$defs/Row"}},
    }, "$defs": {"Row": {"type": "object", "properties": {"kind": {"type": "string", "default": "answer"}}}}}
    original = deepcopy(schema)
    strict = _inputs("Question", schema)
    assert schema == original
    assert strict["required"] == ["reply", "rows"]
    assert strict["additionalProperties"] is False
    assert strict["$defs"]["Row"]["required"] == ["kind"]
    assert strict["$defs"]["Row"]["additionalProperties"] is False
    assert "default" not in strict["properties"]["reply"]
    assert strict["properties"]["reply"]["anyOf"][1] == {"type": "null"}
    assert "default" not in strict["$defs"]["Row"]["properties"]["kind"]
