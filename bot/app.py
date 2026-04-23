from __future__ import annotations

from dataclasses import replace
from typing import Any

from bot.config import BotConfig
from bot.database_provider import DatabaseProvider
from bot.formatter import (
    build_confirmation_keyboard,
    decode_callback_data,
    format_confirmation_text,
    split_message,
)
from bot.runtime import BotRuntime
from bot.session_store import BotSession, SessionStore
from core.gui_service import PaginatedValidationRows, ValidationResult


class TelegramMarkerBot:
    def __init__(
        self,
        api,
        runtime: BotRuntime,
        sessions: SessionStore,
        provider: DatabaseProvider,
        config: BotConfig,
    ) -> None:
        self.api = api
        self.runtime = runtime
        self.sessions = sessions
        self.provider = provider
        self.config = config

    def handle_message(self, chat_id: int, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            return
        if stripped.startswith("/"):
            self._handle_command(chat_id, stripped)
            return

        analyzed = self.runtime.analyze(stripped)
        if analyzed.analysis is None:
            self._send_text(chat_id, analyzed.marked_text or stripped)
            return

        session = self.sessions.create(
            chat_id=chat_id,
            analysis_text=analyzed.analysis.text,
            candidates=analyzed.analysis.candidates,
        )
        self._send_confirmation(chat_id, session)

    def handle_callback(self, callback_query: dict[str, Any]) -> None:
        callback_id = str(callback_query.get("id", ""))
        data = str(callback_query.get("data", ""))
        message = dict(callback_query.get("message", {}))
        chat = dict(message.get("chat", {}))
        chat_id = int(chat.get("id", 0))
        message_id = int(message.get("message_id", 0))

        try:
            action, session_id, value = decode_callback_data(data)
            session = self.sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)

            if action == "toggle":
                session = self.sessions.toggle_index(session_id, int(value))
                self._refresh_confirmation(chat_id, message_id, session)
                self.api.answer_callback_query(callback_query_id=callback_id)
                return

            if action == "page":
                self.sessions.page(session_id, int(value))
                session = self.sessions.get(session_id) or session
                self._refresh_confirmation(chat_id, message_id, session)
                self.api.answer_callback_query(callback_query_id=callback_id)
                return

            if action == "cancel":
                self.sessions.delete(session_id)
                self.api.edit_message_text(chat_id=chat_id, message_id=message_id, text="Маркировка отменена.")
                self.api.answer_callback_query(callback_query_id=callback_id)
                return

            if action == "apply":
                result_text = self.runtime.apply(
                    ValidationResult(
                        text=session.analysis_text,
                        candidates=session.candidates,
                        match_count=0,
                        ambiguous_count=0,
                    ),
                    set(session.selected_candidate_ids),
                )
                self.sessions.delete(session_id)
                self.api.edit_message_text(chat_id=chat_id, message_id=message_id, text="Маркировка применена.")
                self._send_text(chat_id, result_text)
                self.api.answer_callback_query(callback_query_id=callback_id)
                return

            raise ValueError(action)
        except Exception:
            self.api.answer_callback_query(
                callback_query_id=callback_id,
                text="Сессия подтверждения недоступна. Отправьте текст ещё раз.",
                show_alert=True,
            )

    def process_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if isinstance(message, dict):
            text = message.get("text")
            chat = message.get("chat", {})
            if isinstance(text, str) and isinstance(chat, dict) and "id" in chat:
                self.handle_message(int(chat["id"]), text)
            return
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            self.handle_callback(callback_query)

    def run_polling(self) -> None:
        offset: int | None = None
        while True:
            updates = self.api.get_updates(offset=offset, timeout=self.config.poll_timeout)
            for update in updates:
                self.process_update(update)
                update_id = int(update.get("update_id", 0))
                offset = update_id + 1

    def _handle_command(self, chat_id: int, command_text: str) -> None:
        command = command_text.split()[0].lower()
        if command in {"/start", "/help"}:
            self._send_text(
                chat_id,
                "Legal Marker Bot\n\nОтправьте текст, и я проверю его по базе и верну готовую маркировку.",
            )
            return
        if command in {"/version", "/db_version"}:
            self._send_text(chat_id, f"Версия базы: {self.provider.current_version()}")
            return
        if command == "/update_db":
            if self.config.admin_ids and chat_id not in self.config.admin_ids:
                self._send_text(chat_id, "Эта команда доступна только администратору.")
                return
            ready_dir = self.provider.update_from_remote()
            self.runtime.reload(ready_dir)
            self._send_text(chat_id, f"База обновлена: {self.provider.current_version()}")
            return
        self._send_text(chat_id, "Неизвестная команда. Используйте /help.")

    def _send_text(self, chat_id: int, text: str) -> None:
        for chunk in split_message(text):
            self.api.send_message(chat_id=chat_id, text=chunk)

    def _send_confirmation(self, chat_id: int, session: BotSession) -> None:
        page = self.sessions.page(session.session_id, session.page)
        current_session = self.sessions.get(session.session_id) or session
        self.api.send_message(
            chat_id=chat_id,
            text=format_confirmation_text(page),
            reply_markup=build_confirmation_keyboard(current_session, page),
        )

    def _refresh_confirmation(self, chat_id: int, message_id: int, session: BotSession) -> None:
        page = self.sessions.page(session.session_id, session.page)
        current_session = self.sessions.get(session.session_id) or session
        self.api.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=format_confirmation_text(page),
            reply_markup=build_confirmation_keyboard(current_session, page),
        )
