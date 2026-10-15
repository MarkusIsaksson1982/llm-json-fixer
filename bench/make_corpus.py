"""Benchmark corpus of broken LLM JSON outputs. Each case: id, cat, input, expect (list of acceptable parsed values;
None-list means 'must not invent JSON'), optional schema (for schema-guided coerce/validate cases)."""
import json
C = []
def add(cat, inp, *expect, schema=None, id=None, valid=None):
    C.append({"id": id or f"{cat}-{sum(1 for c in C if c['cat']==cat)+1}", "cat": cat, "input": inp,
              "expect": list(expect) if expect != (None,) else None, "schema": schema, "valid": valid})
P = {"name": "Ada", "age": 36, "tags": ["x", "y"]}
# fences / prose
add("fence", '```json\n{"name": "Ada", "age": 36, "tags": ["x", "y"]}\n```', P)
add("fence", '```\n{"a": 1}\n```', {"a": 1})
add("fence", 'Here is the JSON:\n```json\n{"ok": true}\n```\nLet me know if you need more!', {"ok": True})
add("prose", 'Sure! The result is {"city": "Uppsala", "temp": 9.5} as requested.', {"city": "Uppsala", "temp": 9.5})
add("prose", 'Answer:\n[1, 2, 3]\nThat is all.', [1, 2, 3])
add("prose", 'I think {"x": 1} is the answer, not {"x": 2}.', {"x": 1}, [{"x": 1}, {"x": 2}])
add("prose", 'Output: {"msg": "use {braces} carefully"} done', {"msg": "use {braces} carefully"})
# trailing commas
add("trailing_comma", '{"a": 1, "b": 2,}', {"a": 1, "b": 2})
add("trailing_comma", '[1, 2, 3,]', [1, 2, 3])
add("trailing_comma", '{"a": [1, 2,], "b": {"c": 3,},}', {"a": [1, 2], "b": {"c": 3}})
# quotes
add("single_quotes", "{'name': 'Ada', 'age': 36}", {"name": "Ada", "age": 36})
add("single_quotes", "{'msg': \"it's fine\"}", {"msg": "it's fine"})
add("single_quotes", "['a', 'b', 'c']", ["a", "b", "c"])
add("unquoted_keys", '{name: "Ada", age: 36}', {"name": "Ada", "age": 36})
add("unquoted_keys", '{user_id: 7, is_admin: false}', {"user_id": 7, "is_admin": False})
add("smart_quotes", '{\u201cname\u201d: \u201cAda\u201d}', {"name": "Ada"})
# comments
add("comments", '{\n  // the user\n  "name": "Ada" /* inline */, "age": 36\n}', {"name": "Ada", "age": 36})
add("comments", '{"a": 1, # python-style\n "b": 2}', {"a": 1, "b": 2})
add("comments", '{"url": "http://example.com/a//b"}', {"url": "http://example.com/a//b"})
# python literals / special numbers
add("python_literals", '{"a": True, "b": False, "c": None}', {"a": True, "b": False, "c": None})
add("python_literals", "{'ok': True, 'items': ('a', 'b')}", {"ok": True, "items": ["a", "b"]})
add("python_literals", '{"text": "True story, None of it"}', {"text": "True story, None of it"})
add("special_numbers", '{"a": NaN, "b": Infinity, "c": -Infinity}', {"a": None, "b": None, "c": None})
add("special_numbers", '{"a": undefined, "b": 1}', {"a": None, "b": 1}, {"b": 1})
add("special_numbers", '{"n": 007, "h": 0x1F, "p": +5, "d": .5}', {"n": 7, "h": 31, "p": 5, "d": 0.5}, {"n": 7, "h": "0x1F", "p": 5, "d": 0.5})
# missing commas / colons / brackets
add("missing_comma", '{"a": 1 "b": 2}', {"a": 1, "b": 2})
add("missing_comma", '[1 2 3]', [1, 2, 3])
add("missing_comma", '{"a": "x"\n "b": "y"}', {"a": "x", "b": "y"})
add("mismatched", '{"a": [1, 2}', {"a": [1, 2]})
add("mismatched", '{"a": {"b": 1]}', {"a": {"b": 1}})
# truncation
add("truncated", '{"name": "Ada", "age": 36, "tags": ["x", "y"', P)
add("truncated", '{"name": "Ada", "bio": "Mathematician and wri', {"name": "Ada", "bio": "Mathematician and wri"}, {"name": "Ada"})
add("truncated", '[{"id": 1}, {"id": 2}, {"id"', [{"id": 1}, {"id": 2}, {"id": None}], [{"id": 1}, {"id": 2}, {}], [{"id": 1}, {"id": 2}])
add("truncated", '{"a": {"b": {"c": [1, 2, 3', {"a": {"b": {"c": [1, 2, 3]}}})
add("truncated", '{"ok": tr', {"ok": True}, {}, {"ok": None})
add("truncated", '{"items": [{"n": "a", "v": 1}, {"n": "b", "v": 2}, {"n": "c", "v":', {"items": [{"n": "a", "v": 1}, {"n": "b", "v": 2}, {"n": "c", "v": None}]}, {"items": [{"n": "a", "v": 1}, {"n": "b", "v": 2}, {"n": "c"}]}, {"items": [{"n": "a", "v": 1}, {"n": "b", "v": 2}]})
# string escapes / newlines / unicode
add("escapes", '{"text": "line1\nline2"}', {"text": "line1\nline2"})
add("escapes", '{"path": "C:\\Users\\ada"}', {"path": "C:\\Users\\ada"})
add("escapes", '{"q": "she said "hi" to me"}', {"q": 'she said "hi" to me'})
add("escapes", '{"tab": "a\tb"}', {"tab": "a\tb"})
add("nested_escaping", '{"payload": "{\\"inner\\": 1}"}', {"payload": '{"inner": 1}'})
add("nested_escaping", '"{\\"a\\": 1, \\"b\\": [2, 3]}"', {"a": 1, "b": [2, 3]}, '{"a": 1, "b": [2, 3]}')
add("unicode", '{"name": "Åsa Öberg", "city": "Malmö", "emoji": "🙂"}', {"name": "Åsa Öberg", "city": "Malmö", "emoji": "🙂"})
add("unicode", '{"jp": "\\u65e5\\u672c", "raw": "日本"}', {"jp": "日本", "raw": "日本"})
add("unicode", '\ufeff{"bom": true}', {"bom": True})
# concatenated / multiple
add("concatenated", '{"a": 1}{"b": 2}', [{"a": 1}, {"b": 2}], {"a": 1}, {"a": 1, "b": 2})
add("concatenated", '{"a": 1}\n{"a": 2}\n{"a": 3}', [{"a": 1}, {"a": 2}, {"a": 3}], {"a": 1})
# already valid (must be unchanged)
add("valid", '{"a": 1, "b": [true, null, "x"], "c": {"d": 1.5e3}}', {"a": 1, "b": [True, None, "x"], "c": {"d": 1500.0}})
add("valid", '[]', [])
add("valid", '"just a string"', "just a string")
add("valid", '{"key with spaces": "v", "": 0}', {"key with spaces": "v", "": 0})
add("valid", '{"big": 12345678901234567890, "neg": -0.0}', {"big": 12345678901234567890, "neg": -0.0})
# combos (typical LLM mess)
add("combo", "```json\n{\n  name: 'Ada', // who\n  active: True,\n  scores: [1, 2, 3,],\n}\n```", {"name": "Ada", "active": True, "scores": [1, 2, 3]})
add("combo", "Sure, here you go:\n{'results': [{'id': 1, 'ok': True}, {'id': 2, 'ok': False},], 'next': None}\nHope this helps.", {"results": [{"id": 1, "ok": True}, {"id": 2, "ok": False}], "next": None})
add("combo", '```json\n{"summary": "Mixed "quotes" and\nnewlines", "n": 3,}\n```', {"summary": 'Mixed "quotes" and\nnewlines', "n": 3})
add("combo", '{"tool": "search", "args": {"query": "MCP servers", "limit": 5', {"tool": "search", "args": {"query": "MCP servers", "limit": 5}})
# huge
big = {"rows": [{"id": i, "name": f"item {i}", "vals": [i, i * 2, i * 3], "ok": i % 2 == 0} for i in range(3000)]}
s = json.dumps(big); add("huge", "```json\n" + s[:-2] + ",]}\n```", big, id="huge-1")   # ~190 KB with trailing comma + fence
deep = "[" * 500 + "]" * 500; add("huge", deep, json.loads(deep), id="huge-deep")
# must not invent data
add("no_json", "I'm sorry, I can't help with that request.", None)
add("no_json", "", None)
add("no_json", "The answer is yes.", None, ["yes"], "yes")
# schema-guided coerce (repair + coerce to schema)
S1 = {"type": "object", "properties": {"age": {"type": "integer"}, "active": {"type": "boolean"}, "score": {"type": "number"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["age", "active"]}
add("schema_coerce", '{"age": "41", "active": "true", "score": "3.5", "tags": "solo"}', {"age": 41, "active": True, "score": 3.5, "tags": ["solo"]}, schema=S1)
add("schema_coerce", "{'age': 41.0, 'active': 'yes', 'tags': ['a', 'b'],}", {"age": 41, "active": True, "tags": ["a", "b"]}, schema=S1)
add("schema_coerce", '```json\n{"age": "41 years", "active": 1}\n```', {"age": 41, "active": True}, schema=S1)
S2 = {"type": "object", "properties": {"status": {"type": "string", "enum": ["open", "closed"]}, "count": {"type": "integer"}}, "required": ["status", "count"], "additionalProperties": False}
add("schema_coerce", '{"status": "Open", "count": "3", "extra": 1}', {"status": "open", "count": 3}, {"status": "open", "count": 3, "extra": 1}, schema=S2)
add("schema_coerce", '{"status": "closed", "count": 2}', {"status": "closed", "count": 2}, schema=S2)
# schema validation verdicts (valid = expected verdict)
add("schema_validate", '{"status": "open", "count": 2}', {"status": "open", "count": 2}, schema=S2, valid=True)
add("schema_validate", '{"status": "pending", "count": 2}', {"status": "pending", "count": 2}, schema=S2, valid=False)
add("schema_validate", '{"status": "open"}', {"status": "open"}, schema=S2, valid=False)
add("schema_validate", '{"age": 3, "active": true, "tags": [1]}', {"age": 3, "active": True, "tags": [1]}, schema=S1, valid=False)
add("schema_validate", '{"age": 3, "active": false}', {"age": 3, "active": False}, schema=S1, valid=True)
json.dump(C, open("corpus.json", "w"), ensure_ascii=False)
from collections import Counter; print(len(C), Counter(c["cat"] for c in C))
