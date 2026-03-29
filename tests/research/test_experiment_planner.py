from __future__ import annotations

from types import SimpleNamespace

from finance_autoresearch.research import HeuristicExperimentPlanner, KnowledgeSnippet


def make_analysis(*, summary: str = "", weaknesses: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        analysis_output={
            "summary": summary,
            "strengths": [],
            "weaknesses": weaknesses or [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
        }
    )


def make_experiment(*, failures: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        backtest_metrics={
            "guardrail_failures": failures or [],
        }
    )


def make_lesson() -> SimpleNamespace:
    return SimpleNamespace(
        lesson_output={
            "lessons": [
                {"statement": "Preserve exposure before chasing Sharpe."},
                {"statement": "Preserve exposure before chasing Sharpe."},
                {"statement": "Relax one filter before adding a new signal."},
            ],
            "next_actions": [
                "Relax one filter before adding a new signal.",
                "Try a volatility filter replacement.",
                "Ignore this extra action because of the cap.",
            ],
        }
    )


def make_indicator_snippet(name: str, *tags: str) -> KnowledgeSnippet:
    return KnowledgeSnippet(
        source_id=f"knowledge/indicators/{name}.md",
        title=f"{name.title()} notes",
        source_path=f"knowledge/indicators/{name}.md",
        sha256=name * 8,
        excerpt=f"{name} note",
        tags=("knowledge-pack", "indicators", *tags),
        relevance_reason="matched current issue",
        score=2.0,
    )


def test_planner_selects_simplify_filters_for_trade_count_failures() -> None:
    plan = HeuristicExperimentPlanner().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=make_experiment(failures=["trade_count"]),
        latest_analysis=make_analysis(),
        latest_lesson=None,
        knowledge_snippets=[make_indicator_snippet("rsi", "rsi")],
    )

    assert plan.experiment_type == "simplify_filters"
    assert plan.guardrails_to_watch == ("trade_count",)


def test_planner_selects_stabilize_turnover_for_turnover_signals() -> None:
    plan = HeuristicExperimentPlanner().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=make_experiment(failures=["turnover"]),
        latest_analysis=make_analysis(summary="turnover remains high"),
        latest_lesson=None,
        knowledge_snippets=[make_indicator_snippet("atr", "atr")],
    )

    assert plan.experiment_type == "stabilize_turnover"
    assert any(item["area"] == "volatility filter" for item in plan.planned_mutations)


def test_planner_selects_tighten_risk_for_drawdown_signals() -> None:
    plan = HeuristicExperimentPlanner().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=make_experiment(failures=["drawdown"]),
        latest_analysis=make_analysis(summary="drawdown remains elevated"),
        latest_lesson=None,
        knowledge_snippets=[],
    )

    assert plan.experiment_type == "tighten_risk"


def test_planner_selects_split_regime_for_regime_signals() -> None:
    plan = HeuristicExperimentPlanner().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=make_experiment(),
        latest_analysis=make_analysis(
            summary="bull and bear performance diverged by regime"
        ),
        latest_lesson=None,
        knowledge_snippets=[],
    )

    assert plan.experiment_type == "split_regime"
    assert plan.regime_policy == "consider_split_bull_bear"


def test_planner_defaults_to_replace_indicator_and_dedups_carry_forward_lessons() -> None:
    plan = HeuristicExperimentPlanner().build_plan(
        baseline_evaluation={"guardrails_passed": True},
        latest_experiment=make_experiment(),
        latest_analysis=make_analysis(summary="no obvious dominant failure"),
        latest_lesson=make_lesson(),
        knowledge_snippets=[],
    )

    assert plan.experiment_type == "replace_indicator"
    assert plan.carry_forward_lessons == (
        "Preserve exposure before chasing Sharpe.",
        "Relax one filter before adding a new signal.",
        "Try a volatility filter replacement.",
    )
