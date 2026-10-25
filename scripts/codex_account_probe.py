"""Codex account-only readiness for the isolated Python MCP fork.

No login, model turn, checkpoint mutation, credential output or Quant session.
"""

from __future__ import annotations

import json

from application.t4_codex_host_preflight import probe_installed_codex_account


def main() -> int:
    readiness = probe_installed_codex_account()
    print(json.dumps(readiness, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
