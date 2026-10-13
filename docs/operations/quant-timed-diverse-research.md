# Quant Autoresearch — duration-bounded diversified research

## Scope

The supervised Quant HTTP/MCP server limits an individual batch to 100
generations. `scripts/run_timed_diverse_research.py` is a **separate local,
detached orchestration controller** over the existing ResearchBatchService;
it starts additional bounded batches until a configured wall-clock deadline.
It is NOT a new MCP tool, a continuous hosted ChatGPT agent, or an LLM-driven
per-generation strategist. The worker performs local deterministic evaluation,
and local `mixed` replanning is restricted by predefined rules.

Data source: development-only QQQ Tiingo raw daily OHLCV,
2020-01-02–2025-12-31, 1,508 daily bars. PIT as-of vintages and corporate-action
adjustments have NOT been independently certified. A proper independent
QQQ/NASDAQ `SeriesDataSet` benchmark is absent; **`min_qqq_cagr_delta` is
intentionally omitted** rather than failing every candidate on a null
comparison. Such exploratory results must NOT be described as QQQ
outperformance, Sealed OOS approval, alpha, or live profitability.

## Diversification and safety

- Ten catalog strategy IDs, six families: mean_reversion, momentum, week52_high,
  volatility, golden_cross, consecutive, breakout_fail, strong_close,
  trend_filter, disparity. Only strategies with successful canonical read-only
  preflight are scheduled; at least five are required.
- Indicator lookbacks vary between experimental cycles; optional
  stop-loss/take-profit/trailing-stop and position sizing are rotated. Random
  and locally bounded Bayesian samplers alternate; this does not imply
  cross-batch Bayesian learning. Initial `mixed` exploratory runs alternate
  with `parameter` searches in later cycles. Four or fewer parameter domains
  per batch; 24 or fewer values per domain, validated by the canonical runner.
- Illustrative exploratory gates: `min_trades=5`,
  `min_annual_trades=5`. These are deliberately different from previous
  strict 30-trades/year searches; comparing raw pass rates without equal
  policies is invalid.
- `orders_enabled=false` (no broker/order calls), development data only,
  immutable Evidence, one batch worker at a time. An externally active
  research job is never cancelled or pre-empted by this controller.
- Research continues only while the controller process and host remain
  running. Abrupt container shutdown can interrupt the campaign; use existing
  per-batch Evidence/verified checkpoint recovery policy, not blind replay.
  The controller itself is **not** configured as an autostart Supervisor task.
- On deadline, start no new batch and ask any running batch to cancel
  cooperatively after its current generation. Any
  `CANCELLATION_PENDING` status requires explicit follow-up; do not kill
  a worker while it is persisting Evidence.

## Active example: 2026-10-13 Seoul time

The 60-minute campaign was **actually started** with:

- Campaign: `hour-20261013T101529Z`.
- Start (after canonical preflight): `2026-10-13T10:15:35.585981+00:00`
  / **19:15:35 KST**.
- Deadline: `2026-10-13T11:15:35.585981+00:00`
  / **20:15:35 KST**.
- Controller PID at start: `6195`.
- Each batch: 14 generations, 6 candidates, rotating strategies,
  3600-second overall budget; this is **not a global generation cap**.
- The campaign state is PRIVATE local, excluded from Git:
  `state/moon-http/research/system/timed-diverse-research/hour-20261013T101529Z/status.json`
  plus append-only `events.jsonl` and corresponding per-job immutable
  research Evidence and final reports.
- Confirmed after 5 elapsed minutes: 5 completed batches/70 generations,
  420 candidate evaluations, 6th batch underway, 6 distinct strategies
  visited, controller failure count 0. This observation is **not** a final
  profitability or 60-minute completion claim.

### Monitor (inside Moon container)

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
path = Path(
    "state/moon-http/research/system/timed-diverse-research/"
    "hour-20261013T101529Z/status.json"
)
report = json.loads(path.read_text())
for field in (
    "campaign_id", "status", "started_at_utc", "deadline_at_utc",
    "elapsed_seconds", "batches_started", "batches_completed",
    "generations_completed", "evaluated_candidates",
    "strategy_ids_visited", "current_job_id", "failure_count",
):
    print(field, report.get(field))
PY
```

Per-job progress/report can also be queried through the connected
`get_research_batch_status(job_id=...)` or
`get_research_batch_report(job_id=...)` for the current job ID, or by
reading the campaign `batch_records` after its 60-minute window.

To **request** a graceful early stop, create a file named `STOP` in the
specific private campaign directory. The controller checks it and requests
the current batch stop safely; do not issue a remote kill or remove the
Evidence database. The active controller lock
`state/moon-http/research/system/timed-diverse-research/active.lock`
prevents concurrently scheduled campaign controllers.

## Validation and release boundary

Dry-run canonical preflight: **10/10** catalog source strategies READY_WITH_WARNINGS
(warnings reflect dataset provenance and limited preview). Five isolated
tests cover source ordering, bounded parameter domains, inter-cycle changes,
exploratory request gates and time-deadline stop; all passed. Ruff PASS and
Mypy PASS on 197 Python modules.

A real 60-minute **completed** acceptance may be recorded only after the
campaign status becomes `COMPLETED_TIME_BUDGET`, with all launched jobs
accounted for and no active worker. The initial `RUNNING` observation only
proves successful start and measured progress.
