from __future__ import annotations

from bot.session_store import BotSession
from core.gui_service import PaginatedValidationRows


CALLBACK_PREFIX = "tg"


def split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(line) <= limit:
            current = line
            continue
        for start in range(0, len(line), limit):
            chunks.append(line[start : start + limit])
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def encode_callback_data(action: str, session_id: str, value: str) -> str:
    return f"{CALLBACK_PREFIX}:{action}:{session_id}:{value}"


def decode_callback_data(payload: str) -> tuple[str, str, str]:
    prefix, action, session_id, value = payload.split(":", 3)
    if prefix != CALLBACK_PREFIX:
        raise ValueError("Unknown callback prefix")
    return action, session_id, value


def format_confirmation_text(page: PaginatedValidationRows) -> str:
    lines = [
        "Подтвердите маркировку",
        f"Страница {page.page}/{page.total_pages}",
        "",
    ]
    for row in page.rows:
        marker = "[x]" if row.selected else "[ ]"
        lines.append(f"{marker} {row.label}")
    return "\n".join(lines)


def build_confirmation_keyboard(session: BotSession, page: PaginatedValidationRows) -> dict[str, object]:
    candidate_index_by_id = {
        candidate.candidate_id: index
        for index, candidate in enumerate(session.candidates)
    }
    keyboard: list[list[dict[str, str]]] = []
    for row in page.rows:
        action_label = "Убрать" if row.selected else "Добавить"
        if row.is_ambiguous:
            action_label = f"{action_label} вариант"
        index = candidate_index_by_id[row.candidate_id]
        keyboard.append(
            [
                {
                    "text": action_label,
                    "callback_data": encode_callback_data("toggle", session.session_id, str(index)),
                }
            ]
        )
    navigation: list[dict[str, str]] = []
    if page.page > 1:
        navigation.append(
            {
                "text": "← Назад",
                "callback_data": encode_callback_data("page", session.session_id, str(page.page - 1)),
            }
        )
    if page.page < page.total_pages:
        navigation.append(
            {
                "text": "Дальше →",
                "callback_data": encode_callback_data("page", session.session_id, str(page.page + 1)),
            }
        )
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Применить", "callback_data": encode_callback_data("apply", session.session_id, "-")},
            {"text": "Отмена", "callback_data": encode_callback_data("cancel", session.session_id, "-")},
        ]
    )
    return {"inline_keyboard": keyboard}
