#!/usr/bin/env bash
# Non-mutating diagnostics: never print values of tunnel IDs, keys or tokens.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
OFFLINE=false
case "${1:-}" in
  --offline) OFFLINE=true ;;
  "") ;;
  *) printf 'Usage: %s [--offline]\n' "$0" >&2; exit 2 ;;
esac
if [[ -x "$ROOT/.venv/bin/python" && -f "$ROOT/integrations/chatgpt_mcp_stdio.py" && -x "$ROOT/scripts/run_chatgpt_mcp_stdio.sh" ]]; then
  echo 'MCP_STDIO=READY'
else
  echo 'MCP_STDIO=MISSING'
fi
if command -v tunnel-client >/dev/null 2>&1; then
  echo 'TUNNEL_CLIENT=AVAILABLE'
else
  echo 'TUNNEL_CLIENT=MISSING'
fi
if [[ -n "${CONTROL_PLANE_API_KEY:-}" ]]; then
  echo 'CONTROL_PLANE_API_KEY=PRESENT'
else
  echo 'CONTROL_PLANE_API_KEY=NOT_SET'
fi
if [[ -n "${QUANT_TUNNEL_ID:-}" ]]; then
  echo 'QUANT_TUNNEL_ID=PRESENT'
else
  echo 'QUANT_TUNNEL_ID=NOT_SET'
fi
if [[ "$OFFLINE" == false ]]; then
  if command -v curl >/dev/null 2>&1 && curl --silent --show-error --head --max-time 10 'https://api.openai.com' --output /dev/null 2>/dev/null; then
    echo 'HTTPS_EGRESS=REACHABLE'
  else
    echo 'HTTPS_EGRESS=UNVERIFIED'
  fi
fi
