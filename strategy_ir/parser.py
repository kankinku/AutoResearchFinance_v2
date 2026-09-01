from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from strategy_ir.schema import Provenance, StrategyIR


def parse_strategy_document(document: dict[str, Any]) -> StrategyIR:
    return StrategyIR.model_validate(document)


def parse_strategy_yaml(path: Path) -> StrategyIR:
    raw_bytes = path.read_bytes()
    raw: Any = yaml.safe_load(raw_bytes.decode("utf-8"))
    strategy = parse_strategy_document(raw)
    return strategy.model_copy(
        update={
            "provenance": Provenance(
                source_path=path.as_posix(),
                source_hash=hashlib.sha256(raw_bytes).hexdigest(),
                source_type="yaml",
            )
        }
    )
