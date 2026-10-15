from llm_json_fixer import jdiff as m
def test_equal(): assert m.diff({"a": [1, 2]}, {"a": [1, 2]}) == [] and m.diff(1, 1.0) == []
def test_replace_add_remove():
    ops = m.diff({"a": 1, "b": 2}, {"a": "1", "c": 3})
    assert {"op": "replace", "path": "/a", "from": 1, "value": "1"} in ops
    assert {"op": "remove", "path": "/b", "from": 2} in ops
    assert {"op": "add", "path": "/c", "value": 3} in ops
def test_bool_vs_number(): assert m.diff({"x": 1}, {"x": True}) == [{"op": "replace", "path": "/x", "from": 1, "value": True}]
def test_escaping(): assert m.diff({}, {"a/b~c": 1}) == [{"op": "add", "path": "/a~1b~0c", "value": 1}]
def test_lists():
    ops = m.diff([1, 2, 3, 4], [1, 9])
    assert ops[0] == {"op": "replace", "path": "/1", "from": 2, "value": 9}
    assert [o["path"] for o in ops if o["op"] == "remove"] == ["/3", "/2"]
def test_root(): assert m.diff([1], {"a": 1}) == [{"op": "replace", "path": "", "from": [1], "value": {"a": 1}}]
def test_roundtrip():
    import random; random.seed(3)
    def rnd(d=0):
        r = random.random()
        if d > 3 or r < .3: return random.choice([1, 2.5, "s", True, None, "x/y"])
        if r < .65: return {random.choice("abcd~/"): rnd(d + 1) for _ in range(random.randint(0, 3))}
        return [rnd(d + 1) for _ in range(random.randint(0, 4))]
    for _ in range(300):
        a, b = rnd(), rnd(); assert m.apply(a, m.diff(a, b)) == b
