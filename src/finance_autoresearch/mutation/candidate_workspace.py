from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .prompt_builder import OpenClawRequest


@dataclass(slots=True)
class CandidateWorkspace:
    root: Path
    request_path: Path
    response_path: Path
    _temporary_dir: TemporaryDirectory[str] | None = field(default=None, repr=False)

    @classmethod
    def create(
        cls,
        *,
        base_dir: Path | str | None,
        task_kind: str,
        run_id: str,
        iteration: int,
        stage: str,
    ) -> CandidateWorkspace:
        temporary_dir: TemporaryDirectory[str] | None = None
        if base_dir is None:
            temporary_dir = TemporaryDirectory(prefix="finance-openclaw-")
            root = Path(temporary_dir.name)
        else:
            safe_stage = stage.replace(":", "_").replace("/", "_").replace("\\", "_")
            root = Path(base_dir) / f"{task_kind}-{run_id}-{iteration}-{safe_stage}"
            root.mkdir(parents=True, exist_ok=True)

        return cls(
            root=root,
            request_path=root / "request.json",
            response_path=root / "response.json",
            _temporary_dir=temporary_dir,
        )

    def write_request(self, request: OpenClawRequest) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        self.request_path.write_text(
            json.dumps(request.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return self.request_path

    def reset_transport_files(self) -> None:
        for path in (self.request_path, self.response_path):
            try:
                path.unlink()
            except FileNotFoundError:
                continue

    def read_response(self) -> dict[str, Any]:
        if not self.response_path.exists():
            raise FileNotFoundError("wrapper response file was not created")
        try:
            payload = json.loads(self.response_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("wrapper response file must contain valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("wrapper response file must contain a JSON object")
        return payload

    def cleanup(self) -> None:
        if self._temporary_dir is not None:
            self._temporary_dir.cleanup()
            self._temporary_dir = None
