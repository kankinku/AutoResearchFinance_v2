# ADR — Quant V3 checkpoint, main and three separate research lanes

Date: 2026-10-27 KST. **Approved by the user's explicit request** to name the current complete Quant as V3, create a checkpoint and promote to `main`, and create separate branches for the three previously described research directions.

## Mapping to approved scope

- **Track 1:** Q02/Q05/Q06/Q07/Q08/Q09/Q10/Q14/Q15/Q17/Q18/Q20 (evolve StrategyIR, backtests, controlled analysis and parent inheritance).
- **Track 2:** Q05/Q07/Q09/Q10/Q12/Q14/Q18/Q20 (new *research purpose* detecting pre-crash/event regimes; predictive scoring is not yet an executable trading rule).
- **Track 3:** Q04/Q09/Q13/Q20, V01–V04/T5 and V07 (independent OOS evaluation of frozen candidates, not feedback for model search).
- Original Q01–Q20, V05→T4→V01–V04→V06→V07 gates remain binding. Splitting development lanes does **not** claim that the full release sequence has passed. This ADR authorizes *branch preparation and planning*, not changing orders, test approval or engine permission defaults.

## Choices

1. V3 code checkpoint: a new immutable annotated `quant-v3.0.0` tag on `main` pointing to current verified development code + V3 release records. No unrelated master history overwritten.
2. V3 data checkpoint: verify signed generation-150 Evidence SHA and 150 S7 records; 3 private SQLite online backups with hashes under the existing operator state folder, not Git.
3. Three independent branches and workspaces from the exact release commit. Code/data changes for one task may not pollute the others. Keep existing Quant deployed version/live URL/OAuth unchanged by these Git operations.
4. Track 2 event-definition thresholds and horizons are **hypotheses to agree/test**, not retroactively user-approved numeric thresholds; prohibit lookahead/leakage and train/test contamination.
5. Track 3 OOS selects frozen candidates and pass/fail criteria **before accessing any independent test interval**. If authoritative independent data is not available, say BLOCKED rather than fabricating validation.
6. The repository previously had default branch `master` and no `main`. Creating `main` is the requested promotion; modifying GitHub repository **default branch setting** or force-merging unrelated `master` history is a separate administrative action.

## Entry gates / non-goals

- Freeze G150 session final hash and original files; no generation execution in this organizational task.
- Cross-branch protection: no sharing mutable SQLite data, no copying credentials, no model SDK forks, no live orders, no sealed OOS leaks.
- Validate governance requirements, ensure tag/master unchanged, checkpoint state hashes consistent, push branch refs without force and record exact SHAs in the progress ledger.
