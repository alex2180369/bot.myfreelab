"""Booking rules: working hours, slot format and validation. Pure functions, easy to test."""
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Moscow")
FIRST_SLOT = time(10, 0)
LAST_SLOT = time(18, 30)
MIN_LEAD = timedelta(hours=1)
MAX_AHEAD = timedelta(days=60)

WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def now() -> datetime:
    return datetime.now(TZ)


def now_human(moment: datetime | None = None) -> str:
    """Text for the prompt: the model needs today's date to understand 'tomorrow' or 'on Friday'."""
    moment = moment or now()
    return (
        f"Сегодня {WEEKDAYS_RU[moment.weekday()]}, {moment:%d.%m.%Y}, сейчас {moment:%H:%M} по московскому времени. "
        "Формат даты для функции записи: ГГГГ-ММ-ДД ЧЧ:ММ."
    )


def parse_slot(text: str) -> datetime | None:
    try:
        parsed = datetime.strptime((text or "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return parsed.replace(tzinfo=TZ)


def check_slot(slot: datetime, moment: datetime | None = None) -> str | None:
    """Returns an explanation in Russian if the slot cannot be booked, otherwise None."""
    moment = moment or now()
    if slot <= moment + MIN_LEAD:
        return "Это время уже прошло или слишком близко: запись возможна минимум за час."
    if slot - moment > MAX_AHEAD:
        return "Записываем не дальше чем на два месяца вперёд."
    if slot.weekday() >= 5:
        return "В выходные мы не работаем: приём с понедельника по пятницу."
    if slot.time() < FIRST_SLOT or slot.time() > LAST_SLOT:
        return "Приём идёт с 10:00 до 18:30 по московскому времени."
    if slot.minute not in (0, 30):
        return "Запись идёт на начало часа или на половину часа, например 15:00 или 15:30."
    return None


def clean_name(value: str) -> str:
    """Keeps letters, spaces, dashes and apostrophes. Empty string means the name is unusable."""
    name = re.sub(r"[^\w \-'’.]", "", (value or "").strip(), flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:60] if len(name) >= 2 else ""
