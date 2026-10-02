from __future__ import annotations

from experiments.planner import plan_experiment


class PlanningService:
    """Pure experiment planning for MCP/CLI consumers."""

    def plan_generation(
        self,
        *,
        parent_ids: tuple[str, ...],
        method: str,
        count: int,
        seed: int,
    ) -> dict[str, object]:
        plan = plan_experiment(
            parent_ids=parent_ids,
            structure_operations=(),
            parameter_domains=(),
            method=method,
            count=count,
            seed=seed,
        )
        return {
            "parent_ids": list(plan.parent_ids),
            "method": plan.method,
            "count": plan.count,
            "seed": plan.seed,
            "search_stage": plan.search_stage,
        }
