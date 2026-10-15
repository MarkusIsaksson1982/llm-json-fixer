"""Smoke test: start the server over stdio and call every tool once."""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CALLS = [("repair_json", {"text": "```json\n{'a': 1, b: [1,2,],}\n```"}),
         ("extract_json", {"text": 'Result: {"x": 1} and also [1, 2]', "all": True}),
         ("validate_json", {"schema": {"type": "object", "required": ["a"]}, "text": "{'b': 1}"}),
         ("coerce_to_schema", {"schema": {"type": "object", "properties": {"n": {"type": "integer"}}}, "text": '{"n": "5"}'}),
         ("complete_json", {"partial": '{"items": [1, 2, {"name": "x'}),
         ("diff_json", {"before": '{"a": 1}', "after": '{"a": 2, "b": 3}'})]

async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "llm_json_fixer.server"])
    ok = True
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        print("tools:", sorted(t.name for t in (await s.list_tools()).tools))
        for name, args in CALLS:
            res = await s.call_tool(name, args)
            data = res.structured_content or json.loads(res.content[0].text)
            good = not res.is_error; ok &= good
            print(("OK  " if good else "FAIL"), name, json.dumps(data, ensure_ascii=False)[:160])
    return 0 if ok else 1

sys.exit(asyncio.run(main()))
