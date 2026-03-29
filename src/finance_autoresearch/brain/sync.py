from __future__ import annotations

from pathlib import Path
from typing import Any

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer
from finance_autoresearch.state.models import BrainNoteRecord, IterationHistoryRecord
from finance_autoresearch.state.repository import StateRepository

from .indexer import BrainIndexer
from .models import BrainNote
from .writer import BrainWriter


class BrainSync:
    def __init__(
        self,
        *,
        store: StateRepository,
        writer: BrainWriter,
        indexer: BrainIndexer | None = None,
        localizer: OutputLocalizer | None = None,
    ) -> None:
        self._store = store
        self._writer = writer
        self._localizer = localizer or DEFAULT_LOCALIZER
        self._indexer = indexer or BrainIndexer(localizer=self._localizer)

    def export_iteration_bundle(self, *, run_id: str, iteration: int) -> list[BrainNoteRecord]:
        record = self._store.get_iteration_history_entry(run_id=run_id, iteration=iteration)
        if record is None:
            return []
        saved = self._write_iteration_notes(record)
        self.rebuild_maps()
        return saved

    def rebuild_generated_notes(self, *, limit: int = 2000) -> list[BrainNoteRecord]:
        saved: list[BrainNoteRecord] = []
        records = self._store.list_iteration_history(limit=limit)
        for record in reversed(records):
            saved.extend(self._write_iteration_notes(record))
        return saved

    def rebuild_brain(self, *, limit: int = 2000) -> tuple[list[BrainNoteRecord], list[BrainNoteRecord]]:
        notes = self.rebuild_generated_notes(limit=limit)
        maps = self.rebuild_maps()
        return notes, maps

    def _write_iteration_notes(self, record: IterationHistoryRecord) -> list[BrainNoteRecord]:
        notes = self._notes_for_record(record)
        return self._save_notes(
            notes=notes,
            run_id=record.run_id,
            iteration=record.iteration,
        )

    def _notes_for_record(self, record: IterationHistoryRecord) -> list[BrainNote]:
        notes: list[BrainNote] = []
        notes.append(self._iteration_note(record))
        if record.experiment is not None:
            notes.append(self._experiment_note(record))
            notes.append(self._strategy_note(record))
            notes.append(self._baseline_note(record))
        if record.lesson is not None:
            notes.append(self._lesson_note(record))
        if record.decision in {"rollback", "crash"}:
            notes.append(self._failure_note(record))
        if record.research_plan is not None:
            notes.append(self._family_note(record))
        return notes

    def _save_notes(
        self,
        *,
        notes: list[BrainNote],
        run_id: str,
        iteration: int,
    ) -> list[BrainNoteRecord]:
        saved: list[BrainNoteRecord] = []
        for note in notes:
            path = self._writer.write_note(note)
            saved.append(
                self._store.record_brain_note(
                    note_type=note.note_type,
                    path=self._relative_to_root(path),
                    title=note.title,
                    generated=note.generated,
                    run_id=run_id,
                    iteration=iteration,
                    revision=_extract_revision(note.frontmatter),
                    metadata=dict(note.frontmatter),
                )
            )
        return saved

    def rebuild_maps(self) -> list[BrainNoteRecord]:
        notes = self._store.list_brain_notes(limit=2000)
        saved: list[BrainNoteRecord] = []
        for note in self._indexer.build_maps(notes):
            path = self._writer.write_map(note)
            saved.append(
                self._store.record_brain_note(
                    note_type="map",
                    path=self._relative_to_root(path),
                    title=note.title,
                    generated=True,
                    metadata={"sections": [section for section, _ in note.sections]},
                )
            )
        return saved

    def _relative_to_root(self, path: Path) -> str:
        return path.resolve().relative_to(self._writer.root.resolve()).as_posix()

    def _iteration_note(self, record: IterationHistoryRecord) -> BrainNote:
        experiment = record.experiment
        relative_path = Path("01 Iterations") / f"{record.run_id}-{record.iteration}.md"
        links = _build_iteration_links(record)
        frontmatter = {
            "id": f"{record.run_id}-{record.iteration}",
            "note_type": "iteration",
            "generated": True,
            "project_id": experiment.project_id if experiment is not None else "finance",
            "run_id": record.run_id,
            "iteration": record.iteration,
            "decision": record.decision or "",
            "candidate_revision": experiment.candidate_revision if experiment is not None else "",
            "baseline_revision": experiment.baseline_revision if experiment is not None else "",
            "score": _experiment_score(record),
            "tags": ["brain", "iteration", record.decision or "unknown"],
            "links": links,
        }
        body = "\n".join(
            [
                f"# {self._localizer.docs('brain.title.iteration', iteration=record.iteration)}",
                "",
                f"- {self._localizer.docs('brain.field.decision')}: `{record.decision or 'unknown'}`",
                f"- {self._localizer.docs('brain.field.run')}: `{record.run_id}`",
                f"- {self._localizer.docs('brain.field.score')}: `{_experiment_score(record)}`",
                "",
                f"## {self._localizer.docs('brain.section.links')}",
                "",
                *[f"- [[{item}]]" for item in links],
            ]
        )
        return BrainNote(
            note_type="iteration",
            title=self._localizer.docs("brain.title.iteration", iteration=record.iteration),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body=body,
        )

    def _experiment_note(self, record: IterationHistoryRecord) -> BrainNote:
        experiment = record.experiment
        assert experiment is not None
        relative_path = (
            Path("02 Experiments")
            / f"{record.run_id}-{record.iteration}-{experiment.candidate_revision}.md"
        )
        backtest_metrics = experiment.backtest_metrics
        score = backtest_metrics.get("score")
        guardrail_failures = backtest_metrics.get("guardrail_failures", [])
        links = _build_iteration_links(record)
        frontmatter = {
            "id": f"experiment-{record.run_id}-{record.iteration}",
            "note_type": "experiment",
            "generated": True,
            "project_id": experiment.project_id,
            "run_id": record.run_id,
            "iteration": record.iteration,
            "decision": record.decision,
            "candidate_revision": experiment.candidate_revision,
            "baseline_revision": experiment.baseline_revision,
            "score": score,
            "tags": ["brain", "experiment", record.decision],
            "links": links,
        }
        guardrail_lines = [f"- {item}" for item in guardrail_failures] or [
            f"- {self._localizer.docs('brain.guardrails.passed')}"
        ]
        body = "\n".join(
            [
                f"# {self._localizer.docs('brain.title.experiment', iteration=record.iteration)} {record.run_id}/{record.iteration}",
                "",
                f"## {self._localizer.docs('brain.section.hypothesis')}",
                experiment.hypothesis,
                "",
                f"## {self._localizer.docs('brain.section.mutation_summary')}",
                experiment.mutation_summary,
                "",
                f"## {self._localizer.docs('brain.section.guardrails')}",
                *guardrail_lines,
            ]
        )
        return BrainNote(
            note_type="experiment",
            title=self._localizer.docs("brain.title.experiment", iteration=record.iteration),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body=body,
        )

    def _lesson_note(self, record: IterationHistoryRecord) -> BrainNote:
        lesson = record.lesson
        assert lesson is not None
        relative_path = Path("03 Lessons") / f"{record.run_id}-{record.iteration}-{lesson.decision}.md"
        next_actions = lesson.lesson_output.get("next_actions", [])
        links = _build_iteration_links(record)
        frontmatter = {
            "id": f"lesson-{record.run_id}-{record.iteration}",
            "note_type": "lesson",
            "generated": True,
            "project_id": lesson.project_id,
            "run_id": record.run_id,
            "iteration": record.iteration,
            "decision": lesson.decision,
            "tags": ["brain", "lesson", lesson.decision],
            "links": links,
        }
        body_lines = [
            f"# {self._localizer.docs('brain.title.lesson', iteration=record.iteration)}",
            "",
            lesson.summary,
            "",
            f"## {self._localizer.docs('brain.section.next_actions')}",
            "",
        ]
        if next_actions:
            body_lines.extend(f"- {item}" for item in next_actions)
        else:
            body_lines.append(f"- {self._localizer.docs('brain.none')}")
        return BrainNote(
            note_type="lesson",
            title=self._localizer.docs("brain.title.lesson", iteration=record.iteration),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body="\n".join(body_lines),
        )

    def _failure_note(self, record: IterationHistoryRecord) -> BrainNote:
        relative_path = Path("04 Failures") / f"{record.run_id}-{record.iteration}.md"
        analysis_summary = (
            record.analysis.summary
            if record.analysis is not None
            else self._localizer.docs("brain.title.failure", iteration=record.iteration)
        )
        frontmatter = {
            "id": f"failure-{record.run_id}-{record.iteration}",
            "note_type": "failure",
            "generated": True,
            "project_id": record.experiment.project_id if record.experiment is not None else "finance",
            "run_id": record.run_id,
            "iteration": record.iteration,
            "decision": record.decision or "",
            "tags": ["brain", "failure", record.decision or "unknown"],
            "links": _build_iteration_links(record),
        }
        body = "\n".join(
            [
                f"# {self._localizer.docs('brain.title.failure', iteration=record.iteration)}",
                "",
                analysis_summary,
            ]
        )
        return BrainNote(
            note_type="failure",
            title=self._localizer.docs("brain.title.failure", iteration=record.iteration),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body=body,
        )

    def _family_note(self, record: IterationHistoryRecord) -> BrainNote:
        research_plan = record.research_plan
        assert research_plan is not None
        plan_output = research_plan.plan_output
        family = str(plan_output.get("family", plan_output.get("experiment_type", "unclassified")))
        relative_path = Path("08 Families") / f"{family}.md"
        frontmatter = {
            "id": f"family-{family}",
            "note_type": "family",
            "generated": True,
            "project_id": research_plan.project_id,
            "run_id": record.run_id,
            "iteration": record.iteration,
            "tags": ["brain", "family", family],
            "links": _build_iteration_links(record),
        }
        body = "\n".join(
            [
                f"# {family}",
                "",
                f"- {self._localizer.docs('brain.field.latest_iteration')}: `{record.iteration}`",
                f"- {self._localizer.docs('brain.field.summary')}: {research_plan.summary}",
            ]
        )
        return BrainNote(
            note_type="family",
            title=family.replace("_", " ").title(),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body=body,
        )

    def _strategy_note(self, record: IterationHistoryRecord) -> BrainNote:
        experiment = record.experiment
        assert experiment is not None
        relative_path = Path("09 Strategies") / f"{experiment.candidate_revision}.md"
        links = _build_iteration_links(record)
        frontmatter = {
            "id": f"strategy-{experiment.candidate_revision}",
            "note_type": "strategy",
            "generated": True,
            "project_id": experiment.project_id,
            "run_id": record.run_id,
            "iteration": record.iteration,
            "revision": experiment.candidate_revision,
            "tags": ["brain", "strategy"],
            "links": links,
        }
        body = "\n".join(
            [
                f"# {self._localizer.docs('brain.title.strategy', revision=experiment.candidate_revision)}",
                "",
                f"- {self._localizer.docs('brain.field.candidate_revision')}: `{experiment.candidate_revision}`",
                f"- {self._localizer.docs('brain.field.baseline_revision')}: `{experiment.baseline_revision}`",
                f"- {self._localizer.docs('brain.field.decision')}: `{record.decision}`",
            ]
        )
        return BrainNote(
            note_type="strategy",
            title=self._localizer.docs("brain.title.strategy", revision=experiment.candidate_revision),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body=body,
        )

    def _baseline_note(self, record: IterationHistoryRecord) -> BrainNote:
        experiment = record.experiment
        assert experiment is not None
        relative_path = Path("10 Baselines") / f"{experiment.baseline_revision}.md"
        frontmatter = {
            "id": f"baseline-{experiment.baseline_revision}",
            "note_type": "baseline",
            "generated": True,
            "project_id": experiment.project_id,
            "run_id": record.run_id,
            "iteration": record.iteration,
            "revision": experiment.baseline_revision,
            "tags": ["brain", "baseline"],
            "links": _build_iteration_links(record),
        }
        body = "\n".join(
            [
                f"# {self._localizer.docs('brain.title.baseline', revision=experiment.baseline_revision)}",
                "",
                f"- {self._localizer.docs('brain.field.referenced_by', run_id=record.run_id, iteration=record.iteration)}",
            ]
        )
        return BrainNote(
            note_type="baseline",
            title=self._localizer.docs("brain.title.baseline", revision=experiment.baseline_revision),
            relative_path=relative_path,
            frontmatter=frontmatter,
            body=body,
        )


def _build_iteration_links(record: IterationHistoryRecord) -> list[str]:
    links: list[str] = []
    if record.experiment is not None:
        links.append(f"02 Experiments/{record.run_id}-{record.iteration}-{record.experiment.candidate_revision}")
        links.append(f"09 Strategies/{record.experiment.candidate_revision}")
        links.append(f"10 Baselines/{record.experiment.baseline_revision}")
    if record.lesson is not None:
        links.append(f"03 Lessons/{record.run_id}-{record.iteration}-{record.lesson.decision}")
    if record.research_plan is not None:
        family = str(
            record.research_plan.plan_output.get(
                "family",
                record.research_plan.plan_output.get("experiment_type", "unclassified"),
            )
        )
        links.append(f"08 Families/{family}")
    if record.decision in {"rollback", "crash"}:
        links.append(f"04 Failures/{record.run_id}-{record.iteration}")
    return list(dict.fromkeys(links))


def _experiment_score(record: IterationHistoryRecord) -> Any:
    if record.experiment is None:
        return None
    return record.experiment.backtest_metrics.get("score")


def _extract_revision(frontmatter: dict[str, Any]) -> str | None:
    revision = frontmatter.get("revision")
    if isinstance(revision, str) and revision.strip():
        return revision
    candidate_revision = frontmatter.get("candidate_revision")
    if isinstance(candidate_revision, str) and candidate_revision.strip():
        return candidate_revision
    baseline_revision = frontmatter.get("baseline_revision")
    if isinstance(baseline_revision, str) and baseline_revision.strip():
        return baseline_revision
    return None
