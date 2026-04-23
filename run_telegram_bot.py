from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from bot.app import TelegramMarkerBot
from bot.config import BotConfig
from bot.database_provider import DatabaseProvider
from bot.runtime import BotRuntime
from bot.session_store import SessionStore
from bot.telegram_api import TelegramApiClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Legal Marker Telegram bot.")
    parser.add_argument("--once", action="store_true", help="Fetch one batch of updates and exit.")
    parser.add_argument("--update-db-on-start", action="store_true", help="Refresh the database before polling.")
    parser.add_argument("--db-dir", type=Path, help="Override LEGAL_MARKER_DB_DIR.")
    parser.add_argument("--db-url", help="Override LEGAL_MARKER_DB_URL.")
    parser.add_argument("--poll-timeout", type=int, help="Override LEGAL_MARKER_POLL_TIMEOUT.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = BotConfig.from_env(default_root=Path(__file__).resolve().parent)
    if args.db_dir:
        config = replace(config, db_dir=args.db_dir)
    if args.db_url:
        config = replace(config, db_url=args.db_url)
    if args.poll_timeout:
        config = replace(config, poll_timeout=max(1, args.poll_timeout))

    provider = DatabaseProvider(config)
    ready_dir = provider.update_from_remote() if args.update_db_on_start and config.db_url else provider.ensure_ready()
    runtime = BotRuntime(data_dir=ready_dir)
    api = TelegramApiClient(token=config.token)
    app = TelegramMarkerBot(
        api=api,
        runtime=runtime,
        sessions=SessionStore(),
        provider=provider,
        config=config,
    )

    if args.once:
        for update in api.get_updates(timeout=1):
            app.process_update(update)
        return 0

    app.run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
