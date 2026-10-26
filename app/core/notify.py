"""Booking notifications: a message to the owner in Telegram and a row in the Google Sheet."""
import json
import logging
from dataclasses import dataclass

import aiohttp

log = logging.getLogger("notify")

CHANNEL_NAMES = {"vk": "ВКонтакте", "tg": "Telegram"}


@dataclass
class Booking:
    booking_id: int
    channel: str
    name: str
    service: str
    slot_human: str
    contact: str


class Notifier:
    def __init__(self, session: aiohttp.ClientSession, tg_token: str, owner_chat_id: str, sheets_url: str) -> None:
        self._session = session
        self._tg_token = tg_token
        self._owner_chat_id = owner_chat_id
        self._sheets_url = sheets_url

    async def booking(self, b: Booking) -> None:
        """Never raises: a failed notification must not break the booking itself."""
        await self._telegram(b)
        await self._sheet(b)

    async def _telegram(self, b: Booking) -> None:
        if not (self._tg_token and self._owner_chat_id):
            log.info("Owner notification skipped: Telegram token or chat id is not set")
            return
        text = (
            f"Новая запись №{b.booking_id}\n"
            f"Клиент: {b.name}\n"
            f"Услуга: {b.service}\n"
            f"Когда: {b.slot_human} (МСК)\n"
            f"Канал: {CHANNEL_NAMES.get(b.channel, b.channel)}\n"
            f"Контакт: {b.contact}"
        )
        try:
            async with self._session.post(
                f"https://api.telegram.org/bot{self._tg_token}/sendMessage",
                json={"chat_id": self._owner_chat_id, "text": text, "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status != 200:
                    log.warning("Telegram notification failed: HTTP %s", response.status)
        except Exception as exc:  # noqa: BLE001 - notification errors are logged, not raised
            log.warning("Telegram notification failed: %s", type(exc).__name__)

    async def _sheet(self, b: Booking) -> None:
        if not self._sheets_url:
            return
        payload = {
            "site": "bot.myfreelab.ru",
            "name": b.name,
            "contact": b.contact,
            "comment": f"{b.service}; {b.slot_human} МСК",
            "channel": CHANNEL_NAMES.get(b.channel, b.channel),
            "booking_id": b.booking_id,
            "page": "chat-bot",
        }
        try:
            # text/plain avoids the CORS preflight that Apps Script does not answer.
            async with self._session.post(
                self._sheets_url,
                data=json.dumps(payload),
                headers={"Content-Type": "text/plain;charset=utf-8"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status >= 400:
                    log.warning("Sheet row failed: HTTP %s", response.status)
        except Exception as exc:  # noqa: BLE001
            log.warning("Sheet row failed: %s", type(exc).__name__)
