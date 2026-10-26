"""Entry point: python -m app.main  (runs the channels that are configured)."""
import asyncio
import logging
import signal

import aiohttp

from app.channels.tg import run_telegram
from app.channels.vk import VKChannel
from app.config import load_settings
from app.core.brain import Brain
from app.core.llm import LLM
from app.core.memory import Memory
from app.core.notify import Notifier


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    settings = load_settings()

    async with aiohttp.ClientSession() as session:
        memory = Memory(settings.db_path)
        llm = LLM(session, settings.llm_key, settings.llm_model, settings.llm_base_url)
        notifier = Notifier(session, settings.tg_token, settings.owner_chat_id, settings.sheets_url)
        brain = Brain(llm, memory, notifier, settings.history_limit, settings.max_user_chars)

        jobs: list[asyncio.Task] = []
        if settings.vk_enabled:
            jobs.append(asyncio.create_task(VKChannel(session, settings.vk_token, settings.vk_group_id, brain).run()))
        if settings.tg_enabled:
            jobs.append(asyncio.create_task(run_telegram(settings.tg_token, brain)))
        logging.info("Bot started: model %s, channels: %s", settings.llm_model,
                     ", ".join(n for n, on in (("VK", settings.vk_enabled), ("Telegram", settings.tg_enabled)) if on))

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        stopper = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*jobs, stopper], return_when=asyncio.FIRST_COMPLETED)
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        for job in done:
            if job is not stopper and job.exception():
                raise job.exception()  # a channel crashed: let systemd restart the whole process


if __name__ == "__main__":
    asyncio.run(main())
