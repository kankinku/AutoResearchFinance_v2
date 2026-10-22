"""Pre-S7 P3 diagnostic next_intent filtering; development-signal only."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from core.integrity.hashes import content_hash
from research.llm import p3_diagnostic_preflight as under_test
from tests.research.test_p3_semantic_preflight import (
    c,
    make_compiled_for_signals,
    sample_strategy,
)


@pytest.mark.parametrize(
    ("change", "vote", "expected_reason", "expected_reject"),
    [
        ("weaker_or", [0.0, 0.6, 1.0], "PROVABLE_CONDITION_SUBSUMPTION", True),
        ("sampled_equal", [0.0, 1.0, 0.0], "DEVELOPMENT_SIGNAL_EQUIVALENCE", True),
        ("different_gates", [0.0, 0.6, 1.0], "DIFFERENT_SIGNALS_OR_RISK_POLICY", False),
        ("different_risk", [0.0, 1.0, 0.0], "DIFFERENT_SIGNALS_OR_RISK_POLICY", False),
    ],
)
def test_next_intent_inspected_without_counted_commit(
    monkeypatch, change, vote, expected_reason, expected_reject,
):
    parent = sample_strategy()
    child = deepcopy(parent)
    if change == "different_risk":
        child.risk.position_size_pct = 50
    else:
        child.exit.conditions.append(c("less_equal", 0.25 if change == "weaker_or" else 0.75))
    fake = make_compiled_for_signals(parent, vote)
    @dataclass
    class TestCompiled:
        strategy: object
        strategy_hash: str
        replay: object
        feature_values: dict
    compiled = TestCompiled(
        parent, content_hash(parent.model_dump(mode="json", by_alias=True)),
        fake.replay, fake.feature_values,
    )
    experiment = SimpleNamespace(
        hypothesis_id="test_hypothesis", child=child,
        child_hash=content_hash(child.model_dump(mode="json", by_alias=True)),
    )
    monkeypatch.setattr(
        under_test, "audit_inherited_decisions",
        lambda *_: SimpleNamespace(trace_hash="audit"),
    )
    monkeypatch.setattr(
        under_test, "build_diagnostic_context",
        lambda *_: {"context_hash": "audited"},
    )
    monkeypatch.setattr(
        under_test, "approve_diagnostic_plan",
        lambda *_: SimpleNamespace(experiments=[experiment]),
    )
    market = SimpleNamespace(bars=[None] * len(vote), dataset_hash="dev-dataset")
    review = under_test.inspect_diagnostic_next_intents(compiled, market, {"proposal": "typed"})
    assert review["reject"] is expected_reject
    assert review["reviews"][0]["review"]["reason"] == expected_reason
    assert review["review_hash"] == content_hash(
        {k: v for k, v in review.items() if k != "review_hash"}
    )
    assert review["scope"] == "REUSED_DEVELOPMENT_NO_OOS_OR_CAUSAL_CLAIM"
