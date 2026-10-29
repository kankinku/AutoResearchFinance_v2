# ruff: noqa: E501  # Audit evidence includes complete immutable provenance and caveats.
"""A11 controlled scripted diagnostics, preregistered before observation.

Actual ledger-certified G68 donor from disposable sqlite backups and
same 1508 QQQ non-PIT DEVELOPMENT bars. No GPT calls, new counted generations,
broker orders, OOS, original ledger edits or champion promotion.

Six *single-slot* arms use the locked manifest. B4 is a causal 35-bar delay
control, not a shuffled future vector. Conclusions cannot imply statistical
significance or complete feature-family coverage.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.contracts import DataZone
from core.integrity.hashes import content_hash
from evaluation.academic_s7_risk_replay import fill_exposure
from evaluation.metrics import calculate_metrics
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from research.llm.inherited_feature_compiler import (
    InheritedFeatureBindingError,
    _new_feature_vector,
    bind_inherited_features,
)
from research.llm.ledger_donors_v3 import checkout_counted_donors
from strategy_ir.schema import FeatureRef, StrategyIR

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/operations"
PREREG = OUT / "quant-v3-chart-A11-preregistration-20261029.json"
DATA_ROOT = Path("/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021")
SOURCE = DATA_ROOT / "state/moon-http/fresh-20261021"
ORIGINAL = SOURCE / "research/academic-gpt-checkpoints"
EXPECTED_GEN = 68


def read_prereg() -> dict[str, Any]:
    data = json.loads(PREREG.read_text(encoding="utf-8"))
    verified = {key: value for key, value in data.items() if key != "freeze_hash"}
    if content_hash(verified) != data["freeze_hash"]:
        raise ValueError("A11 preregistered policy or arm contents were modified")
    if (
        data["schema"] != "quant-v3-A11-scripted-equal-budget-preregister-v1"
        or data["source_generation"] != EXPECTED_GEN
        or data["candidates_per_arm"] != 1
        or data["seed"] != 20261029
        or len(data["arms"]) != 6
        or len({x["id"] for x in data["arms"]}) != 6
        or data["sealed_2026_OOS_accessed"] is not False
        or data["orders_enabled"] is not False
        or data["model_calls"] != 0
    ):
        raise ValueError("A11 scope/arm count/timing lock violation")
    return cast(dict[str, Any], data)


def checkout_g68(source_backup: Path) -> tuple[Any, Any, dict[str, Any]]:
    """Use only provided disposable SQLite snapshot, never original database."""
    if not source_backup.is_dir() or source_backup.resolve() == ORIGINAL.resolve():
        raise ValueError("source backup must be a physically separate directory")
    if any(
        not (source_backup / name).is_file()
        for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite")
    ):
        raise FileNotFoundError("incomplete isolated checkpoint")
    sid = (SOURCE / "session-id.txt").read_text().strip()
    service = AcademicMCPCheckpointService(project_root=DATA_ROOT, state_dir=source_backup.parent)
    checkout = checkout_counted_donors(service, sid, (EXPECTED_GEN,))
    parent = checkout.compiled_by_hash[checkout.donors[0].strategy_hash]
    market = checkout.market
    info = {
        "parent_generation": EXPECTED_GEN,
        "parent_strategy_sha": parent.strategy_hash,
        "parent_report_sha": checkout.donors[0].report_hash,
        "parent_evidence_sha": checkout.donors[0].evidence_hash,
        "parent_dataset_hash": market.dataset_hash,
        "source_G452_ledger_head": checkout.original_session_head_hash,
        "counted_source_replay_verified": checkout.donors[0].replay_verified,
        "dataset_bars": len(market.bars),
        "zone": str(market.zone),
    }
    return market, parent, info


def _snapshot(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with (
            sqlite3.connect((ORIGINAL / name).resolve().as_uri() + "?mode=ro", uri=True) as src,
            sqlite3.connect(destination / name) as dst,
        ):
            src.backup(dst)


def _compile_arm(parent: Any, market: Any, arm: dict[str, Any], prereg_hash: str) -> Any:
    if not arm["filters"]:
        if arm["id"] != "B0_PARENT":
            raise AssertionError("only baseline may have no extra conditions")
        return parent
    old = parent.strategy.model_dump(mode="json", by_alias=True)
    old["id"] = parent.strategy.strategy_id + "_A11_" + arm["id"].lower()
    old["parents"] = list(parent.strategy.parents) + [parent.strategy_hash]
    old["provenance"] = {
        "source_type": "SCRIPTED_G68_A11_DEVELOPMENT_NOT_GPT",
        "source_path": "scripts.v3_chart_a11_g68_preregistered",
        "source_hash": prereg_hash,
    }
    for item in arm["filters"]:
        alias = item["alias"]
        if alias in old["features"]:
            raise ValueError("A11 feature alias collides with parent")
        feature = FeatureRef(
            feature_id=item["feature_id"],
            timeframe="1d",
            lag_bars=item["lag_bars"],
        )
        old["features"][alias] = feature.model_dump(mode="json")
        old["entry"]["conditions"].append(
            {
                "op": item["op"],
                "left": alias,
                "value": item["value"],
                "enabled": True,
            }
        )
    if (
        old["exit"] != parent.strategy.exit.model_dump(mode="json")
        or old["risk"] != parent.strategy.risk.model_dump(mode="json")
        or old["regime_filters"]
        != [c.model_dump(mode="json") for c in parent.strategy.regime_filters]
    ):
        raise ValueError("A11 changed parent risk, exit or regime")
    if old["entry"]["logic"] != "AND":
        raise ValueError("predeclared entry gate only supports parent AND")
    child = StrategyIR.model_validate(old)
    try:
        bound = bind_inherited_features(parent, child, market, allow_chart_research=arm["optin"])
    except InheritedFeatureBindingError:
        raise
    if (
        bound.strategy_hash == parent.strategy_hash
        or bound.dataset_hash != parent.dataset_hash
        or bound.broker_executable is not False
        or bound.sealed_oos_approved is not False
    ):
        raise ValueError("A11 child bound outside permitted study or duplicate")
    for item in arm["filters"]:
        ref = bound.strategy.features[item["alias"]]
        known = _new_feature_vector(ref, market, allow_chart_research=arm["optin"])
        if bound.feature_values[item["alias"]] != known:
            raise AssertionError("A11 feature vector does not equal typed source")
    return bound


def _metrics(compiled: Any, market: Any, extra: list[dict[str, Any]]) -> dict[str, Any]:
    audit = audit_inherited_decisions(compiled, market)
    executed = evaluate_compiled_development(compiled, market)
    if audit.evaluation.equity_hash != executed.equity_hash:
        raise ValueError("audit and direct costed engine equity differ")
    if audit.evaluation.trades != executed.trades:
        raise ValueError("trade-by-trade canonical replay disagreement")
    closed, exposure = fill_exposure(executed.trades, market.bars)
    if closed != len(audit.round_trips):
        raise ValueError("closed trade count differs from fill trace")
    metrics = calculate_metrics(
        executed.equity_curve,
        tuple(row.net_pnl for row in audit.round_trips),
        periods_per_year=252.0,
        exposure=exposure,
        turnover=sum(abs(t.notional) for t in executed.trades) / executed.initial_cash,
    )
    if metrics.trade_count != closed:
        raise ValueError("closed trade metric mismatch")
    year_ends: dict[str, float] = {}
    for index, bar in enumerate(market.bars):
        year_ends[str(bar.timestamp.year)] = executed.equity_curve[index]
    previous_equity = executed.initial_cash
    per_year_return: dict[str, float] = {}
    for year, ending in sorted(year_ends.items()):
        per_year_return[year] = ending / previous_equity - 1
        previous_equity = ending
    return {
        "strategy_sha": compiled.strategy_hash,
        "strategy_id": compiled.strategy.strategy_id,
        "replay_sha": compiled.replay.replay_hash,
        "equity_sha": executed.equity_hash,
        "audit_trace_sha": audit.trace_hash,
        "cost_model": "academic-research-cost-v1",
        "total_return": metrics.total_return,
        "max_drawdown": metrics.max_drawdown,
        "annualized_return": metrics.cagr,
        "sharpe": metrics.sharpe,
        "sortino": metrics.sortino,
        "closed_trades": closed,
        "fill_count": len(executed.trades),
        "trading_costs": executed.total_paid_costs,
        "market_exposure": metrics.exposure,
        "turnover_cash_multiple": metrics.turnover,
        "extra_filter_bars_passed": {
            item["alias"]: sum(
                (
                    val is not None
                    and ((float(val) > item["value"]) if item["op"] == "greater_than" else False)
                )
                for val in compiled.feature_values[item["alias"]][:-1]
            )
            for item in extra
        },
        "development_calendar_year_returns": per_year_return,
        "first_fill": executed.trades[0].timestamp if executed.trades else None,
        "last_fill": executed.trades[-1].timestamp if executed.trades else None,
        "economic_promotion_eligible": False,
    }


def run_a11(*, save: bool = True) -> dict[str, Any]:
    manifest = read_prereg()
    with tempfile.TemporaryDirectory(prefix="quant-v3-A11-g68-isolated-") as temp:
        checkout_root = Path(temp) / "research"
        snap = checkout_root / "academic-gpt-checkpoints"
        _snapshot(snap)
        market, parent, source = checkout_g68(snap)
        if (
            source["parent_strategy_sha"] != manifest["parent_strategy_sha"]
            or source["parent_report_sha"] != manifest["parent_gateway_report_sha"]
            or source["parent_dataset_hash"] != manifest["dataset_sha"]
            or source["dataset_bars"] != manifest["market_bars"]
            or market.zone != DataZone.DEVELOPMENT
            or any(bar.timestamp.year >= 2026 for bar in market.bars)
        ):
            raise ValueError("preregistered G68 source provenance does not match")
        if not source["counted_source_replay_verified"]:
            raise ValueError("G68 donor is not ledger certified")
        if parent.broker_executable or parent.sealed_oos_approved:
            raise PermissionError("A11 cannot use broker or OOS-enabled parent")
        parent_exit = parent.strategy.exit.model_dump(mode="json")
        parent_risk = parent.strategy.risk.model_dump(mode="json")
        arms: list[dict[str, Any]] = []
        for planned in manifest["arms"]:
            compiled = _compile_arm(parent, market, planned, manifest["freeze_hash"])
            if (
                compiled.strategy.exit.model_dump(mode="json") != parent_exit
                or compiled.strategy.risk.model_dump(mode="json") != parent_risk
            ):
                raise AssertionError("A11 parent exit or risk changed")
            base_metadata = {
                "arm": planned["id"],
                "family": planned["family"],
                "role": planned["role"],
                "candidate_budget": 1,
                "filter_count": len(planned["filters"]),
                "new_feature_ids": [x["feature_id"] for x in planned["filters"]],
                "data_status": "REUSED_NON_PIT_DEVELOPMENT",
            }
            try:
                actual = _metrics(compiled, market, planned["filters"])
            except ResearchCatalogError as exc:
                if (
                    planned["id"] != "B4_DELAYED_CONTROL"
                    or "inherited fill has no valid close decision" not in str(exc)
                ):
                    raise
                # Original B4 is preregistered to lag35. The inherited binder
                # has *already* applied lag35, but the canonical backtester
                # applies StrategyIR.reference.lag_bars a second time. The
                # audit catches this mismatch. Do NOT silently redefine B4.
                arms.append(
                    {
                        **base_metadata,
                        "status": "BLOCKED_DOUBLE_LAG_PROVENANCE",
                        "reason": str(exc),
                        "attempted_strategy_sha": compiled.strategy_hash,
                        "research_feature_ref_lag_bars": 35,
                        "counted_as_valid_evaluation": False,
                    }
                )
                continue
            arms.append(
                {
                    **base_metadata,
                    "status": "VALID_COSTED_DEVELOPMENT_REPLAY",
                    "counted_as_valid_evaluation": True,
                    **actual,
                }
            )
    assert len(arms) == 6 and arms[0]["arm"] == "B0_PARENT"
    base = arms[0]
    for row in arms:
        if not row["counted_as_valid_evaluation"]:
            continue
        row["delta_return_vs_parent_percentage_points"] = (
            row["total_return"] - base["total_return"]
        ) * 100
        row["delta_mdd_vs_parent_percentage_points"] = (
            row["max_drawdown"] - base["max_drawdown"]
        ) * 100
    return_match = abs(base["total_return"] - 0.6067529662408822)
    if return_match > 1e-9 or base["closed_trades"] != 35:
        raise AssertionError("A11 G68 baseline failed original costed evidence")
    if base["max_drawdown"] < 0.15954 or base["max_drawdown"] > 0.15955:
        raise AssertionError("A11 G68 baseline max drawdown mismatch")
    report: dict[str, Any] = {
        "schema": "quant-v3-chart-A11-G68-six-arm-scripted-development-v1",
        "observed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "scope": "A11_PHASE1_SCRIPTED_DEVELOPMENT_NOT_AUTONOMOUS_GPT",
        "preregistration_hash": manifest["freeze_hash"],
        "parent_source": source,
        "arm_count": len(arms),
        "valid_costed_arm_count": sum(x["counted_as_valid_evaluation"] for x in arms),
        "blocked_arm_count": sum(not x["counted_as_valid_evaluation"] for x in arms),
        "all_preregistered_arms_completed": all(x["counted_as_valid_evaluation"] for x in arms),
        "evaluations_per_arm": 1,
        "development_bars": manifest["market_bars"],
        "random_seed_frozen_but_unused": manifest["seed"],
        "fee_slippage_policy": "academic-research-cost-v1 constant across all arms",
        "candidate_arms": arms,
        "real_G68_parent_audited": True,
        "QQQ_same_snapshot_price_only_reference": (
            market.bars[-1].close / market.bars[0].close - 1
        ),
        "all_arms_share_dataset": True,
        "all_arms_same_exit_and_risk": True,
        "all_arms_use_next_open": False,  # B4 cannot be reconciled
        "valid_costed_arms_use_next_open": True,
        "original_ledger_modified": False,
        "no_new_counted_generations": True,
        "independent_OOS_accessed": False,
        "release_authorized": False,
        "gpt_calls_performed": 0,
        "model_generated_candidates": 0,
        "statistical_significance_established": False,
        "alpha_improvement_proved": False,
        "lag_binding_integrity_failure": (
            "StrategyIR lag35 is preapplied in _new_feature_vector and applied "
            "again by core.backtest.engine._feature_values. Original B4 is "
            "reported BLOCKED; do not edit protected engine or re-register."
        ),
        "limitations": [
            "One scripted candidate per arm is not a full GPT/autonomous equal-budget mutation study.",
            "Only one representative of +40 and two pattern family signals are tested, no family-level efficacy claim.",
            "Conjunctive B3 has more gates than B1 or B2; comparison isolates these fixed policies, not equal complexity.",
            "All results use reused, non-PIT, repeatedly seen QQQ 2020-2025 development data.",
            "35-bar delayed event is an eligible causal control, not random shuffling of future prices.",
            "Missing PIT provenance, 2026 sealed OOS, repeated seeds, randomized candidate sampling and multiple-testing corrections.",
            "No live/paper trading approval, no parent/champion promotion or original G research ledger writes.",
            "B4 negative lagged control is BLOCKED by double lag in inherited adapter vs canonical backtester, so full A11 study is incomplete.",
        ],
    }
    for row in arms:
        if row["counted_as_valid_evaluation"]:
            row["delta_vs_QQQ_price_only_pp"] = (
                row["total_return"] - report["QQQ_same_snapshot_price_only_reference"]
            ) * 100
    report["result_content_hash"] = content_hash(
        {k: v for k, v in report.items() if k not in ("observed_at_kst", "result_content_hash")}
    )
    if save:
        (OUT / "quant-v3-chart-A11-G68-diagnostic-results-20261029.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        body = [
            "# Quant V3 A11 — 실제 G68 원장 검증 부모·고정 6군 사전등록 진단",
            "",
            "**상태: SCRIPTED, reused non-PIT DEVELOPMENT ONLY. GPT 완결 세대/독립 알파 실증 아님.**",
            f"- 사전등록 SHA: `{report['preregistration_hash']}`; 데이터 SHA: `{source['parent_dataset_hash']}`.",
            f"- 부모 G68 StrategyIR SHA: `{source['parent_strategy_sha']}`, source gateway S7 SHA `{source['parent_report_sha']}`.",
            "- G452 원장은 임시 SQLite backup으로만 조회, 완료 세대수 증가 0, OOS 접근 0.",
            f"- {manifest['market_bars']}봉, 모든 군 동일 비용·시장·출입 비용/슬리피지·exit·risk, 각 1 후보 평가.",
            f"- 동기간 QQQ 가격만 보유: {report['QQQ_same_snapshot_price_only_reference'] * 100:+.2f}% (배당/거래비용 제외).",
            "- B4는 사전등록한 lag35 음성 대조군이지만 연구 binder/백테스트의",
            "  중복 지연을 감사기가 검출하여 **유효 실험 미완료(BLOCKED)**.",
            "  사후에 B4 정의를 바꾸어 유리한 결과로 재평가하지 않음.",
            "",
            "| 군 | 성격 | 누적 수익률 | 최대 낙폭 | 완료 거래 | 거래비용 | 부모 대비 수익률 격차 |",
            "|---|---|---:|---:|---:|---:|---:|",
            *[
                (
                    f"| {r['arm']} | {r['family']} | {r['total_return'] * 100:+.2f}% | "
                    f"{r['max_drawdown'] * 100:.2f}% | {r['closed_trades']} | "
                    f"{r['trading_costs']:.2f} | "
                    f"{r['delta_return_vs_parent_percentage_points']:+.2f}%p |"
                    if r["counted_as_valid_evaluation"]
                    else f"| {r['arm']} | {r['family']} | BLOCKED | - | - | - | - |"
                )
                for r in arms
            ],
            "",
            "## 연도별 개발기간 NAV 변화(독립 검증 아님)",
            "",
            "| 실험군 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *[
                (
                    f"| {r['arm']} | "
                    + " | ".join(
                        f"{r['development_calendar_year_returns'].get(str(y), 0) * 100:+.1f}%"
                        for y in range(2020, 2026)
                    )
                    + " |"
                    if r["counted_as_valid_evaluation"]
                    else f"| {r['arm']} | 미검증 | 미검증 | 미검증 | 미검증 | 미검증 | 미검증 |"
                )
                for r in arms
            ],
            "",
            "## 판정 제한",
            "",
            "- B1은 double-bottom 1개의 bullish 확정 pulse; 하모닉 전계열 아님.",
            "- B2는 Elliott ABC 외곽 기하학 이벤트, 5-3-5 내부 확인 아님.",
            "- B40은 EFI 한 출력만 적용, 40개 전체를 사용한 자동 연구가 아님.",
            "- B3은 신규 규칙 3개 AND 게이트여서 B1/B2와 복잡도 같지 않음.",
            "- 참값을 바꿔 성능을 맞추지 않은 사전등록 단일 후보; 탐색 예산은 군당 1개.",
            "- 데이터는 비PIT이고 여러 번 관찰된 개발기간. 정밀도·유의성·상업적 수익성·독립성 주장 금지.",
            "- 현재 상위 V05→T4→V01~V04→V06→V07 우선순위 변경 없음.",
            "",
        ]
        (OUT / "quant-v3-chart-A11-G68-diagnostic-report-20261029.md").write_text(
            "\n".join(body), encoding="utf-8"
        )
    return report


if __name__ == "__main__":
    x = run_a11()
    print(
        json.dumps(
            {
                "parent": x["parent_source"],
                "preregistration_hash": x["preregistration_hash"],
                "arms": [
                    (
                        {
                            k: row[k]
                            for k in (
                                "arm",
                                "total_return",
                                "max_drawdown",
                                "closed_trades",
                                "trading_costs",
                                "delta_return_vs_parent_percentage_points",
                            )
                        }
                        if row["counted_as_valid_evaluation"]
                        else {"arm": row["arm"], "status": row["status"], "reason": row["reason"]}
                    )
                    for row in x["candidate_arms"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
