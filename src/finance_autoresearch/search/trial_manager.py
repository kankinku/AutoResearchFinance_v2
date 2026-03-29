from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(slots=True, frozen=True)
class TrialCandidate:
    candidate_id: str
    artifact: dict[str, Any]
    artifact_kind: str
    search_origin: str


class TrialManager:
    def __init__(
        self,
        *,
        optuna_adapter: object | None = None,
        frontier_candidate_limit: int = 3,
        prescreen_max_candidates: int | None = None,
    ) -> None:
        self._optuna_adapter = optuna_adapter
        self._frontier_candidate_limit = frontier_candidate_limit
        self._prescreen_max_candidates = prescreen_max_candidates

    @property
    def candidate_limit(self) -> int:
        if self._prescreen_max_candidates is None:
            return self._frontier_candidate_limit
        return min(self._frontier_candidate_limit, self._prescreen_max_candidates)

    def build_candidates(
        self,
        *,
        run_id: str,
        iteration: int,
        artifact: dict[str, Any],
    ) -> list[TrialCandidate]:
        base_artifact = deepcopy(artifact)
        candidates = [
            TrialCandidate(
                candidate_id=_candidate_id(run_id, iteration, base_artifact, suffix="base"),
                artifact=base_artifact,
                artifact_kind=str(base_artifact.get("kind", "strategy_replacement")),
                search_origin="base",
            )
        ]
        if artifact.get("kind") != "strategy_genome_v1" or self._optuna_adapter is None:
            return candidates

        suggest = getattr(self._optuna_adapter, "suggest_variants", None)
        if not callable(suggest):
            return candidates
        for index, variant in enumerate(suggest(base_artifact), start=1):
            if len(candidates) >= self.candidate_limit:
                break
            candidates.append(
                TrialCandidate(
                    candidate_id=_candidate_id(run_id, iteration, variant, suffix=f"optuna-{index}"),
                    artifact=deepcopy(variant),
                    artifact_kind=str(variant.get("kind", "strategy_genome_v1")),
                    search_origin="optuna_adapter",
                )
            )
        return candidates[: self.candidate_limit]


def _candidate_id(run_id: str, iteration: int, artifact: dict[str, Any], *, suffix: str) -> str:
    digest = sha256(repr(sorted(artifact.items())).encode("utf-8")).hexdigest()[:8]
    return f"{run_id}-{iteration}-{suffix}-{digest}"
