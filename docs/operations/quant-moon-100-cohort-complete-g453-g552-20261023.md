# Quant AutoResearch 100-generation clone cohort — verified COMPLETE (2026-10-23 KST)

## Outcome / user request

User requested to continue the remaining 53 after previously observing 47/100. The **already running process was not relaunched** or duplicated. Its original managed Moon session `7916b9d8-7f4a-4060-9557-9f0935e7e213`, PID37928, advanced from G499 to **G552**, then exited **0** with:
- `SUMMARY {"completed":552,"requested":552,"processed_this_invocation":100,"controller":"DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM","status":"COMPLETED"}`
- `COHORT COMPLETE 453 THROUGH 552`.
- `cohorts/G453-G552-20261023-moon-stress.json`: `state=COMPLETED`, `completed=552`, end at 2026-10-22 16:02:57.658166 UTC (2026-10-23 01:02:57 KST).
- Authoritative `AcademicMCPCheckpointService.get()`: `552 / 552 COMPLETED`, phase `COMPLETED`, orders OFF and independent OOS approval OFF.

## Invariant / provenance checks

This is an **isolated clone of the new academic QQQ development lineage** (separate from the earlier missing official legacy G350 runtime and separate from the manually ChatGPT-authored G453 clone). Data is 1,508 reused QQQ daily bars spanning 2020-01-02 through 2025-12-31; not independently point-in-time certified and not sealed OOS.

- Source G452/452 **untouched**, final parent evidence SHA `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`.
- Clone `state/moon-http/quant-moon-bounded-100-20261023/research/academic-gpt-checkpoints`: **552** consecutive generation rows, 552 unique evidence hashes, **100 novel effective signal hashes** among G453–G552, continuous previous evidence hash chain PASS.
- Latest G552 evidence SHA `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`.
- Gateway `experiment_reports`: **552** persisted (incl. historical G1–G452); `generation_timings`: **552**. All 3 SQLite DBs `PRAGMA integrity_check=ok`; gateway stage `COMPLETED`.
- Live read-only dashboard `127.0.0.1:8082/api/status`: `completed=552`, `requested=552`, `additional_completed=100`, `additional_target=100`, `status=COMPLETED`, `phase=COMPLETED`, `proof_chain_ok=true`, `research_running_confirmed=false`. User URL retains existing Basic Auth via nginx at `127.0.0.1:2999/academic/` or HTTPS `project-moon.taild689f9.ts.net/quant-research/`.

## Measured costed DEVELOPMENT-only results of the 100 independent strategy candidates

| Metric | Actual measured G453–G552 |
| --- | ---: |
| Candidates completed | 100 / 100 |
| Individual candidate mean total return | **+14.46%** |
| Median total return | **+7.02%** |
| Individual candidate mean MDD | **41.13%** |
| Median MDD | **38.04%** |
| Return positive / nonpositive | **59 / 41** |
| MDD <= 30% | **18 / 100** |
| MDD > 30% | **82 / 100** |
| Trades among new candidates | 35–736 closed trades, mean **320.54** |
| Maximum return, regardless of risk: G454 | **+126.70%, MDD 34.95%, 123 trades** — fails MDD30 |
| Best with MDD <= 30% and >=30 closed trades: G465 | **+105.90%, MDD 25.88%, 95 trades** — in-sample only |
| Worst return: G500 | **−70.68%, MDD 74.29%, 604 trades** |
| Last candidate: G552 | **+39.81%, MDD 29.96%, 445 trades** |

First 47 new generations G453–G499: average candidate return **+19.21%**, mean MDD **36.72%**, MDD30 qualifying **16/47**. Next 53 new generations G500–G552: average return **+10.24%**, mean MDD **45.04%**, MDD30 qualifying **2/53**. The newly enumerated candidates generally grew riskier; a longer deterministic rule search is NOT proof of convergent algorithm improvement. Dashboard currently ranks headline 'eligible' on >=30 closed trades only; **this is not MDD-qualified or independent OOS approval**. The historical reference QQQ simple price-only buy-and-hold on this same reused development period was about **+187.77%**; none of these top return figures demonstrates alpha versus that reference.

**Causal limits:** Per-candidate backtest returns are independent scores against the SAME time period, **not** compounded generational investment returns or a portfolio NAV. The controller implements a GPT-designed deterministic mutation grid and scripted measured-trade diagnostics with S7, **not 100 independent new LLM calls**. No live broker, OOS, paid API provider, or OAuth resets. Investment readiness and model-autonomy T4 are still unverified.

## Operational disposition

The 100-generation *engine stress-test* is finished and safely inspectable from the dashboard. The old source G452 is immutable, no concurrent duplicate worker. No changes to fixed URL, credential, project Moon or OAuth, no live trading. The proper next research gate is verified per-generation model-authored experiments (10→100) with provenance; before describing a strategy as risk-acceptable, apply MDD <=30%, >=30 trades and independent out-of-sample controls rather than displaying only highest DEVELOPMENT return.
