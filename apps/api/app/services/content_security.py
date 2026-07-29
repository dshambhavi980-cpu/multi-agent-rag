import re
import unicodedata

CONTROL_CHARACTERS = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
INSTRUCTION_LINE = re.compile(
    r"^\s*(?:system|assistant|developer)\s*:|"
    r"\b(?:ignore|disregard|override)\b.{0,50}\b(?:instruction|prompt|rule)s?\b|"
    r"\b(?:reveal|print|return)\b.{0,40}\b(?:secret|api key|system prompt|token)s?\b",
    re.IGNORECASE,
)


def sanitize_untrusted_text(value: str) -> str:
    """Neutralize hidden controls and label likely prompt-injection lines as data."""
    normalized = unicodedata.normalize("NFKC", CONTROL_CHARACTERS.sub("", value))
    lines: list[str] = []
    for line in normalized.splitlines():
        if INSTRUCTION_LINE.search(line):
            lines.append(f"[UNTRUSTED-INSTRUCTION-TEXT] {line}")
        else:
            lines.append(line)
    return "\n".join(lines)
