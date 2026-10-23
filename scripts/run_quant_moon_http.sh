#!/usr/bin/env bash
# Distinct Moon-style OAuth service, loopback only, no Moon key reuse.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STATE="$ROOT/state/moon-http"
KEY="$STATE/oauth/approval-key"
PIN="$STATE/oauth/public-base-url"
OAUTH_DB="$STATE/research/oauth/quant-oauth.sqlite"
# Existing-identity recovery ONLY. Never bootstrap an OAuth approval key, issuer
# pin, or client database on a fresh/partial mount. Check BEFORE any mkdir or
# Python imports that could create state. Provisioning requires a separate,
# explicitly authorized workflow; this production launcher never provisions.
if [[ -L "$KEY" || -L "$PIN" || -L "$OAUTH_DB" ||
      ! -s "$KEY" || ! -s "$PIN" || ! -s "$OAUTH_DB" ]]; then
    echo 'Original Quant OAuth key, URL pin, or database missing; refusing startup without existing identity' >&2
    exit 78
fi
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo 'Quant virtual environment missing' >&2
    exit 1
fi
cd -- "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
# Validate existing OAuth DB schema, pinned issuer URL and file permissions
# using read-only I/O before the service can instantiate its OAuth store.
"$ROOT/.venv/bin/python" -m scripts.quant_mcp_identity_guard --root "$ROOT" >/dev/null
PINNED_BASE="$("$ROOT/.venv/bin/python" -m scripts.quant_public_url \
 --pin "$STATE/oauth/public-base-url" --oauth-db "$OAUTH_DB")"
if [[ -n "${QUANT_MCP_PUBLIC_BASE:-}" && "$QUANT_MCP_PUBLIC_BASE" != "$PINNED_BASE" ]]; then
    echo 'Quant public URL conflicts with durable OAuth URL pin; refusing change' >&2
    exit 1
fi
export QUANT_MCP_PUBLIC_BASE="$PINNED_BASE"
exec "$ROOT/.venv/bin/python" -m integrations.chatgpt_mcp_http \
 --project-root "$ROOT" --state-dir "$STATE/research" \
 --host 127.0.0.1 --port 8787 \
 --public-url "$QUANT_MCP_PUBLIC_BASE" --approval-key-file "$KEY"
