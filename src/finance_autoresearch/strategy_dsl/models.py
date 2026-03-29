from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any


ParamValue = int | float | bool | str


@dataclass(slots=True, frozen=True)
class StrategyGenomeV1:
    family_id: str
    rationale: str
    regime_policy: str
    indicator_specs: tuple[dict[str, Any], ...]
    entry_clauses: tuple[dict[str, Any], ...]
    exit_clauses: tuple[dict[str, Any], ...]
    risk_clauses: tuple[dict[str, Any], ...]
    params: dict[str, ParamValue]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "StrategyGenomeV1":
        return cls(
            family_id=str(payload["family_id"]),
            rationale=str(payload["rationale"]),
            regime_policy=str(payload["regime_policy"]),
            indicator_specs=tuple(_normalize_records(payload["indicator_specs"])),
            entry_clauses=tuple(_normalize_records(payload["entry_clauses"])),
            exit_clauses=tuple(_normalize_records(payload["exit_clauses"])),
            risk_clauses=tuple(_normalize_records(payload["risk_clauses"])),
            params=_normalize_param_mapping(payload.get("params", {})),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "rationale": self.rationale,
            "regime_policy": self.regime_policy,
            "indicator_specs": [dict(item) for item in self.indicator_specs],
            "entry_clauses": [dict(item) for item in self.entry_clauses],
            "exit_clauses": [dict(item) for item in self.exit_clauses],
            "risk_clauses": [dict(item) for item in self.risk_clauses],
            "params": dict(self.params),
        }


@dataclass(slots=True, frozen=True)
class GenomeCompileResult:
    target_path: str
    full_file_contents: str
    compile_status: str
    indicator_count: int
    new_clause_count: int
    regime_branch_count: int
    exit_family_count: int
    direction_mode: str
    supports_true_regime_split: bool
    validated_indicator_ids: tuple[str, ...] = ()
    validated_clause_refs: tuple[str, ...] = ()

    @property
    def source_sha256(self) -> str:
        return sha256(self.full_file_contents.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, Any]:
        return {
            "target_path": self.target_path,
            "compile_status": self.compile_status,
            "indicator_count": self.indicator_count,
            "new_clause_count": self.new_clause_count,
            "regime_branch_count": self.regime_branch_count,
            "exit_family_count": self.exit_family_count,
            "direction_mode": self.direction_mode,
            "supports_true_regime_split": self.supports_true_regime_split,
            "validated_indicator_ids": list(self.validated_indicator_ids),
            "validated_clause_refs": list(self.validated_clause_refs),
            "source_sha256": self.source_sha256,
        }


@dataclass(slots=True, frozen=True)
class GenomeComparisonRecord:
    raw_sha256: str
    compiled_sha256: str
    raw_matches_compiled: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "raw_sha256": self.raw_sha256,
            "compiled_sha256": self.compiled_sha256,
            "raw_matches_compiled": self.raw_matches_compiled,
        }


def _normalize_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("genome lists must be lists of objects")
    records: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("genome lists must contain only objects")
        records.append({str(key): inner for key, inner in item.items()})
    return records


def _normalize_param_mapping(value: Any) -> dict[str, ParamValue]:
    if not isinstance(value, dict):
        raise ValueError("genome params must be an object")
    normalized: dict[str, ParamValue] = {}
    for key, inner in value.items():
        if not isinstance(inner, (int, float, bool, str)):
            raise ValueError("genome params must use scalar values")
        normalized[str(key)] = inner
    return normalized
