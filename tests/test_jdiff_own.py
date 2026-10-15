import copy

import pytest

from llm_json_fixer.jdiff import apply, diff


def test_scalar_equal_no_ops():
    assert diff(1, 1) == []
    assert diff("a", "a") == []
    assert diff(None, None) == []
    assert diff(True, True) == []
    assert diff(False, False) == []


def test_int_float_equal():
    assert diff(1, 1.0) == []
    assert diff(0, 0.0) == []
    assert apply(1, diff(1, 1.0)) == 1.0


def test_bool_vs_number_different():
    ops = diff(True, 1)
    assert len(ops) == 1
    assert ops[0]["op"] == "replace"
    assert ops[0]["path"] == ""
    assert ops[0]["from"] is True
    assert ops[0]["value"] == 1
    assert diff(False, 0) != []
    assert diff(True, True) == []
    assert diff(True, False) != []


def test_replace_scalar():
    ops = diff(1, 2)
    assert ops == [{"op": "replace", "path": "", "from": 1, "value": 2}]
    assert apply(1, ops) == 2


def test_type_change_is_replace():
    ops = diff({"a": 1}, [1])
    assert ops == [{"op": "replace", "path": "", "from": {"a": 1}, "value": [1]}]
    assert diff("x", 1) != []


def test_dict_add_remove_replace_sorted():
    a = {"b": 1, "a": 2, "c": 3}
    b = {"b": 10, "a": 2, "d": 4}
    ops = diff(a, b)
    # sorted keys: a (equal, no op), b (replace), c (remove), d (add)
    assert ops == [
        {"op": "replace", "path": "/b", "from": 1, "value": 10},
        {"op": "remove", "path": "/c", "from": 3},
        {"op": "add", "path": "/d", "value": 4},
    ]
    assert apply(a, ops) == b


def test_nested_dict_recurse():
    a = {"x": {"y": 1}}
    b = {"x": {"y": 2}}
    assert diff(a, b) == [{"op": "replace", "path": "/x/y", "from": 1, "value": 2}]
    assert apply(a, diff(a, b)) == b


def test_list_common_and_tail_add():
    a = [1, 2]
    b = [1, 9, 3, 4]
    ops = diff(a, b)
    assert ops == [
        {"op": "replace", "path": "/1", "from": 2, "value": 9},
        {"op": "add", "path": "/2", "value": 3},
        {"op": "add", "path": "/3", "value": 4},
    ]
    assert apply(a, ops) == b


def test_list_removals_highest_index_down():
    a = [1, 2, 3, 4]
    b = [1]
    ops = diff(a, b)
    assert [o["path"] for o in ops] == ["/3", "/2", "/1"]
    assert all(o["op"] == "remove" for o in ops)
    assert ops[0] == {"op": "remove", "path": "/3", "from": 4}
    assert apply(a, ops) == b


def test_list_nested_bool_vs_number():
    assert diff([True], [1]) == [{"op": "replace", "path": "/0", "from": True, "value": 1}]
    assert diff({"k": [1, True]}, {"k": [1, 1]}) == [
        {"op": "replace", "path": "/k/1", "from": True, "value": 1}
    ]


def test_pointer_escaping():
    a = {"a/b": 1, "c~d": 2}
    b = {"a/b": 10, "c~d": 20}
    ops = diff(a, b)
    assert ops == [
        {"op": "replace", "path": "/a~1b", "from": 1, "value": 10},
        {"op": "replace", "path": "/c~0d", "from": 2, "value": 20},
    ]
    assert apply(a, ops) == b
    # empty key and tricky key
    assert apply({"": 1}, diff({"": 1}, {"": 2})) == {"": 2}
    assert apply({"~1": 1}, diff({"~1": 1}, {"~1": 2})) == {"~1": 2}


def test_root_replace_and_add_remove_root():
    assert diff({"a": 1}, {"b": 2}) != []
    assert apply({"a": 1}, diff({"a": 1}, {"b": 2})) == {"b": 2}
    assert apply(1, [{"op": "replace", "path": "", "from": 1, "value": [1, 2]}]) == [1, 2]
    assert apply([1], [{"op": "add", "path": "", "value": {"x": 1}}]) == {"x": 1}


def test_roundtrip_complex():
    a = {"x": [1, {"y": True}, 3], "z": None, "m~n": {"a/b": 1}}
    b = {"x": [1.0, {"y": 1}, 4, 5], "w": "new", "m~n": {"a/b": 2}}
    ops = diff(a, b)
    assert apply(a, ops) == b
    # input not mutated
    snapshot = copy.deepcopy(a)
    apply(a, ops)
    assert a == snapshot


def test_apply_deep_copy_isolation():
    a = {"x": [1, 2]}
    ops = [{"op": "add", "path": "/y", "value": {"n": [1]}}]
    out = apply(a, ops)
    out["y"]["n"].append(99)
    out["x"].append(99)
    assert a == {"x": [1, 2]}
