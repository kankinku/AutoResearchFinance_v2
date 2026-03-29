from __future__ import annotations

import glob
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finance_autoresearch.brain.reader import BrainReader
from finance_autoresearch.research.knowledge_catalog import KNOWLEDGE_TAG_VOCABULARY

from .models import KnowledgeSnippet


_KNOWLEDGE_ROOTS = (
    "knowledge/indicators",
    "knowledge/factors",
    "knowledge/regimes",
    "knowledge/failures",
    "knowledge/markets",
)
_KNOWLEDGE_EXTENSIONS = (".md", ".txt", ".json", ".yaml", ".yml")
SAFE_KNOWLEDGE_PATTERNS = tuple(
    f"{root}/**/*{extension}"
    for root in _KNOWLEDGE_ROOTS
    for extension in _KNOWLEDGE_EXTENSIONS
) + (
    "docs/superpowers/specs/**/*.md",
    "docs/openclaw-setup.md",
    "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
    "runtime/baseline/accepted_strategy_candidate.py",
)

STOP_WORDS = {
    "about",
    "after",
    "analysis",
    "baseline",
    "candidate",
    "guardrails",
    "improve",
    "improved",
    "iteration",
    "needs",
    "plan",
    "research",
    "result",
    "results",
    "score",
    "should",
    "strategy",
    "summary",
    "that",
    "them",
    "this",
    "with",
}
SHORT_TERM_ALLOWLIST = {"ema", "sma", "rsi", "atr"}


@dataclass(slots=True, frozen=True)
class CachedKnowledgeDocument:
    mtime_ns: int
    text: str
    source_path: str
    title: str
    tags: tuple[str, ...]
    sha256: str


class WorkspaceKnowledgeLoader:
    def __init__(
        self,
        *,
        repository_root: Path | str,
        patterns: tuple[str, ...] = SAFE_KNOWLEDGE_PATTERNS,
        max_documents: int = 6,
        max_excerpt_chars: int = 480,
        brain_root: Path | str | None = None,
        max_linked_notes: int = 12,
        manual_notes_mode: str = "reference_only",
    ) -> None:
        self._repository_root = Path(repository_root)
        self._patterns = patterns
        self._max_documents = max_documents
        self._max_excerpt_chars = max_excerpt_chars
        self._document_cache: dict[Path, CachedKnowledgeDocument] = {}
        self._brain_root = (
            self._resolve_candidate_path(Path(brain_root))
            if brain_root is not None
            else self._resolve_candidate_path(Path("knowledge/vault"))
        )
        self._brain_reader = BrainReader(root=self._brain_root)
        self._max_linked_notes = max_linked_notes
        self._manual_notes_mode = manual_notes_mode

    def load(
        self,
        *,
        latest_experiment: Any = None,
        latest_analysis: Any = None,
        latest_lesson: Any = None,
        planner_memory_snapshot: Any = None,
    ) -> list[KnowledgeSnippet]:
        terms = self._collect_terms(
            latest_experiment=latest_experiment,
            latest_analysis=latest_analysis,
            latest_lesson=latest_lesson,
            planner_memory_snapshot=planner_memory_snapshot,
        )
        snippets: list[KnowledgeSnippet] = []
        seen_paths: set[Path] = set()
        for relative_path in self._iter_candidate_paths():
            resolved_path = self._resolve_candidate_path(relative_path)
            if resolved_path in seen_paths or not resolved_path.exists():
                continue
            seen_paths.add(resolved_path)
            document = self._load_document(resolved_path)
            if not document.text.strip():
                continue
            score, reason = self._score_text(
                resolved_path=resolved_path,
                text=document.text,
                terms=terms,
            )
            if score <= 0:
                continue
            snippets.append(
                KnowledgeSnippet(
                    source_id=document.source_path,
                    title=document.title,
                    source_path=document.source_path,
                    sha256=document.sha256,
                    excerpt=self._build_excerpt(text=document.text, terms=terms),
                    tags=document.tags,
                    relevance_reason=reason,
                    score=score,
                )
            )
        snippets.extend(
            self._load_linked_brain_snippets(
                terms=terms,
                seen_paths=seen_paths,
                linked_note_paths=tuple(
                    str(path)
                    for path in getattr(planner_memory_snapshot, "linked_note_paths", ())
                ),
            )
        )
        deduped = self._dedupe_snippets(snippets)
        deduped.sort(key=lambda item: (-item.score, item.source_path))
        return deduped[: self._max_documents]

    def _iter_candidate_paths(self) -> list[Path]:
        candidates: list[Path] = []
        for pattern in self._patterns:
            if Path(pattern).is_absolute():
                candidates.extend(
                    Path(path).resolve()
                    for path in glob.glob(pattern, recursive=True)
                    if Path(path).is_file()
                )
                continue
            candidates.extend(
                path.relative_to(self._repository_root)
                for path in self._repository_root.glob(pattern)
                if path.is_file()
            )
        return sorted(set(candidates))

    def _collect_terms(
        self,
        *,
        latest_experiment: Any,
        latest_analysis: Any,
        latest_lesson: Any,
        planner_memory_snapshot: Any,
    ) -> set[str]:
        values: list[str] = []
        if latest_experiment is not None:
            values.extend(
                [
                    str(getattr(latest_experiment, "hypothesis", "")),
                    str(getattr(latest_experiment, "mutation_summary", "")),
                ]
            )
            metrics = getattr(latest_experiment, "backtest_metrics", {}) or {}
            failures = metrics.get("guardrail_failures", [])
            values.extend(str(item) for item in failures)
        if latest_analysis is not None:
            analysis_output = getattr(latest_analysis, "analysis_output", {}) or {}
            values.append(str(analysis_output.get("summary", "")))
            for key in (
                "strengths",
                "weaknesses",
                "coverage_gaps",
                "regime_observations",
                "next_hypothesis_hints",
            ):
                values.extend(str(item) for item in analysis_output.get(key, []))
        if latest_lesson is not None:
            lesson_output = getattr(latest_lesson, "lesson_output", {}) or {}
            values.append(str(lesson_output.get("summary", "")))
            values.extend(str(item) for item in lesson_output.get("next_actions", []))
        if planner_memory_snapshot is not None:
            values.extend(str(item) for item in getattr(planner_memory_snapshot, "family_cooldowns", ()))
            values.extend(
                str(item)
                for item in getattr(planner_memory_snapshot, "repeated_failure_signals", ())
            )
            values.extend(
                str(item)
                for item in getattr(planner_memory_snapshot, "carry_forward_lessons", ())
            )

        terms: set[str] = set()
        for value in values:
            for raw_word in value.lower().replace("-", " ").replace("_", " ").split():
                word = "".join(ch for ch in raw_word if ch.isalnum())
                if (
                    (len(word) < 4 and word not in SHORT_TERM_ALLOWLIST)
                    or word in STOP_WORDS
                ):
                    continue
                terms.add(word)
        if not terms:
            terms.update({"regime", "indicator", "strategy", "lesson"})
        return terms

    def _load_linked_brain_snippets(
        self,
        *,
        terms: set[str],
        seen_paths: set[Path],
        linked_note_paths: tuple[str, ...],
    ) -> list[KnowledgeSnippet]:
        if not self._brain_root.exists():
            return []
        linked = self._brain_reader.select_related_snippets(
            terms=terms,
            max_notes=self._max_linked_notes,
            preferred_paths=linked_note_paths,
            manual_notes_mode=self._manual_notes_mode,
        )
        unique_linked: list[KnowledgeSnippet] = []
        for snippet in linked:
            resolved_path = self._resolve_candidate_path(Path(snippet.source_path))
            if resolved_path in seen_paths:
                continue
            seen_paths.add(resolved_path)
            unique_linked.append(snippet)
        return unique_linked

    def _dedupe_snippets(self, snippets: list[KnowledgeSnippet]) -> list[KnowledgeSnippet]:
        ranked = sorted(snippets, key=lambda item: (-item.score, item.source_path))
        deduped: list[KnowledgeSnippet] = []
        seen_sources: set[str] = set()
        seen_hashes: set[str] = set()
        for snippet in ranked:
            if snippet.source_path in seen_sources or snippet.sha256 in seen_hashes:
                continue
            seen_sources.add(snippet.source_path)
            seen_hashes.add(snippet.sha256)
            deduped.append(snippet)
        return deduped

    def _read_text(self, path: Path) -> str:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(payload, indent=2, sort_keys=True)
        return path.read_text(encoding="utf-8")

    def _load_document(self, resolved_path: Path) -> CachedKnowledgeDocument:
        stat = resolved_path.stat()
        cached = self._document_cache.get(resolved_path)
        if cached is not None and cached.mtime_ns == stat.st_mtime_ns:
            return cached

        text = self._read_text(resolved_path)
        source_path = self._display_source_path(resolved_path)
        source_ref = Path(source_path)
        document = CachedKnowledgeDocument(
            mtime_ns=stat.st_mtime_ns,
            text=text,
            source_path=source_path,
            title=self._extract_title(relative_path=source_ref, text=text),
            tags=self._infer_tags(relative_path=source_ref, text=text),
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        self._document_cache[resolved_path] = document
        return document

    def _score_text(
        self,
        *,
        resolved_path: Path,
        text: str,
        terms: set[str],
    ) -> tuple[float, str]:
        lower_text = text.lower()
        match_count = sum(lower_text.count(term) for term in terms)
        relative = resolved_path.relative_to(self._repository_root).as_posix()
        base_score = 0.0
        reason = "Matches current research terms."
        if relative.endswith("strategy_candidate.py"):
            base_score = 5.0
            reason = "Current mutable strategy is always relevant."
        elif relative.endswith("accepted_strategy_candidate.py"):
            base_score = 4.0
            reason = "Accepted baseline anchors the next mutation."
        elif relative.startswith("knowledge/indicators/"):
            base_score = 2.5
            reason = "Indicator notes matched the current issue."
        elif relative.startswith("knowledge/regimes/"):
            base_score = 2.5
            reason = "Regime notes matched the current issue."
        elif relative.startswith("knowledge/factors/"):
            base_score = 2.5
            reason = "Factor catalog notes matched the current issue."
        elif relative.startswith("knowledge/failures/"):
            base_score = 2.5
            reason = "Failure notes matched the current issue."
        elif relative.startswith("knowledge/markets/"):
            base_score = 2.5
            reason = "Market behavior notes matched the current issue."
        elif relative.startswith("docs/superpowers/specs/"):
            base_score = 1.5
            reason = "Project spec may constrain the mutation."
        elif relative == "docs/openclaw-setup.md":
            base_score = 1.0
            reason = "OpenClaw setup notes matched the iteration context."
        score = base_score + float(match_count)
        return score, reason

    def _extract_title(self, *, relative_path: Path, text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return relative_path.stem.replace("_", " ").replace("-", " ").title()

    def _build_excerpt(self, *, text: str, terms: set[str]) -> str:
        compact = " ".join(part.strip() for part in text.splitlines() if part.strip())
        if len(compact) <= self._max_excerpt_chars:
            return compact
        lowered = compact.lower()
        for term in sorted(terms):
            index = lowered.find(term)
            if index >= 0:
                start = max(index - (self._max_excerpt_chars // 3), 0)
                end = min(start + self._max_excerpt_chars, len(compact))
                return compact[start:end].strip()
        return compact[: self._max_excerpt_chars].strip()

    def _infer_tags(self, *, relative_path: Path, text: str) -> tuple[str, ...]:
        tags: list[str] = []
        relative = relative_path.as_posix()
        lower_text = text.lower()
        if relative.startswith("knowledge/"):
            tags.append("knowledge-pack")
            parts = relative.split("/")
            if len(parts) > 1:
                tags.append(parts[1])
        if relative.startswith("docs/superpowers/specs/"):
            tags.append("spec")
        if relative.endswith("strategy_candidate.py"):
            tags.append("current-logic")
        if relative.endswith("accepted_strategy_candidate.py"):
            tags.append("accepted-baseline")
        for keyword in KNOWLEDGE_TAG_VOCABULARY:
            if keyword in lower_text:
                tags.append(keyword)
        return tuple(dict.fromkeys(tags))

    def _resolve_candidate_path(self, candidate_path: Path) -> Path:
        if candidate_path.is_absolute():
            return candidate_path.resolve()
        return (self._repository_root / candidate_path).resolve()

    def _display_source_path(self, resolved_path: Path) -> str:
        try:
            return resolved_path.relative_to(self._repository_root).as_posix()
        except ValueError:
            return resolved_path.as_posix()
