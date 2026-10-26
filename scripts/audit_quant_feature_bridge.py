"""Read-only feature/academic mapping report; opt-in output files only."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from application.quant_feature_bridge_audit import audit_feature_bridge


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--csv-out", type=Path)
    args = parser.parse_args()
    report = audit_feature_bridge(args.catalog)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=list(report["features"][0]), extrasaction="ignore"
            )
            writer.writeheader()
            for feature in report["features"]:
                writer.writerow(feature)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "features"},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
