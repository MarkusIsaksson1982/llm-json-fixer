import json, math, re, jsonschema
def norm(v):
    if isinstance(v, bool) or v is None or isinstance(v, str): return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return "NONFINITE"
        return float(v)
    if isinstance(v, list): return [norm(x) for x in v]
    if isinstance(v, dict): return {k: norm(x) for k, x in v.items()}
    return v
def strings(v):
    if isinstance(v, str): yield v
    elif isinstance(v, list):
        for x in v: yield from strings(x)
    elif isinstance(v, dict):
        for k, x in v.items(): yield k; yield from strings(x)
def score(case, r):
    """r: {ok: bool, value: any, valid: bool|None, ms, error}. Returns dict(correct, halluc, robust)."""
    out = {"correct": False, "halluc": False, "robust": r.get("error_kind") not in ("exception", "timeout")}
    if case["cat"] == "schema_validate":
        out["correct"] = r.get("valid") is not None and r.get("valid") == case["valid"]; return out
    exp = case["expect"]
    if not r.get("ok"):
        out["correct"] = exp is None or None in exp; return out
    v = r.get("value")
    if exp is None: out["halluc"] = True; return out
    if r.get("ok") and isinstance(v, (dict, list, str)):
        src = case["input"]
        for s in strings(v):
            exp_strings = {x for e in (case["expect"] or []) for x in strings(e)}
            if len(s) > 2 and s not in src and s.lower() not in src.lower() and s not in exp_strings and s not in ("open", "closed"):
                out["halluc"] = True; break
    out["correct"] = any(e is not None and norm(v) == norm(e) for e in exp)
    if case["cat"] == "schema_coerce" and out["correct"]:
        try: jsonschema.validate(v, case["schema"])
        except Exception: out["correct"] = False
    return out
