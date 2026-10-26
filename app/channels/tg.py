"""Telegram channel built on aiogram (long polling). Answers are plain text on purpose, no Markdown."""
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from app.core.brain import Brain
from app.core.text import split_message

log = logging.getLogger("telegram")


def _contact(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "Telegram"
    return f"@{user.username}" if user.username else f"Telegram id {user.id}"


async def run_telegram(token: str, brain: Brain) -> None:
    bot = Bot(token=token)
    dispatcher = Dispatcher()

    @dispatcher.message(F.chat.type == "private", F.text)
    async def on_text(message: Message) -> None:
        if message.from_user is None:
            return
        try:
            await bot.send_chat_action(message.chat.id, "typing")
            reply = await brain.reply("tg", message.from_user.id, message.text or "", _contact(message))
            for part in split_message(reply):
                await message.answer(part)
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to handle a Telegram message: %s", type(exc).__name__)

    @dispatcher.message(F.chat.type == "private")
    async def on_other(message: Message) -> None:
        await message.answer("Я понимаю только текстовые сообщения. Напишите, пожалуйста, словами.")

    me = await bot.get_me()
    log.info("Telegram polling started as @%s", me.username)
    try:
        await dispatcher.start_polling(bot, handle_signals=False)
    finally:
        await bot.session.close()
