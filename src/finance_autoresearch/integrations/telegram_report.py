from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from finance_autoresearch.state.models import OutboxMessage
from finance_autoresearch.state.repository import StateRepository


class TelegramReportAdapter:
    def __init__(
        self,
        *,
        store: StateRepository,
        bot: Any,
        chat_id: str,
    ) -> None:
        self._store = store
        self._bot = bot
        self._chat_id = chat_id

    async def drain_pending(self) -> list[str]:
        delivered: list[str] = []
        sender = self._resolve_sender()
        for message in self._store.list_pending_outbox():
            await sender(chat_id=self._chat_id, text=self._format_message(message))
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
        payload = ", ".join(
            f"{key}={value}" for key, value in message.payload.items()
        )
        return f"{message.event_type}: {payload}"
