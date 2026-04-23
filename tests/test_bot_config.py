import shutil
import unittest
from pathlib import Path

from bot.config import BotConfig


class BotConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / "test_artifacts" / "bot_config"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_from_env_reads_local_env_file(self) -> None:
        env_path = self.root / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "TELEGRAM_BOT_TOKEN=test-token",
                    "LEGAL_MARKER_DB_DIR=./runtime/db",
                    "LEGAL_MARKER_POLL_TIMEOUT=33",
                ]
            ),
            encoding="utf-8",
        )

        config = BotConfig.from_env(env={}, default_root=self.root)

        self.assertEqual(config.token, "test-token")
        self.assertEqual(config.db_dir, Path("./runtime/db"))
        self.assertEqual(config.poll_timeout, 33)
