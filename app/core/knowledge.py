"""Builds the system prompt from prompts/system.md and the knowledge base files in kb/."""
from pathlib import Path

from app.config import ROOT
from app.core.booking import now_human


def load_knowledge(kb_dir: Path | None = None) -> str:
    kb_dir = kb_dir or ROOT / "kb"
    parts = []
    for path in sorted(kb_dir.glob("*.md")):
        parts.append(path.read_text(encoding="utf-8").strip())
    if not parts:
        raise RuntimeError(f"Knowledge base is empty: no .md files in {kb_dir}")
    return "\n\n".join(parts)


def load_prompt_template(path: Path | None = None) -> str:
    return (path or ROOT / "prompts" / "system.md").read_text(encoding="utf-8")


def build_system_prompt(template: str, knowledge: str) -> str:
    """The date is inserted on every call: 'tomorrow' must mean tomorrow, not the day the bot started."""
    return template.replace("{{NOW}}", now_human()).replace("{{KNOWLEDGE}}", knowledge)
