from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash


@dataclass(frozen=True)
class StateSnapshot:
    payload: dict[str, Any]
    checksum: str


class StateFileStore:
    _SAFE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, payload: dict[str, Any]) -> str:
        self._validate_name(name)
        checksum = content_hash(payload)
        target = self.root / f"{name}.json"
        temporary = self.root / f".{name}.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return checksum

    def read(self, name: str) -> StateSnapshot:
        self._validate_name(name)
        payload = json.loads((self.root / f"{name}.json").read_text(encoding="utf-8"))
        checksum = content_hash(payload)
        return StateSnapshot(payload, checksum)

    def _validate_name(self, name: str) -> None:
        if not self._SAFE_NAME.fullmatch(name):
            raise ValueError(f"invalid state file name: {name}")
