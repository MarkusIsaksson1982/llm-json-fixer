"""coerce.py: deterministically coerce an already-parsed JSON value toward a JSON Schema.

Standard library only, Python 3.10+, no network/LLM.
"""
from __future__ import annotations

import copy
import json
import math
import re

_LEADING_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")

_TRUE_STRINGS = {"true", "yes", "y", "on", "1"}
_FALSE_STRINGS = {"false", "no", "n", "off", "0"}


def _esc(s: object) -> str:
    return str(s).replace("~", "~0").replace("/", "~1")


def _resolve_ref(ref: str, root: object):
    try:
        if not isinstance(ref, str):
            return None
        if ref == "#":
            return root
        if not ref.startswith("#/"):
            return None
        parts = ref[2:].split("/")
        cur = root
        for raw in parts:
            key = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(cur, dict):
                if key not in cur:
                    return None
                cur = cur[key]
            elif isinstance(cur, list):
                try:
                    idx = int(key)
                except Exception:
                    return None
                if idx < 0 or idx >= len(cur):
                    return None
                cur = cur[idx]
            else:
                return None
        return cur
    except Exception:
        return None


def _effective_schema(schema: object, root: object, _seen=None):
    if _seen is None:
        _seen = set()
    cur = schema
    for _ in range(20):
        if not isinstance(cur, dict):
            break
        ref = cur.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#"):
            break
        if ref in _seen:
            break
        _seen.add(ref)
        target = _resolve_ref(ref, root)
        if target is None:
            break
        if isinstance(target, bool):
            if target is True:
                sib = {k: v for k, v in cur.items() if k != "$ref"}
                if not sib:
                    cur = True
                    break
                cur = sib
                break
            else:
                cur = False
                break
        if not isinstance(target, dict):
            break
        merged = dict(target)
        for k, v in cur.items():
            if k == "$ref":
                continue
            merged[k] = v
        cur = merged
    return cur


def _matches_type(v: object, t: str) -> bool:
    try:
        if t == "null":
            return v is None
        if t == "boolean":
            return isinstance(v, bool)
        if t == "integer":
            return isinstance(v, int) and not isinstance(v, bool)
        if t == "number":
            return (isinstance(v, int) and not isinstance(v, bool)) or isinstance(v, float)
        if t == "string":
            return isinstance(v, str)
        if t == "array":
            return isinstance(v, list)
        if t == "object":
            return isinstance(v, dict)
        return False
    except Exception:
        return False


def _json_equal(a: object, b: object) -> bool:
    try:
        if isinstance(a, bool) or isinstance(b, bool):
            return isinstance(a, bool) and isinstance(b, bool) and a == b
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            try:
                return bool(a == b)
            except Exception:
                return False
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return False
            return all(_json_equal(x, y) for x, y in zip(a, b))
        if isinstance(a, dict) and isinstance(b, dict):
            if set(a.keys()) != set(b.keys()):
                return False
            return all(_json_equal(a[k], b[k]) for k in a)
        return bool(a == b)
    except Exception:
        return False


def _split_leading(s: str):
    try:
        m = _LEADING_RE.match(s)
        if not m:
            return None
        num = m.group(0)
        rest = s[len(num):]
        return num, rest
    except Exception:
        return None


def _try_integer(v: object):
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, float):
            if math.isfinite(v) and v.is_integer():
                return int(v), "coerce_integer"
            return None
        if isinstance(v, str):
            stripped = v.strip()
            if stripped == "":
                return None
            sp = _split_leading(stripped)
            if sp is None:
                return None
            num_str, rest = sp
            try:
                if "." not in num_str and "e" not in num_str and "E" not in num_str:
                    ival = int(num_str, 10)
                else:
                    fval = float(num_str)
                    if not math.isfinite(fval) or not fval.is_integer():
                        return None
                    ival = int(fval)
            except Exception:
                return None
            if rest == "":
                return ival, "coerce_integer"
            else:
                return ival, "leading_number"
        return None
    except Exception:
        return None


def _try_number(v: object):
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return None
        if isinstance(v, str):
            stripped = v.strip()
            if stripped == "":
                return None
            sp = _split_leading(stripped)
            if sp is None:
                return None
            num_str, rest = sp
            try:
                if "." not in num_str and "e" not in num_str and "E" not in num_str:
                    nval = int(num_str, 10)
                else:
                    fval = float(num_str)
                    if not math.isfinite(fval):
                        return None
                    nval = fval
            except Exception:
                return None
            if rest == "":
                return nval, "coerce_number"
            else:
                return nval, "leading_number"
        return None
    except Exception:
        return None


def _try_boolean(v: object):
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if s in _TRUE_STRINGS:
                return True, "coerce_boolean"
            if s in _FALSE_STRINGS:
                return False, "coerce_boolean"
            return None
        if isinstance(v, int) and not isinstance(v, bool):
            if v == 1:
                return True, "coerce_boolean"
            if v == 0:
                return False, "coerce_boolean"
            return None
        if isinstance(v, float):
            try:
                if v == 1.0:
                    return True, "coerce_boolean"
                if v == 0.0:
                    return False, "coerce_boolean"
            except Exception:
                pass
            return None
        return None
    except Exception:
        return None


def _try_string(v: object):
    try:
        if isinstance(v, bool):
            return ("true" if v else "false"), "coerce_string"
        if isinstance(v, int) and not isinstance(v, bool):
            try:
                return json.dumps(v), "coerce_string"
            except Exception:
                return str(v), "coerce_string"
        if isinstance(v, float):
            try:
                if math.isnan(v) or math.isinf(v):
                    return None
                return json.dumps(v), "coerce_string"
            except Exception:
                return None
        return None
    except Exception:
        return None


def _try_null(v: object):
    try:
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in ("null", "none"):
                return None, "coerce_null"
        return None
    except Exception:
        return None


def _minimal_valid(val: object, schema: object, root: object) -> bool:
    try:
        eff = _effective_schema(schema, root)
        if eff is True:
            return True
        if eff is False:
            return False
        if not isinstance(eff, dict):
            return True
        if "type" in eff:
            t = eff["type"]
            allowed = None
            if isinstance(t, str):
                allowed = [t]
            elif isinstance(t, list):
                allowed = [x for x in t if isinstance(x, str)]
            if allowed:
                ok = False
                for a in allowed:
                    try:
                        if _matches_type(val, a):
                            ok = True
                            break
                    except Exception:
                        continue
                if not ok:
                    return False
        if "enum" in eff and isinstance(eff["enum"], list):
            found = False
            for e in eff["enum"]:
                if _json_equal(val, e):
                    found = True
                    break
            if not found:
                return False
        if "required" in eff and isinstance(eff["required"], list) and isinstance(val, dict):
            for r in eff["required"]:
                if isinstance(r, str) and r not in val:
                    return False
        for key in ("anyOf", "oneOf"):
            if key in eff and isinstance(eff[key], list) and len(eff[key]) > 0:
                any_ok = False
                for sub in eff[key]:
                    try:
                        if _minimal_valid(val, sub, root):
                            any_ok = True
                            break
                    except Exception:
                        continue
                if not any_ok:
                    return False
        return True
    except Exception:
        return True


def _inner(val: object, schema: object, path: str, root: object, drop_additional: bool, fill_defaults: bool, changes: list, seen: set):
    try:
        if isinstance(schema, bool):
            return val
        if not isinstance(schema, dict):
            return val
        # $ref (local only, no network)
        if isinstance(schema.get("$ref"), str):
            ref = schema["$ref"]
            if isinstance(ref, str) and ref.startswith("#"):
                if ref not in seen:
                    target = _resolve_ref(ref, root)
                    if target is not None:
                        if isinstance(target, dict):
                            merged = dict(target)
                            for k, v in schema.items():
                                if k != "$ref":
                                    merged[k] = v
                            nseen = set(seen)
                            nseen.add(ref)
                            return _inner(val, merged, path, root, drop_additional, fill_defaults, changes, nseen)
                        elif isinstance(target, bool):
                            if target is True:
                                sib = {k: v for k, v in schema.items() if k != "$ref"}
                                if not sib:
                                    return val
                                nseen = set(seen)
                                nseen.add(ref)
                                return _inner(val, sib, path, root, drop_additional, fill_defaults, changes, nseen)
                            else:
                                return val
                sib = {k: v for k, v in schema.items() if k != "$ref"}
                if not sib:
                    return val
                schema = sib
            else:
                sib = {k: v for k, v in schema.items() if k != "$ref"}
                if not sib:
                    return val
                schema = sib
        # anyOf / oneOf
        has_any = isinstance(schema.get("anyOf"), list)
        has_one = isinstance(schema.get("oneOf"), list)
        if has_any or has_one:
            for key in ("anyOf", "oneOf"):
                branches = schema.get(key)
                if not isinstance(branches, list):
                    continue
                for br in branches:
                    if not isinstance(br, (dict, bool)):
                        continue
                    tchanges: list = []
                    try:
                        tval = copy.deepcopy(val)
                    except Exception:
                        tval = val
                    try:
                        cres = _inner(tval, br, path, root, drop_additional, fill_defaults, tchanges, set(seen))
                    except Exception:
                        continue
                    try:
                        if _minimal_valid(cres, br, root):
                            changes.extend(tchanges)
                            return cres
                    except Exception:
                        continue
            return val
        # type coercion
        allowed = None
        if "type" in schema:
            t = schema["type"]
            if isinstance(t, str):
                allowed = [t]
            elif isinstance(t, list):
                allowed = [x for x in t if isinstance(x, str)]
        if allowed:
            already = False
            for a in allowed:
                try:
                    if _matches_type(val, a):
                        already = True
                        break
                except Exception:
                    continue
            if not already:
                ordered = [a for a in allowed if a != "null"] + [a for a in allowed if a == "null"]
                for tgt in ordered:
                    res = None
                    try:
                        if tgt == "integer":
                            res = _try_integer(val)
                        elif tgt == "number":
                            res = _try_number(val)
                        elif tgt == "boolean":
                            res = _try_boolean(val)
                        elif tgt == "string":
                            res = _try_string(val)
                        elif tgt == "null":
                            res = _try_null(val)
                        elif tgt == "array":
                            if not isinstance(val, list):
                                res = ([val], "wrap_array")
                            else:
                                res = None
                        else:
                            res = None
                    except Exception:
                        res = None
                    if res is not None:
                        nval, rule = res
                        try:
                            f = copy.deepcopy(val)
                        except Exception:
                            f = val
                        try:
                            tt = copy.deepcopy(nval)
                        except Exception:
                            tt = nval
                        changes.append({"path": path, "from": f, "to": tt, "rule": rule})
                        val = nval
                        break
        # enum (case-insensitive for strings)
        try:
            ev = schema.get("enum")
            if isinstance(ev, list) and isinstance(val, str):
                inex = False
                for e in ev:
                    if _json_equal(val, e):
                        inex = True
                        break
                if not inex:
                    vn = val.strip().lower()
                    for e in ev:
                        if isinstance(e, str) and e.strip().lower() == vn:
                            changes.append({"path": path, "from": copy.deepcopy(val), "to": copy.deepcopy(e), "rule": "enum_case"})
                            val = e
                            break
        except Exception:
            pass
        # objects
        try:
            if isinstance(val, dict):
                props = schema.get("properties")
                if not isinstance(props, dict):
                    props = {}
                for pname, psub in props.items():
                    if pname in val:
                        try:
                            sub_path = path + "/" + _esc(pname)
                            new_sub = _inner(val[pname], psub, sub_path, root, drop_additional, fill_defaults, changes, set(seen))
                            val[pname] = new_sub
                        except Exception:
                            continue
                if schema.get("additionalProperties") is False and drop_additional:
                    extras = [k for k in list(val.keys()) if k not in props]
                    for k in sorted(extras, key=lambda x: str(x)):
                        try:
                            f = copy.deepcopy(val[k])
                        except Exception:
                            f = val[k]
                        changes.append({"path": path + "/" + _esc(k), "from": f, "to": None, "rule": "drop_additional"})
                        try:
                            del val[k]
                        except Exception:
                            pass
                if fill_defaults:
                    req = schema.get("required")
                    if isinstance(req, list):
                        for r in req:
                            if not isinstance(r, str):
                                continue
                            if r not in val:
                                sub = props.get(r)
                                if isinstance(sub, dict) and "default" in sub:
                                    try:
                                        d = copy.deepcopy(sub["default"])
                                    except Exception:
                                        d = sub["default"]
                                    try:
                                        f_to = copy.deepcopy(d)
                                    except Exception:
                                        f_to = d
                                    changes.append({"path": path + "/" + _esc(r), "from": None, "to": f_to, "rule": "fill_default"})
                                    val[r] = d
        except Exception:
            pass
        # arrays
        try:
            if isinstance(val, list):
                items = schema.get("items")
                if isinstance(items, dict):
                    for idx in range(len(val)):
                        try:
                            sub_path = f"{path}/{idx}"
                            new_el = _inner(val[idx], items, sub_path, root, drop_additional, fill_defaults, changes, set(seen))
                            val[idx] = new_el
                        except Exception:
                            continue
        except Exception:
            pass
        return val
    except Exception:
        try:
            return val
        except Exception:
            return None


def coerce(value, schema, *, drop_additional=True, fill_defaults=False):
    """Coerce already-parsed JSON value toward JSON Schema.

    Returns (new_value, changes). Never mutates input. Never raises.
    """
    try:
        new_val = copy.deepcopy(value)
    except Exception:
        new_val = value
    changes: list = []
    try:
        result = _inner(new_val, schema, "", schema, bool(drop_additional), bool(fill_defaults), changes, set())
        return result, changes
    except Exception:
        try:
            return new_val, changes
        except Exception:
            return value, []
