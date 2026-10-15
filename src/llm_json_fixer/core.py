"""Deterministic repair pipeline for broken LLM JSON output. No network or LLM calls.

Pipeline: strict parse -> code-fence strip -> locate JSON in prose -> token pre-pass (NaN/Infinity/undefined,
hex/+/.5 numbers, truncated literals) -> tolerant parse (json_repair) -> post-pass (non-finite floats) ->
optional schema coercion + validation. Every step that changes something is recorded in `changes`.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

import json_repair

from . import coerce as _coerce
from . import extract as _extract
from . import jdiff as _jdiff

MAX_INPUT = 5_000_000  # characters

_LITERALS = {"NaN": "null", "Infinity": "null", "-Infinity": "null", "+Infinity": "null", "undefined": "null"}
_WORD = re.compile(r"[+-]?(?:Infinity|NaN|undefined)\b|0[xX][0-9a-fA-F]+\b|[+](?=\d|\.\d)|(?<![\w.])\.(?=\d)")


@dataclass
class Result:
    ok: bool
    value: Any = None
    changes: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    error: str | None = None
    code: str | None = None

    def as_dict(self, *, include_text: bool = True) -> dict:
        d: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            d["json"] = self.value
            if include_text: d["text"] = json.dumps(self.value, ensure_ascii=False, separators=(",", ":"))
        else:
            d["error"] = self.error
            d["code"] = self.code or "UNRECOVERABLE"
        d["changed"] = bool(self.changes)
        d["changes"] = self.changes
        d["truncated"] = self.truncated
        if self.warnings: d["warnings"] = self.warnings
        return d


def _outside_strings(text: str):
    """Yield (start, end, is_string) segments; strings are "..." or '...' with backslash escapes."""
    i, n, start = 0, len(text), 0
    while i < n:
        ch = text[i]
        if ch in "\"'\u201c\u201d":
            if i > start: yield start, i, False
            close = {'"': '"', "'": "'", "\u201c": "\u201d", "\u201d": "\u201d"}[ch]
            j = i + 1
            while j < n and text[j] != close and not (close == "\u201d" and text[j] == '"'):
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            yield i, j, True
            i = start = j
            continue
        i += 1
    if start < n: yield start, n, False


def _prepass(text: str, changes: list[dict]) -> str:
    out, counts = [], {}
    for s, e, is_str in _outside_strings(text):
        seg = text[s:e]
        if not is_str:
            def sub(m):
                t = m.group(0)
                if t.lstrip("+-") in ("NaN", "Infinity", "undefined"):
                    counts["non_json_literal"] = counts.get("non_json_literal", 0) + 1; return "null"
                if t[:2].lower() == "0x":
                    counts["hex_number"] = counts.get("hex_number", 0) + 1; return str(int(t, 16))
                if t == "+":
                    counts["plus_sign"] = counts.get("plus_sign", 0) + 1; return ""
                if t == ".":
                    counts["leading_dot"] = counts.get("leading_dot", 0) + 1; return "0."
                return t
            seg = _WORD.sub(sub, seg)
        out.append(seg)
    res = "".join(out)
    # a truncated literal at the very end: {"ok": tr -> {"ok": true
    m = re.search(r"(?<![\w\"'])(t|tr|tru|f|fa|fal|fals|n|nu|nul|T|Tr|Tru|F|Fa|Fal|Fals|N|No|Non)\s*$", res)
    if m and re.search(r"[:\[,]\s*$", res[: m.start()]):
        word = m.group(1)
        full = next(w for w in ("true", "false", "null", "True", "False", "None") if w.startswith(word))
        full = {"True": "true", "False": "false", "None": "null"}.get(full, full)
        res = res[: m.start()] + full
        counts["completed_literal"] = 1
    for k, v in counts.items():
        changes.append({"fix": k, "count": v})
    return res


_DANGLING = re.compile(r"""([{,])\s*(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[A-Za-z_$][\w$]*)\s*:?\s*$""")


def _drop_dangling_member(text: str, changes: list[dict]) -> str:
    """A truncated object that ends in a key with no value ({"a": 1, "b": or {"a": 1, "b) loses that key:
    nothing is invented for it."""
    stripped = text.rstrip()
    if not stripped or stripped[-1] in "}]":
        return text
    # only when the tail is a key in object context: the last unclosed bracket must be '{'
    depth, last_open = [], None
    for s, e, is_str in _outside_strings(stripped):
        if is_str: continue
        for ch in stripped[s:e]:
            if ch in "{[": depth.append(ch)
            elif ch in "}]" and depth: depth.pop()
    if not depth or depth[-1] != "{":
        return text
    m = _DANGLING.search(stripped)
    if not m:
        return text
    changes.append({"fix": "dropped_incomplete_member"})
    out = stripped[: m.start()] + (m.group(1) if m.group(1) == "{" else "")
    if m.group(1) == "{" and len(depth) >= 2 and depth[-2] == "[":
        out = re.sub(r",?\s*\{$", "", out)   # the object had nothing else in it: drop it from its array
    return out


def _unclosed_stack(text: str) -> tuple[list[str], bool]:
    """Unclosed brackets at the end of `text` and whether the text ends inside a string."""
    stack: list[str] = []; in_str = False
    for s, e, is_str in _outside_strings(text):
        if is_str:
            seg = text[s:e]
            in_str = len(seg) < 2 or seg[-1] != {"'": "'", '"': '"'}.get(seg[0], "\u201d") or (seg.endswith("\\" + seg[-1]) and not seg.endswith("\\\\" + seg[-1]))
            continue
        in_str = False
        for ch in text[s:e]:
            if ch in "{[": stack.append(ch)
            elif ch in "}]" and stack: stack.pop()
    return stack, in_str


def _drop_partial_tail(text: str, value: Any, changes: list[dict]) -> Any:
    """Truncation policy "drop": remove the half-written scalar at the end and half-written objects in arrays."""
    stack, in_str = _unclosed_stack(text)
    if not stack or not isinstance(value, (dict, list)): return value
    tail = text.rstrip()
    mid_scalar = in_str or any(c.get("fix") == "completed_literal" for c in changes)
    # walk down the chain of last members through the unclosed containers
    chain = [value]; node = value
    for _ in range(len(stack) - 1):
        if isinstance(node, dict) and node: node = node[list(node)[-1]]
        elif isinstance(node, list) and node: node = node[-1]
        else: break
        if not isinstance(node, (dict, list)): break
        chain.append(node)
    dropped = []
    inner = chain[-1]
    if mid_scalar and inner:
        if isinstance(inner, dict):
            k = list(inner)[-1]
            if not isinstance(inner[k], (dict, list)): inner.pop(k); dropped.append("member")
        elif not isinstance(inner[-1], (dict, list)):
            inner.pop(); dropped.append("element")
    # half-written objects inside arrays, and objects emptied by the drop, are removed (never the root)
    for depth in range(len(chain) - 1, 0, -1):
        child, parent = chain[depth], chain[depth - 1]
        if (isinstance(parent, list) and isinstance(child, dict) and dropped) or child in ({}, []):
            if isinstance(parent, list) and parent and parent[-1] is child: parent.pop(); dropped.append("partial_object")
            elif isinstance(parent, dict) and parent:
                k = list(parent)[-1]
                if parent[k] is child: parent.pop(k); dropped.append("partial_object")
        else:
            break
    if dropped: changes.append({"fix": "dropped_partial_values", "count": len(dropped)})
    return value


def _clean_nonfinite(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    if isinstance(v, list): return [_clean_nonfinite(x) for x in v]
    if isinstance(v, dict): return {k: _clean_nonfinite(x) for k, x in v.items()}
    return v


_LOG_MAP = [
    ("missing the right delimiter", "fixed_delimiters"), ("misplaced quote", "escaped_inner_quotes"),
    ("closing quote", "closed_string"), ("found a literal instead of a quote", "quoted_bare_value"),
    ("comment", "removed_comments"), ("missing", "inserted_missing_token"), ("returning the element", "merged_values"),
]


def _summarise_log(log: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for item in log:
        t = item.get("text", "").lower()
        key = next((v for k, v in _LOG_MAP if k in t), "syntax_repair")
        counts[key] = counts.get(key, 0) + 1
    return [{"fix": k, "count": v} for k, v in counts.items()]


def _tolerant_parse(text: str, changes: list[dict]) -> Any:
    value, log = json_repair.repair_json(text, return_objects=True, logging=True, skip_json_loads=False)
    changes.extend(_summarise_log(log or []))
    return value


def _is_json_scalar_text(t: str) -> bool:
    try: json.loads(t); return True
    except Exception: return False


def repair(text: str, *, schema: dict | None = None, mode: str = "lenient", multiple: str = "first",
           coerce: bool = True, drop_additional: bool = True, fill_defaults: bool = False,
           truncation: str = "drop") -> Result:
    """Repair `text` into a JSON value.

    mode: "lenient" (default) applies every deterministic repair, including truncation completion and quote/delimiter
          heuristics. "strict" only applies lossless fixes (fences, surrounding prose, comments, trailing commas,
          Python/JS literals, single quotes, unquoted keys) and refuses inputs that need guessing (truncation,
          missing delimiters, unescaped quotes).
    multiple: when the text holds several JSON values one after another: "first" (default) or "list".
    truncation: for cut-off output. "drop" (default) removes the value that was being written when the text ended
          (a half string, number or literal) and any half-written object inside an array, so no partial data is
          returned. "keep" keeps every partial value (useful for streaming previews).
    """
    if not isinstance(text, str): return Result(False, error="input must be a string", code="BAD_INPUT")
    if len(text) > MAX_INPUT: return Result(False, error=f"input larger than {MAX_INPUT} characters", code="TOO_LARGE")
    changes: list[dict] = []
    src = text
    if src.startswith("\ufeff"):
        src = src[1:]; changes.append({"fix": "removed_bom"})
    stripped = src.strip()
    if not stripped: return Result(False, error="empty input", code="NO_JSON")
    # 1) already valid
    try:
        v = json.loads(stripped)
        if isinstance(v, str) and v.strip()[:1] in ("{", "["):
            try:
                v = json.loads(v); changes.append({"fix": "decoded_nested_json_string"})
            except ValueError:
                inner = repair(v, schema=None, mode=mode, coerce=False, truncation=truncation)
                if inner.ok and isinstance(inner.value, (dict, list)):
                    v = inner.value; changes.append({"fix": "decoded_nested_json_string"}); changes.extend(inner.changes)
        res = Result(True, _clean_nonfinite(v), changes)
        if any(isinstance(x, float) and not math.isfinite(x) for x in _walk(v)):
            res.changes.append({"fix": "non_json_literal"})
        return _finish(res, schema, coerce, drop_additional, fill_defaults)
    except (ValueError, RecursionError):
        pass
    # 2) fences
    fenced = _extract.strip_fences(src)
    if fenced is not None:
        src = fenced; changes.append({"fix": "stripped_code_fence"})
    # 3) locate JSON in prose / concatenated values
    spans = _extract.find_spans(src)
    truncated = False
    if not spans:
        cand = src.strip()
        if cand.startswith(("\"", "'")) or _is_json_scalar_text(cand):
            pass  # a lone (possibly quoted) scalar
        else:
            return Result(False, changes=changes, error="no JSON object or array found in the input", code="NO_JSON")
        pieces = [cand]
    else:
        before = src[: spans[0][0]].strip(); after = src[spans[-1][1]:].strip()
        between = [src[spans[k][1]: spans[k + 1][0]].strip() for k in range(len(spans) - 1)]
        concatenated = len(spans) > 1 and not before and not after and all(b in ("", ",") for b in between)
        if concatenated and multiple == "list":
            pieces = [src[s:e] for s, e, _ in spans]; changes.append({"fix": "concatenated_values_to_list", "count": len(spans)})
        else:
            best = _extract.best_span(src)
            s, e, complete = best
            pieces = [src[s:e]]
            if before or src[e:].strip() or len(spans) > 1:
                changes.append({"fix": "removed_surrounding_text"})
            if len(spans) > 1:
                changes.append({"fix": "ignored_additional_values", "count": len(spans) - 1})
            truncated = not complete
    values = []
    for piece in pieces:
        if mode == "strict":
            if truncated:
                return Result(False, changes=changes, truncated=True, error="input is truncated (strict mode)", code="TRUNCATED")
            ok, v = _strict_parse(piece, changes)
            if not ok: return Result(False, changes=changes, truncated=truncated, error=v, code="TRUNCATED" if "truncated" in v else "STRICT_REFUSED")
        else:
            pre = _prepass(piece, changes)
            if truncated:
                pre = _drop_dangling_member(pre, changes)
            try: v = json.loads(pre)
            except (ValueError, RecursionError):
                pre2 = _requote(_strip_comments(pre, changes), changes)
                try: v = json.loads(pre2)
                except (ValueError, RecursionError): v = _tolerant_parse(pre2, changes)
            if truncated and truncation == "drop":
                v = _drop_partial_tail(pre, v, changes)
            if v == "" and pre.strip() not in ('""', "''"):
                return Result(False, changes=changes, error="could not recover a JSON value", code="UNRECOVERABLE")
        values.append(_clean_nonfinite(v))
    if truncated:
        if mode == "strict": return Result(False, changes=changes, truncated=True, error="input is truncated (strict mode)", code="TRUNCATED")
        changes.append({"fix": "completed_truncated_json"})
    value = values if len(values) > 1 else values[0]
    if isinstance(value, str) and pieces and pieces[0].lstrip()[:1] in ("{", "["):
        # nested-escaped JSON like "{\"a\": 1}" handled below; a bare string from a {...} piece means failure
        pass
    # 4) double-encoded JSON: a string that itself holds an object/array
    if isinstance(value, str) and value.strip()[:1] in ("{", "["):
        try:
            inner = json.loads(value); value = inner; changes.append({"fix": "decoded_nested_json_string"})
        except ValueError:
            pass
    return _finish(Result(True, value, _dedupe(changes), truncated=truncated), schema, coerce, drop_additional, fill_defaults)


def _strict_parse(piece: str, changes: list[dict]):
    """Lossless fixes only, then a strict json.loads. Returns (ok, value_or_error)."""
    t = _strip_comments(piece, changes)
    t = _prepass(t, changes)
    if any(c.get("fix") == "completed_literal" for c in changes): return False, "input is truncated (strict mode)"
    t2 = _requote(t, changes)
    parts, hit = [], False
    for s0, e0, is_str in _outside_strings(t2):
        seg = t2[s0:e0]
        if not is_str:
            new = re.sub(r",(\s*[}\]])", r"\1", seg)
            hit |= new != seg; seg = new
        parts.append(seg)
    # a trailing comma can straddle a string boundary: '"x",}' -> handled since ',' and '}' are outside strings
    t2 = "".join(parts)
    if hit: changes.append({"fix": "removed_trailing_commas"})
    try:
        return True, json.loads(t2)
    except ValueError as e:
        return False, f"strict mode could not parse without guessing: {e.msg} at line {e.lineno} col {e.colno}"


def _strip_comments(t: str, changes: list[dict]) -> str:
    out, n = [], 0
    for s, e, is_str in _outside_strings(t):
        seg = t[s:e]
        if not is_str:
            new = re.sub(r"//[^\n]*|/\*.*?\*/|#[^\n]*", "", seg, flags=re.S)
            if new != seg: n += 1
            seg = new
        out.append(seg)
    if n: changes.append({"fix": "removed_comments"})
    return "".join(out)


def _requote(t: str, changes: list[dict]) -> str:
    """Single/smart-quoted strings -> double quotes, bare keys -> quoted, Python literals -> JSON (outside strings)."""
    out, fixes = [], set()
    for s, e, is_str in _outside_strings(t):
        seg = t[s:e]
        if is_str:
            if seg[0] != '"' or seg[-1:] == "\u201d":
                body = seg[1:-1] if len(seg) > 1 else ""
                body = body.replace("\\'", "'").replace('"', '\\"') if seg[0] == "'" else body.replace('"', '\\"')
                seg = '"' + body + '"'; fixes.add("normalised_quotes")
        else:
            new = re.sub(r"([{,]\s*)([A-Za-z_$][\w$-]*)(\s*:)", r'\1"\2"\3', seg)
            if new != seg: fixes.add("quoted_keys")
            new2 = re.sub(r"\b(True|False|None)\b", lambda m: {"True": "true", "False": "false", "None": "null"}[m.group(1)], new)
            if new2 != new: fixes.add("python_literals")
            new3 = re.sub(r"(?<=[\[,:])\s*\((.*?)\)", r"[\1]", new2) if "(" in new2 else new2
            seg = new3
        out.append(seg)
    changes.extend({"fix": f} for f in sorted(fixes))
    return "".join(out)


def _walk(v):
    if isinstance(v, list):
        for x in v: yield from _walk(x)
    elif isinstance(v, dict):
        for x in v.values(): yield from _walk(x)
    else:
        yield v


def _dedupe(changes: list[dict]) -> list[dict]:
    seen, out = {}, []
    for c in changes:
        k = c.get("fix")
        if k in seen:
            if "count" in c: seen[k]["count"] = seen[k].get("count", 1) + c["count"]
            continue
        c = dict(c); seen[k] = c; out.append(c)
    return out


def _finish(res: Result, schema, coerce, drop_additional, fill_defaults) -> Result:
    if not res.ok or not schema: return res
    if coerce:
        new, ch = _coerce.coerce(res.value, schema, drop_additional=drop_additional, fill_defaults=fill_defaults)
        if ch:
            res.value = new
            res.changes.append({"fix": "schema_coercion", "count": len(ch), "details": ch})
    errs = validate_value(res.value, schema)
    if errs:
        res.warnings.append(f"result does not match the schema ({len(errs)} error(s))")
        res.changes.append({"fix": "schema_validation_failed", "errors": errs[:20]})
    return res


def validate_value(value: Any, schema: dict) -> list[dict]:
    import jsonschema
    cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft202012Validator)
    v = cls(schema, format_checker=cls.FORMAT_CHECKER)
    out = []
    for e in sorted(v.iter_errors(value), key=lambda e: list(e.absolute_path)):
        out.append({"path": "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in e.absolute_path) if e.absolute_path else "",
                    "message": e.message, "keyword": e.validator})
    return out


def diff(a: Any, b: Any) -> list[dict]:
    return _jdiff.diff(a, b)


def complete(partial: str, truncation: str = "keep") -> Result:
    """Close a truncated / streaming JSON prefix into a valid value (lenient). Keeps partial values by default."""
    r = repair(partial, mode="lenient", truncation=truncation)
    if r.ok and not r.truncated:
        try: json.loads(partial.strip()); r.warnings.append("input was already complete")
        except ValueError: pass
    return r
