"""Extract JSON from a markdown code fence or surrounding prose in a model response.

Locate JSON-like spans in LLM output text (no parsing, no repair). Standard library only."""
from __future__ import annotations

import re

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)(?:```|\Z)", re.S)
_OPEN = {"{": "}", "[": "]"}
_QUOTES = {'"': '"', "'": "'", "\u201c": "\u201d", "\u201d": "\u201d"}


def strip_fences(text: str) -> str | None:
    """Content of the first Markdown code fence that contains '{' or '['; None if there is none."""
    for m in _FENCE.finditer(text):
        body = m.group(2)
        if "{" in body or "[" in body:
            return body
    return None


def _skip_string(text: str, i: int) -> int:
    """i points at an opening quote; return the index just past the closing quote (or len(text))."""
    close = _QUOTES[text[i]]; n = len(text); j = i + 1
    while j < n:
        c = text[j]
        if c == "\\": j += 2; continue
        if c == close or (close == "\u201d" and c == '"' and text[i] != "'"): return j + 1
        j += 1
    return n


def _prev_sig(text: str, i: int, floor: int) -> str:
    j = i - 1
    while j >= floor and text[j].isspace(): j -= 1
    return text[j] if j >= floor else ""


def _scan_span(text: str, start: int) -> tuple[int, bool, bool]:
    """Scan from an opening bracket. Returns (end, complete, has_json_chars)."""
    n = len(text); stack = [_OPEN[text[start]]]; i = start + 1; jsonish = False
    while i < n:
        c = text[i]
        if c in '"\u201c\u201d':
            jsonish = True; i = _skip_string(text, i); continue
        if c == "'":
            if _prev_sig(text, i, start) in "{[,:":
                jsonish = True; i = _skip_string(text, i); continue
            jsonish = True; i += 1; continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            k = text.find("\n", i); i = n if k < 0 else k; continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            k = text.find("*/", i + 2); i = n if k < 0 else k + 2; continue
        if c in _OPEN:
            stack.append(_OPEN[c])
        elif c in "}]":
            stack.pop()  # a mismatched closer still closes the innermost open bracket
            if not stack: return i + 1, True, jsonish
        elif c in ":,":
            jsonish = True
        i += 1
    return n, False, jsonish


def find_spans(text: str) -> list[tuple[int, int, bool]]:
    spans: list[tuple[int, int, bool]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in _OPEN:
            end, complete, jsonish = _scan_span(text, i)
            nxt = text[i + 1: i + 2]
            if complete and not jsonish and nxt.isalpha():
                i += 1; continue  # prose like [citation] or {braces}
            spans.append((i, end, complete)); i = end; continue
        i += 1
    return spans


def best_span(text: str) -> tuple[int, int, bool] | None:
    spans = [s for s in find_spans(text) if s[1] - s[0] >= 2]
    if not spans: return None
    for s in spans:
        if s[2]: return s
        break
    return spans[0]
