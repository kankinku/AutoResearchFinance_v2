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
```

The local pipeline is callable through `orchestration.pipeline.GenerationPipeline`. It
executes candidate generation, IR backtests, metrics, robustness checks, validation,
selection, and abstract knowledge extraction. Parquet datasets must carry
`dataset_version` and `data_zone` metadata. The Docker runner mounts input read-only,
disables networking, drops capabilities, and writes only to the run output directory.

Paper trading is available only after an exact Champion-hash paper approval. The live
KIS order capability is intentionally absent from the research package; a live deployment
also needs a real account, data provider, calendar, image digest, and human approval.
