import json, sys, statistics as st
from collections import defaultdict
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
CORE = {"fence","prose","trailing_comma","single_quotes","unquoted_keys","smart_quotes","comments","python_literals","special_numbers","missing_comma","mismatched","truncated","escapes","nested_escaping","unicode","concatenated","valid","combo","huge"}
by = defaultdict(list)
for r in rows: by[r["server"]].append(r)
print("| Server | Core repair (%d) | No-JSON refusal (3) | Schema coerce (5) | Schema validate (5) | Total | Hallucinated | Robust errors | Median ms | p95 ms |" % sum(1 for r in by[next(iter(by))] if r["cat"] in CORE))
print("|---|---|---|---|---|---|---|---|---|---|")
res = []
for s, R in by.items():
    f = lambda cats: sum(r["correct"] for r in R if r["cat"] in cats)
    ms = sorted(r["ms"] for r in R if r.get("ms") is not None)
    res.append((f(CORE), s, f({"no_json"}), f({"schema_coerce"}), f({"schema_validate"}), sum(r["correct"] for r in R), sum(r["halluc"] for r in R), sum(not r["robust"] for r in R), st.median(ms), ms[int(len(ms)*.95)-1]))
for c, s, n, sc, sv, t, h, rb, md, p95 in sorted(res, reverse=True):
    print(f"| {s} | {c} | {n} | {sc} | {sv} | {t}/{len(by[s])} | {h} | {rb} | {md:.0f} | {p95:.0f} |")
if "-v" in sys.argv[0:0] or True:
    fails = defaultdict(list)
    for r in rows:
        if not r["correct"]: fails[r["server"]].append(r["id"])
    for s, f in fails.items(): print(s, "FAIL:", " ".join(f))
