#!/usr/bin/env bash
# Distinct Moon-style OAuth service, loopback only, no Moon key reuse.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
STATE="$ROOT/state/moon-http"
install -d -m 0700 "$STATE/oauth"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo 'Quant virtual environment missing' >&2
    exit 1
fi
# Never silently reissue OAuth identity when a persistent approval database exists.
KEY="$STATE/oauth/approval-key"
OAUTH_DB="$STATE/research/oauth/quant-oauth.sqlite"
if [[ ! -s "$KEY" ]]; then
    if [[ -e "$OAUTH_DB" ]]; then
        echo 'Quant OAuth key missing; refusing to rotate existing authentication' >&2
        exit 1
    fi
    umask 077
    openssl rand -hex 32 > "$KEY"
    chmod 600 "$KEY"
fi
cd -- "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PINNED_BASE="$("$ROOT/.venv/bin/python" -m scripts.quant_public_url \
 --pin "$STATE/oauth/public-base-url" --oauth-db "$OAUTH_DB")"
if [[ -n "${QUANT_MCP_PUBLIC_BASE:-}" && "$QUANT_MCP_PUBLIC_BASE" != "$PINNED_BASE" ]]; then
    echo 'Quant public URL conflicts with durable OAuth URL pin; refusing change' >&2
    exit 1
fi
export QUANT_MCP_PUBLIC_BASE="$PINNED_BASE"
# Upgrade imported application code only; keep ROOT / pinned URL / OAuth state untouched.
SOURCE_ROOT="/shared/moon-workspace/AutoResearchFinance_v2-quant-mcp-runtime-091d066"
[[ -d "$SOURCE_ROOT/integrations" && -f "$SOURCE_ROOT/application/academic_checkpoint_service.py" ]] || exit 1
# Refuse a moved or edited code worktree: production is commit-pinned.
EXPECTED_SOURCE_SHA="091d066f700be36d61467380f7ba393cd1c42b5d"
[[ "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA" ]] || exit 1
[[ -z "$(git -C "$SOURCE_ROOT" status --porcelain)" ]] || exit 1
export PYTHONPATH="$SOURCE_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd -- "$SOURCE_ROOT"
exec "$ROOT/.venv/bin/python" -m integrations.chatgpt_mcp_http \
 --project-root "$ROOT" --state-dir "$STATE/research" \
 --host 127.0.0.1 --port 8787 \
 --public-url "$QUANT_MCP_PUBLIC_BASE" --approval-key-file "$KEY"
