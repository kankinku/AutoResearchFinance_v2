from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from application.catalog_service import FeatureCatalogService
from dashboard.service import DashboardService
from memory.evidence_knowledge import failure_context
from research.llm.codex_exec import record_intent, sanitize_context
from research.llm.director import ResearchIntent


class ResearchService:
    """Coordinate read-only research context and validated intent persistence."""

    def __init__(
        self,
        state_dir: Path,
        *,
        dashboard: DashboardService | None = None,
        catalog: FeatureCatalogService | None = None,
    ) -> None:
        self.state_dir = state_dir.resolve()
        self.dashboard = dashboard or DashboardService(self.state_dir)
        self.catalog = catalog or FeatureCatalogService()

    def context(self) -> dict[str, object]:
        snapshot = self.dashboard.snapshot()
        observations = [
            {
                "run_id": item.run_id,
                "strategy_hash": item.strategy_hash,
                "generation": item.generation,
                "score": item.score,
                "total_return": item.total_return,
                "nasdaq_excess_return": item.nasdaq_excess_return,
                "max_drawdown": item.max_drawdown,
                "risk_compliant": item.risk_compliant,
                "status": item.status,
            }
            for item in snapshot.tests[:20]
        ]
        payload = sanitize_context(
            {
                "failure_knowledge": failure_context(self.state_dir),
                "generation": snapshot.strategy.generation or 0,
                "champion": snapshot.strategy.model_dump(mode="json"),
                "frontier": [],
                "observations": observations,
                "feature_catalog": self.catalog.research_features(),
            }
        )
        if not isinstance(payload, dict):
            raise ValueError("research context must be an object")
        return {str(key): value for key, value in payload.items()}

    def evidence(self, run_id: str | None = None) -> dict[str, Any]:
        return self.dashboard.research_evidence(run_id)

    def record_intent(self, intent: ResearchIntent) -> None:
        record_intent(self.state_dir / "llm" / "intents.jsonl", intent)

    def validate_and_record_intent(self, arguments: Mapping[str, Any]) -> dict[str, object]:
        intent = ResearchIntent.model_validate(dict(arguments))
        payload = sanitize_context(intent.model_dump(mode="json", exclude_none=True))
        if not isinstance(payload, dict):
            raise ValueError("research intent payload must be an object")
        self.record_intent(intent)
        return {
            "status": "VALIDATED",
            "intent": {str(key): value for key, value in payload.items()},
        }
