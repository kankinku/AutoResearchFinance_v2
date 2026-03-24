from __future__ import annotations

from finance_autoresearch.integrations.cli import dispatch_command
from finance_autoresearch.supervisor.service import SupervisorService


_COMMAND_ALIASES = {
    "/status": "status",
    "/start_pipeline": "start_pipeline",
    "/start_autoresearch": "start_autoresearch",
    "/pause_autoresearch": "pause_autoresearch",
    "/resume_autoresearch": "resume_autoresearch",
    "/stop_autoresearch": "stop_autoresearch",
    "/reset_project": "reset_project",
    "/start pipeline": "start_pipeline",
    "/start autoresearch": "start_autoresearch",
}


class TelegramControlAdapter:
    def __init__(
        self,
        *,
        supervisor: SupervisorService,
        default_project_id: str = "finance",
    ) -> None:
        self._supervisor = supervisor
        self._default_project_id = default_project_id

    def handle_text(self, command_text: str, *, user_id: str) -> dict[str, object]:
        normalized_text = " ".join(command_text.strip().split())
        command = _COMMAND_ALIASES.get(normalized_text)
        if command is None:
            raise ValueError(f"unsupported Telegram control command: {command_text}")

        return dispatch_command(
            supervisor=self._supervisor,
            command=command,
            source="telegram_control",
            requested_by=user_id,
            project_id=self._default_project_id,
        )
