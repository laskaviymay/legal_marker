import shutil
import unittest
from pathlib import Path

from bot.app import TelegramMarkerBot
from bot.config import BotConfig
from bot.database_provider import DatabaseProvider
from bot.runtime import BotRuntime
from bot.session_store import SessionStore
from core.database_bundle import build_database_bundle
from core.models import LegalEntity


class _FakeApi:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []
        self.edited_messages: list[dict[str, object]] = []
        self.callback_answers: list[dict[str, object]] = []

    def send_message(self, **payload):
        self.sent_messages.append(payload)
        return {"message_id": len(self.sent_messages)}

    def edit_message_text(self, **payload):
        self.edited_messages.append(payload)
        return {"message_id": payload["message_id"]}

    def answer_callback_query(self, **payload):
        self.callback_answers.append(payload)
        return True


class TelegramMarkerBotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / "test_artifacts" / "bot_app"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

        source_data = self.root / "source_data"
        source_data.mkdir()
        (source_data / "agents.json").write_text("[]", encoding="utf-8")
        (source_data / "aliases.json").write_text("[]", encoding="utf-8")
        (source_data / "forms.json").write_text("[]", encoding="utf-8")
        (source_data / "sources.json").write_text("{}", encoding="utf-8")
        self.bundle_path = self.root / "bundle.zip"
        build_database_bundle(source_data, self.bundle_path, version="v-test")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _provider(self) -> DatabaseProvider:
        config = BotConfig(
            token="token",
            db_dir=self.root / "runtime",
            db_url="https://example.invalid/db.zip",
            admin_ids=(1,),
        )
        return DatabaseProvider(config=config, download_bytes=lambda *_args, **_kwargs: self.bundle_path.read_bytes())

    def test_start_command_sends_greeting(self) -> None:
        api = _FakeApi()
        bot = TelegramMarkerBot(
            api=api,
            runtime=BotRuntime(entities=[]),
            sessions=SessionStore(),
            provider=self._provider(),
            config=BotConfig(token="token", db_dir=self.root / "runtime"),
        )

        bot.handle_message(chat_id=10, text="/start")

        self.assertEqual(len(api.sent_messages), 1)
        self.assertIn("Legal Marker", str(api.sent_messages[0]["text"]))

    def test_plain_text_direct_result_sends_marked_text(self) -> None:
        api = _FakeApi()
        runtime = BotRuntime(
            entities=[
                LegalEntity(
                    id="1",
                    name="Мария Певчих",
                    entity_type="person",
                    statuses=("foreign_agent",),
                    aliases=(),
                    source="test",
                )
            ]
        )
        bot = TelegramMarkerBot(
            api=api,
            runtime=runtime,
            sessions=SessionStore(),
            provider=self._provider(),
            config=BotConfig(token="token", db_dir=self.root / "runtime"),
        )

        bot.handle_message(chat_id=10, text="Мария Певчих дала комментарий.")

        self.assertEqual(len(api.sent_messages), 1)
        self.assertIn("*", str(api.sent_messages[0]["text"]))
        self.assertEqual(api.sent_messages[0]["parse_mode"], "HTML")

    def test_plain_text_direct_result_renders_signature_without_underscores(self) -> None:
        api = _FakeApi()
        runtime = BotRuntime(
            entities=[
                LegalEntity(
                    id="1",
                    name="Мария Певчих",
                    entity_type="person",
                    statuses=("foreign_agent",),
                    aliases=(),
                    source="test",
                )
            ]
        )
        bot = TelegramMarkerBot(
            api=api,
            runtime=runtime,
            sessions=SessionStore(),
            provider=self._provider(),
            config=BotConfig(token="token", db_dir=self.root / "runtime"),
        )

        bot.handle_message(chat_id=10, text="Мария Певчих дала комментарий.")

        rendered_text = str(api.sent_messages[0]["text"])
        self.assertIn("<i>", rendered_text)
        self.assertNotIn("_Мария", rendered_text)

    def test_plain_text_ambiguous_result_bootstraps_confirmation(self) -> None:
        api = _FakeApi()
        runtime = BotRuntime(
            entities=[
                LegalEntity("1", "Первая организация", "organization", ("foreign_agent",), ("Общее имя",), "test"),
                LegalEntity("2", "Вторая организация", "organization", ("undesirable_organization",), ("Общее имя",), "test"),
            ]
        )
        bot = TelegramMarkerBot(
            api=api,
            runtime=runtime,
            sessions=SessionStore(page_size=5),
            provider=self._provider(),
            config=BotConfig(token="token", db_dir=self.root / "runtime"),
        )

        bot.handle_message(chat_id=10, text="В тексте есть Общее имя.")

        self.assertEqual(len(api.sent_messages), 1)
        self.assertIn("reply_markup", api.sent_messages[0])
