# Quant Autoresearch Harness

An LLM-assisted autonomous quantitative research platform.

The system separates responsibilities:

```text
LLM = research direction and interpretation
LOCAL = IR mutation, planning, analysis, and persistence
WORKER = isolated backtest execution
EVALUATOR = immutable statistical judgment
MEMORY = experiment and knowledge accumulation
```

Research is separate from KIS order execution. Live trading is denied by default and requires a separate, explicit human approval gate.

## Development

This repository targets Python 3.10+ and uses pytest, Ruff, and mypy. Install the development dependencies from `pyproject.toml`, then run:

```powershell
python -m pytest -q
ruff check .
python -m mypy .
```

The approved architecture and the complete implementation plan are in `docs/architecture/` and `docs/superpowers/plans/`.

## Quick start

```powershell
python cli.py init --state-dir state
python cli.py validate-strategy --source path\to\strategy.yaml
python cli.py import-strategy --source path\to\strategy.py
python cli.py plan-generation --parent champion-1 --method random --count 32 --seed 7
python cli.py list-features
python cli.py set-mode --state-dir state --mode paper
python cli.py mode --state-dir state
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

The local paper operations dashboard is available at `http://127.0.0.1:8080/` after
starting the last command. It reports the effective paper-only mode, sanitized KIS
account snapshot, evaluation ledger, Champion strategy, generation trend, and worker
heartbeat state. See `docs/operations/paper-dashboard.md` for the safety boundary and
refresh behavior.

The local pipeline is callable through `orchestration.pipeline.GenerationPipeline`. It
executes candidate generation, IR backtests, metrics, robustness checks, validation,
selection, and abstract knowledge extraction. Parquet datasets must carry
`dataset_version` and `data_zone` metadata. The Docker runner mounts input read-only,
disables networking, drops capabilities, and writes only to the run output directory.

External price, macro, rate, and benchmark series use the same versioned Parquet
contract through `ParquetDataProvider.write_series/read_series`. The optional Feature
Registry exposes VIX, gold, DXY, QQQ, Nasdaq, and US/Japan/Korea 2-year and 10-year
rate candidates. A strategy selects only the features it declares; no macro feature is
implicitly mandatory. `list-features` reports the current selectable catalog.

Generation evaluation keeps the existing Fast/Full, robustness, walk-forward, OOS,
CSCV/CPCV, cost, and complexity checks. When benchmark data is supplied, it adds QQQ
total return and Nasdaq Composite comparison plus excess-return fields. Strategy risk
appetite and daily-loss behavior are recorded separately from the immutable system
emergency cutoff.

Paper trading is available only after an exact Champion-hash paper approval. The live
KIS order capability is intentionally absent from the research package; a live deployment
also needs a real account, data provider, calendar, image digest, and human approval.
