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
python cli.py import-strategies --source path\to\strategy.py --strategies-dir strategies
python cli.py import-strategies --repo https://github.com/ORG/REPO.git --ref main --kis-presets
python cli.py plan-generation --parent champion-1 --method random --count 32 --seed 7
python cli.py list-features
python cli.py run-generation --source strategies\normalized\golden_cross.json --data data\daily.parquet --method random --count 8 --seed 7 --domain '{"name":"indicators.sma_fast.period","values":[5,10,20]}'
python cli.py set-mode --state-dir state --mode paper
python cli.py mode --state-dir state
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
python cli.py research-intent --state-dir state --env-file .env --project-root .
```

For Codex Desktop, the MCP system orchestrator can preflight and start the local
dashboard, research detector, and isolated Docker backtest worker together. See
`docs/operations/system-orchestrator.md` for registration and the natural-language
command flow.

The local paper operations dashboard is available at `http://127.0.0.1:8080/` after
starting the last command. It reports the effective paper-only mode, sanitized KIS
account snapshot, evaluation ledger, Champion strategy, generation trend, and worker
heartbeat state. See `docs/operations/paper-dashboard.md` for the safety boundary and
refresh behavior.

`import-strategies` is the safe external-strategy intake path. It scans local files or
clones a public GitHub repository at a specified ref into a temporary directory, then
uses AST/static analysis only. KIS builder presets can be imported with
`--kis-presets`; the ten preset files under `strategy_builder/strategy_core/preset` use
the same conversion and duplicate-detection path as any other source. Imported and
normalized records are written under `strategies/`, while dynamic or non-representable
logic is retained as `REVIEW_REQUIRED` with a reason. No external Python source is
executed and no order endpoint is called.

Use `--dry-run` to inspect counts without writing:

```powershell
python cli.py import-strategies --repo https://github.com/ORG/REPO.git --ref main --kis-presets --dry-run
```

The dashboard's 접힌 `전략 카탈로그` section reads `strategies/catalog.json` and shows
conversion status, source path, duplicate classification, and review reasons. A
successful import is not a Champion promotion; run the approved backtest pipeline
separately before considering a strategy for Frontier.

## How to use the system

Run commands from the repository root. Create the state directory once, keep the
trading mode set to paper, refresh the read-only KIS snapshot when needed, and leave
the dashboard process running in its own terminal:

```powershell
python cli.py init --state-dir state
python cli.py set-mode --state-dir state --mode paper
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/`. The dashboard's Quick Guide contains the same commands
with copy buttons. `init` is only for a new state directory; do not repeat it over a
state directory whose experiment history you want to keep. `dashboard-refresh` reads
paper account/quote data; it does not place orders.

For Codex Desktop, register `.codex/config.toml.example` in the Desktop MCP settings.
The local MCP server can then be started with:

```powershell
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

In Codex Desktop, use `get_dashboard_status` and `get_research_context` first, submit
the resulting structured intent with `submit_research_intent`, and run only an
approved local evaluation with `run_evaluation`. The server has no order or live
account tool. For a non-interactive alternative, authenticate the Codex CLI and run:

```powershell
codex login status
python cli.py research-intent --state-dir state --env-file .env --project-root .
```

The command records a validated intent in `state/llm/intents.jsonl`; the dashboard
shows the provider state in the Codex LLM card. Keep KIS values only in the ignored
`.env` file, never in a prompt or source file.

## Codex Desktop connection

Codex Desktop can connect to the local stdio MCP server using the credential-free
example in `.codex/config.toml.example`. Copy its section into the trusted Codex
configuration or register the same command in Desktop MCP settings:

```powershell
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

The exposed tools are limited to sanitized research context, the feature catalog,
dashboard status, validated intent submission, and local evaluation. There is no
order, live-account, credential, arbitrary-write, raw-market, or sealed-OOS tool.
For an unattended/local subprocess call, use `research-intent`; it invokes the
installed `codex exec` command and revalidates its structured output locally. The
interactive Desktop conversation is not implicitly reused by a separate `codex exec`
process. Codex CLI authentication is taken from its own saved login; KIS secrets are
removed from the child environment.
The CLI adapter accepts `QUANT_CODEX_MODEL` for a model supported by the installed
CLI; the example uses `gpt-5.4-mini`.

The local pipeline is callable through `orchestration.pipeline.GenerationPipeline`. It
executes candidate generation, IR backtests, metrics, robustness checks, validation,
selection, and abstract knowledge extraction. Parquet datasets must carry
`dataset_version` and `data_zone` metadata. The Docker runner mounts input read-only,
disables networking, drops capabilities, and writes only to the run output directory.

### 반복 백테스트 실행

`run-generation`에 `--domain`을 반복 지정하면 Strategy IR의 파라미터를 변경해
후보를 만듭니다. 도메인을 지정하지 않으면 `--count`와 관계없이 기준선 후보
1개만 실행합니다.

```powershell
python cli.py run-generation `
  --source strategies\normalized\golden_cross.json `
  --data data\daily.parquet `
  --series-data data\external-series.parquet `
  --method grid --count 9 --seed 7 --min-trades 0 `
  --domain '{"name":"indicators.sma_fast.period","values":[5,10,20]}' `
  --domain '{"name":"risk.position_size_pct","values":[25,50,75]}' `
  --state-dir state
```

`--series-data`는 `ParquetDataProvider.write_series` 계약을 따르는 외부 시계열
파일입니다. VIX·금·DXY·각국 2년/10년/20년 금리와 같은 전략 입력을 제공할 수
있습니다. QQQ와 NASDAQ 시계열이 모두 있으면 동일 기간 벤치마크 비교가 추가되고,
매크로·금리만 있으면 벤치마크 없이 전략 입력으로만 사용됩니다. 외부 데이터는
관측 시각과 `available_at`을 기준으로 as-of 정렬하여 미래 공개값을 차단합니다.

External price, macro, rate, and benchmark series use the same versioned Parquet
contract through `ParquetDataProvider.write_series/read_series`. The optional Feature
Registry exposes VIX, gold, DXY, QQQ, Nasdaq, and US/Japan/Korea 2-year, 10-year, and
20-year rate candidates. Any registered series can receive any registered transform on
`1m`, `5m`, `15m`, `1h`, `1d`, `1w`, or `1mo`; for example, `US20Y.close@1w:rsi(period=14)`.
A strategy selects
only the features it declares; no macro feature is implicitly mandatory. `list-features`
reports the current selectable catalog, and the dashboard exposes it at
`/api/features/catalog`.

The four audited indicator sources are represented by canonical FeatureSpecs with
aliases and semantic duplicate groups. `pythonpine` is treated as AGPL-3.0 and is not
vendored; its formulas are independently reimplemented. Profile, TPO, and tick
order-flow indicators require explicit data contracts. Account, order, network,
downloader, and plotting functions are never feature calculators.

Generation evaluation keeps the existing Fast/Full, robustness, walk-forward, OOS,
CSCV/CPCV, cost, and complexity checks. When benchmark data is supplied, it adds QQQ
total return and Nasdaq Composite comparison plus excess-return fields. Strategy risk
appetite and daily-loss behavior are recorded separately from the immutable system
emergency cutoff.

Paper trading is available only after an exact Champion-hash paper approval. The live
KIS order capability is intentionally absent from the research package; a live deployment
also needs a real account, data provider, calendar, image digest, and human approval.
