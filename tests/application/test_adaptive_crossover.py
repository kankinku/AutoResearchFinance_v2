"""Registered multi-parent research stays IR-based and paper-only."""

from __future__ import annotations

import json
from pathlib import Path

from application.research_batch_service import ResearchBatchService
from application.research_hypothesis import propose_next_hypothesis
from experiments.candidate_generator import generate_candidates
from mutation.engine import MutationOperation, apply_operations
from strategy_ir.schema import StrategyIR

ROOT = Path(__file__).resolve().parents[2]


def _source(name: str) -> StrategyIR:
    for path in (ROOT / "strategies/normalized").glob("*.json"):
        parent = StrategyIR.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if parent.strategy_id == name:
            return parent
    raise AssertionError(f"missing catalog source: {name}")


def test_crossover_carries_required_partner_indicator_and_lineage() -> None:
    primary, second = _source("mean_reversion"), _source("disparity")
    child = apply_operations(primary, [MutationOperation("CROSSOVER", other=second)])
    assert child.exit == second.exit
    assert "disp_20" in child.indicators
    assert second.strategy_id in child.parents


def test_crossover_is_fallback_only_for_explicit_partner() -> None:
    primary, second = _source("mean_reversion"), _source("disparity")
    used = frozenset(
        {
            "ENTRY_THRESHOLD_EXPERIMENT_TIGHTER",
            "ENTRY_THRESHOLD_EXPERIMENT_LOOSER",
            "RISK_POSITION_SIZING_EXPERIMENT",
            "RISK_STOP_LOSS_EXPERIMENT",
            "RISK_TAKE_PROFIT_EXPERIMENT",
            "EXIT_THRESHOLD_EXPERIMENT_TIGHTER",
            "EXIT_THRESHOLD_EXPERIMENT_LOOSER",
            "INDICATOR_RSI_ENTRY_CONFIRMATION",
        }
    )
    kwargs = dict(
        parent=primary,
        initial_operations=(),
        initial_domains=(),
        gate_names=("annual_trade_count",),
        prior_attempt_id="verified-attempt",
        used_hypotheses=used,
        already_evaluated=frozenset(),
        method="grid",
        count=1,
        next_seed=33,
    )
    assert propose_next_hypothesis(**kwargs) is None
    plan = propose_next_hypothesis(**kwargs, partner=second)
    assert plan is not None
    assert plan.reason_code == "CROSSOVER_REGISTERED_PARENT_EXIT"
    assert second.strategy_id in plan.summary()["crossover_parent_ids"]
    candidate = generate_candidates(
        primary, plan.operations, plan.domains, method="grid", count=1, seed=33
    )[0]
    assert candidate.strategy.exit == second.exit


def test_only_registered_second_parent_is_accepted_in_mixed_mode(tmp_path: Path) -> None:
    from shutil import copy2

    from core.data.parquet import ParquetDataProvider
    from tests.research.test_academic_algorithm_plan import _market

    # Registered parents stay the real versioned repository fixture; the input
    # market is isolated, avoiding reliance on ignored live vendor data files.
    root = tmp_path
    normalized = root / "strategies/normalized"
    normalized.mkdir(parents=True)
    for source in (ROOT / "strategies/normalized").glob("*.json"):
        copy2(source, normalized / source.name)
    market_file = root / "data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet"
    market_file.parent.mkdir(parents=True)
    ParquetDataProvider.write(market_file, _market())
    s = ResearchBatchService(project_root=root, state_dir=root / "state/moon-http/research")
    args = {
        "source_path": "strategies/normalized/e8dad9397b1d9611-5.json",
        "data_path": "data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet",
        "intent": {
            "mode": "mixed",
            "parent_ids": ["mean_reversion", "disparity"],
            "operations": [],
            "rationale": "Approved catalog parents, research only",
        },
        "generations": 2,
        "count": 1,
        "method": "grid",
        "seed": 42,
    }
    assert s._validate_request(args)["intent"]["parent_ids"] == ["mean_reversion", "disparity"]
    for name in ("unknown-forged-parent", "mean_reversion"):
        bad = {**args, "intent": {**args["intent"], "parent_ids": ["mean_reversion", name]}}
        try:
            s._validate_request(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid partner must fail closed")
