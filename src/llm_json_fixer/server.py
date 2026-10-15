"""llm-json-fixer: MCP server that deterministically repairs, extracts, validates and coerces JSON produced by LLMs."""
from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from llm_json_fixer import __version__, core
from llm_json_fixer import coerce as _coerce
from llm_json_fixer import extract as _extract

mcp = MCPServer(
    "llm-json-fixer",
    version=__version__,
    instructions=("Deterministic JSON repair for LLM output (no LLM calls, no network). Use repair_json on any broken "
                  "model output, extract_json to pull JSON out of prose, validate_json / coerce_to_schema with a JSON "
                  "Schema, complete_json for truncated or streaming output, and diff_json to see what changed."),
    website_url="https://github.com/MarkusIsaksson1982/llm-json-fixer",
)

Mode = Literal["lenient", "strict"]


def _parse_input(text: str | None, data: Any) -> tuple[bool, Any, dict]:
    if data is not None: return True, data, {}
    if not isinstance(text, str): return True, text, {}
    if not text: return False, None, {"ok": False, "error": "send either 'text' or 'data'"}
    r = core.repair(text)
    return (r.ok, r.value, r.as_dict(include_text=False))


@mcp.tool()
def repair_json(text: str, schema: dict[str, Any] | None = None, mode: Mode = "lenient",
                multiple: Literal["first", "list"] = "first", include_diff: bool = False) -> dict[str, Any]:
    """Repair malformed JSON from an LLM: code fences, surrounding prose, trailing commas, single/smart quotes,
    unquoted keys, comments, Python/JS literals (True/None/NaN/undefined), missing commas, unescaped quotes and
    newlines, double-encoded JSON and truncated output. Optional JSON Schema: values are coerced toward it and the
    result is validated. mode='strict' only applies lossless fixes and refuses anything that needs guessing.
    Returns {ok, json, text, changed, changes[], truncated, warnings?, error?, diff?}."""
    r = core.repair(text, schema=schema, mode=mode, multiple=multiple)
    out = r.as_dict()
    if include_diff and r.ok:
        base = core.repair(text, mode="lenient", coerce=False)
        out["diff"] = core.diff(base.value, r.value) if base.ok else []
    return out


@mcp.tool()
def extract_json(text: str, all: bool = False) -> dict[str, Any]:
    """Find and repair JSON embedded in prose or Markdown. all=False returns the best (first complete) value;
    all=True returns every JSON object/array found, each repaired. Never invents JSON when none is present."""
    fenced = _extract.strip_fences(text)
    src = fenced if fenced is not None else text
    spans = _extract.find_spans(src)
    if not spans: return {"ok": False, "error": "no JSON object or array found", "values": []}
    if not all:
        s, e, _ = _extract.best_span(src)
        r = core.repair(src[s:e])
        return r.as_dict() | {"span": [s, e], "from_fence": fenced is not None}
    vals = []
    for s, e, complete in spans:
        r = core.repair(src[s:e])
        if r.ok: vals.append({"json": r.value, "span": [s, e], "complete": complete})
    return {"ok": bool(vals), "values": vals, "count": len(vals), "from_fence": fenced is not None}


@mcp.tool()
def validate_json(schema: dict[str, Any], text: str = "", data: Any = None, repair: bool = True) -> dict[str, Any]:
    """Validate JSON against a JSON Schema (draft 2020-12, 2019-09, 7, 6 or 4). Send 'text' (repaired first unless
    repair=False) or already-parsed 'data'. Returns {valid, errors[{path, message, keyword}], repaired?}."""
    if data is None and text and not repair:
        try: data = json.loads(text)
        except ValueError as e: return {"valid": False, "errors": [{"path": "", "message": f"invalid JSON: {e}", "keyword": "syntax"}]}
    ok, value, info = _parse_input(text, data)
    if not ok: return {"valid": False, "errors": [{"path": "", "message": info.get("error", "unparseable"), "keyword": "syntax"}]}
    errs = core.validate_value(value, schema)
    out: dict[str, Any] = {"valid": not errs, "errors": errs}
    if info.get("changed"): out["repaired"] = {"json": value, "changes": info["changes"]}
    return out


@mcp.tool()
def coerce_to_schema(schema: dict[str, Any], text: str = "", data: Any = None,
                     drop_additional: bool = True, fill_defaults: bool = False) -> dict[str, Any]:
    """Repair (if text) and then coerce values toward a JSON Schema: "41"->41, "yes"->true, 41.0->41, "Open"->"open"
    (enum case), scalar->[scalar], "null"->null, extra keys dropped when additionalProperties is false, defaults filled
    on request. Never invents missing values. Returns {ok, json, coercions[], valid, errors[]}."""
    ok, value, info = _parse_input(text, data)
    if not ok: return {"ok": False, "error": info.get("error", "unparseable")}
    new, ch = _coerce.coerce(value, schema, drop_additional=drop_additional, fill_defaults=fill_defaults)
    errs = core.validate_value(new, schema)
    return {"ok": True, "json": new, "coercions": ch, "valid": not errs, "errors": errs,
            "repairs": info.get("changes", [])}


@mcp.tool()
def complete_json(partial: str) -> dict[str, Any]:
    """Close truncated or still-streaming JSON (cut-off strings, open arrays/objects, half-written true/false/null)
    into a valid value. Returns {ok, json, text, truncated, changes[]}."""
    return core.complete(partial).as_dict()


@mcp.tool()
def diff_json(before: str, after: str) -> dict[str, Any]:
    """Compare two JSON texts (each repaired leniently first) and return RFC 6902-style operations
    [{op: add|remove|replace, path, from?, value?}] that turn 'before' into 'after'."""
    a, b = core.repair(before), core.repair(after)
    if not (a.ok and b.ok): return {"ok": False, "error": "could not parse " + ("before" if not a.ok else "after")}
    ops = core.diff(a.value, b.value)
    return {"ok": True, "equal": not ops, "ops": ops}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
