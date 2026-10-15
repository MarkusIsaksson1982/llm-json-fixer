import copy


def _escape(key) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def _unescape(tok: str) -> str:
    return tok.replace("~1", "/").replace("~0", "~")


def _scalar_equal(x, y) -> bool:
    # bool is subclass of int: bool vs number must be different
    if isinstance(x, bool) != isinstance(y, bool):
        return False
    try:
        return bool(x == y)
    except Exception:
        return False


def diff(a, b) -> list[dict]:
    """Return RFC 6902-style ops turning a into b."""

    def _rec(x, y, path: str) -> list[dict]:
        if isinstance(x, dict) and isinstance(y, dict):
            ops: list[dict] = []
            keys = sorted(set(x.keys()) | set(y.keys()))
            for k in keys:
                p = path + "/" + _escape(k)
                if k not in y:
                    ops.append({"op": "remove", "path": p, "from": copy.deepcopy(x[k])})
                elif k not in x:
                    ops.append({"op": "add", "path": p, "value": copy.deepcopy(y[k])})
                else:
                    ops.extend(_rec(x[k], y[k], p))
            return ops
        if isinstance(x, list) and isinstance(y, list):
            ops = []
            n = min(len(x), len(y))
            for i in range(n):
                p = f"{path}/{i}"
                ops.extend(_rec(x[i], y[i], p))
            if len(x) > len(y):
                for i in range(len(x) - 1, len(y) - 1, -1):
                    ops.append({"op": "remove", "path": f"{path}/{i}", "from": copy.deepcopy(x[i])})
            elif len(y) > len(x):
                for i in range(len(x), len(y)):
                    ops.append({"op": "add", "path": f"{path}/{i}", "value": copy.deepcopy(y[i])})
            return ops
        if _scalar_equal(x, y):
            return []
        return [{"op": "replace", "path": path, "from": copy.deepcopy(x), "value": copy.deepcopy(y)}]

    return _rec(a, b, "")


def apply(a, ops) -> object:
    """Apply ops (as produced by diff) to a deep copy of a."""
    res = copy.deepcopy(a)
    for op in ops:
        typ = op["op"]
        path = op["path"]
        if path == "":
            if typ in ("add", "replace"):
                res = copy.deepcopy(op["value"])
            elif typ == "remove":
                raise ValueError("cannot remove root document")
            else:
                raise ValueError(f"unknown op {typ!r}")
            continue
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError(f"invalid path {path!r}")
        raw_tokens = path.split("/")[1:]
        tokens = [_unescape(t) for t in raw_tokens]
        parent = res
        for tok in tokens[:-1]:
            if isinstance(parent, dict):
                parent = parent[tok]
            elif isinstance(parent, list):
                parent = parent[int(tok)]
            else:
                raise TypeError("path parent is not a container")
        last = tokens[-1]
        if isinstance(parent, dict):
            if typ == "add":
                parent[last] = copy.deepcopy(op["value"])
            elif typ == "replace":
                parent[last] = copy.deepcopy(op["value"])
            elif typ == "remove":
                del parent[last]
            else:
                raise ValueError(f"unknown op {typ!r}")
        elif isinstance(parent, list):
            if last == "-":
                if typ != "add":
                    raise ValueError(f"op {typ!r} does not support '-'")
                parent.append(copy.deepcopy(op["value"]))
            else:
                try:
                    idx = int(last)
                except ValueError:
                    raise ValueError(f"invalid list index {last!r}") from None
                if typ == "add":
                    if idx < 0 or idx > len(parent):
                        raise IndexError(f"add index out of range: {idx}")
                    parent.insert(idx, copy.deepcopy(op["value"]))
                elif typ == "replace":
                    parent[idx] = copy.deepcopy(op["value"])
                elif typ == "remove":
                    del parent[idx]
                else:
                    raise ValueError(f"unknown op {typ!r}")
        else:
            raise TypeError("path parent is not a container")
    return res
