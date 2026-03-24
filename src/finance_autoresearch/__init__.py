from __future__ import annotations

import typer

from .settings import Settings

__all__ = ["Settings", "__version__", "app", "main"]

__version__ = "0.1.0"

app = typer.Typer(
    add_completion=False,
    help="Bootstrap CLI for the finance autoresearch package.",
)


@app.command("settings")
def show_settings() -> None:
    typer.echo(
        Settings().model_dump_json(
            indent=2,
            exclude={
                "telegram_control_token",
                "telegram_control_chat_id",
                "telegram_report_token",
                "telegram_report_chat_id",
            },
        )
    )


def main() -> None:
    app()
