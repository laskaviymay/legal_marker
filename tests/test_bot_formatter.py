import unittest

from bot.formatter import (
    build_confirmation_keyboard,
    decode_callback_data,
    encode_callback_data,
    format_confirmation_text,
    format_result_message,
    split_message,
)
from bot.session_store import BotSession
from core.gui_service import PaginatedValidationRows, ValidationCandidate, ValidationListRow
from core.models import LegalEntity


def _candidate(candidate_id: str, group_id: str, text: str, selected: bool = False, ambiguous: bool = False) -> ValidationCandidate:
    return ValidationCandidate(
        candidate_id=candidate_id,
        group_id=group_id,
        text=text,
        start=0,
        end=len(text),
        entity=LegalEntity(
            id=candidate_id,
            name=text,
            entity_type="person",
            statuses=("foreign_agent",),
            aliases=(),
            source="test",
        ),
        confidence=0.91,
        match_type="alias",
        reason="",
        selected_by_default=selected,
        is_ambiguous=ambiguous,
    )


class BotFormatterTest(unittest.TestCase):
    def test_split_message_keeps_chunks_below_limit(self) -> None:
        chunks = split_message(("abcde\n" * 20).strip(), limit=30)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 30 for chunk in chunks))

    def test_encode_and_decode_callback_data(self) -> None:
        payload = encode_callback_data("toggle", "deadbeef", "12")

        self.assertEqual(decode_callback_data(payload), ("toggle", "deadbeef", "12"))

    def test_confirmation_keyboard_contains_toggle_and_apply_controls(self) -> None:
        session = BotSession(
            session_id="deadbeef",
            chat_id=1,
            analysis_text="text",
            candidates=(
                _candidate("1", "g1", "One", selected=True),
                _candidate("2", "g2", "Two", ambiguous=True),
            ),
            selected_candidate_ids={"1"},
            page=1,
            expires_at=9999999999,
        )
        page = PaginatedValidationRows(
            rows=(
                ValidationListRow(candidate_id="1", label="One", selected=True, is_ambiguous=False),
                ValidationListRow(candidate_id="2", label="Two", selected=False, is_ambiguous=True),
            ),
            page=1,
            page_size=5,
            total_pages=2,
            total_rows=2,
        )

        keyboard = build_confirmation_keyboard(session, page)

        self.assertIn("inline_keyboard", keyboard)
        flat_buttons = [button for row in keyboard["inline_keyboard"] for button in row]
        self.assertTrue(any(button["callback_data"].startswith("tg:toggle:deadbeef:") for button in flat_buttons))
        self.assertTrue(any(button["callback_data"] == "tg:apply:deadbeef:-" for button in flat_buttons))

    def test_format_confirmation_text_includes_page_summary(self) -> None:
        page = PaginatedValidationRows(
            rows=(
                ValidationListRow(candidate_id="1", label="One", selected=True, is_ambiguous=False),
            ),
            page=1,
            page_size=5,
            total_pages=1,
            total_rows=1,
        )

        text = format_confirmation_text(page)

        self.assertIn("1/1", text)
        self.assertIn("One", text)

    def test_format_result_message_converts_italic_signature_to_html(self) -> None:
        text = "Текст*\n\n_Иван Иванов — признан иноагентом_"

        rendered = format_result_message(text)

        self.assertIn("<i>Иван Иванов — признан иноагентом</i>", rendered)
        self.assertNotIn("_Иван Иванов", rendered)
