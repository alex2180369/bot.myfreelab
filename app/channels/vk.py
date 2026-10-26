"""VKontakte community messages through the Long Poll API (no web server, no public address needed)."""
import asyncio
import logging
import random

import aiohttp

from app.core.brain import Brain
from app.core.text import split_message

log = logging.getLogger("vk")

API = "https://api.vk.com/method/"
VERSION = "5.199"


class VKError(RuntimeError):
    pass


class VKChannel:
    def __init__(self, session: aiohttp.ClientSession, token: str, group_id: int, brain: Brain) -> None:
        self._session = session
        self._token = token
        self._group_id = group_id
        self._brain = brain
        self._tasks: set[asyncio.Task] = set()

    async def _api(self, method: str, **params) -> dict:
        params.update(access_token=self._token, v=VERSION)
        async with self._session.post(API + method, data=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            data = await response.json(content_type=None)
        if "error" in data:
            error = data["error"]
            raise VKError(f"{method}: [{error.get('error_code')}] {error.get('error_msg')}")
        return data["response"]

    async def run(self) -> None:
        backoff = 3
        while True:
            try:
                server = await self._api("groups.getLongPollServer", group_id=self._group_id)
                url, key, ts = server["server"], server["key"], server["ts"]
                log.info("VK Long Poll connected (community %s)", self._group_id)
                backoff = 3
                while True:
                    async with self._session.get(
                        url,
                        params={"act": "a_check", "key": key, "ts": ts, "wait": 25},
                        timeout=aiohttp.ClientTimeout(total=40),
                    ) as response:
                        data = await response.json(content_type=None)
                    failed = data.get("failed")
                    if failed == 1:
                        ts = data["ts"]
                        continue
                    if failed in (2, 3):
                        break  # key expired or history lost: ask VK for a fresh server
                    ts = data["ts"]
                    for update in data.get("updates", []):
                        if update.get("type") == "message_new":
                            task = asyncio.create_task(self._on_message(update["object"]["message"]))
                            self._tasks.add(task)
                            task.add_done_callback(self._tasks.discard)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the bot alive, reconnect with growing pauses
                log.warning("VK connection problem: %s. Reconnect in %s s", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _on_message(self, message: dict) -> None:
        try:
            from_id = int(message.get("from_id", 0))
            peer_id = int(message.get("peer_id", 0))
            if from_id <= 0 or peer_id != from_id:
                return  # only private messages from people, not group chats or other communities
            text = (message.get("text") or "").strip()

            await self._set_typing(peer_id)
            reply = await self._brain.reply("vk", from_id, text, f"https://vk.com/id{from_id}")
            for part in split_message(reply):
                await self._api("messages.send", peer_id=peer_id, message=part, random_id=random.randint(1, 2**31 - 1))
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to handle a VK message: %s", type(exc).__name__)

    async def _set_typing(self, peer_id: int) -> None:
        try:
            await self._api("messages.setActivity", peer_id=peer_id, type="typing")
        except Exception:  # noqa: BLE001 - the typing indicator is optional
            pass
