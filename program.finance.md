# AutoResearchFinance Program Contract

This repository runs a finance-specific autoresearch loop. Candidate generation is editable; evaluation, verification, promotion policy, and data policy are fixed harness code unless a human explicitly upgrades the policy.

## Editable Surface

The LLM may propose only these research artifacts:

- `strategySpec` objects matching `af-spec/v1`
- `specPatch` descriptions that explain the intentional changes
- candidate summaries, next mutation hints, and condition inventory
- hypotheses about failures, loss zones, and follow-up mutations

The LLM must not hand-author Pine as the source of truth. Pine is generated deterministically from `strategySpec`.

## Evaluation Firewall

The following paths are fixed evaluation infrastructure:

- `src/evaluation/`
- `src/automation/local-backtest/`
- `src/automation/tradingview/`
- `config/objective.*`
- `config/targets/*`
- `src/state/`

Autonomous mutation prompts must not ask the LLM to change these paths. Human policy upgrades may change them only with tests that prove promotion gates still reject local-only candidates.

## Promotion Rule

Local backtests are screening evidence only. A local record may enter the archive, frontier, or calibration queue, but it cannot replace the champion in steady state.

Champion replacement requires all of the following:

- a matching `local_evaluation` and `tv_verification` pair with the same `candidateId` and `candidateHash`
- `tvCalibrationStatus === "verified_match"`
- non-major local/TradingView parity
- walk-forward OOS pass
- verified promotion score at or above the trial-budget-adjusted threshold

If TradingView is unavailable, candidates remain in the frontier or calibration queue. The active champion is not replaced by local evidence.

## Holdout Policy

Automatic loops may use local screening, walk-forward folds, and regime diagnostics. Canary holdout exposure is sealed by default and must not be opened by the autonomous loop. Canary review is a human operation.

