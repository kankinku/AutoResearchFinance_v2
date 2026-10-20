# Quant AutoResearch — P5 source comparison and bounded full-suite shards

2026-10-21 KST · P5 / S9–T4 · Q05/Q06/Q08/Q10/Q11/Q12/Q17/Q18/Q20.
User-approved Pine five-question ADR, existing 20Q scope lock, V05→T4→V01–V04→V06→V07 order remain unchanged.

## Actual implemented change

- Added research/pine_import/p5_reference_compare.py: strict original upload hash / DEVELOPMENT dataset hash / reference CSV SHA-256 / timezone-aware bar timestamp / OHLC / numeric and event equality comparison, bounded diagnostic examples. No Pine runtime dependency, no hidden bar-shifting, no sealed OOS, no live orders.
- P5 comparator always reports NUMERIC_MATCH_ONLY_UNAUTHENTICATED or MISMATCH; no CSV or self-generated fixture can authenticate actual TradingView provenance or approve operational promotion.
- Added tests/research/test_pine_reference_parity_p5.py; 7 test cases on deliberately synthetic internal CSV witnesses. This tests failure detection, NOT external TradingView parity.
- External export handoff and required column schema documented in autoresearch-pine-p5-external-reference-2026-10-21.md.
- Code source commit **ffb317e686a21460febe63207d4c8f5b8427dea1**, confirmed PUSHED to feat/quant-same-session-350-20261019.

## Measured checks

| Check | Real result |
|---|---|
| Pine/BOSWaves/Shaakuni/typed composition/P5 comparator + scope-lock pytest | **36 PASSED** |
| Whole-repository Ruff | **PASS** |
| Whole-repository Mypy | **295 source files, PASS** |
| Entire test suite earlier collection | **1904 collected on preceding commit**; source this turn adds 7 new tests |

### Full-suite bounded sharding (7 groups, 150 seconds per group)

| Shard | Actual result |
|---|---|
| other | TIMEOUT 150s (~87% progress, not pass) |
| research_1 | 189 PASS, 5 SKIP |
| research_2 | 186 PASS, 2 FAIL (missing G33), 2 SKIP |
| research_3 | 142 PASS, 1 FAIL (missing G33), 6 SKIP |
| research_4 | 153 PASS, 6 FAIL (missing G33), 4 SKIP |
| integrations_1 | TIMEOUT 150s (not pass) |
| integrations_2 | TIMEOUT 150s (not pass) |

**Four completed research shards**: 670 passed, 9 failed, 17 skipped. All 9 failures occurred while reading an historical snapshot manifest file **absent from this isolated Moon workspace**:

    /shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research/audits/phase1-20261017-1950/snapshot-manifest.json

Failures affected old G33 snapshot hash/bootstrap/parent inheritance and S2 guard tests. The missing historical-evidence dependency cannot be counted as passed or substituted with made-up fixtures.

**Other + both integrations groups** exceeded 150 seconds. Partial dot progress before timeout is **not counted as passed**. Whole repository tests are therefore **NOT PASS**.

## Acceptance and remaining work

- **P5 numeric comparator infrastructure: IMPLEMENTED AND UNIT TESTED; independent original TradingView export has not been supplied or attested**. Hence Pine source equivalence P5 remains NOT VERIFIED; 0/11 fully internalized.
- P6 official FeatureRegistry/StrategyIR promotion NOT RUN, P7 real GPT/MCP S7 experimental generation, diagnosis, memory and inheritance NOT RUN.
- To finish full-regression check: obtain exact immutable G33 snapshot with manifest/hash from its authoritative source, verify rather than synthesize; split slow other/integrations suites into smaller bounded groups.
- To finish P5: acquire source-version-pinned, parameter-pinned chart export from independent TradingView (including per-bar series/markers), validate against identical input market data, resolve confirmed divergences, separately test unrepresented live panel, drawings and broker fills.
- Protected core, sealed OOS, existing official G350 ledger, OAuth/MCP endpoint, real-orders-off policy and deployment remain unchanged. No production feature registration or trading permission was added.
