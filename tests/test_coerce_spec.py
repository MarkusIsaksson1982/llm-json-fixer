import copy
from llm_json_fixer import coerce as m
S = {"type": "object", "properties": {"age": {"type": "integer"}, "active": {"type": "boolean"}, "score": {"type": "number"},
     "tags": {"type": "array", "items": {"type": "string"}}, "status": {"type": "string", "enum": ["open", "closed"]},
     "note": {"type": ["integer", "null"]}, "n": {"type": "string"}}, "required": ["age"], "additionalProperties": False}
def c(v, s=S, **k): return m.coerce(v, s, **k)
def test_basic_types():
    v, ch = c({"age": "41", "active": "yes", "score": "3.5", "tags": "solo", "status": " Open ", "n": 5})
    assert v == {"age": 41, "active": True, "score": 3.5, "tags": ["solo"], "status": "open", "n": "5"}
    paths = {x["path"] for x in ch}; assert {"/age", "/active", "/score", "/tags", "/status", "/n"} <= paths
    assert all(set(x) >= {"path", "from", "to", "rule"} for x in ch)
def test_integral_float_and_leading_number():
    assert c({"age": 41.0})[0] == {"age": 41}
    assert c({"age": "41 years"})[0] == {"age": 41}
    assert c({"age": "3.5"})[0] == {"age": "3.5"}          # not integral: unchanged
    assert c({"age": 3.5})[0] == {"age": 3.5}
def test_bool_from_numbers_and_strings():
    assert c({"age": 1, "active": 1})[0]["active"] is True
    assert c({"age": 1, "active": "FALSE"})[0]["active"] is False
    assert c({"age": 1, "active": "maybe"})[0]["active"] == "maybe"
def test_bool_not_integer():
    v, _ = c({"age": True}); assert v["age"] is True or v["age"] == True and type(v["age"]) is bool
def test_null():
    assert c({"age": 1, "note": "null"})[0]["note"] is None
    assert c({"age": 1, "note": "hello"})[0]["note"] == "hello" and c({"age": 1, "note": "5"})[0]["note"] == 5
def test_drop_additional_and_no_invention():
    v, ch = c({"age": 2, "extra": 1}); assert v == {"age": 2} and any(x["rule"] == "drop_additional" for x in ch)
    v, _ = c({"active": "true"}); assert "age" not in v
    v, _ = c({"age": 2, "extra": 1}, drop_additional=False); assert v == {"age": 2, "extra": 1}
def test_defaults():
    s = {"type": "object", "properties": {"lang": {"type": "string", "default": "sv"}}, "required": ["lang"]}
    assert c({}, s)[0] == {} and c({}, s, fill_defaults=True)[0] == {"lang": "sv"}
def test_no_mutation():
    src = {"age": "41", "tags": "x"}; keep = copy.deepcopy(src); c(src); assert src == keep
def test_refs_and_arrays():
    s = {"type": "array", "items": {"$ref": "#/$defs/p"}, "$defs": {"p": {"type": "object", "properties": {"id": {"type": "integer"}}}}}
    assert c([{"id": "1"}, {"id": 2.0}], s)[0] == [{"id": 1}, {"id": 2}]
    s2 = {"definitions": {"n": {"type": "number"}}, "type": "object", "properties": {"x": {"$ref": "#/definitions/n"}}}
    assert c({"x": "1e3"}, s2)[0] == {"x": 1000.0}
def test_anyof():
    s = {"anyOf": [{"type": "integer"}, {"type": "boolean"}]}
    assert c("7", s)[0] == 7
    assert c("yes", s)[0] is True
def test_never_raises():
    for v in [None, [], {}, "x", 1, {"age": {"deep": [1]}}]:
        c(v); c(v, {}); c(v, {"type": "weird"})
