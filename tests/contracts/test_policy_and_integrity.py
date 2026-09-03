from __future__ import annotations

from pathlib import Path

import pytest

from core.evaluator.immutable_guard import assert_research_write_allowed
from core.integrity.hashes import canonical_bytes, experiment_hash
from research.policy import PolicyError, default_evaluation_thresholds, load_policy


def test_canonical_bytes_ignore_mapping_order_but_hash_content() -> None:
    left = {"b": 2, "a": {"value": 1.0}}
    right = {"a": {"value": 1.0}, "b": 2}

    assert canonical_bytes(left) == canonical_bytes(right)
    assert canonical_bytes(left) != canonical_bytes({"a": {"value": 1.1}, "b": 2})


def test_experiment_hash_includes_all_reproducibility_inputs() -> None:
    base = dict(
        strategy_ir={"id": "S1", "entry": {"logic": "AND"}},
        parameters={"fast": 12},
        symbols=["TEST"],
        start_date="2020-01-01",
        end_date="2024-01-01",
        dataset_version="data-v1",
        evaluator_version="eval-v1",
        cost_model_version="cost-v1",
        compiler_version="compiler-v1",
        image_digest="sha256:image",
        seed=7,
    )

    original = experiment_hash(**base)
    assert original == experiment_hash(**base)
    changed_inputs = (
        ("dataset_version", "data-v2"),
        ("seed", 8),
        ("image_digest", "sha256:other"),
    )
    for key, value in changed_inputs:
        changed = {**base, key: value}
        assert experiment_hash(**changed) != original


def test_policy_ratios_must_sum_to_one() -> None:
    policy_path = Path("research/policy.yaml")
    policy = load_policy(policy_path)
    assert policy.search.candidate_target == 256
    assert policy.search.total_ratio == pytest.approx(1.0)

    invalid = policy_path.read_text(encoding="utf-8").replace(
        "explore_ratio: 0.30", "explore_ratio: 0.31"
    )
    invalid_path = policy_path.with_name("invalid-policy.yaml")
    invalid_path.write_text(invalid, encoding="utf-8")
    try:
        with pytest.raises(PolicyError, match="sum to 1"):
            load_policy(invalid_path)
    finally:
        invalid_path.unlink()


def test_policy_centralizes_operational_evaluation_thresholds() -> None:
    policy = load_policy(Path("research/policy.yaml"))
    thresholds = default_evaluation_thresholds()

    assert policy.evaluation.min_qqq_cagr_delta == pytest.approx(0.10)
    assert policy.evaluation.min_annual_trades == 30
    assert thresholds.min_qqq_cagr_delta == pytest.approx(
        policy.evaluation.min_qqq_cagr_delta
    )
    assert thresholds.min_annual_trades == policy.evaluation.min_annual_trades


def test_research_cannot_write_protected_core_paths() -> None:
    allowed = Path("research/intent.json")
    protected = Path("core/evaluator/scoring.py")

    assert_research_write_allowed(allowed)
    with pytest.raises(PermissionError, match="protected"):
        assert_research_write_allowed(protected)
