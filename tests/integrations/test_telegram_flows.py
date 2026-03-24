from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    yield repository
    repository.close()


def test_control_command_creates_command_history_and_matches_cli_transition(
    store: SQLiteStateStore,
) -> None:
    from finance_autoresearch.integrations.cli import dispatch_command
    from finance_autoresearch.integrations.telegram_control import (
        TelegramControlAdapter,
    )

    supervisor = SupervisorService(
        state_store=store,
        seed_validator=lambda _project_id: (True, "seed baseline validated"),
        run_id_factory=lambda: "run-001",
    )
    telegram = TelegramControlAdapter(
        supervisor=supervisor,
        default_project_id="finance",
    )

    telegram_response = telegram.handle_text("/start_pipeline", user_id="tg-user")

    reset_store = SQLiteStateStore(db_path=store._db_path, project_id="parallel")
    try:
        parallel_supervisor = SupervisorService(
            state_store=reset_store,
            seed_validator=lambda _project_id: (True, "seed baseline validated"),
            run_id_factory=lambda: "run-001",
        )
        cli_response = dispatch_command(
            supervisor=parallel_supervisor,
            command="start_pipeline",
            source="cli",
            requested_by="cli-user",
            project_id="parallel",
        )
    finally:
        reset_store.close()

    commands = store.list_commands(limit=1)

    assert telegram_response["accepted"] is True
    assert telegram_response["project_state"] == cli_response["project_state"]
    assert telegram_response["pipeline_state"] == cli_response["pipeline_state"]
    assert telegram_response["autoresearch_state"] == cli_response["autoresearch_state"]
    assert commands[0].source == "telegram_control"
    assert commands[0].requested_by == "tg-user"


def test_report_sender_only_uses_outbox_messages(store: SQLiteStateStore) -> None:
    from finance_autoresearch.integrations.telegram_report import TelegramReportAdapter

    class FakeBot:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        async def send_message(self, *, chat_id: str, text: str) -> None:
            self.messages.append((chat_id, text))

    store.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    pending = store.append_outbox_event(
        event_type="candidate_kept",
        payload={"run_id": "run-001", "iteration": 3},
    )
    fake_bot = FakeBot()
    adapter = TelegramReportAdapter(
        store=store,
        bot=fake_bot,
        chat_id="report-room",
    )

    delivered = asyncio.run(adapter.drain_pending())
    pending_after = store.list_pending_outbox()

    assert delivered == [pending.id]
    assert fake_bot.messages == [
        ("report-room", "candidate_kept: run_id=run-001, iteration=3")
    ]
    assert pending_after == []
