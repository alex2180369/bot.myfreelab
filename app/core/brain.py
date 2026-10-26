"""The dialogue engine shared by all channels: memory, model call, booking tool, safety limits."""
import asyncio
import json
import logging
import time
from collections import defaultdict, deque

from app.config import ROOT
from app.core.booking import check_slot, clean_name, now, parse_slot
from app.core.knowledge import build_system_prompt, load_knowledge, load_prompt_template
from app.core.llm import LLM, LLMError
from app.core.memory import Memory
from app.core.notify import Booking, Notifier
from app.core.text import strip_markdown

log = logging.getLogger("brain")

FALLBACK = "Извините, сейчас не получается ответить. Попробуйте написать чуть позже."
TOO_FAST = "Вы пишете слишком быстро. Подождите минуту, и я отвечу."
NO_TEXT = "Я понимаю только текстовые сообщения. Напишите, пожалуйста, словами."
START_WORDS = {"/start", "start", "начать"}
RATE_LIMIT = 8  # messages
RATE_WINDOW = 60  # seconds

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "Оформить запись на консультацию. Вызывай только после явного согласия клиента с итогом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Имя клиента"},
                    "service": {"type": "string", "description": "Название услуги из базы знаний"},
                    "slot": {
                        "type": "string",
                        "description": "Дата и время начала по Москве, формат ГГГГ-ММ-ДД ЧЧ:ММ",
                    },
                },
                "required": ["name", "service", "slot"],
            },
        },
    }
]


class Brain:
    def __init__(self, llm: LLM, memory: Memory, notifier: Notifier, history_limit: int = 12, max_chars: int = 1000):
        self.llm = llm
        self.memory = memory
        self.notifier = notifier
        self.history_limit = history_limit
        self.max_chars = max_chars
        self._template = load_prompt_template()
        self._knowledge = load_knowledge()
        self._greeting = (ROOT / "prompts" / "greeting.txt").read_text(encoding="utf-8").strip()
        self._locks: dict[tuple, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._recent: dict[tuple, deque] = defaultdict(deque)

    # ---------------------------------------------------------------- public
    async def reply(self, channel: str, user_id: str | int, text: str, contact: str) -> str:
        key = (channel, str(user_id))
        async with self._locks[key]:  # one message of one user at a time
            text = (text or "").strip()
            if not text:
                return NO_TEXT
            if self._too_fast(key):
                return TOO_FAST
            text = text[: self.max_chars]

            if text.lower() in START_WORDS:
                self.memory.reset(channel, user_id)
                self.memory.add(channel, user_id, "assistant", self._greeting)
                return self._greeting

            history = self.memory.history(channel, user_id, self.history_limit)
            messages = [{"role": "system", "content": build_system_prompt(self._template, self._knowledge)}]
            messages += history + [{"role": "user", "content": text}]

            try:
                answer = await self._run(messages, channel, user_id, contact)
            except LLMError as exc:
                log.error("Model unavailable: %s", exc)
                return FALLBACK

            answer = strip_markdown(answer) or FALLBACK
            self.memory.add(channel, user_id, "user", text)
            self.memory.add(channel, user_id, "assistant", answer)
            return answer

    # --------------------------------------------------------------- private
    def _too_fast(self, key: tuple) -> bool:
        moment = time.monotonic()
        stamps = self._recent[key]
        while stamps and moment - stamps[0] > RATE_WINDOW:
            stamps.popleft()
        if len(stamps) >= RATE_LIMIT:
            return True
        stamps.append(moment)
        return False

    async def _run(self, messages: list[dict], channel: str, user_id: str | int, contact: str) -> str:
        for _ in range(3):  # model -> tool -> model, never an endless loop
            message = await self.llm.chat(messages, TOOLS)
            calls = message.get("tool_calls") or []
            if not calls:
                return message.get("content") or ""
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call in calls:
                result = await self._call_tool(call, channel, user_id, contact)
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
                )
        return ""

    async def _call_tool(self, call: dict, channel: str, user_id: str | int, contact: str) -> dict:
        function = call.get("function", {})
        if function.get("name") != "create_booking":
            return {"ok": False, "error": "Неизвестная функция."}
        try:
            args = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "Не удалось разобрать данные записи. Уточните их у клиента."}
        return await self.create_booking(channel, user_id, contact, args)

    async def create_booking(self, channel: str, user_id: str | int, contact: str, args: dict) -> dict:
        """Validates the booking, saves it and notifies the owner. Errors are returned to the model in words."""
        name = clean_name(str(args.get("name", "")))
        service = str(args.get("service", "")).strip()[:120]
        if not name:
            return {"ok": False, "error": "Нужно настоящее имя клиента. Спросите его."}
        if not service:
            return {"ok": False, "error": "Не указана услуга. Уточните её у клиента."}

        slot_dt = parse_slot(str(args.get("slot", "")))
        if slot_dt is None:
            return {"ok": False, "error": "Неверный формат времени. Нужен формат ГГГГ-ММ-ДД ЧЧ:ММ."}
        problem = check_slot(slot_dt, now())
        if problem:
            return {"ok": False, "error": problem}

        slot = slot_dt.strftime("%Y-%m-%d %H:%M")
        human = slot_dt.strftime("%d.%m.%Y %H:%M")
        if self.memory.has_booking(channel, user_id, slot):
            return {"ok": True, "note": "Эта запись уже оформлена ранее.", "when": human}
        if self.memory.slot_taken(slot):
            return {"ok": False, "error": "Это время уже занято. Предложите клиенту другое."}

        booking_id = self.memory.save_booking(channel, user_id, name, service, slot, contact)
        await self.notifier.booking(Booking(booking_id, channel, name, service, human, contact))
        log.info("Booking #%s saved (%s)", booking_id, channel)
        return {"ok": True, "booking_id": booking_id, "when": human, "name": name, "service": service}
