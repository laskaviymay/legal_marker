import unittest

from run_telegram_bot import build_parser, process_updates_once


class RunTelegramBotTest(unittest.TestCase):
    def test_build_parser_accepts_once_flag(self) -> None:
        args = build_parser().parse_args(["--once"])

        self.assertTrue(args.once)

    def test_process_updates_once_confirms_offset_after_processing(self) -> None:
        class FakeApi:
            def __init__(self) -> None:
                self.calls: list[tuple[int | None, int]] = []

            def get_updates(self, offset: int | None = None, timeout: int = 0):
                self.calls.append((offset, timeout))
                if len(self.calls) == 1:
                    return [{"update_id": 10}, {"update_id": 11}]
                return []

        class FakeApp:
            def __init__(self) -> None:
                self.processed: list[int] = []

            def process_update(self, update) -> None:
                self.processed.append(int(update["update_id"]))

        api = FakeApi()
        app = FakeApp()

        process_updates_once(api, app, timeout=1)

        self.assertEqual(app.processed, [10, 11])
        self.assertEqual(api.calls, [(None, 1), (12, 0)])
