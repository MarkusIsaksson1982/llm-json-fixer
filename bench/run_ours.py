"""Score llm-json-fixer (in-process core, plus a stdio MCP pass for latency) on the corpus."""
import json, os, sys, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score import score
from llm_json_fixer import core
import os
C = json.load(open(os.environ.get("CORPUS", "corpus.json")))
NAME = "markusisaksson/llm-json-fixer"
def adapter(c):
    if c["cat"] == "schema_validate":
        r = core.repair(c["input"]); return {"ok": True, "valid": r.ok and not core.validate_value(r.value, c["schema"])}
    r = core.repair(c["input"], schema=c["schema"])
    return {"ok": r.ok, "value": r.value}
async def mcp_latency():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    ms = {}
    async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "llm_json_fixer.server"])) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        for c in C:
            t = time.perf_counter()
            if c["cat"] == "schema_validate": await s.call_tool("validate_json", {"schema": c["schema"], "text": c["input"]})
            else: await s.call_tool("repair_json", {"text": c["input"]} | ({"schema": c["schema"]} if c["schema"] else {}))
            ms[c["id"]] = round((time.perf_counter() - t) * 1000)
    return ms
rows = []
ms = asyncio.run(mcp_latency()) if "--mcp" in sys.argv else {}
for c in C:
    t = time.perf_counter()
    try: res = adapter(c)
    except Exception as e: res = {"ok": False, "error_kind": "exception", "err": repr(e)}
    rows.append({"server": NAME, "id": c["id"], "cat": c["cat"], "ms": ms.get(c["id"], round((time.perf_counter() - t) * 1000)),
                 **{k: (json.dumps(v, ensure_ascii=False)[:300] if k == "value" else v) for k, v in res.items()}, **score(c, res)})
with open(os.environ.get("OUT", "results-ours.jsonl"), "w") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
