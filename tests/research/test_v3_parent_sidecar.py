"""V3 sidecar audit tests: research-only, no real GPT generation."""

import sqlite3

import pytest

from research.llm.v3_parent_sidecar import ResearchParentSidecar, SidecarIntegrityError

SOURCE = "a" * 64
DATA = "b" * 64
INITIAL = "c" * 64


def store(tmp_path):
    ledger = ResearchParentSidecar(tmp_path / "v3.sqlite")
    label = ledger.pin_cohort(
        cohort_id="v3-trial",
        source_ledger_head=SOURCE,
        dataset_hash=DATA,
        initial_parent_hash=INITIAL,
        source_generations=(68, 192, 248),
    )
    return ledger, label


def trial(*, number=1, risk=False, duplicate=(), s7="NOT_RUN", s7_hash=None):
    return {
        "proposal_id": f"{number:064x}",
        "economic_fingerprint": f"{number + 200:064x}",
        "strategy_hash": f"{number + 100:064x}",
        "audit_hash": "f" * 64,
        "dataset_hash": DATA,
        "source_ledger_head": SOURCE,
        "donor_generations": [68, 192, 248],
        "donor_component_hashes": ["1" * 64, "2" * 64, "3" * 64],
        "source_evidence_hashes": ["4" * 64, "5" * 64, "6" * 64],
        "source_s7_report_hashes": ["7" * 64, "8" * 64, "9" * 64],
        "entry_generation": 68,
        "exit_generation": 192,
        "risk_generation": 248,
        "return": 0.83,
        "mdd": 0.2,
        "closed_trades": 36,
        "risk_eligible": risk,
        "economic_duplicate_of": list(duplicate),
        "s7_status": s7,
        "s7_evidence_hash": s7_hash,
        "measured_costs": 100.0,
        "validation_origin": "COSTED_S2_DEVELOPMENT_REPLAY",
        "model_origin": "SCRIPTED_NOT_GPT",
        "broker_executable": False,
        "oos_approved": False,
    }


def test_idempotent_rejection_and_conflict(tmp_path):
    ledger, label = store(tmp_path)
    item = trial(risk=True, duplicate=(192,))
    result = ledger.record_candidate(label, item)
    assert result.decision == "REJECT_ECONOMIC_DUPLICATE"
    assert result.selected_parent_hash == INITIAL
    assert ledger.record_candidate(label, item) == result
    assert ledger.audit(label)["attempt_count"] == 1
    with pytest.raises(SidecarIntegrityError, match="conflicting replay"):
        ledger.record_candidate(label, {**item, "return": 0.92})


def test_conditional_development_parent_and_restarts(tmp_path):
    ledger, label = store(tmp_path)
    one = ledger.record_candidate(label, trial())
    assert one.decision == "REJECT_RISK"
    two = ledger.record_candidate(label, trial(number=2, risk=True))
    assert two.decision == "REJECT_MISSING_S7"
    three = ledger.record_candidate(
        label,
        trial(
            number=3,
            risk=True,
            s7="DIRECTION_MATCHED",
            s7_hash="d" * 64,
        ),
    )
    assert three.decision == "SELECT_RESEARCH_PARENT_CANDIDATE"
    assert three.is_counted_gpt_generation is False
    restart = ResearchParentSidecar(ledger.path)
    last = restart.record_candidate(label, trial(number=4))
    assert last.previous_parent_hash == three.selected_parent_hash
    assert last.selected_parent_hash == three.selected_parent_hash
    assert restart.audit(label)["attempt_count"] == 4


def test_chain_tampering_is_rejected(tmp_path):
    ledger, label = store(tmp_path)
    ledger.record_candidate(label, trial())
    ledger.record_candidate(label, trial(number=2))
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE candidate_events SET event_json='{}' WHERE sequence=1")
    with pytest.raises(SidecarIntegrityError, match="chain"):
        ledger.audit(label)
    with pytest.raises(SidecarIntegrityError, match="chain"):
        ledger.record_candidate(label, trial(number=3))


def test_previous_candidate_same_costed_execution_cannot_be_selected(tmp_path):
    ledger, label = store(tmp_path)
    recorded = trial(number=7)
    ledger.record_candidate(label, recorded)
    same_execution = trial(
        number=8,
        risk=True,
        s7="DIRECTION_MATCHED",
        s7_hash="d" * 64,
    )
    same_execution["economic_fingerprint"] = recorded["economic_fingerprint"]
    second = ledger.record_candidate(label, same_execution)
    assert second.decision == "REJECT_PRIOR_CANDIDATE_DUPLICATE"
    assert second.selected_parent_hash == INITIAL


def test_cohort_pin_cannot_change_source_or_metric_proof(tmp_path):
    from research.llm.v3_parent_sidecar import SidecarInputError

    ledger, label = store(tmp_path)
    assert (
        ledger.pin_cohort(
            cohort_id=label,
            source_ledger_head=SOURCE,
            dataset_hash=DATA,
            initial_parent_hash=INITIAL,
            source_generations=(68, 192, 248),
        )
        == label
    )
    with pytest.raises(SidecarIntegrityError, match="cohort pin"):
        ledger.pin_cohort(
            cohort_id=label,
            source_ledger_head="0" * 64,
            dataset_hash=DATA,
            initial_parent_hash=INITIAL,
            source_generations=(68, 192, 248),
        )
    with pytest.raises(SidecarInputError, match="donor"):
        ledger.record_candidate(label, {**trial(), "donor_component_hashes": []})
    with pytest.raises(SidecarInputError, match="unsupported origin"):
        ledger.record_candidate(label, {**trial(), "model_origin": "UNKNOWN"})
