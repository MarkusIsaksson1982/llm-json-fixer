"""Run every fixture in fixtures/<failure-class>/ through the deterministic repair (no LLM)."""
import json
from pathlib import Path
import pytest
from llm_json_fixer import core
from tests.test_corpus import norm

FIX = Path(__file__).resolve().parents[1] / "fixtures"
CASES = sorted(FIX.glob("*/*.input.txt"))


def test_fixture_folder_is_populated():
    assert len(CASES) >= 60


@pytest.mark.parametrize("path", CASES, ids=[f"{p.parent.name}/{p.name[:-10]}" for p in CASES])
def test_repair_llm_json_fixture(path):
    text = path.read_text()
    meta = json.loads(path.with_name(path.name.replace(".input.txt", ".expected.json")).read_text())
    if "valid" in meta:  # schema validation fixture
        r = core.repair(text)
        assert r.ok and (not core.validate_value(r.value, meta["schema"])) == meta["valid"]
        return
    r = core.repair(text, schema=meta.get("schema"))
    expect = meta.get("expect")
    if expect is None:  # no JSON in the output: must refuse, never hallucinate
        assert not r.ok
        return
    if not r.ok:
        assert None in expect
        return
    assert any(e is not None and norm(r.value) == norm(e) for e in expect)


def test_repair_is_deterministic():
    for p in CASES[:20]:
        a, b = core.repair(p.read_text()), core.repair(p.read_text())
        assert (a.ok, a.value if a.ok else None) == (b.ok, b.value if b.ok else None)


def test_fixtures_and_catalogue_in_sync_with_corpus(tmp_path, monkeypatch):
    """fixtures/ and docs/REPAIR-CATALOGUE.md must match what scripts/export_fixtures.py generates."""
    import importlib.util, filecmp
    root = FIX.parent
    spec = importlib.util.spec_from_file_location("export_fixtures", root / "scripts/export_fixtures.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    (tmp_path / "tests/data").mkdir(parents=True); (tmp_path / "docs").mkdir()
    (tmp_path / "tests/data/corpus.json").write_bytes((root / "tests/data/corpus.json").read_bytes())
    monkeypatch.setattr(mod, "ROOT", tmp_path); monkeypatch.setattr(mod, "FIX", tmp_path / "fixtures")
    mod.main()
    assert (tmp_path / "docs/REPAIR-CATALOGUE.md").read_text() == (root / "docs/REPAIR-CATALOGUE.md").read_text()
    cmp = filecmp.dircmp(tmp_path / "fixtures", FIX)
    stack = [cmp]
    while stack:
        c = stack.pop()
        assert not (c.left_only or c.right_only or c.diff_files), c.report()
        stack += c.subdirs.values()
