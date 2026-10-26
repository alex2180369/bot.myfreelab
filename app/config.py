"""Settings loaded from environment variables.

Secrets live only in the environment (systemd EnvironmentFile or ~/Myfreelab/.env).
Nothing in this file contains a secret.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Public address of the Google Apps Script web app that appends rows to the leads sheet.
# It is not a secret: the same address is used by the public websites.
DEFAULT_SHEETS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbymy7csfZY35SZP53O13DHC3PkIV5vDFC775UsWtwq1iznGw4myiUYPqRRUUVfVwIB7Gg/exec"
)


def _load_env_file(path: Path) -> None:
    """Fills os.environ from a KEY=VALUE file without overriding existing variables."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    vk_group_id: int | None
    vk_token: str
    tg_token: str
    owner_chat_id: str
    llm_key: str
    llm_model: str
    llm_base_url: str
    sheets_url: str
    db_path: Path
    history_limit: int = 12
    max_user_chars: int = 1000

    @property
    def vk_enabled(self) -> bool:
        return bool(self.vk_group_id and self.vk_token)

    @property
    def tg_enabled(self) -> bool:
        return bool(self.tg_token)


def load_settings() -> Settings:
    _load_env_file(ROOT / ".env")
    _load_env_file(Path.home() / "Myfreelab" / ".env")

    group_raw = "".join(ch for ch in os.getenv("VK_GROUP_ID", "") if ch.isdigit())  # accepts 123, -123, club123
    settings = Settings(
        vk_group_id=int(group_raw) if group_raw else None,
        vk_token=os.getenv("VK_TOKEN", "").strip(),
        tg_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        owner_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        llm_key=os.getenv("PROXYAPI_KEY", "").strip(),
        llm_model=os.getenv("PROXYAPI_MODEL", "").strip() or "gpt-4.1-mini",
        llm_base_url=os.getenv("PROXYAPI_BASE_URL", "https://api.proxyapi.ru/openai/v1").rstrip("/"),
        sheets_url=os.getenv("LEADS_SHEET_URL", DEFAULT_SHEETS_URL).strip(),
        db_path=Path(os.getenv("BOT_DB_PATH", str(ROOT / "data" / "bot.db"))),
    )
    if not settings.llm_key:
        raise SystemExit("PROXYAPI_KEY is empty: the bot cannot answer without a language model.")
    if not (settings.vk_enabled or settings.tg_enabled):
        raise SystemExit("Neither VK nor Telegram is configured: nothing to run.")
    return settings
