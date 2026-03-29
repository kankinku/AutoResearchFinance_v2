from __future__ import annotations

import json
from pathlib import Path
import sys

import typer

from finance_autoresearch.integrations.cli import COMMANDS, build_command_payload
from finance_autoresearch.integrations.openclaw_control import OpenClawControlAdapter
from finance_autoresearch.localization import OutputLocalizer
from finance_autoresearch.runtime import build_runtime
from finance_autoresearch.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> typer.Typer:
    resolved_settings = settings or load_settings()
    localizer = OutputLocalizer(
        output_language=resolved_settings.output_language,
        docs_output_language=resolved_settings.docs_output_language,
        log_output_language=resolved_settings.log_output_language,
    )
    app = typer.Typer(
        add_completion=False,
        help=localizer.log("app.command_surface_help"),
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

    @app.command("brain-status")
    def brain_status() -> None:
        runtime = build_runtime(resolved_settings)
        try:
            notes = runtime.store.list_brain_notes(limit=10)
            maps = runtime.store.list_brain_maps(limit=10)
        finally:
            runtime.close()
        typer.echo(
            json.dumps(
                {
                    "enabled": resolved_settings.research_brain_enabled,
                    "root": str(resolved_settings.research_brain_root),
                    "auto_export": resolved_settings.research_brain_auto_export,
                    "note_count": len(notes),
                    "map_count": len(maps),
                },
                sort_keys=True,
            )
        )

    @app.command("rebuild-brain")
    def rebuild_brain() -> None:
        runtime = build_runtime(resolved_settings)
        try:
            brain_sync = getattr(runtime.autoresearch_runner, "_brain_sync", None)
            if brain_sync is None:
                typer.echo(
                    json.dumps(
                        {
                            "ok": False,
                            "message": localizer.log("app.research_brain_disabled"),
                        },
                        sort_keys=True,
                    )
                )
                raise typer.Exit(code=1)
            notes, maps = brain_sync.rebuild_brain()
        finally:
            runtime.close()
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "notes_rebuilt": len(notes),
                    "maps_rebuilt": len(maps),
                },
                sort_keys=True,
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
    def openclaw_control(
        request_json_path: str | None = typer.Option(
            None,
            "--request-json-path",
            help=localizer.log("app.openclaw_request_json_help"),
        )
    ) -> None:
        runtime = build_runtime(resolved_settings)
        try:
            adapter = OpenClawControlAdapter(
                command_handler=runtime.handle_command_payload,
                default_project_id=resolved_settings.project_id,
            )
            request_payload = (
                Path(request_json_path).read_text(encoding="utf-8-sig")
                if request_json_path
                else sys.stdin.read()
            )
            exit_code, stdout, stderr = adapter.run(request_payload)
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
