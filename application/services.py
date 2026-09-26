from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from application.catalog_service import FeatureCatalogService
from application.evaluation_service import EvaluationService
from application.research_service import ResearchService
from application.system_service import SystemService
from dashboard.service import DashboardService


@dataclass(frozen=True)
class ApplicationServices:
    catalog: FeatureCatalogService
    research: ResearchService
    evaluation: EvaluationService
    system: SystemService
    dashboard: DashboardService


def create_application_services(
    *,
    state_dir: Path,
    project_root: Path,
) -> ApplicationServices:
    resolved_state = state_dir.resolve()
    resolved_root = project_root.resolve()
    catalog = FeatureCatalogService()
    dashboard = DashboardService(resolved_state)
    return ApplicationServices(
        catalog=catalog,
        research=ResearchService(
            resolved_state,
            dashboard=dashboard,
            catalog=catalog,
        ),
        evaluation=EvaluationService(
            project_root=resolved_root,
            state_dir=resolved_state,
        ),
        system=SystemService(
            state_dir=resolved_state,
            project_root=resolved_root,
        ),
        dashboard=dashboard,
    )
