from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from finance_autoresearch.research.workspace_knowledge import WorkspaceKnowledgeLoader


def test_workspace_knowledge_loader_reuses_cached_documents_until_mtime_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository_root = tmp_path / "repo"
    source_path = repository_root / "knowledge" / "indicators" / "rsi.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("# RSI\ninitial\n", encoding="utf-8")

    loader = WorkspaceKnowledgeLoader(repository_root=repository_root)
    read_calls: list[Path] = []
    original_read = WorkspaceKnowledgeLoader._read_text

    def tracking_read(self: WorkspaceKnowledgeLoader, path: Path) -> str:
        read_calls.append(path)
        return original_read(self, path)

    monkeypatch.setattr(WorkspaceKnowledgeLoader, "_read_text", tracking_read)

    first = loader.load()
    second = loader.load()

    source_path.write_text("# RSI\nupdated\n", encoding="utf-8")
    third = loader.load()

    assert first[0].source_path == "knowledge/indicators/rsi.md"
    assert second[0].source_path == "knowledge/indicators/rsi.md"
    assert third[0].source_path == "knowledge/indicators/rsi.md"
    assert read_calls.count(source_path.resolve()) == 2


def test_workspace_knowledge_loader_reads_linked_brain_notes(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    vault_path = repository_root / "knowledge" / "vault" / "03 Lessons" / "run-001-1-keep.md"
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    vault_path.write_text(
        "\n".join(
            [
                "---",
                'note_type: "lesson"',
                "generated: true",
                "tags:",
                '  - "brain"',
                '  - "lesson"',
                '  - "rsi"',
                "---",
                "",
                "# Lesson",
                "",
                "Relax RSI thresholds and keep regime exposure balanced.",
            ]
        ),
        encoding="utf-8",
    )

    loader = WorkspaceKnowledgeLoader(repository_root=repository_root)
    snippets = loader.load()

    assert any("knowledge/vault/03 Lessons/run-001-1-keep.md" in item.source_path for item in snippets)


def test_workspace_knowledge_loader_keeps_short_finance_acronyms_in_term_matching(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    source_path = repository_root / "knowledge" / "indicators" / "ema.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("# EMA\nEMA and RSI notes.\n", encoding="utf-8")
    loader = WorkspaceKnowledgeLoader(repository_root=repository_root)

    snippets = loader.load(
        latest_analysis=SimpleNamespace(
            analysis_output={
                "summary": "EMA RSI regime drift",
                "strengths": [],
                "weaknesses": [],
                "coverage_gaps": [],
                "regime_observations": [],
                "next_hypothesis_hints": [],
            }
        )
    )

    assert snippets[0].source_path == "knowledge/indicators/ema.md"


def test_workspace_knowledge_loader_reads_factor_catalog_notes(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    source_path = repository_root / "knowledge" / "factors" / "catalog.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "# Factor Catalog\nTurbulence covariance metadata quantile turnover notes.\n",
        encoding="utf-8",
    )
    loader = WorkspaceKnowledgeLoader(repository_root=repository_root)

    snippets = loader.load(
        latest_analysis=SimpleNamespace(
            analysis_output={
                "summary": "turbulence covariance metadata drift",
                "strengths": [],
                "weaknesses": [],
                "coverage_gaps": [],
                "regime_observations": [],
                "next_hypothesis_hints": [],
            }
        )
    )

    assert any(item.source_path == "knowledge/factors/catalog.md" for item in snippets)


def test_workspace_knowledge_loader_allows_reference_only_manual_notes_but_prefers_generated_notes(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    manual_note_path = repository_root / "knowledge" / "vault" / "03 Lessons" / "manual-note.md"
    inbox_note_path = repository_root / "knowledge" / "vault" / "00 Inbox" / "manual-note.md"
    generated_note_path = repository_root / "knowledge" / "vault" / "03 Lessons" / "generated-note.md"
    manual_note_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_note_path.parent.mkdir(parents=True, exist_ok=True)
    generated_note_path.parent.mkdir(parents=True, exist_ok=True)
    manual_note_path.write_text(
        "\n".join(
            [
                "---",
                'note_type: "lesson"',
                "generated: false",
                "tags:",
                '  - "manual"',
                '  - "rsi"',
                "---",
                "",
                "# Manual Note",
                "",
                "This manual note mentions RSI but should not enter planner retrieval.",
            ]
        ),
        encoding="utf-8",
    )
    inbox_note_path.write_text(
        "\n".join(
            [
                "---",
                'note_type: "lesson"',
                "generated: false",
                "tags:",
                '  - "manual"',
                '  - "rsi"',
                "---",
                "",
                "# Inbox Note",
                "",
                "Inbox note should stay excluded.",
            ]
        ),
        encoding="utf-8",
    )
    generated_note_path.write_text(
        "\n".join(
            [
                "---",
                'note_type: "lesson"',
                "generated: true",
                "tags:",
                '  - "brain"',
                '  - "lesson"',
                '  - "rsi"',
                "---",
                "",
                "# Generated Note",
                "",
                "Generated RSI note that should remain eligible for retrieval.",
            ]
        ),
        encoding="utf-8",
    )

    loader = WorkspaceKnowledgeLoader(repository_root=repository_root)
    snippets = loader.load()

    generated = next(item for item in snippets if "generated-note.md" in item.source_path)
    manual = next(item for item in snippets if "manual-note.md" in item.source_path)

    assert any("generated-note.md" in item.source_path for item in snippets)
    assert any("manual-note.md" in item.source_path for item in snippets)
    assert generated.score > manual.score
    assert not any("00 Inbox" in item.source_path for item in snippets)


def test_workspace_knowledge_loader_prioritizes_linked_generated_notes_and_dedupes_by_sha(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    linked_note_path = repository_root / "knowledge" / "vault" / "03 Lessons" / "linked.md"
    duplicate_note_path = repository_root / "knowledge" / "vault" / "03 Lessons" / "duplicate.md"
    linked_note_path.parent.mkdir(parents=True, exist_ok=True)
    note_body = "\n".join(
        [
            "---",
            'note_type: "lesson"',
            "generated: true",
            "tags:",
            '  - "brain"',
            '  - "ema"',
            "---",
            "",
            "# EMA Lesson",
            "",
            "EMA drift note.",
        ]
    )
    linked_note_path.write_text(note_body, encoding="utf-8")
    duplicate_note_path.write_text(note_body, encoding="utf-8")

    loader = WorkspaceKnowledgeLoader(repository_root=repository_root)
    snippets = loader.load(
        latest_analysis=SimpleNamespace(
            analysis_output={
                "summary": "EMA drift",
                "strengths": [],
                "weaknesses": [],
                "coverage_gaps": [],
                "regime_observations": [],
                "next_hypothesis_hints": [],
            }
        ),
        planner_memory_snapshot=SimpleNamespace(linked_note_paths=("03 Lessons/linked.md",)),
    )

    assert snippets[0].source_path.endswith("/knowledge/vault/03 Lessons/linked.md")
    assert sum(1 for item in snippets if item.title == "EMA Lesson") == 1
