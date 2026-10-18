from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.data.contracts import Bar, MarketDataSet
from core.integrity.hashes import content_hash
from strategy_ir.feature_receipt import FeatureAuditReceipt, compile_reviewed_policy_switch
from strategy_ir.policy_program import PolicySwitch, Predicate


def test_receipt_binds_dataset_and_exact_vector():
    bars = tuple(
        Bar(datetime(2024, 1, i, tzinfo=timezone.utc), "QQQ", 20, 20, 20, 20, 100)
        for i in range(1, 4)
    )
    dataset = MarketDataSet("receipt", "development", bars)
    program = PolicySwitch((Predicate("sma", "gt", 5),), 0.65, 0.25, "policy")
    values = (1.0, 9.0, 9.0)
    receipt = FeatureAuditReceipt(
        "sma", dataset.dataset_hash, content_hash(values), "review-1", "AUDITED"
    )
    assert [
        decision.target_weight
        for decision in compile_reviewed_policy_switch(
            dataset, program, {"sma": values}, trusted_receipts={"sma": receipt}
        )
    ] == [0.25, 0.65]
    for bad in (
        replace(receipt, dataset_hash="other"),
        replace(receipt, values_hash="other"),
        replace(receipt, verification_status="REGISTERED"),
        replace(receipt, verification_id=""),
    ):
        with pytest.raises(ValueError, match="receipt mismatch"):
            compile_reviewed_policy_switch(
                dataset, program, {"sma": values}, trusted_receipts={"sma": bad}
            )
    with pytest.raises(ValueError, match="receipt required"):
        compile_reviewed_policy_switch(dataset, program, {"sma": values}, trusted_receipts={})
    with pytest.raises(ValueError, match="receipt mismatch"):
        compile_reviewed_policy_switch(
            dataset, program, {"sma": (1.0, 2.0, 9.0)}, trusted_receipts={"sma": receipt}
        )
