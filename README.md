# llm-json-fixer

**Use when** an agent needs to repair invalid JSON from an LLM (code fences, trailing commas, single quotes, Python `True`/`None`, truncated output) without calling another LLM.

An MCP server that turns broken JSON from language models into valid JSON. It is **deterministic**: no LLM calls, no network access, no API key, and the same input always gives the same output. It never invents data. When there is no JSON in the input, it says so instead of making something up.

It is available on Smithery as [`markusisaksson/llm-json-fixer`](https://smithery.ai/servers/markusisaksson/llm-json-fixer).

## Tools

| Tool | What it does |
|---|---|
| `repair_json` | Repairs malformed model output: code fences, surrounding prose, trailing commas, single and smart quotes, unquoted keys, comments, Python/JS literals (`True`, `None`, `NaN`, `undefined`), hex, `+1` and `.5` numbers, missing commas, mismatched brackets, unescaped quotes and newlines, double-encoded JSON and truncated output. It takes an optional JSON Schema and has `lenient` and `strict` modes, and it can return a diff. |
| `extract_json` | Finds JSON objects and arrays inside prose or Markdown. It returns the best one or all of them, each repaired, with character spans. |
| `validate_json` | Validates against a JSON Schema (drafts 2020-12, 2019-09, 7, 6 and 4). Errors carry a JSON Pointer path and the failing keyword. Text input is repaired first unless you set `repair=false`. |
| `coerce_to_schema` | Coerces values toward a schema: `"41"`→`41`, `"yes"`→`true`, `41.0`→`41`, enum case, scalar→array, `"null"`→`null`. It drops extra keys when `additionalProperties` is false and can fill defaults. Missing values are never invented. |
| `complete_json` | Closes truncated or still-streaming JSON into a valid value and keeps the partial values. Useful for streaming previews. |
| `diff_json` | Compares two JSON texts and returns RFC 6902-style `add`/`remove`/`replace` operations. |

Every repair result lists its `changes` (for example `stripped_code_fence`, `removed_trailing_commas`, `completed_truncated_json`), plus `changed`, `truncated` and `warnings`. A failure has a typed `code`: `NO_JSON`, `TRUNCATED`, `STRICT_REFUSED`, `UNRECOVERABLE`, `TOO_LARGE` or `BAD_INPUT`.

**Modes**
- `lenient` (default) repairs everything it reasonably can.
- `strict` applies only lossless fixes: fences, prose, comments, trailing commas, quote style and Python literals. It refuses anything that would need guessing, such as missing commas or truncation.

**Truncation.** By default `repair_json` drops the value that was still being written when the output was cut off (a half string, number or literal), so partial data is never presented as complete. `complete_json` keeps those partial values.

## Example

```text
repair_json(text="Sure! ```json\n{'name': 'Ada', tags: ['x',], ok: True, // note\n \"score\": NaN\n```")
→ {"ok": true, "json": {"name": "Ada", "tags": ["x"], "ok": true, "score": null},
   "changes": [{"fix": "stripped_code_fence"}, {"fix": "non_json_literal", "count": 1}, ...]}
```

## Benchmark

All servers I could find on Smithery for JSON repair or validation were tried on **2026-10-15** through Smithery Connect. Four could be called and returned results:
- [jsonaut](https://smithery.ai/servers/progamerplayzyt97/jsonaut)
- [bristlecone-logic](https://smithery.ai/servers/joshua-wkl4/bristlecone-logic)
- [jsonmend](https://smithery.ai/servers/mike-tusa/jsonmend)
- the [`json_repair`](https://pypi.org/project/json-repair/) Python library (v0.64), called directly as a baseline

Scoring compares each parsed result with the expected value. A result is counted as **hallucinated** when the server returns JSON containing strings that are not in the input, including JSON returned for input that has none.

**Own corpus (71 cases).** 58 core repair cases across 19 categories, 3 inputs with no JSON, 5 schema-coercion cases and 5 schema-validation cases. The corpus includes a 490 KB document and 400-level nesting.

| Server | Core repair (58) | No-JSON refusal (3) | Schema coerce (5) | Schema validate (5) | Total | Hallucinated | Median latency |
|---|---|---|---|---|---|---|---|
| **llm-json-fixer** | **58** | **3** | **5** | **5** | **71/71** | **0** | <1 ms (local) |
| json_repair (library) | 51 | 3 | 1 | 5 | 60/71 | 1 | <1 ms (local) |
| bristlecone-logic | 51 | 0 | 1 | 3 | 55/71 | 3 | 382 ms |
| jsonaut | 44 | 3 | 1 | 5 | 53/71 | 2 | 352 ms |
| jsonmend | 8* | 3 | 0 | 0 | 11/71 | 0 | 446 ms |

\* jsonmend's anonymous tier allows a limited number of requests per day. The quota ran out partway through the run, so its score mostly reflects rate-limit errors and not repair quality.

**Held-out set (40 cases).** I tuned against the corpus above, so I also ran a second set of 40 realistic broken outputs. They were written independently, by a different model, after the repair code was finished, and were not used for tuning.

| Server | Correct | Hallucinated | Median latency |
|---|---|---|---|
| **llm-json-fixer** | **39/40** | **0** | <1 ms (local) |
| json_repair (library) | 28/40 | 2 | <1 ms (local) |
| jsonaut | 26/40 | 2 | 352 ms |
| bristlecone-logic | 24/40 | 6 | 438 ms |

The one held-out miss is a string value that contains unescaped JSON-like text, which is ambiguous.

Hosted latencies include the Smithery Connect proxy round trip from Sweden, so compare them with each other and not with the local numbers. The other servers I looked at could not be benchmarked: their endpoints returned 404/5xx, or they required a paid account or an API key.

The corpus and held-out set are in [`tests/data`](tests/data); generator, scoring scripts and raw results are in [`bench/`](bench). Both sets run as regression tests.

## Install

Through Smithery, or locally with [uv](https://docs.astral.sh/uv/):

```json
{ "mcpServers": { "llm-json-fixer": { "command": "uvx", "args": ["--from", "git+https://github.com/MarkusIsaksson1982/llm-json-fixer", "llm-json-fixer"] } } }
```

Development:

```sh
pip install -e .[dev]
pytest                      # 250 tests
python scripts/smoke.py     # starts the server over stdio and calls every tool
packaging/build_mcpb.sh     # builds dist/llm-json-fixer.mcpb
```

## Fixtures and repair catalogue

[`fixtures/`](fixtures) holds one folder per failure class (`trailing_comma/`, `truncated/`, `python_literals/`, `no_json/` and so on). Each case is a plain `<id>.input.txt` with the broken model output and `<id>.expected.json` with the accepted result. [`docs/REPAIR-CATALOGUE.md`](docs/REPAIR-CATALOGUE.md) shows every case with its input, the repaired output and the fixes applied. Both are generated from `tests/data/corpus.json` by `scripts/export_fixtures.py`, and a test checks that they are in sync.

## Test queries

These five queries should find this repository in a code search such as [Xerj](https://xerj.dev); each lists the file expected in the top 5 results. Checked locally with `xerj code` (v1.0.0-rc.100) on 2026-10-29.

| Query | Expected file |
|---|---|
| `repair invalid JSON from LLM output without calling an LLM` | `src/llm_json_fixer/core.py` |
| `remove trailing commas in LLM JSON` | `docs/REPAIR-CATALOGUE.md` |
| `repair truncated JSON max_tokens cut-off` | `docs/REPAIR-CATALOGUE.md` |
| `convert Python True None literals to JSON` | `docs/REPAIR-CATALOGUE.md` |
| `extract JSON from markdown code fence in model response` | `src/llm_json_fixer/extract.py` |

## Credits

Tolerant parsing is built on [`json_repair`](https://github.com/mangiucugna/json_repair) by Stefano Baccianella (MIT). llm-json-fixer adds the following on top:
- prose and fence extraction
- token pre-passes (non-JSON literals, number forms, truncated literals)
- a strict mode
- truncation policies that never fabricate values
- double-encoded JSON decoding
- schema coercion and validation
- change reporting and diffs

Schema validation uses [`jsonschema`](https://github.com/python-jsonschema/jsonschema).

## License

MIT
