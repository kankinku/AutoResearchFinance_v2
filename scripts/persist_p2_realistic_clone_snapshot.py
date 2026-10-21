"""Persist the completed /tmp research clone as a nonproduction audit snapshot.

Source and destination are verified using SQLite's online backup API, with
explicit no-overwrite semantics and full 457-generation hash-chain check.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from core.integrity.hashes import content_hash
from scripts.run_p2_precommit_realistic_pilot import DEST, EXPECTED_HEAD


def main():
    result = json.loads((DEST / "result.json").read_text())
    assert result["status"] == "COMPLETED"
    assert result["actual_new_generations"] == 5
    src = Path(result["local_source"]).resolve()
    assert src.is_dir() and src.as_posix().startswith("/tmp/quant-p2-realistic-recover-")
    assert (src / "academic-gpt-checkpoints").is_dir()
    target = DEST / "final-clone-snapshot"
    target.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        original = src / "academic-gpt-checkpoints" / name
        copied = target / name
        with sqlite3.connect(original) as db:
            with sqlite3.connect(copied) as output:
                db.backup(output)
        with sqlite3.connect(copied) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            if name == "cycles.sqlite":
                hashes_chain = db.execute(
                    "SELECT generation,evidence_hash,evidence_json "
                    "FROM generations ORDER BY generation"
                ).fetchall()
                assert len(hashes_chain) == 457
                assert hashes_chain[451][1] == EXPECTED_HEAD
                assert all(
                    json.loads(row[2])["previous_evidence_hash"] == hashes_chain[i - 1][1]
                    for i, row in enumerate(hashes_chain)
                    if i > 0
                )
                for i, child in enumerate(result["new_generations"], start=452):
                    assert child["evidence_hash"] == hashes_chain[i][1]
            if name == "gateway.sqlite":
                assert db.execute("SELECT count(*) FROM experiment_reports").fetchone()[0] == 457
                assert (
                    db.execute("SELECT count(*) FROM precommit_risk_rejections").fetchone()[0] == 12
                )
        hashes[name] = hashlib.sha256(copied.read_bytes()).hexdigest()
    shutil.copy2(src / "attempts.jsonl", target / "attempts.jsonl")
    hashes["attempts.jsonl"] = hashlib.sha256((target / "attempts.jsonl").read_bytes()).hexdigest()
    manifest = {
        "schema": "p2-realistic-final-clone-snapshot-v1",
        "source_report_hash": content_hash(result),
        "original_research_unchanged": result["original_chain_unchanged"],
        "generations": 457,
        "generation_source": "ISOLATED_CLONE_NON_PIT",
        "rejected_child_count": 12,
        "files_sha256": hashes,
        "not_independent_oos": True,
        "no_broker_orders": True,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("P2_PERSISTED_CLONE_OK", target, content_hash(manifest), flush=True)


if __name__ == "__main__":
    main()
