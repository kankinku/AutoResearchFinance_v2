from __future__ import annotations

from dataclasses import dataclass

from core.integrity.hashes import experiment_hash
from mutation.parameter import ParameterValue


@dataclass(frozen=True)
class ExperimentManifest:
    strategy_ir: dict[str, object]
    parameters: dict[str, ParameterValue]
    symbols: tuple[str, ...]
    start_date: str
    end_date: str
    dataset_version: str
    evaluator_version: str
    cost_model_version: str
    compiler_version: str
    image_digest: str
    seed: int

    @property
    def experiment_hash(self) -> str:
        return experiment_hash(
            strategy_ir=self.strategy_ir,
            parameters=self.parameters,
            symbols=self.symbols,
            start_date=self.start_date,
            end_date=self.end_date,
            dataset_version=self.dataset_version,
            evaluator_version=self.evaluator_version,
            cost_model_version=self.cost_model_version,
            compiler_version=self.compiler_version,
            image_digest=self.image_digest,
            seed=self.seed,
        )
