# Seed Strategy And Loss-Zone Analysis Design

## Summary

AF will stop treating `baseline.pine` as a generic starter only. Instead, AF will keep one curated seed strategy as the fixed reference point for research and use the latest accepted candidate as the working head for iterative improvement.

AF will also upgrade post-evaluation analysis so that each evaluated candidate's own Strategy Tester trades are matched against QQQ 2-hour market context. The system will extract loss-heavy zones and likely failure reasons, then feed that analysis back into the next mutation brief.

This design does not import or analyze arbitrary external TradingView strategies. The analysis scope is limited to strategies generated and evaluated by AF itself.

## Goals

1. Keep one known-good seed strategy as the stable starting reference for research.
2. Allow tasks to improve from AF's own evaluated candidates while preserving the seed as a separate anchor.
3. Detect where losses happen in QQQ 2-hour context, not just whether a candidate scored poorly.
4. Convert loss analysis into structured mutation guidance instead of free-form narrative only.
5. Preserve AF's layered knowledge model: `policy / evidence / ledger / views / taxonomy`.

## Non-Goals

1. Importing trades from user-specified or third-party TradingView strategies.
2. Building a general multi-symbol market context engine in this phase.
3. Replacing the existing objective function with a fully new scoring framework.
4. Adding trade-trigger logging beyond the Strategy Tester trade records already collected.

## Approved Decisions

### 1. Curated Seed Strategy

AF will store the provided Pine logic as a curated seed file:

- `strategies/source/seed_primary.pine`

The strategy content will be preserved, but the public-facing strategy title inside the Pine source will be renamed to an AF-owned neutral name. The default name for this phase is:

- `AF Seed 01`

`strategies/source/baseline.pine` will continue to exist, but its meaning changes:

- `seed_primary.pine`: curated reference seed
- `baseline.pine`: active seed snapshot used by the runtime
- `runtime_target.pine`: current file written for actual evaluation execution

If there is no accepted candidate yet, mutation begins from the active seed. Once accepted candidates exist, mutation continues from the latest accepted head, while the seed remains as the anchor reference for comparison and brief construction.

### 2. Improvement Source Of Truth

AF will distinguish between two strategy references in the mutation loop:

- `seedStrategy`: fixed curated reference
- `acceptedHead`: latest accepted candidate in the main line

The next mutation should be generated against the current accepted head when it exists. The seed is not replaced by accepted candidates. Instead, it stays available as:

- the original improvement anchor
- the fallback mutation source if no accepted candidate exists
- the reference point for reporting "how far current candidates moved away from the original thesis"

### 3. Loss Analysis Scope

Loss analysis will use only:

- the candidate AF just evaluated
- that candidate's Strategy Tester trades
- QQQ 2-hour market context derived from market data

The system will not read arbitrary external trades. This keeps the loop self-consistent and ensures every diagnosis maps directly to code that AF generated and evaluated.

## Architecture Changes

### 1. New Seed Strategy Layer

AF will add a small seed strategy layer on top of the current source layout.

New responsibilities:

- load the curated seed from `seed_primary.pine`
- materialize it into `baseline.pine` when bootstrapping or resetting the active seed
- expose seed metadata to mutation brief generation

Expected module:

- `src/research/seed-strategy.ts`

Expected capabilities:

- read curated seed
- read active seed
- sync curated seed into active seed
- expose seed summary for ledgers and briefs

### 2. QQQ 2-Hour Context Cache

AF will add a market context module specialized for QQQ 2-hour bars.

Expected evidence path:

- `state/pi-autoresearch/evidence/results/qqq-2h-context.json`

Expected responsibilities:

- fetch recent QQQ price history
- resample or normalize into 2-hour bars if needed
- compute context features per bar
- cache the result locally for reuse

Expected features per bar:

- timestamp
- OHLCV
- EMA20 / EMA50 / EMA200
- ATR14 and ATR percent
- RSI14
- Bollinger band width
- short return windows such as `ret3` and `ret10`
- regime label such as `trend_up`, `trend_down`, `range`, `range_squeeze`, `volatile`
- distance to key EMAs
- overextension markers where useful

Expected module:

- `src/research/market-context.ts`

### 3. Trade Context Enrichment

After evaluation, AF will enrich the candidate's own trades by matching each trade's `entryTime` and `exitTime` to the nearest QQQ 2-hour bar.

Expected evidence path:

- `state/pi-autoresearch/evidence/results/trade-context-<iteration>-<candidateId>.json`

Per-trade enrichment should include:

- nearest QQQ 2-hour entry bar
- nearest QQQ 2-hour exit bar
- entry regime
- exit regime
- entry RSI / ATR percent / BB width
- exit RSI / ATR percent / BB width
- entry relative position to EMA20 / EMA50 / EMA200
- exit relative position to EMA20 / EMA50 / EMA200
- flags such as `overextendedEntry`, `counterTrendEntry`, `lateEntry`, `weakExit`

Expected module:

- `src/research/trade-context.ts`

### 4. Loss-Zone Analysis

AF will derive structured loss analysis from the enriched trades.

Expected evidence path:

- `state/pi-autoresearch/evidence/results/loss-analysis-<iteration>-<candidateId>.json`

The analysis should at minimum identify:

- which market regimes are overrepresented among losing trades
- whether losses cluster around overextended entries
- whether losses happen mostly in counter-trend entries
- whether losses are caused by exits that occur too late
- whether losses cluster after repeated same-direction entries
- whether losses are concentrated in a small number of severe drawdown segments

Expected top-level outputs:

- `lossAnalysisSummary`
- `lossHotZones`
- `lossPatterns`
- `repairPriorities`

Expected module:

- `src/research/loss-analysis.ts`

## Mutation Brief Changes

`MutationBrief` will be extended so the LLM sees not only objective and recent failures, but also the structural context for improvement.

New brief fields:

- `seedStrategy`
  - `candidateId`
  - `summary`
  - `studyTitle`
- `improvementSource`
  - `"seed"` or `"accepted_head"`
- `recentLossAnalysis`
  - concise structured summary of the latest evaluated candidate's losses
- `lossHotZones`
  - top 3-5 loss-heavy contexts
- `repairPriorities`
  - mutation instructions derived from the loss analysis

Example directions the system should generate:

- avoid counter-trend B2 entries during `trend_down` and high ATR regimes
- reduce overextended entries when price is above EMA20 by more than threshold
- tighten bearish confirmation exits in range-to-down transitions
- reduce slot replacement aggressiveness when repeated losses cluster in the same regime

The brief should remain machine-oriented and compact. The loss analysis must be summarized into stable keys and short phrases, not long prose dumps.

## Ledger And Evidence Changes

### Evidence

New evidence artifacts:

- `qqq-2h-context.json`
- `trade-context-<iteration>-<candidateId>.json`
- `loss-analysis-<iteration>-<candidateId>.json`

### Ledger

`experiments.jsonl` will add optional summary fields:

- `seedStrategyId`
- `improvementSource`
- `lossAnalysisSummary`
- `topLossZones`
- `repairPriorities`

`mutation-briefs.jsonl` should persist the richer brief payload including loss-analysis summaries.

### Views

New derived view:

- `state/pi-autoresearch/views/loss-pattern-summary.json`

This view should aggregate recurring loss regimes and repair suggestions across recent iterations so the system can avoid rediscovering the same failure mode repeatedly.

## Task Flow Changes

For each task:

1. Resolve curated seed and active baseline.
2. Choose mutation source:
   - accepted head if one exists
   - otherwise active seed
3. Generate candidate.
4. Evaluate candidate on TradingView.
5. Collect strategy metrics and trades.
6. Refresh or load QQQ 2-hour context cache.
7. Enrich trades with market context.
8. Build loss-zone analysis.
9. Persist evidence and ledger summaries.
10. Build next mutation brief using objective, recent failures, and loss analysis.

The core change is that post-evaluation analysis becomes part of the mutation loop, not just a reporting side effect.

## Error Handling

### 1. No Trades

If the candidate produces no trades:

- keep current `backtest_empty` handling
- do not fabricate loss analysis
- write a loss-analysis artifact with status `unavailable_no_trades`
- add a concise repair hint focused on restoring tradability

### 2. Market Context Fetch Failure

If QQQ context refresh fails:

- use the last cached `qqq-2h-context.json` if available
- record an incident if cache fallback is used
- if no cache exists, continue the iteration without loss-zone enrichment
- record `lossAnalysisSummary.status = "market_context_unavailable"`

### 3. Trade Timestamp Mismatch

If some trades cannot be matched cleanly to 2-hour bars:

- match to nearest valid bar within a bounded tolerance
- record mismatch count in the loss-analysis artifact
- do not fail the full task unless nearly all trades are unmatched

## Testing

Minimum required tests:

1. Seed strategy loading
   - curated seed is copied or synchronized correctly
   - active baseline can be reset from seed

2. Brief generation
   - seed strategy and loss analysis appear in `MutationBrief`
   - `improvementSource` resolves correctly

3. Trade context matching
   - Strategy Tester trades map to expected QQQ 2-hour bars
   - unmatched trades are reported safely

4. Loss analysis
   - losing trades cluster into stable `lossHotZones`
   - `repairPriorities` are generated deterministically from the same input

5. Ledger and evidence persistence
   - new evidence files are written
   - experiment records include loss analysis summaries
   - derived `loss-pattern-summary.json` rebuilds deterministically

## Implementation Boundaries

This phase includes:

- curated seed support
- active seed synchronization
- QQQ 2-hour context cache
- trade context enrichment
- loss-zone summary generation
- mutation brief upgrade
- evidence and ledger persistence

This phase does not include:

- arbitrary external strategy imports
- multi-symbol market context
- automatic strategy selection across many seeds
- deep causal inference beyond rule-based loss pattern extraction

## Recommended Next Plan

Implementation should proceed in four slices:

1. Seed strategy support and brief schema changes
2. QQQ 2-hour context cache and trade enrichment
3. Loss analysis evidence and brief feedback loop
4. Ledger/view integration and test coverage

## Spec Review Notes

Self-review completed with these checks:

- no placeholder sections remain
- seed vs accepted-head responsibilities are explicit
- external strategy analysis is explicitly excluded
- loss analysis failure handling is defined
- scope is bounded to a single-symbol QQQ 2-hour context engine
