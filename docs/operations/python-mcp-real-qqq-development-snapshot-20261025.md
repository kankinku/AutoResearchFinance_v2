# PythonMCP: isolated existing QQQ development data import (2026-10-25 KST)

**Work ID:** V05-PY-MCP-QQQ-DEV-IMPORT-01; **Q IDs:** Q04/Q09/Q11/Q13/Q15/Q17/Q20. **User value:** remove the missing-real-development-data blocker without reauthorizing a provider or altering original Quant research. **Scope:** immutable, unsealed development dataset only. **Next frozen work:** V05 cost/stat validation, then T4 genuine model invocation provenance and bounded 1→3→10→20 (then 100) GPT checkpoint cycles. **Not goals:** PIT/OOS attestation, model-provider attestation, live trading, changing original P5 or accepted product scope.

## Observed data and action

- Existing original development source: `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet` and neighboring `snapshot-origin.json`.
- Source metadata explicitly declares `NON_PIT_DEVELOPMENT_ONLY`, `vendor_confirmed=false`, `orders_enabled=false`, and 1,508 QQQ daily bars from 2020-01-02 to 2025-12-31.
- Checked raw file SHA-256 against pinned manifest: `94e1f5f118e6dc14d25dc95b654fcfd485f07bce251fb1c8a16d1843df638037`. Checked canonical dataset hash: `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`.
- New isolated importer `application/python_mcp_development_data.py`, CLI `scripts/prepare_python_mcp_development_data.py`, 7 focused tests. Import checks original SHA, canonical dataset hash, symbol, count, range, DEVELOPMENT zone, daily timeframe, no-orders manifest; prohibits destination symlink escape, silent overwrite, sealed OOS, or source aliasing. Copies only to gitignored `state/python-mcp/development-qqq/` and checks bytes again. No changes to original data, model auth/OAuth, research checkpoints or order routes.
- Actual fork destination now exists: `state/python-mcp/development-qqq/QQQ_2020-01-02_2025-12-31_raw.parquet`. Import CLI returned `VERIFIED_EXISTING_DEVELOPMENT_COPY`, `bars=1508`, `orders_enabled=false`, `independent_oos_approved=false`, `model_invocation_verified=false`, `generations_completed=0`.
- Quality flags `revisions_not_as_of` and `corporate_action_adjustment_unverified`; these are real limitations, not blockers to *development-only* testing, and prohibit PIT/OOS/performance certification.

## One-command reproducibility (inside existing Docker CMD session)

```bash
cd /shared/moon-workspace/AutoResearchFinance_PythonMCP
PYTHONPATH=. .venv/bin/python scripts/prepare_python_mcp_development_data.py --source /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet --manifest /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/data/market/public_yahoo_qqq/snapshot-origin.json
```

This command is idempotent and reads original data without changing it. It is **not** a generation launch command, and no user action is required when the file is already present.

## Acceptance and still missing

- Isolated data import: PASS, count/range/hash/zone validated; symlink and bad-hash rejection tested.
- Actual model-authored development QQQ new generations this task: **0**; Codex account already connected, but P4 model-provider invocation audit remains **unverified**. Existing fork synthetic Codex smoke 1 generation is separate and never promoted.
- No new login/API key, no OAuth change, no model turns ordered by this import, no external market provider download or OOS access, no orders.
- V05 real net-cost/stat acceptance and T4 independently attributed model calls: **BLOCKED/NOT RUN**. Automated 10–20 GPT research: **NOT RUN**. Full PIT/OOS/economic acceptance: **NOT RUN**.

## Verification result (2026-10-25 KST)

- Focused data-import tests: **7/7 PASS**.
- Scoped data ingestion + Codex account + signed MCP handoff + T4 controller + scope governance suite: **59/59 PASS** (69.57 s).
- Ruff for the new source, CLI and tests: **PASS**; mypy for the two new source files: **PASS**; `git diff --check`: **PASS**.
- Full repository pytest/mypy and economic PIT/OOS validation: **NOT RUN**.
