"""Offline-only completion of missing S7 whole-period risk diagnostics."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from evaluation.academic_campaign_audit import _sha256
from evaluation.academic_s7_risk_replay import replay_missing_children


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--catalog-source", type=Path, required=True)
    parser.add_argument("--market-parquet", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    options = parser.parse_args()
    target = options.snapshot / "catalog-for-risk-replay.sqlite"
    input_manifest = options.snapshot / "risk-replay-inputs.json"
    if target.exists():
        if not input_manifest.exists():
            raise ValueError("catalog freeze has no input manifest")
        saved = json.loads(input_manifest.read_text(encoding="utf-8"))
        if saved.get("catalog_copy_sha256") != _sha256(target) or saved.get(
            "market_input_sha256"
        ) != _sha256(options.market_parquet):
            raise ValueError("frozen replay input changed")
    source = options.catalog_source.resolve()
    if not source.exists() or not (options.snapshot / "snapshot-manifest.json").exists():
        raise FileNotFoundError("research ledger snapshot or catalog missing")
    if source.is_relative_to(options.snapshot.resolve()):
        raise ValueError("catalog source must be separate from frozen destination")
    if not target.exists():
        with (
            sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as active,
            sqlite3.connect(target) as frozen,
        ):
            active.backup(frozen)
            if frozen.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("catalog replay snapshot corrupted")
    manifest = {
        "catalog_copy_sha256": _sha256(target),
        "market_input_sha256": _sha256(options.market_parquet),
        "market_is_development_only": True,
        "original_live_databases_modified": False,
        "unverified_oos": True,
    }
    (options.snapshot / "risk-replay-inputs.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    sidecar = replay_missing_children(
        snapshot=options.snapshot,
        catalog_path=target,
        market_path=options.market_parquet,
        session_id=options.session_id,
    )
    if sidecar["expected_generations"] != sidecar["full_period_coverage"]:
        raise ValueError("not all S7 whole-period risk records are covered")
    outfile = options.snapshot / "risk-replay-sidecar.json"
    with outfile.open("x", encoding="utf-8") as writer:
        json.dump(sidecar, writer, ensure_ascii=False, sort_keys=True, indent=2)
        writer.write("\n")
    print(
        f"whole-period covered {sidecar['full_period_coverage']}/"
        f"{sidecar['expected_generations']} "
        f"(new {sidecar['newly_replayed']}, existing {sidecar['preexisting_verified']})"
    )
    print(f"risk replay sidecar SHA256: {_sha256(outfile)}")


if __name__ == "__main__":
    main()
