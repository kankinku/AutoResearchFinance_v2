from __future__ import annotations

from copy import deepcopy
from typing import Any


class OptunaAdapter:
    """Bounded parameter variant generator.

    The name stays for compatibility with the existing search stack, but this
    class does not run real Optuna optimization in this cycle.
    """

    def __init__(self, *, max_variants: int = 8) -> None:
        self._max_variants = max_variants

    def suggest_variants(self, artifact: dict[str, Any]) -> list[dict[str, Any]]:
        if artifact.get("kind") != "strategy_genome_v1":
            return []
        variants: list[dict[str, Any]] = []
        seen: set[str] = set()
        numeric_paths = _collect_numeric_paths(artifact)
        bool_paths = _collect_bool_paths(artifact)
        adjustments = (0.8, 1.2, 0.6, 1.4)

        for path in numeric_paths:
            for factor in adjustments:
                if len(variants) >= self._max_variants:
                    return variants
                candidate = deepcopy(artifact)
                original = _get_path_value(candidate, path)
                updated = _scale_numeric(original, factor)
                if updated == original:
                    continue
                _set_path_value(candidate, path, updated)
                signature = repr(candidate)
                if signature in seen:
                    continue
                seen.add(signature)
                variants.append(candidate)

        for path in bool_paths:
            if len(variants) >= self._max_variants:
                break
            candidate = deepcopy(artifact)
            original = bool(_get_path_value(candidate, path))
            updated = not original
            _set_path_value(candidate, path, updated)
            signature = repr(candidate)
            if signature in seen:
                continue
            seen.add(signature)
            variants.append(candidate)
        return variants


def _collect_numeric_paths(value: Any, *, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    paths: list[tuple[Any, ...]] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            paths.extend(_collect_numeric_paths(inner, prefix=(*prefix, key)))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            paths.extend(_collect_numeric_paths(inner, prefix=(*prefix, index)))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        paths.append(prefix)
    return paths


def _collect_bool_paths(value: Any, *, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    paths: list[tuple[Any, ...]] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            paths.extend(_collect_bool_paths(inner, prefix=(*prefix, key)))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            paths.extend(_collect_bool_paths(inner, prefix=(*prefix, index)))
    elif isinstance(value, bool):
        paths.append(prefix)
    return paths


def _get_path_value(payload: Any, path: tuple[Any, ...]) -> Any:
    current = payload
    for step in path:
        current = current[step]
    return current


def _set_path_value(payload: Any, path: tuple[Any, ...], value: Any) -> None:
    current = payload
    for step in path[:-1]:
        current = current[step]
    current[path[-1]] = value


def _scale_numeric(value: int | float, factor: float) -> int | float:
    if isinstance(value, int):
        return max(1, int(round(value * factor)))
    return round(float(value) * factor, 6)
