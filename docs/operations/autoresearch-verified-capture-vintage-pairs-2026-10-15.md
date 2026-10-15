# Quant Autoresearch — verified captured-price vintage pairs (2026-10-15)

## Scope and outcome

A new **offline, research-only** capability compares two preserved public Nasdaq QQQ snapshots after replaying and verifying **each** archived raw JSON, SHA-256 source digest, manifest and development Parquet file. It detects changed overlapping historical session bars, refuses tampered captures and refuses unordered/equal collection timestamps, incomparable sources or the same capture reused as both inputs.

The evidence pair is content-addressed and reports capture hashes, raw-file hashes, collection timestamps, count and sample dates of changed bars, overlap, and maximum relative difference. It separates *observed later vendor revisions* from **historical point-in-time availability**. These are local capture times (and the vendor is the same), not independently authenticated publisher release times. No historical PIT certification, original decision-time availability, strategy validation, trading or OOS promotion occurs.

## Testing and real-world gap

Synthetic independently generated Nasdaq response payloads with preserved manifests verified that an original 2020-01-03 close could differ between captures made 2026-10-10 and 2026-10-15: **2 overlapping sessions, 1 changed**. Identical pairs report unchanged sessions without PIT certification. Tampered raw, manifest, parquet, same-capture, and non-chronological pairs are refused. These are **synthetic test values**, not evidence of a real Nasdaq price revision.

No usable two-capture real Nasdaq archive was discovered in the previously inspected production deployment workspace. A fresh remote-capture attempt was blocked before running; this task did **not** obtain a real independent historical price vintage. The existing stored Tiingo data are still latest-revised historical snapshots, not contemporaneously signed vintages.

## Local-only usage

First, preserve two captures using the existing `research-cli capture-nasdaq-qqq` command, each with a unique append-only output/raw/manifest set in ignored local research state (never Git). Then compare with:

```bash
python -m research.indicator_engine.cli compare-nasdaq-vintages \
  --earlier-output <first.parquet> --earlier-raw <first.raw.json> --earlier-manifest <first.manifest.json> \
  --later-output <second.parquet> --later-raw <second.raw.json> --later-manifest <second.manifest.json>
```

The command returns structured revision evidence or a refusal with exit code 2. It never reads sealed OOS, touches broker orders, modifies the original runtime or changes the registered MCP URL/OAuth. No deployment.

## Remaining acceptance requirements

1. Build a genuine **longitudinal** archive with independently attested timestamp authority and archived original source bytes. A locally entered captured_at value is not an external timestamp proof.
2. Obtain authenticated provider historical as-of publication/revision records and independently audited corporate-action/split history (and handle survivorship/delistings for multi-asset tests).
3. Align publisher availability timestamps to every real historical strategy decision and only then separately evaluate untouched OOS; keep research-only order block until all independent gates have passed.
