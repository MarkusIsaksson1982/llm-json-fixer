import asyncio, json
from llm_json_fixer.server import mcp, repair_json, extract_json, validate_json, coerce_to_schema, complete_json, diff_json

TOOLS = ["coerce_to_schema", "complete_json", "diff_json", "extract_json", "repair_json", "validate_json"]


def test_tools_registered():
    tools = asyncio.run(mcp.list_tools())
    assert sorted(t.name for t in tools) == TOOLS
    for t in tools: assert t.input_schema["type"] == "object" and t.description


def test_tool_functions():
    r = repair_json("```json\n{'a': 1,}\n```", include_diff=True)
    assert r["ok"] and r["json"] == {"a": 1} and r["text"] == '{"a":1}'
    s = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert repair_json("{'a': 1}", schema=s, include_diff=True)["diff"] == [{"op": "replace", "path": "/a", "from": 1, "value": "1"}]
    e = extract_json('A {"x": 1} and B {"y": [2,]}', all=True)
    assert e["count"] == 2 and e["values"][1]["json"] == {"y": [2]}
    assert extract_json("no json")["ok"] is False
    v = validate_json({"type": "object", "required": ["a"]}, text="{'b': 1}")
    assert v["valid"] is False and v["errors"][0]["keyword"] == "required" and "repaired" in v
    assert validate_json({"type": "array"}, data=[1])["valid"] is True
    c = coerce_to_schema({"type": "object", "properties": {"n": {"type": "integer"}}}, text='{"n": "5"}')
    assert c["json"] == {"n": 5} and c["valid"] and c["coercions"][0]["path"] == "/n"
    assert complete_json('{"a": [1, {"b": "x')["json"] == {"a": [1, {"b": "x"}]}
    d = diff_json('{"a": 1}', "{'a': 2, 'b': 3}")
    assert d["ok"] and {"op": "add", "path": "/b", "value": 3} in d["ops"]


def test_json_looking_text_args_over_the_protocol():
    from llm_json_fixer.server import mcp
    for name, args in [("coerce_to_schema", {"schema": {"type": "object"}, "text": '{"n": "5"}'}),
                       ("validate_json", {"schema": {"type": "object"}, "text": '{"n": 5}'}),
                       ("repair_json", {"text": '{"n": 5}'})]:
        asyncio.run(mcp.call_tool(name, args))
