"""Thai wrapping, timing format, and number checks."""

from __future__ import annotations

import re

NONSPACING = {0x0E31} | set(range(0x0E34, 0x0E3B)) | set(range(0x0E47, 0x0E4F))
DIGIT_RE = re.compile(r"\d[\d,]*")
URL_RE = re.compile(r"https?://\S+")
YEAR_MIN = 2490
YEAR_MAX = 2610


def is_mark(ch: str) -> bool:
    return ord(ch) in NONSPACING


def wrap_thai(text: str, width: int) -> list[str]:
    """Wrap on spaces when possible, and never split a vowel off its base."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if " " in paragraph:
            current = ""
            for word in paragraph.split(" "):
                trial = word if not current else f"{current} {word}"
                if len(trial) <= width:
                    current = trial
                else:
                    if current:
                        lines.append(current)
                    if len(word) <= width:
                        current = word
                    else:
                        lines.extend(_wrap_chars(word, width))
                        current = ""
            if current:
                lines.append(current)
        else:
            lines.extend(_wrap_chars(paragraph, width))
    return lines or [""]


def _wrap_chars(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        if len(current) >= width and not is_mark(ch):
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    seconds_only, cs = divmod(cs, 100)
    minutes, sec = divmod(seconds_only, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}.{cs:02d}"


def srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms = int(round(seconds * 1000))
    seconds_only, ms = divmod(ms, 1000)
    minutes, sec = divmod(seconds_only, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}"


def clock(seconds: float) -> str:
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def collect_text(script: dict) -> str:
    parts = [
        script.get("title", ""),
        script.get("as_of", ""),
        script.get("description_lead", ""),
    ]
    thumb = script.get("thumbnail") or {}
    parts.extend(thumb.get(key, "") for key in ("kicker", "title", "big"))
    for section in script.get("sections", []):
        parts.append(section.get("heading", ""))
        parts.append(section.get("narration", ""))
        parts.extend(section.get("lines") or [])
    return "\n".join(parts)


def unexpected_numbers(text: str, allowed: set[str], phone_patterns: list[str]) -> list[str]:
    cleaned = URL_RE.sub(" ", text)
    for pattern in phone_patterns:
        cleaned = re.sub(pattern, " ", cleaned)
    bad: list[str] = []
    for match in DIGIT_RE.findall(cleaned):
        token = match.replace(",", "")
        if token in allowed:
            continue
        if token.isdigit() and len(token) == 4 and YEAR_MIN <= int(token) <= YEAR_MAX:
            continue
        bad.append(match)
    return bad
