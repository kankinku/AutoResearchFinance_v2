from __future__ import annotations

from pathlib import Path

import application.evaluation_service as evaluation_module
from application.catalog_service import FeatureCatalogService
from application.evaluation_service import EvaluationService
from application.research_service import ResearchService
from application.services import create_application_services


def test_feature_catalog_service_preserves_research_projection() -> None:
    features = FeatureCatalogService().research_features()

    assert len(features) == 173
    assert set(features[0]) == {
        "name",
        "family",
        "inputs",
        "calculator",
        "lookback",
        "timeframe",
    }
    assert any(item["name"] == "rsi" for item in features)


def test_research_service_builds_sanitized_context_and_records_intent(tmp_path: Path) -> None:
    service = ResearchService(tmp_path / "state")

    context = service.context()
    assert context["failure_knowledge"] == []
    assert context["feature_catalog"]
    assert "raw_market_rows" not in context
    assert "sealed_oos" not in context

    payload = service.validate_and_record_intent(
        {
            "mode": "structure",
            "parent_ids": ["champion-1"],
            "operations": [],
            "rationale": "preserve the existing application contract",
        }
    )

    assert payload["status"] == "VALIDATED"
    assert (tmp_path / "state" / "llm" / "intents.jsonl").is_file()


def test_application_services_share_dashboard_read_model(tmp_path: Path) -> None:
    services = create_application_services(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert services.research.dashboard is services.dashboard
    assert services.research.catalog is services.catalog
    assert services.system.controller.state_dir == (tmp_path / "state").resolve()
    assert services.evaluation.project_root == tmp_path.resolve()


def test_evaluation_service_delegates_without_changing_arguments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_local_evaluation(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "COMPLETED", "candidate_count": 1}

    monkeypatch.setattr(
        evaluation_module,
        "run_local_evaluation",
        fake_run_local_evaluation,
    )
    service = EvaluationService(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
    )

    result = service.run(
        source_path="strategy.json",
        data_path="market.parquet",
        method="random",
        count=8,
        seed=7,
        min_trades=30,
        min_annual_trades=31,
        min_qqq_cagr_delta=0.1,
    )

    assert result == {"status": "COMPLETED", "candidate_count": 1}
    assert captured["project_root"] == tmp_path.resolve()
    assert captured["state_dir"] == (tmp_path / "state").resolve()
    assert captured["source_path"] == "strategy.json"
    assert captured["data_path"] == "market.parquet"
    assert captured["method"] == "random"
    assert captured["count"] == 8
    assert captured["seed"] == 7
    assert captured["min_trades"] == 30
    assert captured["min_annual_trades"] == 31
    assert captured["min_qqq_cagr_delta"] == 0.1
