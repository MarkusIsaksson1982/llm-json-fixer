"""Tests for coerce.py."""
import copy

import pytest

from llm_json_fixer.coerce import coerce


def test_no_mutation_and_root_path():
    v = {"a": "41"}
    orig = copy.deepcopy(v)
    nv, ch = coerce(v, {"type": "object", "properties": {"a": {"type": "integer"}}})
    assert v == orig
    assert nv == {"a": 41}
    assert ch[0]["path"] == "/a"


def test_bool_is_not_integer():
    nv, ch = coerce(True, {"type": "integer"})
    assert nv is True
    assert ch == []
    nv2, _ = coerce(True, {"type": "number"})
    assert nv2 is True


def test_integral_float_number_vs_integer():
    nv, ch = coerce(41.0, {"type": "number"})
    assert nv == 41.0 and ch == []
    nv2, ch2 = coerce(41.0, {"type": "integer"})
    assert nv2 == 41 and isinstance(nv2, int)
    nv3, ch3 = coerce(3.5, {"type": "integer"})
    assert nv3 == 3.5 and ch3 == []


def test_integer_from_strings():
    assert coerce("41", {"type": "integer"})[0] == 41
    assert coerce(" 41 ", {"type": "integer"})[0] == 41
    assert coerce("41.0", {"type": "integer"})[0] == 41
    assert coerce("-3", {"type": "integer"})[0] == -3
    nv, _ = coerce("3.5", {"type": "integer"})
    assert nv == "3.5"


def test_integer_leading_number_rule():
    nv, ch = coerce("41 years", {"type": "integer"})
    assert nv == 41
    assert ch[0]["rule"] == "leading_number"
    nv2, ch2 = coerce("3.5 stars", {"type": "integer"})
    assert nv2 == "3.5 stars" and ch2 == []


def test_number_from_strings():
    assert coerce("3.5", {"type": "number"})[0] == 3.5
    assert coerce("1e3", {"type": "number"})[0] == 1000.0
    nv, ch = coerce("41 kg", {"type": "number"})
    assert nv == 41
    assert ch[0]["rule"] == "leading_number"


def test_boolean_from_strings_and_numbers():
    for s in ["true", "True", "YES", "y", "On", "1"]:
        assert coerce(s, {"type": "boolean"})[0] is True
    for s in ["false", "FALSE", "No", "n", "OFF", "0"]:
        assert coerce(s, {"type": "boolean"})[0] is False
    assert coerce(1, {"type": "boolean"})[0] is True
    assert coerce(0, {"type": "boolean"})[0] is False
    assert coerce(2, {"type": "boolean"})[0] == 2


def test_string_json_form():
    assert coerce(True, {"type": "string"})[0] == "true"
    assert coerce(False, {"type": "string"})[0] == "false"
    assert coerce(5, {"type": "string"})[0] == "5"


def test_null_coercion():
    assert coerce("null", {"type": "null"})[0] is None
    assert coerce("None", {"type": "null"})[0] is None
    assert coerce("", {"type": "null"})[0] is None
    # already matches other allowed type -> leave
    nv, ch = coerce("null", {"type": ["string", "null"]})
    assert nv == "null" and ch == []


def test_type_list_already_matches():
    nv, ch = coerce("hi", {"type": ["string", "integer"]})
    assert nv == "hi" and ch == []


def test_wrap_array_and_items():
    nv, ch = coerce("41", {"type": "array", "items": {"type": "integer"}})
    assert nv == [41]
    rules = {c["rule"] for c in ch}
    assert "wrap_array" in rules
    assert any(c["path"] == "" for c in ch)
    assert any(c["path"] == "/0" for c in ch)


def test_enum_case():
    nv, ch = coerce("red", {"type": "string", "enum": ["Red", "Blue"]})
    assert nv == "Red"
    assert ch[0]["rule"] == "enum_case"
    nv2, ch2 = coerce(" red ", {"type": "string", "enum": ["Red"]})
    assert nv2 == "Red"


def test_object_properties_and_drop_additional():
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "additionalProperties": False}
    nv, ch = coerce({"a": "1", "extra": 2}, schema, drop_additional=True)
    assert nv == {"a": 1}
    drop = [c for c in ch if c["rule"] == "drop_additional"]
    assert len(drop) == 1 and drop[0]["path"] == "/extra" and drop[0]["to"] is None
    # keep when disabled
    nv2, _ = coerce({"a": "1", "extra": 2}, schema, drop_additional=False)
    assert "extra" in nv2


def test_fill_defaults():
    schema = {"type": "object", "properties": {"a": {"type": "string", "default": "hi"}}, "required": ["a"]}
    nv, ch = coerce({}, schema, fill_defaults=True)
    assert nv == {"a": "hi"}
    assert ch[0]["rule"] == "fill_default"
    nv2, ch2 = coerce({}, schema, fill_defaults=False)
    assert nv2 == {} and ch2 == []


def test_array_items():
    nv, _ = coerce(["1", "2"], {"type": "array", "items": {"type": "integer"}})
    assert nv == [1, 2]


def test_ref_definitions_and_defs():
    schema = {"definitions": {"x": {"type": "integer"}}, "properties": {"a": {"$ref": "#/definitions/x"}}}
    assert coerce({"a": "5"}, schema)[0] == {"a": 5}
    schema2 = {"$defs": {"y": {"type": "boolean"}}, "properties": {"b": {"$ref": "#/$defs/y"}}}
    assert coerce({"b": "yes"}, schema2)[0] == {"b": True}


def test_anyof_first_valid():
    schema = {"anyOf": [{"type": "integer"}, {"type": "string"}]}
    assert coerce("41", schema)[0] == 41
    assert coerce("hi", schema)[0] == "hi"
    nv, _ = coerce("hi", {"oneOf": [{"type": "integer"}, {"type": "string"}]})
    assert nv == "hi"


def test_anyof_no_branch_unchanged():
    schema = {"anyOf": [{"type": "integer"}]}
    nv, ch = coerce("abc", schema)
    assert nv == "abc" and ch == []


def test_never_raise_and_no_rule_no_change():
    nv, ch = coerce({"a": 1}, {"type": "weird", "properties": "nope"})
    assert nv == {"a": 1}
    nv2, ch2 = coerce("abc", {"type": "integer"})
    assert nv2 == "abc" and ch2 == []


def test_pointer_escaping():
    nv, ch = coerce({"a/b": "1"}, {"properties": {"a/b": {"type": "integer"}}})
    assert nv == {"a/b": 1}
    assert ch[0]["path"] == "/a~1b"
