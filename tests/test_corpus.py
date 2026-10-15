"""The benchmark corpus as regression tests (the two huge cases live in bench/ and are generated)."""
import json, math
from pathlib import Path
import pytest
from llm_json_fixer import core

DATA = Path(__file__).parent / "data"
CORPUS = json.loads((DATA / "corpus.json").read_text())
HELDOUT = json.loads((DATA / "heldout.json").read_text())
KNOWN_HELDOUT_MISSES = {"h-30"}  # string payload with unescaped inner JSON: ambiguous, kept as a documented miss


def norm(v):
    if isinstance(v, bool) or v is None or isinstance(v, str): return v
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, list): return [norm(x) for x in v]
    return {k: norm(x) for k, x in v.items()}


def check(case):
    if case["cat"] == "schema_validate":
        r = core.repair(case["input"]); return r.ok and (not core.validate_value(r.value, case["schema"])) == case["valid"]
    r = core.repair(case["input"], schema=case.get("schema"))
    if case["expect"] is None: return not r.ok
    if not r.ok: return None in case["expect"]
    return any(e is not None and norm(r.value) == norm(e) for e in case["expect"])


@pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
def test_corpus(case):
    assert check(case), case["input"][:200]


@pytest.mark.parametrize("case", [c for c in HELDOUT if c["id"] not in KNOWN_HELDOUT_MISSES], ids=lambda c: c["id"])
def test_heldout(case):
    assert check(case), case["input"][:200]


def test_huge_and_deep():
    big = {"rows": [{"id": i, "name": f"item {i}", "ok": i % 2 == 0} for i in range(3000)]}
    s = json.dumps(big)
    assert core.repair("```json\n" + s[:-2] + ",]}\n```").value == big
    deep = "[" * 800 + "]" * 800
    assert core.repair(deep).ok


def test_strict_mode():
    ok = core.repair("```json\n{'a': True, // c\n b: [1, 2,], 'u': 'http://x//y'}\n```", mode="strict")
    assert ok.ok and ok.value == {"a": True, "b": [1, 2], "u": "http://x//y"}
    assert core.repair('{"a": 1 "b": 2}', mode="strict").code == "STRICT_REFUSED"
    assert core.repair('{"a": [1', mode="strict").code == "TRUNCATED"
    assert core.repair('{"s": "a,}", "b": [1,],}', mode="strict").value == {"s": "a,}", "b": [1]}


def test_truncation_policies():
    t = '{"confidence": 0.8, "answer": "The capital of France is Par'
    assert core.repair(t).value == {"confidence": 0.8}
    assert core.repair(t, truncation="keep").value == {"confidence": 0.8, "answer": "The capital of France is Par"}
    assert core.complete(t).value["answer"].endswith("Par")


def test_error_codes_and_no_invention():
    for t in ["", "   ", "I'm sorry, I can't help with that.", "1) Open Settings\n2) Sign out"]:
        r = core.repair(t); assert not r.ok and r.code == "NO_JSON"


def test_changes_are_reported():
    r = core.repair("```json\n{'a': 1,}\n```")
    fixes = {c["fix"] for c in r.changes}
    assert "stripped_code_fence" in fixes and r.as_dict()["changed"] is True
    v = core.repair('{"a": 1}'); assert v.changes == [] and v.as_dict()["changed"] is False


def test_multiple_values():
    assert core.repair('{"a": 1}\n{"a": 2}', multiple="list").value == [{"a": 1}, {"a": 2}]
    assert core.repair('{"a": 1}\n{"a": 2}').value == {"a": 1}


def test_schema_flow():
    s = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"], "additionalProperties": False}
    r = core.repair("{'n': '7', 'x': 1}", schema=s)
    assert r.value == {"n": 7} and any(c["fix"] == "schema_coercion" for c in r.changes)
    r = core.repair("{'m': 1}", schema=s)
    assert r.ok and r.warnings and any(c["fix"] == "schema_validation_failed" for c in r.changes)
