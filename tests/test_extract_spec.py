from llm_json_fixer import extract as m
def T(text): return [text[s:e] for s, e, _ in m.find_spans(text)]
def test_fences():
    assert m.strip_fences('x\n```json\n{"a": 1}\n```\ny').strip() == '{"a": 1}'
    assert m.strip_fences('```\n[1]\n```').strip() == "[1]"
    assert m.strip_fences('```python\nprint(1)\n```\n```json\n{"b": 2}\n```').strip() == '{"b": 2}'
    assert m.strip_fences('```json\n{"a": 1,').strip() == '{"a": 1,'
    assert m.strip_fences('no fences {"a": 1}') is None
def test_spans_basic():
    assert T('Sure! {"a": 1} ok') == ['{"a": 1}']
    assert T('I think {"x": 1} is it, not {"x": 2}.') == ['{"x": 1}', '{"x": 2}']
    assert T('Answer:\n[1, 2, 3]\nThat is all.') == ['[1, 2, 3]']
def test_strings_and_apostrophes():
    assert T('Output: {"msg": "use {braces} carefully"} done') == ['{"msg": "use {braces} carefully"}']
    assert T("I'm sure: {'a': 'it}s'} don't") == ["{'a': 'it}s'}"]
    assert T('{"q": "a \\" } b"}') == ['{"q": "a \\" } b"}']
def test_prose_brackets_skipped():
    assert T('See [citation] and {braces} here: {"a": 1}') == ['{"a": 1}']
def test_comments():
    assert T('{"a": 1, // }\n "b": 2}') == ['{"a": 1, // }\n "b": 2}']
def test_truncated_and_mismatch():
    sp = m.find_spans('x {"a": [1, 2'); assert sp[-1][2] is False and sp[-1][1] == len('x {"a": [1, 2')
    assert T('{"a": [1, 2}') == ['{"a": [1, 2}']
def test_best():
    assert m.best_span("no json here") is None
    t = 'a {"x": 1} b {"y": ['; s, e, c = m.best_span(t); assert t[s:e] == '{"x": 1}' and c
    t = 'only {"y": [1'; s, e, c = m.best_span(t); assert t[s:e] == '{"y": [1' and not c
def test_big_and_deep():
    t = "[" * 2000 + "]" * 2000; assert T(t) == [t]
    t = '{"rows": [' + ",".join('{"i": %d}' % i for i in range(20000)) + "]}"; assert T(t) == [t]
