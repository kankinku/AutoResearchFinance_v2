#!/usr/bin/env bash
# Entrypoint for OpenAI Secure MCP Tunnel; no network listener or local LLM.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  printf 'Quant MCP virtual environment unavailable\n' >&2
  exit 1
fi
cd -- "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/python" -m integrations.chatgpt_mcp_stdio \
  --project-root "$ROOT" --state-dir "$ROOT/state"
