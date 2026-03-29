from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer
from finance_autoresearch.state.models import OutboxMessage
from finance_autoresearch.state.repository import StateRepository


class TelegramReportAdapter:
    def __init__(
        self,
        *,
        store: StateRepository,
        bot: Any,
        chat_id: str,
        event_type_prefix: str | None = None,
        exclude_event_type_prefix: str | None = None,
        formatter: Callable[[OutboxMessage], str] | None = None,
        localizer: OutputLocalizer | None = None,
    ) -> None:
        self._store = store
        self._bot = bot
        self._chat_id = chat_id
        self._event_type_prefix = event_type_prefix
        self._exclude_event_type_prefix = exclude_event_type_prefix
        self._formatter = formatter or self._format_message
        self._localizer = localizer or DEFAULT_LOCALIZER

    async def drain_pending(self) -> list[str]:
        delivered: list[str] = []
        sender = self._resolve_sender()
        for message in self._store.list_pending_outbox(
            event_type_prefix=self._event_type_prefix,
            exclude_event_type_prefix=self._exclude_event_type_prefix,
        ):
            await sender(chat_id=self._chat_id, text=self._formatter(message))
            self._store.mark_outbox_sent(message.id)
            delivered.append(message.id)
        return delivered

    def _resolve_sender(self) -> Callable[..., Awaitable[Any]]:
        if hasattr(self._bot, "send_message"):
            return self._bot.send_message
        if hasattr(self._bot, "bot") and hasattr(self._bot.bot, "send_message"):
            return self._bot.bot.send_message
        raise AttributeError("bot must expose an async send_message method")

    def _format_message(self, message: OutboxMessage) -> str:
        if not message.payload:
            return message.event_type
        payload = ", ".join(f"{key}={value}" for key, value in message.payload.items())
        return f"{message.event_type}: {payload}"


class TelegramProgressAdapter(TelegramReportAdapter):
    def __init__(
        self,
        *,
        store: StateRepository,
        bot: Any,
        chat_id: str,
        mode: str,
        localizer: OutputLocalizer | None = None,
    ) -> None:
        super().__init__(
            store=store,
            bot=bot,
            chat_id=chat_id,
            event_type_prefix="progress_",
            formatter=self._format_progress_message,
            localizer=localizer,
        )
        self._mode = mode

    async def drain_pending(self) -> list[str]:
        delivered: list[str] = []
        sender = self._resolve_sender()
        for message in self._store.list_pending_outbox(event_type_prefix="progress_"):
            if not self._should_emit(message):
                self._store.mark_outbox_sent(message.id)
                delivered.append(message.id)
                continue
            await sender(chat_id=self._chat_id, text=self._format_progress_message(message))
            self._store.mark_outbox_sent(message.id)
            delivered.append(message.id)
        return delivered

    def _should_emit(self, message: OutboxMessage) -> bool:
        if self._mode != "simple":
            return True
        return message.event_type in {
            "progress_started",
            "progress_decision",
            "progress_failed",
            "progress_success",
            "progress_stopped",
        }

    def _format_progress_message(self, message: OutboxMessage) -> str:
        payload = message.payload
        event_type = message.event_type.removeprefix("progress_")
        if self._mode == "simple":
            return self._format_simple(event_type, payload)
        return self._format_standard(event_type, payload)

    def _format_simple(self, event_type: str, payload: dict[str, Any]) -> str:
        if event_type == "started":
            return "\n".join(
                [
                    self._localizer.log("telegram.event.autoresearch_started"),
                    self._field("run_id", payload.get("run_id")),
                    self._field("max_iterations", payload.get("max_iterations")),
                ]
            )
        if event_type == "decision":
            return "\n".join(
                [
                    self._localizer.log(
                        "telegram.event.iteration_decision",
                        iteration=payload.get("iteration"),
                        decision=payload.get("decision"),
                    ),
                    " ".join(
                        [
                            self._field("candidate_score", payload.get("candidate_score")),
                            self._field("baseline_score", payload.get("baseline_score")),
                        ]
                    ),
                ]
            )
        if event_type in {"failed", "success", "stopped"}:
            return "\n".join(
                [
                    self._event_heading(event_type),
                    self._field("run_id", payload.get("run_id")),
                    self._field("message", payload.get("message")),
                ]
            )
        return self._format_standard(event_type, payload)

    def _format_standard(self, event_type: str, payload: dict[str, Any]) -> str:
        if event_type == "started":
            return "\n".join(
                [
                    self._localizer.log("telegram.event.autoresearch_started"),
                    self._field("run_id", payload.get("run_id")),
                    self._field("max_iterations", payload.get("max_iterations")),
                    self._field("baseline_revision", payload.get("baseline_revision")),
                ]
            )
        if event_type == "stage_changed":
            return "\n".join(
                [
                    self._localizer.log(
                        "telegram.event.stage_changed",
                        stage=self._localizer.stage_label(str(payload.get("stage", ""))),
                    ),
                    " ".join(
                        [
                            self._field("run_id", payload.get("run_id")),
                            self._field("iteration", payload.get("iteration")),
                        ]
                    ),
                ]
            )
        if event_type == "decision":
            return "\n".join(
                [
                    self._localizer.log(
                        "telegram.event.iteration_decision",
                        iteration=payload.get("iteration"),
                        decision=payload.get("decision"),
                    ),
                    " ".join(
                        [
                            self._field("candidate_score", payload.get("candidate_score")),
                            self._field("baseline_score", payload.get("baseline_score")),
                        ]
                    ),
                    self._field("hypothesis", payload.get("hypothesis")),
                ]
            )
        if event_type in {"failed", "success", "stopped", "paused"}:
            lines = [
                self._event_heading(event_type),
                self._field("run_id", payload.get("run_id")),
                self._field("iteration", payload.get("iteration")),
            ]
            if event_type != "paused":
                lines.append(self._field("message", payload.get("message")))
            return "\n".join(lines)
        return super()._format_message(message)

    def _event_heading(self, event_type: str) -> str:
        return self._localizer.log(f"telegram.event.autoresearch_{event_type}")

    def _field(self, name: str, value: Any) -> str:
        return f"{self._localizer.log(f'telegram.field.{name}')}={value}"
