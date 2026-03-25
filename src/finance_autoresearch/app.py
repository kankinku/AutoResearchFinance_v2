from __future__ import annotations

import json
import sys

import typer

from finance_autoresearch.integrations.cli import COMMANDS, build_command_payload
from finance_autoresearch.integrations.openclaw_control import OpenClawControlAdapter
from finance_autoresearch.runtime import build_runtime
from finance_autoresearch.settings import Settings


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
        runtime = build_runtime(resolved_settings)
        try:
            response = runtime.handle_command_payload(
                build_command_payload(
                    command=command,
                    source="cli",
                    requested_by="cli",
                    project_id=resolved_settings.project_id,
                )
            )
        finally:
            runtime.close()
        typer.echo(json.dumps(response, sort_keys=True))

    def _make_cli_command(command: str):
        def _command() -> None:
            _handle_cli_command(command)

        return _command

    for command in COMMANDS:
        app.command(name=command)(_make_cli_command(command))

    @app.command("openclaw-control")
    def openclaw_control() -> None:
        runtime = build_runtime(resolved_settings)
        try:
            adapter = OpenClawControlAdapter(
                command_handler=runtime.handle_command_payload,
                default_project_id=resolved_settings.project_id,
            )
            exit_code, stdout, stderr = adapter.run(sys.stdin.read())
        finally:
            runtime.close()
        if stdout:
            typer.echo(stdout)
        if stderr:
            typer.echo(stderr, err=True)
        raise typer.Exit(code=exit_code)

    @app.command("run-pipeline-worker", hidden=True)
    def run_pipeline_worker() -> None:
        runtime = build_runtime(resolved_settings)
        try:
            result = runtime.run_pipeline_worker()
        finally:
            runtime.close()
        typer.echo(json.dumps(result, sort_keys=True))

    @app.command("run-autoresearch-worker", hidden=True)
    def run_autoresearch_worker(run_id: str) -> None:
        runtime = build_runtime(resolved_settings)
        try:
            result = runtime.run_autoresearch_worker(run_id=run_id)
        finally:
            runtime.close()
        typer.echo(json.dumps(result, sort_keys=True))

    return app


app = create_app()


def main() -> None:
    app()
