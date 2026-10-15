"""MCP client for Smithery-listed servers via Smithery Connect. Bearer key from env; never printed."""
import os, time, re, httpx, contextlib
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
NS = "markusisaksson"; API = "https://api.smithery.ai"
def _h(): return {"Authorization": f"Bearer {os.environ['SMITHERY_API_KEY']}"}
def conn_id(qn): return "bench-" + re.sub(r"[^a-z0-9-]", "-", qn.lower().replace("/", "--"))[:60]
def ensure_connection(qn):
    cid = conn_id(qn)
    r = httpx.put(f"{API}/connect/{NS}/{cid}", headers=_h(), json={"server": qn, "name": cid}, timeout=60)
    j = r.json(); return cid, r.status_code, (j.get("status") or {}).get("state", j.get("error"))
def delete_connection(cid): return httpx.delete(f"{API}/connect/{NS}/{cid}", headers=_h(), timeout=30).status_code
@contextlib.asynccontextmanager
async def session(cid):
    async with httpx.AsyncClient(headers=_h(), timeout=90) as http:
        async with streamable_http_client(f"{API}/connect/{NS}/{cid}/mcp", http_client=http) as (r, w, *_):
            async with ClientSession(r, w) as s:
                await s.initialize(); yield s
async def call(s, name, args):
    t = time.perf_counter()
    try: res = await s.call_tool(name, args)
    except Exception as e: return {"ms": round((time.perf_counter()-t)*1000), "is_error": True, "text": f"EXC {e!r}"[:500], "structured": None}
    return {"ms": round((time.perf_counter()-t)*1000), "is_error": bool(res.is_error), "text": "\n".join(getattr(c, "text", "") for c in res.content), "structured": res.structured_content}
