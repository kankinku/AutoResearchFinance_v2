# T-004 partial — market source lineage and research quality reporting

Implemented a backward-compatible, versioned **vendor declaration contract** for `MarketDataSet`:

- Optional `MarketSourceProvenance` holds `source_id`, timezone-aware `retrieved_at`, revision policy (`as_of` vs `latest`), universe policy (point-in-time, current-constituents or single-symbol), corporate-action policy (raw, split-adjusted or total-return-adjusted), named corporate-action reference and inclusion of delisted securities.
- New lineage data round-trips through Parquet file metadata. The immutable `dataset_hash` commits to lineage declarations whenever provided. The legacy no-provenance daily US-equity hash remains **byte-for-byte unchanged** for existing datasets.
- Invalid timestamps, nonsensical chronology, unrecognized enum strings and malformed provenance metadata fail before accepting the dataset.
- `market_data_quality()` identifies missing declarations, look-ahead revision risks, current-index survivorship bias, exclusion of delisted stocks and missing corporate-action adjustments. Legacy fixtures and unknown vendor sources are labeled `UNVERIFIED`. Otherwise status is **`DECLARED_POINT_IN_TIME`**, never `VERIFIED`: source claims do not establish independent, vendor-backed point-in-time evidence.
- Every local research run persists the quality assessment into both response and immutable manifest/attempt Evidence. Multi-symbol backtests and fast/validation dataset slices preserve provenance metadata instead of losing it.

**Important limitations:** This layer does not verify vendor data externally, independently validate split/dividend adjustments, reconstruct historical constituents, detect all exchange-holiday/session gaps or secure a cryptographic signed source snapshot. A newer vendor snapshot, even if accompanied by `revision_policy=as_of`, is not proof of what a historical trader actually knew. Sealed OOS is not accessed. Separate genuine vendor audit and PIT availability checks remain required before T-004 is complete.

Tests: `tests/core/test_market_data_provenance.py` and `tests/orchestration/test_evaluation_runner.py`, plus existing parquet, core, pipeline and runner regression tests.
