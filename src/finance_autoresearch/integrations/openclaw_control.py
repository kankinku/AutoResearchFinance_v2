from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from finance_autoresearch.supervisor.command_gate import CommandValidationError, normalize_command
from finance_autoresearch.supervisor.service import SupervisorService


class OpenClawControlAdapter:
    def __init__(
        self,
        *,
        supervisor: SupervisorService | None = None,
        command_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        default_project_id: str = "finance",
    ) -> None:
        if command_handler is None:
            if supervisor is None:
                raise ValueError("either supervisor or command_handler must be provided")
            command_handler = supervisor.handle
        self._command_handler = command_handler
        self._default_project_id = default_project_id

    def run(self, stdin_text: str) -> tuple[int, str, str]:
        try:
            payload = json.loads(stdin_text)
        except json.JSONDecodeError as exc:
            return 1, "", f"malformed JSON: {exc.msg}"

        if not isinstance(payload, dict):
            return 1, "", "invalid command: expected an object payload"

        resolved_payload = dict(payload)
        resolved_payload.setdefault("project_id", self._default_project_id)

        try:
            normalize_command(resolved_payload)
        except CommandValidationError as exc:
            return 1, "", str(exc)

        response = self._command_handler(resolved_payload)
        return 0, json.dumps(response, sort_keys=True), ""
