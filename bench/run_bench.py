"""Run the corpus against hosted Smithery servers (via Smithery Connect) and local baselines."""
import asyncio, json, sys, time, subprocess, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpcall import session, conn_id, call
from score import score
import os
C = json.load(open(os.environ.get("CORPUS", "corpus.json")))
def parse_text(t):
    try: return json.loads(t)
    except Exception: return None

# ---- adapters: return dict(ok, value, valid, error_kind)
async def jsonaut(s, c):
    if c["cat"] == "schema_validate":
        r = await call(s, "validate_json", {"input": c["input"], "schema": c["schema"]}); j = parse_text(r["text"]) or {}
        return r, {"valid": j.get("valid"), "ok": True}
    args = {"input": c["input"]} | ({"schema": c["schema"]} if c["schema"] else {})
    r = await call(s, "repair_json", args); j = parse_text(r["text"])
    if r["text"].startswith("EXC"): return r, {"ok": False, "error_kind": "exception"}
    if not isinstance(j, dict) or j.get("repaired") is None and j.get("method") == "failed": return r, {"ok": False}
    return r, {"ok": True, "value": j.get("repaired")}
async def jsonmend(s, c):
    if c["cat"] == "schema_validate":
        r = await call(s, "validate_json", {"input": c["input"], "schema": c["schema"]}); st = r["structured"] or {}
        return r, {"valid": st.get("valid"), "ok": True}
    args = {"input": c["input"]} | ({"schema": c["schema"], "coerce": True} if c["schema"] else {})
    r = await call(s, "repair_json", args); st = r["structured"] or {}
    if r["text"].startswith("EXC"): return r, {"ok": False, "error_kind": "exception"}
    if r["is_error"] or "json" not in st: return r, {"ok": False}
    return r, {"ok": True, "value": st["json"]}
async def bristlecone(s, c):
    if c["cat"] == "schema_validate":
        r = await call(s, "validate_schema", {"schema_definition": {k: "" for k in c["schema"].get("required", [])}, "data": parse_text(c["input"])})
        t = r["text"].lower(); v = None if r["is_error"] else (False if ("invalid" in t or "missing" in t or "false" in t) else True)
        return r, {"valid": v, "ok": True}
    r = await call(s, "repair_json", {"raw_json": c["input"]}); j = parse_text(r["text"])
    if r["text"].startswith("EXC"): return r, {"ok": False, "error_kind": "exception"}
    if r["is_error"] or j is None: return r, {"ok": False}
    if isinstance(j, dict) and set(j) >= {"error"} and len(j) <= 3 and "error" not in c["input"]: return r, {"ok": False}
    return r, {"ok": True, "value": j}
HOSTED = {"progamerplayzyt97/jsonaut": jsonaut, "mike-tusa/jsonmend": jsonmend, "joshua-wkl4/bristlecone-logic": bristlecone}

def local_json_repair(c):
    import json_repair
    t = time.perf_counter()
    try:
        if c["cat"] == "schema_validate":
            import jsonschema; v = json_repair.loads(c["input"])
            ok = True
            try: jsonschema.validate(v, c["schema"])
            except jsonschema.ValidationError: ok = False
            return {"ms": round((time.perf_counter()-t)*1000)}, {"ok": True, "valid": ok}
        v = json_repair.repair_json(c["input"], return_objects=True)
        ok = not (v == "" or v is None and c["input"].strip() not in ("null",))
        return {"ms": round((time.perf_counter()-t)*1000)}, {"ok": ok, "value": v}
    except Exception as e: return {"ms": round((time.perf_counter()-t)*1000)}, {"ok": False, "error_kind": "exception"}

async def run_hosted(qn, fn, rows):
    async with session(conn_id(qn)) as s:
        for c in C:
            for attempt in range(2):
                await asyncio.sleep(1.5)
                try: r, res = await asyncio.wait_for(fn(s, c), 90)
                except asyncio.TimeoutError: r, res = {"ms": 90000, "text": "TIMEOUT"}, {"ok": False, "error_kind": "timeout"}
                sc = score(c, res)
                if sc["correct"] or attempt: break
                await asyncio.sleep(6)   # retry once after a pause (rate limits / transient)
            rows.append({"server": qn, "id": c["id"], "cat": c["cat"], "ms": r.get("ms"), "raw": (r.get("text") or "")[:240], "attempts": attempt + 1, **res, **sc})
async def main(which):
    rows = []
    for qn, fn in HOSTED.items():
        if which and qn not in which: continue
        try: await run_hosted(qn, fn, rows)
        except BaseException as e: print("session fail", qn, repr(e)[:200])
    if not which or "lib:json_repair(py)" in which:
        for c in C:
            r, res = local_json_repair(c); rows.append({"server": "lib:json_repair(py)", "id": c["id"], "cat": c["cat"], "ms": r["ms"], **res, **score(c, res)})
    return rows
if __name__ == "__main__":
    which = sys.argv[1:]
    rows = asyncio.run(main(which))
    out = os.environ.get("OUT") or "results-" + ("all" if not which else "-".join(w.replace("/", "_").replace(":", "_") for w in which)) + ".jsonl"
    with open(out, "w") as f:
        for r in rows: f.write(json.dumps({k: (v if k != "value" else json.dumps(v, ensure_ascii=False)[:300]) for k, v in r.items()}, ensure_ascii=False) + "\n")
    print("wrote", out, len(rows))
