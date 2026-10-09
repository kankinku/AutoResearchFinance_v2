#!/usr/bin/env bash
# Distinct Moon-style OAuth service, loopback only, no Moon key reuse.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STATE="$ROOT/state/moon-http"
install -d -m 0700 "$STATE/oauth"
KEY="$STATE/oauth/approval-key"
if [[ ! -s "$KEY" ]]; then
    umask 077
    openssl rand -hex 32 > "$KEY"
    chmod 600 "$KEY"
fi
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo 'Quant virtual environment missing' >&2
    exit 1
fi
if [[ -z "${QUANT_MCP_PUBLIC_BASE:-}" ]]; then
    export QUANT_MCP_PUBLIC_BASE
    QUANT_MCP_PUBLIC_BASE="$($ROOT/.venv/bin/python - <<'PY'
from pathlib import Path
import re
source=Path('/shared/AGENTS.md').read_text(encoding='utf-8')
urls=sorted(set(re.findall(r'https://[a-zA-Z0-9.-]+\.ts\.net',source)))
if len(urls)!=1:
    raise SystemExit('Cannot derive a unique stable Moon Funnel URL')
print(urls[0]+'/quant')
PY
)"
fi
case "$QUANT_MCP_PUBLIC_BASE" in
  https://*.ts.net/quant) ;;
  *) echo 'Expected a Moon *.ts.net HTTPS /quant URL' >&2; exit 1 ;;
esac
cd -- "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/python" -m integrations.chatgpt_mcp_http \
 --project-root "$ROOT" --state-dir "$STATE/research" \
 --host 127.0.0.1 --port 8787 \
 --public-url "$QUANT_MCP_PUBLIC_BASE" --approval-key-file "$KEY"
