#!/bin/sh
# Build dist/llm-json-fixer.mcpb (MCPB bundle; the host runs it with `uv run`, so uv must be installed).
set -e
cd "$(dirname "$0")/.."
rm -rf build/mcpb && mkdir -p build/mcpb dist
cp -r pyproject.toml README.md LICENSE src build/mcpb/
cp packaging/manifest.json build/mcpb/
find build/mcpb -name __pycache__ -exec rm -rf {} +
npx -y @anthropic-ai/mcpb pack build/mcpb dist/llm-json-fixer.mcpb
