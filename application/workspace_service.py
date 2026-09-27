from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from application.workspace_contracts import WorkspaceStatusSnapshot
from memory.state_files import StateFileStore

_WORKSPACE_COMPONENTS = ("champion", "frontier", "knowledge", "rescue_pool", "mode")


class WorkspaceService:
    """Research-safe state initialization and read-only workspace status."""

    def __init__(self, *, state_dir: Path, project_root: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()

    def initialize(self, *, overwrite: bool = False) -> dict[str, object]:
        store = StateFileStore(self.state_dir)
        defaults: dict[str, dict[str, Any]] = {
            "champion": {
                "schema_version": 1,
                "status": "EMPTY",
                "champion": None,
            },
            "frontier": {
                "schema_version": 1,
                "families": {},
            },
            "knowledge": {
                "schema_version": 1,
                "known_good": [],
                "known_bad": [],
                "interactions": [],
                "unexplored": [],
            },
            "rescue_pool": {
                "schema_version": 1,
                "entries": [],
            },
            "mode": {
                "schema_version": 1,
                "selected_mode": "paper",
                "orders_enabled": False,
                "requested_by": "initialization",
            },
        }
        created: list[str] = []
        preserved: list[str] = []
        for name, payload in defaults.items():
            target = self.state_dir / f"{name}.json"
            if target.is_file() and not overwrite:
                preserved.append(name)
                continue
            store.write(name, payload)
            created.append(name)
        return {
            "status": "INITIALIZED",
            "state_dir": str(self.state_dir),
            "created": created,
            "preserved": preserved,
            "orders_enabled": False,
        }

    def set_mode(self, mode: str) -> dict[str, object]:
        if mode not in {"paper", "live"}:
            raise ValueError("mode must be paper or live")
        store = StateFileStore(self.state_dir)
        payload = {
            "schema_version": 1,
            "selected_mode": mode,
            "orders_enabled": False,
            "requested_by": "mcp",
        }
        store.write("mode", payload)
        return {"status": "MODE_SELECTED", **payload}

    def validate_cache(self, *, manifest_dir: str = "manifests") -> dict[str, object]:
        directory = self._project_path(manifest_dir)
        return {
            "status": "VALIDATED",
            "validated_manifests": _valid_manifest_count(directory),
            "orders_enabled": False,
        }

    def status(self) -> dict[str, object]:
        states = {
            name: self._read_json_state(name)
            for name in _WORKSPACE_COMPONENTS
        }
        initialized_components = [
            name for name, (_, present, valid) in states.items() if present and valid
        ]
        missing_components = [
            name for name, (_, present, _) in states.items() if not present
        ]
        invalid_components = [
            name for name, (_, present, valid) in states.items() if present and not valid
        ]
        present_count = len(initialized_components) + len(invalid_components)
        status: Literal["NOT_INITIALIZED", "PARTIAL", "READY"]
        if present_count == 0:
            status = "NOT_INITIALIZED"
        elif len(initialized_components) == len(_WORKSPACE_COMPONENTS):
            status = "READY"
        else:
            status = "PARTIAL"

        champion = states["champion"][0]
        frontier = states["frontier"][0]
        mode = states["mode"][0]
        families = frontier.get("families", {}) if isinstance(frontier, dict) else {}
        raw_mode = mode.get("selected_mode") if isinstance(mode, dict) else None
        mode_configured = raw_mode in {"paper", "live"}
        selected_mode: Literal["paper", "live"] = (
            raw_mode if raw_mode in {"paper", "live"} else "paper"
        )

        snapshot = WorkspaceStatusSnapshot(
            status=status,
            initialized_components=initialized_components,
            missing_components=missing_components,
            invalid_components=invalid_components,
            champion=(
                str(champion.get("status", "UNKNOWN"))
                if isinstance(champion, dict)
                else "INVALID"
                if "champion" in invalid_components
                else "MISSING"
            ),
            frontier_families=len(families) if isinstance(families, dict) else 0,
            selected_mode=selected_mode,
            mode_configured=mode_configured,
            orders_enabled=False,
            audit_records=_line_count(self.state_dir / "audit.jsonl"),
            validated_manifests=_valid_manifest_count(self.project_root / "manifests"),
        )
        return snapshot.model_dump(mode="json")

    def _read_json_state(
        self,
        name: str,
    ) -> tuple[dict[str, Any] | None, bool, bool]:
        path = self.state_dir / f"{name}.json"
        if not path.is_file():
            return None, False, False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, True, False
        if not isinstance(payload, dict):
            return None, True, False
        return payload, True, True


    def _project_path(self, value: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("project path is required")
        candidate = (self.project_root / value).resolve()
        if candidate != self.project_root and self.project_root not in candidate.parents:
            raise PermissionError("path is outside project root")
        return candidate


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _valid_manifest_count(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    valid = 0
    for manifest in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("experiment_hash"):
            valid += 1
    return valid
