"""Text helpers: the model sometimes slips Markdown into answers, messengers show it as noise."""
import re


def strip_markdown(text: str) -> str:
    out = text.replace("\r\n", "\n")
    out = re.sub(r"```.*?```", lambda m: m.group(0).strip("`"), out, flags=re.S)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out, flags=re.S)
    out = re.sub(r"__(.+?)__", r"\1", out, flags=re.S)
    out = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", out)
    out = re.sub(r"(?m)^\s*[*•]\s+", "- ", out)
    out = out.replace("`", "")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def split_message(text: str, limit: int = 3500) -> list[str]:
    """Splits a long answer by paragraphs so it fits into one messenger message."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    parts, current = [], ""
    for paragraph in text.split("\n\n"):
        candidate = (current + "\n\n" + paragraph).strip() if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(paragraph) > limit:
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        parts.append(current)
    return parts
