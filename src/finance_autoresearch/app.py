from __future__ import annotations

import json
import sys

import typer

from finance_autoresearch.integrations.cli import COMMANDS, dispatch_command
from finance_autoresearch.integrations.openclaw_control import OpenClawControlAdapter
from finance_autoresearch.settings import Settings
from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService


def build_supervisor(settings: Settings | None = None) -> SupervisorService:
    resolved_settings = settings or Settings()
    store = SQLiteStateStore(
        db_path=resolved_settings.state_db_path,
        project_id=resolved_settings.project_id,
    )
    return SupervisorService(
        state_store=store,
        seed_validator=lambda _project_id: (False, "seed validator is not configured"),
    )


def create_app(settings: Settings | None = None) -> typer.Typer:
    resolved_settings = settings or Settings()
    app = typer.Typer(
        add_completion=False,
        help="Finance autoresearch command surface.",
    )

    @app.command("settings")
    def show_settings() -> None:
        typer.echo(
            resolved_settings.model_dump_json(
                indent=2,
                exclude={
                    "telegram_control_token",
                    "telegram_control_chat_id",
                    "telegram_report_token",
                    "telegram_report_chat_id",
                },
            )
        )

    def _handle_cli_command(command: str) -> None:
        supervisor = build_supervisor(resolved_settings)
        try:
            response = dispatch_command(
                supervisor=supervisor,
                command=command,
                source="cli",
                requested_by="cli",
                project_id=resolved_settings.project_id,
            )
        finally:
            supervisor._state_store.close()
        typer.echo(json.dumps(response, sort_keys=True))

    def _make_cli_command(command: str):
        def _command() -> None:
            _handle_cli_command(command)

        return _command

    for command in COMMANDS:
        app.command(name=command)(_make_cli_command(command))

    @app.command("openclaw-control")
    def openclaw_control() -> None:
        supervisor = build_supervisor(resolved_settings)
        try:
            adapter = OpenClawControlAdapter(
                supervisor=supervisor,
                default_project_id=resolved_settings.project_id,
            )
            exit_code, stdout, stderr = adapter.run(sys.stdin.read())
        finally:
            supervisor._state_store.close()
        if stdout:
            typer.echo(stdout)
        if stderr:
            typer.echo(stderr, err=True)
        raise typer.Exit(code=exit_code)

    return app


app = create_app()


def main() -> None:
    app()
