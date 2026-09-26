from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.planning_service import PlanningService
from application.strategy_service import StrategyService
from application.workspace_service import WorkspaceService
from runtime.system_controller import SystemController, SystemLaunchConfig
from strategy_import.sources import CloneManager


def _strategy_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "phase4-strategy",
        "family": "trend",
        "generation": 0,
        "indicators": {"fast": {"type": "SMA", "period": 5}},
        "entry": {
            "logic": "AND",
            "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
        },
        "exit": {
            "logic": "AND",
            "conditions": [{"op": "less_than", "left": "close", "value": 0}],
        },
        "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
    }


def _write_strategy(root: Path, name: str = "strategy.json") -> Path:
    path = root / name
    path.write_text(json.dumps(_strategy_document()), encoding="utf-8")
    return path


def test_workspace_service_initializes_missing_state_without_enabling_orders(
    tmp_path: Path,
) -> None:
    service = WorkspaceService(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    result = service.initialize()

    assert result["status"] == "INITIALIZED"
    assert result["orders_enabled"] is False
    assert set(result["created"]) == {
        "champion",
        "frontier",
        "knowledge",
        "rescue_pool",
        "mode",
    }
    mode = json.loads((tmp_path / "state" / "mode.json").read_text(encoding="utf-8"))
    assert mode["selected_mode"] == "paper"
    assert mode["orders_enabled"] is False


def test_workspace_service_preserves_existing_state_unless_reset_is_explicit(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    service = WorkspaceService(state_dir=state, project_root=tmp_path)
    service.initialize()
    (state / "mode.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected_mode": "live",
                "orders_enabled": True,
                "requested_by": "fixture",
            }
        ),
        encoding="utf-8",
    )

    preserved = service.initialize()
    assert "mode" in preserved["preserved"]
    assert json.loads((state / "mode.json").read_text(encoding="utf-8"))[
        "selected_mode"
    ] == "live"

    safe_status = service.status()
    assert safe_status["selected_mode"] == "live"
    assert safe_status["orders_enabled"] is False

    reset = service.initialize(overwrite=True)
    assert "mode" in reset["created"]
    restored = json.loads((state / "mode.json").read_text(encoding="utf-8"))
    assert restored["selected_mode"] == "paper"
    assert restored["orders_enabled"] is False


def test_strategy_service_validates_and_imports_without_executing_source(
    tmp_path: Path,
) -> None:
    _write_strategy(tmp_path)
    service = StrategyService(project_root=tmp_path)

    validated = service.validate("strategy.json")
    assert validated["status"] == "VALID"
    assert validated["strategy_id"] == "phase4-strategy"

    dry_run = service.import_strategies(source_path="strategy.json")
    assert dry_run["status"] == "DRY_RUN"
    assert dry_run["normalized"] == 1
    assert dry_run["orders_enabled"] is False
    assert not (tmp_path / "strategies" / "catalog.json").exists()

    imported = service.import_strategies(
        source_path="strategy.json",
        dry_run=False,
    )
    assert imported["status"] == "IMPORTED"
    assert imported["normalized"] == 1

    catalog = service.list_strategies()
    assert catalog["count"] == 1
    records = catalog["records"]
    assert isinstance(records, list)
    assert records[0]["strategy_id"] == "phase4-strategy"
    assert "strategy" not in records[0]


def test_strategy_service_confines_local_paths_and_github_source(tmp_path: Path) -> None:
    service = StrategyService(project_root=tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text(json.dumps(_strategy_document()), encoding="utf-8")

    with pytest.raises(PermissionError, match="outside project root"):
        service.validate(str(outside))

    with pytest.raises(ValueError, match="https github.com"):
        service.import_strategies(
            repository_url="http://example.com/repository.git",
        )


def test_list_strategies_is_read_only_when_catalog_is_missing(tmp_path: Path) -> None:
    service = StrategyService(project_root=tmp_path)

    result = service.list_strategies()

    assert result == {"status": "OK", "count": 0, "records": []}
    assert not (tmp_path / "strategies").exists()


def test_planning_service_matches_cli_generation_plan_semantics() -> None:
    result = PlanningService().plan_generation(
        parent_ids=("champion-1", "frontier-2"),
        method="random",
        count=32,
        seed=7,
    )

    assert result == {
        "parent_ids": ["champion-1", "frontier-2"],
        "method": "random",
        "count": 32,
        "seed": 7,
        "search_stage": "parameter",
    }



def test_workspace_mode_and_cache_operations_keep_orders_disabled(tmp_path: Path) -> None:
    service = WorkspaceService(state_dir=tmp_path / "state", project_root=tmp_path)
    service.initialize()
    selected = service.set_mode("live")

    assert selected["selected_mode"] == "live"
    assert selected["orders_enabled"] is False

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "good.json").write_text(
        json.dumps({"experiment_hash": "hash-1"}),
        encoding="utf-8",
    )
    (manifests / "bad.json").write_text("{}", encoding="utf-8")

    cache = service.validate_cache()
    assert cache == {
        "status": "VALIDATED",
        "validated_manifests": 1,
        "orders_enabled": False,
    }

    with pytest.raises(PermissionError, match="outside project root"):
        service.validate_cache(manifest_dir=str(tmp_path.parent / "outside"))



def test_live_mode_selection_cannot_start_paper_research_runtime(tmp_path: Path) -> None:
    state = tmp_path / "state"
    workspace = WorkspaceService(state_dir=state, project_root=tmp_path)
    workspace.initialize()
    workspace.set_mode("live")

    report = SystemController(state_dir=state, project_root=tmp_path).preflight(
        SystemLaunchConfig(
            source_path="missing.json",
            data_path="missing.parquet",
        )
    )

    assert report.status == "BLOCKED"
    assert "state_ready" in {issue.id for issue in report.issues}


def test_github_strategy_import_uses_static_clone_boundary_without_network(
    tmp_path: Path,
) -> None:
    clone_root = tmp_path / "cloned"
    clone_root.mkdir()
    (clone_root / "strategy.py").write_text(
        "STRATEGY = " + repr(_strategy_document()) + "\n",
        encoding="utf-8",
    )

    class FakeCloneManager(CloneManager):
        def clone(self, source):  # type: ignore[no-untyped-def]
            return clone_root, "a" * 40

    service = StrategyService(
        project_root=tmp_path,
        clone_manager=FakeCloneManager(),
    )
    result = service.import_strategies(
        repository_url="https://github.com/example/research-strategies",
        ref="main",
    )

    assert result["status"] == "DRY_RUN"
    assert result["normalized"] == 1
    assert result["orders_enabled"] is False
    assert not clone_root.exists()
