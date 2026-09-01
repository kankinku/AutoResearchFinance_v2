from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.manifest import ExperimentManifest


@dataclass(frozen=True)
class CacheLookup:
    status: str
    result: dict[str, Any] | None = None


class ExperimentCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS experiment_cache "
            "(experiment_hash TEXT PRIMARY KEY, result_json TEXT NOT NULL)"
        )
        self._connection.commit()

    def lookup(self, manifest: ExperimentManifest) -> CacheLookup:
        row = self._connection.execute(
            "SELECT result_json FROM experiment_cache WHERE experiment_hash = ?",
            (manifest.experiment_hash,),
        ).fetchone()
        if row is None:
            return CacheLookup("CACHE_MISS")
        return CacheLookup("CACHE_HIT", json.loads(row[0]))

    def store(self, manifest: ExperimentManifest, result: dict[str, Any]) -> None:
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._connection.execute(
            "INSERT OR REPLACE INTO experiment_cache(experiment_hash, result_json) VALUES (?, ?)",
            (manifest.experiment_hash, payload),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
