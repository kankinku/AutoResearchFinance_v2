"""Run one externally-directed research hypothesis without executing an LLM locally."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from application.evaluation_service import EvaluationService
from core.data.parquet import ParquetDataProvider
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from memory.research_evidence import research_evidence
from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    resolve_project_input,
)
from research.llm.director import ResearchIntent
from research.llm.gpt_context import record_intent
from research.llm.intent_bridge import apply_intent, intent_to_operations
from runtime.evidence_session import EvidenceSession
from strategy_ir.normalizer import normalize_source


class ChatDirectedResearchService:
    """The external MCP caller owns the hypothesis; local code owns validation."""

    def __init__(
        self, *, project_root: Path, state_dir: Path, evaluation: EvaluationService
    ) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = state_dir.resolve()
        self.evaluation = evaluation

    def run(
        self,
        *,
        source_path: str,
        data_path: str,
        intent_payload: dict[str, Any],
        method: str = "random",
        count: int = 1,
        seed: int = 0,
        min_trades: int = 10,
        min_annual_trades: int = 30,
        min_qqq_cagr_delta: float | None = None,
        series_data_path: str | None = None,
        previous_research_run_id: str | None = None,
    ) -> dict[str, object]:
        if method not in {"grid", "random", "bayesian"}:
            raise ValueError("invalid experiment method")
        if count < 1 or seed < 0 or min_trades < 0 or min_annual_trades < 0:
            raise ValueError("invalid experiment parameters")
        source = resolve_project_input(self.project_root, source_path, ALLOWED_STRATEGY_SUFFIXES)
        data = resolve_project_input(self.project_root, data_path, frozenset({".parquet"}))
        if series_data_path is not None:
            resolve_project_input(self.project_root, series_data_path, frozenset({".parquet"}))
        imported = normalize_source(source)
        if imported.strategy is None:
            raise ValueError("strategy source is unsupported")
        parent = imported.strategy
        intent = ResearchIntent.model_validate(intent_payload)
        if len(intent.parent_ids) != 1:
            raise ValueError("exactly one source parent is required; crossover is not supported")
        if intent.primitive_request is not None:
            raise ValueError("unregistered primitive requests cannot be executed")
        feature_specs = research_feature_specs()
        operations = intent_to_operations(intent, feature_specs)
        # Verifies selected parent, mutation paths and registered feature selection.
        apply_intent(parent, intent, feature_specs)
        if previous_research_run_id is not None:
            if not isinstance(previous_research_run_id, str) or not re.fullmatch(
                r"[0-9a-f]{32}", previous_research_run_id
            ):
                raise ValueError("previous research run ID must be 32 lowercase hex characters")
            preceding = research_evidence(self.state_dir, previous_research_run_id)["runs"]
            if len(preceding) != 1 or preceding[0]["status"] != "COMPLETED":
                raise ValueError("previous research run is missing or not completed")
            previous_candidates = [
                candidate
                for event in EvidenceStore(self.state_dir).events()
                if event["kind"] == "attempt"
                and event["payload"]["research_run_id"] == previous_research_run_id
                and event["payload"]["status"] == "COMPLETED"
                for candidate in event["payload"].get("candidates", [])
            ]
            current_data_hash = ParquetDataProvider.read(data).dataset_hash
            if not previous_candidates or any(
                candidate.get("dataset_hash") != current_data_hash
                for candidate in previous_candidates
            ):
                raise ValueError("previous research evidence and current dataset are incompatible")
        session = EvidenceSession(
            self.state_dir,
            requested_generations=1,
            seed=seed,
            settings={
                "controller": "external_mcp_client",
                "intent_hash": content_hash(intent.model_dump(mode="json", exclude_none=True)),
                "parent_id": parent.strategy_id,
                "previous_research_run_id": previous_research_run_id,
                "method": method,
                "count": count,
            },
        )
        record_intent(self.state_dir / "llm" / "intents.jsonl", intent)
        try:
            result = session.evaluate(
                self.evaluation.run,
                source_path=source.relative_to(self.project_root).as_posix(),
                data_path=data.relative_to(self.project_root).as_posix(),
                method=method,
                count=count,
                seed=seed,
                generation=1,
                min_trades=min_trades,
                min_annual_trades=min_annual_trades,
                min_qqq_cagr_delta=min_qqq_cagr_delta,
                series_data_path=series_data_path,
                operations=operations,
                strategy_override=parent,
            )
        except EvidenceIntegrityError:
            # Untrusted or inconsistent immutable Evidence must not be masked.
            raise
        except Exception:
            session.finish_generation(1, "FAILED", None)
            session.finish_run("FAILED")
            raise
        session.finish_generation(1, str(result.get("status", "UNKNOWN")), result)
        session.finish_run("COMPLETED")
        return {
            **result,
            "parent_id": parent.strategy_id,
            "llm_controller": "external_mcp_client",
            "previous_research_run_id": previous_research_run_id,
            "orders_enabled": False,
        }
