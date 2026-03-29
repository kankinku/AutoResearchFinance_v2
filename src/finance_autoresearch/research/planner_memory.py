from __future__ import annotations

from collections import Counter
from typing import Any

from finance_autoresearch.state.repository import StateRepository

from .models import PlannerMemorySnapshot


KNOWN_FAILURE_TOKENS = (
    "qqq",
    "iwm",
    "btc-usd",
    "1d",
    "2h",
    "bull",
    "bear",
    "turnover",
    "drawdown",
    "trade_count",
    "exposure",
    "turbulence",
    "covariance",
    "vix",
    "metadata",
    "sector",
    "industry",
    "exchange",
    "country",
    "universe",
)


class PlannerMemory:
    def __init__(
        self,
        *,
        state_store: StateRepository,
        history_window: int = 20,
    ) -> None:
        self._state_store = state_store
        self._history_window = history_window

    def build_snapshot(self) -> PlannerMemorySnapshot:
        iterations = self._state_store.list_iteration_history(limit=self._history_window)
        family_counts: Counter[str] = Counter()
        repeated_failure_counts: Counter[str] = Counter()
        carry_forward_lessons: list[str] = []
        linked_note_paths: list[str] = []
        failed_families_from_iterations: list[str] = []

        for record in iterations:
            if record.research_plan is not None:
                family = str(
                    record.research_plan.plan_output.get(
                        "family",
                        record.research_plan.plan_output.get("experiment_type", ""),
                    )
                ).strip()
                if family:
                    family_counts[family] += 1
                    if record.decision in {"rollback", "crash"}:
                        failed_families_from_iterations.append(family)
            if record.lesson is not None:
                lesson_output = record.lesson.lesson_output
                for lesson in lesson_output.get("lessons", []):
                    if not isinstance(lesson, dict):
                        continue
                    statement = str(lesson.get("statement", "")).strip()
                    if statement and statement not in carry_forward_lessons:
                        carry_forward_lessons.append(statement)
                        if len(carry_forward_lessons) == 5:
                            break
                if len(carry_forward_lessons) < 5:
                    for action in lesson_output.get("next_actions", []):
                        statement = str(action).strip()
                        if statement and statement not in carry_forward_lessons:
                            carry_forward_lessons.append(statement)
                            if len(carry_forward_lessons) == 5:
                                break
            if record.analysis is not None:
                analysis_text = " ".join(
                    [
                        record.analysis.summary,
                        " ".join(str(item) for item in record.analysis.analysis_output.get("weaknesses", [])),
                        " ".join(str(item) for item in record.analysis.analysis_output.get("coverage_gaps", [])),
                        " ".join(str(item) for item in record.analysis.analysis_output.get("regime_observations", [])),
                    ]
                ).lower()
                for token in KNOWN_FAILURE_TOKENS:
                    if token in analysis_text:
                        repeated_failure_counts[token] += 1
            if record.experiment is not None:
                for item in record.experiment.backtest_metrics.get("guardrail_failures", []):
                    failure_text = str(item).lower()
                    for token in KNOWN_FAILURE_TOKENS:
                        if token in failure_text:
                            repeated_failure_counts[token] += 1
        family_memory = list(self._state_store.list_family_memory(limit=self._history_window))
        if family_memory:
            for record in family_memory:
                family_counts[record.family] += 1
            family_cooldowns = tuple(
                family
                for family in dict.fromkeys(record.family for record in family_memory)
                if len(
                    [
                        record
                        for record in family_memory
                        if record.family == family and record.outcome in {"rollback", "crash"}
                    ][:3]
                )
                == 3
            )
        else:
            family_cooldowns = tuple(
                family
                for family, count in Counter(failed_families_from_iterations).items()
                if count >= 3
            )
        repeated_failure_signals = tuple(
            token for token, count in repeated_failure_counts.items() if count >= 2
        )
        for note in self._state_store.list_brain_notes(limit=self._history_window * 3):
            if not note.generated:
                continue
            lowered_path = note.path.lower()
            if lowered_path.startswith("00 inbox/") or "/manual/" in lowered_path or lowered_path.endswith("/manual.md"):
                continue
            if note.path not in linked_note_paths:
                linked_note_paths.append(note.path)
            if len(linked_note_paths) == 24:
                break

        return PlannerMemorySnapshot(
            history_window=self._history_window,
            family_counts=dict(family_counts),
            family_cooldowns=family_cooldowns,
            repeated_failure_signals=repeated_failure_signals,
            carry_forward_lessons=tuple(carry_forward_lessons[:5]),
            linked_note_paths=tuple(linked_note_paths),
        )
