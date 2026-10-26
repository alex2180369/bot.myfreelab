"""Offline checks of the rules that do not need the language model: python -m tests.test_unit"""
import asyncio
from datetime import datetime, timedelta

from app.core.booking import TZ, check_slot, clean_name, now_human, parse_slot
from app.core.memory import Memory
from app.core.text import split_message, strip_markdown


def at(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


# 2026-10-26 is a Monday
NOW = at(2026, 10, 26, 12, 0)


def test_slots():
    assert check_slot(at(2026, 10, 27, 15, 0), NOW) is None                    # Tuesday 15:00
    assert check_slot(at(2026, 10, 27, 18, 30), NOW) is None                   # last slot
    assert check_slot(at(2026, 10, 27, 10, 0), NOW) is None                    # first slot
    assert "выходные" in check_slot(at(2026, 10, 31, 15, 0), NOW)              # Saturday
    assert "выходные" in check_slot(at(2026, 11, 1, 15, 0), NOW)               # Sunday
    assert "10:00" in check_slot(at(2026, 10, 27, 9, 30), NOW)                 # too early
    assert "18:30" in check_slot(at(2026, 10, 27, 19, 0), NOW)                 # too late
    assert "половину" in check_slot(at(2026, 10, 27, 15, 10), NOW)             # not a half-hour step
    assert "прошло" in check_slot(at(2026, 10, 26, 12, 30), NOW)               # less than an hour ahead
    assert "прошло" in check_slot(at(2026, 10, 20, 15, 0), NOW)                # in the past
    assert "два месяца" in check_slot(at(2027, 3, 3, 15, 0), NOW)              # too far


def test_parse():
    assert parse_slot("2026-10-27 15:00") == at(2026, 10, 27, 15, 0)
    assert parse_slot("завтра в 15:00") is None
    assert parse_slot("") is None
    assert parse_slot("2026-13-40 99:99") is None


def test_names():
    assert clean_name("  Анна  ") == "Анна"
    assert clean_name("Мария-Тереза О'Нил") == "Мария-Тереза О'Нил"
    assert clean_name("<script>alert(1)</script>") == "scriptalert1script"
    assert clean_name("А") == ""
    assert clean_name("") == ""
    assert len(clean_name("Я" * 200)) == 60


def test_markdown():
    assert strip_markdown("**Важно:** срок 3 дня") == "Важно: срок 3 дня"
    assert strip_markdown("## Заголовок\nТекст") == "Заголовок\nТекст"
    assert strip_markdown("* пункт один\n* пункт два") == "- пункт один\n- пункт два"
    assert strip_markdown("`код`") == "код"
    assert "\n\n\n" not in strip_markdown("а\n\n\n\nб")


def test_split():
    assert split_message("") == []
    assert split_message("коротко") == ["коротко"]
    long_text = "\n\n".join(["абзац " * 100] * 20)
    parts = split_message(long_text, limit=3500)
    assert all(len(p) <= 3500 for p in parts) and len(parts) > 1
    assert split_message("я" * 9000, limit=3500)[0] == "я" * 3500


def test_memory():
    memory = Memory(":memory:")
    for i in range(20):
        memory.add("vk", 1, "user", f"сообщение {i}")
    last = memory.history("vk", 1, limit=12)
    assert len(last) == 12 and last[-1]["content"] == "сообщение 19" and last[0]["content"] == "сообщение 8"
    assert memory.history("tg", 1) == []                                       # channels are separate
    memory.reset("vk", 1)
    assert memory.history("vk", 1) == []

    assert not memory.slot_taken("2026-10-27 15:00")
    memory.save_booking("vk", 1, "Анна", "Консультация", "2026-10-27 15:00", "https://vk.com/id1")
    assert memory.slot_taken("2026-10-27 15:00")
    assert memory.has_booking("vk", 1, "2026-10-27 15:00")
    assert not memory.has_booking("vk", 2, "2026-10-27 15:00")


def test_prompt_date():
    text = now_human(NOW)
    assert "понедельник" in text and "26.10.2026" in text and "12:00" in text


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def booking(self, booking):
        self.sent.append(booking)


def test_booking_flow():
    """The booking tool: validation, duplicates, busy slots, and exactly one notification per booking."""
    from app.core import brain as brain_module

    tomorrow = (datetime.now(TZ) + timedelta(days=1))
    while tomorrow.weekday() >= 5:
        tomorrow += timedelta(days=1)
    slot = tomorrow.strftime("%Y-%m-%d") + " 15:00"

    memory, notifier = Memory(":memory:"), FakeNotifier()
    b = brain_module.Brain.__new__(brain_module.Brain)  # no model and no files needed for this check
    b.memory, b.notifier = memory, notifier

    async def run():
        r = await b.create_booking("vk", 7, "https://vk.com/id7", {"name": "Анна", "service": "Консультация", "slot": slot})
        assert r["ok"] and r["booking_id"] == 1
        assert len(notifier.sent) == 1 and notifier.sent[0].contact == "https://vk.com/id7"

        again = await b.create_booking("vk", 7, "https://vk.com/id7", {"name": "Анна", "service": "Консультация", "slot": slot})
        assert again["ok"] and "уже" in again["note"] and len(notifier.sent) == 1

        busy = await b.create_booking("tg", 8, "@boris", {"name": "Борис", "service": "Консультация", "slot": slot})
        assert not busy["ok"] and "занято" in busy["error"] and len(notifier.sent) == 1

        bad_name = await b.create_booking("tg", 9, "@x", {"name": "?", "service": "Консультация", "slot": slot})
        assert not bad_name["ok"] and "имя" in bad_name["error"]

        bad_time = await b.create_booking("tg", 9, "@x", {"name": "Олег", "service": "Консультация", "slot": "завтра"})
        assert not bad_time["ok"] and "формат" in bad_time["error"].lower()

        weekend = tomorrow
        while weekend.weekday() != 5:
            weekend += timedelta(days=1)
        sat = await b.create_booking("tg", 9, "@x", {"name": "Олег", "service": "Консультация",
                                                     "slot": weekend.strftime("%Y-%m-%d") + " 15:00"})
        assert not sat["ok"] and "выходные" in sat["error"]
        assert len(notifier.sent) == 1

    asyncio.run(run())


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print(f"ok  {name}")
    print(f"\nAll {len(tests)} checks passed.")
