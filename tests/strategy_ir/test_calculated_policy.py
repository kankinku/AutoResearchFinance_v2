import json
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from core.data.contracts import Bar, MarketDataSet
from core.features.calculators import calculate_feature
from core.features.contracts import FeatureSpec, FeatureVerification
from core.features.registry import FeatureRegistry
from core.integrity.hashes import content_hash
from strategy_ir.calculated_policy import compile_calculated_policy
from strategy_ir.policy_program import PolicySwitch, Predicate
from strategy_ir.receipt_manifest import PinnedReceiptManifest


def test_real_calculator_pinned_receipt_to_decisions(tmp_path):
    bars = tuple(
        Bar(datetime(2024, 1, day, tzinfo=timezone.utc), "QQQ", value, value, value, value, 100)
        for day, value in enumerate((10, 12, 14, 16), 1)
    )
    dataset = MarketDataSet("test-calculated-policy", "development", bars)
    spec = FeatureSpec(
        name="reviewed_sma",
        family="price",
        inputs=("close",),
        calculator="sma",
        lookback=2,
        formula="SMA(close,2)",
    )
    verified = FeatureVerification(**dict.fromkeys(FeatureVerification.model_fields, True))
    registry = FeatureRegistry()
    registry.register_verified(spec, verified)
    values = calculate_feature(
        registry.get("reviewed_sma"), {"close": tuple(b.close for b in bars)}
    )
    record = {
        "feature_id": "reviewed_sma",
        "dataset_hash": dataset.dataset_hash,
        "values_hash": content_hash(values),
        "verification_id": "independent-review-1",
        "verification_status": "AUDITED",
    }
    raw = json.dumps({"schema_version": 1, "receipts": [record]}).encode()
    path = tmp_path / "review.json"
    path.write_bytes(raw)
    manifest = PinnedReceiptManifest(path, expected_sha256=sha256(raw).hexdigest())
    program = PolicySwitch((Predicate("reviewed_sma", "gt", 12),), 0.65, 0.25, "switch")
    decisions = compile_calculated_policy(dataset, program, registry, manifest)
    assert [d.target_weight for d in decisions] == [0, 0.25, 0.65]
    with pytest.raises(ValueError, match="receipt mismatch"):
        mutated = MarketDataSet(
            "test-calculated-policy",
            "development",
            tuple(
                Bar(b.timestamp, b.symbol, b.open + 1, b.high + 1, b.low + 1, b.close + 1, b.volume)
                for b in bars
            ),
        )
        compile_calculated_policy(mutated, program, registry, manifest)
