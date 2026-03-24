from __future__ import annotations

import json

from finance_autoresearch.supervisor.command_gate import CommandValidationError, normalize_command
from finance_autoresearch.supervisor.service import SupervisorService


class OpenClawControlAdapter:
    def __init__(
        self,
        *,
        supervisor: SupervisorService,
        default_project_id: str = "finance",
    ) -> None:
        self._supervisor = supervisor
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

        response = self._supervisor.handle(resolved_payload)
        return 0, json.dumps(response, sort_keys=True), ""
