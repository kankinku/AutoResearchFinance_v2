import json
from hashlib import sha256

import pytest

from strategy_ir.receipt_manifest import PinnedReceiptManifest


def test_pinned_manifest_is_readonly_and_rejects_tampering(tmp_path):
    payload = {
        "schema_version": 1,
        "receipts": [
            {
                "feature_id": "sma",
                "dataset_hash": "data",
                "values_hash": "values",
                "verification_id": "independent-review",
                "verification_status": "AUDITED",
            }
        ],
    }
    path = tmp_path / "snapshot.json"
    original = json.dumps(payload).encode()
    path.write_bytes(original)
    manifest = PinnedReceiptManifest(path, expected_sha256=sha256(original).hexdigest())
    assert manifest.lookup("sma").verification_id == "independent-review"
    assert manifest.lookup("unverified") is None
    payload["receipts"][0]["values_hash"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="digest mismatch"):
        PinnedReceiptManifest(path, expected_sha256=sha256(original).hexdigest())


def test_rejects_duplicate_records(tmp_path):
    entry = {
        "feature_id": "sma",
        "dataset_hash": "d",
        "values_hash": "v",
        "verification_id": "check",
        "verification_status": "AUDITED",
    }
    raw = json.dumps({"schema_version": 1, "receipts": [entry, entry]}).encode()
    path = tmp_path / "duplicate.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="duplicate"):
        PinnedReceiptManifest(path, expected_sha256=sha256(raw).hexdigest())
