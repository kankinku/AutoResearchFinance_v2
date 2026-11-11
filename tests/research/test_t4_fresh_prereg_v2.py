"""T4 [10/16]: new G1 three-arm policy, never historical GPT evidence."""

from copy import deepcopy

import pytest

from core.integrity.hashes import content_hash
from scripts.preregister_t4_equal_plan_comparison import (
    FreshProtocolError,
    freeze_fresh_manifest,
    fresh_three_arm_protocol,
)


def _manifest():
    return freeze_fresh_manifest(
        fresh_three_arm_protocol(),
        market_hash="1" * 64,
        evaluator_version="quant-improved-evaluator-20261110",
        cost_policy_hash="2" * 64,
        feature_policy_hash="3" * 64,
        cohort_id="fresh-study-g1",
        market_start="2021-01-01", market_end="2025-12-31",
        source_code_hash="4" * 64,
        session_ids={
            "GPT_S7_S8": "a" * 32,
            "FIXED_RULE": "b" * 32,
            "RANDOM_SEEDED": "c" * 32,
        },
    )


def test_new_study_protocol_fixes_budget_before_any_new_G1() -> None:
    policy = fresh_three_arm_protocol()
    assert policy["protocol_hash"] == content_hash({
        k: v for k, v in policy.items() if k != "protocol_hash"
    })
    assert policy["status"] == "BLOCKED_UNTIL_FRESH_MARKET_AND_SESSIONS"
    assert policy["past_cohort_reused"] is False
    assert policy["independent_oos_approved"] is False
    assert policy["arms"] == ["GPT_S7_S8", "FIXED_RULE", "RANDOM_SEEDED"]
    assert policy["budget_per_arm"] == {
        "plan_attempts": 10, "s7_trials": 10, "canonical_backtests": 20,
        "model_call_ceiling": 20, "model_token_ceiling": 200000,
    }
    assert policy["seed"] == 20261110
    assert policy["selection_metric"] == "UNIQUE_COSTED_FILL_TRACE_WITH_RISK_GATES"


def test_frozen_fresh_manifest_binds_new_sessions_data_and_policy() -> None:
    manifest = _manifest()
    assert manifest["freeze_hash"] == content_hash({
        k: v for k, v in manifest.items() if k != "freeze_hash"
    })
    assert manifest["protocol_hash"] == fresh_three_arm_protocol()["protocol_hash"]
    assert manifest["dataset_hash"] == "1" * 64
    assert manifest["market_window"] == {"start": "2021-01-01", "end": "2025-12-31"}
    assert manifest["source_code_hash"] == "4" * 64
    assert manifest["cohort_id"] == "fresh-study-g1"
    assert manifest["start_at_generation"] == 1
    assert len(set(manifest["session_ids"].values())) == 3
    assert manifest["old_sessions_prohibited"] is True
    assert manifest["actual_live_gpt_work_done"] is False


@pytest.mark.parametrize("case", [
    "old_session", "duplicate_session", "missing_market", "old_evaluator",
    "bad_policy", "tamper_protocol", "missing_arm", "bad_seed", "old_cohort",
    "reversed_period", "bad_code",
])
def test_fresh_manifest_rejects_invalid_or_old_cohort_inputs(case: str) -> None:
    policy = fresh_three_arm_protocol()
    if case == "tamper_protocol":
        policy["budget_per_arm"]["canonical_backtests"] = 10
    if case == "bad_seed":
        policy["seed"] = 42
    opts = {
        "market_hash": "1" * 64,
        "evaluator_version": "quant-improved-evaluator-20261110",
        "cost_policy_hash": "2" * 64,
        "feature_policy_hash": "3" * 64,
        "cohort_id": "fresh-study-g1",
        "market_start": "2021-01-01",
        "market_end": "2025-12-31",
        "source_code_hash": "4" * 64,
        "session_ids": {
            "GPT_S7_S8": "a" * 32,
            "FIXED_RULE": "b" * 32,
            "RANDOM_SEEDED": "c" * 32,
        },
    }
    if case == "old_session":
        opts["session_ids"]["GPT_S7_S8"] = "14626d55fb2b461faa485df911920071"
    elif case == "duplicate_session":
        opts["session_ids"]["RANDOM_SEEDED"] = "b" * 32
        opts["session_ids"]["FIXED_RULE"] = "b" * 32
    elif case == "missing_market":
        opts["market_hash"] = ""
    elif case == "old_evaluator":
        opts["evaluator_version"] = "legacy"
    elif case == "bad_policy":
        opts["cost_policy_hash"] = "unverified"
    elif case == "reversed_period":
        opts["market_end"] = "2020-01-01"
    elif case == "bad_code":
        opts["source_code_hash"] = "unverified"
    elif case == "missing_arm":
        del opts["session_ids"]["RANDOM_SEEDED"]
    elif case == "old_cohort":
        opts["cohort_id"] = "G150-reuse"
    with pytest.raises(FreshProtocolError):
        freeze_fresh_manifest(policy, **opts)


def test_protocol_input_is_not_mutated_by_freeze() -> None:
    policy = fresh_three_arm_protocol()
    original = deepcopy(policy)
    _ = _manifest()
    assert policy == original


def test_new_protocol_cli_writes_once_without_legacy_gpt_input(
    tmp_path, monkeypatch,
) -> None:
    import json
    import sys

    from scripts.preregister_t4_equal_plan_comparison import main

    target = tmp_path / "fresh-protocol.json"
    monkeypatch.setattr(sys, "argv", [
        "preregister", "--fresh-protocol-output", str(target),
    ])
    main()
    assert json.loads(target.read_text()) == fresh_three_arm_protocol()
    with pytest.raises(FileExistsError):
        main()


def test_new_manifest_cli_requires_explicit_bound_data_and_sessions(
    tmp_path, monkeypatch,
) -> None:
    import json
    import sys

    from scripts.preregister_t4_equal_plan_comparison import main

    approved = _manifest()
    config = {
        "market_hash": approved["dataset_hash"],
        "evaluator_version": approved["evaluator_version"],
        "cost_policy_hash": approved["cost_policy_hash"],
        "feature_policy_hash": approved["feature_policy_hash"],
        "cohort_id": approved["cohort_id"],
        "market_start": approved["market_window"]["start"],
        "market_end": approved["market_window"]["end"],
        "source_code_hash": approved["source_code_hash"],
        "session_ids": approved["session_ids"],
    }
    cfg = tmp_path / "fresh-input.json"
    out = tmp_path / "fresh-manifest.json"
    cfg.write_text(json.dumps(config))
    monkeypatch.setattr(sys, "argv", [
        "preregister", "--fresh-manifest-config", str(cfg),
        "--fresh-manifest-output", str(out),
    ])
    main()
    assert json.loads(out.read_text()) == approved
    with pytest.raises(FileExistsError):
        main()


def test_committed_new_protocol_matches_approved_immutable_sha() -> None:
    import json
    from pathlib import Path

    protocol = fresh_three_arm_protocol()
    expected = "45a446476150784b92da958ffb78f280d406fe12d5dafa1be82f1c0334695daa"
    saved = json.loads((
        Path(__file__).resolve().parents[2]
        / "docs/operations/quant-t4-fresh-three-arm-preregistration-20261110.json"
    ).read_text(encoding="utf-8"))
    assert saved == protocol
    assert saved["protocol_hash"] == expected
