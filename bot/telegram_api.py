from __future__ import annotations

import json
from urllib.request import Request, urlopen


class TelegramApiClient:
    def __init__(self, token: str, transport=None, timeout: int = 60) -> None:
        self.token = token
        self.timeout = timeout
        self._transport = transport or self._request

    def get_updates(self, offset: int | None = None, timeout: int = 20) -> list[dict[str, object]]:
        payload: dict[str, object] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        response = self._transport("getUpdates", payload)
        return list(response.get("result", []))

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, object] | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = self._transport("sendMessage", payload)
        return dict(response.get("result", {}))

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, object] | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = self._transport("editMessageText", payload)
        return dict(response.get("result", {}))

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        payload: dict[str, object] = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text
        response = self._transport("answerCallbackQuery", payload)
        return bool(response.get("ok", True))

    def _request(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "LegalMarkerBot/1.0",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not decoded.get("ok", False):
            raise RuntimeError(f"Telegram API error for {method}: {decoded}")
        return decoded
